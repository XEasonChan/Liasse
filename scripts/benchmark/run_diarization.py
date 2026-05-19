#!/usr/bin/env python3
"""跑当前 liasse pipeline 在 5 个 benchmark samples 上,落 prediction JSON。

**24GB 安全规则**:每次只跑一个 ASR 模型,必须显式 --model 指定。
两个模型同进程会爆内存(MLX 不会自动释放上一个模型的权重)。

写入:
  scripts/benchmark/results/<sample>__qwen-0.6B.pred.json
  scripts/benchmark/results/<sample>__qwen-1.7B.pred.json

speakerMode 固定 pyannote(精确声纹模式),language 固定 Chinese,2 speakers。

必需 args:
  --model qwen-0.6B  跑 0.6B
  --model qwen-1.7B  跑 1.7B

可选 args:
  --skip-checks     跳过 RAM / ollama pre-flight (默认会跑,失败 abort)
"""
from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

SAMPLES = ROOT / "scripts" / "benchmark" / "samples"
PRED = ROOT / "scripts" / "benchmark" / "results"

ASR_MODELS = {
    "qwen-0.6B": "Qwen/Qwen3-ASR-0.6B",
    "qwen-1.7B": "Qwen/Qwen3-ASR-1.7B",
}

# 按 sample 文件名前缀决定 ASR language。Qwen3-ASR 支持 Chinese/English 等,
# 错配 language 会显著降低 ASR 质量进而拖垮 alignment。
_LANG_BY_PREFIX = {
    "s":    "Chinese",   # legacy s1-s5 (xiaojun_yaoshunyu)
    "xj":   "Chinese",
    "luyu": "Chinese",
    "kd":   "Chinese",   # kedaibiao_weihui (中文,男+女)
    "cd":   "English",   # Lenny podcast (Claude design)
    "ce":   "English",   # Lenny podcast (Claude engineer)
    "cp":   "English",   # Lenny podcast (Claude product)
}


def _language_for(stem: str) -> str:
    for prefix in sorted(_LANG_BY_PREFIX, key=len, reverse=True):
        if stem.startswith(prefix):
            return _LANG_BY_PREFIX[prefix]
    return "Chinese"  # safe fallback

# 单模型推理 + pyannote MPS 大致 RAM 上限。小于此值 abort,避免开始才崩。
# 0.6B: ~4GB live; 1.7B: ~8GB live;留 buffer 但 macOS inactive 可回收。
_MIN_FREE_GB = {"qwen-0.6B": 5.0, "qwen-1.7B": 8.0}


def _load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _git_rev() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, text=True,
        ).strip()
    except Exception:
        return "unknown"


def _probe_dur(audio: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def run_one(audio: Path, asr_model: str, model_tag: str) -> dict:
    from liasse.models import TranscriptionJob
    from liasse.transcribe_pipeline import TranscribePipeline

    out_dir = PRED / "_pipeline_outputs" / f"{audio.stem}__{model_tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    job = TranscriptionJob(
        audio_path=audio,
        output_dir=out_dir,
        asr_backend="mlx",
        language=_language_for(audio.stem),
        qwen_model=asr_model,
        qwen_return_timestamps=True,
        diarization_enabled=True,
        diarization_num_speakers=2,
        pyannote_model="pyannote/speaker-diarization-community-1",
        hf_token=os.environ.get("HF_TOKEN") or os.environ.get("PYANNOTE_AUTH_TOKEN"),
    )
    t0 = time.time()
    result = TranscribePipeline().run(job)
    wall = time.time() - t0
    dur = _probe_dur(audio)

    turns = []
    for s in result.segments:
        turns.append({
            "start": float(s.start or 0.0),
            "end": float(s.end or 0.0),
            "speaker": str(s.speaker),
            "text": str(s.text or ""),
        })

    return {
        "sample": audio.stem,
        "audio_dur_sec": dur,
        "asr_model": asr_model,
        "speakers": sorted({t["speaker"] for t in turns}),
        "wall_sec": round(wall, 2),
        "rt_factor": round(dur / wall, 2) if wall > 0 else None,
        "pipeline_version": _git_rev(),
        "turns": turns,
    }


def _wall_str(s: float) -> str:
    if s < 120:
        return f"{s:.1f}s"
    return f"{s / 60:.1f}min"


