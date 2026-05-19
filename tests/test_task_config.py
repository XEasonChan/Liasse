from local_transcriber.settings_store import normalize_settings
from local_transcriber.task_runner import _resolve_speaker_execution
from local_transcriber.schemas import TaskConfig, normalize_task_config


def test_task_config_defaults_to_llm_mode():
    cfg = TaskConfig()

    assert cfg.speakerMode == "llm"
    assert cfg.diarize is False


def test_task_config_migrates_legacy_diarize_true_to_pyannote():
    cfg = TaskConfig(diarize=True, asrModel="Qwen/Qwen3-ASR-0.6B")

    assert cfg.speakerMode == "pyannote"
    assert cfg.diarize is True


def test_task_config_migrates_legacy_diarize_false_to_fast():
    cfg = TaskConfig(diarize=False)

    assert cfg.speakerMode == "fast"
    assert cfg.diarize is False


def test_task_config_prefers_explicit_speaker_mode():
    cfg = TaskConfig(speakerMode="llm", diarize=True)

    assert cfg.speakerMode == "llm"
    assert cfg.diarize is False


def test_normalize_task_config_keeps_compat_diarize_field():
    cfg = normalize_task_config({"speakerMode": "pyannote", "numSpeakers": 9})

    assert cfg["speakerMode"] == "pyannote"
    assert cfg["diarize"] is True
    assert cfg["numSpeakers"] == 5


def test_settings_migrates_old_default_diarize_true_to_llm():
    settings = normalize_settings({"defaultDiarize": True})

    assert settings["defaultSpeakerMode"] == "llm"
    assert settings["defaultDiarize"] is False


def test_settings_migrates_old_default_diarize_false_to_fast():
    settings = normalize_settings({"defaultDiarize": False})

    assert settings["defaultSpeakerMode"] == "fast"
    assert settings["defaultDiarize"] is False


def test_runner_speaker_execution_only_pyannote_runs_diarization():
    llm_cfg, llm_mode, llm_pyannote, llm_label = _resolve_speaker_execution(
        {"speakerMode": "llm"}
    )
    py_cfg, py_mode, py_pyannote, py_label = _resolve_speaker_execution(
        {"speakerMode": "pyannote"}
    )
    fast_cfg, fast_mode, fast_pyannote, fast_label = _resolve_speaker_execution(
        {"speakerMode": "fast"}
    )

    assert llm_cfg["diarize"] is False
    assert (llm_mode, llm_pyannote, llm_label) == ("llm", False, True)
    assert py_cfg["diarize"] is True
    assert (py_mode, py_pyannote, py_label) == ("pyannote", True, False)
    assert fast_cfg["diarize"] is False
    assert (fast_mode, fast_pyannote, fast_label) == ("fast", False, False)


def test_runner_forces_fast_when_auto_segment_disabled():
    cfg, mode, pyannote, label = _resolve_speaker_execution(
        {"speakerMode": "pyannote", "autoSegment": False}
    )

    assert cfg["speakerMode"] == "pyannote"
    assert (mode, pyannote, label) == ("fast", False, False)
