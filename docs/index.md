---
title: Braindump
---

# Braindump

**A portable, Claude Code-integrated personal knowledge management system.**

Capture todos, TILs (Today I Learned), thoughts, prompts, and a daily journal.
Everything is plain markdown on disk with JSONL indexes for fast structured
search — driven by a single shared Python core.

There are **three ways to use it**, all backed by the same code in
`braindump/core/`, so every operation goes through one code path:

<div class="grid cards" markdown>

-   :material-console:{ .lg .middle } __`bd` CLI__

    ---

    Direct shell access — `bd create`, `bd search`, `bd journal`, and more.

    [:octicons-arrow-right-24: CLI reference](guides/cli.md)

-   :material-slash-forward-box:{ .lg .middle } __Claude skills__

    ---

    `/bd-dump`, `/bd-todo`, `/bd-search`, … — thin wrappers that shell out to
    `bd` from inside a Claude Code session.

    [:octicons-arrow-right-24: Claude skills](guides/claude-skills.md)

-   :material-web:{ .lg .middle } __Local web UI__

    ---

    `bd serve` — a FastAPI + Jinja2 + htmx app for browsing, editing, and the
    daily journal.

    [:octicons-arrow-right-24: Web UI](guides/web-ui.md)

</div>

## Why braindump

- **Plain markdown on disk** — browsable and backup-able; the JSONL indexes are
  a cache, not the source of truth.
- **Single shared core** — CLI, web UI, and Claude skills all call the same
  Python functions, so behavior stays consistent. Change `braindump/core/` and
  all three surfaces inherit the fix.
- **Projects are first class** — `project` is indexed, filterable everywhere,
  and has its own dashboards; the active-project focus is persisted so every
  query stays scoped.
- **Journal with a sane day cutoff** — late-night writes go to the previous
  day's file by default; a "finish the day" button seals today manually.
- **Soft delete** — removing an entry moves it to `.trash/` so nothing is ever
  lost accidentally.

## Get going

<div class="grid cards" markdown>

-   __Install it__

    ---

    One command with [uv](https://docs.astral.sh/uv/).

    [:octicons-arrow-right-24: Installation](getting-started/installation.md)

-   __First five minutes__

    ---

    Capture something, search it, write a journal entry.

    [:octicons-arrow-right-24: Quickstart](getting-started/quickstart.md)

-   __Feed it to an LLM__

    ---

    A single markdown file describing the whole project, ready to paste into a
    chat.

    [:octicons-arrow-right-24: For LLMs](llms.md)

</div>

!!! tip "Discussing braindump with an LLM?"

    Grab [`llms-full.txt`](https://mojzis.github.io/braindump/llms-full.txt) —
    the entire documentation as one clean markdown file — and drop it into your
    conversation. See [For LLMs](llms.md) for details.
