from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TranscriptSegment:
    start: Optional[float]
    end: Optional[float]
    text: str
    speaker: str = "SPEAKER_00"
    confidence: Optional[float] = None
    source: str = "asr"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SummaryResult:
    model: str
    text: str
    chunks: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptionJob:
    audio_path: Path
    output_dir: Path
    asr_backend: str = "mlx"
    language: Optional[str] = None
    qwen_model: str = "Qwen/Qwen3-ASR-0.6B"
    qwen_aligner: str = "Qwen/Qwen3-ForcedAligner-0.6B"
    qwen_return_timestamps: bool = True
    whisper_model: str = "large-v3"
    diarization_enabled: bool = False
    diarization_num_speakers: Optional[int] = None
    pyannote_model: str = "pyannote/speaker-diarization-community-1"
    hf_token: Optional[str] = None
    export_srt: bool = True


@dataclass
class PipelineResult:
    audio_path: Path
    output_dir: Path
    markdown_path: Path
    json_path: Path
    srt_path: Optional[Path]
    segments: List[TranscriptSegment]
    speaker_turns: List[SpeakerTurn]
    summary: Optional[SummaryResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audio_path": str(self.audio_path),
            "output_dir": str(self.output_dir),
            "markdown_path": str(self.markdown_path),
            "json_path": str(self.json_path),
            "srt_path": str(self.srt_path) if self.srt_path else None,
            "segments": [segment.to_dict() for segment in self.segments],
            "speaker_turns": [turn.to_dict() for turn in self.speaker_turns],
            "summary": self.summary.to_dict() if self.summary else None,
        }
