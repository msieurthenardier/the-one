# Squawk 0035: Document the studio lane's full-run timing flake as a standing pattern

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: 2026-09-02

## Report

Three occurrences across two flights of the same shape: a studio browser-lane test
fails on a FULL-lane run with an element-wait timeout, then passes clean in isolation
within seconds (Flight 3 leg 2: `test_last_updated_renders_relative_time_format`;
leg 3: `test_studio_section_nav_renders_four_buttons`; Flight 3 debrief run:
`test_studio_connector_enabled_checkbox_unchecked_persists_disabled`, isolated rerun
2.5s clean). Each was re-diagnosed from scratch. Add a standing note in the studio
lane's conftest or lane header: full-run timing flakes are a known characteristic;
isolated-rerun-before-treating-as-regression is the standing disposition.

## Evidence

- Flight 3 flight-log entries (legs 2, 3) and flight-debrief Test Metrics (2026-09-02)
- Raised by the Flight 3 debrief, Developer interview recommendation 3

## Corrective Action

Added a standing-pattern paragraph to `tests/browser/conftest.py`'s module
docstring — the shared fixture module every `--lane` (chat/studio/system/
shared) imports, so it's the one place a person debugging any full-lane
failure looks first, not just studio. Content: full-lane timing flakes are
a known standing characteristic, citing all five dated occurrences briefly
(2026-09-01 Flight 23/3 leg 2 `test_last_updated_renders_relative_time_format`;
2026-09-01 leg 3 `test_studio_section_nav_renders_four_buttons`; 2026-09-02
Flight 23/3 debrief run `test_studio_connector_enabled_checkbox_unchecked_persists_disabled`
(isolated rerun 2.5s clean); 2026-09-02 squawk 0032 verification
`test_create_stdio_source` and `test_enter_commits_focused_tab`); standing
disposition is isolated-rerun-before-treating-as-regression; a flake that
also fails isolated is a real failure. Doc/comment-only — no retry logic,
timeout changes, or test modifications (those are design decisions outside
this squawk's scope).

## Verification

`git diff --stat tests/browser/conftest.py` → 14 insertions, 0 deletions,
docstring-only (no code lines touched). `PYTHON=.venv/bin/python bash
scripts/run-tests.sh -m browser tests/browser/ --collect-only -q --timeout 30`
(foreground) → **475/487 tests collected (12 deselected)** in 0.16s, no
collection errors — confirms the touched conftest still imports/collects
cleanly across every lane (the 12 deselected are the pre-existing
`pixel`-marked visual-snapshot tests, unrelated to this change).

## Sign-Off
**Reviewer**: independent batch Reviewer (Haiku), squawk/turnaround-2026-09-02
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-02 batch commit (PR follows)
