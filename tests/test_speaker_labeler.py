import urllib.error

import pytest

from liasse.models import TranscriptSegment
from liasse import speaker_labeler


def test_label_segments_parses_json_assignments(monkeypatch):
    segments = [
        TranscriptSegment(start=0.0, end=2.0, text="请介绍一下你的研究。"),
        TranscriptSegment(start=2.0, end=8.0, text="我的研究主要关注课堂里的人工智能。"),
    ]

    monkeypatch.setattr(
        speaker_labeler,
        "_generate",
        lambda prompt, *, model: (
            '[{"id":"seg-0","speaker":"SPEAKER_00"},'
            '{"id":"seg-1","speaker":"SPEAKER_01"}]'
        ),
    )

    result = speaker_labeler.label_segments(segments, model="qwen3:4b", num_speakers=2)

    assert [segment.speaker for segment in result.segments] == [
        "SPEAKER_00",
        "SPEAKER_01",
    ]
    assert result.speaker_labels["SPEAKER_00"] == "采访者"
    assert result.speaker_labels["SPEAKER_01"] == "受访者"


def test_label_segments_accepts_markdown_json(monkeypatch):
    segments = [TranscriptSegment(start=0.0, end=2.0, text="谢谢你的回答。")]

    monkeypatch.setattr(
        speaker_labeler,
        "_generate",
        lambda prompt, *, model: '```json\n[{"id":"seg-0","speaker":"受访者"}]\n```',
    )

    result = speaker_labeler.label_segments(segments)

    assert result.segments[0].speaker == "SPEAKER_01"


def test_label_segments_raises_on_malformed_json(monkeypatch):
    segments = [TranscriptSegment(start=0.0, end=2.0, text="坏输出")]
    monkeypatch.setattr(speaker_labeler, "_generate", lambda prompt, *, model: "not json")

    with pytest.raises(speaker_labeler.SpeakerLabelingError):
        speaker_labeler.label_segments(segments)


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
