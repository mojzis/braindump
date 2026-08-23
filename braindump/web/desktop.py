"""Run the braindump web UI inside a native desktop window via pywebview.

This is a thin convenience wrapper, not a packaged app: it starts the same
FastAPI server the CLI's `serve` command uses (in a background thread) and
points a `pywebview` window at it. No bundling, no installers — just a local
window instead of a browser tab.

`bd app` detaches by default (see `launch_detached`), so the window outlives
the shell it was started from; `run_app` is the attached/foreground path the
detached child re-enters.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import ModuleType

import uvicorn

from braindump.core.config import load_config

#: How long the parent waits after spawning the detached child before it
#: assumes the child came up fine. Long enough to catch import-time blowups
#: (missing extra, no webview backend), short enough not to feel like a hang.
_STARTUP_GRACE = 5.0

#: Default window geometry. The journal editor plus the rendered days below it
#: want a lot of vertical room, so start noticeably larger than pywebview's
#: 800x600 default.
_WINDOW_WIDTH = 1400
_WINDOW_HEIGHT = 950
_WINDOW_MIN_SIZE = (900, 600)

#: Window/taskbar icon. Same brain the web UI uses as its favicon; pywebview
#: wants a raster file path, so we ship the rendered PNG next to the SVG.
_ICON_PATH = Path(__file__).parent / "static" / "brain.png"


class _Server(uvicorn.Server):
    """A uvicorn Server that can be started on a background thread.

    uvicorn installs signal handlers on startup, which only works on the main
    thread; we're running on a worker thread, so we skip that.
    """

    def install_signal_handlers(self) -> None:
        pass


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """True if something is already accepting connections on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _wait_until_ready(host: str, port: int, timeout: float = 20.0) -> bool:
    """Poll the TCP port until the server accepts connections (or we time out)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.1)
    return False


def _import_webview() -> ModuleType:
    try:
        import webview  # noqa: PLC0415  # optional 'app' extra
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "pywebview is not installed. Install the desktop extra:\n"
            "    uv tool install --force --reinstall --no-cache '.[app]'\n"
            "or run `bd serve` and open the URL in your browser instead."
        ) from exc
    return webview


def launch_detached(
    host: str = "127.0.0.1",
    port: int | None = None,
    log_file: Path | None = None,
) -> tuple[int, Path]:
    """Start `bd app --foreground` in its own session; return (pid, log path).

    The child gets a new process group and its stdio redirected to `log_file`,
    so it survives the terminal (and any Ctrl-C in it) that launched it. We
    block for a few seconds afterwards purely to turn a fast crash — a missing
    extra, no webview backend — into an error here instead of silence plus a
    window that never appears.
    """
    cfg = load_config()
    resolved_port = port if port is not None else cfg.port
    log_file = log_file or cfg.home / ".bd-app.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # The port coming up is only evidence the child started if it wasn't
    # already up: `run_app` deliberately attaches to an existing server, so a
    # running `bd serve` would otherwise mask a child that died on spawn.
    port_was_open = _port_open(host, resolved_port, timeout=0.2)
    # Only what this child writes may be quoted back as its crash output.
    log_offset = log_file.stat().st_size if log_file.exists() else 0

    cmd = [sys.executable, "-m", "braindump.cli.main", "app", "--foreground"]
    cmd += ["--host", host]
    if port is not None:
        cmd += ["--port", str(port)]

    with log_file.open("ab") as log:
        proc = subprocess.Popen(  # noqa: S603  # fixed argv, no shell
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    deadline = time.monotonic() + _STARTUP_GRACE
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"bd app exited immediately. Log: {log_file}\n"
                f"{_log_tail(log_file, log_offset)}"
            )
        if not port_was_open and _port_open(host, resolved_port, timeout=0.2):
            break
        time.sleep(0.1)
    return proc.pid, log_file


def _log_tail(log_file: Path, offset: int = 0, lines: int = 15) -> str:
    """Last few lines the child wrote, i.e. everything past `offset`."""
    try:
        with log_file.open("rb") as fh:
            fh.seek(offset)
            written = fh.read().decode(errors="replace")
    except OSError:  # pragma: no cover - unreadable log is not worth failing over
        return ""
    return "\n".join(written.splitlines()[-lines:])


def run_app(host: str = "127.0.0.1", port: int | None = None) -> None:
    """Launch the web UI in a pywebview window, blocking until it's closed.

    If the port is already serving (a `bd serve`, or another `bd app`), we
    attach a window to that server rather than starting — and later killing —
    a second one. The server belongs to whichever process started it, so
    closing *that* window stops it for any window that attached to it.
    """
    webview = _import_webview()

    cfg = load_config()
    resolved_port = port or cfg.port
    url = f"http://{host}:{resolved_port}/"

    server: _Server | None = None
    thread: threading.Thread | None = None

    if not _port_open(host, resolved_port):
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
        webview.create_window(
            "Braindump",
            url,
            width=_WINDOW_WIDTH,
            height=_WINDOW_HEIGHT,
            min_size=_WINDOW_MIN_SIZE,
        )
        webview.start(icon=str(_ICON_PATH) if _ICON_PATH.exists() else None)
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
