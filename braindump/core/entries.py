"""Create, read, update, delete braindump entries.

All mutations go through here; callers should never touch JSONL or markdown
files directly. This is the module the CLI and web server both import.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from braindump.core import store
from braindump.core.config import Config
from braindump.core.schema import (
    ALL_TYPE_DIRS,
    Entry,
    TYPE_TO_DIR,
    dir_to_type,
    type_to_dir,
)


# --- details block ---------------------------------------------------------

_DETAILS_RE = re.compile(
    r"(?ms)^\s*---\s*\n\s*<details>\s*\n\s*<summary>Original input</summary>.*?</details>\s*$"
)


def wrap_with_original(body: str, original_input: str | None) -> str:
    """Append the standard `<details>` block with the original input."""
    body = body.rstrip("\n")
    if not original_input:
        return body + "\n"
    return (
        f"{body}\n\n---\n\n"
        f"<details>\n<summary>Original input</summary>\n\n"
        f"{original_input.rstrip()}\n\n"
        f"</details>\n"
    )


def split_body(text: str) -> tuple[str, str, str]:
    """Split a markdown body into (heading_line, authored_body, details_block).

    heading_line is the first '# Title' line (or empty). authored_body is the
    content between the heading and the details block. details_block is the
    tail starting with '---\\n<details>...' or ''.
    """
    m = _DETAILS_RE.search(text)
    details = ""
    main = text
    if m:
        details = text[m.start() :]
        main = text[: m.start()]
    # peel off leading title
    lines = main.splitlines()
    heading = ""
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i < len(lines) and lines[i].startswith("# "):
        heading = lines[i]
        i += 1
    # skip one blank line after heading
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    authored = "\n".join(lines[i:]).rstrip("\n")
    return heading, authored, details.rstrip("\n")


def join_body(heading: str, authored: str, details: str) -> str:
    parts: list[str] = []
    if heading:
        parts.append(heading)
        parts.append("")
    parts.append(authored.rstrip("\n"))
    if details:
        parts.append("")
        parts.append(details.rstrip("\n"))
    return "\n".join(parts).rstrip("\n") + "\n"


# --- create ----------------------------------------------------------------


@dataclass
class CreateResult:
    entry: Entry
    full_path: Path


def create_entry(
    cfg: Config,
    type_name: str,
    title: str,
    body: str,
    *,
    tags: list[str] | None = None,
    project: str | None = None,
    summary: str | None = None,
    original_input: str | None = None,
    type_fields: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> CreateResult:
    """Create a new entry of the given type.

    - `body` is the authored content only (no frontmatter, no title heading,
      no `<details>` block). The function adds those.
    - `type_fields` holds type-specific fields like status/priority/category.
    - `original_input` is wrapped into the standard `<details>` block so we
      always preserve the user's verbatim text.
    """
    type_dir = type_to_dir(type_name)
    canonical_type = dir_to_type(type_dir)
    if canonical_type == "project":
        if title == "(none)":
            raise ValueError(
                "project title '(none)' is reserved as the aggregation sentinel"
            )
        # a project does not belong to itself
        project = None
    if now is None:
        now = datetime.now()
        created_at = store.utcnow_iso()
    else:
        # Caller supplied the clock — use it for both the file path and the
        # stamp so tests and CLI backfills stay consistent.
        created_at = now.astimezone().strftime("%Y-%m-%dT%H:%M:%SZ") if now.tzinfo else now.strftime("%Y-%m-%dT%H:%M:%SZ")
    slug = store.slugify(title)
    stem = store.file_stem(slug, now)
    rel_dir = store.date_path(now)
    rel_file_path = f"{rel_dir}/{stem}.md"
    full_path = store.full_path_for(cfg, type_dir, rel_file_path)

    entry_id = store.next_id(cfg)

    entry_fields: dict[str, Any] = {
        "id": entry_id,
        "type": canonical_type,
        "title": title,
        "file_path": rel_file_path,
        "created_at": created_at,
        "tags": tags or [],
    }
    if summary is not None:
        entry_fields["summary"] = summary
    if project is not None:
        entry_fields["project"] = project
    if original_input is not None:
        entry_fields["input"] = original_input
    if type_fields:
        for k, v in type_fields.items():
            if v is not None:
                entry_fields[k] = v

    entry = Entry.model_validate(entry_fields)

    frontmatter = _frontmatter_from_entry(entry)
    full_body = wrap_with_original(body, original_input)
    md_text = store.build_markdown(frontmatter, title, full_body)
    store.atomic_write_text(full_path, md_text)
    store.append_index(cfg, type_dir, entry)
    return CreateResult(entry=entry, full_path=full_path)


def _frontmatter_from_entry(entry: Entry) -> dict[str, Any]:
    data = entry.to_index_json()
    # these stay in JSONL only, not in frontmatter:
    for k in ("id", "file_path", "summary", "input"):
        data.pop(k, None)
    return data


# --- lookup ----------------------------------------------------------------


def find_by_id(cfg: Config, entry_id: int) -> tuple[str, Entry] | None:
    """Scan every index for the entry with this id. Returns (type_dir, Entry) or None."""
    for type_dir in ALL_TYPE_DIRS:
        for entry in store.read_index(cfg, type_dir):
            if entry.id == entry_id:
                return type_dir, entry
    return None


def find_by_file_path(
    cfg: Config, file_path: str, type_or_dir: str | None = None
) -> tuple[str, Entry] | None:
    if type_or_dir:
        type_dirs = [type_to_dir(type_or_dir)]
    else:
        type_dirs = list(ALL_TYPE_DIRS)
    for type_dir in type_dirs:
        for entry in store.read_index(cfg, type_dir):
            if entry.file_path == file_path:
                return type_dir, entry
    return None


# --- update ----------------------------------------------------------------


_MUTABLE_FIELDS = {
    "title",
    "summary",
    "tags",
    "project",
    "status",
    "subtype",
    "priority",
    "due_date",
    "category",
    "source",
    "mood",
    "related_to",
    "prompt_type",
    "model_target",
    "description",
    "state",
    "local_dir",
    "tech_stack",
}


def update_entry(
    cfg: Config,
    entry_id: int,
    patch: dict[str, Any],
    *,
    body: str | None = None,
) -> Entry:
    """Patch an entry's metadata and (optionally) its authored body.

    - `patch` may contain any field in `_MUTABLE_FIELDS`. Unknown or immutable
      fields are rejected.
    - `body` replaces the authored portion of the markdown (between the title
      heading and the `<details>` block). Pass None to leave the body alone.
    """
    found = find_by_id(cfg, entry_id)
    if found is None:
        raise KeyError(f"entry id {entry_id} not found")
    type_dir, entry = found

    bad = set(patch) - _MUTABLE_FIELDS
    if bad:
        raise ValueError(f"cannot patch immutable fields: {sorted(bad)}")

    updated = entry.model_copy(update=patch)
    updated.updated_at = store.utcnow_iso()

    # rewrite markdown file: new frontmatter + (maybe) new body
    full_path = store.full_path_for(cfg, type_dir, entry.file_path)
    _, current_md_body = store.read_markdown(full_path)
    heading, authored, details = split_body(current_md_body)

    new_title = patch.get("title", entry.title)
    new_heading = f"# {new_title}"
    new_authored = authored if body is None else body.rstrip("\n")
    new_body = join_body(new_heading, new_authored, details)

    frontmatter = _frontmatter_from_entry(updated)
    store.rewrite_markdown(full_path, frontmatter, new_body)

    # rewrite JSONL index in place
    all_entries = store.read_index(cfg, type_dir)
    for i, e in enumerate(all_entries):
        if e.id == entry_id:
            all_entries[i] = updated
            break
    store.rewrite_index_atomic(cfg, type_dir, all_entries)
    return updated


def set_status(cfg: Config, entry_id: int, status: str) -> Entry:
    return update_entry(cfg, entry_id, {"status": status})


def mark_done(cfg: Config, entry_id: int) -> Entry:
    return set_status(cfg, entry_id, "done")


# --- delete ----------------------------------------------------------------


def delete_entry(cfg: Config, entry_id: int) -> Entry:
    """Soft delete: move the markdown file to .trash/ and drop the index line."""
    found = find_by_id(cfg, entry_id)
    if found is None:
        raise KeyError(f"entry id {entry_id} not found")
    type_dir, entry = found

    store.move_to_trash(cfg, type_dir, entry.file_path)
    remaining = [e for e in store.read_index(cfg, type_dir) if e.id != entry_id]
    store.rewrite_index_atomic(cfg, type_dir, remaining)
    return entry
