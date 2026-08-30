"""Create, read, update, delete braindump entries.

All mutations go through here; callers should never touch JSONL or markdown
files directly. This is the module the CLI and web server both import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from braindump.core import store
from braindump.core.config import Config
from braindump.core.errors import EntryNotFoundError
from braindump.core.schema import (
    ALL_TYPE_DIRS,
    LEGACY_TODO_STATUSES,
    PLANNING_STATUSES,
    PROJECT_STATES,
    QA_RESULTS,
    TODO_STATUSES,
    Entry,
    dir_to_type,
    type_to_dir,
)

# Relationships are deliberately explicit.  Keeping this table small prevents
# the permissive Entry model from quietly turning arbitrary fields into graph
# edges.
RELATION_TARGET_TYPES: dict[str, dict[str, str]] = {
    "todo": {"initiative_id": "initiative", "pitch_id": "pitch"},
    "initiative": {"project_ids": "project"},
    "pitch": {"project_ids": "project", "initiative_ids": "initiative"},
}
_ALL_RELATION_FIELDS = frozenset(
    field for fields in RELATION_TARGET_TYPES.values() for field in fields
)

# --- details block ---------------------------------------------------------

_DETAILS_RE = re.compile(
    r"(?ms)^\s*---\s*\n\s*<details>\s*\n\s*"
    r"<summary>Original input</summary>.*?</details>\s*$"
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


def drop_self_project_tag(tags: list[str] | None, project: str | None) -> list[str]:
    """Strip a tag that just repeats the entry's own project name.

    `project` is already a first-class field, so tagging a braindump entry
    `braindump` says nothing the entry doesn't already say — it only inflates
    tag analytics, where project names then dominate the real topic tags. A tag
    naming a *different* project is left alone: that's a cross-reference
    ("this introspect todo is about braindump"), which is worth keeping.
    """
    tags = list(tags or [])
    if not project:
        return tags
    return [t for t in tags if t.casefold() != project.casefold()]


def create_entry(  # noqa: PLR0913  # keyword-only entry fields, each maps to a schema column
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
        # Local wall-clock drives the filename / YYYY-MM path (reads as "when I
        # made it"); created_at stays UTC. .astimezone() keeps DTZ happy.
        now = datetime.now().astimezone()
        created_at = store.utcnow_iso()
    elif now.tzinfo:
        # Caller supplied the clock — use it for both the file path and the
        # stamp so tests and CLI backfills stay consistent.
        created_at = now.astimezone().strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    slug = store.slugify(title)
    stem = store.file_stem(slug, now)
    rel_dir = store.date_path(now)
    rel_file_path = f"{rel_dir}/{stem}.md"
    full_path = store.full_path_for(cfg, type_dir, rel_file_path)

    entry_fields: dict[str, Any] = {
        "type": canonical_type,
        "title": title,
        "file_path": rel_file_path,
        "created_at": created_at,
        "tags": drop_self_project_tag(tags, project),
    }
    if summary is not None:
        entry_fields["summary"] = summary
    if project is not None:
        entry_fields["project"] = project
    if original_input is not None:
        entry_fields["input"] = original_input
    if type_fields:
        entry_fields.update({k: v for k, v in type_fields.items() if v is not None})
    if canonical_type == "todo" and not entry_fields.get("status"):
        # New todos always enter the actionable lifecycle.  Keep accepting the
        # legacy postponed value when it is explicitly supplied for imports.
        entry_fields["status"] = "pending"

    _validate_canonical_fields(cfg, canonical_type, entry_fields)
    entry_fields["id"] = store.next_id(cfg)
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
    """Scan every index for this id. Returns (type_dir, Entry) or None."""
    for type_dir in ALL_TYPE_DIRS:
        for entry in store.read_index(cfg, type_dir):
            if entry.id == entry_id:
                return type_dir, entry
    return None


def resolve_entry(
    cfg: Config, entry_id: int, expected_type: str | None = None
) -> Entry | None:
    """Resolve an ID without making missing or deleted targets exceptional."""
    found = find_by_id(cfg, entry_id)
    if found is None:
        return None
    type_dir, entry = found
    if expected_type is not None and dir_to_type(type_dir) != dir_to_type(
        type_to_dir(expected_type)
    ):
        return None
    return entry


def resolve_relation(cfg: Config, entry_id: int, expected_type: str) -> Entry | None:
    """Resolve one typed relation, returning None for stale or wrong links."""
    return resolve_entry(cfg, entry_id, expected_type)


def resolve_relations(cfg: Config, entry: Entry, field: str) -> list[Entry | None]:
    """Resolve all IDs in a canonical relation, retaining missing slots.

    Retaining a None slot lets callers render a useful missing-reference
    warning while preserving the source entry's stable numeric link.
    """
    expected_type = RELATION_TARGET_TYPES.get(entry.type, {}).get(field)
    if expected_type is None:
        raise ValueError(f"unknown relation field {field!r} for {entry.type}")
    raw_ids = getattr(entry, field, None)
    if raw_ids is None:
        return []
    ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
    return [resolve_relation(cfg, relation_id, expected_type) for relation_id in ids]


def relation_target_ids(entry: Entry, field: str) -> list[int]:
    """Return a canonical relation as a list, regardless of scalar shape."""
    if field not in RELATION_TARGET_TYPES.get(entry.type, {}):
        raise ValueError(f"unknown relation field {field!r} for {entry.type}")
    value = getattr(entry, field, None)
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _validate_canonical_fields(
    cfg: Config,
    entry_type: str,
    fields: dict[str, Any],
    *,
    relation_fields: set[str] | None = None,
) -> None:
    """Validate lifecycle values and typed numeric links before any write."""
    _validate_status_and_state(entry_type, fields)
    _validate_relation_fields(cfg, entry_type, fields, relation_fields)


def _validate_status_and_state(entry_type: str, fields: dict[str, Any]) -> None:
    status = fields.get("status")
    if status is not None:
        if entry_type == "todo" and status not in (
            *TODO_STATUSES,
            *LEGACY_TODO_STATUSES,
        ):
            raise ValueError(f"todo status must be one of {list(TODO_STATUSES)}")
        if entry_type in {"initiative", "pitch"} and status not in PLANNING_STATUSES:
            raise ValueError(
                f"{entry_type} status must be one of {list(PLANNING_STATUSES)}"
            )
    state = fields.get("state")
    if entry_type == "project" and state is not None and state not in PROJECT_STATES:
        raise ValueError(f"project state must be one of {list(PROJECT_STATES)}")


def _validate_relation_fields(
    cfg: Config,
    entry_type: str,
    fields: dict[str, Any],
    relation_fields: set[str] | None,
) -> None:
    for field, target_type in RELATION_TARGET_TYPES.get(entry_type, {}).items():
        if relation_fields is not None and field not in relation_fields:
            continue
        if field not in fields or fields[field] is None:
            continue
        value = fields[field]
        values = value if isinstance(value, list) else [value]
        if field.endswith("_ids") and not isinstance(value, list):
            raise ValueError(f"{field} must be a list of numeric IDs")
        for relation_id in values:
            if isinstance(relation_id, bool) or not isinstance(relation_id, int):
                raise ValueError(  # noqa: TRY004 - mutation API uses one error type
                    f"{field} must contain numeric IDs"
                )
            target = resolve_entry(cfg, relation_id, target_type)
            if target is None:
                raise ValueError(
                    f"{field} target #{relation_id} is not an existing {target_type}"
                )


def find_by_file_path(
    cfg: Config, file_path: str, type_or_dir: str | None = None
) -> tuple[str, Entry] | None:
    type_dirs = [type_to_dir(type_or_dir)] if type_or_dir else list(ALL_TYPE_DIRS)
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
    "initiative_id",
    "pitch_id",
    "project_ids",
    "initiative_ids",
    "prompt_type",
    "model_target",
    "description",
    "state",
    "area",
    "local_dir",
    "tech_stack",
    "qa_result",
    "qa_verified_at",
    "qa_run_ref",
    "source_path",
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
        raise EntryNotFoundError(entry_id)
    type_dir, entry = found

    bad = set(patch) - _MUTABLE_FIELDS
    if bad:
        raise ValueError(f"cannot patch immutable fields: {sorted(bad)}")

    relation_fields_for_type = set(RELATION_TARGET_TYPES.get(entry.type, {}))
    unsupported_relations = (
        set(patch) & _ALL_RELATION_FIELDS
    ) - relation_fields_for_type
    if unsupported_relations:
        raise ValueError(
            f"relation fields {sorted(unsupported_relations)} are not valid for "
            f"{entry.type}"
        )

    merged = entry.model_dump()
    merged.update(patch)
    _validate_canonical_fields(
        cfg,
        entry.type,
        merged,
        relation_fields=set(patch) & relation_fields_for_type,
    )
    updated = Entry.model_validate(merged)
    updated.tags = drop_self_project_tag(updated.tags, updated.project)
    updated.updated_at = store.utcnow_iso()

    # rewrite markdown file: new frontmatter + (maybe) new body
    full_path = store.full_path_for(cfg, type_dir, entry.file_path)
    _, current_md_body = store.read_markdown(full_path)
    _heading, authored, details = split_body(current_md_body)

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


def record_qa_result(
    cfg: Config,
    entry_id: int,
    result: str,
    *,
    run_ref: str | None = None,
    now: datetime | None = None,
) -> Entry:
    """Store one QA receipt and advance the todo in the same mutation.

    A passing receipt settles the todo; a failing receipt puts it back in
    progress.  ``update_entry`` is deliberately called once so the receipt's
    result, timestamp, run reference, and lifecycle transition share one
    index/markdown update.
    """
    found = find_by_id(cfg, entry_id)
    if found is None:
        raise EntryNotFoundError(entry_id)
    _, entry = found
    if entry.type != "todo":
        raise ValueError("QA results can only be recorded for todos")

    normalized = result.strip().lower()
    if normalized not in QA_RESULTS:
        raise ValueError(f"QA result must be one of {list(QA_RESULTS)}")

    if now is None:
        verified_at = store.utcnow_iso()
    else:
        clock = now.replace(tzinfo=UTC) if now.tzinfo is None else now
        verified_at = clock.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return update_entry(
        cfg,
        entry_id,
        {
            "qa_result": normalized,
            "qa_verified_at": verified_at,
            "qa_run_ref": run_ref,
            "status": "done" if normalized == "pass" else "in-progress",
        },
    )


# --- delete ----------------------------------------------------------------


def delete_entry(cfg: Config, entry_id: int) -> Entry:
    """Soft delete: move the markdown file to .trash/ and drop the index line."""
    found = find_by_id(cfg, entry_id)
    if found is None:
        raise EntryNotFoundError(entry_id)
    type_dir, entry = found

    store.move_to_trash(cfg, type_dir, entry.file_path)
    remaining = [e for e in store.read_index(cfg, type_dir) if e.id != entry_id]
    store.rewrite_index_atomic(cfg, type_dir, remaining)
    return entry
