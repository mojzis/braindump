"""Journal digest engine: turn a day's free-form journal into structured entries.

Two Claude passes:

1. **Pass 1** (no tools, cwd = braindump home): reads the day's journal as
   numbered lines plus the project/tag inventory, groups lines into
   per-project sections, and proposes an entry (type/title/body/summary/tags)
   for each actionable line. Validated in Python (`validate_pass1`) — the
   model is never trusted with the anchoring indexes.
2. **Pass 2** (read-only tools, cwd = the project's local checkout, when it
   exists): lightly enhances title/body per section using real repo context.
   Falls back to the pass-1 items untouched if there's no local dir or the
   call fails.

After each section is enhanced, entries are created via the real
`entries.create_entry` path and the journal is annotated + rewritten
immediately (`apply_annotations` + `journal.replace_body`), one section at a
time, so a crash mid-parse only risks duplicating the section in flight.

Idempotency: `validate_pass1` drops any line already containing `[→` before
it ever reaches entry creation, and `apply_annotations` writes the `[→type#id]`
mark back per section.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

from braindump.core import claude_cli, entries, journal, store
from braindump.core import projects as projects_mod
from braindump.core import tags as tags_mod
from braindump.core.config import Config

ProgressCallback = Callable[[str, str], None]
Runner = Callable[..., Awaitable[dict[str, Any]]]

logger = logging.getLogger("braindump.digest")

ENTRY_TYPES = ("todo", "til", "thought", "prompt")


# --- scratchpad --------------------------------------------------------------

_SCRATCHPAD_HEADING_RE = re.compile(r"^##\s*scratchpad\s*$", re.IGNORECASE)


def _scratchpad_start(lines: list[str]) -> int | None:
    for i, line in enumerate(lines):
        if _SCRATCHPAD_HEADING_RE.match(line.rstrip()):
            return i
    return None


def split_scratchpad(body: str) -> tuple[str, str]:
    """Split `body` at the first `## Scratchpad` heading (case-insensitive).

    Returns `(main, scratchpad)`. `main` is everything before that heading
    line (trailing blank lines trimmed); `scratchpad` is the heading line
    through the end of the doc, verbatim. No heading found -> `(body, "")`.
    """
    lines = body.splitlines()
    idx = _scratchpad_start(lines)
    if idx is None:
        return body, ""
    main = "\n".join(lines[:idx]).rstrip("\n")
    scratchpad = "\n".join(lines[idx:])
    return main, scratchpad


def carry_forward_scratchpad(prev_body: str) -> str:
    """Extract the scratchpad block from yesterday's body to seed tomorrow's file."""
    _, scratchpad = split_scratchpad(prev_body)
    return scratchpad


def numbered_lines_for_prompt(
    body: str, *, anchor_map: dict[str, tuple[int, str]] | None = None
) -> str:
    """Render non-scratchpad lines with opaque anchors for the pass-1 prompt.

    When ``anchor_map`` is supplied it is populated with the generated
    ``anchor -> (source index, source text)`` mapping used to validate the
    model response. The random anchors make duplicate lines independently
    addressable without exposing source indexes to the model.
    """
    lines = body.splitlines()
    idx = _scratchpad_start(lines)
    limit = idx if idx is not None else len(lines)
    rendered = []
    for i in range(limit):
        line = lines[i]
        anchor = _new_anchor(anchor_map)
        if anchor_map is not None:
            anchor_map[anchor] = (i, line)
        suffix = "  [already digested]" if "[→" in line else ""
        rendered.append(f"{anchor}: {line}{suffix}")
    return "\n".join(rendered)


def _new_anchor(anchor_map: dict[str, tuple[int, str]] | None) -> str:
    """Create an opaque per-snapshot anchor, avoiding the unlikely collision."""
    while True:
        anchor = f"a_{secrets.token_urlsafe(12)}"
        if anchor_map is None or anchor not in anchor_map:
            return anchor


# --- edit distance -------------------------------------------------------


def _levenshtein(a: str, b: str) -> int:
    """Classic O(len(a)*len(b)) edit distance, no dependency needed for this."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current[j] = min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + cost,
            )
        previous = current
    return previous[-1]


