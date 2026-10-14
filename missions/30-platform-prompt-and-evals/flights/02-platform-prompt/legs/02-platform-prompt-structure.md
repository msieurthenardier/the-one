# Leg: platform-prompt-structure

**Status**: planning
**Flight**: [The platform prompt](../flight.md)

## Objective
Replace the fixed `BASE_PROMPT`/`CHAT_ONLY_PROMPT` with a sectioned, capability-conditioned platform prompt. Do it in two steps: first a byte-identical restructure, then the conditions switched on.
- Build both the tool-capable and the tool-free system prompts at build time.
- Seed the connector tools only for agents a connector uses.
- Show each section and its condition on Settings › Prompts.

No wording is tuned in this leg; leg 2 does that.

## Context
- Flight DD1, DD2, DD3, DD7, DD8 and DD10 are authoritative; read them in `../flight.md`.
- Leg 1a (`evals-readiness`) made `evals/tokens.py::extract_parts` structural, with a section hook defaulting to one `platform` part. This leg plugs `platform_prompt`'s section ids into that hook.
- **Two steps, in order:**
  1. **Byte-identical.** `platform_prompt` holds today's text split verbatim into sections, all conditions effectively true for an all-on tool-capable agent. Tests pin that `render_platform(all-on caps)` equals today's `BASE_PROMPT` and that the tool-free render equals today's `CHAT_ONLY_PROMPT`. Pin them **before** deleting the old constants; keep the old strings as test-local literals copied from `the_one/agent/config.py` at this leg's base commit. Those literals are not captured model output, so they are not golden files.
  2. **Conditions on, then DD7.** Run the second tiktoken verification (`measure-prompt` reproduces `m30-today`'s sizes) **after step 1 and before DD7**. Then switch the conditions on (DD3) and the connector seeding on (DD7).
- The KB mentions sit inside today's "Tool discovery" bullets, so splitting them into a `knowledge` section is a wording change. Keep it minimal and log it as such. Leg 2 owns real rewording.
- Everything that reads the pending notes must keep working: the `<saved_notes>` block, the `[n]` line format, `NOTES_EMPTY_TEXT`, and the "Rules take precedence over saved notes" coupling.

## Inputs
- Leg 1a landed, uncommitted, on `flight/02-platform-prompt`.
- Product code as of `085c15d` plus the Flight 2 planning commits.

## Outputs
- `the_one/agent/platform_prompt.py` (new): `Capabilities`, `Section`, `SECTIONS`, `render_platform`, plus `sections_for(caps)` for UI and evals use.
- `the_one/agent/config.py`: `BASE_PROMPT` and `CHAT_ONLY_PROMPT` removed. `compose_system_prompt` unchanged in shape: it takes the rendered platform text as `base`.
- `the_one/agent/prompt_layers.py`: `build_system_prompt(..., knowledge, time_tool, exec_tools, ...) -> SystemPrompts(tool_capable, tool_free)`. The rules and notes rendering take `Capabilities`; the tool-free notes layer never mentions calling `update_note`/`forget_note`.
- `the_one/agent/core.py`: `Agent` gains `degraded_system_prompt: str | None`, and `_build_degraded_messages` uses it, with no prefix logic.
- `the_one/agent/factory.py`: computes the capabilities, passes both prompts, and does connector-conditional seeding through `connector_bindings`.
- `the_one/self_configuration/pending.py`: the main path and the fallback rebuild both prompts from the live agent's registry capabilities.
- `the_one/db/repositories.py`: a module-level `connector_bindings(conn)` and `agent_names_in_use(conn)`. `ConnectorDirectoryRepository.search` is refactored to use them, and bad rows are skipped and logged.
- `the_one/db/_notes.py`, `_rules.py`: render functions take `Capabilities` (or a `tools` flag). Headings are unchanged in wording except to remove tool calls from the tool-free notes layer.
- `the_one/interfaces/web/app.py` `/api/info`: `platform_sections` (and a tool-free entry) replaces `base_prompt`.
- `the_one/interfaces/web/static/js/areas/admin/system-page.js`: one block per section with "Applies when …", DOM APIs only. The intro copy is updated.
- `evals/tokens.py`: the section hook is wired to `platform_prompt.sections_for`.
- Tests: every listed consumer is updated, plus new tests. `docs/ui-testid-registry.md` is updated.
- Docs: `the_one/agents.md` gets a "Platform prompt" section, and the CLAUDE.md "Settings › Prompts" paragraph is updated.

## Acceptance Criteria
- [ ] **Byte-identical step.** Tests pin `render_platform(Capabilities(all true))` == the old `BASE_PROMPT` literal and the tool-free render == the old `CHAT_ONLY_PROMPT` literal. They pass at the byte-identical step, are recorded in the flight log, and are then deliberately updated when the conditions switch on.
- [ ] **Second tiktoken verification.** At the byte-identical step, before DD7, `make eval ARGS="measure-prompt"` reproduces `m30-today`'s sizes (595 / 862 / 84; 1308 / 1789 / 84). The output is in the flight log.
- [ ] **Old constants gone.** No reference to `BASE_PROMPT` or `CHAT_ONLY_PROMPT` remains in `the_one/`, `tests/`, `evals/` or `scripts/`: `grep -rn "BASE_PROMPT\|CHAT_ONLY_PROMPT"` returns only historical prose in `missions/`/`squawks/`.
- [ ] **Two prompts per agent (DD2).**
  - The factory builds both prompts.
  - `Agent._build_degraded_messages` sends `degraded_system_prompt` when `supports_tools()` is False.
  - With the attribute absent (an `Agent` constructed directly), it falls back to `system_prompt` verbatim.
  - Tests cover: a tool-free model with KB, notes and rules on (no tool guidance, no `current_time` wording, no `update_note`/`forget_note` mention, the persona, rules and notes present), and a tool-capable model.
- [ ] **Conditions (DD3).** Tests cover a matrix of capabilities: none, each alone, all.
  - A bare agent's prompt contains no knowledge, notes or rules guidance.
  - The `execution` section appears only when `shell` or `python_exec` is registered.
  - The `knowledge` section appears only when a `kb__` tool is registered after filtering. A disabled KB tool means no section.
- [ ] **Pending (DD2).** `pending.apply_pending_revision`'s main path and its error fallback rebuild both prompts from the live agent's registry capabilities. Tests pin the fallback no longer referencing a removed constant, and the existing self-configuration write tests pass with updated expectations.
- [ ] **Connector seeding (DD7).**
  - `connector_bindings(conn)` returns `{connector_id: {agent names}}`, and a row whose config fails to parse is skipped with a log line.
  - `ConnectorDirectoryRepository.search` behaves identically (existing tests pass).
  - An agent named as `default_agent` or in a `channel_map` gets `send_to_platform_channel`/`find_platform_destination` in its starting schemas. An unmapped agent does not, but can still find them through `search_tools`. Tests cover both.
  - The inbound connector path's existing tests pass.
- [ ] **Settings › Prompts (DD8).**
  - `/api/info` returns `platform_sections: [{id, title, applies_when, text}]` covering both variants, and no longer returns `base_prompt`. The existing rules, notes and date examples still render through the real functions.
  - `renderPromptsPage` renders one titled block per section with its "Applies when …" line, built with DOM APIs.
  - `docs/ui-testid-registry.md` retires `base-prompt-content` and lists the new testids.
  - Updated: `tests/test_prompt_layers.py`'s `/api/info` assertions, `tests/test_aiat.py`'s key check, and the browser test `tests/browser/test_flow_admin_settings_nav.py::test_general_pages_each_render_their_own_block`.
  - The static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`) pass.
  - `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane settings` passes.
- [ ] **Evals section hook.** `evals/tokens.py` attributes platform parts by section id, and `measure-prompt` prints per-section parts. Leg 1a's freeze test still passes; the scoring modules are unchanged.
- [ ] **Docs.** `the_one/agents.md` has a "Platform prompt" section (structure, capabilities, the two variants, where each consumer reads it), and the CLAUDE.md Settings › Prompts paragraph matches the new page.
- [ ] **Regression checks.**
  - `make test-unit` passes (expected 12 skips).
  - The `settings` browser lane passes under `THE_ONE_TEST_NETNS=1`.
  - Ruff is clean on `the_one/ tests/ scripts/ evals/`.
  - `make eval ARGS="measure-prompt"` after the switch is recorded in the flight log; the sizes are expected to shrink.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_prompt_layers.py tests/test_config.py tests/test_agent_degraded_injection.py tests/test_self_configuration_write.py tests/test_connectors_inbound.py tests/test_factory.py -x --timeout 60`
- `make test-unit`
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane settings -x`
- The static guards listed above.
- `make eval ARGS="measure-prompt"`, run twice: before DD7 (byte-identical) and after the switch.
- `grep -rn "BASE_PROMPT\|CHAT_ONLY_PROMPT" the_one tests evals scripts`

## Implementation Guidance
1. **Write `platform_prompt.py`** with today's text split verbatim:
   - `core` (two variants by `tools`)
   - `tools` (the Tool discovery, Tool use minus the box bullet, and Turn semantics blocks)
   - `execution` (the box / `host_access` bullet)
   - `closing` (the persona-append sentence)
   - the tool-free core text from `CHAT_ONLY_PROMPT`

   Make sure joining the applicable sections reproduces the original whitespace exactly; that is what the byte-identical tests are for. KB mentions inside the discovery bullets stay in `tools` at step 1. At step 2, move them to a `knowledge` section (`tools and knowledge`), with minimal wording change, logged.
2. **Change `build_system_prompt`'s signature** and update both callers. In the factory, compute:
   - `knowledge` = any registered tool name starting with `kb__`
   - `exec_tools` = `shell` or `python_exec` in `registry.tool_names`
   - `time_tool` = the existing `time_tool_available`
3. **Give `Agent.__init__`** an optional `degraded_system_prompt`. Keep `system_prompt` as the tool-capable text (persisted as `messages[0]`, as today).
4. **`connector_bindings`** follows the parse logic of the existing inline scan in `ConnectorDirectoryRepository.search` (`default_agent` plus `channel_map` values), wrapped in try/except per row.
5. **UI.** Follow the existing `system-page.js` DOM-building style and the "Settings item pages" conventions in CLAUDE.md. The page keeps one `h1`; sections are `h2`/`h3` like today's layer titles.
6. **Run the order exactly as the Context describes,** and record each step in the flight log.

## Edge Cases
- **An agent attached to a KB whose tool is disabled** (`disabled_tools`) gets no `knowledge` section.
- **An agent whose model's `supports_tools()` times out at build.** `time_tool` is False; both prompts are still built, and the per-turn choice decides.
- **A connector row with an invalid JSON config** is skipped; `create()` still succeeds.
- **The `"default"` synthesized agent** (no stored row) works and is unmapped unless a connector names it.

## Files Affected
- `the_one/agent/platform_prompt.py` (new), `config.py`, `prompt_layers.py`, `core.py`, `factory.py`
- `the_one/self_configuration/pending.py`
- `the_one/db/repositories.py`, `the_one/db/_notes.py`, `the_one/db/_rules.py`
- `the_one/interfaces/web/app.py`, `the_one/interfaces/web/static/js/areas/admin/system-page.js` (and CSS if needed)
- `evals/tokens.py`
- Tests: `test_config.py`, `test_prompt_layers.py`, `test_agent_degraded_injection.py`, `test_self_configuration_write.py`, `test_connectors_inbound.py`, `test_governor.py`, `test_agent_redundant_backstop.py`, `test_factory.py`, `test_agent_search_integration.py`, `test_notes_tools.py`, `test_evals_tokens.py`, `test_evals_harness.py`, `test_aiat.py`, `tests/browser/test_flow_admin_settings_nav.py`, plus new tests
- `docs/ui-testid-registry.md`, `the_one/agents.md`, `CLAUDE.md`

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
From the Flight 2 code interrogation and the Architect's two cycles (2026-10-14):
- `core.py::Agent._build_degraded_messages` uses `startswith(BASE_PROMPT)`.
- `pending.py` falls back to `compose_system_prompt(BASE_PROMPT, …)`.
- `app.py` `/api/info` returns `base_prompt`.
- The factory seeds the connector pair and `current_time`.
- `ConnectorDirectoryRepository.search` scans inline.
- `system-page.js::renderPromptsPage` renders five `<pre>` blocks.
- The browser test checks five blocks.
- `tests/test_notes_tools.py` counts `(unverified)` occurrences in the heading.

Line numbers are deliberately omitted; re-locate them by symbol.
