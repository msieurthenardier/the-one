# Leg: verify-integration

**Status**: completed
**Flight**: [Daily Automatic Purge](../flight.md)

## Objective

Verify the daily automatic purge against a live, restarted instance: run the `agent-history-auto-purge` behavior gate (Witnessed) and the full unit + browser suites, confirming the sweep deletes aged conversations (interactive + connector) while leaving recent, active-connector, and other-agent conversations intact, and that `last_purge_at` advances.

## Context

- This is the flight's acceptance-verification leg. It is **not** an autonomous-implementation leg — the Flight Director runs it directly (`/behavior-test agent-history-auto-purge`); the behavior-test skill orchestrates its own Executor + Validator crew under the Witnessed pattern.
- Legs 1–3 delivered the code (reviewed, all 335 unit/integration tests green). This leg confirms the live composition that unit tests can't: the real sweep firing against a running DB + lifespan, driven through real HTTP.
- **Setup the live gate requires** (apparatus, both axes, already audited in the flight's DD5 and prerequisites):
  - The instance restarted so the new lifespan purge loop **and** the `POST /api/_test/purge-sweep` route are loaded (the route was added in Leg 3; the running container predates it).
  - `THE_ONE_DEV_MODE=true` (already set in `docker-compose.yml`) **and** `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1` (added to `docker-compose.yml` for this gate) — the dual gate the endpoint requires.
  - At least two agents (target + bystander) — five exist; the test seeds its own sessions via `POST /api/chat/sessions` with backdated `updated_at`.
- **Startup-sweep safety (checked at planning):** on restart the catch-up sweep runs immediately (no `last_purge_at` yet → due). Verified beforehand that **zero real sessions are at risk** — all 47 dev sessions are ≤12 days old and all 5 agents use the default 30-day window, so the catch-up purges nothing real. The behavior test then seeds its own aged rows and asserts on those.

## Inputs
- Legs 1–3 landed (uncommitted working tree), code review confirmed.
- `tests/behavior/agent-history-auto-purge.md` — the Witnessed spec (authored during flight planning).
- Running container `the-one` (bind-mounted code), restartable via the Makefile / `docker compose`.

## Outputs
- A behavior-test run log at `tests/behavior/agent-history-auto-purge/runs/{ts}.md` (committed) with evidence (gitignored).
- Confirmation of the full unit + browser suite result for the flight (for the debrief metrics).
- `docker-compose.yml`: `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1` added (makes the dev-only test seam reachable; dual-gated by dev_mode).

## Acceptance Criteria
- [ ] The instance is restarted; `GET /api/config` shows `dev_mode:true`; `POST /api/_test/purge-sweep` is reachable (not 404) and returns `{deleted, last_purge_at}` (not 403) with the dual gate on.
- [ ] `/behavior-test agent-history-auto-purge` runs and **passes** (aged interactive + aged superseded-connector rows gone; recent + active-connector + bystander rows kept; `last_purge_at` advances; second sweep deletes nothing).
- [ ] Full unit suite green (`docker exec the-one pytest -m "not browser and not live and not pixel"`); record pass/skip/deselect counts + wall time for the debrief.
- [ ] Browser suite green (`docker exec the-one pytest tests/browser -m browser`); record counts for the debrief.
- [ ] `ruff check` + `ruff format --check` clean across the flight's changed files.

## Verification Steps
- Restart: `make rebuild` (or `docker compose up -d --force-recreate the-one`); wait for healthy.
- Endpoint reachability: `curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8484/api/_test/purge-sweep` → `200` (gate on).
- Lifespan: check container logs show the purge loop started and the startup catch-up ran (a "daily purge" log line or a clean no-op).
- Gate: `/behavior-test agent-history-auto-purge`.
- Suites: the two pytest commands above.

## Implementation Guidance
1. Add `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1` to the `the-one` service `environment:` in `docker-compose.yml` (beside `THE_ONE_DEV_MODE=true`).
2. Restart the container so the new app.py lifespan wiring + the new api.py route load. Confirm health and endpoint reachability.
3. Run the behavior gate via `/behavior-test agent-history-auto-purge` (Flight Director invokes the skill directly).
4. Run the full unit + browser suites; capture metrics.
5. If the gate fails: investigate, fix in code (a Developer agent if needed), re-run — do not paper over.

## Edge Cases
- **Restart purges real aged data**: pre-checked — none at risk (see Context). If re-run later when real aged data exists, that is the intended retention behavior, not a defect.
- **Endpoint 404 after restart**: means the new route didn't load — confirm the restart actually recreated the process (bind mount alone doesn't reload a running uvicorn).
- **Endpoint 403**: the env flag didn't reach the container — verify `docker-compose.yml` change + recreate.

## Files Affected
- `docker-compose.yml` — `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1` (dev test-seam reachability).
- `tests/behavior/agent-history-auto-purge/runs/{ts}.md` — run log (created by the gate).

---

## Post-Completion Checklist
- [ ] Behavior gate passed; run log committed
- [ ] Full suites green; metrics captured
- [ ] Update flight-log.md with the verify-integration entry
- [ ] Set this leg's status to `completed`
- [ ] This is the final leg → Flight Director checks off all legs in flight.md, sets flight `landed`, checks off the flight in mission.md, commits
