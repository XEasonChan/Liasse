# Liasse Agent Guide

This file is the public onboarding contract for AI coding agents working from a fresh clone of this repository.

## Product Context

Liasse is a local-first desktop app for interview and case-file transcription. It targets researchers, IRB/DPO teams, litigators, paralegals, oral historians, and field researchers who cannot upload sensitive recordings to cloud transcription services.

Naming:

- Product name: `Liasse`
- Python package: `liasse/`
- Public repository: `XEasonChan/Liasse`

Core stack:

- Desktop shell: `pywebview`
- Backend: FastAPI + Uvicorn
- Frontend: Vue 3 from CDN, no npm build step
- Task storage: SQLite + SQLAlchemy
- ASR: `Qwen/Qwen3-ASR-0.6B` by default through `mlx-qwen3-asr`
- Speaker labeling: lightweight LLM text labeling by default, optional pyannote 4.x diarization
- Summary and Q&A: local Ollama models, usually `qwen3:4b` or `qwen3:8b`

## First Read

Before changing code, read:

1. `ARCHITECTURE.md` for the current module map and data flow.
2. `README.md` for user-facing install and product expectations.
3. The relevant tests under `tests/` before touching a module.

Do not start by sweeping the whole repo. `ARCHITECTURE.md` is the intended entry point.

## Install Rules

Use Python 3.12 only. On Apple Silicon Homebrew installs, prefer:

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12
```

Never create a dot-prefixed virtualenv such as `.venv/` or `.venv-mlx/`. In iCloud-backed folders, hidden dot directories can break `.pth` handling in newer Python versions. Always use:

```bash
venv/
```

Bootstrap from a fresh clone:

```bash
brew install python@3.12 ffmpeg ollama
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv venv
venv/bin/python -m pip install -U pip setuptools wheel
venv/bin/python -m pip install -r requirements-bootstrap.txt
venv/bin/python -m pip install -r requirements-mlx.txt
venv/bin/python scripts/check_runtime.py
```

If the user prefers the bundled launcher script, use:

```bash
./Setup\ MLX\ Test\ Env.command
./Check\ Runtime.command
```

Paths may contain spaces. Always quote paths in shell commands.

## Model Download Policy

Do not download large models, write `.env`, or start long-running services without asking the user first.

Default install set:

| Purpose | Model | Approx size | Notes |
| --- | --- | ---: | --- |
| ASR | `Qwen/Qwen3-ASR-0.6B` | 1.2 GB | Default transcription model |
| Timestamp alignment | `Qwen/Qwen3-ForcedAligner-0.6B` | 1.3 GB | Needed by long-audio alignment/chunking features |
| Summary / Q&A | `qwen3:4b` | 2.5 GB | Best default for 8 GB and 16 GB Macs |

Optional install set:

| Purpose | Model | Approx size | Notes |
| --- | --- | ---: | --- |
| Higher-quality ASR | `Qwen/Qwen3-ASR-1.7B` | 3.4 GB | Slower, better quality |
| Speaker diarization | `pyannote/speaker-diarization-community-1` | 600 MB | Requires Hugging Face token and license acceptance |
| Higher-quality summary / Q&A | `qwen3:8b` | 5.2 GB | Prefer on 16 GB+ machines |

Hugging Face token rules:

- `.env` is gitignored and may contain `HF_TOKEN` and `PYANNOTE_AUTH_TOKEN`.
- Never print, commit, or overwrite the user's token.
- If pyannote is requested, ask the user to confirm they have accepted the model license on Hugging Face.

Ollama rules:

- Check Ollama with `curl -s http://127.0.0.1:11434/api/tags`.
- Do not silently start `ollama serve` or `brew services start ollama`.
- Ask first, then either tell the user the command or run it with their explicit approval.

## Runtime Commands

Run the desktop app:

```bash
./Start\ Liasse.command
```

or, after the venv is ready:

```bash
venv/bin/python launch_app.py
```

Run unit tests:

```bash
venv/bin/python -m pytest tests/
```

Run a short local audio check only if the user has local test audio available:

```bash
venv/bin/python scripts/run_test_audio.py --seconds 60 --diarize --num-speakers 2
```

Do not run full-length sample transcription during normal development. It can take several hours.

## Privacy Invariants

- Liasse must not call cloud transcription or cloud LLM APIs.
- First-time dependency and model downloads are allowed only as explicit install steps.
- After models are local, the app should be able to run offline.
- Do not add telemetry, update checks, license checks, remote logging, or analytics.
- User audio, transcripts, summaries, and chat context must stay local.

## Code Style

- Python: 3.12, type hints, dataclasses where appropriate, `pathlib.Path` for paths.
- JavaScript: ES2022+, Vue 3 CDN style, no build step unless the user explicitly asks for a larger frontend migration.
- UI copy is primarily Chinese, with existing English and Spanish locale files kept in sync for user-visible strings.
- Keep comments sparse and useful.
- Prefer the repository's existing patterns over new abstractions.

## Change Discipline

- Do not revert unrelated user changes in a dirty worktree.
- Keep edits scoped to the user's request.
- Add or update focused tests when behavior changes.
- Run the smallest useful verification command before handing work back.
- If a task touches the transcription pipeline, check the relevant tests first and avoid full audio runs unless explicitly requested.
