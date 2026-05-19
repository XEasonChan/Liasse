from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_env_file = ROOT / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        for _line in _env_file.read_text().splitlines():
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from liasse.models import TranscriptionJob
from liasse.transcribe_pipeline import TranscribePipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local MLX/Qwen flow on test_audio.")
    parser.add_argument("--audio", default=None, help="Audio file to test. Defaults to first file in test_audio/.")
    parser.add_argument("--seconds", type=int, default=60, help="Seconds to transcribe for a quick smoke test.")
    parser.add_argument("--full", action="store_true", help="Run the full audio file instead of a short sample.")
    parser.add_argument("--model", default="Qwen/Qwen3-ASR-0.6B", help="Qwen ASR model id or local path.")
    parser.add_argument("--language", default="Chinese", help="Language hint, e.g. Chinese, English, Cantonese.")
    parser.add_argument("--no-timestamps", action="store_true", help="Skip timestamp alignment for a speed test.")
    parser.add_argument("--no-srt", action="store_true", help="Skip SRT export.")
    parser.add_argument("--diarize", action="store_true", help="Enable pyannote speaker diarization.")
    parser.add_argument("--num-speakers", type=int, default=None, help="Hint number of speakers for diarization (e.g. 2 for 1-on-1 interview).")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    audio_path = Path(args.audio).expanduser() if args.audio else find_first_test_audio()
    if not audio_path:
        print("没有在 test_audio/ 里找到音频文件。")
        return 1

    missing = missing_runtime_modules()
    if missing:
        print("MLX/Qwen 测试依赖还没装好：")
        for name in missing:
            print(f"- {name}")
        print("")
        print("请先双击 Setup MLX Test Env.command，或手动运行：")
        print("  /opt/homebrew/opt/python@3.12/bin/python3.12 -m venv venv")
        print("  venv/bin/python -m pip install -r requirements-mlx.txt")
        return 1

    if not shutil.which("ffmpeg") and (audio_path.suffix.lower() != ".wav" or not args.full):
        print("需要 ffmpeg 来读取 m4a/mp3 或抽取短样本。请先安装 ffmpeg。")
        return 1

    output_dir = ROOT / "outputs" / "test-runs"
    output_dir.mkdir(parents=True, exist_ok=True)

    run_path = audio_path
    if not args.full:
        run_path = make_sample(audio_path, output_dir, args.seconds)

    audio_duration = probe_duration(run_path)
    print(f"测试音频：{run_path}")
    if audio_duration:
        print(f"音频时长：{format_duration(audio_duration)}")
    print(f"模型：{args.model}")
    print("首次运行会下载模型权重；下载完成后可以离线重复运行。")

    def progress(message: str, value: float) -> None:
        print(f"{int(value * 100):3d}% {message}", flush=True)

    started_at = time.perf_counter()
    job = TranscriptionJob(
        audio_path=run_path,
        output_dir=output_dir,
        asr_backend="mlx",
        language=args.language,
        qwen_model=args.model,
        qwen_return_timestamps=not args.no_timestamps,
        summary_enabled=False,
        diarization_enabled=args.diarize,
        diarization_num_speakers=args.num_speakers,
        export_srt=not args.no_srt,
    )
    result = TranscribePipeline(on_progress=progress).run(job)
    elapsed = time.perf_counter() - started_at
    metrics_path = write_metrics(
        result.output_dir,
        source_audio=audio_path,
        run_audio=run_path,
        model=args.model,
        audio_duration_sec=audio_duration,
        elapsed_sec=elapsed,
        timestamps=not args.no_timestamps,
    )
    print("")
    print("跑通了。输出文件：")
    print(f"- {result.markdown_path}")
    print(f"- {result.json_path}")
    if result.srt_path:
        print(f"- {result.srt_path}")
    print(f"- {metrics_path}")
    if audio_duration:
        print("")
        print(f"本次速度：{audio_duration / elapsed:.2f}x 实时")
    return 0


def find_first_test_audio() -> Path | None:
    test_dir = ROOT / "test_audio"
    suffixes = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}
    if not test_dir.exists():
        return None
    for path in sorted(test_dir.iterdir()):
        if path.suffix.lower() in suffixes:
            return path
    return None


def missing_runtime_modules() -> list[str]:
    missing = []
    for name in ["mlx", "numpy", "regex", "huggingface_hub"]:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    return missing


def make_sample(audio_path: Path, output_dir: Path, seconds: int) -> Path:
    sample_path = output_dir / f"{audio_path.stem}-first-{seconds}s.wav"
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-t",
        str(seconds),
        "-i",
        str(audio_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(sample_path),
    ]
    print(f"抽取前 {seconds} 秒测试样本...")
    subprocess.run(command, check=True)
    return sample_path


def probe_duration(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return None
    try:
        return float(completed.stdout.strip())
    except ValueError:
        return None


def write_metrics(
    output_dir: Path,
    *,
    source_audio: Path,
    run_audio: Path,
    model: str,
    audio_duration_sec: float | None,
    elapsed_sec: float,
    timestamps: bool,
) -> Path:
    realtime_factor = (audio_duration_sec / elapsed_sec) if audio_duration_sec else None
    metrics = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_audio": str(source_audio),
        "run_audio": str(run_audio),
        "model": model,
        "timestamps": timestamps,
        "audio_duration_sec": audio_duration_sec,
        "elapsed_sec": elapsed_sec,
        "realtime_factor": realtime_factor,
    }
    path = output_dir / "run-metrics.json"
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分{secs}秒"
    return f"{minutes}分{secs}秒"


if __name__ == "__main__":
    raise SystemExit(main())
