from __future__ import annotations

from datetime import datetime

import pytest

from braindump.core import entries, store


def _fake_now() -> datetime:
    return datetime(2026, 4, 11, 14, 15)


def test_create_todo_round_trip(cfg):
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
    assert r.entry.id == 1
    assert r.entry.file_path.startswith("2026/04/fix-auth-bug--")
    assert r.full_path.exists()

    text = r.full_path.read_text()
    assert "# Fix auth bug" in text
    assert "Details about the bug." in text
    assert "<details>" in text
    assert "raw user text" in text
    assert 'tags: ["auth", "bug"]' in text
    assert "status: pending" in text
    # summary lives in JSONL, not frontmatter
    assert "summary" not in text.split("---", 2)[1]

    stored = store.read_index(cfg, "todos")
    assert len(stored) == 1
    assert stored[0].summary == "Fixes the login flow"
    assert stored[0].status == "pending"


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


def test_update_entry_rewrites_title_and_index(cfg):
    r = entries.create_entry(
        cfg, "todos", "old title", "body", tags=["a"], project="p", now=_fake_now()
    )
    updated = entries.update_entry(
        cfg, r.entry.id, {"title": "new title", "tags": ["b"]}
    )
    assert updated.title == "new title"
    assert updated.tags == ["b"]
    text = r.full_path.read_text()
    assert "title: new title" in text
    assert "# new title" in text
    assert 'tags: ["b"]' in text
    stored = store.read_index(cfg, "todos")
    assert stored[0].title == "new title"
    assert stored[0].tags == ["b"]
    assert stored[0].updated_at is not None


def test_update_entry_replaces_body(cfg):
    r = entries.create_entry(
        cfg, "todos", "t", "old body content", project="p", now=_fake_now()
    )
    entries.update_entry(cfg, r.entry.id, {}, body="fresh new body content")
    text = r.full_path.read_text()
    assert "fresh new body content" in text
    assert "old body content" not in text


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


def test_create_project_entry_roundtrip(cfg):
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
            "local_dir": "/tmp/alpha",
            "tech_stack": ["python", "fastapi"],
        },
        now=_fake_now(),
    )
    assert r.entry.type == "project"
    # project entries never belong to a project themselves
    assert r.entry.project is None

    stored = store.read_index(cfg, "projects")
    assert len(stored) == 1
    persisted = stored[0]
    assert persisted.title == "Alpha"
    assert persisted.description == "The alpha project."
    assert persisted.state == "active"
    assert persisted.local_dir == "/tmp/alpha"
    assert persisted.tech_stack == ["python", "fastapi"]
    assert isinstance(persisted.tech_stack, list)
    assert persisted.project is None

    text = r.full_path.read_text()
    assert "type: project" in text
    assert "description: The alpha project." in text
    assert "state: active" in text
    assert "local_dir: /tmp/alpha" in text
    assert 'tech_stack: ["python", "fastapi"]' in text

    found = entries.find_by_id(cfg, r.entry.id)
    assert found is not None
    _, e = found
    assert e.description == "The alpha project."
    assert e.tech_stack == ["python", "fastapi"]
    assert e.project is None


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


def test_planning_graph_round_trip_and_typed_relations(cfg):
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
            "source_path": "/tmp/source.md",
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

    persisted = store.read_index(cfg, "pitches")[0]
    assert persisted.project_ids == [project.entry.id]
    assert persisted.initiative_ids == [initiative.entry.id]
    assert "project_ids: [1]" in pitch.full_path.read_text()
    assert store.read_index(cfg, "todos")[0].qa_run_ref == "run-1"
    assert (
        entries.resolve_relations(cfg, persisted, "initiative_ids")[0].id
        == initiative.entry.id
    )
    assert (
        entries.resolve_relations(cfg, todo.entry, "initiative_id")[0].id
        == initiative.entry.id
    )


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
    assert entries.resolve_relations(cfg, current, "project_ids")[0].title == "Renamed"
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

    assert updated.qa_result == result.lower()
    assert updated.qa_verified_at == "2026-04-11T15:16:00Z"
    assert updated.qa_run_ref == "run-42"
    assert updated.status == status
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


def test_pitch_import_preserves_source_intent_and_verifies(cfg, tmp_path):
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

    assert result.verified
    assert result.entry is not None
    assert result.entry.title == "Launch proposal"
    assert result.entry.source_path == str(source.resolve())
    assert result.entry.project_ids == [project.entry.id]
    assert result.entry.initiative_ids == [initiative.entry.id]
    assert "Keep this authored body exactly." in result.full_path.read_text()
    assert "type: pitch" in result.full_path.read_text()
    assert "summary: A durable proposal" not in result.full_path.read_text()
    assert entries.verify_pitch_import(cfg, result) == []


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
