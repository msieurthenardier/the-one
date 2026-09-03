# Squawk 0044: Pairing control is filed under "Diagnostics", implying it's optional

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-03
**Completed**: 2026-09-03

## Report

The connector editor puts "Generate pairing code" inside the **Diagnostics** section,
next to "Run doctor". Pairing is not diagnosis — it is the required enrollment action
that admits the first peer, and placing it under Diagnostics actively misleads
(operator report: "its actually a required thing"). Fix (relocation only, no behavior
change): move the pairing button + result out of Diagnostics into their own section
near the admission fields (allowlist/always-listen), titled for what it does (e.g.
"Pairing" or "Admit a peer"), with one line of inline help naming the flow (peer DMs
the bot → generate → peer replies with the code within 10 minutes). Diagnostics keeps
the doctor control only. Preserve existing `data-testid` hooks.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js:331-352` — Diagnostics section holding both controls
- `tests/browser/test_studio_connector_editor.py` — existing pairing coverage to keep green
- Operator report + screenshot, 2026-09-03

## Corrective Action

Relocated the pairing control (button + result element — code element, copy
button, expiry span, as left by squawk 0043) out of the Diagnostics section
in `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` into
its own new "Pairing" section, positioned immediately after Admission
(allowlist peers/channels + always-listen fields) and before the Channel →
agent map section — i.e. next to the admission fields it feeds, per the
squawk's placement guidance. Added one line of inline help under the section
title (`.section-description`, the established sits-under-title pattern
already used by the Built-in Tools tab — see `studio.css`'s "friendly
description sits flush under each section-title" comment) naming the flow:
"The peer DMs the bot, you generate a code, and the peer replies with it
within 10 minutes." Diagnostics now holds only the doctor control ("Run
doctor" + its result element); the pairing button's click handler (fetch to
`/api/connectors/{id}/pairing-code`, code-row rendering, copy-to-clipboard)
moved with it verbatim — no behavior change. Both controls remain edit-mode
only (`!isCreate`), matching their prior gating.

All existing `data-testid` hooks (`connector-pairing-btn`,
`connector-pairing-result`, `connector-pairing-code`,
`connector-pairing-copy-btn`, `connector-doctor-btn`,
`connector-doctor-result`) and the `role="status"`/`aria-live="polite"`
attributes on both result elements were preserved unchanged. No test edits
were needed — `tests/browser/test_studio_connector_editor.py` locates
controls by `data-testid` only, never by DOM position within Diagnostics.

JS line delta: `connector-editor.js` went from 543 to 555 lines (+12) — pure
relocation plus the new section title, help paragraph, and one added
comment block; the moved code (button, result element, click handler) is
otherwise unchanged.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio` (foreground,
  ~4m39s): 147 passed, 3 skipped, 1 failed —
  `test_flow_studio_mcp_editor.py::test_server_info_website_and_icon_allow_https`,
  an MCP-source server-info test unrelated to the connector editor. Re-ran in
  isolation (`.venv/bin/python -m pytest
  tests/browser/test_flow_studio_mcp_editor.py::test_server_info_website_and_icon_allow_https
  -m browser`) and it passed — confirms full-lane flake per standing
  disposition, not a regression from this change. All 7 tests in
  `tests/browser/test_studio_connector_editor.py`, including the two pairing
  tests, passed in the full-lane run.
- `.venv/bin/ruff check the_one/ tests/ && .venv/bin/ruff format --check the_one/ tests/`
  (CI's exact lint gate): both passed clean (401 files already formatted).

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-03b — two passes (blocking dead-link issue routed back into 0046, re-reviewed after fix)
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-03b batch commit (PR follows)
