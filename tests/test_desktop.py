"""Tests for the plumbing behind `bd app`.

Everything here stops short of an actual window: the pywebview module is
stubbed, so no display or native backend is needed.
"""

from __future__ import annotations

import socket
import subprocess
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


class _StubWebview:
    """Stand-in for the pywebview module."""

    def __init__(self):
        self.windows: list[tuple[str, str]] = []
        self.started = False

    def create_window(self, title, url, **kwargs):
        self.windows.append((title, url))

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
