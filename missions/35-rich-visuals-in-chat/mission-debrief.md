# Mission Debrief: Rich Visuals in Chat

**Date**: 2026-11-13
**Mission**: [Rich Visuals in Chat](mission.md)
**Status**: completed
**Duration**: 2026-11-08 - 2026-11-13
**Flights Completed**: 3 of 3 planned (the optional Flight 4, Alignment, was dropped by operator decision on 2026-11-13; its items moved to the mission's Follow-ups)
**Plugin version**: mission-control 1.2.3 (1.2.4 available, not installed)

## Outcome Assessment

### Success Criteria Results
| Criterion | Status | Notes |
|-----------|--------|-------|
| Charts appear in the app | met | Flight 1: all six chart types are drawn in place and follow a theme change without a reload. Each has a "Show data" table, an aria summary and a keyboard live reading. |
| Live visuals run in the app, walled off | met | Flight 2: an opaque-origin `srcdoc` frame, the page-level `frame-src 'none'` header, and a size-only channel keyed on `event.source`. The escape battery was silent in Chromium, WebKit, WebKitGTK and WebView2, and `widget-escape` passed 9 of 9. SECURITY-MODEL.md "Live visuals" records the residuals. |
| A visual appears when it is ready | met | Flights 1 and 2: the "Rendering" placeholder with the shared dots, parser-confirmed commit boundaries, error notices with the source under "Technical details", and Copy reply copying the original. Covered by flow tests and HAT steps. |
| Long chats stay responsive | met, with documented residuals | Flight 2, as amended at its planning: run in view and pause off screen, 3 running and 8 loaded, and a three-layer hang guard. Documented residuals: a WebKit freeze once per busy-looping widget, "Start anyway" hanging on some Chromium hosts, a first-scroll shift. "Pause blocks input" is a follow-up. |
| Operators choose per agent | met | Flight 1: the Rich visuals switch (schema v52), on for new and existing agents; a change takes effect at the next join. Flight 2 widened the prompt section to widgets. |
| The prompt cost is measured and accepted | met, with caveats | The visuals section grew from 209 to 425 tokens (the all-on prompt from 525 to 741). Same-prompt `m35f2b-*` baselines were recorded, and the operator accepted them at gates 3 to 3e. Caveats: lfm3 `no-secrets` and qwen3-4b `planted-flagged` at 19/20 were accepted as noise or an eval gap. Small local models almost never write widgets, so the feature in practice serves Haiku-class models. |
| Charts reach chat platforms as images | met, against fakes | Flight 3. The criterion was amended on 2026-11-11: we prove what the app sends, not what the platforms show. `charts-reach-platforms` failed 4 of 6 on run 1 and passed 6 of 6 on run 2. **What Discord and Telegram actually render is unproven**, a recorded residual. |
| Chart images work on every install | met | Flight 3: Pillow is a base dependency; the SHA-pinned Geist TTFs are in every freeze spec. The `chart images` doctor gate read width 20463 on the Linux AppImage and `.deb` (Debian 13, Ubuntu 26.04), Windows and macOS, even though the `.deb` builds load the host's own FreeType. |
| Visuals work in the desktop app | partly met, accepted | Flight 2: WebKitGTK and WebView2 were checked in both themes, with the native-bridge removal. WKWebView was only probed by the hosted run: no chart screenshot, and no widget seen animating (Reduce motion was on). The operator accepted this. The macOS probe and the WebView2 canvas check are follow-ups. |

### Overall Outcome
**Achieved.** An agent can now answer with a picture. Charts and live widgets render in the chat, in both themes, as they stream. Live widgets run behind a boundary that has been tested against real escape attempts, and charts reach Discord and Telegram as images, with every failure falling back to the text the agent wrote. The outcome was still the right goal at the end.

Two mid-mission amendments narrowed it on purpose, both operator decisions:
- **Pause, not stop.** Pause off screen replaced stop-and-restart.
- **Fakes, not live bots.** Platform delivery is proved against local fakes instead of live bots ("we can't really control what they see, we can only control what we send").

There are two honest gaps:
- **Platform rendering:** what Discord and Telegram show a reader is unproven.
- **macOS:** the desktop check there was a probe, not a walk.

The operator closed the mission without the optional alignment flight.

## Flight Summary
| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 1. Charts in chat | completed | A language-neutral chart format (`docs/chart-format.md`) shared by two implementations through one corpus. The SVG chart control, the streaming "Rendering" state, the per-agent Rich visuals switch, and the platform prompt section with its eval comparison. 5 legs including a HAT. |
| 2. Live visuals | completed | The walled-off widget frame (risk seam first, with a go/no-go after leg 1), the card, the lifecycle manager and hang guard, widgets in chat, native-bridge removal in the desktop shell, the `widget-escape` behavior test, the `chart.js` split, and new eval baselines. 9 of 10 legs (leg 3 aborted and split). The HAT took four fix rounds. |
| 3. Visuals on chat platforms | completed (PR #366 open) | A server chart renderer with a font-file measurement contract proved on three platforms, one shared conversion step for both send paths, Discord multipart and Telegram `sendPhoto` with 4xx-only resend, fake platforms and a loopback-only dev seam, and `charts-reach-platforms` 6 of 6. 6 legs, no HAT. |

## What Went Well
- **The risk seam was proved first.** Flight 2's first leg proved the frame boundary in all three desktop engines and ended in an explicit go/no-go before anything was built on it. The escape battery, positive controls for every "unreachable" claim, and a witnessed behavior test give the mission's riskiest promise real evidence.
- **Shared corpora between implementations.** These held four contracts across two or three implementations, and each found real divergences:
  - chart validation and number format (Python and the browser);
  - y-ticks (Python and both browser engines);
  - block finding (`visuals/blocks.py` against the frozen eval scorer).
- **Design reviews before code, every time.** Two Architect cycles per flight plus per-leg reviews found high-severity issues in every flight before implementation. Examples: the parser counter-cases in Flight 1, BASIC kerning and a double-post risk in Flight 3.
- **Cheap cross-platform contracts.** The `chart images` doctor gate pins one integer derived from a SHA-pinned file and turned "will text render the same everywhere?" into a pass/fail fact on three platforms in one run.
- **The operator's time was spent on decisions, not drudgery.** The operator called coordination "clear throughout" and Flight 3's autonomy "about right". Operator time went to the go/no-go, the sample sheet, the eval gates, outward pushes and dispatches, and failure triage.

## What Could Be Improved
- **The prompt and eval cost was the mission's biggest surprise (operator).** This part grew far beyond its planned size:
  - Flight 1's prompt-trim criterion lost the optional keys and cost two HAT round trips plus stale baselines.
  - Flight 2's prompt leg grew into a ten-part mini-flight, at about two hours per n=20 round, with five operator gates.
  - Three generations of baselines were recorded (`m35`, `m35f2`, `m35f2b`).
  
  A prompt change is a measured, quota-spending loop with gates, and it was planned as if it were one leg. Future missions that touch platform prompt text should give it its own flight or leg family, with a round budget, a stop rule, a must-keep list and each measured text committed before its runs.
- **Documentation drifted, and the method did not catch it (operator).** The README fell behind across many flights; squawk 0349 lists 12 inaccuracies. Flight 2 also left CLAUDE.md describing pre-amendment behaviour until the Flight Director's check. The landing check asks only about new commands, endpoints and configuration.
- **Apparatus was not self-checked before the human or the witnessed test used it.** The same thing happened in every flight:
  - Flight 1's HAT seed defects;
  - Flight 2's headless-only legs, whose HAT then found three real-browser defects;
  - Flight 3's fake, which had a reset bug and had skipped review as low-risk.
- **The test suite is at its limits.** The unit tier is 281 s against a 300 s target (+13% in one flight). The full local gate is 42.5 minutes against 43, and Flight 2's closing gate was skipped, leaving the browser tier a flight stale. Lane budgets (`contracts-chat`, `contracts-overlay`, the provisional widget lanes) need a quiet-host reading.
- **Crew rules in prompts did not hold.** Background `sleep` waiters, killing by port and `sed -i` on freeze specs each recurred despite explicit prompt rules.

## Lessons Learned
- **Technical:**
  - A frame boundary needs probes in every target engine before design locks. Insertion order (insert sandboxed, read width, arm load counting, then assign `srcdoc`) only showed under real Chromium site isolation.
  - "Safe to resend" must be tied to an explicit platform answer: a 4xx means nothing posted, anything else may have posted.
  - Outbound transport code needs log and exception-chain hygiene from the start: the status and never the body, `from None`, resends outside `except`, one warning per event.
  - Three chart implementations are held equal by corpora for parsing and ticks, but layout and paint can diverge. That is accepted (no kerning on the server), and worth stating.
- **Process:**
  - A leg that waits on an operator gate or a pushed build needs its own shape. All three flights improvised one: Part A/B legs, checkpoint commits, gated sub-parts.
  - A behavior test with two independent agents is worth its cost: in Flight 3 it found two defects that 500-plus unit tests missed.
- **Domain:**
  - Small local models effectively cannot write widgets (lfm3 managed 1-3 of 20), so live widgets are a Haiku-class feature in practice.
  - On chat platforms the app controls only what it sends; how a platform shows it is the platform's.

## Methodology Feedback
Plugin version 1.2.3 throughout. These restate observations from the flight debriefs; the source flights are named so a later sweep counts each occurrence once.

1. **agentic-workflow, Phase 2 to 2d: operator-gated or outward-dependent legs have no shape.** *Methodology observation.* **Recurrence: 3 of 3 flights.**
   - **What the method does:** design, implement and land, then one review and commit after the last autonomous leg.
   - **What was needed:**
     - Flight 1: a review and commit before quota-spending eval runs, then an operator decision (Flight 1 debrief, observation 3).
     - Flight 2: legs 7 and 8 with ten sub-parts and five gates, and autonomous, operator and outward platform parts (Flight 2, observation 2).
     - Flight 3: an early review, commit and push, because Leg 2's apparatus builds a pushed ref (Flight 3, observation 1).
   - **Cost:** the Flight Director improvised structure, commit points and review placement each time; leg statuses got ad hoc suffixes; extra review cycles.
2. **agentic-workflow, Phase 3 step 3: the documentation check is narrow.** *Methodology observation.* **Recurrence: 2 of 3 flights**, plus the operator's report of README drift since about Mission 25.
   - **What it checks:** whether new commands, endpoints, configuration or APIs reach CLAUDE.md and the README.
   - **What was expected:** every doc a flight's user-visible changes touch (README, `docs/*`, install guides, CLAUDE.md), and the old wording after a DD amendment.
   - **Sources:** Flight 2, observation 3 (CLAUDE.md stale after a HAT amendment); Flight 3, observation 2 (operator-raised README drift).
   - **Cost:** a stale README over many flights (squawk 0349), and a late CLAUDE.md fix in Flight 2.
3. **agentic-workflow, Phase 2a, and the HAT and behavior-test protocols: no apparatus self-check before a human or witnessed gate.** *Methodology observation.* **Recurrence: 3 of 3 flights** (related forms).
   - Flight 1, observation 5: HAT seed defects cost the operator two failed steps.
   - Flight 2, observation 1: no headed real-browser pass before the HAT; four fix rounds and about four extra operator hours.
   - Flight 3, observation 4: a stateful fake tiered low-risk skipped review; its reset bug forced a full behavior-test re-run.
   - **Expected:** a crew-run check that the apparatus produces each step's state, with test doubles that hold state tiered high or given a "what survives reset" line.
4. **flight, Phase 4/5b, and agentic-workflow, Phase 2a: design reviews verify structure, not executed behaviour or failure paths.** *Methodology observation.* **Recurrence: 2 of 3 flights.**
   - Flight 1, observation 1: parser behaviour was reasoned about, not executed; two extra design cycles.
   - Flight 3, observation 3: the log-duplicate and chained-body leaks were missed by every review and found by the behavior test and the flight-end review; one failed run, a fix pass and a re-run.
5. **flight / agentic-workflow, Phase 3: a flight Verification item with no owning leg.** *Methodology observation.* **Recurrence: 1 of 3** (Flight 1, observation 2; an extra Developer spawn after the gate).
6. **leg, acceptance criteria: a trim-by-measurement criterion with no must-keep list.** *Methodology observation.* **Recurrence: 1 of 3** (Flight 1, observation 4; two HAT round trips and stale baselines). It feeds the prompt-cost lesson above.
7. **squawk, branch step: no mid-flight case.** *Methodology observation.* **Recurrence: 1 of 3** (Flight 2, observation 4; a squawk folded into the flight's PR).
8. **Test-metrics rule assumes a flight gate exists.** *Local fix* (this project's `flight-debrief.md` crew file). Flight 2, observation 5.
9. **Two Developers in one tree, behavior-test agents saying they "cannot be resumed", crew prompt rules not holding.** *Local lessons* (no methodology cost, or project-specific). Flight 2, observation 6; Flight 3, observations 5 and 6.

## Action Items
- [ ] **Docs pass at every flight landing (operator request; local fix in `.flightops` crew files).**
  - Add a "Docs pass" step to the landing checklist and the Reviewer prompt: list the user-visible changes, check the README, `docs/*`, the install guides and CLAUDE.md for each, and record "Docs checked: …" in the flight log. The debrief names which docs were checked.
  - Add cheap unit guards for testable doc facts, following the pattern of `tests/test_settings_pages_static.py`:
    - the README command table matches `the_one/main.py`;
    - no README mention of a Settings page that `App.settingsPages` lacks;
    - the version example matches `__version__`;
    - linked `docs/*` paths exist.
- [ ] **Squawks open from this mission:**
  - [0349](../../squawks/0349-readme-out-of-date.md) README rewrite;
  - [0350](../../squawks/0350-httpx-log-prints-telegram-token.md) httpx log prints the Telegram token;
  - [0351](../../squawks/0351-widget-heartbeat-loss-flake.md) heartbeat flake;
  - from Flight 2, still open: [0345](../../squawks/0345-eval-untrusted-note-positional-args.md), [0346](../../squawks/0346-evals-fingerprint-test-order.md), [0347](../../squawks/0347-windows-test-copy-dev-mode-relaunch.md), [0348](../../squawks/0348-isolated-chromium-test-silent-skip.md).
- [ ] **Test budget decision before the next mission.** Either raise the 43-minute full-gate target to the measured value plus headroom, or rebalance: split `contracts-chat`/`contracts-widget`, share one fake server per module, profile the slowest unit directories. Re-budget `contracts-chat`, `contracts-overlay` and the provisional widget lanes from a quiet-host `--parallel 3` run, and record the result in CLAUDE.md and `scripts/run-tests.sh`.
- [ ] **Design decision for the next mission: Telegram delivery and liveness.** Deliver off the poll task, or extend liveness during a delivery.
- [ ] **Refactors:**
  - split `chart_image.py` (measure, layout, draw);
  - split `transcript.js` (carried from Flight 2);
  - move the widget prelude to a node-tested source file;
  - define a typed connector capability Protocol (or fold `send_visual_fallback` into `send_visual`) before a fourth optional method appears.
- [ ] **Record the mission's patterns in `the_one/agents.md`:**
  - a spec document plus a shared corpus;
  - armed-`srcdoc` insertion order;
  - the pure `reconcile` lifecycle;
  - a positive control for every "unreachable" claim;
  - a one-integer doctor gate from a pinned file;
  - the outbound transport rules;
  - fake state that survives reset.
- [ ] **Decide nested visual blocks on purpose** (a visual inside a quote or list stays code everywhere) and state it in `docs/chart-format.md` and `docs/widget-format.md`.
- [ ] **Optional live checks:**
  - one manual chart reply to a real Discord and a real Telegram test channel;
  - the macOS probe that scrolls a chart into view and reads `reduceMotion`;
  - the WebView2 canvas sized at start.
- [ ] **Promote the HAT's real model widgets into `tests/fixtures/widgets/`**, with a paint, no-scrollbar and non-zero-size corpus test (Flight 2, recommendation 3).
- [x] **A full quiet-host gate before PR #366 merges:** Flight 3's debrief gate on `14fc068e` covers it.
  - Unit: 10118 passed.
  - Browser: `rc=1`, on one flake, now squawk 0351.
  - Later commits are artifacts only.
- [ ] **The other session's notes-layer change** needs its own eval against `m35f2b-platform` before it lands.
