# Squawk 0342: Charts in chat — three missing documentation notes

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-09
**Completed**: —

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
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
