# Functional QA

## Journal earlier-days toolbar

1. Prepare isolated sample data from the repository root:

   ```bash
   uv sync --all-extras --all-groups
   export BRAINDUMP_DIR="$(mktemp -d)"
   uv run bd journal append --day 2026-01-01 "earlier-days smoke test"
   ```

2. Start the local web UI:

   ```bash
   uv run bd serve
   ```

3. Open `http://127.0.0.1:8765/journal` in a browser and click `▸ earlier days` in
   the sticky journal toolbar.

4. Verify that the first historical day heading and its content are visible
   above the sticky toolbar, with no part of the top of the earlier-days
   section hidden behind it. Click `▾ earlier days` again and verify that the
   section collapses.

5. Stop the server with `Ctrl-C`.
