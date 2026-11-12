# Leg: hat

**Status**: completed (walk passed 2026-11-11; step 4 accepted with minor jitter, step 6 with the documented Start anyway residual; HAT fixes reviewed by the Reviewer and the Accessibility Reviewer)
**Flight**: [Live Visuals](../flight.md)

## Objective
The operator walks live widgets in the real app, step by step, and confirms they look and behave as approved (mockups 1-6 and the explicit OKs). Fixes are made inline, and the usage walk ends with the debrief question.

## Context
- **Interactive leg:** the Flight Director guides one step at a time; the operator performs it and reports. Look-and-feel fixes ride inline. Anything that adds behaviour goes through the fix-vs-feature gate. A change that touches more than one surface gets a lightweight Developer design review first. Every fix pass runs `THE_ONE_TEST_NETNS=1 make test-unit` and the owning browser lane before it is re-verified.
- **The frozen contract (DD18):** the tag `widget`; `docs/widget-format.md`'s variables, events and limits; the page header (`frame-src 'none'; child-src 'none'`); the prelude's neutering list; the testids `chat-widget`, `chat-widget-frame`, `chat-widget-pause`, `chat-widget-restart`, `chat-widget-start`, `chat-widget-source`, `chat-widget-notice` and `chat-widget-placeholder`. A HAT change to these is a spec re-author, not an inline fix.
- **What is already proven** (so the walk is about look, feel and real use, not re-measuring): the escape battery and sink in Chromium, WebKit, WebKitGTK and WebView2 (legs 1, 3, 6, 8); the lifecycle, cap, ceiling and hang guard contracts (leg 5); widgets in chat and the `widget-escape` behavior test (leg 6); the prompt and evals (leg 7); the desktop bridge removal and quit-path crash record on all three platforms (leg 8).
- **Where:** the operator's browser on Windows against a scratch dev instance in WSL (mirrored networking, `127.0.0.1`). The desktop shell was walked by leg 8; step 9 below adds a short desktop look.
- **Known behaviour to expect, not a defect:** with the OS's "reduce motion" setting on, every widget starts paused (Paused chip, Resume), as approved. A browser closed as a whole with a widget loaded shows "This widget stopped responding last time." once on the next visit (DD9, accepted for `serve`).

## Inputs
- Legs 1-8 committed (`95a9bcd9`). The other session's uncommitted `the_one/db/_notes.py`, `tests/test_prompt_layers.py`, `tests/behavior/agent-notes-round-trip.md` and `env.sh` stay untouched.
- The operator at the Windows desktop with a browser; the eval plan token (`~/.config/the-one-evals/plan-token`) for the real-model agent, used only with the operator's OK at step 0; Ollama with `qwen3:4b-instruct-2507-q4_K_M` (one local model at a time).

