from __future__ import annotations

from datetime import datetime

from braindump.core import entries, projects


def _seed(cfg) -> None:
    entries.create_entry(
        cfg, "todos", "a", "b", tags=["x"], project="alpha",
        type_fields={"status": "pending"},
        now=datetime(2026, 4, 1),
    )
    entries.create_entry(
        cfg, "todos", "b", "c", tags=["x", "y"], project="alpha",
        type_fields={"status": "done"},
        now=datetime(2026, 4, 5),
    )
    entries.create_entry(
        cfg, "til", "learn", "d", tags=["z"], project="beta",
        now=datetime(2026, 4, 10),
    )


def test_list_projects_aggregates(cfg):
    _seed(cfg)
    result = {p.name: p for p in projects.list_projects(cfg)}
    assert set(result) == {"alpha", "beta"}
    alpha = result["alpha"]
    assert alpha.entry_count == 2
    assert alpha.open_todos == 1
    assert alpha.done_todos == 1
    assert alpha.tag_counts["x"] == 2
    assert alpha.tag_counts["y"] == 1

    beta = result["beta"]
    assert beta.entry_count == 1
    assert beta.open_todos == 0


def test_active_project_round_trip(cfg):
    projects.set_active_project(cfg, "alpha")
    assert projects.get_active_project(cfg) == "alpha"
    projects.set_active_project(cfg, None)
    assert projects.get_active_project(cfg) is None
