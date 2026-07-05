"""Run the braindump web UI inside a native desktop window via pywebview.

This is a thin convenience wrapper, not a packaged app: it starts the same
FastAPI server the CLI's `serve` command uses (in a background thread) and
points a `pywebview` window at it. No bundling, no installers — just a local
window instead of a browser tab.
"""

from __future__ import annotations

import socket
import threading
import time

import uvicorn

from braindump.core.config import load_config


class _Server(uvicorn.Server):
    """A uvicorn Server that can be started on a background thread.

    uvicorn installs signal handlers on startup, which only works on the main
    thread; we're running on a worker thread, so we skip that.
    """

    def install_signal_handlers(self) -> None:
        pass


def _wait_until_ready(host: str, port: int, timeout: float = 20.0) -> bool:
    """Poll the TCP port until the server accepts connections (or we time out)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def run_app(host: str = "127.0.0.1", port: int | None = None) -> None:
    """Launch the web UI in a pywebview window.

    Blocks until the window is closed, then shuts the server down.
    """
    try:
        import webview  # ty: ignore[unresolved-import]  # optional 'app' extra
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "pywebview is not installed. Install the desktop extra:\n"
            "    uv tool install 'braindump[app]'\n"
            "or run `bd serve` and open the URL in your browser instead."
        ) from exc

    cfg = load_config()
    resolved_port = port or cfg.port

    uvicorn_config = uvicorn.Config(
        "braindump.web.app:app",
        host=host,
        port=resolved_port,
        log_level="warning",
    )
    server = _Server(uvicorn_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    if not _wait_until_ready(host, resolved_port):
        server.should_exit = True
        raise RuntimeError(f"Web server did not start on {host}:{resolved_port}")

    try:
        webview.create_window("Braindump", f"http://{host}:{resolved_port}/")
        webview.start()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
