from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from braindump.core import claude_cli


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _write_stub(tmp_path: Path, body: str) -> Path:
    """Write an executable python stub standing in for the `claude` binary."""
    path = tmp_path / "claude-stub"
    path.write_text(f"#!/usr/bin/env python3\n{textwrap.dedent(body)}")
    path.chmod(0o755)
    return path


@pytest.mark.anyio
async def test_happy_path_uses_structured_output(tmp_path, monkeypatch):
    stub = _write_stub(
        tmp_path,
        """
        import json
        print(json.dumps({
            "type": "result",
            "is_error": False,
            "result": "{\\"answer\\": 7}",
            "structured_output": {"answer": 7},
        }))
        """,
    )
    monkeypatch.setenv("BRAINDUMP_CLAUDE_BIN", str(stub))

    payload = await claude_cli.run_claude("hello", json_schema={"type": "object"})
    assert payload == {"answer": 7}


@pytest.mark.anyio
async def test_fenced_json_in_result_with_no_structured_output(tmp_path, monkeypatch):
    stub = _write_stub(
        tmp_path,
        '''
        import json
        envelope = {
            "type": "result",
            "is_error": False,
            "result": "```json\\n{\\"answer\\": 9}\\n```",
        }
        print(json.dumps(envelope))
        ''',
    )
    monkeypatch.setenv("BRAINDUMP_CLAUDE_BIN", str(stub))

    payload = await claude_cli.run_claude("hello")
    assert payload == {"answer": 9}


@pytest.mark.anyio
async def test_is_error_raises(tmp_path, monkeypatch):
    stub = _write_stub(
        tmp_path,
        """
        import json
        print(json.dumps({"type": "result", "is_error": True, "result": "boom"}))
        """,
    )
    monkeypatch.setenv("BRAINDUMP_CLAUDE_BIN", str(stub))

    with pytest.raises(claude_cli.ClaudeCallError, match="boom"):
        await claude_cli.run_claude("hello")


@pytest.mark.anyio
async def test_nonzero_exit_raises(tmp_path, monkeypatch):
    stub = _write_stub(
        tmp_path,
        """
        import sys
        print("some stderr noise", file=sys.stderr)
        sys.exit(1)
        """,
    )
    monkeypatch.setenv("BRAINDUMP_CLAUDE_BIN", str(stub))

    with pytest.raises(claude_cli.ClaudeCallError, match="exited 1"):
        await claude_cli.run_claude("hello")


@pytest.mark.anyio
async def test_garbage_stdout_raises(tmp_path, monkeypatch):
    stub = _write_stub(tmp_path, 'print("not json at all")')
    monkeypatch.setenv("BRAINDUMP_CLAUDE_BIN", str(stub))

    with pytest.raises(claude_cli.ClaudeCallError, match="non-JSON"):
        await claude_cli.run_claude("hello")


@pytest.mark.anyio
async def test_missing_binary_raises_unavailable(monkeypatch):
    monkeypatch.setenv("BRAINDUMP_CLAUDE_BIN", "definitely-not-a-real-claude-bin")

    with pytest.raises(claude_cli.ClaudeUnavailableError):
        await claude_cli.run_claude("hello")


@pytest.mark.anyio
async def test_timeout_kills_process_and_raises(tmp_path, monkeypatch):
    stub = _write_stub(
        tmp_path,
        """
        import time
        time.sleep(5)
        print("{}")
        """,
    )
    monkeypatch.setenv("BRAINDUMP_CLAUDE_BIN", str(stub))

    with pytest.raises(claude_cli.ClaudeCallError, match="timed out"):
        await claude_cli.run_claude("hello", timeout=0.2)


def test_strip_fences_plain_json_untouched():
    assert claude_cli.strip_fences('{"a": 1}') == '{"a": 1}'


def test_strip_fences_removes_json_fence():
    assert claude_cli.strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_fences_removes_bare_fence():
    assert claude_cli.strip_fences('```\n{"a": 1}\n```') == '{"a": 1}'
