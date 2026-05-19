#!/usr/bin/env python3
"""用 OpenRouter (Gemini 3.1 Pro multimodal) 给 5 个样本生成 speaker GT。

为什么用 Gemini via OpenRouter:
- Claude Code (本 agent session) 无法直接处理音频 multimodal 输入
- Anthropic 官方 messages API 截至 2026-05 还不暴露 audio block
- Gemini 3.1 Pro 原生支持音频 input,中文质量好
- OpenRouter 一个 key 后续可以换 Gemini→Claude→GPT 互验

需要 `.env` 加(项目根目录):
  OPENROUTER_API_KEY=sk-or-v1-...

从 https://openrouter.ai/keys 拿。

可选 env:
  BENCHMARK_JUDGE_MODEL=google/gemini-3.1-pro    # 默认
  # 备选: google/gemini-3.1-flash (更便宜更快,质量略低)
  # 也可换 anthropic/claude-opus-4-7 (但 OpenRouter 上 Claude 走不通 audio)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLES = ROOT / "scripts" / "benchmark" / "samples"
GT = ROOT / "scripts" / "benchmark" / "ground_truth"

JUDGE_MODEL = os.environ.get("BENCHMARK_JUDGE_MODEL", "google/gemini-3.1-pro")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """你是音频访谈标注员。这是一段约 5 分钟的中文访谈音频,
**两个说话人**(研究者和受访者)。

任务:输出每一段说话的「时间区间 + 说话人 label + 文本」。

规则:
- 两个说话人用 A / B 标记;按音频中**首先开口**的那位标为 A,后开口的为 B
- 时间精度 0.1 秒。区间不重叠(同时说话时选音量更高那位)
- 短于 0.3 秒的语气词如果属于另一方,作为独立短段标出;否则合并到相邻
- 整段静音 / 笑声 / 咳嗽不要单独成段
- text 字段写转录文本,中文准确为主

**严格输出 JSON 一个对象,不要 markdown 代码块,不要解释,不要前后缀。**

{
  "speakers": ["A", "B"],
  "turns": [
    {"start": 0.0, "end": 8.7, "speaker": "A", "text": "..."},
    {"start": 8.8, "end": 15.2, "speaker": "B", "text": "..."}
  ]
}

确保 turns 按 start 升序,end 不超过音频总时长(约 300 秒)。
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
    """从模型输出文本里抓第一个 { ... } 段并 parse。"""
    cleaned = raw.strip()
    # 剥 markdown code fence
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl > 0:
            cleaned = cleaned[first_nl + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < 0:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        print(f"  JSON parse failed: {exc}", file=sys.stderr)
        print(f"  cleaned[:400]: {cleaned[:400]}", file=sys.stderr)
        return None


def call_openrouter_audio(api_key: str, audio_path: Path) -> Optional[Dict[str, Any]]:
    """调 OpenRouter OpenAI-compatible API,audio input_audio block (Gemini)。"""
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/XEasonChan/Liasse",
        "X-Title": "Liasse Diarization Benchmark",
    }
    payload = {
        "model": JUDGE_MODEL,
        "max_tokens": 16384,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64,
                            "format": "mp4",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "请严格按 system prompt 的 JSON schema 输出整段音频的标注。"
                            "只输出 JSON,不要任何其它文本。"
                        ),
                    },
                ],
            },
        ],
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(600.0, connect=10.0),
            proxy=None,
            trust_env=False,
        ) as cl:
            resp = cl.post(OPENROUTER_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            print(f"  OpenRouter {resp.status_code}: {resp.text[:400]}",
                  file=sys.stderr)
            return None
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return _extract_json(text)
    except Exception as exc:
        print(f"  request error: {exc}", file=sys.stderr)
        return None


def annotate(audio_path: Path, api_key: str) -> Optional[Dict[str, Any]]:
    print(f"\n=== {audio_path.name} ===")
    t0 = time.time()
    payload = call_openrouter_audio(api_key, audio_path)
    if payload is None:
        return None
    if "turns" not in payload:
        print(f"  malformed (no 'turns'): keys={list(payload.keys())}",
              file=sys.stderr)
        return None
    elapsed = time.time() - t0
    print(f"  ✓ {len(payload['turns'])} turns in {elapsed:.1f}s")
    return {
        "sample": audio_path.stem,
        "audio_dur_sec": _probe_dur(audio_path),
        "method": "openrouter-multimodal",
        "judge_model": JUDGE_MODEL,
        **payload,
    }


def main() -> int:
    _load_env()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print(
            "ERROR: OPENROUTER_API_KEY 未设置。\n\n"
            "  请把你的 OpenRouter key 加到项目根目录的 .env 文件:\n\n"
            "    echo 'OPENROUTER_API_KEY=sk-or-v1-...' >> .env\n\n"
            "  从 https://openrouter.ai/keys 获取。\n",
            file=sys.stderr,
        )
        return 1

    samples = sorted(SAMPLES.glob("*.m4a"))
    if not samples:
        print(f"ERROR: no samples in {SAMPLES}. Run cut_samples.py first.",
              file=sys.stderr)
        return 1

    print(f"Judge model: {JUDGE_MODEL}")
    GT.mkdir(parents=True, exist_ok=True)
    failures = []
    for audio in samples:
        gt_path = GT / f"{audio.stem}.gt.json"
        if gt_path.exists():
            print(f"  ✓ exists  {gt_path.name}")
            continue
        try:
            payload = annotate(audio, key)
            if payload is None:
                failures.append(audio.name)
                continue
            gt_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            print(f"  ✓ wrote   {gt_path.name}")
        except Exception as exc:
            import traceback
            print(f"  ✗ FAILED  {audio.name}: {exc}\n{traceback.format_exc()}",
                  file=sys.stderr)
            failures.append(audio.name)
    if failures:
        print(f"\n⚠ {len(failures)} samples failed: {failures}", file=sys.stderr)
        return 1
    print(f"\n✓ All {len(samples)} ground truth files in {GT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
