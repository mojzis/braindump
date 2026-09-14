"""Search and list queries over the braindump indexes.

Two-stage strategy mirroring the legacy search.sh:

1. Metadata scan: look for query words in title / summary / tags. Fast, typed,
   supports structured filters (project, status, tags, date range).
2. Full-text fallback: shell out to ripgrep against markdown bodies to catch
   entries whose metadata doesn't contain the query word. Still respects the
   structural filters we already have in the index.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from braindump.core import store
from braindump.core.config import Config
from braindump.core.schema import (
    ALL_TYPE_DIRS,
    LEGACY_TODO_STATUSES,
    SETTLED_STATUSES,
    TODO_PRESENCES,
    TODO_STATUSES,
    Entry,
    type_to_dir,
)

StatusFilter = Literal[
    "open",
    "done",
    "settled",
    "all",
    "pending",
    "in-progress",
    "in-qa",
    "cancelled",
    "postponed",
    "active",
]
PresenceFilter = Literal[
    "agent", "together", "personal", "unclassified", "needs-my-time"
]
SortField = Literal["date", "priority"]
SortDirection = Literal["asc", "desc"]

_SORT_FIELDS = ("date", "priority")
_SORT_DIRECTIONS = ("asc", "desc")
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_MISSING_PRIORITY_RANK = len(_PRIORITY_ORDER)
_LOW_PRIORITY_RANK = _MISSING_PRIORITY_RANK - 1


@dataclass
class SearchFilters:
    q: str | None = None
    types: list[str] = field(default_factory=list)
    project: str | None = None
    project_id: int | None = None
    initiative_id: int | None = None
    pitch_id: int | None = None
    priority: str | None = None
    presence: PresenceFilter | None = None
    coverage: str | None = None
    related_id: int | None = None
    related_type: str | None = None
    branch: str | None = None
    status: StatusFilter = "all"
    tags: list[str] = field(default_factory=list)
    since: date | None = None
    until: date | None = None
    sort: SortField = "date"
    direction: SortDirection = "desc"
    limit: int = 50
    offset: int = 0
    fulltext: bool = True


def _normalize_types(types: Iterable[str]) -> list[str]:
    return [type_to_dir(t) for t in types] if types else list(ALL_TYPE_DIRS)


def _created_date(entry: Entry) -> date | None:
    if not entry.created_at:
        return None
    try:
        return date.fromisoformat(entry.created_at[:10])
    except ValueError:
        return None


def _entry_matches_structural(  # noqa: PLR0911 -- each structural filter is explicit
    entry: Entry, f: SearchFilters
) -> bool:
    if not _entry_matches_relations(entry, f) or not _entry_matches_status(entry, f):
        return False
    if f.priority is not None and entry.priority != f.priority:
        return False
    if not _entry_matches_presence(entry, f.presence):
        return False
    if not _entry_matches_coverage(entry, f.coverage):
        return False
    if f.tags:
        entry_tags = set(entry.tags or [])
        if not all(t in entry_tags for t in f.tags):
            return False
    if f.since or f.until:
        d = _created_date(entry)
        if d is None:
            return False
        if f.since and d < f.since:
            return False
        if f.until and d > f.until:
            return False
    return True


def _entry_matches_coverage(entry: Entry, coverage: str | None) -> bool:
    if coverage is None:
        return True
    if coverage == "unaudited":
        return entry.type == "pitch" and entry.coverage is None
    return entry.coverage == coverage


def _entry_matches_presence(entry: Entry, presence: str | None) -> bool:
    if presence is None:
        return True
    if entry.type != "todo":
        return False
    if presence == "unclassified":
        return entry.presence is None
    if presence == "needs-my-time":
        return entry.presence in {"together", "personal"}
    return entry.presence == presence


def _validate_presence(presence: str | None) -> None:
    if presence is None:
        return
    allowed = (*TODO_PRESENCES, "unclassified", "needs-my-time")
    if presence not in allowed:
        raise ValueError(f"presence must be one of {list(allowed)}")


def _entry_matches_relations(entry: Entry, f: SearchFilters) -> bool:
    if f.branch is not None and entry.branch != f.branch:
        return False
    if f.project is not None and entry.project != f.project:
        return False
    if f.project_id is not None and f.project_id not in (entry.project_ids or []):
        return False
    if (
        f.initiative_id is not None
        and entry.initiative_id != f.initiative_id
        and f.initiative_id not in (entry.initiative_ids or [])
    ):
        return False
    if f.pitch_id is not None and entry.pitch_id != f.pitch_id:
        return False
    return f.related_id is None or _has_relation(entry, f.related_type, f.related_id)


def _entry_matches_status(entry: Entry, f: SearchFilters) -> bool:
    if f.status == "open":
        return entry.status not in SETTLED_STATUSES
    if f.status == "done":
        return entry.status == "done"
    if f.status == "settled":
        return entry.status in SETTLED_STATUSES
    if f.status in (*TODO_STATUSES, *LEGACY_TODO_STATUSES, "active"):
        return entry.status == f.status
    return True


def _has_relation(entry: Entry, relation_type: str | None, relation_id: int) -> bool:
    """Match a typed graph relation without dereferencing its target."""
    if relation_type == "project":
        return relation_id in (entry.project_ids or [])
    if relation_type == "initiative":
        return relation_id == entry.initiative_id or relation_id in (
            entry.initiative_ids or []
        )
    if relation_type == "pitch":
        return relation_id == entry.pitch_id
    # A generic relation filter is useful to callers that already know the
    # entry shape; no type means any canonical relation.
    return any(
        relation_id in values
        for values in (
            [entry.initiative_id] if entry.initiative_id is not None else [],
            [entry.pitch_id] if entry.pitch_id is not None else [],
            entry.project_ids or [],
            entry.initiative_ids or [],
        )
    )


def _words(q: str) -> list[str]:
    return [w for w in re.split(r"\s+", q.strip()) if w]


def _entry_matches_keywords(entry: Entry, words: list[str]) -> bool:
    if not words:
        return True
    haystacks = [
        entry.title or "",
        entry.summary or "",
        " ".join(entry.tags or []),
    ]
    blob = "\n".join(haystacks).lower()
    return all(w.lower() in blob for w in words)


@dataclass
class Hit:
    entry: Entry
    source: Literal["index", "fulltext"] = "index"
    type_dir: str = ""


def _validate_sort(f: SearchFilters) -> None:
    if f.sort not in _SORT_FIELDS:
        raise ValueError(f"sort must be one of {list(_SORT_FIELDS)}")
    if f.direction not in _SORT_DIRECTIONS:
        raise ValueError(f"direction must be one of {list(_SORT_DIRECTIONS)}")


def _priority_sort_key(hit: Hit, direction: SortDirection) -> tuple[bool, int]:
    rank = _PRIORITY_ORDER.get(hit.entry.priority or "", _MISSING_PRIORITY_RANK)
    if direction == "desc" and rank < _MISSING_PRIORITY_RANK:
        rank = _LOW_PRIORITY_RANK - rank
    return rank == _MISSING_PRIORITY_RANK, rank


def _sort_hits(hits: list[Hit], f: SearchFilters) -> None:
    """Sort in place, keeping missing/legacy priorities after canonical ones."""
    hits.sort(key=lambda h: h.entry.created_at or "", reverse=True)
    if f.sort == "date":
        if f.direction == "asc":
            hits.reverse()
        return
    hits.sort(key=lambda hit: _priority_sort_key(hit, f.direction))


def search(cfg: Config, f: SearchFilters) -> list[Hit]:
    _validate_sort(f)
    _validate_presence(f.presence)

    words = _words(f.q or "")
    type_dirs = _normalize_types(f.types)

    hits: list[Hit] = []
    seen_paths: set[tuple[str, str]] = set()

    # stage 1: index scan
    for type_dir in type_dirs:
        for entry in store.read_index(cfg, type_dir):
            if not _entry_matches_structural(entry, f):
                continue
            if words and not _entry_matches_keywords(entry, words):
                continue
            hits.append(Hit(entry=entry, source="index", type_dir=type_dir))
            seen_paths.add((type_dir, entry.file_path))

    # stage 2: full-text fallback (only if we have a query and rg is available)
    if f.fulltext and words and shutil.which("rg"):
        for type_dir in type_dirs:
            for fp in _rg_matches(cfg, type_dir, words):
                key = (type_dir, fp)
                if key in seen_paths:
                    continue
                found = _lookup_by_file_path(cfg, type_dir, fp)
                if found is None:
                    continue
                if not _entry_matches_structural(found, f):
                    continue
                hits.append(Hit(entry=found, source="fulltext", type_dir=type_dir))
                seen_paths.add(key)

    _sort_hits(hits, f)

    if f.offset:
        hits = hits[f.offset :]
    if f.limit:
        hits = hits[: f.limit]
    return hits


def _rg_matches(cfg: Config, type_dir: str, words: list[str]) -> list[str]:
    """Relative paths in `type_dir` whose markdown body matches every word."""
    root = cfg.type_dir(type_dir)
    if not root.exists():
        return []

    first, *rest = words
    try:
        result = subprocess.run(
            ["rg", "-l", "-i", "-g", "*.md", first, str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    files = [p for p in result.stdout.splitlines() if p]
    for word in rest:
        if not files:
            return []
        try:
            filtered = subprocess.run(
                ["rg", "-l", "-i", word, *files],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return []
        files = [p for p in filtered.stdout.splitlines() if p]

    root_str = str(root).rstrip("/") + "/"
    return [p[len(root_str) :] for p in files if p.startswith(root_str)]


def _lookup_by_file_path(cfg: Config, type_dir: str, file_path: str) -> Entry | None:
    for entry in store.read_index(cfg, type_dir):
        if entry.file_path == file_path:
            return entry
    return None


def related_entries(
    cfg: Config,
    relation_type: str,
    relation_id: int,
    *,
    types: Iterable[str] = (),
) -> list[Hit]:
    """List entries carrying a typed relation, including links to missing IDs."""
    type_dirs = _normalize_types(types)
    hits: list[Hit] = []
    for type_dir in type_dirs:
        hits.extend(
            Hit(entry=entry, source="index", type_dir=type_dir)
            for entry in store.read_index(cfg, type_dir)
            if _has_relation(entry, relation_type, relation_id)
        )
    hits.sort(key=lambda h: h.entry.created_at or "", reverse=True)
    return hits


# --- listings --------------------------------------------------------------


def list_recent(
    cfg: Config,
    *,
    types: Iterable[str] = (),
    project: str | None = None,
    limit: int = 10,
) -> list[Hit]:
    return search(
        cfg,
        SearchFilters(
            types=list(types),
            project=project,
            status="all",
            limit=limit,
            fulltext=False,
        ),
    )
