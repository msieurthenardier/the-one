# Leg: drawer-read-only-notes

**Status**: completed
**Flight**: [HAT and Alignment](../flight.md)

## Objective

Make the chat agent panel's Rules and Notes groups read-only and uncluttered,
show which notes are not yet in the open chat's prompt, and refresh them live.
This is the operator's HAT decision on 2026-10-10, after reviewing mockup E.

## Context

**The operator's decisions** (a HAT feature request; it passed the
fix-vs-feature gate as a FEATURE, so this design is reviewed before it is
built):
1. **Remove every delete control from the panel:** the per-note Delete and
   Clear all. Notes are managed in the agent's Rules and notes tab, reached
   through the panel's existing **Open agent settings** footer.
2. **Remove the "Edit rules" and "Edit notes" links,** since Open agent
   settings already sits at the bottom of the panel.
3. **Replace the "Check this" chip with a warning-triangle icon**
   (`alert-triangle` in `static/js/icons.js`) next to the note number.
4. **Pending notes:** notes that are not in the open chat's current prompt are
   **greyed out** and listed under a **"Pending · used from the next chat"**
   subheading, below the in-use notes.
5. **Live refresh:** when the agent saves, updates or forgets a note in the
   open chat, the panel re-fetches its notes without a reopen. This fixes HAT
   step 4's "No notes yet" after a save.

**Unchanged:**
- The Rules and notes **tab** keeps its "Check this" badge, Edit, Delete and
  Clear all. The operator did not ask to change it.
- The Rules group keeps its list of enabled rules plus "{n} off".

**This overrides #230**, which asked for per-note delete and Clear all in the
panel. The Flight Director amends the mission constraint text.

**Behavior-spec contracts change (flight DD2):** `agent-rules-round-trip`
step 4 (the Edit rules link) and `agent-notes-round-trip` steps 5 and 9 (panel
Delete, Clear all and Edit notes). The Flight Director re-authors those specs.
The Developer does not edit `tests/behavior/`.

## Design

**"Pending" is decided by the server, from the prompt actually in use.**
- `the_one/db/_notes.py` gains `parse_notes_block(system_text) ->
  dict[int, str] | None`, the inverse of `render_notes_block`:
  - it returns `{number: text}` for the `[n] text` lines inside
    `<saved_notes>…</saved_notes>`, with the `(unverified) ` marker removed and
    the delimiter neutralisation reversed;
  - it returns `None` when the prompt has no notes block (notes were off at
    build);
  - "No saved notes yet." gives `{}`.
- `GET /api/agents/{name}/notes` takes an optional `session_id` query
  parameter. When it is given and the session belongs to this agent, the
  server reads that session's current system message:
  - from the **live** web `Session` in `the_one.interfaces.web.app._sessions`
    (lazy import, the existing `api.py` pattern near `:4300`), using
    `agent.messages[0]`;
  - otherwise from the **persisted** `chat_sessions.messages[0]`, which is the
    last connector turn's build.

  It then adds `pending: bool` to every note: true when the note's number is
  absent from the parsed map, or its normalised text differs (an edited
  note). It also returns top-level `pending_known: true`.
