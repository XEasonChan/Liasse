import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from liasse.memory_monitor import MemoryBudget
from liasse.models import TranscriptSegment
from liasse.summary_pipeline import (
    AnalysisResult,
    ProgressEvent,
    analyze,
    load_existing_l1,
)


def _segs():
    return [
        TranscriptSegment(start=0, end=10, text="问题一", speaker="A"),
        TranscriptSegment(start=10, end=30, text="回答一" * 50, speaker="B"),
        TranscriptSegment(start=30, end=40, text="追问", speaker="A"),
        TranscriptSegment(start=40, end=80, text="回答二" * 50, speaker="B"),
    ]


def _l1(idx):
    return MagicMock(
        chunk_index=idx, topics=["t"], quotes=[], entities=[],
        questions_raised=[], raw_text="",
        to_dict=lambda: {"chunk_index": idx, "topics": ["t"], "quotes": [],
                         "entities": [], "questions_raised": []},
    )


def test_analyze_runs_l1_for_each_chunk(tmp_path):
    with patch("liasse.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)) as l1_mock, \
         patch("liasse.summary_pipeline.synthesize_l2",
               return_value="## 总览\n") as l2_mock:
        result = analyze(_segs(), output_dir=tmp_path,
                         task_id="t1", budget=MemoryBudget(16, 8))
    assert l1_mock.call_count >= 1
    assert l2_mock.called
    assert isinstance(result, AnalysisResult)
    assert result.summary_markdown.startswith("## 总览")


def test_analyze_unloads_4b_before_loading_8b_on_comfortable(tmp_path):
    with patch("liasse.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)), \
         patch("liasse.summary_pipeline.synthesize_l2",
               return_value="## 总览\n"), \
         patch("liasse.summary_pipeline.unload_model") as un:
        analyze(_segs(), output_dir=tmp_path, task_id="t2",
                budget=MemoryBudget(16, 8))
    calls = [c.args[0] for c in un.call_args_list]
    assert "qwen3:4b" in calls


def test_analyze_does_not_switch_on_tight(tmp_path):
    with patch("liasse.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)), \
         patch("liasse.summary_pipeline.synthesize_l2",
               return_value="## 总览\n"), \
         patch("liasse.summary_pipeline.unload_model") as un:
        analyze(_segs(), output_dir=tmp_path, task_id="t3",
                budget=MemoryBudget(8, 3))
    calls = [c.args[0] for c in un.call_args_list]
    # 4B 用于 L1 和 L2，中间不应卸载
    # 但 tight 时 L2 完成后会卸载（释放给 QA）— 允许末尾卸载
    intermediate = [c for c in calls if c == "qwen3:4b"]
    # 允许最多 1 次（末尾 cleanup），不应有中间切换
    assert len(intermediate) <= 1


def test_analyze_builds_and_persists_index(tmp_path):
    with patch("liasse.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)), \
         patch("liasse.summary_pipeline.synthesize_l2",
               return_value="## 总览\n"):
        result = analyze(_segs(), output_dir=tmp_path, task_id="t4",
                         budget=MemoryBudget(16, 8))
    assert result.index_path.exists()


def test_analyze_emits_progress_events(tmp_path):
    events = []
    def progress(ev: ProgressEvent):
        events.append(ev)

    with patch("liasse.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)), \
         patch("liasse.summary_pipeline.synthesize_l2",
               return_value="## 总览\n"):
        analyze(_segs(), output_dir=tmp_path, task_id="t5",
                budget=MemoryBudget(16, 8), on_progress=progress)

    phases = {ev.phase for ev in events}
    # 至少这些 phase 必须出现
    assert "chunking" in phases
    assert "l1" in phases
    assert "l2" in phases
    assert "indexing" in phases
    # 最后一个事件 value=1.0
    assert events[-1].value == 1.0
    # value 单调不减
    values = [ev.value for ev in events]
    assert values == sorted(values)
    # 至少一次 l1 事件带 current/total
    l1_evs = [ev for ev in events if ev.phase == "l1"]
    assert any(ev.current is not None and ev.total is not None for ev in l1_evs)


def test_analyze_resumes_from_sqlite_when_l1_already_done(tmp_path):
    # 第一次运行：让 extract_l1 跑 1 次，模拟中断（手动写 SQLite，模拟 1 个 chunk 已完成）
    output_dir = tmp_path
    task_id = "resume-task"

    # 先跑一次完整流程，保存 L1 结果
    with patch("liasse.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)), \
         patch("liasse.summary_pipeline.synthesize_l2",
               return_value="## 总览\n"):
        analyze(_segs(), output_dir=output_dir, task_id=task_id,
                budget=MemoryBudget(16, 8))

    # 验证 SQLite 里有持久化的 L1 行
    existing = load_existing_l1(output_dir, task_id)
    assert len(existing) >= 1

    # 第二次跑：extract_l1 不应再被调用
    with patch("liasse.summary_pipeline.extract_l1") as l1_mock, \
         patch("liasse.summary_pipeline.synthesize_l2",
               return_value="## 总览（重跑）\n"):
        result = analyze(_segs(), output_dir=output_dir, task_id=task_id,
                         budget=MemoryBudget(16, 8))
    assert l1_mock.call_count == 0  # 全部从 SQLite 取回
    assert result.summary_markdown.startswith("## 总览（重跑）")


