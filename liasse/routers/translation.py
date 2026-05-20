"""翻译 + 词库 API。

- GET    /api/glossaries          列出所有词库名
- GET    /api/glossaries/{name}   取单个词库
- POST   /api/glossaries          新建词库 (body = Glossary)
- PUT    /api/glossaries/{name}   覆盖词库 (path 必须与 body.name 一致)
- DELETE /api/glossaries/{name}   删除

- POST   /api/tasks/{id}/translate   触发翻译,持久化到 TaskRow.translations

错误码:404 任务/词库不存在,409 任务未 done,400 词库名非法/payload 不匹配,
502 Ollama 失败 (含 JSON 解析失败)。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import TaskRow, get_db
from ..exporters import export_markdown_bilingual
from ..glossary_store import GlossaryStore
from ..models import TranscriptSegment
from ..ollama_lifecycle import OllamaClient, OllamaError
from ..schemas import Glossary, TranslationRequest, TranslationResult
from ..translate import now_iso, translate_segments

logger = logging.getLogger(__name__)
router = APIRouter()


def _store() -> GlossaryStore:
    """惰性取 web_app.OUTPUTS_DIR — 避免 import 时序问题 / 测试 monkeypatch。"""
    from .. import web_app
    return GlossaryStore(Path(web_app.OUTPUTS_DIR) / "glossaries")


@router.get("/api/glossaries")
def list_glossaries():
    return {"names": _store().list_names()}


@router.get("/api/glossaries/{name}")
def get_glossary(name: str):
    try:
        g = _store().get(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if g is None:
        raise HTTPException(status_code=404, detail="glossary not found")
    return g.model_dump()


@router.post("/api/glossaries")
def create_glossary(payload: Glossary):
    try:
        _store().put(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "name": payload.name}


@router.put("/api/glossaries/{name}")
def update_glossary(name: str, payload: Glossary):
    if payload.name != name:
        raise HTTPException(status_code=400, detail="payload.name must match path")
    try:
        _store().put(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "name": payload.name}


@router.delete("/api/glossaries/{name}")
def delete_glossary(name: str):
    try:
        ok = _store().delete(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="glossary not found")
    return {"ok": True}


@router.post("/api/tasks/{task_id}/translate")
def translate_task(
    task_id: str,
    req: TranslationRequest,
    db: Session = Depends(get_db),
):
    task = db.get(TaskRow, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status != "done":
        raise HTTPException(status_code=409, detail="task not done yet")

    transcript = task.transcript or {}
    segments = transcript.get("segments") or []
    if not segments:
        raise HTTPException(status_code=409, detail="task has no segments")

    glossary: Optional[Glossary] = None
    if req.glossaryName:
        try:
            glossary = _store().get(req.glossaryName)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if glossary is None:
            raise HTTPException(
                status_code=404, detail=f"glossary {req.glossaryName!r} not found",
            )

    ollama = OllamaClient()
    try:
        translated = translate_segments(
            segments=segments,
            target=req.target,
            glossary=glossary,
            ollama=ollama,
            model=req.model,
        )
    except OllamaError as exc:
        logger.warning("translation: ollama down: %s", exc)
        raise HTTPException(status_code=502, detail=f"ollama not available: {exc}")
    except ValueError as exc:
        # translate.py JSON parse failure
        logger.warning("translation: model returned malformed JSON: %s", exc)
        raise HTTPException(status_code=502, detail=f"translation failed: {exc}")

    result = TranslationResult(
        target=req.target,
        model=req.model,
        glossaryName=req.glossaryName,
        segments=translated,
        generatedAt=now_iso(),
    )

    existing = dict(task.translations or {})
    existing[req.target] = result.model_dump()
    task.translations = existing
    db.commit()
    return result.model_dump()


@router.get("/api/tasks/{task_id}/export-bilingual")
def export_bilingual(
    task_id: str,
    target: str = Query("English"),
    db: Session = Depends(get_db),
):
    """导出双语 Markdown。task.translations[target] 必须存在(用户先点过翻译)。"""
    task = db.get(TaskRow, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    translations = task.translations or {}
    if target not in translations:
        raise HTTPException(
            status_code=409,
            detail=f"该任务没有 {target} 译文,请先在详情页点「翻译」",
        )
    segs_raw = (task.transcript or {}).get("segments") or []
    if not segs_raw:
        raise HTTPException(status_code=409, detail="任务无逐字稿")

    # 应用 edits.segmentOverrides
    overrides = (task.edits or {}).get("segmentOverrides") or {}
    segments = []
    for s in segs_raw:
        sid = s.get("id")
        text = overrides.get(str(sid)) or overrides.get(sid) or s.get("text", "")
        segments.append(TranscriptSegment(
            start=s.get("start"),
            end=s.get("end"),
            text=text,
            speaker=s.get("speaker") or "SPEAKER_00",
        ))

    from .. import web_app
    out_dir = Path(web_app.OUTPUTS_DIR) / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(task.file_name or task.audio_path or "transcript").stem or "transcript"
    out_path = out_dir / f"{stem}-bilingual-{target}.md"
    export_markdown_bilingual(
        out_path,
        Path(task.audio_path or "unknown.audio"),
        segments,
        translations[target],
    )
    return FileResponse(
        str(out_path),
        media_type="text/markdown",
        filename=out_path.name,
    )
