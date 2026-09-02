# Leg: live-gate-and-docs

**Status**: completed
**Flight**: [Discord Client](../flight.md)

## Objective

Land the controlled-disconnect test seam, finalize the `discord-live-round-trip` behavior spec against the real client, repair the one browser test this flight's design falsified, and rewrite the connector docs — leaving the flight ready for the live behavior gate (run by the Flight Director once the operator supplies bot credentials).

## Context

- Flight DD-7 (apparatus split + sever-hook shape, settled in flight design review round 2): an OPTIONAL `ConnectorClient` hook discovered via `getattr(client, "sever_for_test", None)` — the same optional-hook pattern as `history` — reached through `manager.client_for(connector_id)` (`manager.py:92-94`) from a dual-gated route. Gate: `settings.dev_mode` AND `THE_ONE_DISCORD_TEST_ENDPOINT=1` — mirror the stub seam's gate block verbatim (`api.py` `/_test/stub/inbound`, the "dual-gated like purge-sweep" region ~`:2970-3018`).
- The old `discord_hat` conventions (recovered via `git show 138025e^:tests/live/discord_hat/.env.hat.example` and its README) used N sender bots (`THE_ONE_HAT_BOT_TOKENS` list). This flight simplifies to ONE driver bot: `THE_ONE_HAT_DRIVER_TOKEN` (singular, per flight DD-7). The README's operational wisdom worth carrying into the new docs: bot apps must be created in a REAL browser (hCaptcha + MFA block automation); the DRIVER bot does NOT need Message Content intent (it only POSTs and reads via REST); the MAIN bot DOES need it; `.env.hat` is gitignored, only a `.example` with placeholders is committed (verify the gitignore pattern survived Flight 1's deletion — re-add if not).
- Leg 2's finding, folded here as this flight's own consequence: `tests/browser/test_studio_connector_editor.py::test_studio_connector_doctor_no_plugin_registered` pins the Flight-2-era "no plugin registered" doctor path for a `discord`-typed connector — leg 1's unconditional production registration falsified that premise (the real plugin now answers "failed: no bot token configured"). Per the leg-design risk rule, a test pinning behavior the new design breaks is re-aimed and RENAMED (never delete-and-readd) so git blame documents the intent shift: point it at a `stub`-typed connector with the stub gate closed — the only remaining no-plugin state in a live process.
- The behavior spec draft (`tests/behavior/discord-live-round-trip.md`, status `draft`) fixed the key observables and 6 steps; this leg finalizes env-var names, the step-6 disconnect mechanism (the sever route), and flips status to `active`. The spec's DELIBERATE proof shape is unchanged: NO tool-discipline nudge on `test-agent` — the leg-2 carve-out is the mechanical fallback being proven.
- The behavior test RUN is the Flight Director's job (via `/behavior-test`), not this leg's Developer. This leg makes the run POSSIBLE; the leg lands only when the gate passes (or the operator dispositions a failure), per the agentic-workflow behavior-test rule.
- Budgets after leg 2: Discord subpackage 712 (+ sever hook, expect ≤~40 more) of 1,100; JS 21 of ≤50 used (this leg should add none).

## Inputs

- Legs 1–2 uncommitted tree: working Discord client with per-account state; carve-out + `enabled` key live; suite at 3,728 passing.
- `tests/behavior/discord-live-round-trip.md` (draft) and Flight 2's committed exemplars (`tests/behavior/stub-connector-round-trip.md` + run logs) for spec conventions.
- `the_one/connectors/README.md`, `agents.md`, project `CLAUDE.md` — current state pre-Discord.

## Outputs

- `the_one/connectors/discord/` — `sever_for_test()` on the client (abrupt ws close, no close handshake, no state cleanup — the point is to simulate a network drop).
- `the_one/interfaces/web/api.py` — `POST /_test/discord/sever` dual-gated route (gate → 403; unknown connector or no live client → 404/409; missing hook on the client → 501-style explicit error, not a silent no-op).
- `tests/behavior/discord-live-round-trip.md` — finalized, status `active`.
- `tests/behavior/.env.hat.example` (or equivalent committed placeholder file; real `.env.hat` gitignored).
- `tests/browser/test_studio_connector_editor.py` — the re-aimed, renamed no-plugin doctor test.
- Unit tests for the sever route (gate closed/open, each error state) and the client hook.
- Docs: `the_one/connectors/README.md` Discord section; `agents.md` (carve-out + new gate registered per its risk-tiering convention); `CLAUDE.md` (env conventions: `THE_ONE_DISCORD_TEST_ENDPOINT`, the HAT env vars).

## Acceptance Criteria

