from unittest.mock import MagicMock, patch

from local_transcriber.memory_monitor import MemoryBudget, MemoryTier


def _mock_vm(total_gb: float, available_gb: float):
    vm = MagicMock()
    vm.total = int(total_gb * 1024**3)
    vm.available = int(available_gb * 1024**3)
    return vm


def test_tier_tight_for_8gb():
    with patch("local_transcriber.memory_monitor.psutil.virtual_memory",
               return_value=_mock_vm(8, 3)):
        b = MemoryBudget.detect()
    assert b.tier == MemoryTier.TIGHT


def test_tier_comfortable_for_16gb():
    with patch("local_transcriber.memory_monitor.psutil.virtual_memory",
               return_value=_mock_vm(16, 8)):
        b = MemoryBudget.detect()
    assert b.tier == MemoryTier.COMFORTABLE


def test_tier_spacious_for_32gb():
    with patch("local_transcriber.memory_monitor.psutil.virtual_memory",
               return_value=_mock_vm(32, 18)):
        b = MemoryBudget.detect()
    assert b.tier == MemoryTier.SPACIOUS


def test_can_load_8b_needs_at_least_6gb_available():
    with patch("local_transcriber.memory_monitor.psutil.virtual_memory",
               return_value=_mock_vm(16, 5.5)):
        b = MemoryBudget.detect()
    assert b.can_load_8b() is False

    with patch("local_transcriber.memory_monitor.psutil.virtual_memory",
               return_value=_mock_vm(16, 7.0)):
        b = MemoryBudget.detect()
    assert b.can_load_8b() is True


def test_can_load_4b_needs_at_least_3gb_available():
    with patch("local_transcriber.memory_monitor.psutil.virtual_memory",
               return_value=_mock_vm(8, 2.0)):
        b = MemoryBudget.detect()
    assert b.can_load_4b() is False
