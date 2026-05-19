from __future__ import annotations

import socket
import subprocess
import threading
import time
from pathlib import Path

import uvicorn
import webview

from local_transcriber.web_app import app


HOST = "127.0.0.1"
PORT = 5173
APP_ICON_PATH = Path(__file__).resolve().parent / "local_transcriber" / "web_static" / "assets" / "app-icon.png"

AUDIO_FILE_TYPES = (
    "音频文件 (*.mp3;*.wav;*.m4a;*.flac;*.aac;*.ogg;*.wma;*.mp4)",
)


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _set_macos_app_icon() -> None:
    """给 pywebview 开发态窗口设置 Dock / App Switcher 图标。"""
    if not APP_ICON_PATH.exists():
        return
    try:
        from AppKit import NSApplication, NSImage
    except ImportError:
        return

    image = NSImage.alloc().initWithContentsOfFile_(str(APP_ICON_PATH))
    if image is not None:
        NSApplication.sharedApplication().setApplicationIconImage_(image)


class JSApi:
    """暴露给前端 JS 的接口。通过 window.pywebview.api.* 调用。"""

    def pick_files(self) -> list[str]:
        windows = webview.windows
        if not windows:
            return []
        result = windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=AUDIO_FILE_TYPES,
        )
        if not result:
            return []
        return [str(Path(p)) for p in result]

    def pick_folder(self) -> dict:
        """返回 {cancelled: bool, folder: str|None, paths: list[str]}
        以便前端区分「用户取消」和「文件夹里没音频」。"""
        windows = webview.windows
        if not windows:
            return {"cancelled": True, "folder": None, "paths": []}
        result = windows[0].create_file_dialog(
            webview.FOLDER_DIALOG,
            allow_multiple=False,
        )
        if not result:
            return {"cancelled": True, "folder": None, "paths": []}
        folder = Path(result[0])
        exts = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma", ".mp4"}
        files: list[str] = []
        for f in sorted(folder.rglob("*")):
            if f.is_file() and f.suffix.lower() in exts:
                files.append(str(f))
        return {"cancelled": False, "folder": str(folder), "paths": files}

    def open_path(self, path: str) -> dict:
        try:
            target = Path(path).expanduser()
        except (OSError, RuntimeError) as exc:
            return {"ok": False, "error": str(exc)}
        try:
            subprocess.run(["open", str(target)], check=False, timeout=5)
            return {"ok": True}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "error": str(exc)}

    def platform_info(self) -> dict:
        return {"hasNative": True, "platform": "macos"}


def main() -> None:
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    if not _wait_for_port(HOST, PORT):
        raise RuntimeError(f"FastAPI did not start on {HOST}:{PORT}")

    _set_macos_app_icon()

    webview.create_window(
        title="WhisperQwen",
        url=f"http://{HOST}:{PORT}",
        width=1280,
        height=820,
        min_size=(960, 640),
        js_api=JSApi(),
    )
    webview.start()


if __name__ == "__main__":
    main()
