from __future__ import annotations

from pathlib import Path

import pytest

from braindump.core.config import Config
from braindump.core.store import ensure_type_dirs


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    home = tmp_path / "braindump"
    home.mkdir()
    c = Config(home=home, day_cutoff_hour=4)
    ensure_type_dirs(c)
    return c
