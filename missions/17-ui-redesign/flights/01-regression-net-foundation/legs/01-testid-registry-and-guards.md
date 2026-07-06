# Leg: testid-registry-and-guards

**Status**: completed
**Flight**: [Regression-Net Foundation](../flight.md)

## Objective

Create the UI testid registry (`docs/ui-testid-registry.md`) and the guard test suite (`tests/test_ui_guards.py`) enforcing testid↔source sync and an innerHTML dynamic-sink baseline freeze.

## Context

- Flight DD "Guards ship as pytest tests": unit-tier, runs in `make test-unit` and existing Concourse lanes; no new CI plumbing.
- Flight DD "Testid registry": two id classes — literal ids and parametric-prefix ids; loud failure with exact diff.
- Flight DD "innerHTML baseline-freeze": per-file allowlist of current dynamic sink sites; guard fails on NEW sites only; single-sink enforcement deferred to Flight 4.
- Ground-truth calibration (verified 2026-07-03, **indicative order-of-magnitude only** — the extractor bootstrap in Guidance §3 is the authority for exact baseline numbers): on the order of 190 literal testids (both attr-form and setAttribute-form), ~30 setAttribute-concat parametric sites plus ~17 parametric-in-HTML-string sites, ~160 innerHTML/insertAdjacentHTML write sites of which ~95 are dynamic and exactly 65 static under the classification rule below; zero backtick-template innerHTML assignments exist; exactly one innerHTML *read* site (`connector-editor.js:3508 — "var originalHtml = btn.innerHTML;"`).

## Inputs

- `the_one/interfaces/web/static/js/**/*.js` — source of truth for testids and sink sites
- Existing test conventions: `tests/test_token_definitions.py` (same genre: repo-source lint-by-pytest; mirror its style)

## Outputs

- `docs/ui-testid-registry.md` — registry with two tables (literal ids; parametric prefix families), each row: id/prefix, surface (chat/studio/admin/shell), notes
- `tests/test_ui_guards.py` — three tests minimum:
  1. `test_testids_in_source_are_registered` — extract ids from source, diff against registry, fail with exact add/remove list
  2. `test_registered_testids_exist_in_source` — reverse direction
  3. `test_no_new_dynamic_innerhtml_sinks` — classify all `.innerHTML`/`.insertAdjacentHTML` assignment sites; compare against a frozen per-file baseline embedded in the test module (dict: relative path → count AND normalized site snippets); fail if any file's dynamic sites include a snippet not in baseline (catches offsetting add+remove) or a new file appears

## Acceptance Criteria

- [x] `docs/ui-testid-registry.md` exists; every literal testid in source appears exactly once; every parametric family registered by prefix (185 literals, 46 prefixes, 4 manual exceptions; duplicate-row detection enforced by the sync test)
- [x] `tests/test_ui_guards.py` passes via `.venv/bin/python -m pytest tests/test_ui_guards.py -x --timeout 60` (5 passed)
- [x] Full unit tier still green: `make test-unit` — 3680 passed; one failure, `test_lifespan.py::test_lifespan_drains_session_registry` (`RuntimeError: session registry is shutting down`), verified **pre-existing and unrelated**: fails identically with this leg's files removed, passes in isolation and module-alone. See flight-log anomaly.
- [x] Guard failure modes verified: probe `data-testid="zz-probe-id"` in `general-tab.js` → test 1 failed naming `zz-probe-id` + file; probe `panel.innerHTML = zzProbeVar;` in `general-tab.js` (a file already in baseline, exercising snippet-level detection) → test 3 failed naming file + snippet. Both probes reverted (working tree verified clean of product-JS changes).
- [x] `ruff check` and `ruff format --check` clean on new/changed Python (`tests/test_ui_guards.py`, `tests/_ui_guard_helpers.py`)

## Verification Steps

- Run the pytest command above; confirm 0 failures
- Probe-edit verification per criterion 4 (add `data-testid="zz-probe-id"` to any JS string; run test 1; expect failure naming `zz-probe-id`; revert. Add `el.innerHTML = someVar;` to a JS file; run test 3; expect failure naming the file; revert)
- `make test-unit` green

## Implementation Guidance

