"""Braindump CLI — the `bd` entrypoint.

This module is intentionally thin: all logic lives in `braindump.core.*`. The
CLI is just argument parsing, stdin plumbing, and output formatting. Both the
Claude skills and any shell scripts should call into this surface.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import cast

import typer

from braindump.core import entries, journal, projects, query, store
from braindump.core import tags as tags_mod
from braindump.core.config import Config, load_config
from braindump.core.query import StatusFilter
from braindump.core.schema import ALL_TYPE_DIRS, PROJECT_STATES, Entry, type_to_dir

app = typer.Typer(
    help="Braindump CLI — personal knowledge management.",
    no_args_is_help=True,
    add_completion=False,
)

journal_app = typer.Typer(help="Daily journal commands.", no_args_is_help=True)
project_app = typer.Typer(help="Project commands.", no_args_is_help=True)
tags_app = typer.Typer(help="Tag analytics.", no_args_is_help=True)

app.add_typer(journal_app, name="journal")
app.add_typer(project_app, name="project")
app.add_typer(tags_app, name="tags")


# --- helpers ---------------------------------------------------------------


def _read_stdin_if_piped() -> str:
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def _emit_hit_json(hit: query.Hit) -> None:
    data = hit.entry.to_index_json()
    data["_source"] = hit.source
    typer.echo(json.dumps(data, ensure_ascii=False))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _require_date(value: str) -> date:
    return date.fromisoformat(value)


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _effective_project(explicit: str | None, cfg) -> str | None:
    """Honor the active-project filter unless the caller passed --all or --project."""
    if explicit is not None:
        return explicit
    return projects.get_active_project(cfg)


# --- create ----------------------------------------------------------------


@app.command()
def create(
    entry_type: str = typer.Argument(
        ..., metavar="TYPE", help="todo, til, thought, prompt, project"
    ),
    title: str = typer.Argument(..., help="Entry title"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Tag (repeatable)"),
    project: str | None = typer.Option(None, "--project", "-p"),
    summary: str | None = typer.Option(None, "--summary", "-s"),
    status: str | None = typer.Option(None, "--status"),
    priority: str | None = typer.Option(None, "--priority"),
    subtype: str | None = typer.Option(None, "--subtype"),
    category: str | None = typer.Option(None, "--category"),
    source: str | None = typer.Option(None, "--source"),
    mood: str | None = typer.Option(None, "--mood"),
    related_to: str | None = typer.Option(None, "--related-to"),
    prompt_type: str | None = typer.Option(None, "--prompt-type"),
    model_target: str | None = typer.Option(None, "--model-target"),
    due_date: str | None = typer.Option(None, "--due-date"),
    description: str | None = typer.Option(None, "--description"),
    state: str | None = typer.Option(None, "--state"),
    area: str | None = typer.Option(
        None,
        "--area",
        help="Project grouping (project type; free-form, reused like a tag)",
    ),
    local_dir: str | None = typer.Option(None, "--local-dir"),
    tech: list[str] = typer.Option([], "--tech", help="Tech stack entry (repeatable)"),
    original_input: str | None = typer.Option(None, "--original-input"),
    original_input_file: Path | None = typer.Option(None, "--original-input-file"),
    body_file: Path | None = typer.Option(None, "--body-file"),
):
    """Create a new entry. Body is read from stdin unless --body-file is given."""
    cfg = load_config()
    store.ensure_type_dirs(cfg)

    body = body_file.read_text() if body_file is not None else _read_stdin_if_piped()

    if original_input_file is not None:
        original_input = original_input_file.read_text()

    if entry_type == "project" and state is not None and state not in PROJECT_STATES:
        raise typer.BadParameter(
            f"--state must be one of {list(PROJECT_STATES)} (got {state!r})"
        )

    type_fields: dict[str, object] = {
        k: v
        for k, v in {
            "status": status,
            "priority": priority,
            "subtype": subtype,
            "category": category,
            "source": source,
            "mood": mood,
            "related_to": related_to,
            "prompt_type": prompt_type,
            "model_target": model_target,
            "due_date": due_date,
            "description": description,
            "state": state,
            "area": area,
            "local_dir": local_dir,
        }.items()
        if v is not None
    }
    if tech:
        type_fields["tech_stack"] = list(tech)

    try:
        result = entries.create_entry(
            cfg,
            entry_type,
            title,
            body,
            tags=tag,
            project=project,
            summary=summary,
            original_input=original_input,
            type_fields=type_fields,
        )
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    typer.echo(f"created: #{result.entry.id} {result.entry.file_path}")


# --- list ------------------------------------------------------------------


@app.command("list")
def list_cmd(
    entry_type: str | None = typer.Argument(None, metavar="[TYPE]"),
    limit: int = typer.Option(10, "--limit", "-n"),
    project: str | None = typer.Option(None, "--project", "-p"),
    all_projects: bool = typer.Option(False, "--all", help="Ignore active project"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List recent entries (newest first)."""
    cfg = load_config()
    types: list[str] = [type_to_dir(entry_type)] if entry_type else []
    proj = None if all_projects else _effective_project(project, cfg)
    hits = query.list_recent(cfg, types=types, project=proj, limit=limit)
    if as_json:
        for h in hits:
            _emit_hit_json(h)
        return
    for h in hits:
        date_str = (h.entry.created_at or "")[:10]
        proj_str = f" ({h.entry.project})" if h.entry.project else ""
        status_str = ""
        if h.entry.type == "todo":
            status_str = f" [{h.entry.status or 'pending'}]"
        typer.echo(
            f"#{h.entry.id} {date_str} [{h.entry.type}]{status_str} "
            f"{h.entry.title}{proj_str}"
        )