TYPO_FOLD_MAX_DISTANCE = 2
TYPO_FOLD_MIN_LENGTH = 5


def _resolve_project_slug(raw_project: str, existing_projects: Sequence[str]) -> str:
    """Slugify `raw_project`; typo-fold onto an existing project at distance <= 2.

    Short slugs (e.g. "api" vs "cli") are only 2 edits apart despite being
    genuinely distinct projects, so folding is restricted to slugs of at
    least `TYPO_FOLD_MIN_LENGTH` characters (on either side of the
    comparison) to keep the <=2 rule from mis-folding short names.
    """
    slug = store.slugify(raw_project or "")
    if slug in existing_projects:
        return slug
    if len(slug) < TYPO_FOLD_MIN_LENGTH:
        return slug
    best: str | None = None
    best_dist = TYPO_FOLD_MAX_DISTANCE + 1
    for candidate in existing_projects:
        if len(candidate) < TYPO_FOLD_MIN_LENGTH:
            continue
        dist = _levenshtein(slug, candidate)
        if dist <= TYPO_FOLD_MAX_DISTANCE and dist < best_dist:
            best = candidate
            best_dist = dist
    return best if best is not None else slug


# --- pass-1 validation -----------------------------------------------------


@dataclass
class ValidatedItem:
    line: int
    line_text: str
    type: str
    title: str
    body: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    sub_lines: list[str] = field(default_factory=list)


@dataclass
class ValidatedSection:
    project: str
    items: list[ValidatedItem] = field(default_factory=list)


def _resolve_anchor_details(
    snapshot_lines: list[str],
    raw: dict[str, Any],
    anchor_map: dict[str, tuple[int, str]] | None = None,
) -> tuple[tuple[int, str] | None, str | None]:
    if anchor_map is not None:
        return _resolve_opaque_anchor(raw, anchor_map)
    return _resolve_legacy_anchor(snapshot_lines, raw)


def _resolve_opaque_anchor(
    raw: dict[str, Any], anchor_map: dict[str, tuple[int, str]]
) -> tuple[tuple[int, str] | None, str | None]:
    anchor = raw.get("anchor")
    if not isinstance(anchor, str) or not anchor:
        return None, "missing_anchor"
    resolved = anchor_map.get(anchor)
    if resolved is None:
        return None, "unknown_anchor"
    _, actual = resolved
    if "[→" in actual:
        return None, "already_digested"
    return resolved, None


def _resolve_legacy_anchor(
    snapshot_lines: list[str], raw: dict[str, Any]
) -> tuple[tuple[int, str] | None, str | None]:
    """Compatibility for direct callers using the pre-anchor item shape."""
    idx = raw.get("line")
    if not isinstance(idx, int) or isinstance(idx, bool):
        return None, "invalid_line_index"
    if idx < 0 or idx >= len(snapshot_lines):
        return None, "line_index_out_of_range"
    actual = snapshot_lines[idx]
    if "[→" in actual:
        return None, "already_digested"
    line_text = raw.get("line_text")
    if not isinstance(line_text, str):
        return None, "missing_line_text"
    if actual == line_text:
        return (idx, actual), None
    if _normalize_sub_line(actual) == _normalize_sub_line(line_text):
        return (idx, actual), None
    return None, "line_text_mismatch"


def _resolve_anchor(
    snapshot_lines: list[str],
    raw: dict[str, Any],
    anchor_map: dict[str, tuple[int, str]] | None = None,
) -> str | None:
    """Return the ground-truth journal line this item anchors to, or None."""
    resolved, _ = _resolve_anchor_details(snapshot_lines, raw, anchor_map)
    return resolved[1] if resolved is not None else None


_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")


