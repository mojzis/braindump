"""Tag analytics."""
from __future__ import annotations

from collections import Counter

from braindump.core import store
from braindump.core.config import Config
from braindump.core.schema import ALL_TYPE_DIRS


def tag_frequency(cfg: Config) -> Counter[str]:
    counter: Counter[str] = Counter()
    for type_dir in ALL_TYPE_DIRS:
        for entry in store.read_index(cfg, type_dir):
            for tag in entry.tags or []:
                counter[tag] += 1
    return counter


def entries_with_tag(cfg: Config, tag: str) -> list[tuple[str, int, str]]:
    """Return (type, id, title) triples for every entry carrying the tag."""
    out: list[tuple[str, int, str]] = []
    for type_dir in ALL_TYPE_DIRS:
        for entry in store.read_index(cfg, type_dir):
            if tag in (entry.tags or []):
                out.append((entry.type, entry.id, entry.title))
    return out
