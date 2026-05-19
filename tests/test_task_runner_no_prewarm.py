import inspect

from local_transcriber import task_runner
from local_transcriber.task_runner import TaskRunner


def test_task_runner_has_no_prewarm_digest_method():
    """该方法已废弃；如果它回来了，说明又长出双轨。"""
    assert not hasattr(TaskRunner, "_prewarm_digest"), (
        "TaskRunner._prewarm_digest 已废弃，不应回归"
    )


def test_task_runner_does_not_import_chat_module():
    """task_runner 内部不应再 import chat 模块。"""
    source = inspect.getsource(task_runner)
    assert "from . import chat" not in source, (
        "task_runner 不应再 'from . import chat'"
    )
    assert "import local_transcriber.chat" not in source


def test_task_runner_does_not_reference_prewarm_chat_variable():
    """残留的 prewarm_chat 变量会让审阅者困惑，确保彻底清理。"""
    source = inspect.getsource(task_runner)
    assert "prewarm_chat" not in source
