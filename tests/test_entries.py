from __future__ import annotations

from datetime import datetime

import pytest

from braindump.core import entries, store


def _fake_now() -> datetime:
    return datetime(2026, 4, 11, 14, 15)


@pytest.fixture
def created_todo(cfg):
    r = entries.create_entry(
        cfg,
        "todos",
        "Fix auth bug",
        "Details about the bug.",
        tags=["auth", "bug"],
        project="braindump",
        summary="Fixes the login flow",
        type_fields={"status": "pending", "subtype": "code", "priority": "high"},
        original_input="raw user text",
        now=_fake_now(),
    )
    return r


def test_created_todo_identity_and_path(created_todo):
    r = created_todo
    assert r.entry.id == 1
    assert r.entry.file_path.startswith("2026/04/fix-auth-bug--")
    assert r.full_path.exists()


def test_created_todo_authored_content(created_todo):
    text = created_todo.full_path.read_text()
    assert "# Fix auth bug" in text
    assert "Details about the bug." in text
    assert "<details>" in text
    assert "raw user text" in text


def test_created_todo_frontmatter(created_todo):
    text = created_todo.full_path.read_text()
    assert 'tags: ["auth", "bug"]' in text
    assert "status: pending" in text
    assert "summary" not in text.split("---", 2)[1]


def test_created_todo_index_metadata(created_todo, cfg):
    stored = store.read_index(cfg, "todos")
    assert len(stored) == 1
    assert stored[0].summary == "Fixes the login flow"
    assert stored[0].status == "pending"


def test_pitch_priority_and_coverage_round_trip_and_validation(cfg):
    result = entries.create_entry(
        cfg,
        "pitch",
        "Launch pitch",
        "body",
        type_fields={"priority": "high", "coverage": "partial"},
        now=_fake_now(),
    )

    assert (result.entry.priority, result.entry.coverage) == ("high", "partial")
    text = result.full_path.read_text()
    assert "priority: high" in text
    assert "coverage: partial" in text
    assert store.read_index(cfg, "pitches")[0].coverage == "partial"

    with pytest.raises(ValueError, match="pitch priority"):
        entries.create_entry(
            cfg, "pitch", "bad priority", "body", type_fields={"priority": "urgent"}
        )
    with pytest.raises(ValueError, match="pitch coverage"):
        entries.create_entry(
            cfg, "pitch", "bad coverage", "body", type_fields={"coverage": "unknown"}
        )
    with pytest.raises(ValueError, match="only valid for pitches"):
        entries.create_entry(
            cfg, "todo", "bad coverage", "body", type_fields={"coverage": "partial"}
        )
    with pytest.raises(ValueError, match="only valid for todos and pitches"):
        entries.create_entry(
            cfg, "til", "bad priority", "body", type_fields={"priority": "urgent"}
        )


def test_parse_source_document_tracks_headings_and_checked_items():
    items = entries.parse_source_document(
        "- [ ] first\n## Alpha\n* second\n- [x] finished\n"
    )

    assert [(item.text, item.heading, item.checked) for item in items] == [
        ("first", None, False),
        ("second", "Alpha", False),
        ("finished", "Alpha", True),
    ]


def test_create_til_sets_category(cfg):
    r = entries.create_entry(
        cfg,
        "til",
        "Something learned",
        "I learned a thing.",
        tags=["python"],
        project="braindump",
        type_fields={"category": "programming", "source": "docs"},
        now=_fake_now(),
    )
    assert r.entry.category == "programming"
    assert r.entry.source == "docs"


@pytest.fixture
def renamed_todo(cfg):
    r = entries.create_entry(
        cfg, "todos", "old title", "body", tags=["a"], project="p", now=_fake_now()
    )
    updated = entries.update_entry(
        cfg, r.entry.id, {"title": "new title", "tags": ["b"]}
    )
    return r, updated


def test_update_returns_renamed_todo(renamed_todo):
    _, updated = renamed_todo
    assert updated.title == "new title"
    assert updated.tags == ["b"]


