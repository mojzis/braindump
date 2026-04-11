"""Project inventory and dashboards."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from braindump.core import store
from braindump.core.config import (
    Config,
    get_active_project,
    set_active_project,
)
from braindump.core.schema import ALL_TYPE_DIRS, Entry


@dataclass
class ProjectStats:
    name: str
    entry_count: int = 0
    open_todos: int = 0
    done_todos: int = 0
    last_activity: str | None = None
    type_counts: Counter[str] = field(default_factory=Counter)
    tag_counts: Counter[str] = field(default_factory=Counter)


def list_projects(cfg: Config) -> list[ProjectStats]:
    stats: dict[str, ProjectStats] = {}
    for type_dir in ALL_TYPE_DIRS:
        for entry in store.read_index(cfg, type_dir):
            name = entry.project or "(none)"
            bucket = stats.setdefault(name, ProjectStats(name=name))
            _accumulate(bucket, entry)
    return sorted(
        stats.values(),
        key=lambda s: (s.last_activity or ""),
        reverse=True,
    )


def project_stats(cfg: Config, project: str) -> ProjectStats:
    bucket = ProjectStats(name=project)
    for type_dir in ALL_TYPE_DIRS:
        for entry in store.read_index(cfg, type_dir):
            if (entry.project or "(none)") != project:
                continue
            _accumulate(bucket, entry)
    return bucket


def _accumulate(bucket: ProjectStats, entry: Entry) -> None:
    bucket.entry_count += 1
    bucket.type_counts[entry.type] += 1
    for tag in entry.tags or []:
        bucket.tag_counts[tag] += 1
    if entry.type == "todo":
        if entry.status == "done":
            bucket.done_todos += 1
        else:
            bucket.open_todos += 1
    ts = entry.updated_at or entry.created_at
    if ts and (bucket.last_activity is None or ts > bucket.last_activity):
        bucket.last_activity = ts


__all__ = [
    "ProjectStats",
    "list_projects",
    "project_stats",
    "get_active_project",
    "set_active_project",
]