def _normalize_sub_line(text: str) -> str:
    """Strip any leading bullet/number marker and surrounding whitespace."""
    return _BULLET_PREFIX_RE.sub("", text.strip()).strip()


def render_body_with_sub_lines(body: str, sub_lines: Sequence[str]) -> str:
    """Append the entry's sub-items to `body` as a markdown bullet list.

    Second-level journal items (sub-bullets under an actionable line) are the
    concrete substance of the entry, so they're rendered here in Python rather
    than left to the model — neither pass is trusted to keep them, and pass 2
    has been seen to overwrite a good body with a vague "no concrete list yet".
    Each sub-line is normalized (leading marker stripped) and re-prefixed with
    `- ` so the list renders cleanly regardless of how the model returned it.
    """
    items = [_normalize_sub_line(s) for s in sub_lines]
    items = [s for s in items if s]
    if not items:
        return body
    bullets = "\n".join(f"- {s}" for s in items)
    body = body.strip()
    return f"{body}\n\n{bullets}" if body else bullets


def _string_list(value: Any) -> list[str]:
    """Coerce a model-supplied field to `list[str]`, never trusting its shape.

    A malformed model response returning a bare string here would otherwise
    iterate character-by-character (`"abc"` -> `["a", "b", "c"]`), silently
    corrupting real tags/sub-lines instead of failing loudly.
    """
    if not isinstance(value, list):
        return []
    return [str(v) for v in value]


def _validate_item_with_reason(
    snapshot_lines: list[str],
    raw: dict[str, Any],
    anchor_map: dict[str, tuple[int, str]] | None = None,
) -> tuple[ValidatedItem | None, str | None]:
    resolved, reason = _resolve_anchor_details(snapshot_lines, raw, anchor_map)
    if resolved is None:
        return None, reason
    line, actual = resolved
    if raw.get("type") not in ENTRY_TYPES:
        return None, "invalid_type"
    title = str(raw.get("title") or "").strip()
    if not title:
        return None, "missing_title"
    return ValidatedItem(
        line=line,
        line_text=actual,
        type=raw["type"],
        title=title,
        body=str(raw.get("body") or "").strip(),
        summary=str(raw.get("summary") or "").strip(),
        tags=_string_list(raw.get("tags")),
        sub_lines=_string_list(raw.get("sub_lines")),
    ), None


def _validate_item(
    snapshot_lines: list[str], raw: dict[str, Any]
) -> ValidatedItem | None:
    """Validate one legacy/direct-call item without exposing its reason."""
    item, _ = _validate_item_with_reason(snapshot_lines, raw)
    return item


def validate_pass1(
    snapshot_lines: list[str],
    data: dict[str, Any],
    existing_projects: Iterable[str],
    *,
    anchor_map: dict[str, tuple[int, str]] | None = None,
    diagnostics: Counter[str] | None = None,
) -> list[ValidatedSection]:
    """Sanitize pass-1 model output against ground truth. Never trust the model.

    - Drops items with a missing or unknown opaque anchor.
    - Drops items whose target line already contains `[→` (idempotency).
    - Slugifies each section's `project`, typo-folding onto an existing
      project name at Levenshtein distance <= 2; otherwise it's a new project.
    - Sections that fold onto the same project name are merged, in the order
      first encountered. Sections left with no valid items are dropped.
    """
    existing = [p for p in existing_projects if p != "(none)"]
    # dicts preserve insertion order, so this alone tracks first-encountered order too
    merged: dict[str, list[ValidatedItem]] = {}

    raw_sections = data.get("sections", [])
    if not isinstance(raw_sections, list):
        return []
    for section in raw_sections:
        if not isinstance(section, dict):
            continue
        project = _resolve_project_slug(str(section.get("project") or ""), existing)
        items = []
        raw_items = section.get("items", [])
        if not isinstance(raw_items, list):
            continue
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            validated, reason = _validate_item_with_reason(
                snapshot_lines, raw, anchor_map
            )
            if validated is not None:
                items.append(validated)
            elif diagnostics is not None and reason is not None:
                diagnostics[reason] += 1
        if not items:
            continue
        merged.setdefault(project, []).extend(items)

    return [ValidatedSection(project=p, items=items) for p, items in merged.items()]


