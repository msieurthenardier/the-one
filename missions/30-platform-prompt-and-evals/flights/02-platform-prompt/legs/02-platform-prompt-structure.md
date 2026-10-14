# Leg: platform-prompt-structure

**Status**: completed
**Flight**: [The platform prompt](../flight.md)

## Objective
Replace the fixed `BASE_PROMPT`/`CHAT_ONLY_PROMPT` constants with a sectioned platform prompt whose rendered output is **byte-identical** to today's for both variants. Also:
- build both the tool-capable and the tool-free system prompts at build time, with no prefix recovery
- migrate every consumer
- prove with tiktoken that the evals still measure today's sizes

No condition is switched on and no wording changes in this leg. That is leg 1c (`conditions-and-ui`).

## Context
- Flight DD1, DD2 and DD10 are authoritative. Leg 1a has landed:
  - `evals/tokens.py::extract_parts` is structural, with a hook `platform_sections: Callable[[str], list[tuple[str, str]]]` that defaults to a single `platform` part.
  - The freeze test pins the scoring modules and `evals/measure/`.
  - The five-configuration prompt fingerprint is `259f0a1e…`.
- **The design review settled the following.** Each point refines DD1.
  - **Section text depends on the capabilities, and joins are explicit.** A `Section` has `id`, `title`, `applies_when`, `applies(caps) -> bool` and `text(caps) -> str`. Sections are concatenated **with no separator inserted by the renderer**: each section's text carries its own leading whitespace. That is what lets the box / `host_access` bullet sit mid-way through the "Tool use:" block.
  - **The `tools` text is split around that bullet:** `tools_discovery_and_use_head` (through Tool use bullet 2), then `execution` (the box bullet with its single leading `\n`), then `tools_use_tail` (from "On failure" through Turn semantics). Names are the Developer's choice.
  - **KB phrases are not a section.** They sit mid-bullet in Tool discovery bullet 2 ("AND search tools for any knowledge bases…", `kb:<name>: …`, "internal docs"). In this leg they stay inside the tools text verbatim. Leg 1c makes them conditional fragments of that text (`caps.knowledge`) and registers `knowledge` as an informational row for the UI.
  - **Trailing newline.** `BASE_PROMPT` and `CHAT_ONLY_PROMPT` each end in `"\n"`. The `closing` section carries that final newline. The byte-identical tests compare against literals copied **exactly**, trailing newline included.
  - **`build_system_prompt` keeps its `str` return** (the tool-capable prompt), so direct test callers are untouched. A new `build_system_prompts(...) -> SystemPrompts(tool_capable, tool_free)` is what the factory and `pending` call. Both take the new keyword arguments `knowledge`, `time_tool` and `exec_tools`, all defaulting to today's effective behaviour.
  - **One helper derives the capabilities.** `capabilities_from_registry(registry, *, notes, rules, time_tool)` lives in `platform_prompt.py` and is used by both the factory and `pending`. A `None` registry gives all-False tool capabilities.
  - **`pending` must also set `agent.degraded_system_prompt`.** Today it sets `system_prompt` and `messages[0]` only.
- No captured model output is committed. The byte-identical literals are copies of source constants, not golden files.

## Inputs
- Leg 1a landed, uncommitted. Product code as of `085c15d`.

## Outputs
- `the_one/agent/platform_prompt.py` (new):
  - `Capabilities`: a frozen dataclass with `tools, knowledge, notes, rules, time_tool, exec_tools` and an `all_on()` classmethod
  - `Section`
  - `SECTIONS`
  - `render_platform(caps)`
  - `render_tool_free(caps)` (or `render_platform` with `tools=False`, `time_tool=False`)
  - `sections_for(caps) -> list[tuple[id, text]]`
  - `capabilities_from_registry(...)`
- `the_one/agent/config.py`: `BASE_PROMPT` and `CHAT_ONLY_PROMPT` removed.
- `the_one/agent/prompt_layers.py`: `build_system_prompts` and `SystemPrompts`. `build_system_prompt` becomes a thin wrapper.
- `the_one/agent/core.py`: `Agent(..., degraded_system_prompt: str | None = None)`. `_build_degraded_messages` returns it when set, else `system_prompt` verbatim, with no `startswith`. Stale comments are updated.
- `the_one/agent/factory.py`: builds both prompts through `build_system_prompts` and passes `degraded_system_prompt`. Seeding is unchanged in this leg.
- `the_one/self_configuration/pending.py`: the main path and the fallback build both prompts from `capabilities_from_registry(agent.tools, …)` and set `system_prompt`, `messages[0]` and `degraded_system_prompt`.
- `the_one/interfaces/web/app.py` `/api/info`: **unchanged in shape this leg.** It keeps returning `base_prompt`, now `render_platform(Capabilities.all_on())`, so the UI and its tests are untouched until leg 1c.
- `evals/tokens.py`: the `platform_sections` hook is wired to `platform_prompt.sections_for` for the platform layer; the tool-free layer uses the tool-free sections. **The category totals must stay identical.**
- Tests: every consumer migrated (list below) plus new tests.
- Docs: `evals/README.md` stops naming the removed constants. `evals/measure/tool-free.toml` is **frozen** (DD12) and is not edited; its comment's mention of `CHAT_ONLY_PROMPT` stays as history. `the_one/agents.md`'s references (around lines 858, 862, 879, 916, 1641 and 2504) are updated to describe `platform_prompt` and the two built prompts.

