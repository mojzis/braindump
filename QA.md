# Functional QA

Run from the final task checkout. Development gates and the commit hook are
separate. Preparation owns environment setup; read-only QA never syncs or
installs project dependencies.

## Setup

Fresh worktree preparation:

    uv sync --all-extras --all-groups
    uv run madoqua install

Confirm the prepared Madoqua 0.2.3 floor in pyproject.toml and uv.lock; do not
resolve or edit the lock. Keep reports outside the repository.

Use one same-shell disposable store:

    set -eu
    qa_root="$(mktemp -d)"
    export BRAINDUMP_DIR="$qa_root/store"
    export BRAINDUMP_CLAUDE_BIN=/nonexistent/braindump-qa-claude
    mkdir -p "$qa_root/screenshots"
    server_pid=
    cleanup() {
      if [ -n "$server_pid" ]; then
        kill -INT "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
      fi
      rm -rf "$qa_root"
    }
    trap cleanup EXIT

    find_free_port() {
      uv run --frozen --no-sync python - <<'PY'
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        print(sock.getsockname()[1])
    PY
    }

    cli_line="$(printf 'CLI QA body\n' | uv run --frozen --no-sync bd create todo 'QA CLI navigation' --priority high)"
    cli_id="${cli_line#*#}"
    cli_id="${cli_id%% *}"
    browser_line="$(printf 'Browser QA body\n' | uv run --frozen --no-sync bd create todo 'QA browser navigation' --priority high)"
    browser_id="${browser_line#*#}"
    browser_id="${browser_id%% *}"
    test -n "$cli_id" -a -n "$browser_id"

    effective_day_line="$(uv run --frozen --no-sync bd journal today)"
    effective_day="${effective_day_line#day: }"
    effective_day="${effective_day%% *}"
    historical_day="$(uv run --frozen --no-sync python - "$effective_day" <<'PY'
    import sys
    from datetime import date, timedelta
    print(date.fromisoformat(sys.argv[1]) - timedelta(days=1))
    PY
    )"
    printf 'QA historical day\n' | uv run --frozen --no-sync bd journal append --day "$historical_day"
    printf 'QA effective current day\n' | uv run --frozen --no-sync bd journal append --day "$effective_day"

Record both IDs. The fixtures are synthetic and isolated. Historical day is
relative to the effective journal day (including the 04:00 cutoff), never a
hard-coded wall-clock date. Do not import data, invoke Parse, dispatch tasks,
change client configuration, use real credentials, or perform external writes.
The CLI and browser todos are distinct because CLI rename/done must not break
browser navigation. Delete only this scratch directory after evidence and
owned-server cleanup.

## Route selection

| Changed behavior | Required journey |
| --- | --- |
| CLI/storage contract | CLI round trip plus affected consumer journeys |
| Templates, CSS, JavaScript, web behavior | Applicable browser journey |
| Handoff metadata/filtering | docs/qa/handoff.md plus changed surface |
| MCP adapter/transport | Real stdio consumer route from the task; in-process is supplemental |
| Native windows/menu/clipboard/lifecycle | Native journey; HTTP is insufficient |
| Docs/refactor without behavior change | Explain why Functional QA is inapplicable; retain gates |

The check brief must link QA.md, name the selected journey, and add feature
actions/pass conditions. Resolve an absent route; do not substitute unit tests.

## CLI round trip

With cli_id, use only uv run --frozen --no-sync:

    uv run --frozen --no-sync bd show --json "$cli_id" | tee "$qa_root/cli-before.json"
    printf 'CLI QA updated body\n' | uv run --frozen --no-sync bd update "$cli_id" --title 'QA CLI navigation updated' --body
    uv run --frozen --no-sync bd list todo --all --json | tee "$qa_root/cli-list.jsonl"
    uv run --frozen --no-sync bd search 'QA CLI navigation updated' --type todo --all --json | tee "$qa_root/cli-search.jsonl"
    uv run --frozen --no-sync bd done "$cli_id" | tee "$qa_root/cli-done.txt"
    uv run --frozen --no-sync bd show --json "$cli_id" | tee "$qa_root/cli-after.json"

Final show retains the updated body and reports done; list/search identify the
intended entry. JSON lists are JSONL. Record literal commands, IDs, and status.

