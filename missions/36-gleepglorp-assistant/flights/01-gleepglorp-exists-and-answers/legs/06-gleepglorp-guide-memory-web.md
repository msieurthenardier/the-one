# Leg: gleepglorp-guide-memory-web

**Status**: aborted (never started; split at its design review into
`06-gleepglorp-memory-and-web`, `07-gleepglorp-guide` and
`08-gleepglorp-prompt`, which carry its scope; kept for its survey and
citations)
**Flight**: [GleepGlorp exists and can answer](../flight.md)

## Objective
Give GleepGlorp what it knows and remembers: the shipped app guide with a
`get_app_guide(topic)` tool and a drift test, its own notes (memory) behind the
memory switch with a Memory section on its Settings page, `fetch_url` and
`web_search` behind the web switch, and its real shipped prompt, shown read-only
in Settings › Prompts.

## Context
- Flight DD4, DD6, DD7 (the Memory section), the rest of DD5 (web tools), the
  mission's knowledge-sources and help-docs planning decisions, and the board's
  screens 1 (Memory section) and 6 (Prompts). Split from the original Leg 5
  (flight log).
- Legs 3-5 (landed, uncommitted) built: the settings (`memory`, `web_access`),
  the GleepGlorp branch of `AgentFactory._build` (force-seeds every GleepGlorp
  tool, `factory.py` ~:729-735; asserts `not config.notes_enabled` ~:522-529),
  `gleepglorp/build.py` (`notes_enabled=False` ~:23, `enabled_tools=[]`),
  `gleepglorp/prompt.py` (`PLACEHOLDER_PROMPT` ~:16, `build_prompts(conn, *,
  tool_available, now=None)`), `read_app_config`, the chat surfaces and the
  Settings page (Model and Behavior sections, `gleepglorp-page.js` ~:432-447).
- Code facts (read-only survey; re-locate by symbol):
  - Notes tools (`the_one/notes/tools.py`): `_NotesToolBase.__init__(agent_name,
    counter)` ~:62; `_repo()` is a staticmethod hard-coding
    `AgentNoteRepository(await get_connection())` ~:112-117; save ~:166 (taint
    via `compute_taint`, origin via `_origin(turn)` ~:120, `repo.create(...)`),
    update ~:198 (`update_by_agent`), forget ~:230 (`forget_by_agent`); the
    tools expect `KeyError`, `NotesDisabledError`, `NoteLimitError`,
    `NoteDuplicateError`. `NotesToolProvider` returns tools only when
    `config.notes_enabled` (`notes/tool_provider.py` ~:25-34).
  - `AgentNoteRepository` (`db/repositories.py` ~:2361-2664): `list_for_agent`,
    `list_if_enabled` (reads `agents.notes_enabled`), `get`, `get_by_number`,
    `total_chars`, `_switch_state` (reads the agents row) , `create` (dedup,
    4000-char total, bumps the counter), `update_by_agent`,
    `update_by_operator`, `forget_by_agent`, `delete`, `clear`; helpers
    `_COLS`/`_FROM` (LEFT JOIN `chat_sessions` for `origin_label`),
    `write_transaction`, `validate_note_text`, `dedup_key`,
    `notes_total_limit_error`, `_merge_sources`. Model `AgentNote`
    (`db/models.py` ~:331, `agent_name` required).
  - Schema v53 (`db/schema.py` ~:3393-3421): `gleepglorp_notes` (the
    `agent_notes` columns minus `agent_name`, unique index on `number`) and
    `gleepglorp_notes_counter` `(1, next_number)`.
  - Notes prompt text: `db/_notes.py` `render_notes_block(notes, *, tools=True)`
    ~:116 (duck-types `.number/.text/.untrusted`), `NOTES_HEADING` ~:25,
    `NOTES_HEADING_TOOL_FREE` ~:34; `RenderedNote` in `agent/config.py` ~:30.
  - Taint: `TRUSTED_TOOL_NAMES` (`agent/taint.py` ~:33). **`get_app_guide` must
    join it** (shipped text), or every note saved after a guide lookup is
    flagged. `fetch_url`, `web_search` and `read_app_config` stay untrusted.
  - Web tools: `FetchUrlTool` (`tools/web.py` ~:244, `WebConfig`),
    `WebSearchTool` (~:479, `WebSearchConfig`); built in `tools/builtins.py`
    (~:195-255) with the search backend from `build_search_backend`
    (`_search_backends.py` ~:541-579; keyless DuckDuckGo by default; keyed
    engines searxng (`searxng_base_url`), google_pse (`google_pse_api_key` +
    `google_pse_cse_id`), brave (`brave_api_key`), tavily (`tavily_api_key`)
    raise `SearchUnavailableError` at call time when a field is missing).
    GleepGlorp's `enabled_tools=[]` whitelist blocks them today
    (`agent/config.py` ~:175-207); the app-wide `disabled_names` still applies.
  - Notes UI: `areas/studio/notes-section.js` `buildOrigin` ~:57, `buildRow`
    ~:177 (not exported), Clear all via `App.confirmDialog` ~:333;
    `App.studio.rulesNotesShared` (`rules-notes-shared.js` ~:212, delete button
    ~:199 with `App.ui.confirm`); `App.ui.noteFlag` (`ui/feedback.js` ~:197).
    Load order puts them before `gleepglorp-page.js` (`index.html` ~:129-130,
    ~:172).
  - Prompts page: `/api/info` (`app.py` ~:3209-3255); `renderPromptsPage`
    (`areas/admin/system-page.js` ~:171-251: `promptBlock` ~:87, `promptLayer`
    ~:104, platform blocks ~:118-136, intro ~:192); testids in
    `docs/ui-testid-registry.md` ~:75-83; pins in
    `tests/test_prompt_layers.py` ~:479, `tests/test_aiat.py` ~:111,
    `tests/browser/test_flow_admin_settings_nav.py` ~:240-335,
    `tests/browser/test_flow_admin_encryption_page.py` ~:271-312.
  - Packaging: `pyproject.toml` ~:206 package-data; the three specs'
    `collect_data_files("the_one", includes=[...])`
    (`packaging/linux/the-one.spec` ~:63-67, `packaging/macos/the-one.spec`
    ~:81-85, `packaging/windows/the-one.spec` ~:156-204); the pattern test
    `tests/test_chart_image.py` ~:96.
  - Routes: no product-side Python route list; `router.js` `SECTIONS` ~:85-103
    (Library: providers, knowledge, mcp, connectors, secrets with `~new`;
    Settings: gleepglorp, appearance, date-and-time, prompts, encryption,
    tools[/{name}], knowledge-indexing); agent tabs general, rules-and-notes,
    knowledge, tools, routines, self-configuration
    (`studio/agent-editor.js` ~:42-49); aliases that redirect: bare
    `#library/{group}`, `#settings`, `#settings/general…`, `#agents/{n}/mcps…`,
    bare `#chats/~new`, legacy `#chat`/`#studio`/`#admin`
    (`router.js` resolve ~:275-375). `tests/test_settings_pages_static.py`
    parses `settings-pages.js` and the router `SECTIONS`.
  - Links: the platform prompt's wording "write links as [text](url)"
    (`platform_prompt.py` ~:140); `reply_has_markdown_link` in
    `evals/checks.py` ~:298.

