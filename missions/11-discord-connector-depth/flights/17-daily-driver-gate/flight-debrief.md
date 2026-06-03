# Flight Debrief: Daily-driver validation gate (full-working-day run + connector observability)

**Date**: 2026-06-03
**Flight**: [Daily-driver validation gate](flight.md)
**Status**: landed
**Duration**: 2026-06-02 (planning) → 2026-06-03 (landed) — single extended session
**Legs Completed**: 10 (L1, L2 planned; L3 interactive; L4 + A–F injected) of a 3-leg plan

## Outcome Assessment

### Objectives Achieved

F17 achieved its objective — certify the Discord connector as daily-driver-ready — and **vastly over-delivered** relative to its 3-leg plan. The L3 daily-driver soak was designed as a finding engine, and it worked: L1's instrumentation, live within hours, turned a silent "the bot ignored my DM" into a precise "the gateway is disconnected" in one grep, and the deliberate UI once-over surfaced a string of real defects. The result was an injected **A–F batch** plus a substrate fix (L4), delivered across **5 commits, 2 schema migrations (v28/v29), and 2 Witnessed behavior tests (both 7/7)** — backend suite **2935 passed / 4 skipped / 536 deselected** (+100 vs F16).

What shipped:
- **L1 observability** — a single greppable stdout disposition stream (inbound + outbound) + per-account counters; the evidence surface the soak ran on.
- **L2 HAT-driver hardening** — `tests/live/discord_hat/README.md` (closes F15+F16 carry-forwards), `_BOT_IDS`→env (real snowflakes scrubbed from the public repo), hermetic helper tests, doc-lag scrub.
- **L4 gateway idle-reap fix** — the idle reaper was disconnecting the inbound gateway after 30 min of quiet (silent offline → "constant Test Connection"); now account-keyed gateway listeners are idle-exempt-while-alive with a liveness self-heal. The #19 blocker.
- **Editor cluster A/B/C** — live connection status (the F1 fix), Save-reconnects-the-WS, Test→Validate, intent checkboxes deleted (always-on + actionable portal error), Additional Config demoted to a bottom Advanced section, contextualized invite. Behavior-tested.
- **DM cluster D/E/F** — "Direct Messages" simplification (dropped `dm_allowed`, one-step approve), pending-approval signaling (one-time auto-reply + nav badge + left-panel section), and respond-on-approval (the bot answers the peer's original question via re-dispatch). Behavior-tested against **real Discord**.
- **+ 3 latent bugs incidentally fixed:** the Additional-Config kv-table never round-tripped on save for Discord connectors; `studio.js` wrote a per-agent `dm_allowed` the post-v26 validator already rejected; and the save-warm connect-error was silently swallowed to "Disconnected."

### Mission Criteria Advanced

- **#19 (survives a full working day, no intervention)** — closed on **operator-judged live-session validation**: the bot ran live throughout (including a clean restart that auto-reconnected via L4's boot-warm), and every robustness failure mode the live use surfaced was root-caused and fixed in-flight. Accepted in lieu of a separate stopwatch 8-hour run; the mission-debrief makes the final mission-level call.
- **#17 (rate-limiting/backpressure)** — closed *passively*: the 429 substrate is code-correct (discord.py pre-empts; typed `ConnectorRateLimitError`, no retry-cascade path) and no cascade appeared under live use. L1's outbound stream is the standing watch.
- **Closes the F16-parked Known Issue** — "pairing-approval two-step DM-grant" (the F3a confusion that gave the first real DM-er "no agents available"), resolved by Leg D with a permanent F3a-reproduction regression test.
- **#1–4 (Discord-shaped UX)** — opportunistically re-validated live during the once-over; the editor was substantially improved.

All checkpoints met. Both behavior tests pass 7/7.

## What Went Well

- **The soak as a finding engine — the central bet, and it paid off immediately.** L1's disposition stream (built first, per F15's observability-leg-first lesson) localized F2 (gateway disconnected) in a single grep within hours of going live. The instrumentation is the reason the soak produced *actionable* findings instead of anecdotes.
- **Design-review-before-implement was load-bearing on every substantive leg.** It caught issues that would have shipped subtly-wrong: L1's disposition vocabulary (`command-intercepted` missing, `admitted`→`stepped`, `denied` across three sites — without which the stream wouldn't grep-correlate with the DB); **Leg D's `models.py` validator landmine** (a `{id}` row would crash `Connector.model_validate()` on every read — a production-down without the same-commit validator update); **Leg A's connect-error swallow** (the most consequential catch — shipping B's intent-checkbox deletion without the actionable error would have stranded users hitting `PrivilegedIntentsRequired`); L4's `_rewarm_dead_listeners` unconditional-rewarm + `is_alive`-absent bugs; Leg F's `get_factory` guard. None were cosmetic.
- **Behavior-tests-as-visual-gate caught what unit + browser tests structurally couldn't.** F4 (the connector editor showing a stale peers chip list after an approval) required a multi-step cross-surface flow no unit test models; the `connector-editor-ux` test found it at step 7. `discord-approval-flow` validated the whole unknown-DM→approve→answer loop against **real Discord** (Chrome MCP driving the web client as Chuck R) — the apparatus risk I'd flagged never materialized.
- **Selective-commit discipline preserved the operator's parallel MCP fix** across all 5 commits — `git add -A` + `git restore --staged` the 5 MCP files every time, verified each commit. Zero contamination.
- **Cluster-commit + per-cluster-behavior-test rhythm** gave clean, theme-scoped history (L1+L2, L4, editor, DM, F4-follow-up) without per-leg noise.
- **The Sonnet Reviewer escalation** (over the crew-default Haiku) for the correctness-sensitive clusters — same situational call as F16 — earned its keep (the connect-error-swallow + the migration/ACL reviews).

## What Could Be Improved

### Process

- **The "gate-sweep batch" had no scope fence.** The Adaptation Criteria pre-authorized "injected fix-legs from the L3 once-over" — appropriate language for 1–2 small fixes; it ended up absorbing **6 substantive legs + a substrate fix = a mini-mission inside a flight** (10 legs, 5 commits, 2 migrations). Keeping the robustness fixes (L4) and the Known-Issue closure (D) in-flight was correct — they're gate-blocking by definition. But **B (intent removal) and C (Advanced relocation) were quality-of-life, not gate blockers**, and could have been triaged to a follow-on quality flight. The criteria's "only substrate-re-architecture / new-criterion findings get filed as follow-ons" threshold was too coarse and absorbed everything below it. *(See Recommendations: name + fence the pattern.)*

### Technical

- **Test metrics: 2935 passed / 4 skipped / 536 deselected, ~282s** (F15 2832/262s; F16 2835/286s). +100 passed, wall steady (the added suites are fast pure-logic: observability, hermetic HAT helpers, the ACL matrix, migration-shape assertions). No throughput regression. The **3 `aiosqlite` "Event loop is closed" teardown warnings in `test_db_migration.py` persist** — carried since F11; tini (F15) addressed zombie reaping, not this. Still a routine-maintenance ticket, not a regression.
- **`is_dm=True` is stored on the v29 pending row but the replay hardcodes `raw={"is_dm": True}` anyway** — the stored column is unused for its stated purpose. Factually correct today (only DMs reach the pending branch), but the gap between "we stored it to read it back" and "we hardcode it" should be closed.
- **`_connect_error_store` is an in-memory module-level dict** — wiped on restart, per-worker. Acceptable for single-user-local, but the last connect error is lost on restart (an operator who restarts + opens the editor sees "Disconnected" with no reason), and it silently breaks under multi-process. A scaling assumption baked in.
- **No dedicated regression test for the `studio.js` per-agent peer-add shape** (the latent `dm_allowed`-rejected bug) — verified only by the general ACL sweep.
- **`application_id` persistence has no token-change invalidation** — a stale app-id could persist if the bot's application changes; add it to the secret-change invalidation.

### Documentation

- **agents.md convention promotion needs verifying.** Several nameable patterns emerged (disposition-helper, status-snapshot-via-pool-entry, save-warm-background, re-dispatch-on-approval, the connector-form four-way field lifecycle). The flight added the `≥1-attached-agent listen criterion` per L4 — confirm the rest are promoted (see Action Items).
- **"Anyone" DM mode hides that the list is ignored** — a tooltip noting "the Direct Messages list below is ignored in this mode" would prevent operator confusion.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| #19 closed on live-session validation, not a formal 8h stopwatch soak | The session surfaced + fixed a real #19 failure mode (idle-reap) and ran fixed-and-live with instrumentation throughout — that IS the evidence the soak seeks | Situational — operator-judgment gate; mission-debrief confirms. Defensible when the live use produced fix-and-confirm evidence |
| Formal HAT entry-gate skipped (soak on real config, not HAT-reconfig) | HAT reconfig would disrupt the live daily-driver connector; F15 already proved the HAT green | Yes — for daily-driver soaks on the operator's real connector, don't disrupt it with a HAT-reconfig entry gate |
| L1's "no inbound record exists" premise corrected to "exists in DB, not on stdout" at design | Architect premise-audit (observability axis) | Yes — premise-audit observability, not just feasibility (the F15 lesson, applied) |
| F4 (stale chip list) emerged from the behavior test, not design review | A cross-surface data-freshness bug not visible in static review | Expected — this is exactly the behavior-test's job; not a process miss |
| Leg F replay passes kwargs from memory vs the specced DB re-fetch | Avoids a second round-trip + aiosqlite background-task cursor timing | Yes — pass in-memory data to background tasks rather than re-fetching where possible |
| Test residue left on the live connector (presence `Simmering2`; Chuck R approved + in the DM list) | The behavior tests deliberately drove real mutations | No — note + offer cleanup; behavior tests on live operator state should flag residue (the F15 set/restore-in-finally discipline applies to driver tests, not these interactive ones) |

## Key Learnings

1. **Observability-leg-first turns a soak into a finding engine.** Build the evidence surface (L1) before the soak; it's the difference between "the bot ignored me" and "the gateway is disconnected (one grep)." Applied F15's lesson; confirmed.
2. **Design-review-before-implement is the standard, not the exception, for any leg on a load-bearing path.** It caught a would-be production-down (the v28 validator landmine) and a would-be vacuous-error-surface (the connect-error swallow) before a line was written.
3. **Behavior-test-per-cluster (not per-leg) is the right granularity** for UI clusters with cross-leg dependencies — and it catches cross-surface/data-freshness bugs (F4) that unit + browser tests structurally can't.
4. **Selective-commit lets a flight coexist with the operator's parallel work** — `git add -A` then unstage the known-foreign files, verify every commit. A reusable discipline when the working tree carries someone else's in-flight changes.
5. **Re-dispatch-via-the-real-dispatcher beats a bespoke replay path** — reconstruct the envelope and call `dispatch_inbound` so the replay traverses the same routing/policy/agent/send path; the `raw={"is_dm": True}` policy-gate requirement is the kind of edge only visible from the actual code.
6. **A daily-driver gate's UI once-over is the most ecologically valid finding environment** — the operator is using the product as intended, and the findings are mission-relevant by construction. But it needs a scope fence (next).

## Recommendations

1. **Name + fence the "gate-sweep batch" pattern** (methodology). When a daily-driver/validation gate's soak surfaces findings, triage each explicitly at the finding point: **gate-blocking** (robustness, observability that prevents asserting the criteria, a parked Known Issue) → in-flight; **quality-of-life** (UX polish that doesn't block the gate) → a follow-on quality flight unless trivially cheap. F17's L4 + D belonged in-flight; B/C were the unclear calls. Add the fence to the L3-style Adaptation Criteria template.
2. **Promote the emergent patterns to `agents.md`** (verify): `connector-disposition-observability`; `account-entry-snapshot-via-pool-lock` (the three `_get_account_*_snapshot` family — consider a `_read_account_entry` helper); `background-reconnect-on-config-change` (`_save_warm_background` + `_connection_relevant_changed`); `re-dispatch-on-approval` (incl. the `get_factory()` guard + `raw={"is_dm"}`); the `connector-form` four-way field-lifecycle contract (render + collect + snapshot + wireEvents).
3. **Persist the last connect error** (Discord connector follow-up) — write it to `account.config` (or the pool entry) so it survives restart + is visible after a cold-boot failure; this closes the "Disconnected with no reason" UX gap from the in-memory `_connect_error_store`.
4. **Read `is_dm` from the stored v29 column on replay** instead of the hardcoded literal; add an explicit invariant/assertion at the pending-approval branch entry ("DM-only") so the implicit assumption is documented.
5. **Fold two small cleanups into the next connector-touching flight:** an `application_id` token-change invalidation (add to the secret-change reconnect path); the "Anyone" DM-mode "list is ignored" tooltip; and a dedicated regression test for the `studio.js` per-agent peer-add shape.
6. **Route the carried `aiosqlite` teardown warning to routine-maintenance** (`test_db_migration.py` `TestSchemaV17`, 3 warnings since F11) — apply F11 L3's async-fixture-redesign pattern.

## Action Items

- [ ] **Verify the emergent `agents.md` conventions are promoted** (Rec 2) — the flight.md post-flight "agents.md conventions promoted" item; promote any missing ones.
- [x] **Behavior-test residue on the live connector** — operator decision (2026-06-03): **leave both as-is** (presence `Simmering2`; Chuck R stays approved + in the Direct Messages list).
- [ ] *(Carried)* `aiosqlite` "Event loop is closed" teardown warnings → routine-maintenance (since F11; tini did NOT address it).
- [ ] *(Follow-up)* Persist last-connect-error + `application_id` token-change invalidation + `is_dm`-from-column on replay + the "Anyone"-mode tooltip + the `studio.js` per-agent shape regression test — fold into the next connector-touching flight.
- [ ] *(Methodology)* Add the "gate-sweep batch" triage fence to the L3-style Adaptation Criteria template (Rec 1).
- [ ] **Mission-debrief** makes the final #19/#17 mission-criteria call (this flight's evidence: live-session validation + passive-429).
- [ ] **PR #87** ready-for-review when the operator's parallel MCP fix is committed/merged alongside (the 5 MCP files are still uncommitted in the tree by design).
