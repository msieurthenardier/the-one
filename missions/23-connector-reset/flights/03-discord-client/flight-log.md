# Flight Log: Discord Client

**Flight**: [Discord Client](flight.md)

## Summary
In-flight 2026-09-01. Branch `flight/03-discord-client` cut from main @ `9245047` (includes PR #186). Flight-end commit model (one review+commit after the last autonomous leg).

### Flight Director Notes

- 2026-09-01 — Flight `ready` → `in-flight`; branch cut verified against synced main. Crew file `leg-execution.md` validated (Crew/Interaction Protocol/Prompts present).
- 2026-09-01 — Leg 1 design review cycle 1 (Sonnet Developer): approve with changes. High: no Gateway sequence-number (`s`) tracking — heartbeat `d` and resume `seq` payloads would be wrong and the resume test would pass on opcode alone. Medium: single-listener fixture can't prove `resume_gateway_url` is honored (now a two-listener scenario); op 7 RECONNECT unhandled (now AC-3b, handled directly); no stale-resume-URL fallback (now an edge case). Designer answers to review questions: seq tracking added (omission, not deliberate); op 7 handled directly; two-address fixture required; mid-session permanent-close one-extra-cycle latency ACCEPTED as stated behavior (read-loop signaling adds machinery for no recovery benefit) and documented in AC-4. Budget heads-up: the added seq/op-7/fallback surface tightens the ≤1,100 ceiling — watch mid-leg counts. All fixes applied; substantive → cycle 2 re-review spawned.
- 2026-09-01 — Leg 1 design review cycle 2: approve with changes. Medium: stale-resume-URL edge case untestable as written ("repeated resume rejections" had no threshold; fallback state mutation unspecified). Fixed per the reviewer's own prescription: trigger narrowed to connection-error-only, fallback clears `resume_gateway_url`+`session_id` in per-account state and re-identifies on the default URL within the same `connect()` call. Also applied: AC label nit; op-7 self-initiated-close must bypass the close-code-policy check (new edge case). At the 2-cycle cap with only reviewer-specified completions outstanding → applied and proceeding (Flight 2 precedent). Leg 1 `ready`. Reviewer flagged early mid-leg budget checks given the amendment surface — instruction passed to the implementing Developer. — modifies the shared contract (`base.py`: `PermanentConnectorFailure`) and manager lifecycle (`_run`/`_connect_once`), both with existing consumers (stub plugin, Flight 2 manager tests); design review required despite the flight-level Architect cycles, because leg-level implementation guidance carries new detail (fixture architecture, registration wiring) not covered there. DD-7's `sever_for_test` hook deliberately deferred to leg 3 — unit resume tests are fixture-server-driven and need no client hook.

- 2026-09-01 — Leg 1 landed (Sonnet Developer, one spawn, no stalls): 712/1,100 subpackage lines, 40 new tests, `make test-unit` 3,711 passed / 380s. Mid-leg READY-race bug caught by the fixture's zero-delay dispatch test and fixed in place (documented in Leg Progress). `legs_completed = 1`.
- 2026-09-01 — Leg 2 `loop-carveout-and-enabled` designed. **Risk tier: HIGH** — touches the frozen agent loop under the mission's amended carve-out (the flight's most sensitive surface), plus lifecycle/state transitions (`start_all` skip, PUT enable/disable branches) and a validator change on a shared model. Design review mandatory. Key design point recorded: `manager.start()` stays dumb — the disabled-skip lives in `start_all` and the API call sites per DD-6's assignment, preserving `start()`'s contract for in-memory-account unit tests.

- 2026-09-01 — Leg 2 design review cycle 1 (Sonnet Developer): approve with changes. HIGH: AC-8's "unchanged → today's stop+start" branch would restart a listener on any PUT to an already-disabled connector (unrelated field edit), silently defeating pause-without-delete — fixed to branch on the NEW effective enabled value only, with the trap case now an explicit test. MEDIUM: `registry.get()` raises `KeyError` (not Optional) — seed check rewritten to the `tool_names` membership property. LOW: citation drift repaired; JS checked-state trap (`config.enabled !== false`, never truthy) spelled out. Reviewer also VERIFIED three load-bearing claims: seed condition is exactly "enabled for the agent" (send tool unconditionally yielded by BuiltinToolProvider, gated only by the shared filter); no existing test pins the exact baseline set through the factory path (visibility tests construct Agent directly; test_factory uses a stub provider without the send tool); no new Agent-invalidation path needed (session-rejoin rebuild covers it). AC-8 fix is substantive → cycle 2 re-review spawned.

