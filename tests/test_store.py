from __future__ import annotations

import json

from braindump.core import store
from braindump.core.schema import Entry


def test_slugify_basic():
    assert store.slugify("Fix auth bug!") == "fix-auth-bug"
    assert store.slugify("  Hello World  ") == "hello-world"
    assert store.slugify("####") == "entry"


def test_slugify_caps_at_50_chars():
    s = store.slugify("a" * 80)
    assert len(s) == 50
    assert s == "a" * 50


def test_frontmatter_round_trip():
    data = {
        "type": "todo",
        "title": "Fix auth bug",
        "tags": ["auth", "bug"],
        "project": "braindump",
        "status": "pending",
        "subtype": "code",
        "created_at": "2026-04-11T14:15:02Z",
    }
    rendered = store.render_frontmatter(data)
    assert rendered.startswith("---\ntype: todo\n")
    assert 'tags: ["auth", "bug"]' in rendered
    parsed, _ = store.parse_frontmatter(rendered + "\n\nbody\n")
    assert parsed["type"] == "todo"
    assert parsed["tags"] == ["auth", "bug"]
    assert parsed["project"] == "braindump"
    assert parsed["status"] == "pending"


def test_frontmatter_preserves_unknown_keys():
    data = {"type": "todo", "title": "t", "tags": [], "foo": "bar"}
    rendered = store.render_frontmatter(data)
    parsed, _ = store.parse_frontmatter(rendered)
    assert parsed["foo"] == "bar"


def test_next_id_increments(cfg):
    a = store.next_id(cfg)
    b = store.next_id(cfg)
    c = store.next_id(cfg)
    assert (a, b, c) == (1, 2, 3)


def test_append_and_read_index(cfg):
    entry = Entry(
        id=1,
        type="todo",
        title="hi",
        file_path="2026/04/hi--2026-04-11-1200.md",
        created_at="2026-04-11T12:00:00Z",
        tags=["a"],
    )
    store.append_index(cfg, "todos", entry)
    entries = store.read_index(cfg, "todos")
    assert len(entries) == 1
    assert entries[0].id == 1
    assert entries[0].tags == ["a"]


def test_rewrite_index_atomic(cfg):
    for i in range(1, 4):
        store.append_index(
            cfg,
            "todos",
            Entry(
                id=i,
                type="todo",
                title=f"t{i}",
                file_path=f"f{i}.md",
                created_at="2026-04-11T12:00:00Z",
            ),
        )
    entries = store.read_index(cfg, "todos")
    entries[1] = entries[1].model_copy(update={"title": "changed"})
    store.rewrite_index_atomic(cfg, "todos", entries)
    reread = store.read_index(cfg, "todos")
    assert [e.title for e in reread] == ["t1", "changed", "t3"]
    # raw line-count sanity: the on-disk file should be exactly 3 lines, no dupes
    raw = (cfg.home / "todos" / "index.jsonl").read_text().strip().splitlines()
    assert len(raw) == 3
    assert all(json.loads(line) for line in raw)
