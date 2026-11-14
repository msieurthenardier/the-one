# Squawk 0317: CLAUDE.md's Routines and Self-configuration paragraphs carry change-log detail

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: 2026-11-14

## Report
Squawk 0294 asked for the Routines and Self-configuration change-log detail to move out of CLAUDE.md into `the_one/agents.md`. Its Developer left that half undone. The squawk never named the sentences, and choosing them is an editorial call. Name the text to move here first, for example the per-flight "Since M33 F2 …" and "Since M33 F4 L06 …" history, then move it. Never delete information.

## Evidence
- `squawks/0294-agents-md-flight-4-patterns-and-claude-md-trim.md` (Corrective Action and Verification).
- CLAUDE.md's "Self-configuration surface" and "Routines (M33 F1)" paragraphs.

## Corrective Action
Named the text to move, then trimmed `CLAUDE.md`:
- "Self-configuration surface" paragraph: removed the tab-ordinal history ("the sixth, after Routines ... M33 F1 L06 ... L08"), "Since M31 F2 the tab is built on the control library and refreshes in place ...", "Since M33 F2 the tab has two items ..." (labels, testids, queue behaviours, `activate`) and "Since M33 F4 L06 the tab is two item cards ..." (card layout, expanders, the Routines-tab origin chip and flag). Kept: the tab is off by default and last, the loopback source, the four tools, approval mode, the endpoints, restore, and one sentence naming the two items, "unsaved General edits are kept" and the `agents.md` pointers.
- "Routines (M33 F1)" paragraph: removed the tab and form UI detail (compact grid, row menu, form fields, date and time pickers, Repeat presets, Custom recurrence dialog, preview line, Starts radio group). Kept the model, REST, scheduler, agent-written routines, agent tools and the operator-only now-start contract, with a pointer to "Routines (M33)".
Every removed fact already lives in `the_one/agents.md`; checked by grep: the Self-configuration tab item cards (`#### Self-configuration tab: two item cards`, "Two items", "Routines item", "Origin and flag elsewhere" bullets), the in-place refresh and "Save will replace it" note (agent editor frame, `general-tab.js` `applyStored`), the token reveal and `deactivate`, and the Routines modules, form, recurrence, `resolve_now_start`, preview and `Run now` bullets in "Routines (M33)". No `agents.md` change was needed.

## Verification
- The named sentences now live in agents.md.
- CLAUDE.md keeps one pointer line per surface.
- The doc-reading tests and `make test-unit` pass.

Done: grep of each removed term against `agents.md` (see Corrective Action) and a read of the two edited `CLAUDE.md` paragraphs. Doc-reading unit files named in the 0336 entry pass. The full `make test-unit` was not run (left to the Flight Director).

Review fixes: the five flagged facts were already in `the_one/agents.md`, so nothing was added. "Start in an amount of time" is the "Or start in N minutes/hours/days" fill in "Routine form (M33 F1 L9)" Fields; month by day or nth weekday is the `routine-custom-month-by` group in its Custom recurrence bullet; Save disabled in edit mode is in Fields; routines approval off for a new agent with existing rows kept is the "Agent-written routines" bullet (`AgentConfig.routines_require_approval = False`, `repositories.py` INSERT only); the Agent prompt default off is "Approval mode + revision queue"; focus to the next Approve or the empty state is the Routines item bullet (`self-config-routines-queue.js` `focusAfter`). A token-by-token check of every backticked term removed from `CLAUDE.md` found only `App.ui.noteFlag({subject:'routine'})` absent verbatim (documented as the `subject` option), and a phrase check of the prose found no fact held only in `CLAUDE.md`.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`. This covers the full `make test-unit` the Developer left open.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
