"""Run the braindump web UI inside a native desktop window via pywebview.

This is a thin convenience wrapper, not a packaged app: it starts the same
FastAPI server the CLI's `serve` command uses (in a background thread) and
points a `pywebview` window at it. No bundling, no installers — just a local
window instead of a browser tab.

`bd app` detaches by default (see `launch_detached`), so the window outlives
the shell it was started from; `run_app` is the attached/foreground path the
detached child re-enters.

One thing the window doesn't inherit from a browser tab is the copy plumbing:
pywebview switches the native context menu off outside debug mode, and its Qt
backend leaves JS clipboard access disabled, so text in the window can't be
gotten out of it. `_enable_clipboard` puts both back (see also
`web/static/clipboard.js`, the in-page half of the same fix).
"""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import uvicorn

from braindump.core.config import load_config

logger = logging.getLogger("braindump.app")

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


#: Editing actions offered in the window's right-click menu. Named rather than
#: imported so the same code works against the Qt5 and Qt6 enum layouts.
_EDIT_ACTIONS = ("Copy", "Cut", "Paste", "SelectAll")

#: Distinguishes "no such enum member" from a member that is falsy (Qt's enums
#: start at 0, so `or` would misread the first one of every enum).
_MISSING = object()


def _qt_enum_member(scope: Any, enum_name: str, member: str) -> Any:
    """Look a Qt enum member up under either binding's layout, else None.

    Qt6 nests members under the enum type (`WebAction.Copy`); Qt5 hangs them off
    the enclosing class (`QWebEnginePage.Copy`) while still exposing a member-less
    `WebAction` type, so the nested lookup has to fall through rather than stop
    at the first name that resolves.
    """
    value = getattr(getattr(scope, enum_name, None), member, _MISSING)
    if value is _MISSING:
        value = getattr(scope, member, _MISSING)
    return None if value is _MISSING else value


def _enable_clipboard_on_show(window: Any) -> None:
    """Register the copy plumbing to be switched on once the window exists.

    `before_show` is the last event pywebview fires from the GUI thread while
    the window is still being built, which is where native widgets may be
    touched from.
    """
    events = getattr(window, "events", None)
    if events is None or getattr(events, "before_show", None) is None:
        # Registration runs inline in `run_app`, so an unfamiliar window shape
        # must not raise: no copy menu still beats no window.
        return  # pragma: no cover - every pywebview window has the event
    events.before_show += _on_before_show


# The parameter *name* is load-bearing: pywebview's Event.set() passes the
# window only to a handler that declares a parameter literally called `window`,
# and calls it with no arguments otherwise (see webview/event.py).
def _on_before_show(window: Any) -> None:
    """Grant copy/paste to the native view; never block the window over it."""
    # Only the Qt backend needs (and exposes) this: its `native` is pywebview's
    # own QMainWindow, carrying the QWebEngineView as `.webview`. Cocoa already
    # ships an Edit menu, and GTK hands us a bare GtkWindow.
    view = getattr(getattr(window, "native", None), "webview", None)
    if view is None:
        return
    try:
        _install_qt_clipboard(view)
    except Exception as exc:
        # A copy menu is not worth a dead window; say so in the log and go on.
        logger.warning("could not enable the copy menu: %s", exc)


def _install_qt_clipboard(view: Any) -> None:
    """Give a QWebEngineView an edit context menu and JS clipboard access."""
    from qtpy import QtCore  # noqa: PLC0415  # optional 'app' extra
    from qtpy.QtWidgets import QMenu  # noqa: PLC0415

    page = view.page()

    # `navigator.clipboard.writeText` — what the in-page copy buttons use — is
    # off by default in QtWebEngine. The matching `JavascriptCanPaste` stays
    # off: nothing in the UI reads the clipboard, and the native ctrl+V (and
    # the Paste entry below) don't go through that setting.
    settings = page.settings()
    attribute = _qt_enum_member(
        type(settings), "WebAttribute", "JavascriptCanAccessClipboard"
    )
    if attribute is None:
        logger.warning(
            "this webview has no JS clipboard setting; copy buttons "
            "will fall back to execCommand"
        )
    else:
        settings.setAttribute(attribute, True)

    actions = [
        page.action(member)
        for member in (
            _qt_enum_member(type(page), "WebAction", name) for name in _EDIT_ACTIONS
        )
        if member is not None
    ]
    if not actions:
        logger.warning("this webview exposes no edit actions; no context menu")
        return

    # One menu for the life of the view: the actions never change, and a fresh
    # QMenu parented to the view would outlive every right-click.
    menu = QMenu(view)
    for action in actions:
        menu.addAction(action)
    popup = getattr(menu, "exec", None) or menu.exec_

    def show_menu(pos: Any) -> None:
        popup(view.mapToGlobal(pos))

    policy = _qt_enum_member(QtCore.Qt, "ContextMenuPolicy", "CustomContextMenu")
    view.setContextMenuPolicy(policy)
    view.customContextMenuRequested.connect(show_menu)


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
        window = webview.create_window(
            "Braindump",
            url,
            width=_WINDOW_WIDTH,
            height=_WINDOW_HEIGHT,
            min_size=_WINDOW_MIN_SIZE,
        )
        _enable_clipboard_on_show(window)
        webview.start(icon=str(_ICON_PATH) if _ICON_PATH.exists() else None)
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
