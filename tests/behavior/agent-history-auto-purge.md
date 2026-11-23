# Behavior Test: Daily Automatic Purge Sweeps Aged Conversations

**Slug**: `agent-history-auto-purge`
**Status**: active
**Created**: 2026-06-06
**Last Run**: 2026-06-06-14-10-46

## Intent

Verifies the daily automatic purge end to end against a live instance: a single sweep
deletes every conversation whose last engaged interaction (`updated_at`) predates the
owning agent's retention window, while leaving conversations inside the window intact
and never touching another agent's conversations. It also verifies the due-based
catch-up semantics: the global `last_purge_at` advances after a sweep, and a sweep is
skipped when one ran recently.

This needs real-environment observation because the behavior is the composition of three
runtime facts that unit tests pin individually but cannot exercise together against a
live DB + lifespan: per-agent cutoff arithmetic over real `updated_at` strings, the
agent-enumeration sweep, and the in-memory `_sessions` eviction. The unit suite (Legs 2–3)
asserts the deterministic invariants; this test confirms they hold against the running
service driven through real HTTP, and that the dev-mode trigger fires one true sweep.

## Preconditions

- A host-native instance is running on a **dedicated non-default port (`{PORT}`: 8486 or higher, assigned per run; never 8484 or 8485) with a scratch data
  directory** — e.g. `THE_ONE_PORT={PORT} THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/data
  the-one serve` (create the credential first with `the-one rotate-api-credential` against that data dir) started from a scratch working directory (`mkdir -p <scratch>/cwd && cd <scratch>/cwd`, detached, PID recorded; stop and restart by that PID after `the_one/` changes, against that same instance; CLAUDE.md "SAFETY RULE") — never
  the operator's default `:8484` instance. Started in **dev mode** (`settings.dev_mode`
  true) with the purge-sweep test seam enabled (`THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1`, the
  env gate from Leg 3).
- At least two agents exist (the `mock` provider suffices): a **target** agent with a
  known retention window (default 30 days is fine) and a **bystander** agent that must be
  left untouched. Operator-checkable via `GET /api/agents`.
- `curl` available for seeding sessions and reading observations.
- No assumptions about pre-existing sessions for the two agents — the test seeds its own
  and asserts on counts relative to what it seeds (it reads the baseline count first).
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" — read the long-lived credential from the
  instance's data directory and attach `Authorization: Bearer <credential>` to every
  `curl` call in the Steps below (they use relative paths against this instance's base
  URL).

## Observables Required

- **http** (response status / JSON body) — measured via `curl` (Bash apparatus): seed
  sessions (`POST /api/chat/sessions`), trigger the sweep (`POST /api/_test/purge-sweep`),
  read remaining sessions (`GET /api/chat/sessions?agent_name=…`), read `last_purge_at`
  (returned by the trigger response).
- **shell** (exit code, stdout) — measured via Bash for the curl invocations and JSON
  field extraction.

**Assertion convention (read before running):** survivors and victims are tracked by the
**session ids returned from the seeding `POST`s**. So the Executor records each seeded id at
POST time and asserts presence/absence of those ids after the sweep.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Read baseline: `GET /api/chat/sessions?agent_name=TARGET` and `?agent_name=BYSTANDER`; record both counts. | (Setup row — record the two baseline counts for later delta assertions. No judgment.) |
| 2 | Seed for TARGET via `POST /api/chat/sessions`: (a) an **aged** session with `updated_at` 60 days in the past; (b) a **recent** session with `updated_at` = now. | Each `POST` returns 201 with the session id echoed. TARGET now has baseline+2 sessions on `GET …?agent_name=TARGET`. |
| 3 | Seed for BYSTANDER via `POST /api/chat/sessions`: one **aged** session with `updated_at` 90 days in the past. | `POST` returns 201. BYSTANDER now has baseline+1 sessions. |
| 4 | Fire one sweep: `POST /api/_test/purge-sweep`. | Response is 200 with a JSON body reporting a `deleted` count ≥ 1 (at least TARGET's aged row) AND a `last_purge_at` timestamp that is recent (within the last minute). |
| 5 | Read TARGET's sessions: `GET /api/chat/sessions?agent_name=TARGET`; check the seeded ids from step 2. | The **aged** TARGET id (2a) is **absent**; the **recent** id (2b) is **present**. Net TARGET count = baseline+1. This proves the sweep's cutoff is age-based (`updated_at` alone), keeping a row inside the window while dropping one outside it. |
| 6 | Read BYSTANDER's sessions: `GET /api/chat/sessions?agent_name=BYSTANDER`. | BYSTANDER's aged session is **still present** — count = baseline+1, unchanged. The sweep honored BYSTANDER's own (default) retention window independently and, more importantly, did not bleed TARGET's sweep across agents. *(Note: this asserts no cross-agent bleed; BYSTANDER's 90-day-aged row is itself past the default 30-day window, so whether it is also swept depends on BYSTANDER's retention — see Variant B for the explicit per-agent-window case. For THIS step seed BYSTANDER with an aged row whose age is **inside** BYSTANDER's window to isolate the isolation assertion. Author note: set BYSTANDER's seed `updated_at` to 5 days past, not 90, so the only thing under test here is "TARGET's sweep didn't touch BYSTANDER.")* |
| 7 | Fire a second sweep immediately: `POST /api/_test/purge-sweep`, but this time **without** forcing (use the due-respecting form if the endpoint exposes one; otherwise read `last_purge_at` and assert the due-check would skip). | Either the endpoint reports `skipped` / `deleted: 0` because `< 24h` elapsed since step 4's `last_purge_at`, OR (if the test endpoint always forces) the response still reports `deleted: 0` because there is nothing left to purge. The due-based "don't re-run within 24h" property is observable via the unchanged `last_purge_at` on the due-respecting path. |

**Author corrections folded in (do not re-derive at run time):** Step 6's BYSTANDER seed age is **5 days** (inside window), so step 6 isolates cross-agent non-bleed; the explicit per-agent-window difference is exercised in Variant B. Step 7's exact form depends on whether Leg 3 gives the test endpoint a `force` flag — the spec's intent is "the second sweep does not delete anything and the due-check is observable," not a specific status string.

## Out of Scope

- The manual "Purge now" button flow — covered by `agent-purge-now-clears-history` (F2).
- The retention setting set/persist roundtrip — covered by `agent-retention-setting-roundtrip` (F1).
- Real 24h wall-clock timing and the lifespan loop's sleep cadence — exercised by unit
  tests (Leg 3 due-check) and the restart-catch-up case, not by this live UI-less test.
- WebSocket `session_list` push freshness after the sweep — the in-memory `_sessions`
  eviction is asserted by Leg 3 unit tests; this test reads the authoritative REST view.

## Variants (optional)

- **Variant A — restart catch-up:** Set `last_purge_at` to ~25h in the past (or seed it
  absent), restart the instance, and assert a sweep ran during lifespan startup
  (`last_purge_at` advanced, aged rows gone) — the down-through-a-due-window self-heal case.
- **Variant B — per-agent windows differ:** Give TARGET a 7-day retention and BYSTANDER a
  90-day retention, seed each a 30-day-aged session, run one sweep, and assert TARGET's row
  is purged while BYSTANDER's identical-age row survives — proving the cutoff is computed
  per agent, not globally.
