from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from braindump.core import entries, store
from braindump.web.app import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _set_home(monkeypatch, cfg) -> None:
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    monkeypatch.setenv("BRAINDUMP_DAY_CUTOFF", str(cfg.day_cutoff_hour))


async def _request(monkeypatch, cfg, method: str, url: str, **kwargs):
    _set_home(monkeypatch, cfg)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        return await client.request(method, url, **kwargs)


@pytest.mark.anyio
async def test_graph_capture_edit_and_details(monkeypatch, cfg):
    project = entries.create_entry(
        cfg, "project", "Alpha", "body", now=datetime(2026, 4, 11, 10)
    )
    initiative = entries.create_entry(
        cfg,
        "initiative",
        "Launch",
        "body",
        type_fields={"status": "active", "project_ids": [project.entry.id]},
        now=datetime(2026, 4, 11, 11),
    )
    pitch = entries.create_entry(
        cfg,
        "pitch",
        "Pitch",
        "body",
        type_fields={
            "status": "active",
            "priority": "high",
            "coverage": "partial",
            "project_ids": [project.entry.id],
            "initiative_ids": [initiative.entry.id],
        },
        now=datetime(2026, 4, 11, 12),
    )

    capture = await _request(
        monkeypatch,
        cfg,
        "GET",
        "/capture?type=pitch",
    )
    assert capture.status_code == 200
    assert f'value="{initiative.entry.id}"' in capture.text
    assert (
        f'value="{pitch.entry.id}"' in capture.text or "active_pitches" in capture.text
    )
    assert "prioritySelect.disabled = !priorityApplies" in capture.text
    assert "coverageSelect.disabled = !coverageApplies" in capture.text

    todo = entries.create_entry(
        cfg,
        "todo",
        "Implement",
        "body",
        type_fields={"initiative_id": initiative.entry.id, "pitch_id": pitch.entry.id},
        now=datetime(2026, 4, 11, 13),
    )
    detail = await _request(monkeypatch, cfg, "GET", f"/entries/{todo.entry.id}")
    assert detail.status_code == 200
    assert f'href="/entries/{initiative.entry.id}"' in detail.text
    assert f'href="/entries/{pitch.entry.id}"' in detail.text

    edit = await _request(monkeypatch, cfg, "GET", f"/entries/{pitch.entry.id}/edit")
    assert edit.status_code == 200
    assert "project_ids" in edit.text
    assert "initiative_ids" in edit.text
    assert "coverage" in edit.text
    assert "partial" in edit.text

    pitch_detail = await _request(monkeypatch, cfg, "GET", f"/entries/{pitch.entry.id}")
    assert "priority high" in pitch_detail.text
    assert "coverage partial" in pitch_detail.text

    capture_post = await _request(
        monkeypatch,
        cfg,
        "POST",
        "/capture",
        data={
            "entry_type": "pitch",
            "title": "Captured pitch",
            "priority": "low",
            "coverage": "uncovered",
        },
    )
    assert capture_post.status_code == 303
    captured = store.read_index(cfg, "pitches")[-1]
    assert captured.priority == "low"
    assert captured.coverage == "uncovered"

    bad = await _request(
        monkeypatch,
        cfg,
        "POST",
        f"/api/entries/{pitch.entry.id}",
        data={"coverage": "invalid"},
    )
    assert bad.status_code == 400

    updated = await _request(
        monkeypatch,
        cfg,
        "POST",
        f"/api/entries/{todo.entry.id}",
        data={"initiative_id": str(initiative.entry.id), "pitch_id": ""},
    )
    assert updated.status_code == 200
    updated_todo = entries.find_by_id(cfg, todo.entry.id)
    assert updated_todo is not None
    assert updated_todo[1].pitch_id is None

    initiative_index = await _request(monkeypatch, cfg, "GET", "/initiatives")
    assert "Launch" in initiative_index.text
    done_initiative = entries.update_entry(cfg, initiative.entry.id, {"status": "done"})
    assert done_initiative.status == "done"
    initiative_index = await _request(monkeypatch, cfg, "GET", "/initiatives")
    assert "Launch" not in initiative_index.text

    project_page = await _request(monkeypatch, cfg, "GET", "/projects/Alpha")
    assert project_page.status_code == 200
    assert f"/entries/{initiative.entry.id}" in project_page.text
    assert f"/entries/{pitch.entry.id}" in project_page.text


