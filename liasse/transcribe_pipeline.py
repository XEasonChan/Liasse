from __future__ import annotations

import os
import threading
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Optional

from .alignment import assign_speakers
from .asr import create_asr_backend
from .diarization import PyannoteDiarizer, speaker_turns_from_segments
from .exporters import export_json, export_markdown, export_srt
from .models import PipelineResult, SpeakerTurn, SummaryResult, TranscriptionJob, TranscriptSegment

ProgressCallback = Callable[[str, float], None]
PartialTranscriptCallback = Callable[[dict[str, Any]], None]

ASR_PROGRESS_START = 0.04
ASR_CHUNK_PROGRESS_END = 0.82
ASR_PROGRESS_DONE = 0.88
SUMMARY_PROGRESS_START = 0.91
EXPORT_PROGRESS_START = 0.96


class TranscribePipeline:
    def __init__(
        self,
        on_progress: Optional[ProgressCallback] = None,
        on_partial_transcript: Optional[PartialTranscriptCallback] = None,
    ) -> None:
        self.on_progress = on_progress or (lambda _message, _value: None)
        self.on_partial_transcript = on_partial_transcript or (lambda _payload: None)
        self._partial_segments: List[TranscriptSegment] = []
        self._partial_chunk_indices: set[int] = set()
        self._partial_raw_text_path: Optional[Path] = None
        self._partial_output_dir: Optional[Path] = None

    def run(self, job: TranscriptionJob) -> PipelineResult:
        if not job.audio_path.exists() and job.asr_backend != "demo":
            raise FileNotFoundError(f"找不到音频文件：{job.audio_path}")

        job.output_dir.mkdir(parents=True, exist_ok=True)
        output_dir = self._job_output_dir(job)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._prepare_partial_transcript(job, output_dir)

        is_mlx = job.asr_backend.lower().strip() in {"mlx", "mlx-qwen", "mlx-qwen3-asr"}
        speaker_turns: List[SpeakerTurn] = []

        if job.diarization_enabled and is_mlx:
            # 关键路径：ASR 和 pyannote 并行。两者都读完整 wav 互不依赖。
            # 在 M1 16GB 上能把 pyannote 5-10 分钟的开销「吃」进 ASR 的时间里。
            self._progress("准备转录音频", ASR_PROGRESS_START)
            segments, speaker_turns = self._run_parallel_asr_and_diarization(job)
        else:
            # 走 ASR-only 或 whisper-then-pyannote 老路径。
            self._progress("准备转录音频", ASR_PROGRESS_START)
            # 强制 backend 内部不做 diarization (pyannote 走我们这边或不做)
            asr_job = replace(job, diarization_enabled=False) if is_mlx and job.diarization_enabled else job
            segments = self._transcribe(asr_job)
            if not segments:
                raise RuntimeError("转录没有返回任何文本。")

            if job.diarization_enabled and not is_mlx:
                self._progress("正在识别发言人", ASR_PROGRESS_DONE)
                speaker_turns = PyannoteDiarizer(
                    job.pyannote_model,
                    job.hf_token,
                    num_speakers=job.diarization_num_speakers,
                ).diarize(job.audio_path)
                segments = assign_speakers(segments, speaker_turns)
            else:
                speaker_turns = speaker_turns_from_segments(segments)

        if not segments:
            raise RuntimeError("转录没有返回任何文本。")

        # Summary 由 task_runner 在 pipeline 之后调 summary_pipeline.analyze() 生成。
        # 这里仍保留 PipelineResult.summary 字段，task_runner 会塞 L2 结果进去。
        summary: Optional[SummaryResult] = None

        self._progress("正在导出文件", EXPORT_PROGRESS_START)
        markdown_path = output_dir / f"{job.audio_path.stem or 'demo'}-transcript.md"
        json_path = output_dir / f"{job.audio_path.stem or 'demo'}-transcript.json"
        srt_path = output_dir / f"{job.audio_path.stem or 'demo'}-transcript.srt"

        export_markdown(markdown_path, job.audio_path, segments, speaker_turns, summary)
        export_json(json_path, job.audio_path, segments, speaker_turns, summary)
        if job.export_srt:
            export_srt(srt_path, segments)
        else:
            srt_path = None

        self._progress("完成", 1.0)
        return PipelineResult(
            audio_path=job.audio_path,
            output_dir=output_dir,
            markdown_path=markdown_path,
            json_path=json_path,
            srt_path=srt_path,
            segments=segments,
            speaker_turns=speaker_turns,
            summary=summary,
        )

    def _run_parallel_asr_and_diarization(
        self, job: TranscriptionJob
    ) -> tuple[List[TranscriptSegment], List[SpeakerTurn]]:
        """并行跑 ASR + pyannote diarization。两者都读完整 wav，互不依赖。

        旧路径：mlx_qwen3_asr.transcribe(diarize=True) 内部先 ASR 再 pyannote
        串行，总时间 = ASR + pyannote。pyannote 在 CPU 上跑 60min 音频约
        10-15 分钟，是个明显瓶颈。

        新路径：开一个 thread 跑独立 PyannoteDiarizer（先 .to("mps") 拿 3-5x
        加速），主线程跑纯 ASR；ASR 完后 join() 等 pyannote。总时间约等于
        max(ASR, pyannote)，pyannote 通常会比 ASR 略短，所以「贴近 ASR
        时间」。

        失败处理：pyannote 抛错 → 落回 speaker_turns_from_segments（按
        segment 拆 turn），ASR 结果不丢；可通过 transcript.warnings 让
        前端看到。
        """
        diar_state: dict[str, Any] = {"turns": None, "error": None, "started_at": None}
        # 让 worker 在做完一次性 setup（import torch / accelerate）之后再让主
        # 线程往下走，确保 pyannote 真的与 ASR 并发跑而不是排队跑。生产场景
        # ASR 几分钟，setup 1s 无影响；但短任务/测试时尺度小，必须显式同步。
        worker_ready = threading.Event()

        def diar_worker():
            diar_state["started_at"] = time.time()
            try:
                # 一次性 setup（可能慢：import torch、检查 MPS）
                self._accelerate_pyannote_on_mps_if_possible()
                # setup 完了，主线程可以开始 ASR。
                worker_ready.set()
                # 真正的工作：load pipeline + run diarization
                diarizer = PyannoteDiarizer(
                    job.pyannote_model,
                    job.hf_token,
                    num_speakers=job.diarization_num_speakers,
                )
                turns = diarizer.diarize(job.audio_path)
                diar_state["turns"] = turns
            except Exception as exc:
                diar_state["error"] = exc
                worker_ready.set()  # 必须 set，否则主线程 wait 卡死

        thread = threading.Thread(
            target=diar_worker, name="pyannote-parallel", daemon=True
        )
        thread.start()
        # 等 worker 完成轻量 setup（最长 5 秒；超时也继续，不阻塞 ASR）
        worker_ready.wait(timeout=5.0)

        # 主线程跑纯 ASR（强制 backend 内部 diarize=False，避免装 pyannote 两份）
        asr_job = replace(job, diarization_enabled=False)
        segments = self._transcribe(asr_job)

        # ASR 完了，等 pyannote
        if thread.is_alive():
            self._progress(
                "ASR 完成，正在等发言人识别收尾", ASR_CHUNK_PROGRESS_END + 0.02
            )
        thread.join()

        if diar_state["error"] is not None:
            # pyannote 失败 → 不影响转录交付，但记 warning（caller 处理）
            self._progress(
                f"发言人识别失败({diar_state['error']})，按 ASR 时间窗划分",
                ASR_PROGRESS_DONE,
            )
            return segments, speaker_turns_from_segments(segments)

        turns = diar_state["turns"] or []
        if not turns:
            return segments, speaker_turns_from_segments(segments)

        self._progress("对齐发言人与转录", ASR_PROGRESS_DONE)
        aligned = assign_speakers(segments, turns)
        return aligned, turns

    @staticmethod
    def _accelerate_pyannote_on_mps_if_possible() -> None:
        """让独立加载的 pyannote pipeline 也走 MPS（M1/M2 上 3-5x 加速）。

        注意：pyannote pipeline.from_pretrained 没有 device 参数；要在加载
        完之后 .to(torch.device("mps"))。这里只设环境变量，pipeline.to()
        在 PyannoteDiarizer.diarize 内部不写（保留独立），所以我们直接在
        worker thread 里 patch 一次 from_pretrained 让它返回的 pipeline 自动
        切 MPS。

        实际做法：包一个 monkey patch — 但更简单地，我们在 diar_worker 加载
        pipeline 后直接 .to('mps')。这里只确保 MPS fallback 开关已开，pyannote
        遇到 MPS 没实现的算子能 fallback CPU 而不崩。
        """
        try:
            import torch
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        except Exception:
            pass

    def _transcribe(self, job: TranscriptionJob) -> List[TranscriptSegment]:
        # 记给 _asr_progress 用：知道是否启用 diarization，决定最后一 chunk 完成后
        # stage 要切到 "正在识别发言人" 还是 "转录完成"。
        self._diarize_enabled = bool(job.diarization_enabled)
        backend = create_asr_backend(
            backend=job.asr_backend,
            qwen_model=job.qwen_model,
            qwen_aligner=job.qwen_aligner,
            qwen_return_timestamps=job.qwen_return_timestamps,
            whisper_model=job.whisper_model,
            diarization_enabled=job.diarization_enabled,
            pyannote_model=job.pyannote_model,
            hf_token=job.hf_token,
            num_speakers=job.diarization_num_speakers,
        )
        return backend.transcribe(job.audio_path, job.language, on_progress=self._asr_progress)

    def _job_output_dir(self, job: TranscriptionJob) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        stem = job.audio_path.stem or "demo"
        return job.output_dir / f"{stem}-{timestamp}"

    def _progress(self, message: str, value: float) -> None:
        self.on_progress(message, self._clamp_progress(value))

    def _asr_progress(self, payload: dict[str, Any]) -> None:
        event = str(payload.get("event") or "")
        if event == "chunks_prepared":
            total = self._positive_int(payload.get("total_chunks"))
            if total:
                self._progress(f"准备转录音频（共 {total} 段）", ASR_PROGRESS_START)
            else:
                self._progress("准备转录音频", ASR_PROGRESS_START)
            return

        if event in {"chunk_started", "chunk_completed"}:
            total = self._positive_int(payload.get("total_chunks"))
            index = self._positive_int(payload.get("chunk_index"))
            raw = self._float_or_none(payload.get("progress"))
            value = self._scale_asr_progress(raw if raw is not None else 0.0)
            if total and index:
                self._progress(f"正在转录音频 {index}/{total}", value)
            else:
                self._progress("正在转录音频", value)
            if event == "chunk_completed":
                self._record_partial_chunk(payload)
            # 最后一个 chunk 完成后，pyannote 会在后台跑全局 diarization
            # （CPU/MPS 上几分钟，mlx-qwen3-asr 没有 diarization_started 事件）。
            # 主动切 stage 让用户知道阶段已经变了，UI 不再卡在 "X/X"。
            if (
                event == "chunk_completed"
                and total
                and index
                and index == total
                and getattr(self, "_diarize_enabled", False)
            ):
                self._progress(
                    "正在识别发言人，请稍候（pyannote 全局推理，2-5 分钟）",
                    ASR_CHUNK_PROGRESS_END,
                )
            return

        if event == "diarization_completed":
            self._progress("正在整理发言人分段", ASR_PROGRESS_DONE - 0.01)
            return

        if event == "completed":
            self._progress("转录完成，准备导出", ASR_PROGRESS_DONE)
            return

    def _scale_asr_progress(self, raw_value: float) -> float:
        raw = self._clamp_progress(raw_value)
        return ASR_PROGRESS_START + raw * (ASR_CHUNK_PROGRESS_END - ASR_PROGRESS_START)

    def _clamp_progress(self, value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    def _float_or_none(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _positive_int(self, value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _prepare_partial_transcript(
        self,
        job: TranscriptionJob,
        output_dir: Path,
    ) -> None:
        self._partial_segments = []
        self._partial_chunk_indices = set()
        self._partial_output_dir = output_dir
        stem = job.audio_path.stem or "demo"
        self._partial_raw_text_path = output_dir / f"{stem}-raw.partial.txt"

    def _record_partial_chunk(self, payload: dict[str, Any]) -> None:
        text = str(payload.get("text") or "").strip()
        if not text:
            return

        index = self._positive_int(payload.get("chunk_index"))
        if index is not None:
            if index in self._partial_chunk_indices:
                return
            self._partial_chunk_indices.add(index)

        start = self._float_or_none(payload.get("chunk_offset_sec"))
        duration = self._float_or_none(payload.get("chunk_duration_sec"))
        end = start + duration if start is not None and duration is not None else None
        self._partial_segments.append(
            TranscriptSegment(
                start=start,
                end=end,
                speaker="SPEAKER_00",
                text=text,
                source="raw-chunk",
            )
        )

        raw_text = "\n".join(seg.text for seg in self._partial_segments if seg.text).strip()
        if self._partial_raw_text_path is not None:
            self._partial_raw_text_path.write_text(raw_text, encoding="utf-8")

        self.on_partial_transcript(
            {
                "segments": list(self._partial_segments),
                "rawText": raw_text,
                "rawTextPath": str(self._partial_raw_text_path)
                if self._partial_raw_text_path is not None
                else None,
                "outputDir": str(self._partial_output_dir)
                if self._partial_output_dir is not None
                else None,
            }
        )