# --- search ----------------------------------------------------------------


@app.command()
def search(
    query_words: list[str] = typer.Argument(None, metavar="QUERY..."),
    entry_type: str | None = typer.Option(None, "--type"),
    project: str | None = typer.Option(None, "--project", "-p"),
    all_projects: bool = typer.Option(False, "--all"),
    status: str = typer.Option("all", "--status", help="open, done, or all"),
    tag: list[str] = typer.Option([], "--tag", "-t"),
    since: str | None = typer.Option(None, "--since", help="YYYY-MM-DD"),
    until: str | None = typer.Option(None, "--until", help="YYYY-MM-DD"),
    limit: int = typer.Option(50, "--limit", "-n"),
    no_fulltext: bool = typer.Option(False, "--no-fulltext"),
    as_json: bool = typer.Option(True, "--json/--human"),
):
    """Search across braindump entries."""
    cfg = load_config()
    q = " ".join(query_words or [])
    proj = None if all_projects else _effective_project(project, cfg)
    types = [entry_type] if entry_type else []
    filters = query.SearchFilters(
        q=q or None,
        types=types,
        project=proj,
        status=cast(StatusFilter, status),
        tags=tag,
        since=_parse_date(since),
        until=_parse_date(until),
        limit=limit,
        fulltext=not no_fulltext,
    )
    hits = query.search(cfg, filters)
    if as_json:
        for h in hits:
            _emit_hit_json(h)
        return
    for h in hits:
        date_str = (h.entry.created_at or "")[:10]
        proj_str = f" ({h.entry.project})" if h.entry.project else ""
        typer.echo(
            f"#{h.entry.id} {date_str} [{h.entry.type}] {h.entry.title}{proj_str}"
        )


# --- show ------------------------------------------------------------------

# Keep in sync with type-specific fields in schema.py (Entry model).
_TYPE_SPECIFIC_FIELDS: dict[str, list[str]] = {
    "todo": ["status", "subtype", "priority", "due_date"],
    "til": ["category", "source"],
    "thought": ["mood", "related_to"],
    "prompt": ["prompt_type", "model_target"],
    "journal": ["date", "word_count"],
    "project": ["description", "state", "area", "local_dir", "tech_stack"],
}


def _read_authored_body(cfg: Config, type_dir: str, entry: Entry) -> str:
    """Read the authored body from the entry's markdown file."""
    full_path = store.full_path_for(cfg, type_dir, entry.file_path)
    if full_path.exists():
        _, md_body = store.read_markdown(full_path)
        _, authored, _ = entries.split_body(md_body)
        return authored
    return ""


def _find_entries_by_ids(
    cfg: Config,
    ids: set[int],
) -> dict[int, tuple[str, Entry]]:
    """Scan indexes once and return all requested entries."""
    found: dict[int, tuple[str, Entry]] = {}
    for type_dir in ALL_TYPE_DIRS:
        for entry in store.read_index(cfg, type_dir):
            if entry.id in ids:
                found[entry.id] = (type_dir, entry)
    return found


