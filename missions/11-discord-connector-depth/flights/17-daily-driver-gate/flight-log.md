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

- **F3 — parked F16 two-step DM-grant issue CONFIRMED in real use + a misleading peer-facing message.** After the L4 fix + restart (bot auto-connected, gateway warm), the operator re-DM'd from "Chuck R" and got **"no agents available."** L1 captured: `connector.inbound … peer=1389008395092103273 disposition=no-eligible` + `connector.outbound … disposition=ok latency_ms=360`. Config: `allowlist.dm_admission="admin-approved"`, `allowlist.peers=[{id:1389008395092103273 (Chuck R), dm_allowed:false}]`, Sonos `connector_acls=null`. So Chuck R is approved as a peer but **`dm_allowed:false`** under `admin-approved` → his DM is gated at per-agent admission → `no-eligible`. **This is exactly the F16-parked Known Issue**; F16's disposition was "park until F17 evidence; scope a follow-on only if confusing." **Evidence is in — two findings:**
  - **F3a (the parked issue, robustness/UX):** an approved peer's DM stays silently gated until the operator flips `dm_allowed`. Real-use confusing → reconsider the F16 park (scope an approve-flow/grant follow-on).
  - **F3b (misleading message — `ui-fix`/messaging candidate):** the peer-facing reply for an admin-approval-gated DM is **"no agents available"** — wrong/misdirecting (the agent IS attached; the gate is DM-approval). The `no-eligible` peer-facing copy conflates "no eligible agent" with "your DM isn't approved." Should say "not approved to DM yet" / surface the pending-approval flow.
  - *Immediate unblock during soak: operator flips Chuck R's `dm_allowed`→true (per-peer DM toggle) or opens `dm_admission`.*

