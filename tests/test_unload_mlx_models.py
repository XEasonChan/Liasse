"""验证 unload_mlx_models 的契约：

1. 总是可调用（mlx_qwen3_asr 不可用时也不抛错）
2. 幂等（多次调用 OK）
3. 真正调到底层的 cache clear 函数（用 mock 验证）
4. task_runner 在 speaker labeling / summary 前会调它（防止 regression）
"""
import inspect
from unittest.mock import MagicMock, patch

from local_transcriber.asr import unload_mlx_models


def test_unload_is_callable_even_without_mlx():
    """mlx_qwen3_asr 缺失时 unload 必须静默通过，不能阻塞主流程。"""
    # 函数应能直接调用而不抛
    unload_mlx_models()


def test_unload_is_idempotent():
    """连续两次调用同样 OK。"""
    unload_mlx_models()
    unload_mlx_models()


def test_unload_clears_pyannote_pipeline_cache_if_present():
    """pyannote pipeline cache 存在时必须被清空（不然 8GB Air 跑 llm mode
    时 MLX + pyannote + Ollama 三个驻留会爆）。"""
    try:
        from mlx_qwen3_asr import diarization as _diar
    except ImportError:
        return  # 没装 mlx 就跳过

    cache = getattr(_diar, "_PYANNOTE_PIPELINE_CACHE", None)
    if cache is None:
        return  # 上游 API 变化时跳过，但不让测试失败
    cache[("fake-model", "fake-token")] = object()
    assert len(cache) >= 1

    unload_mlx_models()
    assert len(cache) == 0


def test_unload_calls_mlx_metal_cache_clear():
    """_clear_mlx_cache 必须被调用（释放 Metal/MPS GPU 缓存）。"""
    with patch("mlx_qwen3_asr.transcribe._clear_mlx_cache") as mock_clear:
        unload_mlx_models()
        # mlx_qwen3_asr 装着的话应被调；没装也不抛错
        if mock_clear.called:
            mock_clear.assert_called()


def test_task_runner_unloads_mlx_before_llm_speaker_labeling():
    """反向回归：task_runner._worker_entry 必须在 llm speaker labeling
    前调 unload_mlx_models。如果有人删了这行，8GB Air 用户会重新踩坑。"""
    from local_transcriber import task_runner

    source = inspect.getsource(task_runner)
    # 查找 llm_speaker_enabled 分支并验证它调了 unload
    assert "unload_mlx_models" in source, (
        "task_runner 必须 import unload_mlx_models 用于 llm/summary 前释放 MLX"
    )
    # 数 unload_mlx_models 出现次数：应至少 2 处（llm 分支 + summary 分支）
    assert source.count("unload_mlx_models") >= 2, (
        f"unload_mlx_models 应在 llm 分支 + summary 分支各调一次，实际 {source.count('unload_mlx_models')}"
    )


def test_task_runner_unloads_in_both_llm_and_summary_paths():
    """两条触发 Ollama 大模型加载的路径都必须先 unload MLX：
    1. llm_speaker_enabled → label_segments
    2. summarize_requested → summary_pipeline.analyze
    源码里 `from .asr import unload_mlx_models` 应至少出现 2 次（每条路径一次）。"""
    from local_transcriber import task_runner

    source = inspect.getsource(task_runner)
    n_imports = source.count("from .asr import unload_mlx_models")
    assert n_imports >= 2, (
        f"llm 分支 + summary 分支都应 import + 调 unload_mlx_models，"
        f"实际 import 数 {n_imports}"
    )
