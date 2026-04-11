from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DAY_CUTOFF_HOUR = 4
DEFAULT_PORT = 8765


@dataclass(frozen=True)
class Config:
    home: Path
    day_cutoff_hour: int = DEFAULT_DAY_CUTOFF_HOUR
    port: int = DEFAULT_PORT

    @property
    def state_file(self) -> Path:
        return self.home / ".state.json"

    @property
    def next_id_file(self) -> Path:
        return self.home / ".next_id"

    @property
    def trash_dir(self) -> Path:
        return self.home / ".trash"

    def type_dir(self, type_dir_name: str) -> Path:
        return self.home / type_dir_name

    def index_path(self, type_dir_name: str) -> Path:
        return self.type_dir(type_dir_name) / "index.jsonl"


def load_config() -> Config:
    home = Path(os.environ.get("BRAINDUMP_DIR", Path.home() / "braindump"))
    cutoff = int(os.environ.get("BRAINDUMP_DAY_CUTOFF", DEFAULT_DAY_CUTOFF_HOUR))
    port = int(os.environ.get("BRAINDUMP_PORT", DEFAULT_PORT))
    return Config(home=home, day_cutoff_hour=cutoff, port=port)


def read_state(cfg: Config) -> dict:
    if not cfg.state_file.exists():
        return {}
    try:
        return json.loads(cfg.state_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(cfg: Config, state: dict) -> None:
    cfg.state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg.state_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(cfg.state_file)


def get_active_project(cfg: Config) -> str | None:
    return read_state(cfg).get("active_project")


def set_active_project(cfg: Config, project: str | None) -> None:
    state = read_state(cfg)
    if project is None:
        state.pop("active_project", None)
    else:
        state["active_project"] = project
    write_state(cfg, state)
