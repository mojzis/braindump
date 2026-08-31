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
from braindump.core.schema import ALL_TYPE_DIRS, SETTLED_STATUSES, Entry


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
    area: str | None = None
    local_dir: str | None = None
    tech_stack: list[str] = field(default_factory=list)


def _non_project_type_dirs() -> list[str]:
    # `project` is still the single-name ownership field for ordinary
    # entries. Initiatives and pitches use numeric links and are exposed via
    # related_work instead of being folded into the legacy project dashboard.
    return [d for d in ALL_TYPE_DIRS if d not in {"projects", "initiatives", "pitches"}]


def _hydrate_from_project_entry(bucket: ProjectStats, entry: Entry) -> None:
    bucket.registered = True
    bucket.entry = entry
    bucket.description = entry.description
    bucket.state = entry.state
    bucket.area = entry.area
    bucket.local_dir = entry.local_dir
    bucket.tech_stack = list(entry.tech_stack or [])


def list_projects(cfg: Config) -> list[ProjectStats]:
    stats: dict[str, ProjectStats] = {}

    for entry in store.read_index(cfg, "projects"):
        bucket = ProjectStats(name=entry.title)
        _hydrate_from_project_entry(bucket, entry)
        stats[entry.title] = bucket

    for type_dir in _non_project_type_dirs():
        for entry in store.read_index(cfg, type_dir):
            name = entry.project or "(none)"
            bucket = stats.setdefault(name, ProjectStats(name=name))
            _accumulate(bucket, entry)

    # Registered projects first, then by recent activity within each group.
    # Two stable sorts because Python's sort is stable and the secondary key
    # uses reverse=True while the primary does not.
    items = list(stats.values())
    items.sort(key=lambda s: s.last_activity or "", reverse=True)
    items.sort(key=lambda s: 0 if s.registered else 1)
    return items


def project_stats(cfg: Config, project: str) -> ProjectStats:
    bucket = ProjectStats(name=project)

    project_entry = find_project_entry(cfg, project)
    if project_entry is not None:
        _hydrate_from_project_entry(bucket, project_entry)

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


def related_work(cfg: Config, project_id: int) -> list[Entry]:
    """Return initiatives and pitches linked to a project ID.

    This intentionally remains separate from project ownership aggregation:
    renaming a project never rewrites numeric links, and stale links simply
    produce no related work after the target is soft-deleted.
    """
    related: list[Entry] = []
    for type_dir in ("initiatives", "pitches"):
        related.extend(
            entry
            for entry in store.read_index(cfg, type_dir)
            if project_id in (entry.project_ids or [])
        )
    related.sort(key=lambda entry: entry.created_at or "", reverse=True)
    return related


def _accumulate(bucket: ProjectStats, entry: Entry) -> None:
    # Defense-in-depth: callers exclude the "projects" type_dir, but guard
    # here too so a project entry can never pollute its own related-item stats.
    if entry.type == "project":
        return
    bucket.entry_count += 1
    bucket.type_counts[entry.type] += 1
    for tag in entry.tags or []:
        bucket.tag_counts[tag] += 1
    if entry.type == "todo":
        if entry.status == "done":
            bucket.done_todos += 1
        elif entry.status not in SETTLED_STATUSES:
            bucket.open_todos += 1
    ts = entry.updated_at or entry.created_at
    if ts and (bucket.last_activity is None or ts > bucket.last_activity):
        bucket.last_activity = ts


__all__ = [
    "ProjectStats",
    "find_project_entry",
    "get_active_project",
    "list_projects",
    "project_stats",
    "related_work",
    "set_active_project",
]
