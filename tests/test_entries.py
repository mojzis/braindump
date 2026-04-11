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
    assert "summary" not in text.split("---", 2)[1]  # summary lives in JSONL, not frontmatter

    stored = store.read_index(cfg, "todos")
    assert len(stored) == 1
    assert stored[0].summary == "Fixes the login flow"
    assert stored[0].status == "pending"


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
    updated = entries.update_entry(cfg, r.entry.id, {"title": "new title", "tags": ["b"]})
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
