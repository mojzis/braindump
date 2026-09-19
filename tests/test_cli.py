"""Tests for the bd CLI commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from braindump.cli.main import app
from braindump.core import entries
from braindump.core.config import Config
from braindump.core.store import ensure_type_dirs

runner = CliRunner()


def _make_cfg(tmp_path):
    home = tmp_path / "braindump"
    home.mkdir()
    cfg = Config(home=home, day_cutoff_hour=4)
    ensure_type_dirs(cfg)
    return cfg


def _create_todo(cfg: Config, title: str = "Fix auth bug", **kwargs):
    return entries.create_entry(
        cfg,
        "todo",
        title,
        "Body of the todo.",
        tags=kwargs.get("tags", ["auth", "bug"]),
        project=kwargs.get("project", "braindump"),
        type_fields=kwargs.get("type_fields", {"status": "pending"}),
        now=kwargs.get("now", datetime(2026, 4, 11, 14, 15, 2, tzinfo=UTC)),
    )


def _create_til(cfg: Config, title: str = "Python walrus operator"):
    return entries.create_entry(
        cfg,
        "til",
        title,
        "You can use := in Python 3.8+.",
        tags=["python"],
        type_fields={"category": "python", "source": "docs"},
        now=datetime(2026, 4, 11, 10, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def shown_todo(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    result = _create_todo(cfg)
    eid = result.entry.id

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", str(eid)])
    return eid, res


def test_show_todo_identity(shown_todo):
    eid, res = shown_todo
    assert res.exit_code == 0
    assert f"#{eid} todo" in res.output
    assert "Fix auth bug" in res.output
    assert "created: 2026-04-11" in res.output


def test_show_todo_metadata_and_body(shown_todo):
    _, res = shown_todo
    assert "project: braindump" in res.output
    assert "tags: auth, bug" in res.output
    assert "status: pending" in res.output
    assert "Body of the todo." in res.output


def test_show_multiple_entries(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    r1 = _create_todo(cfg)
    r2 = _create_til(cfg)

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", str(r1.entry.id), str(r2.entry.id)])
    assert res.exit_code == 0
    assert "Fix auth bug" in res.output
    assert "Python walrus operator" in res.output
    assert "---" in res.output


def test_show_unknown_id(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", "9999"])
    assert res.exit_code == 1
    assert "not found" in res.output


def test_show_mixed_known_unknown(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    r1 = _create_todo(cfg)

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", str(r1.entry.id), "9999"])
    # At least one succeeded, so exit code should be 0
    assert res.exit_code == 0
    assert "Fix auth bug" in res.output
    assert "not found" in res.output


def test_show_all_unknown(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", "9998", "9999"])
    assert res.exit_code == 1


def test_show_json(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    r1 = _create_todo(cfg)

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", "--json", str(r1.entry.id)])
    assert res.exit_code == 0
    data = json.loads(res.output.strip())
    assert (data["id"], data["type"], data["title"]) == (
        r1.entry.id,
        "todo",
        "Fix auth bug",
    )
    assert "body" in data
    assert "Body of the todo." in data["body"]


def test_show_json_unknown(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", "--json", "9999"])
    assert res.exit_code == 1


def test_show_type_specific_fields(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    r1 = _create_til(cfg)

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", str(r1.entry.id)])
    assert res.exit_code == 0
    assert "category: python" in res.output
    assert "source: docs" in res.output


def test_show_no_tables(tmp_path, monkeypatch):
    """Ensure output never contains markdown table syntax."""
    cfg = _make_cfg(tmp_path)
    r1 = _create_todo(cfg)

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", str(r1.entry.id)])
    assert res.exit_code == 0
    # No table borders
    assert "|" not in res.output


def test_create_echoes_the_new_id(tmp_path, monkeypatch):
    """The id is what you reference the entry by later — print it, not just the path."""
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))

    res = runner.invoke(app, ["create", "todo", "Fix auth bug", "--tag", "auth"])
    assert res.exit_code == 0
    assert res.output.startswith("created: #")

    eid = int(res.output.split("#", 1)[1].split()[0])
    shown = runner.invoke(app, ["show", str(eid)])
    assert "Fix auth bug" in shown.output


def test_delete_with_missing_file_drops_the_row(tmp_path, monkeypatch):
    """Regression #200: `bd delete` failed once the markdown was already gone."""
    cfg = _make_cfg(tmp_path)
    r = _create_todo(cfg)
    r.full_path.unlink()
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))

    res = runner.invoke(app, ["delete", str(r.entry.id)])

    assert res.exit_code == 0
    assert runner.invoke(app, ["doctor"]).exit_code == 0


