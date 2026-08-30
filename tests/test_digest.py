from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from braindump.core import digest, entries, journal, store


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- split_scratchpad --------------------------------------------------------


def test_split_scratchpad_no_heading_returns_body_unchanged():
    body = "line one\nline two\nline three"
    main, scratchpad = digest.split_scratchpad(body)
    assert main == body
    assert scratchpad == ""


def test_split_scratchpad_splits_at_heading():
    body = "note one\nnote two\n## Scratchpad\nidea a\nidea b"
    main, scratchpad = digest.split_scratchpad(body)
    assert main == "note one\nnote two"
    assert scratchpad == "## Scratchpad\nidea a\nidea b"


def test_split_scratchpad_case_insensitive_and_flexible_spacing():
    body = "hello\n##   scratchpad\nstuff"
    main, scratchpad = digest.split_scratchpad(body)
    assert main == "hello"
    assert scratchpad == "##   scratchpad\nstuff"


def test_split_scratchpad_heading_at_start():
    body = "## Scratchpad\nonly scratch content"
    main, scratchpad = digest.split_scratchpad(body)
    assert main == ""
    assert scratchpad == body


def test_carry_forward_scratchpad_extracts_block():
    body = "note\n## Scratchpad\ncarried over"
    assert digest.carry_forward_scratchpad(body) == "## Scratchpad\ncarried over"


def test_carry_forward_scratchpad_empty_when_no_block():
    assert digest.carry_forward_scratchpad("just notes, no heading") == ""


# --- numbered_lines_for_prompt -----------------------------------------------


def test_numbered_lines_excludes_scratchpad_with_true_indexes():
    body = "zero\none\n\nthree\n## Scratchpad\nfive\nsix"
    rendered = digest.numbered_lines_for_prompt(body)
    lines = rendered.splitlines()
    assert lines == ["0: zero", "1: one", "2: ", "3: three"]
    # scratchpad lines (indexes 4-6) never appear
    assert "five" not in rendered
    assert "Scratchpad" not in rendered


def test_numbered_lines_flags_already_digested():
    body = "todo the thing [→todo#3]\nfresh line"
    rendered = digest.numbered_lines_for_prompt(body)
    assert "0: todo the thing [→todo#3]  [already digested]" in rendered
    assert "1: fresh line" in rendered
    assert "[already digested]" not in rendered.splitlines()[1]


def test_numbered_lines_no_scratchpad_covers_everything():
    body = "a\nb\nc"
    rendered = digest.numbered_lines_for_prompt(body)
    assert rendered == "0: a\n1: b\n2: c"


# --- validate_pass1 -----------------------------------------------------------


def _section(project: str, **item_kwargs) -> dict:
    item = {
        "line": 0,
        "line_text": "x",
        "type": "todo",
        "title": "T",
        "body": "B",
        "summary": "S",
        "tags": [],
    }
    item.update(item_kwargs)
    return {"project": project, "items": [item]}


def test_validate_pass1_drops_out_of_range_index():
    snapshot = ["only line"]
    data = {"sections": [_section("proj", line=5, line_text="does not exist")]}
    result = digest.validate_pass1(snapshot, data, [])
    assert result == []


def test_validate_pass1_drops_text_mismatch():
    snapshot = ["the real line"]
    data = {"sections": [_section("proj", line=0, line_text="not what is there")]}
    result = digest.validate_pass1(snapshot, data, [])
    assert result == []


def test_validate_pass1_drops_already_digested_line():
    snapshot = ["did the thing [→todo#9]"]
    data = {
        "sections": [
            _section("proj", line=0, line_text="did the thing [→todo#9]")
        ]
    }
    result = digest.validate_pass1(snapshot, data, [])
    assert result == []


def test_validate_pass1_keeps_valid_item_and_slugifies_project():
    snapshot = ["a real actionable line"]
    data = {
        "sections": [_section("Bd Web!", line=0, line_text="a real actionable line")]
    }
    result = digest.validate_pass1(snapshot, data, [])
    assert len(result) == 1
    assert result[0].project == "bd-web"
    assert result[0].items[0].line == 0
    assert result[0].items[0].title == "T"


def test_validate_pass1_tolerates_bullet_stripped_line_text():
    # The model routinely echoes `line_text` with the leading "- " bullet
    # stripped. The item must still anchor, and line_text must be stored as the
    # ground-truth full line so annotation lands on the real bullet.
    snapshot = ["- when developing in a branch, isolate the db"]
    data = {
        "sections": [
            _section(
                "proj", line=0, line_text="when developing in a branch, isolate the db"
            )
        ]
    }
    result = digest.validate_pass1(snapshot, data, [])
    assert len(result) == 1
    assert (
        result[0].items[0].line_text == "- when developing in a branch, isolate the db"
    )