@pytest.mark.anyio
async def test_pitch_lists_sort_priority_and_filter_unaudited(monkeypatch, cfg):
    entries.create_entry(
        cfg,
        "pitch",
        "Low audited pitch",
        "body",
        type_fields={"status": "active", "priority": "low", "coverage": "partial"},
        now=datetime(2026, 4, 11, 12),
    )
    entries.create_entry(
        cfg,
        "pitch",
        "High unaudited pitch",
        "body",
        type_fields={"status": "active", "priority": "high"},
        now=datetime(2026, 4, 11, 11),
    )

    pitches = await _request(monkeypatch, cfg, "GET", "/pitches?sort=priority&dir=asc")
    generic = await _request(
        monkeypatch,
        cfg,
        "GET",
        "/entries?type=pitch&sort=priority&dir=asc&all=1",
    )
    filtered = await _request(
        monkeypatch,
        cfg,
        "GET",
        "/entries?type=pitch&coverage=unaudited&sort=priority&dir=asc&all=1",
    )
    default_form = await _request(
        monkeypatch,
        cfg,
        "GET",
        "/entries?type=pitch&priority=&coverage=&all=1",
    )
    priority_with_blank_coverage = await _request(
        monkeypatch,
        cfg,
        "GET",
        "/entries?type=pitch&priority=high&coverage=&all=1",
    )
    unaudited_with_blank_priority = await _request(
        monkeypatch,
        cfg,
        "GET",
        "/entries?type=pitch&priority=&coverage=unaudited&all=1",
    )

    assert pitches.status_code == 200
    assert pitches.text.index("High unaudited pitch") < pitches.text.index(
        "Low audited pitch"
    )
    assert generic.text.index("High unaudited pitch") < generic.text.index(
        "Low audited pitch"
    )
    assert "priority ▲" in pitches.text
    assert "priority ▲" in generic.text
    assert "High unaudited pitch" in filtered.text
    assert "Low audited pitch" not in filtered.text
    assert '<option value="unaudited" selected>' in filtered.text
    assert "High unaudited pitch" in default_form.text
    assert "Low audited pitch" in default_form.text
    assert "High unaudited pitch" in priority_with_blank_coverage.text
    assert "Low audited pitch" not in priority_with_blank_coverage.text
    assert "High unaudited pitch" in unaudited_with_blank_priority.text
    assert "Low audited pitch" not in unaudited_with_blank_priority.text

    invalid = await _request(monkeypatch, cfg, "GET", "/pitches?sort=bogus")
    assert invalid.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("entry_type", "type_dir"), (("todo", "todos"), ("pitch", "pitches"))
)
async def test_web_edit_preserves_selected_legacy_priority(
    monkeypatch, cfg, entry_type, type_dir
):
    result = entries.create_entry(
        cfg,
        entry_type,
        "Legacy priority",
        "body",
        type_fields={"priority": "high"},
    )
    result.entry.priority = "urgent"
    store.rewrite_index_atomic(cfg, type_dir, [result.entry])

    edit = await _request(monkeypatch, cfg, "GET", f"/entries/{result.entry.id}/edit")
    updated = await _request(
        monkeypatch,
        cfg,
        "POST",
        f"/api/entries/{result.entry.id}",
        data={"title": "Renamed", "priority": "urgent"},
    )

    assert '<option value="urgent" selected>urgent (legacy)</option>' in edit.text
    assert updated.status_code == 200
    stored = entries.find_by_id(cfg, result.entry.id)
    assert stored is not None
    assert stored[1].title == "Renamed"
    assert stored[1].priority == "urgent"


