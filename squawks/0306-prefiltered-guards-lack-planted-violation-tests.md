# Squawk 0306: the pre-filtered source-scan guards have no test that they still fire

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: 2026-11-02

## Report
Mission 34 Flight 1 sped up four source-scan guards by checking a cheap substring before running the expensive scan. Each pre-filter was argued exact at review: it should never skip a file the full scan would flag. No test proves it, so a later edit to a needle list could quietly turn a guard into one that never fires. Add one test per guard that plants a violation in a temp tree (or a crafted source string) and expects the guard to report it through the pre-filtered path.

## Evidence
- `tests/test_ui_ownership.py:189` — `if name not in content:  # a token match needs the substring: skip the regex`, and `:209` (`name not in selector`).
- `tests/test_desktop_split_guard.py:250-255` — `needles = {SHELL_PACKAGE} | fixtures` … `if not any(needle in source for needle in needles):`.
- `tests/test_mcp_httpx_guard.py:84` — `if not any(word in source for word in (*_REMOVED_MODULES, *_REMOVED_NAMES)):`.
- `tests/test_schema_template.py:126` — `if "ensure_schema" not in source and "init_db" not in source:`.
- Flight debrief: `missions/34-maintenance/flights/01-test-suite-runtime-ii/flight-debrief.md`, Recommendation 3.

## Corrective Action
One new test per guard, each planting a violation and driving the guard's pre-filtered path:
- `tests/test_ui_ownership.py::test_prefiltered_scans_still_report_a_planted_use` (crafted JS and CSS strings through `count_js_uses` / `count_css_uses`).
- `tests/test_desktop_split_guard.py::test_the_prefilter_never_skips_a_planted_violation`. The per-file check was inlined in the guard loop, so I extracted `_prefiltered_violations(source, allowed, fixtures)` (needle pre-filter, then `find_violations`) and the guard loop now calls it. Behaviour is unchanged.
- `tests/test_mcp_httpx_guard.py::test_the_prefilter_never_skips_a_planted_violation` (four files in tmp_path, one per removed module or name, through `_removed_surface_uses`).
- `tests/test_schema_template.py::test_direct_calls_are_found_through_the_prefilter` (three tmp_path files through `_direct_calls`: a bare `ensure_schema`, a bare `init_db`, an attribute `ensure_schema`).

## Verification
- Falsification, each done by editing the guard's pre-filter so it skips the planted input, running, and restoring by editing. All four new tests failed under the edit and pass restored:
  - ownership: needle `name + "X"`: falsified yes.
  - desktop split: `SHELL_PACKAGE + "X"` needle: falsified yes.
  - mcp httpx: dropped `_REMOVED_NAMES` from the pre-filter: falsified yes.
  - schema template: dropped the `init_db` needle: falsified yes.
- Timings, the four files, `run-tests.sh -x --timeout 30`: before (new tests deselected) 84 passed in 1.84 s; after 88 passed in 1.87-1.93 s.
- `ruff check` and `ruff format --check` clean on the four files.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 8607 passed, 15 skipped, 221.80 s.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches `tests/test_encryption.py` key-path guards and logging setup), batch review of the 2026-11-02 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]` with no blocking issues; the Reviewer's own `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped; `ruff check`/`format --check` clean.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02` commit on `squawk/turnaround-2026-11-02`.
