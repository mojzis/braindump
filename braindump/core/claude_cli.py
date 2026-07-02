"""Thin async wrapper around the `claude` CLI for one-shot structured calls.

This is the only module that shells out to the `claude` binary. Callers pass
a prompt (and optionally a JSON schema) and get back a parsed dict; every
other module in `braindump.core` stays Claude-agnostic and easily testable.

Binary and model are resolved from the environment so the digest engine can
be pointed at a stub in tests: `BRAINDUMP_CLAUDE_BIN` (default `"claude"`)
and `BRAINDUMP_CLAUDE_MODEL` (default `"sonnet"`).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import signal
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 180


class ClaudeError(RuntimeError):
    """Base class for claude_cli failures."""


class ClaudeUnavailableError(ClaudeError):
    """Raised when the `claude` binary cannot be located on PATH."""

    def __init__(self, bin_name: str) -> None:
        super().__init__(
            f"claude CLI not found (looked for {bin_name!r} on PATH). "
            "Install the Claude Code CLI or set BRAINDUMP_CLAUDE_BIN."
        )


class ClaudeCallError(ClaudeError):
    """Raised when a claude invocation fails, times out, or returns unusable output."""

    @classmethod
    def timed_out(cls, timeout: float) -> ClaudeCallError:
        return cls(f"claude call timed out after {timeout}s")

    @classmethod
    def nonzero_exit(cls, returncode: int | None, stderr: bytes) -> ClaudeCallError:
        detail = stderr.decode(errors="replace")[:2000]
        return cls(f"claude exited {returncode}: {detail}")

    @classmethod
    def invalid_stdout(cls, stdout: bytes) -> ClaudeCallError:
        return cls(f"claude returned non-JSON stdout: {stdout[:2000]!r}")

    @classmethod
    def reported_error(cls, detail: object) -> ClaudeCallError:
        return cls(f"claude reported an error: {detail}")

    @classmethod
    def no_payload(cls, envelope: dict[str, Any]) -> ClaudeCallError:
        return cls(f"claude envelope had no usable payload: {envelope}")

    @classmethod
    def invalid_result_json(cls, result: str) -> ClaudeCallError:
        return cls(f"claude result was not valid JSON: {result[:2000]!r}")

    @classmethod
    def invalid_payload_shape(cls, payload: Any) -> ClaudeCallError:
        return cls(f"claude payload was not a JSON object: {payload!r}"[:2000])


_FENCE_RE = re.compile(r"^```[a-zA-Z0-9]*\n(.*?)\n?```$", re.DOTALL)


def strip_fences(text: str) -> str:
    """Strip a single leading/trailing ```-fence (optionally ```json) from text."""
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        return m.group(1).strip()
    return stripped


async def run_claude(
    prompt: str,
    *,
    cwd: str | Path | None = None,
    tools: str = "",
    json_schema: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Run `claude -p <prompt> --output-format json ...` and return the payload.

    Raises `ClaudeUnavailableError` if the binary is missing, or
    `ClaudeCallError` on a non-zero exit, `is_error` result, timeout, or
    unparseable output. Never uses `--bare` (breaks OAuth auth).
    """
    bin_name = os.environ.get("BRAINDUMP_CLAUDE_BIN", "claude")
    model = os.environ.get("BRAINDUMP_CLAUDE_MODEL", "sonnet")

    resolved = shutil.which(bin_name)
    if resolved is None:
        raise ClaudeUnavailableError(bin_name)

    args = [
        resolved,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--tools",
        tools,
        "--model",
        model,
    ]
    if json_schema is not None:
        args += ["--json-schema", json.dumps(json_schema)]

    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        await proc.wait()
        raise ClaudeCallError.timed_out(timeout) from None

    if proc.returncode != 0:
        raise ClaudeCallError.nonzero_exit(proc.returncode, stderr)

    try:
        envelope = json.loads(stdout.decode(errors="replace"))
    except json.JSONDecodeError as e:
        raise ClaudeCallError.invalid_stdout(stdout) from e

    if envelope.get("is_error"):
        detail = envelope.get("result") or envelope
        raise ClaudeCallError.reported_error(detail)

    structured = envelope.get("structured_output")
    if structured is not None:
        if not isinstance(structured, dict):
            raise ClaudeCallError.invalid_payload_shape(structured)
        return structured

    result = envelope.get("result")
    if not isinstance(result, str):
        raise ClaudeCallError.no_payload(envelope)
    try:
        payload = json.loads(strip_fences(result))
    except json.JSONDecodeError as e:
        raise ClaudeCallError.invalid_result_json(result) from e
    if not isinstance(payload, dict):
        raise ClaudeCallError.invalid_payload_shape(payload)
    return payload