# --- annotation --------------------------------------------------------------


@dataclass
class Annotation:
    line: int
    line_text: str
    type: str
    entry_id: int


def apply_annotations(
    body: str, annotations: Sequence[Annotation]
) -> tuple[str, list[Annotation]]:
    """Append `` [→type#id]`` to each annotation's line. Never guess.

    - Exact match: `lines[ann.line] == ann.line_text` -> annotate that line.
    - Else, if `ann.line_text` occurs exactly once anywhere in the doc ->
      annotate that line (the index shifted but the text is unambiguous).
    - Else (edited beyond recognition, or duplicated elsewhere) -> reported
      back as unanchored, untouched.
    """
    lines = body.splitlines()
    unanchored: list[Annotation] = []
    for ann in annotations:
        mark = f" [→{ann.type}#{ann.entry_id}]"
        target: int | None = None
        if 0 <= ann.line < len(lines) and lines[ann.line] == ann.line_text:
            target = ann.line
        else:
            matches = [i for i, line in enumerate(lines) if line == ann.line_text]
            if len(matches) == 1:
                target = matches[0]
        if target is None:
            unanchored.append(ann)
            continue
        lines[target] = lines[target] + mark

    new_body = "\n".join(lines)
    if body.endswith("\n"):
        new_body += "\n"
    return new_body, unanchored


# --- schemas -----------------------------------------------------------------

_ITEM_PROPERTIES: dict[str, Any] = {
    "anchor": {"type": "string"},
    "type": {"type": "string", "enum": list(ENTRY_TYPES)},
    "title": {"type": "string"},
    "body": {"type": "string"},
    "summary": {"type": "string"},
    "tags": {"type": "array", "items": {"type": "string"}},
    "sub_lines": {"type": "array", "items": {"type": "string"}},
}

PASS1_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": _ITEM_PROPERTIES,
                            "required": ["anchor", "type", "title"],
                        },
                    },
                },
                "required": ["project", "items"],
            },
        },
    },
    "required": ["sections"],
}

PASS2_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "line_text": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "summary": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["line", "line_text", "title", "body"],
            },
        },
    },
    "required": ["items"],
}


# --- prompts -----------------------------------------------------------------

_DIGEST_CONVENTIONS = """\
You are digesting a personal daily journal into structured braindump entries.

Grouping: journal lines are informally grouped under a label/heading/topic
(e.g. "bd web", "introspect - fix the flaky test"). That label IS the
project the lines belong to — group actionable lines under the project they
most naturally belong to, inferring topic shifts from blank lines, labels,
or repeated keywords even without an explicit heading. If a whole day is a
flat unstructured list with no discernible project grouping at all, put
everything under one section named "journal-notes".

Prefer creating a NEW project section over folding lines into an unrelated
existing one just because nothing matches exactly — misfiled entries are
much harder to find later than stray projects are to merge.

Selecting lines: skip lines that already contain `[→` anywhere (already
digested — idempotent), skip blank lines, and skip lines that are pure
section labels with no actionable content of their own.

Sub-bullets / second-level items: when an actionable line has indented
sub-bullets under it, treat the parent line as ONE entry and never split its
sub-bullets into separate entries. Put each sub-bullet as its own string in
`sub_lines` (verbatim, only fixing obvious typos). These are the concrete
substance of the entry and are rendered into its body as a bullet list
automatically, so keep `body` as short framing prose and do NOT re-list them
there — and never summarize the concrete sub-items away.

Classifying: pick `type` = "todo" (actionable, has a verb, a task or a
question about doing something), "til" (something learned), "thought" (an
idea, observation, or open question), or "prompt" (a reusable prompt worth
saving). Infer `title` (<=60 chars), `tags` (1-5, prefer reusing the
existing tags below over inventing new ones), and a one-line `summary`.
`body` should lightly clean up typos/grammar while staying close to what was
actually written — do not invent facts.

Every item's `anchor` must be an exact opaque anchor shown before the line's
text below. Copy the anchor exactly; do not invent or alter it. Do not return
the source line number or line text — Python resolves the anchor to the exact
snapshot line."""


