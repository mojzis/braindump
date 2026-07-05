---
title: For LLMs
---

# For LLMs

When you're discussing braindump with an LLM — asking it how to use the `bd`
CLI, extend the core, or write a new skill — hand it the project's documentation
as context. This site publishes that context as clean, machine-readable markdown
following the [llms.txt standard](https://llmstxt.org/).

## The two files

<div class="grid cards" markdown>

-   :material-file-document-outline:{ .lg .middle } __`llms.txt`__ — the index

    ---

    A short, structured map of the documentation: a summary plus curated links
    to every page. Small enough to drop in as a table of contents so a model
    knows what exists and can fetch what it needs.

    [:octicons-download-24: Open `llms.txt`](https://mojzis.github.io/braindump/llms.txt)

-   :material-file-document-multiple-outline:{ .lg .middle } __`llms-full.txt`__ — everything

    ---

    The **entire** documentation concatenated into one markdown file. This is
    the one to paste into a chat when you want the model to know everything
    about braindump in a single shot.

    [:octicons-download-24: Open `llms-full.txt`](https://mojzis.github.io/braindump/llms-full.txt)

</div>

## How to use it

=== "Paste into a chat"

    Open [`llms-full.txt`](https://mojzis.github.io/braindump/llms-full.txt),
    copy all of it, and paste it at the start of your conversation:

    > Here is the full documentation for a tool called braindump. Use it to
    > answer my questions.
    >
    > ```
    > <paste llms-full.txt here>
    > ```

=== "Point a tool at the URL"

    Many assistants and agents can fetch a URL directly. Give them the raw link:

    ```text
    https://mojzis.github.io/braindump/llms-full.txt
    ```

    or the smaller index:

    ```text
    https://mojzis.github.io/braindump/llms.txt
    ```

=== "Feed braindump to Claude Code"

    Inside a Claude Code session working on braindump, the repo's own
    `CLAUDE.md` and the `braindump` skill already carry the conventions. The
    `llms-full.txt` file is most useful when you're talking to an LLM **outside**
    this repository — where it has no other context.

## Kept in sync automatically

Both files are regenerated from the documentation on every deploy by the
[`mkdocs-llmstxt`](https://pawamoy.github.io/mkdocs-llmstxt/) plugin, so they
never drift from what you're reading here. There's nothing to maintain by hand.
