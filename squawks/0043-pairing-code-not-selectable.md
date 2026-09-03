# Squawk 0043: Generated pairing code is not selectable or copyable

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-03
**Completed**: 2026-09-03

## Report

The pairing code renders as plain text inside `div.connector-pairing-result`
("Code: 1651d37a (expires ...)"). The operator cannot highlight or copy it — the one
thing the string exists for is to be transcribed into a chat window. Fix: render the
code itself in a distinct copyable element (a `<code>`-styled span with
`user-select: text` plus a copy-to-clipboard affordance, mirroring whatever copy
pattern the codebase already uses for credentials/ids if one exists; otherwise a small
"Copy" button next to it). Keep the expiry text as ordinary prose. Keep the existing
`data-testid="connector-pairing-result"` so current browser tests stay valid; add one
test asserting the code is in its own element and copyable-shaped.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js:348-352` — the result div
- Operator screenshot, 2026-09-03: "the code is not hightlightable nor copyable"

## Corrective Action

`connector-editor.js`'s pairing-code click handler (`the_one/interfaces/web/static/js/areas/studio/connector-editor.js`)
no longer collapses the result into a single fused prose string. On a
successful response it clears `pairingResultEl` and builds:

- a `.connector-pairing-code-row` holding a `<code data-testid="connector-pairing-code">`
  (the code text only, `user-select: text`) and a
  `<button data-testid="connector-pairing-copy-btn" aria-label="Copy pairing code">Copy</button>`;
- an ordinary `<span class="connector-pairing-expiry">Expires …</span>` next to it.

The copy button follows the codebase's existing `<code>` + copy-button +
`navigator.clipboard.writeText` precedent (`markdown.js`'s `renderCodeBlock`
copy affordance for fenced code blocks), with the same `document.execCommand('copy')`
fallback used by `provider-editor.js`/`self-configuration-tab.js` for
browsers without Clipboard API access, and reports success/failure via the
existing `window.App.showFlash` toast. `pairingResultEl` keeps its
`data-testid="connector-pairing-result"`, `role="status"`, and
`aria-live="polite"` unchanged, so the announcement and existing test
selector both still work.

Added matching CSS in `the_one/interfaces/web/static/css/studio.css`
(`.connector-pairing-code-row`, `.connector-pairing-code`,
`.connector-pairing-expiry`) — monospace, bordered, `user-select: text` for
the code; caption-sized muted prose for the expiry.

JS delta: `connector-editor.js` grew from 514 to 543 lines (+29).

## Verification

- Updated the existing `test_studio_connector_pairing_code_generation`
  browser test (`tests/browser/test_studio_connector_editor.py`) — its
  assertion now checks the result region for "Expires" (the old fused
  "Code:" prose no longer exists as a single string).
- Added `test_studio_connector_pairing_code_is_selectable_and_copyable`,
  which generates a pairing code and asserts: the `connector-pairing-code`
  element is visible and holds non-empty text that does NOT contain
  "expires" (i.e. it's the code alone, not the old fused prose), that text
  is contained within the overall result region, and the
  `connector-pairing-copy-btn` is visible with a non-empty `aria-label`.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio` — 148
  passed, 3 skipped (0 failures), including all 7 tests in
  `test_studio_connector_editor.py` (one new). Single run, no flake
  encountered, no isolated-rerun needed.
- `.venv/bin/ruff check the_one/ tests/` — all checks passed.
- `.venv/bin/ruff format --check the_one/ tests/` — 401 files already
  formatted (no diffs).
- Follow-up (turnaround 2026-09-03b): `connector-pairing-code` and
  `connector-pairing-copy-btn` had not been added to
  `docs/ui-testid-registry.md`, which broke
  `tests/test_ui_guards.py::test_testids_in_source_are_registered` for the
  batch. Registered both as part of the batch-wide registry fix (batch also
  covered Squawk 0045); `tests/test_ui_guards.py` (14 tests) now passes.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-03b — two passes (blocking dead-link issue routed back into 0046, re-reviewed after fix)
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-03b batch commit (PR follows)
