from unittest.mock import MagicMock, patch

from local_transcriber.memory_monitor import MemoryBudget
from local_transcriber.qa_engine import QAEngine, QA_SYSTEM_PROMPT
from local_transcriber.transcript_chunker import Chunk
from local_transcriber.transcript_index import SearchResult, TranscriptIndex


def _chunk(idx, text, start=0, end=60):
    return Chunk(index=idx, text=text, segment_ids=[idx],
                 start_time=start, end_time=end, speaker_set={"A", "B"})


def test_qa_retrieves_top_k_chunks_and_includes_in_prompt():
    chunks = [_chunk(0, "B: 我支持开放教育"),
              _chunk(1, "B: 经济不是核心")]
    idx = TranscriptIndex.build(chunks)
    engine = QAEngine(index=idx, budget=MemoryBudget(16, 8))

    with patch("local_transcriber.qa_engine.OllamaClient") as Cls:
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
    with patch("local_transcriber.qa_engine.OllamaClient") as Cls:
        Cls.return_value.stream_chat.return_value = iter([])
        list(engine.answer("hi", history=[]))
    assert Cls.return_value.stream_chat.call_args.kwargs["model"] == "qwen3:8b"


def test_qa_uses_4b_on_tight():
    chunks = [_chunk(0, "x")]
    idx = TranscriptIndex.build(chunks)
    engine = QAEngine(index=idx, budget=MemoryBudget(8, 3))
    with patch("local_transcriber.qa_engine.OllamaClient") as Cls:
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
    with patch("local_transcriber.qa_engine.OllamaClient") as Cls:
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
    with patch("local_transcriber.qa_engine.OllamaClient") as Cls:
        Cls.return_value.stream_chat.return_value = iter(["未提及"])
        out = list(engine.answer("xxxxxx不存在的词", history=[]))
    msgs = Cls.return_value.stream_chat.call_args.kwargs["messages"]
    # system prompt 应包含「未检索」的提示
    assert "未检索" in msgs[0]["content"] or "未匹配" in msgs[0]["content"]
