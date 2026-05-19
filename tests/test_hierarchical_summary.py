import json
from unittest.mock import patch

from liasse.hierarchical_summary import (
    L1Result,
    extract_l1,
    L1_PROMPT_TEMPLATE,
)
from liasse.transcript_chunker import Chunk


def _chunk(text="A: 你好\nB: 再见", idx=0):
    return Chunk(
        index=idx, text=text, segment_ids=[idx],
        start_time=0.0, end_time=10.0, speaker_set={"A", "B"},
    )


def test_l1_prompt_includes_chunk_text():
    chunk = _chunk(text="A: 关于 X 你怎么看\nB: 我觉得 X 很重要")
    prompt = L1_PROMPT_TEMPLATE.format(
        chunk_text=chunk.text,
        chunk_index=chunk.index + 1,
        chunk_total=3,
    )
    assert "A: 关于 X 你怎么看" in prompt
    assert "1/3" in prompt or "第 1 段" in prompt


def test_extract_l1_parses_json_response():
    fake_json = {
        "topics": ["X 的重要性"],
        "quotes": [{"speaker": "B", "text": "X 很重要", "time": "00:00-00:10"}],
        "entities": ["X"],
        "questions_raised": [],
    }
    with patch("liasse.hierarchical_summary.OllamaClient") as Cls:
        Cls.return_value.generate.return_value = json.dumps(fake_json,
                                                            ensure_ascii=False)
        result = extract_l1(_chunk(), total_chunks=1)
    assert isinstance(result, L1Result)
    assert result.topics == ["X 的重要性"]
    assert result.quotes[0]["speaker"] == "B"


def test_extract_l1_handles_malformed_json_gracefully():
    with patch("liasse.hierarchical_summary.OllamaClient") as Cls:
        Cls.return_value.generate.return_value = "（模型乱说，没有 JSON）"
        result = extract_l1(_chunk(), total_chunks=1)
    # 不抛异常，返回空结构 + raw_text
    assert result.topics == []
    assert result.raw_text  # 保留原始文本以便人工 review


def test_extract_l1_uses_4b_model():
    with patch("liasse.hierarchical_summary.OllamaClient") as Cls:
        Cls.return_value.generate.return_value = "{}"
        extract_l1(_chunk(), total_chunks=1)
    args, kwargs = Cls.return_value.generate.call_args
    assert kwargs.get("model") == "qwen3:4b" or args[0] == "qwen3:4b"


from liasse.hierarchical_summary import _parse_l1, _extract_first_json_object


def test_parse_l1_handles_think_block_prefix():
    raw = '<think>reasoning {about something}</think>\n{"topics": ["real"], "quotes": [], "entities": [], "questions_raised": []}'
    r = _parse_l1(raw, chunk_index=0)
    assert r.topics == ["real"]


def test_parse_l1_handles_null_fields():
    raw = '{"topics": null, "quotes": null, "entities": null, "questions_raised": null}'
    r = _parse_l1(raw, chunk_index=0)
    assert r.topics == [] and r.quotes == [] and r.entities == [] and r.questions_raised == []


def test_parse_l1_trims_to_caps():
    raw = '{"topics": ["t1","t2","t3","t4","t5","t6","t7"], "quotes": [], "entities": [], "questions_raised": []}'
    r = _parse_l1(raw, chunk_index=0)
    assert len(r.topics) == 5


def test_extract_first_json_object_respects_string_escapes():
    # 字符串内的 } 不应误判为结束
    raw = '{"text": "结束符号 } 在字符串里", "topics": ["x"]}'
    block = _extract_first_json_object(raw)
    assert block == raw


def test_extract_first_json_object_returns_none_when_no_braces():
    assert _extract_first_json_object("no json here") is None


from liasse.hierarchical_summary import (
    synthesize_l2,
    L2_PROMPT_TEMPLATE,
    format_l1_digest,
)
from liasse.memory_monitor import MemoryBudget


def test_l2_prompt_includes_all_l1_results():
    l1_results = [
        L1Result(chunk_index=0, topics=["话题A"], quotes=[{"speaker":"A","text":"x","time":"00:00"}]),
        L1Result(chunk_index=1, topics=["话题B"], entities=["实体X"]),
    ]
    digest = format_l1_digest(l1_results)
    assert "话题A" in digest
    assert "话题B" in digest
    assert "实体X" in digest


def test_l2_uses_8b_on_comfortable_memory():
    l1_results = [L1Result(chunk_index=0, topics=["t"])]
    budget = MemoryBudget(total_gb=16, available_gb=8)
    with patch("liasse.hierarchical_summary.OllamaClient") as Cls:
        Cls.return_value.generate.return_value = "## 总览\n内容"
        synthesize_l2(l1_results, budget=budget, user_pref="auto")
    kwargs = Cls.return_value.generate.call_args.kwargs
    assert kwargs["model"] == "qwen3:8b"


def test_l2_falls_back_to_4b_on_tight():
    l1_results = [L1Result(chunk_index=0, topics=["t"])]
    budget = MemoryBudget(total_gb=8, available_gb=3)
    with patch("liasse.hierarchical_summary.OllamaClient") as Cls:
        Cls.return_value.generate.return_value = "## 总览\n"
        synthesize_l2(l1_results, budget=budget, user_pref="auto")
    kwargs = Cls.return_value.generate.call_args.kwargs
    assert kwargs["model"] == "qwen3:4b"


def test_l2_unloads_after_use_when_flag_set():
    l1_results = [L1Result(chunk_index=0, topics=["t"])]
    budget = MemoryBudget(total_gb=16, available_gb=8)
    with patch("liasse.hierarchical_summary.OllamaClient") as Cls, \
         patch("liasse.hierarchical_summary.unload_model") as un:
        Cls.return_value.generate.return_value = "## 总览\n"
        synthesize_l2(l1_results, budget=budget, user_pref="auto",
                      unload_after=True)
        un.assert_called_once_with("qwen3:8b")
