"""v0.2.3 起：speakerMode='llm' (Smart) 同时启用 pyannote 和 LLM，
而不是 pyannote/llm 互斥。这是因为声纹分离本质是声学问题，LLM 单跑
没法做。LLM 只在 pyannote 已经分好的簇上贴语义标签。"""

from liasse.task_runner import _resolve_speaker_execution


def test_llm_mode_runs_both_pyannote_and_llm():
    """Smart / LLM 模式现在双跑：pyannote 做声纹，LLM 做语义命名。"""
    _, effective, pyannote_enabled, llm_enabled = _resolve_speaker_execution(
        {"speakerMode": "llm"}
    )
    assert effective == "llm"
    assert pyannote_enabled is True, "Smart 模式必须跑 pyannote（声纹）"
    assert llm_enabled is True, "Smart 模式必须跑 LLM（语义标签）"


def test_pyannote_mode_only_runs_pyannote():
    """单 pyannote 模式：跑声纹，不跑 LLM 命名。"""
    _, effective, pyannote_enabled, llm_enabled = _resolve_speaker_execution(
        {"speakerMode": "pyannote"}
    )
    assert effective == "pyannote"
    assert pyannote_enabled is True
    assert llm_enabled is False


def test_fast_mode_runs_neither():
    """快速模式：不分发言人。"""
    _, effective, pyannote_enabled, llm_enabled = _resolve_speaker_execution(
        {"speakerMode": "fast"}
    )
    assert effective == "fast"
    assert pyannote_enabled is False
    assert llm_enabled is False


def test_default_mode_is_llm_with_pyannote():
    """缺省（没传 speakerMode）走 llm 模式，pyannote 必须跟着启用。"""
    _, effective, pyannote_enabled, llm_enabled = _resolve_speaker_execution({})
    assert effective == "llm"
    assert pyannote_enabled is True
    assert llm_enabled is True


def test_auto_segment_off_forces_fast():
    """关闭 autoSegment 会强制 fast 模式（用户主动选不分段）。"""
    _, effective, pyannote_enabled, llm_enabled = _resolve_speaker_execution(
        {"speakerMode": "llm", "autoSegment": False}
    )
    assert effective == "fast"
    assert pyannote_enabled is False
    assert llm_enabled is False


def test_task_runner_skips_llm_when_pyannote_collapses_to_one_cluster():
    """task_runner.py 源码层校验：pyannote 只分出 1 簇时，必须有跳过 LLM 的分支
    （而不是无脑调 label_segments → 命中 SpeakerLabelingError → 弹「智能分离失败」）。"""
    import inspect

    from liasse import task_runner

    source = inspect.getsource(task_runner)
    # 关键标记必须出现在源码里：检测 distinct pyannote speakers，并在 <= 1 时短路
    assert "distinct_pyannote_speakers" in source, (
        "task_runner 应该在调 label_segments 前检测 pyannote 的 distinct 簇数"
    )
    assert "len(distinct_pyannote_speakers) <= 1" in source, (
        "短路条件应该是 distinct 簇数 <= 1"
    )
