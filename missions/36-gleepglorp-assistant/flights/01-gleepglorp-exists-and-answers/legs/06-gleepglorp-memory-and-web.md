# Leg: gleepglorp-memory-and-web

**Status**: completed
**Flight**: [GleepGlorp exists and can answer](../flight.md)

## Objective
Give GleepGlorp its own notes (memory) behind the memory switch, with a Memory
section on its Settings page, and `fetch_url` and `web_search` behind the web
switch, with a Settings hint when web search is not set up.

## Context
- Flight DD4, the web part of DD5, DD7 (the Memory section), board screen 1.
  This leg is the first of three split from the planned Leg 6 at its design
  review (flight log): memory and web here; the guide in Leg 7; the shipped
  prompt and the Prompts block in Leg 8. The superseded leg file
  `06-gleepglorp-guide-memory-web.md` is kept, marked `aborted` (never
  started), for its survey and citations.
- Decisions from the design review (Flight Director):
  - `read_app_config` stays untrusted (the fail-closed default): agent-written
    prompts and descriptions (self-configuration) and server-written MCP tool
    descriptions reach GleepGlorp through it. So most GleepGlorp notes will be
    flagged. This is recorded in `SECURITY-MODEL.md`; Flight 2 revisits the
    granularity, as DD5 planned.
  - The notes heading and the save tool's description speak of a person's life
    and of rules that take precedence (`db/_notes.py` `NOTES_HEADING` ~:25-32;
    `notes/tools.py` save description ~:150), wrong for GleepGlorp. GleepGlorp
    gets its own heading and save description (setup facts and preferences
    about the app; no rules clause); the agent defaults stay byte-identical (the
    platform pins and the evals depend on them).
  - The Memory rows share the agent Notes tab's row through a new pure builder;
    the rows keep the shared `notes-row*` testids inside a
    `gleepglorp-memory-list` wrapper.
- Code facts (survey, re-locate by symbol; Leg 5 may shift `factory.py`):
  - `notes/tools.py`: `_NotesToolBase.__init__(agent_name, counter)` ~:62;
    `_repo()` staticmethod hard-coding `AgentNoteRepository` ~:112-117; save
    ~:166, update ~:198, forget ~:230; `_origin(turn)` ~:120-150 reads only
    `chat_sessions` (works for GleepGlorp); tool names from `NOTES_TOOL_NAMES`
    (`agent/tool_names.py` ~:14).
  - `notes/tool_provider.py` ~:25-34 builds tools only when
    `config.notes_enabled`, one `_WriteCounter` per build.
  - `AgentNoteRepository` (`db/repositories.py` ~:2361-2664), its helpers and
    `_COLS`/`_FROM` (the LEFT JOIN on `chat_sessions` that yields
    `origin_exists` for "(chat deleted)").
  - Schema v53: `gleepglorp_notes`, `gleepglorp_notes_counter` `(1, next)`.
  - `render_notes_block(notes, *, tools=True)` (`db/_notes.py` ~:116).
  - Factory: the GleepGlorp assertion that `notes_enabled` is false (~:522-529);
    notes tools register outside the whitelist and `disabled_names`
    (~:625-631) and are force-seeded for GleepGlorp.
  - `gleepglorp/build.py` sets `notes_enabled=False` (~:23) and
    `enabled_tools=[]`, which blocks `fetch_url`/`web_search`
    (`agent/config.py` ~:175-207); the app-wide `disabled_names` still applies.
  - Web tools and search engines: `tools/web.py` ~:244 (`fetch_url`), ~:479
    (`web_search`); `tools/builtins.py` ~:195-255; `_search_backends.py`
    ~:541-579; keyed engines' required fields (`_web_search_config.py`):
    searxng `searxng_base_url`; google_pse `google_pse_api_key` +
    `google_pse_cse_id`; brave `brave_api_key`; tavily `tavily_api_key`.
  - Notes UI: `areas/studio/notes-section.js` (`buildOrigin` ~:57 module-level,
    not exported; `buildRow` ~:177 a closure inside `buildNotesSection` using
    `editingId`, `maxChars`, `mutate`, `cb.updateNote`, `listWrap`, `busy`;
    only `App.studio.buildNotesSection` exported ~:358; Clear all via
    `App.confirmDialog` ~:333); `App.studio.rulesNotesShared` delete button
    (`rules-notes-shared.js` ~:199-212); `App.ui.noteFlag`.