def _format_entry(cfg: Config, type_dir: str, entry: Entry) -> str:
    """Return the formatted text for a single entry."""
    lines: list[str] = []
    lines.append(f"#{entry.id} {entry.type} — {entry.title}")

    meta_parts: list[str] = []
    meta_parts.append(f"created: {(entry.created_at or '')[:10]}")
    if entry.project:
        meta_parts.append(f"project: {entry.project}")
    if entry.tags:
        meta_parts.append(f"tags: {', '.join(entry.tags)}")
    lines.append("  ".join(meta_parts))

    for field in _TYPE_SPECIFIC_FIELDS.get(entry.type, []):
        val = getattr(entry, field, None)
        if val is not None:
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            lines.append(f"{field}: {val}")

    authored = _read_authored_body(cfg, type_dir, entry)
    if authored.strip():
        lines.append("")
        lines.append(authored)

    return "\n".join(lines)


def _entry_json(cfg: Config, type_dir: str, entry: Entry) -> dict:
    """Return JSON dict for an entry."""
    data = entry.to_index_json()
    data["body"] = _read_authored_body(cfg, type_dir, entry)
    return data


@app.command()
@app.command(name="view", hidden=True)
def show(
    ids: list[int] = typer.Argument(..., metavar="ID..."),
    as_json: bool = typer.Option(False, "--json"),
):
    """Display one or more entries by ID."""
    cfg = load_config()
    found = _find_entries_by_ids(cfg, set(ids))
    success_count = 0
    outputs: list[str] = []

    for entry_id in ids:
        if entry_id not in found:
            typer.echo(f"error: entry {entry_id} not found", err=True)
            continue
        type_dir, entry = found[entry_id]
        success_count += 1
        if as_json:
            typer.echo(
                json.dumps(_entry_json(cfg, type_dir, entry), ensure_ascii=False)
            )
        else:
            outputs.append(_format_entry(cfg, type_dir, entry))

    if not as_json and outputs:
        typer.echo("\n---\n".join(outputs))

    if success_count == 0:
        raise typer.Exit(code=1)


# --- done / update / delete ------------------------------------------------


@app.command()
def done(arg: str = typer.Argument(...)):
    """Mark a todo as done by id, file path, or search query."""
    cfg = load_config()
    entry_id = _resolve_todo(cfg, arg)
    updated = entries.mark_done(cfg, entry_id)
    typer.echo(f"done: #{updated.id} {updated.file_path}")


@app.command()
def update(
    entry_id: int = typer.Argument(..., metavar="ID"),
    title: str | None = typer.Option(None, "--title"),
    summary: str | None = typer.Option(None, "--summary"),
    tags: str | None = typer.Option(
        None, "--tags", help="Comma-separated — replaces existing tags"
    ),
    project: str | None = typer.Option(None, "--project", "-p"),
    status: str | None = typer.Option(None, "--status"),
    priority: str | None = typer.Option(None, "--priority"),
    area: str | None = typer.Option(
        None, "--area", help="Project grouping (project type)"
    ),
    body_from_stdin: bool = typer.Option(
        False, "--body", help="Replace body with stdin"
    ),
):
    """Patch an entry's metadata and (optionally) its body."""
    cfg = load_config()
    patch: dict[str, object] = {}
    if title is not None:
        patch["title"] = title
    if summary is not None:
        patch["summary"] = summary
    if tags is not None:
        patch["tags"] = _split_csv(tags)
    if project is not None:
        patch["project"] = project
    if status is not None:
        patch["status"] = status
    if priority is not None:
        patch["priority"] = priority
    if area is not None:
        patch["area"] = area
    body = _read_stdin_if_piped() if body_from_stdin else None
    updated = entries.update_entry(cfg, entry_id, patch, body=body)
    typer.echo(f"updated: #{updated.id} {updated.file_path}")


@app.command()
def delete(entry_id: int = typer.Argument(...)):
    """Soft-delete an entry (moves the file to .trash/)."""
    cfg = load_config()
    entries.delete_entry(cfg, entry_id)
    typer.echo(f"deleted: {entry_id}")


def _resolve_todo(cfg, arg: str) -> int:
    if arg.isdigit():
        return int(arg)
    # Try file path first
    if arg.endswith(".md") or "/" in arg:
        found = entries.find_by_file_path(cfg, arg, "todos")
        if found:
            return found[1].id
        typer.echo(f"No todo found with file path: {arg}", err=True)
        raise typer.Exit(code=1)
    # Otherwise treat as a search over open todos
    hits = query.search(
        cfg,
        query.SearchFilters(
            q=arg, types=["todos"], status="open", limit=5, fulltext=False
        ),
    )
    if not hits:
        typer.echo(f"No open todos found for: {arg}", err=True)
        raise typer.Exit(code=1)
    if len(hits) > 1:
        typer.echo("Multiple matches:", err=True)
        for h in hits:
            typer.echo(
                f"  #{h.entry.id} [{h.entry.status or 'pending'}] {h.entry.title}",
                err=True,
            )
        raise typer.Exit(code=1)
    return hits[0].entry.id