def test_update_rewrites_todo_markdown(renamed_todo):
    r, _ = renamed_todo
    text = r.full_path.read_text()
    assert "title: new title" in text
    assert "# new title" in text
    assert 'tags: ["b"]' in text


def test_update_rewrites_todo_index(renamed_todo, cfg):
    stored = store.read_index(cfg, "todos")
    assert stored[0].title == "new title"
    assert stored[0].tags == ["b"]
    assert stored[0].updated_at is not None


@pytest.mark.parametrize(
    ("entry_type", "type_dir"), (("todo", "todos"), ("pitch", "pitches"))
)
def test_update_preserves_unchanged_legacy_priority(cfg, entry_type, type_dir):
    result = entries.create_entry(
        cfg,
        entry_type,
        "Legacy priority",
        "body",
        type_fields={"priority": "high"},
        now=_fake_now(),
    )
    result.entry.priority = "urgent"
    store.rewrite_index_atomic(cfg, type_dir, [result.entry])

    renamed = entries.update_entry(cfg, result.entry.id, {"title": "Renamed"})
    unchanged = entries.update_entry(cfg, result.entry.id, {"priority": "urgent"})

    assert renamed.priority == "urgent"
    assert unchanged.priority == "urgent"
    assert "priority: urgent" in result.full_path.read_text()
    with pytest.raises(ValueError, match=f"{entry_type} priority"):
        entries.update_entry(cfg, result.entry.id, {"priority": "critical"})


def test_update_entry_replaces_body(cfg):
    r = entries.create_entry(
        cfg, "todos", "t", "old body content", project="p", now=_fake_now()
    )
    entries.update_entry(cfg, r.entry.id, {}, body="fresh new body content")
    text = r.full_path.read_text()
    assert "fresh new body content" in text
    assert "old body content" not in text


def test_partial_body_edits_replace_insert_delete_and_preserve_original(cfg):
    result = entries.create_entry(
        cfg,
        "todo",
        "partial",
        "alpha\nkeep\nomega",
        original_input="the original prompt",
        now=_fake_now(),
    )
    revision = entries.body_revision("alpha\nkeep\nomega")
    receipt = entries.update_entry_partial(
        cfg,
        result.entry.id,
        {},
        edits=[
            {"match": "alpha", "replacement": "ALPHA\ninserted"},
            {"match": "keep\n", "replacement": ""},
        ],
        body_revision=revision,
    )
    assert (receipt["entry_id"], receipt["edits_applied"]) == (result.entry.id, 2)
    assert entries.body_revision("ALPHA\ninserted\nomega") == receipt["body_revision"]
    text = result.full_path.read_text()
    assert (
        "ALPHA\ninserted\nomega" in text,
        "the original prompt" in text,
        store.read_index(cfg, "todos")[0].input == "the original prompt",
    ) == (True, True, True)


def test_partial_body_edits_are_atomic_and_report_edit_number(cfg):
    result = entries.create_entry(cfg, "todo", "partial", "one\ntwo", now=_fake_now())
    revision = entries.body_revision("one\ntwo")
    with pytest.raises(ValueError, match=r"edit 2: exact match not found"):
        entries.update_entry_partial(
            cfg,
            result.entry.id,
            {"title": "must not persist"},
            edits=[
                {"match": "one", "replacement": "ONE"},
                {"match": "missing", "replacement": "x"},
            ],
            body_revision=revision,
        )
    assert entries.split_body(store.read_markdown(result.full_path)[1])[1] == "one\ntwo"
    with pytest.raises(ValueError, match=r"edit 1: exact match is ambiguous"):
        entries.update_entry_partial(
            cfg,
            result.entry.id,
            {},
            edits=[{"match": "o", "replacement": "x"}],
            body_revision=revision,
        )