def test_validate_pass1_drops_blank_title():
    snapshot = ["a real actionable line"]
    data = {
        "sections": [
            _section("proj", line=0, line_text="a real actionable line", title="   ")
        ]
    }
    result = digest.validate_pass1(snapshot, data, [])
    assert result == []


def test_validate_pass1_drops_unknown_type():
    snapshot = ["a real actionable line"]
    data = {
        "sections": [
            _section(
                "proj", line=0, line_text="a real actionable line", type="project"
            )
        ]
    }
    result = digest.validate_pass1(snapshot, data, [])
    assert result == []


def test_validate_pass1_coerces_non_list_tags_and_sub_lines_to_empty():
    # A malformed model response could hand back a bare string for a field
    # that's supposed to be a list -- must not silently iterate it char by
    # char into garbage tags/sub_lines.
    snapshot = ["a real actionable line"]
    data = {
        "sections": [
            _section(
                "proj",
                line=0,
                line_text="a real actionable line",
                tags="notalist",
                sub_lines="alsonotalist",
            )
        ]
    }
    result = digest.validate_pass1(snapshot, data, [])
    assert len(result) == 1
    item = result[0].items[0]
    assert item.tags == []
    assert item.sub_lines == []


def test_validate_pass1_typo_folds_onto_existing_project():
    snapshot = ["line zero"]
    data = {"sections": [_section("intrspect", line=0, line_text="line zero")]}
    result = digest.validate_pass1(snapshot, data, ["introspect", "bd-web"])
    assert len(result) == 1
    assert result[0].project == "introspect"


def test_validate_pass1_does_not_fold_short_names_within_distance_two():
    # "api" is only distance 2 from "cli", but both are short, genuinely
    # distinct project names -- must not fold just because they're close
    # in edit distance.
    snapshot = ["line zero"]
    data = {"sections": [_section("api", line=0, line_text="line zero")]}
    result = digest.validate_pass1(snapshot, data, ["cli"])
    assert len(result) == 1
    assert result[0].project == "api"


def test_validate_pass1_does_not_fold_beyond_distance_two():
    snapshot = ["line zero"]
    data = {
        "sections": [
            _section("completely-different-name", line=0, line_text="line zero")
        ]
    }
    result = digest.validate_pass1(snapshot, data, ["introspect"])
    assert len(result) == 1
    assert result[0].project == "completely-different-name"


def test_validate_pass1_merges_sections_that_fold_onto_same_project():
    snapshot = ["first line", "second line"]
    data = {
        "sections": [
            _section("bd-web", line=0, line_text="first line"),
            _section("bd web", line=1, line_text="second line"),
        ]
    }
    result = digest.validate_pass1(snapshot, data, [])
    assert len(result) == 1
    assert result[0].project == "bd-web"
    assert {i.line for i in result[0].items} == {0, 1}


# --- apply_annotations ---------------------------------------------------------


def _ann(
    line: int, line_text: str, entry_id: int = 1, type_: str = "todo"
) -> digest.Annotation:
    return digest.Annotation(
        line=line, line_text=line_text, type=type_, entry_id=entry_id
    )


def test_apply_annotations_exact_match():
    body = "one\ntwo\nthree"
    new_body, unanchored = digest.apply_annotations(body, [_ann(1, "two", entry_id=42)])
    assert new_body == "one\ntwo [→todo#42]\nthree"
    assert unanchored == []


def test_apply_annotations_shifted_but_unique_match():
    body = "zero\none\ntwo"
    # claims line 0, but "two" now actually lives at index 2 (indexes shifted)
    new_body, unanchored = digest.apply_annotations(body, [_ann(0, "two", entry_id=7)])
    assert new_body == "zero\none\ntwo [→todo#7]"
    assert unanchored == []


def test_apply_annotations_edited_line_is_unanchored():
    body = "zero\none\ntwo"
    ann = _ann(1, "this text was never here", entry_id=3)
    new_body, unanchored = digest.apply_annotations(body, [ann])
    assert new_body == body
    assert unanchored == [ann]


def test_apply_annotations_duplicate_line_is_unanchored():
    # index no longer matches (shifted/wrong) *and* the text now appears
    # twice, so there's no unambiguous line left to anchor to.
    body = "other\nsame line\nsame line"
    ann = _ann(0, "same line", entry_id=5)
    new_body, unanchored = digest.apply_annotations(body, [ann])
    assert new_body == body
    assert unanchored == [ann]


