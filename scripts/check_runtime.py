from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_env_file()
    line("Local Transcriber runtime check")
    line(f"project: {ROOT}")
    line("")

    ok = True
    ok &= check_binary("ffmpeg")
    ok &= check_binary("ffprobe")
    check_ollama_model()
    check_hf_cache()
    check_hf_token()
    print("")
    ok &= check_python_runtime(ROOT / "venv" / "bin" / "python", "model runtime")
    check_python_runtime(Path("/usr/bin/python3"), "GUI runtime", required_modules=["tkinter"])

    print("")
    if ok:
        line("核心转录依赖看起来齐了。")
    else:
        line("还有缺口，优先看上面标为 FAIL 的项目。")
    return 0 if ok else 1


def check_binary(name: str) -> bool:
    path = shutil.which(name)
    if path:
        line(f"[OK] {name}: {path}")
        return True
    line(f"[FAIL] {name}: not found")
    return False


def check_ollama_model() -> None:
    root = Path.home() / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / "qwen3"
    manifest_4b = root / "4b"
    manifest_8b = root / "8b"
    if manifest_4b.exists():
        line("[OK] ollama qwen3:4b: model manifest found")
    else:
        line("[WARN] ollama qwen3:4b: manifest not found; summary/chat need `ollama pull qwen3:4b`")

    if manifest_8b.exists():
        line("[OK] ollama qwen3:8b: optional model manifest found")
    else:
        line("[WARN] ollama qwen3:8b: optional model not found; quality mode may need `ollama pull qwen3:8b`")


def check_hf_cache() -> None:
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    qwen = hub / "models--Qwen--Qwen3-ASR-0.6B"
    aligner = hub / "models--Qwen--Qwen3-ForcedAligner-0.6B"
    pyannote = hub / "models--pyannote--speaker-diarization-community-1"
    line(f"[{'OK' if qwen.exists() else 'WARN'}] HF cache Qwen3-ASR-0.6B")
    line(f"[{'OK' if aligner.exists() else 'WARN'}] HF cache Qwen3-ForcedAligner-0.6B")
    line(f"[{'OK' if pyannote.exists() else 'WARN'}] HF cache pyannote speaker diarization")


def check_hf_token() -> None:
    env_token = any(os.environ.get(k) for k in ["PYANNOTE_AUTH_TOKEN", "HF_TOKEN", "HUGGINGFACE_TOKEN"])
    cached_token = False
    try:
        from huggingface_hub import get_token

        cached_token = bool(get_token())
    except Exception:
        pass
    if env_token or cached_token:
        line("[OK] Hugging Face token: available")
    else:
        line("[WARN] Hugging Face token: missing; diarization gated model cannot download yet")


def load_env_file() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file)
        return
    except ImportError:
        pass

    for line_text in env_file.read_text(encoding="utf-8").splitlines():
        if line_text and not line_text.startswith("#") and "=" in line_text:
            key, value = line_text.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def check_python_runtime(
    python: Path,
    label: str,
    required_modules: list[str] | None = None,
) -> bool:
    if not python.exists():
        line(f"[FAIL] {label}: {python} not found")
        return False

    modules = required_modules or [
        "mlx",
        "numpy",
        "regex",
        "huggingface_hub",
        "mlx_qwen3_asr",
        "pyannote.audio",
        "torch",
        "torchcodec",
        "fastapi",
        "uvicorn",
    ]
    line(f"{label}: {python}")
    all_ok = True
    version = run_json(python, "import sys, json; print(json.dumps({'version': sys.version.split()[0]}))")
    if version:
        line(f"  python: {version.get('version')}")

    for module in modules:
        timeout = 30 if module in {"torch", "torchcodec", "pyannote.audio"} else 8
        result = run_json(
            python,
            (
                "import importlib.util, json\n"
                f"name = {module!r}\n"
                "try:\n"
                "    spec = importlib.util.find_spec(name)\n"
                "    if spec is None:\n"
                "        print(json.dumps({'ok': False, 'error': 'module not found'}))\n"
                "    elif name in {'tkinter', '_tkinter', 'torch', 'torchcodec'}:\n"
                "        import importlib\n"
                "        importlib.import_module(name)\n"
                "        print(json.dumps({'ok': True}))\n"
                "    else:\n"
                "        print(json.dumps({'ok': True}))\n"
                "except Exception as e:\n"
                "    print(json.dumps({'ok': False, 'error': type(e).__name__ + ': ' + str(e)}))\n"
            ),
            timeout=timeout,
        )
        if result and result.get("ok"):
            line(f"  [OK] {module}")
        else:
            all_ok = False
            error = result.get("error") if result else "timeout or no output"
            line(f"  [FAIL] {module}: {error}")
    return all_ok


def run_json(python: Path, code: str, timeout: int = 8) -> dict | None:
    try:
        completed = subprocess.run(
            [str(python), "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if not completed.stdout.strip():
        return None
    try:
        return json.loads(completed.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": completed.stdout.strip() or completed.stderr.strip()}


def line(text: str) -> None:
    print(text, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