## Inputs
- Legs 3-5 landed. **This leg starts only after Leg 5 has landed** (both touch
  the GleepGlorp build and its allowlist test).

## Outputs
- `the_one/gleepglorp/notes.py`: `GleepGlorpNoteRepository`.
- Notes tools with an injectable repository; GleepGlorp's notes behind `memory`.
- `GET /api/gleepglorp/notes`, `DELETE /api/gleepglorp/notes/{id}`,
  `DELETE /api/gleepglorp/notes`; the Memory section on the Settings page.
- Web tools behind `web_access`; `web_search_available` in `GET /api/gleepglorp`
  and the Settings page hint.
- `the_one/gleepglorp/guide/*.md`, `the_one/gleepglorp/guide_tool.py`
  (`get_app_guide`), the drift test, package data in `pyproject.toml` and the
  three specs, and a packaging test.
- The shipped prompt in `the_one/gleepglorp/prompt.py` (replacing the
  placeholder), `/api/info` `gleepglorp_prompt`, and the Prompts block.
- Tests and docs.

## Acceptance Criteria

**Memory**
- [ ] With `memory` on, GleepGlorp has `save_note`, `update_note` and
      `forget_note` (the existing notes tools, same names and schemas), backed
      by `GleepGlorpNoteRepository` (the `gleepglorp_notes` table and its
      counter), with the same rules as agent notes: dedup, the per-note and
      4000-char total limits, the per-turn write counter, numbers that only go
      up, and the untrusted flag and sources from `compute_taint`. With
      `memory` off it has none of them, and a call raises
      `NotesDisabledError`'s message. No agent's notes table is touched.
- [ ] GleepGlorp's prompt carries the notes layer (`render_notes_block`,
      tool-capable and tool-free variants) after the shipped prompt and before
      the date line, only when `memory` is on.
