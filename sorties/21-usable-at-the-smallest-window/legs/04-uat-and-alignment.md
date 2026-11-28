# Leg: uat-and-alignment

**Status**: completed
**Flight**: [Usable at the smallest window](../flight.md)

## Objective
The operator confirms, hands-on at real window sizes, that every page works in a small window and that wider windows are unchanged, with look-and-feel fixes made inline and any new behaviour routed through the fix-vs-feature gate.

## Context
- Interactive leg: the Flight Director guides the operator one step at a time; code fixes are made by spawned Developers.
- Before the session, one fix batch clears the flight review's carried non-blocking items (flight log, "flight review"): the `shell-pane.js` tidy-ups (one statement per line, a named first-tick constant), one shared focusable selector, GleepGlorp's `rescueFocus` fallback, the agent panel's header and `App.shellPane` guard, the exact Settings rail href pin, the stale docstring, the `agents.md` GleepGlorp width wording, `aria-keyshortcuts="Escape"` on the agent panel's Close button, and a wide clearance check on the Chats page.
- Environment: a dev instance on port 8491 with a scratch data dir under `$HOME`, started from a scratch cwd, `THE_ONE_DEV_MODE=true` (the `mock` provider), seeded with a mock provider and an agent; the operator opens it in a browser through a one-time handoff link. JS and CSS fixes need only a hard reload; Python changes need a restart.
- Things the leg design left for the HAT to judge: the brief list before the auto-join on a cold `#chats` load; Jump to and a dead-id heal at narrow widths; the "Appearance" title while the narrow Settings menu shows.

## Acceptance Criteria (verification steps, one at a time)
- [x] **S1 Carried fixes.** The fix batch lands; static guards, `layout`, `chats`, `gleepglorp-chat`, `contracts-overlay` lanes and the unit tier pass.
- [x] **S2 [setup] → [chats-narrow].** Window about 640 wide, short (or the browser's smallest). Chats: the list shows; open a chat: the chat fills the pane, the header is compact, at least three lines show above the composer; send a message and get the mock reply; no error messages.
- [x] **S3 [chats-narrow] → [list-via-rail].** Click Chats on the rail: the list shows; Back: the chat shows again; open a different chat from the list.
- [x] **S4 [chats-narrow] → [agent-panel].** Open the agent panel from the chat header: it fills the pane, focus is inside, the ✕ Close button shows; Tab never reaches the hidden chat; Escape closes it and focus is back on the toggle; open it again and close with ✕; open it and click Agents on the rail: it closes and Agents shows.
- [x] **S5 [agents-narrow].** Agents: the list shows; open an agent; walk every tab; the last control of each tab can be scrolled into view and is not under the GleepGlorp button; click Agents on the rail: the list shows.
- [x] **S6 [library-narrow].** Library: the grouped list shows; open a provider and a create form; nothing scrolls sideways; the rail icon returns to the list.
- [x] **S7 [settings-narrow].** From another destination click Settings: the Settings menu shows; open several pages including Built-in tools and a tool's editor; the rail icon returns to the menu.
- [x] **S8 [gleepglorp-narrow].** On Agents or Library open GleepGlorp from its corner button: it fills the pane with focus inside; ask it something; Close returns focus to the corner button; open it and use Jump to (Ctrl K): it closes and the destination shows.
- [x] **S9 [snapped-third].** A window snapped to a third of the screen (about 640 wide, full height): the same one-pane behaviour; nothing cramped; the transcript is roomy.
- [x] **S10 [half-screen].** A half-screen window (about 960 wide): list and detail side by side as before; the agent panel behaves as before (overlay at this width).
- [x] **S11 [wide].** A full-width window: the app looks and behaves as it did before this sortie.
- [x] **S12 [themes].** Repeat S2 and S4 briefly in the other theme.
- [x] **S13 Judgement calls.** The operator rules on: the brief list on a cold `#chats` load; the title saying "Appearance" while the Settings menu shows; anything else noticed.

## Fix protocol
- Look-and-feel fixes: spawned Developer, then re-verify the step. A fix spanning more than one surface gets a lightweight Developer design-review pass first.
- New behaviour: promoted to a scoped design review (fix-vs-feature gate), the FD's call made out loud.
- Each fix batch re-runs the static guards and the owning lanes before the step is re-verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
