# Flight: Live-Traffic HAT Capability

**Status**: in-flight
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [x] #5 — Multi-user routing validated against real Discord traffic (≥3 distinct senders through one channel → one shared channel-scoped session with correct per-peer attribution + per-user ACL enforcement + correct agent routing) **— CLOSED by L4 (PASS 4/4: topology + per-user ACL differentiation + hard-deny→no-eligible).** DM-isolation ("channel of 1") deferred to L7's human pass (bot-to-bot DM blocked by Discord 50007).
- [ ] #6 — Multi-channel routing validated against real Discord traffic (≥3 channels each defaulting to a different agent via the routing-rules editor; channel-scoped overrides exercised)
- [ ] #7 — Multi-peer / multi-agent routing validated against real Discord traffic (multiple agents on one connector; per-(agent, peer) ACL precedent; peer-issued `/talk_to` override)
- [x] #9 — Detach-from-Connectors-screen exercised end-to-end **— CLOSED by L7 (Chrome-MCP interactive HAT): in-place detach (no reload), grid badge 2→1, `connector_ids` cleared, persisted across restart.**
- [~] #11 — The end-to-end HAT ships as a committed, repeatable, agent-runnable artifact in the repository (closes the `[~]` left by F14's slash-only portion; multi-user / multi-channel / multi-agent / pairing / mentions-aware coverage lands here) **— committed autonomous driver `tests/live/discord_hat/` covers multi-user (L4) / multi-channel (L5) / multi-agent (L6) + the smoke (L3), all re-runnable; mentions-aware verified live (L7, UI-selected model). Pairing + DM-isolation are inherently human-interactive (a Discord bot can't DM another bot — 50007) and were verified in L7's operator-driven pass, not the autonomous driver. Behavior-test specs (`discord-multi-user/channel/agent-routing`, `discord-engagement`, `discord-slash-end-to-end`) wrap the Witnessed layer. Remaining `[~]` nuance: the pairing/DM-isolation portions are operator-interactive by platform necessity, not a single autonomous script.**
- [x] #13 — Peer-name attribution observed end-to-end under real multi-user traffic **— CLOSED by L4 (3 distinct bots' F6 `peer_name` present on their inbound messages in the shared session).** Chat-UI rendering re-confirmable visually in L7/L8.

> **Out of scope for F15 (deferred):** #17 rate-limiting/backpressure. discord.py pre-empts per-route limits internally; no 429 cascade has been observed; the criterion is inherited from M10 #23 as a robustness property, not from a real failure. #17 is validated under real load during the daily-driver flight (F16) and a backpressure substrate is built only if the day-long run surfaces cascades. See Design Decisions.

---

## Pre-Flight

### Objective

Deliver the mission's end-to-end verification capability: a committed, repeatable, agent-runnable HAT that drives the real Discord bot through multi-user, multi-channel, and multi-agent routing — plus pairing, peer-name attribution, mentions-aware response, and the never-exercised detach affordance — against a real test guild, and reports pass/fail per mission criterion. The HAT is the artifact future Discord-touching flights run as a regression gate. F15 ships the *capability*; the wall-clock daily-driver validation (criterion #19) and rate-limiting (criterion #17) are gated to F16. Following the F14 precedent, the live HAT is expected to surface pre-existing bugs that no unit/integration test reached; the flight is structured to absorb inline fix-legs when it does.

### Open Questions

