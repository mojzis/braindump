"""Daily journal: cutoff-aware day rollover, carry-forward, append/close.

The journal has one file per day at `journal/YYYY/MM/YYYY-MM-DD.md` and one
index entry per day. The index entry tracks word count and last activity so
the web UI can render a calendar/activity view cheaply.

Day rollover semantics:

- Writes before `cfg.day_cutoff_hour` (default 04:00 local) still go to the
  previous day's file. That's what "finish the day when I go to bed" means
  in practice.
- A manual "close day" action bypasses the cutoff: you can seal today at 11pm
  and start tomorrow's file immediately.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from braindump.core import store
from braindump.core.config import Config
from braindump.core.schema import Entry


JOURNAL_TYPE_DIR = "journal"


def current_day(cfg: Config, now: datetime | None = None) -> date:
    """Return the logical 'today' for journaling, respecting day_cutoff_hour."""
    now = now or store.local_now()
    if now.hour < cfg.day_cutoff_hour:
        return (now - timedelta(days=1)).date()
    return now.date()


def day_file_rel(d: date) -> str:
    return f"{d.year:04d}/{d.month:02d}/{d.isoformat()}.md"


def day_full_path(cfg: Config, d: date) -> Path:
    return cfg.home / JOURNAL_TYPE_DIR / day_file_rel(d)


def _frontmatter_for_day(
    d: date, *, project: str | None, created_at: str, updated_at: str, word_count: int
) -> dict[str, Any]:
    fm: dict[str, Any] = {
        "type": "journal",
        "title": d.isoformat(),
        "date": d.isoformat(),
        "created_at": created_at,
        "updated_at": updated_at,
        "word_count": word_count,
    }
    if project:
        fm["project"] = project
    return fm


def get_day_entry(cfg: Config, d: date) -> Entry | None:
    for entry in store.read_index(cfg, JOURNAL_TYPE_DIR):
        if entry.date == d.isoformat() or entry.file_path == day_file_rel(d):
            return entry
    return None


def get_or_create_day(
    cfg: Config,
    d: date,
    *,
    project: str | None = None,
) -> Entry:
    """Return the journal entry for day `d`, creating the file and index row if missing."""
    existing = get_day_entry(cfg, d)
    if existing:
        return existing

    now_iso = store.utcnow_iso()
    rel = day_file_rel(d)
    full = day_full_path(cfg, d)
    entry_id = store.next_id(cfg)
    entry = Entry(
        id=entry_id,
        type="journal",
        title=d.isoformat(),
        file_path=rel,
        created_at=now_iso,
        updated_at=now_iso,
        date=d.isoformat(),
        word_count=0,
        project=project,
        tags=[],
    )
    fm = _frontmatter_for_day(
        d,
        project=project,
        created_at=now_iso,
        updated_at=now_iso,
        word_count=0,
    )
    md = store.build_markdown(fm, d.isoformat(), "")
    store.atomic_write_text(full, md)
    store.append_index(cfg, JOURNAL_TYPE_DIR, entry)
    return entry


def append_text(
    cfg: Config,
    d: date,
    text: str,
    *,
    project: str | None = None,
) -> Entry:
    """Append a free-form chunk to a day's journal and refresh the index row."""
    entry = get_or_create_day(cfg, d, project=project)
    full = day_full_path(cfg, d)
    fm, body = store.read_markdown(full)
    stripped = text.rstrip()
    if not stripped:
        return entry
    body = body.rstrip("\n")
    new_body = f"{body}\n\n{stripped}\n" if body else f"{stripped}\n"
    new_word_count = _count_words(_extract_body_after_heading(new_body))
    now_iso = store.utcnow_iso()
    fm["updated_at"] = now_iso
    fm["word_count"] = new_word_count
    store.rewrite_markdown(full, fm, new_body)

    # update index row
    all_entries = store.read_index(cfg, JOURNAL_TYPE_DIR)
    for i, e in enumerate(all_entries):
        if e.id == entry.id:
            updated = e.model_copy(
                update={"updated_at": now_iso, "word_count": new_word_count}
            )
            all_entries[i] = updated
            store.rewrite_index_atomic(cfg, JOURNAL_TYPE_DIR, all_entries)
            return updated
    return entry


def replace_body(
    cfg: Config,
    d: date,
    body: str,
    *,
    project: str | None = None,
) -> Entry:
    """Overwrite the authored body of a day's journal. Used by the web editor."""
    entry = get_or_create_day(cfg, d, project=project)
    full = day_full_path(cfg, d)
    fm, _ = store.read_markdown(full)
    body = body.rstrip("\n") + "\n" if body.strip() else ""
    rendered = f"# {d.isoformat()}\n\n{body}" if body else f"# {d.isoformat()}\n"
    word_count = _count_words(body)
    now_iso = store.utcnow_iso()
    fm["updated_at"] = now_iso
    fm["word_count"] = word_count
    store.rewrite_markdown(full, fm, rendered)

    all_entries = store.read_index(cfg, JOURNAL_TYPE_DIR)
    for i, e in enumerate(all_entries):
        if e.id == entry.id:
            updated = e.model_copy(
                update={"updated_at": now_iso, "word_count": word_count}
            )
            all_entries[i] = updated
            store.rewrite_index_atomic(cfg, JOURNAL_TYPE_DIR, all_entries)
            return updated
    return entry


def read_body(cfg: Config, d: date) -> str:
    """Return the authored body (no heading, no frontmatter) for day `d`."""
    full = day_full_path(cfg, d)
    if not full.exists():
        return ""
    _, body = store.read_markdown(full)
    return _extract_body_after_heading(body)


def close_today(cfg: Config, *, project: str | None = None) -> Entry:
    """Seal today's journal and open tomorrow's immediately, regardless of cutoff.

    Returns the freshly-opened next-day entry.
    """
    today = current_day(cfg)
    get_or_create_day(cfg, today, project=project)
    next_day = today + timedelta(days=1)
    return get_or_create_day(cfg, next_day, project=project)


def previous_day_with_content(cfg: Config, d: date, max_look_back: int = 30) -> date | None:
    for i in range(1, max_look_back + 1):
        candidate = d - timedelta(days=i)
        entry = get_day_entry(cfg, candidate)
        if entry and (entry.word_count or 0) > 0:
            return candidate
    return None


def _extract_body_after_heading(body: str) -> str:
    lines = body.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i < len(lines) and lines[i].startswith("# "):
        i += 1
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    return "\n".join(lines[i:]).rstrip("\n")


_word_re = re.compile(r"\S+")


def _count_words(text: str) -> int:
    return len(_word_re.findall(text))
