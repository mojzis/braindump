from __future__ import annotations

from datetime import date, datetime

from braindump.core import entries, query


def _seed(cfg) -> None:
    entries.create_entry(
        cfg,
        "todos",
        "Ship deploy pipeline",
        "kubernetes rollout details",
        tags=["deploy", "k8s"],
        project="alpha",
        type_fields={"status": "pending"},
        now=datetime(2026, 4, 1, 9),
    )
    entries.create_entry(
        cfg,
        "todos",
        "Fix auth bug",
        "session token corruption",
        tags=["auth", "bug"],
        project="beta",
        type_fields={"status": "done"},
        now=datetime(2026, 4, 5, 9),
    )
    entries.create_entry(
        cfg,
        "til",
        "Ripgrep glob trick",
        "rg supports -g",
        tags=["rg", "cli"],
        project="alpha",
        type_fields={"category": "tools"},
        now=datetime(2026, 4, 10, 9),
    )


def test_search_keyword_matches_title(cfg):
    _seed(cfg)
    hits = query.search(cfg, query.SearchFilters(q="deploy"))
    assert len(hits) == 1
    assert hits[0].entry.title == "Ship deploy pipeline"


def test_search_filter_by_project(cfg):
    _seed(cfg)
    hits = query.search(cfg, query.SearchFilters(project="alpha"))
    assert len(hits) == 2
    assert {h.entry.title for h in hits} == {"Ship deploy pipeline", "Ripgrep glob trick"}


def test_search_filter_by_status_open(cfg):
    _seed(cfg)
    hits = query.search(cfg, query.SearchFilters(types=["todos"], status="open"))
    assert len(hits) == 1
    assert hits[0].entry.title == "Ship deploy pipeline"


def test_search_filter_by_status_done(cfg):
    _seed(cfg)
    hits = query.search(cfg, query.SearchFilters(types=["todos"], status="done"))
    assert len(hits) == 1
    assert hits[0].entry.title == "Fix auth bug"


def test_search_filter_by_tags_and_type(cfg):
    _seed(cfg)
    hits = query.search(cfg, query.SearchFilters(types=["til"], tags=["rg"]))
    assert len(hits) == 1
    assert hits[0].entry.title == "Ripgrep glob trick"


def test_search_date_range(cfg):
    _seed(cfg)
    hits = query.search(
        cfg,
        query.SearchFilters(since=date(2026, 4, 6), until=date(2026, 4, 30)),
    )
    assert len(hits) == 1
    assert hits[0].entry.title == "Ripgrep glob trick"


def test_search_sorts_newest_first(cfg):
    _seed(cfg)
    hits = query.search(cfg, query.SearchFilters())
    titles = [h.entry.title for h in hits]
    assert titles == ["Ripgrep glob trick", "Fix auth bug", "Ship deploy pipeline"]


def test_search_multi_word_and(cfg):
    _seed(cfg)
    # both words must appear across title/summary/tags
    hits = query.search(cfg, query.SearchFilters(q="deploy k8s"))
    assert len(hits) == 1
    assert hits[0].entry.title == "Ship deploy pipeline"


def test_fulltext_finds_body_match(cfg):
    _seed(cfg)
    # "kubernetes" only appears in the markdown body, not title/summary/tags
    hits = query.search(cfg, query.SearchFilters(q="kubernetes"))
    if not hits:
        # ripgrep may not be available on CI — skip gracefully
        import shutil
        assert shutil.which("rg") is None
        return
    assert len(hits) == 1
    assert hits[0].source == "fulltext"
    assert hits[0].entry.title == "Ship deploy pipeline"
