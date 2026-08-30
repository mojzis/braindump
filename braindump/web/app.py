"""FastAPI app for the braindump local UI.

Routes are server-rendered Jinja + htmx. No JS framework, no build step.
Everything speaks to `braindump.core.*` — the same code the CLI uses — so there
is one source of truth for the data.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import markdown as md
import nh3
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from watchfiles import Change, awatch

from braindump.core import claude_cli, digest, entries, journal, projects, query, store
from braindump.core import tags as tags_mod
from braindump.core.config import Config, load_config
from braindump.core.errors import BraindumpError, EntryNotFoundError, ReadOnlyStoreError
from braindump.core.query import StatusFilter
from braindump.core.schema import ALL_TYPES, PROJECT_STATES, Entry

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

PAST_DAYS_PAGE = 7


@dataclass
class ParseJob:
    """State for the single running/last parse job (in-memory; not persisted)."""

    day: date
    status: str = "running"  # running | done | error
    progress: dict[str, str] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    result: digest.ParseResult | None = None
    error: str | None = None


def _watch_filter(_change: Change, path: str) -> bool:
    p = Path(path)
    name = p.name
    if name == ".state.json":
        return False
    if name.startswith("."):
        return False
    if name.endswith((".swp", ".swx", "~", ".tmp")):
        return False
    if "/.git/" in path:
        return False
    return p.suffix in {".md", ".jsonl", ".json"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    # Starlette's State is untyped, so bind a typed local and share the object
    # with it — that keeps a real declaration for the one long-lived container.
    subscribers: set[asyncio.Queue[str]] = set()
    app.state.subscribers = subscribers
    # parse_job (ParseJob | None) and parse_task (asyncio.Task | None) are
    # reassigned from the parse handlers, so they can only be documented here.
    app.state.parse_job = None
    app.state.parse_task = None
    stop = asyncio.Event()
    app.state.watch_stop = stop
    log = logging.getLogger("braindump.web")

    async def watcher() -> None:
        while not stop.is_set():
            try:
                async for _changes in awatch(
                    cfg.home, watch_filter=_watch_filter, stop_event=stop
                ):
                    for q in list(subscribers):
                        with contextlib.suppress(asyncio.QueueFull):
                            q.put_nowait("reload")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("braindump watcher crashed, restarting in 1s")
                await asyncio.sleep(1)

    task = asyncio.create_task(watcher())
    try:
        yield
    finally:
        stop.set()
        for q in list(subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait("__shutdown__")
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        parse_task = app.state.parse_task
        if parse_task is not None and not parse_task.done():
            parse_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await parse_task


def _render_markdown(text: str) -> Markup:
    """Render entry body markdown to HTML for read-only display."""
    html = md.markdown(
        text or "",
        extensions=["fenced_code", "tables", "sane_lists"],
    )
    # nh3.clean sanitizes the HTML above before it is wrapped as safe Markup.
    return Markup(nh3.clean(html))  # noqa: S704


_REF_CHIP_RE = re.compile(
    r"\[→(todo|til|thought|prompt|project|initiative|pitch)#(\d+)\]"
)


def _ref_chip_sub(m: re.Match[str]) -> str:
    entry_type, entry_id = m.group(1), m.group(2)
    if entry_type in {"project", "initiative", "pitch"}:
        target = entries.resolve_relation(load_config(), int(entry_id), entry_type)
        if target is None:
            return f'<span class="missing-ref">missing {entry_type} #{entry_id}</span>'
    return f'<a class="ref-chip" href="/entries/{entry_id}">{entry_type}#{entry_id}</a>'


def _journal_markdown(text: str) -> Markup:
    """Render journal body markdown, then re-link typed reference marks as chips.

    The chip-linking regex runs *after* `_render_markdown`'s nh3 pass because
    nh3 strips `class` attributes — a `class="ref-chip"` anchor injected
    before sanitizing would come out unstyled.
    """
    html = _render_markdown(text)
    # `html` is already nh3-sanitized by `_render_markdown`; the regex only
    # rewrites `[→type#id]` marks into anchors, so re-wrapping is safe.
    return Markup(_REF_CHIP_RE.sub(_ref_chip_sub, str(html)))  # noqa: S704


class _SuppressShutdownCancel(logging.Filter):
    """Drop uvicorn's "Exception in ASGI application" traceback when it's just
    the long-lived `/events` SSE stream being force-cancelled on shutdown/reload.

    `bd serve` runs with ``timeout_graceful_shutdown=0`` so Ctrl-C / --reload
    don't hang on the never-closing SSE connection. The tradeoff is uvicorn
    force-cancels the in-flight request, and starlette's StreamingResponse
    disconnect-listener surfaces that as a `CancelledError` uvicorn logs at
    ERROR. It's noise, not a real failure — filter exactly that record and
    nothing else.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.getMessage().strip() != "Exception in ASGI application":
            return True
        exc = record.exc_info[1] if record.exc_info else None
        return not isinstance(exc, asyncio.CancelledError)


