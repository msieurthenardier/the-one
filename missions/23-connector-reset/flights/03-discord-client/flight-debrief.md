# Flight Debrief: Discord Client

**Date**: 2026-09-02
**Flight**: [Discord Client](flight.md)
**Status**: landed
**Duration**: 2026-09-01 → 2026-09-02 (single continuous orchestration session)
**Legs Completed**: 4 of 4

## Outcome Assessment

### Objectives Achieved
The full flight objective, delivered: a hand-rolled Gateway v10 + REST Discord client (767 of the 1,100-line budget, zero new dependencies), the mission-amended send-tool visibility carve-out (exactly 27 sanctioned agent-loop lines), the `enabled` pause-without-delete key, the platform-agnostic sever seam, and live proof — `/behavior-test discord-live-round-trip` PASS 6/6 against a real guild, plus a guided HAT verifying every human-only path (DM silence, pairing, DM round-trip, private console, instructed send). Three design gaps the paper reviews missed were found by the live gate, decided by the operator, fixed, and re-proven mid-run (DD-4 amendment, DD-10, DD-11).

### Mission Criteria Advanced
- **Live channel contract** (criterion 1): @mention reply, always-listen, untracked silence, agent-initiated send, resume-after-disconnect — all observed live; DM/pairing half verified in the HAT. ✔
- **No discord.py/aiohttp** (criterion 2): `pyproject.toml`/`uv.lock` untouched. ✔
- **Budgets** (criterion 3): connector Python running total 1,782/3,000; flight JS +45 of ≤50 (~720/1,000 mission). ✔
- **New live HAT** (criterion 10 second half): leg 4 is the `discord_hat` replacement, executed. ✔
- **Carve-out** (RQ8 amendment): five pin tests + live no-nudge proof (with the model-tier caveat below). ✔

## What Went Well

