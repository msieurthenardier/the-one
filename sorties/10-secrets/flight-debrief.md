# Flight Debrief: Secrets

**Date**: 2026-11-05
**Flight**: [Secrets](flight.md) (sortie 10)
**Status**: completed
**Duration**: 2026-11-04 (charter) - 2026-11-05 (landing)
**Legs Completed**: 4 of 4 (3 autonomous legs, leg 3 in parts A and B, plus the HAT)
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
An operator stores a secret once in Library › Secrets and grants it per agent from the Tools tab. The agent writes `{{secret:key}}` in a tool argument, and the loop fills the value into a copy of the arguments just before the tool runs. Every stored value is masked to `[secret:key]` in results and error strings. In the HAT, a real model on the operator's own provider found Goldfinch's `vaultUnlock` through `search_tools` without being told and unlocked the vault. The stored call held only `{"accessKey": "{{secret:goldfinch_vault_key}}"}`.

Delivered:
- schema v51 and the eighth encrypted corpus;
- write-only routes;
- `GET /api/tool-names`;
- the refused-tool set;
- `SecretResolver` (substitution, masking, refusals, fail-closed);
- the Secrets prompt layer;
- the Library editor with `App.ui.chipList` search-ahead, the Tools-tab grant section, the drawer group, the Prompts example and Jump to;
- behavior test `secrets-round-trip` (10/10).

### Charter Criteria (sortie)
| # | Criterion | Met? | Note |
|---|---|---|---|
| 1 | A granted `{{secret:key}}` reaches the tool as its real value; the saved chat, trace and provider request hold only the placeholder | **Met** | Behavior run 1 steps 2-3 (file witness). HAT H5 with a real model and Goldfinch. The provider request is proven by leg 2's `FakeLLM` assertions; the mock provider records nothing (spec Out of Scope). |
| 2 | A result or error containing a stored value reaches the model and database as `[secret:key]` | **Met**, with two recorded limits | Behavior step 4, leg 2's encoding tests, and step 9 (zero plaintext in log, db and `-wal`). Limits (HAT fix F1, SECURITY-MODEL.md): short values over-mask unrelated text; masking checks text only. |
| 3 | An ungranted key, or a tool off the allowed list, is refused naming only the key | **Met** | Behavior steps 5-6 (exact wording) and leg 2's tests. With a real model the tool-not-allowed path was **not** exercised at runtime: the model declined on its own (H5). |
| 4 | A Library change applies to every granted agent's next call with no agent edits; no API returns the value | **Met** | Behavior steps 1, 7 and 8 (REST, live store and rotation); leg 2's same-Agent unit tests; HAT H6 in an open WebSocket chat. That test used the operator's Home address variant, since the Goldfinch vault does not relock, and the changed value rests on the operator's observation. |

### Checkpoints
All four were met (`flight.md` "Checkpoints"). Leg 3's full gate needed a second pass: G2 was `rc=1` on 12 stale pins in `agents`, `providers` and `settings`; those were fixed and the three lanes re-run green.

