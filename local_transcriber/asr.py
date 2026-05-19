from __future__ import annotations

import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

from .models import TranscriptSegment

_CJK_SPACING_RE = re.compile(r"([一-鿿　-〿＀-￯])\s+(?=[一-鿿　-〿＀-￯])")
ProgressCallback = Callable[[dict[str, Any]], None]


def _clean_cjk_spacing(text: str) -> str:
    cleaned = _CJK_SPACING_RE.sub(r"\1", text)
    cleaned = _CJK_SPACING_RE.sub(r"\1", cleaned)
    return cleaned.strip()


class ASRError(RuntimeError):
    pass


class BaseASRBackend:
    name = "base"

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str],
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[TranscriptSegment]:
        raise NotImplementedError


class DemoASRBackend(BaseASRBackend):
    name = "demo"

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str],
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[TranscriptSegment]:
        return [
            TranscriptSegment(
                start=0.0,
                end=7.5,
                speaker="SPEAKER_00",
                text="欢迎参加这次访谈。我们先从你的研究背景开始聊起。",
                source=self.name,
            ),
            TranscriptSegment(
                start=7.8,
                end=19.2,
                speaker="SPEAKER_01",
                text="我的项目主要关注生成式人工智能进入课堂之后，学生如何重新理解写作和原创性。",
                source=self.name,
            ),
            TranscriptSegment(
                start=20.0,
                end=31.0,
                speaker="SPEAKER_00",
                text="你刚才提到原创性，这一点在伦理审查里也很关键。能不能举一个具体例子？",
                source=self.name,
            ),
        ]


class WhisperASRBackend(BaseASRBackend):
    name = "faster-whisper"

    def __init__(self, model_name: str = "large-v3") -> None:
        self.model_name = model_name

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str],
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[TranscriptSegment]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ASRError(
                "缺少 faster-whisper。请先安装 requirements-whisper.txt，或切换到 Qwen3-ASR 后端。"
            ) from exc

        device, compute_type = self._pick_device()
        model = WhisperModel(self.model_name, device=device, compute_type=compute_type)
        whisper_language = _language_for_whisper(language)
        segments, _info = model.transcribe(
            str(audio_path),
            language=whisper_language,
            vad_filter=True,
            beam_size=5,
        )
        return [
            TranscriptSegment(
                start=float(item.start),
                end=float(item.end),
                text=item.text.strip(),
                confidence=getattr(item, "avg_logprob", None),
                source=self.name,
            )
            for item in segments
            if item.text and item.text.strip()
        ]

    def _pick_device(self) -> tuple[str, str]:
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda", "float16"
            if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                return "auto", "int8"
        except Exception:
            pass
        return "cpu", "int8"


class MLXQwenASRBackend(BaseASRBackend):
    name = "mlx-qwen3-asr"

    def __init__(
        self,
        model_name_or_path: str = "Qwen/Qwen3-ASR-0.6B",
        return_timestamps: bool = True,
        diarize: bool = False,
        pyannote_model: Optional[str] = None,
        hf_token: Optional[str] = None,
        num_speakers: Optional[int] = None,
    ) -> None:
        self.model_name_or_path = model_name_or_path
        self.return_timestamps = return_timestamps
        self.diarize = diarize
        self.pyannote_model = pyannote_model
        self.hf_token = hf_token
        self.num_speakers = num_speakers

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str],
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[TranscriptSegment]:
        _add_vendored_mlx_qwen_to_path()
        try:
            from mlx_qwen3_asr import transcribe
        except ImportError as exc:
            raise ASRError(
                "缺少 mlx-qwen3-asr/MLX。请使用 Python 3.10+，并安装 requirements-mlx.txt。"
            ) from exc

        if self.pyannote_model:
            os.environ["PYANNOTE_MODEL_ID"] = self.pyannote_model
        if self.hf_token:
            os.environ["PYANNOTE_AUTH_TOKEN"] = self.hf_token

        transcribe_kwargs: dict[str, Any] = dict(
            model=self.model_name_or_path,
            language=_language_for_qwen(language),
            return_timestamps=self.return_timestamps or self.diarize,
            diarize=self.diarize,
            return_chunks=True,
            verbose=False,
        )
        if self.diarize and self.num_speakers:
            transcribe_kwargs["diarization_num_speakers"] = self.num_speakers
        if on_progress is not None:
            transcribe_kwargs["on_progress"] = on_progress

        result = transcribe(str(audio_path), **transcribe_kwargs)

        speaker_segments = getattr(result, "speaker_segments", None) or []
        if speaker_segments:
            return [
                TranscriptSegment(
                    start=_optional_float(item.get("start")),
                    end=_optional_float(item.get("end")),
                    speaker=str(item.get("speaker") or "SPEAKER_00"),
                    text=_clean_cjk_spacing(str(item.get("text") or "")),
                    source=self.name,
                )
                for item in speaker_segments
                if str(item.get("text") or "").strip()
            ]

        timestamp_segments = getattr(result, "segments", None) or []
        if timestamp_segments:
            marks = [
                {"text": item.get("text"), "start": item.get("start"), "end": item.get("end")}
                for item in timestamp_segments
            ]
            return _segments_from_time_marks(marks, source=self.name)

        chunk_segments = getattr(result, "chunks", None) or []
        if chunk_segments:
            return [
                TranscriptSegment(
                    start=_optional_float(item.get("start")),
                    end=_optional_float(item.get("end")),
                    text=str(item.get("text") or "").strip(),
                    source=self.name,
                )
                for item in chunk_segments
                if str(item.get("text") or "").strip()
            ]

        text = str(getattr(result, "text", "") or "").strip()
        if not text:
            return []
        return [TranscriptSegment(start=None, end=None, text=text, source=self.name)]