- **When there is nothing to compare** (no `session_id`, an unknown session,
  another agent's session, or a prompt with no notes block), every note gets
  `pending: false` and `pending_known: false`.
- **Rationale:** exact, because it reflects what the model was actually given.
  It needs no client clock and no separate stored state, and it covers web
  sessions (rebuilt on rejoin), connector sessions (rebuilt per message) and
  the `next_turn` recompose (which rewrites `messages[0]`).

**Panel (`static/js/areas/chat/agent-drawer.js`):**
- **The view carries the session id:** `chat.js` passes `{agent, sessionId}`
  for `joined` and `joining` views. The notes fetch adds
  `?session_id=<encoded id>` when there is a session id, and the fetch state is
  keyed on agent and session.
- **Notes group, notes on:**
  - the in-use list (`pending` false), then, if any are pending, a subheading
    `p.chat-drawer-notes-pending-head` reading "Pending · used from the next
    chat", then a list of the pending notes;
  - pending notes use `--fg-muted` text, not opacity, to keep AA contrast;
  - each note is `[n]`, then the triangle icon for untrusted notes, then the
    text clamped to two lines (full text in the row `title`), then the origin
    line;
  - when there are no notes: "No notes yet".
- **Notes group, notes off:** "Off", plus "{n} kept".
- **The triangle icon:** the `alert-triangle` SVG (aria-hidden) in a
  `span.chat-drawer-note-flag` with `role="img"`, an `aria-label` of "Check
  this: written after content not from you: {sources}", and the same text in
  `title`. It is coloured with `--status-warning`; check the contrast as a
  graphical object at 3:1 on `--surface` in both themes.
- **Hover explains the icon** (operator, HAT). The `title` tooltip is a
  self-explaining sentence, not just the sources: "Check this note: it was
  written after content that didn't come from you ({sources}). It may have been
  planted." For example, "(fetch_url)" or "(peer:peer-1)". The `aria-label`
  carries the same sentence. AC3 and the browser test assert the `title`
  text.
- **Removed:** per-note Delete, Clear all, the Notes status line, "Couldn't
  delete", `focusNotesControl` and its helpers, the Edit notes link, and the
  Rules group's Edit rules link.
- **Live refresh:** a new `refreshNotes()` on the drawer handle re-fetches the
  current view's notes, bypassing the per-open cache. `chat.js` calls it on
  each live `tool_result` whose tool is `save_note`, `update_note` or
  `forget_note`. Live `tool_result` events carry no name, so `chat.js` maps
  `tool_call_id` to the tool name from the preceding live `tool_call` event,
  for the current turn. It also calls `refreshNotes()` after a
  `session_joined`, so a rejoin's rebuild clears the Pending entries.

## Design review amendments (binding, supersede the text above where they differ)

1. **Building the icon.** `App.icon(name)` returns an SVG **string**. Build the
   node without an HTML sink by copying the `markdown.js` `injectIcon` pattern
   (`:620-631`): `new DOMParser().parseFromString(svg, 'image/svg+xml')`, then
   `appendChild(doc.documentElement)`. Factor a small shared helper if
   convenient. **No `innerHTML`.**
2. **No exact inverse.** `parse_notes_block` returns `{number: rendered
   remainder}`: the text after `[n] ` exactly as rendered, `(unverified) `
   marker included. `api.py` decides pending by rendering each stored note the
   same way the renderer does (the marker when `untrusted`, then the
   neutralised text) and comparing it with the parsed remainder. This avoids
   reversing anything, and it also marks a trust flip as pending. AC1 becomes
   "parse agrees with render" over the listed cases. Its test is named
   accordingly.
3. **Anchoring.** Anchor on the **last** `"\n<saved_notes>\n"` (`rfind`) and
   the trailing `"\n</saved_notes>"`, since notes are the final layer
   (`agent/config.py`). Return `None` when either is missing. The body line
   `NOTES_EMPTY_TEXT` maps to `{}`, and the other lines match `^\[(\d+)\] `.
4. **Notes switched on after the build** (the prompt has no block, so the
   parse gives `None`): `pending_known` is false, and the panel shows no
   Pending section. This is **intentional**. Name it in `agents.md`.
5. **Reading the live session.** Use a lazy import of `_sessions` inside the
   handler (the established pattern).
   - Guard `session is not None`, its `agent`, and non-empty `messages`.
   - Check ownership with `(session.agent_name or "default") == name`.
   - On any miss, fall through to the persisted row, read through the
     repository app.py uses (confirm that the decoded `messages[0]` is the
     system message).
   - Always return both `pending` and `pending_known`.
6. **The live refresh map.** In `chat.js`:
   - the `tool_call` handler records `liveToolNames[data.tool_call_id] =
     data.name`;
   - the `tool_result` branch reads the map **before** the delivered-result
     split and calls `refreshNotes()` for a notes tool name;
   - `session_joined` clears the map and triggers `refreshNotes()`.
7. **Removed-control tests.** About eight tests in `test_flow_chat_drawer.py`
   exercise removed controls (`:695`/`:722` rules edit link; `:812`-`:1008`
   delete, clear, status, focus and the notes edit link). Remove them, or
   invert them into "absent" assertions where a guard is useful. Keep one test
   asserting that the panel has no delete controls or edit links. Grep for
   `notes-check|notes-delete|notes-clear|notes-status|notes-failed|edit-link`.
   The label-order test is updated.
8. **Registry.** Remove the retired rows from the **live** table as well as
   adding them to the Retired table. No retired id may be a left-boundary
   prefix of a live id. The new `chat-drawer-notes-flag`,
   `chat-drawer-notes-pending` and `chat-drawer-notes-pending-head` are clear.
9. **The tooltip format.** Sources are joined with ", ", as the current chip
   does. The full text is "Check this note: it was written after content that
   didn't come from you (fetch_url, peer:peer-1). It may have been planted."
10. **The AC4 mock turn.** The mock provider returns the same response on every
    call. A `save_note` `tool_calls` response therefore repeats until
    `max_iterations`, with de-duplication preventing extra notes. Prefer a mock
    config that keeps this short: set the test agent's `max_iterations` low
    (for example 2) through the agent API. Do not change the mock provider.

## Acceptance Criteria

- [ ] AC1. `parse_notes_block` round-trips `render_notes_block` for: no block;
      an empty block; trusted and unverified notes; text containing the
      neutralised delimiter tokens; numbers with several digits. Unit tests
      cover each.
- [ ] AC2. `GET .../notes?session_id=` sets `pending` and `pending_known`
      exactly as the design states, for each case:
      - a live web session;
      - a persisted connector session;
      - a note created after the build;
      - a note edited after the build;
      - an unknown session, another agent's session, and no `session_id`.

      Unit tests use the template database and seed the live `_sessions`
      entry. The response shape is otherwise unchanged (no `session_id`
      means an identical body except `pending_known: false` and
      `pending: false`).
- [ ] AC3. The panel renders the in-use list, then the Pending subheading and
      list (muted). There are no Delete, Clear all, Edit notes or Edit rules
      controls. The triangle replaces the chip, with the accessible name and
      title as designed. Off shows "Off" and "{n} kept". There is no
      HTML-string sink: build the icon with `App.icon`, as other areas do;
      check how `icons.js` exposes it.
- [ ] AC4. **Live refresh:** in a browser test, a mock-provider turn whose
      `tool_calls` run `save_note` makes the new note appear under Pending in
      the open chat's panel without reopening it. After a rejoin (reload the
      chat route) it moves to the in-use list.
