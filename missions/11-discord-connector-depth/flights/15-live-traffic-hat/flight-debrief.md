# Flight Debrief: Live-Traffic HAT Capability

**Date**: 2026-06-02
**Flight**: [Live-Traffic HAT Capability](flight.md)
**Status**: landed
**Duration**: 2026-06-01 (planning) → 2026-06-02 (land)
**Legs Completed**: 7 of 7 (L8 optional UAT skipped — every surface verified live across L3–L7)

## Outcome Assessment

### Objectives Achieved

The flight delivered its objective: a committed, re-runnable `discord.py` multi-bot HAT driver (`tests/live/discord_hat/`) that drove the **real** test guild end-to-end through multi-user / multi-channel / multi-agent routing, peer-name attribution, pairing, mentions-aware response, and detach — with a hybrid apparatus (autonomous bot driver + an operator Chrome-MCP pass for the irreducibly-human surfaces). Every leg's live run passed first-try (smoke 3/3, multi-user 4/4, multi-channel 4/4, multi-agent 3/3, L7 interactive all-PASS).

### Mission Criteria Advanced

| # | Criterion | Result |
|---|-----------|--------|
| #5 | Multi-user routing + DM-isolation | **CLOSED** (L4 shared-session topology + per-(agent,peer) ACL + hard-deny; L7 DM "channel of 1") |
| #6 | Multi-channel routing | **CLOSED** (L5 per-channel rules + default fall-through + channel-scoped override) |
| #7 | Multi-peer/multi-agent routing | **CLOSED** (L4 multi-agent/peer + ACL; L6 `/talk-to` override: intercept, override>rule, re-override) |
| #9 | Detach-from-Connectors-screen | **CLOSED** (L7 in-place detach, badge 2→1, `connector_ids` cleared, restart-persisted) |
| #13 | Peer-name attribution | **CLOSED** (L4 — 3 distinct bots' F6 `peer_name` in the shared session) |
| #11 | Committed HAT artifact | **`[~]`** — autonomous driver covers multi-user/channel/agent + mentions-aware; pairing/DM-isolation are inherently human (bot-can't-DM-bot) |
| #8 / #12 | Pairing / mentions-aware | re-verified live (L7); #12 exercised the UI-selected inference model (qwen2.5:7b) for the first time since F13 L4 |

