"""label_segments 在 v0.2.4 起改为 cluster-mapping 模式：
LLM 只产出 {cluster_id → role_label} 映射，不改 segments 的 speaker 字段。
原来 v0.2.3 的「per-segment 分类」会让 LLM 覆盖 pyannote 的声学判断，
经常 collapse 到 1 个 speaker，因此重构。"""

import urllib.error

import pytest

from liasse.models import TranscriptSegment
from liasse import speaker_labeler


def test_label_segments_maps_clusters_to_roles(monkeypatch):
    """两簇 pyannote 输出 + LLM 给出 cluster→role 映射 → segment.speaker
    保留原值，speaker_labels 反映 LLM 的语义命名。"""
    segments = [
        TranscriptSegment(start=0.0, end=2.0, text="请介绍一下你的研究。", speaker="SPEAKER_00"),
        TranscriptSegment(start=2.0, end=8.0, text="我的研究主要关注课堂里的人工智能。", speaker="SPEAKER_01"),
    ]

    monkeypatch.setattr(
        speaker_labeler,
        "_generate",
        lambda prompt, *, model: (
            '{"SPEAKER_00":"采访者","SPEAKER_01":"受访者"}'
        ),
    )

    result = speaker_labeler.label_segments(segments, model="qwen3:4b", num_speakers=2)

    # 关键：segment.speaker 来自 pyannote，LLM 不能动
    assert [s.speaker for s in result.segments] == ["SPEAKER_00", "SPEAKER_01"]
    # 语义标签由 LLM 给
    assert result.speaker_labels == {"SPEAKER_00": "采访者", "SPEAKER_01": "受访者"}


def test_label_segments_preserves_pyannote_speakers_even_if_llm_swaps(monkeypatch):
    """回归保护：即便 LLM 觉得 SPEAKER_01 才是采访者，也只影响
    speaker_labels 的标签，不会反过来去改 segment.speaker。"""
    segments = [
        TranscriptSegment(start=0.0, end=2.0, text="谢谢你来分享。", speaker="SPEAKER_00"),
        TranscriptSegment(start=2.0, end=8.0, text="不客气，我们继续。", speaker="SPEAKER_01"),
    ]

    monkeypatch.setattr(
        speaker_labeler,
        "_generate",
        lambda prompt, *, model: '{"SPEAKER_00":"受访者","SPEAKER_01":"采访者"}',
    )

    result = speaker_labeler.label_segments(segments, num_speakers=2)

    # segment.speaker 仍是 pyannote 的输出
    assert [s.speaker for s in result.segments] == ["SPEAKER_00", "SPEAKER_01"]
    # 但 speaker_labels 反映 LLM 的反向判断
    assert result.speaker_labels["SPEAKER_00"] == "受访者"
    assert result.speaker_labels["SPEAKER_01"] == "采访者"


def test_label_segments_accepts_markdown_json(monkeypatch):
    segments = [
        TranscriptSegment(start=0.0, end=2.0, text="A", speaker="SPEAKER_00"),
        TranscriptSegment(start=2.0, end=4.0, text="B", speaker="SPEAKER_01"),
    ]

    monkeypatch.setattr(
        speaker_labeler,
        "_generate",
        lambda prompt, *, model: '```json\n{"SPEAKER_00":"采访者","SPEAKER_01":"受访者"}\n```',
    )

    result = speaker_labeler.label_segments(segments)

    assert result.speaker_labels == {"SPEAKER_00": "采访者", "SPEAKER_01": "受访者"}


def test_label_segments_raises_on_malformed_json(monkeypatch):
    """LLM 完全没返回 JSON → 抛 SpeakerLabelingError，由 task_runner 兜底。"""
    segments = [
        TranscriptSegment(start=0.0, end=2.0, text="A", speaker="SPEAKER_00"),
        TranscriptSegment(start=2.0, end=4.0, text="B", speaker="SPEAKER_01"),
    ]
    monkeypatch.setattr(
        speaker_labeler, "_generate", lambda prompt, *, model: "not json"
    )

    with pytest.raises(speaker_labeler.SpeakerLabelingError):
        speaker_labeler.label_segments(segments, num_speakers=2)


def test_label_segments_single_speaker_skips_llm(monkeypatch):
    """num_speakers=1 时跳过 LLM 直接全部归 SPEAKER_00。"""
    segments = [
        TranscriptSegment(start=0.0, end=2.0, text="一段独白。"),
        TranscriptSegment(start=2.0, end=4.0, text="还有一段独白。"),
    ]

    def _fail(*args, **kwargs):
        raise AssertionError("单说话人不应该调用 LLM")

    monkeypatch.setattr(speaker_labeler, "_generate", _fail)

    result = speaker_labeler.label_segments(segments, num_speakers=1)

    assert [s.speaker for s in result.segments] == ["SPEAKER_00", "SPEAKER_00"]
    assert result.speaker_labels == {"SPEAKER_00": "采访者"}


def test_label_segments_one_cluster_skips_llm(monkeypatch):
    """v0.2.4：pyannote 实际只分出 1 簇时也跳过 LLM（即便 num_speakers=2）。"""
    segments = [
        TranscriptSegment(start=0.0, end=2.0, text="一", speaker="SPEAKER_00"),
        TranscriptSegment(start=2.0, end=4.0, text="二", speaker="SPEAKER_00"),
    ]

    def _fail(*args, **kwargs):
        raise AssertionError("只 1 簇时不应该调 LLM")

    monkeypatch.setattr(speaker_labeler, "_generate", _fail)

    result = speaker_labeler.label_segments(segments, num_speakers=2)

    assert [s.speaker for s in result.segments] == ["SPEAKER_00", "SPEAKER_00"]
    assert result.speaker_labels == {"SPEAKER_00": "采访者"}


def test_generate_wraps_ollama_connection_error(monkeypatch):
    class FakeOpener:
        def open(self, *args, **kwargs):
            raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(
        speaker_labeler.urllib.request,
        "build_opener",
        lambda *args, **kwargs: FakeOpener(),
    )

    with pytest.raises(speaker_labeler.SpeakerLabelingError, match="Ollama"):
        speaker_labeler._generate("prompt", model="qwen3:4b")


def test_generate_sets_think_false_to_skip_qwen_thinking():
    """回归保护：必须显式 think=False，否则 Qwen3 hybrid thinking 会跑 100+s
    在不可见的 think tokens 上（v0.2.3 实测：151s → v0.2.4 25s）。"""
    import inspect

    source = inspect.getsource(speaker_labeler._generate)
    assert '"think": False' in source or "'think': False" in source, (
        "_generate 必须显式 think=False 来关闭 Qwen3 thinking mode"
    )
