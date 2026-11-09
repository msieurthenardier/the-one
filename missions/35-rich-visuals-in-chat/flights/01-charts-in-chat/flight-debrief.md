# Flight Debrief: Charts in Chat

**Date**: 2026-11-09
**Flight**: [Charts in Chat](flight.md)
**Status**: landed (flight marked `completed` at this debrief)
**Duration**: 2026-11-08 - 2026-11-09
**Legs Completed**: 5 of 5 (4 implementation legs + HAT)
**Plugin version**: 1.2.3

## Outcome Assessment

### Objectives Achieved
An agent reply can carry a ```` ```chart ```` block that the chat draws in place:
- bar, line, area, scatter, pie and sparkline;
- stacking, two y-axes, log scales, reference lines;
- a value tooltip with a keyboard live reading, and a "Show data" table;
- the current theme, followed without a reload, including Auto following the OS.

While a chart streams, a glimmering placeholder in the chart's shape holds the space, and the chart replaces it the moment its block closes. A broken chart shows a plain danger notice with the source under Technical details; a cut-off chart shows a muted notice. The format is written once (`docs/chart-format.md`) with a shared corpus (23 valid, 60 invalid, 43 number-format rows). The browser and the server-side `the_one/visuals/chart_spec.py` validate against it with identical sentences; the Python one is what Flight 3 reuses. Each agent has a "Rich visuals" switch (schema v52, on by default) that adds a short platform-prompt section.

PR #363 holds four commits: `37eb0309` legs 1-4A, `aeb4198b` the m35 baselines, `8f20d378` the HAT fixes, and `2f3b6ddb` the landing.

### Mission Criteria Advanced
| Criterion | This flight | Notes |
|---|---|---|
| Charts appear in the app | met | All types; theme change without reload; text alternative ("Show data", aria summary, keyboard live node) |
| A visual appears when it is ready | met for charts | Placeholder, error and cut-off notices, Copy reply unchanged; Flight 2 extends to live visuals |
| Operators choose per agent | met | Switch on by default, existing agents included; it takes effect at the next join, new chat or routine run (pinned by tests) |
| The prompt cost is measured and accepted | met, with a caveat | The operator accepted +107 tokens and the m35 baselines were recorded. The HAT then added +96 (section now 203 tokens), checked only with n=5 sentinels, so the **m35 baselines are stale against the shipped prompt** until the deferred re-baseline |
| Visuals work in the desktop app | met for charts (WebKitGTK) | WebKit contract lanes, plus a WebKitGTK 2.52.6 probe in both themes. The probe cannot check console errors; WebView2 and WKWebView are Flight 2's engine leg |
| Live visuals / connectors / chart images | not this flight | Flights 2 and 3 |

All six checkpoints were met.

## What Went Well
- **One doc, one corpus, two validators.** The parity design (DD3) held across the whole flight. The security reviewer fuzzed the Python validator with adversarial input (100k nested brackets, 2M-element arrays, NaN, bytes) and it never raised. Flight 3 inherits a ready contract.
- **The design reviews caught real faults before code.** The two flight-design cycles and four leg design reviews caught:
  - a column-0 fence rule that would split code blocks in list steps;
  - a gap between a closing fence and the commit;
  - a prompt flag threaded through capabilities that are never rendered;
  - quadratic parse cost;
  - a scroll-pinning trap.

  None reached the HAT.
- **Falsification paid off.** Leg 2 found that its first fence tests passed even with parse confirmation removed, because fast mock streams drain at `done` and never exercise commit logic. The tests were re-paced (5 characters every 100 ms) and falsified. The hold invariants, the parse-count bound and the width test were each falsified too.
- **Parser-confirmed streaming commits** (`areas/chat/chart-stream.js`): the scanner proposes, the real parser confirms, and a per-generation verdict cache with a poison rule bounds the cost. It is a reusable pattern.
- **A mid-flight commit before quota** (DD13) meant every eval run measured reviewed, committed code. The n=5 sentinel caught nothing alarming, so n=20 proceeded.
- **Security and accessibility:**
  - The code review found no HTML sinks, only safe SVG elements, and model text through `textContent`.
  - The accessibility review added the keyboard live reading and removed a redundant live region.
  - The chart palette passed contrast on the composited bubble untuned (lowest ratio 4.72:1).
- **The HAT walk:** all 9 steps passed. The usage-walk question ("what would you want day to day?") produced no gaps.

## What Could Be Improved

### Process
- **A prompt trim silently dropped approved scope (important).** Leg 4 AC1 allowed trimming DD12's draft "by measurement" while naming the optional keys. The Developer cut to 108 tokens and dropped `y2`, series `type`, `annotations` and `scale: log`, and the flight review did not catch it. The HAT found dual-axis and target-line charts undiscoverable on a real model. Restoring them cost a prompt edit, a pin regeneration, a sentinel run and an instance restart. Then the bar-only example left pie's `x.values` rule to guesswork (haiku put slice names in `"labels"`), which needed a second edit. The validator supported every feature; the prompt made some of them dead scope.
- **HAT apparatus defects cost round trips (minor).** The Flight Director's seed:
  - put a ```` ```chart ```` opener mid-line;
  - sent a chart body in one chunk, so "Stop mid-chart" could not land mid-JSON.

  Each cost a re-seed and a repeated step.