def test_apply_annotations_preserves_trailing_newline():
    body = "one\ntwo\n"
    new_body, _ = digest.apply_annotations(body, [_ann(0, "one", entry_id=1)])
    assert new_body.endswith("\n")
    assert new_body == "one [→todo#1]\ntwo\n"


# --- _merge_pass2 --------------------------------------------------------------


def test_merge_pass2_coerces_non_list_tags_to_empty():
    item = digest.ValidatedItem(
        line=0, line_text="x", type="todo", title="T", body="B", tags=["kept"]
    )
    pass2_data = {
        "items": [
            {"line": 0, "line_text": "x", "title": "T2", "body": "B2", "tags": "oops"}
        ]
    }
    merged = digest._merge_pass2([item], pass2_data)
    assert merged[0].title == "T2"
    assert merged[0].tags == []


# --- render_body_with_sub_lines ---------------------------------------------


def test_render_body_with_sub_lines_appends_bullets():
    out = digest.render_body_with_sub_lines("Parent context.", ["do a", "do b"])
    assert out == "Parent context.\n\n- do a\n- do b"


def test_render_body_with_sub_lines_normalizes_existing_markers():
    out = digest.render_body_with_sub_lines(
        "", ["- do a", "* do b", "1. do c", "  do d"]
    )
    assert out == "- do a\n- do b\n- do c\n- do d"


def test_render_body_with_sub_lines_no_sub_lines_returns_body():
    assert digest.render_body_with_sub_lines("just body", []) == "just body"
    assert digest.render_body_with_sub_lines("just body", ["   ", ""]) == "just body"


# --- run_parse -----------------------------------------------------------------


class FakeRunner:
    """Records calls; dispatches on `tools` (pass-1 has none, pass-2 is read-only)."""

    def __init__(self, pass1_data, pass2_data_by_dir=None, pass2_raise_for_dirs=None):
        self.pass1_data = pass1_data
        self.pass2_data_by_dir = pass2_data_by_dir or {}
        self.pass2_raise_for_dirs = pass2_raise_for_dirs or set()
        self.calls: list[dict] = []

    async def __call__(
        self, prompt, *, cwd=None, tools="", json_schema=None, timeout=180
    ):
        self.calls.append({"prompt": prompt, "cwd": cwd, "tools": tools})
        if tools == "":
            return self.pass1_data
        dir_name = Path(cwd).name if cwd else None
        if dir_name in self.pass2_raise_for_dirs:
            msg = f"pass2 boom for {dir_name}"
            raise RuntimeError(msg)
        return self.pass2_data_by_dir.get(dir_name, {"items": []})


def _seed_project(cfg, name: str, local_dir: Path | None = None):
    type_fields = {}
    if local_dir is not None:
        type_fields["local_dir"] = str(local_dir)
    entries.create_entry(
        cfg, "project", name, f"{name} project body.",
        type_fields=type_fields or None,
        now=datetime(2026, 4, 1),
    )


def _seed_journal(cfg, day: date, body: str) -> None:
    journal.replace_body(cfg, day, body)


@pytest.mark.anyio
async def test_run_parse_creates_entries_and_annotates_journal(cfg):
    day = date(2026, 5, 1)
    _seed_journal(
        cfg,
        day,
        "bd web\nfix the flaky test\nintrospect\nadd caching layer",
    )
    pass1_data = {
        "sections": [
            {
                "project": "bd-web",
                "items": [
                    {
                        "line": 1,
                        "line_text": "fix the flaky test",
                        "type": "todo",
                        "title": "Fix flaky test",
                        "body": "The test flakes under load.",
                        "summary": "flaky test",
                        "tags": ["testing"],
                    }
                ],
            },
            {
                "project": "introspect",
                "items": [
                    {
                        "line": 3,
                        "line_text": "add caching layer",
                        "type": "thought",
                        "title": "Add caching layer",
                        "body": "Consider caching.",
                        "summary": "caching idea",
                        "tags": ["perf"],
                    }
                ],
            },
        ]
    }
    runner = FakeRunner(pass1_data)
    progress_events: list[tuple[str, str]] = []

    result = await digest.run_parse(
        cfg,
        day,
        runner=runner,
        progress=lambda project, status: progress_events.append((project, status)),
    )

    assert result.errors == []
    assert result.unanchored == []
    assert result.total_entries == 2
    projects_seen = {s.project: s for s in result.sections}
    assert projects_seen["bd-web"].counts["todo"] == 1
    assert projects_seen["introspect"].counts["thought"] == 1

    todos = store.read_index(cfg, "todos")
    assert len(todos) == 1
    assert todos[0].title == "Fix flaky test"
    assert todos[0].project == "bd-web"

    thoughts = store.read_index(cfg, "thoughts")
    assert len(thoughts) == 1
    assert thoughts[0].project == "introspect"

    body = journal.read_body(cfg, day)
    assert f"fix the flaky test [→todo#{todos[0].id}]" in body
    assert f"add caching layer [→thought#{thoughts[0].id}]" in body

    # progress fired queued + done for both sections (no pass-2, no local_dir)
    statuses = {p for p, _ in progress_events}
    assert statuses == {"bd-web", "introspect"}
    assert ("bd-web", "done") in progress_events
    assert ("introspect", "done") in progress_events


