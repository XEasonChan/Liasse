#!/usr/bin/env python3
"""转录性能 eval — 跑 2 分钟样本，详细打点。

跑两次：fast 模式（纯 ASR）和 llm 模式（ASR + LLM speaker labeling）。
不跑 pyannote（避免 4 小时痛点 + diarization 模型可能未就绪）。

输出:
- outputs/eval-2min/<mode>/  — 各自的转录产物
- outputs/eval-2min-report.json  — 两次的事件流 + 统计
- stdout 实时进度
"""
from __future__ import annotations

import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# 加载 .env （HF_TOKEN 等）
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
env_file = ROOT / ".env"
if env_file.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file)
    except ImportError:
        for line in env_file.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

import psutil

from liasse.models import TranscriptionJob
from liasse.transcribe_pipeline import TranscribePipeline


AUDIO = ROOT / "test_audio" / "cut-2min-mid.m4a"
OUT_ROOT = ROOT / "outputs" / "eval-2min"
REPORT = ROOT / "outputs" / "eval-2min-report.json"


def run_one(mode: str) -> Dict[str, Any]:
    """Returns dict with mode, events, total_wall_sec, segments_count."""
    print(f"\n{'=' * 60}")
    print(f"MODE: {mode}")
    print(f"{'=' * 60}")

    out_dir = OUT_ROOT / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = psutil.Process()

    events: List[Dict[str, Any]] = []
    t0 = time.time()
    peak_rss_mb = 0.0

    def log(stage: str, value: float, extra: Dict[str, Any] = None):
        nonlocal peak_rss_mb
        elapsed = time.time() - t0
        rss_mb = proc.memory_info().rss / 1024 ** 2
        peak_rss_mb = max(peak_rss_mb, rss_mb)
        ev = {
            "wall_sec": round(elapsed, 3),
            "value": round(float(value), 4),
            "stage": stage,
            "rss_mb": round(rss_mb, 1),
        }
        if extra:
            ev["extra"] = extra
        events.append(ev)
        print(f"[{elapsed:6.2f}s | rss {rss_mb:6.0f}MB] {value * 100:5.1f}% {stage}")

    partial_count = 0

    def on_partial(payload: Dict[str, Any]):
        nonlocal partial_count
        partial_count += 1
        seg_count = len(payload.get("segments") or [])
        log("partial_transcript", 0.0, {"chunk_idx": partial_count, "segments_so_far": seg_count})

    diarize_enabled = False
    if mode == "pyannote":
        diarize_enabled = True

    job = TranscriptionJob(
        audio_path=AUDIO,
        output_dir=out_dir,
        asr_backend="mlx",
        language="Chinese",
        qwen_model="Qwen/Qwen3-ASR-0.6B",
        qwen_return_timestamps=True,
        diarization_enabled=diarize_enabled,
        diarization_num_speakers=2,
        hf_token=os.environ.get("HF_TOKEN") or os.environ.get("PYANNOTE_AUTH_TOKEN"),
        export_srt=True,
    )

    log("init", 0.0, {"audio": str(AUDIO), "audio_dur_sec": 120.0, "mode": mode})

    pipeline = TranscribePipeline(on_progress=log, on_partial_transcript=on_partial)
    result = pipeline.run(job)

    transcribe_wall = time.time() - t0

    # llm 模式：在 pipeline 之后跑 LLM speaker labeling
    if mode == "llm":
        log("llm_speaker_labeling_start", 0.88)
        try:
            from liasse.diarization import speaker_turns_from_segments
            from liasse.speaker_labeler import label_segments

            labeling = label_segments(
                result.segments,
                model="qwen3:4b",
                num_speakers=2,
            )
            log("llm_speaker_labeling_done", 0.98, {
                "speakers_assigned": len(set(s.speaker for s in labeling.segments)),
                "suggested_labels": labeling.speaker_labels,
            })
            result.segments = labeling.segments
            result.speaker_turns = speaker_turns_from_segments(result.segments)
        except Exception as exc:
            log("llm_speaker_labeling_FAILED", 0.99, {"error": str(exc)})

    log("done", 1.0, {
        "segments": len(result.segments),
        "speakers": sorted(set(s.speaker for s in result.segments)),
        "markdown_path": str(result.markdown_path),
    })

    total_wall = time.time() - t0
    summary = {
        "mode": mode,
        "audio_dur_sec": 120.0,
        "total_wall_sec": round(total_wall, 2),
        "transcribe_wall_sec": round(transcribe_wall, 2),
        "realtime_factor": round(120.0 / total_wall, 3),
        "segments_count": len(result.segments),
        "speaker_count": len(set(s.speaker for s in result.segments)),
        "partial_transcript_events": partial_count,
        "peak_rss_mb": round(peak_rss_mb, 1),
        "events": events,
    }

    print(f"\n--- {mode}: {total_wall:.1f}s wall for 120s audio (RT factor {summary['realtime_factor']:.2f}x), peak RSS {peak_rss_mb:.0f}MB ---")

    # 强制 gc，让下一次跑从干净状态开始
    del pipeline, result
    gc.collect()

    return summary


def main():
    print(f"AUDIO: {AUDIO}")
    print(f"OUT  : {OUT_ROOT}")
    if not AUDIO.exists():
        print("ERROR: audio not found", file=sys.stderr)
        sys.exit(1)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    sys_info = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "cpu_count": psutil.cpu_count(logical=True),
        "total_ram_gb": round(psutil.virtual_memory().total / 1024 ** 3, 1),
        "available_ram_gb_at_start": round(psutil.virtual_memory().available / 1024 ** 3, 1),
    }
    print(f"SYSTEM: {sys_info}")

    runs = []
    for mode in ["fast", "llm", "pyannote"]:
        try:
            runs.append(run_one(mode))
        except Exception as exc:
            import traceback
            print(f"\n!!! {mode} FAILED: {exc}", file=sys.stderr)
            traceback.print_exc()
            runs.append({"mode": mode, "error": str(exc), "traceback": traceback.format_exc()})

    report = {
        "system": sys_info,
        "runs": runs,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n\nREPORT: {REPORT}")

    # 打印一行总结
    print("\n=== SUMMARY ===")
    for run in runs:
        if "error" in run:
            print(f"  {run['mode']:10s}  FAILED: {run['error'][:80]}")
        else:
            print(f"  {run['mode']:10s}  {run['total_wall_sec']:6.1f}s wall  RT={run['realtime_factor']:.2f}x  "
                  f"segments={run['segments_count']}  speakers={run['speaker_count']}  "
                  f"peak_RSS={run['peak_rss_mb']:.0f}MB  partials={run['partial_transcript_events']}")


if __name__ == "__main__":
    main()
