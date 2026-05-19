import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_transcriber.memory_monitor import MemoryBudget
from local_transcriber.models import TranscriptSegment
from local_transcriber.summary_pipeline import (
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
    with patch("local_transcriber.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)) as l1_mock, \
         patch("local_transcriber.summary_pipeline.synthesize_l2",
               return_value="## 总览\n") as l2_mock:
        result = analyze(_segs(), output_dir=tmp_path,
                         task_id="t1", budget=MemoryBudget(16, 8))
    assert l1_mock.call_count >= 1
    assert l2_mock.called
    assert isinstance(result, AnalysisResult)
    assert result.summary_markdown.startswith("## 总览")


def test_analyze_unloads_4b_before_loading_8b_on_comfortable(tmp_path):
    with patch("local_transcriber.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)), \
         patch("local_transcriber.summary_pipeline.synthesize_l2",
               return_value="## 总览\n"), \
         patch("local_transcriber.summary_pipeline.unload_model") as un:
        analyze(_segs(), output_dir=tmp_path, task_id="t2",
                budget=MemoryBudget(16, 8))
    calls = [c.args[0] for c in un.call_args_list]
    assert "qwen3:4b" in calls


def test_analyze_does_not_switch_on_tight(tmp_path):
    with patch("local_transcriber.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)), \
         patch("local_transcriber.summary_pipeline.synthesize_l2",
               return_value="## 总览\n"), \
         patch("local_transcriber.summary_pipeline.unload_model") as un:
        analyze(_segs(), output_dir=tmp_path, task_id="t3",
                budget=MemoryBudget(8, 3))
    calls = [c.args[0] for c in un.call_args_list]
    # 4B 用于 L1 和 L2，中间不应卸载
    # 但 tight 时 L2 完成后会卸载（释放给 QA）— 允许末尾卸载
    intermediate = [c for c in calls if c == "qwen3:4b"]
    # 允许最多 1 次（末尾 cleanup），不应有中间切换
    assert len(intermediate) <= 1


def test_analyze_builds_and_persists_index(tmp_path):
    with patch("local_transcriber.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)), \
         patch("local_transcriber.summary_pipeline.synthesize_l2",
               return_value="## 总览\n"):
        result = analyze(_segs(), output_dir=tmp_path, task_id="t4",
                         budget=MemoryBudget(16, 8))
    assert result.index_path.exists()


def test_analyze_emits_progress_events(tmp_path):
    events = []
    def progress(ev: ProgressEvent):
        events.append(ev)

    with patch("local_transcriber.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)), \
         patch("local_transcriber.summary_pipeline.synthesize_l2",
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
    with patch("local_transcriber.summary_pipeline.extract_l1",
               side_effect=lambda chunk, total_chunks, **kw: _l1(chunk.index)), \
         patch("local_transcriber.summary_pipeline.synthesize_l2",
               return_value="## 总览\n"):
        analyze(_segs(), output_dir=output_dir, task_id=task_id,
                budget=MemoryBudget(16, 8))

    # 验证 SQLite 里有持久化的 L1 行
    existing = load_existing_l1(output_dir, task_id)
    assert len(existing) >= 1

    # 第二次跑：extract_l1 不应再被调用
    with patch("local_transcriber.summary_pipeline.extract_l1") as l1_mock, \
         patch("local_transcriber.summary_pipeline.synthesize_l2",
               return_value="## 总览（重跑）\n"):
        result = analyze(_segs(), output_dir=output_dir, task_id=task_id,
                         budget=MemoryBudget(16, 8))
    assert l1_mock.call_count == 0  # 全部从 SQLite 取回
    assert result.summary_markdown.startswith("## 总览（重跑）")