- [x] **Apparatus — Chrome-MCP single-session, multi-bot driver, or hybrid?** → see Design Decisions ("HAT Apparatus"). Resolved: **hybrid** — committed discord.py multi-bot driver for the automatable routing/pairing/mentions paths + a short operator-driven Chrome-MCP pass for what bots cannot reach (real-human pairing-approval click-through; Chat UI attribution observation).
- [x] **Is a discord.py multi-bot driver even viable, given the bot-author inbound filter?** → Premise-audited and resolved YES. `account.config["ingest_bots"]` (`the_one/connectors/_discord.py:935`) disables the bot-author filter (the self-filter stays always-on); `peer_id = str(message.author.id)` (`the_one/connectors/_discord_translate.py:124`) so each distinct burner-bot token resolves to a distinct peer. The post-gate inbound path is identical to a human sender's.
- [x] **Is rate-limiting (#17) in F15?** → No. Deferred to F16 (daily-driver). See Design Decisions.
- [x] **Bot-peer vs human-peer path equivalence** → Premise-audited at planning (Architect cycle-1): grep of `_routing.py`/`_acl.py`/`_inbound.py`/`_session.py` found ZERO `.bot`/`is_bot`/author-type branches; a bot-authored peer is treated identically to a human peer for session resolution, ACL admission, and attribution. Still confirm with an L3 smoke round-trip, but the static premise holds.
- [x] **Session topology in a shared channel** → Resolved (Architect H1 + operator): sessions key on `(platform, connector_id, channel_id, thread_id)` (`_session.py:123`), `peer_id` excluded — so ≥3 senders in one channel share ONE session (verified per-peer by attribution + ACL + routing), while DMs isolate naturally (`channel_id = message.channel.id` per `_discord_translate.py:99`). See "Shared-channel session semantics" DD. L3's smoke scenario empirically demonstrates the topology before L4 asserts against it.
- [x] **Mention detection is author-agnostic** → Pre-verified statically (Architect cycle-2): `is_mention` (`_discord.py:1825`) checks the bot's id in `message.mentions`, independent of who authored the message — so a burner-bot `@mention` registers. Confirmed live at the L3 smoke. This both (a) gives the routing legs a deterministic, inference-free engagement path and (b) de-risks the L7 mentions-aware re-verify. Fallback if the live smoke contradicts: `always_listen`+substantive messages for routing legs, human-sender Chrome-MCP pass for mentions-aware.

### Design Decisions

**HAT Apparatus — hybrid: committed discord.py multi-bot driver + operator Chrome-MCP pass**
- Choice: A committed, `live`-marked discord.py harness spins up N burner bot clients that post real messages to a configured test guild; the target connector runs with `ingest_bots=true` so the-one ingests them; distinct burner author ids give distinct peers. The harness asserts routing/session/ACL outcomes against the-one's API + console side. A separate short operator-driven Chrome-MCP pass covers what bots structurally cannot do: a real-human DM exercising the pairing-approval UX, and visual confirmation of Chat UI peer-name attribution.
- Rationale: Premise-audited as viable (ingest_bots + author-id peers). Fully agent-automatable and re-runnable as a regression gate — which is exactly what criterion #11 asks for ("committed, reviewed, lint-passing code artifact treated as production code"), and what a one-time Chrome-MCP walk is not. The F14 debrief's apparatus lesson (L9 lost a cycle assuming a bot could invoke another bot's *slash* commands) does not bite here: F15 rides the *message* path (closed-loop bots posting and being ingested), not slash interactions (already closed by F14).
- Trade-off: Burner bots are not literally human users (a peer is a bot id), and bot-authored `@mentions` may not register (see Open Question). The path under test is identical post-gate, but the two genuinely human-only surfaces (pairing-approval click-through; attribution as a human reads it) are covered by the Chrome-MCP pass rather than the driver — hence *hybrid*, not pure-driver.
- Premise evidence: `_discord.py:935` (`ingest_bots`), `_discord_translate.py:124` (`peer_id=author.id`).

**Committed HAT artifact = discord.py `live`-marked driver; behavior-test specs wrap the operator-observable layer**
- Choice: The committed regression artifact (criterion #11) is the discord.py multi-bot driver under `tests/live/` (consistent with the existing `live` pytest marker). The Witnessed-pattern behavior-test specs (`tests/behavior/*.md`, run via `/behavior-test`) wrap the operator-observable judgments — their Actions reference running a driver scenario; their Expected Results are what a Validator observes in the Chat UI / channel.
- Rationale: Separates deterministic machine assertions (driver) from human-judged UX observation (Witnessed specs). Both are needed; #11 wants committed code, the routing/attribution UX wants a Validator.
- Trade-off: Two artifacts to keep in sync; mitigated by the driver scenarios being the single source of the posting sequence the specs reference.

**Rate-limiting (#17) deferred to the daily-driver flight (F16)**
- Choice: F15 builds no backpressure substrate. #17 is validated under real load during F16's full-working-day run; a queue + adaptive backoff is built only if that run surfaces 429 cascades.
- Rationale: discord.py's `HTTPClient` pre-empts per-route limits internally (the SDK has its own bucket tracker; we only see a 429 at the `send()` boundary in the residual global-limit / pathological-flood case). No cascade has been observed in daily-driver use since F8. Building speculatively against an unobserved failure violates the F14 "verify the premise before building" discipline — applied here to a whole feature.
- Trade-off: #17 stays open past F15. Acceptable: SDK pre-empts; the daily-driver run is the correct place to discover whether anything is needed.

**Shared-channel session semantics — one session per channel, isolated per DM (no substrate change)**
- Choice: F15 verifies multi-user routing (#5) against the substrate's actual session topology: a shared guild channel resolves all senders to ONE channel-scoped session (per-peer-ness comes from attribution + ACL + routing within it), and a DM resolves to its own session (a "channel of 1"). The mission #5 wording was clarified to match (operator-confirmed); no session-keying change is made.
- Rationale: `resolve_session` keys on `(platform, connector_id, channel_id, thread_id)` and deliberately excludes `peer_id` (`_session.py:123`). Isolating peers *within* one channel would give the bot incoherent parallel conversations in a single room; the channel-as-group-conversation model (with F6 attribution distinguishing speakers) is the correct design. DMs isolate for free because each DM channel id is unique per user-pair (`_discord_translate.py:99`).
- Trade-off: The flagship multi-user spec asserts "one shared, correctly-attributed session," not "three sessions." A future genuine need for per-peer threads in a channel would require re-opening M10 F3 session keying — out of scope here.
- Premise evidence: `_session.py:123`, `repositories.py:872` (4-tuple lookup), `_discord_translate.py:99` (DM channel id).

**Routing HAT engages deterministically via `@mention` so routing — not the policy gate's inference — is the variable**
- Choice: The driver's routing-leg messages (L4–L6) `@mention` the-one's bot. The mention path engages the agent immediately with NO inference call. `always_listen=true` (account + per-agent) is configured as a documented fallback only.
- Rationale: The policy gate (`_inbound.py:_policy_gate_decision`, lines 224–266) has only two non-inference engagement paths for a channel message: `@mention` (outcome=`mention`, line 226) and `/talk_to` override. The `always_listen` path (lines 247–266) ALWAYS runs `run_engagement_inference`, whose prompt is strongly biased toward silence ("STRONG BIAS TOWARD 'no'… When in doubt, 'no'", `_inference.py:73,81`) and engages only on a single-word `"yes"`. So `always_listen=true` alone does NOT deterministically engage — a plain message can land `policy-silent`, which in a routing test reads as a false routing failure (the exact false-FAIL class the F14/F13 debriefs warned about). `@mention` removes the inference confound entirely, so a non-`stepped` disposition unambiguously means a routing/ACL fault, not policy silence. `is_mention` is author-agnostic (`_discord.py:1825` — checks the bot's id in `message.mentions`, independent of who authored), so it fires for a burner-bot-authored mention; verified at the L3 smoke.
- Trade-off: The routing legs don't exercise the non-mention `always_listen`+inference path; that's intentional separation of concerns — mentions-aware engagement is criterion #12 (already closed, re-verified in L7 via `discord-engagement`). If the L3 smoke shows bot-authored mentions do NOT register, fall back to `always_listen=true` + substantive direct messages crafted to clear the inference "yes" bar (acceptable variation).

**Diagnostic observability lands before the HAT legs (L1 first)**
- Choice: Wire connector loggers to stdout (and add `tini` as PID 1) as the first leg, before any live-traffic HAT leg.
- Rationale: F14 called app-level connector logging invisible to `docker logs` "the single largest diagnostic impediment of the flight." The live HAT is expected to surface bugs (F14 surfaced three). Diagnosing them without connect/READY/sync/ACL/dispatch log visibility repeats F14's pain. Observability is a prerequisite, not a nicety.
- Trade-off: Front-loads two fold-ins that don't advance a routing criterion; justified by diagnostic leverage on every subsequent leg.

### Prerequisites

- [ ] **Three burner Discord bot applications + tokens**, each invited to the test guild with the **Message Content privileged intent** enabled (required — without it the burners' posts arrive empty-text and silently no-op the translate; the-one's own client sets it at `_discord.py:781`). The burner bots are **posting-only and never auto-reply** (the L3 driver contract; prevents an `ingest_bots` feedback loop where the-one's reply is re-ingested). Tokens are injected at run time via env and are gitignored — never committed.
- [ ] **A test guild** with ≥3 text channels and ≥2 roles (per mission environment requirements), used by the test connector ONLY (isolated from the operator's daily-driver connector to contain the `ingest_bots` blast radius). Its structure is documented as a committed fixture description (not the tokens).
- [ ] **A dedicated test connector** in the-one configured with `ingest_bots=true`, **`always_listen=FALSE`** (revised from `true` at L3 design — see flight log 2026-06-02: with `always_listen=false`, `@mention → stepped` and `non-mention → policy-silent(always-listen-off)`, a deterministic control with inference fully out of the routing path; L7 flips it on to exercise the mentions-aware inference), the test guild on `allowlist.guilds`, and ≥2 agents attached (for multi-agent routing). Kept separate from the operator's daily-driver connector.
- [ ] **Local inference provider (Ollama)** configured for the mentions-aware path (per the `discord-engagement` precedent) so the inference pre-step runs without external-API rate limits during the HAT.
- [ ] **Chrome-MCP browser session** with the operator logged into Discord, for the hybrid operator pass (pairing approval + attribution observation).
- [ ] **the-one container running**; a new `discord_hat` pytest marker + `make test-discord-hat` target are added in L3 (the existing `live` marker / `make test-live` are NOT reused — see DD/L3).
- [ ] L1's stdout logging landed before L4 (the first live-traffic leg) so HAT bugs are diagnosable.

### Pre-Flight Checklist

- [ ] All open questions resolved (two premise-audits scheduled into L3/L4 and L7 — pre-authorized in Adaptation Criteria)
- [ ] Design decisions documented
- [ ] Prerequisites verified (burner bots + test guild + test connector provisioned by the operator before L4)
- [ ] Validation approach defined (committed driver + behavior-test specs; see Verification)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

The flight front-loads diagnostic and baseline hygiene (L1–L2), builds the multi-bot driver foundation (L3), then drives one mission-criterion routing scenario per leg (L4–L6), then runs the hybrid operator pass for the human-only surfaces (L7), and finishes with an optional guided UAT that runs the full committed HAT and finalizes the report (L8).

- **Driver harness (L3):** a `live`-marked module under `tests/live/discord_hat/` that (a) reads burner-bot tokens + test-guild/channel ids from env, (b) brings up N `discord.py` clients, (c) exposes a scenario API (post-as-bot-k to channel-j, DM-as-bot-k, await the-one bot's reply or silence), and (d) asserts against the-one's side via its HTTP API (session list, session detail with `session_metadata["routing"]`, attribution) and/or the routing-audit panel. It emits a per-criterion pass/fail report. The smoke scenario proves one bot → the-one reply round-trips and resolves the bot-peer-equivalence premise.
- **Routing scenarios (L4–L6):** each leg drives a real multi-X scenario and asserts the F6/F7 substrate behaves under real traffic. Expected to surface pre-existing bugs (F14 precedent); inline fix-legs are pre-authorized.
- **Hybrid operator pass (L7):** Chrome-MCP + a real human sender for pairing-approval click-through, mentions-aware re-verify (if bot mentions don't register), and the detach-from-Connectors-screen affordance (#9). Reuses the `discord-engagement` Chrome-MCP precedent.
- **Observability (L1):** route the `the_one` package loggers (incl. `the_one.connectors.*`) to stdout so `docker logs` captures connect/READY/`tree.sync`/ACL/dispatch lines; add `tini` as PID 1 in the Dockerfile to reap the test-runner zombies.

### Checkpoints

- [x] L1 lands: `docker logs` shows connector connect/READY/ACL lines; `tini` is PID 1
- [ ] L2 lands: full browser baseline green (2 prior fails resolved); `audit-log-inspector` behavior test re-runs PASS
- [ ] L3 lands: committed multi-bot driver smoke round-trips; bot-peer-equivalence premise confirmed
- [ ] L4 lands: #5 multi-user + #13 attribution PASS
- [ ] L5 lands: #6 multi-channel PASS
- [ ] L6 lands: #7 multi-agent/multi-peer PASS
- [ ] L7 lands: #9 detach + pairing + mentions-aware re-verify PASS
- [ ] HAT report committed; criteria #5/#6/#7/#9/#11/#13 checked in mission.md

### Adaptation Criteria

**Divert if**:
- The bot-peer-equivalence premise (L3) fails — a human-specific branch downstream of the `ingest_bots` gate means burner bots can't stand in for users. Re-plan the apparatus toward operator-orchestrated human burners (the Chrome-MCP + manual option) before L4.
- The operator cannot provision three burner bot tokens / a test guild — the driver has no inputs; fall back to a reduced-fidelity operator-manual HAT and re-scope criteria coverage.

**Acceptable variations**:
- **Inline fix-legs (F14 precedent):** if a routing scenario surfaces a pre-existing bug, add an inline fix-leg (e.g. L4a) with its own ACs + regression test, fix, then resume the HAT. Pre-authorized; record in the flight log.
- **Mentions-aware fallback:** if bot-authored `@mentions` don't register (L7 premise), verify mentions-aware via the operator Chrome-MCP human-sender pass instead of the driver.
- **Driver location/shape:** `tests/live/discord_hat/` is the default; a sibling `scripts/` location is acceptable if the `live` marker integration proves awkward — record the choice in the log.
- **L5/L6 consolidation:** if multi-channel and multi-agent fixtures overlap heavily, the designer may merge them into one extended-routing leg, provided both criteria get distinct report rows.

### Legs

> **Note:** Tentative; planned one at a time as the flight progresses. Verification legs (L4–L6) are light when no bug surfaces and may spawn pre-authorized inline fix-legs when one does.

- [x] `connector-observability-and-reaper` *(completed)* — Wire `the_one.*` loggers (incl. connectors) to stdout so `docker logs` captures connect/READY/`tree.sync`/ACL/dispatch lines; add `tini` as PID 1 in the Dockerfile to reap test-runner zombies. *(fold-ins; diagnostic prerequisite for the HAT)*
- [x] `test-baseline-hygiene` *(autonomous landed — browser-fails retired as already-satisfied; seed endpoint built; FD `/behavior-test` re-run still owed)* — Re-locate and fix the two pre-existing browser failures in `test_flow_agent_tabs.py` + `test_flow_studio_navigation.py` (function names drifted from the debrief; the studio one is near `test_flow_studio_navigation.py:253` — re-locate the exact current names first, then fix); fix the `audit-log-inspector` behavior-test seeding path (`ChatSessionRepository.update` at `repositories.py:936` drops `session_metadata` by design per its docstring — seed via a test-only session/fixture or direct write, NOT a PUT) and re-run it to PASS. *(fold-ins; restores a clean baseline before the HAT adds to it)*
- [x] `multi-bot-hat-driver-foundation` — *(completed — live smoke PASS 3/3; DM-isolation deferred to L7)* Committed discord.py multi-bot driver skeleton under `tests/live/discord_hat/`: N-bot lifecycle, env-injected token/guild config (gitignored), test-connector `ingest_bots=true` fixture, scenario API, per-criterion pass/fail report shape, and a one-bot smoke round-trip. Adds a **dedicated pytest marker + Make target** for the HAT (the existing `live` marker means "real LLM APIs" and `make test-live` is hardcoded to `test_aiat.py` — do NOT overload it; add e.g. a `discord_hat` marker and a `make test-discord-hat` target). Driver contract: burner bots are **posting-only, never auto-reply**; test connector targets the isolated test guild only (M2 loop guard). Empirically demonstrates the session topology (smoke: confirm one channel → one shared session; a DM → its own session) AND that a burner-bot-authored `@mention` registers (`is_mention` fires → outcome=`mention`, no inference) so L4 asserts against verified behavior, not the spec's assumption. *(criterion #11 foundation)*
- [x] `multi-user-routing-hat` *(completed — live PASS 4/4; closes #5 + #13)* — Drive ≥3 burner bots through one channel; assert all resolve to ONE shared channel-scoped session, each correctly attributed (F6) and routed to the right agent, with F6 per-user ACL overlays admitting/denying correctly under real traffic (an ACL-denied (agent, peer) collapses to `disposition: no-eligible`); response correctness observable from the console. Then drive a DM from a burner bot and assert it resolves to its OWN isolated session ("channel of 1"). Observe Chat UI renders `discord-username: message` per distinct peer in the shared session. *(criteria #5, #13)*
- [x] `multi-channel-routing-hat` *(completed — live PASS 4/4; closes #6)* — Drive traffic across ≥3 channels each defaulting to a different agent via the routing-rules editor; exercise channel-scoped agent overrides; confirm the F7 routing engine resolves correctly under real traffic. *(criterion #6)*
- [x] `multi-agent-routing-hat` *(completed — live PASS 3/3; with L4 closes #7)* — Multiple agents on one connector + multiple burner-bot peers; exercise the per-(agent, peer) ACL precedent (L4) and the peer-issued `/talk-to <agent>` override (L6: text-prefix override, intercept + scope=override + override-beats-rule + re-override). *(criterion #7)*
- [x] `pairing-mentions-detach-hat` *(completed — interactive HAT PASS; closes #9 + DM-isolation half of #5; surfaced the pairing→peers-narrowing Known Issue)* — Hybrid operator Chrome-MCP pass: a real-human DM from an unpaired account exercises the Discord-native pairing-approval click-through; mentions-aware re-verify (UI-selected model); detach an attached agent from the Connectors screen and confirm access revokes immediately + persists across restart + grid updates without reload. *(criterion #9; re-verify pairing/mentions under real traffic)*
- [ ] `uat-and-alignment` *(optional)* — Guided UAT: run the full committed HAT end-to-end, walk the operator through each criterion's evidence, fix any last-mile issues, finalize the committed HAT script + report, and check off criteria #5/#6/#7/#9/#11/#13 in mission.md.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged (committed multi-bot driver + fixes; behavior-test specs)
- [ ] Tests passing (backend + browser baseline green; `live` HAT passes against the test guild)
- [ ] Documentation updated (agents.md: HAT-driver usage + the bot-peer-equivalence + ingest_bots facts; README if operator-facing HAT instructions are warranted)
- [ ] mission.md criteria #5/#6/#7/#9/#11/#13 checked; #11 flips `[~]`→`[x]`

### Verification

The flight is verified by the committed HAT itself plus the Witnessed behavior-test specs:

- **Committed driver** (`tests/live/discord_hat/`, behind a dedicated `discord_hat` pytest marker + `make test-discord-hat` target — NOT the `live` marker, which means "real LLM APIs" and whose `make test-live` is hardcoded to `test_aiat.py`): re-runnable against the provisioned test guild; emits a per-criterion pass/fail report. This is the regression-gate artifact (criterion #11).
- **Behavior-test specs** (Witnessed, `/behavior-test`):
  - `discord-multi-user-routing` *(draft authored this flight — `tests/behavior/discord-multi-user-routing.md`)* — apparatus: hybrid (multi-bot driver posts; Chrome-MCP + `[mixed-frame]` session-detail observe). Key observable: ≥3 distinct bot-peers → ≥3 distinct sessions each routed to the correct agent, with per-peer attribution rendered in the Chat UI. ~8 steps. Closes #5 + #13.
  - `discord-multi-channel-routing` *(named; fleshed at L5)* — apparatus: multi-bot driver + console. Key observable: each of ≥3 channels routes to its configured default agent; a channel-scoped override redirects correctly. ~6 steps. Closes #6.
  - `discord-multi-agent-routing` *(named; fleshed at L6)* — apparatus: multi-bot driver + console. Key observable: per-(agent, peer) ACL admits/denies correctly; a `/talk_to` override re-routes a peer. ~6 steps. Closes #7.
  - `discord-detach-and-pairing` *(named; fleshed at L7)* — apparatus: operator Chrome-MCP + real human sender. Key observable: detach revokes access immediately + survives restart + grid updates without reload; an unpaired DM surfaces the approval UX and one-click approve admits the peer. ~7 steps. Closes #9; re-verifies pairing.
- **Existing regression gates** re-run green: `discord-slash-end-to-end` (F14), `connector-inference-provider-config-roundtrip` (F13), `audit-log-inspector-renders-routing-entries` (re-enabled in L2).
