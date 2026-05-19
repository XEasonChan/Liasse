"""服务层：纯函数式的本机/外部健康检查与文件系统辅助。

routers 应该只做参数校验 + ORM 操作 + 调 services。具体业务（探活 Ollama、
查 HF cache、ffprobe 取时长、计算唯一文件名）都放这里，方便单元测试与
他处复用。
"""

from .ollama_health import check_ollama, check_ollama_model
from .model_cache import check_model_cache, check_runtime_ready, read_install_progress
from .fs_helpers import unique_path, probe_audio_duration

__all__ = [
    "check_ollama",
    "check_ollama_model",
    "check_model_cache",
    "check_runtime_ready",
    "read_install_progress",
    "unique_path",
    "probe_audio_duration",
]
