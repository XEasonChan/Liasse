from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = Path(os.environ.get("WHISPERQWEN_SETTINGS", str(ROOT / "outputs" / "settings.json")))


def default_settings() -> Dict[str, Any]:
    return {
        "outputDir": str((Path.home() / "Documents" / "WhisperQwen").resolve()),
        "fullyOffline": False,
        "defaultASRModel": "Qwen/Qwen3-ASR-0.6B",
        "defaultLanguage": "English",
        "defaultDiarize": True,
        "defaultNumSpeakers": 2,
        "defaultSummarize": False,
        "defaultSummaryModel": "qwen3:4b",
    }


def load_settings() -> Dict[str, Any]:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            return {**default_settings(), **data}
        except (json.JSONDecodeError, OSError):
            pass
    return default_settings()


def save_settings(settings: Dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    fully_offline = bool(settings.get("fullyOffline"))
    if fully_offline:
        os.environ["WHISPERQWEN_FULLY_OFFLINE"] = "1"
    else:
        os.environ.pop("WHISPERQWEN_FULLY_OFFLINE", None)