def _free_ram_gb() -> Optional[float]:
    """macOS vm_stat → 当前 free + inactive 字节数(可立即回收的)。"""
    try:
        out = subprocess.check_output(["vm_stat"], text=True)
    except Exception:
        return None
    page_size = 16384
    pages_free = pages_inactive = 0
    for line in out.splitlines():
        if line.startswith("Mach Virtual Memory Statistics"):
            m = line.split("page size of ")
            if len(m) == 2:
                try:
                    page_size = int(m[1].rstrip(" bytes)\n"))
                except Exception:
                    pass
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        n = v.strip().rstrip(".")
        try:
            n = int(n)
        except ValueError:
            continue
        if k == "Pages free":
            pages_free = n
        elif k == "Pages inactive":
            pages_inactive = n
    return (pages_free + pages_inactive) * page_size / (1024 ** 3)


def _ollama_running() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def _preflight(model_tag: str) -> int:
    free = _free_ram_gb()
    needed = _MIN_FREE_GB.get(model_tag, 6.0)
    if free is not None:
        print(f"[pre-flight] free RAM ≈ {free:.1f} GB (need ≥ {needed:.1f} GB for {model_tag})")
        if free < needed:
            print(
                f"\nABORT: free RAM {free:.1f}GB < {needed:.1f}GB required for {model_tag}.\n"
                "  Free memory:\n"
                "    pkill -f 'ollama serve'   # frees ~6GB if qwen3:8b loaded\n"
                "    close browser tabs / IDE windows you don't need\n"
                "  Then retry. Override with --skip-checks (NOT recommended).\n",
                file=sys.stderr,
            )
            return 1
    if _ollama_running():
        print(
            "\nWARN: ollama is running on :11434 and may be holding 6+ GB.\n"
            "  Strongly recommend:  pkill -f 'ollama serve'\n"
            "  Continuing anyway in 5s (Ctrl-C to abort)...",
            file=sys.stderr,
        )
        time.sleep(5)
    return 0


def main(argv: List[str] | None = None) -> int:
    _load_env()
    os.environ.setdefault("WHISPERQWEN_DISABLE_RUNNER", "1")
    PRED.mkdir(parents=True, exist_ok=True)

    argv = argv or []
    only_tag: Optional[str] = None
    if "--model" in argv:
        idx = argv.index("--model")
        if idx + 1 < len(argv):
            only_tag = argv[idx + 1]
    if only_tag not in ASR_MODELS:
        print(
            "ERROR: --model is required and must be one of: "
            f"{sorted(ASR_MODELS.keys())}\n\n"
            "  24GB safety rule: never run two ASR models in the same process.\n"
            "  Run them as separate python invocations.\n",
            file=sys.stderr,
        )
        return 2

    if "--skip-checks" not in argv:
        rc = _preflight(only_tag)
        if rc != 0:
            return rc

    samples = sorted([
        *SAMPLES.glob("*.m4a"),
        *SAMPLES.glob("*.mp3"),
    ])
    if not samples:
        print(f"ERROR: no samples in {SAMPLES}. Run cut_samples.py first.",
              file=sys.stderr)
        return 1

    asr_model = ASR_MODELS[only_tag]
    for audio in samples:
        pred_path = PRED / f"{audio.stem}__{only_tag}.pred.json"
        if pred_path.exists():
            print(f"  ✓ exists {pred_path.name} (delete to re-run)")
            continue
        free_before = _free_ram_gb()
        print(f"\n=== {audio.name}  [model={only_tag}]  free RAM ≈ "
              f"{free_before:.1f}GB" if free_before is not None else
              f"\n=== {audio.name}  [model={only_tag}] ===")
        try:
            r = run_one(audio, asr_model, only_tag)
            pred_path.write_text(
                json.dumps(r, indent=2, ensure_ascii=False)
            )
            print(f"  ✓ {_wall_str(r['wall_sec'])} wall, RT={r['rt_factor']}, "
                  f"{len(r['turns'])} turns, {len(r['speakers'])} speakers")
        except Exception as exc:
            import traceback
            print(f"  ✗ FAILED: {exc}\n{traceback.format_exc()}",
                  file=sys.stderr)
        # 每个样本之间手动回收,降低 unified memory 累积压力。
        gc.collect()
        try:
            import mlx.core as _mx
            if hasattr(_mx, "metal") and hasattr(_mx.metal, "clear_cache"):
                _mx.metal.clear_cache()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
