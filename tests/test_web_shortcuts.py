from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def node_executable() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the optional DOM behavior test")
    return node


def test_web_shortcut_dom_behaviors(node_executable: str) -> None:
    js_test = Path(__file__).with_name("web_shortcuts.test.js")

    result = subprocess.run(
        [node_executable, "--test", str(js_test)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
