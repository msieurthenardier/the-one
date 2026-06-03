# Flight: Daily-driver validation gate (full-working-day run + connector observability)

**Status**: in-flight
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [ ] **#19 — survives a full working day of daily-driver use without operator intervention** (no manual restarts, no token re-decryption issues, no stuck sessions, no silently-dropped inbound). The mission's operational definition of "robust"; this flight is its validation gate.
- [ ] **#17 — outbound rate-limiting + backpressure under live load** — closed *passively* here: the existing 429 substrate is correct (code-verified, see Design Decisions) and a single-operator daily driver is structurally unlikely to trip Discord's outbound limits; the full-working-day run is instrumented to catch a 429 cascade if one occurs. **Backpressure substrate is built only if the run surfaces a real cascade** (the mission's own "build only if cascades surface" framing) — otherwise #17 closes on substrate-correct + clean-instrumented-day.
- [ ] **#11 (durability) — the committed HAT artifact** stays `[~]` (pairing / DM-isolation remain inherently human), but this flight hardens it into a maintainable, documented, CI-net-covered suite so future Discord-touching flights can rely on it as a regression gate.
- [ ] **#1–4 (Discord-shaped UX) — opportunistic validation.** The L3 full-UI once-over walks the creation form, allowlist + routing dropdowns, detach, and audit-log inspector live — an occasion to confirm these criteria are genuinely satisfied (reconciling the stale `[ ]` checkboxes flagged at planning) and to surface any residual surface defects as injected `ui-fix-*` legs. Not the flight's headline, but its natural by-product.

