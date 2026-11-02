# Flight Debrief: Dead code

**Date**: 2026-11-02
**Flight**: [Dead code](flight.md)
**Status**: completed
**Duration**: 2026-11-02 – 2026-11-02 (one session)
**Legs Completed**: 2 of 2
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
- **Definite dead code deleted (#24).** 11 items, each re-grepped immediately before deletion, with the command and result in the flight log:
  - `scripts/entrypoint.sh`, `ui_capture._tool_read_file`, `VALID_ROUTING_SCOPES`, `UV_ENVIRONMENTS_ROOT`, `SEARCH_BACKENDS`;
  - the `.self-configuration-toggle-switch` rule and the `App.studio.AGENT_PANEL_IDS` export;
  - the `make_registry` fixture (and its CLAUDE.md bullet), `NO_SLEEP_HOOKS`, `_MISSING`, `_origin`;
  - the imports this left unused.

  `badge--local`/`badge--remote` and `ui-list-pane-compact` were kept because their factories string-build them. The first two are live (the MCP row badge). The third is an unused option value (squawk 0313). Vulture went from 252 to 248 lines.
- **Two test-only production methods retired (#25, settled items).** `Encryptor.rotate_key` and `ToolConfigRepository.list_all` are gone. Their properties moved to tests of the live code:
  - in-place cache promotion, checked against an independent `Fernet`;
  - 0o600 on the promoted key file;
  - promote drops the old key; discard leaves the key file unchanged;
  - both key-path guards, which had no test before;
  - `list()` carries each row's config without `enabled`.

  The factory spy test was inverted to "reads tool configs through `list()` once". Only `rotate_key`'s callback contract went with the method; the route rotation tests cover the real sequence.

### Mission Criteria Advanced
- "Dead code removed" — met: the definite dead code is deleted, `rotate_key` and `list_all` are deleted with their coverage moved, and no live code was removed (independently re-grepped by the flight Reviewer).
- With this flight, **all six Mission 34 success criteria are checked**. Finding #25's remainder stays outside the mission (operator decision below).

### Checkpoints
Both met: the sweep is deleted and the guards are green; the rotation primitives carry the 0o600 assertion (`test_promoted_key_file_permissions`).

## What Went Well
- **The design review saved Leg 2.** The flight's coverage inventory (carried from the maintenance report) said the 0o600 mode was the only property `rotate_key`'s tests alone pinned. The review found that:
  - the final-path mode, in-place cache promotion and both key-path guards had no live test;
  - discard was only partly covered;
  - a spy test (`test_factory_does_not_call_list_all`) would have broken;
  - removing the method would leave an unused import (ruff F401) and two stale mentions in `tests/test_factory.py`.

  All were fixed before implementation, and every new or extended test was falsified.
- **Evidence per deletion.** A pre- and post-deletion grep per item, recorded in the log, made the sweep auditable; the Reviewer repeated the greps independently and found nothing live.
- **Inverting instead of deleting.** The `list_all` spy test now pins the live contract (one `list()` read), so the regression it guarded stays guarded in its new form.
- **The no-coverage-loss table** (one row per removed test: the covering test, or "removed with the method" and why) met the mission constraint in a form the Reviewer could check row by row.
- **Small and fast.** Both legs were designed together; Leg 2's design review ran while Leg 1 was being implemented (no shared files); one review cycle with no issues.

## What Could Be Improved

### Process
- **The flight's citation audit verified the wrong claim for `rotate_key`.** It verified "only tests call it" (true) and treated the maintenance report's "the only property solely covered through it is the 0o600 mode" as fact. Those are two claims; the second was half wrong. A plan to retire test-only code should list what each doomed test asserts and name the live test that fails on the same regression before the leg is written (now squawk 0312's convention).
- **One more artifact edit by `sed -i`** (Leg 2's status line). It is an artifact, not source, so it is outside squawk 0286's rule; it is recorded only for the recurrence count.
- **No full gate ran in-flight**; the first full run was the debrief's.

### Technical
- **Lane drift since Flight 1, on a quiet reading.** See Test Metrics. Three lanes are over budget and three moved more than 15%; Flight 3 changed nothing browser-visible.
- **Squawk 0305 failed again** — now 3 of 3 full gates this mission.
- **Vulture still lists 248 items at 60% confidence.** Most are traps (handlers, hooks, callbacks); the sweep deliberately took only the definite items.

## Test Metrics

All numbers are from the **debrief's fresh run on `7f8d119f`**: the flight ran no full gate, so the crew file's reuse rule did not apply.

**Unit tier** (`THE_ONE_TEST_NETNS=1 make test-unit`, start load 0.07): 8603 passed, 15 skipped, 0 failed; pytest 226.6 s, wall 240 s.
- Flight 2 debrief: 8607 passed, 15 skipped, 243 s (netns).
- −4 tests is the expected net (8 `rotate_key` tests removed, 4 primitive tests added; the `list_all` tests were renamed, not removed).
- 17 s faster.

**Browser tier** (`--parallel 3`, `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1`): `PARALLEL_RESULT rc=1 total=2223s lanes=17 failed=chats-transcript`.
- **Start load 0.42**, after the unit tier's 0.79 settled. This applies Flight 2's lesson, so the reading is **budget-eligible** under squawk 0259's rule.
- End load 1.91.

| Lane | This run (s) | Budget (s) | CLAUDE.md measured (s) | Δ vs measured |
|---|---|---|---|---|
| routing | 599 | 720 | 564 | +6% |
| agents | 562 | 630 | 512 | +10% |
| contracts-controls | 558 | 600 | 509 | +10% |
| providers | 426 (OVER BUDGET) | 420 | 363 | **+17%** |
| shared | 426 (OVER BUDGET) | 420 | 362 | **+18%** |
| agent-tabs | 425 | 510 | 407 | +4% |
| chats | 421 (OVER BUDGET) | 420 | 370 | +14% |
| library | 388 | 420 | 348 | +11% |
| knowledge | 366 | 420 | 308 | **+19%** |
| chats-transcript | 330 (rc=1) | 390 | 291 | +13% |
| mcp-connection | 309 | 390 | 291 | +6% |
| settings | 303 | 360 | 286 | +6% |
| settings-tools | 297 | 330 | 271 | +10% |
| mcp | 289 | 330 | 268 | +8% |
| contracts-overlay | 275 | 330 | 246 | +12% |
| agent-routines | 255 | 300 | 245 | +4% |
| contracts-chat | 62 | 90 | 61 | +2% |

- Total: +196 s (+9.7%) over Flight 1's quiet 2027 s, and about level with Flight 2's loaded 2235 s.
- The rise is broad and Flight 3 changed no browser-visible code, so it is drift (host, or tests added in Flights 1 and 2), not this flight.
- **Operator decision: record only; re-budget after a second quiet reading confirms it.** CLAUDE.md's one-reading rule would re-budget providers, shared and knowledge now.
- Full gate: 240 s + 2223 s = 2463 s (about 41 min), inside the 43 min target.

**Flakes on this run:** one, squawk 0305 (`test_continue_sends_exactly_one_message_and_the_button_goes`, 96 passed and 1 failed in `chats-transcript`). It passed 3 of 3 isolated. This makes **3 of 3 full gates this mission**. 0229 and 0241 did not recur.

## Deviations and Lessons Learned

| Deviation | Why | Disposition |
|---|---|---|
| Leg 2's coverage inventory replaced at design review | the plan carried the maintenance report's "only the 0o600 property" claim | Design Review table in the leg; 4 new or extended tests, all falsified |
| `test_factory_does_not_call_list_all` inverted (not in the flight's table) | it spied on the deleted method | renamed to `test_factory_reads_tool_configs_through_list_once` |
| "Leave `tools/resolver.py` alone" became moot | sortie 07 and squawk 0296 had already removed the stale `list_all` mention | nothing to do |
| Three CSS variants kept | factories string-build them | recorded; `ui-list-pane-compact` → squawk 0313 |
| Accessibility Reviewer skipped | no user-facing change | recorded in the flight log |

## Key Learnings
- **"Uncalled" and "covered elsewhere" are separate claims.** Retiring test-only code needs both, and the second only holds per test, with a named live test that fails on the same regression.
- **Static grep cannot see string-built names, decorator registration or framework hooks.** The sweep's safety came from checking producers (`'badge badge--' + kind`) and leaving the trap list alone, not from the grep.
- **Letting the load settle between tiers made the debrief gate count.** The 0.42 start gave the mission its first budget-eligible reading since Flight 1, and it shows real drift.

## Methodology Observations

All in mission-control **1.2.3**.

1. **flight skill / agentic-workflow Phase 2a — citation audit scope.**
   - What happened: the flight's Citation Audit table marked the `Encryptor.rotate_key` row "verified" for "called only by tests". The flight's Technical Approach then carried a factual claim from the maintenance report as fact: "the properties those tests alone cover" were the 0o600 mode and in-place install. Neither the audit nor the leg template asks the designer to verify such derived claims, only code locations.
   - Expected: a claim about what tests cover is verified like a citation.
   - Cost: none here (the Leg 2 design review caught it), but a low-risk tier would have shipped a coverage loss against the mission constraint.
   - This is the same shape as Flight 2's observation 1 (an unverified prose claim about stored state, which that time did cost a re-run). Recorded for the mission debrief's recurrence count.
2. **agentic-workflow Phase 2a — design review effectiveness (credit).** For the second flight running, a high-risk design review changed a leg materially before code: Flight 2 Leg 3 (a dead design), Flight 3 Leg 2 (half the coverage inventory). Recorded so a later sweep sees the review as load-bearing, not ceremony.
3. **flight-debrief Phase 2 — fresh metrics.** With the brief now saying "wait for the load to settle after the unit tier", the browser run started at 0.42 and was budget-eligible. Flight 2's run, without that instruction, started at 1.19 and was not. The skill's generic "run the full test suite once" does not carry this; the project crew file's quiet-host rule should say "between tiers" too (project-side follow-up, not a plugin defect).
4. **Squawk 0286 / artifact edits.** The Developer used `sed -i` on a leg artifact's status line. The project rule covers source and test files only, so this was allowed; it is noted because it is the third `sed`/heredoc write this mission (two in Flight 2 were on test files).

## Recommendations

1. **(Critical) Fix squawk 0305 first in the squawk turnaround** (already the operator's decision at the Flight 2 debrief). It failed in all three full gates this mission, so no full gate can read rc=0.
2. **(Important) Take a second quiet-host reading and re-budget if it confirms the drift.** The lanes are providers, shared and knowledge (more than 15%), plus chats, providers and shared (over budget). Use the next full gate, for example the squawk turnaround's or the mission debrief's (operator decision: wait for that reading).
3. **(Important) Plan finding #25's remainder as the next maintenance item** (operator decision). Shape:
   - Scope: `ChatSessionRepository.append_to_session_metadata`, the `KBChunkRepository` delete/FTS methods, `RoutineRepository.set_next_run`, `DiscordRest.trigger_typing`/`get_guild_channels`, `tools/_search_stubs.py`.
   - Size: a small flight of 2–3 legs, grouped by risk, using Leg 2's coverage-table method.
   - Decide per method whether it is orphaned or has a planned caller.
   - Move true test seams into `tests/` rather than deleting them.
4. **(Minor) Write the dead-code method down** (squawk 0312) so the next sweep does not rediscover the exclusions, the string-built-name check and the coverage-table rule.
5. **(Minor) Add "let the load settle between the unit tier and the browser run" to the project crew file's debrief metrics rule** (`.flightops/agent-crews/flight-debrief.md`, "Test metrics: reuse the flight's gate").

## Action Items
- [ ] Squawk 0305 — first item of the squawk turnaround.
- [ ] [Squawk 0311](../../../../squawks/0311-promote-guard-no-arg-path-untested.md) — `promote_pending_key` guard, no-argument path.
- [ ] [Squawk 0312](../../../../squawks/0312-document-dead-code-method.md) — write the dead-code method into agents.md.
- [ ] [Squawk 0313](../../../../squawks/0313-listpane-density-option-unused.md) — trim `listPane`'s unused `density: 'compact'`.
- [ ] Second quiet-host browser reading, then re-budget providers, shared, knowledge (and chats) if confirmed.
- [ ] Finding #25's remainder — plan it for the next maintenance mission or a sortie.
- [ ] Crew file: "between tiers" in the debrief metrics rule (Recommendation 5).
- [ ] Carried, open: squawks 0229, 0241, 0306–0310.
