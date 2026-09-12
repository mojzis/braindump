from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def node_executable() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    return node


def test_mermaid_renderer_dom_behaviors(node_executable: str) -> None:
    js_test = Path(__file__).with_name("web_mermaid.test.js")
    completed = subprocess.run(
        [node_executable, "--test", str(js_test)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
