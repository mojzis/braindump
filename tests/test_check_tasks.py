"""Mandatory parallel checks must fail the aggregate gate."""

from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path

import pytest

CHECK_TOOLS = ("ruff", "ty", "vulture", "biston", "deptry", "uvx")


@pytest.fixture
def fake_check_tools(tmp_path):
    for name in CHECK_TOOLS:
        command = tmp_path / name
        command.write_text(
            "#!/bin/bash\n"
            'printf "%s\\n" "${0##*/}"\n'
            'test "${0##*/}" != "$FAILING_CHECK"\n'
        )
        command.chmod(0o755)
    return tmp_path


@pytest.mark.parametrize(
    ("failing_check", "expected_status"),
    [(name, 1) for name in CHECK_TOOLS[:-1]] + [("uvx", 0), ("none", 0)],
)
def test_parallel_gate_collects_every_child_status(
    fake_check_tools, failing_check, expected_status
):
    tasks_path = Path(__file__).parents[1] / "poe_tasks.toml"
    tasks = tomllib.loads(tasks_path.read_text())
    script = tasks["tool"]["poe"]["tasks"]["_check-parallel"]["shell"]

    completed = subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "PATH": f"{fake_check_tools}:{os.defpath}",
            "FAILING_CHECK": failing_check,
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == expected_status, completed.stderr
    assert set(completed.stdout.splitlines()) == set(CHECK_TOOLS)
