from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import psutil


class MemoryTier(Enum):
    TIGHT = "tight"          # < 10 GB 总内存（8GB M2 Air）
    COMFORTABLE = "comfortable"  # 10–18 GB（16GB M1/M2）
    SPACIOUS = "spacious"    # >= 18 GB


_MIN_4B_AVAILABLE_GB = 3.0
_MIN_8B_AVAILABLE_GB = 6.0


@dataclass(frozen=True)
class MemoryBudget:
    total_gb: float
    available_gb: float

    @classmethod
    def detect(cls) -> "MemoryBudget":
        vm = psutil.virtual_memory()
        return cls(
            total_gb=vm.total / (1024**3),
            available_gb=vm.available / (1024**3),
        )

    @property
    def tier(self) -> MemoryTier:
        if self.total_gb < 10:
            return MemoryTier.TIGHT
        if self.total_gb < 18:
            return MemoryTier.COMFORTABLE
        return MemoryTier.SPACIOUS

    def can_load_4b(self) -> bool:
        return self.available_gb >= _MIN_4B_AVAILABLE_GB

    def can_load_8b(self) -> bool:
        return self.available_gb >= _MIN_8B_AVAILABLE_GB

    def describe(self) -> str:
        return (
            f"内存 {self.total_gb:.1f}GB 总 / {self.available_gb:.1f}GB 可用 "
            f"(tier={self.tier.value})"
        )