logging.getLogger("uvicorn.error").addFilter(_SuppressShutdownCancel())

app = FastAPI(title="Braindump", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["markdown"] = _render_markdown
templates.env.filters["journal_markdown"] = _journal_markdown


@app.exception_handler(EntryNotFoundError)
async def _entry_not_found(_request: Request, exc: Exception) -> Response:
    return PlainTextResponse(str(exc), status_code=404)


@app.exception_handler(BraindumpError)
async def _braindump_error(_request: Request, exc: Exception) -> Response:
    """Answer with the message the CLI would print instead of a 500 traceback.

    Almost always a data directory the server can't write to — worth telling
    the browser plainly, since no amount of retrying the request fixes it.
    """
    status = 403 if isinstance(exc, ReadOnlyStoreError) else 500
    hint = getattr(exc, "hint", None)
    body = f"{exc}\n\n{hint}" if hint else str(exc)
    return PlainTextResponse(body, status_code=status)


@app.get("/events")
async def events(request: Request):
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=8)
    request.app.state.subscribers.add(q)

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if msg == "__shutdown__":
                    return
                if await request.is_disconnected():
                    return
                yield f"event: change\ndata: {msg}\n\n"
        finally:
            request.app.state.subscribers.discard(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _csv_ints(value: str | None) -> list[int]:
    return [int(v) for v in _csv(value)]


def _active_planning_entries(cfg: Config, type_dir: str) -> list[Entry]:
    return [
        entry for entry in store.read_index(cfg, type_dir) if entry.status == "active"
    ]


def _relation_groups(cfg: Config, entry: Entry) -> list[dict]:
    labels = {
        "project_ids": "projects",
        "initiative_id": "initiative",
        "initiative_ids": "initiatives",
        "pitch_id": "pitch",
    }
    groups = []
    for relation_field in entries.RELATION_TARGET_TYPES.get(entry.type, {}):
        relations = [
            {"id": relation_id, "entry": target}
            for relation_id, target in zip(
                entries.relation_target_ids(entry, relation_field),
                entries.resolve_relations(cfg, entry, relation_field),
                strict=True,
            )
        ]
        if relations:
            groups.append({"label": labels[relation_field], "relations": relations})
    return groups


def _context(request: Request, **extra) -> dict:
    cfg = load_config()
    active = projects.get_active_project(cfg)
    ctx = {
        "request": request,
        "active_project": active,
        "all_types": list(ALL_TYPES),
    }
    ctx.update(extra)
    return ctx


# --- dashboard -------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    cfg = load_config()
    active = projects.get_active_project(cfg)
    today = journal.current_day(cfg)
    journal_body = journal.read_body(cfg, today)
    journal_preview = _first_lines(journal_body, 8)

    open_todos = query.search(
        cfg,
        query.SearchFilters(
            types=["todos"],
            status="open",
            project=active,
            limit=10,
            fulltext=False,
        ),
    )
    recent = query.list_recent(cfg, project=active, limit=10)
    tag_counter = tags_mod.tag_frequency(cfg)
    top_tags = tag_counter.most_common(12)
    project_stats = projects.list_projects(cfg)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        _context(
            request,
            today=today,
            journal_preview=journal_preview,
            open_todos=open_todos,
            recent=recent,
            top_tags=top_tags,
            project_stats=project_stats,
        ),
    )


# --- journal -----------------------------------------------------------------


