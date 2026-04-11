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
    entry: Entry | None = None
    registered: bool = False
    description: str | None = None
    state: str | None = None
    local_dir: str | None = None
    tech_stack: list[str] = field(default_factory=list)


def _non_project_type_dirs() -> list[str]:
    return [d for d in ALL_TYPE_DIRS if d != "projects"]


def list_projects(cfg: Config) -> list[ProjectStats]:
    stats: dict[str, ProjectStats] = {}

    # first pass: seed registered projects from the projects index
    for entry in store.read_index(cfg, "projects"):
        stats[entry.title] = ProjectStats(
            name=entry.title,
            registered=True,
            entry=entry,
            description=entry.description,
            state=entry.state,
            local_dir=entry.local_dir,
            tech_stack=list(entry.tech_stack or []),
        )

    # second pass: accumulate non-project entries, bucket by project field
    for type_dir in _non_project_type_dirs():
        for entry in store.read_index(cfg, type_dir):
            name = entry.project or "(none)"
            bucket = stats.setdefault(name, ProjectStats(name=name, registered=False))
            _accumulate(bucket, entry)

    # sort: registered first, then by -last_activity (newest first; unregistered
    # after). We sort non-registered newest-first inside their own group as well.
    items = list(stats.values())
    # sort newest-first by activity timestamp (ISO 8601 is lexicographically sortable)
    items.sort(key=lambda s: s.last_activity or "", reverse=True)
    # stable sort by registered flag — registered True comes first
    items.sort(key=lambda s: 0 if s.registered else 1)
    return items


def project_stats(cfg: Config, project: str) -> ProjectStats:
    bucket = ProjectStats(name=project)

    # hydrate metadata from the project entry (if any)
    project_entry = find_project_entry(cfg, project)
    if project_entry is not None:
        bucket.registered = True
        bucket.entry = project_entry
        bucket.description = project_entry.description
        bucket.state = project_entry.state
        bucket.local_dir = project_entry.local_dir
        bucket.tech_stack = list(project_entry.tech_stack or [])

    for type_dir in _non_project_type_dirs():
        for entry in store.read_index(cfg, type_dir):
            if (entry.project or "(none)") != project:
                continue
            _accumulate(bucket, entry)
    return bucket


def find_project_entry(cfg: Config, title: str) -> Entry | None:
    """Return the first project entry whose title matches, or None."""
    for entry in store.read_index(cfg, "projects"):
        if entry.title == title:
            return entry
    return None


def _accumulate(bucket: ProjectStats, entry: Entry) -> None:
    # project entries are never counted against themselves — callers already
    # exclude the "projects" type_dir, but keep this as a belt-and-braces guard.
    if entry.type == "project":
        return
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
    "find_project_entry",
    "get_active_project",
    "set_active_project",
]
