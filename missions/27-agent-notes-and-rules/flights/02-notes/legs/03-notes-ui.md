# Leg: notes-ui

**Status**: completed
**Flight**: [Notes](../flight.md)

## Objective

Let the operator turn notes on and off and see, trace, edit, delete and clear an
agent's notes from the Rules and notes tab's new Notes section, and review and
prune them from the open conversation's agent panel.

## Context

- Flight **DD10** (UI), **DD11** (REST shapes) and **DD13** (test placement)
  govern this leg; read [flight.md](../flight.md).
- **Leg 1's REST surface:**
  - `GET /api/agents/{name}/notes` returns `{enabled, notes:[{id, number,
    text, untrusted, untrusted_sources, origin_kind, origin_session_id,
    origin_label, origin_exists, origin_platform, origin_peer_id,
    origin_peer_name, created_at, updated_at, updated_by}], limits:
    {note_chars, total_chars, writes_per_turn}, usage: {total_chars}}`;
  - `PUT .../notes/settings {enabled}`;
  - `PUT .../notes/{id} {text}`;
  - `DELETE .../notes/{id}`;
  - `DELETE .../notes` returns `{deleted}`.

  Check the flight log's leg 1 entry for anything that landed differently.
- **Flight 1's tab:** `areas/studio/rules-notes-tab.js`.
  - It is built from `makeSection(panel, id, title)`; the Rules section is
    `buildRulesSection`.
  - Its `mutate(action, afterFocus, opts)` helper handles busy state, errors
    and focus restore.
  - The tab's callbacks come from `studio.js`, the same as the five rules
    callbacks.

  **Fold-in from Flight 1:** `mutate` takes an **explicit origin** (an
  `opts.origin` element or key) instead of inferring it from
  `document.activeElement`. Apply this to both the Rules and Notes sections,
  and keep the Flight 1 browser tests green.
- **Flight 1's drawer:** `areas/chat/agent-drawer.js` `rulesGroup(agentName)`
  with a per-open `rulesState` fetch (generation-guarded). The Notes group is
  its sibling, after Rules.
- Note text can come from an attacker. It is rendered through **`textContent`
  only**, with no HTML-string sinks; `tests/test_ui_guards.py` enforces this.
- Controls come from `App.ui`: `App.ui.toggle`, `App.ui.button`,
  `App.ui.textarea` and `App.ui.badge` (or the badge CSS),
  `App.confirmDelete` for arm-then-confirm, and `App.confirmDialog` for Clear
  all in the tab.

## Inputs

- Legs 1 and 2 landed, uncommitted, on `flight/02-notes`.

## Outputs

- A Notes section in `rules-notes-tab.js`, plus the explicit-origin `mutate`.
- The `studio.js` notes callbacks.
- A Notes group in `agent-drawer.js`.
- CSS.
- Registered testids.
- `tests/browser/test_flow_agent_notes.py` (new) and drawer tests.
- Docs.

## Acceptance Criteria

**Tab: Notes section (DD10)**
- [ ] AC1. Below Rules, a Notes section (`makeSection(panel, 'notes',
      'Notes')`) shows:
      - an `App.ui.toggle` labelled "Let this agent keep notes", which saves
        immediately through `PUT .../notes/settings` and reflects the server
        state after a re-read;
      - the shared "Changes apply…" line (already in the tab; do not
        duplicate it if it sits at tab level, otherwise reuse the same text);
      - when **off**, the message "Notes are off. This agent can't see or
        write notes. Saved notes are kept." The list is still shown when notes
        exist, so the operator can review and prune;
      - a usage line, "{used} of {total} characters";
      - the empty state "No notes yet." when there are none.
