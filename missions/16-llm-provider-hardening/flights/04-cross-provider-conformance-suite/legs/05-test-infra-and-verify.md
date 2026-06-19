# Leg: test-infra-and-verify

**Status**: completed
**Flight**: [Cross-Provider Tool-Use Conformance Suite](../flight.md)

## Objective

Fix the `make test-unit` marker-selection bug so its `-m` expression is additive
(deselects all five default-deselected markers, not three), then run
verify-integration: full suite green, `requires_bwrap`/`discord_hat` confirmed
deselected, and re-baselined pass/skip/deselect counts recorded and reconciled
against the Flight-3 figure.

## Context

- **DD7**: `make test-unit` (`Makefile:113`) passes
  `-m 'not browser and not live and not pixel'` (3 markers), which **replaces**
  (last-`-m`-wins) the pyproject `addopts` deselection (`pyproject.toml:86`, 5
  markers including `requires_bwrap` and `discord_hat`). So `make test-unit`
  silently runs the `requires_bwrap` (~44) and `discord_hat` (5) tests — they pass
  here only because this host has `/bin/bwrap`; on a bwrap-less host / CI they'd
  error. (Flight-3 debrief Rec 2.) This flight runs the full suite repeatedly, so it
  is the natural home for the fix.
- This is the **final leg**. Beyond DD7 it runs verify-integration for the whole
  flight: confirm the suite is green with the new conformance/guard/recovery tests
  (legs 02-04) added and the marker fix applied, and record an auditable count delta.
