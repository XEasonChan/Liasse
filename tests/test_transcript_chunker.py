from liasse.models import TranscriptSegment
from liasse.transcript_chunker import (
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


def test_chunk_interview_overlap_disabled_by_default():
    """默认 overlap_chars=0 — 不能因为加了 overlap 改变现有行为。"""
    segs = [_seg(i * 1.0, (i + 1) * 1.0, "x" * 200, "A" if i % 2 == 0 else "B")
            for i in range(60)]
    chunks = chunk_interview(segs, target_chars=2000, max_chars=2500)
    assert len(chunks) >= 2
    # 第二块文本不应包含「上文回顾」标记
    assert "[上文回顾]" not in chunks[1].text


def test_chunk_interview_overlap_prepends_previous_tail():
    """overlap_chars > 0 时第二块应包含「[上文回顾]」头部，含上一块尾部。"""
    segs = [_seg(i * 1.0, (i + 1) * 1.0, f"段{i:03d}内容" + "x" * 80,
                 "A" if i % 2 == 0 else "B") for i in range(60)]
    chunks = chunk_interview(segs, target_chars=2000, max_chars=2500,
                              overlap_chars=300)
    assert len(chunks) >= 2
    assert chunks[1].text.startswith("[上文回顾]")
    assert "[本块开始]" in chunks[1].text
    # 上文回顾段不应让 chunks[1].text 超过 max_chars + overlap 太多
    assert len(chunks[1].text) <= 2500 + 400


def test_chunk_interview_overlap_does_not_change_segment_ids():
    """关键不变量：overlap 仅影响 text，segment_ids / start_time / end_time
    必须和不开 overlap 时一致（保证 L1 抽取结果能 1:1 对应原 segments）。"""
    segs = [_seg(i * 1.0, (i + 1) * 1.0, f"段{i:03d}" + "x" * 100, "A")
            for i in range(30)]
    a = chunk_interview(segs, target_chars=1500, max_chars=2000)
    b = chunk_interview(segs, target_chars=1500, max_chars=2000,
                         overlap_chars=200)
    assert len(a) == len(b)
    for ca, cb in zip(a, b):
        assert ca.segment_ids == cb.segment_ids
        assert ca.start_time == cb.start_time
        assert ca.end_time == cb.end_time


def test_chunk_interview_first_chunk_never_has_overlap():
    """第一块没有「前一块」，不应有上文回顾标记。"""
    segs = [_seg(i, i + 1, "x" * 100, "A") for i in range(40)]
    chunks = chunk_interview(segs, target_chars=1500, max_chars=2000,
                              overlap_chars=300)
    assert "[上文回顾]" not in chunks[0].text
