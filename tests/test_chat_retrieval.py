from local_transcriber import chat


def test_retrieve_context_returns_matching_time_block():
    segments = [
        {"id": "1", "speaker": "A", "start": 0.0, "end": 12.0, "text": "我们先讨论天气。"},
        {"id": "2", "speaker": "B", "start": 12.0, "end": 30.0, "text": "我认为教育公平的核心是资源分配。"},
        {"id": "3", "speaker": "A", "start": 30.0, "end": 50.0, "text": "谢谢，我们换一个话题。"},
    ]

    context = chat.retrieve_context(segments, "教育公平")

    assert "教育公平" in context
    assert "00:12" in context
    assert "资源分配" in context


def test_retrieve_context_applies_speaker_and_segment_edits():
    segments = [
        {"id": "seg-1", "speaker": "SPEAKER_00", "start": 0.0, "end": 8.0, "text": "原始文本"},
    ]

    context = chat.retrieve_context(
        segments,
        "隐私",
        speaker_labels={"SPEAKER_00": "受访者"},
        overrides={"seg-1": "隐私保护是第一要求"},
    )

    assert "受访者" in context
    assert "隐私保护" in context


def test_retrieve_context_reports_no_match():
    segments = [
        {"id": "1", "speaker": "A", "start": 0.0, "end": 8.0, "text": "完全无关内容"},
    ]

    context = chat.retrieve_context(segments, "quantum entanglement")

    assert "未检索到" in context