- [x] **AC-1 Sever hook**: `sever_for_test()` exists on the Discord client only (NOT on the Protocol, NOT on the stub); calling it kills the ws transport abruptly; the gateway's normal death-detection then drives `is_alive()` → False and the manager's reconnect — unit-asserted against the fake gateway (sever → fixture sees abrupt close → next connect resumes).
- [x] **AC-2 Dual-gated route**: with the gate closed (either condition), the route 403s and — like the stub seams — does not exist in any observable form beyond that; with the gate open, sever on a live Discord connector returns ok. Error taxonomy REQUIRES a repo-existence check FIRST (design review 2026-09-01: `client_for` returns the identical `None` for never-started and mid-backoff — it cannot carry the 404/409 distinction alone; use the `generate_connector_pairing_code` idiom at `api.py:2955-2959`, `repo.get` → `KeyError` → 404): unknown connector → 404; row exists but `client_for` → None (mid-backoff or not started) → 409; client present but hook missing (stub-typed) → explicit missing-hook error. Client reached ONLY via `manager.client_for` + `getattr` (platform-agnostic — Telegram inherits the seam for free). **The seam sweep test** `tests/test_seam_routes_403_sweep.py` asserts `_EXPECTED_SEAMS` matches every discovered `/api/_test/` route — add the new route to that frozenset or the sweep breaks on registration.
- [x] **AC-3 Behavior spec finalized**: `discord-live-round-trip.md` status `active`; preconditions name the exact env contract (`THE_ONE_HAT_DRIVER_TOKEN`, `THE_ONE_HAT_GUILD_ID`, `THE_ONE_HAT_TEST_CHANNEL_ID`, `THE_ONE_HAT_ALWAYS_LISTEN_CHANNEL_ID`, `THE_ONE_HAT_UNTRACKED_CHANNEL_ID`) and the Flight 2 dev-instance conventions; step 6's mechanism is the sever route; the no-nudge proof language stays; the spec passes the `/behavior-test` Phase-1 shape validation against ARTIFACTS.md.
- [x] **AC-4 Env example + hygiene**: the committed example file carries placeholders only; `.env.hat` (real) is already covered — the unscoped `*.env.hat` gitignore pattern survived Flight 1 (design review verified; optionally prune the dead `tests/live/discord_hat/.env.hat` line while there); the example documents the driver-bot provisioning notes (real browser, no Message Content intent on the driver, MAIN bot needs it).
- [x] **AC-5 Falsified test re-aimed** (*re-designed after review cycle 1 — the original stub-with-gate-closed re-aim was unimplementable*: stub creatability in Studio and stub plugin registration share the SAME dual gate — `api.py:2712-2725` `_creatable_connector_types` vs `app.py:275-280` — so with the gate closed the type isn't even selectable, and with Discord unconditionally registered NO type is both UI-creatable and plugin-less; documented at `agents.md:497` / `CLAUDE.md:109`): the browser test is RENAMED (blame-preserving) and re-aimed at the state the lane CAN reach and that leg 1 actually created — a `discord`-typed connector with no token, whose doctor reports the real plugin's failure (e.g. name it `test_studio_connector_doctor_reports_plugin_failure_without_token`; assert the failed status + message shape, not exact prose). The no-plugin doctor branch keeps its coverage at UNIT level where the state is constructible (registry cleared / nothing registered): verify existing unit coverage of `test_connector`'s no-plugin branch and add a test if it's missing. The browser lane's HTTP-only seeding convention stays intact (no out-of-band DB writes). Studio lane green including the renamed test (the leg-2 flake `test_last_updated_renders_relative_time_format` excepted if it recurs — recheck via isolated rerun before calling it a failure).
- [x] **AC-6 Docs**: connectors README gains the Discord section (protocol scope incl. the no-sharding/no-compression trade-off, close-code policy + one-cycle mid-session latency, resume behavior, rate-limiter shape, token in `secrets["token"]`, `enabled` key); agents.md registers `THE_ONE_DISCORD_TEST_ENDPOINT` per its gate risk-tiering convention and documents the carve-out; CLAUDE.md gains the HAT env conventions. No operator-identity leaks anywhere.
- [x] **AC-7 Budget + suite**: subpackage total re-counted and reported (≤1,100); `make test-unit` green; studio browser lane green per AC-5.
- [x] **AC-8 Live gate (Flight Director-run, blocks leg landing)**: `/behavior-test discord-live-round-trip` PASSES against the operator's test guild; run log committed at `tests/behavior/discord-live-round-trip/runs/`. This criterion is verified AFTER the Developer hands off — the leg does not land while it fails, unless the operator dispositions a failure as a known issue (recorded in the flight log).

## Verification Steps

- AC-1/AC-2: scoped foreground runs of the new test files.
- AC-3: run the spec-shape check by eye against ARTIFACTS.md's Behavior Test — Spec format (all required sections present and non-empty).
- AC-5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio` foreground (note leg 2's anomaly: ALWAYS set `PYTHON` explicitly — bare invocation falls back to a stale system python).
- AC-7: `wc -l the_one/connectors/discord/*.py`; `make test-unit` foreground once at leg end.
- AC-8: Flight Director runs `/behavior-test discord-live-round-trip` after operator setup.

## Implementation Guidance

1. **Sever hook**: a few lines — call `transport.abort()` on the underlying ws, NEVER `.close()` in any form (design review: `ws.close()` always performs the full close handshake regardless of arguments — the fixture's own `close_abrupt()` at `tests/_discord_gateway_fixture.py:79-83` uses `transport.abort()` for exactly this reason), and do NOT set the self-initiated-close flag. Leave all state intact so the reconnect path runs exactly as after a network drop (symmetric to the already-passing abrupt-close resume test at `tests/test_discord_gateway.py:180`). Implementation freedom: the hook may live on `GatewayConnection` with a one-line `DiscordClient.sever_for_test()` delegate.
2. **Route**: copy the stub seam's gate block shape verbatim with the new env name — including the raw `Request` + manual `await request.json()` body handling (a Pydantic body model would let FastAPI 422 an empty body BEFORE the gate line runs, breaking the 403-sweep's minimal-body POST assumption); handler order is `repo.get` (→404, the pairing-code idiom) → `manager`/`client_for` (→409 when None) → `getattr(client, "sever_for_test", None)` (→missing-hook error) → call. Place it adjacent to the stub seams in the same `/_test/` region, and add it to `_EXPECTED_SEAMS` in `tests/test_seam_routes_403_sweep.py`.
3. **Spec finalization**: keep the 6 steps and their observables; fill in the env-contract preconditions and step-6 payload (`POST /_test/discord/sever {"connector_id": ...}`); update the header (`Status: active`, drop the draft caveats).
4. **Renamed browser test**: per AC-5's re-design — rename to what it now proves (tokenless discord connector → real plugin failure via doctor); assert status + message shape, not exact prose. Unit-cover the no-plugin branch separately if not already covered.
5. **Docs order**: README section first (it feeds the example file's comments), then agents.md gate registration, then CLAUDE.md env conventions.
6. **Test-run discipline**: foreground only, explicit timeouts (up to 600000 ms), never background, never end turn mid-run; `uv sync` always `--extra dev`; scoped iterations, `make test-unit` once at leg end.

## Edge Cases

- **Sever on a connector mid-backoff** (no live client): 409-style error, not a crash — `client_for` returns None.
- **Sever route on a stub-typed connector**: the stub client has no hook → the explicit missing-hook error (this is also the unit test for the `getattr` discovery path; unit-level, where stub registration is free via `register_for_test`).
- **Gate env set but dev_mode off**: 403 — both conditions, mirroring the stub seam exactly.
- **Spec preconditions vs. reality drift**: the spec is finalized against code, but ids/tokens arrive at run time — anything discovered wrong AT RUN TIME follows the behavior-test skill's precondition-amendment discipline (in-place amendment + recorded rationale), not silent editing.

## Files Affected

- `the_one/connectors/discord/plugin.py` (or `_gateway.py`) — sever hook
- `the_one/interfaces/web/api.py` — sever route
- `tests/behavior/discord-live-round-trip.md`, `tests/behavior/.env.hat.example`, `.gitignore` (if needed)
- `tests/browser/test_studio_connector_editor.py` — renamed, re-aimed test
- `tests/test_seam_routes_403_sweep.py` — `_EXPECTED_SEAMS` addition
- New unit tests for hook + route + (if missing) the no-plugin doctor branch
- `the_one/connectors/README.md`, `agents.md`, `CLAUDE.md`

## Citation Audit (2026-09-01)

Verified against the leg-2 working tree: `manager.py:92-94` `client_for`; stub seam gate block + `/_test/stub/*` routes in `api.py` (~`:2970-3018` region, gate string "test-seam endpoint requires dev_mode + THE_ONE_STUB_TEST_ENDPOINT=1"); old HAT conventions recovered from `138025e^` (README + `.env.hat.example` — N-token list shape confirmed, adapted to singular per DD-7); `tests/behavior/discord-live-round-trip.md` draft header + 6-step table; leg-2 flight-log entry for the falsified browser test and the `PYTHON` anomaly. All live.

---

## Post-Completion Checklist

**Flight-end commit model — do NOT commit and do NOT signal `[COMPLETE:leg]`:**

- [x] AC-1..AC-7 verified (AC-8 is the Flight Director's post-handoff gate)
- [x] Tests passing (`make test-unit` + studio lane, foreground)
- [x] Flight log updated (subpackage count, test numbers, doc files touched)
- [ ] Leg status left `in-flight` — the FLIGHT DIRECTOR sets `landed` after AC-8 passes
- [ ] Signal `[HANDOFF:review-needed]`
