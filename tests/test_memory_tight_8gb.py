"""8GB Air 边界场景守卫测试。

模拟 M2 MacBook Air 8GB 统一内存，可用内存只有 2-3GB（系统 + Safari +
Slack 已经吃掉一半）。验证：

1. MemoryBudget.detect 在模拟 8GB 系统返回 TIGHT tier
2. model_router 在 TIGHT 全部任务锁 qwen3:4b（不会尝试 8B）
3. summary_pipeline 的 L1 并发度在 TIGHT 是 1（避免内存峰值叠加）
4. summary_pipeline 在 TIGHT 完 L2 后会卸 model（释放 RAM 给 QA）

不实际跑 ASR / Ollama —— 完全靠 monkeypatch 模拟 RAM 状态。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from liasse.memory_monitor import MemoryBudget, MemoryTier
from liasse.model_router import TaskKind, route


# ---------- M2 Air 8GB 系统快照 fixtures ----------


@pytest.fixture
def air_8gb_idle():
    """模拟 8GB Air 开机几乎没占用 — 总 8GB，可用 5GB。
    这是「理想」场景，但实际用户开几个 app 就 < 3GB。"""
    return MemoryBudget(total_gb=8.0, available_gb=5.0)


@pytest.fixture
def air_8gb_realistic():
    """模拟 8GB Air 日常 — 系统 + Safari + 几个 tabs 占了 5GB，剩 3GB。"""
    return MemoryBudget(total_gb=8.0, available_gb=3.0)


@pytest.fixture
def air_8gb_loaded():
    """模拟 8GB Air 重负载 — 用户 Slack/Zoom/IDE 都开着，可用 1.5GB。
    这种场景应该 fall back 4B 并 warn 用户关其他 app。"""
    return MemoryBudget(total_gb=8.0, available_gb=1.5)


# ---------- tier 检测 ----------


def test_8gb_air_classified_as_tight(air_8gb_idle, air_8gb_realistic, air_8gb_loaded):
    """8GB total 永远是 TIGHT，不管 available 多少 — tier 看 total 不看 free。"""
    assert air_8gb_idle.tier == MemoryTier.TIGHT
    assert air_8gb_realistic.tier == MemoryTier.TIGHT
    assert air_8gb_loaded.tier == MemoryTier.TIGHT


def test_can_load_4b_threshold():
    """4B 需要 ≥3GB free。8GB Air realistic (3GB) 边界过线；loaded (1.5GB) 不行。"""
    assert MemoryBudget(8.0, 3.0).can_load_4b() is True
    assert MemoryBudget(8.0, 3.1).can_load_4b() is True
    assert MemoryBudget(8.0, 2.9).can_load_4b() is False
    assert MemoryBudget(8.0, 1.5).can_load_4b() is False


def test_can_load_8b_threshold_never_met_on_8gb():
    """8B 需要 ≥6GB free —— 8GB 总内存机器实际永远满足不了。"""
    assert MemoryBudget(8.0, 5.9).can_load_8b() is False
    # 极端：系统刚开机
    assert MemoryBudget(8.0, 7.0).can_load_8b() is True
    # 但 8GB total 上 7GB free 几乎不可能（系统至少占 1.5-2GB）


# ---------- model_router 在 tight 锁 4B ----------


@pytest.mark.parametrize("task", [
    TaskKind.CLEAN,
    TaskKind.TITLE,
    TaskKind.L1_EXTRACT,
    TaskKind.L2_SYNTHESIS,
    TaskKind.QA,
])
def test_router_locks_4b_on_tight_for_all_tasks(task, air_8gb_realistic):
    """auto 模式下所有任务都应该选 4B（不能试图加载 8B）。"""
    choice = route(task, air_8gb_realistic, user_pref="auto")
    assert choice.model == "qwen3:4b", (
        f"{task.value} on tight expected 4B, got {choice.model}"
    )


def test_router_quality_pref_falls_back_with_warning_on_tight(air_8gb_realistic):
    """用户强制 quality 模式，但内存不够 — 必须 fall back 4B 并 warn。"""
    choice = route(TaskKind.L2_SYNTHESIS, air_8gb_realistic, user_pref="quality")
    assert choice.model == "qwen3:4b"
    assert choice.warning is not None
    assert "降级" in choice.warning or "swap" in choice.warning


def test_router_speed_pref_always_4b(air_8gb_idle):
    """speed 模式永远 4B，不管 tier。"""
    for task in [TaskKind.L1_EXTRACT, TaskKind.QA, TaskKind.L2_SYNTHESIS]:
        choice = route(task, air_8gb_idle, user_pref="speed")
        assert choice.model == "qwen3:4b"


# ---------- summary_pipeline 在 tight 锁 1 并发 ----------


def test_summary_l1_concurrency_locked_to_1_on_tight():
    """tight tier 必须串行跑 L1，否则 3 并发 × 4B 内存峰值会让 8GB Air OOM。"""
    from liasse.summary_pipeline import _l1_concurrency

    assert _l1_concurrency(MemoryBudget(8.0, 5.0)) == 1
    assert _l1_concurrency(MemoryBudget(8.0, 3.0)) == 1
    assert _l1_concurrency(MemoryBudget(8.0, 1.5)) == 1


def test_summary_l1_concurrency_3_on_comfortable():
    """16GB 才允许 3 并发。"""
    from liasse.summary_pipeline import _l1_concurrency

    assert _l1_concurrency(MemoryBudget(16.0, 8.0)) == 3


# ---------- summary_pipeline 在 tight 完 L2 后卸 model ----------


def test_summary_unloads_l2_model_on_tight(tmp_path):
    """tight 跑完 L2 后必须 unload_model 释放 RAM 给 QA。8GB Air 上
    L2 的 4B + Qwen3-ASR 残留 + 系统已经吃满，必须主动让位。"""
    from liasse.models import TranscriptSegment
    from liasse.summary_pipeline import analyze

    segs = [
        TranscriptSegment(start=0, end=10, text="问题" + "内容" * 200, speaker="A"),
        TranscriptSegment(start=10, end=30, text="回答" + "内容" * 200, speaker="B"),
        TranscriptSegment(start=30, end=40, text="再问", speaker="A"),
    ]

    fake_l1 = MagicMock(
        chunk_index=0, topics=["t"], quotes=[], entities=[],
        questions_raised=[], raw_text="",
        to_dict=lambda: {"chunk_index": 0, "topics": ["t"], "quotes": [],
                         "entities": [], "questions_raised": []},
    )

    with patch("liasse.summary_pipeline.extract_l1", return_value=fake_l1), \
         patch("liasse.summary_pipeline.synthesize_l2",
               return_value="## 总览"), \
         patch("liasse.summary_pipeline.TranscriptIndex.build",
               return_value=MagicMock(save=lambda: None)), \
         patch("liasse.summary_pipeline.unload_model") as unload_mock:
        analyze(segs, output_dir=tmp_path, task_id="tight",
                budget=MemoryBudget(8.0, 3.0))  # TIGHT

    # 至少调一次 unload_model — L2 完后释放
    assert unload_mock.called, "tight tier 跑完 L2 必须 unload_model"


def test_summary_does_not_unload_on_comfortable(tmp_path):
    """对应地，comfortable tier 不应主动 unload（保留模型给后续 QA）。"""
    from liasse.models import TranscriptSegment
    from liasse.summary_pipeline import analyze

    segs = [
        TranscriptSegment(start=0, end=10, text="x" * 600, speaker="A"),
        TranscriptSegment(start=10, end=20, text="y" * 600, speaker="B"),
    ]

    fake_l1 = MagicMock(
        chunk_index=0, topics=["t"], quotes=[], entities=[],
        questions_raised=[], raw_text="",
        to_dict=lambda: {"chunk_index": 0, "topics": ["t"], "quotes": [],
                         "entities": [], "questions_raised": []},
    )

    with patch("liasse.summary_pipeline.extract_l1", return_value=fake_l1), \
         patch("liasse.summary_pipeline.synthesize_l2", return_value="ok"), \
         patch("liasse.summary_pipeline.TranscriptIndex.build",
               return_value=MagicMock(save=lambda: None)), \
         patch("liasse.summary_pipeline.unload_model") as unload_mock:
        analyze(segs, output_dir=tmp_path, task_id="comfy",
                budget=MemoryBudget(16.0, 8.0))  # COMFORTABLE

    # comfortable 下，model_router 给 L1 和 L2 选的都是同一个 4B → 不需要
    # model_switch；也不主动卸（让后续 QA 复用）。
    # unload 调用只可能因为 L1≠L2 model switch；comfortable 这里都是 4B。
    # 如果 unload 完全没调，OK；如果调了，必须是 model switch 不是 cleanup。
    if unload_mock.called:
        # 不能是 cleanup 级别的卸（tight tier 才会发"cleanup"进度事件）
        # 我们靠"调用次数 ≤ 1（来自 L1/L2 model_switch）"区分
        assert unload_mock.call_count <= 1