def test_partial_body_edit_rejects_stale_revision_and_preserves_file_only_frontmatter(
    cfg,
):
    result = entries.create_entry(cfg, "todo", "partial", "old", now=_fake_now())
    text = result.full_path.read_text().replace(
        "---\n\n# partial", "qa-note: keep me\n---\n\n# partial"
    )
    result.full_path.write_text(text)
    with pytest.raises(ValueError, match="stale body revision"):
        entries.update_entry_partial(
            cfg,
            result.entry.id,
            {},
            edits=[{"match": "old", "replacement": "new"}],
            body_revision=entries.body_revision("other"),
        )
    entries.update_entry_partial(
        cfg,
        result.entry.id,
        {},
        edits=[{"match": "old", "replacement": "new"}],
        body_revision=entries.body_revision("old"),
    )
    assert "qa-note: keep me" in result.full_path.read_text()


def test_update_entry_rejects_immutable_fields(cfg):
    r = entries.create_entry(cfg, "todos", "t", "b", project="p", now=_fake_now())
    with pytest.raises(ValueError):
        entries.update_entry(cfg, r.entry.id, {"id": 999})
    with pytest.raises(ValueError):
        entries.update_entry(cfg, r.entry.id, {"file_path": "x.md"})


def test_default_clock_file_path_uses_local_wall_clock(cfg):
    # With no explicit clock the filename / YYYY-MM path must track local
    # wall-clock, not UTC — the naming convention reads as "when I made it".
    before = datetime.now().astimezone()
    r = entries.create_entry(cfg, "todos", "local time", "b")
    after = datetime.now().astimezone()
    # both the directory and the --YYYY-MM-DD-HHmm stamp come from local now
    assert r.entry.file_path.startswith(before.strftime("%Y/%m/"))
    stamp = r.entry.file_path.rsplit("--", 1)[1].removesuffix(".md")
    assert before.strftime("%Y-%m-%d-%H%M") <= stamp <= after.strftime("%Y-%m-%d-%H%M")


def test_set_status_and_find_by_id(cfg):
    r = entries.create_entry(cfg, "todos", "t", "b", project="p", now=_fake_now())
    entries.set_status(cfg, r.entry.id, "done")
    found = entries.find_by_id(cfg, r.entry.id)
    assert found is not None
    _, entry = found
    assert entry.status == "done"


@pytest.fixture
def created_project(cfg, tmp_path):
    r = entries.create_entry(
        cfg,
        "project",
        "Alpha",
        "Alpha is a project for testing.",
        tags=["infra"],
        project="should-be-dropped",
        type_fields={
            "description": "The alpha project.",
            "state": "active",
            "local_dir": str(tmp_path / "alpha"),
            "tech_stack": ["python", "fastapi"],
        },
        now=_fake_now(),
    )
    return r


def test_project_does_not_belong_to_itself(created_project):
    assert created_project.entry.type == "project"
    assert created_project.entry.project is None


def test_project_index_metadata(created_project, cfg):
    stored = store.read_index(cfg, "projects")
    assert len(stored) == 1
    persisted = stored[0]
    assert persisted.title == "Alpha"
    assert persisted.description == "The alpha project."
    assert persisted.state == "active"


def test_project_index_location_and_stack(created_project, cfg, tmp_path):
    persisted = store.read_index(cfg, "projects")[0]
    assert persisted.local_dir == str(tmp_path / "alpha")
    assert persisted.tech_stack == ["python", "fastapi"]
    assert isinstance(persisted.tech_stack, list)
    assert persisted.project is None


def test_project_frontmatter_identity(created_project):
    text = created_project.full_path.read_text()
    assert "type: project" in text
    assert "description: The alpha project." in text
    assert "state: active" in text


def test_project_frontmatter_location_and_stack(created_project, tmp_path):
    text = created_project.full_path.read_text()
    assert f"local_dir: {tmp_path / 'alpha'}" in text
    assert 'tech_stack: ["python", "fastapi"]' in text


