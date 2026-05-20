"""GlossaryStore CRUD."""
from __future__ import annotations

from pathlib import Path

import pytest

from liasse.glossary_store import GlossaryStore
from liasse.schemas import Glossary, GlossaryEntry


@pytest.fixture
def store(tmp_path: Path) -> GlossaryStore:
    return GlossaryStore(tmp_path / "glossaries")


def test_create_and_list(store: GlossaryStore):
    g = Glossary(name="法律", entries=[GlossaryEntry(source="原告", target="plaintiff")])
    store.put(g)
    assert "法律" in store.list_names()


def test_get_returns_glossary(store: GlossaryStore):
    g = Glossary(name="t", entries=[GlossaryEntry(source="术语", target="term")])
    store.put(g)
    got = store.get("t")
    assert got is not None
    assert got.entries[0].source == "术语"


def test_get_missing_returns_none(store: GlossaryStore):
    assert store.get("nope") is None


def test_delete(store: GlossaryStore):
    store.put(Glossary(name="x"))
    assert store.delete("x") is True
    assert store.get("x") is None
    assert store.delete("x") is False


def test_invalid_name_rejected(store: GlossaryStore):
    with pytest.raises(ValueError):
        store.put(Glossary(name="../etc/passwd"))


def test_overwrite_replaces_atomically(store: GlossaryStore):
    g1 = Glossary(name="t", entries=[GlossaryEntry(source="a", target="A")])
    store.put(g1)
    g2 = Glossary(name="t", entries=[GlossaryEntry(source="b", target="B")])
    store.put(g2)
    got = store.get("t")
    assert got is not None
    assert len(got.entries) == 1
    assert got.entries[0].source == "b"


def test_list_skips_hidden_tmp_files(store: GlossaryStore, tmp_path: Path):
    """put() 用 tmpfile + rename,中途崩可能留 .gloss-xxxx.json — 不要列出来。"""
    (store.root / ".gloss-abc.json").write_text("{}")
    store.put(Glossary(name="real"))
    assert store.list_names() == ["real"]
