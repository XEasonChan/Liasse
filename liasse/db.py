from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, create_engine, inspect, text
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
    translations = Column(JSON, nullable=True, default=None)

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
            "translations": self.translations or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "elapsedSec": self.elapsed_sec,
        }


_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _ensure_added_columns(engine: Engine) -> None:
    """SQLite 不支持 Base.metadata.create_all 往已存在的表加新列。
    手动 ALTER 检测 + 兼容老库。新增列必须先在这里登记。
    """
    insp = inspect(engine)
    if "tasks" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("tasks")}
    additions: list[tuple[str, str]] = [
        ("translations", "ALTER TABLE tasks ADD COLUMN translations JSON"),
    ]
    with engine.begin() as conn:
        for col, ddl in additions:
            if col not in existing:
                conn.execute(text(ddl))


def init_db(db_path: Path) -> Engine:
    global _engine, _SessionLocal
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    _engine = create_engine(url, future=True, connect_args={"check_same_thread": False})
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(_engine)
    _ensure_added_columns(_engine)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("数据库还没初始化，先调用 init_db()")
    return _engine


def session_scope() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("数据库还没初始化，先调用 init_db()")
    return _SessionLocal()


def get_db():
    """FastAPI Depends() 用的 generator：yield 一个 Session，请求结束 close。

    web_app.py 的 tasks routes 和 routers/qa.py 都用这个，保证它们共享同一个
    工厂（而不是各自定义同名函数）。
    """
    db = session_scope()
    try:
        yield db
    finally:
        db.close()


__all__ = [
    "Base",
    "TaskRow",
    "init_db",
    "get_engine",
    "session_scope",
    "get_db",
    "new_task_id",
    "utc_now",
]