## Browser

Choose a free loopback port, never attach to a personal server:

    qa_port="$(find_free_port)"
    server_log="$qa_root/server.log"
    uv run --frozen --no-sync bd serve --host 127.0.0.1 --port "$qa_port" >"$server_log" 2>&1 &
    server_pid=$!
    export QA_BASE_URL="http://127.0.0.1:$qa_port"
    export QA_ROOT="$qa_root"
    export QA_HISTORICAL_DAY="$historical_day"

Verify the owned PID serves and record PID, URL, port, and log. Use the exact
real-browser route below; no HTML/curl substitute:

    uv run --no-project --with playwright python - <<'PY'
    import json, os
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    base = os.environ["QA_BASE_URL"]
    root = Path(os.environ["QA_ROOT"])
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(base + "/entries", wait_until="networkidle")
        page.get_by_text("QA browser navigation", exact=True).click()
        assert "Browser QA body" in page.locator("body").inner_text()
        page.locator('a[href="/entries"]').first.click()
        assert page.url.rstrip("/") == base + "/entries"
        assert "QA browser navigation" in page.locator("body").inner_text()
        page.screenshot(path=str(root / "screenshots" / "entries.png"), full_page=True)
        page.goto(base + "/journal", wait_until="networkidle")
        page.locator("#earlier-days-btn").click()
        page.wait_for_timeout(500)
        first = page.locator("#past-days .day-block").first
        assert first.is_visible() and "QA historical day" in first.inner_text()
        toolbar_box = page.locator(".journal-toolbar").bounding_box()
        first_box = first.bounding_box()
        assert toolbar_box is not None and first_box is not None
        page.screenshot(path=str(root / "screenshots" / "journal-desktop.png"), full_page=True)
        page.locator("#earlier-days-btn").click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(base + "/journal", wait_until="networkidle")
        page.locator("#earlier-days-btn").click()
        page.wait_for_timeout(500)
        assert page.locator("#past-days .day-block").first.is_visible()
        page.screenshot(path=str(root / "screenshots" / "journal-narrow.png"), full_page=True)
        print(json.dumps({
            "url": base,
            "historical_day": os.environ["QA_HISTORICAL_DAY"],
            "desktop_toolbar_box": toolbar_box,
            "desktop_first_day_box": first_box,
        }, sort_keys=True))
        browser.close()
    PY

This uses Chrome at the stated executable through ephemeral Playwright and adds
no project dependency/framework. Record executable, browser, viewports, URLs,
visible text, screenshots, and boxes. Inspect both screenshots: the clicked
earlier-days control reveals the historical heading/content with no sticky
toolbar overlap; collapse/expand again at narrow width. Chrome or Playwright
launch failure, including sandbox failure, is a setup gap and remains
unverified, not a product failure.

Entry pass: /entries shows the browser fixture, its detail shows its body, and
the visible back link returns to /entries without raw JSON/blank page. If editing
changed, edit/save/reload and record persistence. Returning to /todos with
sort/filter state is #212's separate acceptance condition.

Journal pass: click the exact control, verify the effective-relative fixture,
and inspect desktop/narrow screenshots. If autosave changed, edit today's text,
wait, reload, verify; never click Parse.

## Native windows

For native changes only, choose another free port and reuse the store:

    native_port="$(find_free_port)"
    uv run --frozen --no-sync bd app --host 127.0.0.1 --port "$native_port" --foreground >"$qa_root/native.log" 2>&1 &
    native_pid=$!

Observe Journal/Todos focus, selection/copy, and the changed action. Closing one
owned window leaves the other usable; closing both stops the owned server.
Attachment to a separate scratch server must leave that server running. Record
macOS/backend; headless reports this gap. Stop only the owned native process.

## Evidence and fixes

Report source SHA, selected route, separate IDs, scratch store, owned PID/ports,
literal actions/results, screenshots or client output, browser/viewport, and
cleanup. Distinguish missing route, setup blocker, and behavior failure. After
a fix rerun affected behavior on the final tree and name what was superseded.
Never mark an unexercised browser/native/transport route verified.

docs/qa/handoff.md retains the complete handoff route. Its CLI and in-process
FastAPI/MCP assertions are supplemental and do not prove browser, native-window,
or stdio-transport evidence.
