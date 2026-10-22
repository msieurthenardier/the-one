# Leg: flight-hat

**Status**: ready
**Flight**: [Agents on the library](../flight.md)

## Objective
The operator walks the agent editor on a dedicated dev instance, in both themes: every tab, the Agents list, and the Built-in tools editor guard. The walk confirms that:
- the agent editor on the library looks as it did, apart from the DD4 differences and the items below;
- the squawk 0220 and 0221 behaviours hold;
- the three DD9 defects are fixed;
- the before and after capture set is approved (the mission's capture criterion for this flight).

## Context
- **Flight decisions:** DD3 and DD4 (the visible changes), DD5 (0220/0221), DD6 (mount once, patch), DD9 (the defects), DD10 (captures).
- **Captures:**
  - before: `$HOME/.cache/the-one-ui-capture/m31-f2-before/`;
  - after: `$HOME/.cache/the-one-ui-capture/m31-f2-after/`, taken at leg 11, before the flight-review fix pass, so the mixed-switch edge (item 12) shows only live.
- **The HAT list from the flight log**, approved or changed by the operator:
  1. "Confirm delete?" / "Confirm purge?" in sentence case (06b).
  2. The standard-size Test button (06b).
  3. The switch label typography (07a).
  4. The MCP tile layout: flush rows, chip order, and the dimmed locked switch (07b).
  5. The error line's danger LED on Rules and notes (09).
  6. The visible self-configuration switch labels (10c).
  7. The stored-value note on a self-configuration conflict (10a, the operator's choice).
  8. The 0220/0221 behaviours (05).
  9. The DD9 fixes: collapsing an MCP source (07b), tool overrides preserved (08a), unsaved edits kept (10a).
  10. The capture differences leg 11 resolved: the "New" icon is restored; the danger-zone gap and trash icons are Flight 1 DD8's canonical layout.
  11. A VoiceOver check of a tool row's checkbox inside its Overrides `<summary>` (an a11y review finding). Optional; it needs a Mac.
  12. From the flight-review fix pass: the half-on master switch's track now has a thin accent edge.
- **Fix-vs-feature gate:** a look-and-feel fix rides inline. New behaviour goes through a scoped design review first. A change that spans more than one surface gets a quick Developer design pass before the fix.

## Inputs
- The flight is committed on `flight/02-agents-on-the-library`, and the draft PR is open.
- A dev instance:
  - port 8486 or higher (never 8484 or 8485);
  - a scratch data dir under `$HOME`;
  - started from a scratch cwd;
  - `THE_ONE_DEV_MODE=true`.
- Seeded with:
  - a mock provider;
  - two agents, A and B;
  - one knowledge base;
  - one stdio MCP source with a few tools;
  - one rule and one note on agent A.

## HAT steps (state transitions)
1. **[fresh] Open the dev instance** through its handoff URL and go to Agents.
   - The list shows A and B, and "New" has its icon at normal size (item 10).
   - Open agent A: the editor shows the "Agents" breadcrumb, the Chat button, Cancel and Save, and the six tabs.
   - No error messages.
2. **[general] Inspect General.**
   - Fields, the model picker, and Test at standard size with a status line (item 2).
   - Edit the description: the unsaved caption appears. Save: it clears, and focus goes back to the title.
   - Danger zone: Delete arms to "Confirm delete?" and Purge to "Confirm purge?" (item 1). Both lapse after about 3 s.
   - The arm is announced (0220).
3. **[knowledge] Inspect Knowledge.**
   - One library switch per knowledge base, with the label beside it (item 3). Tab reaches it, and Space toggles it.
   - Toggle, Save, reload: the attachment held.
4. **[mcps] Inspect MCPs.**
   - The MCP tile: flush rows and the chip order (item 4). Refresh is the small button.
   - The "N tools" expand opens the tool rows.
   - Turn one tool off: the master shows half-on, with the accent edge (item 12). Collapse and re-expand the source, and the choice is kept (DD9-1, item 9).
   - Save.
5. **[tools] Inspect Tools.**
   - Category tiles have tristate masters. Open one tool's Overrides, set a value and Save.
   - Edit only the description on General and Save again. Then reopen Overrides: the override is still there (DD9-2, item 9).
   - The chip "×" is muted and turns red on hover and focus (DD4 item 2).
   - Info buttons open on press, not hover, and close on Escape (0221, item 8).
6. **[rules-and-notes] Inspect Rules and notes.**
   - Add a rule, toggle it, move it, and delete it with an arm. Each saves at once.
   - An over-limit rule shows the error line with its danger LED (item 5).
   - The notes list and the empty states look right.
7. **[self-config] Inspect Self-configuration.**
   - The visible switch labels (item 6).
   - Enable it: the MCPs tab shows the locked source, dimmed, with the "managed on the Self-configuration tab" text (item 4).
   - Reveal an external token: Copy shows "Copied". Leave the tab and come back: the token is gone.
   - The history disclosure opens.
8. **[conflict] An unsaved edit meets a self-configuration write** (DD9-3, item 7). Type into agent A's description on General without saving. Approve or apply a description revision for A (the Flight Director drives the write through the API).
   - The typed text stays, and a note says the stored value changed and that Save will replace it.
   - Cancel: the stored value shows and the note clears.
9. **[theme] Switch to the other theme** (Settings › Appearance) and take a quick look at steps 4, 5 and 7. Nothing reads wrong.
10. **[guard] Settings › Built-in tools: open one tool's editor.** It looks unchanged (the admin editor guard capture).
11. **[captures] Review the before and after set**, side by side. The Flight Director can publish a private comparison page on request. Approve the set, or name each difference to change.
12. **Optional: [voiceover]** item 11, on a Mac.

## Acceptance Criteria
- [ ] Every step passes, or each failure is fixed and re-verified, with the fixes recorded in the flight log.
- [ ] HAT items 1-12 are approved or changed by the operator.
- [ ] The before and after capture set is approved (the mission's capture criterion for this flight).

## Edge Cases
- **Step 8 needs a write the UI cannot make on its own.** The Flight Director makes it through the API against the dev instance, or with approval mode on, the operator approves a pending revision from the Self-configuration tab in a second window.
- **A fix that touches other surfaces:** route it through a Developer design pass first.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
