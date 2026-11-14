# Squawk 0342: Charts in chat — three missing documentation notes

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-09
**Completed**: 2026-11-14

## Report
The Mission 35 Flight 1 debrief found three facts about charts in chat that are known but written nowhere a future developer or operator would look:
1. **Streaming-test pacing rule.** Mock streams in browser tests must be slower than the chat's 16 ms pacing tick (for example a few characters every 100 ms through `delay_ms`). Otherwise `done` drains everything at once and the commit and streaming logic is never exercised. Leg 2's first fence tests passed even with parse confirmation removed. Home: `the_one/agents.md` "Charts in chat", or the UI test apparatus notes.
2. **Small models do not chart.** qwen3-4b and lfm3 wrote no chart block in the m35 evals (0/120), so Rich visuals mainly helps larger models and can be switched off per agent. Home: `the_one/agents.md`, next to the switch's description.
3. **Axis text width is an estimate.** It is 6.4 px per code point, which mis-sizes CJK, emoji and bold labels. Home: `docs/chart-format.md` and the `App.ui.chart` catalogue row in `docs/ui-control-inventory.md`.

## Evidence
- `the_one/interfaces/web/static/js/ui/chart.js:512`: `function textWidth(text) { return cpLen(String(text)) * 6.4; }`. Also `:789`, where `maxChars` divides by 6.4.
- `the_one/agents.md:1644`: the "Charts in chat" paragraph mentions neither the pacing rule nor the small-model limit.
- `missions/35-rich-visuals-in-chat/flights/01-charts-in-chat/flight-log.md`: the leg 2 "Fast mock streams" finding, and the Part B visuals table (qwen3-4b and lfm3 at 0/20 per cell).
- Raised in `missions/35-rich-visuals-in-chat/flights/01-charts-in-chat/flight-debrief.md` (Documentation; Action Items).

## Corrective Action
1. **Pacing rule: already closed.** Sortie 16 removed the chat's pacing tick and commit logic, and `the_one/agents.md` already has "Streaming-test pacing rule (retired, sortie 16)" saying a mock stream needs no minimum chunk interval (and how to hold a turn open). No change.
2. **Small models do not chart: added.** `the_one/agents.md`, "Rich visuals switch" bullet: `qwen3-4b` and `lfm3` wrote no chart block in the Mission 35 Flight 1 evals (0 of 120, cited to the flight log), so the switch mainly helps larger models and can be turned off per agent.
3. **Axis text width: already closed.** `docs/chart-format.md` "Text width" and the `App.ui.chart` row of `docs/ui-control-inventory.md` already say axis text is measured in the browser (`getComputedTextLength()` through a probe `<text>`) and that 6.4 px per code point is only the fallback (`chart-scale.js::estimateWidth`). The squawk's evidence line (`chart.js:512`) is stale: that estimate moved to `chart-scale.js`. No change.

## Verification
Item 2 text checked against the flight log (`flights/01-charts-in-chat/flight-log.md`: "qwen3-4b and lfm3 never write a chart (0/120)"). Items 1 and 3 checked by reading `agents.md` and `docs/chart-format.md` and grepping `chart-scale.js`. `tests/test_ui_control_inventory.py` passes.

Two of the three notes were already closed by sortie 16 (the pacing rule and the axis text width); only the small-model note needed a change.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