- [ ] AC2. Each note row (`notes-row` with `data-id` and `data-number`) shows:
      - `[n]` and the text (through `textContent`);
      - a meta line with:
        - the time: `App.time.formatClock` for today, otherwise a short date;
          "Updated …" when `updated_at` differs from `created_at`;
        - the origin: when `origin_exists`, a link to `#chats/{id}` (built
          with `App.router.href`) labelled with `origin_label`; otherwise
          "{origin_label or 'Untitled chat'} (chat deleted)"; for connector
          origins, the platform badge plus the peer name; for `other`,
          "Outside a chat";
        - "Edited by you" when `updated_by === 'operator'`.
      - For `untrusted` notes, a **"Check this"** badge. Its accessible name
        and `title` read "Written after content not from you: {sources joined
        by ', '}".
- [ ] AC3. Row actions:
      - **Edit** opens an inline textarea with a live "{n} / 400" count,
        `aria-invalid` and Save disabled while over, the same pattern as
        Rules, plus Save and Cancel;
      - **Delete** arms, then confirms, through `App.confirmDelete`, with the
        arm announced through the section's status region (the Flight 1
        pattern);
      - a 422 shows its `detail` inline in the section's error area.
- [ ] AC4. A **Clear all** button (shown when there are notes) opens
      `App.confirmDialog` "Clear all {n} notes? This can't be undone." On
      confirm it calls `DELETE .../notes`, then re-reads; Cancel changes
      nothing. Focus afterwards goes to the toggle.
- [ ] AC5. Focus behaviour mirrors Flight 1 AC9, and failures restore focus
      through the explicit origin. Create mode shows "Save the agent first."

**Drawer (DD10)**
- [ ] AC6. With a chat open, "What it can use" has a
      `.chat-drawer-group[data-group=notes]` group, after Rules, labelled
      "Notes".
      - **Off:** "Off", plus "{n} kept" when notes exist.
      - **On with notes:** each note shows `[n]`, its text clamped to two
        lines (full text in `title`), a short origin line (the chat label, or
        "{platform} · {peer}"), and a "Check this" marker for untrusted ones.
        Each has a Delete button (`App.confirmDelete`, its accessible name
        "Delete note {n}").
      - A **Clear all** button arms, then confirms, through
        `App.confirmDelete`, its armed text stating the count.
      - An "Edit notes" link to `#agents/{name}/rules-and-notes`.
      - **On with none:** "No notes yet" and the link.
- [ ] AC7. The drawer fetches notes once per open, beside the rules fetch, with
      the same generation guards. A 404 reads "No notes yet". After a delete or
      clear, the group re-fetches. A failed delete shows "Couldn't delete" in
      the group and keeps the list.

**Registry, tests, docs**
- [ ] AC8. Every new testid is registered in `docs/ui-testid-registry.md`
      (`notes-*`, `chat-drawer-notes*`), and `tests/test_ui_guards.py` passes
      both ways.
- [ ] AC9. `tests/browser/test_flow_agent_notes.py` (in the `agents` lane;
      confirm with `--lane agents --list`) seeds notes through the API. The
      seeding: enable notes, then insert notes. Notes can only be created by
      the agent, so tests seed through a **test-only path**: a direct repository
      insert against the instance's database (the browser harness gives the
      data directory), or a scripted mock-provider turn whose `tool_calls` run
      `save_note`. **Prefer the mock-provider path**, which proves the real
      chain; check whether the browser fixtures expose the data directory if
      the direct insert is needed. The tests cover:
      - toggle on and off, with the off message and the list kept;
      - the row meta with an origin link to the chat;
      - the "Check this" badge with its sources, for a note seeded after an
        untrusted tool result (via mock `tool_calls`, if feasible; otherwise a
        direct insert with `untrusted=1`);
      - inline edit, with "Edited by you" afterwards;
      - armed delete;
      - Clear all through the dialog, both cancel and confirm;
      - an over-limit edit blocked;
      - a failed save restoring focus;
      - create mode.
- [ ] AC10. `tests/browser/test_flow_chat_drawer.py` gains Notes-group tests:
      - off shows "{n} kept";
      - on lists notes with the origin and the "Check this" marker;
      - a per-note delete;
      - Clear all;
      - the Edit notes link navigates.
- [ ] AC11. The Flight 1 rules browser tests (`test_flow_agent_rules.py`) and
      drawer rules tests still pass with the explicit-origin `mutate`. Add one
      Rules test where a mouse-clicked Add (`page.click` on the button) fails
      and focus lands on the Add textarea. That closes the Flight 1 cycle-3
      residual.
