"""Tests for the plumbing behind `bd app`.

Everything here stops short of an actual window: the pywebview module is
stubbed, so no display or native backend is needed.
"""

from __future__ import annotations

import inspect
import socket
import subprocess
import sys
import types
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from braindump.cli.main import app as cli_app
from braindump.web import desktop

runner = CliRunner()

#: Nothing binds port 1, so probing it is a deterministic "closed" — unlike an
#: ephemeral port we bound and released, which another process can claim.
CLOSED_PORT = 1


class _FakeProc:
    def __init__(self, pid: int = 4242, exit_code: int | None = None):
        self.pid = pid
        self._exit_code = exit_code

    def poll(self):
        return self._exit_code


class _StubEvent:
    """Stand-in for pywebview's Event, which registers handlers with `+=`."""

    def __init__(self):
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _StubWindow:
    def __init__(self):
        self.events = types.SimpleNamespace(before_show=_StubEvent())


class _StubWebview:
    """Stand-in for the pywebview module."""

    def __init__(self):
        self.windows: list[tuple[str, str]] = []
        self.window_kwargs: dict = {}
        self.window = _StubWindow()
        self.started = False

    def create_window(self, title, url, **kwargs):
        self.windows.append((title, url))
        self.window_kwargs = kwargs
        return self.window

    def start(self, **kwargs):
        self.started = True


class _FakeServer:
    """Stand-in for the uvicorn server `run_app` starts on a thread."""

    instances: ClassVar[list[_FakeServer]] = []

    def __init__(self, config):
        self.should_exit = False
        self.instances.append(self)

    def run(self):
        pass


def _stub_popen(monkeypatch, proc, captured=None, writes: bytes = b""):
    def fake_popen(cmd, **kwargs):
        if captured is not None:
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
        if writes:
            kwargs["stdout"].write(writes)
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)


# --- port probing ----------------------------------------------------------


def test_port_open_false_for_dead_port():
    assert desktop._port_open("127.0.0.1", CLOSED_PORT, timeout=0.2) is False


def test_port_open_true_for_listening_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        assert desktop._port_open("127.0.0.1", s.getsockname()[1], timeout=0.5) is True


# --- launch_detached -------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_startup_wait(monkeypatch):
    """Nothing here is really starting up; don't sit out the grace period."""
    monkeypatch.setattr(desktop, "_STARTUP_GRACE", 0.2)


def test_launch_detached_spawns_foreground_child(monkeypatch, tmp_path):
    captured = {}
    _stub_popen(monkeypatch, _FakeProc(), captured)
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: False)

    log_file = tmp_path / "logs" / "bd-app.log"
    pid, used_log = desktop.launch_detached(
        host="127.0.0.1", port=9911, log_file=log_file
    )

    assert (pid, used_log) == (4242, log_file)
    assert captured["cmd"][1:] == [
        "-m",
        "braindump.cli.main",
        "app",
        "--foreground",
        "--host",
        "127.0.0.1",
        "--port",
        "9911",
    ]
    assert captured["kwargs"]["start_new_session"] is True
    assert log_file.exists()


def test_launch_detached_surfaces_the_childs_own_crash_output(monkeypatch, tmp_path):
    log_file = tmp_path / "bd-app.log"
    _stub_popen(
        monkeypatch,
        _FakeProc(exit_code=1),
        writes=b"WebViewException: no backend\n",
    )
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: False)

    with pytest.raises(RuntimeError, match="exited immediately") as exc:
        desktop.launch_detached(port=9911, log_file=log_file)

    assert str(log_file) in str(exc.value)
    assert "WebViewException: no backend" in str(exc.value)


def test_launch_detached_ignores_a_previous_runs_log(monkeypatch, tmp_path):
    """Stale output must not be quoted back as this child's crash."""
    log_file = tmp_path / "bd-app.log"
    log_file.write_text("Traceback from the run before this one\n")
    _stub_popen(monkeypatch, _FakeProc(exit_code=1))
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: False)

    with pytest.raises(RuntimeError, match="exited immediately") as exc:
        desktop.launch_detached(port=9911, log_file=log_file)

    assert "the run before this one" not in str(exc.value)


def test_launch_detached_still_detects_a_crash_behind_a_running_server(
    monkeypatch, tmp_path
):
    """An already-open port is not evidence that *our* child came up."""
    _stub_popen(monkeypatch, _FakeProc(exit_code=1), writes=b"boom\n")
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: True)

    with pytest.raises(RuntimeError, match="exited immediately"):
        desktop.launch_detached(port=9911, log_file=tmp_path / "bd-app.log")


# --- run_app ---------------------------------------------------------------


def test_run_app_attaches_to_an_already_running_server(monkeypatch):
    stub = _StubWebview()
    monkeypatch.setattr(desktop, "_import_webview", lambda: stub)
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: True)

    def no_server(*a, **kw):
        raise AssertionError("started a second server instead of attaching")

    monkeypatch.setattr(desktop, "_Server", no_server)

    desktop.run_app(host="127.0.0.1", port=9911)

    assert stub.windows == [("Braindump", "http://127.0.0.1:9911/")]
    assert stub.started