def test_done_and_update_echo_the_id(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    eid = _create_todo(cfg).entry.id
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))

    res = runner.invoke(app, ["update", str(eid), "--title", "Fix auth bug for real"])
    assert res.exit_code == 0
    assert res.output.startswith(f"updated: #{eid} ")

    res = runner.invoke(app, ["done", str(eid)])
    assert res.exit_code == 0
    assert res.output.startswith(f"done: #{eid} ")


def test_update_rejects_unsupported_relation_without_traceback(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    eid = _create_todo(cfg).entry.id
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))

    res = runner.invoke(app, ["update", str(eid), "--project-id", "999"])

    assert res.exit_code == 2
    assert "Traceback" not in res.output
    assert "not valid for todo" in res.output


@pytest.fixture
def cli_handoff(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))

    created = runner.invoke(
        app,
        ["create", "handoff", "Auth session", "--branch", "feature/auth"],
        input="Resume the auth work.\n",
    )
    assert created.exit_code == 0
    entry_id = int(created.output.split("#", 1)[1].split()[0])

    return cfg, entry_id


def test_cli_handoff_list_and_search(cli_handoff):
    _, entry_id = cli_handoff
    listed = runner.invoke(
        app, ["list", "handoff", "--branch", "feature/auth", "--json"]
    )
    assert listed.exit_code == 0
    assert json.loads(listed.output)["branch"] == "feature/auth"
    searched = runner.invoke(
        app, ["search", "auth", "--type", "handoff", "--branch", "feature/auth"]
    )
    assert searched.exit_code == 0
    assert json.loads(searched.output)["id"] == entry_id


def test_cli_handoff_show_body_and_branch(cli_handoff):
    _, entry_id = cli_handoff
    shown = runner.invoke(app, ["show", "--json", str(entry_id)])
    assert json.loads(shown.output)["body"] == "Resume the auth work."
    assert json.loads(shown.output)["branch"] == "feature/auth"


def test_cli_handoff_update_branch(cli_handoff):
    cfg, entry_id = cli_handoff
    updated = runner.invoke(app, ["update", str(entry_id), "--branch", "release"])
    assert updated.exit_code == 0
    found = entries.find_by_id(cfg, entry_id)
    assert found is not None
    assert found[1].branch == "release"


def test_cli_handoff_clear_updated_branch(cli_handoff):
    cfg, entry_id = cli_handoff
    updated = runner.invoke(app, ["update", str(entry_id), "--branch", "release"])
    assert updated.exit_code == 0
    cleared = runner.invoke(app, ["update", str(entry_id), "--branch", ""])
    assert cleared.exit_code == 0
    found = entries.find_by_id(cfg, entry_id)
    assert found is not None
    assert found[1].branch is None


def test_qa_result_records_receipt_and_marks_done(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    todo = _create_todo(cfg, type_fields={"status": "in-qa"})
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))

    res = runner.invoke(app, ["qa", str(todo.entry.id), "pass", "--run-ref", "run-7"])

    assert res.exit_code == 0
    assert res.output.startswith(f"qa: #{todo.entry.id} pass -> done ")
    stored = entries.find_by_id(cfg, todo.entry.id)
    assert stored is not None
    assert (stored[1].qa_run_ref, bool(stored[1].qa_verified_at)) == ("run-7", True)


def test_qa_result_failure_returns_todo_to_progress(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    todo = _create_todo(cfg, type_fields={"status": "in-qa"})
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))

    res = runner.invoke(app, ["qa-result", str(todo.entry.id), "fail"])

    assert res.exit_code == 0
    assert "fail -> in-progress" in res.output


