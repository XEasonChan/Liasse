from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Optional

from .alignment import assign_speakers
from .asr import create_asr_backend
from .diarization import PyannoteDiarizer, speaker_turns_from_segments
from .exporters import export_json, export_markdown, export_srt
from .models import PipelineResult, SpeakerTurn, SummaryResult, TranscriptionJob, TranscriptSegment
from .summarizer import OllamaSummarizer

ProgressCallback = Callable[[str, float], None]

ASR_PROGRESS_START = 0.04
ASR_CHUNK_PROGRESS_END = 0.82
ASR_PROGRESS_DONE = 0.88
SUMMARY_PROGRESS_START = 0.91
EXPORT_PROGRESS_START = 0.96


class LocalTranscriptionPipeline:
    def __init__(self, on_progress: Optional[ProgressCallback] = None) -> None:
        self.on_progress = on_progress or (lambda _message, _value: None)

    def run(self, job: TranscriptionJob) -> PipelineResult:
        if not job.audio_path.exists() and job.asr_backend != "demo":
            raise FileNotFoundError(f"找不到音频文件：{job.audio_path}")

        job.output_dir.mkdir(parents=True, exist_ok=True)
        output_dir = self._job_output_dir(job)
        output_dir.mkdir(parents=True, exist_ok=True)

        self._progress("准备转录音频", ASR_PROGRESS_START)
        segments = self._transcribe(job)
        if not segments:
            raise RuntimeError("转录没有返回任何文本。")

        speaker_turns: List[SpeakerTurn] = []
        mlx_diarization = job.asr_backend.lower().strip() in {"mlx", "mlx-qwen", "mlx-qwen3-asr"}
        if job.diarization_enabled and not mlx_diarization:
            self._progress("正在识别发言人", ASR_PROGRESS_DONE)
            speaker_turns = PyannoteDiarizer(job.pyannote_model, job.hf_token).diarize(job.audio_path)
            segments = assign_speakers(segments, speaker_turns)
        else:
            speaker_turns = speaker_turns_from_segments(segments)

        summary: Optional[SummaryResult] = None
        if job.summary_enabled:
            self._progress("正在生成本地摘要", SUMMARY_PROGRESS_START)
            summary = OllamaSummarizer(job.summary_model).summarize(segments)

        self._progress("正在导出文件", EXPORT_PROGRESS_START)
        markdown_path = output_dir / f"{job.audio_path.stem or 'demo'}-transcript.md"
        json_path = output_dir / f"{job.audio_path.stem or 'demo'}-transcript.json"
        srt_path = output_dir / f"{job.audio_path.stem or 'demo'}-transcript.srt"

        export_markdown(markdown_path, job.audio_path, segments, speaker_turns, summary)
        export_json(json_path, job.audio_path, segments, speaker_turns, summary)
        if job.export_srt:
            export_srt(srt_path, segments)
        else:
            srt_path = None

        self._progress("完成", 1.0)
        return PipelineResult(
            audio_path=job.audio_path,
            output_dir=output_dir,
            markdown_path=markdown_path,
            json_path=json_path,
            srt_path=srt_path,
            segments=segments,
            speaker_turns=speaker_turns,
            summary=summary,
        )

    def _transcribe(self, job: TranscriptionJob) -> List[TranscriptSegment]:
        backend = create_asr_backend(
            backend=job.asr_backend,
            qwen_model=job.qwen_model,
            qwen_aligner=job.qwen_aligner,
            qwen_return_timestamps=job.qwen_return_timestamps,
            whisper_model=job.whisper_model,
            diarization_enabled=job.diarization_enabled,
            pyannote_model=job.pyannote_model,
            hf_token=job.hf_token,
            num_speakers=job.diarization_num_speakers,
        )
        return backend.transcribe(job.audio_path, job.language, on_progress=self._asr_progress)

    def _job_output_dir(self, job: TranscriptionJob) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        stem = job.audio_path.stem or "demo"
        return job.output_dir / f"{stem}-{timestamp}"

    def _progress(self, message: str, value: float) -> None:
        self.on_progress(message, self._clamp_progress(value))

    def _asr_progress(self, payload: dict[str, Any]) -> None:
        event = str(payload.get("event") or "")
        if event == "chunks_prepared":
            total = self._positive_int(payload.get("total_chunks"))
            if total:
                self._progress(f"准备转录音频（共 {total} 段）", ASR_PROGRESS_START)
            else:
                self._progress("准备转录音频", ASR_PROGRESS_START)
            return

        if event in {"chunk_started", "chunk_completed"}:
            total = self._positive_int(payload.get("total_chunks"))
            index = self._positive_int(payload.get("chunk_index"))
            raw = self._float_or_none(payload.get("progress"))
            value = self._scale_asr_progress(raw if raw is not None else 0.0)
            if total and index:
                self._progress(f"正在转录音频 {index}/{total}", value)
            else:
                self._progress("正在转录音频", value)
            return

        if event == "diarization_completed":
            self._progress("正在整理发言人分段", ASR_PROGRESS_DONE - 0.01)
            return

        if event == "completed":
            self._progress("转录完成，准备导出", ASR_PROGRESS_DONE)
            return

    def _scale_asr_progress(self, raw_value: float) -> float:
        raw = self._clamp_progress(raw_value)
        return ASR_PROGRESS_START + raw * (ASR_CHUNK_PROGRESS_END - ASR_PROGRESS_START)

    def _clamp_progress(self, value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    def _float_or_none(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _positive_int(self, value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
