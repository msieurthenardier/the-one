# Flight: Telegram and the Name Directory

**Status**: landed
**Mission**: [Connector Reset](../../mission.md)

## Contributing to Criteria
- [x] A Telegram peer gets the same round-trip through the same contract; every shared-code touch is named, minimal, and platform-agnostic in its DD (the reworded additive-seam criterion, 2026-09-02)
- [x] Name-directory send targeting (mission criterion added 2026-09-02): observed-name directory, separate lookup tool, ambiguity surfaced, multi-connector
- [x] A new live HAT exists for Telegram (mission criterion 10's Telegram half)
- [x] *(running count)* Connector Python within 3,000 (1,782 used; this flight targets ≤700 total: Telegram subpackage ≤350, directory/tool/migration/refactor ≤350); JS within 1,000 (~720 used; target ≤30 — the generic form should cover Telegram)

---

## Pre-Flight

### Objective

Land Telegram as the second real platform through the Flight 2 contract — a long-poll client on the `httpx` already in base dependencies (getUpdates/sendMessage against the Bot API, translate to the contract envelope, manager-owned reconnect) — and prove the architecture is genuinely multi-connector by shipping the name directory: a passively-populated table of observed names (display name + username + platform id, because bare friendly names collide), a separate read-only lookup tool the agent chains with the existing send tool, both baseline-visible via the generalized DD-5 carve-out, gated by a stub behavior test before the live HAT. One narrowly-authorized migration step (v39, mission RQ10) carries the connector-type CHECK change and the directory table together. Ride-alongs: the `keying_to_target` extraction (Flight 3 debrief debt), directory-named channel-session titles, and the per-connector setup help file.

### Open Questions
- [x] `'telegram'` needs a CHECK-change migration but v38 is spent → mission RQ10: v39 authorized narrowly (type CHECK + directory table, one step)
- [x] Additive-seam criterion wording → reworded by the mission owner per the Flight 3 debrief (named/minimal/platform-agnostic shared touches)
- [x] Directory schema breadth → operator: id + display name + username (nullable) — names collide, usernames disambiguate
- [x] Resolution surface → operator: separate lookup tool, NOT a send-tool name form
- [x] Two-call chain gating → stub behavior test before the HAT
- [x] Lookup-tool visibility → seeded via the generalized carve-out, same as the send tool
- [x] Session-title ride-along → included, own DD and criterion

### Design Decisions

**DD-1 — Telegram lands as a small subpackage**: `the_one/connectors/telegram/` (suggested split: `_api.py` for the Bot API client, `plugin.py` for the Protocol implementation + translate; boundaries are the implementer's within budget). Production registration alongside Discord in the app lifespan (same block pattern). Shared-code touches this flight makes are enumerated here per the reworded seam criterion: (a) v39 migration in `db/schema.py` (DD-3); (b) `Connector.type` Literal + `_CONNECTOR_TYPES` + module assert + `_creatable_connector_types()` gain `'telegram'` (lockstep set, DD-3); (c) the `keying_to_target` extraction (DD-8); (d) directory population hooks in `inbound.py` and the lookup tool in `tools/` (DD-4/DD-5 — new platform-agnostic capability, not Telegram-specific); (e) carve-out seed list in `agent/factory.py` (DD-6, a two-name iteration inside the already-sanctioned seed block); (f) the stub test seam `stub_test_inbound` (`api.py`) gains passthrough of the optional `peer_username` envelope field (design review: a third `InboundEnvelope` construction site — the behavior gate's step 1 depends on it); (g) the connector delete route gains one deterministic `connector_directory` DELETE. Each is named, minimal, platform-agnostic. NOTHING else outside the subpackage.
- Rationale: mission scope; the enumeration IS the criterion's evidence.
- Trade-off: none new; the seam criterion's honesty was the Flight 3 lesson.

**DD-2 — Long-poll client design**: one `getUpdates` loop per account (`timeout=50`, `allowed_updates=["message"]`), offset tracked in-memory and advanced only after dispatch of a batch (Telegram's offset-acknowledge semantics mean an unacked batch redelivers after restart — at-least-once, dedupe not attempted at personal scale, noted). `getMe` at `connect()` captures bot identity (id + @username) into the account-keyed state (the `_AccountState` shape from Discord). `is_alive()` = the poll task lives and the last successful poll is within `2*timeout+grace`. Error policy: 401/404 (bad token) and 409 Conflict (another consumer holds getUpdates — a config error that retrying cannot fix) raise `PermanentConnectorFailure` (REUSED from Flight 3 — contract-level, zero new shared code); everything else lets the loop die and the manager's existing backoff reconnect own retry. "Reconnect" for long-poll is simply a fresh loop from the persisted-in-memory offset — there is no gateway-resume analog, and none is pretended (Flight 3 debrief's explicit design input). Translation: `chat.type == "private"` → `is_dm`; `mentions_bot` from `entities` of type `mention` matching `@botusername` (or `text_mention` matching bot id); `peer_name` from `first_name [+ last_name]`, username captured for the directory; channel/group targets keyed by `str(chat.id)`; bot-authored (`from.is_bot`) messages dropped UNLESS on `allowlist.peers` (parity with Flight 3's DD-4, as amended — NOT this flight's DD-4); `/new` arrives as plain text and hits the existing command path. Outbound `sendMessage` with plain text (no parse_mode — no entity-escaping surface, noted).
- Rationale: the smallest honest Bot API surface; retry stays with the manager; permanent-failure semantics inherited, proving the Flight 3 contract evolution earned its place.
- Trade-off: at-least-once redelivery after an unclean restart (acceptable, documented); no webhooks (long-poll only, per mission); no media handling (text bot).

**DD-3 — v39 migration (mission RQ10), one step, two payloads**: (a) `connectors.type` CHECK gains `'telegram'` via the established table-rewrite ceremony (the frozen v19 block's own documented successor path — a NEW constraint, never editing history); (b) `connector_directory` table (DD-4 schema). Lockstep code set updated in the same leg: model Literal, `_CONNECTOR_TYPES`, the import-time assert, `_creatable_connector_types()`. Migration created AND executed against a live scratch database in the same leg (leg-design risk rule).
- Rationale: RQ10's exact scope; bundling the table into the authorized step is why the step was authorized "narrowly" rather than "CHECK-only."
- Trade-off: the mission's migration budget is now definitively closed at v39 — any further schema need is a new mission conversation.

**DD-4 — `connector_directory` schema and passive population**: columns `connector_id TEXT`, `kind TEXT CHECK (kind IN ('peer','channel'))`, `platform_id TEXT`, `thread_id TEXT NULL` (design review 2026-09-02: added NOW while v39 already touches this table — a thread-scoped entry can be name-addressed with thread precision instead of silently landing on the parent channel; NULL for peers and plain channels), `display_name TEXT`, `username TEXT NULL`, `last_seen TEXT`, `PRIMARY KEY (connector_id, kind, platform_id)` — `platform_id` is always the send-addressable channel/peer id, with `thread_id` carried alongside exactly as `ChannelTarget` expects it, so copy-the-ids stays literal for thread entries too; no FK to `connectors` (a deleted connector's rows are removed by one deterministic DELETE wired into the existing connector delete route — named shared touch, DD-1g). Plaintext (names are the same sensitivity class as the plaintext chat history; no secrets). Populated passively via upsert-on-observation: (a) peers — in `dispatch_inbound` **immediately after `is_admitted` passes and BEFORE the `/new` and `should_reply` early returns** (design review 2026-09-02: "every admitted envelope" means every admitted envelope — a peer who says `/new`, or speaks in a channel the reply policy ignores, is still observed), from the envelope's `peer_id`/`peer_name` plus a platform-supplied username when the envelope carries one (envelope gains an OPTIONAL `peer_username: str | None = None` field — a named contract touch: additive, defaulted, platform-agnostic; Discord fills it from `author.username`, Telegram from `from.username`, stub optionally); (b) channels — plugin-side, where each platform already learns channel metadata (Discord: the existing Get Channel resolution captures `name`; Telegram: every group message carries `chat.title`) — reported through a small `on_directory` observation callback delivered alongside `on_inbound` OR direct repository upserts from the plugin (implementer's choice within the contract; design review to vet). **Channel entries are DELIBERATELY NOT admission-gated** (cycle-2 design decision, made at flight level not deferred): plugin-side channel observation records any channel the bot can see, allowlisted or not — a stated asymmetry with the peer path, because channel names are operator-domain metadata (the operator invited the bot into the guild/group; rooms are not people, so no third-party-silence concern) and the bound agent is ALREADY authorized to send to any channel of its connector (Flight 2's bound-agent rule), so naming visible channels grants zero new reach. Peer entries remain strictly admission-gated. Upsert-on-change only (skip the write when name+username are unchanged) to avoid a DB write per message.
- Rationale: the operator's framing verbatim — persist names the system already observes; display name + username because names collide.
- Trade-off: the directory only knows conversations the system has seen (no proactive roster sync — deliberately not a guild-member crawl); unadmitted peers are never recorded (admission gate runs first — no directory entry for dropped traffic, preserving the silence guarantee).

**DD-5 — The lookup tool** (suggested name `find_platform_destination`; implementer may refine, behavior spec pins the final name): read-only; input `query: str` (+ optional `connector_id` filter — the tool's DESCRIPTION instructs the model to omit it unless an id came from a prior result, since operators name connectors by phrase and a guessed filter yields false zero-matches; design review 2026-09-02); case-insensitive substring match over `display_name` and `username`; returns bounded candidates (≤10, newest `last_seen` first) each carrying `connector_id`, connector `name`, `kind`, `display_name`, `username`, `last_seen`, and — **keyed literally as the send tool's target expects** (design review HIGH fix: copy-the-ids must be literal, no model-performed rename at the gpt-oss floor) — `peer_id` for peer-kind candidates or `channel_id` (+ nullable `thread_id`) for channel-kind ones, never a generic `platform_id`. Zero matches → a clear "no directory entry matches" message naming the query. **Authorization**: scoped to connectors whose bound agent is the caller (the send tool's bound-agent rule applied to reads — an agent cannot enumerate another agent's platform contacts). The two-call chain (lookup → send with explicit ids) is the operator-chosen shape; ambiguity is surfaced as multiple candidates and the agent asks — the confirm-under-genuine-ambiguity behavior Flight 3 observed is CORRECT here.
- Rationale: operator decisions verbatim (separate tool; candidates not guesses); read-authorization mirrors the existing matrix rather than inventing a new one.
- Trade-off: two tool calls for the happy path — accepted with the gpt-oss:20b floor (mission posture, Flight 3 debrief).

**DD-6 — Carve-out generalized to the connector tool pair**: the factory's sanctioned seed block seeds BOTH `send_to_platform_channel` AND the lookup tool when each is enabled for the agent (one line inside the existing block; `agent/core.py` untouched — the seed/reset mechanism already handles N entries). `fetch_channel_history` deliberately stays search-discovered (not chain-critical). Pin tests extended: pair-seeded when enabled, independently absent when either is disabled, reset survival for both, no duplication on search match.
- Rationale: the two-call chain must not depend on mid-chain `search_tools` discovery (RQ8's lesson, applied at planning this time).
- Trade-off: baseline grows by one schema; the frozen-loop boundary is respected (factory seed-list only).

**DD-7 — Directory-named session titles**: at channel-session creation, `resolve_session` titles the session from the directory (`display_name`) when an entry exists, else the raw channel id as today. Repository surface (design review): DD-5's tool uses `search(agent_name, query, connector_id=None)` (agent-scoped candidates); DD-7 uses a separate exact-match `get(connector_id, kind, platform_id)` — two named methods on one repository, not a shared query. Creation-time only — a later directory update does NOT retro-rename existing sessions (stated trade-off; retro-rename would need an update path with UI-refresh semantics — out of scope). DM sessions already use peer names.
- Rationale: operator-approved ride-along; the directory's first in-app consumer beyond the tool.
- Trade-off: sessions created before the name was observed keep the raw id title.

**DD-8 — `keying_to_target` extraction** (Flight 3 debrief debt): one shared helper mapping a chat-session row's keying columns to a `SendTarget` (peer-keyed → `PeerTarget`, channel-keyed → `ChannelTarget` with thread passthrough), consumed by `connector_send._resolve_default_target` AND used as the reference for `resolve_session`'s keying semantics; the two current independent implementations collapse to one before Telegram would have added a third. Home: `the_one/connectors/base.py` or a small `_keying.py` (implementer's within the named touch).
- Rationale: the debrief's forcing-function timing, exactly as recommended.
- Trade-off: none; behavior-preserving refactor pinned by existing DD-11 tests.

**DD-9 — Setup help file**: `docs/connector-setup.md` — per-platform operator walkthroughs: Discord (app + bot creation in a real browser, token reset/MFA, Message Content intent on the MAIN bot — and on any driver/test bot doing REST reads, the Flight 3 lesson — OAuth invite, form fields, pairing) and Telegram (@BotFather token, privacy mode implications for group listening — `/setprivacy` OFF needed for always-listen groups, noted explicitly — form fields, pairing). Linked from `connectors/README.md` and the top-level README.
- Rationale: operator request from the Flight 3 HAT; written while the walkthrough is fresh and the Telegram half is being lived.
- Trade-off: docs drift risk accepted; the file states its verified-against date.

**DD-10 — Verification apparatus** (three-axis audited: act, observe, ADMIT — the Flight 3 axis):
- **Stub behavior test `directory-lookup-send`** (the mechanical gate, FD-run before the HAT): seeds a directory entry by driving an admitted stub envelope (act: the `/_test/stub/inbound` seam — its output is ADMITTED because the stub peer is allowlisted; observe: `/_test/stub/outbound` + `GET /api/chat/sessions` + Chat UI), then the operator instructs by NAME; expected: lookup tool returns the candidate, send fires with explicit ids, `[platform-send-ok]` lands, stub outbound records the content. Proves the two-call chain with a real model, no live platform. Draft authored this phase.
- **Telegram unit truth**: fake Bot API fixture (`tests/_telegram_api_fixture.py`, an httpx-mockable or local-HTTP double scripting getUpdates batches/errors/409/401) — no live network in unit tests, ever (DD-8 Flight 3 pattern).
- **Live**: guided HAT (leg 4) — Telegram DM + pairing + group always-listen + `/new` from the operator's real account, PLUS cross-connector directory sends (name-address a Discord peer and a Telegram peer from the console). No automated Telegram live gate: bots cannot see other bots' messages on Telegram (platform rule — the driver-bot apparatus does not exist), and a userbot would need a new dependency; the HAT is the honest live instrument. Model prerequisite: gpt-oss:20b bound before the stub gate (mission posture).

**DD-11 — Budgets**: flight total ≤700 connector Python (Telegram subpackage ≤350; migration + directory + tool + extraction + hooks ≤350 — loosened from 300 at design review against this codebase's documentation density: the DD-citing comment house pattern is worth more than 50 lines, and precedents run 100-200 lines per comparable unit), leaving ≥500 mission slack; JS ≤30 (generic form expected to cover Telegram; session titles are server-side). Mid-leg counts per the standing discipline.

### Prerequisites
- [ ] PR #188 merged (done — branch cuts from `ec2a0e0`+)
- [ ] Telegram bot token from @BotFather (operator-supplied before leg 4; the stub gate and all unit work need none)
- [ ] `/setprivacy` decision for the bot (OFF for group always-listen — leg 4 setup, documented in DD-9's help file)
- [ ] Network egress to `api.telegram.org` (leg 4 only)
- [ ] Dev-instance conventions (port 8485, scratch dir; never 8484); gpt-oss:20b present in Ollama (verified — pulled during Flight 3)
- [ ] Operator's Telegram account for the HAT

### Pre-Flight Checklist
- [x] All open questions resolved (mission RQ10/RQ11 + criterion rewording recorded in mission.md)
- [x] Design decisions documented (11 DDs)
- [x] Prerequisites verified (bot token + privacy mode at leg 4; rest verified)
- [x] Validation approach defined (stub behavior gate; fake Bot API fixture; guided HAT)
- [x] Legs defined (4: schema-and-shared, telegram-client, directory-tool-and-gate, hat-alignment)

---

## In-Flight

### Technical Approach

Schema first (leg 1: v39 executed live, lockstep type set, repository, passive-population hooks, keying extraction, session titles — the shared-surface leg, high-risk by definition), then the Telegram subpackage against its fake Bot API fixture (leg 2, plus the setup help file while the walkthrough is lived), then the lookup tool + generalized carve-out + the stub behavior gate (leg 3, FD-run gate), closing with the guided HAT (leg 4: Telegram live + cross-connector name sends). Flight 3 disciplines carry: DD-to-AC traceability, the three new review-time questions (DD-to-DD contradiction sweep, trace-the-happy-path, tool parameter-source audit — applied at leg design, not discovered live), citation audits, foreground-only test runs, mid-leg budget counts.

### Checkpoints
- [ ] Leg 1 lands: v39 applied to a live scratch DB and idempotent on re-run; directory repository + hooks live; keying helper extracted with DD-11 tests green; suite green
- [ ] Leg 2 lands: Telegram subpackage complete against the fixture; counts reported; help file drafted
- [ ] Leg 3 lands: `directory-lookup-send` stub gate PASSES; pin tests green
- [ ] Leg 4 lands: Telegram HAT + cross-connector name sends verified by the operator

### Adaptation Criteria

**Divert if**:
- v39's ceremony surfaces any need beyond the CHECK + directory table — stop; RQ10's scope is exact and a third step is a mission conversation
- The Telegram subpackage approaches 350 lines before long-poll correctness is complete — stop-and-split per the ceiling discipline
- The lookup→send chain fails the stub gate on model-policy grounds at the gpt-oss floor — pause; that is a mission-posture conversation (RQ8's escalation shape), not a rerun-until-pass

**Acceptable variations**:
- File boundaries within the subpackage; fixture transport mechanism; lookup tool's final name (behavior spec pins it before the gate runs)
- Directory channel-observation plumbing (callback vs. plugin-side repository access) per leg-1 design review

### Legs

> **Note:** Tentative; planned one at a time as the flight progresses.

- [x] `schema-and-shared` - v39 (CHECK + `connector_directory` incl. `thread_id`, executed live) + lockstep type set + `ConnectorDirectoryRepository` (query + exact-match methods) + passive-population hooks (inbound peers pre-early-return, incl. optional `peer_username` envelope field + stub-seam passthrough; Discord channel-name capture) + delete-route directory cleanup + DD-7 session titles + DD-8 `keying_to_target` extraction
- [x] `telegram-client` - `the_one/connectors/telegram/` (long-poll `_api` + plugin + translate + **`chat.title` → directory channel upsert**, DD-4b's Telegram half) + production registration + `tests/_telegram_api_fixture.py` + unit tests (offset semantics, 401/409 permanent-failure, error→manager-backoff, translation incl. is_dm/mentions/bot-drop-with-allowlist, at-least-once note, directory upsert-on-change) + DD-9 setup help file
- [x] `directory-tool-and-gate` - lookup tool + read-authorization + DD-6 carve-out generalization + pin tests + finalize and RUN `directory-lookup-send` (FD-run stub gate)
- [x] `hat-alignment` *(interactive)* - guided HAT: Telegram DM/pairing/group/`/new` live + cross-connector name-addressed sends + daily-driver alignment

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing
- [x] Documentation updated

### Verification
- `make test-unit` + browser lanes green; no new deps in `uv.lock`; v39 idempotency proven.
- `/behavior-test directory-lookup-send` PASS; run log committed.
- Counts vs. DD-11 budgets; the DD-1 shared-touch enumeration audited against the final diff (the seam criterion's evidence).
- Guided HAT sign-off (leg 4), including at least one cross-connector name-addressed send observed on each live platform.
