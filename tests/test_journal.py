from __future__ import annotations

from datetime import date, datetime, timedelta

from braindump.core import journal, store


def test_current_day_respects_cutoff(cfg):
    # cfg has cutoff hour 4 (see conftest)
    before_cutoff = datetime(2026, 4, 11, 3, 30)
    after_cutoff = datetime(2026, 4, 11, 4, 0)
    noon = datetime(2026, 4, 11, 12, 0)
    assert journal.current_day(cfg, before_cutoff) == date(2026, 4, 10)
    assert journal.current_day(cfg, after_cutoff) == date(2026, 4, 11)
    assert journal.current_day(cfg, noon) == date(2026, 4, 11)


def test_get_or_create_day_creates_file_and_index(cfg):
    d = date(2026, 4, 11)
    entry = journal.get_or_create_day(cfg, d, project="alpha")
    assert entry.date == "2026-04-11"
    full = journal.day_full_path(cfg, d)
    assert full.exists()
    assert "2026-04-11" in full.read_text()
    stored = store.read_index(cfg, "journal")
    assert len(stored) == 1

    # calling again does not duplicate
    journal.get_or_create_day(cfg, d, project="alpha")
    assert len(store.read_index(cfg, "journal")) == 1


def test_append_text_updates_body_and_word_count(cfg):
    d = date(2026, 4, 11)
    journal.append_text(cfg, d, "first thought")
    journal.append_text(cfg, d, "second thought here")
    body = journal.read_body(cfg, d)
    assert "first thought" in body
    assert "second thought here" in body
    stored = store.read_index(cfg, "journal")
    assert stored[0].word_count == 5


def test_replace_body_overwrites(cfg):
    d = date(2026, 4, 11)
    journal.append_text(cfg, d, "throwaway")
    journal.replace_body(cfg, d, "brand new content only")
    body = journal.read_body(cfg, d)
    assert "throwaway" not in body
    assert body.strip() == "brand new content only"
    stored = store.read_index(cfg, "journal")
    assert stored[0].word_count == 4


def test_close_today_opens_tomorrow(cfg):
    # simulate "it's evening, I want to start tomorrow's file now"
    # current_day uses real local clock, so just assert both files get created
    today = journal.current_day(cfg)
    journal.append_text(cfg, today, "today's content")
    next_entry = journal.close_today(cfg)
    assert next_entry.date == (today + timedelta(days=1)).isoformat()
    assert journal.day_full_path(cfg, today).exists()
    assert journal.day_full_path(cfg, today + timedelta(days=1)).exists()


def test_previous_day_with_content(cfg):
    base = date(2026, 4, 11)
    journal.append_text(cfg, base - timedelta(days=2), "yesterday-ish content")
    # empty day in between
    journal.get_or_create_day(cfg, base - timedelta(days=1))
    prev = journal.previous_day_with_content(cfg, base)
    assert prev == base - timedelta(days=2)