class QwenASRBackend(BaseASRBackend):
    name = "qwen3-asr"

    def __init__(
        self,
        model_name_or_path: str = "Qwen/Qwen3-ASR-1.7B",
        forced_aligner: Optional[str] = "Qwen/Qwen3-ForcedAligner-0.6B",
        return_timestamps: bool = True,
    ) -> None:
        self.model_name_or_path = model_name_or_path
        self.forced_aligner = forced_aligner
        self.return_timestamps = return_timestamps

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str],
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[TranscriptSegment]:
        try:
            import torch
            from qwen_asr import Qwen3ASRModel
        except ImportError as exc:
            raise ASRError(
                "缺少 qwen-asr。请在 Python 3.12 环境中安装 requirements-qwen.txt。"
            ) from exc

        dtype, device_map = self._pick_torch_runtime(torch)
        kwargs: dict[str, Any] = {
            "dtype": dtype,
            "device_map": device_map,
            "max_inference_batch_size": int(os.getenv("LOCAL_ASR_BATCH_SIZE", "4")),
            "max_new_tokens": int(os.getenv("LOCAL_ASR_MAX_NEW_TOKENS", "4096")),
        }
        if self.return_timestamps and self.forced_aligner:
            kwargs["forced_aligner"] = self.forced_aligner
            kwargs["forced_aligner_kwargs"] = {
                "dtype": dtype,
                "device_map": device_map,
            }

        model = Qwen3ASRModel.from_pretrained(self.model_name_or_path, **kwargs)
        qwen_language = _language_for_qwen(language)
        results = model.transcribe(
            audio=str(audio_path),
            language=qwen_language,
            return_time_stamps=self.return_timestamps,
        )
        result = results[0] if isinstance(results, Sequence) else results
        marks = _coerce_time_marks(getattr(result, "time_stamps", None))
        if marks:
            return _segments_from_time_marks(marks, source=self.name)

        text = getattr(result, "text", "") or str(result)
        text = text.strip()
        if not text:
            return []
        return [TranscriptSegment(start=None, end=None, text=text, source=self.name)]

    def _pick_torch_runtime(self, torch: Any) -> tuple[Any, str]:
        dtype_name = os.getenv("LOCAL_ASR_DTYPE")
        device_map = os.getenv("LOCAL_ASR_DEVICE_MAP")
        if dtype_name:
            dtype = getattr(torch, dtype_name)
        elif torch.cuda.is_available():
            dtype = torch.bfloat16
        else:
            dtype = torch.float32

        if device_map:
            device = device_map
        elif torch.cuda.is_available():
            device = "cuda:0"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        return dtype, device