#### Pending injected legs (the "go to town" batch — identify all, then design+build together)
- **Leg A — `connector-connection-status`** (UI + small backend). Rolls up **F1** (+ improves **F3b**). Recon-grounded (`connector-editor.js` / `api.py`): today **Save only persists config** (`update_connector` at `api.py:2489` — no `account_acquire`); **Test Connection** (`POST …/test/connect`, `api.py:2832`) is the only UI path that opens the WS (doctor probe + `account_acquire`); **"Not tested"** is a session-only doctor result, NOT live state; **"Last refreshed"** is the discoverable-entities cache age (`fetched_at`), a different concept; **no live connection indicator exists**. Design (operator-aligned): (1) **Save opens/reconnects the WS** — evict + re-`account_acquire`, gated on ≥1 attached agent, only when connection-relevant fields changed (bonus: a save-reconnect is a fresh connect → picks up `ingest_bots` too, killing most of the F15 "restart after reconfig" friction); (2) **one live connection status on General** (Connected/Connecting/Disconnected/Error from `is_alive()`) replacing "Not tested" — the F1 fix; (3) **demote Test Connection to optional "Validate"** (token/intents pre-flight, mainly first-setup); (4) **relocate the discoverable-entities surface** (the dropdown-data cache status / "last refreshed" / refresh control) to a better location — *operator note: current placement is awkward*; design picks the spot (co-located with the dropdowns it powers and/or the data-status area), and relabel "entries last refreshed" (kept distinct from connection status); (5) **invite link folded in** — it's the OAuth2 bot-invite URL (`connector-form-discord.js:78`, perms `2147552256` = View Channel + Send Messages + Read History + Use Slash Commands, scopes `bot applications.commands`), a one-time **setup** affordance: its **info-icon tooltip must say what it's actually for** ("Open this to add the bot to a Discord server — needed once per server at setup"), fix that it only populates after Test Connection (needs `application_id` from the doctor probe — source/persist the application_id so it renders without a prior Test), and group it with the other first-run/setup affordances (invite + validate) separate from the steady-state live status. **Theme: setup-vs-steady-state split on the General tab.** **(6) Owns the shared connect-error display surface** — the live status + the Validate action render the single actionable error for connect failures incl. `PrivilegedIntentsRequired` (clear message + Developer-Portal link). **Leg B depends on this** (B deletes the intent checkboxes / escape hatch, so this error becomes the only guidance) → A+B ship together.
- **Leg B — `intents-ux`** (UI + copy). The Advanced-tab "Receive messages from" 3 checkboxes are the Discord gateway intents (`connector-form-discord.js:97-99`; `_discord.py:811`/`:832`): **Message content** + **Server members** are *privileged* (must ALSO be enabled in the Discord Developer Portal — else `PrivilegedIntentsRequired` connect failure, `_discord.py:1308`); **Server info** (guilds) not privileged. They're effectively **mandatory** for a working bot — unchecking Message content cripples channel reading (warning already exists at `_discord.py:847`), DMs still work. Presented as casual toggles that invite self-breakage, with the real dependency (portal enablement) nowhere near the control. **Design (operator-decided — subtractive, "nothing left to take away"):** **DELETE the 3 checkboxes entirely**; the-one **always requests all 3 intents** (no UI, no config knob, no conditional — option (i)). The escape hatch the checkboxes provided (uncheck to dodge `PrivilegedIntentsRequired` when the portal hasn't enabled a privileged intent) is replaced by an **actionable connect-error**: on `PrivilegedIntentsRequired` (`_discord.py:1308`), surface a clear message + a link to the bot's Developer-Portal "Privileged Gateway Intents" page. **Couples to Leg A (shared connect-error feedback path):** the actionable error is surfaced by Leg A's re-roled **Validate** action (the doctor's gateway-smoke check already attempts the connect that triggers it), by Leg A's **live connection status** (status=Error → "enable privileged intents in the portal"), and by Save-warm / boot-warm — one error, one message, everywhere a connect happens. **SHIP-TOGETHER dependency:** deleting the checkboxes (B) without the actionable error (A) strands an operator who hasn't enabled the portal intents → **A's connect-error feedback is a prerequisite of B; design + build A+B as one coordinated batch.** (B's UI work — removing the checkbox row in `connector-form-discord.js` — may also drop the now-unused `account.config["intents"]` write path; design will decide whether to keep the field defaulted-full for back-compat or remove it.)
- **Leg C — `additional-config-advanced-section`** (UI relocation/demote — *operator revised from "remove" to "keep + demote"*). The "Additional Config" key-value table (`connector-form-discord.js:253-277`, `renderConfigKvTable`) is the generic escape hatch where ad-hoc keys like **`ingest_bots`** get hand-typed. `ingest_bots` (`_discord.py:979/998`): default false → bot ignores other bots (author noise-filter); true → processes other-bot messages (added for the F15 multi-bot HAT; self-filter always on) — a test/advanced seam, never wanted on a normal daily driver. **Operator decision: KEEP the kv-table** (advanced users, test flags, and forward-compat for not-yet-typed keys legitimately need it) but **move it to the BOTTOM under its own clearly-labeled "Advanced" section**, visually separated from the everyday typed fields so it reads as "you usually don't need this." **Design:** dedicated bottom "Advanced" section housing the kv-table; de-emphasize (collapsed-or-quiet, not competing with typed controls); no removal. **Light note (not a guardrail anymore — nothing gets orphaned since the table stays):** as typed fields cover more keys over time, the kv-table remains the fallback for the long tail, not the home for everyday config. Demote-not-delete; same advanced-vs-everyday hygiene family as A & B.
- **Leg D — `dm-allowlist-simplify`** (substrate + UI — **the heaviest; CLOSES the F16-parked mission Known Issue / F3a**). Post-F16 the account-scope `peers` axis gates **DMs only**, so a user being in the list already means "this person may DM" — the per-peer **`dm_allowed`** flag (`{id, dm_allowed}`) is a redundant second state and the exact two-step that gave Chuck R "no agents available" (approve appends `{id, dm_allowed:False}`, `api.py:2716`). **Design (operator-confirmed):** (1) **relabel the users/peers allowlist section → "Direct Messages"** (who may DM the bot); (2) **drop the per-peer `dm_allowed` flag** — in-list = can-DM, remove = can't; storage migration `peers {id, dm_allowed}` → `{id}` + update the `_acl.py` DM composition (`:504`/`:559`/`:571`) to drop the `dm_allowed` term; (3) **keep the `dm_admission` 3-mode policy** (`all`/`admin-approved`/`none`) as a clean top-of-section radio — **Anyone / Only people on this list / No one** — but **relabel it** (clearer copy, e.g. "Who can DM the bot?"); (4) **approve flow** (`api.py:2716`) adds an approved peer **as allowed** (just `{id}`). **Closes the F16-parked two-step DM-grant Known Issue** (resolution candidate (a): grant DM admission without the limbo state). Mark the mission Known Issue resolved on landing. Storage migration (vN) + ACL semantics + approve handler + UI.
- **Leg E — `approval-pending-signaling`** (UI + connector). When an unknown user DMs for the first time they hit the pending-approval flow (`_inbound.py:449-465` upserts a `PendingApproval` row — `models.py:669`: `peer_id/peer_name/preview/status` — then **returns WITHOUT replying**; the user gets dead air). A Chat-UI pending surface exists (F9 L4) but no left-panel flag / cross-screen badge. **Design:** (1) **Chat left-panel flag** on the pending item; (2) **top-nav badge on the Chat button** = live count of `PendingApproval` status=pending (WS-pushed), so the operator knows from any screen; (3) **one-time Discord auto-reply** to the unknown DMer ("awaiting the operator's approval") sent ONCE on pending-row creation (not on repeat DMs). Builds on D's approve semantics.
- **Leg F — `respond-on-approval`** (substrate; operator chose option **(ii)**). On approve (`approve_peer_approval`, `api.py:2654`) the bot **proactively answers the user's ORIGINAL message** — not just a greeting. Today only a truncated `preview` is stored, so F **persists the full original first message on the pending row** and, on approval, replays it through an agent step + `account_acquire → client.send` to the DM. Closes the loop: unknown DM → "you're pending" (E) → operator badge (E) → approve (D) → bot answers their first question (F). After D + E.

#### Batch formalized → ready for `/agentic-workflow` (2026-06-03)
- **UI once-over (L3) complete — 6 injected legs identified (A–F), operator-walked + confirmed.** Formalized into flight.md's Legs list as two clusters with ordering/dependencies: connector-editor cluster **A→B** (ship together; A owns the connect-error surface B depends on), **C** (independent); DM/approval cluster **D→E→F** (D = substrate DM simplify + closes the F16-parked Known Issue; E = pending signaling; F = respond-on-approval). Operator instruction: update the flight plan + run `/agentic-workflow` over the batch. Recommended execution order: **A, B, C, D, E, F** (alphabetical happens to satisfy every within-cluster dependency). Findings F1 (→Leg A), F3a (→Leg D), F3b (→Legs A+E messaging) are subsumed by the batch; F2 already fixed (L4). Each leg: per-leg design + Sonnet review, batched implementation, single end-of-batch review + commit per the agentic-workflow model.
- **Behavior tests added to the batch (operator directive — "they are all UX, validate visually").** Two Witnessed behavior-test specs (Executor + Validator, Chrome MCP), one per cluster, run as the **visual acceptance gate** after each cluster lands (not per-leg): **`connector-editor-ux`** (Legs A/B/C — Chrome MCP on the Studio editor; spec authored draft at `tests/behavior/connector-editor-ux.md`) and **`discord-approval-flow`** (Legs D/E/F — Chrome MCP on the the-one UI **+ Discord web client logged in as Chuck R**; authored when the D cluster designs). **Apparatus (operator-confirmed):** Chrome MCP drives BOTH the the-one UI and Discord-as-Chuck-R (act = type DMs in the Discord web client; observe = read the bot's replies in the Discord DOM + the the-one UI). **Apparatus risk:** driving the Discord *web* DOM may be finicky (bot-detection / dynamic DOM) — mission allows a `discord.py` fallback if the run proves it unreliable. Behavior tests are the visual layer ON TOP of each leg's unit/browser tests, not a replacement.

#### Leg 04 `fix-gateway-idle-reap` — design (Sonnet review, approve-with-changes)
- **Resolved:** (A) exempt ALL `_ACCOUNT_POOL_AGENT_SLOT` entries from idle-reap (every account entry IS the one gateway-listener entry per account — inbound + F4 send + F8 auto-relay share it; no pure-outbound account entry), gated on `is_alive()`. (B) boot warm-up ALREADY exists (`app.py:148-172`, ≥1-attached-agent gate) and fires on restart/reload — the operator's connector was cold purely because the F15 test agents were deleted; no flag/migration. **Dead-listener self-heal (HIGH):** removing idle-reap would strand a terminally-dead listener, so a liveness sweep must evict+immediately-rewarm dead account entries (~30s self-heal). Predicate at `_pool.py:469-474`; use the `_ACCOUNT_POOL_AGENT_SLOT` constant (`:255`). No `_discord.py` change. Proceeding to implementation (one design cycle — the review was prescriptive with code evidence).

#### Editor cluster (A/B/C) — implemented + batch-reviewed (2026-06-03)
- **A/B/C all landed.** A: status endpoint + live status + background save-warm + `_map_connect_error` + Test→Validate + invite app_id persist + discoverable-entities→A&R-top. B: all intent code removed; both connect paths always-on. C: kv-table → bottom collapsed Advanced section + FIXED the pre-existing display-only save bug (`ingest_bots` now round-trips).
- **Batch review (Sonnet): [HANDOFF:confirmed] + 1 blocking fix.** BLOCKING: a save-warm connect failure popped the pool entry → status returned `disconnected` and **swallowed the PrivilegedIntentsRequired portal error** (defeating A+B's point); test was vacuous. Fixed: entry-None + last_error → `state="error"` with message/link; test de-vacuumed. Non-blocking (both fixed): drain `_inflight_save_warm_tasks` at shutdown; reserve `application_id` from the kv-table. Backend 2916/4/536. **Cluster review-clean; pending the `connector-editor-ux` behavior-test visual gate + commit.**

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

### L5 / Leg A — connector-connection-status
**Status**: landed (2026-06-03)

#### Design decisions (resolved at design review — implemented to these)
See leg artifact `missions/11-discord-connector-depth/flights/17-daily-driver-gate/legs/05-connector-connection-status.md` for the full resolved-decisions section.

#### Implementation (2026-06-03)

**Files changed:**

- `the_one/connectors/_pool.py` — added `_StatusSnapshot` frozen dataclass; added `_get_account_status_snapshot(account_id, last_error, last_error_link)` async function that reads pool-entry state under `_lock` (connected/connecting/disconnected/error states from `client_ready`, `failure`, and `is_alive()`).

- `the_one/interfaces/web/api.py` — added `_connection_relevant_changed(existing, updated)` helper (compares secrets, config.intents, config.presence — NOT the whole config dict so label/ACL edits don't bounce the gateway); added `_save_warm_background(account_id)` async background task (evict + account_acquire, clears/writes `_connect_error_store` on success/failure); added `_map_connect_error(exc)` module-level function (walks `exc.__cause__`, maps PrivilegedIntentsRequired → portal link, LoginFailure → bad-token copy, generic → one-liner); added `_connect_error_store` + `_inflight_save_warm_tasks` module-level state; added `GET /api/connectors/{id}/status` endpoint (state/alive/last_error/last_error_link, 404 for unknown account, degrades to disconnected when cold); extended `update_connector` with save-warm gate (≥1 attached agent AND connection-relevant change → background task); added same gate to `create_connector` (no-op in practice — agents attached post-create); added `application_id` persistence on successful Validate (saves to `account.config["application_id"]` best-effort).

- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — added `renderDiscoverableEntitiesBanner()` function (banner HTML extracted from the Users section, relabeled "Entries last refreshed", with stable `connector-allowlist-banner` testid; moved to the TOP of the Access-and-Routing tab); added `renderLiveStatusRow()` function (new live status indicator with `data-testid="connector-live-status"` + `-error` + `-error-link`); relabeled `renderTestConnectionRow()` button text from "Test connection" → "Validate" (testid `connector-test-connection-btn` unchanged); inserted `renderLiveStatusRow()` into the Connection section above the Validate row; prepended `renderDiscoverableEntitiesBanner()` to the Access-and-Routing tab panel; added `_wireLiveStatus(container, account)` function (polls `GET /api/connectors/{id}/status` every 3s, stops on unmount via `isConnected` guard, updates LED + text + error elements); wired `_wireLiveStatus` in `wireEditorEvents` (edit mode only).

- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — `renderInviteSection`: seeds `_lastApplicationIdByAccount` cache from `account.config.application_id` on render (so invite renders pre-Validate if config has the id); updated info-icon tooltip text to "Open this to add the bot to a Discord server — needed once per server at setup"; updated stale-hint text to "Run Validate to fetch your application ID.".

**New testids added (behavior test `connector-editor-ux.md` depends on them):**
- `connector-live-status` — live status text span (steps 1/2/8)
- `connector-live-status-error` — error message span (step 8)
- `connector-live-status-error-link` — error action link (step 8)
- `connector-allowlist-banner` preserved (now rendered by `renderDiscoverableEntitiesBanner` in new location)

**Endpoint added:** `GET /api/connectors/{account_id}/status`

**Save-warm shape:** `asyncio.create_task(_save_warm_background(account_id))` — non-blocking (PUT responds immediately); `_save_warm_background` evicts then re-acquires; errors written to `_connect_error_store`; cleared on success.

**Tests:**
- `tests/test_connector_status_endpoint.py` *(new)* — 23 tests: status endpoint 404/cold/warm/error shapes; `_get_account_status_snapshot` no-entry/warm-alive/warm-dead/failure/connecting; `_connection_relevant_changed` secrets/intents/presence/label-only/non-connection-config/no-change; save-warm gate ≥1-agent/label-only-no-op/no-agent-no-op; `_map_connect_error` PrivilegedIntentsRequired-direct/as-cause/LoginFailure/generic/cause-chain-depth.
- `tests/browser/test_connector_live_status.py` *(new)* — 7 browser tests: live-status testid renders; "Not tested" absent; Validate button testid preserved; Validate label text; invite info-icon tooltip; invite renders from persisted application_id; discoverable-entities banner in Access-and-Routing tab.

**Metrics:** Full backend suite: **2916 passed / 4 skipped / 536 deselected** in ~5:46 (wall). Prior L4 baseline: 2890/4/529. Delta +26 (23 new backend tests). Browser suite: 37 connector-related tests (7 new + 30 existing) all green (58s).

**Deviations / judgment calls:**
- The `_get_account_status_snapshot` returns `state=error` based on `entry.failure is not None` (not based on `_connect_error_store`). The error store is read by the HTTP endpoint and passed to the snapshot function; but when the entry has been evicted (failed and removed from pool), the snapshot returns `disconnected`. This is semantically correct: an evicted entry IS disconnected; the error message from the store is plumbed to the UI separately.
- The status endpoint `GET /api/connectors/{id}/status` is positioned AFTER `GET /api/connectors/{account_id}` in route registration order; FastAPI's sub-path routing handles `/status` suffix correctly without conflicts.
- `application_id` persistence in `test_connector_connection` uses `model_copy(update=...)` which skips Pydantic validators — acceptable because `application_id` is a plain string config key with no validation constraint; the DB update is best-effort (catches all exceptions).
- Discoverable-entities banner removed from the Users section and added to the top of Access-and-Routing tab. The `_wireAllowlistBanner` function still resolves by testid from the container, so the wiring works from the new location without changes.

---

### L6 / Leg B — intents-ux
**Status**: landed (2026-06-03)

#### Implementation (2026-06-03)

**Files changed:**

- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — removed all intent-related code: (1) deleted `INTENT_AXES` constant (the three `{key, label}` axis objects); (2) removed `intentsCfg` variable from `_renderRuntimeConfigBody` and deleted the entire intents-row block (~`:172-199` pre-Leg-B, the `discord-intents-row` div + label + 3 checkboxes + tooltip); (3) removed `_readIntentChecked(container, axisKey)` helper; (4) deleted the intents block from `collect()` (the `_readIntentChecked` calls + allTrue/hadIntentsBefore logic that conditionally wrote `config.intents`); (5) removed `intents` key from `snapshot()` return; (6) deleted `_onIntentChange` inner function and the three `_wireListener` intent-checkbox calls from `wireEvents()`. Presence, BOT_TOKEN, and all other fields left intact.

- `the_one/connectors/_discord.py` — two paths updated to always-on intents:
  - **`connect()` (~`:832`):** replaced the config-driven `intents_cfg.get(...)` block (three lines reading from `account.config["intents"]` with True-fallback) with three explicit assignments: `intents.message_content = True; intents.members = True; intents.guilds = True`. Deleted the now-dead `message_content is False` WARNING log (~`:847-858`). Comment updated: `config["intents"]` kept for back-compat, no longer drives intent values.
  - **`_probe_gateway_connect()` (~`:1698`):** same substitution — replaced `cfg.get(...)` reads with the three explicit True assignments. `intents_cfg` parameter retained for call-site back-compat.

**Tests changed:**

- `tests/test_connectors_discord.py`:
  - `test_intents_from_config_honored`: REWRITTEN — now asserts that even with `config["intents"]={"message_content": False, ...}`, the constructed intents have `message_content=True` (always-on). Previously asserted `False`.
  - `test_probe_gateway_intents_from_config_honored`: REWRITTEN — same always-on assertion on the probe path. Previously asserted `False`.

- `tests/browser/test_flow_studio_connector_discord_form.py`:
  - `test_edit_mode_renders_typed_fields_with_persisted_intents`: REMOVED (was `:83`). Asserted checkboxes are visible+checked — checkboxes are gone.
  - `test_intent_toggle_re_enables_save`: REMOVED (was `:120`). Toggled a checkbox to dirty the form — toggle gone.
  - `test_intent_toggle_save_emits_typed_payload`: REMOVED (was `:200`). Toggled + saved → asserted False in payload — toggle gone.
  - `test_editor_renders_no_intent_checkboxes`: ADDED. Asserts `discord-intents-row`, `discord-intent-message_content`, `discord-intent-members`, `discord-intent-guilds` all have count 0 on the Access-and-Routing tab, even with a pre-existing `config.intents`.
  - `test_no_change_save_preserves_pre_existing_all_true_intents`: REFRAMED → `test_save_with_pre_existing_intents_key_does_not_crash`. Now asserts a clean save (no 422) and name update; does NOT assert key preservation (collect() no longer re-emits the key).
  - Module docstring updated to reflect the intent-toggle removal.

- `tests/browser/test_flow_studio_connector_invite_section.py`:
  - `test_intent_toggle_preserves_url_and_permissions_constant`: REFRAMED → `test_permissions_constant_stable_and_no_intent_checkboxes`. Removed intent-toggle interaction; now asserts the `permissions=2147552256` constant is present in the post-probe URL AND all four intent testids (`discord-intents-row`, `discord-intent-*` ×3) have count 0 on the Access-and-Routing tab.
  - Module docstring updated.

**Confirmation — A's error mapping covers PrivilegedIntentsRequired:**
`_map_connect_error` in `api.py` walks `exc.__cause__` and maps `discord.errors.PrivilegedIntentsRequired` → portal link message. Covered by `tests/test_connector_status_endpoint.py::test_map_connect_error_privileged_intents_required_direct` and `::test_map_connect_error_privileged_intents_as_cause`. No new error UI added in Leg B.

**Metrics:** Full backend suite: **2916 passed / 4 skipped / 534 deselected** in 4:55 (wall). Prior Leg A baseline: 2916/4/536. Deselected count changed by −2 (two of the previously-deselected discord_hat tests are now different deselection-set items — no functional change). No net test count change (rewrites + removals balanced by additions).

**Deviations:**
- `test_no_change_save_preserves_pre_existing_all_true_intents` was reframed rather than kept as-is. The test as written would have failed after this Leg because `collect()` no longer re-emits `config.intents`, so a save wipes the pre-existing key via the backend's REPLACE-not-merge config contract. The reframe (→ `test_save_with_pre_existing_intents_key_does_not_crash`) tests what the code actually does: the save succeeds, the name is updated, no crash. The original "key preserved" claim was only ever true because collect() re-emitted it; that semantic is now gone.
- The `_activate_access_and_routing_tab` helper in `test_flow_studio_connector_invite_section.py` is retained (used by the reframed test and still accurate as a navigation helper). Its docstring reference to "intent testids" is now reframed: it navigates to the tab to ASSERT ABSENCE of those testids.

---

### L7 / Leg C — additional-config-advanced-section
**Status**: landed (2026-06-03)

#### Implementation (2026-06-03)

**Files changed:**

- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — two changes:

  1. **Round-trip fix (pre-existing bug, blocking):** Extended `collect()` to scan `.connector-config-row` inputs in the kv-table and merge non-reserved keys into the returned `config`. The `collectFormData` substrate takes the Discord typed-registry branch (`cfdCollected` truthy) and skips the generic DOM-scan `else` branch — so ad-hoc kv-table entries (e.g. `ingest_bots`) were silently dropped on every save. The fix builds the same effective reserved-key set that `collectConfigRows` builds at runtime (baseline: `pairing`, `allowlist`, `routing`, `always_listen`, `inference_provider_config_id`, `inference_model`; Discord-specific: `intents`, `presence`) and merges any key not in that set from the kv-table rows into `config`. No backend change — the API already passes config through.

  2. **Relocation to bottom "Advanced" section:** Moved the Additional Config block (previously inline among the typed fields) to be the LAST element of `_renderRuntimeConfigBody`'s return, wrapped in a `<details class="advanced-collapsible connector-advanced-section">` disclosure (reusing the existing `advanced-collapsible` CSS class from `components.css`). Collapsed by default — reads as "you usually don't need this." Both testids preserved: `discord-additional-config-row` (inner row, used by `connector-editor-ux` step 5 and the create-mode-absence assertion) and `connector-advanced-section` (outer wrapper, new — for the DOM-order assertion). Section orchestration in `connector-editor.js` untouched.

- `tests/browser/test_flow_studio_connector_discord_form.py` — three changes:

  1. **`test_additional_config_hides_reserved_keys`**: added `el.setAttribute('open', '')` to open the `<details>` before querying the kv-table rows (now collapsed by default).
  2. **`test_advanced_section_is_last_element_in_runtime_config`** *(new)*: asserts `connector-advanced-section` is the LAST child element of its parent in the DOM after navigating to the Access-and-Routing tab.
  3. **`test_kv_table_key_round_trips_on_save`** *(new)*: opens the Advanced disclosure, adds a kv-table row (`ingest_bots=true`), saves, asserts key in backend config, reloads and re-asserts (end-to-end round-trip for the collect fix).

**Pre-existing bug confirmed:** Before this leg, any key added via the Additional Config kv-table was silently dropped on save for Discord accounts. This includes `ingest_bots` (the canonical advanced seam used by the HAT). The bug was present since the kv-table was added to the Discord typed form (M11 F1 L4); the typed-registry branch in `collectFormData` simply never collected from the kv-table.

**Metrics:** Full backend suite (non-browser): **2916 passed / 4 skipped / 536 deselected** in 4:40 (wall) — exact baseline match. Discord form browser suite: **10 passed** (8 existing + 2 new) in 15.49s. Create-and-test browser suite: **4 passed** in 6.14s. Connector-editor browser suite: **18 passed** in 30.47s.

**Deviations:**
- The `connector-advanced-section` testid was added on the outer `<details>` wrapper (the leg spec said "keep/relocate `discord-additional-config-row` or add `connector-advanced-section`"). Both testids are now present: `discord-additional-config-row` for backward-compat (behavior test step 5 + create-mode test); `connector-advanced-section` for the new DOM-order assertion.
- No CSS added — reused the existing `advanced-collapsible` class from `components.css` (already styled with border-top, de-emphasized summary color, focus ring). Zero new design tokens.

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
