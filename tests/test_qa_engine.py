from unittest.mock import MagicMock, patch

from liasse.memory_monitor import MemoryBudget
from liasse.qa_engine import QAEngine, QA_SYSTEM_PROMPT
from liasse.transcript_chunker import Chunk
from liasse.transcript_index import SearchResult, TranscriptIndex


def _chunk(idx, text, start=0, end=60):
    return Chunk(index=idx, text=text, segment_ids=[idx],
                 start_time=start, end_time=end, speaker_set={"A", "B"})


def test_qa_retrieves_top_k_chunks_and_includes_in_prompt():
    chunks = [_chunk(0, "B: 我支持开放教育"),
              _chunk(1, "B: 经济不是核心")]
    idx = TranscriptIndex.build(chunks)
    engine = QAEngine(index=idx, budget=MemoryBudget(16, 8))

    with patch("liasse.qa_engine.OllamaClient") as Cls:
        Cls.return_value.stream_chat.return_value = iter(["开放", "教育"])
        out = list(engine.answer("教育", history=[], top_k=2))

    messages = Cls.return_value.stream_chat.call_args.kwargs["messages"]
    system = messages[0]["content"]
    assert "开放教育" in system
    assert "".join(out) == "开放教育"


def test_qa_uses_8b_on_comfortable():
    chunks = [_chunk(0, "x")]
    idx = TranscriptIndex.build(chunks)
    engine = QAEngine(index=idx, budget=MemoryBudget(16, 8))
    with patch("liasse.qa_engine.OllamaClient") as Cls:
        Cls.return_value.stream_chat.return_value = iter([])
        list(engine.answer("hi", history=[]))
    assert Cls.return_value.stream_chat.call_args.kwargs["model"] == "qwen3:8b"


def test_qa_uses_4b_on_tight():
    chunks = [_chunk(0, "x")]
    idx = TranscriptIndex.build(chunks)
    engine = QAEngine(index=idx, budget=MemoryBudget(8, 3))
    with patch("liasse.qa_engine.OllamaClient") as Cls:
        Cls.return_value.stream_chat.return_value = iter([])
        list(engine.answer("hi", history=[]))
    assert Cls.return_value.stream_chat.call_args.kwargs["model"] == "qwen3:4b"


def test_qa_carries_chat_history():
    chunks = [_chunk(0, "x")]
    idx = TranscriptIndex.build(chunks)
    engine = QAEngine(index=idx, budget=MemoryBudget(16, 8))
    history = [
        {"role": "user", "content": "之前问题"},
        {"role": "assistant", "content": "之前回答"},
    ]
    with patch("liasse.qa_engine.OllamaClient") as Cls:
        Cls.return_value.stream_chat.return_value = iter([])
        list(engine.answer("新问题", history=history))
    msgs = Cls.return_value.stream_chat.call_args.kwargs["messages"]
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "user"]
    assert msgs[-1]["content"] == "新问题"


def test_qa_handles_no_retrieval_match():
    chunks = [_chunk(0, "完全无关")]
    idx = TranscriptIndex.build(chunks)
    engine = QAEngine(index=idx, budget=MemoryBudget(16, 8))
    with patch("liasse.qa_engine.OllamaClient") as Cls:
        Cls.return_value.stream_chat.return_value = iter(["未提及"])
        out = list(engine.answer("xxxxxx不存在的词", history=[]))
    msgs = Cls.return_value.stream_chat.call_args.kwargs["messages"]
    # system prompt 应包含「未检索」的提示
    assert "未检索" in msgs[0]["content"] or "未匹配" in msgs[0]["content"]


from liasse.qa_engine import build_index_for_task


class _FakeTaskRow:
    def __init__(self, segments, edits=None):
        self.transcript = {"segments": segments}
        self.edits = edits or {}


def test_build_index_for_task_applies_speaker_labels_and_overrides():
    segments = [
        {"id": "seg-0", "speaker": "SPEAKER_00", "start": 0.0, "end": 5.0,
         "text": "原始 A 文本"},
        {"id": "seg-1", "speaker": "SPEAKER_01", "start": 5.0, "end": 10.0,
         "text": "原始 B 文本"},
    ]
    edits = {
        "speakerLabels": {"SPEAKER_00": "研究者", "SPEAKER_01": "受访者"},
        "segmentOverrides": {"seg-1": "改过的 B 文本"},
    }
    task = _FakeTaskRow(segments, edits)

    index = build_index_for_task(task)

    assert index is not None
    hits = index.search("改过的", top_k=3)
    assert any("改过的 B 文本" in r.chunk.text for r in hits)
    hits = index.search("受访者", top_k=3)
    assert any("受访者" in r.chunk.text for r in hits)


def test_build_index_for_task_returns_none_when_no_segments():
    task = _FakeTaskRow(segments=[])
    assert build_index_for_task(task) is None


def test_build_index_for_task_handles_missing_edits():
    segments = [{"id": "seg-0", "speaker": "A", "start": 0.0, "end": 5.0, "text": "测试"}]
    task = _FakeTaskRow(segments, edits=None)
    index = build_index_for_task(task)
    assert index is not None
    assert len(index.search("测试", top_k=1)) == 1