## Environment (prepared by a Developer spawn, never the operator's production app)
- A scratch dev instance on port 8490 (free first: `ss -ltnp`), `THE_ONE_DEV_MODE=true`, a scratch data dir under `$HOME`, started from a scratch working directory; PID recorded; a credential from `the-one rotate-api-credential`; a handoff URL for the operator's browser (`POST /api/session/handoff`), minted fresh per browser navigation from an unauthenticated state.
- `scripts/widget_sink.py` running on `127.0.0.1` (PID recorded), for the hostile widget.
- Seeded agents:
  - **Widget Demo (mock):** a mock provider streaming a reply with text, an animated canvas widget (with a `<title>`), text, a bar chart, then a small interactive widget (a button that counts clicks), in `stream_chunks` paced slower than the 16 ms tick (`delay_ms` 300); blank lines around every fence.
  - **Hostile (mock):** a reply holding the escape battery (`tests/fixtures/widgets/escape.html` served by the sink's `/__sink/fixture`).
  - **Runaway (mock):** a reply holding a widget whose script, after a "Start loop" button press, runs `for(;;){}`.
  - **Analyst (haiku):** an `anthropic-plan-token` provider using the eval plan token (operator's OK at step 0), Rich visuals on.
  - **Small (qwen3-4b):** an Ollama agent, Rich visuals on.
- A seeded session **Long chat** (history through `POST /api/chat/sessions` with `messages`) with twelve assistant replies, each holding one small animated widget with a visible frame counter, and text between them; created last but one so it does not auto-open.
- **Apparatus self-check before the operator starts** (Flight 1 debrief observation 5), reported by the Developer: every seeded reply has blank lines around its fences; the mock streams are paced (`delay_ms` 300, more than one chunk per fence); `ss -ltnp` shows exactly the recorded PID on 8490 and the sink's ports; a scripted Playwright pass opens Widget Demo and Long chat once and finds the expected card counts and no notice, then closes (no state left behind beyond those sessions).

## Acceptance Criteria (the walk)
0. **[setup]:** the Flight Director shows the environment report and the self-check; the operator OKs the plan-token use and opens the handoff URL.
   - The app opens on Chats; no error messages.
1. **[new chat] → [widget streams]:** New chat with Widget Demo, send "show me".
   - Text streams; a placeholder reads "Rendering widget" with the glimmer and "Show source" (board 4); no raw HTML shows in the bubble.
   - The canvas widget replaces the placeholder when its block closes, while text still streams; it is headed "Widget by Widget Demo · {title}" (board 1) and animates.
   - The chart and the click-counter widget follow in order; clicking the counter's button counts.
   - No error messages; focus stays in the composer while the widgets start.
2. **[running] → [pause, scroll, resume]:** press Pause on the canvas widget, scroll it out of view and back, then Resume.
   - Pause shows the "Paused" chip and Resume (board 2), and the animation stops.
   - Scrolled away and back it is still paused; Resume restarts it.
   - View source opens and shows the exact source.
   - Restart reloads it from the start.
3. **[running] → [theme switch]:** switch Appearance to Light, then to Auto with the OS in the other theme, while widgets run.
   - The card chrome and the widget's own colours (it uses the theme variables) change with no reload, and the widgets keep running.
4. **[many widgets]:** open Long chat and scroll from top to bottom and back.
   - At most three widgets animate at once (the ones in view); widgets scrolled away pause and resume when back in view.
   - A widget beyond the running cap shows the capped card with Start (board 3); Start runs it.
   - Scrolling the whole chat never shows more than eight loaded frames' worth of work (no stutter, no runaway CPU); unloaded cards keep their height, so the page does not jump.
5. **[hostile]:** a new chat with Hostile, send "go".
   - The battery's grid shows every path refused; the page's URL and history are unchanged; no new tab or dialog; the sink count (read by the Flight Director) stays 0.
   - Typing in the composer while the widget runs keeps the text in the composer.
6. **[hang guard]:** a new chat with Runaway, send "go", press "Start loop".
   - Within about 5 s the widget is stopped with "This widget stopped responding." and Start anyway (board 3, board 6's stall variant); the rest of the page stays usable.
   - With the loop loaded again (Start anyway, Start loop), end the tab's process from the browser's task manager (Shift+Esc → End process), reopen the handoff URL (a fresh mint) and the chat: the widget shows "This widget stopped responding last time." once, with Start anyway.
7. **[background and window]:** start Widget Demo's reply, switch to another chat while it streams, then switch back; then minimise the browser and restore it.
   - No stray placeholder; the widgets are drawn after the switch back.
   - Minimised, the widgets pause; restored, they resume (no "stopped responding" false positive).
8. **[copy, history, narrow]:**
   - Copy reply on Widget Demo: the pasted text holds the raw `widget` and `chart` blocks.
   - Reload the page: the widgets and the chart draw again from history, with no placeholder.
   - Narrow the window below 1280 px (drawer overlay mode): the cards fit (board 6's narrow layout) and the header controls stay usable.
9. **[real models]:** ask Analyst for an animation (for example a pendulum), a calculator and a simulation, and for one reply with two widgets and a chart.
   - Each widget runs and is the thing asked for; the two-widget reply renders both widgets and the chart.
   - A question with no need for visuals gets plain text.
   - Ask Small for an animation too: record what it does (the evals predict a widget most of the time).
   - Optional desktop look: open the same chat in the desktop app test copy if the operator wants (not required; leg 8 covered the shells).
10. **[switch off]:** Analyst's General tab: turn "Rich visuals" off and Save.
    - The drawer shows Rich visuals Off after you rejoin the chat.
    - A new chat with Analyst asked for an animation answers without a widget block; a pasted `widget` block in a reply from history still renders (the switch only changes the prompt).
11. **[usage walk close]:** the debrief question: "What would you want from live widgets day to day that this does not support?" Answers are recorded in the flight log as follow-ups, not built here unless they are fixes.

## Verification Steps
The operator's report at each step. The Flight Director records each step's result, and every fix, in the flight log.

## Implementation Guidance
- A Developer prepares the environment (above), runs the self-check and reports the handoff URL, the PIDs and the seeded session ids. It stops the instance and the sink by those PIDs at the end. It never touches port 8484/8485 or the default data dir.
- Fixes during the walk are made by a Developer spawn with the "Fix Review Issues" prompt and re-verified at that step. After the walk, the Reviewer (Sonnet; the widget frame is a security-sensitive surface) and the Accessibility Reviewer cover any HAT fixes, then the flight's closing gate (`make gate` under `THE_ONE_TEST_NETNS=1`, contract lanes with `THE_ONE_REQUIRE_WEBKIT=1`, quiet host) runs before the flight lands.

## Edge Cases
- **Reduce motion on:** every widget starts paused; the walk presses Resume where it says "animates".
- **A real model writes no widget** (Small): recorded, not a failure.
- **Ollama:** only one local model loaded at a time (operator, 2026-11-10).

## Files Affected
Only what inline fixes need; recorded in the flight log.

## Citation Audit
No new code citations: the walk exercises the landed legs 1-8. The fixture `tests/fixtures/widgets/escape.html`, `scripts/widget_sink.py` (`/__sink/fixture`, `/__sink/counts`) and the seeding route are the ones leg 6's behavior test and leg 8's sessions used.
