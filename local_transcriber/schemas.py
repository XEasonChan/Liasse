from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


SpeakerMode = Literal["fast", "llm", "pyannote"]


def normalize_speaker_mode(config: Optional[Dict[str, Any]]) -> str:
    raw = dict(config or {})
    explicit = raw.get("speakerMode")
    if explicit in {"fast", "llm", "pyannote"}:
        return str(explicit)
    if "diarize" in raw:
        return "pyannote" if bool(raw.get("diarize")) else "fast"
    return "llm"


def normalize_task_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return TaskConfig(**dict(config or {})).model_dump()


class TaskConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    asrModel: Literal["Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-1.7B"] = "Qwen/Qwen3-ASR-0.6B"
    language: Literal["Chinese", "English", "Cantonese", "auto"] = "Chinese"
    speakerMode: SpeakerMode = "llm"
    diarize: bool = False
    numSpeakers: Optional[int] = 2
    autoSegment: bool = True
    summarize: bool = False
    enableChat: bool = True
    summaryModel: str = "qwen3:4b"
    userPref: Literal["auto", "quality", "speed"] = "auto"

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_diarize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        if migrated.get("speakerMode") not in {"fast", "llm", "pyannote"}:
            if "diarize" in migrated:
                migrated["speakerMode"] = "pyannote" if bool(migrated.get("diarize")) else "fast"
            else:
                migrated["speakerMode"] = "llm"
        return migrated

    @model_validator(mode="after")
    def _sync_legacy_diarize(self) -> "TaskConfig":
        self.diarize = self.speakerMode == "pyannote"
        if self.numSpeakers is not None:
            self.numSpeakers = max(1, min(5, int(self.numSpeakers)))
        return self


class SpeakerEditRequest(BaseModel):
    speakerId: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1, max_length=64)


class SegmentEditRequest(BaseModel):
    segmentId: str = Field(..., min_length=1)
    text: str = Field(...)


class DeleteResponse(BaseModel):
    ok: bool
    deletedOutputs: bool


__all__ = [
    "SpeakerMode",
    "normalize_speaker_mode",
    "normalize_task_config",
    "TaskConfig",
    "SpeakerEditRequest",
    "SegmentEditRequest",
    "DeleteResponse",
]