## Inputs
- Leg 5 landed (**hard precondition**: both touch the GleepGlorp build and its
  allowlist test).

## Outputs
- `the_one/gleepglorp/notes.py` (`GleepGlorpNoteRepository`) and the GleepGlorp
  notes heading and save description.
- Notes tools with a repository chosen by agent name; GleepGlorp notes behind
  `memory`; the notes layer in GleepGlorp's prompt.
- `GET /api/gleepglorp/notes`, `DELETE /api/gleepglorp/notes/{id}`,
  `DELETE /api/gleepglorp/notes`; the Memory section.
- Web tools behind `web_access`; `web_search_available`; the Settings hint.
- Tests and docs.

## Acceptance Criteria

**Memory**
- [ ] With `memory` on, GleepGlorp has the three notes tools (the
      `NOTES_TOOL_NAMES`, same schemas except the save description), backed by
      `GleepGlorpNoteRepository`: dedup, the per-note and 4000-char total
      limits, the per-turn write counter, the untrusted flag and sources from
      `compute_taint`, and numbers that only go up (`create` bumps the counter
      row in the same `write_transaction`; a delete or clear never decrements
      it). `memory` is read from `the_one.gleepglorp.settings` on every write,
      so turning memory off mid-chat makes the next write fail with
      `NotesDisabledError`'s message. With `memory` off GleepGlorp has none of
      the tools. No agent's notes table is touched (a test).
- [ ] GleepGlorp's prompt carries its notes layer, rendered by
      `render_notes_block` with a GleepGlorp heading (tool-capable and
      tool-free), after the prompt text and before the date line, only when
      `memory` is on. `render_notes_block` gains an optional heading override;
      with no override its output is byte-identical (the existing tests and
      `tests/_platform_prompt_pins.py` pass untouched). GleepGlorp's save
      description speaks of setup facts and preferences about the app.
- [ ] The repository keeps the `chat_sessions` LEFT JOIN, so a note whose
      origin chat is gone reads "(chat deleted)".
- [ ] `GET /api/gleepglorp/notes` returns `{enabled, notes, limits, usage}` in
      the agent notes route's shape (no `agent_name`, no pending);
      `DELETE /api/gleepglorp/notes/{id}` (404 on unknown) and
      `DELETE /api/gleepglorp/notes` (`{deleted}`); all behind the credential
      gate and classified in `tests/test_api_name_rule.py`.
