# Flight: Discord Client

**Status**: planning
**Mission**: [Connector Reset](../../mission.md)

## Contributing to Criteria
- [ ] A Discord peer who DMs or @mentions the bot receives the attached agent's reply in the same channel, thread, or DM; the agent can send an unprompted message via the single send tool; the bot resumes automatically after a gateway disconnect — observed live against a real Discord bot
- [ ] `discord.py`/`aiohttp` stay absent — the client is built on the `websockets` + `httpx` already in base dependencies (no new deps)
- [ ] *(running count)* Connector Python within 3,000 (1,060 used; this flight targets ≤1,100 for the Discord client incl. plugin/translate); connector JS within 1,000 (~675 used; this flight targets ≤50 — the generic form already covers Discord)
- [ ] A new live HAT exists for Discord (mission criterion 10's second half; the `discord_hat` replacement)
- [ ] *(mission-amendment)* The send tool is baseline-visible when enabled — the Flight 2 reliability gap closed mechanically (mission Resolved Question 8)

---

## Pre-Flight

### Objective

Implement Discord as the first real platform behind the Flight 2 contract: a hand-rolled Gateway v10 client (hello → heartbeat with jitter → identify with intents → dispatch; resume to `resume_gateway_url`; reconnect with backoff via the manager's existing loop; non-reconnectable close codes honored) and a bot-only REST client on `httpx` (per-bucket + global rate limiting, 429 retry-after, the ~10 endpoints a text bot needs), translating `MESSAGE_CREATE` into the contract's envelope (`is_dm`, `mentions_bot`, self/bot-authored ignored). Restore the mission-amended minimal visibility carve-out for the send tool, add `enabled` as a config key (pause-without-delete, no migration), and prove it all live: a second-bot-driven behavior test in the test guild plus a guided HAT covering the DM/pairing paths only a human account can exercise.

### Open Questions
- [x] Send-tool discoverability → mission Resolved Question 8 (owner-amended constraint; DD-5)
- [x] `enabled` without a migration → mission Resolved Question 9 (config key; DD-6)
- [x] Live verification shape → behavior test + guided HAT leg (operator decision, 2026-09-01)
- [x] Peer driver → second-bot `.env.hat` conventions stand (operator confirmed)

### Design Decisions

**DD-1 — Discord lands as a small subpackage**: `the_one/connectors/discord/` (suggested split: `_gateway.py`, `_rest.py`, `plugin.py` housing the Protocol implementation + translate; exact file boundaries are the implementer's within the budget). Registration site: the production registry (unconditional — Discord is a real platform, unlike the gated stub). Nothing outside the subpackage and its registration line (the mission's additive-seam criterion, exercised here ahead of Telegram proving it).
- Rationale: gateway/REST/plugin have distinct testing shapes; one file each keeps the fake-gateway tests aimed at `_gateway` alone.
- Trade-off: none; the package namespace can't collide with the removed `discord.py` lib (gone from the closure).

**DD-2 — Gateway v10, minimal opcode coverage**: hello (op 10) → heartbeat loop with `jitter*interval` first beat, heartbeat-ACK (op 11) watchdog (missed ACK ⇒ close+reconnect); identify (op 2) with intents `GUILDS | GUILD_MESSAGES | DIRECT_MESSAGES | MESSAGE_CONTENT`; dispatch (op 0) handling READY (capture `session_id` + `resume_gateway_url`) and MESSAGE_CREATE; resume (op 6) on reconnectable disconnects, falling back to fresh identify when resume is rejected (op 9 invalid-session). Close-code policy: 4004 and 4010–4014 raise a NEW typed `PermanentConnectorFailure` (defined in `connectors/base.py` — contract-level, so Telegram inherits it); `manager._run` gains a narrow catch that stops retrying and logs — catch-and-stop ONLY (second-pass review: the manager has no path to doctor). The FAILURE MARKER lives in the plugin's account-id-keyed state dict, set where the close code is detected, so `plugin.doctor()` can short-circuit to a "permanently failed: <reason>" report. **Lifecycle rule**: `connect()` clears the marker unconditionally at the top of every fresh attempt — the only reset point, since a failed listener's `_run` has exited and only a manager-driven restart (PUT/boot) re-enters `connect()`; the PUT stop/start thus recovers a fixed token with no extra wiring. Implementation note: `_connect_once`'s blanket `except Exception` needs an explicit `except PermanentConnectorFailure: raise` carve-out or the new exception never reaches `_run`'s catch. Make `PermanentConnectorFailure` a subclass of `ConnectorClientError` so existing doctor/route handlers catch it naturally. Anything else → the manager's existing backoff + fresh-row re-fetch loop, unchanged. **Per-account gateway state is explicit** (design review Q1): `registry` plugins are type-keyed singletons, so the Discord plugin holds `session_id`/`resume_gateway_url`/live-connection state in an account-id-keyed dict — the shape the stub already established with `_live`.
- Rationale: the protocol surface a text bot needs; retry ownership stays with the manager, now with an honest permanent-failure channel instead of retry-forever on a bad token.
- Trade-off: one small named manager/base change beyond the subpackage (DD-1's nothing-outside framing amended for it — it's contract evolution, and Flight 4's additive criterion is measured for Telegram); no zlib compression, no sharding — noted in the README.

**DD-3 — REST client: httpx, per-bucket + global rate limiting**: an `AsyncClient` against `https://discord.com/api/v10`, honoring `X-RateLimit-Bucket/Remaining/Reset-After` per route-bucket, the global limit, and 429 `retry_after` (bounded retries). Endpoints (~10): Get Gateway Bot, Get Current User, Create Message, Create DM (user→DM channel), Get Channel, Get Channel Messages (powers the Protocol's `history`), Trigger Typing (optional nicety), Get Guild Channels (doctor detail). No webhooks, no interactions/slash surface.
- Rationale: mission scope verbatim; the rate limiter is the part that must be right (the 2026-08-27 research brief's "honest 700–1,100 lines" is mostly here + gateway).
- Trade-off: no request queuing beyond per-bucket serialization; a personal bot's volume doesn't need it.

**DD-4 — Envelope translation policy**: MESSAGE_CREATE → `InboundEnvelope` with `is_dm` from the channel type (DM channels resolved via Create-DM/READY cache or channel fetch), `mentions_bot` from the mentions array containing the bot's user id, `peer_name` from author global/display name; messages authored by the bot itself or any other bot are dropped before the pipeline (loop prevention); thread messages carry `thread_id` per the kept session keying.
- Rationale: explicit envelope flags are the contract (Flight 2 DD-1); bot-authored drops are the standard echo-loop guard.
- Trade-off: webhook-authored messages are treated as bots (dropped) — fine for scope.

**DD-5 — The mission-amended visibility carve-out (agent loop, narrow)**: implemented by SEEDING `_loaded_schemas`/`_loaded_tool_names` with the send tool when enabled — the factory (which knows "enabled") passes pre-seeded containers to `Agent.__init__`, AND `__init__` captures the seed on new instance state (e.g. `self._carveout_schema`/`_carveout_tool_name`) so `reset()` — which today unconditionally `.clear()`s both containers with no memory of the seed (second-pass review, `core.py:646-647`) — can re-seed from it — NOT by appending inside `_compute_visible_schemas` (design review 2026-09-01: a naive per-call append bypasses `_on_search_match`'s dedup and a later `search_tools` hit would send the model two copies of the schema). Reuses the existing dedup mechanism for free; nothing else in the loop changes. The Flight 2 pin test (`tag_post_step_visibility` literals) and `test_mcp_pool` lifespan-order test are unaffected; new unit tests pin: (a) carve-out present when enabled, absent when disabled; (b) the rest of the baseline unchanged; (c) a live-shaped test that the tool schema reaches the model-visible set without a `search_tools` call; (d) a `search_tools` query matching the carved-out tool does NOT duplicate its schema in the visible set; (e) after `Agent.reset()`, the carve-out reappears when enabled and stays absent when disabled (the surviving-a-reset guarantee). The behavior spec's tool-use nudge is then REMOVED from `test-agent`'s precondition (the mechanical fallback replaces it — that's the proof).
- Rationale: mission Resolved Question 8; the constraint's own condition failed empirically.
- Trade-off: one deliberate, owner-approved touch to the frozen loop; scoped to a single baseline entry and pinned by tests.

**DD-6 — `enabled` as a DD-2 config key**: default `true`. DD-to-AC traceability applied — the four touch points are EACH a named leg-2 acceptance criterion, not prose: (1) validator accepts the key (`db/models.py` `_validate_connector_config`); (2) `manager.start_all` skips disabled; (3) PUT transitions at `api.py:update_connector` (enable → start, disable → stop, else restart-as-today) and create honors it; (4) doctor (`api.py:test_connector`) reports "disabled" as a distinct state; plus (5) the Studio form checkbox. No migration — absent key reads enabled.
- Rationale: mission Resolved Question 9.
- Trade-off: none; absent-key default keeps old rows valid.

**DD-7 — Live verification split by what each apparatus CAN do** (behavior-test apparatus audited both axes):
- **Behavior test `discord-live-round-trip`** (autonomous gate): the second **driver bot** (ADAPTED from the old `.env.hat` conventions — recoverable via `git show 138025e^:tests/live/discord_hat/README.md`; the old shape was N sender bots, this flight simplifies to one `THE_ONE_HAT_DRIVER_TOKEN`; guild/channel ids) ACTS — posts an @mention in the test channel, posts in the always-listen channel, and reads back the main bot's replies via REST (its own observe path); the app side observes via `GET /api/chat/sessions` + the Chat UI (browser apparatus) for session keying/visibility, as proven in Flight 2. Covers: @mention reply, always-listen reply, silence-in-untracked-channel, agent-initiated channel send, resume-after-disconnect (driver asks the operator-side seamlessly? no — resume is verified by killing the gateway connection server-side via a doctor-adjacent test control or by observing reconnect logs; see the spec draft's step notes).
- **Guided HAT leg** (interactive): what bots cannot do — DM the bot from your human account, pair via the code, watch the private console, daily-driver feel; inline fixes per the HAT protocol.
- Rationale: bots cannot DM bots — the DM/pairing criterion half needs a human; everything channel-shaped automates.
- Trade-off: the controlled-disconnect mechanism (second-pass review, settled shape): an OPTIONAL `ConnectorClient` sever hook discovered via `getattr(client, "sever_for_test", None)` — the same optional-hook pattern DD-8's `history` uses, keeping the Protocol surface clean and the seam platform-agnostic for Telegram — reached through `manager.client_for(connector_id)` from a dual-gated `/_test/` route in `api.py` (dev_mode AND `THE_ONE_DISCORD_TEST_ENDPOINT=1`, named now per the agents.md risk-tiering convention). This is a second, named out-of-subpackage touch beyond DD-2's — recorded here, not discovered mid-leg. It severs the websocket without a close handshake; never a production kill switch.

**DD-8 — Fake-gateway fixture at the shared tests root** (mission Resolved Question 7): `tests/_discord_gateway_fixture.py` — a `websockets.serve` double scripting hello/heartbeat/identify/resume/dispatch/close-code scenarios for `_gateway.py`'s unit tests; no real network in unit tests, ever.

**DD-9 — Budgets**: Discord Python ≤1,100 (subpackage total); JS ≤50 (the enabled checkbox + any Discord-specific form hint — the generic editor already handles token/agent/allowlists). Mid-leg count checks per DD-11 discipline (Flight 2's).

### Prerequisites
- [ ] **PR #186 (squawk turnaround) merged** — the flight branch cuts from a main that includes the Tools-tab category and mask changes
- [ ] Discord application + MAIN bot token, Message Content intent enabled, bot in the operator's test guild
- [ ] DRIVER bot token (second bot) in the same guild, per old `.env.hat` conventions; test channel + always-listen channel ids known
- [ ] Network egress to `discord.com` / `gateway.discord.gg`
- [ ] Dev instance conventions from Flight 2 (port 8485, scratch data dir; never 8484) for the behavior test; the operator's real instance only for the guided HAT
- [ ] A model for the live agent that reports `supports_tools()=True` (design review: the degraded non-tool path sends `tools=None` and bypasses the carve-out entirely); with DD-5 the search-indirection caveat no longer applies to the send tool

### Pre-Flight Checklist
- [x] All open questions resolved (two mission-level resolutions recorded: RQ8 carve-out, RQ9 enabled key)
- [x] Design decisions documented (9 DDs)
- [ ] Prerequisites verified (operator supplies tokens/ids before leg 3's gate; PR #186 merge before branch cut)
- [x] Validation approach defined (unit + fake-gateway; behavior gate; guided HAT)
- [x] Legs defined (4: discord-client, loop-carveout-and-enabled, live-gate-and-docs, hat-alignment)

---

## In-Flight

### Technical Approach

Build the client against the fake gateway first (leg 1 fully unit-tested, no live traffic), touch the loop and lifecycle in a small isolated leg (leg 2 — the two highest-risk changes get their own checkpoint), then go live (leg 3: author + run the behavior test with the driver bot, rewrite docs), and close with the operator in the loop (leg 4 HAT). The Flight 2 discipline carries: recon content-grep step zero per leg, DD-to-AC traceability (every operator-visible affordance in these DDs has a named criterion — the enabled checkbox, the doctor disabled state, the carve-out's visible schema), budgets checked mid-leg, foreground-only test runs.

### Checkpoints
- [ ] Leg 1 lands: gateway+REST+plugin complete against the fake gateway; unit suite green; Discord Python count reported
- [ ] Leg 2 lands: carve-out + enabled key in, all pin tests green; suite green
- [ ] Leg 3 lands: `discord-live-round-trip` PASSES against the real test guild; docs updated
- [ ] Leg 4 lands: guided HAT complete, operator satisfied; flight metrics recorded

### Adaptation Criteria

**Divert if**:
- The Discord client approaches 1,100 lines before resume/rate-limit correctness is complete — stop-and-split per the mission ceiling discipline, never trim correctness
- The carve-out can't be expressed without touching more of the loop than the baseline entry — stop; that's a second mission-owner conversation, not an FD call
- Live gateway behavior contradicts the fake-gateway model (protocol drift) — pause leg 3, update the fixture first so unit truth stays authoritative

**Acceptable variations**:
- File boundaries within the subpackage; endpoint list ±2 within scope
- Behavior-test checkpoint order/count as the spec finalizes against the real guild

### Legs

> **Note:** Tentative; planned one at a time as the flight progresses.

- [ ] `discord-client` - Gateway v10 + REST + translate + plugin + production registration + fake-gateway fixture (`tests/_discord_gateway_fixture.py`) + unit tests (heartbeat/jitter/ACK-watchdog, identify/resume/invalid-session, close-code policy, per-bucket + global rate limiting, 429, translation incl. is_dm/mentions_bot/bot-drop/thread_id)
- [ ] `loop-carveout-and-enabled` - DD-5 carve-out (agent loop, narrow, pin-tested) + DD-6 enabled key (validator/manager/PUT/doctor/form checkbox) — the two hard-to-reverse changes isolated with their own checkpoint
- [ ] `live-gate-and-docs` - Finalize + run `discord-live-round-trip` (driver-bot apparatus); `connectors/README.md` Discord section, `agents.md`, CLAUDE.md env conventions; metrics
- [ ] `hat-alignment` *(interactive)* - Guided HAT: human-account DM + pairing, private console, daily-driver alignment; inline fixes per the HAT fix-vs-feature gate

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
- `make test-unit` + all four browser lanes green; no new deps in `uv.lock`.
- `/behavior-test discord-live-round-trip` PASS; run log committed.
- Carve-out pin tests green; the behavior spec's `test-agent` nudge REMOVED and the test still passes (the mechanical-fallback proof).
- Counts: Discord Python vs 1,100 / mission 3,000 running total; JS delta vs ~50 / 1,000.
- Guided HAT sign-off from the operator (leg 4).
