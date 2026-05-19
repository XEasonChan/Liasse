from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def new_task_id() -> str:
    return secrets.token_urlsafe(9)


def utc_now() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class TaskRow(Base):
    __tablename__ = "tasks"

    id = Column(String(32), primary_key=True, default=new_task_id)
    audio_path = Column(Text, nullable=False)
    file_name = Column(Text, nullable=False)
    file_size_bytes = Column(Integer, nullable=False, default=0)
    duration_sec = Column(Float, nullable=True)

    status = Column(String(16), nullable=False, default="queued")
    progress = Column(Float, nullable=False, default=0.0)
    progress_stage = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    config = Column(JSON, nullable=False, default=dict)
    outputs = Column(JSON, nullable=True)
    transcript = Column(JSON, nullable=True)
    edits = Column(JSON, nullable=False, default=lambda: {"speakerLabels": {}, "segmentOverrides": {}})
    chat_messages = Column(JSON, nullable=False, default=list)
    chat_context_digest = Column(Text, nullable=True)
    summary_text = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utc_now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    elapsed_sec = Column(Float, nullable=True)

    def to_api(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "audioPath": self.audio_path,
            "fileName": self.file_name,
            "fileSizeBytes": self.file_size_bytes,
            "durationSec": self.duration_sec,
            "status": self.status,
            "progress": self.progress,
            "progressStage": self.progress_stage,
            "errorMessage": self.error_message,
            "config": self.config or {},
            "outputs": self.outputs,
            "transcript": self.transcript,
            "edits": self.edits or {"speakerLabels": {}, "segmentOverrides": {}},
            "chatMessages": self.chat_messages or [],
            "chatContextDigest": self.chat_context_digest,
            "summaryText": self.summary_text,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "elapsedSec": self.elapsed_sec,
        }


class TaskConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    asrModel: Literal["Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-1.7B"] = "Qwen/Qwen3-ASR-0.6B"
    language: Literal["Chinese", "English", "Cantonese", "auto"] = "Chinese"
    diarize: bool = True
    numSpeakers: Optional[int] = 2
    autoSegment: bool = True
    summarize: bool = False
    enableChat: bool = True
    summaryModel: str = "qwen3:4b"


class SpeakerEditRequest(BaseModel):
    speakerId: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1, max_length=64)


class SegmentEditRequest(BaseModel):
    segmentId: str = Field(..., min_length=1)
    text: str = Field(...)


class DeleteResponse(BaseModel):
    ok: bool
    deletedOutputs: bool


_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def init_db(db_path: Path) -> Engine:
    global _engine, _SessionLocal
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    _engine = create_engine(url, future=True, connect_args={"check_same_thread": False})
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(_engine)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("数据库还没初始化，先调用 init_db()")
    return _engine


def session_scope() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("数据库还没初始化，先调用 init_db()")
    return _SessionLocal()


__all__ = [
    "Base",
    "TaskRow",
    "TaskConfig",
    "SpeakerEditRequest",
    "SegmentEditRequest",
    "DeleteResponse",
    "init_db",
    "session_scope",
    "new_task_id",
    "utc_now",
]
