"""Tests for the detached-launch plumbing behind `bd app`.

The pywebview window itself needs a display and a native webview backend, so
these cover only the parts that run before one exists.
"""

from __future__ import annotations

import socket
import subprocess

import pytest

from braindump.web import desktop


class _FakeProc:
    def __init__(self, pid: int = 4242, exit_code: int | None = None):
        self.pid = pid
        self._exit_code = exit_code

    def poll(self):
        return self._exit_code


def test_port_open_false_for_dead_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert desktop._port_open("127.0.0.1", port, timeout=0.2) is False


def test_port_open_true_for_listening_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        assert desktop._port_open("127.0.0.1", s.getsockname()[1], timeout=0.5) is True


def test_launch_detached_spawns_foreground_child(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: True)

    log_file = tmp_path / "logs" / "bd-app.log"
    pid = desktop.launch_detached(host="127.0.0.1", port=9911, log_file=log_file)

    assert pid == 4242
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


def test_launch_detached_reports_immediate_crash(monkeypatch, tmp_path):
    log_file = tmp_path / "bd-app.log"
    log_file.write_text("Traceback...\nWebViewException: no backend\n")

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: _FakeProc(exit_code=1))
    monkeypatch.setattr(desktop, "_port_open", lambda *a, **kw: False)

    with pytest.raises(RuntimeError, match="WebViewException"):
        desktop.launch_detached(port=9911, log_file=log_file)
