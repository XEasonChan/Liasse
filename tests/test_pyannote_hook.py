"""测试 pyannote progress hook 注入。

monkey-patch 给 pyannote Pipeline.__call__ 注入 hook，让 mlx-qwen3-asr 内部
不传 hook 的调用也能把 segmentation/embeddings/clustering 阶段进度送到
worker progress queue。
"""

from __future__ import annotations

import queue

import pytest


@pytest.fixture
def reset_pyannote_patch_flag():
    """每个测试前后保证 Pipeline 状态干净。"""
    import pyannote.audio.core.pipeline as _pyp

    original_call = _pyp.Pipeline.__call__
    if hasattr(_pyp.Pipeline, "_qwensper_hook_patched"):
        delattr(_pyp.Pipeline, "_qwensper_hook_patched")
    yield
    _pyp.Pipeline.__call__ = original_call
    if hasattr(_pyp.Pipeline, "_qwensper_hook_patched"):
        delattr(_pyp.Pipeline, "_qwensper_hook_patched")


def test_hook_factory_segmentation_event():
    """无 total/completed 时，单阶段事件只有 stage label，progress 保持 0.82。"""
    from local_transcriber.task_runner import _make_pyannote_progress_hook

    q: queue.Queue = queue.Queue()
    hook = _make_pyannote_progress_hook(q)

    hook("segmentation", None)

    evt = q.get_nowait()
    assert evt["type"] == "progress"
    assert "切分音频" in evt["stage"]
    assert evt["value"] == pytest.approx(0.82)


def test_hook_factory_batched_progress():
    """带 total/completed 的事件应该把 N/M 写进 stage，progress 平滑推进。"""
    from local_transcriber.task_runner import _make_pyannote_progress_hook

    q: queue.Queue = queue.Queue()
    hook = _make_pyannote_progress_hook(q)

    hook("embeddings", None, total=4, completed=2)

    evt = q.get_nowait()
    assert "提取声纹 (2/4)" in evt["stage"]
    # 50% × 0.05 = 0.025 → 0.82 + 0.025 = 0.845
    assert evt["value"] == pytest.approx(0.845)


def test_hook_factory_full_progression():
    """连续多事件 →  queue 收集成有序序列。"""
    from local_transcriber.task_runner import _make_pyannote_progress_hook

    q: queue.Queue = queue.Queue()
    hook = _make_pyannote_progress_hook(q)

    hook("segmentation", None)
    hook("embeddings", None, total=10, completed=5)
    hook("embeddings", None, total=10, completed=10)
    hook("discrete_diarization", None)

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    assert len(events) == 4
    assert "切分音频" in events[0]["stage"]
    assert "提取声纹 (5/10)" in events[1]["stage"]
    assert "提取声纹 (10/10)" in events[2]["stage"]
    assert events[2]["value"] == pytest.approx(0.87)  # 0.82 + 0.05 * 1.0
    assert "聚类发言人" in events[3]["stage"]


def test_hook_factory_unknown_step_falls_back_to_raw():
    """没见过的 step_name 直接显示原名而不是炸掉。"""
    from local_transcriber.task_runner import _make_pyannote_progress_hook

    q: queue.Queue = queue.Queue()
    hook = _make_pyannote_progress_hook(q)

    hook("some_future_step", None, total=3, completed=1)

    evt = q.get_nowait()
    assert "some_future_step (1/3)" in evt["stage"]


def test_install_sets_class_flag(reset_pyannote_patch_flag):
    """install 后 Pipeline 类应当标记为已 patched。"""
    from local_transcriber.task_runner import _install_pyannote_progress_hook
    import pyannote.audio.core.pipeline as _pyp

    q: queue.Queue = queue.Queue()
    assert not getattr(_pyp.Pipeline, "_qwensper_hook_patched", False)

    _install_pyannote_progress_hook(q)
    assert getattr(_pyp.Pipeline, "_qwensper_hook_patched", False) is True


def test_install_is_idempotent(reset_pyannote_patch_flag):
    """二次调用不应该堆叠包装（否则同一事件会发两次）。"""
    from local_transcriber.task_runner import _install_pyannote_progress_hook
    import pyannote.audio.core.pipeline as _pyp

    q: queue.Queue = queue.Queue()
    _install_pyannote_progress_hook(q)
    patched_once = _pyp.Pipeline.__call__

    _install_pyannote_progress_hook(q)
    assert _pyp.Pipeline.__call__ is patched_once
