from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional

from .memory_monitor import MemoryBudget, MemoryTier


class TaskKind(Enum):
    CLEAN = "clean"              # 清洗填充词、错字
    TITLE = "title"              # 生成标题/tag
    L1_EXTRACT = "l1_extract"    # 单块结构化抽取
    L2_SYNTHESIS = "l2_synthesis"  # 多块综合总结
    QA = "qa"                    # 用户自由问答


UserPref = Literal["auto", "quality", "speed"]


@dataclass(frozen=True)
class ModelChoice:
    model: str
    num_ctx: int
    reason: str
    warning: Optional[str] = None


_MODEL_4B = "qwen3:4b"
_MODEL_8B = "qwen3:8b"


def route(task: TaskKind, budget: MemoryBudget, user_pref: UserPref = "auto") -> ModelChoice:
    # speed: 强制 4B，不管 task
    if user_pref == "speed":
        return ModelChoice(_MODEL_4B, 8192, "用户选择速度优先")

    # quality: 尝试 8B，内存不够则降级带 warning
    if user_pref == "quality":
        if budget.can_load_8b():
            return ModelChoice(_MODEL_8B, _ctx_for(task, prefer_long=True),
                               "用户选择质量优先 + 内存充足")
        return ModelChoice(
            _MODEL_4B, _ctx_for(task, prefer_long=False),
            "用户请求 8B 但可用内存不足，降级到 4B",
            warning="可用内存低于 6GB，已自动降级到 4B 以避免严重 swap"
        )

    # auto: 按任务类型默认
    if task in (TaskKind.CLEAN, TaskKind.TITLE, TaskKind.L1_EXTRACT):
        return ModelChoice(_MODEL_4B, 8192, f"{task.value} 默认 4B（机械任务）")

    if task == TaskKind.L2_SYNTHESIS:
        if budget.tier == MemoryTier.TIGHT or not budget.can_load_8b():
            return ModelChoice(_MODEL_4B, 8192,
                               "tight 内存 tier，L2 降级到 4B 配合更多 chunk")
        return ModelChoice(_MODEL_8B, 16384, "L2 综合优先用 8B")

    if task == TaskKind.QA:
        if budget.tier == MemoryTier.TIGHT or not budget.can_load_8b():
            return ModelChoice(_MODEL_4B, 8192, "tight 内存，QA 用 4B + RAG")
        return ModelChoice(_MODEL_8B, 8192, "QA 用 8B + RAG，平衡质量与速度")

    return ModelChoice(_MODEL_4B, 8192, "未识别任务类型，回退 4B")


def _ctx_for(task: TaskKind, prefer_long: bool) -> int:
    if task in (TaskKind.L2_SYNTHESIS,):
        return 16384 if prefer_long else 8192
    return 8192