@pytest.fixture
def cli_graph(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    project = entries.create_entry(cfg, "project", "Alpha", "project")

    initiative_res = runner.invoke(
        app,
        [
            "create",
            "initiative",
            "Launch",
            "--status",
            "active",
            "--project-id",
            str(project.entry.id),
        ],
    )
    assert initiative_res.exit_code == 0
    initiative_id = int(initiative_res.output.split("#", 1)[1].split()[0])

    pitch_res = runner.invoke(
        app,
        [
            "create",
            "pitch",
            "Launch pitch",
            "--status",
            "active",
            "--project-id",
            str(project.entry.id),
            "--initiative-id",
            str(initiative_id),
            "--source-path",
            "pitch.md",
        ],
    )
    assert pitch_res.exit_code == 0
    pitch_id = int(pitch_res.output.split("#", 1)[1].split()[0])

    todo_res = runner.invoke(
        app,
        [
            "create",
            "todo",
            "Implement",
            "--initiative-id",
            str(initiative_id),
            "--pitch-id",
            str(pitch_id),
            "--status",
            "in-progress",
        ],
    )
    assert todo_res.exit_code == 0
    todo_id = int(todo_res.output.split("#", 1)[1].split()[0])

    return initiative_id, pitch_id, todo_id


def test_cli_graph_show_relations(cli_graph):
    initiative_id, pitch_id, _ = cli_graph
    shown = runner.invoke(app, ["show", str(pitch_id)])
    assert shown.exit_code == 0
    assert "status: active" in shown.output
    assert f"initiative_ids: {initiative_id}" in shown.output
    assert "source_path: pitch.md" in shown.output


def test_cli_graph_list_and_search(cli_graph):
    initiative_id, pitch_id, todo_id = cli_graph
    listed = runner.invoke(app, ["list", "initiative", "--status", "active"])
    assert listed.exit_code == 0
    assert "Launch" in listed.output
    searched = runner.invoke(app, ["search", "--initiative-id", str(initiative_id)])
    assert searched.exit_code == 0
    assert {json.loads(line)["id"] for line in searched.output.splitlines()} == {
        pitch_id,
        todo_id,
    }


@pytest.fixture
def cli_pitch(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    created = runner.invoke(
        app,
        [
            "create",
            "pitch",
            "Covered pitch",
            "--priority",
            "high",
            "--coverage",
            "covered",
        ],
    )
    assert created.exit_code == 0
    pitch_id = int(created.output.split("#", 1)[1].split()[0])

    return cfg, pitch_id


def test_cli_pitch_show_and_coverage_search(cli_pitch):
    _, pitch_id = cli_pitch
    shown = runner.invoke(app, ["show", str(pitch_id)])
    assert "priority: high" in shown.output
    assert "coverage: covered" in shown.output
    searched = runner.invoke(app, ["search", "--coverage", "covered"])
    assert json.loads(searched.output)["id"] == pitch_id


def test_cli_pitch_update_coverage(cli_pitch):
    cfg, pitch_id = cli_pitch
    updated = runner.invoke(app, ["update", str(pitch_id), "--coverage", "partial"])
    assert updated.exit_code == 0
    found = entries.find_by_id(cfg, pitch_id)
    assert found is not None
    assert found[1].coverage == "partial"


def test_cli_pitch_clear_priority_and_coverage(cli_pitch):
    cfg, pitch_id = cli_pitch
    runner.invoke(app, ["update", str(pitch_id), "--coverage", "partial"])
    cleared = runner.invoke(
        app, ["update", str(pitch_id), "--priority", "", "--coverage", ""]
    )
    assert cleared.exit_code == 0
    found = entries.find_by_id(cfg, pitch_id)
    assert found is not None
    assert found[1].priority is None
    assert found[1].coverage is None


@pytest.fixture
def cli_priority_pitches(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    entries.create_entry(
        cfg,
        "pitch",
        "Low audited",
        "body",
        type_fields={"priority": "low", "coverage": "covered"},
    )
    unaudited = entries.create_entry(
        cfg, "pitch", "High unaudited", "body", type_fields={"priority": "high"}
    )

    return unaudited


def test_cli_priority_sort_before_limit(cli_priority_pitches):
    unaudited = cli_priority_pitches
    listed = runner.invoke(
        app,
        [
            "list",
            "pitch",
            "--sort",
            "priority",
            "--dir",
            "asc",
            "--limit",
            "1",
            "--json",
        ],
    )
    searched = runner.invoke(
        app, ["search", "--sort", "priority", "--dir", "asc", "--limit", "1"]
    )
    assert listed.exit_code == 0
    assert json.loads(listed.output)["id"] == unaudited.entry.id
    assert searched.exit_code == 0
    assert json.loads(searched.output)["id"] == unaudited.entry.id


def test_cli_unaudited_list_and_search(cli_priority_pitches):
    unaudited = cli_priority_pitches
    unaudited_list = runner.invoke(
        app, ["list", "pitch", "--coverage", "unaudited", "--json"]
    )
    unaudited_search = runner.invoke(app, ["search", "--coverage", "unaudited"])
    assert json.loads(unaudited_list.output)["id"] == unaudited.entry.id
    assert json.loads(unaudited_search.output)["id"] == unaudited.entry.id


def test_cli_sort_validation(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    invalid = runner.invoke(app, ["search", "--sort", "bogus"])
    assert invalid.exit_code == 2
    assert "sort must be one of" in invalid.output


@pytest.mark.parametrize("command", ["list", "search"])
@pytest.mark.parametrize(
    "term", ["--coverage", "unaudited", "uncovered", "partial", "covered"]
)
def test_cli_coverage_help(command, term):
    help_result = runner.invoke(app, [command, "--help"], terminal_width=140)
    assert term in help_result.output


@pytest.fixture
def cli_pitch_source(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    project = entries.create_entry(cfg, "project", "Alpha", "body")
    initiative = entries.create_entry(cfg, "initiative", "Launch", "body")
    source = tmp_path / "selected-pitch.md"
    source.write_text(
        '---\ntitle: Selected pitch\ntags: ["launch"]\n'
        "priority: medium\ncoverage: partial\n---\n"
        "# Selected pitch\n\nPreserve this body.\n"
    )

    return cfg, project, initiative, source


def test_cli_pitch_import_dry_run(cli_pitch_source):
    cfg, project, initiative, source = cli_pitch_source
    preview = runner.invoke(
        app,
        [
            "pitch",
            "import",
            str(source),
            "--project-id",
            str(project.entry.id),
            "--initiative-id",
            str(initiative.entry.id),
            "--dry-run",
        ],
    )
    assert preview.exit_code == 0
    assert "dry-run:" in preview.output
    assert entries.store.read_index(cfg, "pitches") == []
    assert source.exists()


@pytest.fixture
def cli_imported_pitch(cli_pitch_source):
    cfg, project, initiative, source = cli_pitch_source
    imported = runner.invoke(
        app,
        [
            "pitch",
            "import",
            str(source),
            "--project-id",
            str(project.entry.id),
            "--initiative-id",
            str(initiative.entry.id),
        ],
    )
    assert imported.exit_code == 0
    return imported, cfg, project, initiative, source


def test_cli_pitch_import_receipt_and_source(cli_imported_pitch):
    imported, cfg, _, _, source = cli_imported_pitch
    assert "verified" in imported.output
    pitch = entries.store.read_index(cfg, "pitches")[0]
    assert pitch.source_path == str(source.resolve())
    assert source.exists()


def test_cli_pitch_import_metadata(cli_imported_pitch):
    _, cfg, project, initiative, _ = cli_imported_pitch
    pitch = entries.store.read_index(cfg, "pitches")[0]
    assert pitch.project_ids == [project.entry.id]
    assert pitch.initiative_ids == [initiative.entry.id]
    assert pitch.priority == "medium"
    assert pitch.coverage == "partial"


def test_cli_imported_pitch_source_removal_requires_confirmation(cli_imported_pitch):
    _, _, _, _, source = cli_imported_pitch
    removed = runner.invoke(
        app, ["pitch", "remove-source", str(source), "--confirm-source-removal"]
    )
    assert removed.exit_code == 0
    assert "removed-source:" in removed.output
    assert not source.exists()