- **The live gate earned its existence**: 3 real findings in 6 checkpoints — a 50% real-finding rate, zero apparatus-noise verdicts (Validator's own closing assessment). Every failure produced an operator decision and a unit-tested mechanism, not a workaround.
- **The mid-flight amendment discipline was exemplary** (Developer interview's words): each gap followed the same loop — operator decision via explicit structured choice, DD amended in place with dated annotation, Developer spawned, superseded contracts re-authored deliberately (Flight 2's stub spec) rather than silently broken, checkpoint rerun under the sanctioned disposition. The methodology held under real pressure.
- **Design reviews caught real bugs before code existed**: leg 1's missing sequence-number tracking (the resume test would have passed on opcode alone), leg 2's disabled→disabled PUT restart trap, leg 3's unimplementable stub re-aim. Seven paper passes were not wasted — they caught a different defect class than the gate did.
- **Citation-audit discipline paid off**: every leg spec verified its line citations against the working tree pre-flight; zero mid-leg drift incidents (contrast Flight 1's stale-citation bug class).
- **The fixture design paid for itself pre-gate**: leg 1's zero-delay-dispatch test caught a real READY race during implementation.
- **Validator fresh-observation proof patterns** (reusable, from the run log): `edited_timestamp=null` to separate read-side redaction from data change; DOM parent-chain containment (`details.contains(node)`) to settle top-level-vs-nested rendering; log-signature uniqueness matching (`/users/@me` cold-start fingerprint) to prove a reconnect was genuine.
- **Leg breakdown validated by outcome**: isolating the two hard-to-reverse changes (leg 2) meant live-gate failures were cleanly attributable to new gaps, never to "is the carve-out even working."

## What Could Be Improved

### Process
- **Three review-time questions would have caught the three live findings on paper** (Architect interview — lift these into the methodology):
  1. *DD-to-DD contradiction sweep*: "for each DD defining an admission/drop rule, does any other DD's apparatus or actor fail that rule?" (catches DD-4/DD-7 — two paragraphs apart in the same file, never cross-checked across 7 review passes).
  2. *Trace-the-happy-path*: "walk one complete round trip through the DDs as written — at which DD does the reply cross back onto the platform?" (catches DD-10's hole, on paper, no Discord needed; the gap was even pre-named in the stub spec's Out of Scope and planning never picked it up).
  3. *Tool parameter-source audit*: "for each tool made visible/mechanically invoked, list every required parameter and its source — prompt, conversation, or must-guess?" (catches DD-11 immediately).
- **Model capability is a live-gate prerequisite**: checkpoint 5 burned a full rerun cycle establishing that ministral-3:8b confirms-before-acting even with the mechanism present and understood. Confirm a capable model *before* the gate leg. **Operator posture decision (2026-09-02): gpt-oss:20b-class is the supported floor for tool-using agents; ministral-class is out of scope.**
- **Subagent stall pattern**: 3 of 6 Developer spawns this flight stalled by backgrounding a long test run and ending their turn "waiting" — despite explicit preemptive instructions (8 occurrences mission-wide). Each cost a resume round-trip. Harness feedback filed; until fixed, the resume-with-foreground-directive recovery is the standing play.

### Technical
- **DD-11 keying duplication**: `_resolve_default_target` mirrors `resolve_session`'s keying by convention/comment, not by construction. Extract a shared `keying_to_target(session)` helper *before* Telegram adds a third copy (Flight 4 forcing function).
- **Implicit stop-before-start invariant**: `_run`'s permanent-failure return leaves the `_ListenerEntry` in place, correct only because both recovery paths (PUT, rotation-restart) call `stop()` first — an untested multi-file invariant. → squawk 0033.
- **Unbounded `channel_type_cache`** (`discord/plugin.py:60-62`): accepted personal-bot-scale debt, documented in code; revisit only if deployment shape changes.
- **Suite crossed 7 minutes for the first time** (456s, +17% over leg 3's close) — proportionate to genuinely new test surface (86 new test functions this flight), not a regression, but worth a formal time budget conversation if the trend continues.

### Documentation
- Citation drift at `inbound.py:62` (names the wrong pin test) → squawk 0034.
- Studio-lane full-run timing flake is now a three-occurrence house pattern (leg 2, leg 3, this debrief's run — always full-lane-only, never reproducing isolated) → standing note in the lane, squawk 0035.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| DD-4 amended mid-flight (allowlisted-bot admission) | Live gate: apparatus output couldn't be admitted | Yes — the third apparatus-audit axis (below) |
| DD-10 added mid-flight (auto-reply fallback) | No mechanism existed for replies to reach the platform | Yes — mechanical-fallback convention now proven twice (DD-5, DD-10); apply at planning time via trace-the-happy-path |
| DD-11 added mid-flight (session-default target) | Target undiscoverable by the model | Yes — parameter-source audit at planning |
| Behavior-spec precondition amended in place (driver-bot Message Content intent) | Old advice assumed API-side assertions; the driver-REST observe path needs the intent | Yes — required platform intents belong in spec Preconditions explicitly |
| test-agent model swap (ministral → gpt-oss:20b) | Model-policy failure tier, not wiring | Yes — model floor now an operator posture |
| Reviewer accepted studio lane on documented prior greens, then confirmed live | 2-min default timeout auto-backgrounded the lane | Acceptable disposition; note the flake pattern |

## Key Learnings

1. **The apparatus premise-audit needs a third axis**: *can it act*, *can it observe*, and now **can its output be admitted by the system under test**. (Flight-log's own words, minted at checkpoint 2.)
2. **Unit and fixture tests cannot catch mechanism-composition gaps** — all three live findings were gaps in what the system *does* with correctly-computed results, invisible to any test that scripts the model. Flight 2's "only a live run proves perception" lesson generalizes to protocol-level mechanism gaps.
3. **Some behavior-test findings are model-tier findings, not code findings** — a no-nudge proof's verdict is partly a property of the bound model. AUTHORING.md should name this confound (extends Flight 2's nudge lesson).
4. **The additive-seam criterion needs rewording before Flight 4 is graded against it**: Discord went 4-for-4 on deliberate, named shared-code touches (base.py, manager.py, inbound.py, connector_send.py). "Additive" should mean "every shared-code touch is named, minimal, and platform-agnostic in the DD that introduces it" — which is what actually happened and held up — not "no shared-code touches," which even Discord failed for legitimate reasons. **Mission-owner decision needed before Flight 4 planning.**
5. **House pattern worth naming**: this codebase's DD-citing inline comments (every non-obvious choice names its DD, review cycle, and rejected alternative) made all seven review passes and both debrief interviews materially cheaper — keep doing it.

## Test Metrics

`make test-unit` (debrief run): **3,758 passed, 10 skipped, 551 deselected, 17 warnings, 456.03s**. Studio lane: **146+1-flake passed / 3 skipped, 312.90s** (flake reproduced-isolated-clean in 2.5s — the standing lane pattern). Trend: F1 close 3,561 @ 352s → F2 close 3,669 @ 398s → F3 close 3,758 @ 456s. The +22 pass-count vs. +86 raw new test functions since F2 reflects deselection/parametrization effects plus the mission's recurring ±1-2 count drift — flagged, never grounded, likely not worth chasing.

## Recommendations

1. **Methodology (for the mission debrief to carry to mission-control)**: add the three review-time questions to the flight/leg design skills, and the third apparatus axis + model-tier-finding confound to behavior-test AUTHORING.md.
2. **Mission owner, before Flight 4 planning**: reword the additive-seam criterion per Key Learning 4.
3. **Flight 4 (Telegram) design inputs**: extract `keying_to_target` before a third keying copy; reuse the sever-hook and fake-server fixture patterns as templates; budget real design time for what "reconnect" means for long-poll (no gateway-resume analog); confirm the gate model up front; carry the HAT's two recorded features (name-directory send targeting — the operator's "persist friendly names with ids as observed" framing verbatim — and the per-connector setup help file).
4. **Convert the small concrete items to squawks** (see Action Items).

## Action Items
- [x] Squawk 0033 (logged) — test pinning the stop-before-start `_ListenerEntry` invariant (or comment cross-references at both call sites)
- [x] Squawk 0034 (logged) — fix citation drift at `the_one/connectors/inbound.py:62` (wrong pin-test name)
- [x] Squawk 0035 (logged) — standing studio-lane flake note (isolated-rerun-before-treating-as-regression) in the lane's conftest/header
- [x] Squawk 0036 (logged) — test for DD-10's skip-rule cross-channel trade-off (tool-send to a different channel suppresses that turn's auto-reply — assert and document the accepted behavior)
- [ ] Mission debrief: carry methodology recommendations (review questions, third axis, model confound) to mission-control
- [ ] Flight 4 planning: additive-seam rewording decision; keying_to_target extraction; the two HAT feature requests
