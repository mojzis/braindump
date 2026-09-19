"""Typed application operations shared by interactive clients.

The core package owns persistence and validation.  This module owns the
application contract: callers provide request objects and receive domain
objects, without needing to know about indexes, markdown files, or CLI
formatting.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from braindump.core import entries, journal, projects, query, store, tags
from braindump.core.config import Config
from braindump.core.errors import BraindumpError, MutuallyExclusiveBodyUpdateError
from braindump.core.query import PresenceFilter, SortDirection, SortField, StatusFilter
from braindump.core.schema import ALL_TYPE_DIRS, Entry


@dataclass(frozen=True)
class CreateRequest:
    """Input for creating an entry through an application adapter."""

    entry_type: str
    title: str
    body: str = ""
    tags: tuple[str, ...] = ()
    project: str | None = None
    summary: str | None = None
    original_input: str | None = None
    branch: str | None = None
    type_fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchRequest:
    """Structured list/search filters, independent of a presentation layer."""

    query: str | None = None
    types: tuple[str, ...] = ()
    project: str | None = None
    all_projects: bool = False
    status: StatusFilter = "all"
    tags: tuple[str, ...] = ()
    since: date | None = None
    until: date | None = None
    limit: int = 50
    offset: int = 0
    fulltext: bool = True
    project_id: int | None = None
    initiative_id: int | None = None
    pitch_id: int | None = None
    priority: str | None = None
    presence: PresenceFilter | None = None
    coverage: str | None = None
    related_id: int | None = None
    related_type: str | None = None
    branch: str | None = None
    sort: SortField = "date"
    direction: SortDirection = "desc"


@dataclass(frozen=True)
class UpdateRequest:
    """Input for metadata, whole-body, or ordered partial-body updates."""

    entry_id: int
    patch: Mapping[str, Any] = field(default_factory=dict)
    body: str | None = None
    edits: tuple[Mapping[str, str], ...] | None = None
    body_revision: str | None = None


@dataclass(frozen=True)
class EntryView:
    """An index entry together with its authored markdown body."""

    entry: Entry
    type_dir: str
    body: str

    @property
    def body_revision(self) -> str:
        return entries.body_revision(self.body)

    def to_json(self) -> dict[str, Any]:
        data = self.entry.to_index_json()
        data["body"] = self.body
        data["body_revision"] = self.body_revision
        return data


class AmbiguousTodoError(BraindumpError):
    """A query matched more than one open todo."""

    def __init__(self, query_text: str, matches: Iterable[query.Hit]) -> None:
        self.query_text = query_text
        self.matches = tuple(matches)
        super().__init__(
            f"{query_text!r} matches {len(self.matches)} open todos — pass an id"
        )


class BraindumpService:
    """Application service backed by one configured braindump store."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def create(self, request: CreateRequest) -> entries.CreateResult:
        store.ensure_type_dirs(self.cfg)
        type_fields = dict(request.type_fields)
        if request.branch is not None:
            type_fields["branch"] = request.branch
        return entries.create_entry(
            self.cfg,
            request.entry_type,
            request.title,
            request.body,
            tags=list(request.tags),
            project=request.project,
            summary=request.summary,
            original_input=request.original_input,
            type_fields=type_fields,
        )

    create_entry = create

    def search(self, request: SearchRequest) -> list[query.Hit]:
        project = (
            None if request.all_projects else self._effective_project(request.project)
        )
        filters = query.SearchFilters(
            q=request.query,
            types=list(request.types),
            project=project,
            status=request.status,
            tags=list(request.tags),
            since=request.since,
            until=request.until,
            limit=request.limit,
            offset=request.offset,
            fulltext=request.fulltext,
            project_id=request.project_id,
            initiative_id=request.initiative_id,
            pitch_id=request.pitch_id,
            priority=request.priority,
            presence=request.presence,
            coverage=request.coverage,
            related_id=request.related_id,
            related_type=request.related_type,
            branch=request.branch,
            sort=request.sort,
            direction=request.direction,
        )
        return query.search(self.cfg, filters)

    def list_entries(self, request: SearchRequest) -> list[query.Hit]:
        """List entries using the same filter contract as search."""
        return self.search(replace(request, query=None, fulltext=False))

    def get_entry(self, entry_id: int) -> EntryView | None:
        found = entries.find_by_id(self.cfg, entry_id)
        if found is None:
            return None
        type_dir, entry = found
        return self._entry_view(type_dir, entry)

    def get_entries(self, entry_ids: Iterable[int]) -> dict[int, EntryView]:
        requested = set(entry_ids)
        found: dict[int, EntryView] = {}
        for type_dir in ALL_TYPE_DIRS:
            for entry in store.read_index(self.cfg, type_dir):
                if entry.id in requested:
                    found[entry.id] = self._entry_view(type_dir, entry)
        return found

    show = get_entries

    def update(self, request: UpdateRequest) -> Any:
        if request.edits is not None:
            if request.body is not None:
                raise MutuallyExclusiveBodyUpdateError
            return entries.update_entry_partial(
                self.cfg,
                request.entry_id,
                dict(request.patch),
                edits=list(request.edits),
                body_revision=request.body_revision,
            )
        return entries.update_entry(
            self.cfg, request.entry_id, dict(request.patch), body=request.body
        )

    update_entry = update

    def done(self, arg: int | str) -> Entry:
        entry_id = arg if isinstance(arg, int) else self.resolve_todo(arg)
        return entries.mark_done(self.cfg, entry_id)

    mark_done = done

    def resolve_todo(self, arg: str) -> int:
        if arg.isdigit():
            return int(arg)
        if arg.endswith(".md") or "/" in arg:
            found = entries.find_by_file_path(self.cfg, arg, "todos")
            if found:
                return found[1].id
            raise BraindumpError(f"no todo found with file path: {arg}")
        hits = query.search(
            self.cfg,
            query.SearchFilters(
                q=arg, types=["todos"], status="open", limit=5, fulltext=False
            ),
        )
        if not hits:
            raise BraindumpError(f"no open todos found for: {arg}")
        if len(hits) > 1:
            raise AmbiguousTodoError(arg, hits)
        return hits[0].entry.id

    def project_list(self) -> list[projects.ProjectStats]:
        return projects.list_projects(self.cfg)

    def project_stats(self, name: str) -> projects.ProjectStats:
        return projects.project_stats(self.cfg, name)

    def get_active_project(self) -> str | None:
        return projects.get_active_project(self.cfg)

    def set_active_project(self, name: str | None) -> None:
        projects.set_active_project(self.cfg, name)

    def tag_frequency(self) -> Counter[str]:
        return tags.tag_frequency(self.cfg)

    def entries_with_tag(self, tag: str) -> list[tuple[str, int, str]]:
        return tags.entries_with_tag(self.cfg, tag)

    def journal_today(self) -> tuple[date, Entry, str]:
        day = journal.current_day(self.cfg)
        entry = journal.get_or_create_day(self.cfg, day)
        return day, entry, journal.read_body(self.cfg, day)

    def journal_append(self, text: str, target_day: date | None = None) -> Entry:
        day = target_day or journal.current_day(self.cfg)
        return journal.append_text(self.cfg, day, text)

    def journal_close(self) -> Entry:
        return journal.close_today(self.cfg)

    def journal_show(self, day: date) -> str:
        return journal.read_body(self.cfg, day)

    def _effective_project(self, explicit: str | None) -> str | None:
        return explicit if explicit is not None else self.get_active_project()

    def _entry_view(self, type_dir: str, entry: Entry) -> EntryView:
        full_path = store.full_path_for(self.cfg, type_dir, entry.file_path)
        body = ""
        if full_path.exists():
            _, markdown_body = store.read_markdown(full_path)
            _, body, _ = entries.split_body(markdown_body)
        return EntryView(entry=entry, type_dir=type_dir, body=body)


__all__ = [
    "AmbiguousTodoError",
    "BraindumpService",
    "CreateRequest",
    "EntryView",
    "SearchRequest",
    "UpdateRequest",
]