- 2026-09-01 — Leg 2 design review cycle 2: approve with changes, all reviewer-specified completions. Medium: flight DD-6 still recorded the disproven "else restart-as-today" PUT framing — DD-6 amended in place with an annotation (in-flight spec modification, rationale here per the skill's mid-execution rule); AC-8's trap-case test payload shape pinned to full-config-resend (the endpoint's shallow top-level merge would drop `enabled: false` from a partial body and the test would exercise nothing). Low: Inputs citation `:188-190`→`:188-191`; stale connector-editor.js header comment added to guidance; `.checked` reader note; seed-guidance clause disambiguated. Reviewer confirmed rotation-hook safety (iterates `listener_ids()`, which never contains a disabled id) and the no-invalidation claim (`app.py:1157-1165` rejoin rebuild). At the 2-cycle cap → applied and proceeding. Leg 2 `ready`.

- 2026-09-01 — Leg 2 Developer stalled mid-leg (the recurring pattern: backgrounded the studio browser lane and ended its turn "waiting for the notification" despite the preemptive foreground instruction). Resumed via message with an explicit kill-and-rerun-foreground directive. Sixth occurrence across the mission — already queued as harness feedback.

- 2026-09-01 — Leg 2 landed (after the stall resume): all 12 ACs verified; `git diff --stat the_one/agent/` = exactly core.py +13 / factory.py +14; JS net +21 of ≤50; `make test-unit` 3,728 passed (+17, matching new tests exactly); studio lane green except two: one confirmed load-timing flake (isolated rerun passed) and one REAL falsified test (`test_studio_connector_doctor_no_plugin_registered` — leg 1's production Discord registration changed the premise). FD ruling: that failure is this flight's own consequence, not a squawk — folded into leg 3 as a named AC (re-aim + rename per the risk-check rule). `legs_completed = 2`.
- 2026-09-01 — Leg 3 `live-gate-and-docs` designed. **Risk tier: HIGH** — adds a dual-gated test seam (security-sensitive surface by the crew file's own Reviewer-tier definition), finalizes an external contract (the behavior spec other readers depend on), and re-aims a pinning test. Design review spawned. Leg structure notes: the behavior-test RUN (AC-8) is the Flight Director's job post-handoff — the Developer makes it runnable; the leg lands only when the gate passes. Operator prerequisites (driver/main bot tokens, guild/channel ids) become blocking at AC-8, not before.

- 2026-09-01 — Leg 3 design review cycle 1: NEEDS REWORK, two highs requiring designer resolution. (1) AC-5's stub-with-gate-closed re-aim was self-contradicting — stub creatability and stub registration share the same dual gate, so the browser lane can never select a plugin-less type; FD ruling: browser test re-aimed at the reachable, genuinely new state (tokenless discord connector → real plugin doctor failure, renamed), no-plugin branch coverage moves/stays at unit level, HTTP-only lane seeding convention preserved. (2) AC-2's 404/409 taxonomy impossible via `client_for` alone (identical `None` for unknown and mid-backoff); FD ruling: repo-existence-first per the pairing-code idiom. Mediums applied: `_EXPECTED_SEAMS` sweep-test addition; sever mechanism pinned to `transport.abort()` (never `ws.close()`, which always handshakes) without the self-initiated flag. Low: `*.env.hat` gitignore pattern confirmed surviving. Substantive rework → cycle 2 re-review spawned.

- 2026-09-01 — Leg 3 design review cycle 2: APPROVE. All three reworked items code-verified: tokenless-discord doctor returns before any REST construction (`plugin.py:242-250` — hermetic, no egress; the browser lane hits the real plugin per the unconditional registration); no-plugin unit coverage already exists (`test_connector_routes.py:341` under the registry-clearing autouse fixture — AC-5's conditional clause is moot); 404→409→missing-hook taxonomy implementable per the pairing-code idiom; sever-abort path traced (permanent-failure check short-circuits on `ready_reached`, `finally` drops `_alive`, resume state on `_AccountState` untouched). One non-blocking callout applied: raw `Request` body per the stub seams so the gate outruns FastAPI validation. Leg 3 `ready`.

- 2026-09-01 — Leg 3 Developer stalled at the same point (backgrounded `make test-unit`; seventh occurrence); resumed with the foreground directive. Also noted: leg 3's Context bullet on the falsified browser test still carries the pre-rework stub-re-aim wording (missed while AC-5 received the full redesign during cycle-1 rework; the leg was already `in-flight` when noticed, so it stays per immutability). AC-5 is authoritative and records why the stub approach was unimplementable; the Developer's spawn prompt carries the corrected instruction explicitly.

- 2026-09-01 — Leg 3 AC-1..AC-7 verified by the Developer (after one stall resume): sever hook + dual-gated route (own gate name `THE_ONE_DISCORD_TEST_ENDPOINT`, 6 route tests, seam sweep updated), behavior spec `active`, env example committed, falsified browser test renamed in place and re-aimed, docs rewritten. Subpackage 739/1,100; `make test-unit` 3,736 passed / studio lane 147 passed, 0 failures either. Leg 3 remains `in-flight` pending AC-8 (the live behavior gate) — BLOCKED on operator-supplied credentials (driver/main bot tokens, guild/channel ids) per the flight prerequisite; escalated to the operator. Developer anomalies logged: the `uv sync` extras interaction (bare `--extra dev` strips all-llms/gui — full incantation now in the log), two timing races in its own new tests found and fixed with polling, and a +1 test-count drift vs the leg-2 baseline (0 failures, flagged for the debrief).

- 2026-09-01 — **Live gate run 1, checkpoint 2 FAIL → DD-4/DD-7 contradiction found and resolved.** The behavior test's driver-bot mention got no reply: `plugin.py:80-81` drops ALL bot-authored messages exactly as DD-4 specified — and DD-7's apparatus IS a bot. Design contradiction between two flight DDs that neither the flight-level Architect cycles nor three leg reviews caught: the apparatus was premise-audited on act+observe axes but never against the pipeline's admission policy (methodology lesson for the debrief — the apparatus audit needs a third axis: CAN ITS OUTPUT BE ADMITTED). Verified live before diagnosis: gateway connect, identify, doctor all worked (the client itself is sound). Operator decision (AskUserQuestion): amend DD-4 with the allowlist carve-out — self+webhook always dropped; other bots admitted iff on `config.allowlist.peers`. DD-4 amended in flight.md with annotation; Developer spawned for the fix + unit tests; checkpoint 2 will be rerun (rerun-checkpoint disposition) with the run log recording both attempts.

- 2026-09-01 — **Live gate checkpoint 2 attempt 2 FAIL → second real finding: the reply path has no mechanism.** After the DD-4 fix, inbound works end-to-end (session keyed to the channel, correct answer computed by ministral in ~30s) but the reply stays `visibility: operator` and never reaches Discord: `dispatch_inbound` passes only raw text (the model can't target the send tool — the discoverability gap the STUB SPEC's Out of Scope explicitly deferred: "tracked as a follow-up rather than asserted or fixed here"), and assistant text is operator-only by the visibility contract. Operator viewed the stranded reply live in the dev-instance Chat UI (handoff-minted tab) and decided: auto-respond. **DD-10 added** (auto-reply mechanical fallback; full text in flight.md) — operator-approved via the mid-flight decision protocol. Developer spawned to implement in `inbound.py` + re-aim the tests and the Flight 2 stub spec rows that pinned the superseded operator-only-reply behavior (deliberate spec re-author per the HAT contract-change rule, not a silent break). Checkpoint 2 attempt 3 to follow.

- 2026-09-01 — **Live gate checkpoints 3-4 PASS on first attempt** (untracked silence exact; always-listen unprompted reply in ~24s, Discord/app content verbatim-identical). **Checkpoint 5 FAIL → third finding: target discoverability on the operator-instructed send path.** The a11y evidence is definitive and VALIDATES DD-5 (model named `send_to_platform_channel` spontaneously — schema baseline-visible, zero search, bare prompt) but it asked the operator for connector/channel ids: the session's binding is invisible to the model. DD-10's boundaries held correctly (clarifying reply did NOT auto-deliver — operator-path turn; operator bubble rendered `[operator-only]`). Operator decision: **DD-11 added** — send-tool `target` optional, defaulting to the current session's own keying (contextvar set on both paths; Mission 10 keying columns). Developer spawned; checkpoint 5 rerun to follow.

- 2026-09-01 — Checkpoint 5 attempt 2 FAIL post-DD-11: the Validator's tier analysis — the model READ the default-target mechanism back in its own words yet confirmed instead of acting, against the base prompt's own take-the-action directive. Model-policy-under-ambiguity, not wiring; a third blind rerun would not self-resolve. Operator decision: stronger model for the gate — `test-agent` rebound `ministral-3:8b` → `gpt-oss:20b` (operator pulled it; same ollama provider; bare prompt unchanged, no nudge). ministral's confirm-bias recorded as a small-model limitation for the debrief; the spec's no-nudge proof still stands or falls mechanically on the rerun.

- 2026-09-02 — **Live gate PASSED 6/6** — `/behavior-test discord-live-round-trip` run 2026-09-01-19-19-17, run log committed at `tests/behavior/discord-live-round-trip/runs/`. Checkpoints 2 and 5 each took 3 attempts; every failure was a real finding → DD-4 amendment, DD-10, DD-11, one spec-precondition amendment (driver-bot Message Content intent), one model rebind (ministral→gpt-oss:20b after a model-policy failure tier was established; ministral's confirm-bias recorded for the debrief). Checkpoint 6 proved sever→re-identify forensically (the `/users/@me` log-signature match). **Leg 3 AC-8 met → leg 3 `landed`.** Validator's closing carries spec-quality + reusable proof-pattern feedback for the debrief (edited_timestamp redaction check, DOM parent-chain containment, log-signature uniqueness). Next: Phase 2d flight-end review over ALL uncommitted changes (legs 1-3 + three amendments), then commit + draft PR, then leg 4 guided HAT.
- 2026-09-02 — Budget correction (flight-end review note): Discord subpackage is **767** lines after the DD-4/DD-10/DD-11 amendments (the leg-3 entry's 739 predates them); ≤1,100 ceiling intact. Mission connector-Python running total: 1,060 prior + 767 + the inbound/tool amendment deltas.
- 2026-09-02 — Flight-end review (Sonnet Reviewer — security tier per crew file: dual-gated seams, admission policy, agent-loop carve-out in the diff): **[HANDOFF:confirmed]**, no blocking issues. Verified: carve-out diff exactly the sanctioned 27 lines; DD-4 self/webhook drop unconditional and ordered before the allowlist check; DD-10 skip rule scans the whole turn, visibility flips only on success; DD-11 defaulted targets flow through the unchanged authorization block (dedicated tests); sever route gate-checks before body/repo (no info leak); no new deps; no operator-identity leaks. Two non-blocking doc notes fixed in this pass (duplicate log entry removed, budget figure corrected above). Studio lane accepted on its two documented green runs against this tree.


## Flight Design Notes (planning, 2026-09-01)

- Two mission-level resolutions recorded in mission.md during this flight's planning: RQ8 (owner-amended agent-loop constraint → minimal send-tool visibility carve-out) and RQ9 (`enabled` as config key, no migration).
- Architect design review, 2 cycles (cap). Round 1 (approve with changes): close-code "stop" had no manager give-up primitive → typed `PermanentConnectorFailure` in base.py with a narrow `_run` catch; graceful stop/start can never exercise RESUME → fixture-pins-resume / live-accepts-any-reconnect split with a dev-gated sever hook; DD-5 naive append would duplicate schemas past `_on_search_match` dedup → seed-the-containers approach; per-account plugin state made explicit; `supports_tools()=True` prerequisite. Round 2 (approve with changes, amendment-scoped): failure marker moved plugin-side (manager has no path to doctor) with the connect()-clears-marker lifecycle rule; `_connect_once`'s catch-all needs the explicit re-raise; `reset()` re-seeding requires captured instance state + a fifth pin test; DD-7's sever-hook shape settled as an optional `getattr` client hook via `manager.client_for` behind a dual-gated route (`THE_ONE_DISCORD_TEST_ENDPOINT`). All fixes were reviewer-specified completions (no design disputes) — applied and proceeding to operator sign-off per the Flight 2 precedent at the cycle cap.

---

## Leg Progress

### Leg 1 — discord-client (landed 2026-09-01)

Implemented the hand-rolled Discord Gateway v10 + REST client as
`the_one/connectors/discord/`, registered production plugin, and proved
the full protocol surface against a fake in-process gateway — no live
Discord traffic in this leg.

**Built**:
- `base.py`: `PermanentConnectorFailure(ConnectorClientError)`.
- `manager.py`: `_connect_once` re-raises `PermanentConnectorFailure` ahead
  of its catch-all; `_run` catches it narrowly (log + `return`, no
  backoff), leaving the `_ListenerEntry` in place per the documented
  lifecycle note.
- `registry.py`: production `register()` (docstring distinguishes it from
  `register_for_test`; mechanically identical flat-dict registration).
- `the_one/connectors/discord/` subpackage:
  - `_gateway.py` (277 lines) — hello/heartbeat (jitter first beat,
    ACK watchdog)/identify/resume/dispatch, op 7 RECONNECT handled
    directly, op 9 INVALID_SESSION same-connection re-identify, stale-
    resume-URL same-`connect()` fallback, close-code policy checked ONLY
    pre-READY (mid-session permanent codes surface at the next handshake
    — documented design-review-accepted latency, see the module
    docstring and `plugin.py::connect`).
  - `_rest.py` (146 lines) — `httpx.AsyncClient` against
    `/api/v10`, per-bucket + global rate limiter (429 `retry_after`,
    bounded retries, `global: true` gates every bucket), 8 endpoint
    helpers (Get Gateway Bot, Get Current User, Create Message, Create
    DM, Get Channel, Get Channel Messages, Trigger Typing, Get Guild
    Channels).
  - `plugin.py` (265 lines) — `DiscordPlugin`/`DiscordClient`, per-account
    `_state` dict (the `StubPlugin._live` shape), MESSAGE_CREATE
    translation (`is_dm`/`mentions_bot`/`peer_name`/`thread_id`, bot/
    self/webhook drop), `history()` hook, idempotent `disconnect()`,
    `doctor()` (failure-marker short-circuit, REST-reachability check,
    ok/degraded/failed).
  - `__init__.py` (24 lines) — `register()` wiring into
    `the_one.connectors.registry`.
  - **Subpackage total: 712 / 1,100 lines** (mission running total: 1,772
    of 3,000 — 1,060 prior + 712 this leg).
- `interfaces/web/app.py`: unconditional Discord registration (own
  guarded try/except, before `ConnectorManager()`/`start_all`) with
  symmetric unregistration at shutdown, mirroring the stub hook's
  hygiene.
- `tests/_discord_gateway_fixture.py` — fake gateway (`websockets.serve`
  on an ephemeral localhost port), scriptable per test.
- New tests: `tests/test_discord_gateway.py` (12), `tests/test_discord_rest.py`
  (15), `tests/test_discord_plugin.py` (13) — 40 total, all against the
  fake gateway / mocked `httpx` transports, no live network.

**Acceptance criteria**: AC-1 through AC-11 (including AC-3b) verified —
gateway happy path, heartbeat discipline + sequence tracking (payload `d`
value asserted, not just opcode), resume with the two-listener fixture
(proves `resume_gateway_url` is honored, not just the resume opcode), op 7
RECONNECT, close-code policy (permanent codes raise pre-READY only;
mid-session codes surface at the next handshake per the documented design
decision; a manager-level test proves the listener task terminates on
`PermanentConnectorFailure` while an ordinary connect failure keeps
backing off), `_connect_once` re-raise, REST rate limiting (per-bucket +
global, 429 bounded retries), envelope translation (per-field and
per-drop-case), Protocol conformance (`isinstance` checks against the
runtime-checkable Protocols, `history()` hook, idempotent `disconnect()`),
production registration (lifespan test, two cycles), budget (712 ≤ 1,100),
purity (`git diff` on `pyproject.toml`/`uv.lock` empty — verified), and
suite green.

**Tests**: `make test-unit` — 3,711 passed, 10 skipped, 549 deselected, 17
warnings (all pre-existing, unrelated to this leg — Starlette/websockets
deprecation notices and a `forkpty` multithread notice from other test
files), 380s (0:06:20). Baseline was ~3,669 passing; +40 new Discord tests
(gateway 12 + REST 15 + plugin 13) accounts for the increase (+2 delta
from unrelated concurrent test-suite drift, not investigated — out of
this leg's charter).

**Mid-leg fix (found during implementation, not a deviation from the
spec)**: the original design read `bot_user_id`/private-channel cache
seeds back out of `ready_info` in `plugin.py::connect()` AFTER awaiting
`ready_future` — a race, since a MESSAGE_CREATE dispatched immediately
after READY is processed by the SAME gateway read-loop iteration
sequence, not by the awaiting `connect()` coroutine (which only resumes
on a later event-loop tick). Caught by a plugin-level translation test
using a fixture that dispatches MESSAGE_CREATE frames immediately after
READY with no delay. Fixed by moving the capture into
`GatewayConnection`'s READY handling itself (synchronous, before
`ready_future` resolves) — the same pattern already used for
`session_id`/`resume_gateway_url`. No behavior or AC change; the fix
tightened an implementation detail the spec didn't dictate at that level.

No deviations or anomalies from the leg spec.

### Leg 2 — loop-carveout-and-enabled (landed 2026-09-01)

Implemented the two hard-to-reverse changes in isolation: DD-5's
mission-amended send-tool visibility carve-out (agent loop, frozen
except this) and DD-6's `enabled` connector config key across its four
lifecycle touch points plus the Studio checkbox.

**Built, file-by-file**:

- `the_one/agent/factory.py` — ONE seed block after the built-in/MCP tool
  registration loops, before `Agent(...)`: membership check via
  `SEND_TO_PLATFORM_CHANNEL_TOOL_NAME in registry.tool_names` (never
  `registry.get(...)`, which raises `KeyError` on a filtered-out tool);
  when present, `tool.to_schema()` (the same source `SearchTools` uses via
  `registry.all_schemas()`) is appended to `loaded_schemas` and the name to
  `loaded_tool_names`. Imports the name constant from
  `the_one.tools.connector_send` — no string literal.
- `the_one/agent/core.py` — `__init__` captures
  `self._seed_schemas`/`self._seed_tool_names` as COPIES of whatever the
  factory seeded (empty for non-factory/test construction, so existing
  hand-built-Agent tests are unaffected); `reset()` re-extends/re-updates
  the same container objects in place, after the existing `.clear()`
  calls, preserving the closure-capture invariant the module comment
  already documented.
- `the_one/db/models.py` — `"enabled"` added to `_validate_connector_config`'s
  allowed-key set; `isinstance(value["enabled"], bool)` check mirroring
  the `default_agent` shape check (rejects `1`/`"yes"`, not just wrong
  type generically).
- `the_one/connectors/manager.py` — `start_all` gained one guard line:
  skips a row where `account.config.get("enabled", True) is False`;
  `start()` itself untouched (unit tests constructing accounts and calling
  `start()` directly keep the original unconditional behavior).
- `the_one/interfaces/web/api.py` — `create_connector`: the existing
  `manager.start(...)` call wrapped in the enabled guard. `update_connector`:
  rewritten to branch on the NEW row's effective `enabled` value ONLY
  (never on whether it changed) — `stop()` always runs, `start()` only
  when the new effective value is not `False`; this replaces the old
  unconditional stop+start and is the amended-design-review fix for the
  disabled→disabled-PUT-restarts-listener trap. `test_connector` (doctor):
  response gained a top-level `"disabled"` bool
  (`account.config.get("enabled", True) is False`); the stale
  "there is no enabled gate to check" docstring note replaced with the
  DD-6-superseding note, and the disabled+stale-failure-marker
  independence documented inline (Edge Cases).
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` —
  new `_checkbox(field, checked)` helper alongside `_select`/`_textarea`;
  one field group in the Identity section rendering
  `config.enabled !== false` (never a truthy check — the absent-key
  legacy-row trap); save path reads `.checked` directly (the generic
  `field(name)` reader returns `.value`, useless for a checkbox) and
  writes `enabled: false` only when unchecked (sparse-config pattern:
  checked/default omits the key). Top-of-file comment (the stale
  "there is no persisted enabled field" note) rewritten to describe the
  new contract.
- Tests (17 new, all through real paths per the leg's requirement — no
  hand-built containers for the carve-out pins):
  - `tests/test_factory.py` — new `builtin_factory` fixture (wires the
    REAL `BuiltinToolProvider`, not `StubToolProvider`, so the carve-out
    exercises the real `send_to_platform_channel` tool and its real
    `to_schema()`) + `TestSendToolCarveOut` (5 tests: AC-1 present/absent
    via `AgentFactory.create()`; AC-2 exact-shape baseline in both states;
    AC-3 first LLM call's `tools=` carries the schema with zero
    `search_tools` calls; AC-4 `search_tool.execute(query="")` against the
    real `SearchTools` produces no duplicate — schema-list-length AND
    name-set-length asserted in lockstep; AC-5 reset survival asserting
    `is` object-identity on both containers pre/post-`reset()`).
  - `tests/test_connector_config_validation.py` — 5 new tests (AC-6):
    absent-key validates as before, `enabled: true`/`false` accepted,
    non-bool string rejected, `1` (int, not literal bool) rejected.
  - `tests/test_connectors_manager.py` — 1 new test (AC-7):
    `start_all` against a 3-row fake repo (absent-key/`true`/`false`)
    asserts only the disabled row gets no listener.
  - `tests/test_connector_routes.py` — 6 new tests (AC-8/AC-9): create
    with `enabled: false` starts nothing; disabled→enabled PUT starts;
    enabled→disabled PUT stops-only-never-restarts; the AC-8 TRAP CASE
    (disabled→disabled PUT changing an unrelated field, using a FULL
    current-config resend body per the leg's shallow-merge warning) stays
    down; doctor marks a disabled connector `"disabled": true` while still
    running the plugin probe, and an enabled one `"disabled": false`.
  - `tests/browser/test_studio_connector_editor.py` — 2 new tests (AC-10):
    default-checked round-trip (create without touching the checkbox →
    save → back to grid → reopen → still checked, key stays absent);
    unchecked round-trip (uncheck → save → reopen → still unchecked).

**AC-11 (frozen-loop guarantee) — `git diff --stat the_one/agent/`**:

```
 the_one/agent/core.py    | 13 +++++++++++++
 the_one/agent/factory.py | 14 ++++++++++++++
 2 files changed, 27 insertions(+)
```

27 insertions, 0 deletions, across exactly the two named files — no other
lines in `the_one/agent/` touched. The `tag_post_step_visibility` pin
literals (`tests/test_connector_send_tool.py`) and `test_mcp_pool.py`'s
lifespan-order test pass unmodified (both re-run in the scoped verification
pass and again inside the full `make test-unit`).

**JS delta**: `connector-editor.js` — 27 insertions, 6 deletions (net +21,
well inside the ≤50-line flight budget); running JS total ~696 of 1,000.

**Tests**:
- Scoped (carve-out + DD-6 + adjacent pin suites):
  `tests/test_factory.py`, `tests/test_agent_visibility_filter.py`,
  `tests/test_connector_config_validation.py`,
  `tests/test_connectors_manager.py`, `tests/test_connector_routes.py`,
  `tests/test_connector_rotation_restart.py`,
  `tests/test_connector_send_tool.py`, `tests/test_mcp_pool.py`,
  `tests/test_ws_storage_edge_shim_visibility.py`,
  `tests/test_connectors_inbound.py` — all green (139 + 46 = 185 passed,
  2 deselected).
- Studio browser lane (`scripts/run-tests.sh --lane studio`, foreground,
  PYTHON=.venv/bin/python): 145 passed, 3 skipped, 2 FAILED —
  `test_flow_studio_mcp_editor.py::test_last_updated_renders_relative_time_format`
  and `test_studio_connector_editor.py::test_studio_connector_doctor_no_plugin_registered`.
  Both verified NOT caused by this leg's diff (see Deviations): the
  relative-time test passed cleanly re-run in isolation (`-m browser` on
  just that test, 1 passed) — a load-timing flake under the full 150-test
  lane, unrelated to any file this leg touches. The doctor test fails
  deterministically (re-run in isolation, `test_studio_connector_editor.py`
  alone: same failure) because leg 1's uncommitted `app.py` change
  registers the real Discord plugin in production unconditionally, so a
  "discord"-typed connector now gets a REAL doctor probe
  ("failed: no bot token configured") instead of the "no plugin
  registered" report this Flight-2-era test still asserts — a leg-1-caused
  drift in a leg-1-adjacent test, outside this leg's `enabled`-key/JS-
  checkbox scope. This leg's own 2 new checkbox tests in that same file
  pass. Neither failure touches AC-1..AC-11's own suites. Reported as a
  squawk candidate (see Deviations) — NOT fixed inline per the leg's
  out-of-scope-breakage instruction.
- `make test-unit` (foreground, 600000ms timeout): 3,728 passed, 10
  skipped, 551 deselected, 17 warnings (all pre-existing/unrelated —
  same Starlette/websockets/forkpty notices leg 1 logged), 383.01s
  (0:06:23). Leg-1 baseline was 3,711 passing; +17 matches this leg's new
  tests exactly (5 carve-out + 5 validator + 1 manager + 6 routes).

**Squawk candidate (out of this leg's charter, found during AC-12
verification, not fixed inline)**: `tests/browser/test_studio_connector_editor.py::test_studio_connector_doctor_no_plugin_registered`
now fails deterministically because leg 1's production Discord
registration (`the_one/interfaces/web/app.py`, uncommitted) supersedes the
test's "no plugin registered for discord" premise — the doctor now runs
the real plugin and reports "failed: no bot token configured" instead.
The test needs its assertion/setup updated to a still-unconfigured-but-
real-plugin scenario (or moved to assert on a type with no registered
plugin, if one still exists post-Flight-3). Should be picked up before or
at flight end, since it will still be failing when the flight's own final
`make test-browser`/studio-lane pass runs.

### Leg 3 — live-gate-and-docs (in-flight; AC-8 Flight-Director gate pending)

Landed AC-1..AC-7 (implementation + docs). AC-8 (`/behavior-test
discord-live-round-trip` against the operator's real test guild) is the
Flight Director's job per the leg's own charter — leg status stays
`in-flight` until that gate passes or a failure is dispositioned.

**Built, file-by-file**:

- `the_one/connectors/discord/_gateway.py` — `GatewayConnection.sever_for_test()`:
  `self.ws.transport.abort()` only (never `.close()` in any form — a close
  handshake always completes regardless of arguments), no
  `_self_initiated_close` flag set, no state cleanup. The existing
  `_read_loop`'s `ConnectionClosed` catch + `run()`'s `finally: self._alive
  = False` do the rest — the exact death-detection path a real network
  drop takes.
- `the_one/connectors/discord/plugin.py` — `DiscordClient.sever_for_test()`:
  one-line delegate to `self._gw.sever_for_test()`. Not added to any
  Protocol; discovered only via `getattr`.
- `the_one/interfaces/web/api.py` — new `POST /_test/discord/sever` route,
  placed adjacent to the stub seams. Dual-gated (`settings.dev_mode` AND
  `THE_ONE_DISCORD_TEST_ENDPOINT=1`, its own env name — not the stub gate).
  Raw `Request` + manual `await request.json()` (gate check runs BEFORE
  the body is parsed, so an empty-body 403 probe never risks a 422).
  Handler order: `repo.get` (the `generate_connector_pairing_code`
  idiom) → 404 on `KeyError`; `manager.client_for` → 409 on `None`;
  `getattr(client, "sever_for_test", None)` → 501 on missing hook; else
  call the hook and return `{"status": "ok"}`.
- `tests/test_seam_routes_403_sweep.py` — `("POST",
  "/api/_test/discord/sever")` added to `_EXPECTED_SEAMS`, with a dated
  comment block matching the existing DD-10 entry's style.
- `tests/test_discord_gateway.py` — 1 new test (AC-1):
  `test_sever_for_test_aborts_transport_and_next_connect_resumes` —
  client-side `conn.sever_for_test()` (not the fixture's server-side
  `close_abrupt()`) triggers the same abrupt-close path; asserts
  `is_alive()` → False and that `session_id`/`resume_gateway_url`/`last_seq`
  survive intact for the next `connect()`'s resume (payload-and-address
  asserted, mirroring the existing abrupt-close resume test's shape).
- `tests/test_discord_sever_route.py` (new file) — 6 tests (AC-2): 403
  gate-closed both ways (dev_mode off, env unset); 404 unknown connector;
  409 when `client_for` returns `None` (a disabled-at-create row, so the
  manager never starts a listener — the "never started" half of the
  mid-backoff/never-started ambiguity `client_for` can't disambiguate
  alone); 501 when the live client is stub-typed (no `sever_for_test`
  hook — the `getattr` discovery path's negative case); 200 `ok` against a
  real `DiscordPlugin` wired to the fake gateway, asserting
  `live_client.is_alive()` flips to `False` after the call.
- `tests/browser/test_studio_connector_editor.py` — the falsified
  `test_studio_connector_doctor_no_plugin_registered` RENAMED in place to
  `test_studio_connector_doctor_reports_plugin_failure_without_token`
  (blame-preserving edit, not delete-and-readd) and re-aimed: asserts the
  doctor result contains `"failed"` and `"token"` (shape, not exact
  prose) instead of `"no plugin registered"`. Per AC-5's redesign note in
  the leg spec, a stub-with-gate-closed re-aim was tried first and found
  unimplementable — stub creatability and stub plugin registration share
  the same dual gate, so with the gate closed "stub" isn't even
  selectable in the form, and with Discord unconditionally registered no
  type is both UI-creatable and plugin-less. `tests/test_connector_routes.py:341`'s
  unit-level no-plugin coverage was verified still green as-is (that test
  never runs the app lifespan, so the registry stays empty regardless of
  leg 1's production registration) — not duplicated.
- `tests/behavior/discord-live-round-trip.md` — finalized: `Status: active`;
  draft caveats removed; exact env-var contract named (see the summary's
  "Env-var contract" below); step 6's mechanism is now the sever route
  with its literal request/response shape; the no-tool-discipline-nudge
  proof language kept verbatim per the leg's instruction.
- `tests/behavior/.env.hat.example` (new) — driver-bot env template
  (`THE_ONE_HAT_DRIVER_TOKEN`/`_GUILD_ID`/`_TEST_CHANNEL_ID`/
  `_ALWAYS_LISTEN_CHANNEL_ID`/`_UNTRACKED_CHANNEL_ID`), carrying forward
  the pre-reset `discord_hat` README's provisioning notes (real-browser
  bot creation, driver bot doesn't need Message Content intent, main bot
  does) adapted to DD-7's single-driver-bot simplification.
- `.gitignore` — the dead `tests/live/discord_hat/.env.hat` line pruned
  (that directory no longer exists); the unscoped `*.env.hat` pattern
  (which already covers the new example's real counterpart) kept and its
  comment updated to point at the new example file's location.
- `the_one/connectors/README.md` — new "Discord (Flight 3)" section
  (protocol scope incl. no-sharding/no-compression, close-code policy +
  the accepted one-cycle mid-session-permanent-close latency, resume
  behavior, rate-limiter shape, `secrets["token"]`, per-account state);
  intro paragraph updated off the stale "no production plugin ships yet"
  framing; `enabled`/DD-6 documented under Config schema; Test seams
  section gained the sever route's contract; the stale "no persisted
  `enabled` field" Known-limitations entry removed (DD-6 landed in leg 2);
  the still-true "no in-band connector_id/peer_id discovery" limitation
  left as-is.
- `the_one/agents.md` — Connector subsystem contract's module map updated
  off the "no production plugin ships yet" framing to name `discord/` and
  its unconditional registration; a new DD-5 carve-out paragraph
  (mechanism summary + pointer to `core.py`/`factory.py`, not duplicating
  the code comments); a new `risk-tiered-test-seam-gating` precedent
  bullet for `THE_ONE_DISCORD_TEST_ENDPOINT` explaining why it's a
  separate gate name from the stub seam's.
- `CLAUDE.md` — new "Discord test endpoint + live HAT env conventions"
  subsection: the sever route's gate, and the HAT driver-bot env-var
  contract with a pointer to `.env.hat.example`.

**Operator-identity leak sweep**: grepped every touched doc/code file for
`/home/`, the operator's machine username, and the mission-control repo
owner's GitHub handle — none introduced by this leg (one pre-existing,
unrelated `github.com/msieurthenardier/mission-control` link in
`CLAUDE.md`'s "Flight Operations" pointer, not touched).

**Budget**: `wc -l the_one/connectors/discord/*.py` → `__init__.py` 24 +
`_gateway.py` 295 (+18 for the sever hook) + `_rest.py` 146 + `plugin.py`
274 (+7 for the delegate) = **739 total**, within the ≤1,100 flight
budget (leg-2 baseline was 712; this leg added 27 lines). No new deps
(`git diff --stat pyproject.toml uv.lock` empty). JS delta from this leg:
0 (confirmed — the only uncommitted JS diff in the tree is leg 2's
enabled-checkbox work, untouched here).

**Tests** (all foreground, explicit tool timeouts, `uv sync --extra
all-llms --extra dev --extra gui` run first to restore the full dev
environment after an earlier scoped `--extra dev`-only sync had dropped
the `anthropic`/`openai`/gui extras):
- Scoped, run together as `tests/test_discord_gateway.py
  tests/test_discord_sever_route.py tests/test_seam_routes_403_sweep.py
  tests/test_discord_plugin.py` (38 tests): a first combined run
  surfaced 2 REAL races in this leg's own new tests (not flakes, not
  pre-existing) — `test_sever_for_test_aborts_transport_and_next_connect_resumes`
  asserted `last_seq == 42` right after `ready_future` resolves, but
  `ready_future` only guarantees the READY dispatch (seq=1) was
  processed; the `MESSAGE_REACTION_ADD` (seq=42) sent immediately after
  is a separate frame the read loop may not have consumed yet — fixed
  by polling `state.last_seq == 42` before calling `sever_for_test()`
  instead of asserting immediately. `test_sever_ok_on_live_discord_connector`
  (and `test_sever_501_when_client_has_no_hook`) used a fixed
  `await asyncio.sleep(0.05)` after `POST /api/connectors` before
  reading `mgr.client_for(...)` — not reliably long enough for a REAL
  websocket handshake (identify → READY) to complete under scheduler
  load, unlike the stub plugin's synchronous connect the rest of the
  test suite's `sleep(0.05)` convention was tuned against — fixed with
  a poll-until-non-None helper (`_wait_for_client`, 5s ceiling) in both
  tests, and a poll-until-`is_alive()-is-False` loop replacing the
  post-sever sleep. Re-run 4x after the fix: 38 passed every time
  (previously reproduced the failure in 3 of 4 combined runs, 0 of 3
  when `test_discord_sever_route.py` ran alone — confirming it was
  file-ordering/load-dependent, not present in isolation).
- `make test-unit` (foreground, 600000ms timeout), re-run after the
  fix above: **3,736 passed, 10 skipped, 551 deselected, 17 warnings**,
  390.03s (0:06:30). Zero failures, identical count across both the
  pre-fix and post-fix full-suite runs (the race never manifested inside
  the full suite's file ordering — only in the smaller combined-file
  run above — but the fix is in regardless, since the failure mode is
  real and load-dependent). Leg-2's logged baseline was 3,728 passing;
  this leg adds 7 new unit tests (1 gateway sever test + 6 sever-route
  tests — the renamed browser test doesn't affect the unit count); the
  observed +8 vs. expected +7 delta against the logged baseline remains
  a minor unresolved discrepancy, flagged for the flight-end reviewer
  rather than assumed benign (zero failures in either run).
- Studio browser lane (`PYTHON=.venv/bin/python bash
  scripts/run-tests.sh --lane studio`, foreground), run twice: first
  pass 146 passed, 3 skipped, 1 FAILED
  (`test_flow_studio_navigation.py::test_studio_section_nav_renders_four_buttons`,
  a page-mount-timing assertion unrelated to any file this leg touches).
  Isolated re-run (`-m browser` on just that test): 1 passed. Full-lane
  re-run: **147 passed, 3 skipped, 0 failed** — confirms that failure
  was a transient timing flake, not a regression (same disposition as
  the scoped races above: verified via re-run rather than assumed).
  The renamed doctor test
  (`test_studio_connector_doctor_reports_plugin_failure_without_token`)
  passed in every lane run, closing leg 2's squawk candidate.

**Env-var contract the operator must fill before AC-8** (in
`tests/behavior/.env.hat.example`, copy to `tests/behavior/.env.hat`):
`THE_ONE_HAT_DRIVER_TOKEN`, `THE_ONE_HAT_GUILD_ID`,
`THE_ONE_HAT_TEST_CHANNEL_ID`, `THE_ONE_HAT_ALWAYS_LISTEN_CHANNEL_ID`,
`THE_ONE_HAT_UNTRACKED_CHANNEL_ID`. Plus the dev-instance boot command
(`THE_ONE_PORT=8485 THE_ONE_DATA_DIR=/tmp/the-one-behavior-test-scratch
THE_ONE_DEV_MODE=true THE_ONE_DISCORD_TEST_ENDPOINT=1 make up`), a MAIN
bot connector row created in Studio with `default_agent: test-agent`,
`always_listen` naming `THE_ONE_HAT_ALWAYS_LISTEN_CHANNEL_ID`, and the
driver bot's Discord user id on `allowlist.peers`.

---

## Decisions
*(runtime decisions recorded here during execution)*

---

## Deviations

**Leg 2**: No deviation from the leg-2 spec's own scope. One out-of-scope
discovery during AC-12 verification: the full `--lane studio` browser run
surfaced `test_studio_connector_editor.py::test_studio_connector_doctor_no_plugin_registered`
failing deterministically — caused by leg 1's uncommitted production
Discord registration (`app.py`) making a "discord"-typed connector's
doctor probe hit the REAL plugin instead of the "no plugin registered"
path that Flight-2-era test still asserts. Not fixed inline (outside this
leg's `enabled`-key/carve-out charter); logged as a squawk candidate above
and reported to the flight-end reviewer. A second lane failure
(`test_flow_studio_mcp_editor.py::test_last_updated_renders_relative_time_format`)
was a load-timing flake, confirmed by an isolated re-run (1 passed) —
unrelated to any file this leg or leg 1 touched, not logged as a squawk.

**Leg 3**: No deviation from the leg-3 spec's own scope; the leg's own
AC-5 already documents a redesign-during-review (stub-with-gate-closed
re-aim was tried first and found unimplementable, superseded by the
tokenless-discord re-aim actually shipped) — not a deviation discovered
during THIS leg's execution, carried in the leg spec itself. One
transient studio-lane failure
(`test_flow_studio_navigation.py::test_studio_section_nav_renders_four_buttons`)
confirmed a flake by isolated re-run and a clean full-lane re-run — not
logged as a squawk, same disposition as leg 2's analogous flake. Leg 2's
squawk candidate (the falsified doctor test) is CLOSED by this leg's
AC-5 rename — no longer an open item for the flight-end reviewer.
Separately (not a deviation from scope, but worth recording alongside
it): this leg's OWN new tests initially carried 2 real races — see
Anomalies below — caught and fixed before handoff, not left as flagged
flakes.

---

## Anomalies

**Leg 2**: `bash scripts/run-tests.sh --lane studio` run without an
explicit `PYTHON=.venv/bin/python` falls back to the system `python3`
(`${PYTHON:-python3}` in the script), which resolves a stale `mcp` package
(1.18.0, missing `mcp.client.auth.exceptions`) and fails collection at
`tests/conftest.py` import time. Always set `PYTHON=.venv/bin/python`
explicitly for this project's scoped/lane test invocations — `make test-*`
targets already do this internally, but a bare `scripts/run-tests.sh` call
does not.

**Leg 3**: `uv sync --extra dev` (in isolation, without `--extra
all-llms`) UNINSTALLS `anthropic`/`openai` and the gui extras from the
venv if they were only present via a broader prior sync — `make
test-unit` then fails collection on 14 files with `ModuleNotFoundError:
No module named 'anthropic'/'openai'`. Re-synced with `uv sync --extra
all-llms --extra dev --extra gui` (matching this project's `pip install
-e ".[all-llms,dev]"` convention plus the gui extra the venv already
carried) before re-running the suite; no further recurrence. Worth a
CLAUDE.md correction in a future leg/squawk — the "uv sync always with
--extra dev" instruction as literally stated narrows an already-broader
venv. A second minor anomaly: `make test-unit` reported 3,736 passing
against a leg-2-logged baseline of 3,728 plus this leg's 7 new tests
(expected 3,735) — a one-test discrepancy, zero failures either way, not
tracked down further (see Tests, above).

**Leg 3 (own-test races, fixed before handoff)**: running
`tests/test_discord_gateway.py` + `tests/test_discord_sever_route.py` +
`tests/test_seam_routes_403_sweep.py` + `tests/test_discord_plugin.py`
together (not each file alone) reproduced 2 real timing races in this
leg's own new tests in 3 of 4 attempts: (1) the gateway sever test
asserted `state.last_seq == 42` immediately after `ready_future`
resolved, but that future only guarantees the READY dispatch (seq=1)
was processed — the very next `MESSAGE_REACTION_ADD` (seq=42) frame the
handler sends can still be in flight; (2) the route-level "live discord
connector" and "stub, no hook" tests used a fixed `await
asyncio.sleep(0.05)` after `POST /api/connectors` before reading
`mgr.client_for(...)`, copying the stub-plugin convention used
throughout `tests/test_connector_routes.py` — but a REAL
`DiscordPlugin` connect does an actual websocket handshake (identify →
READY) across several await points, which 0.05s is not reliably long
enough for under scheduler load from other concurrently-running test
files, unlike the stub plugin's synchronous in-process connect that
convention was tuned against. Both fixed with explicit polling (loop on
the actual condition with a generous ceiling — `state.last_seq == 42`
before severing; a new `_wait_for_client` helper polling
`client_for(...) is not None` up to 5s; a poll-until-`is_alive()-is-False`
loop replacing the post-sever fixed sleep) rather than a longer guessed
sleep. Re-verified stable across 4 consecutive combined runs post-fix.
**Convention note for future legs**: `await asyncio.sleep(0.05)` after a
connector-create call is safe ONLY for the stub plugin's synchronous
connect; a plugin that does real network I/O (Discord, and any future
platform) needs a poll loop, not a borrowed fixed-sleep duration from a
different plugin's timing profile.
