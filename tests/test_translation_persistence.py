"""TaskRow.translations 列存读 + init_db 老库迁移。"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from liasse.db import Base, TaskRow, _ensure_added_columns, init_db


def test_taskrow_has_translations_column(tmp_path: Path):
    db_file = tmp_path / "t.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        row = TaskRow(
            id="t1",
            audio_path="/x.m4a",
            file_name="x.m4a",
            file_size_bytes=0,
            status="done",
            config={},
        )
        row.translations = {"English": {"target": "English", "segments": []}}
        s.add(row)
        s.commit()
    with Session() as s:
        got = s.get(TaskRow, "t1")
        assert got.translations == {"English": {"target": "English", "segments": []}}


def test_init_db_adds_translations_column_to_legacy_db(tmp_path: Path):
    """模拟老库:先建一个没有 translations 列的 tasks 表,再跑 init_db,
    应该自动 ALTER 加列。"""
    db_file = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    # 手建一个不带 translations 列的 tasks 表 (legacy 形态)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE tasks ("
            "id VARCHAR(32) PRIMARY KEY, "
            "audio_path TEXT NOT NULL, "
            "file_name TEXT NOT NULL, "
            "file_size_bytes INTEGER NOT NULL DEFAULT 0, "
            "status VARCHAR(16) NOT NULL DEFAULT 'queued', "
            "progress FLOAT NOT NULL DEFAULT 0.0, "
            "config JSON NOT NULL DEFAULT '{}', "
            "edits JSON NOT NULL DEFAULT '{}', "
            "chat_messages JSON NOT NULL DEFAULT '[]', "
            "created_at DATETIME NOT NULL"
            ")"
        ))
    cols_before = {c["name"] for c in inspect(engine).get_columns("tasks")}
    assert "translations" not in cols_before
    engine.dispose()

    # init_db should ALTER
    init_db(db_file)
    eng2 = create_engine(f"sqlite:///{db_file}", future=True)
    cols_after = {c["name"] for c in inspect(eng2).get_columns("tasks")}
    assert "translations" in cols_after


def test_translations_defaults_to_none(tmp_path: Path):
    db_file = tmp_path / "fresh.db"
    init_db(db_file)
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        row = TaskRow(
            id="t2",
            audio_path="/x.m4a",
            file_name="x.m4a",
            file_size_bytes=0,
            status="queued",
            config={},
        )
        s.add(row)
        s.commit()
    with Session() as s:
        got = s.get(TaskRow, "t2")
        assert got.translations is None
        api = got.to_api()
        # to_api 把 None 映射成 {} 方便前端
        assert api["translations"] == {}
