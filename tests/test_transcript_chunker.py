from local_transcriber.models import TranscriptSegment
from local_transcriber.transcript_chunker import (
    Chunk,
    chunk_interview,
    normalize_to_two_speakers,
)


def _seg(start, end, text, speaker="A"):
    return TranscriptSegment(start=start, end=end, text=text, speaker=speaker)


def test_normalize_keeps_top_two_speakers_by_duration():
    segments = [
        _seg(0, 10, "long", "A"),
        _seg(10, 30, "longer", "B"),
        _seg(30, 31, "blip", "C"),  # 1s 噪声标签
    ]
    normalized = normalize_to_two_speakers(segments)
    assert {s.speaker for s in normalized} == {"A", "B"}
    # C 的片段应被合并到时间上邻近的那一个
    blip = [s for s in normalized if s.text == "blip"][0]
    assert blip.speaker in {"A", "B"}


def test_chunker_respects_target_size():
    segments = [
        _seg(i * 5, i * 5 + 5, "你好" * 200, "A" if i % 2 == 0 else "B")
        for i in range(20)
    ]
    chunks = chunk_interview(segments, target_chars=4000)
    assert all(len(c.text) <= 6500 for c in chunks)
    assert len(chunks) >= 2


def test_chunker_preserves_speaker_turns():
    segments = [
        _seg(0, 5, "问题一", "A"),
        _seg(5, 10, "回答一", "B"),
        _seg(10, 15, "追问", "A"),
    ]
    chunks = chunk_interview(segments, target_chars=4000)
    assert len(chunks) == 1
    assert "A:" in chunks[0].text and "B:" in chunks[0].text


def test_chunker_splits_on_long_silence():
    long_text_a = "我们先聊聊第一个话题" * 20  # ~200 chars
    long_text_b = "好的没问题这个话题我来分享" * 20  # ~260 chars
    segments = [
        _seg(0, 5, long_text_a, "A"),
        _seg(5, 10, long_text_b, "B"),
        # 5 秒静默
        _seg(15, 20, "新话题开始", "A"),
        _seg(20, 25, "回应内容", "B"),
    ]
    chunks = chunk_interview(segments, target_chars=200, silence_split_seconds=3.0)
    # 第 2 段后 cur_chars >> 200，且接下来有 5s 静默 → 切
    assert len(chunks) == 2


def test_chunker_emits_chunk_metadata():
    segments = [
        _seg(0, 30, "x" * 100, "A"),
        _seg(30, 60, "y" * 100, "B"),
    ]
    chunks = chunk_interview(segments, target_chars=300)
    assert chunks[0].start_time == 0
    assert chunks[0].end_time == 60
    assert chunks[0].speaker_set == {"A", "B"}
    assert chunks[0].index == 0