@pytest.mark.anyio
async def test_graph_missing_relation_is_a_warning(monkeypatch, cfg):
    todo = entries.create_entry(
        cfg,
        "todo",
        "Stale link",
        "body",
        type_fields={"status": "pending"},
        now=datetime(2026, 4, 11, 13),
    )
    # Simulate an old/deleted target without using a second storage path.
    index = cfg.home / "todos" / "index.jsonl"
    text = index.read_text().replace(
        '"status": "pending"',
        '"status": "pending", "initiative_id": 999',
    )
    index.write_text(text)
    detail = await _request(monkeypatch, cfg, "GET", f"/entries/{todo.entry.id}")
    assert detail.status_code == 200
    assert "missing initiative #999" in detail.text
    assert "/entries/999" not in detail.text


@pytest.mark.anyio
async def test_generic_handoff_list_view_and_edit(monkeypatch, cfg):
    handoff = entries.create_entry(
        cfg,
        "handoff",
        "Web handoff",
        "Web authored body",
        type_fields={"branch": "feature/web"},
        now=datetime(2026, 4, 11, 10),
    )

    listing = await _request(
        monkeypatch, cfg, "GET", "/entries?type=handoff&branch=feature%2Fweb"
    )
    assert listing.status_code == 200
    assert "Web handoff" in listing.text
    assert "feature/web" in listing.text

    detail = await _request(monkeypatch, cfg, "GET", f"/entries/{handoff.entry.id}")
    assert "Web authored body" in detail.text
    assert "branch feature/web" in detail.text

    edit = await _request(monkeypatch, cfg, "GET", f"/entries/{handoff.entry.id}/edit")
    assert 'name="branch"' in edit.text
    updated = await _request(
        monkeypatch,
        cfg,
        "POST",
        f"/api/entries/{handoff.entry.id}",
        data={"branch": "release/web", "body": "Updated web body"},
    )
    assert updated.status_code == 200
    persisted = entries.find_by_id(cfg, handoff.entry.id)
    assert persisted is not None
    assert persisted[1].branch == "release/web"


@pytest.mark.anyio
async def test_generic_entries_blank_branch_control_is_not_a_filter(monkeypatch, cfg):
    entries.create_entry(cfg, "todo", "Ordinary entry", "body")
    entries.create_entry(cfg, "handoff", "Branchless handoff", "body")
    entries.create_entry(
        cfg,
        "handoff",
        "Named branch handoff",
        "body",
        type_fields={"branch": "feature/web"},
    )

    blank_branch = await _request(
        monkeypatch,
        cfg,
        "GET",
        "/entries",
        params={"branch": "", "all": "1"},
    )
    named_branch = await _request(
        monkeypatch,
        cfg,
        "GET",
        "/entries",
        params={"branch": "feature/web", "all": "1"},
    )

    assert blank_branch.status_code == 200
    assert "Ordinary entry" in blank_branch.text
    assert "Branchless handoff" in blank_branch.text
    assert "Named branch handoff" in blank_branch.text
    assert named_branch.status_code == 200
    assert "Named branch handoff" in named_branch.text
    assert "Ordinary entry" not in named_branch.text
    assert "Branchless handoff" not in named_branch.text


@pytest.mark.anyio
async def test_initiative_parse_route_creates_linked_todos_once(monkeypatch, cfg):
    project = entries.create_entry(cfg, "project", "Alpha", "body")
    initiative = entries.create_entry(
        cfg,
        "initiative",
        "Launch",
        "- [ ] ship it",
        type_fields={"project_ids": [project.entry.id]},
    )

    detail = await _request(monkeypatch, cfg, "GET", f"/entries/{initiative.entry.id}")
    assert "parse todos" in detail.text

    parsed = await _request(
        monkeypatch,
        cfg,
        "POST",
        f"/api/initiatives/{initiative.entry.id}/parse",
    )
    assert parsed.status_code == 200
    assert parsed.headers["hx-redirect"] == f"/entries/{initiative.entry.id}"
    assert len(store.read_index(cfg, "todos")) == 1

    await _request(
        monkeypatch,
        cfg,
        "POST",
        f"/api/initiatives/{initiative.entry.id}/parse",
    )
    assert len(store.read_index(cfg, "todos")) == 1
