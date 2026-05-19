from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .models import SpeakerTurn, TranscriptSegment


class DiarizationError(RuntimeError):
    pass


class PyannoteDiarizer:
    def __init__(self, model_name_or_path: str, hf_token: Optional[str] = None) -> None:
        self.model_name_or_path = model_name_or_path
        self.hf_token = hf_token or None

    def diarize(self, audio_path: Path) -> List[SpeakerTurn]:
        try:
            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise DiarizationError(
                "缺少 pyannote.audio。请安装 requirements-qwen.txt 或 requirements-whisper.txt。"
            ) from exc

        # pyannote.audio 4.x: Pipeline.from_pretrained 用 `token`，不再接受
        # `use_auth_token`（3.x 旧名）。为兼容两个版本，先试新 API。
        kwargs: dict = {}
        if self.hf_token:
            kwargs["token"] = self.hf_token
        try:
            pipeline = Pipeline.from_pretrained(self.model_name_or_path, **kwargs)
        except TypeError:
            # 落回 3.x API
            kwargs = {}
            if self.hf_token:
                kwargs["use_auth_token"] = self.hf_token
            pipeline = Pipeline.from_pretrained(self.model_name_or_path, **kwargs)

        # Apple Silicon: 把 pipeline 切到 Metal/MPS，3-5x 加速。
        # 失败静默落回 CPU。
        try:
            import os as _os
            import torch as _torch

            if (
                hasattr(_torch.backends, "mps")
                and _torch.backends.mps.is_available()
            ):
                _os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
                pipeline.to(_torch.device("mps"))
        except Exception:
            pass

        diarization = pipeline(str(audio_path))

        # pyannote.audio 4.x: pipeline() 返回 DiarizeOutput（含
        # speaker_diarization: Annotation），不再直接是 Annotation。
        # 3.x: 直接返回 Annotation，自带 itertracks。
        annotation = getattr(diarization, "speaker_diarization", diarization)

        turns: List[SpeakerTurn] = []
        for turn, _track, speaker in annotation.itertracks(yield_label=True):
            turns.append(
                SpeakerTurn(
                    start=float(turn.start),
                    end=float(turn.end),
                    speaker=str(speaker),
                )
            )
        return turns


def speaker_turns_from_segments(segments: List[TranscriptSegment]) -> List[SpeakerTurn]:
    turns: List[SpeakerTurn] = []
    for segment in segments:
        if segment.start is None or segment.end is None:
            continue
        turns.append(
            SpeakerTurn(
                start=segment.start,
                end=segment.end,
                speaker=segment.speaker,
            )
        )
    return turns
