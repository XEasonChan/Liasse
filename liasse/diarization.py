from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from .models import SpeakerTurn, TranscriptSegment


class DiarizationError(RuntimeError):
    pass


def _to_wav_if_needed(audio_path: Path) -> tuple[Path, Optional[Path]]:
    """如果是 m4a / mp3 / 其他容器，转 16kHz mono wav 到 tmp 文件,
    返回 (wav_path, tmp_to_clean)。wav 输入直接返回 (path, None)。

    pyannote 4.x 在 m4a 上读容器声明长度,但解码后实际可能短几十毫秒,
    最后一个 10s chunk crop 时会 ValueError。强制走 wav 绕开。
    """
    suffix = audio_path.suffix.lower()
    if suffix == ".wav":
        return audio_path, None
    tmp = Path(tempfile.mkstemp(suffix=".wav", prefix="liasse-diar-")[1])
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(audio_path),
            "-ac", "1", "-ar", "16000",
            "-f", "wav", str(tmp),
        ],
        check=True,
    )
    return tmp, tmp


class PyannoteDiarizer:
    def __init__(
        self,
        model_name_or_path: str,
        hf_token: Optional[str] = None,
        num_speakers: Optional[int] = None,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> None:
        self.model_name_or_path = model_name_or_path
        self.hf_token = hf_token or None
        self.num_speakers = num_speakers
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers

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

        # pyannote 4.x 默认会自动估算 speaker count,在短(<10min)清晰对话上
        # 经常错估为 1。访谈场景固定 2 人,显式 hint 是关键准确率杠杆。
        diar_kwargs: dict = {}
        if self.num_speakers:
            diar_kwargs["num_speakers"] = int(self.num_speakers)
        else:
            if self.min_speakers:
                diar_kwargs["min_speakers"] = int(self.min_speakers)
            if self.max_speakers:
                diar_kwargs["max_speakers"] = int(self.max_speakers)
        # m4a 容器声明长度往往大于实际解码长度几十毫秒,pyannote 最后 10s chunk
        # 会 ValueError。先转 16k mono wav 再喂。
        wav_path, _tmp = _to_wav_if_needed(audio_path)
        try:
            try:
                diarization = pipeline(str(wav_path), **diar_kwargs)
            except TypeError:
                # 老 pyannote 不接受这些 kwarg,退回无 hint 模式
                diarization = pipeline(str(wav_path))
        finally:
            if _tmp is not None:
                try:
                    _tmp.unlink()
                except Exception:
                    pass

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
