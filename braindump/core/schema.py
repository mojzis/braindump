from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


EntryType = Literal["todo", "til", "thought", "prompt", "journal", "project"]

TODO_STATUSES = ("pending", "in-progress", "done")

PROJECT_STATES = ("active", "paused", "archived")

TYPE_TO_DIR: dict[str, str] = {
    "todo": "todos",
    "til": "til",
    "thought": "thoughts",
    "prompt": "prompts",
    "journal": "journal",
    "project": "projects",
}

DIR_TO_TYPE: dict[str, str] = {v: k for k, v in TYPE_TO_DIR.items()}

ALL_TYPES: tuple[str, ...] = tuple(TYPE_TO_DIR.keys())
ALL_TYPE_DIRS: tuple[str, ...] = tuple(TYPE_TO_DIR.values())


def type_to_dir(type_or_dir: str) -> str:
    """Accept either a type name ('todo') or a directory name ('todos') and return the dir."""
    if type_or_dir in TYPE_TO_DIR:
        return TYPE_TO_DIR[type_or_dir]
    if type_or_dir in DIR_TO_TYPE:
        return type_or_dir
    raise ValueError(f"Unknown braindump type: {type_or_dir!r}")


def dir_to_type(dir_name: str) -> str:
    if dir_name in DIR_TO_TYPE:
        return DIR_TO_TYPE[dir_name]
    raise ValueError(f"Unknown braindump type dir: {dir_name!r}")


class Entry(BaseModel):
    """Schema for a braindump index entry.

    All fields are loose — the JSONL format is append-only and has accumulated
    type-specific fields over time. Unknown fields are preserved via model_extra.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: int
    type: EntryType
    title: str
    file_path: str
    created_at: str
    updated_at: str | None = None

    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    project: str | None = None
    input: str | None = None

    # Type-specific (all optional; presence depends on .type)
    # todo
    status: str | None = None
    subtype: str | None = None
    priority: str | None = None
    due_date: str | None = None
    # til
    category: str | None = None
    source: str | None = None
    # thought
    mood: str | None = None
    related_to: str | None = None
    # prompt
    prompt_type: str | None = None
    model_target: str | None = None
    # journal
    date: str | None = None
    word_count: int | None = None
    # project
    description: str | None = None
    state: str | None = None
    local_dir: str | None = None
    tech_stack: list[str] | None = None

    def type_dir(self) -> str:
        return TYPE_TO_DIR[self.type]

    def to_index_json(self) -> dict:
        """Return the dict that gets serialized into the JSONL index.

        Drops None values so we don't bloat the index with empty fields.
        """
        data = self.model_dump(exclude_none=True)
        # preserve ordering roughly matching legacy scripts
        return data
