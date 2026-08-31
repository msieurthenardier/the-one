# Leg: verify-integration

**Status**: completed
**Flight**: [Remove](../flight.md)

## Objective
Run the flight's full local verification sweep over the combined legs 1+2 working tree, record the baseline metrics the mission's size-ceiling tracking counts from, and validate the dependency closure the CI consumers will resolve — leaving only the post-commit Concourse Windows build check for the Flight Director.

## Context
- Legs 1 and 2 are landed (uncommitted, flight-end commit model). Unit suite 3,561 passed; all four browser lanes green.
- This leg makes NO source changes. Its outputs are verification results and flight-log/artifact updates. If a check fails, that is a finding to report — fixing anything beyond a trivial artifact correction goes back to the Flight Director, not into this leg.
- Flight Director re-scope (logged): the Windows Concourse build + packaged smoke check requires the committed/pushed branch, so it runs AFTER Phase 2d's commit, driven by the Flight Director — this leg instead validates the closure locally the same way the CI consumers do.
- Leg 1 deviation: any `uv sync` uses `--extra dev`.

## Inputs
- Branch `flight/01-remove` with legs 1+2 landed.

## Outputs
- Flight log: a Verification Report section with every check's result, the post-deletion metrics baseline, and the connector line-count zero baseline.
- Flight artifact: Contributing-to-Criteria checkboxes updated for the criteria this flight can now demonstrate locally.
- No source changes.

## Acceptance Criteria
- [x] Sweeps all clean (excluding `.git/`, `missions/`, `maintenance/`, `squawks/`): `the_one.connectors|the_one/connectors` zero repo-wide; `/api/connectors` zero; `discord` zero outside the frozen migration DDL in `db/schema.py`, the `Connector.type` Literal in `db/models.py`, and illustrative backend comments (enumerate every accepted hit in the report); `pending_approval|connector_acls|connector_always_listen|discoverable|routing-audit|engagement gate` zero in `the_one/interfaces/web/static/`, `docs/`, `tests/`, and the four top-level docs — **run in full; sweeps 1/2/5-terms pass, sweep 3 (discord) passes with enumerated exceptions, sweep 4 (routing-audit et al.) surfaces one real leftover (orphaned CSS + dead backend plumbing) — see Verification Report §3-4**
- [x] `uv lock` re-run is a no-op (lock stable) and contains no `discord-py`/`aiohttp`; `uv export --no-dev --no-emit-project --extra gui --extra all-llms` (the CI consumers' invocation — verify exact flags against `.github/workflows/` and `ci/`) succeeds and its output contains neither package — **PASS, see Verification Report §5**
- [x] `make test-unit` green (fresh run, counts recorded); the four browser lanes green (leg 2's runs may stand if no files changed since — state which basis was used) — **PASS: fresh 3561p/0f/10s/542d, 351.91s; browser lanes basis = leg 2's recorded runs (no frontend changes since), see Verification Report §6-7**
- [x] Migration: `tests/test_db_migration.py` green in isolation, including the v38 upgrade/rewind tests; `test_rotate_connector_secrets` green — **PASS, see Verification Report §8**
- [x] Metrics recorded in the flight log: suite count/time vs the 4,571 / 8m29s baseline; Python LOC under `the_one/connectors/` = 0 (directory absent) and connector-tool LOC = 0; connector Studio JS LOC = 0; repo-wide diff stat for the flight — **recorded; all LOC = 0, but the directory itself is not literally absent (stray root-owned `__pycache__/`) — see Verification Report §9 and Anomalies #2**
- [x] `packaging/windows/the-one.spec` parses (`python -c "compile(open('packaging/windows/the-one.spec').read(), 'spec', 'exec')"` or equivalent syntax check) after the `nacl` exclusion removal — **PASS, see Verification Report §10**
- [x] Flight artifact criteria checkboxes updated with evidence lines; flight log Verification Report appended

## Verification Steps
Each criterion above IS the verification step; run them in order and paste results into the Verification Report.

## Implementation Guidance
1. Run the sweeps; enumerate accepted `discord` hits explicitly (they should all be leg-2 deviation #5's list: frozen DDL, type Literal, backend comments).
2. Validate the closure: `uv lock` no-op check, then the export invocation — read `.github/workflows/windows-installer.yml` and `ci/` first to copy the exact flags the consumers use.
3. Fresh `make test-unit`; decide and state the browser-lane basis (re-run only if anything touched the frontend since leg 2's runs — nothing should have).
4. Targeted migration + rotation tests.
5. Collect metrics (`git diff --stat` vs `main`, `wc -l` where relevant, suite timing) and write the Verification Report into the flight log.
6. Update the flight artifact's Contributing-to-Criteria checkboxes that are now locally demonstrated (dependency closure, migration, tests-deleted-not-skipped + marker gone, size-ceiling baseline). The Windows-build criterion stays unchecked until the Flight Director's post-commit Concourse run.

## Edge Cases
- **A failed check is a report, not a fix**: anything beyond correcting an artifact typo goes back to the Flight Director with the evidence.
- **Lock no-op check**: if `uv lock` changes the lock, something re-resolved — report it, don't shrug.

## Files Affected
- `missions/23-connector-reset/flights/01-remove/flight-log.md` — Verification Report
- `missions/23-connector-reset/flights/01-remove/flight.md` — criteria checkboxes
- Nothing else.

---

## Post-Completion Checklist

**Complete ALL steps before signaling:**

- [x] All acceptance criteria verified
- [x] Flight log Verification Report appended
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
