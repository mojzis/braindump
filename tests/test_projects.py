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


def _seed_with_registered(cfg) -> None:
    """Seed the index with a registered 'Alpha' project entry alongside
    existing alpha/orphan-referencing entries."""
    entries.create_entry(
        cfg,
        "project",
        "Alpha",
        "Alpha body.",
        tags=["meta"],
        type_fields={
            "description": "Alpha is a registered project.",
            "state": "active",
            "local_dir": "/tmp/alpha",
            "tech_stack": ["python"],
        },
        now=datetime(2026, 4, 2),
    )
    entries.create_entry(
        cfg, "todos", "alpha todo open", "body", tags=["x"], project="Alpha",
        type_fields={"status": "pending"},
        now=datetime(2026, 4, 3),
    )
    entries.create_entry(
        cfg, "todos", "alpha todo done", "body", tags=["x", "y"], project="Alpha",
        type_fields={"status": "done"},
        now=datetime(2026, 4, 6),
    )
    entries.create_entry(
        cfg, "til", "learn orphan", "body", tags=["z"], project="Orphan",
        now=datetime(2026, 4, 9),
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


def test_list_projects_merges_registered_and_unregistered(cfg):
    _seed_with_registered(cfg)
    result_list = projects.list_projects(cfg)
    result = {p.name: p for p in result_list}
    assert "Alpha" in result
    assert "Orphan" in result

    alpha = result["Alpha"]
    assert alpha.registered is True
    assert alpha.description == "Alpha is a registered project."
    assert alpha.state == "active"
    assert alpha.local_dir == "/tmp/alpha"
    assert alpha.tech_stack == ["python"]
    # Alpha has two todos (open + done); the project entry itself is NOT counted.
    assert alpha.entry_count == 2
    assert alpha.open_todos == 1
    assert alpha.done_todos == 1

    orphan = result["Orphan"]
    assert orphan.registered is False
    assert orphan.entry_count == 1

    # sort order: registered first, then unregistered.
    # Alpha should appear before Orphan in the list.
    names_in_order = [p.name for p in result_list]
    assert names_in_order.index("Alpha") < names_in_order.index("Orphan")


def test_project_stats_excludes_self(cfg):
    _seed_with_registered(cfg)
    stats = projects.project_stats(cfg, "Alpha")
    # project entry itself must not be counted
    assert stats.entry_count == 2
    # type counts should NOT contain 'project'
    assert "project" not in stats.type_counts
    # last_activity should reflect the latest todo (2026-04-06), not the
    # project entry's own 2026-04-02 timestamp.
    assert stats.last_activity is not None
    assert stats.last_activity.startswith("2026-04-06")
    # metadata is hydrated
    assert stats.registered is True
    assert stats.description == "Alpha is a registered project."


def test_active_project_round_trip(cfg):
    projects.set_active_project(cfg, "alpha")
    assert projects.get_active_project(cfg) == "alpha"
    projects.set_active_project(cfg, None)
    assert projects.get_active_project(cfg) is None