def test_run_app_starts_a_server_when_the_port_is_free(monkeypatch):
    stub = _StubWebview()
    started: list[_FakeServer] = []
    monkeypatch.setattr(_FakeServer, "instances", started)

    monkeypatch.setattr(desktop, "_import_webview", lambda: stub)
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: False)
    monkeypatch.setattr(desktop, "_Server", _FakeServer)
    monkeypatch.setattr(desktop, "_wait_until_ready", lambda *a, **kw: True)

    desktop.run_app(host="127.0.0.1", port=9911)

    assert len(started) == 1
    assert started[0].should_exit is True  # torn down with the window


# --- the CLI command -------------------------------------------------------


def test_bd_app_detaches_by_default(monkeypatch, tmp_path):
    log_file = tmp_path / "bd-app.log"
    monkeypatch.setattr(
        desktop, "launch_detached", lambda **kwargs: (4242, log_file), raising=True
    )
    monkeypatch.setattr(
        desktop,
        "run_app",
        lambda **kwargs: pytest.fail("ran attached without --foreground"),
    )

    res = runner.invoke(cli_app, ["app"])
    assert res.exit_code == 0
    assert "pid 4242" in res.output
    assert str(log_file) in res.output


def test_bd_app_foreground_flag_runs_attached(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(desktop, "run_app", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        desktop,
        "launch_detached",
        lambda **kwargs: pytest.fail("detached despite --foreground"),
    )

    res = runner.invoke(cli_app, ["app", "-f", "--port", "9911"])
    assert res.exit_code == 0
    assert calls == [{"host": "127.0.0.1", "port": 9911}]


def test_bd_app_reports_a_failed_launch(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("bd app exited immediately. Log: /tmp/x")

    monkeypatch.setattr(desktop, "launch_detached", boom)

    res = runner.invoke(cli_app, ["app"])
    assert res.exit_code == 1
    assert "exited immediately" in res.output


# --- the macOS app name ----------------------------------------------------


class _FakeBundle:
    """Stand-in for NSBundle.mainBundle() and its info dictionaries."""

    def __init__(self, info: dict | None = None, localized: dict | None = None):
        self.info = {} if info is None else info
        self.localized = localized

    def infoDictionary(self):
        return self.info

    def localizedInfoDictionary(self):
        return self.localized


def _stub_foundation(monkeypatch, bundle):
    foundation = types.SimpleNamespace(
        NSBundle=types.SimpleNamespace(mainBundle=lambda: bundle)
    )
    monkeypatch.setitem(sys.modules, "Foundation", foundation)


def test_brand_macos_app_renames_the_bundle(monkeypatch):
    """Otherwise macOS names the window after the interpreter."""
    bundle = _FakeBundle(
        info={"CFBundleName": "Python", "CFBundleDisplayName": "Python 3.14"}
    )
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    _stub_foundation(monkeypatch, bundle)

    desktop._brand_macos_app()

    # The menu bar reads CFBundleName, the app switcher CFBundleDisplayName.
    assert bundle.info["CFBundleName"] == "Braindump"
    assert bundle.info["CFBundleDisplayName"] == "Braindump"


def test_brand_macos_app_prefers_the_localized_dictionary(monkeypatch):
    """macOS (and pywebview) read the localized one when there is one."""
    bundle = _FakeBundle(
        info={"CFBundleName": "Python"}, localized={"CFBundleName": "Python"}
    )
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    _stub_foundation(monkeypatch, bundle)

    desktop._brand_macos_app()

    assert bundle.localized["CFBundleName"] == "Braindump"
    assert bundle.info["CFBundleName"] == "Python"


def test_brand_macos_app_does_nothing_off_darwin(monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "linux")
    monkeypatch.setitem(
        sys.modules,
        "Foundation",
        types.SimpleNamespace(
            NSBundle=types.SimpleNamespace(
                mainBundle=lambda: pytest.fail("touched AppKit off macOS")
            )
        ),
    )

    desktop._brand_macos_app()


def test_brand_macos_app_survives_an_unusable_bundle(monkeypatch, caplog):
    """A window called "Python" beats no window at all."""

    def boom():
        raise RuntimeError("no main bundle")

    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setitem(
        sys.modules,
        "Foundation",
        types.SimpleNamespace(NSBundle=types.SimpleNamespace(mainBundle=boom)),
    )

    desktop._brand_macos_app()

    assert "could not set the macOS app name" in caplog.text


def test_run_app_brands_before_pywebview_is_imported(monkeypatch):
    """Cocoa registers the process (and takes its name) at backend import."""
    order: list[str] = []
    stub = _StubWebview()

    monkeypatch.setattr(desktop, "_brand_macos_app", lambda: order.append("brand"))
    monkeypatch.setattr(
        desktop, "_import_webview", lambda: (order.append("import"), stub)[1]
    )
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: True)

    desktop.run_app(host="127.0.0.1", port=9911)

    assert order == ["brand", "import"]


# --- clipboard plumbing ----------------------------------------------------


class _FakeSettings:
    """Qt6 layout: enum members live on a nested type."""

    class WebAttribute:
        JavascriptCanAccessClipboard = "clipboard"

    def __init__(self):
        self.attributes: dict = {}

    def setAttribute(self, attribute, value):
        self.attributes[attribute] = value


class _FakePage:
    class WebAction:
        Copy = "copy"
        Cut = "cut"
        Paste = "paste"
        SelectAll = "select-all"

    settings_class: ClassVar[type] = _FakeSettings

    def __init__(self):
        self._settings = self.settings_class()

    def settings(self):
        return self._settings

    def action(self, member):
        return f"action:{member}"


class _FakeQt5Settings(_FakeSettings):
    """Qt5 layout: the nested type exists but carries no members."""

    class WebAttribute:
        pass

    JavascriptCanAccessClipboard = "clipboard"


class _FakeQt5Page(_FakePage):
    class WebAction:
        pass

    Copy = "copy"
    Cut = "cut"
    Paste = "paste"
    SelectAll = "select-all"

    settings_class: ClassVar[type] = _FakeQt5Settings


class _FakeSignal:
    def __init__(self):
        self.slots: list = []

    def connect(self, slot):
        self.slots.append(slot)


class _FakeView:
    def __init__(self, page=None):
        self._page = page or _FakePage()
        self.customContextMenuRequested = _FakeSignal()
        self.policy = None

    def page(self):
        return self._page

    def setContextMenuPolicy(self, policy):
        self.policy = policy

    def mapToGlobal(self, pos):
        return ("global", pos)


class _FakeMenu:
    last: ClassVar[_FakeMenu | None] = None

    def __init__(self, parent):
        self.parent = parent
        self.actions: list = []
        self.shown_at = None
        _FakeMenu.last = self

    def addAction(self, action):
        self.actions.append(action)

    def exec(self, pos):
        self.shown_at = pos


@pytest.fixture
def qtpy_stub(monkeypatch):
    """Put a minimal fake qtpy on sys.modules; the real one needs a Qt build."""
    _FakeMenu.last = None  # never let one test's menu answer for another's
    widgets = types.SimpleNamespace(QMenu=_FakeMenu)
    qtpy = types.SimpleNamespace(
        QtWidgets=widgets,
        QtCore=types.SimpleNamespace(
            Qt=types.SimpleNamespace(
                ContextMenuPolicy=types.SimpleNamespace(CustomContextMenu="custom")
            )
        ),
    )
    monkeypatch.setitem(sys.modules, "qtpy", qtpy)
    monkeypatch.setitem(sys.modules, "qtpy.QtWidgets", widgets)


def test_run_app_asks_for_a_selectable_window(monkeypatch):
    """Without this pywebview injects `user-select: none` into every page."""
    stub = _StubWebview()
    monkeypatch.setattr(desktop, "_import_webview", lambda: stub)
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: True)

    desktop.run_app(host="127.0.0.1", port=9911)

    assert stub.window_kwargs["text_select"] is True


