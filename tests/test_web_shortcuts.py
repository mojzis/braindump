from __future__ import annotations

import subprocess
from pathlib import Path


def test_web_shortcut_dom_behaviors() -> None:
    js_test = Path(__file__).with_name("web_shortcuts.test.js")

    result = subprocess.run(
        ["node", "--test", str(js_test)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
