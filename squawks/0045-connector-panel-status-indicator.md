# Squawk 0045: Connector panel has no at-a-glance connection status (MCP-panel parity)

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-03
**Completed**: 2026-09-03

## Report

A connector's health is only visible by manually clicking "Run doctor" and reading
prose ("ok: poll loop connected"). The MCP server panel already solves this: a shared
`indicator-led` component (`indicator-led--success` / `--idle`) with a connection
label and a Refresh/Reset pair near the top of the panel. Operator asked for the same
treatment on connectors. Fix: REUSE the existing `indicator-led` component (do not
invent a new one) — show a connection LED with an accessible label in the connector
panel's header area, driven by the doctor result; keep the existing doctor button as
the manual re-probe (relabel to match the MCP panel's verb if that reads better).

**Pinned technical decisions** (FD, per the mission-debrief routing rule — recorded so
this stays a squawk rather than a design conversation): (1) the panel probes doctor
ONCE automatically when an existing connector is opened — that is the operator's
"auto green dot"; no polling loop, no probe on the create form; (2) LED states map
doctor `status` → `ok`→success, `degraded`→ an idle/warn state already available on the
component, `failed`→ the component's error/idle state; disabled connectors show idle;
(3) no new CSS component. If the implementer finds this needs behavior beyond that,
STOP with `[BLOCKED:exceeds-squawk-scope]` rather than designing in place.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:505-518` — the `indicator-led` + last-updated pattern to mirror
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js:331-342` — today's doctor-only affordance
- Operator screenshots (connector panel vs MCP panel), 2026-09-03

## Corrective Action

Added a connection-status LED to the connector panel's header, reusing the
existing `indicator-led` component (components.css) — no new CSS component,
per pinned decision #3.

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js`:
  - Header now renders a `.connector-status-row` (LED + text label) under the
    connector name, edit-mode only — absent on the create form (pinned
    decision #1's "no probe on the create form" implies no LED there either,
    since there's nothing yet to reflect).
  - On opening an EXISTING connector, fires the existing
    `POST /api/connectors/{id}/test` doctor endpoint exactly ONCE
    (no polling loop) and applies the result to the LED — the operator's
    "auto green dot" (pinned decision #1).
  - New `_connectorLedState` / `_connectorLedLabel` helpers map doctor
    `status` (`DoctorReport` in `the_one/connectors/base.py`: `"ok"` /
    `"degraded"` / `"failed"`) plus the `/test` response's `disabled` flag
    onto the LED's four existing modifier states: `ok`→`success`,
    `degraded`→`warning`, `failed`→`danger`, and a disabled connector always
    shows `idle` regardless of the underlying probe status (pinned
    decision #2).
  - `applyDoctorStatusToLed` is shared between the auto-probe and the
    existing "Run doctor" button's click handler, so a manual re-probe keeps
    the LED in sync too. The Diagnostics section's `Run doctor` button and
    its result prose are otherwise untouched — kept as the manual re-probe,
    testid unchanged (`connector-doctor-btn` / `connector-doctor-result`),
    same `aria-live="polite"` behavior. Relabeling was considered (mirroring
    the MCP panel's verb) but "Run doctor" already reads at least as well as
    "Refresh connection" for a connector, so it was left as-is to minimize
    blast radius.
  - New testids: `connector-status-led`, `connector-status-label`. The LED
    carries its own `aria-label` (state text, e.g. "Connected" / "Not
    connected" / "Degraded" / "Disabled" / "Checking connection…") since the
    adjacent visible label conveys the same state, not an independent action
    — closer to the `test-result-*` shape than the MCP panel's
    action-button-adjacent case, but an explicit `aria-label` is kept on the
    LED itself (not just the sibling label span) to stay unambiguous for
    screen-reader users regardless of DOM traversal order.
- `the_one/interfaces/web/static/css/studio.css`: added
  `.area-studio .connector-status-row` / `.connector-status-label` — layout
  only (flex row, spacing, secondary text color); the LED's own color/shape
  comes entirely from the pre-existing `.indicator-led` / `.indicator-led--*`
  rules in `components.css`, unchanged.
- `tests/browser/test_studio_connector_editor.py`: two new browser tests —
  `test_studio_connector_create_form_shows_no_status_led` (no LED on the
  create form) and `test_studio_connector_status_led_reflects_doctor_result_on_open`
  (opening an existing tokenless-discord connector shows the LED with a
  non-empty accessible label, then settles to `indicator-led--danger` /
  "Not connected" from the auto-probed doctor failure — the same
  deterministic failure shape the pre-existing manual-doctor test pins).

No new endpoint, no caching/persistence, no polling — the auto-probe is a
single `fetch` per panel-open, matching pinned decision #1 exactly. Squawks
0042/0043/0044's uncommitted Pairing-section work in the same file was left
untouched; the new code was inserted around it, not through it.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio` (foreground):
  `150 passed, 3 skipped in 272.80s` — includes the two new browser tests in
  `test_studio_connector_editor.py` (file went from 7 to 9 tests, both new
  ones green on the first run, no rerun needed).
- `.venv/bin/ruff check the_one/ tests/ && .venv/bin/ruff format --check the_one/ tests/`
  (CI's exact lint gate): `All checks passed!` / `401 files already formatted`.
- Follow-up (turnaround 2026-09-03b): `connector-status-led` and
  `connector-status-label` had not been added to
  `docs/ui-testid-registry.md`, which broke
  `tests/test_ui_guards.py::test_testids_in_source_are_registered` for the
  batch. Registered both as part of the batch-wide registry fix (batch also
  covered Squawk 0043); `tests/test_ui_guards.py` (14 tests) now passes.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-03b — two passes (blocking dead-link issue routed back into 0046, re-reviewed after fix)
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-03b batch commit (PR follows)
