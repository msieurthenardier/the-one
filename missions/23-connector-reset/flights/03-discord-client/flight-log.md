# Flight Log: Discord Client

**Flight**: [Discord Client](flight.md)

## Summary
*(execution not started)*

## Flight Design Notes (planning, 2026-09-01)

- Two mission-level resolutions recorded in mission.md during this flight's planning: RQ8 (owner-amended agent-loop constraint → minimal send-tool visibility carve-out) and RQ9 (`enabled` as config key, no migration).
- Architect design review, 2 cycles (cap). Round 1 (approve with changes): close-code "stop" had no manager give-up primitive → typed `PermanentConnectorFailure` in base.py with a narrow `_run` catch; graceful stop/start can never exercise RESUME → fixture-pins-resume / live-accepts-any-reconnect split with a dev-gated sever hook; DD-5 naive append would duplicate schemas past `_on_search_match` dedup → seed-the-containers approach; per-account plugin state made explicit; `supports_tools()=True` prerequisite. Round 2 (approve with changes, amendment-scoped): failure marker moved plugin-side (manager has no path to doctor) with the connect()-clears-marker lifecycle rule; `_connect_once`'s catch-all needs the explicit re-raise; `reset()` re-seeding requires captured instance state + a fifth pin test; DD-7's sever-hook shape settled as an optional `getattr` client hook via `manager.client_for` behind a dual-gated route (`THE_ONE_DISCORD_TEST_ENDPOINT`). All fixes were reviewer-specified completions (no design disputes) — applied and proceeding to operator sign-off per the Flight 2 precedent at the cycle cap.

---

## Leg Progress

*(none yet)*

---

## Decisions
*(runtime decisions recorded here during execution)*

---

## Deviations
*(none yet)*

---

## Anomalies
*(none yet)*