Rate-limiting (#17) was removed at planning → F16 (validate under real load, build backpressure only if a 429 cascade surfaces).

## What Went Well

- **Hybrid multi-bot-driver apparatus, premise-audited at *planning* — the central bet, and it never wobbled.** The viability premise (`ingest_bots` + author-id peers, `_discord.py:935` / `_discord_translate.py:124`) was confirmed before lock, not discovered mid-flight. This is the direct corrective to F14 L9 (which lost a cycle to an unaudited apparatus premise). L4/L5/L6 each landed first-try-clean on the live run.
- **`@mention`-deterministic engagement with `always_listen=false` — the single best design call.** The team recognized that `always_listen=true` does NOT deterministically engage (it always runs the silence-biased `run_engagement_inference`, so a plain routing-test message can land `policy-silent` and read as a *false routing failure* — the exact F13/F14 false-FAIL class). Routing via `@mention` removed the inference confound entirely, making any non-`stepped` disposition an unambiguous routing/ACL fault. This is what made L4–L6 deterministic.
- **The design-review loop caught every assertion-shape error before code.** Session keying excludes `peer_id` (shared-channel topology, not 3 sessions); `stepped` entries omit `policy.outcome`/`peer_id`; the `propagate=False` logging change empirically breaks the `test_lifespan.py` caplog tests; `post_and_wait_new_routing` blocks on a cold channel. **Every mid-flight revision was a shape correction caught at review against real code — not an approach reversal, and none cost a live run.**
- **L1 observability-first earned its keep within hours.** L3 diagnosed the "connector SKIPPED — no attached agents" startup condition *only because* L1 had wired connector logs to `docker logs`.
- **L2 recon retired a fold-in before writing code.** The "2 pre-existing browser fails" were `already-satisfied` (F14 L5 had fixed them; the debrief-cited function names had drifted). L2 collapsed to building the clean seed endpoint + retiring the item with evidence.
- **Set/restore-in-`finally` self-contained live tests.** Every test that mutated the operator's live connector/agent config captured the prior value and restored it None-safely in `finally` (verified restored on every leg), with `secrets` omitted on every PUT so the live token was never round-tripped. Re-runnable with zero manual cleanup.
- **L7 surfaced the highest-value finding of the flight** — the pairing→peers-narrowing lock-out — which *only* a live human-DM pass against a real connector could have caught.

## What Could Be Improved

### Process

- **Premise audit covered the *ingestion* path but not the *assertion/observability* path.** The L3 cycle-1 HIGH ("the HTTP session API exposes no connector-keying fields", `_session_summary` api.py:3271) is a *static* fact that a planning-time audit would have surfaced — the flight thoroughly audited "can a bot be ingested as a peer?" but not "can the driver observe everything it must assert, through an existing surface?". No live cost (caught at design review), but it's the one premise that should have been on the planning checklist alongside the `ingest_bots` audit. **Headline forward-looking lesson.**
- **The `always_listen=true` "fallback" was dead-on-arrival but re-litigated at L3.** The cycle-2 Architect review (N1) already established `@mention` as the deterministic path; the planning DD/prereq still carried `always_listen=true` as a fallback into L3, where it was explicitly superseded to `always_listen=false`. Lock a decision once it's understood rather than carrying a known-dead alternative forward.
- **Provisioning friction was under-weighted in prerequisites.** Burner bots had to be created *manually* in a normal browser (the MCP-automated browser loops hCaptcha; token reset is MFA-gated — both hard automation blockers). The connector needed reconfiguration + a **container restart** (the `ingest_bots` gate reads connect-time-closure config). The prereqs listed "3 burner bots + test guild + test connector" but flagged neither the captcha/MFA manual-provisioning reality nor the restart requirement.

### Technical

- **The driver SKIPs without creds, so CI has no regression net for it.** Correct (no secrets in CI), but a refactor that breaks `wait_for_session`/`inbound_peer_names`/the routing-length logic would only surface on the next operator live run. **Add a handful of hermetic unit tests for the pure helpers** (against fixture dicts — no Discord needed).
- **`_BOT_IDS` is hardcoded in `test_multi_user.py:53`** — the only HAT test that doesn't take its ids from env. Re-provisioning burner bots silently breaks that one file. Move into the env contract.
- **The lookup seam papers over a production observability gap.** `_session_summary` / the WS `list_sessions` projection carry no connector-keying fields; the HAT relies on a dev-mode test seam to resolve "the session for this (connector, channel)". Sound as a HAT artifact, but if a future operator-facing feature needs connector-keyed session resolution it will rediscover this gap — promote the production projection rather than reaching for the seam.
- **`tini` (L1) reaps process zombies — it does NOT address the pre-existing aiosqlite "Event loop is closed" teardown warning** (`test_db_migration.py` `TestSchemaV17`, 3 warnings, tracked since F11). Different problem (asyncio loop teardown vs `<defunct>` reaping). Stated explicitly so no one assumes tini resolved it; still belongs on the routine-maintenance ticket.

### Documentation

- **The committed HAT driver has no README / agents.md note — the highest-value doc the flight could leave behind.** A `tests/live/discord_hat/README.md` should capture: the burner-bot provisioning procedure (created in a *normal* browser; Message Content intent is NOT needed on the burners — they only post; only the-one's own bot needs it); how to find the-one's gateway-assigned bot user id; that `make test-discord-hat` SKIPs without `.env.hat`; the `_BOT_IDS` re-provisioning gotcha; and the `wait_for_session(until=…)` timing rationale. All of this is currently buried in the flight log and will be lost.
- **Doc lag:** the L3 leg spec + L3 implementation note still describe a `message_content` intent on the burner bots; the actual fix was `Intents.default()` (bots only post). Cosmetic one-line scrub.

## Test Metrics

Full backend suite at debrief time (`docker exec the-one pytest tests/ -m 'not browser and not live and not pixel and not requires_bwrap and not discord_hat' --timeout 30 -q`):

| Metric | F12 | F13 | F14 | **F15** | Δ vs F14 |
|--------|-----|-----|-----|---------|----------|
| Backend passed | — | 2796 | 2820 | **2832** | **+12** |
| Backend skipped | 4 | 4 | 4 | **4** | 0 |
| Backend deselected | — | 520 | — | **528** | +8 (the 4 new `discord_hat` tests + bookkeeping) |
| Backend wall (s) | — | 243 | 301 | **262** | −39 |
| Failures / flakes | 0 | 0 | 0 | **0** | 0 |

- **+12 backend (net):** all from F15's own unit tests — L1 logging +5 (`test_logging_config.py`), L2 seed +6, L3 lookup +3 (= +14 added; −2 incidental churn elsewhere). Intra-flight the suite climbed 2823→2829→2832 as L1/L2/L3 landed.
- **Wall-clock −39s (301→262):** F14's 301 was inflated by a one-off (zombie pile + cold start); F15's 262 is in-line with the F11–F13 trend (~243–254) given +14 tests. No throughput regression — the M10-flagged t/s concern remains a non-signal.
- **The 4 `discord_hat` live tests are deselected/SKIP** without creds (correct); they are not part of the default suite.
- **3 warnings = the pre-existing aiosqlite teardown class** (unchanged by F15). Browser suite not re-run this debrief (F14 baseline 460).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| DM-isolation (#5 half) → L7 human pass | A Discord **bot cannot DM another bot** (REST 50007) — twice-confirmed apparatus law (cf. F14 L9 bot-can't-invoke-bot-slash) | **Yes** — bot-to-bot interactions requiring the target to receive/act are blocked; budget a human pass |
| `wait_for_session(until=…)` timing fix (L3) | Session row created early in dispatch; messages + `peer_name` + engaged routing entry persist only after `agent.step()` (post-LLM) | **Yes** — poll the *detail* until the expected state lands, never just the session existence |
| L3 cycle-2 rework: lookup seam + `always_listen=false` + bot-user-id | Assertion path couldn't see connector-keying fields; `stepped` entries lack `policy.outcome`/`peer_id` | The **assertion-path premise audit** → YES |
| `ingest_bots` change needed a container restart | `on_message`'s `ingest_bots` gate reads the **connect-time-closure** `account.config`; `always_listen`/`dm_admission`/`routing`/`connector_acls` read fresh per-dispatch | Document the **non-uniform config freshness** as an agents.md convention |
| Driver intents `message_content` → `Intents.default()` | Burner bots only POST; a privileged intent they don't have enabled raises `PrivilegedIntentsRequired` on connect | One-off; note in the driver README |

## Key Learnings

1. **Premise-audit the apparatus AND its assertion/observability path at planning** — with code citations. F15 audited ingestion viability flawlessly; the one gap (the lookup-seam need) was a foreseeable static fact about `_session_summary`.
2. **Observability-leg-first before a live HAT.** L1's connector-logging-to-stdout paid off same-day. Wire diagnostics as leg 1.
3. **Set/restore-in-`finally` is the reference shape for tests that touch live operator state** — capture prior, mutate, restore None-safely, assert restoration, omit `secrets`.
4. **Isolated one-at-a-time posting for peer→agent correlation** when audit entries lack a correlating key (`stepped` entries carry no `peer_id`). Bulk posting only proves "both agents appear."
5. **Connector config freshness is non-uniform** (`ingest_bots` = connect-time closure → restart; others = fresh per-dispatch). Promote to a convention.
6. **`@mention` is a deterministic, inference-free engagement path** — use it to isolate routing from the engagement gate; reserve `always_listen`+inference for testing the gate itself.

## Recommendations

1. **Open a follow-on flight to fix the pairing→peers-narrowing defect** (mission Known Issue) — the flagship. Architecturally it is a **DM-admission-vs-peers-axis conflation**: approving a DM peer should grant DM admission without collapsing the general `peers` allowlist (and the peers axis arguably shouldn't gate guild-channel messages when DM admission was the intent). This sits in the F9/F10 DM-admission-axis lineage — re-open that design rather than patch the approve handler in isolation. **Author a behavior test that reproduces the lock-out before the fix and gates it after** — the HAT driver's set/restore connector helpers make this straightforward.
2. **Write `tests/live/discord_hat/README.md`** — the provisioning + run procedure, the bot-can't-DM-bot constraint, the `wait_for_session(until=…)` timing gotcha, and the `_BOT_IDS` re-provisioning note. Highest-value doc the flight can leave.
3. **F16 (daily-driver gate):** run the committed HAT driver as the regression gate first, then add the production-realistic rate-limiting (#17, build backpressure only if a 429 cascade surfaces) + the full-working-day run (#19).
4. **Add hermetic unit tests for the pure driver helpers** (`inbound_peer_names`, `latest_routing_entry`, the routing-length before/after logic) so the no-creds CI run has *some* regression coverage of the driver's shape-parsing.
5. **Promote agents.md conventions:** premise-audit-includes-assertion-path; observability-leg-first; set/restore-in-finally; non-uniform-connector-config-freshness; isolated-posting-for-peer-correlation.
6. **Small cleanups:** move `_BOT_IDS` to the env contract; scrub the L3 `message_content` doc lag; add a one-line `/_test/*` endpoint-registry note (the surface is now 2 routes and dev-mode-gated, but worth keeping from sprawling).

## Methodology Feedback (mission-control skills)

- **The premise-audit discipline (an F14-debrief action item) paid off enormously** — the apparatus never wobbled. The one enhancement: the `/flight` skill's premise-audit step should explicitly prompt **both** the *ingestion/feasibility* premise AND the *assertion/observability* premise ("can the apparatus observe everything it must assert, through an existing surface?"). The lookup-seam need was foreseeable and would have been caught.
- **Behavior-test-authoring-in-planning (F14 directive) worked** — F15 drafted the `discord-multi-user-routing` spec at planning and it shaped the apparatus + leg breakdown; the routing specs were authored alongside their legs.
- **Interactive-HAT-leg handling held up** — L7's FD-guided step-by-step (Chrome-MCP on the-one's UI + operator for the human-DM surfaces) is the right shape for surfaces no autonomous agent can reach.

## Action Items

- [ ] **Follow-on flight: pairing→peers-narrowing fix** (DM-admission-vs-peers-axis separation; re-open F9/F10 DM-admission design; behavior-test reproduces-then-gates). *Flagship.*
- [ ] **`tests/live/discord_hat/README.md`** (provisioning + run + constraints + timing gotcha).
- [ ] Hermetic unit tests for the pure driver helpers (CI regression net).
- [ ] Move `_BOT_IDS` from `test_multi_user.py` into the env contract (`config.py` / `THE_ONE_HAT_BOT_USER_IDS`).
- [ ] Codify 5 agents.md conventions (Key Learnings 1–5).
- [ ] Scrub L3 `message_content`→`Intents.default()` doc lag (leg spec + flight-log note).
- [ ] aiosqlite "Event loop is closed" teardown warning → routine-maintenance (carried since F11; tini did NOT address it).
- [ ] **F16:** run the committed HAT driver as the regression gate; validate #17 under real load; full-working-day run (#19).
- [ ] **(mission-control `/flight` skill):** premise-audit step should include the assertion/observability path, not just ingestion/feasibility.
- [ ] Content-aware agent routing — parked as a mission enhancement (out of M11 scope; future flight).
