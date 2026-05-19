from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class DownloadJob:
    job_id: str
    model_id: str
    kind: str
    status: str = "running"
    progress: float = 0.0
    bytes_done: int = 0
    bytes_total: int = 0
    speed_bps: float = 0.0
    eta_sec: Optional[int] = None
    message: str = ""
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    events: "queue.Queue[dict]" = field(default_factory=queue.Queue)
    _stop: threading.Event = field(default_factory=threading.Event)


_JOBS: Dict[str, DownloadJob] = {}
_LOCK = threading.Lock()


def get_job(job_id: str) -> Optional[DownloadJob]:
    with _LOCK:
        return _JOBS.get(job_id)


def list_jobs() -> List[DownloadJob]:
    with _LOCK:
        return list(_JOBS.values())


def _publish(job: DownloadJob, event: str, **payload) -> None:
    msg = {"event": event, **payload}
    job.events.put(msg)


def _finish(job: DownloadJob, error: Optional[str] = None) -> None:
    job.finished_at = time.time()
    if error:
        job.status = "failed"
        job.error = error
        _publish(job, "error", message=error)
    else:
        job.status = "done"
        job.progress = 1.0
        _publish(job, "done")
    job.events.put({"event": "__close__"})


_OLLAMA_PROGRESS_RE = re.compile(
    r"pulling\s+([a-f0-9]+).*?(\d+)%.*?(\d+(?:\.\d+)?\s*[KMGT]?B)/(\d+(?:\.\d+)?\s*[KMGT]?B)",
    re.IGNORECASE,
)


def _parse_size_to_bytes(s: str) -> int:
    s = s.strip().upper()
    m = re.match(r"(\d+(?:\.\d+)?)\s*([KMGT]?)B", s)
    if not m:
        return 0
    num = float(m.group(1))
    unit = m.group(2)
    mult = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}.get(unit, 1)
    return int(num * mult)


def _run_ollama_pull(job: DownloadJob, model_id: str) -> None:
    try:
        proc = subprocess.Popen(
            ["ollama", "pull", model_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        _finish(job, "ollama 二进制未找到（brew install ollama）")
        return

    assert proc.stdout is not None
    last_pct = -1
    for line in proc.stdout:
        if job._stop.is_set():
            proc.terminate()
            _finish(job, "用户取消")
            return
        line = line.strip()
        if not line:
            continue
        m = _OLLAMA_PROGRESS_RE.search(line)
        if m:
            pct = int(m.group(2))
            done = _parse_size_to_bytes(m.group(3))
            total = _parse_size_to_bytes(m.group(4))
            job.progress = pct / 100.0
            job.bytes_done = done
            job.bytes_total = total
            elapsed = time.time() - job.started_at
            if elapsed > 0:
                job.speed_bps = done / elapsed
                if job.speed_bps > 0 and total > done:
                    job.eta_sec = int((total - done) / job.speed_bps)
            if pct != last_pct:
                _publish(
                    job,
                    "progress",
                    progress=job.progress,
                    bytesDone=job.bytes_done,
                    bytesTotal=job.bytes_total,
                    speedBps=job.speed_bps,
                    etaSec=job.eta_sec,
                )
                last_pct = pct
        else:
            job.message = line
            _publish(job, "log", line=line)

    proc.wait()
    if proc.returncode != 0:
        _finish(job, f"ollama pull 退出码 {proc.returncode}")
    else:
        _finish(job)


def _run_hf_download(job: DownloadJob, repo_id: str) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        _finish(job, "huggingface_hub 未安装")
        return

    token = (
        os.environ.get("HF_TOKEN")
        or os.environ.get("PYANNOTE_AUTH_TOKEN")
        or os.environ.get("HUGGINGFACE_TOKEN")
    )

    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    repo_cache = cache_dir / f"models--{repo_id.replace('/', '--')}"
    blobs_dir = repo_cache / "blobs"

    job.bytes_total = 0
    expected_total_bytes: Dict[str, int] = {}
    try:
        from huggingface_hub import HfApi

        api = HfApi(token=token)
        info = api.repo_info(repo_id=repo_id, files_metadata=True)
        for sibling in info.siblings or []:
            if sibling.size:
                expected_total_bytes[sibling.rfilename] = sibling.size
        job.bytes_total = sum(expected_total_bytes.values())
    except Exception:
        pass

    stop_poll = threading.Event()

    def poller():
        while not stop_poll.is_set():
            try:
                if blobs_dir.exists():
                    total = 0
                    for f in blobs_dir.iterdir():
                        if f.is_file():
                            try:
                                total += f.stat().st_size
                            except OSError:
                                pass
                    job.bytes_done = total
                    if job.bytes_total > 0:
                        job.progress = min(0.99, total / job.bytes_total)
                    elapsed = time.time() - job.started_at
                    if elapsed > 0.5:
                        job.speed_bps = total / elapsed
                        if job.bytes_total > 0 and job.speed_bps > 0:
                            remaining = job.bytes_total - total
                            job.eta_sec = max(0, int(remaining / job.speed_bps))
                    _publish(
                        job,
                        "progress",
                        progress=job.progress,
                        bytesDone=job.bytes_done,
                        bytesTotal=job.bytes_total,
                        speedBps=job.speed_bps,
                        etaSec=job.eta_sec,
                    )
            except OSError:
                pass
            stop_poll.wait(1.0)

    poll_thread = threading.Thread(target=poller, daemon=True)
    poll_thread.start()

    try:
        snapshot_download(repo_id=repo_id, token=token)
    except Exception as exc:
        stop_poll.set()
        poll_thread.join(timeout=2)
        _finish(job, f"{type(exc).__name__}: {exc}")
        return

    stop_poll.set()
    poll_thread.join(timeout=2)
    job.progress = 1.0
    if job.bytes_total:
        job.bytes_done = job.bytes_total
    _finish(job)


_HF_REPOS = {
    "Qwen/Qwen3-ASR-0.6B",
    "Qwen/Qwen3-ASR-1.7B",
    "Qwen/Qwen3-ForcedAligner-0.6B",
    "pyannote/speaker-diarization-community-1",
}


def start_download(model_id: str) -> DownloadJob:
    job_id = uuid.uuid4().hex[:12]

    if model_id in _HF_REPOS:
        kind = "hf"
        target = lambda: _run_hf_download(job, model_id)
    elif ":" in model_id:
        kind = "ollama"
        target = lambda: _run_ollama_pull(job, model_id)
    else:
        raise ValueError(f"未知 model_id: {model_id}")

    job = DownloadJob(job_id=job_id, model_id=model_id, kind=kind)
    with _LOCK:
        _JOBS[job_id] = job
    threading.Thread(target=target, daemon=True).start()
    return job


def cancel_job(job_id: str) -> bool:
    job = get_job(job_id)
    if not job or job.status != "running":
        return False
    job._stop.set()
    return True