def test_project_lookup(created_project, cfg):
    found = entries.find_by_id(cfg, created_project.entry.id)
    assert found is not None
    _, entry = found
    assert entry.description == "The alpha project."
    assert entry.tech_stack == ["python", "fastapi"]
    assert entry.project is None


def test_project_title_none_forbidden(cfg):
    with pytest.raises(ValueError):
        entries.create_entry(
            cfg,
            "project",
            "(none)",
            "body",
            now=_fake_now(),
        )


def test_delete_entry_moves_file_to_trash(cfg):
    r = entries.create_entry(cfg, "todos", "t", "b", project="p", now=_fake_now())
    full = r.full_path
    entries.delete_entry(cfg, r.entry.id)
    assert not full.exists()
    assert store.read_index(cfg, "todos") == []
    trashed = list((cfg.trash_dir / "todos").rglob("*.md"))
    assert len(trashed) == 1


def test_create_drops_a_tag_that_repeats_the_project(cfg):
    """`project` already says it; the tag would only pollute tag analytics."""
    result = entries.create_entry(
        cfg,
        "todo",
        "Fix the parser",
        "body",
        tags=["braindump", "parser", "BRAINDUMP"],
        project="braindump",
        now=_fake_now(),
    )
    assert result.entry.tags == ["parser"]


def test_create_keeps_a_tag_naming_a_different_project(cfg):
    """Cross-references ("this introspect todo is about braindump") are real."""
    result = entries.create_entry(
        cfg,
        "todo",
        "Borrow the index format",
        "body",
        tags=["braindump", "schema"],
        project="introspect",
        now=_fake_now(),
    )
    assert result.entry.tags == ["braindump", "schema"]


def test_update_drops_the_tag_when_the_project_moves(cfg):
    r = entries.create_entry(
        cfg,
        "todo",
        "Fix the parser",
        "body",
        tags=["parser"],
        project="introspect",
        now=_fake_now(),
    )
    updated = entries.update_entry(cfg, r.entry.id, {"project": "parser"})
    assert updated.tags == []


@pytest.fixture
def created_handoff(cfg):
    result = entries.create_entry(
        cfg,
        "handoff",
        "Resume auth",
        "Continue investigating the token bug.",
        type_fields={"branch": "feature/auth"},
        now=_fake_now(),
    )

    return result


def test_handoff_identity_and_path(created_handoff):
    result = created_handoff
    assert result.entry.type == "handoff"
    assert result.entry.branch == "feature/auth"
    assert result.entry.file_path.startswith("2026/04/")
    assert "handoffs" in result.full_path.parts


def test_handoff_markdown_and_index(created_handoff, cfg):
    result = created_handoff
    assert "branch: feature/auth" in result.full_path.read_text()
    assert "Continue investigating the token bug." in result.full_path.read_text()
    assert store.read_index(cfg, "handoffs")[0].branch == "feature/auth"


def test_handoff_branch_clearing(created_handoff, cfg):
    result = created_handoff
    updated = entries.update_entry(cfg, result.entry.id, {"branch": None})
    assert updated.branch is None
    assert "branch:" not in result.full_path.read_text()


@pytest.fixture
def planning_graph(cfg, tmp_path):
    project = entries.create_entry(cfg, "project", "Alpha", "body", now=_fake_now())
    initiative = entries.create_entry(
        cfg,
        "initiative",
        "Launch initiative",
        "body",
        type_fields={"status": "active", "project_ids": [project.entry.id]},
        now=_fake_now(),
    )
    pitch = entries.create_entry(
        cfg,
        "pitch",
        "Launch pitch",
        "body",
        type_fields={
            "status": "active",
            "project_ids": [project.entry.id],
            "initiative_ids": [initiative.entry.id],
            "source_path": str(tmp_path / "source.md"),
        },
        now=_fake_now(),
    )
    todo = entries.create_entry(
        cfg,
        "todo",
        "Implement launch",
        "body",
        type_fields={
            "initiative_id": initiative.entry.id,
            "pitch_id": pitch.entry.id,
            "qa_result": "pass",
            "qa_verified_at": "2026-04-11T14:15:00Z",
            "qa_run_ref": "run-1",
        },
        now=_fake_now(),
    )

    return project, initiative, pitch, todo