# --- journal ---------------------------------------------------------------


@journal_app.command("today")
def journal_today(
    show: bool = typer.Option(False, "--show", help="Print today's body"),
):
    """Show or ensure today's journal exists."""
    cfg = load_config()
    d = journal.current_day(cfg)
    entry = journal.get_or_create_day(cfg, d)
    if show:
        typer.echo(journal.read_body(cfg, d))
        return
    typer.echo(f"day: {d.isoformat()} id: {entry.id} words: {entry.word_count or 0}")


@journal_app.command("append")
def journal_append(
    text: str | None = typer.Argument(None),
    target_day: str | None = typer.Option(
        None, "--day", help="YYYY-MM-DD (defaults to today)"
    ),
):
    """Append text to a day's journal. Text is read from stdin if not given."""
    cfg = load_config()
    body = text if text is not None else _read_stdin_if_piped()
    if not body.strip():
        typer.echo("No text to append.", err=True)
        raise typer.Exit(code=1)
    d = _require_date(target_day) if target_day else journal.current_day(cfg)
    entry = journal.append_text(cfg, d, body)
    typer.echo(f"appended: {d.isoformat()} words: {entry.word_count or 0}")


@journal_app.command("close")
def journal_close():
    """Seal today's journal and open tomorrow's, regardless of the cutoff clock."""
    cfg = load_config()
    next_entry = journal.close_today(cfg)
    typer.echo(f"opened: {next_entry.date}")


@journal_app.command("show")
def journal_show(day: str = typer.Argument(..., help="YYYY-MM-DD")):
    cfg = load_config()
    typer.echo(journal.read_body(cfg, _require_date(day)))


# --- projects --------------------------------------------------------------


def _project_counts(s: projects.ProjectStats) -> str:
    return (
        f"{s.entry_count} entries "
        f"({s.open_todos} open / {s.done_todos} done) "
        f"last: {(s.last_activity or '')[:10]}"
    )


def _project_line(s: projects.ProjectStats, active: str | None) -> str:
    marker = "* " if s.name == active else "  "
    reg = "R" if s.registered else "-"
    state_str = f" [{s.state}]" if s.state else ""
    return f"{marker}[{reg}] {s.name}{state_str}: {_project_counts(s)}"


@project_app.command("list")
def project_list(
    by_area: bool = typer.Option(
        False, "--by-area", help="Group projects under their area"
    ),
):
    """List all projects with aggregate stats."""
    cfg = load_config()
    stats = projects.list_projects(cfg)
    active = projects.get_active_project(cfg)
    if not stats:
        typer.echo("(no projects yet)")
        return
    if not by_area:
        for s in stats:
            typer.echo(_project_line(s, active))
        return
    grouped: dict[str, list] = {}
    for s in stats:
        grouped.setdefault(s.area or "(no area)", []).append(s)
    for area in sorted(grouped, key=lambda a: (a == "(no area)", a)):
        typer.echo(f"\n{area}")
        for s in grouped[area]:
            typer.echo(_project_line(s, active))


@project_app.command("unregistered")
def project_unregistered():
    """List projects referenced by entries but never registered with create."""
    cfg = load_config()
    stats = [
        s
        for s in projects.list_projects(cfg)
        if not s.registered and s.name != "(none)"
    ]
    if not stats:
        typer.echo("(no unregistered projects)")
        return
    for s in stats:
        typer.echo(f"  {s.name}: {_project_counts(s)}")


@project_app.command("show")
def project_show(name: str = typer.Argument(...)):
    cfg = load_config()
    s = projects.project_stats(cfg, name)
    typer.echo(f"project: {name}")
    if s.registered:
        typer.echo("registered: yes")
        if s.state:
            typer.echo(f"state: {s.state}")
        if s.area:
            typer.echo(f"area: {s.area}")
        if s.description:
            typer.echo(f"description: {s.description}")
        if s.local_dir:
            typer.echo(f"local_dir: {s.local_dir}")
        if s.tech_stack:
            typer.echo(f"tech_stack: {', '.join(s.tech_stack)}")
    else:
        typer.echo("registered: no")
    typer.echo(f"entries: {s.entry_count}")
    typer.echo(f"open todos: {s.open_todos}")
    typer.echo(f"done todos: {s.done_todos}")
    typer.echo(f"last activity: {s.last_activity or '(none)'}")
    if s.type_counts:
        typer.echo("types:")
        for t, n in s.type_counts.most_common():
            typer.echo(f"  {t}: {n}")
    if s.tag_counts:
        typer.echo("top tags:")
        for tag, n in s.tag_counts.most_common(10):
            typer.echo(f"  {tag}: {n}")


