from __future__ import annotations

import os
from pathlib import Path

import pytest

# Typer forces a Rich "terminal" (ANSI styling) whenever GITHUB_ACTIONS,
# FORCE_COLOR or PY_COLORS is set, so on CI `--help` output captured by
# CliRunner is full of escape codes: `--coverage` renders as `-` + `-coverage`
# in separate styled spans and plain-text assertions fail. Typer reads this at
# import of typer.rich_utils, so it must be set before any CLI module loads.
os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"

from braindump.core.config import Config
from braindump.core.store import ensure_type_dirs


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    home = tmp_path / "braindump"
    home.mkdir()
    c = Config(home=home, day_cutoff_hour=4)
    ensure_type_dirs(c)
    return c
