# Flight Debrief: Visuals on Chat Platforms

**Date**: 2026-11-13
**Flight**: [Visuals on Chat Platforms](flight.md)
**Status**: landed (marked `completed` at this debrief)
**Duration**: 2026-11-11 (planning) - 2026-11-13 (landed, PR #366)
**Legs Completed**: 6 of 6
**Plugin version**: mission-control 1.2.3 (1.2.4 available, not installed)

## Outcome Assessment

### Objectives Achieved
A reply that an agent sends to Discord or Telegram now carries its charts as server-drawn PNG images. This covers the automatic reply and the agent's own `send_to_platform_channel`.
- **The text:** it keeps its order. Each chart becomes `📊 Chart: {title} (below)` and each widget a note pointing to the app.
- **The images:** they follow, captioned with the title.
- **Failures:** any chart that cannot be drawn or uploaded goes out as its code block. A text resend happens only after a 4xx, so nothing is double-posted.
- **Unchanged:** plain replies go out byte-for-byte as before, and the stored chat is never rewritten.

The server renderer uses Pillow, now a base dependency, with SHA-pinned Geist TTFs, `Layout.BASIC` and per-character design-unit measurement. It follows the same format and the same y-tick corpus as the browser. A thirteenth doctor gate, `chart images`, pins the reference text width.

Both platforms are proved end to end against local fakes: `scripts/fake_platforms.py` and a dev-only, loopback-IP-only `THE_ONE_FAKE_PLATFORMS_URL` seam.

**Evidence:**
- `charts-reach-platforms`: run 1 failed (4 of 6). Run 2 passed 6 of 6 after a fix pass (`tests/behavior/charts-reach-platforms/runs/2026-11-12-23-52-13.md`).
- The doctor gate passed with width **20463 du** in all three packaged builds: Linux AppImage and `.deb` on Debian 13 and Ubuntu 26.04, Windows and macOS (runs `43320295681`, `43320302843`, `43320307092`).
- The operator approved the Leg 1 sample sheet.
- The flight-end review (Sonnet) and its re-review confirmed the changes.

### Mission Criteria Advanced
- **Charts reach chat platforms as images**: met, against fakes. The criterion was amended at planning (operator: "we can't really control what they see, we can only control what we send"). The fakes prove the request shapes the app sends, not how Discord or Telegram render them. That residual is in SECURITY-MODEL.md and the connectors README; the mission debrief should restate it.
- **Chart images work on every install**: met. Pillow is a base dependency, the font is bundled in every freeze spec, and the doctor gate passed in all three packaged builds.

## What Went Well
- **DD4's font-file measurement proved itself on real builds.** The `.deb` builds load the host's FreeType (2.13.3 on Debian 13, 2.14.2 on Ubuntu 26.04), the AppImage, Windows and macOS load the bundled 2.14.3, and the local doctor loads 2.13.2. The reference width was 20463 everywhere. The Leg 1 design review caught the one hole beforehand: BASIC still applies a legacy `kern` table, so layout now sums per-character advances and draws per character.
- **Every leg got a design review before code.** Five legs were tiered high and reviewed; Leg 5 was tiered low. Each review found real problems, and every finding was applied in one cycle:
  - Leg 1: kerning, the legend wrap, the sparkline geometry, and gate lists the spec had missed.
  - Leg 3: an off-by-one at end of text, and fakes returning `None` from `send`.
  - Leg 4: the purpose-built transport, the 429 give-up rule, and enforcing the budget with `wait_for`.
  - Leg 6: no agent cache, fixed connector ids, and logging userinfo.
- **Leg design caught a double-post risk.** `TelegramClient.send` retries as plain text on any `TelegramApiError`. Mapping transport errors into that class would have re-posted replies that may already have gone out. The sibling transport classes (AC8) prevent it.
- **The witnessed behavior test earned its cost.** Run 1 found two things no unit test caught: a duplicate fallback warning, and a fake whose `reset` restarted Telegram `update_id`s.
- **Shared-corpus parity guards held:**
  - `blocks.py` against the frozen `evals/checks.py`, over 31 replies and 2 tags (falsification found a corpus gap, an indented closer, and fixed it);
  - the tick corpus, Python against the browser in both engines;
  - `number-format.json`.
- **Falsification was routine.** About 25 new tests were shown to fail without their fix, by editing the fix out and back in.
- **Operator time was small** ("About right"; "nothing notable" as friction). The check-ins were:
  - the font copy;
  - the sample sheet;
  - the push and dispatches;
  - the behavior-test decision;
  - the PR.

## What Could Be Improved

### Process
- **Documentation drifts between flights (operator, 2026-11-13).** The README had not tracked features for many flights. It still says providers live in Settings, omits Rich visuals, Secrets and the macOS Dock mode, half-describes `search_tools` after sortie 11, and has a build record frozen at "25+ missions".
  - The flight-end documentation check (agentic-workflow Phase 3) asks only whether new commands, endpoints, configuration or APIs reached CLAUDE.md and the README. A feature that changes what the app *is* passes that check while leaving the README and `docs/*` wrong.
  - **The operator wants a mechanism that always checks the docs as part of the work, not only the README.** See Recommendation 1 and Methodology Observation 2.
- **Design reviews were weak on failure-path observability.** Two Architect cycles and five leg reviews did not flag:
  - that `VisualUploadError` carried the platform response body, which exception chaining could print into a traceback;
  - that a fallback would log twice, once in the plugin and once in the helper.
  
  The behavior test and the flight-end review found them. For any outbound transport code, a leak test per error path should be a design checklist item.
- **A low-risk tier for a stateful tool.** Leg 5 (the fake) skipped its leg design review as additive and single-surface. Its `reset` restarted Telegram `update_id`s, which made behavior-test checkpoint 10 inconclusive and forced a full re-run. A tool with state across calls deserves a "what survives reset" line, or a high tier.
- **Behavior-test clauses on log text must pin the exact grep.** Checkpoint 8 grepped "fallback", but the design never fixed the wording. Run 2's spec pins `grep -c "falling back to text"` and the baseline count.
- **Crew process slips:**
  - Crew left background `sleep` waiters running, despite the rule in their prompts (8 in the first fix pass, plus another loop in the second).
  - A dry check started processes with `cd X && cmd &`, recorded the subshell's PIDs, and then killed the real children by port.
  - Leg 1 edited the three freeze specs with `sed -i`, outside the edit-tool path the hook watches.
  
  None caused damage, but the rules in the prompts are not holding.

### Technical
- **`chart_image.py` is 1095 lines in one module** (fonts, measurement, scale, layout, painting). It wants the measure/layout/draw split `chart.js` got in Flight 1. There are now three implementations of chart scale logic (the Python spec, the browser and the image renderer), held together by the shared corpora.
- **Telegram delivery runs inside the poll task.** `is_alive` turns false after 110 s without a poll. The README records honestly that the existing text send's worst case (an HTML attempt plus a plain retry, each up to a 60 s 429 clamp) already exceeds that, and the new 45 s photo budget adds to it. This predates the flight but is now more reachable. It needs a design decision: deliver off the poll task, or extend liveness while a delivery is in flight. That is not a squawk.
- **The connector contract grows through comments.** `history`, `send_visual` and `send_visual_fallback` are optional, `getattr`-discovered methods on a structural Protocol. If a fourth appears, define a typed capability protocol. The Architect suggests folding `send_visual_fallback` into `send_visual` (for example a `resend_text` keyword), or at least a per-implementer test of the clamped policy.
- **httpx's INFO request log prints the full Telegram URL, bot token included, on every request** (pre-existing). Leg 4's token tests deliberately check only `the_one.*` records.
- **A widget-lifecycle timing flake surfaced at the debrief gate.** `tests/browser/test_ui_widget_hang_contract.py::test_heartbeat_loss_stops_a_loaded_card_while_the_page_ticks[chromium]` got `['stopped-hung', 'paused-user']`; it passed on isolated re-run. The file is from Flight 2 and Flight 3 did not touch it. It should wait on its clock seam deterministically.
- **No kerning on server text.** Server text sits slightly wider than the browser's kerned text. Measure the gap at Flight 4 alignment, with both renderers side by side.

### Documentation
- The README needs a rewrite (squawk candidate, below).
- `the_one/agents.md` should gain the patterns this flight established:
  - the optional `send_visual` / `send_visual_fallback` contract and "`VisualUploadError` only when nothing was posted";
  - transport errors as siblings of status errors;
  - one warning per fallback, from the shared helper;
  - error messages carry the status, never the body, raised `from None`, with resends outside the `except`;
  - measure from the font file plus a one-integer doctor gate;
  - the `monkeypatch.delitem(sys.modules, "PIL…")` rule for tests that drop Pillow.

## Test metrics (debrief gate, run fresh on `14fc068e`)

**Unit tier:** `THE_ONE_TEST_NETNS=1 make test-unit` gave 10118 passed, 15 skipped (the expected netns count), 0 failed, in 281.4 s (start load about 1.5).
- Against Flight 2's debrief (9769 passed, 248.85 s): +349 tests, +32.5 s (+13%).
- Against Flight 1's gate (9642, 256 s): +476 tests, +25 s.
- The suite is now **19 s inside the 300 s standing target**.
- Likely causes: about 350 new tests, including the fake-platform tests that start real servers on port 0, and Pillow and font loading in the renderer and doctor tests. The app's own import stays lazy.

**Browser gate:** `PARALLEL_RESULT rc=1 total=2268s lanes=20 failed=contracts-widget-lifecycle` (`--parallel 3`, WebKit required, netns, start load 0.96).
- Against Flight 1's gate (2163 s, 17 lanes): +105 s (+4.9%). Against M34 F1 (2027 s): +241 s.
- The one failure is the widget-lifecycle flake above (passed on isolated re-run).
- **The full local gate is about 2550 s (42.5 minutes) against the 43-minute target**, under 30 s of headroom.
- Lanes over budget:
  - `contracts-chat`: 177 s against a 150 s budget (about 100 s at Flight 1, +77%). Flight 3 added the tick-corpus contract test to that lane.
  - `contracts-overlay`: 257 s against 240 s (192 s at Flight 1). No overlay file changed, so this is probably the parallel mix or the host.
- Every other lane is within budget and within 15% of its Flight 1 reading. Skip counts are the usual engine skips.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Measurement by per-character advance sums, with per-character drawing (refines DD4) | BASIC still applies a legacy `kern` table (DejaVu "AV" 2799.953 against 2802) | Yes. Measure from the font file, per character. |
| The operator placed the font files by hand | The shell-write hook blocks `cp` into `the_one/`, and the Edit tool cannot write binaries | Yes, for vendored binaries. Plan it in the leg. |
| Leg 1 checkpoint review, commit and push before Leg 2 | Leg 2's apparatus, the hosted package workflows, builds a pushed ref | Yes, when a leg's apparatus needs a pushed ref |
| Leg 2 used hosted workflows instead of local container gates and the Windows test copy | They cover all three platforms the same way, with no operator at the desktop | Yes for gate-only checks |
| Leg 3 ran in parallel with Leg 2's builds | Leg 3 touched no packaging or renderer code, and Leg 2's only divert was independent | Case by case: a deliberate bet, not a default |
| `send_visual_fallback`, a second optional method (refines DD8/DD10) | `ConnectorClient.send` cannot carry the clamped 429 policy for the resend | Revisit (fold into `send_visual`?) |
| Transport errors as sibling classes | Telegram's plain retry catches any `TelegramApiError`, so a subclass would re-post | Yes |
| The fake answers the first `getUpdates` at once | The client's `connect()` waits on it, with a 50 s timeout | Yes, for long-poll fakes |
| One fallback warning, worded "falling back to text", with status only (behavior-test fix pass) | Run 1 found two warnings, and a body could reach a traceback | Yes |
| The fake's `update_id` monotonic across `reset` | Run 1, checkpoint 10 inconclusive | Yes. A fake's state must survive its reset where the client has state. |
| A refused seam value logs only the scheme and host; an empty variable counts as unset | Leg 6 design review | Yes |

## Key Learnings
- **A doctor gate that pins one integer derived from a SHA-pinned file is a cheap, strong cross-platform contract.** It turned a worry ("text renders differently on every host") into a pass/fail fact on three platforms in one run.
- **A fake proves what you send, and needs its own state discipline.** The fake earned its place: it found a real defect and pinned exact request shapes. But a reset that rewound its own state looked to the real client like an old message. Fakes need the same "what survives a reset" design line as the code they stand in for.
- **Witnessed behavior tests find failure-path defects that unit tests pinned to their own assumptions miss.** Both run-1 findings were invisible to the 500-plus unit tests written for them.
- **"Safe to resend" must be tied to an explicit platform answer.** A 4xx means nothing was posted; a 5xx, a timeout or a transport failure means it may have been. Every resend rule in this flight follows from that line.

## Methodology Observations

1. **agentic-workflow, Phase 2d / Git Workflow (commit once per flight): a leg whose apparatus builds a pushed ref.**
   - **What the methodology did:** it prescribes one review and one commit after the last autonomous leg.
   - **What was expected:** Leg 2's acceptance apparatus (hosted `linux-packages`, `windows-packages` and `macos-packages`) builds a pushed ref, so Leg 1 needed an early review, commit and push.
   - **Cost:** one extra review cycle (Haiku, about 2 minutes), plus a deviation recorded in the flight log. Low.
   - Recurrence in Mission 35: first time this flight. Flight 2's debrief should be checked for checkpoint commits to count it.
   - Plugin 1.2.3.

2. **agentic-workflow, Phase 3 step 3 ("Verify documentation"): the documentation check is too narrow (operator-raised).**
   - **What the methodology did:** it asks whether CLAUDE.md and the README reflect new commands, endpoints, configuration or APIs.
   - **What was expected:** the operator expects every flight to check all documentation its features touch: the README's feature tour and tables, the `docs/*` guides and the install guides. That covers features that change what the app *is* without adding a command.
   - **Cost:** the README went stale over many flights: providers in Settings, missing Rich visuals, Secrets and Dock mode, stale `search_tools` text, a build record stuck at "25+ missions". It now needs a dedicated squawk to rewrite.
   - **Recurrence:** cumulative across missions, not countable from one flight. The mission debrief should count which flights since about Mission 25 changed user-visible features without touching the README.
   - Plugin 1.2.3.

3. **flight, Phase 5b, and agentic-workflow, Phase 2a design reviews: failure-path observability was not checked.**
   - **What the methodology did:** two flight-level Architect cycles and five leg-level Developer reviews, all aimed at structure, citations and acceptance criteria.
   - **What was missed:** whether error paths leak data into logs or tracebacks, and whether one event logs once.
   - **Cost:** behavior-test run 1 failed checkpoint 8; one fix pass; a full re-run (about 30 minutes); a second fix pass for the chained-traceback body leak found at the flight-end review.
   - Plugin 1.2.3.

4. **agentic-workflow, Phase 2a risk tiering: "additive, single-surface" let a stateful test double skip review.**
   - Leg 5 (the fake platforms) was tiered low by the rule as written. Its reset-state defect surfaced only in the behavior test.
   - **Cost:** checkpoint 10 inconclusive, and a re-run of the whole test.
   - Plugin 1.2.3.

5. **behavior-test, Phase 4 (live mode): agents repeatedly reported they "cannot be resumed".**
   - Both Executor and Validator ended each turn with a hand-back that said they could not wait for `SendMessage`. Every `SendMessage` resumed them correctly, so the live mode worked.
   - **Cost:** noise in about 20 messages, and an Orchestrator check after each one. No rework.
   - Plugin 1.2.3.

6. **Crew rules in prompts not holding (local lesson, not a methodology finding).**
   - The "no backgrounded sleep" and "kill only recorded PIDs" rules are in this project's `leg-execution.md` prompts, and crews still broke them three times. The cost was cleanup only.
   - Kept as a local lesson. A hook or a wrapper (as for shell writes) may be the only reliable enforcement.

## Recommendations
1. **Make a documentation pass part of every flight's landing (operator request).** In the project's `.flightops` crew files, add a "Docs pass" step to the landing checklist and the Reviewer prompt:
   - list every user-visible change in the flight;
   - grep the README, `docs/*`, the install guides and CLAUDE.md for the affected surface;
   - update or explicitly clear each one, recorded in the flight log as "Docs checked: …".
   
   The debrief then states which docs were checked. Consider a cheap unit guard for facts that can be tested, for example that the README's command table matches `main.py`'s commands, or that the README doesn't name a Settings page that no longer exists.
2. **Log the squawks below,** including the README rewrite.
3. **Budget work before the next flight.** Re-budget `contracts-chat` (about 225 s, or split the chart contracts into their own lane) and `contracts-overlay` (back to 330 s). Then either raise the 43-minute full-gate target with a recorded reading, or rebalance: the gate is at 42.5 minutes.
4. **Decide Telegram delivery and liveness** (deliver off the poll task, or extend liveness during a delivery) at Flight 4 or the mission debrief. It is a design call, not a squawk.
5. **Add the flight's transport and logging patterns to `agents.md`, and a leak-test-per-error-path line to the leg design checklist** (Methodology Observation 3).
6. **Optional:** one live check, a single manual send of a chart reply to a real test channel on each platform, to see rendering. The fakes leave that unproven.

### Squawk candidates (Phase 6)
Logged 2026-11-13 by operator choice: 0349, 0350 and 0351. The lane re-budget was not logged; it stays Recommendation 3.
- **README rewrite** (servicing), **[squawk 0349](../../../../squawks/0349-readme-out-of-date.md)**. Fix the 12 inaccuracies found on 2026-11-13: providers in Settings; missing Model providers and Secrets in Library; `search_tools` after sortie 11; Dock mode; the build record; Rich visuals; Secrets; the notes, routines and time tools; `the-one quit`; the example version; the squawk-0170 line; the Pillow/`gui` wording.
- **httpx INFO log prints the Telegram bot token URL** (defect), **[squawk 0350](../../../../squawks/0350-httpx-log-prints-telegram-token.md)**. Raise the `httpx` logger to WARNING, or add a redacting filter, at the app level, with a `caplog` test across all loggers.
- **Widget heartbeat-loss timing flake** (defect), **[squawk 0351](../../../../squawks/0351-widget-heartbeat-loss-flake.md)**. Make `test_heartbeat_loss_stops_a_loaded_card_while_the_page_ticks` wait on the clock seam deterministically.
- **Lane re-budget** (servicing), not logged (operator choice). `contracts-chat` and `contracts-overlay` budgets, and the full-gate target, from this debrief's reading.