- **A leaked HAT server (minor, own goal).** The HAT restart recorded `$!` of a `nohup` wrapper instead of the server's PID. The server kept listening on 8490 until a `ps` check before the closing gate found it, identified it from `/proc/<pid>/environ`, and stopped it.
- **A verification item with no owner (minor).** The WebKitGTK probe was in the flight's Verification section, but no leg owned it, so it ran only at landing.

### Technical
- **`ui/chart.js` is 1,475 lines** in one control: parsing, layout, scales, six renderers, tooltip, keyboard, live node. Split it before Flight 2 adds more.
- **Axis text width is estimated** at 6.4 px per code point (`chart.js` near `:512` and the truncation near `:789`). That is wrong for CJK, emoji and bold. Measure with `getComputedTextLength` or a cached canvas measure, falling back to the estimate. Flight 3's server renderer needs its own font metrics anyway.
- **`transcript.js` is at about 710 lines** against the 800-line area rule; the scanner had to move out. The next chat feature should extract commit and pacing first.
- **A third place tracks fence rules:** `evals/checks.py`'s top-level scanner mirrors `markdown.js` (it is pinned and falsified).
- **The m35 eval baselines are stale against the shipped prompt** (fingerprint `99842c3f` vs `9f213ed2`), and the `_VISUALS` log-scale clause is loose ("on an axis"; x log is scatter-only). Both are deferred to one re-baseline.
- **Small models never chart** (qwen3-4b and lfm3: 0/120) and pay about 200 prompt tokens. The operator decided to leave it: operators can turn Rich visuals off per agent.
- **Unexplained eval readings:**
  - qwen3-4b `notes-as-told` fell 19/20 → 11/20 against s11. The on/off control run was not done, so it is not attributed to this flight.
  - Three small-model safety cells sit at 19/20 in the m35 baselines (accepted as noise).

### Documentation
- **Streaming-test rule:** mock streams must be slower than the 16 ms pacing tick, or commit logic is never exercised. Record it in `agents.md` "Charts in chat" or the UI test apparatus notes.
- **Operator note:** small local models do not write charts.
- **Text-width estimate:** its limits are not stated in `docs/chart-format.md`.
- **HAT instance recipe:** take the server PID from `ss -ltnp`, not `$!`. The behavior-test credential section of CLAUDE.md is the natural home.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| A valid chart with an unclosed fence still draws (leg 1); the cut-off notice is only for invalid or truncated JSON | Better for a stream that ends without the closing fence | Yes. State it in the design next time; DD8 implied every Stop gives the cut-off notice, which made HAT step 5's first try look like a bug |
| The scanner moved to `areas/chat/chart-stream.js` | The 800-line area rule | Yes (an area module split for size is fine) |
| Leg 4 split into Part A and Part B around a mid-flight commit; one review over legs 1-4A | Eval runs must measure committed code | Yes for eval-driven legs |
| Charts get a preferred `width: 46rem` inside the assistant bubble (HAT) | A shrink-to-fit bubble plus a chart that measures its container is circular | Yes. A control that lays out from its container needs an explicit preferred width in auto-width parents |
| Prompt additions during the HAT were checked by sentinel only, with the re-baseline deferred | Operator choice (cost and time) | Only with a tracked follow-up; CLAUDE.md now names stale baselines as current |
| `contracts-chat` was budgeted from loaded solo readings in leg 1 | No quiet host mid-flight | No. The closing gate re-measured it (150 s), as the rule says |

