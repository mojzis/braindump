from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_web_shortcut_dom_behaviors() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the optional DOM behavior test")
    js_test = Path(__file__).with_name("web_shortcuts.test.js")

    result = subprocess.run(
        [node, "--test", str(js_test)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
