"""Contract tests for the application service adapter."""

from __future__ import annotations

from datetime import date

import pytest
from typer.testing import CliRunner

from braindump.cli.main import app
from braindump.service import (
    BraindumpService,
    CreateRequest,
    SearchRequest,
    UpdateRequest,
)


@pytest.fixture
def service_handoff(cfg):
    service = BraindumpService(cfg)
    created = service.create(
        CreateRequest(
            entry_type="handoff",
            title="Service handoff",
            body="Service body",
            branch="feature/service",
        )
    )

    return service, created


def test_service_handoff_show_and_branch_filter(service_handoff):
    service, created = service_handoff
    view = service.get_entry(created.entry.id)
    assert view is not None
    assert view.body == "Service body"
    assert view.entry.branch == "feature/service"
    assert [
        hit.entry.id
        for hit in service.search(
            SearchRequest(types=("handoff",), branch="feature/service")
        )
    ] == [created.entry.id]


def test_service_updates_handoff_branch(service_handoff):
    service, created = service_handoff
    updated = service.update(UpdateRequest(created.entry.id, {"branch": "release"}))
    assert updated.branch == "release"


@pytest.fixture
def service_todo(cfg):
    service = BraindumpService(cfg)
    created = service.create(
        CreateRequest(
            entry_type="todo",
            title="Service contract todo",
            body="Auth body",
            tags=("auth",),
            project="braindump",
            type_fields={"status": "pending"},
        )
    )

    return service, created


def test_service_todo_show_includes_body(service_todo):
    service, created = service_todo
    view = service.get_entry(created.entry.id)
    assert view is not None
    assert view.entry.title == "Service contract todo"
    assert view.body == "Auth body"
    assert view.to_json()["body"] == "Auth body"


def test_service_todo_list_and_search(service_todo):
    service, created = service_todo
    listed = service.list_entries(
        SearchRequest(project="braindump", status="pending", limit=10)
    )
    assert [hit.entry.id for hit in listed] == [created.entry.id]
    searched = service.search(
        SearchRequest(query="Service contract", project="braindump")
    )
    assert [hit.entry.id for hit in searched] == [created.entry.id]


def test_service_todo_update_and_done(service_todo):
    service, created = service_todo
    updated = service.update(
        UpdateRequest(
            entry_id=created.entry.id,
            patch={"title": "Updated service todo"},
            body="Updated body",
        )
    )
    assert updated.title == "Updated service todo"
    assert service.done(created.entry.id).status == "done"


def test_service_project_and_tag_operations(cfg):
    service = BraindumpService(cfg)
    project = service.create(CreateRequest(entry_type="project", title="Alpha"))
    service.create(
        CreateRequest(
            entry_type="todo",
            title="Alpha task",
            project="Alpha",
            tags=("work",),
            type_fields={"status": "pending"},
        )
    )

    stats = service.project_stats("Alpha")
    assert stats.registered
    assert stats.open_todos == 1
    assert service.tag_frequency()["work"] == 1
    assert service.entries_with_tag("work")[0][1] != project.entry.id


def test_service_journal_append_and_show(cfg):
    service = BraindumpService(cfg)
    day = date(2026, 4, 11)
    journal_entry = service.journal_append("journal note", day)
    assert journal_entry.date == day.isoformat()
    assert service.journal_show(day) == "journal note"


@pytest.fixture
def service_pitches(cfg):
    service = BraindumpService(cfg)
    for title, priority, coverage in (
        ("Low unaudited", "low", None),
        ("Medium covered", "medium", "covered"),
        ("High unaudited", "high", None),
    ):
        type_fields = {"priority": priority}
        if coverage is not None:
            type_fields["coverage"] = coverage
        service.create(
            CreateRequest(
                entry_type="pitch",
                title=title,
                type_fields=type_fields,
            )
        )

    return service


def test_service_preserves_priority_coverage_filtering_and_sorting(service_pitches):
    service = service_pitches
    covered = service.search(SearchRequest(coverage="covered"))
    assert [hit.entry.title for hit in covered] == ["Medium covered"]

    unaudited = service.list_entries(
        SearchRequest(
            types=("pitch",),
            coverage="unaudited",
            sort="priority",
            direction="asc",
        )
    )
    assert [hit.entry.title for hit in unaudited] == [
        "High unaudited",
        "Low unaudited",
    ]


def test_cli_create_keeps_title_positional():
    result = CliRunner().invoke(app, ["create", "todo", "--tag", "cli"])
    assert result.exit_code != 0
    assert "{TYPE} {title}" in result.output
