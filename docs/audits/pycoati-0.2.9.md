# Pycoati 0.2.9 audit

## Scope and source record

- Historical audit checkout: `/Users/mojzis/worktrees/braindump--adopt-pycoati-accepted-findings-in-brain`
- Pre-integration task source: `cc51dc3e1554ed96bb5e5e163c0f0fbfcf5255f1`
- Local `main` merged, no remote contact: `d7a749a7e92268e66a1193d24d70fcacf0918eca`
- Post-integration source used for the initial audit: `57d5704599660f4d72def7cb8652b1b637ff1892`
- Dependency source before/after: `pycoati>=0.2.9`; locked `pycoati 0.2.9`; no lock movement
- Tool before/after: pycoati `0.2.9` / `0.2.9`; Madoqua `0.2.3` floor retained

The audit is periodic evidence, not a hook or CI gate. Pycoati remains out of
Madoqua and CI. Run from the final prepared checkout and compare the checkout
first:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
test "$(git rev-parse --show-toplevel)" = "$REPO_ROOT"
git status --short
git rev-parse HEAD
git diff --check
```

Prerequisites and preparation (once per fresh checkout):

```bash
uv sync --all-extras --all-groups
uv run madoqua install
uv run --frozen --no-sync pycoati --version
```

The version command must report `pycoati 0.2.9`. Pytest and pytest-cov come
from the frozen environment; do not install or sync during read-only QA.

## Commands and evidence

Use only disposable output paths outside the repository. The three JSON files
are raw, actionable-default, and full-including-accepted evidence respectively:

```bash
uv run --frozen --no-sync pycoati . --format json --no-accept -o /private/tmp/braindump-pycoati-raw.json
uv run --frozen --no-sync pycoati . --format json -o /private/tmp/braindump-pycoati-actionable.json
uv run --frozen --no-sync pycoati . --format json --include-accepted -o /private/tmp/braindump-pycoati-full.json
uv run --frozen --no-sync pycoati . --format pretty
uv run --frozen --no-sync python scripts/qa_pycoati_acceptance.py
```

Inspect stderr for warnings on every JSON command; stdout is reserved for the
inventory when `-o` is used. Check `tool.ran_pytest` and `tool.ran_coverage`
before trusting suite metrics, then inspect the inventory's tool and suite
fields, every ranked test, and every active signal. The helper creates its own
temporary project and output, prints visible PASS/FAIL lines, and removes all
of it on exit. It verifies accepted reasons, unchanged raw test evidence,
fingerprint invalidation, `unknown_test`, `signal_not_active`, and
`content_changed`, continued pytest/coverage execution, and independent
actionability of an active signal.

## Observed audit

Initial raw command at post-integration source `57d5704599660f4d72def7cb8652b1b637ff1892`:

- Command result: exit `0`; 23 test files discovered
- pycoati `0.2.9`; `ran_pytest=true`; `ran_coverage=true`
- Suite: 379 collected tests; 40.71 seconds; 85.71428571428571% line coverage
- Accepted: 0; stale: 0 (`--no-accept` intentionally ignores the baseline)
- stderr: discovery INFO only; no warning or pytest/coverage failure
- Ranked tests: setup-heavy/slow-scoring ordinary tests; intentional desktop
  boundary signals reviewed below; no dead test requiring deletion
- Checked subprocess review: the three subprocess tests use `check=False` and
  assert the returned exit code, so they are ordinary assertion verification,
  not unchecked child-process verification. No `check=True` cases were present.

The sequential default command result was exit `0`, with 379 tests, 24.40
seconds, 85.71428571428571% coverage, pytest/coverage both true, 2 accepted
findings, and 0 stale entries. The sequential `--include-accepted` result was
exit `0`, with 379 tests, 22.85 seconds, 85.71428571428571% coverage,
pytest/coverage both true, 2 accepted findings, and 0 stale entries. Both
stderr streams contained discovery INFO only. The default shortlist suppresses
only tests whose active signals are fully accepted; `--include-accepted`
restores them. Runtime seconds vary with machine load and subprocess scheduling;
compare test counts, coverage, signals, and raw evidence rather than requiring
identical wall-clock timing.

## Accepted findings

Both entries in `.pycoati-accept.toml` were reviewed against the merged source,
use exact nodeids, one active signal, substantive reasons, the current review
date, and current fingerprints:

- `tests/test_desktop.py::test_brand_macos_app_does_nothing_off_darwin` —
  `zero_asserts`; off-macOS behavior is the no-import/no-raise contract, and a
  monkeypatched Foundation failure sentinel makes an accidental import fail.
- `tests/test_desktop.py::test_run_app_brands_before_pywebview_is_imported` —
  `mock_overuse`; three seam stubs isolate branding, webview import, and server
  probing so the observable ordering contract can be asserted without opening
  a desktop window.

No acceptance covers a gap, uses a wildcard, or imports an Albert decision.
No remaining real verification weaknesses were confirmed. The setup-heavy
and interaction-boundary signals remain visible in raw/full evidence for future
review; they are not changed into broad suppressions.

## Functional QA preparation and cleanup

The application route remains the isolated synthetic-data CLI round trip in
`QA.md`: set a disposable `BRAINDUMP_DIR`, create distinct CLI/browser todos,
exercise show/update/list/search/done/show, and append historical/effective
journal days. Do not import data, invoke Parse, use real credentials, attach to
live services, or write outside the temporary root. The check phase runs that
route from the final checkout without dependency installation. Remove the
owned scratch directory and stop any owned server/native process after the
evidence is recorded.

Pycoati's helper is independent of that application route and cleans its own
`TemporaryDirectory`; it does not touch the personal store or repository.
