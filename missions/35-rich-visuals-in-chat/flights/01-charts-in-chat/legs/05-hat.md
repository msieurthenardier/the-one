# Leg: hat

**Status**: completed
**Flight**: [Charts in Chat](../flight.md)

## Objective
The operator walks charts in the real app, step by step, and confirms they look and behave as approved (mockups 1-6). Fixes are made inline, and the usage walk ends with the debrief question (DD15).

## Context
- Interactive leg: the Flight Director guides one step at a time and the operator performs it and reports. Look-and-feel fixes ride inline. Anything that adds behaviour goes through the fix-vs-feature gate. A change that touches more than one surface gets a lightweight Developer design review first.
- The frozen contract (DD15): the chart format (DD2) and the testids `chat-chart`, `chat-chart-plot`, `chat-chart-tooltip`, `chat-chart-data`, `chat-chart-live`, `chat-chart-error`, `chat-chart-placeholder`, `chat-chart-placeholder-source`, `agent-rich-visuals-toggle` and `chat-drawer-group[data-group="rich-visuals"]`. A HAT change to these is a spec re-author, not an inline fix.
- **Environment** (prepared by a Developer spawn, never the operator's production app):
  - a scratch dev instance on port 8490, with `THE_ONE_DEV_MODE=true` and a scratch data dir under `$HOME`, started from a scratch working directory;
  - a credential minted with `the-one rotate-api-credential`, and a handoff URL for the operator's browser;
  - seeded agents:
    - **Chart Demo (mock)**: a mock provider streaming a fixed reply with text, a line chart, text and a bar chart, `delay_ms` 300;
    - **Broken Chart (mock)**: a mock reply with an invalid chart;
    - **Analyst (haiku)**: an `anthropic-plan-token` provider using the operator's eval plan token, with the operator's OK at step 0;
    - **Small (qwen3-4b)**: an Ollama agent.

## Acceptance Criteria (the walk)
1. **[setup] → [chart streams]:** open Chats, New chat with Chart Demo, send "show me".
   - Text appears; then a glimmering placeholder reads "Rendering chart", then "Rendering line chart".
   - "Show source" holds the partial JSON.
   - No raw JSON shows in the bubble; the chart replaces the placeholder as soon as its block closes, while text still streams.
   - Two charts end up in the reply, in order.
   - No error messages.
2. **[chart drawn] → [inspect]:** hover the line chart, Tab to it and use the arrow keys, open "Show data".
   - The tooltip shows the x label and every series value.
   - The keyboard moves along points and Escape hides the tooltip.
   - The table lists every value with units, in a bounded scroll box.
   - The look matches boards 1-2.
3. **[inspect] → [theme switch]:** switch Appearance to Light, then to Auto with the OS in the other theme.
   - The chart repaints with no reload.
   - Contrast looks right in both themes (board 2).
4. **[theme] → [copy and history]:**
   - Copy reply: the pasted text holds the raw `chart` blocks.
   - Reload the page: the same charts draw again from history, with no placeholder.
5. **[history] → [broken and cut-off]:**
   - Broken Chart shows "Couldn't draw this chart." with a plain reason and the source under Technical details (board 5); the rest of the reply renders.
   - Stopping Chart Demo mid-chart shows "This chart was cut off before it finished."
6. **[real model]:** ask Analyst for charts.
   - Each chart type you ask for draws, including a stacked bar, a chart with two axes and one with a reference line.
   - A question with no numbers gets no chart.
   - Ask the Small agent too: it answers in text or tables, as the evals predict.
7. **[switch]:**
   - Analyst's General tab shows "Rich visuals" on, with its hint (board 6).
   - Turn it off and Save: the drawer shows Off after you rejoin the chat.
   - Settings › Prompts shows the "Rich visuals" section once, with its "Applies when".
   - A new chat with Analyst no longer offers charts unprompted, but a pasted chart block still draws.
8. **[layout and background]:**
   - Narrow the window below 1280 px (drawer overlay mode): the charts stay legible and the table scrolls.
   - Start a chart reply, switch to another chat while it streams, then switch back: no stray placeholder, and the chart is drawn.
9. **[usage walk close]:** the debrief question: "What would you want from charts day to day that this does not support?" Answers are recorded in the flight log as follow-ups, not built here unless they are fixes.

## Verification Steps
The operator's report at each step. The Flight Director records each step's result, and every fix, in the flight log.

## Implementation Guidance
- A Developer prepares the environment and reports the handoff URL and the PID file. It stops the instance by that PID at the end. Port 8490 must be free first (`ss -ltn`).
- Fixes during the walk are made by a Developer spawn with the "Fix Review Issues" prompt and re-verified at that step. After the walk, the flight's closing gate (`make gate`, quiet host) runs before the flight lands.

## Files Affected
Only what inline fixes need; recorded in the flight log.

## Citation Audit
No new code citations: the walk exercises the landed legs 1-4.
