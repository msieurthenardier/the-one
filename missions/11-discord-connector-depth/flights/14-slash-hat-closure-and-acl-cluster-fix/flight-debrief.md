# Flight Debrief: Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt

**Date**: 2026-06-01
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix](flight.md)
**Status**: landed
**Duration**: 2026-05-31 (planning) → 2026-06-01 (land)
**Legs Completed**: 13 of 13 (10 planned L1–L10 + 3 inline-HAT-fix legs L11–L13 surfaced by the L10 HAT)

## Outcome Assessment

### Objectives Achieved

The flight's stated objective — **close M11 criterion #10 (all six platform slash commands validated end-to-end against the real Discord bot, ephemeral-where-appropriate)** — was achieved, but only after the L10 HAT surfaced three pre-existing bugs that no prior flight had caught. The `discord-slash-end-to-end` Chrome-MCP behavior test passed 7/7 against the live bot: `/whoami`, `/agents`, `/help` ephemeral ("Only you can see this"); `/talk_to`, `/new`, `/reset` channel-visible; `/agents` lists the agent (live before/after evidence of the L1 Bug D fix). The original F13 L6 4-bug cluster was resolved (Bug B → guilds-unification, Bug D, Bug E, Bug A docs; Bug C retired as a false positive), AND three NEW pre-existing slash-registration bugs were fixed (F/G/H, below).

### Mission Criteria Advanced

- **#10 (slash commands validated)** — **CLOSED.** All 6 commands work as real Discord slash interactions with correct ephemeral disposition.
- **#11 (re-runnable HAT artifact)** — **PARTIAL `[~]`.** The slash-command portion ships as the re-runnable `discord-slash-end-to-end` Chrome-MCP behavior-test (status `active`, PASS 7/7). Multi-user / multi-channel / multi-agent / pairing / mentions-aware coverage remains for F15+.
- Carry-forwards from F13 debrief CLOSED: the L4-enhancement test backfill (L4), the 2 pre-existing browser failures (L5), Bug A ops docs (L6).

## What Went Well

- **The design-review gate earned its keep three times before code was written.** L1 (corrected `is_dm` derivation to honor the plugin hook), L3 (rejected an unachievable browser "defense-in-depth" test), L7 (caught that `Webhook.partial` raises `ValueError` for ephemeral — `from_state` with `"type": 3` is the only working path, verified against discord.py 2.4.0 pre-implementation). Each correction prevented a runtime failure or wasted implementation.
- **L8's `AdmissionContext` dataclass is a durable architectural win.** It converts the Bug D failure mode (a call site silently using kwarg defaults) into a compile-time type error: any future ACL axis becomes a required field. `from_envelope(envelope, plugin)` centralizes the previously-duplicated derivation; the option-b test wrapper kept ~30+ flat-shape fixtures untouched (`test-translator-helpers-for-shape-evolution` convention).
- **The HAT did exactly what a real-environment HAT is for.** It exercised the real slash-interaction path for the first time in 8 flights and caught three pre-existing bugs (F/G/H) that the entire unit/integration suite missed.
- **Behavior tests, again, caught what unit tests structurally cannot** (reinforcing the F13 debrief's canonical-case finding): the inference-roundtrip regression gate confirmed no F14 substrate regression; the slash HAT surfaced F/G/H. (See Methodology Feedback — the operator's note.)
- **Operator-directed pivots landed clean.** L2's false-premise escalation → unification, and L9's infeasible-driver escalation → Chrome MCP, were both surfaced early and re-scoped without rework downstream.
- **Mid-flight test-infra remediation** (`scripts/run-tests.sh`) fixed a real operator-flagged problem (orphaned browser-test CPU peg) with a bounded, self-cleaning process-group wrapper — and unblocked the rest of the flight.

## What Could Be Improved

### Process