## What Went Well
- **The rendered mockup in the real CSS and factories (sortie 09's lesson applied).** Two operator rounds before legs locked, then **zero UI fixes in the HAT**. Sortie 09's HAT had rejected its surface and cost about two and a half legs. This is the first direct evidence that the remedy works.
- **Two Architect design reviews before legs locked.** Review 2 caught a false load-bearing claim (DD9: REST `/api/chat` with a `session_id` rebuilds the Agent on every call), which would otherwise have let the behavior test "prove" the long-lived-Agent property it cannot see.
- **Per-leg review and commit (sortie 09's practice).** Each review found something real: the AC2/AC4 empty-Library pass-through in leg 2, and the unpinned leave-guard `discard` in leg 3.
- **Fail-closed, single choke point.** The `core.py` touch is one kwarg, one `prepare` call, and the mask before `_govern`, so a truncated tail can't split a value. The timeout and exception strings are masked too. `secrets=None` is byte-identical (`test_an_agent_without_a_resolver_changes_nothing`).
- **Falsification as a habit.** The new tests were falsified by removing the code they pin: the repr needle, the omit-on-load-failure path, the empty-Library refusal and the leave-guard discard.
- **The behavior test ran after leg 2, before any UI** (Architect review 1 suggestion). Wiring was proven over REST early, so leg 3 only had UI risk.
- **The logging sweep (AC14) found a real leak path.** The `mcp` SDK logs whole JSON-RPC messages at DEBUG, so `mcp`, `httpx2` and `httpcore2` are now held at WARNING.
- **The HAT apparatus checklist (sortie 09 observation 4) was written into the leg.** Real PID from `ss -ltnp`, verified through `/proc/<pid>/environ`, a fresh link per context. There were no stale-instance problems.

## What Could Be Improved

### Process
- **Part A's gate picked lanes by the files it touched, not by what asserts on them.** A fifth Library group and a fifth Prompts layer changed counts that `agents`, `providers` and `settings` pin. G2 found 12 stale pins, which meant a fix round and a three-lane re-run. Rule for next time: when a leg changes a shared list, menu or table, grep the tests for its old count and labels and run every lane that matches.
- **A HAT prerequisite was assumed, not dry-run.** The flight assumed a Goldfinch vault could be locked again; it can't (a Goldfinch bug). H6 had to be substituted mid-HAT with a weaker witness: the operator's eyes on a typed postcode instead of an unlock failing on a wrong key. A HAT step that depends on an external system's behaviour should get the same dry run the behavior test's seed gets.
- **The Flight Director recorded a security finding before checking the code.** HAT finding (b) said screenshots carry secret values to the model. The F1 Developer showed that MCP images reach the model only as `[image: N bytes, mime=...]`, and the block stays in `ToolResult.raw`, which nothing reads; the model's own reply said it couldn't read the image. It cost one doc rewrite. A HAT finding about a leak path should be checked in code before it goes in the log.
- **Debrief crew claims needed checking.** Four crew claims were false on inspection:
  - the Developer said `flight.md` still carries the stale REST claim (it was corrected at review 2, lines 168 and 188);
  - the Developer said the spec promised image masking (no sortie 10 artifact mentions images);
  - the Architect said keys differing only by case could collide (`secret_values.key` is `UNIQUE COLLATE NOCASE` Library-wide);
  - the Architect said the `MCPAuthRequired` branch returns unmasked output (it returns the fixed `<auth required>`).

  Both agents said they had skipped files. Their reports were useful, but every claim had to be verified before it went in.

### Technical
- **No minimum masking length** is the operator's accepted choice, and the HAT showed its cost: a dummy postcode replaced part of a base64 alphabet in a page script (`…XYZ0[secret:home_postcode]6789+/=`). That corrupts what the model reads, though it never leaks. A boundary-aware mode for short values is a design question for a later sortie (see Recommendations).
- **The refused-tool set is a hand-kept list** (`secret_store/refused.py::_FIXED_REFUSED` plus prefixes). A future built-in that stores or publishes its input would be allowable until someone remembers the list. Better: a per-tool `persists_arguments`-style declaration that the set is derived from, with a test that fails on an undeclared tool (Architect).
- **The uncached resolver.** Once any secret exists, every tool call of every agent decrypts every value and runs about four queries. A database fault refuses every tool call, even for agents without grants. That is correct by design, fixed-cost and pinned (`test_fixed_number_of_queries`), but unmeasured at scale. If it ever matters, use a write-generation stamp in `app_metadata` (DD7 already allows that), not a TTL.
- **`core.py` repeats the mask-then-withhold block three times** (success, timeout, exception). A small helper would stop a fourth branch landing unmasked. The frozen-loop policy argues for waiting until the loop is next opened.
- **Coverage gaps found by the Developer** (all small):
  - no test with regex metacharacters in a value (`re.escape` is used);
  - a `{{secret:…}}` inside a dict **key** is neither filled nor refused, which is safe but unspecified and untested;
  - the routine and connector paths are tested only for the hook's presence (a refusal), never for a positive grant.
- **The Tools-tab Secrets section polish carried from leg 3**, which the operator did not raise in the HAT:
  - the 422 status is un-hidden and filled in one step;
  - the error isn't linked to the switches, and the list isn't a labelled group;
  - a stale error survives a toggle;
  - a secret deleted in another tab leaves its row until refresh.
- **Pre-existing:** rotation gathers corpora before its write transaction.

### Documentation
- HAT fix F1 added the two masking limits to SECURITY-MODEL.md and `agents.md`. `flight.md` had said SECURITY-MODEL.md recorded the short-value limit before it did. The claim is true now.
- `agents.md` "Secrets (sortie 10)" could gain a short checklist for any new **output channel** (streaming, PTY reads, image or resource blocks forwarded to a model). Today only `_execute_tool`'s returned string is masked (Developer, Architect).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Mockup in the real CSS and factories, two operator rounds, before the leg design | Sortie 09 observation 1 | **Yes**: it already produced a HAT with no UI fixes |
| Per-leg review and commit instead of one flight-end review | Sortie 09's practice; risky shared surfaces | Yes, for multi-leg flights touching security or shared UI |
| Leg 3 split into parts A and B, with the gate between them | Five UI surfaces plus a library control change | Yes, when a leg carries a library change and its consumers |
| 3 legs plus HAT, above the 2-leg soft limit | Accepted at planning; the prompt-migration helper was cut to stay near it | No: an honest 4-leg estimate up front would have been clearer (Architect) |
| Behavior test run after leg 2, before the UI | Architect review 1 | Yes, for runtime features with a REST path |
| H6 substituted (Home address with `typeText`) | The Goldfinch vault does not relock | No: dry-run external HAT prerequisites instead |
| Quiet-host gate precondition waived for G2 | Operator's loaded-host note | Only on operator say-so; the debrief re-ran a quiet gate |
| HAT fix F1 reviewed by the Flight Director, not a crew Reviewer | Doc-only, two paragraphs | Yes, for doc-only HAT fixes |

## Key Learnings
- **Show the real surface, early.** A mockup built from the product's own CSS and factories, approved before legs lock, moves UI disagreement to the cheapest point. Two sorties of data now: an ASCII sketch (sortie 09) cost about 2.5 legs; a rendered mockup (sortie 10) cost none.
- **A fast path in a fail-closed design must come from the refusal conditions.** The empty-Library pass-through came from writing the optimisation first: a literal token would have reached a tool.
- **Name what a test cannot see.** REST rebuilds the Agent per call, so a REST behavior test cannot prove the long-lived-Agent property. Writing that into the spec's Out of Scope kept the HAT step honest.
- **Masking is literal and global.** It works on exact textual forms (six encodings), so its two failure modes are a transformed value (not masked) and a short value (masked too widely). Both are now written down; neither surfaced until real pages went through a real browser tool.
- **Verify a leak claim in code before recording it.** In this flight, both the Flight Director and the debrief crew got one wrong from a partial read.

### Test Metrics
Fresh gate on `ba5ff7ee` (the branch head), run by the Flight Director on a quiet host. The flight's own G2 ran loaded with its quiet-host precondition waived, and three lanes were re-run after it, so its numbers don't count for budgets. Comparison by the debrief Developer.

- **Unit:** `THE_ONE_TEST_NETNS=1 make test-unit` at start load 0.29: **9136 passed, 15 skipped** (the expected netns count), 258.5 s.
  - Sortie 09: 8963 passed, 15 skipped, 242 s.
  - Sortie 08: 8777 passed, 226 s.
  - +173 tests and +7% time over sortie 09, in proportion. Inside the 300 s target.
- **Browser:** `--parallel 3`, WebKit required, netns, start load 0.88: **`PARALLEL_RESULT rc=0 total=1938s lanes=17 failed=-`**. No failures, no flakes, no lane over budget.
  - Sortie 09: 1855 s; sortie 08: 1858 s; that is +4.5%.
- **Full gate:** 2196 s (36.6 min), inside the 43-minute target.
- **Lanes this sortie grew:**
  - `agent-tabs`: 466 s, **91%** of 510, +14.5% over the CLAUDE.md M34 reading of 407 s. It gained `test_flow_agent_secrets.py`; sortie 09 had already flagged it at 83%.
  - `library`: 379 s, **90%** of 420, +9% over 348 s. It gained `test_flow_studio_secrets.py`.
  - `chats` sits at 91% of 420, unchanged and unrelated.
- **The three contract lanes ran 26-29% faster** than the M34 reading (`contracts-controls` 379 s against 509 s). No sortie 10 change explains it; likely host or engine variance. It is not a regression.
- `routing` and `agents` are flat, so the Secrets routes and Jump to entries cost nothing measurable.

## Methodology Observations
Recorded against mission-control **1.2.3**. Not judged.

1. **flight skill, Phase 5b / flight-design crew rule 6 (mockups): the remedy from sortie 09 observation 1 worked.**
   - *What happened:* the design step built the mockup in the product's real CSS and factories, and asked which existing surface it should resemble (the provider editor, the MCP headers table). The operator approved it over two rounds.
   - *Expected:* as hoped.
   - *Cost:* none (positive). The HAT had zero UI fixes, against about 2.5 legs of rework in sortie 09. Recorded so a sweep can count a fixed observation.
2. **agentic-workflow, Phase 2b/2d (per-leg gates): no guidance on choosing verification lanes for a change to a shared structure.**
   - *What happened:* the leg 3 part A gate ran the lanes that own the changed files. A fifth Library group broke count and label pins in three other lanes, found only at the flight's full gate.
   - *Expected:* guidance that a leg changing a shared list, menu or registry verifies every suite that asserts on it, found by grepping the old count and labels.
   - *Cost:* 12 test fixes in a separate round, and a three-lane re-run.
3. **agentic-workflow, HAT legs (leg design): external prerequisites are listed but not dry-run.**
   - *What happened:* `flight.md` Prerequisites said "re-verify at the start of leg 4" for Goldfinch. The re-verification checked that Goldfinch was reachable, not the behaviour H6 needed (relocking a vault). The behavior-test skill requires a dry run of the seed; the HAT has no equivalent.
   - *Expected:* a HAT step that depends on an external system's behaviour gets a dry run when the HAT is designed.
   - *Cost:* H6 was substituted mid-HAT, with a weaker witness: the operator's observation instead of a deterministic failure.
4. **agentic-workflow, HAT inline-fix protocol: no step to verify a finding before logging or fixing it.**
   - *What happened:* the Flight Director logged "screenshots carry the secret to the model" from a transcript read and briefed a doc fix on it. The fixing Developer showed it was false from the code.
   - *Expected:* the inline protocol could say that a HAT finding is verified against code before it is recorded or briefed, especially a security claim.
   - *Cost:* one doc rewrite, plus a corrected log entry and leg addendum.
5. **flight-debrief, Phase 2 crew prompts: crew reports mix verified and unverified claims without marking them.**
   - *What happened:* the Developer and Architect each stated two false claims as findings (listed under Process), while saying elsewhere that they hadn't read some files.
   - *Expected:* the debrief crew prompts could ask for each claim to be marked "verified in code" or "from the log", or forbid a defect claim about an unread file.
   - *Cost:* the Flight Director checked four claims by hand; none reached the debrief.
6. **sortie skill, "Re-check the gate": the leg budget was exceeded knowingly and it worked.**
   - *What happened:* the sortie went 3 legs plus HAT against the 2-leg soft limit, accepted at planning. Leg 3 then split into parts A and B. The skill's options at that gate are "consolidate or escalate".
   - *Expected:* a third option: accept an overage the operator agrees to, with the reason recorded. That is what happened here and in sortie 09.
   - *Cost:* none; the sortie was still one decision cluster, so it was the right vehicle. Recorded because two consecutive sorties went over the limit.
7. **flight-debrief crew file, "Test metrics: reuse the flight's gate": the reuse rule's path filter counts doc-only changes under `the_one/`.**
   - *What happened:* the gate could not be reused here anyway (it ran loaded). But the rule would also have required a fresh run for HAT fix F1, which touched only `the_one/agents.md`.
   - *Expected:* doc files under `the_one/` (`*.md`) could be exempt like the lane-budget table.
   - *Cost:* none this time. Project crew-file scope, not plugin.

## Recommendations
1. **Re-budget or split `agent-tabs` (91%) and `library` (90%) before the next sortie that adds tests to them.** Sortie 09 flagged `agent-tabs`; this sortie added to both.
2. **Derive the refused-tool set from a per-tool declaration** instead of the hand-kept list in `secret_store/refused.py`, with a test that fails on an undeclared built-in. A new storing or publishing tool must not become allowable silently.
3. **Keep the short-value masking limit visible.** The operator kept mask-everything, so the limit stays in SECURITY-MODEL.md. Reopen it only if a real secret's over-masking misleads an agent.
4. **Add the three small missing tests:**
   - a value with regex metacharacters;
   - a placeholder in a dict key (pin its behaviour);
   - a positive grant used on the routine-run and connector paths.
5. **Gate lane selection:** when a leg changes a shared list, menu or table, grep the old count and labels across the browser tests and run every matching lane (CLAUDE.md "Testing" note).

## Operator Interview
- **Short-value masking:** keep it as it is: mask every value everywhere, with no minimum length. The HAT's over-masking is accepted, and no follow-up is planned.
- **Secrets in existing agent prompts:** the operator will move them by hand. No helper or prompt warning.
- **Mockup fidelity:** not asked separately. The HAT's zero UI fixes and the operator's passes are the record.

## Action Items
- [ ] Re-budget `agent-tabs` and `library` from this gate's quiet-host reading: **squawk 0330**.
- [ ] The three missing tests in Recommendation 4: **squawk 0331**.
- [ ] Tools-tab Secrets section errors (the 422 announcement, the error linked to the switches and a labelled group, the stale error cleared on toggle): **squawk 0332**.
- [ ] Drop a secret's row from the Tools tab when it is deleted in another tab: **squawk 0333**.
- [ ] CLAUDE.md "Testing": the gate-lane rule in Recommendation 5: **squawk 0334**.
- [ ] Derive the refused-tool set from per-tool declarations (design; a future sortie).
- Short-value masking policy: **closed by the operator** (kept as is).
- Prompt-secret warning: **closed by the operator** (manual migration).
