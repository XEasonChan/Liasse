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

    @app.get("/api/health")
    def health() -> dict:
        from .hf_paths import is_downloaded
        asr_ok = is_downloaded("Qwen/Qwen3-ASR-0.6B")
        aligner_ok = is_downloaded("Qwen/Qwen3-ForcedAligner-0.6B")
        pyannote_ok = is_downloaded("pyannote/speaker-diarization-community-1")
        ollama_up = check_ollama()
        qwen4b_ok = check_ollama_model("qwen3:4b") if ollama_up else False
        runtime_ready = check_runtime_ready()
        hf_token_set = bool(
            os.environ.get("HF_TOKEN")
            or os.environ.get("PYANNOTE_AUTH_TOKEN")
            or os.environ.get("HUGGINGFACE_TOKEN")
        )
        try:
            usage = shutil.disk_usage(str(OUTPUTS_DIR))
            disk_free_gb = round(usage.free / (1024 ** 3), 1)
        except OSError:
            disk_free_gb = None

        blockers: List[str] = []
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            blockers.append("ffmpeg")
        if not asr_ok:
            blockers.append("asr_model")
        if not runtime_ready:
            blockers.append("runtime")

        return {
            "ok": not blockers,
            "blockers": blockers,
            "runtime_ready": runtime_ready,
            "checks": {
                "ffmpeg": bool(shutil.which("ffmpeg")),
                "ffprobe": bool(shutil.which("ffprobe")),
                "ollama": ollama_up,
                "hf_token": hf_token_set,
                "asr_model": asr_ok,
                "aligner_model": aligner_ok,
                "pyannote_model": pyannote_ok,
                "qwen3_4b_model": qwen4b_ok,
                "runtime_ready": runtime_ready,
                "disk_free_gb": disk_free_gb,
                "models": check_model_cache(),
            },
        }

    @app.get("/api/install/progress")
    def install_progress() -> dict:
        return read_install_progress()

    @app.get("/api/models")
    def models() -> dict:
        from .hf_paths import is_downloaded
        items = [
            {
                "id": "Qwen/Qwen3-ASR-0.6B",
                "kind": "asr",
                "downloaded": is_downloaded("Qwen/Qwen3-ASR-0.6B"),
                "label": "Qwen3-ASR 0.6B（默认转录）",
                "sizeBytes": 1_200_000_000,
                "required": True,
                "bundled": True,
                "downloadCommand": (
                    "venv/bin/python -c \"from huggingface_hub import snapshot_download; "
                    "snapshot_download('Qwen/Qwen3-ASR-0.6B')\""
                ),
                "downloadHint": "默认安装应已自带。如缺失，运行下面的命令重新下载。",
            },
            {
                "id": "Qwen/Qwen3-ForcedAligner-0.6B",
                "kind": "aligner",
                "downloaded": is_downloaded("Qwen/Qwen3-ForcedAligner-0.6B"),
                "label": "Qwen3 时间戳对齐器",
                "sizeBytes": 1_300_000_000,
                "required": False,
                "bundled": True,
                "downloadCommand": (
                    "venv/bin/python -c \"from huggingface_hub import snapshot_download; "
                    "snapshot_download('Qwen/Qwen3-ForcedAligner-0.6B')\""
                ),
                "downloadHint": "默认安装应已自带。如缺失，自动分段需要它，运行下面命令补回。",
            },
            {
                "id": "Qwen/Qwen3-ASR-1.7B",
                "kind": "asr",
                "downloaded": is_downloaded("Qwen/Qwen3-ASR-1.7B"),
                "label": "Qwen3-ASR 1.7B（高质量，可选）",
                "sizeBytes": 3_400_000_000,
                "required": False,
                "bundled": False,
                "downloadCommand": (
                    "venv/bin/python -c \"from huggingface_hub import snapshot_download; "
                    "snapshot_download('Qwen/Qwen3-ASR-1.7B')\""
                ),
                "downloadHint": "比 0.6B 慢约 50% 但识别质量更高。下载约 3.4 GB，需要 Hugging Face 账户。",
            },
            {
                "id": "pyannote/speaker-diarization-community-1",
                "kind": "diarization",
                "downloaded": is_downloaded("pyannote/speaker-diarization-community-1"),
                "label": "pyannote 发言人识别 4.x",
                "sizeBytes": 600_000_000,
                "required": False,
                "bundled": False,
                "downloadCommand": (
                    "# 1. 在浏览器同意许可：https://huggingface.co/pyannote/speaker-diarization-community-1\n"
                    "# 2. 在 .env 填入 HF_TOKEN=hf_xxx\n"
                    "venv/bin/python -c \"from huggingface_hub import snapshot_download; import os; "
                    "snapshot_download('pyannote/speaker-diarization-community-1', token=os.environ.get('HF_TOKEN'))\""
                ),
                "downloadHint": "「发言人识别」功能需要这个模型。约 600 MB。首次下载前需要在 Hugging Face 网页同意一次许可。",
            },
            {
                "id": "qwen3:4b",
                "kind": "llm",
                "downloaded": check_ollama_model("qwen3:4b"),
                "label": "Qwen3 4B（总结 / AI Chat）",
                "sizeBytes": 2_500_000_000,
                "required": False,
                "bundled": False,
                "downloadCommand": "ollama pull qwen3:4b",
                "downloadHint": "「生成总结」和「AI Chat」都用这个本地 LLM。约 2.5 GB。先确认 Ollama 已启动（brew install ollama && ollama serve）。",
            },
            {
                "id": "qwen3:8b",
                "kind": "llm",
                "downloaded": check_ollama_model("qwen3:8b"),
                "label": "Qwen3 8B（更高质量，可选）",
                "sizeBytes": 5_200_000_000,
                "required": False,
                "bundled": False,
                "downloadCommand": "ollama pull qwen3:8b",
                "downloadHint": "比 4B 更慢但回答更细致。下载约 5.2 GB，运行时 6 GB+ 内存。",
            },
        ]
        return {"models": items}

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

    @app.post("/api/tasks/{task_id}/summary")
    def regenerate_summary(task_id: str, db: Session = Depends(get_db)) -> dict:
        from .memory_monitor import MemoryBudget
        from .models import TranscriptSegment
        from .summary_pipeline import analyze as analyze_transcript

        task = db.get(TaskRow, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if not task.transcript or not task.transcript.get("segments"):
            raise HTTPException(status_code=400, detail="还没有逐字稿可用于总结")

        edits = task.edits or {}
        labels = edits.get("speakerLabels") or {}
        overrides = edits.get("segmentOverrides") or {}
        segments: List[TranscriptSegment] = []
        for seg in task.transcript["segments"]:
            spk_raw = seg.get("speaker", "SPEAKER_00")
            spk = labels.get(spk_raw) or spk_raw
            text = overrides.get(seg.get("id", ""), seg.get("text", ""))
            segments.append(TranscriptSegment(
                start=seg.get("start"),
                end=seg.get("end"),
                text=text,
                speaker=spk,
                source="task",
            ))

        outputs = task.outputs or {}
        output_dir = Path(outputs.get("dir") or "outputs") / task_id
        user_pref = (task.config or {}).get("userPref") or "auto"

        try:
            analysis = analyze_transcript(
                segments=segments,
                output_dir=output_dir,
                task_id=task_id,
                budget=MemoryBudget.detect(),
                user_pref=user_pref,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        task.summary_text = analysis.summary_markdown
        db.commit()
        return {
            "summary": analysis.summary_markdown,
            "model": f"{analysis.model_used_l1}+{analysis.model_used_l2}",
        }

    @app.post("/api/tasks/{task_id}/chat")
    def chat_stream(task_id: str, payload: ChatRequest, db: Session = Depends(get_db)):
        from .memory_monitor import MemoryBudget
        from .qa_engine import QAEngine, build_index_for_task

        task = db.get(TaskRow, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if not task.transcript or not task.transcript.get("segments"):
            raise HTTPException(status_code=400, detail="还没有逐字稿可用于问答")

        index = build_index_for_task(task)
        if index is None:
            raise HTTPException(status_code=400, detail="逐字稿为空，无法建立检索索引")

        history = list(task.chat_messages or [])
        user_message = payload.message
        ts_request = datetime.utcnow().isoformat()
        user_pref = (task.config or {}).get("userPref") or "auto"
        engine = QAEngine(index=index, budget=MemoryBudget.detect(), user_pref=user_pref)

        def event_stream():
            collected: List[str] = []
            try:
                for delta in engine.answer(user_message, history=history):
                    collected.append(delta)
                    yield f"event: delta\ndata: {json.dumps(delta, ensure_ascii=False)}\n\n"
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps(str(exc), ensure_ascii=False)}\n\n"
                return

            answer = "".join(collected).strip()
            try:
                with session_scope() as s2:
                    row = s2.get(TaskRow, task_id)
                    if row is not None:
                        msgs = list(row.chat_messages or [])
                        msgs.append({"role": "user", "content": user_message, "ts": ts_request})
                        if answer:
                            msgs.append({
                                "role": "assistant",
                                "content": answer,
                                "ts": datetime.utcnow().isoformat(),
                            })
                        row.chat_messages = msgs
                        s2.commit()
            except Exception:
                pass
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

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

    @app.post("/api/models/download")
    def start_model_download(payload: DownloadModelRequest) -> dict:
        try:
            job = downloader_module.start_download(payload.modelId)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "jobId": job.job_id,
            "modelId": job.model_id,
            "kind": job.kind,
            "status": job.status,
        }

    @app.get("/api/models/download/{job_id}/stream")
    def stream_download(job_id: str):
        job = downloader_module.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="下载任务不存在")

        def event_stream():
            yield (
                f"event: snapshot\ndata: "
                f"{json.dumps({'progress': job.progress, 'bytesDone': job.bytes_done, 'bytesTotal': job.bytes_total, 'status': job.status}, ensure_ascii=False)}\n\n"
            )
            while True:
                try:
                    msg = job.events.get(timeout=30.0)
                except Exception:
                    if job.status in {"done", "failed"}:
                        break
                    yield "event: ping\ndata: {}\n\n"
                    continue
                evt = msg.pop("event")
                if evt == "__close__":
                    break
                yield f"event: {evt}\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/models/download/{job_id}/cancel")
    def cancel_download(job_id: str) -> dict:
        ok = downloader_module.cancel_job(job_id)
        return {"ok": ok}

    @app.post("/api/ollama/start")
    def start_ollama() -> dict:
        if check_ollama():
            return {"started": True, "alreadyRunning": True, "message": "Ollama 已在运行"}

        if not shutil.which("ollama"):
            raise HTTPException(
                status_code=400,
                detail="找不到 ollama 二进制（请先 brew install ollama）",
            )

        log_path = OUTPUTS_DIR / "ollama.log"
        env = {**os.environ, "OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0"}
        try:
            with open(log_path, "ab") as log_f:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                )
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"启动失败：{exc}")

        import time as _time

        deadline = _time.time() + 8.0
        while _time.time() < deadline:
            if check_ollama():
                return {
                    "started": True,
                    "alreadyRunning": False,
                    "message": "Ollama 已启动",
                    "logPath": str(log_path),
                }
            _time.sleep(0.3)
        raise HTTPException(status_code=504, detail="Ollama 启动超时（8 秒）")

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