def test_planning_graph_persists_relations(planning_graph, cfg):
    project, initiative, pitch, _ = planning_graph
    persisted = store.read_index(cfg, "pitches")[0]
    assert persisted.project_ids == [project.entry.id]
    assert persisted.initiative_ids == [initiative.entry.id]
    assert "project_ids: [1]" in pitch.full_path.read_text()
    assert store.read_index(cfg, "todos")[0].qa_run_ref == "run-1"


def test_planning_graph_resolves_initiative_links(planning_graph, cfg):
    _, initiative, _, todo = planning_graph
    persisted = store.read_index(cfg, "pitches")[0]
    related_initiative = entries.resolve_relations(cfg, persisted, "initiative_ids")[0]
    assert related_initiative is not None
    assert related_initiative.id == initiative.entry.id
    todo_initiative = entries.resolve_relations(cfg, todo.entry, "initiative_id")[0]
    assert todo_initiative is not None
    assert todo_initiative.id == initiative.entry.id


def test_typed_relation_validation_rejects_wrong_type_and_missing(cfg):
    project = entries.create_entry(cfg, "project", "Alpha", "body", now=_fake_now())
    with pytest.raises(ValueError, match="existing initiative"):
        entries.create_entry(
            cfg,
            "todo",
            "bad",
            "body",
            type_fields={"initiative_id": project.entry.id},
            now=_fake_now(),
        )
    with pytest.raises(ValueError, match="existing project"):
        entries.create_entry(
            cfg,
            "initiative",
            "bad",
            "body",
            type_fields={"project_ids": [999]},
            now=_fake_now(),
        )
    todo = entries.create_entry(cfg, "todo", "needs link", "body", now=_fake_now())
    with pytest.raises(ValueError, match="existing initiative"):
        entries.update_entry(cfg, todo.entry.id, {"initiative_id": project.entry.id})
    # Rejected writes do not consume a global ID.
    assert store.next_id(cfg) == 3


def test_update_rejects_relations_unsupported_by_entry_type(cfg):
    todo = entries.create_entry(cfg, "todo", "needs link", "body", now=_fake_now())

    with pytest.raises(ValueError, match="not valid for todo"):
        entries.update_entry(cfg, todo.entry.id, {"project_ids": [999]})

    persisted = store.read_index(cfg, "todos")[0]
    assert persisted.project_ids is None


def test_relation_survives_project_rename_and_deleted_target_resolves_missing(cfg):
    project = entries.create_entry(cfg, "project", "Alpha", "body", now=_fake_now())
    initiative = entries.create_entry(
        cfg,
        "initiative",
        "I",
        "body",
        type_fields={"project_ids": [project.entry.id]},
        now=_fake_now(),
    )
    entries.update_entry(cfg, project.entry.id, {"title": "Renamed"})
    current = store.read_index(cfg, "initiatives")[0]
    related_project = entries.resolve_relations(cfg, current, "project_ids")[0]
    assert related_project is not None
    assert related_project.title == "Renamed"
    entries.delete_entry(cfg, project.entry.id)
    assert entries.resolve_relations(cfg, current, "project_ids") == [None]
    updated = entries.update_entry(cfg, initiative.entry.id, {"title": "I renamed"})
    assert updated.title == "I renamed"


def test_new_todos_default_to_pending(cfg):
    result = entries.create_entry(cfg, "todo", "New work", "body", now=_fake_now())

    assert result.entry.status == "pending"
    assert store.read_index(cfg, "todos")[0].status == "pending"


