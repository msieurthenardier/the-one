# Squawk 0117: Split the `shared` browser lane; it is the long pole at 12m38s

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-05
**Completed**: —

## Report

`scripts/run-tests.sh --lane shared` is the complement lane: every browser test file that
no destination lane claims. Each flight's dual-engine `test_ui_*` contracts land there,
along with the router, guard and store tests, so it has become the long pole of every
browser verification pass:

| Debrief | Shared lane |
|---|---|
| M25 F1 | 694 passed, 256s |
| M25 F2 | 723 passed, 627s |
| M25 F3 | 867 passed, 3 skipped, 758s (12m38s), 38% of browser wall time |

The Flight 2 debrief recommended the split, and Flight 3 grew the lane another 21% without
it. Flight 4 adds dual-engine contracts for the agent picker and the jump-to palette, which
will push it past 13 minutes.

What needs doing:
- Add a sixth lane, for example `contracts`, holding the `test_ui_*` contract files. There
  are 12 files today: `test_ui_*_contract.py`, `test_ui_dialog_*`,
  `test_ui_listener_cleanup.py`, `test_ui_reference_page.py` and
  `test_ui_apparatus_contract.py`.
- Keep `shared` as the complement of all six lanes, so the union is still exactly the whole
  browser suite.
- Update the lane list in `CLAUDE.md` ("Per-area browser test lanes"), and the
  `--lane` usage and error text.

No product code changes.

## Evidence

- `scripts/run-tests.sh`:
  - the `case "$lane"` block, where `shared` is computed as the complement of
    `chats_pat`, `studio_pat`, `settings_pat` and `test_visual_snapshots.py`;
  - the usage and error line listing `chats|agents|library|settings|shared`.
- `tests/browser/test_ui_*.py`: 12 files, which run in Chromium and WebKit through
  `engine_page`.
- M25 F3 debrief, "Test Metrics"
  (`missions/25-workbench-navigation/flights/03-list-and-detail/flight-debrief.md`).
- M25 F2 debrief, recommendation 2.

## Corrective Action

*(written at completion)*

## Verification

- Each lane runs green alone under `THE_ONE_TEST_NETNS=1`.
- The six lanes' file lists are disjoint, and their union equals
  `pytest -m browser tests/browser/ --collect-only`, checked by file list and by test
  count.
- `shared` drops to roughly the router, guard and store files.

## Sign-Off

*(written at completion)*
