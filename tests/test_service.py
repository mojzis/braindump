"""Contract tests for the application service adapter."""

from __future__ import annotations

from datetime import date

from typer.testing import CliRunner

from braindump.cli.main import app
from braindump.service import (
    BraindumpService,
    CreateRequest,
    SearchRequest,
    UpdateRequest,
)


def test_service_handoff_roundtrip_and_branch_filter(cfg):
    service = BraindumpService(cfg)
    created = service.create(
        CreateRequest(
            entry_type="handoff",
            title="Service handoff",
            body="Service body",
            branch="feature/service",
        )
    )

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

    updated = service.update(UpdateRequest(created.entry.id, {"branch": "release"}))
    assert updated.branch == "release"


def test_service_create_show_search_list_update_and_done(cfg):
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

    view = service.get_entry(created.entry.id)
    assert view is not None
    assert view.entry.title == "Service contract todo"
    assert view.body == "Auth body"
    assert view.to_json()["body"] == "Auth body"

    listed = service.list_entries(
        SearchRequest(project="braindump", status="pending", limit=10)
    )
    assert [hit.entry.id for hit in listed] == [created.entry.id]
    searched = service.search(
        SearchRequest(query="Service contract", project="braindump")
    )
    assert [hit.entry.id for hit in searched] == [created.entry.id]

    updated = service.update(
        UpdateRequest(
            entry_id=created.entry.id,
            patch={"title": "Updated service todo"},
            body="Updated body",
        )
    )
    assert updated.title == "Updated service todo"
    assert service.done(created.entry.id).status == "done"


def test_service_project_tag_and_journal_operations(cfg):
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

    day = date(2026, 4, 11)
    journal_entry = service.journal_append("journal note", day)
    assert journal_entry.date == day.isoformat()
    assert service.journal_show(day) == "journal note"


def test_service_preserves_priority_coverage_filtering_and_sorting(cfg):
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
