"""Functional browser journey for todo presence classification.

The caller owns a disposable store and loopback ``bd serve`` process.  This
script owns only its synthetic entries and screenshots under ``QA_ROOT``.
"""

# ruff: noqa: E501, S101, S603, S607, T201

from __future__ import annotations

import importlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

sync_playwright = importlib.import_module("playwright.sync_api").sync_playwright


def create(title: str, body: str, *options: str) -> int:
    result = subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "--no-sync",
            "bd",
            "create",
            "todo",
            title,
            "--project",
            "presence-qa",
            "--tag",
            "presence-filter",
            "--body-file",
            "/dev/stdin",
            *options,
        ],
        input=body,
        text=True,
        capture_output=True,
        check=True,
    )
    return int(result.stdout.split("#", 1)[1].split()[0])


def assert_only(page: Any, visible: str, hidden: str) -> None:
    text = page.locator("body").inner_text()
    assert visible in text, (visible, text)
    assert hidden not in text, (hidden, text)


def main() -> None:
    base = os.environ["QA_BASE_URL"].rstrip("/")
    root = Path(os.environ["QA_ROOT"])
    screenshots = root / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)

    away_id = create(
        "Presence away fixture",
        "away body",
        "--priority",
        "high",
        "--presence",
        "agent",
    )
    unclassified_id = create(
        "Presence unclassified fixture", "unclassified body", "--priority", "high"
    )
    together_id = create(
        "Presence together fixture",
        "together body",
        "--priority",
        "high",
        "--presence",
        "together",
    )
    done_id = create(
        "Presence done fixture", "done body", "--priority", "high", "--status", "done"
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{base}/todos", wait_until="networkidle")
        assert_only(page, "Presence away fixture", "Presence done fixture")
        assert "Agent can handle" in page.locator("body").inner_text()
        page.screenshot(path=str(screenshots / "todos-classified.png"), full_page=True)

        page.goto(f"{base}/todos?presence=unclassified", wait_until="networkidle")
        assert_only(page, "Presence unclassified fixture", "Presence away fixture")
        assert "unclassified" in page.locator("body").inner_text()
        page.screenshot(
            path=str(screenshots / "todos-unclassified.png"), full_page=True
        )

        page.goto(f"{base}/todos?presence=agent", wait_until="networkidle")
        assert_only(page, "Presence away fixture", "Presence together fixture")
        page.get_by_role("link", name="Needs my time", exact=True).click()
        assert_only(page, "Presence together fixture", "Presence away fixture")

        page.goto(
            f"{base}/todos?presence=together&project=presence-qa&tag=presence-filter"
            f"&priority=high&all=1&q=Presence+together",
            wait_until="networkidle",
        )
        assert_only(page, "Presence together fixture", "Presence done fixture")

        page.goto(f"{base}/entries/{away_id}/edit", wait_until="networkidle")
        selector = page.locator('select[name="presence"]')
        selector.select_option("personal")
        page.get_by_role("button", name="save").click()
        page.wait_for_url(f"{base}/entries/{away_id}", wait_until="networkidle")
        assert "I must do it" in page.locator("body").inner_text()

        page.goto(f"{base}/entries/{away_id}/edit", wait_until="networkidle")
        page.locator('select[name="presence"]').select_option("")
        page.get_by_role("button", name="save").click()
        page.wait_for_url(f"{base}/entries/{away_id}", wait_until="networkidle")
        assert "unclassified" not in page.locator("body").inner_text()
        page.goto(f"{base}/entries/{away_id}", wait_until="networkidle")
        assert "Presence away fixture" in page.locator("body").inner_text()
        assert "away body" in page.locator("body").inner_text()

        page.goto(f"{base}/capture?type=todo", wait_until="networkidle")
        page.locator('select[name="presence"]').select_option("together")
        assert page.locator('select[name="presence"]').input_value() == "together"

        print(
            json.dumps(
                {
                    "status": "pass",
                    "url": base,
                    "fixture_ids": {
                        "away": away_id,
                        "unclassified": unclassified_id,
                        "together": together_id,
                        "done": done_id,
                    },
                    "screenshots": [
                        str(screenshots / "todos-classified.png"),
                        str(screenshots / "todos-unclassified.png"),
                    ],
                },
                sort_keys=True,
            )
        )
        browser.close()


if __name__ == "__main__":
    main()
