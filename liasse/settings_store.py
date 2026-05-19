from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = Path(
    os.environ.get("LIASSE_SETTINGS")
    or os.environ.get("WHISPERQWEN_SETTINGS")  # legacy
    or str(ROOT / "outputs" / "settings.json")
)


def _default_output_dir() -> str:
    """Prefer ~/Documents/Liasse; fall back to legacy ~/Documents/WhisperQwen if it
    exists and the new path does not (preserves users' historical output)."""
    new_path = Path.home() / "Documents" / "Liasse"
    legacy = Path.home() / "Documents" / "WhisperQwen"
    if not new_path.exists() and legacy.exists() and any(legacy.iterdir()):
        return str(legacy.resolve())
    return str(new_path.resolve())


def default_settings() -> Dict[str, Any]:
    return {
        "outputDir": _default_output_dir(),
        "fullyOffline": False,
        "defaultASRModel": "Qwen/Qwen3-ASR-0.6B",
        "defaultLanguage": "English",
        "defaultSpeakerMode": "llm",
        "defaultDiarize": False,
        "defaultNumSpeakers": 2,
        "defaultSummarize": False,
        "defaultSummaryModel": "qwen3:4b",
    }


def normalize_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    defaults = default_settings()
    data = dict(settings or {})
    merged = {**defaults, **data}
    mode = data.get("defaultSpeakerMode")
    if mode not in {"fast", "llm", "pyannote"}:
        if "defaultDiarize" in data:
            mode = "llm" if bool(data.get("defaultDiarize")) else "fast"
        else:
            mode = defaults["defaultSpeakerMode"]
    merged["defaultSpeakerMode"] = mode
    merged["defaultDiarize"] = mode == "pyannote"
    return merged


def load_settings() -> Dict[str, Any]:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return normalize_settings(data)
        except (json.JSONDecodeError, OSError):
            pass
    return normalize_settings({})


def save_settings(settings: Dict[str, Any]) -> None:
    settings = normalize_settings(settings)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    fully_offline = bool(settings.get("fullyOffline"))
    if fully_offline:
        os.environ["WHISPERQWEN_FULLY_OFFLINE"] = "1"
    else:
        os.environ.pop("WHISPERQWEN_FULLY_OFFLINE", None)
