"""translate.py 单元测试 — mock Ollama,无网络。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from liasse.schemas import Glossary, GlossaryEntry
from liasse.translate import (
    build_translate_prompt,
    translate_segments,
)


def _seg(i: int, text: str, speaker: str = "SPEAKER_00") -> dict:
    return {"id": i, "start": float(i), "end": float(i + 1), "speaker": speaker, "text": text}


def test_prompt_contains_glossary_terms():
    g = Glossary(
        name="t",
        entries=[
            GlossaryEntry(source="原告", target="plaintiff"),
            GlossaryEntry(source="被告", target="defendant", domain="法律"),
        ],
    )
    prompt = build_translate_prompt([_seg(1, "原告反对")], target="English", glossary=g)
    assert "plaintiff" in prompt
    assert "原告" in prompt
    # 领域标签也要带上,让模型有上下文
    assert "法律" in prompt


def test_prompt_without_glossary_has_no_glossary_block():
    prompt = build_translate_prompt([_seg(1, "hi")], target="Chinese", glossary=None)
    assert "Glossary" not in prompt


def test_prompt_includes_target_language_directive():
    p_en = build_translate_prompt([_seg(1, "你好")], target="English", glossary=None)
    p_zh = build_translate_prompt([_seg(1, "hi")], target="Chinese", glossary=None)
    assert "English" in p_en
    assert "中文" in p_zh


def test_translate_segments_parses_valid_json():
    mock = MagicMock()
    mock.generate.return_value = json.dumps({
        "translations": [{"id": 1, "translation": "Plaintiff objects"}]
    })
    result = translate_segments(
        segments=[_seg(1, "原告反对")],
        target="English",
        glossary=None,
        ollama=mock,
        model="qwen3:4b",
        batch_size=20,
    )
    assert len(result) == 1
    assert result[0].translation == "Plaintiff objects"
    assert result[0].text == "原告反对"
    assert result[0].id == 1


def test_translate_segments_handles_chatty_prefix_around_json():
    """Qwen3 偶尔输出 'Here is the JSON: { ... }' — 应该靠 _JSON_BLOCK_RE 抓住。"""
    mock = MagicMock()
    mock.generate.return_value = (
        'Sure, here is the translation:\n'
        '{"translations":[{"id":1,"translation":"X"}]}\n'
        'Let me know if you need anything else.'
    )
    result = translate_segments(
        segments=[_seg(1, "y")],
        target="English", glossary=None, ollama=mock,
    )
    assert result[0].translation == "X"


def test_translate_segments_raises_on_unparseable():
    mock = MagicMock()
    mock.generate.return_value = "not json at all"
    with pytest.raises(ValueError, match="无法解析"):
        translate_segments(
            segments=[_seg(1, "x")],
            target="English", glossary=None, ollama=mock,
        )


def test_translate_segments_batches_long_input():
    mock = MagicMock()
    mock.generate.side_effect = [
        json.dumps({"translations": [{"id": i, "translation": f"T{i}"} for i in range(1, 21)]}),
        json.dumps({"translations": [{"id": i, "translation": f"T{i}"} for i in range(21, 31)]}),
    ]
    segs = [_seg(i, f"src{i}") for i in range(1, 31)]
    result = translate_segments(
        segments=segs,
        target="English", glossary=None, ollama=mock, batch_size=20,
    )
    assert len(result) == 30
    assert mock.generate.call_count == 2
    # 顺序保持
    assert result[0].id == 1 and result[29].id == 30
    assert result[15].translation == "T16"


def test_translate_segments_handles_missing_id_in_response():
    """模型偷懒只返回一半 ids → 没返回的段 translation = ""。"""
    mock = MagicMock()
    mock.generate.return_value = json.dumps({
        "translations": [{"id": 2, "translation": "got it"}],  # id=1 缺
    })
    result = translate_segments(
        segments=[_seg(1, "x"), _seg(2, "y")],
        target="English", glossary=None, ollama=mock,
    )
    assert result[0].translation == ""
    assert result[1].translation == "got it"


def test_translate_segments_empty_input():
    mock = MagicMock()
    assert translate_segments([], "English", None, mock) == []
    mock.generate.assert_not_called()
