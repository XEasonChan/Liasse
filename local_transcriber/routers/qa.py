"""问答 + 摘要路由（task 完成后的"消费侧"）。

- POST /api/tasks/:id/summary  — 重新生成分层摘要（L1+L2），结果写回
                                 row.summary_text。同步调用，可能跑几分钟。
- POST /api/tasks/:id/chat     — SSE 流式问答。BM25 检索 + LLM 流式输出
                                 delta；流结束后把 user/assistant 消息追加
                                 到 row.chat_messages。

两条路由都依赖 row.transcript.segments 已就绪（含 partial=True 的情况
也允许 — 用户希望即使 diarization 还在跑也能问答）。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import TaskRow, session_scope


router = APIRouter()


class ChatRequest(BaseModel):
    message: str


def get_db() -> Session:
    db = session_scope()
    try:
        yield db
    finally:
        db.close()


@router.post("/api/tasks/{task_id}/summary")
def regenerate_summary(task_id: str, db: Session = Depends(get_db)) -> dict:
    from ..memory_monitor import MemoryBudget
    from ..models import TranscriptSegment
    from ..summary_pipeline import analyze as analyze_transcript

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


@router.post("/api/tasks/{task_id}/chat")
def chat_stream(task_id: str, payload: ChatRequest, db: Session = Depends(get_db)):
    from ..memory_monitor import MemoryBudget
    from ..qa_engine import QAEngine, build_index_for_task

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
