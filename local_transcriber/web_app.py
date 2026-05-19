from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import downloader as downloader_module
from .services import (
    check_model_cache,
    check_ollama,
    check_ollama_model,
    check_runtime_ready,
    probe_audio_duration,
    read_install_progress,
    unique_path,
)
from .settings_store import default_settings, load_settings, save_settings
from .db import TaskRow, init_db, session_scope, utc_now
from .schemas import (
    DeleteResponse,
    SegmentEditRequest,
    SpeakerEditRequest,
    TaskConfig,
)


class ChatRequest(BaseModel):
    message: str


class CreateFromPathsRequest(BaseModel):
    paths: List[str]
    config: TaskConfig


class OpenPathRequest(BaseModel):
    path: str


class DownloadModelRequest(BaseModel):
    modelId: str

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"
TASKS_DB_PATH = OUTPUTS_DIR / "tasks.db"
STATIC_DIR = Path(__file__).resolve().parent / "web_static"

_env_file = ROOT / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(_env_file)
    except ImportError:
        for _line in _env_file.read_text().splitlines():
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())


def get_db() -> Session:
    db = session_scope()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = Path(os.environ.get("WHISPERQWEN_DB", str(TASKS_DB_PATH)))
    init_db(db_path)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    runner = None
    if not os.environ.get("WHISPERQWEN_DISABLE_RUNNER"):
        try:
            from .task_runner import TaskRunner

            runner = TaskRunner(db_path)
            runner.start()
        except Exception as exc:
            print(f"[web_app] task runner 启动失败：{exc}")
            runner = None
    app.state.runner = runner
    try:
        yield
    finally:
        if runner is not None:
            runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="WhisperQwen", version="0.2.0", lifespan=lifespan)

    @app.middleware("http")
    async def _no_cache_for_static(request, call_next):
        response = await call_next(request)
        # 前端是本地静态文件，全程毫秒级响应；强制不缓存，避免 WebKit
        # 在我们改完 JS/CSS 后还吃老版本。
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # 路由注册：domain-specific routes 拆到 routers/ 子模块，web_app.py 自己
    # 只装配。每个 router 自带 prefix（声明在装饰器里），include 时不再加。
    from .routers import health_router, models_router, qa_router
    app.include_router(health_router)
    app.include_router(models_router)
    app.include_router(qa_router)


    @app.post("/api/tasks/upload")
    async def upload_tasks(
        files: List[UploadFile] = File(...),
        config: str = Form(...),
        db: Session = Depends(get_db),
    ) -> dict:
        try:
            config_data = json.loads(config)
            cfg = TaskConfig(**config_data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=f"无效的 config 字段：{exc}")

        if not files:
            raise HTTPException(status_code=400, detail="没有上传文件")

        created: List[Dict[str, Any]] = []
        upload_dir = OUTPUTS_DIR / "uploaded_audio"
        upload_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            data = await file.read()
            if not data:
                continue
            safe_name = Path(file.filename or "audio").name
            target = unique_path(upload_dir / safe_name)
            target.write_bytes(data)

            duration = probe_audio_duration(target)
            task = TaskRow(
                audio_path=str(target),
                file_name=safe_name,
                file_size_bytes=len(data),
                duration_sec=duration,
                status="queued",
                progress=0.0,
                progress_stage="排队中",
                config=cfg.model_dump(),
            )
            db.add(task)
            db.flush()
            created.append(task.to_api())

        db.commit()
        return {"tasks": created}

    @app.post("/api/tasks/create-from-paths")
    def create_from_paths(
        payload: CreateFromPathsRequest,
        db: Session = Depends(get_db),
    ) -> dict:
        if not payload.paths:
            raise HTTPException(status_code=400, detail="没有提供文件路径")

        created: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []
        cfg = payload.config

        for raw_path in payload.paths:
            try:
                path = Path(raw_path).expanduser().resolve()
            except (OSError, RuntimeError) as exc:
                skipped.append({"path": raw_path, "reason": f"路径解析失败：{exc}"})
                continue
            if not path.exists() or not path.is_file():
                skipped.append({"path": raw_path, "reason": "文件不存在"})
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                skipped.append({"path": raw_path, "reason": f"读取大小失败：{exc}"})
                continue

            duration = probe_audio_duration(path)
            task = TaskRow(
                audio_path=str(path),
                file_name=path.name,
                file_size_bytes=size,
                duration_sec=duration,
                status="queued",
                progress=0.0,
                progress_stage="排队中",
                config=cfg.model_dump(),
            )
            db.add(task)
            db.flush()
            created.append(task.to_api())

        db.commit()
        return {"tasks": created, "skipped": skipped}

    @app.get("/api/tasks")
    def list_tasks(status: Optional[str] = None, db: Session = Depends(get_db)) -> dict:
        stmt = select(TaskRow).order_by(TaskRow.created_at.desc())
        if status:
            stmt = stmt.where(TaskRow.status == status)
        rows = db.execute(stmt).scalars().all()
        return {"tasks": [row.to_api() for row in rows]}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str, db: Session = Depends(get_db)) -> dict:
        task = db.get(TaskRow, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task.to_api()

    @app.delete("/api/tasks/{task_id}", response_model=DeleteResponse)
    def delete_task(
        task_id: str, delete_outputs: bool = False, db: Session = Depends(get_db)
    ) -> DeleteResponse:
        task = db.get(TaskRow, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        deleted = False
        if delete_outputs and task.outputs:
            out_dir = task.outputs.get("dir") if isinstance(task.outputs, dict) else None
            if out_dir:
                out_path = Path(out_dir)
                if out_path.exists() and OUTPUTS_DIR in out_path.resolve().parents:
                    shutil.rmtree(out_path, ignore_errors=True)
                    deleted = True
        db.delete(task)
        db.commit()
        return DeleteResponse(ok=True, deletedOutputs=deleted)

    @app.post("/api/tasks/clear-completed")
    def clear_completed(db: Session = Depends(get_db)) -> dict:
        rows = (
            db.execute(select(TaskRow).where(TaskRow.status.in_(["done", "failed", "stopped"])))
            .scalars()
            .all()
        )
        for row in rows:
            db.delete(row)
        db.commit()
        return {"ok": True, "removed": len(rows)}

    @app.post("/api/tasks/{task_id}/edits/speaker")
    def edit_speaker(
        task_id: str, payload: SpeakerEditRequest, db: Session = Depends(get_db)
    ) -> dict:
        task = db.get(TaskRow, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        edits = dict(task.edits or {"speakerLabels": {}, "segmentOverrides": {}})
        speaker_labels = dict(edits.get("speakerLabels") or {})
        speaker_labels[payload.speakerId] = payload.label
        edits["speakerLabels"] = speaker_labels
        edits.setdefault("segmentOverrides", {})
        task.edits = edits
        db.commit()
        return {"ok": True, "edits": task.edits}

    @app.post("/api/tasks/{task_id}/edits/segment")
    def edit_segment(
        task_id: str, payload: SegmentEditRequest, db: Session = Depends(get_db)
    ) -> dict:
        task = db.get(TaskRow, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        edits = dict(task.edits or {"speakerLabels": {}, "segmentOverrides": {}})
        overrides = dict(edits.get("segmentOverrides") or {})
        overrides[payload.segmentId] = payload.text
        edits["segmentOverrides"] = overrides
        edits.setdefault("speakerLabels", {})
        task.edits = edits
        db.commit()
        return {"ok": True, "edits": task.edits}

    @app.post("/api/tasks/{task_id}/retry")
    def retry_task(task_id: str, db: Session = Depends(get_db)) -> dict:
        task = db.get(TaskRow, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task.status not in {"failed", "stopped"}:
            raise HTTPException(
                status_code=400,
                detail=f"只能重试 failed / stopped 任务，当前 status={task.status}",
            )
        if not task.audio_path or not Path(task.audio_path).exists():
            raise HTTPException(
                status_code=400,
                detail="原始音频文件不存在（可能已被移动或删除）",
            )
        task.status = "queued"
        task.progress = 0.0
        task.progress_stage = "排队中"
        task.error_message = None
        task.started_at = None
        task.completed_at = None
        task.transcript = None
        task.summary_text = None
        task.chat_context_digest = None
        task.chat_messages = []
        task.outputs = None
        db.commit()
        return task.to_api()

    @app.post("/api/tasks/{task_id}/stop")
    def stop_task(task_id: str, db: Session = Depends(get_db)) -> dict:
        task = db.get(TaskRow, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task.status in {"done", "failed", "stopped"}:
            return {"ok": True, "status": task.status}
        runner = app.state.runner if hasattr(app.state, "runner") else None
        if runner is not None:
            runner.request_stop(task_id)
        task.status = "stopped"
        task.progress_stage = "已停止"
        task.completed_at = utc_now()
        db.commit()
        return {"ok": True, "status": "stopped"}

    @app.get("/api/tasks/{task_id}/file")
    def get_task_file(task_id: str, kind: str = "markdown", db: Session = Depends(get_db)):
        task = db.get(TaskRow, task_id)
        if not task or not task.outputs:
            raise HTTPException(status_code=404, detail="找不到任务输出")
        outputs = task.outputs if isinstance(task.outputs, dict) else {}
        key_map = {"markdown": "markdownPath", "json": "jsonPath", "srt": "srtPath"}
        if kind not in key_map:
            raise HTTPException(status_code=400, detail="kind 必须是 markdown / json / srt")
        path = outputs.get(key_map[kind])
        if not path or not Path(path).exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(path)

    @app.delete("/api/tasks")
    def delete_all_tasks(db: Session = Depends(get_db)) -> dict:
        rows = db.execute(select(TaskRow)).scalars().all()
        for row in rows:
            db.delete(row)
        db.commit()
        return {"ok": True, "removed": len(rows)}

    @app.get("/api/settings")
    def get_settings() -> dict:
        return load_settings()

    @app.put("/api/settings")
    def put_settings(payload: Dict[str, Any] = Body(...)) -> dict:
        merged = {**default_settings(), **load_settings(), **payload}
        save_settings(merged)
        return load_settings()

    @app.post("/api/open-path")
    def open_path(payload: OpenPathRequest, db: Session = Depends(get_db)) -> dict:
        try:
            target = Path(payload.path).expanduser().resolve()
        except (OSError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=f"路径解析失败：{exc}")
        if not target.exists():
            raise HTTPException(status_code=404, detail="路径不存在")

        outputs_root = OUTPUTS_DIR.resolve()
        allowed = False
        try:
            target.relative_to(outputs_root)
            allowed = True
        except ValueError:
            pass

        if not allowed:
            audio_paths = {
                Path(row.audio_path).resolve()
                for row in db.execute(select(TaskRow)).scalars().all()
                if row.audio_path
            }
            if target in audio_paths or target.parent in {p.parent for p in audio_paths}:
                allowed = True

        if not allowed:
            raise HTTPException(status_code=403, detail="路径不在允许范围内")

        try:
            subprocess.run(["open", str(target)], check=False, timeout=5)
        except (OSError, subprocess.SubprocessError) as exc:
            raise HTTPException(status_code=500, detail=f"无法打开：{exc}")
        return {"ok": True, "path": str(target)}

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        html_file = STATIC_DIR / "index.html"
        if html_file.exists():
            return HTMLResponse(html_file.read_text(encoding="utf-8"))
        return HTMLResponse(
            "<h1>WhisperQwen backend up</h1><p>前端静态文件还没生成。</p>"
        )

    return app


app = create_app()