- [ ] `get_app_guide` is in `TRUSTED_TOOL_NAMES`; a note saved after only a
      guide lookup is not flagged, and one saved after `fetch_url`,
      `web_search` or `read_app_config` is.
- [ ] `GET /api/gleepglorp/notes` returns `{enabled, notes:[...], limits,
      usage}` in the agent notes route's shape (no `agent_name`, no pending);
      `DELETE /api/gleepglorp/notes/{id}` (404 on unknown) and
      `DELETE /api/gleepglorp/notes` (`{deleted}`) work; all three are behind
      the credential gate and classified in `tests/test_api_name_rule.py`.
- [ ] The Settings page's Memory section (board screen 1): the eyebrow
      "Memory" with a Clear all action, the notes list (text, time, origin link
      to the chat, the warning flag for an untrusted note, a delete button with
      the armed confirm), "No saved notes yet." when empty, and a hint when
      memory is off ("Memory is off. GleepGlorp keeps no new notes; these stay
      until you delete them."). Delete and Clear all act at once (not part of
      Save); Clear all asks through `App.confirmDialog`. Note text is set with
      `textContent` only. Testids: `gleepglorp-memory-list`,
      `gleepglorp-memory-row`, `gleepglorp-memory-delete`,
      `gleepglorp-memory-clear`. Row pieces are shared with the agent Notes tab
      by exporting `buildRow`/`buildOrigin` (or a slimmer shared builder), not
      copied.

**Web**
- [ ] With `web_access` on, GleepGlorp has `fetch_url`, and `web_search` unless
      the configured engine is a keyed one with a required field empty; each
      is also absent when switched off for the whole app. With `web_access` off
      it has neither. They run under the operator's existing `WebConfig` /
      `WebSearchConfig` limits.
- [ ] `GET /api/gleepglorp` gains `web_search_available` (false only for a keyed
      engine with a required field empty); the Settings page shows under the
      Web access switch "Web search isn't set up, so GleepGlorp can only read
      pages you give it." with a link to `#settings/tools/web_search` when it
      is false and web access is on.

**The guide**
- [ ] `the_one/gleepglorp/guide/` holds one markdown file per topic, each
      starting with `# Title` and a one-sentence summary paragraph, written as
      plain help text for a person (second person, sentence case, no internal
      names, no code paths), and accurate to the app as it is in this branch.
      Topics at least: `overview` (the four destinations and what lives where),
      `agents`, `agent-tools` (built-in tools, overrides, MCP and knowledge
      attachments), `rules-and-notes`, `routines`, `self-configuration`,
      `mcp-servers` (local command vs HTTP, arguments, headers and environment
      variables, sign-in, per-agent credentials, Test), `model-providers`
      (types, the two Claude plan sign-ins, Ollama and pulling models),
      `knowledge-bases`, `connectors`, `secrets` (`{{secret:key}}`, allowed
      tools, grants), `settings` (each Settings page), `gleepglorp` (what it
      can and cannot do). Each topic is at most about 600 words.
- [ ] `get_app_guide(topic)` returns the topic's text; an unknown or empty topic
      returns the topic list with each summary. The topic ids are in the tool
      description. No network, no write.
- [ ] The drift test fails when a guide link (`](#…)`) names a route that the
      router does not serve or an alias that redirects (bare `#library/{group}`,
      bare `#settings`, `#settings/general…`, `#agents/{n}/mcps…`, bare
      `#chats/~new`, legacy hashes), a Settings section missing from
      `settings-pages.js`, a Library group missing from the router `SECTIONS`,
      an agent tab not in the editor's tab list, or a topic id with no file;
      it is falsified (a planted bad link fails it).
- [ ] The guide files are package data in `pyproject.toml` and in all three
      freeze specs; a test (on the `test_chart_image.py` fonts pattern) fails if
      either is missing.