def build_pass1_prompt(
    numbered_lines: str,
    project_stats: Sequence[projects_mod.ProjectStats],
    top_tags: Sequence[tuple[str, int]],
) -> str:
    if project_stats:
        project_lines = "\n".join(_format_project_line(p) for p in project_stats)
    else:
        project_lines = "(no projects yet)"
    if top_tags:
        tag_line = ", ".join(f"{t} ({n})" for t, n in top_tags)
    else:
        tag_line = "(no tags yet)"

    return f"""{_DIGEST_CONVENTIONS}

## Existing projects
{project_lines}

## Frequently used tags
{tag_line}

## Today's journal (opaque snapshot anchors)
{numbered_lines}

Return JSON matching the schema:
{{"sections": [{{"project": ..., "items": [...]}}]}}."""


def _format_project_line(p: projects_mod.ProjectStats) -> str:
    bits = [f"- {p.name}"]
    if p.description:
        bits.append(f"— {p.description}")
    if p.area:
        bits.append(f"[{p.area}]")
    if p.state:
        bits.append(f"({p.state})")
    if p.tech_stack:
        bits.append(f"tech: {', '.join(p.tech_stack)}")
    return " ".join(bits)


def build_pass2_prompt(project: str, items: Sequence[ValidatedItem]) -> str:
    payload = [
        {
            "line": item.line,
            "line_text": item.line_text,
            "title": item.title,
            "body": item.body,
            "summary": item.summary,
            "tags": item.tags,
            "sub_lines": item.sub_lines,
        }
        for item in items
    ]
    return f"""You are lightly polishing braindump entries just extracted from a
journal for project "{project}". You have read-only access (Read/Glob/Grep)
to that project's local checkout in your working directory — use it only to
sharpen wording with real file/function names if it clearly helps; keep
changes light, this is a polish pass, not a rewrite.

Rules:
- Do NOT add or remove items.
- Do NOT change `line` or `line_text` — return them byte-for-byte identical,
  they anchor these entries back to the journal.
- You may improve `title` (still <=60 chars), `body`, `summary`, and `tags`.
- `sub_lines` are the concrete second-level items the user wrote under this
  line. They are read-only context and are rendered into the entry body
  automatically — do NOT repeat them in `body`, and never write a `body` that
  contradicts them (e.g. "no concrete list yet" when sub_lines is non-empty).
  Keep `body` as short prose that frames those items.

Items:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return JSON matching the schema, same number of items, same order, with
`line`/`line_text` unchanged."""


# --- orchestrator -------------------------------------------------------------


@dataclass
class SectionResult:
    project: str
    entry_ids: list[int] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)
    error: str | None = None


