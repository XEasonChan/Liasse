from __future__ import annotations

import multiprocessing as mp
import os
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .web_models import TaskRow, init_db, session_scope, utc_now

ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file)
    except ImportError:
        for line in env_file.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _worker_entry(
    job_payload: Dict[str, Any],
    progress_queue: mp.Queue,
    stop_event: "mp.synchronize.Event",
) -> None:
    """Runs in a fresh subprocess. Loads pipeline + executes job."""
    try:
        _load_env()
        from .models import TranscriptionJob
        from .pipeline import LocalTranscriptionPipeline

        config = job_payload["config"]
        audio_path = Path(job_payload["audioPath"])
        output_dir = Path(job_payload["outputDir"])

        if os.environ.get("WHISPERQWEN_FULLY_OFFLINE"):
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"

        def on_progress(message: str, value: float) -> None:
            if stop_event.is_set():
                raise InterruptedError("用户停止了任务")
            progress_queue.put({"type": "progress", "stage": message, "value": value})

        auto_segment = config.get("autoSegment")
        auto_segment = True if auto_segment is None else bool(auto_segment)
        # 关闭自动分段时强制不做发言人识别，否则 diarization 没法对齐时间戳
        diarize = bool(config.get("diarize")) and auto_segment
        job = TranscriptionJob(
            audio_path=audio_path,
            output_dir=output_dir,
            asr_backend="mlx",
            language=config.get("language") or "Chinese",
            qwen_model=config.get("asrModel") or "Qwen/Qwen3-ASR-0.6B",
            qwen_return_timestamps=auto_segment,
            diarization_enabled=diarize,
            diarization_num_speakers=config.get("numSpeakers"),
            hf_token=os.environ.get("HF_TOKEN") or os.environ.get("PYANNOTE_AUTH_TOKEN"),
            summary_enabled=bool(config.get("summarize")),
            summary_model=config.get("summaryModel") or "qwen3:4b",
            export_srt=True,
        )

        progress_queue.put({"type": "progress", "stage": "加载模型", "value": 0.02})
        result = LocalTranscriptionPipeline(on_progress=on_progress).run(job)

        segments = [
            {
                "id": f"seg-{i}",
                "speaker": seg.speaker,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
            }
            for i, seg in enumerate(result.segments)
        ]
        summary_text = result.summary.text if result.summary else None

        progress_queue.put(
            {
                "type": "done",
                "outputs": {
                    "dir": str(result.output_dir),
                    "markdownPath": str(result.markdown_path),
                    "jsonPath": str(result.json_path),
                    "srtPath": str(result.srt_path) if result.srt_path else None,
                },
                "segments": segments,
                "summaryText": summary_text,
            }
        )
    except InterruptedError:
        progress_queue.put({"type": "stopped"})
    except Exception as exc:
        progress_queue.put(
            {
                "type": "failed",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )


class TaskRunner:
    """Background single-worker runner. Polls SQLite for queued tasks, dispatches one at a time."""

    def __init__(self, db_path: Path, poll_interval: float = 1.0):
        self.db_path = db_path
        self.poll_interval = poll_interval
        self._stop_runner = threading.Event()
        self._dispatcher_thread: Optional[threading.Thread] = None
        self._current_process: Optional[mp.Process] = None
        self._current_task_id: Optional[str] = None
        self._current_stop_event: Optional[Any] = None
        self._lock = threading.Lock()
        self._ctx = mp.get_context("spawn")

    def start(self) -> None:
        init_db(self.db_path)
        self._cleanup_orphans()
        self._dispatcher_thread = threading.Thread(
            target=self._dispatcher_loop, name="task-dispatcher", daemon=True
        )
        self._dispatcher_thread.start()

    def _cleanup_orphans(self) -> None:
        """启动时把上次应用退出后还停在 running 的任务标为 stopped (interrupted)，
        这样 UI 不会一直显示「处理中」，用户可以重试。
        """
        from sqlalchemy import select

        session = session_scope()
        try:
            rows = session.execute(
                select(TaskRow).where(TaskRow.status.in_(["running", "stopping"]))
            ).scalars().all()
            for row in rows:
                row.status = "stopped"
                row.progress_stage = "应用上次退出时被中断"
                row.error_message = (
                    "Task was interrupted because the app exited while it was running. "
                    "Click Retry to re-queue this task from the beginning."
                )
                row.completed_at = utc_now()
            session.commit()
        finally:
            session.close()

    def stop(self) -> None:
        self._stop_runner.set()
        with self._lock:
            proc = self._current_process
            stop_event = self._current_stop_event
        if stop_event is not None:
            stop_event.set()
        if proc is not None and proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()
        if self._dispatcher_thread is not None:
            self._dispatcher_thread.join(timeout=3)

    def request_stop(self, task_id: str) -> bool:
        with self._lock:
            if self._current_task_id != task_id:
                return False
            stop_event = self._current_stop_event
            proc = self._current_process
        if stop_event is not None:
            stop_event.set()
        if proc is not None and proc.is_alive():
            time.sleep(0.5)
            if proc.is_alive():
                proc.terminate()
        return True

    def _pick_next_queued(self) -> Optional[Dict[str, Any]]:
        with session_scope() as session:
            from sqlalchemy import select

            row = (
                session.execute(
                    select(TaskRow)
                    .where(TaskRow.status == "queued")
                    .order_by(TaskRow.created_at.asc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            if row is None:
                return None
            row.status = "running"
            row.started_at = utc_now()
            row.progress = 0.01
            row.progress_stage = "启动中"
            session.commit()
            return {
                "id": row.id,
                "audioPath": row.audio_path,
                "config": dict(row.config or {}),
            }

    def _dispatcher_loop(self) -> None:
        outputs_dir = ROOT / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        while not self._stop_runner.is_set():
            job = self._pick_next_queued()
            if job is None:
                time.sleep(self.poll_interval)
                continue

            queue: mp.Queue = self._ctx.Queue()
            stop_event = self._ctx.Event()
            payload = {
                "id": job["id"],
                "audioPath": job["audioPath"],
                "outputDir": str(outputs_dir),
                "config": job["config"],
            }
            proc = self._ctx.Process(
                target=_worker_entry,
                args=(payload, queue, stop_event),
                daemon=True,
            )
            with self._lock:
                self._current_task_id = job["id"]
                self._current_process = proc
                self._current_stop_event = stop_event
            proc.start()

            final_msg: Optional[Dict[str, Any]] = None
            started = time.time()
            while True:
                if self._stop_runner.is_set() and not stop_event.is_set():
                    stop_event.set()

                try:
                    msg = queue.get(timeout=0.5)
                except Exception:
                    msg = None

                if msg is None:
                    if not proc.is_alive() and queue.empty():
                        if final_msg is None:
                            final_msg = {
                                "type": "failed",
                                "error": "工作进程意外退出（可能崩溃或被系统终止）",
                                "traceback": "",
                            }
                        break
                    continue

                if msg["type"] == "progress":
                    self._apply_progress(job["id"], msg)
                elif msg["type"] in {"done", "failed", "stopped"}:
                    final_msg = msg

            proc.join(timeout=5)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2)

            elapsed = time.time() - started
            self._finalize(job["id"], final_msg or {"type": "failed", "error": "未知错误"}, elapsed)

            with self._lock:
                self._current_task_id = None
                self._current_process = None
                self._current_stop_event = None

    def _apply_progress(self, task_id: str, msg: Dict[str, Any]) -> None:
        with session_scope() as session:
            row = session.get(TaskRow, task_id)
            if row is None or row.status != "running":
                return
            incoming = min(1.0, max(0.0, float(msg.get("value", row.progress))))
            row.progress = max(float(row.progress or 0.0), incoming)
            row.progress_stage = msg.get("stage") or row.progress_stage
            session.commit()

    def _finalize(self, task_id: str, msg: Dict[str, Any], elapsed_sec: float) -> None:
        prewarm_chat = False
        with session_scope() as session:
            row = session.get(TaskRow, task_id)
            if row is None:
                return
            now = utc_now()
            row.elapsed_sec = elapsed_sec
            row.completed_at = now

            kind = msg.get("type")
            if kind == "done":
                row.status = "done"
                row.progress = 1.0
                row.progress_stage = "完成"
                row.outputs = msg.get("outputs")
                row.transcript = {"segments": msg.get("segments") or []}
                row.summary_text = msg.get("summaryText")
                prewarm_chat = bool((row.config or {}).get("enableChat"))
            elif kind == "stopped":
                if row.status != "stopped":
                    row.status = "stopped"
                row.progress_stage = "已停止"
            else:
                row.status = "failed"
                row.progress_stage = "失败"
                err = msg.get("error") or "未知错误"
                tb = msg.get("traceback") or ""
                row.error_message = f"{err}\n\n{tb}" if tb else err
            session.commit()

        if prewarm_chat:
            threading.Thread(target=self._prewarm_digest, args=(task_id,), daemon=True).start()

    def _prewarm_digest(self, task_id: str) -> None:
        try:
            from . import chat as chat_module

            with session_scope() as session:
                row = session.get(TaskRow, task_id)
                if row is None or row.chat_context_digest:
                    return
                segments = (row.transcript or {}).get("segments", []) if row.transcript else []
                if not segments:
                    return
                edits = row.edits or {}
                transcript_text = chat_module.segments_to_text(
                    segments,
                    speaker_labels=edits.get("speakerLabels") or {},
                    overrides=edits.get("segmentOverrides") or {},
                )
                model = (row.config or {}).get("summaryModel") or "qwen3:4b"

            digest = chat_module.generate_digest(transcript_text, model=model)

            with session_scope() as session:
                row = session.get(TaskRow, task_id)
                if row is not None and not row.chat_context_digest:
                    row.chat_context_digest = digest
                    session.commit()
        except Exception as exc:
            print(f"[task_runner] 预热 digest 失败 task={task_id}: {exc}")