> *(Numbering: F17 was the planned daily-driver gate. Its original "rate-limiting realistic" half is descoped to passive observation per the recon — see Design Decisions. The optional alignment flight stays F18.)*
> *(Mission scope change agreed at this flight's planning: **criterion #18 (a never-seen-it operator does onboarding in <15 min) is descoped from M11** — operator decision. Recorded in mission.md.)*

---

## Pre-Flight

### Objective

Validate that the Discord connector is a connector the operator trusts to **leave running** — by (1) building the lightweight observability the runs need to be *assertable* rather than anecdotal, (2) hardening the committed live-traffic HAT driver into a maintainable regression gate, and (3) running the bot as a daily driver across a **real full working day** — paired with a deliberate **once-over of every UI surface** — and confirming it stays up and coherent with no operator intervention. The headline gate is mission criterion #19; rate-limiting (#17) is watched passively through the same instrumentation, with backpressure built only if a real cascade surfaces. The UI once-over is expected to surface latent surface defects that become injected `ui-fix-*` legs — that scope growth is the intended shape of this flight, not creep.

### Open Questions

- [x] **Should F17 actively stress-test outbound rate-limiting (synthetic 429 harness)?** → **No (passive).** Recon: discord.py 2.4's internal bucket limiter does *pre-emptive* sleeping (slows sends rather than 429-ing); the-one correctly types any escaped 429 as `ConnectorRateLimitError` with `retry_after` (`_discord.py:533-554`; no retry/backoff wrapper around `destination.send`, `:522-554` — Architect-confirmed). The per-session lock + per-reply LLM latency naturally space the bot's outbound to well under Discord's 5-msgs/5s-per-channel — a single-operator daily driver won't trip it, and manufacturing a synthetic 429 is high-effort/low-yield against a condition real use won't hit. Watch passively during the full day; build backpressure only on a real cascade. *(Operator-confirmed.)*
- [x] **Where does criterion #18 (15-min onboarding walkthrough) go?** → **Descoped from M11** (operator decision). Removed as an active gate; this flight does not own it.
- [x] **What observability surface do the runs read?** → **A unified, greppable stdout disposition stream** (via `docker logs`, building on F15 L1's connector-log-to-stdout wiring) as the *binding* evidence surface, plus **light per-account in-memory counters** for at-a-glance aggregates. **Reframed after Architect review:** most inbound dispositions are *already* recorded in DB `session_metadata["audit"]`/`["routing"]` (`_inbound.py` deny `:398-409`, no-eligible/pool-failure `:547-625`, policy-silent `:797-815`) — but the DB arrays are NOT on stdout, so an 8-hour soak has no single stream to grep. L1 is therefore a **log-projection/consolidation** leg (project each existing disposition onto one stdout line), **not** a "build the missing record" leg. The only genuinely untraced drops are the two by-design noise filters (bot-author `_discord.py:934-937`, self `:945-949`) — L1 adds a debug-level `dropped(reason=…)` line for those. Counters live on the pool `_RegistryEntry` (mirroring the discoverable-entities cache, `_pool.py:135-181` → `_get_account_cache_snapshot` → `GET /connectors/{id}/discoverable-entities`, `api.py:3022-3094`) and surface through a connector-detail-family snapshot endpoint — **NOT** the doctor probe (which spins its own short-lived client with zero pool-state access, `_discord.py:1244-1413`). No new persistence layer, no metrics backend.
- [x] **Full-day run cadence — how does an 8-hour soak fit a planning/exec session?** → The flight delivers the instrumentation + a green HAT regression-gate run inside the session; the **full working day is operator wall-clock**, performed over a real day of use. The flight lands on the operator's reported evidence (logs/counters + judgment). Leg 3 is an interactive/operator-judgment leg, not an autonomous one.

### Design Decisions

**Passive close of #17 (no synthetic rate-limit harness)**
- Choice: No dedicated rate-limiting stress work. The observability leg (L1) instruments the outbound path so a 429/cascade is *visible* during the full-day run; #17 closes on (existing correct 429 substrate, code-verified) + (a clean instrumented full-day real-load run). Backpressure (per-account send queue / tool-layer retry) is built only if the day surfaces an actual cascade — as a follow-on, not in-flight.
- Rationale: The substrate is sound and real single-operator load won't trip outbound limits; chasing a manufactured 429 yields a low-signal artifact. "Build only if cascades surface" is the mission's own language.
- Trade-off: no re-runnable synthetic 429 regression gate. Acceptable — if a cascade ever appears, that's the trigger to build *and* test backpressure deliberately.

**Observability-first leg (L1) — unified stdout disposition stream + light counters**
- Choice: Project every inbound disposition onto one greppable stdout line at each `dispatch_inbound` return site (`admitted | denied(reason) | no-eligible | pool-failure | policy-silent | dropped(reason)`), **alongside** (not replacing) the existing DB `session_metadata` append at each site, via a shared helper so the disposition vocabulary is single-sourced and no double-logging occurs. Add a stdout line per outbound send → `ok | rate_limited(retry_after) | error` (account/channel/latency) in the `_discord.py` send path. Add a debug-level `dropped(reason=bot-author|self)` line for the two by-design silent noise filters (`_discord.py:934-937`, `:945-949`). Light per-account counters on the pool `_RegistryEntry`, surfaced via a connector-detail snapshot endpoint. Log **ids and dispositions only — never message content or tokens**.
- Rationale: Applies F15's headline lesson (observability-leg-first; premise-audit the *observability* axis). The recon + Architect review found: outbound has **zero** metrics (a 429 is only a WARNING line), and while most inbound dispositions ARE in DB `session_metadata`, none reach the stdout stream an 8-hour soak greps. #19's "no silently-dropped inbound" needs a single, durable, greppable stream — L1 is that projection (see Premise Audit).
- Trade-off: a small, deliberately-minimal amount of connector-layer code + unit tests (DI/code-side stubs only — the mission's env-seam constraint forbids an env flag to force the 429 path). No metrics backend (stdout-log + in-memory by design).
- Known limitation (named, not fixed): the `_RegistryEntry` counters reset when the pool entry is reaped on idle TTL — so the aggregate reads "since the current pool entry warmed," not "since start." The **stdout disposition log is the binding evidence surface**; counters are convenience. (Lifting counters to module-level account-keyed survival was considered and rejected as persistence-creep.)

**Bundle the carried HAT-driver debt into one hardening leg (L2)**
- Choice: Fold all `tests/live/discord_hat/`-touching debt into L2: write `tests/live/discord_hat/README.md`; move `_BOT_IDS` from `test_multi_user.py` into the env contract; add hermetic unit tests for the pure driver helpers (`inbound_peer_names`, `latest_routing_entry`, the routing-length before/after logic) so the no-creds CI run has *some* regression net; scrub the L3 `message_content`→`Intents.default()` doc-lag.
- Rationale: F17 is the named forcing function for the README; everything here shares one surface (`tests/live/discord_hat/`), matching the project's `touched-surface-debt-folding` convention. The driver is about to be leaned on hard as the full-day regression gate — harden it first.
- Trade-off: L2 is mostly docs + tests, lower-risk than L1; sequencing it second keeps the live regression gate ready before the full-day run.

**Full-working-day run is an operator-judgment (interactive) leg, gated by a green HAT run**
- Choice: L3 runs the committed HAT driver green (entry gate, confirms the live baseline), then the operator runs the bot as a daily driver across a real working day; evidence comes from the L1 instrumentation + operator judgment. Not driven by autonomous agents.
- Rationale: "A full working day" is irreducibly wall-clock and operator-experiential; no agent can soak 8 hours judging coherence. The interactive-HAT-leg shape (FD guides, operator performs/reports) is the right structure.
- Trade-off: the flight's land date depends on the operator completing a real working day — the gate can't be rushed.

**Watch the parked pairing two-step DM-grant gap during the day**
- Choice: L3's watch-list includes the parked F16 Known Issue (an approved peer gets channel access immediately but can't DM until the operator flips the per-peer toggle, with no UX signal). The full-day run is its trigger: if an approved peer's DM silently fails and confuses, that's the signal to scope a focused approve-flow UX/docs follow-on.
- Rationale: F16 debrief operator disposition was "park until F17 evidence." This flight is that evidence-gathering occasion.
- Trade-off: no fix here — observation only; a follow-on is scoped only if confusion is actually observed.

### Prerequisites

- [ ] F15's HAT credentials (`.env.hat`: burner-bot tokens, test guild, channel ids, connector id, the-one bot user id) — **already present in the tree** (`tests/live/discord_hat/.env.hat`, gitignored; Architect-confirmed), so L3's entry-gate HAT run is realistically runnable now. **Provisioning friction applies to *re*-provisioning, not first-run** (F15): burner bots are created manually in a normal browser (captcha/MFA block automation); the `ingest_bots` connector config is a **connect-time closure (`_discord.py:882-884`) → a container restart is required** after any connector reconfiguration for the HAT.
- [ ] The live test guild + the-one's own bot online with Message Content intent.
- [ ] Operator availability to use the bot as a daily driver across a real working day (L3).
- [ ] L1 instrumentation merged before L3 (the full-day run reads it).

### Pre-Flight Checklist

- [x] All open questions resolved *(done — see above)*
- [x] Design decisions documented *(done)*
- [x] Prerequisites verified *(`.env.hat` present; operator availability for the full-day run + L1-before-L3 sequencing are runtime gates)*
- [x] Validation approach defined *(L1 unit tests + L2 hermetic helper tests + the live HAT regression gate + the operator-judged full-day soak + the UI once-over)*
- [x] Legs defined *(done — see below)*

### Premise Audit — full-day apparatus (both axes)

- **ACT (can the apparatus drive the system as a real actor would?)** — Yes, trivially: the apparatus *is* the operator + real peers using the live bot all day. No synthetic driving needed for #19.
- **OBSERVE (can the apparatus read, through an existing-or-built surface, everything the criteria must assert?)** — Partially today, fully after L1:
  - "Stayed up / no manual restarts" → pool `is_alive()` (`_discord.py:398-413`) + outer-reconnect backoff logs (`~:1099-1220`) — **exists**.
  - "No token re-decryption issues" → reconnect re-decrypts on rotation; `LoginFailure` surfaces in logs — **exists**.
  - "No stuck sessions" → `chat_sessions.last_inbound_at` advancing, readable via the session API / audit inspector — **exists**.
  - "**No silently-dropped inbound**" → inbound dispositions ARE recorded in DB `session_metadata` (`_inbound.py` deny `:398-409`, no-eligible/pool-failure `:547-625`, policy-silent `:797-815`) but **not on the `docker logs` stdout stream** the soak greps; and the two by-design noise filters (bot-author `_discord.py:934-937`, self `:945-949`) leave no trace at all. **L1 projects these onto one greppable stdout stream** + traces the two filters — a log-consolidation gap, not a "no record exists" gap.
  - "429 → graceful backoff, not cascade" (#17 passive) → today only a WARNING line + agent `[error]`; **L1's outbound disposition line/counter makes a 429 and its handling visible** for the passive watch.

---

## In-Flight

### Technical Approach

Two small backend/test legs that make the runs *assertable*, then the operator-judged soak:

1. **L1 — connector observability:** project each existing inbound disposition (admitted/denied/no-eligible/pool-failure/policy-silent) onto one greppable stdout line via a shared helper alongside the existing `session_metadata` append (no double-logging); add outbound send lines (ok/rate_limited/error) + the two missing noise-filter `dropped` traces; light per-account counters on the pool `_RegistryEntry` surfaced via a connector-detail snapshot endpoint. Ids/dispositions only — no content, no secrets. Unit-tested with DI/code-side stubs.
2. **L2 — HAT-driver hardening:** README + `_BOT_IDS`→env + hermetic helper unit tests + doc-lag scrub. Lower-risk; makes the live driver a dependable regression gate.
3. **L3 — full-working-day run (interactive):** run the committed HAT driver green (entry gate), then the operator runs a real working day **plus a deliberate once-over of every UI surface**; collect L1 evidence; assess #19, passively assess #17, watch the parked pairing DM-grant gap; triage UI-sweep findings into injected `ui-fix-*` legs (expected — see Adaptation Criteria).

### Checkpoints

- [x] L1: structured inbound/outbound disposition logging + per-account counters land; "dropped inbound" leaves a trace; no content/secret leakage in logs; unit tests green; full backend suite green. **(2861 passed; new helper `_observability.py`, endpoint `GET /api/connectors/{id}/disposition-counters`.)**
- [x] L2: `tests/live/discord_hat/README.md` written; `_BOT_IDS` in the env contract (both consumer files; real snowflakes scrubbed from public source); hermetic unit tests for the pure driver helpers green in the no-creds CI run; `message_content` doc-lag scrubbed. **(2884 passed / 4 skipped / 529 deselected.)**
- [ ] L3: committed HAT driver runs green against the live guild (entry gate); operator completes a real full working day; L1 evidence shows the bot stayed up, no stuck sessions, no silently-dropped inbound, no token issues; no 429 cascade (or, if one surfaced, it is documented as the trigger for a backpressure follow-on); the parked pairing DM-grant gap is assessed; the full-UI once-over is complete with every finding logged and triaged.
- [ ] Injected `ui-fix-*` legs (from the L3 sweep): each surfaced defect either fixed in its own leg with passing acceptance criteria, or explicitly filed as out-of-scope (Known Issue / follow-on) with rationale.

### Adaptation Criteria

**Divert if**:
- The full-day run surfaces a **429 cascade** (outbound failures pile into tool-failure cascades). → Do NOT build backpressure in-flight; capture the evidence, land L3 with #17 staying open, and scope a dedicated backpressure follow-on flight (the deliberate trigger the mission framing describes).
- L1 reveals that "silently-dropped inbound" is **structural** (a real drop path, not just unlogged). → Re-scope: that's a correctness defect, not an observability gap — file it and decide whether it blocks the gate.
- The bot requires manual intervention during the day (restart, re-auth, stuck-session clear). → #19 fails for this run; capture the failure mode and re-run after a fix.

**Acceptable variations**:
- The counters' read surface (doctor report vs connector-detail endpoint) is a leg-design choice finalized at L1 design — structured stdout logs are the binding evidence surface either way.
- L3's full working day may span more than one calendar attempt if the first is interrupted for reasons unrelated to the bot.
- **Injected fix-legs from the L3 UI once-over are EXPECTED and pre-authorized.** The operator's full-day run includes a deliberate sweep of every UI surface; defects it surfaces become `ui-fix-*` legs added mid-flight (each with its own acceptance criteria, recorded in the flight log with rationale per the `/agentic-workflow` mid-flight-adaptation protocol). Scope growth from this sweep is the intended shape of the flight, not a divert condition — the Flight Director should absorb and sequence the injected legs without relitigating the flight's size. Only genuinely out-of-scope findings (substrate re-architecture, a new mission criterion) get filed as Known Issues / follow-on flights rather than injected here.

### Legs

> **Note:** Tentative; planned one at a time during execution. Detailed leg design happens per-leg in `/agentic-workflow`.

- [x] `connector-observability` — **Outbound:** a stdout disposition line per send (`ok | rate_limited(retry_after) | error`, with account/channel/latency) in the `_discord.py` send path (`:522-554`). **Inbound:** project each disposition decided at `dispatch_inbound`'s return sites (deny `_inbound.py:398-409`; no-eligible/pool-failure `:547-625`; policy-silent `:797-815`) onto one greppable stdout line **alongside** the existing `session_metadata` append at each site, via a shared disposition helper (single-sourced vocabulary, no double-logging); add a debug-level `dropped(reason=bot-author|self)` line for the two by-design silent filters (`_discord.py:934-937`, `:945-949`). **Counters:** light per-account counters on the pool `_RegistryEntry` (mirroring the discoverable-entities cache, `_pool.py:135-181`), surfaced via a connector-detail snapshot endpoint like `GET /connectors/{id}/discoverable-entities` (`api.py:3022-3094`) — **NOT** the doctor probe (no pool-state access). Counters reset on TTL eviction (named limitation; stdout log is the binding surface). **Ids and dispositions only — never message content or tokens.** Unit tests (DI/code-side stubs, no env-flag seam) for the logging/counter logic; full backend suite green.
- [x] `hat-driver-hardening` — `tests/live/discord_hat/README.md` (burner-bot provisioning in a normal browser; Message Content NOT needed on burners; finding the-one's gateway bot-user-id; `make test-discord-hat` SKIPs without `.env.hat`; the `_BOT_IDS` re-provisioning gotcha; the `wait_for_session(until=…)` timing rationale; the connect-time-closure restart requirement). Move `_BOT_IDS` from `test_multi_user.py:53` into the env contract (`config.py` / a `THE_ONE_HAT_BOT_USER_IDS`-style var). Add hermetic unit tests for the pure driver helpers (`inbound_peer_names`, `latest_routing_entry`, the routing-length before/after logic) against fixture dicts (no Discord) so the no-creds CI run has a regression net. Scrub the L3 `message_content`→`Intents.default()` doc-lag in the F15 leg spec + flight-log note.
- [ ] `full-working-day-run` *(interactive / operator-judgment)* — Run the committed HAT driver green against the live guild as the entry gate (confirms the baseline; needs `.env.hat` + the container restart). Then the operator runs the bot as a daily driver across a real full working day. **In parallel, a deliberate once-over of the entire UI** — every operator-facing surface (Chat, Studio agent + connector editors, Administration, the Discord-shaped creation form / allowlist + routing dropdowns / detach / audit-log inspector) is walked while the bot is live, looking for visual, copy, interaction, and freshness defects. Collect L1 evidence (logs + counters). Assess **#19** (stayed up, no stuck sessions, no silently-dropped inbound, no token re-decryption issues, no manual restarts); passively assess **#17** (any 429s? graceful?); watch the parked F16 pairing two-step DM-grant gap (does an approved peer's DM silently fail/confuse?). Write the run evidence — and every UI-sweep finding — into the flight log. **Findings are expected to spawn injected fix-legs** (see Adaptation Criteria); this leg's job is to *surface and triage*, with fixes landing in their own legs.
- [x] `fix-gateway-idle-reap` *(injected — L3 finding F2, substrate fix)* — the idle-TTL reaper disconnected the Discord gateway after ~30 min of quiet, silently taking the bot offline until a manual Test Connection (the "constant Test Connection" symptom; #19 blocker). Fixed: (A) live account-keyed gateway entries are idle-reap-exempt (per-agent entries still reap); (B) boot warm-up confirmed (≥1-attached-agent gate already fires on restart); dead listeners self-heal (evict + rewarm within ~30s, gated on still-having-attached-agents). Reviewed (Sonnet, confirmed) + 2 hardening fixes. **2890 passed.** Own follow-up commit.
**Injected batch from the L3 UI once-over (operator-walked; full design notes per leg in the flight log).** Six legs, two clusters. Ordering respects the dependencies noted; run via `/agentic-workflow`. *Theme: a typed, subtractive connector editor + a coherent unknown-DM → approve → respond flow.*

*Connector-editor cluster:*
- [x] `connector-connection-status` **(Leg A)** — replace the manual "Not tested"/Test-Connection model with a **live connection status** on General (`is_alive()`: Connected/Connecting/Disconnected/Error — the F1 fix); **Save opens/reconnects the WS** (evict + re-`account_acquire`, gated ≥1 agent, on connection-relevant change — also picks up `ingest_bots`, killing most restart-after-reconfig friction); **demote Test Connection → optional "Validate"**; **contextualize the invite link** (info-icon says it's for adding the bot to a server; source the `application_id` so it renders pre-Test); **relocate the discoverable-entities** cache/"last refreshed" surface to a better spot + relabel. **Owns the shared actionable connect-error display** (incl. `PrivilegedIntentsRequired` → Developer-Portal link). *Ships with B.*
- [x] `intents-ux` **(Leg B)** — **delete the 3 intent checkboxes**; the-one **always requests all 3** intents; the removed escape hatch is replaced by A's actionable portal error on `PrivilegedIntentsRequired`. *Depends on A's connect-error surface; ship together.*
- [x] `additional-config-advanced-section` **(Leg C)** — keep the generic kv-table (advanced/escape-hatch use, e.g. `ingest_bots`) but **demote it to its own "Advanced" section at the bottom**, out of the way of the typed fields. Independent.

*DM / approval-flow cluster:*
- [ ] `dm-allowlist-simplify` **(Leg D, substrate + closes a Known Issue)** — post-F16 `peers` gates DMs only, so **relabel the users section "Direct Messages"**, **drop the per-peer `dm_allowed` flag** (in-list = can-DM; storage migration `{id,dm_allowed}`→`{id}` + `_acl.py` DM-composition update), **keep `dm_admission` as a relabeled 3-mode policy** (Anyone / Only these people / No one), and **fix the approve flow** to add an approved peer as allowed. **Closes the F16-parked two-step DM-grant mission Known Issue.**
- [ ] `approval-pending-signaling` **(Leg E)** — surface a pending **first-DM approval**: a **Chat left-panel flag**, a **top-nav badge on the Chat button** (live count of `PendingApproval` status=pending), and a **one-time Discord auto-reply** to the unknown DMer ("awaiting approval", sent once on pending-row creation). *Builds on D's approve semantics.*
- [ ] `respond-on-approval` **(Leg F)** — on approve (`approve_peer_approval`), the bot **proactively answers the user's original message** (persist the full first message on the pending row to replay it through an agent step + send) rather than making them poke it again. *After D + E.*

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (L1 unit + L2 hermetic helper tests green; full backend suite green; committed HAT driver green against the live guild)
- [ ] Documentation updated (`tests/live/discord_hat/README.md`; any agents.md conventions promoted; mission #18 descope + #17/#19 dispositions recorded)

### Verification

- **L1 (unit):** structured-disposition logging + counter logic covered by unit tests; manual confirm that a dropped inbound and a 429 each leave a readable trace, and that no message content or token appears in any log line.
- **L2 (CI net):** the hermetic driver-helper unit tests pass in the default no-creds run; the README is sufficient for a cold operator to provision + run the HAT.
- **L3 (live, operator-judged):** the committed HAT driver passes against the live guild; the operator confirms a real full working day of daily-driver use with the L1 evidence showing no intervention was needed. #19 closes on that evidence; #17 closes passively (substrate-correct + no cascade) or stays open with a documented cascade trigger.
