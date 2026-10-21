# Flight Log: Agents on the library

**Flight**: [Agents on the library](flight.md)

## Summary
Planned 2026-10-15/16 on branch `flight/02-agents-on-the-library` (from `main` at `dbcd458`).

---

## Planning Notes

- **Re-plan.** Flight 1's debrief found the old Flight 2 overloaded. The operator chose two flights: Agents (this one), then Library and Settings (Flight 3). The mission's flight list was renumbered to six flights.
- **Operator decisions, 2026-10-15/16:**
  - New controls were previewed on a mock-up canvas built from the real CSS (https://claude.ai/artifact/Pzn35KdwV9gsTrnCPRCcqo), and the operator approved it.
  - The MCPs-tab boards could not be published (an auto-mode classifier refusal), so the Refresh-button change was described in words. It was approved.
  - Squawks 0094, 0217, 0220 and 0221 are folded in.
  - The flight closes with a HAT.
- **Planning surveys at `dbcd458`:**
  - the `studio.js` section map and split plan;
  - the agent editor and tabs;
  - the browser tests and their class selectors;
  - squawk recon: 0094 confirmed live and wider than reported, 0217 live with drifted evidence, 0220 and 0221 confirmed live.
- **Defects found in planning** (DD9):
  - the MCPs-tab collapse throws: `_parseSourceIdFromHash` is undefined;
  - suspected: stored `tool_overrides` are wiped on Save when Overrides was never opened;
  - a self-configuration change discards unsaved General edits.
- **Remaining debt ledger at the start** (reuse uses / sinks):

  | Area | Uses | Sinks |
  |---|---|---|
  | Agents | ~135 | ~35 |
  | Library and Settings | ~210 | ~16 |
  | MCP editor | 89 | 18 |
  | Chat | ~30 | ~6 |

  Totals: 243 rows / 504 uses, and 75 sinks in 14 files.

- **Architect design review: "approve with changes". All folded in.**
  - **DD9-2 confirmed real.** The server also wipes on an omitted key, so the fix is server-side preserve-on-omit plus a client omit-when-not-loaded.
  - **DD8 corrected.** There is no DOM builder in `tools-form-helpers.js`, so a `renderFieldNode` is added beside the string path, which stays as debt until Flight 3.
  - **DD5 test breaks listed.** The operator chose press-only toggletips on 2026-10-21, and that is now part of DD4.
  - **Listener and live-region rules** follow the `menu.js` precedent.
  - **Legs pre-split** from 7 autonomous to 11: before-set; the studio split as data/route, then state plus editor; Knowledge+MCPs vs Tools+overrides; Rules and notes vs Self-configuration.
  - **Smaller corrections:** the admin `.tool-tile*` is left alone; the chip-list admin variants are preserved, with an expected allowance bump; the admin editor is added to the captures; the files over 800 lines are recorded; `App.tabs` → `App.ui.tabs` API change; `mountSlot` in core with the singletons removed; environment re-verified per leg.

- **Architect review, cycle 2: "approve with changes" (text edits only), all applied.** Stale leg numbers fixed (the after set in leg 11; DD9-2 confirmed in leg 08; the split in legs 02-03). DD1 now maps modules to legs and introduces the state object at the top of leg 02. DD5's broken-test list is corrected: the admin string path keeps `title`. DD4 item 4 is marked as approved separately. DD8's node helpers are decided at leg 08. Flight set to `ready`.

---

## Leg Progress