def test_run_app_registers_the_clipboard_hook(monkeypatch):
    stub = _StubWebview()
    monkeypatch.setattr(desktop, "_import_webview", lambda: stub)
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: True)

    desktop.run_app(host="127.0.0.1", port=9911)

    assert stub.window.events.before_show.handlers == [desktop._on_before_show]
    # pywebview hands the window only to a parameter with this exact name, and
    # calls the handler with no arguments otherwise (webview/event.py).
    assert "window" in inspect.signature(desktop._on_before_show).parameters


@pytest.mark.parametrize("page_class", [_FakePage, _FakeQt5Page], ids=["qt6", "qt5"])
def test_install_qt_clipboard_wires_an_edit_menu(qtpy_stub, page_class):
    view = _FakeView(page=page_class())

    desktop._install_qt_clipboard(view)

    assert view.page().settings().attributes == {"clipboard": True}
    assert view.policy == "custom"
    assert len(view.customContextMenuRequested.slots) == 1

    view.customContextMenuRequested.slots[0]((3, 4))
    menu = _FakeMenu.last
    assert menu is not None
    assert menu.actions == [
        "action:copy",
        "action:cut",
        "action:paste",
        "action:select-all",
    ]
    assert menu.shown_at == ("global", (3, 4))


def test_before_show_ignores_backends_without_a_qt_view(monkeypatch):
    """Cocoa and GTK hand us a native window with no `.webview` — and no need."""
    wired: list = []
    monkeypatch.setattr(desktop, "_install_qt_clipboard", wired.append)

    desktop._on_before_show(types.SimpleNamespace(native=object()))
    assert wired == []

    view = _FakeView()
    desktop._on_before_show(
        types.SimpleNamespace(native=types.SimpleNamespace(webview=view))
    )
    assert wired == [view]


def test_before_show_survives_a_backend_it_cannot_wire(monkeypatch, caplog):
    def boom(view):
        raise RuntimeError("no such attribute")

    monkeypatch.setattr(desktop, "_install_qt_clipboard", boom)

    native = types.SimpleNamespace(webview=_FakeView())
    desktop._on_before_show(types.SimpleNamespace(native=native))

    assert "could not enable the copy menu" in caplog.text
    assert "no such attribute" in caplog.text  # the warning has to name the cause
