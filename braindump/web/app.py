"""FastAPI app for the braindump local UI.

Routes are server-rendered Jinja + htmx. No JS framework, no build step.
Everything speaks to `braindump.core.*` — the same code the CLI uses — so there
is one source of truth for the data.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from watchfiles import Change, awatch

from braindump.core import entries, journal, projects, query, store, tags as tags_mod
from braindump.core.config import load_config
from braindump.core.schema import ALL_TYPES, PROJECT_STATES, type_to_dir


BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _watch_filter(change: Change, path: str) -> bool:
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
    app.state.subscribers: set[asyncio.Queue[str]] = set()
    stop = asyncio.Event()
    app.state.watch_stop = stop
    log = logging.getLogger("braindump.web")

    async def watcher() -> None:
        while not stop.is_set():
            try:
                async for _changes in awatch(
                    cfg.home, watch_filter=_watch_filter, stop_event=stop
                ):
                    for q in list(app.state.subscribers):
                        try:
                            q.put_nowait("reload")
                        except asyncio.QueueFull:
                            pass
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
        for q in list(app.state.subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait("__shutdown__")
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Braindump", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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
                except asyncio.TimeoutError:
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


def _csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


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


# --- journal ---------------------------------------------------------------


@app.get("/journal", response_class=HTMLResponse)
def journal_root(request: Request):
    cfg = load_config()
    d = journal.current_day(cfg)
    return RedirectResponse(url=f"/journal/{d.isoformat()}", status_code=302)


@app.get("/journal/{day}", response_class=HTMLResponse)
def journal_day(request: Request, day: str):
    cfg = load_config()
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="bad date")
    journal.get_or_create_day(cfg, d, project=projects.get_active_project(cfg))
    body = journal.read_body(cfg, d)
    prev_day = journal.previous_day_with_content(cfg, d)
    prev_body = journal.read_body(cfg, prev_day) if prev_day else ""
    is_today = d == journal.current_day(cfg)
    return templates.TemplateResponse(
        request,
        "journal_day.html",
        _context(
            request,
            day=d,
            body=body,
            prev_day=prev_day,
            prev_body=prev_body,
            is_today=is_today,
            next_day=d + timedelta(days=1),
            prior_day=d - timedelta(days=1),
        ),
    )


@app.put("/api/journal/{day}")
def api_journal_save(day: str, body: str = Form("")):
    cfg = load_config()
    d = date.fromisoformat(day)
    journal.replace_body(cfg, d, body, project=projects.get_active_project(cfg))
    return Response(status_code=204)


@app.post("/api/journal/close", response_class=HTMLResponse)
def api_journal_close():
    cfg = load_config()
    entry = journal.close_today(cfg, project=projects.get_active_project(cfg))
    target = entry.date or journal.current_day(cfg).isoformat()
    return HTMLResponse(
        headers={"HX-Redirect": f"/journal/{target}"},
        content="",
    )


# --- capture ---------------------------------------------------------------


@app.get("/capture", response_class=HTMLResponse)
def capture_get(
    request: Request,
    type: Optional[str] = None,
    title: Optional[str] = None,
):
    cfg = load_config()
    tag_counter = tags_mod.tag_frequency(cfg)
    all_projects = [p.name for p in projects.list_projects(cfg) if p.name != "(none)"]
    return templates.TemplateResponse(
        request,
        "capture.html",
        _context(
            request,
            top_tags=[t for t, _ in tag_counter.most_common(20)],
            all_projects=all_projects,
            preset_type=type or "",
            preset_title=title or "",
            project_states=list(PROJECT_STATES),
        ),
    )


@app.post("/capture")
def capture_post(
    entry_type: str = Form(...),
    title: str = Form(...),
    body: str = Form(""),
    tags: str = Form(""),
    project: str = Form(""),
    summary: str = Form(""),
    description: str = Form(""),
    state: str = Form(""),
    local_dir: str = Form(""),
    tech_stack: str = Form(""),
):
    cfg = load_config()
    active = projects.get_active_project(cfg)
    type_fields: dict = {}
    effective_project: Optional[str]
    if entry_type == "project":
        # A project entry does not belong to itself; ignore any submitted project value
        # and let entries.create_entry enforce project=None.
        effective_project = None
        for key, raw in (
            ("description", description),
            ("state", state),
            ("local_dir", local_dir),
        ):
            if raw.strip():
                type_fields[key] = raw.strip()
        tech_list = _csv(tech_stack)
        if tech_list:
            type_fields["tech_stack"] = tech_list
    else:
        effective_project = project.strip() or active or None
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
    return RedirectResponse(
        url=f"/entries/{result.entry.id}", status_code=303
    )


# --- entries ---------------------------------------------------------------


@app.get("/entries", response_class=HTMLResponse)
def entries_list(
    request: Request,
    q: Optional[str] = None,
    type: Optional[str] = None,
    project: Optional[str] = None,
    status: str = "all",
    tag: Optional[str] = None,
    all_projects: bool = Query(False, alias="all"),
):
    cfg = load_config()
    active = projects.get_active_project(cfg)
    proj_filter = None if all_projects else (project or active)
    filters = query.SearchFilters(
        q=q or None,
        types=[type] if type else [],
        project=proj_filter,
        status=status,  # type: ignore[arg-type]
        tags=[tag] if tag else [],
        limit=100,
    )
    hits = query.search(cfg, filters)
    all_projects_list = [p.name for p in projects.list_projects(cfg) if p.name != "(none)"]
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
    heading, authored, _ = entries.split_body(md_body)
    return templates.TemplateResponse(
        request,
        "entry_view.html",
        _context(
            request,
            entry=entry,
            body=authored,
            type_dir=type_dir,
        ),
    )


@app.post("/api/entries/{entry_id}", response_class=HTMLResponse)
def api_entry_update(
    request: Request,
    entry_id: int,
    title: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    body: Optional[str] = Form(None),
):
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
    entries.update_entry(cfg, entry_id, patch, body=body)
    return HTMLResponse(headers={"HX-Refresh": "true"}, content="")


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


# --- projects --------------------------------------------------------------


@app.get("/projects", response_class=HTMLResponse)
def projects_list(request: Request):
    cfg = load_config()
    stats = projects.list_projects(cfg)
    return templates.TemplateResponse(request, "projects.html", _context(request, project_stats=stats))


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
    return templates.TemplateResponse(request, "tags.html", _context(request, tag_counts=counter.most_common()))


# --- helpers ---------------------------------------------------------------


def _first_lines(text: str, n: int) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:n])
