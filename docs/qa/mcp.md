# Partial body edits over real stdio

Run from the final task checkout. This route is the functional evidence for the
MCP adapter and transport. It uses only MCP `create`, `show`, and `update`
calls against a disposable store; it does not read or write the user's store.

## Setup and command

Dev-owned preparation, from the repository working directory:

```bash
uv sync --all-extras --all-groups
uv run madoqua install
```

After preparation, the frozen/no-sync journey is one command:

```bash
uv run --frozen --no-sync python scripts/qa_mcp_partial_body.py
```

Prerequisites: Python 3.11+, `uv`, the checked-in lockfile, the `mcp` extra,
and a working local `bd-mcp` entry point. The script launches
`uv run --frozen --no-sync bd-mcp` over MCP SDK stdio, creates its own temporary
`BRAINDUMP_DIR`, and removes only that directory in a `finally` cleanup.

## Journey and pass conditions

The consumer creates disposable entries and reads their `body_revision`, then
proves replace, insert, delete, ordered multi-edit, Unicode/multiline matching,
missing and ambiguous match errors, failure atomicity, stale revision rejection
after an intervening update, competing stdio-client updates with one stale
rejection, and update/create contention while preserving both index rows. It also
proves legacy whole-body and metadata updates, the `update` tool schema, and a
long-pitch partial request whose captured arguments omit `body` and whose
receipt omits the full body.

Expected observable output is one JSON object on stdout with `status: "pass"`,
`transport: "stdio"`, the tool names exercised, compact receipts, revisions,
`contention_observed_while_external_lock_held: true`, and
`body_present_in_long_partial_arguments: false`. Any failed assertion exits
non-zero and prints the failure; successful output contains no full long body.

The route is complete only when the command exits 0 from the final checkout and
the JSON evidence is retained by the check step. No manual server, credentials,
imports, Parse operation, or external write is needed.
