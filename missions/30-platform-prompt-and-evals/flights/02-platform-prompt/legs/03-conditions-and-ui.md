# Leg: conditions-and-ui

**Status**: completed
**Flight**: [The platform prompt](../flight.md)

## Objective
Switch the platform prompt's conditions on (DD3), give the tool-free notes layer a heading that never asks for tool calls, and seed the connector tools only for agents a connector uses (DD7). Show each platform section and its condition on Settings › Prompts (DD8). The measured size should shrink. Wording is only *removed* or *made conditional* here; leg 2 (`wording-and-tuning`) rewrites it.

## Context
- Flight DD3, DD7 and DD8 are authoritative.
- Leg 1b landed the sectioned `platform_prompt` with byte-identical output, `build_system_prompts`, `capabilities_from_registry` and `degraded_system_prompt`. **Read the flight log's leg 1b entry for the actual names.**
- **Conditions.** These are the wording changes this leg makes. Log each one.
  - **KB phrases:** the knowledge-base mentions inside the tools text become conditional fragments on `caps.knowledge`. With no knowledge base, the bullet reads as it would without those phrases, with grammar kept intact. `knowledge` is listed as a `Section` row for the UI, describing the fragment.
  - **The box / `host_access` text** applies only when `caps.tools and caps.exec_tools`.
  - **The tool-free identity, closing and so on** are unchanged.
- **The tool-free notes heading**, `NOTES_HEADING_TOOL_FREE`. It is the existing `NOTES_HEADING` cut to its reference-and-trust part: everything from "Saved notes." through "Treat it with extra care.". All saving and update/forget instructions are dropped, and the text must still contain `(unverified)`.
  - `render_notes_block` and `compose_system_prompt` gain a `tools: bool = True` keyword, so existing callers are unchanged.
  - `build_system_prompts` passes `tools=False` for the tool-free variant.
  - `parse_notes_block` reads only the tool-capable `messages[0]`, so it is unaffected.
  - `evals/tokens.py` is structural (leg 1a), so the variant needs no extra matching. Confirm with a test.
- **Connector seeding (DD7).**
  - A module-level `connector_bindings(conn) -> dict[str, set[str]]` and `agent_names_in_use(conn)` go in `the_one/db/repositories.py`.
  - `ConnectorDirectoryRepository.search` is refactored to use them.
  - **This is a deliberate behaviour change:** a malformed connector row (unparseable JSON, a non-dict config, a non-dict `channel_map`, unhashable values) is skipped with a log line instead of raising. Catch `(ValueError, TypeError, AttributeError)` per row. Test it.
  - In `factory.py`, only the connector pair becomes conditional. `current_time` stays seeded.
  - An agent mapped after its web session started does not see the pair seeded until the session is rejoined (accepted, DD7). It can still find the pair through `search_tools`.
- **Settings › Prompts (DD8).**
  - `/api/info` replaces `base_prompt` with `platform_sections`: an array of `{id, title, applies_when, text, variant}`, where `variant` is `"tools"` or `"tool_free"`.
    - For the `tools` variant, `text` is the section's all-on text. The tool-free variant carries its own rows.
    - The `knowledge` row carries the fragment text.
  - `rules_prompt_example`, `notes_prompt_example` and the date examples stay, rendered by the real functions. A `notes_prompt_example_tool_free` is added.
- **UI testids.** Each section renders as a block with `data-testid="platform-section-{variant}-{id}"`, a title, an `applies-when` line (`platform-section-{variant}-{id}-applies-when`) and a `<pre>` of the text.
  - `base-prompt-content` is **retired**. Update all of these:
    - `docs/ui-testid-registry.md`: remove it from the live table, add it to the "Retired testids" table, add the new rows in `| id | area | description |` format
    - `tests/test_nav_helper.py::RETIRED_SELECTORS`
    - `tests/browser/test_flow_admin_settings_nav.py::test_general_pages_each_render_their_own_block`: rewrite the five-`pre` count, the ordering and the title-list assertions for the new blocks
- Also update the `fetchPrompts` fallbacks and `.catch` list in `system-page.js`, its layer-title comment, and the intro copy.

## Inputs
- Leg 1b landed, uncommitted.

