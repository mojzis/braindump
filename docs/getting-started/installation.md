# Installation

## Prerequisites

- [**uv**](https://docs.astral.sh/uv/) — used to install the `bd` CLI.
- [**ripgrep**](https://github.com/BurntSushi/ripgrep) — optional; enables the
  full-text fallback in `bd search`.

## Install

```bash
./install.sh
```

This will:

1. `uv tool install` the `bd` CLI (with the `web` extra for the local UI).
2. Copy Claude skills to `~/.claude/skills/`.
3. Seed the data directory at `~/braindump/` with empty indexes for each type.
4. Drop optional session-tracking scripts into `~/braindump/scripts/`.

!!! note "Start a fresh Claude Code session"

    After installing, start a new Claude Code session so the `/bd-*` skills are
    picked up.

## Reinstalling / upgrading the global `bd`

`bd` is installed as a [uv tool](https://docs.astral.sh/uv/concepts/tools/) — it
runs from its own isolated environment under
`~/.local/share/uv/tools/braindump/`, **not** from this repo's checkout. To pick
up local changes (or fix a broken install), reinstall from the repo directory:

```bash
cd ~/git/braindump
uv tool install --force --reinstall --no-cache ".[web]"
```

The `[web]` extra is required for `bd serve`. If it's omitted you'll get
`ModuleNotFoundError: No module named 'uvicorn'` when starting the web UI —
that's the symptom of a `bd` installed without it. Running `./install.sh` does
the same thing (it always installs with `[web]`).

## Desktop window (optional)

`bd app` runs the exact same web UI inside a native
[pywebview](https://pywebview.flet.dev/) window instead of a browser tab.
It requires the `[app]` extra:

```bash
uv tool install --force --reinstall --no-cache ".[app]"
```

Without it, `bd app` prints an install hint and falls back to suggesting
`bd serve`.

## Runtime data location

All data lives under `~/braindump/` by default. Override it with the
`BRAINDUMP_DIR` environment variable:

```bash
export BRAINDUMP_DIR=/path/to/your/braindump
```

## Developing on braindump itself

```bash
uv venv
uv pip install -e ".[dev,web]"
pytest                   # core test suite
bd serve --reload        # local UI with autoreload
```

The `braindump.core` package has no I/O except through `store.py`, and every
mutation is atomic (`fcntl.flock` + temp-file rename). See `tests/` for the
round-trip coverage.
