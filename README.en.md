<p align="right">
  <a href="README.md">中文</a> · <strong>English</strong>
</p>

<p align="center">
  <img src="docs/assets/liasse-hero.png" alt="Liasse — private local transcription for interviews and case files" width="100%">
</p>

<h1 align="center"><em>Liasse</em></h1>

<p align="center">
  <em>Private local transcription for interviews and case files.</em>
</p>

<p align="center">
  <a href="#use-cases">Use cases</a> · <a href="#how-it-works">How it works</a> · <a href="#quickstart">Quickstart</a> · <a href="#agent-starter">AI Agent Starter</a> · <a href="#privacy">Privacy</a>
</p>

---

> **Liasse** (French: *a bound bundle of documents tied with a ribbon*) turns interview recordings into citable, archivable transcripts that never leave your machine.
>
> It is not for developers. It is for researchers, lawyers, compliance officers, oral historians, and field workers — anyone whose recordings cannot be uploaded.

Liasse is not another "AI recorder." Its shape is borrowed from the bundle of interview materials on a researcher's desk: the originals stay with you; the tool only helps you keep them tidy. Audio, transcripts, summaries, Q&A context — from the moment models are downloaded to the moment you export a PDF — never leave this machine.

It runs **fully locally on Apple Silicon Mac**. An ordinary **8 GB MacBook Air is enough** (slower, but it works); 16 GB is the daily driver; 24 GB+ lets you use the 1.7 B ASR and the 8 B summarizer. With **fully-offline mode** on, no network calls happen at all after the first model download.

> Status: alpha · backend pipeline working, desktop UI usable.

<a id="use-cases"></a>

## Use Cases

Liasse's shape and name came from a 2026-05 multi-persona brand sandbox — six target users gave structured feedback in the same product environment. The six use cases below are the patterns that emerged.

<table>
<tr>
<td width="50%" valign="top">
<a href="docs/assets/use-case-1-academic.png"><img src="docs/assets/use-case-1-academic.png" alt="Sensitive Interviews"></a>

**Sensitive Interviews**

GDPR-clean, IRB-bound, never uploaded. Can be written directly into the Data Management Plan.

<sub>For academic researchers — Available now</sub>

</td>
<td width="50%" valign="top">
<a href="docs/assets/use-case-2-compliance.png"><img src="docs/assets/use-case-2-compliance.png" alt="Compliance &amp; Audit"></a>

**Compliance &amp; Audit**

DMP-ready · audit-friendly · no cloud anywhere. Export an audit bundle with retention, processors, and full local log.

<sub>For DPO &amp; IRB officers — Available now</sub>

</td>
</tr>
<tr>
<td width="50%" valign="top">
<a href="docs/assets/use-case-3-litigation.png"><img src="docs/assets/use-case-3-litigation.png" alt="Deposition Prep"></a>

**Deposition Prep**

Privileged · confidential · on your machine. Transcripts citable in court filings without entering any vendor log.

<sub>For litigators — Available now</sub>

</td>
<td width="50%" valign="top">
<a href="docs/assets/use-case-4-paralegal.png"><img src="docs/assets/use-case-4-paralegal.png" alt="Case Management at Scale"></a>

**Case Management at Scale**

Hundreds of hours, batched and bound. Queue by matter number, export Markdown / SRT / JSON, all local.

<sub>For paralegals &amp; legal ops — Available now</sub>

</td>
</tr>
<tr>
<td width="50%" valign="top">
<a href="docs/assets/use-case-5-oralhistory.png"><img src="docs/assets/use-case-5-oralhistory.png" alt="Oral History"></a>

**Oral History**

Voices preserved · pages bound. Long-form, speaker-labeled, citable for a monograph's methodology chapter.

<sub>For oral historians — Available now</sub>

</td>
<td width="50%" valign="top">
<a href="docs/assets/use-case-6-field.png" alt="Field Research, Bilingual"><img src="docs/assets/use-case-6-field.png"></a>

**Field Research, Bilingual**

Bilingüe · both private. EN / ES / ZH transcription kept locally — works offline in the field.

<sub>For field researchers — Available now</sub>

</td>
</tr>
</table>

> These are not hypothetical scenarios — each maps to a specific persona (EU social-science PI, university DPO / IRB, US litigation partner, paralegal, oral historian, Spanish / LATAM project lead). Each gave Liasse its top score in the original sandbox.

## This is not "a developer tool"

Liasse is **a tasteful local-LLM product** designed so anyone can install, use, and trust it. But it is not a black box either:

- **Default-just-works** — Double-click `Start Liasse.command`, finish the setup, transcribe. No Python, no ML knowledge required.
- **Readable and modifiable** — The whole product is Python + Vue 3 from CDN. No webpack, no npm build, no React framework. Anyone with a little code experience, plus an AI agent (Codex / Claude Code / Cursor), can reshape the UI, copy, or model choices in under an hour.
- **Zero cloud dependence** — Once models are local, the app never goes online. A "fully offline" toggle in settings forces `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.

<a id="agent-starter"></a>

## AI Agent Starter

Liasse stays small, readable, and build-step-free on purpose. You can give this repository link to Claude Code, Codex CLI, or Cursor and ask it to check the machine, confirm downloads, and launch the app step by step.

Clone first:

```bash
git clone https://github.com/XEasonChan/Liasse.git
cd Liasse
```

Then paste this to your agent:

```text
Please help me install and launch Liasse on this Mac.

Read AGENTS.md and ARCHITECTURE.md before acting. The goal is local setup, not product changes.

