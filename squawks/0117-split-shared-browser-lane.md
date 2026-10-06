# Squawk 0117: Split the `shared` browser lane; it is the long pole at 12m38s

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-05
**Completed**: 2026-10-05 (M25 Flight 4 leg 1, `controls-and-data`; flight DD11)

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

Done in M25 Flight 4 leg 1 (`controls-and-data`, flight DD11), before the flight added
any new dual-engine contract. No product code changed.

- **A sixth lane, `contracts`.** `scripts/run-tests.sh` gains
  `contracts_pat=('test_ui_*')`: every `App.ui` control-library contract file
  (engine-parametrized, Chromium and WebKit) plus the Design language reference-page
  guard. No other lane's glob matches `test_ui_*`. It is meant to run with
  `THE_ONE_REQUIRE_WEBKIT=1`, so a WebKit launch failure fails rather than skips.
- **`shared` stays the complement**, now of all five named lanes (`chats`, `agents`,
  `library`, `settings`, `contracts`) and the pixel-only `test_visual_snapshots.py`, so
  the six lanes' union is still exactly the browser suite and a new file still lands in
  `shared` until it is given a lane.
- **`--list`** (parsed explicitly) prints a lane's files and exits 0 without running
  pytest; `--list` without `--lane` exits 2. An unknown lane still exits 2, and the usage
  and error text now read `chats|agents|library|settings|contracts|shared`.
- **A unit-tier pin**, `tests/test_run_tests_lanes.py` (5 tests), so the partition cannot
  drift silently: the lanes are pairwise disjoint; their union is every
  `tests/browser/test_*.py` except `test_visual_snapshots.py`; `contracts` is exactly the
  `test_ui_*` files; and the two exit-2 paths.
- **Docs.** `CLAUDE.md` "Per-area browser test lanes" (the lane list, the `contracts`
  command with `THE_ONE_REQUIRE_WEBKIT=1`, `--list`, the partition test) and the lane
  summary in `the_one/agents.md`. Each `test_ui_*` docstring now says "Falls in the
  `contracts` browser lane".

Why a split by file family rather than xdist or a slimmer `shared`: the contracts are the
one family that grows with every control (each runs in two engines), and they need their
own WebKit-required gate anyway; a basename glob keeps the lanes hand-rolled, with no new
dependency, like the other five.

## Verification

- **The partition, by file list:** `tests/test_run_tests_lanes.py` (unit tier; in every
  `make test-unit`). Falsified in leg 1: adding `test_flow_chat.py` to `contracts_pat`
  failed `test_lanes_are_pairwise_disjoint` and
  `test_contracts_lane_is_exactly_the_ui_contract_files`; a scratch `test_zz_probe.py`
  landed in `shared`.
- **The partition, by test count (leg 1):** the six lanes collected 42 + 132 + 146 + 178 +
  559 + 438 = 1495 tests, exactly the `-m browser tests/browser/` selection (1495 of
  1507, 12 deselected).
- **Each lane green alone** under `THE_ONE_TEST_NETNS=1`, at leg 1 and at every leg since
  (numbers in the flight log). At leg 1: `contracts` 556 passed and 3 skipped in 2m30s
  (the 3 are in-test "WebKit has no forced-colors emulation" skips, so WebKit launched and
  ran); `shared` 438 passed in 11m10s, where it had been 867 tests in 12m38s.
- **The point of the split held through the flight.** Every Flight 4 contract landed in
  `contracts`, not `shared`: leg 1's own `searchList`, modal chooser and list-pane tests
  (already in the 556), then 88 more in legs 6 and 7 (the drawer, `setQuery`, the rail
  footer, the modal's `ariaLabel` and `anyOpen()`). At leg 8 the lane ran 644 passed and 3 skipped in 2m46s (the same
  three in-test WebKit skips). `shared`
  still holds the router, guard, store, seeder, shell and flow files (28 files):
  461 passed in 11m44s at leg 8, the palette's 20 flow tests included. Without the split it would have been about 1,100 tests and well past 13
  minutes.
- **Leg 8 re-check:** `bash scripts/run-tests.sh --lane <lane> --list` gives 20 (`chats`),
  19 (`agents`), 6 (`library`), 13 (`settings`), 15 (`contracts`) and 28 (`shared`) files,
  and `--list` alone exits 2 with the six-lane usage.

## Sign-Off

*(pending: the M25 Flight 4 flight-end review signs it off)*