## Key Learnings
- **A trimmed prompt must still name every feature the design approved.** Token-trimming is a design decision, not an implementation detail. The leg should carry the must-mention list.
- **Run the real parser on candidate cases at design time.** DD10 took three revisions. Each reviewer that ran `markdown.js` under node found a case the prose missed.
- **A seemingly cosmetic layout assumption ("fill the container") hides an intrinsic-size dependency** in a shrink-to-fit parent. Only the real app showed it.
- **Streaming tests need streams slower than the consumer's pacing**, and falsification is what reveals a test that can't fail.

### Test Metrics
Source: the **closing gate at `8f20d378`**, on a quiet host (start load 0.43), with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`. It is reused under the crew file's rule, since `8f20d378..HEAD` touches only the lane-budget table, CLAUDE.md and artifacts.
- **Unit tier:** 9642 passed, 15 skipped (the expected count under netns), 256 s.
  - Against the sortie 14 debrief (9372, 258.7 s): +270 tests, -2.7 s. The growth is `test_chart_spec.py` (147), `test_evals_visuals.py`, `test_agent_rich_visuals.py` and the schema pins.
  - Under the 300 s standing target.
- **Browser tier:** `PARALLEL_RESULT rc=0 total=2163s lanes=17 failed=-`, with no flakes.
  - Against sortie 14: 1989 s, +174 s (+8.7%), though sortie 14's start load was 0.97.
  - Against M34 F1: 2027 s, +136 s.
- **Lanes:**

  | Lane | Measured | Budget | Previous reading | Cause / note |
  |---|---|---|---|---|
  | `chats-transcript` | 430 s | 390 s (over) | 291 s at M34 F1 (+48%) | The 25 chart flow tests with deliberately slow streams. Re-budgeted to 540 s |
  | `contracts-chat` | 100 s | 120 s | 61 s | Chart and placeholder contracts on two engines. Re-budgeted to 150 s |
  | `chats` | 417 s | 420 s | 370 s | Almost at its limit. Watch it |
  | `agent-tabs` | 513 s | | 407 s at M34 F1 (+26%) | Not this flight's tests |
  | `contracts-controls` | 425 s | | 509 s (-17%) | Re-budgeted to 540 s |
  | `contracts-overlay` | 192 s | | 246 s | Re-budgeted to 240 s |

- **Full gate:** about 2420 s (40.3 min) against the 43-minute target. Headroom is down to about 3 minutes; M34 F1 was 2256 s.

## Methodology Observations
Plugin version 1.2.3.

1. **The flight skill, Phase 4 (premise audit): parser behaviour was reasoned about, not executed.**
   - What happened: DD10 (streaming fence detection) was designed from reading `markdown.js` and went through three revisions. Each Architect cycle found a counter-case only by running candidate inputs through the real parser under node.
   - What was expected: the flight skill already asks that "a DD that rests on an empirical premise should have that premise verified before it's locked". Here the premise was "the parser treats X as a fence", and it was verified by reading code, not by executing it.
   - Cost: two extra design-review cycles on one decision.
   - The cheap fix was an executable probe of the cited parser at design time.
2. **The agentic-workflow skill, Phase 2 and Phase 3: a flight Verification item with no owning leg.**
   - What happened: the flight's Verification section named a WebKitGTK probe, but no leg's acceptance criteria included it, and Phase 3's checklist (legs completed, log, docs) did not surface it.
   - It was caught only by the Flight Director's reading at landing, and cost an extra Developer spawn after the closing gate.
   - Expected: either the flight skill maps each Verification item to a leg, or agentic-workflow Phase 3 checks the Verification section.
3. **The agentic-workflow skill, Phase 2d: no shape for a quota-gated leg.**
   - What happened: the skill reviews and commits once after the last autonomous leg. DD13 needed a review and commit *before* quota-spending eval runs inside leg 4, and an operator decision after them.
   - The Flight Director improvised: a Part A / Part B split of one leg, a combined review over legs 1-4A, and three commits for the leg.
   - It worked, but the leg artifact had to carry protocol text, and leg status values got ad hoc suffixes ("landed (Part A landed; Part B pending)").
   - Expected: a documented pattern for a leg that ends in an operator gate and an outward cost.
4. **The leg skill (acceptance criteria): a "trim by measurement" criterion with no must-keep list.**
   - What happened: leg 4 AC1 told the Developer to trim the prompt as short as possible "while naming … the optional keys in one line". The Developer dropped most of the keys anyway, and the single flight review did not catch it.
   - Cost: two HAT round trips, two prompt edits, two sentinel runs and stale baselines.
   - Expected: when a criterion invites trimming text that carries a design's scope, the criterion enumerates what must survive, and the reviewer checks against it.
5. **The agentic-workflow skill, the HAT protocol: no apparatus self-check.**
   - What happened: the HAT leg's environment (seeded mock replies) was built by a Developer spawn and handed straight to the operator.
   - Two seed defects (a mid-line fence; one-chunk bodies that could not be stopped mid-JSON) each cost the operator a failed step.
   - Expected: a step where the Flight Director or a crew member confirms the seeded scenario actually produces the state each HAT step needs, before the operator starts.

## Recommendations
1. **Re-baseline the evals on the shipped prompt, with the log-scale wording fix folded in, before any other platform-prompt change lands** (sortie 12 included). CLAUDE.md currently names stale baselines as current. *Important.*
2. **Before Flight 2 builds on `chart.js`, split it** (parse, layout and scales, per-type renderers, interaction) and measure text width instead of estimating it. Flight 2 should reuse `codeBlockRenderers`, the placeholder and `setTailHold`, with no second streaming path, and keep `transcript.js` under 800 lines by extracting commit and pacing first. *Important.*
3. **In future flight designs, carry a must-mention list for any prompt text** a leg may trim, and run cited parser or library behaviour at design time rather than reasoning from source. *Important.*
4. **HAT apparatus:** the leg spec supplies the seed (fence spacing, chunk timing) and a pre-walk self-check of each step's state. Record the server PID from `ss -ltnp`. *Minor.*
5. **Attach the qwen3-4b `notes-as-told` question and the 19/20 safety cells to sortie 12** (claimed actions), where an on/off control run belongs. *Minor.*

## Action Items
- [ ] Re-baseline m35 on the shipped prompt and tighten the log-scale clause (offered as a squawk; the operator chose not to log it, so it stays a debrief recommendation, #1)
- [ ] Measure axis text width in `chart.js` (offered as a squawk; the operator chose not to log it; it goes to Flight 2 planning with the `chart.js` split, recommendation #2)
- [x] Docs: the streaming-test pacing rule, the small-model chart note, the text-width limits. Logged as [squawk 0342](../../../../squawks/0342-charts-in-chat-docs.md) (open, routine)
- [ ] HAT and behavior-test instance recipe: take the PID from `ss -ltnp` (offered as a squawk, not logged; recommendation #4)
- [ ] Flight 2 planning: split `chart.js`; reuse the streaming seams; reserve the live-visual tag; own the engine probes in a leg
- [ ] Sortie 12: add the qwen3-4b `notes-as-told` drop and the 19/20 safety cells to its scope notes