@dataclass
class ParseResult:
    day: date
    sections: list[SectionResult] = field(default_factory=list)
    unanchored: list[Annotation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    eligible: int = 0
    proposed: int = 0
    dropped: int = 0
    validation_failures: Counter[str] = field(default_factory=Counter)
    outcome: str = "finished"
    retry_attempted: bool = False
    retry_succeeded: bool = False
    retry_exhausted: bool = False
    warning: str | None = None

    @property
    def total_entries(self) -> int:
        return sum(len(s.entry_ids) for s in self.sections)


@dataclass(frozen=True)
class _Pass1Context:
    cfg: Config
    snapshot_lines: list[str]
    snapshot_anchors: dict[str, tuple[int, str]]
    existing_names: list[str]


def _eligible_line_count(lines: Sequence[str]) -> int:
    """Count non-empty, not-yet-annotated lines outside the scratchpad."""
    return sum(1 for line in lines if line.strip() and "[→" not in line)


def _proposal_count(data: dict[str, Any]) -> int:
    sections = data.get("sections", [])
    if not isinstance(sections, list):
        return 0
    total = 0
    for section in sections:
        if isinstance(section, dict) and isinstance(section.get("items"), list):
            total += sum(1 for item in section["items"] if isinstance(item, dict))
    return total


def _retry_pass1_prompt(prompt: str, failures: Counter[str]) -> str:
    details = ", ".join(f"{reason}: {count}" for reason, count in failures.items())
    return f"""{prompt}

Your previous response contained proposed candidates, but Python rejected every
candidate during validation. Retry once, preserving the same opaque anchors
exactly. Fix these validation problems: {details or "invalid candidate data"}.
Return only corrected JSON matching the schema."""


async def _retry_rejected_pass1(
    runner: Runner,
    prompt: str,
    context: _Pass1Context,
    result: ParseResult,
) -> list[ValidatedSection]:
    result.retry_attempted = True
    try:
        retry_data = await runner(
            _retry_pass1_prompt(prompt, result.validation_failures),
            cwd=context.cfg.home,
            tools="",
            json_schema=PASS1_SCHEMA,
        )
    except Exception as e:
        result.errors.append(f"pass 1 retry failed: {e}")
        retry_data = {"sections": []}
    result.proposed += _proposal_count(retry_data)
    retry_sections = validate_pass1(
        context.snapshot_lines,
        retry_data,
        context.existing_names,
        anchor_map=context.snapshot_anchors,
        diagnostics=result.validation_failures,
    )
    result.dropped = sum(result.validation_failures.values())
    if retry_sections:
        result.retry_succeeded = True
    else:
        result.retry_exhausted = True
        result.warning = (
            "All proposed candidates were rejected during validation after one retry."
        )
    return retry_sections


def _set_parse_outcome(result: ParseResult, sections: list[ValidatedSection]) -> None:
    if not result.eligible:
        result.outcome = "no_eligible"
    elif not result.proposed:
        result.outcome = "no_candidates"
    elif not sections:
        result.outcome = "validation_rejected"
    else:
        result.outcome = "created"


def _merge_pass2(
    items: Sequence[ValidatedItem], pass2_data: dict[str, Any]
) -> list[ValidatedItem]:
    by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for raw in pass2_data.get("items", []):
        if not isinstance(raw, dict):
            continue
        key = (raw.get("line"), raw.get("line_text"))
        by_key[key] = raw

    merged: list[ValidatedItem] = []
    for item in items:
        enhanced = by_key.get((item.line, item.line_text))
        if enhanced is None:
            merged.append(item)
            continue
        enhanced_tags = enhanced.get("tags")
        tags = _string_list(enhanced_tags) if enhanced_tags is not None else item.tags
        merged.append(
            replace(
                item,
                title=str(enhanced.get("title") or item.title),
                body=str(enhanced.get("body") or item.body),
                summary=str(enhanced.get("summary") or item.summary),
                tags=tags,
            )
        )
    return merged


async def _enhance_section_items(
    runner: Runner,
    section: ValidatedSection,
    local_dir: str | None,
    errors: list[str],
    report: ProgressCallback,
) -> list[ValidatedItem]:
    """Run pass 2 for one section, falling back to the pass-1 items on any failure."""
    if not local_dir or not Path(local_dir).is_dir():
        return section.items
    report(section.project, "enhancing")
    try:
        pass2_data = await runner(
            build_pass2_prompt(section.project, section.items),
            cwd=local_dir,
            tools="Read,Glob,Grep",
            json_schema=PASS2_SCHEMA,
        )
        return _merge_pass2(section.items, pass2_data)
    except Exception as e:
        errors.append(f"pass 2 failed for {section.project}: {e}")
        return section.items


def _create_section_entries(
    cfg: Config, project: str, items: list[ValidatedItem]
) -> tuple[SectionResult, list[Annotation]]:
    """Create one real entry per item and build the journal annotations for them."""
    section_result = SectionResult(project=project)
    annotations: list[Annotation] = []
    for item in items:
        original_input = item.line_text
        if item.sub_lines:
            original_input += "\n" + "\n".join(
                f"  - {_normalize_sub_line(s)}" for s in item.sub_lines
            )
        body = render_body_with_sub_lines(item.body, item.sub_lines)
        create_result = entries.create_entry(
            cfg,
            item.type,
            item.title,
            body,
            tags=item.tags,
            project=project,
            summary=item.summary or None,
            original_input=original_input,
        )
        section_result.entry_ids.append(create_result.entry.id)
        section_result.counts[item.type] += 1
        annotations.append(
            Annotation(
                line=item.line,
                line_text=item.line_text,
                type=item.type,
                entry_id=create_result.entry.id,
            )
        )
    return section_result, annotations


async def run_parse(
    cfg: Config,
    day: date,
    *,
    runner: Runner = claude_cli.run_claude,
    progress: ProgressCallback | None = None,
) -> ParseResult:
    """Digest one journal day into structured entries.

    1. Snapshot `journal.read_body`.
    2. Pass 1 (no tools, cwd = braindump home) proposes sections.
    3. `validate_pass1` sanitizes the proposal against the snapshot.
    4. Pass 2 per section (read-only tools, cwd = the project's local dir)
       lightly enhances title/body; falls back to pass-1 items when there's
       no local dir or the call raises.
    5. Per section: `entries.create_entry` for each item, then
       `apply_annotations` + `journal.replace_body`, immediately — so a
       crash only risks duplicating the section in flight.
    """

    def _report(project: str, status: str) -> None:
        if progress is not None:
            progress(project, status)

    body = journal.read_body(cfg, day)
    snapshot_lines = body.splitlines()
    snapshot_anchors: dict[str, tuple[int, str]] = {}
    result = ParseResult(day=day)
    scratchpad_idx = _scratchpad_start(snapshot_lines)
    eligible_lines = (
        snapshot_lines[:scratchpad_idx]
        if scratchpad_idx is not None
        else snapshot_lines
    )
    result.eligible = _eligible_line_count(eligible_lines)

    project_stats = projects_mod.list_projects(cfg)
    top_tags = tags_mod.tag_frequency(cfg).most_common(20)

    pass1_prompt = build_pass1_prompt(
        numbered_lines_for_prompt(body, anchor_map=snapshot_anchors),
        project_stats,
        top_tags,
    )
    try:
        pass1_data = await runner(
            pass1_prompt, cwd=cfg.home, tools="", json_schema=PASS1_SCHEMA
        )
    except Exception as e:
        result.errors.append(f"pass 1 failed: {e}")
        result.outcome = "error"
        return result

    existing_names = [p.name for p in project_stats]
    sections = validate_pass1(
        snapshot_lines,
        pass1_data,
        existing_names,
        anchor_map=snapshot_anchors,
        diagnostics=result.validation_failures,
    )
    local_dirs = {p.name: p.local_dir for p in project_stats}
    pass1_context = _Pass1Context(
        cfg=cfg,
        snapshot_lines=snapshot_lines,
        snapshot_anchors=snapshot_anchors,
        existing_names=existing_names,
    )

    result.proposed = _proposal_count(pass1_data)
    kept = sum(len(s.items) for s in sections)
    result.dropped = sum(result.validation_failures.values())
    logger.info(
        "parse %s: pass 1 eligible %d line(s), proposed %d item(s) in %d section(s); "
        "kept %d, dropped %d",
        day,
        result.eligible,
        result.proposed,
        len(sections),
        kept,
        result.dropped,
    )
    if result.dropped:
        logger.warning(
            "parse %s: %d proposed item(s) dropped in validation: %s",
            day,
            result.dropped,
            dict(result.validation_failures),
        )

    if not sections and result.proposed and result.eligible:
        retry_sections = await _retry_rejected_pass1(
            runner,
            pass1_prompt,
            pass1_context,
            result,
        )
        if retry_sections:
            sections = retry_sections

    _set_parse_outcome(result, sections)
    logger.info(
        "parse %s outcome=%s eligible=%d proposed=%d dropped=%d retry_attempted=%s "
        "retry_succeeded=%s",
        day,
        result.outcome,
        result.eligible,
        result.proposed,
        result.dropped,
        result.retry_attempted,
        result.retry_succeeded,
    )

    for section in sections:
        _report(section.project, "queued")

    working_body = body
    for section in sections:
        local_dir = local_dirs.get(section.project)
        enhanced_items = await _enhance_section_items(
            runner, section, local_dir, result.errors, _report
        )
        section_result, annotations = _create_section_entries(
            cfg, section.project, enhanced_items
        )

        working_body, unanchored = apply_annotations(working_body, annotations)
        journal.replace_body(cfg, day, working_body)
        result.unanchored.extend(unanchored)
        result.sections.append(section_result)
        _report(section.project, "done")

    return result


@dataclass
class InitiativeParseResult:
    """Outcome of importing unchecked list items from an initiative."""

    initiative_id: int
    todo_ids: list[int] = field(default_factory=list)
    skipped_checked: int = 0
    unanchored: list[Annotation] = field(default_factory=list)

    @property
    def created(self) -> int:
        return len(self.todo_ids)


def _authored_entry_body(cfg: Config, type_dir: str, entry: entries.Entry) -> str:
    full_path = store.full_path_for(cfg, type_dir, entry.file_path)
    _, markdown_body = store.read_markdown(full_path)
    _, authored, _ = entries.split_body(markdown_body)
    return authored


def _project_heading_matches(heading: str | None, project: str) -> bool:
    if not heading:
        return False
    return store.slugify(heading) == store.slugify(project)


def parse_initiative(cfg: Config, initiative_id: int) -> InitiativeParseResult:
    """Create todos for unchecked list items in an initiative body.

    Existing ``[→todo#id]`` marks are the idempotency key.  Project ownership
    is intentionally conservative: one linked project owns every todo; with
    multiple linked projects only a matching ``## project`` heading assigns
    ownership, and all other todos remain unlabelled.
    """
    found = entries.find_by_id(cfg, initiative_id)
    if found is None or found[1].type != "initiative":
        raise ValueError(f"entry #{initiative_id} is not an initiative")
    type_dir, initiative = found
    body = _authored_entry_body(cfg, type_dir, initiative)
    result = InitiativeParseResult(initiative_id=initiative.id)
    items = entries.parse_source_document(body)
    result.skipped_checked = sum(1 for item in items if item.checked)

    project_names = [
        project.title
        for project in entries.resolve_relations(cfg, initiative, "project_ids")
        if project is not None
    ]
    sole_project = project_names[0] if len(project_names) == 1 else None
    annotations: list[Annotation] = []
    for item in items:
        if item.checked:
            continue
        project = sole_project
        if project is None and len(project_names) > 1:
            matching = next(
                (
                    name
                    for name in project_names
                    if _project_heading_matches(item.heading, name)
                ),
                None,
            )
            project = matching
        created = entries.create_entry(
            cfg,
            "todo",
            item.text,
            item.text,
            project=project,
            original_input=item.line_text,
            type_fields={"initiative_id": initiative.id},
        )
        result.todo_ids.append(created.entry.id)
        annotations.append(
            Annotation(
                line=item.line,
                line_text=item.line_text,
                type="todo",
                entry_id=created.entry.id,
            )
        )

    if annotations:
        new_body, result.unanchored = apply_annotations(body, annotations)
        if new_body != body:
            entries.update_entry(cfg, initiative.id, {}, body=new_body)
    return result
