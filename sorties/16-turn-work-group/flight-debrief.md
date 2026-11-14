# Flight Debrief: One work line per chat turn

**Date**: 2026-11-14
**Flight**: [One work line per chat turn](flight.md)
**Status**: landed (marked `completed` at this debrief, at the operator's instruction)
**Duration**: 2026-11-13 (charter, mockups, design, legs 1 to 3) - 2026-11-14 (legs 4 and 5, review, gate, HAT, landed)
**Legs Completed**: 6 of 6 (five autonomous legs and the HAT; the flight was approved as three legs plus the HAT)
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
In a web chat, a turn now renders as one collapsible work group and one reply, live and after a reload.
- A new library control, `App.ui.turnWork`, draws the group: six states with their own words, a tool-call count, the running tool's name, a plain-text preview of streaming text, and the turn's narration, thinking and tool rows inside.
- A new chat module, `areas/chat/turn-work.js`, decides what goes into it, for live frames and for replay.
- The reply is one normal bubble that lands when the turn ends.
- The code that only served the old shape is deleted: `stream-commit.js`, `visual-stream.js`, `App.ui.trace`, `App.ui.chart.placeholder` and `App.ui.message`'s streaming API.
- One operator-requested rider: the "New agent" form starts at 50 steps (the server default stays 20).

Size: 75 files, 5203 insertions, 2463 deletions, in two commits (`122158bf`, `1a458bcf`) on PR #371. `transcript.js` went from 667 lines to 437; the new chat module is 536 lines and the control 211.

### Charter Criteria

| Criterion | Result | Evidence and limits |
|---|---|---|
| A turn with tool calls shows exactly one work line and one reply bubble, live and after a reload | **Met** | Flow tests for live, reload, a join mid-turn, a paused join, a join during a resume and a second window. HAT steps 1, 2, 4 and 9 passed on a real model. |
| Expanding the work line shows every pass's narration, thinking and tool calls, in order | **Met for narration and tool calls; thinking is test-only** | HAT step 3 passed. Thinking inside the group has never been seen with a real model: the app drops reasoning from Ollama models and the operator's Claude model could not think (HAT step 8C). It rests on contract and flow tests with scripted frames and seeded history. |
| A stopped, errored or step-limited turn loses no text the model wrote | **Met** | Flow tests; HAT steps 5 and 6, and an unplanned real agent error at step 1. |
| Copy reply copies only the final reply | **Met** | Flow test; HAT step 2. |

Constraints: **browser-only held** (no Python under `the_one/` changed; one stale comment in `app.py` was left alone for that reason, squawk 0360). **Built as an `App.ui` control held** (catalogue row, contract tests in both engines, no owned class outside `js/ui/`).

### Not proven
Each of these was put to the operator before the sign-off.
- **The sign-in pause** (HAT step 7, skipped: no OAuth MCP server on the HAT instance). Automated tests only.
- **Thinking in the work group** (step 8C, above).
- **The desktop webview** (not walked, by the operator's choice).
- **The dots in Windows high-contrast mode** (they may not paint; the label still reads "Working"). Not fixed.
- Three of the seven judgement items the HAT leg listed got no answer because their case was never exercised: the dots while the socket is down, where the "Resuming…" line sits, and the second-window send.

## What Went Well
- **Mockups before design.** Eleven boards, three of them animated, let the operator choose the streaming behaviour (option C) and the no-answer behaviour (option 2) by watching them, in one message.
- **Design reviews found real defects before any code.** Two Architect cycles and two leg-2 cycles caught: a promotion that would have moved or redrawn a mounted widget; a paused turn that would have got two replies on re-join; an optimistic Stop that would have lost the reply when `done` raced the click; "Model loaded." opening a second group on a resume. None reached code.
- **One choke point.** Every path that opens a group goes through `ensureOpen`; both leg-2 reviews and the code review walked every frame sequence and found no double group.
- **Deletion with evidence.** Five dead pieces removed with a recorded grep each, and no residual caller found by three later reviewers.
- **Asking a second reviewer what the first skipped.** The first code review said plainly that it had not checked for weakened tests. The follow-up pass on exactly that found a continuous "source never visible" watch reduced to one sample; restoring it exposed the flight's most serious defect (below).
- **Falsification was routine.** Every guarding test named in a leg or a fix pass was broken on purpose and seen to fail, and the results were recorded with a yes or no.
- **The HAT changed the product.** Two things only a person on their own machine would have caught: no sign that a running group can be opened, and a spinner that sat off the text line on Windows.

## What Could Be Improved

### Process
- **The planning estimate was off by a factor of 2.5.** Chartered as two legs plus a HAT, approved as three, flown as five. Each split came from a design review judging a leg too large for one Developer pass, never from new scope. The Architect's debrief view: this was the upper bound of a sortie, and two sorties would have been cleaner (the control and group first; then the preview, the deletions and the reload rules).
- **Legs 2 and 3 were not independently green.** The split left 23 tests failing between them, by design and listed, but it made leg 2's own lane results harder to read.
- **A "must never appear" property was specified as a sample.** DD3 said raw chart and widget source never shows in the preview. The leg's tests checked one stream at one moment. The first code review confirmed the function by reading it. It leaked in six distinct ways (below), found over three review cycles and three fix passes: the largest rework of the flight.
- **HAT prerequisites were listed, not checked.** The flight said a thinking-capable model and an OAuth MCP server would be "re-verified at the start of the HAT leg". Neither was available, and two steps went unwalked. A two-minute check at design would have shown that the app drops Ollama reasoning (sortie 13's gap) and that the operator's Claude model cannot think.
- **The Flight Director substituted a component for a mockup-approved visual.** The mockup drew three CSS dots; DD1 used the existing braille spinner instead, without checking how a braille glyph renders. The app's font has no braille, so every browser draws it from a different fallback font. That cost two HAT fix passes; the first one's geometry test (box centres) passed while the glyph was still visibly off.
- **The Flight Director told the operator the seeded Ollama agent would show thinking.** It cannot. Corrected during the HAT.
- **Crew ignored a written rule.** The leg 1 Developer left seven backgrounded `sleep` timers that re-woke it for ten minutes; the leg 4 Developer ran a `pgrep` wait loop and spawned a subagent by mistake. Both rules were in the prompt.
- **The Flight Director ran two unit tiers at once at the debrief** (a background run not yet finished, then a foreground run). Both passed; the wall times are inflated and are marked as such below.

### Technical
- **The preview's source hiding is a hand-written scanner** (`previewFor`, `unwrapLine` in `areas/chat/turn-work.js`) that imitates `markdown.js`'s fence, quote and list rules. It is held equal to the renderer by a differential test, not by sharing code. If the renderer's block grammar changes, the scanner can leak until a corpus entry covers the new case. Both interviewees flag it as the flight's main debt. The Architect's preferred fix: show no pending text at all once a pass contains any code fence (about ten lines, no coupling; ordinary code blocks would show the phrase too). The Developer's: move the scanner into its own pure module so it can be tested in node and kept beside the parser.
- **The live path and replay implement the same rules twice** (`renderTurn` against the frame handlers; the "latest narration waits" state is built by hand in both). They are held equal by mirrored tests; unfinished turns are exempt.
- **Reopening a trailing turn re-renders the whole log.** Correct, but it redraws every chart and widget, drops focus and collapses opened groups. It only happens on the first live frame after a join.
- **Reload loses why a turn ended.** A stopped, errored or step-limited turn looks finished after a reload, and an abandoned sign-in shows its last text as a reply. Accepted by the operator; it is a limit of what the server stores.
- **`App.ui.thinking.dots` has no caller outside `thinking.js`** now that the work line draws its own dots. A candidate for removal as a public export.
- **A test helper infers too much.** `_chats.turn_dots_stopped` reads "stopped" from the animation being off, which is also true under reduced motion. The flow test that uses it asserts `data-stopped` directly, so nothing is wrong today.
- **The chat module pokes the control's root in three places** (`h.el.hidden`, `h.el.parentNode`). A `remove()` and a `setHidden()` on the handle would close the boundary.

### Documentation
- **One stale sentence shipped.** `the_one/agents.md`, "Chat transcript on the library", the `clearLog()` bullet, ends "(the work group has its own dots, `App.ui.thinking.dots()`)" and says "no 120 ms dot interval survives one". Since HAT fix 2 the work group draws its dots in CSS and has no interval. Found by the debrief Developer. **Fixed on the branch at the debrief**, at the operator's request, by a Developer (a one-line prose edit; the Flight Director checked the new wording against `transcript.js::clearLog` and `dropModelLoading`). No other doc made the same claim.
- Leg 5's spec called `docs/chart-format.md:13` a false positive (it was not) and missed one behavior spec (`directory-lookup-send`); the Developer caught both by grep.
- The verification harnesses that proved the preview (the Reviewer's node fuzz, and the Flight Director's 13,442-text structured sweep) live in the session's scratch directory and are not in the repo.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Three legs became five | Design reviews judged legs 2 and 4 too large for one pass | No. Estimate better: count the test files that pin the old shape before fixing the leg list |
| The lanes were red between legs 2 and 3 | The split put the remaining test rewrites in their own leg; the registry guard forced part of the sweep into leg 2 | No. Prefer a split that leaves each leg green |
| DD1's `App.ui.thinking.dots()` replaced by CSS-drawn dots; the chevron shown in every state | HAT: a font glyph cannot be aligned across browsers; a running group gave no sign it could be opened | Yes: status indicators are drawn in CSS, never as font glyphs |
| `previewFor` rewritten three times | It leaked source for a half-typed opener, a closed block still pending, CRLF, a block in a quote or list, a fence-like body line, and a list marker past a 24-character window | Yes: a "must never appear" property gets an exhaustive or differential test in the leg spec |
| A fourth verification by the Flight Director instead of a fourth review cycle | Three cycles were used; the Reviewer had confirmed, and the last leak had an exact reproducer | Case by case. It was told to the operator at the time |
| A rider outside the charter (the new-agent form's 50 steps) | Operator request mid-flight | No. Recorded as a rider; a second one would have been a squawk or its own sortie |
| The debrief ran a fresh gate | The flight's gate ran on a loaded host and before the HAT commit (crew file rule) | Already the rule |
| HAT steps 7 and 8C not walked | No OAuth MCP server; no model that thinks | No. Check HAT prerequisites at design |

## Key Learnings
- **"Confirmed by reading" is weak evidence for a property that must never fail.** The first reviewer read `previewFor` and confirmed it. Six leaks later, what worked was: a continuous watch in the flow tests, a differential test against the real renderer at every prefix, and a structured sweep whose list cases indent their continuation lines correctly. The Reviewer's own fuzz reported no leaks while a 26-digit list marker sat in its prefix list, because its list cases never put a body inside the block.
- **A test can pass without being able to see the fault.** HAT fix 1's alignment test compared box centres, which a tall glyph's box satisfies while its ink is off the line. Boxes can be tested by their boxes; glyphs cannot.
- **Reduced-motion captures hide the animated state.** The capture tool and the Developer's renders ran with reduced motion, so nobody in the crew saw the moving spinner before the operator did.
- **Do not replace an approved visual with a nearby component without rendering it.** The mockup is the contract.
- **One choke point for a lifecycle object** (`ensureOpen`) made "never two groups" checkable by walking sequences against one function.
- **Ask the reviewer what it did not check, then check that.** The first review's honest "not checked" list was the most valuable part of its report.
- **Flakes need a squawk the first time.** The `agents` test race was noted in the logs of sorties 08 and 09 and cost a re-run in each, and again here, before it got an id (0359).

## Test Metrics

The flight's own closing gate ran on a loaded host and before the HAT commit, so the crew file's "run fresh" rule applied. The Flight Director ran both tiers itself at the debrief, on `1a458bcf`. The per-leg and per-fix-pass runs during the flight are in the flight log; all of those were read on a busy host.

**Unit tier** (`THE_ONE_TEST_NETNS=1 make test-unit`, at the debrief):
- **10137 passed, 15 skipped** (the expected skip count under netns), no failure. 294 s and 296 s.
- Those two times are inflated: the Flight Director started a second run while the first was still going, so they overlapped. The flight's closing-gate run, alone, took 271 s (load 1.70).
- Prior readings: sortie 15's debrief 10137 passed; Mission 35 Flight 3 10118 passed in 281 s; sortie 14 9372 in 259 s; Mission 34 Flight 1 8577 in 229 s.
- The count did not move across this flight overall (10143 after leg 1's new lane case, 10137 after leg 4 removed parametrised lane cases). **The tier now sits close to its standing 300 s target** on this host; the next flight that adds unit tests should expect to cross it.

**Browser tier** (`--parallel 3`, `THE_ONE_REQUIRE_WEBKIT=1`, `THE_ONE_TEST_NETNS=1`, at the debrief):
- `PARALLEL_RESULT rc=1 total=2180s lanes=20 failed=contracts-widget-lifecycle`. **19 of 20 lanes green; no lane over budget.**
- Start load 0.95 on the 1-minute average (1.97 on the 5-minute, straight after the two unit runs). As at sortie 15's debrief, that is borderline, so **no budget is re-based from this run**.
- **The one failure**: `test_ui_widget_lifecycle_contract.py::test_nine_loaded_unloads_the_oldest_visible_paused_auto[webkit]` (`assert 0 == 1` on the frame's load count). It passed 3 of 3 alone in both engines. The test reads the load count the moment the card's state says `running`, which is before the load is counted. The flight changed nothing in that area. Logged as **squawk 0362**. The same lane failed at Mission 35 Flight 2's debrief gate on a sibling race (squawk 0351).
- The `agents` lane, which failed on its own test race in the flight's closing gate (squawk 0359), passed here: 186 passed.

| Lane | This run (s) | Budget (s) | Last quiet reading (s) | Tests |
|---|---|---|---|---|
| `routing` | 597 | 720 | 600 | 186 |
| `agents` | 572 | 630 | 576 | 186 |
| `agent-tabs` | 517 | 600 | 513 | 202 |
| `chats-transcript` | 417 | 540 | 430 | 152 |
| `contracts-controls` | 405 | 540 | 425 | 1230, 4 skipped |
| `library` | 400 | 480 | 420 | 122 |
| `chats` | 384 | 420 | 417 | 176 |
| `shared` | 357 | 420 | 372 | 364 |
| `providers` | 331 | 420 | 360 | 139 |
| `knowledge` | 313 | 420 | 334 | 65 |
| `mcp-connection` | 289 | 390 | 306 | 94 |
| `settings` | 278 | 360 | 300 | 108 |
| `agent-routines` | 275 | 300 | 269 | 86 |
| `mcp` | 267 | 330 | 292 | 88 |
| `settings-tools` | 253 | 330 | 280 | 172 |
| `contracts-widget` | 228 | 300 | 186 (solo, provisional) | 156, 2 skipped |
| `chats-widgets` | 165 | 240 | (provisional) | 32 |
| `contracts-overlay` | 158 | 240 | 192 | 548, 1 skipped |
| `contracts-widget-lifecycle` | 102 | 300 | 48 (solo, provisional) | 112 passed, 1 failed |
| `contracts-chat` | 93 | 150 | 100 | 330 |

"Last quiet reading" is the measured column of CLAUDE.md's budget table (the Mission 35 Flight 1 closing gate, total 2163 s). This run's total is 2180 s, within 1% of it; the flight's loaded closing gate was 2031 s.

**How the flight moved the lanes** (test counts, with the cause):
- `contracts-chat`: 400 → 322 (the trace and chart-placeholder contract files and ten `App.ui.message` streaming cases deleted) → 330 (the HAT fixes' new contract cases). Its time is flat (100 s → 93 s).
- `chats`: 184 → 176 (the deleted visual-stream test file).
- `chats-transcript`: 136 → 152 (26 new turn-work flow tests, less the removed placeholder and per-tick parsing tests). Its time did not grow (430 s → 417 s): the new tests drive scripted frames, and the deleted streaming tests were slow.
- `chats-widgets`: 25 → 32.
- `agents`: 185 → 186 (the rider's test).

**Lanes to watch**: `agent-routines` (275 s of 300 s, 92%) and `chats` (384 s of 420 s, 91%) have the least headroom. Neither is from this flight's changes, and neither is re-budgeted from a borderline run.

**After the gate: the version bump.** At the operator's request the PR also carries a patch bump to 0.16.3 (`the_one/__init__.py`, and `docs/releases/v0.16.3.md` with text the operator approved), made by a Developer after the gate so that the gate measured the code as walked. The unit tier on the bumped tree: **10138 passed, 15 skipped**, 275 s (one more test than before, from the new release-notes file); `ruff` clean; `scripts/release_check.py`'s dry-run path accepts the version. The browser lanes were not re-run for a version string. The release itself is cut by the operator after the merge.

**Flakes seen during the flight** (each passed alone, none caused by the flight): the `agents` model-loading race (twice; squawk 0359), `test_run_tests_lanes.py::test_parallel_exit_codes` (one subprocess timeout under load at fix pass 2; not seen again in four later unit runs), and the widget-lifecycle race above (squawk 0362).

## Methodology Observations
Plugin version for all of these: mission-control 1.2.3.

1. **Sortie skill, qualification and the soft leg limit.** The qualification gate passed the work on all four criteria with a two-leg estimate, and the skill's step 5 re-check ("the legs outgrew the soft limit: say so and ask") fired once at three legs; the operator kept it a sortie. The flight then split twice more during execution, where the sortie skill no longer applies and the agentic-workflow skill has no equivalent re-check. Expected: some prompt, when legs are split mid-flight, to ask again whether this is still a sortie. Cost: none measurable; the operator was told each time. The record is that a sortie ran to five autonomous legs, 75 files and three code review cycles.
2. **Agentic-workflow skill, Phase 2d, the review loop limit.** "Code review loops > 3 times: escalate to human." On cycle 3 the Reviewer signalled confirmed and also named a leak that met the flight's own blocking definition. The skill does not say what a confirmed-with-a-blocking-item verdict is. The Flight Director fixed it and verified it directly rather than run a fourth cycle, and told the operator. Expected: guidance for a mixed verdict. Cost: a judgement call under ambiguity.
3. **Agentic-workflow skill, Phase 2d, one review for the whole flight.** The single flight-end review received a 73-file diff. The first Reviewer covered the product code well and did not get to two of the five things the brief asked for; it said so. Expected: either a brief that splits the review by concern, or a rule that a review's "not checked" list is always followed up. Cost: one extra review pass, which is also what found the flight's worst defect.
4. **Flight skill, pre-flight rigor, HAT prerequisites.** "Prerequisites MUST be verified, not assumed", and for behavior tests "record as a prerequisite, verified at planning, the apparatus-audited environment". The HAT leg's prerequisites (a thinking model, an OAuth server) were written as unchecked boxes to verify at the HAT, and the Architect's review item 8 (external-session prerequisites need a per-leg re-verify) was satisfied by exactly that wording. Expected: for a HAT step that needs something only the operator has, ask at design whether they have it. Cost: two HAT steps unwalked and one charter criterion met only by tests.
5. **Crew file, "Commit (once per flight)": the Developer commits.** A Developer agent was spawned to make the first commit and used about 100,000 tokens for three tool calls. The Flight Director made the HAT commit directly when the operator asked for it. Expected: unclear whether a mechanical commit needs a crew agent. Cost: tokens only.
6. **Crew prompts, process hygiene.** The "no backgrounded `sleep` timers, no `pgrep` loops" paragraph was in every Developer prompt and was broken by two of six Developers. Expected: the rule to hold. Cost: ten minutes of repeated hand-backs, and one agent stopped by the Flight Director.
7. **Flight-debrief skill, "the Developer runs the full test suite once".** The project's crew file narrows this to the Flight Director deciding the source of the metrics; here the Flight Director ran the gate itself so the interviews could run first and the host could be quiet. The skill's wording and the crew file's still point at the Developer. Cost: none.

## Recommendations
1. **Close the preview scanner's drift risk before the next change to `markdown.js`.** Either take the Architect's fallback (no pending text is shown once a pass contains any code fence), or move the scanner into its own module and add a guard that fails when the renderer's block grammar changes without a new corpus entry. Commit the structured sweep as a developer script either way. *Important.*
2. **Put "exhaustive or differential test" in the leg spec for any property worded "never".** And treat a reviewer's "confirmed by reading" on such a property as unverified. *Important.*
3. **Check HAT prerequisites at flight design, with the operator.** For each HAT step that needs something only the operator has (a model capability, an account, a server), ask then, and mark a step that cannot be walked as a known coverage gap in the flight artifact. *Important.*
4. **Walk the two unproven paths when they become possible.** The sign-in pause needs an OAuth MCP server on a dev instance. Thinking in the group needs sortie 13 (Ollama reasoning) or squawk 0361's follow-up (thinking per model). Until then, criterion 2 is met by tests alone for thinking. *Important.*
5. **Plan the second-window send as a small sortie or a leg of the next chat flight.** A window that receives another window's `user` frame should hold its own sends until `done`. Pre-existing; it fails the squawk gate (it changes in-flight state handling). *Minor.*
6. **Draw status indicators in CSS and assert their geometry on boxes.** Add the rule to the control library's conventions. *Minor.*
7. **Size a UI-reshaping sortie by counting what pins the old shape.** Seventeen browser test files, four behavior specs and the capture tool pinned the old transcript; that number was known at design and did not move the leg estimate. *Minor.*

## Action Items
- [x] Fix the stale sentence in `the_one/agents.md` ("Chat transcript on the library", the `clearLog()` bullet): done at the debrief, on the branch.
- [ ] Squawk 0359 (the `agents` lane test race): fix at the next turnaround.
- [ ] Squawk 0360 (the stale "Tool activity" comment in `app.py`): fix at the next turnaround after merge.
- [ ] Squawk 0362 (a widget-lifecycle contract test race, found at the debrief gate): fix with 0359.
- [ ] Squawk 0361 (Extended thinking is a provider setting): charter a sortie.
- [ ] Decide recommendation 1 (the preview scanner) and schedule it.
- [ ] Commit the preview sweep as a developer script (it is in the session scratch directory only).
- [ ] Walk HAT steps 7 and 8C when an OAuth MCP server and a thinking model are available (recommendation 4).
- [ ] Remove the public `App.ui.thinking.dots` export if no caller appears, and make `turn_dots_stopped` read `data-stopped`.
- [ ] A `forced-colors` rule for the work line's dots, if the operator wants it.
