"""Low-level data store: JSONL indexes, markdown files, locks, slugs, IDs.

This is the only module in `braindump.core` that touches the filesystem. Every
mutation goes through atomic_write_text or rewrite_index_atomic so we never
leave index files in a half-written state on crash.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shutil
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from braindump.core.config import Config
from braindump.core.schema import ALL_TYPE_DIRS, Entry, type_to_dir


# --- time ------------------------------------------------------------------


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_now() -> datetime:
    return datetime.now().astimezone()


# --- slugs -----------------------------------------------------------------

_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(title: str, max_len: int = 50) -> str:
    """Match the bash slugify: lowercase, [^a-z0-9] -> '-', collapse, trim, cap at 50."""
    s = _slug_re.sub("-", title.lower()).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "entry"


def file_stem(slug: str, when: datetime) -> str:
    return f"{slug}--{when.strftime('%Y-%m-%d-%H%M')}"


def date_path(when: datetime) -> str:
    return when.strftime("%Y/%m")


# --- locks -----------------------------------------------------------------


@contextlib.contextmanager
def _locked(path: Path, mode: str = "a+") -> Iterator[Any]:
    """Open `path` with an exclusive fcntl lock. Ensures parent exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with open(path, mode) as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield f
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# --- IDs -------------------------------------------------------------------


def next_id(cfg: Config) -> int:
    """Atomically read, increment, and persist the shared ID counter."""
    path = cfg.next_id_file
    with _locked(path, mode="r+") as f:
        raw = f.read().strip()
        current = int(raw) if raw else 1
        next_value = current + 1
        f.seek(0)
        f.truncate()
        f.write(f"{next_value}\n")
        f.flush()
        os.fsync(f.fileno())
    return current


# --- atomic text write -----------------------------------------------------


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content)
    tmp.replace(path)


# --- frontmatter -----------------------------------------------------------

# Field order matches the legacy create-entry.sh output so diffs against
# existing files stay minimal. Fields absent from the dict are skipped.
FRONTMATTER_FIELD_ORDER: tuple[str, ...] = (
    "type",
    "title",
    "tags",
    "project",
    "status",
    "priority",
    "subtype",
    "category",
    "source",
    "mood",
    "related_to",
    "prompt_type",
    "model_target",
    "due_date",
    "date",
    "word_count",
    "created_at",
    "updated_at",
)


def render_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    written: set[str] = set()
    for key in FRONTMATTER_FIELD_ORDER:
        if key not in data or data[key] is None:
            continue
        lines.append(_render_fm_line(key, data[key]))
        written.add(key)
    # preserve any extra unknown keys so round-trip doesn't lose data
    for key, value in data.items():
        if key in written or value is None:
            continue
        lines.append(_render_fm_line(key, value))
    lines.append("---")
    return "\n".join(lines)


def _render_fm_line(key: str, value: Any) -> str:
    if isinstance(value, list):
        # JSON-style list: ["a", "b", "c"]
        return f"{key}: {json.dumps(value, ensure_ascii=False)}"
    if isinstance(value, (int, float)):
        return f"{key}: {value}"
    if isinstance(value, bool):
        return f"{key}: {str(value).lower()}"
    # strings: bare unless they contain characters that would break parsing
    s = str(value)
    if "\n" in s or s.startswith('"') or s.startswith("'"):
        return f"{key}: {json.dumps(s, ensure_ascii=False)}"
    return f"{key}: {s}"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split `---`-delimited frontmatter off the top of a markdown file.

    Returns (metadata_dict, body). If there is no frontmatter, returns ({}, text).
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    end = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            end = i
            break
    if end is None:
        return {}, text
    meta: dict[str, Any] = {}
    for line in lines[1:end]:
        if not line.strip() or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()
        meta[key] = _parse_fm_value(raw)
    body = "\n".join(lines[end + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    return meta, body


def _parse_fm_value(raw: str) -> Any:
    if raw == "":
        return ""
    if raw.startswith("[") or raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    if raw.startswith('"') and raw.endswith('"'):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw[1:-1]
    if raw.isdigit():
        return int(raw)
    return raw


# --- markdown files --------------------------------------------------------


def build_markdown(frontmatter: dict[str, Any], title: str, body: str) -> str:
    """Compose a full markdown file body from frontmatter + title + body."""
    fm = render_frontmatter(frontmatter)
    body = body.rstrip("\n")
    return f"{fm}\n\n# {title}\n\n{body}\n"


def read_markdown(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text()
    return parse_frontmatter(text)


def rewrite_markdown(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    """Rewrite a markdown file preserving its current heading and body shape.

    The on-disk body already contains `# Title\n\n...`, so we serialize the new
    frontmatter and glue it onto the body we were handed.
    """
    fm = render_frontmatter(frontmatter)
    body = body.rstrip("\n")
    atomic_write_text(path, f"{fm}\n\n{body}\n")


# --- JSONL indexes ---------------------------------------------------------


def read_index(cfg: Config, type_or_dir: str) -> list[Entry]:
    type_dir = type_to_dir(type_or_dir)
    path = cfg.index_path(type_dir)
    if not path.exists():
        return []
    entries: list[Entry] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            entries.append(Entry.model_validate(data))
    return entries


def iter_all_indexes(cfg: Config) -> Iterator[Entry]:
    for type_dir in ALL_TYPE_DIRS:
        yield from read_index(cfg, type_dir)


def append_index(cfg: Config, type_or_dir: str, entry: Entry) -> None:
    type_dir = type_to_dir(type_or_dir)
    path = cfg.index_path(type_dir)
    line = json.dumps(entry.to_index_json(), ensure_ascii=False)
    with _locked(path, mode="a+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            # ensure we start on a new line even if the last write was truncated
            f.seek(f.tell() - 1)
            if f.read(1) != "\n":
                f.write("\n")
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def rewrite_index_atomic(cfg: Config, type_or_dir: str, entries: list[Entry]) -> None:
    """Atomically replace an index file with the given entries.

    Used for updates and deletes. The index is locked for the duration so
    concurrent appends from another process wait.
    """
    type_dir = type_to_dir(type_or_dir)
    path = cfg.index_path(type_dir)
    with _locked(path, mode="a+"):
        tmp = path.with_name(f".{path.name}.tmp")
        with tmp.open("w") as out:
            for entry in entries:
                out.write(json.dumps(entry.to_index_json(), ensure_ascii=False) + "\n")
            out.flush()
            os.fsync(out.fileno())
        tmp.replace(path)


# --- filesystem helpers ----------------------------------------------------


def ensure_type_dirs(cfg: Config) -> None:
    for t in ALL_TYPE_DIRS:
        (cfg.home / t).mkdir(parents=True, exist_ok=True)
        (cfg.home / t / "index.jsonl").touch(exist_ok=True)


def full_path_for(cfg: Config, type_or_dir: str, rel_file_path: str) -> Path:
    return cfg.type_dir(type_to_dir(type_or_dir)) / rel_file_path


def move_to_trash(cfg: Config, type_or_dir: str, rel_file_path: str) -> Path:
    src = full_path_for(cfg, type_or_dir, rel_file_path)
    dst = cfg.trash_dir / type_to_dir(type_or_dir) / rel_file_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return dst