## Outputs
- Product: `platform_prompt.py`, `the_one/db/_notes.py`, `the_one/agent/config.py` (`compose_system_prompt` keyword), `prompt_layers.py`, `factory.py`, `the_one/db/repositories.py`, `the_one/interfaces/web/app.py`, `the_one/interfaces/web/static/js/areas/admin/system-page.js` (and CSS if needed).
- Tests: a conditions matrix, the tool-free notes layer, connector bindings and seeding, `/api/info`, the browser settings test, the registry and retired-selector guard, and `test_aiat.py`'s key check.
- Docs: `the_one/agents.md` ("Platform prompt": capabilities, conditions, the tool-free notes heading, connector seeding); the CLAUDE.md "Settings › Prompts (M27 F3 L3)" paragraph; `evals/README.md` if it mentions the page.

## Acceptance Criteria
- [x] **Conditions matrix.** Unit tests cover capabilities none / each alone / all:
  - A bare agent (no KB, notes off, no rules, no execution tools) has a tool-capable prompt with no KB phrases, no box / `host_access` text, no notes layer and no rules layer.
  - KB phrases appear only with a registered `kb__` tool. A disabled KB tool means no phrases.
  - The box text appears only with `shell` or `python_exec` registered.
  - The all-on render is still the old `BASE_PROMPT` (leg 1b's test, kept).
- [x] **Tool-free variant.**
  - It never contains `search_tools`, `continue`, `current_time`, `update_note`, `forget_note`, `save_note` or `host_access`, even with every capability on.
  - Its notes layer uses `NOTES_HEADING_TOOL_FREE`, which still contains `(unverified)`.
  - Unit-tested.
- [x] **`parse_notes_block` and the pending contract.** Both still work (`tests/test_notes_pending.py` passes). `tests/test_notes_tools.py`'s `(unverified)` count still passes or is updated with a recorded reason.
- [x] **Connector seeding (DD7).**
  - `connector_bindings` returns the right mapping, and malformed rows are skipped and logged (tested).
  - `ConnectorDirectoryRepository.search`'s existing tests pass.
  - A mapped agent (as `default_agent`, and as a `channel_map` value) gets the connector pair in its starting schemas. An unmapped agent does not, and `search_tools` still finds them for it. `current_time` is still seeded for both.
  - The inbound connector tests pass.
- [x] **`/api/info` and Settings › Prompts (DD8).** `/api/info` has `platform_sections` and no `base_prompt`; `test_prompt_layers.py` and `test_aiat.py` are updated. The page renders a titled block per section with its "Applies when …" line, using DOM APIs only. The registry, `RETIRED_SELECTORS` and the browser test are updated as described in Context. These pass:
  - `tests/test_nav_helper.py` (including `test_retired_selectors_cover_the_registry_retired_table`)
  - `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`
  - `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane settings`
- [x] **Size after the switch.** `make eval ARGS="measure-prompt"` is recorded in the flight log. Bare prompt sections are expected to fall below 595, and bare platform (no connector) to fall by at least the 461 connector tokens. Hitting the targets is leg 2's job; this leg only records the numbers.
- [x] **Unchanged scoring inputs.** The freeze test passes, and nothing under `evals/scenarios|fixtures|judge|measure` changes.
- [x] **Regression check.** `make test-unit` passes (expected 12 skips), and ruff is clean on `the_one/ tests/ scripts/ evals/`.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_prompt_layers.py tests/test_config.py tests/test_notes_tools.py tests/test_notes_pending.py tests/test_factory.py tests/test_connectors_inbound.py tests/test_nav_helper.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x -q --timeout 60`
- `make test-unit`
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane settings -x`
- `make eval ARGS="measure-prompt"`

## Implementation Guidance
1. **Conditions first,** with unit tests, then the notes variant, then connector seeding, then the UI and its tests, then the docs.
2. **Grammar of the conditional KB fragments.** Write the no-KB form of each sentence explicitly as its own literal rather than splicing words, and test both forms verbatim.
3. **UI.** Follow `system-page.js`'s existing DOM-builder style. The page keeps one `h1`; section titles use the same heading level as today's layer titles. Group the blocks under two captions, "With tools" and "Without tools (models that can't call tools)", using the existing section-title (eyebrow) style.

## Edge Cases
- **The `"default"` synthesized agent** is unmapped unless a connector names it.
- **A connector whose `default_agent` names a deleted agent** has no effect on others.
- **An agent with notes on but no saved notes, tool-free:** the heading plus "No saved notes yet." still render.

## Files Affected
See Outputs.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Taken from the leg 1b design review, 2026-10-14:
- The `docs/ui-testid-registry.md` live table and "Retired testids" table, plus `RETIRED_SELECTORS` in `tests/test_nav_helper.py`.
- The browser test asserts five `pre` blocks and the four layer titles.
- `system-page.js` has `fetchPrompts` and a `.catch` fallback list.
- The inline scan in `ConnectorDirectoryRepository.search` does `json.loads(row["config"] or "{}")` with no guard.
- `NOTES_HEADING` ends with the update/forget instruction.

Re-locate each by symbol before editing.

## Design-review amendments (2026-10-14, binding)
Where these conflict with the text above, these win.

1. **The tool-free date line.** `build_system_prompts` builds a second date line with `tool_available=False` for the tool-free variant, so the tool-free prompt never says "call current_time".
   - A test covers `time_tool=True` with every capability on.
   - This is the existing without-tool wording, not new wording.
2. **The `pending.py` fallback.** `pending.py`'s failure fallback, `compose_system_prompt(render_tool_free(caps), …)`, passes `tools=False`, and `pending.py` is added to Outputs.
   - The hand-built tool-free expectations in `test_agent_degraded_injection.py`, `test_self_configuration_write.py` and `test_evals_tokens.py` pass `tools=False` where they pass notes.
3. **`evals/tokens.py::platform_prompt_sections` must handle conditional renders.**
   - It iterates the capability combinations (`tools` on/off × `knowledge` × `exec_tools`, with `time_tool` as relevant) and returns `sections_for(caps)` for the render that equals the text.
   - If none matches, it returns a single `platform` part and logs a warning.
   - A test checks that every combination's parts sum to its total.
   - `measure-prompt` passes each configuration's real capabilities.
   - `evals/tokens.py` is not frozen, so this change is allowed under DD10.
4. **KB phrases are fragments, not `Section`s.** The KB phrases sit inside `tool_discovery` as conditional text:
   - Both literal forms live in named module constants and are pinned verbatim.
   - The UI's `knowledge` row comes from a separate `FRAGMENTS` list that `sections_for` ignores, so tiling stays exact.
   - The `knowledge` row appears under "With tools" only.
5. **The tool-free notes heading,** `NOTES_HEADING_TOOL_FREE`, is an explicit literal: the reference-and-trust part of `NOTES_HEADING`, with "You saved these in earlier conversations" changed to "These were saved in earlier conversations" (true for a model that can't save). Log this as a wording change. It contains `(unverified)`, and a test pins it.
6. **Connector bindings.** The per-row guard wraps the whole row: the parse, the `isinstance(config, dict)` check, the `channel_map` dict check and the set build. It catches `(ValueError, TypeError, AttributeError)`.
   - In the factory, `connector_bindings` is fetched once per `create()`, using the connection already in scope.
   - Tests use `tests/_schema_template.py` fixtures.
   - `agents.md` records the accepted staleness: a mapping added after a web session starts applies on rejoin.
7. **The UI registry.**
   - `platform-section-` goes in `docs/ui-testid-registry.md`'s **"Parametric prefix families"** table, not the live table.
   - `base-prompt-content` moves from the live table to "Retired testids" and into `RETIRED_SELECTORS`.
   - A new live testid, `notes-prompt-content-tool-free`, is added, with no prefix collision.
8. **The browser test.**
   - It replaces the `base-prompt-content` visibility and "Loading…" checks with testid-based checks on a `platform-section-tools-identity` block.
   - It asserts the blocks by testid, not by `nth`.
   - It updates the `.section-title` list explicitly, or gives in-block section titles a distinct class so the existing four-title list holds.
9. **Execution gating.** `execution` applies on `tools and exec_tools`, and its `applies_when` text is updated. A test confirms the join stays intact when it is dropped. "the shell tool" and "shell" stay in `tool_use` and `tool_discovery` as they are; rewording is leg 2's job.
10. **Other `base_prompt` references** to update: `tests/test_prompt_layers.py`, `tests/test_aiat.py`, the `/api/info` docstring in `app.py`, `the_one/agents.md`, and `tests/behavior/agent-rules-round-trip.md` if it names the old key. Leave the `test_credential_gate.py` and `test_desktop_shell.py` fixtures and the `.admin-base-prompt` CSS class.