**The prompt**
- [ ] `the_one/gleepglorp/prompt.py`'s shipped prompt replaces the placeholder,
      in short sections: who GleepGlorp is; app support only (decline anything
      else in one sentence and suggest one of the operator's own agents); it
      cannot change anything (the operator makes every change; never say a
      change was made); never ask for, repeat or write a secret, and if the
      operator pastes something that looks like a key, do not repeat it and say
      where it belongs; never promise an ability it does not have; how to
      answer (the guide for how things work, `read_app_config` for what is
      configured, the web only for outside facts, and say when unsure);
      links as `[text](#route)` to routes that land on a page, with the main
      ones listed (`#settings/gleepglorp`, `#library`,
      `#library/providers/~new`, `#library/mcp/~new`,
      `#library/knowledge/~new`, `#library/connectors/~new`,
      `#library/secrets/~new`, `#agents/~new`, `#settings/tools`); and brief
      Markdown replies. A tool-free variant drops the tool instructions. The
      text is compact (target 450 tokens or fewer for the tool-capable
      variant, measured with the evals' tokenizer if available, else
      characters/4, recorded in the flight log). Every link in the prompt
      passes the guide's drift test.
- [ ] `/api/info` gains `gleepglorp_prompt` (the tool-capable prompt as
      `build_prompts` renders it, without notes, with the date line), and
      Settings › Prompts shows it first as its own block (board screen 6): an
      `h2` "GleepGlorp", the line "Applies when: a chat with GleepGlorp. It
      replaces the platform prompt; GleepGlorp gets no rules, persona or
      secrets. Its notes (when memory is on) and the date line follow it.", and
      the code block (testid `gleepglorp-prompt-content`). The intro sentence is
      adjusted so it no longer says every agent's prompt is assembled from the
      layers below. `tests/test_prompt_layers.py` ~:479 checks the new field
      against `build_prompts`.
- [ ] Other agents' prompts are unchanged: `tests/_platform_prompt_pins.py`
      and every platform-prompt test pass untouched.

**Allowlist and gate**
- [ ] The allowlist test pins GleepGlorp's registered tools for every
      combination of `memory` on/off, `web_access` on/off, search available or
      not, and `fetch_url`/`web_search`/`current_time` switched off app-wide;
      the base set is `{search_tools, current_time, read_app_config,
      get_app_guide}`.
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes under 350 s; lanes
      `settings`, `agent-tabs` (the Notes tab shares the row builder),
      `chats-transcript` and `shared` pass; static guards pass; ruff clean.
- [ ] Docs: CLAUDE.md (the GleepGlorp paragraph: memory, web, guide, prompt,
      Prompts block; and the project convention from the mission: a change to
      a page or form updates the guide in the same flight), `the_one/agents.md`
      ("GleepGlorp (M36)"), `docs/ui-testid-registry.md`, `SECURITY-MODEL.md`
      (GleepGlorp's web reads and notes are untrusted-flagged like an
      agent's), the README's GleepGlorp line if any.

## Verification Steps
- Targeted: `tests/test_gleepglorp_notes.py`, `tests/test_gleepglorp_guide.py`,
  `tests/test_gleepglorp_build.py`, `tests/test_gleepglorp_settings.py`,
  `tests/test_prompt_layers.py`, `tests/test_notes_tools.py` (or the existing
  notes tool test file), the packaging test.
- `THE_ONE_TEST_NETNS=1 make test-unit`; the named lanes with
  `THE_ONE_TEST_NETNS=1`.
- Falsify: the notes repository's switch (memory off still saves), the taint
  trust of `get_app_guide`, the drift test, the packaging test, the web
  whitelist.
- Manual on a scratch instance with the mock provider and a scripted
  `tool_calls` response that calls `get_app_guide` and `save_note`: the note
  appears in the Memory section; record in the flight log.

## Implementation Guidance
1. **Notes repository.** `the_one/gleepglorp/notes.py`
   `GleepGlorpNoteRepository(conn)` with the methods the tools and the routes
   use (`create`, `update_by_agent`, `forget_by_agent`, `list_for_agent`,
   `delete`, `clear`, `total_chars`, `get`, `get_by_number`), the `name`
   argument accepted and ignored (or asserted equal to `GleepGlorp`), the same
   exceptions, `_switch_state` reading `settings.memory` and the counter row,
   rows built with `agent_name="GleepGlorp"`. Share the pure helpers
   (`validate_note_text`, `dedup_key`, `notes_total_limit_error`,
   `_merge_sources`) by importing them; extract the shared write logic from
   `AgentNoteRepository` into a base or helpers only if it stays small and the
   agent notes tests pass unchanged.
2. **Tools.** Make `_NotesToolBase._repo()` an instance method that returns
   `GleepGlorpNoteRepository` when `self._agent_name == GLEEPGLORP_AGENT_NAME`
   and `AgentNoteRepository` otherwise (or a repo factory passed by the
   provider). `NotesToolProvider` builds tools for GleepGlorp when its config's
   `notes_enabled` is true. `build.py` sets `notes_enabled=settings.memory`;
   the factory's GleepGlorp assertion goes.
3. **Prompt layer.** `build_prompts` loads the GleepGlorp notes when memory is
   on and passes `render_notes_block([...], tools=...)` between the prompt and
   the date line, for both variants.
4. **Taint.** Add `get_app_guide` to `TRUSTED_TOOL_NAMES` with a comment.
5. **Routes and Memory UI.** The three routes beside `GET`/`PUT
   /api/gleepglorp`. Export the row builder from `notes-section.js`; build the
   Memory section in `gleepglorp-page.js` with it (no Edit button, delete
   only), reloading after a delete or clear and on a `gleepglorp_changed` push.
6. **Web.** In `build.py`, `enabled_tools` is `["fetch_url", "web_search"]`
   when `web_access`, else `[]` (`current_time` stays exempt); drop
   `web_search` when the engine is keyed and incomplete (one small function
   `search_configured(tool_configs)` shared with the settings response's
   `web_search_available`). The app-wide switch still removes either.
7. **Guide.** Write the topic files by reading the app (CLAUDE.md, the UI
   modules and the routes) for accuracy; plain help text. `guide_tool.py`
   `GetAppGuideTool` loads the files with `importlib.resources`; register it
   in the GleepGlorp branch. Add the package data (pyproject and the three
   specs) and the packaging test. The drift test reads the router's `SECTIONS`
   and `settings-pages.js` the way `tests/test_settings_pages_static.py` does
   and the agent tab list from `studio/agent-editor.js`.
8. **Prompt.** Replace the placeholder with the shipped text (section
   constants, so Leg 7 can measure and tune one at a time); measure and record
   its size. Add `gleepglorp_prompt` to `/api/info` and the Prompts block.
9. **Docs** as the AC.

## Edge Cases
- **Memory turned off with notes stored**: they stay, shown with the hint, and
  are not in the prompt.
- **A note's origin chat deleted**: "(chat deleted)", as on the agent tab.
- **`fetch_url` switched off app-wide but web access on**: GleepGlorp has
  `web_search` only (if available); the Settings hint is unaffected.
- **Search keyed but incomplete and web access on**: `fetch_url` only, and the
  hint shows.
- **An unknown guide topic** like `"MCP"`: returns the list; matching is by
  exact id, case-insensitive.
- **The prompt in the tool-free variant**: no tool names in it.

## Files Affected
- New: `the_one/gleepglorp/notes.py`, `the_one/gleepglorp/guide_tool.py`,
  `the_one/gleepglorp/guide/*.md`, `tests/test_gleepglorp_notes.py`,
  `tests/test_gleepglorp_guide.py`, a packaging test (or an addition to an
  existing packaging test).
- Changed: `the_one/notes/tools.py`, `the_one/notes/tool_provider.py`,
  `the_one/agent/taint.py`, `the_one/agent/factory.py`,
  `the_one/gleepglorp/{build,prompt,settings}.py`,
  `the_one/interfaces/web/api.py` (notes routes, `web_search_available`),
  `the_one/interfaces/web/app.py` (`/api/info`),
  `static/js/areas/admin/gleepglorp-page.js`,
  `static/js/areas/studio/notes-section.js` (export),
  `static/js/areas/admin/system-page.js`, `pyproject.toml`, the three
  `packaging/*/the-one.spec`, the pinned tests, docs.

## Citation Audit
From a read-only survey of the tree with Legs 3-4 landed and Leg 5 in progress;
re-locate by symbol, and re-check `factory.py`/`build.py`/the allowlist test
after Leg 5 lands (it edits them).
- `notes/tools.py` ~:62, ~:112-117, ~:166, ~:198, ~:230 - verified (survey)
- `notes/tool_provider.py` ~:25-34 - verified (survey)
- `db/repositories.py` `AgentNoteRepository` ~:2361-2664 - verified (survey)
- `db/schema.py` v53 ~:3393-3421 - verified (survey)
- `db/_notes.py` ~:25, ~:34, ~:116; `agent/config.py` ~:30 - verified (survey)
- `agent/taint.py` ~:33 `TRUSTED_TOOL_NAMES` - verified (FD and survey)
- `tools/web.py` ~:244, ~:479; `tools/builtins.py` ~:195-255; `_search_backends.py` ~:541-579; `_web_search_config.py` ~:78, ~:156 - verified (survey)
- `agent/config.py` ~:175-207 whitelist - verified (survey)
- `factory.py` ~:522-529, ~:729-735; `gleepglorp/build.py` ~:23; `gleepglorp/prompt.py` ~:16 - verified (survey; Leg 5 may shift)
- `app.py` `/api/info` ~:3209-3255; `system-page.js` ~:87, ~:104, ~:118-136, ~:171-251 - verified (survey)
- `pyproject.toml` ~:206; specs as listed; `tests/test_chart_image.py` ~:96 - verified (survey)
- `router.js` `SECTIONS` ~:85-103, resolve ~:275-375; `studio/agent-editor.js` ~:42-49 - verified (survey)
