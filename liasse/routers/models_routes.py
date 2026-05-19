"""模型清单 + 下载流 + Ollama 启动路由。

- GET  /api/models                       — 列出 ASR/aligner/diarization/LLM
                                          模型条目及 downloaded/required 状态
- POST /api/models/download              — 启动后台 HF snapshot_download 任务
- GET  /api/models/download/:job/stream  — SSE 流：bytes 进度 + 状态
- POST /api/models/download/:job/cancel  — 取消下载
- POST /api/ollama/start                 — 后台 fork `ollama serve`，最多 8s
                                          等端口起来

依赖：downloader 模块（job state）+ services.ollama_health。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import downloader as downloader_module
from ..services import check_ollama, check_ollama_model


router = APIRouter()

OUTPUTS_DIR = Path(os.environ.get("WHISPERQWEN_OUTPUTS_DIR", "outputs"))


class DownloadModelRequest(BaseModel):
    modelId: str


@router.get("/api/models")
def models() -> dict:
    from ..hf_paths import is_downloaded

    items = [
        {
            "id": "Qwen/Qwen3-ASR-0.6B",
            "kind": "asr",
            "downloaded": is_downloaded("Qwen/Qwen3-ASR-0.6B"),
            "label": "Qwen3-ASR 0.6B（默认转录）",
            "sizeBytes": 1_200_000_000,
            "required": True,
            "bundled": True,
            "downloadCommand": (
                "venv/bin/python -c \"from huggingface_hub import snapshot_download; "
                "snapshot_download('Qwen/Qwen3-ASR-0.6B')\""
            ),
            "downloadHint": "默认安装应已自带。如缺失，运行下面的命令重新下载。",
        },
        {
            "id": "Qwen/Qwen3-ForcedAligner-0.6B",
            "kind": "aligner",
            "downloaded": is_downloaded("Qwen/Qwen3-ForcedAligner-0.6B"),
            "label": "Qwen3 时间戳对齐器",
            "sizeBytes": 1_300_000_000,
            "required": False,
            "bundled": True,
            "downloadCommand": (
                "venv/bin/python -c \"from huggingface_hub import snapshot_download; "
                "snapshot_download('Qwen/Qwen3-ForcedAligner-0.6B')\""
            ),
            "downloadHint": "默认安装应已自带。如缺失，自动分段需要它，运行下面命令补回。",
        },
        {
            "id": "Qwen/Qwen3-ASR-1.7B",
            "kind": "asr",
            "downloaded": is_downloaded("Qwen/Qwen3-ASR-1.7B"),
            "label": "Qwen3-ASR 1.7B（高质量，可选）",
            "sizeBytes": 3_400_000_000,
            "required": False,
            "bundled": False,
            "downloadCommand": (
                "venv/bin/python -c \"from huggingface_hub import snapshot_download; "
                "snapshot_download('Qwen/Qwen3-ASR-1.7B')\""
            ),
            "downloadHint": "比 0.6B 慢约 50% 但识别质量更高。下载约 3.4 GB，需要 Hugging Face 账户。",
        },
        {
            "id": "pyannote/speaker-diarization-community-1",
            "kind": "diarization",
            "downloaded": is_downloaded("pyannote/speaker-diarization-community-1"),
            "label": "pyannote 发言人识别 4.x",
            "sizeBytes": 600_000_000,
            "required": False,
            "bundled": False,
            "downloadCommand": (
                "# 1. 在浏览器同意许可：https://huggingface.co/pyannote/speaker-diarization-community-1\n"
                "# 2. 在 .env 填入 HF_TOKEN=hf_xxx\n"
                "venv/bin/python -c \"from huggingface_hub import snapshot_download; import os; "
                "snapshot_download('pyannote/speaker-diarization-community-1', token=os.environ.get('HF_TOKEN'))\""
            ),
            "downloadHint": "「发言人识别」功能需要这个模型。约 600 MB。首次下载前需要在 Hugging Face 网页同意一次许可。",
        },
        {
            "id": "qwen3:4b",
            "kind": "llm",
            "downloaded": check_ollama_model("qwen3:4b"),
            "label": "Qwen3 4B（总结 / AI Chat）",
            "sizeBytes": 2_500_000_000,
            "required": False,
            "bundled": False,
            "downloadCommand": "ollama pull qwen3:4b",
            "downloadHint": "「生成总结」和「AI Chat」都用这个本地 LLM。约 2.5 GB。先确认 Ollama 已启动（brew install ollama && ollama serve）。",
        },
        {
            "id": "qwen3:8b",
            "kind": "llm",
            "downloaded": check_ollama_model("qwen3:8b"),
            "label": "Qwen3 8B（更高质量，可选）",
            "sizeBytes": 5_200_000_000,
            "required": False,
            "bundled": False,
            "downloadCommand": "ollama pull qwen3:8b",
            "downloadHint": "比 4B 更慢但回答更细致。下载约 5.2 GB，运行时 6 GB+ 内存。",
        },
    ]
    return {"models": items}


@router.post("/api/models/download")
def start_model_download(payload: DownloadModelRequest) -> dict:
    try:
        job = downloader_module.start_download(payload.modelId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "jobId": job.job_id,
        "modelId": job.model_id,
        "kind": job.kind,
        "status": job.status,
    }


@router.get("/api/models/download/{job_id}/stream")
def stream_download(job_id: str):
    job = downloader_module.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="下载任务不存在")

    def event_stream():
        yield (
            f"event: snapshot\ndata: "
            f"{json.dumps({'progress': job.progress, 'bytesDone': job.bytes_done, 'bytesTotal': job.bytes_total, 'status': job.status}, ensure_ascii=False)}\n\n"
        )
        while True:
            try:
                msg = job.events.get(timeout=30.0)
            except Exception:
                if job.status in {"done", "failed"}:
                    break
                yield "event: ping\ndata: {}\n\n"
                continue
            evt = msg.pop("event")
            if evt == "__close__":
                break
            yield f"event: {evt}\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/api/models/download/{job_id}/cancel")
def cancel_download(job_id: str) -> dict:
    ok = downloader_module.cancel_job(job_id)
    return {"ok": ok}


@router.post("/api/ollama/start")
def start_ollama() -> dict:
    if check_ollama():
        return {"started": True, "alreadyRunning": True, "message": "Ollama 已在运行"}

    if not shutil.which("ollama"):
        raise HTTPException(
            status_code=400,
            detail="找不到 ollama 二进制（请先 brew install ollama）",
        )

    log_path = OUTPUTS_DIR / "ollama.log"
    env = {**os.environ, "OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0"}
    try:
        with open(log_path, "ab") as log_f:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"启动失败：{exc}")

    deadline = time.time() + 8.0
    while time.time() < deadline:
        if check_ollama():
            return {
                "started": True,
                "alreadyRunning": False,
                "message": "Ollama 已启动",
                "logPath": str(log_path),
            }
        time.sleep(0.3)
    raise HTTPException(status_code=504, detail="Ollama 启动超时（8 秒）")