- [ ] AC12. Static guards pass (`tests/test_ui_guards.py`,
      `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`),
      and `make test-unit` passes. The `agents` and `chats` lanes pass; record
      the `agents` lane's wall time in the flight log against its 510 s
      budget.
- [ ] AC13. Docs:
      - `the_one/agents.md` extends the "Rules and notes tab" section with the
        Notes section and drawer contract;
      - the CLAUDE.md paragraph Flight 1 added is extended in one or two
        sentences: the Notes section, the switch, the drawer Notes group, and
        the notes REST routes.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_agent_notes.py tests/browser/test_flow_agent_rules.py -x --timeout 90`
  while iterating (with `THE_ONE_TEST_NETNS=1` if `ERR_NETWORK_CHANGED`
  appears).
- `TEST_TIMEOUT=1500 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agents -x`,
  then `--lane chats`.
- The static guards, then `make test-unit`.

## Implementation Guidance

1. **Explicit-origin `mutate` first.** Refactor `mutate(action, afterFocus,
   opts)` so callers pass `opts.origin`: the element or a stable key such as
   `{kind: 'add'}` or `{kind: 'row', id, control}`. Failure focus is restored
   from it rather than from `document.activeElement`. Re-run the Rules browser
   tests before adding Notes.
2. **The Notes section** reuses the same helpers. Factor shared helpers (the
   counter sync, the inline-edit builder, focus restore) rather than copying
   them, where that stays readable.
3. **`studio.js` callbacks:** `fetchNotes`, `setNotesEnabled`, `updateNote`,
   `deleteNote` and `clearNotes`, beside the rules callbacks, through
   `App.api.fetchJson`.
4. **Drawer:** a `notesState` beside `rulesState` and a `notesGroup(agentName)`
   sibling builder. Per-note Delete and Clear all use `App.confirmDelete`, and
   their success and failure re-render through the existing `render()`.
5. **CSS** goes in the existing studio and chat stylesheets, using tokens only.
   The "Check this" badge uses an existing badge or status token with
   sufficient contrast. `tests/test_design_tokens_a11y.py` audits any new
   pair.
6. **Seeding helper for tests:** if the mock-provider path is used, add a small
   helper in `tests/browser/seeders.py`, or the existing seeder module, that
   configures a mock provider whose `response.tool_calls` call `save_note`.
   Record the approach in the flight log.
7. Docs per AC13.

## Edge Cases

- **Notes are off but notes exist:** list and allow pruning.
- **A very long note (400 characters):** it wraps in the tab and is clamped in
  the drawer.
- **An origin chat deleted:** shown as "(chat deleted)", with no link.
- **Rapid clicks:** controls are disabled while a request is in flight.
- **A note text containing HTML or markup** renders as literal text. Test it
  with `<b>x</b>`.
- **The drawer open while the tab changes notes:** the drawer shows the state
  as of when it opened, as with rules.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/rules-notes-tab.js`,
  `areas/studio.js`, `areas/chat/agent-drawer.js`.
- `static/css/studio.css`, `static/css/chat.css`.
- `docs/ui-testid-registry.md`.
- `tests/browser/test_flow_agent_notes.py` (new),
  `tests/browser/test_flow_chat_drawer.py`,
  `tests/browser/test_flow_agent_rules.py`, and possibly
  `tests/browser/seeders.py`.
- `the_one/agents.md`, `CLAUDE.md`.

## Citation Audit

Checked against `82a0396`:
- `rules-notes-tab.js` (472 lines) has `makeSection` (`:45`),
  `buildRulesSection` (`:53`), `mutate` (`:360`) and `App.confirmDelete` use
  (`:303`).
- `agent-drawer.js` has `rulesState` (`:174`) and `rulesGroup` (`:314`), with
  the link built through `App.router.href` (`:342`).
- `App.confirmDialog` is in `static/js/dialog.js`.

All were verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