1. **Extractor** (in `tests/test_ui_guards.py` or a small helper module under `tests/`). Operate on **joined statements**, not raw lines (multi-line HTML-string concatenation splits `data-testid` values across lines). Four pattern classes:
   - **(a) Literal, attr-form**: `data-testid="..."` inside HTML strings where the quoted value is uninterrupted.
   - **(b) Literal, setAttribute-form**: `setAttribute('data-testid', '...')` with a single string-literal argument.
   - **(c) Parametric**: two mechanisms — `setAttribute('data-testid', 'prefix-' + …)` (~30 sites) AND parametric-in-HTML-string, where the quoted attr value is interrupted by `' +` (e.g. `data-testid="connector-acl-axis-' + axis + '-' + account.id + '"` in `connector-editor.js`, `discoverable-dropdown.js`; ~17 sites) — capture the static prefix from either. Beware the false-parametric case: `data-testid="provider-card" data-id="'+id` (`providers-grid.js:78`) — `provider-card` is a LITERAL (the concatenation belongs to `data-id`); anchor to the `data-testid` attribute's own quoted value, not to a `+` later in the statement.
   - **(d) Variable-carried literals** (invisible to regex): ids passed through variables/parameters — known cases: `saveTestId` ternary over `'create-and-test-connector-btn'`/`'save-connector-btn'` (`connector-editor.js:337,342`) and `renderLifecycleSelect(..., testId, ...)` call sites passing `'connector-continuation-input'`/`'connector-idle-timeout-input'` (`connector-editor.js:436,452`, attribute emitted near line 205). Handle via a **manual-exceptions table** in the registry: the guard skips extraction for these but asserts each still appears as a string literal somewhere in source (so deletion is caught).
   - **Selector references do NOT count as definitions**: `[data-testid="..."]` occurrences in `querySelector` calls (~65) are excluded from "defined in source". Ids that are selector-referenced but never defined are surfaced by the guard as a distinct failure. Known instance to disposition during implementation: `connector-test-status` (queried at `connector-editor.js:1775,1828`, defined nowhere) — verify it is truly dead; if so log it to the mission's Known Issues and either fix or allowlist it explicitly with a comment.
2. **Sink classifier** — the rule that ground-truthed at 103/65:
   - Join logical statements to the terminating `;` before classifying (multi-line concatenations must classify as dynamic).
   - Assignment anchor `\.(innerHTML|outerHTML)\s*=[^=]` plus `insertAdjacentHTML(` calls; exclude reads (no `=` or `==`/`===` comparisons).
   - STATIC (exempt): complete single string-literal RHS terminated by `;` (includes `= '';`).
   - DYNAMIC (frozen): everything else — variable, function call, or any concatenation, even when it starts with a literal (e.g. `= '<span>' + escapeHtml(x) + '</span>';` in `provider-models.js`, `mcp-server-editor.js`, `connectors-tab.js`, `mcps-tab.js`, `tools-tab.js`).
   - Baseline stores per-file normalized snippets (whitespace-collapsed first 80 chars of the statement) — snippet match, not bare counts.
3. **Registry generation**: bootstrap the registry by running the extractor once and writing the doc; hand-annotate surface column. Keep the doc the human-readable source; the test compares live extraction against the doc's parsed tables.
4. **Registry doc format**: parse-friendly markdown tables (one row per id/prefix); a surface cell may list multiple areas for shared-component ids (e.g. `dialog.js` modal buttons); include the manual-exceptions table (pattern class d); include a header comment stating the sync test will fail on drift and how to update.
5. Mirror `tests/test_token_definitions.py` style (plain pytest, pathlib file walking, no new dependencies). No pytest marker needed — unmarked tests run in the unit tier automatically (pyproject `addopts` deselects only marked tiers).
6. **Probe verification detail** (AC 4): place the innerHTML probe in a file already in the baseline — this exercises snippet-level detection (the offsetting add+remove property), not just the new-file path.

## Edge Cases

- **Parametric id with two dynamic segments** (`'mcp-tool-toggle-' + source.id + '-' + toolName`): register prefix `mcp-tool-toggle-` — prefix match covers it.
- **Duplicate literal ids across files** (shared components rendered in multiple areas): registry lists the id once; extractor de-duplicates.
- **JS in comments**: acceptable to classify commented-out code like live code (simpler; if it causes a false positive, delete the dead code instead of special-casing).

## Files Affected

- `docs/ui-testid-registry.md` — created
- `tests/test_ui_guards.py` — created
- (possibly) `tests/_ui_guard_helpers.py` — created if extraction logic is better factored out

---

## Citation Audit

Citations verified at leg design time against current code by the Flight 1 second-pass architect review (2026-07-03): 166 literal testids (exact), ~35 parametric, 168 write sites → 103 dynamic/65 static under the statement-joining rule, one innerHTML read at `connector-editor.js:3508 — "var originalHtml = btn.innerHTML;"`, zero backtick innerHTML RHS. `provider-card`/`data-id` false-parametric case confirmed real.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (batch flight commits per agentic-workflow; `completed` at flight review)
- [x] Check off this leg in flight.md