def _parse_day(day: str) -> date:
    try:
        return date.fromisoformat(day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad date") from exc


def _load_past_days(cfg: Config, before: date, limit: int) -> list[dict]:
    """Walk backward from `before` collecting up to `limit` days that have content."""
    days: list[dict] = []
    cursor = before
    for _ in range(limit):
        prev = journal.previous_day_with_content(cfg, cursor)
        if prev is None:
            break
        days.append({"day": prev, "body": journal.read_body(cfg, prev)})
        cursor = prev
    return days


@app.get("/journal", response_class=HTMLResponse)
def journal_root(request: Request):
    cfg = load_config()
    active = projects.get_active_project(cfg)
    today = journal.current_day(cfg)
    journal.get_or_create_day(cfg, today, project=active)
    today_body = journal.read_body(cfg, today)
    past_days = _load_past_days(cfg, today, PAST_DAYS_PAGE)
    has_more = (
        bool(past_days)
        and journal.previous_day_with_content(cfg, past_days[-1]["day"]) is not None
    )
    next_before = past_days[-1]["day"].isoformat() if past_days else today.isoformat()
    job = request.app.state.parse_job
    job_is_live = job is not None and job.day == today and job.status == "running"
    active_job = job if job_is_live else None
    return templates.TemplateResponse(
        request,
        "journal.html",
        _context(
            request,
            mode="running",
            today=today,
            today_body=today_body,
            past_days=past_days,
            has_more=has_more,
            next_before=next_before,
            limit=PAST_DAYS_PAGE,
            job=active_job,
        ),
    )


@app.get("/journal/days", response_class=HTMLResponse)
def journal_days(
    request: Request,
    before: str = Query(...),
    limit: int = Query(PAST_DAYS_PAGE),
):
    cfg = load_config()
    before_day = _parse_day(before)
    past_days = _load_past_days(cfg, before_day, limit)
    has_more = (
        bool(past_days)
        and journal.previous_day_with_content(cfg, past_days[-1]["day"]) is not None
    )
    next_before = past_days[-1]["day"].isoformat() if past_days else before
    return templates.TemplateResponse(
        request,
        "_journal_day_section.html",
        _context(
            request,
            past_days=past_days,
            has_more=has_more,
            next_before=next_before,
            limit=limit,
        ),
    )


@app.get("/journal/{day}", response_class=HTMLResponse)
def journal_day(request: Request, day: str):
    cfg = load_config()
    d = _parse_day(day)
    today = journal.current_day(cfg)
    if d == today:
        return RedirectResponse(url="/journal", status_code=302)
    journal.get_or_create_day(cfg, d, project=projects.get_active_project(cfg))
    body = journal.read_body(cfg, d)
    return templates.TemplateResponse(
        request,
        "journal.html",
        _context(
            request,
            mode="permalink",
            day=d,
            body=body,
            next_day=d + timedelta(days=1),
            prior_day=d - timedelta(days=1),
        ),
    )


@app.put("/api/journal/{day}")
def api_journal_save(day: str, body: str = Form("")):
    cfg = load_config()
    d = _parse_day(day)
    journal.replace_body(cfg, d, body, project=projects.get_active_project(cfg))
    return Response(status_code=204)


@app.post("/api/journal/{day}/parse", response_class=HTMLResponse)
async def api_journal_parse(request: Request, day: str, body: str = Form("")):
    cfg = load_config()
    d = _parse_day(day)

    existing: ParseJob | None = request.app.state.parse_job
    if existing is not None and existing.status == "running":
        raise HTTPException(status_code=409, detail="a parse job is already running")

    # Flush the editor buffer (EasyMDE swallows some autosave triggers) before
    # snapshotting the day for parsing. Only reached once we know a rejected
    # (409) request will not have mutated the day file.
    journal.replace_body(cfg, d, body, project=projects.get_active_project(cfg))

    if not claude_cli.is_available():
        bin_name = claude_cli.configured_bin_name()
        job = ParseJob(
            day=d,
            status="error",
            error=str(claude_cli.ClaudeUnavailableError(bin_name)),
        )
        request.app.state.parse_job = job
        return templates.TemplateResponse(
            request, "_parse_status.html", _context(request, job=job)
        )

    job = ParseJob(day=d)
    request.app.state.parse_job = job

    def _progress(project: str, status: str) -> None:
        if project not in job.progress:
            job.order.append(project)
        job.progress[project] = status

    async def _runner() -> None:
        try:
            job.result = await digest.run_parse(cfg, d, progress=_progress)
            job.status = "done"
        except Exception as exc:  # surfaced to the user via the status fragment
            job.status = "error"
            hint = getattr(exc, "hint", None)
            job.error = f"{exc}\n{hint}" if hint else str(exc)

    request.app.state.parse_task = asyncio.create_task(_runner())
    return templates.TemplateResponse(
        request, "_parse_status.html", _context(request, job=job)
    )


@app.get("/journal/{day}/parse-status", response_class=HTMLResponse)
def journal_parse_status(request: Request, day: str):
    d = _parse_day(day)
    job: ParseJob | None = request.app.state.parse_job
    active = job if job is not None and job.day == d else None
    response = templates.TemplateResponse(
        request, "_parse_status.html", _context(request, job=active)
    )
    if active is None or active.status != "running":
        response.status_code = 286
        response.headers["HX-Trigger"] = "parse-done"
    return response


@app.get("/api/journal/{day}/body", response_class=PlainTextResponse)
def api_journal_body(day: str):
    cfg = load_config()
    d = _parse_day(day)
    return PlainTextResponse(journal.read_body(cfg, d))


@app.post("/api/journal/close", response_class=HTMLResponse)
def api_journal_close():
    cfg = load_config()
    journal.close_today(cfg, project=projects.get_active_project(cfg))
    return HTMLResponse(
        headers={"HX-Redirect": "/journal"},
        content="",
    )


# --- capture ---------------------------------------------------------------


@app.get("/capture", response_class=HTMLResponse)
def capture_get(
    request: Request,
    type: str | None = None,
    title: str | None = None,
):
    cfg = load_config()
    tag_counter = tags_mod.tag_frequency(cfg)
    project_stats = projects.list_projects(cfg)
    all_projects = [p.name for p in project_stats if p.name != "(none)"]
    all_areas = sorted({p.area for p in project_stats if p.area})
    registered_projects = [
        p for p in store.read_index(cfg, "projects") if p.state != "archived"
    ]
    return templates.TemplateResponse(
        request,
        "capture.html",
        _context(
            request,
            top_tags=[t for t, _ in tag_counter.most_common(20)],
            all_projects=all_projects,
            all_areas=all_areas,
            preset_type=type or "",
            preset_title=title or "",
            project_states=list(PROJECT_STATES),
            registered_projects=registered_projects,
            active_initiatives=_active_planning_entries(cfg, "initiatives"),
            active_pitches=_active_planning_entries(cfg, "pitches"),
        ),
    )


@app.post("/capture")
def capture_post(  # noqa: PLR0912, PLR0913, PLR0917 -- one Form field per entry attribute; splitting adds indirection
    entry_type: str = Form(...),
    title: str = Form(...),
    body: str = Form(""),
    tags: str = Form(""),
    project: str = Form(""),
    summary: str = Form(""),
    description: str = Form(""),
    state: str = Form(""),
    area: str = Form(""),
    local_dir: str = Form(""),
    tech_stack: str = Form(""),
    status: str = Form(""),
    project_ids: str = Form(""),
    initiative_ids: str = Form(""),
    initiative_id: str = Form(""),
    pitch_id: str = Form(""),
    qa_result: str = Form(""),
    qa_verified_at: str = Form(""),
    qa_run_ref: str = Form(""),
    source_path: str = Form(""),
):
    cfg = load_config()
    active = projects.get_active_project(cfg)
    type_fields: dict = {}
    effective_project: str | None
    if entry_type == "project":
        # A project entry does not belong to itself; ignore any submitted project value
        # and let entries.create_entry enforce project=None.
        effective_project = None
        for key, raw in (
            ("description", description),
            ("state", state),
            ("area", area),
            ("local_dir", local_dir),
        ):
            if raw.strip():
                type_fields[key] = raw.strip()
        tech_list = _csv(tech_stack)
        if tech_list:
            type_fields["tech_stack"] = tech_list
    else:
        effective_project = project.strip() or active or None
        if entry_type in {"initiative", "pitch"}:
            effective_project = None
    if status.strip():
        type_fields["status"] = status.strip()
    elif entry_type in {"initiative", "pitch"}:
        type_fields["status"] = "active"
    try:
        project_id_values = _csv_ints(project_ids)
        initiative_id_values = _csv_ints(initiative_ids)
        if project_id_values and entry_type not in {"initiative", "pitch"}:
            raise ValueError(  # noqa: TRY301
                "related project IDs are only valid for initiatives and pitches"
            )
        if initiative_id_values and entry_type != "pitch":
            raise ValueError(  # noqa: TRY301
                "related initiative IDs are only valid for pitches"
            )
        if project_id_values:
            type_fields["project_ids"] = project_id_values
        if initiative_id_values:
            type_fields["initiative_ids"] = initiative_id_values
        if initiative_id.strip():
            initiative_value = int(initiative_id.strip())
            if entry_type == "pitch":
                type_fields.setdefault("initiative_ids", []).append(initiative_value)
            elif entry_type == "todo":
                type_fields["initiative_id"] = initiative_value
            else:
                raise ValueError(  # noqa: TRY301
                    "initiative ID is only valid for todos and pitches"
                )
        if pitch_id.strip():
            if entry_type != "todo":
                raise ValueError(  # noqa: TRY301
                    "pitch ID is only valid for todos"
                )
            type_fields["pitch_id"] = int(pitch_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for key, value in {
        "qa_result": qa_result,
        "qa_verified_at": qa_verified_at,
        "qa_run_ref": qa_run_ref,
        "source_path": source_path,
    }.items():
        if value.strip():
            type_fields[key] = value.strip()
    try:
        result = entries.create_entry(
            cfg,
            entry_type,
            title,
            body,
            tags=_csv(tags),
            project=effective_project,
            summary=summary or None,
            type_fields=type_fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/entries/{result.entry.id}", status_code=303)


# --- entries ---------------------------------------------------------------


@app.get("/entries", response_class=HTMLResponse)
def entries_list(  # noqa: PLR0913, PLR0917 -- one query param per filter; splitting adds indirection
    request: Request,
    q: str | None = None,
    type: str | None = None,
    project: str | None = None,
    status: str = "all",
    tag: str | None = None,
    all_projects: bool = Query(False, alias="all"),
    project_id: int | None = None,
    initiative_id: int | None = None,
    pitch_id: int | None = None,
    related_id: int | None = None,
    related_type: str | None = None,
):
    cfg = load_config()
    active = projects.get_active_project(cfg)
    proj_filter = None if all_projects else (project or active)
    filters = query.SearchFilters(
        q=q or None,
        types=[type] if type else [],
        project=proj_filter,
        status=cast(StatusFilter, status),
        tags=[tag] if tag else [],
        project_id=project_id,
        initiative_id=initiative_id,
        pitch_id=pitch_id,
        related_id=related_id,
        related_type=related_type,
        limit=0
        if status
        in {
            "active",
            "pending",
            "in-progress",
            "in-qa",
            "postponed",
            "cancelled",
        }
        else 100,
    )

    hits = query.search(cfg, filters)
    if status in {
        "active",
        "pending",
        "in-progress",
        "in-qa",
        "postponed",
        "cancelled",
    }:
        hits = [h for h in hits if h.entry.status == status]
        hits = hits[:100]
    all_projects_list = [
        p.name for p in projects.list_projects(cfg) if p.name != "(none)"
    ]
    return templates.TemplateResponse(
        request,
        "entries.html",
        _context(
            request,
            hits=hits,
            q=q or "",
            type=type or "",
            project=project or "",
            status=status,
            tag=tag or "",
            all_projects_flag=all_projects,
            all_projects_list=all_projects_list,
            project_id=project_id,
            initiative_id=initiative_id,
            pitch_id=pitch_id,
            related_id=related_id,
            related_type=related_type or "",
        ),
    )


@app.get("/initiatives", response_class=HTMLResponse)
def initiatives_list(request: Request):
    return _planning_list(request, "initiative", "initiatives")


@app.get("/pitches", response_class=HTMLResponse)
def pitches_list(request: Request):
    return _planning_list(request, "pitch", "pitches")


def _planning_list(request: Request, entry_type: str, title: str):
    cfg = load_config()
    hits = [
        hit
        for hit in query.search(
            cfg,
            query.SearchFilters(types=[entry_type], status="all", limit=100),
        )
        if hit.entry.status == "active"
    ]
    all_projects_list = [
        p.name for p in projects.list_projects(cfg) if p.name != "(none)"
    ]
    return templates.TemplateResponse(
        request,
        "entries.html",
        _context(
            request,
            hits=hits,
            q="",
            type=entry_type,
            project="",
            status="all",
            tag="",
            all_projects_flag=True,
            all_projects_list=all_projects_list,
            index_title=title,
            project_id=None,
            initiative_id=None,
            pitch_id=None,
            related_id=None,
            related_type="",
        ),
    )


@app.get("/entries/{entry_id}", response_class=HTMLResponse)
def entry_view(request: Request, entry_id: int):
    cfg = load_config()
    found = entries.find_by_id(cfg, entry_id)
    if not found:
        raise HTTPException(status_code=404)
    type_dir, entry = found
    full_path = store.full_path_for(cfg, type_dir, entry.file_path)
    _, md_body = store.read_markdown(full_path)
    _heading, authored, _ = entries.split_body(md_body)
    relation_groups = _relation_groups(cfg, entry)
    backlinks = (
        query.related_entries(cfg, entry.type, entry.id)
        if entry.type in {"initiative", "pitch"}
        else []
    )
    return templates.TemplateResponse(
        request,
        "entry_view.html",
        _context(
            request,
            entry=entry,
            body=authored,
            type_dir=type_dir,
            relation_groups=relation_groups,
            backlinks=backlinks,
        ),
    )


@app.get("/entries/{entry_id}/edit", response_class=HTMLResponse)
def entry_edit(request: Request, entry_id: int):
    cfg = load_config()
    found = entries.find_by_id(cfg, entry_id)
    if not found:
        raise HTTPException(status_code=404)
    type_dir, entry = found
    full_path = store.full_path_for(cfg, type_dir, entry.file_path)
    _, md_body = store.read_markdown(full_path)
    _, authored, _ = entries.split_body(md_body)
    planning = {
        "initiatives": _active_planning_entries(cfg, "initiatives"),
        "pitches": _active_planning_entries(cfg, "pitches"),
    }
    return templates.TemplateResponse(
        request,
        "entry_edit.html",
        _context(
            request,
            entry=entry,
            body=authored,
            type_dir=type_dir,
            registered_projects=[
                p for p in store.read_index(cfg, "projects") if p.state != "archived"
            ],
            active_initiatives=planning["initiatives"],
            active_pitches=planning["pitches"],
        ),
    )


@app.post("/api/entries/{entry_id}", response_class=HTMLResponse)
async def api_entry_update(  # noqa: PLR0912, PLR0913, PLR0917 -- one Form field per editable attribute; splitting adds indirection
    request: Request,
    entry_id: int,
    title: str | None = Form(None),
    summary: str | None = Form(None),
    tags: str | None = Form(None),
    project: str | None = Form(None),
    status: str | None = Form(None),
    area: str | None = Form(None),
    body: str | None = Form(None),
    initiative_id: str | None = Form(None),
    pitch_id: str | None = Form(None),
    project_ids: str | None = Form(None),
    initiative_ids: str | None = Form(None),
    qa_result: str | None = Form(None),
    qa_verified_at: str | None = Form(None),
    qa_run_ref: str | None = Form(None),
    source_path: str | None = Form(None),
):
    form = await request.form()
    cfg = load_config()
    patch: dict = {}
    if title is not None:
        patch["title"] = title
    if summary is not None:
        patch["summary"] = summary
    if tags is not None:
        patch["tags"] = _csv(tags)
    if project is not None:
        patch["project"] = project.strip() or None
    if status is not None:
        patch["status"] = status
    if area is not None:
        patch["area"] = area.strip() or None
    for key, raw in {
        "initiative_id": initiative_id,
        "pitch_id": pitch_id,
        "qa_result": qa_result,
        "qa_verified_at": qa_verified_at,
        "qa_run_ref": qa_run_ref,
        "source_path": source_path,
    }.items():
        if raw is not None or key in form:
            if key in {"initiative_id", "pitch_id"}:
                try:
                    patch[key] = int(raw) if raw and raw.strip() else None
                except ValueError as exc:
                    raise HTTPException(
                        status_code=400, detail="relation IDs must be integers"
                    ) from exc
            else:
                patch[key] = raw.strip() or None if raw else None
    for key, raw in {
        "project_ids": project_ids,
        "initiative_ids": initiative_ids,
    }.items():
        if raw is not None or key in form:
            try:
                patch[key] = _csv_ints(raw)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="relation IDs must be integers"
                ) from exc
    entries.update_entry(cfg, entry_id, patch, body=body)
    return HTMLResponse(headers={"HX-Redirect": f"/entries/{entry_id}"}, content="")


@app.post("/api/entries/{entry_id}/done", response_class=HTMLResponse)
def api_entry_done(entry_id: int):
    cfg = load_config()
    entries.mark_done(cfg, entry_id)
    return HTMLResponse(headers={"HX-Refresh": "true"}, content="")


@app.delete("/api/entries/{entry_id}", response_class=HTMLResponse)
def api_entry_delete(entry_id: int):
    cfg = load_config()
    entries.delete_entry(cfg, entry_id)
    return HTMLResponse(headers={"HX-Redirect": "/entries"}, content="")


# --- todos ------------------------------------------------------------------


_TODO_SORT_KEYS = {
    "id": lambda h: h.entry.id,
    "date": lambda h: h.entry.created_at or "",
    "status": lambda h: h.entry.status or "",
    "project": lambda h: (h.entry.project or "").lower(),
    "title": lambda h: (h.entry.title or "").lower(),
    "tags": lambda h: ", ".join(h.entry.tags).lower(),
}


@app.get("/todos", response_class=HTMLResponse)
def todos_list(  # noqa: PLR0913, PLR0917 -- one query param per filter; splitting adds indirection
    request: Request,
    q: str | None = None,
    project: str | None = None,
    tag: str | None = None,
    sort: str = "date",
    direction: str = Query("desc", alias="dir"),
    show_all: bool = Query(False, alias="all"),
    show_postponed: bool = Query(False, alias="postponed"),
):
    cfg = load_config()
    # No active-project focus here: /todos is a cross-project view that
    # defaults to the most recent todos regardless of project.
    hits = query.search(
        cfg,
        query.SearchFilters(
            q=q or None,
            types=["todos"],
            project=project or None,
            tags=[tag] if tag else [],
            status="all" if show_all else "open",
            limit=500,
            fulltext=False,
        ),
    )
    # Postponed todos are hidden unless explicitly requested. "open" already
    # keeps them (they're not done), so filter them out in Python.
    if not show_postponed:
        hits = [h for h in hits if h.entry.status != "postponed"]
    groups: dict[str, list[query.Hit]] = {}
    for h in hits:
        groups.setdefault(h.entry.project or "(none)", []).append(h)
    grouped = sorted(groups.items(), key=lambda kv: kv[0].lower())

    sort = sort if sort in _TODO_SORT_KEYS else "date"
    # Unrecognized dir falls back to the default (desc), matching the sort fallback.
    descending = direction != "asc"
    rows = sorted(hits, key=_TODO_SORT_KEYS[sort], reverse=descending)

    return templates.TemplateResponse(
        request,
        "todos.html",
        _context(
            request,
            grouped=grouped,
            rows=rows,
            total=len(hits),
            q=q or "",
            selected=project or "",
            tag=tag or "",
            sort=sort,
            dir="desc" if descending else "asc",
            show_all=show_all,
            show_postponed=show_postponed,
        ),
    )


# --- projects --------------------------------------------------------------


@app.get("/projects", response_class=HTMLResponse)
def projects_list(request: Request):
    cfg = load_config()
    stats = projects.list_projects(cfg)
    return templates.TemplateResponse(
        request, "projects.html", _context(request, project_stats=stats)
    )


@app.get("/projects/{name}", response_class=HTMLResponse)
def project_detail(request: Request, name: str):
    cfg = load_config()
    stats = projects.project_stats(cfg, name)
    project_entry = projects.find_project_entry(cfg, name)
    open_todos = query.search(
        cfg,
        query.SearchFilters(types=["todos"], project=name, status="open", limit=50),
    )
    recent = query.list_recent(cfg, project=name, limit=20)
    related = projects.related_work(cfg, project_entry.id) if project_entry else []
    # list_recent / search already scope to project by title match, and project
    # entries have project=None so they naturally drop out — no extra filtering.
    return templates.TemplateResponse(
        request,
        "project_detail.html",
        _context(
            request,
            project=stats,
            project_entry=project_entry,
            open_todos=open_todos,
            recent=recent,
            related_work=related,
        ),
    )


@app.post("/api/project/focus", response_class=HTMLResponse)
def api_project_focus(name: str = Form("")):
    cfg = load_config()
    projects.set_active_project(cfg, name or None)
    return HTMLResponse(headers={"HX-Refresh": "true"}, content="")


# --- tags ------------------------------------------------------------------


@app.get("/tags", response_class=HTMLResponse)
def tags_view(request: Request):
    cfg = load_config()
    counter = tags_mod.tag_frequency(cfg)
    return templates.TemplateResponse(
        request, "tags.html", _context(request, tag_counts=counter.most_common())
    )


# --- helpers ---------------------------------------------------------------


def _first_lines(text: str, n: int) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:n])
