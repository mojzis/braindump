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
from urllib.parse import parse_qs, urlparse

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


def show(entry_id: int) -> dict[str, Any]:
    result = subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "--no-sync",
            "bd",
            "show",
            "--json",
            str(entry_id),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def assert_visible(page: Any, *titles: str) -> None:
    text = page.locator("body").inner_text()
    for title in titles:
        assert title in text, (title, text)


def assert_hidden(page: Any, *titles: str) -> None:
    text = page.locator("body").inner_text()
    for title in titles:
        assert title not in text, (title, text)


def query_values(page: Any) -> dict[str, list[str]]:
    return parse_qs(urlparse(page.url).query)


def main() -> None:  # noqa: PLR0915 -- keep the browser journey linear and auditable
    base = os.environ["QA_BASE_URL"].rstrip("/")
    root = Path(os.environ["QA_ROOT"])
    screenshots = root / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)

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
        "--original-input",
        "together original input",
    )
    personal_id = create(
        "Presence personal fixture",
        "personal body",
        "--priority",
        "high",
        "--presence",
        "personal",
    )
    done_id = create(
        "Presence done fixture",
        "done body",
        "--priority",
        "high",
        "--presence",
        "together",
        "--status",
        "done",
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{base}/capture?type=todo", wait_until="networkidle")
        page.locator('input[name="title"]').fill("Presence away fixture")
        page.locator('textarea[name="body"]').fill("away body")
        page.locator('input[name="tags"]').fill("presence-filter")
        page.locator('input[name="project"]').fill("presence-qa")
        page.locator('select[name="priority"]').select_option("high")
        page.locator('select[name="presence"]').select_option("agent")
        page.get_by_role("button", name="save").click()
        page.wait_for_url(f"{base}/entries/*", wait_until="networkidle")
        away_id = int(urlparse(page.url).path.rsplit("/", 1)[1])
        assert "Agent can handle" in page.locator("body").inner_text()

        page.goto(f"{base}/todos", wait_until="networkidle")
        assert_visible(
            page,
            "Presence away fixture",
            "Presence together fixture",
            "Presence personal fixture",
            "Presence unclassified fixture",
            "Agent can handle",
            "Needs us together",
            "I must do it",
        )
        assert_hidden(page, "Presence done fixture")
        page.screenshot(path=str(screenshots / "todos-classified.png"), full_page=True)

        page.goto(f"{base}/todos?presence=unclassified", wait_until="networkidle")
        assert_visible(page, "Presence unclassified fixture")
        assert_hidden(
            page,
            "Presence away fixture",
            "Presence together fixture",
            "Presence personal fixture",
        )
        assert "unclassified" in page.locator("body").inner_text()
        page.screenshot(
            path=str(screenshots / "todos-unclassified.png"), full_page=True
        )

        page.goto(f"{base}/todos?presence=agent", wait_until="networkidle")
        assert_visible(page, "Presence away fixture")
        assert_hidden(page, "Presence together fixture", "Presence personal fixture")
        page.get_by_role("link", name="Needs my time", exact=True).click()
        assert_visible(page, "Presence together fixture", "Presence personal fixture")
        assert_hidden(page, "Presence away fixture", "Presence done fixture")

        page.goto(f"{base}/todos?presence=together", wait_until="networkidle")
        assert_visible(page, "Presence together fixture")
        assert_hidden(page, "Presence personal fixture", "Presence done fixture")

        page.goto(
            f"{base}/todos?presence=together&project=presence-qa&tag=presence-filter"
            f"&priority=high&all=1&q=Presence&sort=presence&dir=asc",
            wait_until="networkidle",
        )
        assert_visible(page, "Presence together fixture", "Presence done fixture")
        assert_hidden(
            page,
            "Presence away fixture",
            "Presence personal fixture",
            "Presence unclassified fixture",
        )
        project_link = page.get_by_role("link", name="presence-qa", exact=True).last
        project_query = parse_qs(
            urlparse(project_link.get_attribute("href") or "").query
        )
        assert project_query["presence"] == ["together"]
        page.locator('th a[href*="sort=presence"]').click()
        assert query_values(page)["presence"] == ["together"]
        assert query_values(page)["sort"] == ["presence"]

        before = show(together_id)
        preserved_fields = (
            "title",
            "body",
            "input",
            "tags",
            "project",
            "priority",
            "status",
        )
        page.goto(f"{base}/entries/{together_id}/edit", wait_until="networkidle")
        selector = page.locator('select[name="presence"]')
        selector.select_option("personal")
        page.get_by_role("button", name="save").click()
        page.wait_for_url(f"{base}/entries/{together_id}", wait_until="networkidle")
        page.reload(wait_until="networkidle")
        assert "I must do it" in page.locator("body").inner_text()

        page.goto(f"{base}/entries/{together_id}/edit", wait_until="networkidle")
        selector = page.locator('select[name="presence"]')
        assert selector.input_value() == "personal"
        selector.select_option("")
        page.get_by_role("button", name="save").click()
        page.wait_for_url(f"{base}/entries/{together_id}", wait_until="networkidle")
        page.reload(wait_until="networkidle")
        assert "unclassified" not in page.locator("body").inner_text()
        after = show(together_id)
        assert "presence" not in after
        assert {field: before.get(field) for field in preserved_fields} == {
            field: after.get(field) for field in preserved_fields
        }

        page.goto(f"{base}/entries?type=todo&presence=agent", wait_until="networkidle")
        assert_visible(page, "Presence away fixture", "Agent can handle")
        assert_hidden(
            page, "Presence personal fixture", "Presence unclassified fixture"
        )
        page.get_by_role("link", name="Needs my time", exact=True).click()
        assert_visible(page, "Presence personal fixture", "I must do it")
        assert_hidden(page, "Presence away fixture", "Presence unclassified fixture")

        print(
            json.dumps(
                {
                    "status": "pass",
                    "url": base,
                    "fixture_ids": {
                        "away": away_id,
                        "unclassified": unclassified_id,
                        "together": together_id,
                        "personal": personal_id,
                        "done": done_id,
                    },
                    "browser": {
                        "executable": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                        "version": browser.version,
                        "viewport": {"width": 1280, "height": 900},
                    },
                    "preserved_fields": list(preserved_fields),
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
