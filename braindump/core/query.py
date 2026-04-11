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
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Literal

from braindump.core import store
from braindump.core.config import Config
from braindump.core.schema import ALL_TYPE_DIRS, Entry, type_to_dir


StatusFilter = Literal["open", "done", "all"]


@dataclass
class SearchFilters:
    q: str | None = None
    types: list[str] = field(default_factory=list)
    project: str | None = None
    status: StatusFilter = "all"
    tags: list[str] = field(default_factory=list)
    since: date | None = None
    until: date | None = None
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


def _entry_matches_structural(entry: Entry, f: SearchFilters) -> bool:
    if f.project is not None and entry.project != f.project:
        return False
    if f.status == "open":
        if entry.status == "done":
            return False
    elif f.status == "done":
        if entry.status != "done":
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


def search(cfg: Config, f: SearchFilters) -> list[Hit]:
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

    # sort newest first
    hits.sort(key=lambda h: h.entry.created_at or "", reverse=True)

    if f.offset:
        hits = hits[f.offset :]
    if f.limit:
        hits = hits[: f.limit]
    return hits


def _rg_matches(cfg: Config, type_dir: str, words: list[str]) -> list[str]:
    """Return relative file paths in `type_dir` whose markdown body matches every word."""
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

    rels: list[str] = []
    root_str = str(root).rstrip("/") + "/"
    for p in files:
        if p.startswith(root_str):
            rels.append(p[len(root_str) :])
    return rels


def _lookup_by_file_path(cfg: Config, type_dir: str, file_path: str) -> Entry | None:
    for entry in store.read_index(cfg, type_dir):
        if entry.file_path == file_path:
            return entry
    return None


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