@pytest.mark.parametrize(
    ("result", "status"), [("pass", "done"), ("FAIL", "in-progress")]
)
def test_record_qa_result_stores_receipt_and_transitions_todo(cfg, result, status):
    todo = entries.create_entry(
        cfg,
        "todo",
        "QA me",
        "body",
        type_fields={"status": "in-qa"},
        now=_fake_now(),
    )

    updated = entries.record_qa_result(
        cfg,
        todo.entry.id,
        result,
        run_ref="run-42",
        now=datetime(2026, 4, 11, 15, 16),
    )

    assert (
        updated.qa_result,
        updated.qa_verified_at,
        updated.qa_run_ref,
        updated.status,
    ) == (result.lower(), "2026-04-11T15:16:00Z", "run-42", status)
    persisted = store.read_index(cfg, "todos")[0]
    assert persisted.qa_result == result.lower()
    assert persisted.status == status


def test_record_qa_result_can_omit_run_reference(cfg):
    todo = entries.create_entry(
        cfg, "todo", "QA me", "body", type_fields={"status": "in-qa"}
    )

    updated = entries.record_qa_result(cfg, todo.entry.id, "pass")

    assert updated.status == "done"
    assert updated.qa_verified_at
    assert updated.qa_run_ref is None


@pytest.fixture
def imported_pitch(cfg, tmp_path):
    project = entries.create_entry(cfg, "project", "Alpha", "body", now=_fake_now())
    initiative = entries.create_entry(
        cfg, "initiative", "Launch", "body", now=_fake_now()
    )
    source = tmp_path / "launch.md"
    source.write_text(
        """---
type: pitch
title: Launch proposal
summary: A durable proposal
tags: ["planning", "launch"]
status: active
---
# Launch proposal

Keep this authored body exactly.

## Decision

Preserve this heading too.
"""
    )

    result = entries.import_pitch(
        cfg,
        source,
        project_ids=[project.entry.id],
        initiative_ids=[initiative.entry.id],
    )

    return result, source, project, initiative


def test_pitch_import_verifies(imported_pitch, cfg):
    result, _, _, _ = imported_pitch
    assert result.verified
    assert entries.verify_pitch_import(cfg, result) == []


def test_pitch_import_preserves_source_metadata(imported_pitch):
    result, source, _, _ = imported_pitch
    assert result.entry is not None
    assert result.entry.title == "Launch proposal"
    assert result.entry.source_path == str(source.resolve())


def test_pitch_import_links_planning_graph(imported_pitch):
    result, _, project, initiative = imported_pitch
    assert result.entry is not None
    assert result.entry.project_ids == [project.entry.id]
    assert result.entry.initiative_ids == [initiative.entry.id]


def test_pitch_import_preserves_authored_markdown(imported_pitch):
    result, _, _, _ = imported_pitch
    assert result.full_path is not None
    imported_markdown = result.full_path.read_text()
    assert "Keep this authored body exactly." in imported_markdown
    assert "type: pitch" in imported_markdown
    assert "summary: A durable proposal" not in imported_markdown


def test_pitch_import_dry_run_writes_nothing_and_validates_relations(cfg, tmp_path):
    project = entries.create_entry(cfg, "project", "Alpha", "body", now=_fake_now())
    source = tmp_path / "draft.md"
    source.write_text("# Draft\n\nBody\n")

    result = entries.import_pitch(
        cfg, source, project_ids=[project.entry.id], dry_run=True
    )

    assert result.entry is None
    assert store.read_index(cfg, "pitches") == []
    assert not (cfg.home / "pitches" / "index.jsonl").read_text().strip()
    assert store.next_id(cfg) == 2


def test_pitch_source_removal_requires_confirmation_and_provenance(cfg, tmp_path):
    source = tmp_path / "draft.md"
    source.write_text("# Draft\n\nBody\n")
    entries.import_pitch(cfg, source)

    with pytest.raises(ValueError, match="explicit confirmation"):
        entries.remove_pitch_source(cfg, source)
    assert source.exists()

    removed = entries.remove_pitch_source(cfg, source, confirmed=True)
    assert removed == source.resolve()
    assert not source.exists()