@pytest.mark.anyio
async def test_run_parse_folds_sub_lines_into_entry_body(cfg):
    day = date(2026, 5, 2)
    _seed_journal(
        cfg,
        day,
        "bd web\npolish the journal page\n  - make it wider\n  - add a saved indicator",
    )
    pass1_data = {
        "sections": [
            {
                "project": "bd-web",
                "items": [
                    {
                        "line": 1,
                        "line_text": "polish the journal page",
                        "type": "todo",
                        "title": "Polish journal page",
                        "body": "Journal page needs UI polish.",
                        "summary": "polish",
                        "tags": ["ui"],
                        "sub_lines": ["make it wider", "add a saved indicator"],
                    }
                ],
            }
        ]
    }
    result = await digest.run_parse(cfg, day, runner=FakeRunner(pass1_data))
    assert result.total_entries == 1

    todos = store.read_index(cfg, "todos")
    entry_body = (cfg.home / "todos" / todos[0].file_path).read_text()
    # the concrete second-level items survive in the rendered entry body
    assert "- make it wider" in entry_body
    assert "- add a saved indicator" in entry_body
    # and only the parent line is annotated back in the journal
    body = journal.read_body(cfg, day)
    assert f"polish the journal page [→todo#{todos[0].id}]" in body
    assert "make it wider [→" not in body


@pytest.mark.anyio
async def test_run_parse_pass2_enhances_when_local_dir_exists(cfg, tmp_path):
    checkout = tmp_path / "introspect-checkout"
    checkout.mkdir()
    _seed_project(cfg, "introspect", local_dir=checkout)

    day = date(2026, 5, 2)
    _seed_journal(cfg, day, "add caching layer")
    pass1_data = {
        "sections": [
            {
                "project": "introspect",
                "items": [
                    {
                        "line": 0,
                        "line_text": "add caching layer",
                        "type": "thought",
                        "title": "Add caching layer",
                        "body": "Consider caching.",
                        "summary": "caching idea",
                        "tags": ["perf"],
                    }
                ],
            }
        ]
    }
    pass2_data = {
        "items": [
            {
                "line": 0,
                "line_text": "add caching layer",
                "title": "Add an LRU cache to the query layer",
                "body": "Enhanced with real repo context.",
                "summary": "caching idea, enhanced",
                "tags": ["perf", "cache"],
            }
        ]
    }
    runner = FakeRunner(
        pass1_data, pass2_data_by_dir={"introspect-checkout": pass2_data}
    )

    result = await digest.run_parse(cfg, day, runner=runner)

    assert result.errors == []
    thoughts = store.read_index(cfg, "thoughts")
    assert len(thoughts) == 1
    assert thoughts[0].title == "Add an LRU cache to the query layer"

    # pass-2 was actually invoked with the local dir as cwd and read-only tools
    pass2_calls = [c for c in runner.calls if c["tools"] != ""]
    assert len(pass2_calls) == 1
    assert Path(pass2_calls[0]["cwd"]).name == "introspect-checkout"
    assert pass2_calls[0]["tools"] == "Read,Glob,Grep"


