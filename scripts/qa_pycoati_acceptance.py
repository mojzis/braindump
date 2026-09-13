"""Black-box checks for the Pycoati acceptance workflow."""

# Intentional: this executable reports visible checks and runs a configured CLI.
# ruff: noqa: S101, S603, T201

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_NAME = "pycoati_acceptance_probe"
LIVE_TEST = "tests/test_probe.py::test_smoke_without_assertion"
HEALTHY_TEST = "tests/test_probe.py::test_has_an_assertion"
CHANGED_TEST = "tests/test_probe.py::test_changed_since_review"
LIVE_REASON = "Smoke contract: the child operation must complete without raising."


def _write_probe(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        """[project]
name = "pycoati-acceptance-probe"
version = "0.0.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
""",
        encoding="utf-8",
    )
    package = root / PROJECT_NAME
    package.mkdir()
    (package / "__init__.py").write_text(
        """from pathlib import Path


def write_marker(path: Path) -> None:
    path.write_text("ok", encoding="utf-8")
""",
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_probe.py").write_text(
        """from pathlib import Path

from pycoati_acceptance_probe import write_marker


def test_smoke_without_assertion(tmp_path: Path) -> None:
    write_marker(tmp_path / "marker")


def test_has_an_assertion() -> None:
    assert True


def test_changed_since_review() -> None:
    Path(".").resolve()
""",
        encoding="utf-8",
    )


def _run_scan(root: Path, *flags: str) -> tuple[dict, str]:
    output = root / "inventory.json"
    command = [
        os.environ.get("PYCOATI_BIN", "pycoati"),
        str(root),
        "--format",
        "json",
        "--output",
        str(output),
        "--python",
        sys.executable,
        "--project-package",
        PROJECT_NAME,
        *flags,
    ]
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"pycoati failed ({completed.returncode}): {completed.stderr}"
        )
    return json.loads(output.read_text(encoding="utf-8")), completed.stderr


def _test_record(inventory: dict, nodeid: str) -> dict:
    return next(
        item for item in inventory["test_functions"] if item["nodeid"] == nodeid
    )


def _assert_runtime(inventory: dict) -> None:
    assert inventory["tool"]["ran_pytest"] is True
    assert inventory["tool"]["ran_coverage"] is True
    assert inventory["suite"]["test_count"] is not None
    assert inventory["suite"]["line_coverage_pct"] is not None


def _assert_stale_states(inventory: dict) -> None:
    stale = {item["status"] for item in inventory["accepted"]["stale"]}
    assert stale == {"unknown_test", "signal_not_active", "content_changed"}


def main() -> int:
    if shutil.which(os.environ.get("PYCOATI_BIN", "pycoati")) is None:
        print("FAIL pycoati executable not found", file=sys.stderr)
        return 1

    try:
        with tempfile.TemporaryDirectory(prefix="pycoati-acceptance-") as name:
            root = Path(name)
            _write_probe(root)

            raw, raw_stderr = _run_scan(root, "--no-accept")
            _assert_runtime(raw)
            assert "WARN" not in raw_stderr.upper()
            raw_live = _test_record(raw, LIVE_TEST)
            raw_changed = _test_record(raw, CHANGED_TEST)
            assert raw_live["assertion_count"] == 0
            assert raw_live["external_verification_count"] == 0
            assert LIVE_TEST in raw["top_suspicious"]["test_functions"]

            fingerprint = raw_live["fingerprint"]
            (root / ".pycoati-accept.toml").write_text(
                f'''schema_version = "1"

[[accept]]
test = "{LIVE_TEST}"
signal = "zero_asserts"
reason = "{LIVE_REASON}"
reviewed = "2026-09-14"
fingerprint = "{fingerprint}"

[[accept]]
test = "{HEALTHY_TEST}"
signal = "zero_asserts"
reason = "Previously reviewed, but the assertion now makes this signal inactive."
reviewed = "2026-09-14"
fingerprint = "{_test_record(raw, HEALTHY_TEST)["fingerprint"]}"

[[accept]]
test = "{CHANGED_TEST}"
signal = "zero_asserts"
reason = "Previously reviewed smoke behavior; source must be re-reviewed after edits."
reviewed = "2026-09-14"
fingerprint = "0000000000000000"

[[accept]]
test = "tests/test_probe.py::test_unknown"
signal = "zero_asserts"
reason = "Historical probe entry used to verify unknown-test staleness."
reviewed = "2026-09-14"
fingerprint = "0000000000000000"
''',
                encoding="utf-8",
            )

            default, default_stderr = _run_scan(root)
            _assert_runtime(default)
            assert "stale acceptance" in default_stderr
            _assert_stale_states(default)
            assert default["accepted"]["findings"] == [
                {
                    "test": LIVE_TEST,
                    "signal": "zero_asserts",
                    "reason": LIVE_REASON,
                    "reviewed": "2026-09-14",
                    "fingerprint": fingerprint,
                }
            ]
            assert LIVE_TEST not in default["top_suspicious"]["test_functions"]
            assert CHANGED_TEST in default["top_suspicious"]["test_functions"]
            default_live = _test_record(default, LIVE_TEST)
            for key, value in raw_live.items():
                if key != "accepted_signals":
                    assert default_live[key] == value
            default_changed = _test_record(default, CHANGED_TEST)
            assert default_changed["assertion_count"] == raw_changed["assertion_count"]

            included, _ = _run_scan(root, "--include-accepted")
            _assert_runtime(included)
            assert included["accepted"]["included_in_shortlist"] is True
            assert LIVE_TEST in included["top_suspicious"]["test_functions"]

            print("PASS runtime pytest and coverage")
            print("PASS accepted reason and unchanged raw evidence")
            print("PASS fingerprint invalidation")
            print("PASS stale states: unknown_test, signal_not_active, content_changed")
            print("PASS active-signal actionability and include-accepted mode")
            print("PASS pycoati acceptance helper")
    except (AssertionError, OSError, json.JSONDecodeError) as error:
        print(f"FAIL pycoati acceptance helper: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