- **Allowed non-test edit**: the `Makefile` recipe (DD7) — the second and last
  non-`tests/` edit of the flight (after leg 03's `openrouter_provider.py` docstring).
  No `the_one/**` source changes.

### The exact bug (source-verified 2026-06-19)

- `pyproject.toml:86`:
  `addopts = "-m 'not live and not browser and not pixel and not requires_bwrap and not discord_hat' --import-mode=importlib"`
- `Makefile:113`:
  `PYTHON=$(PY) bash scripts/run-tests.sh tests/ -m 'not browser and not live and not pixel' -v --tb=short`
- pytest applies the **last** `-m`; the recipe's 3-marker `-m` wins over addopts'
  5-marker `-m`, so `requires_bwrap` + `discord_hat` are NOT deselected under
  `make test-unit`.
- `pyproject.toml:85` records per-marker deselect math (last verified L4 F2):
  `live=15, browser=513, pixel=12, requires_bwrap=12, discord_hat=5`. **That comment
  is itself stale** — design-review measurement on a bwrap host found `requires_bwrap`
  actually collects **~44** (not 12) and `discord_hat` = 5. So the fix moves
  **~49 tests** (44 + 5) from run→deselected under `make test-unit`, not ~17. Do NOT
  re-trust the `:85` comment; reproduce the count from the actual run (and record a
  flight-log finding that the comment should be corrected in a future leg — it is
  out of this leg's allowed-edit scope).

## Inputs
What exists before this leg runs:
- `Makefile:111-113` — the `test-unit` recipe.
- `pyproject.toml:86` — the addopts 5-marker deselection (source of truth for the
  default-deselected marker set); `:88-93` — the marker registry.
- All flight-04 test additions landed (legs 01-04, uncommitted): the shared fixtures,
  the harness, the conformance module (32 hermetic tests + guards + recovery rows),
  and the live test in the history file.
- Flight-3 baseline (from `../03-open-model-toolcall-recovery/flight-debrief.md`):
  **3302 passed / 18 skipped / 541 deselected** under the (then-buggy) `make test-unit`.

## Outputs
What exists after this leg completes:
- `Makefile:113` `test-unit` recipe with an **additive** `-m` expression deselecting
  all five default markers, with a one-line comment tying it to `pyproject.toml`
  addopts (the marker list lives in two places; they must be maintained together).
- A recorded, reconciled verify-integration result in the flight log: full suite
  green; `requires_bwrap`/`discord_hat` confirmed deselected; re-baselined counts
  with the delta explained against the Flight-3 figure.
- Any doc update the flight's changes warrant (e.g. a one-line provider-quirk note if
  the project keeps such a doc; otherwise N/A — record the determination).

## Acceptance Criteria
- [x] `make test-unit`'s `-m` expression is additive — it deselects
      `browser`, `live`, `pixel`, `requires_bwrap`, **and** `discord_hat` (matching
      `pyproject.toml:86`'s addopts set), with a one-line comment linking the two
      marker lists.
- [x] Running `make test-unit` shows `requires_bwrap` and `discord_hat` tests are now
      **deselected** (the deselected count rises by ~49 from the marker fix, plus the
      new live test, vs the Flight-3 baseline).
- [x] The full `make test-unit` run is **green** (0 failed) with the flight-04
      additions present.
- [x] Re-baselined counts (passed / skipped / deselected) are recorded in the flight
      log, with the net change **explicitly reconciled** across **all three lines**
      against Flight-3's `3302 passed / 18 skipped / 541 deselected`: the marker fix
      moves ~44 `requires_bwrap` + 5 `discord_hat` from *passed* → *deselected*
      (`passed −44`, `deselected +49`), partially offset by ~N new hermetic flight-04
      tests added to *passed*; the new live test adds to the *deselected*/`live`
      count; and *skipped* may also move (environment-dependent skips — the
      design-review run observed 18 → 10). Report **actual** numbers; the
      design-review host measured `3347 passed / 10 skipped / 594 deselected` (~308s)
      as a reference to reproduce, not a target to assert.
- [x] No `the_one/**` source changed by this leg (`git diff --stat -- 'the_one/**'`
      shows only the pre-existing leg-03 `openrouter_provider.py` docstring; the only
      new edit this leg makes is `Makefile`).
- [x] Doc-update determination recorded (updated, or "N/A — no provider-quirk doc
      kept").

## Verification Steps
- Apply the Makefile fix, then run the full unit suite:
  `make test-unit` → 0 failed; capture the final pytest summary line
  (passed / skipped / deselected / duration).
- Confirm the two markers are now deselected — compare the deselected count to the
  Flight-3 baseline (should be ~+17 from the marker fix alone, plus the new live
  test), and/or spot-check:
  `.venv/bin/python -m pytest tests/ -m 'requires_bwrap' --collect-only -q | tail -3`
  shows the bwrap tests exist (so they were previously run by the buggy recipe).
- `git diff Makefile` → only the `test-unit` recipe `-m` expression (+ a comment)
  changed; no other target touched.
- `git diff --stat -- 'the_one/**'` → only `openrouter_provider.py` (leg 03).

## Implementation Guidance

1. **Fix the `test-unit` recipe** (`Makefile:113`). Lowest-risk form (recommended):
   keep the explicit `-m` and extend it to the full five markers so the recipe stays
   distinct from `make test` and is robust regardless of `run-tests.sh`'s arg
   handling:
   ```make
   .PHONY: test-unit
   test-unit: ## Run unit tests only host-native (excludes browser, live, pixel, requires_bwrap, discord_hat)
   	# Keep this -m in sync with pyproject.toml addopts' default-deselect set.
   	PYTHON=$(PY) bash scripts/run-tests.sh tests/ -m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat' -v --tb=short
   ```
   **The DD7 "drop the `-m` to inherit addopts" alternative is REJECTED** (design-
   review verified): `scripts/run-tests.sh` passes args **verbatim** to pytest (no
   `-m` injection/reordering — `setsid "${PYTHON}" -m pytest "$@"`), so a `test-unit`
   with no `-m` runs purely under addopts and collects the **identical** set to
   `make test` (no `-m`) — both 3357-collected on the review host. That collapses
   `test-unit` into `make test`, removing its reason to exist. Use the explicit
   5-marker form; do not drop the `-m`. (Operator expressed no preference on form;
   this rejection is a correctness finding, not a preference.)

2. **Run verify-integration** — `make test-unit`. Capture the full summary line. The
   suite must be 0-failed. Record passed / skipped / deselected / wall-clock.

3. **Reconcile the delta across all three lines** against the Flight-3 baseline
   (`3302 passed / 18 skipped / 541 deselected`):
   - The DD7 fix moves **~49 tests** (`requires_bwrap`≈44 + `discord_hat`=5) from
     *passed* → *deselected* (`passed −44`, `deselected +49`; the 5 discord_hat were
     already skipping-or-deselected in some runs — verify against the actual numbers).
   - Flight-04 added new **hermetic** tests (passed): leg-02 round-trip matrix
     (~24), leg-03 guards (~6), leg-04 recovery rows (~2) ≈ **~32** (report the
     actual count from the run, do not trust the estimate).
   - Flight-04 added one new **live** test → goes to the *deselected* (live) count,
     not passed.
   - *skipped* may also move (environment-dependent skips — review run saw 18 → 10);
     reconcile it too, don't assume it's stable.
   - The net `passed` can be a **large swing in either direction** (−44 from the
     marker fix vs +~32 new tests); the review host measured `3347 / 10 / 594`. Report
     the **actual** numbers and show the arithmetic against the baseline; exact
     reconciliation is approximate (intervening non-flight tests may have landed since
     F3), so explain the dominant terms (marker fix, new tests) and flag any residual
     you can't account for — **do not** round a discrepancy away as noise. A genuinely
     new *failure* (not a count shift) is a stop-and-investigate finding.
   - **No silent caps**: if anything was deselected/skipped that wasn't before beyond
     this accounting, name it in the log.

4. **Docs + observed findings** — (a) check whether the project keeps a provider-quirk
   / test-layout doc the flight's additions warrant updating (e.g. a note that the
   cross-provider conformance suite + harness exist, or the forward-with-WARN
   asymmetry). If such a doc exists (e.g. `the_one/agents.md` or a testing README),
   add a one-line pointer; if not, record "N/A — no provider-quirk doc kept" in the
   flight log. Do NOT invent a new doc. (b) Record two **flag-don't-fix findings** in
   the flight log (both out of this leg's allowed-edit scope, for a future
   leg/flight): the `pyproject.toml:85` per-marker comment is stale
   (`requires_bwrap=12` actual ~44); and `make test`'s docstring (`Makefile:109`,
   "unit + browser") is inconsistent with addopts, which already deselects `browser`.

5. **Final-leg artifact bookkeeping** — set this leg's status to `landed` and append
   the flight-log verify-integration entry. **Do NOT** set flight.md → `landed` or
   check off the flight in mission.md, and **do NOT commit** — under the flight's
   deferred-commit model those flight-level transitions happen at the single
   end-of-flight commit (handled by the Flight Director after the flight-wide review),
   not by this leg's implementer.

## Edge Cases
- **`run-tests.sh` arg passthrough** — confirm the script forwards `-m` to pytest as
  the last `-m` (it does today; the bug exists precisely because the recipe's `-m`
  wins). If dropping the recipe `-m`, verify the script doesn't inject its own.
- **Two marker lists now exist** (`Makefile` + `pyproject.toml`) — the comment is the
  mitigation; a future marker addition must touch both. (Promoting to a single source
  is out of scope — DD7 is the minimal correctness fix.)
- **Count drift is expected and must be explained, not hidden** — the marker fix
  moves ~44 `requires_bwrap` from *passed* → *deselected* even as ~32 new tests are
  added; the net `passed` can move either way and a reader expecting "more tests =
  higher passed" needs the reconciliation to understand it.
- **bwrap-present host** — the `requires_bwrap` tests pass here, so the bug is
  currently invisible in green/red terms; the fix's value is correctness on a
  bwrap-less host / CI. The verification is the deselected-count rise, not a
  red→green flip.

## Files Affected
- `Makefile` — `test-unit` recipe `-m` expression (+ a sync comment). Only edit.
- Flight log — verify-integration entry (counts + reconciliation + doc determination).
- No `tests/` or `the_one/**` source changes.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` green; counts recorded + reconciled)
- [x] Update flight-log.md with the verify-integration entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Deferred to the end-of-flight commit, NOT this leg: check off this leg in
      flight.md; set flight.md status to `landed`; check off the flight in mission.md;
      commit all changes)

---

## Citation Audit

Citations verified against current code at leg design time (2026-06-19):
- `Makefile:111-113` — `test-unit` recipe, `-m 'not browser and not live and not
  pixel'` (the 3-marker bug) — **OK**
- `pyproject.toml:86` — addopts `-m 'not live and not browser and not pixel and not
  requires_bwrap and not discord_hat' --import-mode=importlib` (the 5-marker set) — **OK**
- `pyproject.toml:85` — per-marker deselect math comment
  (`requires_bwrap=12, discord_hat=5`) — **PRESENT BUT STALE**: design-review
  measurement found `requires_bwrap` ≈ 44 (not 12). Do not trust the comment's
  numbers; reproduce from the run. (Correcting the comment is out of this leg's scope
  — flagged as a flight-log finding.)
- `scripts/run-tests.sh` — passes args verbatim to pytest (`setsid "${PYTHON}" -m
  pytest "$@"`; no `-m` injection) — **OK** (this is why the recipe's `-m` wins, and
  why the inherit-`-m` alternative collapses `test-unit` into `make test`).
- `pyproject.toml:88-93` — marker registry (`requires_bwrap`, `discord_hat` declared) — **OK**
- Flight-3 baseline `3302 passed / 18 skipped / 541 deselected` — from the Flight-3
  debrief (reconciliation reference).