- **Recurring un-verified-premise planning errors.** Three DDs rested on premises that were stated as facts but not verified before lock: L2 (`config.guilds` is an orphan — false; it's the live "Scope to servers" field, verifiable with one `git grep` of `connector-form-discord.js`), L9 (a discord.py bot can invoke another bot's slash commands — false; verifiable in ~2 min from `discord.Client`'s API surface), and the `talk_to`/`talk-to` spelling split (flagged at L7 design review but deferred, then accumulated into the L12/L13 blocking bugs). These are qualitatively different from "didn't know until we looked" — they were assertions confirmable before the DD was marked resolved. **A "premise audit" step belongs in planning** (see Recommendations).
- **HATs validated the wrong invocation path for 8 flights.** Every prior Discord HAT (incl. F13 L6) used the text-prefix `on_message` path, never real slash interactions — so the slash-registration path (`tree.sync` → guild bucket → interaction dispatch → `_build_slash_envelope` → `_parse_command` → handler) was never exercised. Three bugs lurked there. A HAT must exercise the **user's actual entry point**, not an analogous proxy that shares most of the pipeline.
- **Browser-test baseline drift between flights.** L4 found 3 stale-fixture failures in `test_flow_studio_connector_inference_provider_row.py` that the F13 "454/2-failures" baseline missed — F13 L4 landed an input→select UI change without updating same-file tests. Baselines aren't continuously verified; a regression hides until a later leg happens to touch that file.

### Technical

- **App-level connector logging is not captured by `docker logs`** — the single largest diagnostic impediment of the flight. The connect/READY/`tree.sync`/Forbidden log lines that would have instantly distinguished Bug F's failure mode were invisible; diagnosis required a standalone in-container `tree.sync` probe. Every future Discord-connector diagnosis hits the same opacity.
- **`allowlist.guilds` coupling** — the L2 unification fuses inbound-guild admission + DM-deny posture + slash-registration scope into one axis. Intentional + documented, but a future "register slash commands in a guild without admitting inbound from it" need would require re-separating the axes.
- **discord.py internals coupling** — `self._client._connection` (private attr) in `DiscordClient.send` for `Webhook.from_state`; isolated + commented, but fragile across discord.py majors.
- **Container has no init reaper (PID 1 = uvicorn).** The `run-tests.sh` group-kill leaves `<defunct>` zombie entries (~85 pairs observed post-suite) — harmless (no CPU/mem) but the `tini`-as-PID-1 Dockerfile follow-up is real infra debt.
- **N806 lint slipped to Phase 2d** (a non-snake_case local in `_discord.py`) — the implementing agent missed a lint pass. `ruff check` should be a Phase 2d acceptance gate.

### Documentation

- **agents.md lacks a "Slash command architecture notes" subsection** consolidating four discord.py-specific facts a future implementer (autocomplete, modals, new commands) will need: the `Webhook.from_state` `"type": 3` ephemeral mechanism; the `_EPHEMERAL_SLASH_NAMES` conditional-defer pattern; the `copy_global_to(guild)`-before-`sync` ordering; the `_build_slash_envelope` underscore→hyphen vocabulary bridge. Currently scattered in leg-level comments.

## Test Metrics

Continuing the F13 debrief's cross-flight table (full suite run via the bounded `scripts/run-tests.sh` wrapper at debrief time):

| Metric | F10 | F11 | F12 | F13 | **F14** |
|--------|-----|-----|-----|-----|---------|
| Backend passed | 2749 | 2783 | — | 2796 | **2820 (+24)** |
| Backend skipped | 4 | 4 | 4 | 4 | **4** |
| Backend wall (s) | 254 | 246 | — | 243 | **301** |
| Browser passed | 431 | 443 | — | 454 | **460 (+6)** |
| Browser wall (s) | ~530 | 509 | — | ~520 | **591** |
| Pre-existing browser fails | — | — | — | 2 (since pre-F10) | **0 (L5 resolved both)** |

- **Backend +24** accounted for entirely by spec-sanctioned tests: L1 +2, L2 net +1 (3 v27 migration tests − retired api-validation rejection cases), L3 +1, L7 +8 (4 dispatcher-outbound matrix cells + 2 inbound pass-through + NotFound fallback + pre-READY edge — all required by L7's criterion prose, not the "+4" arithmetic line), L8 +3, L11 +1, L12 +6, L13 +2. 0 errors, 0 failures.
- **Browser +6, 0 failures**: L4 net +8 in one file (3 stale repaired + 5 new), L5 resolved the 2 pre-existing fails (assertion updates in place), L3's enumerate test is backend. The 2 deferred failures → 0.
- **Wall-clock**: backend 243→301s (+24 tests at ~2.4s each; plus minor CPU overhead from the zombie pile after the preceding browser run). Browser ~520→591s (+6 tests + a one-off chromium cold-start after a cache wipe; steady-state ≈540s). No throughput regression — the M10-flagged t/s concern is no longer the dominant signal.
- **No live orphaned processes** after either suite (the wrapper self-cleans); `<defunct>` zombies persist pending the tini follow-up.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L2 re-scoped 1-line → v27 unification migration | Flight DD's "orphan key" premise was false (`config.guilds` is the live "Scope to servers" field) | No (one-off), but the **premise-audit discipline** that would have caught it → YES |
| L9 dropped the discord.py 2nd-bot driver → single Chrome-MCP spec | A bot cannot invoke another bot's slash commands / observe ephemeral (platform constraint) | The **verify-apparatus-feasibility-before-locking** rule → YES |
| Flight grew 10 → 13 legs (L11/L12/L13) | L10 HAT surfaced 3 pre-existing slash-registration bugs (F/G/H) | The **HAT-exercises-the-real-entry-point** discipline → YES |
| `audit-log-inspector` behavior test deferred (not run) | Live-traffic seeding drift + `ChatSessionRepository.update` drops `session_metadata` on PUT (a KNOWN F13-debrief finding) | No — fast-follow; seed via a test-only session/fixture |
| Mid-flight `scripts/run-tests.sh` test-infra leg | Operator-flagged orphaned-browser-test CPU peg | The bounded-self-cleaning-runner pattern → YES (already in the Makefile) |

## Key Learnings

1. **A behavior-test spec is a specification of the real interaction, not just a test.** Authoring `discord-slash-end-to-end` forced reasoning about the actual slash path — its precondition-probe row ("6 commands appear in `/` autocomplete") is itself the test of slash registration that would have surfaced Bug F at F8. Writing it earlier (in planning) would have surfaced L9's infeasible apparatus immediately.
2. **Convergent invocation paths hide divergent bugs.** Text-prefix and slash invocations converge at the handler but diverge at entry (`on_message` vs `_build_slash_envelope`→`_parse_command`, plus `tree.sync` registration and interaction-token threading). Testing one to validate the other tests the wrong path.
3. **Precision unit tests can test the wrong layer.** Bug G.1's unit test called `_dispatch_builtin_command("talk_to", …)` directly, bypassing `_parse_command` — so it passed while production failed. When a handler is reached through a pipeline, at least one integration test must drive the full pipeline.
4. **Type-system enforcement beats discipline** (L8): replacing kwarg-defaults with a required dataclass made the Bug D class structurally impossible.
5. **Stated premises deserve a cheap verification before a DD is locked** — minutes of grep/API-check vs a full design-review re-scope cycle.

## Recommendations

1. **Integrate behavior-test spec authoring into the Mission Control planning phases** (operator-directed — see Methodology Feedback). Highest-leverage process change from this flight.
2. **Add a "premise audit" step to flight planning**: for each DD, name the falsifiable empirical claim it rests on and verify it (grep for code claims; API/doc check for platform claims) before marking the question resolved. Would have caught L2 and L9 at planning.
3. **Wire connector Python loggers to stdout** so `docker logs` captures connect/sync/ACL output (1–3 line change; high diagnostic payoff). Removes the largest diagnosis impediment for future Discord work.
4. **Make `ruff check` (and a scoped affected-file browser run on `data-testid`/element-type changes) part of the Phase 2d acceptance gate** — catches lint slips (N806) and browser-baseline drift before they enter the baseline.
5. **Add `tini` as PID 1** (Dockerfile) to reap zombies; **add a "Slash command architecture notes" subsection to agents.md** consolidating the four discord.py facts above.

## Methodology Feedback

**Operator directive: behavior tests proved highly valuable — integrate them into the Mission Control PLANNING phases, not just ad hoc.** This flight is the strongest evidence yet:
- The slash HAT (`discord-slash-end-to-end`) caught 3 pre-existing bugs (F/G/H) the entire unit/integration suite missed across 8 flights.
- The inference-roundtrip regression gate confirmed no F14 substrate regression.
- F13's debrief already found behavior tests catching a product bug unit tests missed.

The gap is **convention, not tooling** — the spec format + `AUTHORING.md` guide already exist; behavior-test specs are simply authored too late (a late leg) or ad hoc. Concretely, the recommendation is to make a behavior-test spec a **planning deliverable** for any criterion whose verification is "against the real environment":

- **`/mission`**: when a success criterion is real-environment-observable (UI flow, multi-component, AI-agent behavior, "validated against real X"), flag it at mission time as behavior-test-backed.
- **`/flight`**: for any criterion ending in a HAT/real-environment verification, the flight's Design Decisions should include a **behavior-test spec draft (or a named spec with apparatus + step-count + key observable identified)** authored in the same session as the other DDs — *before legs are locked*. The **apparatus choice (Chrome MCP vs 2nd-bot vs HTTP) deserves the same vetting as any other DD** (had L9's apparatus been a planning-time DD anchored on the proven `discord-engagement.md` Chrome-MCP precedent, it would have been correct from the start). The draft's precondition-probe rows often surface premise errors (e.g. "do the commands even register?") before implementation.
- **`/leg`**: the verification leg references the planning-time draft spec rather than designing the apparatus from scratch at leg-design time.

**This is a change to the Mission Control planning SKILLS (mission-control repo), not to the-one.** Per the project boundary, this debrief records the recommendation; the actionable skill edits live in `mission-control/.claude/skills/{mission,flight,leg}/`. The FD has offered to apply them (see the closing summary). The `behavior-test/AUTHORING.md` "When to Author" table already gestures at planning-time authoring; the gap is making it a prompted, expected deliverable in the mission/flight/leg skill workflows rather than an optional note.

## Action Items

- [ ] **Integrate behavior-test authoring into the `/mission`, `/flight`, `/leg` planning skills** (mission-control repo) — make a behavior-test spec draft (apparatus + steps + key observable) a planning deliverable for real-environment-verified criteria; vet the apparatus choice as a DD. *(Operator-directed; highest priority.)*
- [ ] Add a **premise-audit step** to the `/flight` planning workflow (verify each DD's empirical premise before lock).
- [ ] **F15 / maintenance**: wire connector loggers to stdout (observability); add `tini` as PID 1 (rebuild); re-run the `audit-log-inspector` behavior test after fixing the seeding path (test-only session/fixture).
- [ ] Add `ruff check` + affected-file browser run to the Phase 2d acceptance gate.
- [ ] Add the "Slash command architecture notes" subsection to `the_one/agents.md`.
- [ ] Cosmetic cleanup (next pre-flight or standalone commit): `/help` text shows `/talk-to` vs the `/talk_to` slash name (1-line in `_handle_help`); provider display name "Antrhopic" typo.
- [ ] **F15+**: the original F14 "live-traffic multi-user + rate-limiting HAT" framing (superseded by slash-HAT-closure) still owed; multi-user/multi-channel/pairing/mentions-aware HAT coverage for criterion #11.