- [ ] AC5. **The registry** retires these testids into its "Retired testids"
      table: `chat-drawer-notes-delete`, `chat-drawer-notes-clear`,
      `chat-drawer-notes-status`, `chat-drawer-notes-failed`,
      `chat-drawer-notes-edit-link`, `chat-drawer-rules-edit-link`. They are
      added to `tests/test_nav_helper.py`'s `RETIRED_SELECTORS` (the guard
      requires the table and the list to agree).
      - `chat-drawer-notes-check` is **renamed** to `chat-drawer-notes-flag`
        (retire the old id).
      - New: `chat-drawer-notes-pending` (the pending list) and
        `chat-drawer-notes-pending-head`.
      - `tests/test_ui_guards.py` passes both ways.
- [ ] AC6. `tests/browser/test_flow_chat_drawer.py`:
      - the Notes and Rules tests that exercised removed controls are
        **inverted or renamed** (rename over delete-and-re-add), to assert the
        controls are absent and the panel is read-only;
      - new tests cover the Pending section, the flag icon's accessible name
        and the live refresh (AC4);
      - the label-order test is updated.

      The `chats` lane passes.
- [ ] AC7. The static guards pass (`tests/test_ui_guards.py`,
      `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`,
      `tests/test_nav_helper.py`). `make test-unit` passes.
- [ ] AC8. Docs:
      - `the_one/agents.md`'s drawer contract (the notes and rules groups)
        and the notes REST section (`session_id`, `pending`);
      - CLAUDE.md's M27 paragraph: one sentence saying the panel is
        read-only, with Pending and live refresh.

## Verification Steps
- The unit tests for AC1 and AC2:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_notes_store.py tests/test_agent_notes_api.py -x --timeout 60`,
  or a new `tests/test_notes_pending.py`.
- The static guards, then `make test-unit`.
- `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=1200 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats -x`.

## Edge Cases
- **A pending chat** (no session yet): `sessionId` is absent, so there is no
  `session_id` parameter and no Pending section.
- **A note deleted after the build:** it is absent from the list. Do not try
  to show it, even though the prompt still has it.
- **The session belongs to another agent:** `pending_known` is false.
- **Notes off with stored notes:** "Off" and "{n} kept", and no Pending
  section.
- **A busy live session:** reading `agent.messages[0]` is safe: it is a
  read-only access.
- **The default agent** (`agent_name` None on the session): compare with
  `session.agent_name or "default"`.

## Files Affected
- `the_one/db/_notes.py`, `the_one/interfaces/web/api.py`.
- `the_one/interfaces/web/static/js/areas/chat/agent-drawer.js`,
  `static/js/areas/chat.js`, `static/css/chat.css`.
- `docs/ui-testid-registry.md`, `tests/test_nav_helper.py`.
- `tests/browser/test_flow_chat_drawer.py`, new or extended unit tests.
- `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit

Checked against `92038cf`:
- `notesGroup` and `rulesGroup` are in `agent-drawer.js`; the view setter is
  `render(next)` (around `:805`).
- `chat.js` builds the `drawerView` (around `:405-423`) and has the live
  `tool_call` and `tool_result` handlers (around `:1829-1870`).
- `api.py` lazily imports `_sessions` around `:4300`.
- The `alert-triangle` icon is in `icons.js:31`.
- The registry rows are at `docs/ui-testid-registry.md:79-91`.

All were verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## HAT scope additions (operator, 2026-10-10)

11. **The tab gets the triangle icon too.** The Rules and notes tab's "Check
    this" badge becomes the same warning-triangle icon, with the same
    tooltip and `aria-label`, built through a shared DOMParser icon helper.
    The tab's Edit, Delete and Clear all controls are unchanged.
12. **An operator edit clears the flag.**
    - `AgentNoteRepository.update_by_operator` sets `untrusted = 0` and
      `untrusted_sources = []`, as well as `updated_by='operator'`: the
      operator has taken ownership of the text.
    - **This applies only when the text actually changes.** An identical-text
      no-op leaves the flag unchanged.
    - An **agent** update still ORs the flag (unchanged).
    - Tests:
      - an operator edit of a flagged note clears the flag and its sources;
      - a later agent update in a tainted conversation flags it again;
      - an identical-text operator save keeps the flag.
    - **Docs:** `SECURITY-MODEL.md` "Agent notes" (the flag's lifecycle) and
      `the_one/agents.md`.
    - **UI:** the tab's row loses the triangle after a successful edit (it
      re-reads). Its browser test asserts this.
