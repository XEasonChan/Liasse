"""双语 MD 导出单测。"""
from __future__ import annotations

from pathlib import Path

from liasse.exporters import export_markdown_bilingual
from liasse.models import TranscriptSegment


def test_bilingual_md_contains_both_languages(tmp_path: Path):
    audio = Path("/tmp/sample.m4a")
    segs = [
        TranscriptSegment(start=0, end=5, text="原告反对", speaker="SPEAKER_00"),
        TranscriptSegment(start=5, end=10, text="被告同意", speaker="SPEAKER_01"),
    ]
    translation = {
        "target": "English",
        "segments": [
            {"id": 1, "translation": "Plaintiff objects"},
            {"id": 2, "translation": "Defendant agrees"},
        ],
    }
    out = tmp_path / "bi.md"
    export_markdown_bilingual(out, audio, segs, translation)
    body = out.read_text(encoding="utf-8")
    assert "原告反对" in body
    assert "Plaintiff objects" in body
    assert "被告同意" in body
    assert "Defendant agrees" in body
    assert "English" in body


def test_bilingual_md_handles_missing_translation_for_segment(tmp_path: Path):
    """模型偷懒,只译一半 → 没译的段不输出 译文行,不崩。"""
    segs = [
        TranscriptSegment(start=0, end=5, text="A", speaker="S0"),
        TranscriptSegment(start=5, end=10, text="B", speaker="S1"),
    ]
    translation = {"target": "English", "segments": [{"id": 1, "translation": "T1"}]}
    out = tmp_path / "half.md"
    export_markdown_bilingual(out, Path("/tmp/x.m4a"), segs, translation)
    body = out.read_text()
    assert "T1" in body
    # 第二段没有英文,但不能崩


def test_bilingual_md_empty_translation(tmp_path: Path):
    segs = [TranscriptSegment(start=0, end=5, text="x", speaker="A")]
    out = tmp_path / "empty.md"
    export_markdown_bilingual(out, Path("/tmp/x.m4a"), segs, {"target": "English", "segments": []})
    body = out.read_text()
    assert "原文" in body and "x" in body