- [ ] A pure row builder is extracted from `notes-section.js`
      (`App.studio.noteRow(note, {actions})`: text, flag, time, origin, "Edited
      by you"), and the agent Notes tab uses it with its Edit and Delete as
      actions; every `notes-row*` testid and the agent tab's behaviour are
      unchanged (the `agent-tabs` lane's Notes tests pass untouched).
- [ ] The Settings page's Memory section (board screen 1): the eyebrow "Memory"
      with Clear all (`gleepglorp-memory-clear`, through `App.confirmDialog`),
      the list (`gleepglorp-memory-list`) of shared rows with a Delete action
      (`gleepglorp-memory-delete`, the armed confirm), "No saved notes yet."
      when empty, and when memory is off the hint "Memory is off. GleepGlorp
      keeps no new notes; these stay until you delete them." Delete and Clear
      all act at once (not part of Save) and the list reloads after each and on
      a `gleepglorp_changed` push. Note text uses `textContent` only.

**Web**
- [ ] With `web_access` on, GleepGlorp has `fetch_url`, and `web_search` unless
      the configured engine is keyed with a required field empty; each is also
      absent when switched off for the whole app. With `web_access` off it has
      neither. They run under the operator's existing `WebConfig` /
      `WebSearchConfig` limits.
- [ ] One function `search_configured(...)` decides the keyed-engine case and
      feeds both the build and `GET /api/gleepglorp`'s new
      `web_search_available`. With web access on and search unavailable, the
      Settings page shows under the Web access switch "Web search isn't set up,
      so GleepGlorp can only read pages you give it." with a link to
      `#settings/tools/web_search`.

**Allowlist and gate**
- [ ] The allowlist test pins GleepGlorp's registered tools for every
      combination of `memory` on/off, `web_access` on/off, search available or
      not, and `fetch_url`/`web_search`/`current_time` switched off app-wide.
      (The base set is `{search_tools, current_time, read_app_config}`; Leg 7
      adds `get_app_guide`.)
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes under 350 s; lanes
      `settings` and `agent-tabs` pass; static guards pass; ruff clean.
- [ ] Docs: CLAUDE.md and `the_one/agents.md` (GleepGlorp memory and web),
      `docs/ui-testid-registry.md`, `SECURITY-MODEL.md` (GleepGlorp's notes are
      flagged like an agent's, and why most will be: `read_app_config` is
      untrusted).

## Verification Steps
- Targeted: `tests/test_gleepglorp_notes.py`, `tests/test_gleepglorp_build.py`,
  `tests/test_gleepglorp_settings.py`, the notes tools tests, the notes render
  tests.
- `THE_ONE_TEST_NETNS=1 make test-unit`; lanes `settings` and `agent-tabs`.
- Falsify: memory off still saving; the counter decrementing; the heading
  override changing the default; the web whitelist; `search_configured`.
- Manual on a scratch instance with the mock provider scripted to call
  `save_note`: the note appears in the Memory section, deletes, and Clear all
  works; record in the flight log.

## Implementation Guidance
1. **Repository.** `the_one/gleepglorp/notes.py` with the methods the tools and
   routes use (`create`, `update_by_agent`, `forget_by_agent`,
   `list_for_agent`, `delete`, `clear`, `total_chars`, `get`, `get_by_number`),
   the `name` argument accepted and asserted to be `GleepGlorp`, the same
   exceptions, `_switch_state` reading `load_settings(conn).memory` and the
   counter row, rows built with `agent_name="GleepGlorp"`. Import the pure
   helpers; extract shared write logic only if small and the agent notes tests
   pass unchanged.
2. **Tools.** `_repo()` becomes an instance method choosing by
   `self._agent_name == GLEEPGLORP_AGENT_NAME`. The provider builds GleepGlorp's
   tools with the GleepGlorp save description. `build.py` sets
   `notes_enabled=settings.memory`; remove the factory assertion's
   `notes_enabled` clause.
3. **Prompt layer.** `render_notes_block(..., heading=None)`; `prompt.py`
   loads GleepGlorp notes when memory is on and inserts the block. Keep a pure
   `compose(...)` beside the async `build_prompts` (Leg 8 uses it).
4. **Routes and UI.** The three routes; extract `noteRow`; the Memory section
   in `gleepglorp-page.js`.
5. **Web.** `build.py` `enabled_tools` = `["fetch_url", "web_search"]` when
   `web_access` (minus `web_search` when `search_configured` is false);
   `web_search_available` in the settings response; the hint.
6. **Docs** as the AC.

## Edge Cases
- **Memory turned off with notes stored**: they stay, listed with the hint, and
  are not in the prompt.
- **`fetch_url` off app-wide, web access on**: `web_search` only (if available).
- **Keyed search incomplete, web access on**: `fetch_url` only, hint shown.
- **The tool-free variant**: the tool-free heading, no tool names.

## Files Affected
- New: `the_one/gleepglorp/notes.py`, `tests/test_gleepglorp_notes.py`.
- Changed: `the_one/notes/tools.py`, `the_one/notes/tool_provider.py`,
  `the_one/db/_notes.py`, `the_one/agent/factory.py`,
  `the_one/gleepglorp/{build,prompt,settings}.py`, `the_one/interfaces/web/api.py`,
  `static/js/areas/admin/gleepglorp-page.js`,
  `static/js/areas/studio/notes-section.js`, tests, docs.

## Citation Audit
See the superseded `06-gleepglorp-guide-memory-web.md` audit and its design
review (flight log); `notes-section.js` closure and export facts and the notes
heading text verified by that review. Re-check `factory.py` and `build.py`
after Leg 5 lands.
