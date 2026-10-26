# Leg: mcp-close

**Status**: ready
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Close the flight's engineering work:
- bring the mission's Known Issues, the control catalogue, `the_one/agents.md` and `CLAUDE.md` up to date with what Flight 5 built;
- complete squawk 0203 (documentation only);
- fix the stale mentions of deleted code;
- take the after capture set and compare it with the before set against the ledger (DD8);
- re-budget the lanes on a quiet host, and pass the full gate.

The FD then runs the `mcp-sensitive-headers-round-trip` behavior spec, which is the leg's last criterion. This leg changes no product behaviour.

## Context
- **Flight decisions:** DD8 (captures), DD10 (standing rules), DD12 (lanes, the re-budget rule, behavior specs). Also the flight spec's Post-Flight "Verification" list, which this leg makes true.
- **The mission's Known Issues** (`missions/31-control-library-everywhere/mission.md:91`): "Alias shims to retire as their callers migrate", with counts after Flights 3 and 4. After Flight 4 the remaining callers were `chat.js`, `markdown.js` and the MCP editor. Flight 5 retires the MCP editor's: `App.confirmDelete(`, `App.showFlash(`, `App.icon(` and `App.consentLink.`.
- **Squawk 0203** (`squawks/0203-era-docstring-and-negotiation-doc-notes.md`, open, servicing, routine): a stale `the_one/mcp/_era.py:7-8` module docstring, and three gaps in `the_one/agents.md`'s "Automatic protocol negotiation" bullet. The operator chose to fold it into this leg (2026-10-25). It is a docstring-and-docs fix; no logic changes.
- **The stale mentions** (the flight spec's Verification list, FD grep at planning; re-run the grep, because lines have moved):
  - `docs/ui-control-inventory.md` (about 45, 58, 110);
  - `the_one/agents.md` (about 1257, 1914, 2083, 2111, 2115, 2169, 2171, 2308, 2311, 2630);
  - `docs/ui-testid-registry.md` (about 72, 416);
  - the comments at `studio.css` (about 401, 433), `components.css` (about 329) and `js/ui/chip-list.js:9`.

  The terms: `adminFormHelpers`, `tools-form-helpers`, `tool-enable-switch`.
- **`CLAUDE.md`:**
  - **The control-library paragraph** ("Control library (`App.ui`, M25)") has grown flight-by-flight detail (Flights 3 and 4 totals and option lists). Flight 4 debrief Recommendation 8: move that detail to `the_one/agents.md` "Control library (`App.ui`)" and keep CLAUDE.md to the operating rules and the current totals.
  - **The Testing section** (`CLAUDE.md:417`) says `tests/test_run_tests_lanes.py` "lists all eleven lanes" while the same paragraph says thirteen lanes. Fix it to match `scripts/run-tests.sh`.
  - **The "Settings item pages" paragraph** says "`tools-form-helpers.js` keeps only the string chip list the MCP editor still uses". That is stale since leg 06.
- **The lane budgets** (`scripts/run-tests.sh`, the table in CLAUDE.md). Flight 5 added many `mcp` lane tests (164 → about 197 by leg 09, plus legs 10 and 11). The re-budget rule (squawk 0217, DD12):
  - a reading counts only from a `--parallel 3` run on a quiet host (1-minute load below about 1.0, and no other test process: check `uptime` and `ps`; squawk 0259);
  - a lane over 1.3x its budget is split or re-budgeted;
  - a lane whose time moved more than 15% is re-budgeted to measured plus 25%, rounded up to 30 s.
- **Captures** (DD8):
  - the before set is `~/.cache/the-one-ui-capture/m31-f5-before` (leg 01);
  - each leg's set is `m31-f5-l{NN}`.

  The after set is taken here, compared with the before set using PIL `ImageChops`, and each difference is mapped to a ledger row, then judged against what the row promised. Run-to-run text (the status line's date, ports) is expected.
- **The behavior specs:**
  - `tests/behavior/mcp-sensitive-headers-round-trip.md` was drafted in leg 07 and has not been run;
  - `tests/behavior/jump-to-palette.md` step 6 is to be checked against the new MCP editor title and wording (DD12);
  - `list-and-detail.md` was amended in legs 10 and 11.

## Inputs
- Legs 01-11 are completed and committed (batch B5 reviewed).

## Outputs
- **The mission's Known Issues:** a "Counts left after Flight 5" sentence in the alias bullet, by the same method (call sites outside `js/ui/` and comments; `git grep`). The expectation is that only `chat.js` and `markdown.js` remain. Also record Flight 5's ownership-allowance and sink totals (whole app) in the mission's progress notes where Flights 3 and 4 recorded theirs.
- **The catalogue** (`docs/ui-control-inventory.md`):
  - every row this flight touched states its current options: `secretInput` stored mode, `keyValueTable` (secret and toggle columns, `width`, `setRow`, `keyColumn`), `editorShell` (the error row, `setTestState`), `chipList` (the middle ellipsis), `toolTile` (`expandLabel`, leg 11), and `dangerZone`;
  - "Legacy toggle 1" is gone;
  - the stale mentions are fixed;
  - `tests/test_ui_control_inventory.py` passes.
- **`the_one/agents.md`:**
  - the MCP editor contract: the modules and their `create()` APIs, the controller's save model (`baselineFrom`, `current`, `syncTestHold`), the side-effect inventory's final state and the stable DOM contract;
  - the `last_check` note (already added in 08a, kept current) and the invalidation map's new paths;
  - the masked column;
  - the control-library detail moved from CLAUDE.md;
  - the stale mentions fixed;
  - squawk 0203's three bullet fixes.
- **`CLAUDE.md`:**
  - trim the control-library paragraph to the operating rules plus the current whole-app totals (ownership rows and uses, HTML sinks), with a pointer to `agents.md`;
  - fix the lane-count sentence;
  - fix the stale `tools-form-helpers.js` sentence;
  - correct the netns unit skip count. The B5 review measured 15 under `THE_ONE_TEST_NETNS=1`, because `tests/test_packaging_apprun.py:186` also skips as root. Re-read `-rs` on the leg's own run and state the figure with its reasons;
  - update the lane budget table if the re-budget changes it.

  Keep every rule; move detail, never delete a rule.
- **Squawk 0203:**
  - fix the `_era.py:7-8` docstring;
  - write the three `agents.md` notes;
  - write its corrective action and verification;
  - set the status to `completed`.

  Its sign-off and commit are filled in at the batch commit.
- **The re-budget:**
  - one `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short` run on a quiet host (record `uptime` and `ps` before it). Apply the 1.3x and 15% rules to the table in `scripts/run-tests.sh` and CLAUDE.md, and pin it through `tests/test_run_tests_lanes.py`;
  - if the host is not quiet, wait. If it never gets quiet, record the loaded reading as NOT counting, leave the budgets alone, and tell the FD;
  - squawk 0259 (chats at budget) gets a re-measured note.
- **The full gate:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` passes (unit, then browser, never concurrent). Any failure is triaged per the gate-flake rule.
- **The after set:** `scripts/ui_capture.py` with every MCP surface plus the provider, connector, knowledge and agent surfaces the flight touched, into `~/.cache/the-one-ui-capture/m31-f5-after`, compared with `m31-f5-before`.
  - Write a table in the flight log: surface, then differs or identical, then the ledger rows, then "as promised: yes or no", with the reason for any no.
  - A difference that maps to no row is a finding for the FD, not something to explain away (Flight 4 debrief, Key Learning 3).
- **`jump-to-palette.md` step 6:** check it against the new wording, and amend the spec text only if it is stale.
- **The Verification list** in `flight.md` is checked item by item, with the grep output pasted into the flight log.

## Acceptance Criteria
- [ ] **The Known Issues alias counts after Flight 5** are recorded, with no MCP file calling a retired alias.
- [ ] **The catalogue, `agents.md` and `CLAUDE.md` are current.** The stale-mention grep (`git grep -n "adminFormHelpers\|tools-form-helpers\|tool-enable-switch"` over `the_one/`, `docs/`, `CLAUDE.md`, `tests/behavior/*.md` excluding run logs, and `scripts/`) finds only historical mission or squawk files and deliberate frozen fixtures. Each hit kept is listed with its reason.
- [ ] **Squawk 0203** is `completed`, with its corrective action and verification.
- [ ] **The flight spec's Verification "Guards" items all hold** (pasted output).
- [ ] **The quiet-host `--parallel 3` reading is recorded,** with the load, and the budgets are re-applied by the rules. `tests/test_run_tests_lanes.py` passes.
- [ ] **`make gate` passes** (`PARALLEL_RESULT rc=0`), with no lane over budget on the quiet run.
- [ ] **The after set is compared with the before set,** and every difference is mapped to a ledger row and judged. Unmapped differences are listed for the FD.
- [ ] **`/mission-control:behavior-test mcp-sensitive-headers-round-trip` passes.** The FD runs it after the Developer lands; it is not the Developer's step.

## Verification Steps
- The greps above, pasted into the flight log.
- `make test-unit`, then the quiet `--parallel 3` run, then `make gate`, all with `THE_ONE_TEST_NETNS=1`. Never run two of them at once, and never alongside another session's lanes.
- The capture compare table.

## Implementation Guidance
1. **The docs first:** the catalogue, `agents.md`, CLAUDE.md, the Known Issues, squawk 0203 and the stale mentions, then `make test-unit` (the doc-pinning tests).
2. **The after set and its compare table.**
3. **The quiet `--parallel 3` run and the re-budget.**
4. **`make gate`.**
5. **Land the leg.** The FD runs the behavior spec.

## Edge Cases
- **A doc test pins CLAUDE.md or `agents.md` text** (for example the lane count or the budget table). Run `make test-unit` after every doc edit.
- **A capture surface from the before set no longer exists or was renamed** (for example `mcp-edit-reset-armed` now arms Reset or Forget). Note the pairing in the table.
- **A lane goes over 1.3x on the quiet run.** Split it, the M31 F3 and F4 precedent: an explicit file list in `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` and CLAUDE.md. Tell the FD before splitting.

## Files Affected
- `missions/31-control-library-everywhere/mission.md` (Known Issues); `squawks/0203-…`, `squawks/0259-…` (a note).
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `the_one/agents.md`, `CLAUDE.md`.
- `the_one/mcp/_era.py` (docstring only).
- Comments in `css/studio.css`, `css/components.css` and `js/ui/chip-list.js`.
- `scripts/run-tests.sh` and `tests/test_run_tests_lanes.py` (budgets, if changed).
- `tests/behavior/jump-to-palette.md` (only if stale); the flight log.

## Citation Audit
- `mission.md:91` (the alias bullet), `squawks/0203` (read in full), `CLAUDE.md:417` (the lane count): FD read, 2026-10-25.
- The stale-mention lines come from the planning grep; legs 06-11 moved them. Re-grep at the start.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
