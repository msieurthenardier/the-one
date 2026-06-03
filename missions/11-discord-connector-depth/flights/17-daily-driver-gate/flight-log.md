# Flight Log: Daily-driver validation gate (full-working-day run + connector observability)

**Flight**: [Daily-driver validation gate](flight.md)

## Summary

Flight **`in-flight`** (2026-06-02). Autonomous legs **L1 (`connector-observability`) + L2 (`hat-driver-hardening`) are COMPLETED**, batch-reviewed (Sonnet, confirmed), and committed on a draft PR. **L3 (`full-working-day-run`) triggered injected leg L4 (`fix-gateway-idle-reap`)** which landed including a post-review hardening pass (two non-blocking findings: no-traffic-connector rewarm gate + no-`is_alive`-exempt fix). **Soak resumes pending commit of L4 review fixes.** Branch: `flight/17-daily-driver-gate`. Latest suite: 2890 passed / 4 skipped / 529 deselected.

---

## Flight Director Notes

- **2026-06-02** — `/agentic-workflow` invoked, scoped to autonomous legs only (operator instruction: "run until the manual steps"). Phase file `leg-execution.md` loaded + validated (Developer=Sonnet, Reviewer=Haiku). Branch `flight/17-daily-driver-gate` cut from `main` (ce288c8); F17 planning artifacts (mission.md #18-descope + the flights/17 dir) carried onto the branch, to be included in the L1+L2 batch commit. Flight `ready`→`in-flight`. Plan: 2a/2b for L1, then L2, then 2d batch review+commit+draft PR, then STOP before L3. F17 is the mission's daily-driver validation gate: light connector observability (L1) → HAT-driver hardening (L2) → a real full-working-day operator soak (L3). Rate-limiting (#17) closes passively (watched, not stress-tested); criterion #18 (onboarding walkthrough) was descoped from M11 at this flight's planning.
- **2026-06-02** — Both autonomous legs landed (L1 2861, L2 2884 passed / 4 skipped / 529 deselected, full suite green). Entering Phase 2d batch review. **FD decision: escalate the Reviewer from the crew-default Haiku to Sonnet** — L1 wires logging into the hot inbound-dispatch (`_inbound.py`, 10 sites) + outbound-send (`_discord.py`) paths, so the review must verify the load-bearing no-behavior-change / no-double-append / no-content-leak / 429-still-raises claims, which warrant stronger scrutiny. Within the "never Opus for Reviewer" envelope; same situational escalation as F16.
- **2026-06-02** — Batch review **[HANDOFF:confirmed]** (Sonnet). All load-bearing claims verified clean: dispatch path purely additive (no control-flow/mutation change, append + log side-by-side at all 10 sites); no double-log (plugin command-intercept returns before builtin path; distinct except-clauses); 429/`Forbidden`/`NotFound` raises intact; no content/token leak (helper signature structurally rejects `content=`/`token=`, test enforces); counters best-effort no-op when cold, snapshot deep-copies under lock; hermetic helper tests genuinely creds-free; anonymization clean. One **non-blocking** finding (misleading "Under `_lock`" opening of `record_disposition`'s docstring in `_pool.py`) fixed by a follow-up Developer (docstring-only; 26 obs tests still green). Proceeding to batch commit + draft PR. **L1+L2 → `completed`; flight stays `in-flight` (L3 held for operator).**

---

## Leg Progress

### L3 — full-working-day-run (interactive, in progress)
**Status**: in-flight (2026-06-02)

#### Findings (UI once-over + soak)

- **F1 (observability/robustness) — no operator-facing connector-connection signal.** At soak start, the operator DM'd the bot (from "Chuck R") and got no response. L1's disposition stream localized it instantly: **zero `connector.inbound` lines** (INFO-level, would show) + **zero Discord gateway activity** in the logs + connector `warm:false` + `GET …/discoverable-entities` 404ing on repeat → the **Discord gateway was disconnected** (bot "up" on HTTP but not connected to Discord; DM never reached `on_message`). Likely trigger: the L1/L2 source edits drove `uvicorn --reload`, dropping the live gateway connection, and nothing re-warmed it. **The product gap:** every UI surface still showed the connector as present/healthy (connectors list 200, no error badge) — the operator could only discover the bot was offline by messaging it. A daily driver needs a visible connection-status indicator ("connected / disconnected — Test Connection"). *Triage: candidate `ui-fix-*` (status surface) + a robustness question (does the connector auto-reconnect / auto-warm on boot, or only via manual Test Connection?). Disambiguate after re-warm.* **(L1's first real win — the instrumentation turned a silent "bot ignored me" into a precise "gateway disconnected" in one grep.)**

- **F2 (robustness, #19 BLOCKER — root cause of the "constant Test Connection") — the idle reaper disconnects the inbound gateway.** Confirmed in code: `_reap_once` (`_pool.py:448-478`) evicts ANY entry idle past `ttl_seconds` (default `_DEFAULT_TTL_SECONDS=1800`/30 min); eviction runs `plugin.disconnect(client)` (`:357`), closing the Discord Gateway WebSocket. `last_activity` is bumped only on `account_acquire` (inbound/outbound), and the pool treats eviction "uniformly" across gateway entries (`:26-28`) — **no exemption for the inbound listener**. So after ~30 min of quiet the gateway is reaped as "idle", the bot silently goes offline, and the next DM can't arrive (disconnected) until a manual Test Connection re-warms it. The acquire→idle→reap model fits per-agent *outbound* MCP clients; it is wrong for the account-keyed *inbound* gateway listener. **F1 is the symptom-hider (no status signal); F2 is the defect.** *Operator decision: click Test Connection to get through now; **create an injected fix leg** — requirements (verbatim): "this should not get reaped at all, and should fire itself up on restart."* → **Leg 04 `fix-gateway-idle-reap`** (substrate fix): (A) never idle-reap the inbound gateway listener (per-agent outbound entries still reap); (B) auto-warm listening connectors on lifespan startup; preserve dead-listener recovery. F1 (connection-status UI signal) tracked separately. This is the flight's adaptation-criteria "bot requires manual intervention → capture + fix + re-run" path; the soak resumes on a bot that stays up after this lands.

#### Leg 04 `fix-gateway-idle-reap` — design (Sonnet review, approve-with-changes)
- **Resolved:** (A) exempt ALL `_ACCOUNT_POOL_AGENT_SLOT` entries from idle-reap (every account entry IS the one gateway-listener entry per account — inbound + F4 send + F8 auto-relay share it; no pure-outbound account entry), gated on `is_alive()`. (B) boot warm-up ALREADY exists (`app.py:148-172`, ≥1-attached-agent gate) and fires on restart/reload — the operator's connector was cold purely because the F15 test agents were deleted; no flag/migration. **Dead-listener self-heal (HIGH):** removing idle-reap would strand a terminally-dead listener, so a liveness sweep must evict+immediately-rewarm dead account entries (~30s self-heal). Predicate at `_pool.py:469-474`; use the `_ACCOUNT_POOL_AGENT_SLOT` constant (`:255`). No `_discord.py` change. Proceeding to implementation (one design cycle — the review was prescriptive with code evidence).

#### Kickoff decisions (operator-confirmed)
- **Entry gate:** the `.env.hat` HAT connector IS the operator's daily driver (`58f1fe5a833f` "Discord Constellation"), so the formal HAT reconfig would disrupt the very thing being soak-tested. Decision: **skip the HAT reconfig; soak on the real daily-driver config.** F15 already proved the HAT green live. Substitute confirmation: verify L1's disposition stream is flowing on REAL traffic before the soak counts. Deploy model confirmed: dev bind-mounts + `uvicorn --reload --reload-dir /app/the_one` → L1's code is live (the `GET /api/connectors/{id}/disposition-counters` endpoint already serves the new shape).
- **UI once-over:** **co-walk** — operator clicks through each surface; FD watches the disposition logs + reasons about findings; each defect triaged live into an injected `ui-fix-*` leg or filed out-of-scope.

### L1 — connector-observability
**Status**: landed

#### Design notes
- Two design-review cycles (both Sonnet Developer). Cycle 1 (`approve with changes`) caught two HIGH issues: the inbound disposition vocabulary was wrong/incomplete — `command-intercepted` (`:693`/`:730`) was missing and `admitted` should be `stepped` (`:822`) to match the DB routing values; and `denied` is split across THREE `NeedsPairing` return sites (`:398-409`/`:418-431`/`:455-465`), not one. Also: pool-counter wiring is a non-issue (`_inbound.py:143` already imports from `_pool` → a module-level `record_disposition` slots in); outbound range is `:522-568` (success return included) with a second send path (`_send_ephemeral_followup` ~`:571`); a third silent drop exists (factory-unavailable `:956-964`). All incorporated.
- Cycle 2 (focused confirmation): disposition set + all wiring sites confirmed accurate, no new issues, no double-logging; two LOW cosmetic line nits fixed (send is `:523` inside the `try:` at `:522`; self-filter `:945-949`).
- Final vocabulary: inbound `stepped | command-intercepted | no-eligible | policy-silent | denied | dropped`; outbound `ok | rate_limited | error` — aligned to DB audit/routing values for grep-correlation.

#### Implementation (2026-06-02)

**Files changed:**
- `the_one/connectors/_observability.py` *(new)* — single shared disposition helper + vocabulary; emits one structured `connector.{inbound|outbound} account=… channel=… peer=… disposition=… [reason=…] [latency_ms=…] [retry_after=…] [error_type=…]` log line at INFO (DEBUG for `dropped`); calls `record_disposition` best-effort for counter increments.
- `the_one/connectors/_pool.py` — added `inbound_counters`/`outbound_counters` dict fields to `_RegistryEntry`; added `_CountersSnapshot` frozen dataclass; added module-level `record_disposition(account_id, kind, disposition)` (synchronous, no lock needed — asyncio single-thread model guarantees no concurrent mutation between await points); added `_get_account_counters_snapshot(account_id)` async snapshot function.
- `the_one/connectors/_inbound.py` — imported `log_disposition` from `_observability`; wired at all 10 inbound disposition sites: 3×`denied` (`:398-409`, `:418-431`, `:455-465`), 1×`no-eligible` (`:548` rule/default-exhausted), 2×`no-eligible` with `reason=pool-acquire-failure` (`:604`, `:619`), 2×`command-intercepted` with `reason=plugin|builtin` (`:693`, `:730`), 1×`policy-silent` (`:799`), 1×`stepped` (`:822`).
- `the_one/connectors/_discord.py` — added `import time`; imported `log_disposition`; wired outbound channel send with timer around `destination.send(content)` (`:522-568`); logs `ok`+`latency_ms` on success, `rate_limited`+`retry_after` before raising `ConnectorRateLimitError` (429 branch), `error`+`error_type` on Forbidden/NotFound/other HTTPException; wired ephemeral followup path to log `ok`+`reason=ephemeral_followup` on success, `error`+`reason=ephemeral_followup` on fatal exception; wired 3×`dropped` debug lines (bot-author, self, factory-unavailable) in `on_message`.
- `the_one/interfaces/web/api.py` — added `_ConnectorDispositionCountersResponse` model + `GET /api/connectors/{account_id}/disposition-counters` endpoint (mirrors discoverable-entities pattern; returns `{warm, inbound, outbound}`; degrades to `warm=False, inbound={}, outbound={}` when no warm entry; 404 for unknown connector).
- `tests/test_connectors_observability.py` *(new)* — 26 tests covering: line format + key=value pairs, inbound vocabulary (5 INFO + 1 DEBUG), outbound vocabulary (3 INFO), `record_disposition` counter increment (warm), `record_disposition` no-op (cold), `_get_account_counters_snapshot` snapshot pair (warm + cold), snapshot-is-copy invariant, API 404 / cold / warm paths, no-leak guarantee (structural + behavioral).

**Endpoint added:** `GET /api/connectors/{account_id}/disposition-counters`

**Deviation — `OutboundTarget` has no `peer_id` field**: the leg spec called for `peer_id` in outbound log lines, but `OutboundTarget` (the connector base Protocol's send-target shape) has no peer field — outbound targets are channel/thread destinations, not peer references. Outbound lines log `peer=None`. No spec change needed: the spec's intent (ids + disposition only, no content) is satisfied; `peer=None` is visible and accurate.

**Deviation — `record_disposition` not imported in `_inbound.py`**: the spec suggested importing it there "the same way `account_acquire` is imported". The helper is called from `_observability.py` (which handles the pool counter increment internally via a deferred import). Importing it directly in `_inbound.py` would be unused. Not imported — the spec's intent (counter increments on every disposition call) is fully satisfied.

**Metrics:** Full backend suite: **2861 passed / 4 skipped / 529 deselected** in 4:19 (wall). Prior baseline F16: 2835/4/528-529. Delta of +26 is the new test_connectors_observability.py.

#### Implementation (2026-06-02)

**Files changed:**
- `the_one/connectors/_pool.py` — rewrote `_reap_once` to split into two sub-sweeps: (A) idle-eviction sweep now exempts account-keyed (`_ACCOUNT_POOL_AGENT_SLOT`) entries whose `is_alive()` returns True (live gateway never reaped); (B) dead-listener sweep collects account-keyed entries where `is_alive()` is False or absent into `dead_evicted`, evicts them, and returns them separately. Added `_rewarm_dead_listeners(keys)` helper. Updated `_reap_loop` to call `_rewarm_dead_listeners(dead_listeners)` after each sweep, enabling self-heal within one reaper interval (~30s). Updated `_refresh_discoverable_entities_for_account` docstring comment to note that `last_activity` avoidance now matters only for per-agent entries (account entries are slot-exempt for idle eviction). Return type changed to `tuple[list[tuple[str,str]], list[tuple[str,str]]]` — `(idle_evicted, dead_evicted)`.
- `tests/test_connectors_pool.py` — updated three existing `_reap_once` call sites to unpack the new 2-tuple return (`idle_evicted, dead_evicted`); added three new tests: `test_alive_account_entry_survives_idle_past_ttl` (A — live gateway exempt), `test_dead_account_entry_is_evicted_and_rewarmed` (B — dead gateway evict+rewarm), `test_agent_acquire_entry_still_reaps_on_ttl` (C — no regression for per-agent entries).
- `tests/test_lifespan.py` — added `test_lifespan_warms_connector_with_attached_agent` (D — B-boot criterion: connector with ≥1 attached agent is warm-acquired at lifespan startup).
- `tests/test_connectors_e2e.py` — updated `_reap_once` call to unpack 2-tuple (no behavior change).

**Approach:**
- **(A) Idle-exemption:** In the new `_reap_once`, account-keyed entries check `getattr(entry.client, "is_alive", None)` — if the function exists and returns True, the entry is skipped entirely from both sweeps. Non-Discord plugins without `is_alive()` fall into the dead-listener path (safe: they get evicted+rewarmed rather than pinned).
- **(B) Dead-listener self-heal:** Account-keyed entries where `is_alive()` is False (or `is_alive` attr absent) are collected in `dead_evicted`, evicted via the same `asyncio.gather` pass as idle evictions, and then re-acquired via `_rewarm_dead_listeners` in `_reap_loop`. Self-heal window: one `_REAPER_INTERVAL_SECONDS` (30s default).
- **(B-boot) Confirmed:** `app.py:148-172` already warm-acquires every connector with ≥1 attached agent at boot. No changes needed; confirmed + tested by both the existing `test_lifespan_warm_acquires_connectors_per_account` and the new `test_lifespan_warms_connector_with_attached_agent`.

**Test names:**
- `test_alive_account_entry_survives_idle_past_ttl` — (A) alive account entry exempt from idle
- `test_dead_account_entry_is_evicted_and_rewarmed` — (B) dead account entry evict+rewarm
- `test_agent_acquire_entry_still_reaps_on_ttl` — (C) per-agent entries still reap on TTL (no regression)
- `test_lifespan_warms_connector_with_attached_agent` — (D / B-boot) boot warm-up confirmed

**Metrics:** Full backend suite: **2888 passed / 4 skipped / 529 deselected** in 4:15 (wall). Prior L2 baseline: 2884/4/529. Delta of +4: the four new tests from this leg.

**Deviations:**
- Return type of `_reap_once` changed from `list[tuple[str,str]]` to `tuple[list, list]`. The caller `_reap_loop` already discarded the return; three internal call sites in tests + one in `test_connectors_e2e.py` updated to unpack the 2-tuple. Kept the return value (rather than hiding it) for test purchase.
- Non-Discord plugins without `is_alive()` fall into the dead-listener path rather than being idle-exempt. This is the safer behavior: they get evicted and re-warmed rather than potentially being pinned alive with a broken client. The `getattr` guard is consistent with the leg spec.

#### Post-review hardening (2026-06-02)

Two non-blocking review findings addressed in a follow-up `fix-review-issues` pass:

**Finding 1 — `_rewarm_dead_listeners` must not resurrect a no-traffic connector.**
Previously `_rewarm_dead_listeners` called `account_acquire(account_id)` unconditionally for every dead entry. If all agents were detached from a connector after boot, the reaper would re-establish a gateway WebSocket on every 30s sweep even though no traffic would route through it. Fix: added an attached-agents gate (mirroring `app.py:148-172`'s lifespan warmup) using function-local `get_connection()` + `SQLiteAgentStore(conn).list_by_connector(account_id)`. If zero agents are attached, the entry is left cold with an INFO log; if ≥1 agent is attached, the rewarm proceeds as before. The store lookup runs outside `_lock` (in `_rewarm_dead_listeners`, which is called from `_reap_loop` after `_reap_once` releases the lock) — no deadlock risk.

**Finding 2 — a plugin without `is_alive()` must be EXEMPT, not churned.**
Previously the `_reap_once` comment said "non-Discord plugins without `is_alive()` are safe" but the logic treated them as dead (evicted + rewarmed every ~30s). Fixed: `is_alive_fn is None` now triggers an early `continue` (exempt path), just like `is_alive_fn()` returning True. Only an account entry that HAS `is_alive` and it returns False is treated as dead. Comment updated to state such plugins are exempt.

**Files changed (review fix):**
- `the_one/connectors/_pool.py` — `_reap_once`: split `is_alive_fn is None` into its own exempt `continue` branch before the `is_alive_fn()` live-check; updated comment. `_rewarm_dead_listeners`: added function-local `get_connection` + `SQLiteAgentStore` import; added `list_by_connector` check before `account_acquire`; logs INFO when leaving cold; logs INFO with agent count on successful rewarm.
- `tests/test_connectors_pool.py` — updated `test_dead_account_entry_is_evicted_and_rewarmed` to patch the DB layer (monkeypatch `get_connection` + `SQLiteAgentStore` in their source modules so the function-local import resolves the stub) and pass one attached agent; added `_patch_agent_store_for_rewarm` helper shared by rewarm tests; added `test_dead_account_entry_no_attached_agents_left_cold` (zero attached agents → evicted, NOT rewarmed); added `test_account_entry_without_is_alive_is_exempt` (no `is_alive` method → exempt, survives `_reap_once`).

**New test names:**
- `test_dead_account_entry_no_attached_agents_left_cold` — dead entry with zero attached agents stays cold
- `test_account_entry_without_is_alive_is_exempt` — liveness-less account entry survives both sweeps

**Metrics:** Full backend suite: **2890 passed / 4 skipped / 529 deselected** (prior: 2888/4/529; delta +2 from the two new tests). All pool + lifespan tests green (51 passed / 1 warning in 1.49s).

---

### L4 — fix-gateway-idle-reap (review hardening)
**Status**: landed (2026-06-02)

*(See the Leg 04 design + initial implementation embedded in the L3 section above. This entry captures the post-review hardening pass.)*

Two non-blocking review findings from the L4 batch review were addressed: (1) `_rewarm_dead_listeners` now gates on ≥1 attached agent before re-establishing a dead gateway (mirrors lifespan warmup; leaves zero-agent connectors cold); (2) account-keyed entries without an `is_alive` method are now EXEMPT from both sweeps (not churned into the dead-listener path every 30s). Two new tests added; existing rewarm test updated to patch the DB layer. Final suite: 2890/4/529.

---

### L2 — hat-driver-hardening
**Status**: landed

#### Design notes
- One Sonnet design-review cycle (`approve with changes`). Findings incorporated: (HIGH) `_BOT_IDS` is hardcoded in TWO files — `test_multi_user.py:53-57` AND `test_pairing_peers_decoupling.py:55-59`, both carrying identical **real Discord snowflakes committed to this public repo** — so the env-contract move also tightens anonymization; both files updated. (MEDIUM) the new `THE_ONE_HAT_BOT_USER_IDS` var must be an OPTIONAL `HatConfig` field with per-consumer local `pytest.skip` (NOT in `load()`'s required gate), else `test_smoke`/`test_multi_channel`/`test_multi_agent` would wrongly start skipping. (LOW) doc-scrub precision: stale `message_content` instructions are at `legs/03-…:60/:80/:95`; `flight-log.md:63` is already the authoritative correction. Adopted suggestion: export `routing_len(detail)` from `driver.py` for real CI coverage of the before/after logic.
- Confirmed: `driver.py` module import is side-effect-free w.r.t. creds (top-level `discord`/`httpx`/`HatConfig` only); pure helpers `latest_routing_entry`/`inbound_peer_names` import cleanly via `from tests.live.discord_hat.driver import …` (`--import-mode=importlib` + `pythonpath=["tests"]`); make target is `test-discord-hat`.

#### Implementation (2026-06-02)

**Files changed:**
- `tests/live/discord_hat/README.md` *(new)* — provisioning + run + constraints + timing rationale + scenario catalogue. Fully anonymized (no machine paths, no real snowflakes, no real ids). Covers: burner-bot provisioning in a normal browser (Message Content NOT needed on burners; only the-one's own bot needs it); how to find the-one's gateway bot user id; the `.env.hat` var contract + suite SKIPs without it; `wait_for_session(until=…)` timing rationale; `ingest_bots` connect-time-closure → container-restart requirement; bot-can't-DM-bot (REST 50007) constraint; scenario catalogue (5 scenarios).
- `tests/live/discord_hat/config.py` — added `_read_bot_user_ids()` + optional `bot_user_ids: list[str]` field (`field(default_factory=list)`, NOT in `load()`'s required gate).
- `tests/live/discord_hat/test_multi_user.py` — removed hardcoded `_BOT_IDS` tuple; added local `pytest.skip` when `cfg.bot_user_ids` is empty; all references now use `cfg.bot_user_ids[…]`.
- `tests/live/discord_hat/test_pairing_peers_decoupling.py` — same: removed hardcoded `_BOT_IDS`; local `pytest.skip`; references use `cfg.bot_user_ids[…]`.
- `tests/live/discord_hat/.env.hat.example` — added `THE_ONE_HAT_BOT_USER_IDS` (commented, with placeholder values) + explanatory comment about its optional nature and where to find bot user ids.
- `tests/live/discord_hat/driver.py` — extracted inline `_routing_len` closure (~`:500-503`) into exported `routing_len(detail: dict) -> int` function; `post_and_wait_new_routing` calls the extracted function (no behavior change).
- `tests/test_discord_hat_helpers.py` *(new)* — 23 hermetic unit tests (default suite, no marker) importing `latest_routing_entry`, `inbound_peer_names`, `routing_len` via `from tests.live.discord_hat.driver import …`. No creds, no network.
- `missions/11-discord-connector-depth/flights/15-live-traffic-hat/legs/03-multi-bot-hat-driver-foundation.md` — doc-lag scrub: ACs line 60 (`BotDriver` now says `Intents.default()`, not `message_content intent`); implementation guidance line 80 (`NOT message_content=True`, with rationale); edge cases line 95 (now explicitly warns NOT to use `message_content`). `flight-log.md:63` left unchanged (already correct).

**New env var:** `THE_ONE_HAT_BOT_USER_IDS` (comma-sep, optional, not in `load()`'s required gate).

**Test metrics:**
- Hermetic helpers: **23 passed** in 0.03s.
- Live-gate SKIP (no creds, `discord_hat` marker): **5 skipped, 0 errors**.
- Full default suite (`not browser and not live and not pixel and not requires_bwrap and not discord_hat`): **2884 passed, 4 skipped, 529 deselected** in 4:24 (wall). Delta vs L1's 2861: +23 (the new hermetic tests).

**Anonymization checks:**
- `grep -rnE '/home/|/Users/|C:\\Users' tests/live/discord_hat/README.md` → **CLEAN**.
- `grep -rnE '\b15111925[0-9]{10}\b' tests/live/discord_hat/*.py` → **CLEAN** (real snowflakes removed from both committed source files).

**Deviations:** none. The `field(default_factory=list)` approach was used instead of `None` + `__post_init__` for the optional `bot_user_ids` field — cleaner Python idiom, same behavior.

---

## Decisions

### Passive close of rate-limiting (#17)
**Context**: F17 was planned with a "rate-limiting realistic" half. Recon found the outbound 429 substrate is already correct (discord.py 2.4 pre-empts 429s via internal bucket sleeping; the-one types any escaped 429 as `ConnectorRateLimitError` with `retry_after` at `_discord.py:533`), and a single-operator daily driver is structurally unlikely to trip Discord's outbound limits (per-session lock + per-reply LLM latency space sends well under 5/5s/channel).
**Decision**: Drop the synthetic rate-limit stress harness. Instrument the outbound path (L1) so a 429/cascade is visible during the full-day run; close #17 on substrate-correct + a clean instrumented day; build backpressure only if a real cascade surfaces (a follow-on, not in-flight).
**Impact**: F17 shrinks to a 3-leg gate flight; no re-runnable synthetic 429 artifact ships.

### Criterion #18 descoped from M11
**Context**: #18 (a never-seen-it operator does onboarding in <15 min) is an end-of-mission operator-performed validation, like #19.
**Decision**: Operator chose to descope #18 from the mission entirely. F17 does not own it.
**Impact**: Recorded in mission.md; the mission's remaining operational gate is #19 (full-day robust), owned here.

---

## Deviations

_(none yet)_

---

## Anomalies

_(none yet)_

---

## Session Notes

- **2026-06-02** — Flight planned via `/flight`. Context loaded (mission, ARTIFACTS, F15 + F16 debriefs). Recon (read-only sweep) confirmed: outbound 429 handling correct, reconnect/liveness solid, but **zero outbound metrics / no inbound-disposition on stdout** — the observe-premise gap L1 closes. Decisions captured above + in flight.md Design Decisions.
- **2026-06-02** — Architect design review (Phase 5b, Opus): **approve with changes** (no rework). Two sharpening corrections folded into flight.md: (1) L1's "no record exists today" premise was overstated — most inbound dispositions ARE in DB `session_metadata`; the real gap is they're not on the `docker logs` stdout stream a soak greps (+ two by-design silent noise filters untraced). L1 reframed as a **log-projection/consolidation** leg. (2) Counter read surface pinned to the pool `_RegistryEntry` snapshot path (mirroring discoverable-entities), **not** the doctor probe (which has no pool-state access). Plus cite fixes (429 `:533-554`; `is_alive` `:398-413`; reconnect `~:1099-1220`), the env-seam test constraint note, the counter reset-on-eviction limitation, and confirmation that `.env.hat` already exists. Architect-confirmed sound: passive #17 close, L2 hardening bundle, L3 prereqs, leg ordering, mission-constraint compliance. Changes were the reviewer's own prescriptions (clarifications, not new design) → no second cycle warranted.
- **2026-06-02** — Operator scope addition (pre-authorized): L3's full-working-day run now includes a **deliberate once-over of every UI surface**. Findings are EXPECTED to spawn injected `ui-fix-*` legs mid-flight — the Flight Director is to absorb and sequence them per the `/agentic-workflow` mid-flight-adaptation protocol *without relitigating flight size*. Captured in flight.md: Objective, Contributing-to-Criteria (#1–4 opportunistic validation + stale-checkbox reconciliation), L3 leg, an injected-leg placeholder, Adaptation Criteria (injected legs pre-authorized; only substrate-re-architecture / new-criterion findings get filed as follow-ons instead), and Checkpoints. The UI sweep also doubles as the occasion to verify #1–4 are genuinely satisfied.