def create_asr_backend(
    backend: str,
    qwen_model: str,
    qwen_aligner: str,
    qwen_return_timestamps: bool,
    whisper_model: str,
    diarization_enabled: bool = False,
    pyannote_model: Optional[str] = None,
    hf_token: Optional[str] = None,
    num_speakers: Optional[int] = None,
) -> BaseASRBackend:
    normalized = backend.lower().strip()
    if normalized in {"demo", "演示"}:
        return DemoASRBackend()
    if normalized in {"mlx", "mlx-qwen", "mlx-qwen3-asr"}:
        return MLXQwenASRBackend(
            qwen_model,
            qwen_return_timestamps,
            diarize=diarization_enabled,
            pyannote_model=pyannote_model,
            hf_token=hf_token,
            num_speakers=num_speakers,
        )
    if normalized in {"whisper", "faster-whisper", "faster_whisper"}:
        return WhisperASRBackend(whisper_model)
    if normalized in {"qwen", "qwen3-asr", "qwen_asr"}:
        return QwenASRBackend(qwen_model, qwen_aligner, qwen_return_timestamps)
    raise ASRError(f"未知转录后端：{backend}")


def _add_vendored_mlx_qwen_to_path() -> None:
    vendor_root = Path(__file__).resolve().parent.parent / "vendor" / "mlx-qwen3-asr"
    if vendor_root.exists():
        vendor_text = str(vendor_root)
        if vendor_text not in sys.path:
            sys.path.insert(0, vendor_text)


def _language_for_whisper(language: Optional[str]) -> Optional[str]:
    if not language or language.lower() == "auto":
        return None
    mapping = {
        "Chinese": "zh",
        "中文": "zh",
        "English": "en",
        "英语": "en",
        "Cantonese": "yue",
        "粤语": "yue",
    }
    return mapping.get(language, language)


def _language_for_qwen(language: Optional[str]) -> Optional[str]:
    if not language or language.lower() == "auto":
        return None
    mapping = {
        "zh": "Chinese",
        "中文": "Chinese",
        "cn": "Chinese",
        "en": "English",
        "英语": "English",
        "yue": "Cantonese",
        "粤语": "Cantonese",
    }
    return mapping.get(language, language)


def _coerce_time_marks(raw_marks: Any) -> List[dict[str, Any]]:
    if not raw_marks:
        return []
    marks: List[dict[str, Any]] = []
    for raw in raw_marks:
        text = _read_attr(raw, "text", 0)
        start = _read_attr(raw, "start_time", 1)
        end = _read_attr(raw, "end_time", 2)
        if start is None:
            start = _read_attr(raw, "start", 1)
        if end is None:
            end = _read_attr(raw, "end", 2)
        if text is None or start is None or end is None:
            continue
        marks.append({"text": str(text), "start": float(start), "end": float(end)})
    return marks


def _read_attr(raw: Any, key: str, tuple_index: int) -> Any:
    if isinstance(raw, dict):
        return raw.get(key)
    if isinstance(raw, (list, tuple)) and len(raw) > tuple_index:
        return raw[tuple_index]
    return getattr(raw, key, None)


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _segments_from_time_marks(
    marks: Iterable[dict[str, Any]],
    source: str,
    max_gap: float = 1.2,
    soft_chars: int = 80,
    hard_chars: int = 180,
) -> List[TranscriptSegment]:
    output: List[TranscriptSegment] = []
    buffer: List[str] = []
    start: Optional[float] = None
    end: Optional[float] = None

    for mark in marks:
        text = str(mark["text"]).strip()
        if not text:
            continue
        mark_start = float(mark["start"])
        mark_end = float(mark["end"])
        gap = None if end is None else mark_start - end
        buffered_text = "".join(buffer)
        should_flush = (
            bool(buffer)
            and (
                (gap is not None and gap > max_gap)
                or len(buffered_text) >= hard_chars
                or (len(buffered_text) >= soft_chars and _ends_sentence(buffered_text))
            )
        )
        if should_flush:
            output.append(
                TranscriptSegment(start=start, end=end, text=_join_qwen_tokens(buffer), source=source)
            )
            buffer = []
            start = None

        if start is None:
            start = mark_start
        end = mark_end
        buffer.append(text)

    if buffer:
        output.append(
            TranscriptSegment(start=start, end=end, text=_join_qwen_tokens(buffer), source=source)
        )
    return output


def _ends_sentence(text: str) -> bool:
    return text.endswith(("。", "！", "？", ".", "!", "?"))


def _join_qwen_tokens(tokens: List[str]) -> str:
    text = "".join(tokens)
    text = text.replace(" ,", ",").replace(" .", ".").replace(" ?", "?").replace(" !", "!")
    return text.strip()