def test_analyze_runs_l1_concurrently_on_comfortable(tmp_path, monkeypatch):
    """comfortable 档应该并发跑 L1。用一个共享 counter + 短 sleep 验证并发性:
    如果 5 个 chunk 串行 × 0.05s = 0.25s，3 并发应该 ≤ 0.15s。"""
    import time

    # 制造 5 个长 chunk，触发 5 次 L1 调用
    segs = []
    for i in range(5):
        segs.append(TranscriptSegment(start=i*120, end=(i+1)*120,
                                       text="问题" + "内容文本" * 200, speaker="A"))
        segs.append(TranscriptSegment(start=(i+1)*120-1, end=(i+1)*120,
                                       text="回答" + "答案文本" * 200, speaker="B"))

    in_flight = {"current": 0, "peak": 0}
    in_flight_lock = __import__("threading").Lock()

    def slow_l1(chunk, total_chunks, **kw):
        with in_flight_lock:
            in_flight["current"] += 1
            in_flight["peak"] = max(in_flight["peak"], in_flight["current"])
        time.sleep(0.05)
        with in_flight_lock:
            in_flight["current"] -= 1
        return _l1(chunk.index)

    with patch("liasse.summary_pipeline.extract_l1", side_effect=slow_l1), \
         patch("liasse.summary_pipeline.synthesize_l2", return_value="ok"), \
         patch("liasse.summary_pipeline.TranscriptIndex.build",
               return_value=MagicMock(save=lambda: None)):
        t0 = time.time()
        analyze(segs, output_dir=tmp_path, task_id="par",
                budget=MemoryBudget(16, 8))  # comfortable
        wall = time.time() - t0

    # comfortable 档默认 3 并发，peak in-flight 应 > 1
    assert in_flight["peak"] >= 2, f"expected concurrent calls, peak={in_flight['peak']}"


def test_analyze_runs_l1_serially_on_tight(tmp_path, monkeypatch):
    """tight 档应该串行（避免内存峰值）。验证 peak in-flight == 1。"""
    import time

    segs = []
    for i in range(4):
        segs.append(TranscriptSegment(start=i*120, end=(i+1)*120,
                                       text="问题" + "内容" * 300, speaker="A"))
        segs.append(TranscriptSegment(start=(i+1)*120-1, end=(i+1)*120,
                                       text="回答" + "答案" * 300, speaker="B"))

    in_flight = {"current": 0, "peak": 0}
    lk = __import__("threading").Lock()

    def slow_l1(chunk, total_chunks, **kw):
        with lk:
            in_flight["current"] += 1
            in_flight["peak"] = max(in_flight["peak"], in_flight["current"])
        time.sleep(0.02)
        with lk:
            in_flight["current"] -= 1
        return _l1(chunk.index)

    with patch("liasse.summary_pipeline.extract_l1", side_effect=slow_l1), \
         patch("liasse.summary_pipeline.synthesize_l2", return_value="ok"), \
         patch("liasse.summary_pipeline.TranscriptIndex.build",
               return_value=MagicMock(save=lambda: None)), \
         patch("liasse.summary_pipeline.unload_model"):
        analyze(segs, output_dir=tmp_path, task_id="ser",
                budget=MemoryBudget(8, 2))  # tight: total=8GB, free=2GB

    assert in_flight["peak"] == 1, f"tight should be serial, peak={in_flight['peak']}"


def test_l1_concurrency_env_override(monkeypatch):
    """WHISPERQWEN_L1_CONCURRENCY env 必须能强制覆盖（测试 / 调优用）。"""
    from liasse.summary_pipeline import _l1_concurrency

    budget_tight = MemoryBudget(8, 2)
    budget_comfy = MemoryBudget(16, 8)

    monkeypatch.delenv("WHISPERQWEN_L1_CONCURRENCY", raising=False)
    assert _l1_concurrency(budget_tight) == 1
    assert _l1_concurrency(budget_comfy) == 3

    monkeypatch.setenv("WHISPERQWEN_L1_CONCURRENCY", "5")
    assert _l1_concurrency(budget_tight) == 5
    assert _l1_concurrency(budget_comfy) == 5

    monkeypatch.setenv("WHISPERQWEN_L1_CONCURRENCY", "1")
    assert _l1_concurrency(budget_comfy) == 1


def test_analyze_preserves_chunk_order_under_concurrency(tmp_path):
    """并发完成顺序乱了，l1_results 必须按 chunk.index 排序。"""
    import random
    import time

    segs = []
    for i in range(6):
        segs.append(TranscriptSegment(start=i*120, end=(i+1)*120,
                                       text="问题" + "内容" * 250, speaker="A"))
        segs.append(TranscriptSegment(start=(i+1)*120-1, end=(i+1)*120,
                                       text="回答" + "答案" * 250, speaker="B"))

    def jittered_l1(chunk, total_chunks, **kw):
        time.sleep(random.uniform(0.0, 0.05))
        return _l1(chunk.index)

    with patch("liasse.summary_pipeline.extract_l1", side_effect=jittered_l1), \
         patch("liasse.summary_pipeline.synthesize_l2", return_value="ok"), \
         patch("liasse.summary_pipeline.TranscriptIndex.build",
               return_value=MagicMock(save=lambda: None)):
        result = analyze(segs, output_dir=tmp_path, task_id="ord",
                         budget=MemoryBudget(16, 8))

    indices = [l1.chunk_index for l1 in result.l1_results]
    assert indices == sorted(indices), f"l1_results order broken: {indices}"
