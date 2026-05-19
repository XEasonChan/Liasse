from unittest.mock import patch

from liasse.memory_monitor import MemoryBudget, MemoryTier
from liasse.model_router import ModelChoice, TaskKind, route


def _budget(total: float, available: float) -> MemoryBudget:
    return MemoryBudget(total_gb=total, available_gb=available)


def test_clean_always_uses_4b():
    choice = route(TaskKind.CLEAN, _budget(32, 20), user_pref="auto")
    assert choice.model == "qwen3:4b"


def test_l1_extract_always_uses_4b():
    choice = route(TaskKind.L1_EXTRACT, _budget(32, 20), user_pref="auto")
    assert choice.model == "qwen3:4b"


def test_l2_synthesis_uses_8b_when_memory_ok():
    choice = route(TaskKind.L2_SYNTHESIS, _budget(16, 8), user_pref="auto")
    assert choice.model == "qwen3:8b"
    assert choice.num_ctx >= 16384


def test_l2_synthesis_falls_back_to_4b_on_tight():
    choice = route(TaskKind.L2_SYNTHESIS, _budget(8, 3), user_pref="auto")
    assert choice.model == "qwen3:4b"
    assert "tight" in choice.reason.lower() or "内存" in choice.reason


def test_qa_uses_8b_on_comfortable():
    choice = route(TaskKind.QA, _budget(16, 8), user_pref="auto")
    assert choice.model == "qwen3:8b"


def test_qa_uses_4b_on_tight():
    choice = route(TaskKind.QA, _budget(8, 3), user_pref="auto")
    assert choice.model == "qwen3:4b"


def test_user_pref_quality_forces_8b_when_possible():
    choice = route(TaskKind.L1_EXTRACT, _budget(16, 8), user_pref="quality")
    assert choice.model == "qwen3:8b"


def test_user_pref_quality_blocked_on_tight_falls_back():
    choice = route(TaskKind.L2_SYNTHESIS, _budget(8, 3), user_pref="quality")
    assert choice.model == "qwen3:4b"
    assert choice.warning is not None


def test_user_pref_speed_forces_4b_everywhere():
    choice = route(TaskKind.L2_SYNTHESIS, _budget(32, 20), user_pref="speed")
    assert choice.model == "qwen3:4b"