@project_app.command("focus")
def project_focus(
    name: str | None = typer.Argument(None),
    clear: bool = typer.Option(False, "--clear"),
):
    """Set or clear the active project filter."""
    cfg = load_config()
    if clear:
        projects.set_active_project(cfg, None)
        typer.echo("focus cleared")
        return
    if not name:
        current = projects.get_active_project(cfg)
        typer.echo(f"active project: {current or '(none)'}")
        return
    projects.set_active_project(cfg, name)
    typer.echo(f"focused: {name}")


# --- tags ------------------------------------------------------------------


@tags_app.command("stats")
def tags_stats():
    cfg = load_config()
    counter = tags_mod.tag_frequency(cfg)
    if not counter:
        typer.echo("Tag frequency:\n==============")
        return
    typer.echo("Tag frequency:")
    typer.echo("==============")
    for tag, n in counter.most_common():
        typer.echo(f"  {n:4d} {tag}")


@tags_app.command("show")
def tags_show(tag: str = typer.Argument(...)):
    cfg = load_config()
    results = tags_mod.entries_with_tag(cfg, tag)
    if not results:
        typer.echo(f"No entries tagged {tag!r}")
        return
    for t, eid, title in results:
        typer.echo(f"#{eid} [{t}] {title}")


# --- doctor ----------------------------------------------------------------


@app.command()
def doctor():
    """Validate indexes and report orphaned markdown files."""
    cfg = load_config()
    problems = 0
    for tmp in store.sweep_stale_tmp(cfg):
        typer.echo(f"REMOVED STALE TMP: {tmp.relative_to(cfg.home)}", err=True)
    for type_dir in ALL_TYPE_DIRS:
        idx = cfg.index_path(type_dir)
        if not idx.exists():
            continue
        entries_in_idx = store.read_index(cfg, type_dir)
        files_referenced = set()
        for e in entries_in_idx:
            full = store.full_path_for(cfg, type_dir, e.file_path)
            files_referenced.add(full.resolve())
            if not full.exists():
                typer.echo(
                    f"MISSING FILE: {type_dir}/{e.file_path} (id={e.id})", err=True
                )
                problems += 1
        root = cfg.type_dir(type_dir)
        for md in root.rglob("*.md"):
            if md.resolve() not in files_referenced:
                typer.echo(f"ORPHAN MD:    {md.relative_to(cfg.home)}", err=True)
                problems += 1
    if problems == 0:
        typer.echo("ok")
    else:
        typer.echo(f"{problems} problem(s) found", err=True)
        raise typer.Exit(code=1)


# --- serve -----------------------------------------------------------------


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int | None = typer.Option(None, "--port"),
    reload: bool = typer.Option(False, "--reload"),
):
    """Start the local web UI."""
    import uvicorn  # noqa: PLC0415  # optional [web] dependency, imported lazily

    cfg = load_config()
    uvicorn.run(
        "braindump.web.app:app",
        host=host,
        port=port or cfg.port,
        reload=reload,
        # The journal live-refresh SSE stream is a long-lived connection;
        # without this, uvicorn's graceful shutdown blocks on it forever
        # ("Waiting for connections to close. CTRL+C to force quit") on every
        # Ctrl-C and every --reload restart. Force connections closed instead.
        timeout_graceful_shutdown=0,
    )


@app.command("app")
def app_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int | None = typer.Option(None, "--port"),
    foreground: bool = typer.Option(
        False,
        "--foreground",
        "-f",
        help="Stay attached to this terminal instead of detaching.",
    ),
):
    """Run the web UI in a native desktop window (pywebview).

    Detaches by default: the window keeps running after the shell that started
    it closes, and its output goes to `~/braindump/.bd-app.log`.
    """
    # optional [app] dep — imported lazily
    from braindump.web.desktop import launch_detached, run_app  # noqa: PLC0415

    try:
        if foreground:
            run_app(host=host, port=port)
            return
        pid, log_file = launch_detached(host=host, port=port)
    except (RuntimeError, OSError) as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"bd app running in the background (pid {pid})  log: {log_file}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
