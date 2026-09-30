# Squawk 0104: Squawk 0102's Server-section repaint trips the dynamic innerHTML-sink ratchet

**Status**: completed
**Type**: defect
**Severity**: grounding
**Reported**: 2026-09-30
**Completed**: 2026-09-30

## Report

`tests/test_ui_guards.py::test_no_new_dynamic_innerhtml_sinks` fails on `main`.
Squawk 0102 (commit `9d3690b`) added `tmp.innerHTML = html;` in
`mcp-server-editor.js::syncServerInfoSection`, and that site is not in the frozen
`DYNAMIC_SINK_BASELINE`. As a result `make test-unit` is red on `main`. 0102's
verification ran only the studio browser lane, which never runs this unit guard.
This is grounding because it blocks the v0.9.1 release.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js::syncServerInfoSection` — `tmp.innerHTML = html;`, where `html` is `renderServerInfoSection(cache)`.
- `tests/test_ui_guards.py::DYNAMIC_SINK_BASELINE["areas/studio/mcp-server-editor.js"]` — has no matching entry. The same renderer's output already reaches the DOM through the baselined `container.innerHTML = html;` in `renderMcpSourceEditor`.
- It fails when run alone: `pytest tests/test_ui_guards.py::test_no_new_dynamic_innerhtml_sinks`.

## Corrective Action

Operator decision (2026-09-30): baseline the site, with a comment. The repaint
passes the same escaped `renderServerInfoSection` output that the mount path
already sends through a baselined sink, so no new data reaches the DOM. Precedent:
Flight 6 (`189a23a`) extended the baseline. Rejected: rewriting
`renderServerInfoSection` with DOM APIs (disproportionate for a squawk) and
reverting 0102.

Applied: `tests/test_ui_guards.py` adds `"tmp.innerHTML = html;"` to
`DYNAMIC_SINK_BASELINE["areas/studio/mcp-server-editor.js"]`. It sits first in
the list, matching its file position (the classifier emits
`syncServerInfoSection`'s site before `renderMcpSourceEditor`'s
`container.innerHTML = html;`), with a comment citing squawks 0102 and 0104 and the
shared, escaped `renderServerInfoSection` output. The snippet string is exactly
what `classify_sinks()` produces for the site; it was read back from the live
classifier, not hand-written. The guard logic and the JS are unchanged. No test
pins a total site count. The baseline's header comment still says "92 sites
across 27 files" (M17 F4 L1). That figure is historical prose and was already
stale: the live count is now 68 dynamic sites across 21 files. It was left as is.

## Verification

- `.venv/bin/python -m pytest tests/test_ui_guards.py -x -q`: 14 passed. The
  guard includes `test_no_new_dynamic_innerhtml_sinks`, which failed before
  the fix.
- `ruff check` and `ruff format --check` on `tests/test_ui_guards.py`: clean.
- Full unit gate (`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/ -m
  'not browser and not live and not pixel' -x -q`):
  - Run 1 stopped at 1 failed, 2571 passed on
    `tests/test_kb_watcher.py::TestStopAndDrain::test_drain_three_live_entries_under_a_second`.
    That test asserts a wall-clock drain under 1.0s, which is load-sensitive
    and unrelated to this change. The file passed alone (39/39), and the test
    passed 3 of 3 times in isolation.
  - Run 2: **4851 passed, 13 skipped, 573 deselected** (13m22s), exit 0.

## Sign-Off

Independent Reviewer: `[HANDOFF:confirmed]`, no blocking issues. The baseline list equals the live `classify_sinks()` output exactly. The justification holds: every server-supplied value in `renderServerInfoSection` is escaped or URL-sanitized. `test_ui_guards.py` passes 14/14. Non-blocking: the baseline header's stale "92 sites across 27 files" prose was left as is.

Commit: `squawk: turnaround 2026-09-30` on branch `squawk/turnaround-2026-09-30`.