Constraints:
- Use Python 3.12 only; the virtualenv must be named venv/, not .venv/.
- Quote shell paths because the directory may live in iCloud Drive.
- You may check Homebrew, Python, ffmpeg, Ollama, model cache, and disk space.
- Before installing system dependencies, tell me the exact brew command.
- Before downloading large models, stop and ask. By default, prepare only Qwen3-ASR-0.6B, Qwen3-ForcedAligner-0.6B, and qwen3:4b.
- Do not download Qwen3-ASR-1.7B, qwen3:8b, or pyannote unless I explicitly approve.
- Do not write, print, or overwrite .env for me. If pyannote is needed, remind me to provide HF_TOKEN and accept the Hugging Face model license first.
- Do not silently start a long-running Ollama daemon; ask whether I prefer ollama serve or brew services start ollama.

After setup, run the health check and tell me how to open the desktop app.
```

Default local models:

| Purpose | Default model | Size |
| --- | --- | ---: |
| Transcription | `Qwen/Qwen3-ASR-0.6B` | about 1.2 GB |
| Timestamp alignment | `Qwen/Qwen3-ForcedAligner-0.6B` | about 1.3 GB |
| Summary / Q&A | `qwen3:4b` through Ollama | about 2.5 GB |

Optional models: `Qwen/Qwen3-ASR-1.7B` is about 3.4 GB, `qwen3:8b` is about 5.2 GB, and `pyannote/speaker-diarization-community-1` is about 600 MB and requires a Hugging Face token plus license acceptance.

<a id="privacy"></a>

## Privacy Model

Liasse's privacy boundary is "your machine":

- Audio is never uploaded to a cloud transcription API.
- Transcripts, summaries, digests, and Q&A history stay in local `outputs/` and SQLite.
- The only network call is the first model download. After that, toggle "Fully offline" — done.
- No telemetry, no update checks, no third-party reporting.
- Inference runs on local Apple Silicon GPU (MLX / Metal).
- Crash logs go only to `~/Library/Logs/Liasse/` and are not sent anywhere.

<a id="how-it-works"></a>

## How it works

<p align="center">
  <img src="docs/assets/liasse-workflow.png" alt="Liasse local workflow: drop audio → ASR → speaker labeling → summary → export" width="100%">
</p>

Five steps, all on your machine:

1. **Drop audio** — `mp3 / wav / m4a / flac / aac / ogg / wma / mp4`
2. **Qwen3-ASR transcription** — 0.6 B default, 1.7 B for quality mode (Apple Silicon Metal GPU)
3. **Speaker labeling** — pyannote 4.x community-1, or the lighter LLM text-based labeler
4. **Summary &amp; Q&A** — Local Qwen3:4 b or 8 b via Ollama
5. **Export bundle** — Markdown / JSON / SRT; law-firm scenarios use the `@media print` PDF template

## What's already there

| Module | Current implementation |
| --- | --- |
| Desktop shell | pywebview + local FastAPI + Vue 3 (no npm build) |
| ASR | Qwen3-ASR-0.6 B default, Qwen3-ASR-1.7 B optional |
| Speaker labeling | pyannote 4.x `speaker-diarization-community-1` or LLM text labeler |
| Task system | SQLite persistence, serial queue, retry on failure |
| Multi-language UI | ZH · EN · ES |
| Summarization | Local Qwen3 via Ollama, Markdown output |
| Q&A / RAG | Digest + retrieval context |
| Export | Markdown / JSON / SRT, PDF via `@media print` template |
| Offline mode | "Fully offline" switch enforces local HF / Transformers cache |

## Hardware &amp; memory

| Tier | Notes |
| --- | --- |
| **Minimum** | Apple Silicon Mac, **8 GB unified memory** (common on MacBook Air). Transcription + 4 B summary / Q&A works; long interviews take noticeably longer. |
| **Daily driver** | **16 GB** (MacBook Air / Pro, entry-level iMac). Most of the development and testing happens at this tier. |
| **Comfortable** | 24 GB+. Run `qwen3:8b`, switch to the 1.7 B ASR for higher quality. |

No discrete GPU or workstation needed. **Not recommended**: Intel Mac, <8 GB RAM, or running Liasse while many browser tabs / VMs are open.

<a id="quickstart"></a>

## Quickstart

```bash
# 1. System dependencies
brew install python@3.12 ffmpeg ollama

# 2. Hugging Face token (first-time pyannote download)
echo "HF_TOKEN=hf_xxx" >> .env
echo "PYANNOTE_AUTH_TOKEN=hf_xxx" >> .env

# 3. Python environment
./Setup\ MLX\ Test\ Env.command

# 4. Local summary / Q&A model (8 GB machines: only 4 B needed)
ollama pull qwen3:4b
ollama pull qwen3:8b              # optional, 16 GB+

# 5. Run
ollama serve                       # separate terminal
./Start\ Liasse.command            # double-click launcher
```

`Start Liasse.command` only checks that Ollama is running; it will not start the daemon for you.

## Speed reference

Qwen3-ASR-0.6 B + diarization (about 0.6–0.7× realtime):

| Audio length | 16 GB | 8 GB |
| --- | --- | --- |
| 60 s | ~90 s | ~1.5–2.5 min |
| 5 min | ~7–8 min | ~10–15 min |
| 30 min | ~45 min | ~1–1.5 h |
| 3 h 50 min | ~5–6 h | overnight / split |

Long audio currently retries from the start. Chunked resume is on the roadmap.

## Project Structure

See [ARCHITECTURE.md](ARCHITECTURE.md); design system in [design.md](design.md).

## Roadmap

- Long-audio chunking + partial resume
- Local semantic retrieval by time range / speaker / topic
- macOS App Bundle / DMG / first-launch onboarding
- Dark mode (v0.3)
- PDF export templates (legal + academic presets)

## License

No open-source license selected yet. Please do not treat it as freely redistributable.

---

<p align="center">
  <sub><em>Liasse</em> · A research instrument that happens to be software.</sub>
</p>