## Acceptance Criteria
- [x] **Byte-identical renders.** Tests pin `render_platform(Capabilities.all_on())` == the exact old `BASE_PROMPT` literal (trailing newline included), and the tool-free render == the exact old `CHAT_ONLY_PROMPT` literal.
- [x] **Unchanged composed prompts.** A test pins that the composed system prompt of an all-on agent (persona, rules, notes, date) is byte-identical to what `compose_system_prompt(<old BASE_PROMPT literal>, …)` produces. Another pins that its degraded prompt equals the old `CHAT_ONLY_PROMPT + rest` construction.
- [x] **`build_system_prompts`.** It returns `SystemPrompts`. The factory passes `degraded_system_prompt` to `Agent`, and `_build_degraded_messages` uses it, with no `startswith` anywhere in `core.py`. Tests:
  - a tool-free model gets the tool-free prompt
  - an `Agent` constructed directly without the attribute sends `system_prompt` verbatim
  - the existing degraded-injection tests are rewritten to the new mechanism with equivalent assertions
- [x] **`pending`.** The main path and the fallback both set `degraded_system_prompt`. A test applies a `next_turn` revision and then takes a tool-free turn, and sees the revised persona in the degraded prompt. The fallback test no longer references a removed constant.
- [x] **`capabilities_from_registry`.** Unit-tested: a `kb__` tool gives `knowledge`, `shell`/`python_exec` give `exec_tools`, and `None` gives all-False. Both the factory and `pending` use it.
- [x] **Constants gone.** `grep -rn "BASE_PROMPT\|CHAT_ONLY_PROMPT" the_one tests evals scripts` returns only the frozen comment in `evals/measure/tool-free.toml`. That covers `.py`, `.md` and `.toml`, including `the_one/agents.md` and `evals/README.md`.
- [x] **Evals measurement.** The `platform_sections` hook is wired, and `make eval ARGS="measure-prompt"` (tiktoken) still reports exactly 595 / 862 / 84 prompt sections, 1308 / 1789 / 84 platform text, and the connector variants 1308 / 1789. The per-section parts are shown. The output is pasted into the flight log as the **second one-time verification**.
- [x] **Unchanged surfaces.** The freeze test passes, and `/api/info` and Settings › Prompts are unchanged.
- [x] **Regression check.** `make test-unit` passes (expected 12 skips), and ruff is clean on `the_one/ tests/ scripts/ evals/`.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_prompt_layers.py tests/test_config.py tests/test_agent_degraded_injection.py tests/test_self_configuration_write.py tests/test_connectors_inbound.py tests/test_factory.py tests/test_evals_tokens.py tests/test_evals_harness.py -x -q --timeout 60`
- `make test-unit`
- `make eval ARGS="measure-prompt"`
- `grep -rn "BASE_PROMPT\|CHAT_ONLY_PROMPT" the_one tests evals scripts`

## Implementation Guidance
1. **Copy the two old constants into a test module as literals first.** Write the byte-identical tests, then build `platform_prompt.py` until they pass. Only then remove the constants and migrate consumers.
2. **Consumers to migrate**, found by grep:
   - `core.py`, `pending.py`, `factory.py` (through `build_system_prompts`), `app.py` (`/api/info`'s `base_prompt` value)
   - `evals/tokens.py`, `evals/README.md` (never `evals/measure/`, which is frozen)
   - Tests: `test_config.py`, `test_prompt_layers.py`, `test_agent_degraded_injection.py`, `test_self_configuration_write.py`, `test_connectors_inbound.py`, `test_governor.py`, `test_agent_redundant_backstop.py`, `test_factory.py`, `test_agent_search_integration.py`, `test_evals_tokens.py`, `test_evals_harness.py`
   - Docs: `the_one/agents.md`
3. **Keep `compose_system_prompt`'s signature unchanged.** It receives the rendered platform text as `base`.

## Edge Cases
- **A `None` registry in `pending`** (an agent in a broken state) gives all-False capabilities, and both prompts are still built.
- **An agent whose `supports_tools()` times out at build** gets `time_tool=False`, and both prompts are built.

## Files Affected
See Outputs and Guidance step 2.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked by the leg design review, 2026-10-14:
- Production `build_system_prompt` callers: `factory.py`, `pending.py`.
- `Agent(` is constructed only in `factory.py`.
- `_build_degraded_messages` is called from one site in `core.py`.
- Both constants end in `"\n"`.
- The box bullet is the third "Tool use" bullet.
- The KB phrases sit mid-bullet in Tool discovery bullet 2.
- `registry.tool_names` is a list property (`tools/base.py`).
- `tests/test_notes_tools.py` and `tests/test_prompt_layers.py` call `build_system_prompt` directly, hence the kept `str` wrapper.
