#!/usr/bin/env python3
"""用 Claude Opus 4.7 multimodal API 给 5 个 benchmark samples 标 ground truth。

接受用户提供的 ANTHROPIC_API_KEY (放 .env 或 env 变量)。

主路径:Claude 直接吃音频(audio block, base64)。
Fallback:如果 audio block 不被支持(返回 400) → 用 mlx-qwen3-asr 转文字
带时间戳,再让 Claude 看 transcript 推断 speaker(此 fallback 精度不如
multimodal,会在输出 JSON 的 method 字段标 fallback)。

输出 schema (JSON):
{
  "sample": "s1-opening",
  "audio_dur_sec": 300.0,
  "method": "claude-multimodal" | "transcript-only-fallback",
  "model": "claude-opus-4-7",
  "speakers": ["A", "B"],
  "turns": [
    {"start": 0.0, "end": 8.7, "speaker": "A", "text": "..."},
    ...
  ]
}
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import anthropic

ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLES = ROOT / "scripts" / "benchmark" / "samples"
GT = ROOT / "scripts" / "benchmark" / "ground_truth"

MODEL = "claude-opus-4-7"

SYSTEM_PROMPT = """你是音频访谈标注员。这是一段 5 分钟的中文访谈音频，
**两个说话人**(研究者和受访者)。

任务:输出每一段说话的「时间区间 + 说话人 label + 文本」。

规则:
- 两个说话人用 A / B 标记;按音频中**首先开口**的那位标为 A,后开口的为 B
- 时间精度 0.1 秒。区间不重叠(同时说话时选音量更高那位)
- 短于 0.3 秒的语气词(嗯/啊/对/嗯哼/对对对)如果显著属于另一方,作为独立
  短段标出来;否则合并到相邻发言
- 整段静音 / 笑声不要单独成段
- text 字段写转录,中文准确为主,不需要逐字精确,但要能反映「这一段是
  谁在说什么」

**严格输出 JSON 一个对象,不要 markdown 包裹,不要解释。schema:**

{
  "speakers": ["A", "B"],
  "turns": [
    {"start": 0.0, "end": 8.7, "speaker": "A", "text": "..."},
    {"start": 8.8, "end": 15.2, "speaker": "B", "text": "..."}
  ]
}

确保 turns 按 start 升序排列;最后一个 turn 的 end ≤ 音频总时长。
"""


def _load_env() -> None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _probe_dur(p: Path) -> float:
    import subprocess
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """从 Claude 输出文本里抓第一个 { ... } 段并 parse。"""
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        print(f"  JSON parse failed: {exc}", file=sys.stderr)
        print(f"  raw[0:200]: {raw[:200]}", file=sys.stderr)
        return None


def try_multimodal(client: anthropic.Anthropic, audio_path: Path) -> Optional[Dict[str, Any]]:
    """主路径:Claude 直接听音频。失败返回 None。"""
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=16384,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "source": {
                            "type": "base64",
                            "media_type": "audio/mp4",
                            "data": audio_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "请严格按 system prompt 的 JSON schema 输出整段音频的标注。",
                    },
                ],
            }],
        )
    except (anthropic.APIError, anthropic.BadRequestError) as exc:
        print(f"  multimodal API rejected: {exc}", file=sys.stderr)
        return None
    raw = resp.content[0].text if resp.content else ""
    return _extract_json(raw)


def fallback_transcript_then_claude(
    client: anthropic.Anthropic, audio_path: Path,
) -> Optional[Dict[str, Any]]:
    """Fallback:跑 ASR → Claude 看 transcript 推断 speaker。"""
    print("  -> falling back to transcript-then-Claude")
    sys.path.insert(0, str(ROOT))
    from liasse.models import TranscriptionJob
    from liasse.transcribe_pipeline import TranscribePipeline

    job = TranscriptionJob(
        audio_path=audio_path,
        output_dir=ROOT / "scripts" / "benchmark" / "_tmp_gt_transcribe" / audio_path.stem,
        asr_backend="mlx",
        language="Chinese",
        diarization_enabled=False,
    )
    result = TranscribePipeline().run(job)
    transcript_text = "\n".join(
        f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in result.segments
    )

    fallback_system = SYSTEM_PROMPT + """

**注意**:这次拿不到音频,只有 ASR 转录(已带时间戳)。从语义推断 speaker:
提问的通常是 A(研究者短句),回答的通常是 B(受访者长句)。
"""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=16384,
        system=fallback_system,
        messages=[{"role": "user", "content": transcript_text}],
    )
    raw = resp.content[0].text if resp.content else ""
    return _extract_json(raw)


def annotate(audio_path: Path, client: anthropic.Anthropic) -> Optional[Dict[str, Any]]:
    print(f"\n=== {audio_path.name} ===")
    t0 = time.time()
    payload = try_multimodal(client, audio_path)
    method = "claude-multimodal"
    if payload is None:
        payload = fallback_transcript_then_claude(client, audio_path)
        method = "transcript-only-fallback"
    if payload is None:
        return None
    if "turns" not in payload:
        print(f"  malformed payload (no 'turns'): {list(payload.keys())}", file=sys.stderr)
        return None
    elapsed = time.time() - t0
    print(f"  ✓ {len(payload['turns'])} turns, {method}, {elapsed:.1f}s")
    return {
        "sample": audio_path.stem,
        "audio_dur_sec": _probe_dur(audio_path),
        "method": method,
        "model": MODEL,
        **payload,
    }


def main() -> int:
    _load_env()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print(
            "ERROR: ANTHROPIC_API_KEY 未设置。\n"
            "  请在 .env 加: ANTHROPIC_API_KEY=sk-ant-...\n"
            "  从 https://console.anthropic.com/settings/keys 获取。",
            file=sys.stderr,
        )
        return 1
    sys.path.insert(0, str(ROOT))
    GT.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic(api_key=key)

    samples = sorted(SAMPLES.glob("*.m4a"))
    if not samples:
        print(f"ERROR: no samples found in {SAMPLES}\n  跑 cut_samples.py 先。", file=sys.stderr)
        return 1

    failures = []
    for audio in samples:
        gt_path = GT / f"{audio.stem}.gt.json"
        if gt_path.exists():
            print(f"  ✓ exists  {gt_path.name}")
            continue
        try:
            payload = annotate(audio, client)
            if payload is None:
                failures.append(audio.name)
                continue
            gt_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            print(f"  ✓ wrote   {gt_path.name}")
        except Exception as exc:
            import traceback
            print(f"  ✗ FAILED  {audio.name}: {exc}\n{traceback.format_exc()}", file=sys.stderr)
            failures.append(audio.name)
    if failures:
        print(f"\n⚠ {len(failures)} samples failed: {failures}", file=sys.stderr)
        return 1
    print(f"\n✓ All {len(samples)} ground truth files in {GT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
