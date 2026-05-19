from __future__ import annotations

import argparse
from pathlib import Path

from .models import TranscriptionJob
from .pipeline import LocalTranscriptionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地访谈转录批处理")
    parser.add_argument("audio", nargs="+", help="一个或多个本地音频文件")
    parser.add_argument("--output-dir", default="outputs", help="输出文件夹")
    parser.add_argument("--backend", default="mlx", choices=["mlx", "qwen", "whisper", "demo"], help="转录后端")
    parser.add_argument("--language", default=None, help="语言，例如 Chinese、English；留空为自动")
    parser.add_argument("--qwen-model", default="Qwen/Qwen3-ASR-0.6B")
    parser.add_argument("--qwen-aligner", default="Qwen/Qwen3-ForcedAligner-0.6B")
    parser.add_argument("--whisper-model", default="large-v3")
    parser.add_argument("--diarize", action="store_true", help="启用 pyannote 发言人识别")
    parser.add_argument("--pyannote-model", default="pyannote/speaker-diarization-community-1")
    parser.add_argument("--hf-token", default=None)
    parser.add_argument("--no-srt", action="store_true", help="不导出 SRT")
    # 注：CLI 不再支持 --summarize（旧 OllamaSummarizer 已删）。摘要现在
    # 通过 web UI 的 /summary 路由触发 summary_pipeline.analyze()。批处理
    # 场景如果需要摘要，请用 Python API 直接调 summary_pipeline.analyze。
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir).expanduser()

    for index, audio in enumerate(args.audio, start=1):
        audio_path = Path(audio).expanduser()

        def progress(message: str, value: float) -> None:
            percent = int(value * 100)
            print(f"[{index}/{len(args.audio)}] {percent:3d}% {message}", flush=True)

        job = TranscriptionJob(
            audio_path=audio_path,
            output_dir=output_dir,
            asr_backend=args.backend,
            language=args.language,
            qwen_model=args.qwen_model,
            qwen_aligner=args.qwen_aligner,
            whisper_model=args.whisper_model,
            diarization_enabled=args.diarize,
            pyannote_model=args.pyannote_model,
            hf_token=args.hf_token,
            export_srt=not args.no_srt,
        )
        result = LocalTranscriptionPipeline(on_progress=progress).run(job)
        print(f"完成：{result.markdown_path}", flush=True)


if __name__ == "__main__":
    main()
