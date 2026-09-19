"""Stdio MCP adapter for the shared braindump application service."""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from braindump.core.config import load_config
from braindump.core.errors import BraindumpError
from braindump.core.query import (
    PresenceFilter,
    SortDirection,
    SortField,
    StatusFilter,
)
from braindump.service import (
    BraindumpService,
    CreateRequest,
    SearchRequest,
    UpdateRequest,
)

mcp = MCPServer(
    "Braindump",
    instructions="All tools use the same application service as the bd CLI.",
)

_READ = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
_MUTATION = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
_CREATE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
_APPEND = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _tool(
    *, name: str, description: str, annotations: ToolAnnotations
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Register an MCP tool whose anticipated failures reach the client verbatim.

    mcp 2.x hides the text of any exception other than ``ToolError`` behind a
    generic "Error executing tool <name>". Service validation failures
    (``BraindumpError``, ``ValueError``) are the caller's to read and correct,
    as the CLI reports them, so they are re-raised as ``ToolError``; anything
    else stays an opaque crash.
    """

    def decorate(fn: Callable[_P, _R]) -> Callable[_P, _R]:
        @functools.wraps(fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            try:
                return fn(*args, **kwargs)
            except (BraindumpError, ValueError) as exc:
                raise ToolError(str(exc)) from exc

        mcp.tool(name=name, description=description, annotations=annotations)(wrapper)
        return wrapper

    return decorate


def _jsonable(value: Any) -> Any:
    """Convert service domain values into MCP JSON-compatible values."""
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(exclude_none=True))
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (date, Path, Enum)):
        return value.value if isinstance(value, Enum) else str(value)
    return value


def _service() -> BraindumpService:
    return BraindumpService(load_config())


def _search_request(
    *,
    query: str | None = None,
    types: list[str] | None = None,
    project: str | None = None,
    all_projects: bool = False,
    status: StatusFilter = "all",
    tags: list[str] | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = 50,
    offset: int = 0,
    fulltext: bool = True,
    project_id: int | None = None,
    initiative_id: int | None = None,
    pitch_id: int | None = None,
    priority: str | None = None,
    presence: str | None = None,
    coverage: str | None = None,
    related_id: int | None = None,
    related_type: str | None = None,
    branch: str | None = None,
    sort: SortField = "date",
    direction: SortDirection = "desc",
) -> SearchRequest:
    return SearchRequest(
        query=query,
        types=tuple(types or ()),
        project=project,
        all_projects=all_projects,
        status=status,
        tags=tuple(tags or ()),
        since=since,
        until=until,
        limit=limit,
        offset=offset,
        fulltext=fulltext,
        project_id=project_id,
        initiative_id=initiative_id,
        pitch_id=pitch_id,
        priority=priority,
        presence=cast(PresenceFilter, presence),
        coverage=coverage,
        related_id=related_id,
        related_type=related_type,
        branch=branch,
        sort=sort,
        direction=direction,
    )


@_tool(
    name="create",
    description="Create an entry through the shared braindump service.",
    annotations=_CREATE,
)
def create(
    entry_type: str,
    title: str,
    body: str = "",
    tags: list[str] | None = None,
    project: str | None = None,
    summary: str | None = None,
    original_input: str | None = None,
    branch: str | None = None,
    type_fields: dict[str, Any] | None = None,
    presence: str | None = None,
) -> dict[str, Any]:
    fields = dict(type_fields or {})
    if presence is not None:
        fields["presence"] = presence
    result = _service().create(
        CreateRequest(
            entry_type=entry_type,
            title=title,
            body=body,
            tags=tuple(tags or ()),
            project=project,
            summary=summary,
            original_input=original_input,
            branch=branch,
            type_fields=fields,
        )
    )
    return _jsonable(result)


@_tool(
    name="show",
    description=(
        "Show entries by numeric ID, including authored markdown bodies and a "
        "body_revision. Pass that revision to update for ordered partial edits."
    ),
    annotations=_READ,
)
def show(ids: list[int]) -> dict[str, Any]:
    service = _service()
    found = service.get_entries(ids)
    return {
        "entries": [
            {
                "entry": _jsonable(found[entry_id].entry),
                "type_dir": found[entry_id].type_dir,
                "body": found[entry_id].body,
                "body_revision": found[entry_id].body_revision,
            }
            for entry_id in ids
            if entry_id in found
        ],
        "missing_ids": [entry_id for entry_id in ids if entry_id not in found],
    }


@_tool(
    name="search",
    description="Search entries with the same filters as bd search.",
    annotations=_READ,
)
def search(
    query: str | None = None,
    types: list[str] | None = None,
    project: str | None = None,
    all_projects: bool = False,
    status: StatusFilter = "all",
    tags: list[str] | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = 50,
    offset: int = 0,
    fulltext: bool = True,
    project_id: int | None = None,
    initiative_id: int | None = None,
    pitch_id: int | None = None,
    priority: str | None = None,
    presence: str | None = None,
    coverage: str | None = None,
    related_id: int | None = None,
    related_type: str | None = None,
    branch: str | None = None,
    sort: SortField = "date",
    direction: SortDirection = "desc",
) -> list[dict[str, Any]]:
    hits = _service().search(
        _search_request(
            query=query,
            types=types,
            project=project,
            all_projects=all_projects,
            status=status,
            tags=tags,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
            fulltext=fulltext,
            project_id=project_id,
            initiative_id=initiative_id,
            pitch_id=pitch_id,
            priority=priority,
            presence=presence,
            coverage=coverage,
            related_id=related_id,
            related_type=related_type,
            branch=branch,
            sort=sort,
            direction=direction,
        )
    )
    return [_jsonable(hit) for hit in hits]


@_tool(
    name="list",
    description="List entries with the same filters as bd list.",
    annotations=_READ,
)
def list_entries(
    types: list[str] | None = None,
    project: str | None = None,
    all_projects: bool = False,
    status: StatusFilter = "all",
    tags: list[str] | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = 10,
    offset: int = 0,
    project_id: int | None = None,
    initiative_id: int | None = None,
    pitch_id: int | None = None,
    priority: str | None = None,
    presence: str | None = None,
    coverage: str | None = None,
    related_id: int | None = None,
    related_type: str | None = None,
    branch: str | None = None,
    sort: SortField = "date",
    direction: SortDirection = "desc",
) -> list[dict[str, Any]]:
    hits = _service().list_entries(
        _search_request(
            types=types,
            project=project,
            all_projects=all_projects,
            status=status,
            tags=tags,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
            fulltext=False,
            project_id=project_id,
            initiative_id=initiative_id,
            pitch_id=pitch_id,
            priority=priority,
            presence=presence,
            coverage=coverage,
            related_id=related_id,
            related_type=related_type,
            branch=branch,
            sort=sort,
            direction=direction,
        )
    )
    return [_jsonable(hit) for hit in hits]


@_tool(
    name="clear_presence",
    description="Clear a todo's presence classification without changing other fields.",
    annotations=_MUTATION,
)
def clear_presence(entry_id: int) -> dict[str, Any]:
    return _jsonable(_service().update(UpdateRequest(entry_id, {"presence": None})))


@_tool(
    name="update",
    description=(
        "Patch metadata or replace the authored body. For partial edits, pass "
        "body_revision from show and edits=[{match, replacement}] in order; "
        "each exact match must occur once. body and edits are mutually exclusive. "
        "Partial updates return a compact receipt without the body."
    ),
    annotations=_MUTATION,
)
def update(
    entry_id: int,
    patch: dict[str, Any],
    body: str | None = None,
    edits: list[dict[str, str]] | None = None,
    body_revision: str | None = None,
) -> dict[str, Any]:
    return _jsonable(
        _service().update(
            UpdateRequest(
                entry_id,
                patch,
                body,
                tuple(edits) if edits is not None else None,
                body_revision,
            )
        )
    )


@_tool(
    name="done",
    description="Mark a todo done by ID, file path, or unique open-todo query.",
    annotations=_MUTATION,
)
def done(arg: int | str) -> dict[str, Any]:
    return _jsonable(_service().done(arg))


@_tool(
    name="project_context",
    description="Return the current active project context.",
    annotations=_READ,
)
def project_context() -> dict[str, Any]:
    return {"active_project": _service().get_active_project()}


@_tool(
    name="project_list",
    description="List projects and their aggregate entry statistics.",
    annotations=_READ,
)
def project_list() -> list[dict[str, Any]]:
    return [_jsonable(item) for item in _service().project_list()]


@_tool(
    name="project_show",
    description="Show aggregate statistics and metadata for one project.",
    annotations=_READ,
)
def project_show(name: str) -> dict[str, Any]:
    return _jsonable(_service().project_stats(name))


@_tool(
    name="project_focus",
    description="Set, inspect, or clear the active project filter.",
    annotations=_MUTATION,
)
def project_focus(name: str | None = None, clear: bool = False) -> dict[str, Any]:
    service = _service()
    if clear:
        service.set_active_project(None)
    elif name is not None:
        service.set_active_project(name)
    return {"active_project": service.get_active_project()}


@_tool(
    name="tag_stats",
    description="Return tag frequencies across all indexed entries.",
    annotations=_READ,
)
def tag_stats() -> dict[str, int]:
    return dict(_service().tag_frequency())


@_tool(
    name="tag_show",
    description="List entries carrying a tag.",
    annotations=_READ,
)
def tag_show(tag: str) -> list[dict[str, Any]]:
    return [
        {"type": entry_type, "id": entry_id, "title": title}
        for entry_type, entry_id, title in _service().entries_with_tag(tag)
    ]


@_tool(
    name="journal_today",
    description="Ensure today's journal exists and return its body and metadata.",
    annotations=_MUTATION,
)
def journal_today() -> dict[str, Any]:
    day, entry, body = _service().journal_today()
    return {"day": day.isoformat(), "entry": _jsonable(entry), "body": body}


@_tool(
    name="journal_append",
    description="Append text to a journal day, defaulting to the logical current day.",
    annotations=_APPEND,
)
def journal_append(text: str, target_day: str | None = None) -> dict[str, Any]:
    day = date.fromisoformat(target_day) if target_day else None
    return _jsonable(_service().journal_append(text, day))


@_tool(
    name="journal_close",
    description="Close the logical current journal day and open the next one.",
    annotations=_MUTATION,
)
def journal_close() -> dict[str, Any]:
    return _jsonable(_service().journal_close())


@_tool(
    name="journal_show",
    description="Read the authored body for a journal day.",
    annotations=_READ,
)
def journal_show(day: str) -> dict[str, str]:
    parsed = date.fromisoformat(day)
    return {"day": day, "body": _service().journal_show(parsed)}


def main() -> None:
    """Run the packaged stdio server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()


__all__ = ["main", "mcp"]