@pytest.mark.anyio
async def test_run_parse_falls_back_to_pass1_items_when_pass2_raises(cfg, tmp_path):
    checkout = tmp_path / "introspect-checkout"
    checkout.mkdir()
    _seed_project(cfg, "introspect", local_dir=checkout)

    day = date(2026, 5, 3)
    _seed_journal(cfg, day, "add caching layer")
    pass1_data = {
        "sections": [
            {
                "project": "introspect",
                "items": [
                    {
                        "line": 0,
                        "line_text": "add caching layer",
                        "type": "thought",
                        "title": "Add caching layer",
                        "body": "Consider caching.",
                        "summary": "caching idea",
                        "tags": ["perf"],
                    }
                ],
            }
        ]
    }
    runner = FakeRunner(pass1_data, pass2_raise_for_dirs={"introspect-checkout"})

    result = await digest.run_parse(cfg, day, runner=runner)

    assert len(result.errors) == 1
    assert "pass 2 failed" in result.errors[0]
    thoughts = store.read_index(cfg, "thoughts")
    assert len(thoughts) == 1
    # fell back to the untouched pass-1 title
    assert thoughts[0].title == "Add caching layer"


@pytest.mark.anyio
async def test_run_parse_no_local_dir_skips_pass2_entirely(cfg):
    day = date(2026, 5, 4)
    _seed_journal(cfg, day, "a brand new idea")
    pass1_data = {
        "sections": [
            {
                "project": "some-new-project",
                "items": [
                    {
                        "line": 0,
                        "line_text": "a brand new idea",
                        "type": "thought",
                        "title": "A brand new idea",
                        "body": "Body.",
                        "summary": "idea",
                        "tags": [],
                    }
                ],
            }
        ]
    }
    runner = FakeRunner(pass1_data)

    await digest.run_parse(cfg, day, runner=runner)

    assert all(c["tools"] == "" for c in runner.calls)  # only the pass-1 call happened


@pytest.mark.anyio
async def test_run_parse_pass1_failure_is_reported_without_touching_journal(cfg):
    day = date(2026, 5, 5)
    original_body = "some line to digest"
    _seed_journal(cfg, day, original_body)

    class BoomRunner:
        async def __call__(self, *args, **kwargs):
            msg = "pass1 exploded"
            raise RuntimeError(msg)

    result = await digest.run_parse(cfg, day, runner=BoomRunner())

    assert result.total_entries == 0
    assert len(result.errors) == 1
    assert "pass 1 failed" in result.errors[0]
    assert journal.read_body(cfg, day) == original_body


@pytest.mark.anyio
async def test_run_parse_reports_unanchored_when_duplicate_line_across_sections(cfg):
    day = date(2026, 5, 6)
    _seed_journal(cfg, day, "fix the flaky test")
    duplicated_item = {
        "line": 0,
        "line_text": "fix the flaky test",
        "type": "todo",
        "title": "Fix flaky test",
        "body": "Body.",
        "summary": "",
        "tags": [],
    }
    # Two sections both legitimately reference the same (single) line -- the
    # second section's write-back attempt happens after the first section
    # already annotated that exact line, so it can no longer be anchored.
    pass1_data = {
        "sections": [
            {"project": "team-a", "items": [duplicated_item]},
            {"project": "team-b", "items": [duplicated_item]},
        ]
    }
    runner = FakeRunner(pass1_data)

    result = await digest.run_parse(cfg, day, runner=runner)

    assert result.total_entries == 2  # both entries still get created
    assert len(result.unanchored) == 1
    assert result.unanchored[0].line_text == "fix the flaky test"
    # only one annotation actually landed in the journal body
    body = journal.read_body(cfg, day)
    assert body.count("[→todo#") == 1


def test_parse_initiative_routes_todos_and_is_idempotent(cfg):
    alpha = entries.create_entry(cfg, "project", "Alpha", "body")
    beta = entries.create_entry(cfg, "project", "Beta", "body")
    initiative = entries.create_entry(
        cfg,
        "initiative",
        "Launch",
        "- [ ] unlabelled\n"
        "## Alpha\n"
        "- [ ] alpha task\n"
        "## Beta\n"
        "- [ ] beta task\n"
        "- [x] already done\n",
        type_fields={"project_ids": [alpha.entry.id, beta.entry.id]},
    )

    result = digest.parse_initiative(cfg, initiative.entry.id)
    assert result.created == 3
    todos = store.read_index(cfg, "todos")
    assert {todo.title: todo.project for todo in todos} == {
        "unlabelled": None,
        "alpha task": "Alpha",
        "beta task": "Beta",
    }
    assert all(todo.initiative_id == initiative.entry.id for todo in todos)

    again = digest.parse_initiative(cfg, initiative.entry.id)
    assert again.created == 0
    assert len(store.read_index(cfg, "todos")) == 3
    body = (cfg.home / "initiatives" / initiative.entry.file_path).read_text()
    assert body.count("[→todo#") == 3
