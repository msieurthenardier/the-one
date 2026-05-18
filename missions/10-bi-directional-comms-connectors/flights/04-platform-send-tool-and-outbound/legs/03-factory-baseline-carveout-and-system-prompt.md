# Leg: factory-baseline-carveout-and-system-prompt

**Status**: completed
**Flight**: [Platform-Send Built-in Tool and Outbound Routing](../flight.md)

## Objective

Wire the leg-2 platform-send tool into `AgentFactory.create()` so a connector-attached agent sees `send_to_platform_channel` in its F10 baseline-visible set (the deliberate carve-out) when the tool is operator-enabled, AND receives a system-prompt directive instructing it to use the tool (enabled state) or notifying it that platform-send is disabled (disabled state). Extract `compose_system_prompt(base, persona, *, connector_attached, send_tool_enabled) -> str` as a module-level free function in `the_one/agent/config.py` so the factory can compose the connector-aware prompt without `AgentConfig` knowing about connector state. Wire the factory's `BuiltinToolProvider.get_tools(...)` call to pass `connector_account_ids=config.connector_account_ids` via an `isinstance` branch (so non-builtin tool providers in test stubs don't break). Update the F10 baseline-strict comment in `agent/core.py` to document the platform-send tool as the second exception. Lock the new behavior with factory-level tests pinning both states + `compose_system_prompt`'s four-combination round trip.

## Context

- **Parent flight design decisions** (see `flight.md` "Design Decisions"):
  - **System-prompt composition: extract free function; factory calls it; AgentConfig keeps signature.** Non-connector callers (the WS handler at `interfaces/web/app.py`, `AgentConfig.get_system_prompt()` callers in tests) see byte-identical output. The factory builds the connector-aware prompt with the actual flags. The locked invariant: `compose_system_prompt(BASE_PROMPT, "", connector_attached=False, send_tool_enabled=False) == BASE_PROMPT` and `compose_system_prompt(BASE_PROMPT, "persona text", connector_attached=False, send_tool_enabled=False) == f"{BASE_PROMPT}\n\n---\n\npersona text"`.
  - **Auto-load mechanism for the F10 baseline carve-out via the F10 L1 shared-container pattern.** At `AgentFactory.create()`, after the tool registry is built but BEFORE `Agent(...)` is constructed, IF `config.connector_account_ids` is non-empty AND `send_to_platform_channel` is operator-enabled (`disabled_names` filter), append the tool's schema to `loaded_schemas` and its name to `loaded_tool_names`. This mutates the shared containers the Agent already holds a reference to. Mirrors the F10 L1 pattern at `factory.py:257-258` (`loaded_schemas` / `loaded_tool_names`).
  - **The two-layer enable check**: `(name not in disabled_names) and config.is_tool_enabled(name)` — the EXACT predicate the registry-build filter uses at `factory.py:301`. Operator-level (`ToolConfigRepository.enabled`) AND per-agent-level (`AgentConfig.is_tool_enabled`) must both pass for the tool to be enabled.
  - **Mid-session enable/disable note**: if the operator toggles `send_to_platform_channel` mid-turn, the cached `Session.agent` keeps the prompt that was set at the previous `factory.create()`. The new prompt applies at the NEXT `factory.create()`. This matches MCP-attachment mid-session-change semantics.

- **`BuiltinToolProvider.get_tools` signature (post-leg-2)**: `def get_tools(self, tool_configs=None, agent_overrides=None, agent_name=None, *, connector_account_ids: list[str] | None = None) -> list[Tool]:` — `connector_account_ids` is keyword-only. Verified at `the_one/tools/builtins.py` after leg 2 landed. The factory must pass this kwarg, but ONLY when the provider is the `BuiltinToolProvider` — other providers in `self.tool_providers` (e.g. test stubs at `tests/test_factory.py:48-73 StubToolProvider`) don't accept it. `isinstance` branch at the call site is the cleanest minimum-blast-radius fix; widening the `ToolProvider` Protocol would force every test stub to accept the kwarg.

- **`AgentConfig.is_tool_enabled(name)`**: `the_one/agent/config.py:99-105` — returns True iff `name` is in `enabled_tools` (if set; otherwise allow-all) AND not in `disabled_tools`. Defined on `AgentConfig` since F2.

- **`disabled_names` set in factory**: `the_one/agent/factory.py:241` — `disabled_names = {c.name for c in configs if not c.enabled}`. This is the operator-level disable, projected from `ToolConfigRepository.list()`. The carve-out check reuses this set without re-querying the DB.

- **The Agent's `_compute_visible_schemas()` is UNCHANGED by this leg.** Currently at `the_one/agent/core.py:102-111`: `return [SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas`. The carve-out is achieved by pre-populating `_loaded_schemas` at factory time (the Agent reads from the same shared list). No core.py code change beyond the documentation comment.

- **F10 baseline assertion location** (`the_one/agent/core.py:30-34`): comment block reading "F10 L1: strict baseline (§2). search_tools is the ONLY non-`continue` schema visible to the LLM at session start. Additional schemas are added to the model-visible set as a side effect of calling search_tools. F10 follow-up: search_tools and search_mcps were merged into a single tool ...". This leg appends a sentence documenting the platform-send tool as the second exception.

- **The existing `test_baseline_visible_at_session_start` test** at `tests/test_agent_search_integration.py:102-124`: constructs `Agent(...)` directly (not via `factory.create()`) with empty `loaded_schemas` and asserts the baseline is exactly `["search_tools", "continue"]`. This non-connector path stays byte-identical — leg 3 ONLY adds a comment pointing to the F4 carve-out. The factory-level tests for the carve-out live in `tests/test_factory.py` (new test class).

- **Existing `get_system_prompt` tests** at `tests/test_config.py:182-191`: assert `cfg.get_system_prompt() == BASE_PROMPT` for empty persona and `cfg.get_system_prompt() == BASE_PROMPT + "\n\n---\n\nCustom prompt."` for non-empty. Both MUST continue to pass byte-identically after leg 3 refactors `get_system_prompt` to delegate to `compose_system_prompt`.

- **Existing `BASE_PROMPT` exposure surface** at `the_one/interfaces/web/app.py:1070 — "return {\"version\": __version__, \"base_prompt\": BASE_PROMPT}"`: unaffected. The new `compose_system_prompt` function is only called by `AgentConfig.get_system_prompt()` (back-compat) and `AgentFactory.create()` (new). The `/version` endpoint returns the bare `BASE_PROMPT` constant.

- **Factory's test fixture** (`tests/test_factory.py:94-126 factory fixture`): uses `StubToolProvider` (a non-`BuiltinToolProvider`). Existing tests pass `connector_account_ids=[]` implicitly via the default-empty-list on `AgentConfig`. To exercise the carve-out, new tests in this leg must construct AgentConfig with `connector_account_ids=["acc-1"]` AND use a tool provider list that includes `BuiltinToolProvider` (so the registry has `send_to_platform_channel` to fetch the schema from).

- **`BuiltinToolProvider`'s import in tests**: `tests/test_builtins.py` already imports it. For test_factory.py to construct a `BuiltinToolProvider`-using factory, follow the existing `BuiltinToolProvider()` instantiation pattern.

## Inputs

State that must exist before this leg runs:

- F4 branch `flight/04-platform-send-tool-and-outbound`; leg 1 + leg 2 uncommitted work in place.
- `the_one/agent/config.py:AgentConfig` has `connector_account_ids: list[str] = Field(default_factory=list)` (leg 1 output).
- `the_one/tools/builtins.py:_TOOL_CLASSES` contains `"send_to_platform_channel": SendToPlatformChannelTool` (leg 2 output).
- `the_one/tools/builtins.py:BuiltinToolProvider.get_tools` accepts the keyword-only `connector_account_ids: list[str] | None = None` kwarg (leg 2 output).
- `the_one/tools/connector_send.py:SendToPlatformChannelTool` is the platform-send tool class (leg 2 output).
- `the_one/agent/config.py:9 — "BASE_PROMPT = ..."` — extant module-level constant.
- `the_one/agent/config.py:109-113 (get_system_prompt)` — extant 4-line method on AgentConfig.
- `the_one/agent/config.py:99-105 (is_tool_enabled)` — extant filter method.
- `the_one/agent/factory.py:241 — "disabled_names = {c.name for c in configs if not c.enabled}"` — extant operator-disable projection.
- `the_one/agent/factory.py:257-258 — "loaded_schemas: list[dict] = []\nloaded_tool_names: set[str] = set()"` — extant F10 L1 shared containers.
- `the_one/agent/factory.py:299-302 (built-in tool loop)` — extant; this leg modifies the call site to branch on `isinstance(provider, BuiltinToolProvider)`.
- `the_one/agent/factory.py:316 — "system_prompt = config.get_system_prompt()"` — extant; this leg replaces with the connector-aware `compose_system_prompt(...)` call.
- `the_one/agent/factory.py:321-328 (Agent(...) construction)` — extant.
- `the_one/agent/core.py:30-34 (F10 baseline strict comment block)` — extant; this leg appends a sentence.
- `the_one/agent/core.py:102-111 (_compute_visible_schemas)` — extant; UNCHANGED by this leg.
- `tests/test_agent_search_integration.py:102-124 (test_baseline_visible_at_session_start)` — extant; this leg adds a documenting comment.
- `tests/test_config.py:182-191 (TestGetSystemPrompt)` — extant; tests must still pass byte-identically.
- `tests/test_factory.py:94-126 (factory fixture)` — extant; the carve-out tests follow this mocking pattern.

## Outputs

State that must exist after this leg completes:

- `the_one/agent/config.py` gains:
  - Two new module-level string constants for the directives:
    - `_CONNECTOR_TOOL_ENABLED_DIRECTIVE` — instructs the agent to call `send_to_platform_channel` to reach peers.
    - `_CONNECTOR_TOOL_DISABLED_DIRECTIVE` — informs the agent that platform-send is operator-disabled and replies stay local.
  - A new module-level function `compose_system_prompt(base, persona, *, connector_attached=False, send_tool_enabled=False) -> str` that composes `base` + optional connector-aware directive + optional persona. Non-connector path is byte-identical to today's `get_system_prompt` output.
  - `AgentConfig.get_system_prompt()` simplified to delegate to `compose_system_prompt(BASE_PROMPT, self.system_prompt, connector_attached=False, send_tool_enabled=False)`. Existing tests pass byte-identically.
- `the_one/agent/factory.py:AgentFactory.create()`:
  - Replaces the `provider.get_tools(...)` loop at L299-302 with an `isinstance`-branched call that passes `connector_account_ids=config.connector_account_ids` to `BuiltinToolProvider` only.
  - Computes `connector_attached = bool(config.connector_account_ids)` BEFORE the registry-build filter loop.
  - Computes `send_tool_enabled` using the SAME predicate the registry-build filter uses: `"send_to_platform_channel" not in disabled_names and config.is_tool_enabled("send_to_platform_channel")`.
  - AFTER the registry-build for-loop (i.e. after the BuiltinToolProvider and MCP tool loops finish), IF `connector_attached AND send_tool_enabled` AND `"send_to_platform_channel"` is registered in `registry` (defensive check; covers test-fixture scenarios where the tool_providers list doesn't include BuiltinToolProvider): append the tool's `to_schema()` result to `loaded_schemas` and its name to `loaded_tool_names`.
  - Replaces `system_prompt = config.get_system_prompt()` at L316 with `system_prompt = compose_system_prompt(BASE_PROMPT, config.system_prompt, connector_attached=connector_attached, send_tool_enabled=send_tool_enabled)`. Add `BASE_PROMPT` + `compose_system_prompt` imports at the top of the file.
- `the_one/agent/core.py` lines 30-34: append a sentence to the comment block documenting `send_to_platform_channel` as the second documented exception to the strict baseline: "F4 (M10) carve-out: `send_to_platform_channel` is pre-loaded into the visible set at `AgentFactory.create()` time when the agent has connector accounts attached AND the operator has the tool enabled — the deliberate exception so connector-attached agents don't need to `search_tools` for it. See `agent/factory.py` for the carve-out site and `agent/config.py:compose_system_prompt` for the paired prompt directive."
- `tests/test_agent_search_integration.py:102-124`: add a one-line `# F4 (M10) note: ...` comment before `test_baseline_visible_at_session_start`'s assertion at L124 pointing to the new tests at `tests/test_factory.py` and `tests/test_config.py`. No assertion change — non-connector baseline is preserved byte-identically.
- `tests/test_config.py` gains:
  - `TestComposeSystemPrompt` class with 5 round-trip tests covering all (connector × tool-enabled) combinations plus the persona+directive ordering shape:
    - `test_non_connector_no_persona_returns_base_only` — asserts byte-identical to `BASE_PROMPT`.
    - `test_non_connector_with_persona_returns_base_separator_persona` — asserts byte-identical to `BASE_PROMPT + "\n\n---\n\npersona"`.
    - `test_connector_attached_tool_enabled_includes_enabled_directive` — asserts BASE_PROMPT is present, enabled-directive substring is present, disabled-directive substring is ABSENT.
    - `test_connector_attached_tool_disabled_includes_disabled_directive` — asserts BASE_PROMPT is present, disabled-directive substring is present, enabled-directive substring is ABSENT.
    - `test_connector_attached_with_persona_persona_after_directive` — asserts the shape `BASE_PROMPT < directive < "---" < persona` and the result ends with the persona.
  - Existing `TestGetSystemPrompt` tests at L182-191 continue to pass byte-identically (no changes to those tests).
- `tests/test_factory.py` gains:
  - `TestConnectorBaselineCarveOut` class with 4 tests using a factory configured with `BuiltinToolProvider`:
    - `test_carveout_loads_send_tool_when_attached_and_enabled` — agent with `connector_account_ids=["acc-1"]`, tool operator-enabled, no per-agent disable → `agent._loaded_schemas` contains exactly one entry with name `"send_to_platform_channel"`; `agent._loaded_tool_names == {"send_to_platform_channel"}`.
    - `test_no_carveout_when_no_connector_accounts` — agent with `connector_account_ids=[]`, tool operator-enabled → `agent._loaded_schemas == []`. Non-connector baseline preserved.
    - `test_no_carveout_when_tool_operator_disabled` — agent with `connector_account_ids=["acc-1"]`, tool operator-disabled (via `ToolConfig(name="send_to_platform_channel", enabled=False)`) → `agent._loaded_schemas == []`. The disabled directive lives in the system prompt; the tool is not in the registry.
    - `test_no_carveout_when_tool_per_agent_disabled` — agent with `connector_account_ids=["acc-1"]`, tool operator-enabled, `disabled_tools=["send_to_platform_channel"]` → `agent._loaded_schemas == []`. Same shape as operator-disabled.
  - `TestConnectorSystemPrompt` class with 3 tests:
    - `test_non_connector_uses_base_prompt` — agent with `connector_account_ids=[]` → `agent.system_prompt == BASE_PROMPT` (no persona).
    - `test_connector_attached_tool_enabled_includes_enabled_directive` — `agent.system_prompt` contains the enabled-directive substring.
    - `test_connector_attached_tool_disabled_includes_disabled_directive` — `agent.system_prompt` contains the disabled-directive substring (operator disabled the tool).
  - `TestFactoryToolProviderWiring` class with 1 test:
    - `test_builtin_provider_receives_connector_account_ids` — uses a wrapping mock around `BuiltinToolProvider.get_tools` to capture the kwarg, then asserts it was called with `connector_account_ids=["acc-1"]`. The `StubToolProvider` (non-builtin) in the same factory must NOT be called with the kwarg (verified via `inspect.signature` or explicit kwargs-not-included assertion).
- Flight log gains a "Leg Progress: factory-baseline-carveout-and-system-prompt" entry.
- Leg status flipped to `landed` in this file's header. Do NOT commit.

## Acceptance Criteria

- [ ] `the_one/agent/config.py` defines `_CONNECTOR_TOOL_ENABLED_DIRECTIVE` and `_CONNECTOR_TOOL_DISABLED_DIRECTIVE` as module-level string constants. Both are non-empty strings; each contains `"send_to_platform_channel"` (the tool name) so the agent has the literal reference.
- [ ] `the_one/agent/config.py:compose_system_prompt(base, persona, *, connector_attached=False, send_tool_enabled=False) -> str` exists as a module-level function.
- [ ] `compose_system_prompt(BASE_PROMPT, "", connector_attached=False, send_tool_enabled=False)` returns `BASE_PROMPT` (byte-identical).
- [ ] `compose_system_prompt(BASE_PROMPT, "Custom.", connector_attached=False, send_tool_enabled=False)` returns `f"{BASE_PROMPT}\n\n---\n\nCustom."` (byte-identical).
- [ ] `compose_system_prompt(BASE_PROMPT, "", connector_attached=True, send_tool_enabled=True)` contains `BASE_PROMPT`, contains the enabled-directive content, does NOT contain the disabled-directive content.
- [ ] `compose_system_prompt(BASE_PROMPT, "", connector_attached=True, send_tool_enabled=False)` contains `BASE_PROMPT`, contains the disabled-directive content, does NOT contain the enabled-directive content.
- [ ] With persona AND connector + tool enabled: the persona appears after the directive after a `\n\n---\n\n` separator. Shape: `f"{BASE_PROMPT}\n\n{ENABLED_DIRECTIVE}\n\n---\n\n{persona}"`.
- [ ] `AgentConfig.get_system_prompt()` delegates to `compose_system_prompt` with both connector flags = False. Existing tests `tests/test_config.py::TestGetSystemPrompt::test_empty_returns_default` and `test_custom_prompt_appended` continue to pass without modification.
- [ ] `the_one/agent/factory.py:AgentFactory.create()` computes `connector_attached = bool(config.connector_account_ids)` and `send_tool_enabled = "send_to_platform_channel" not in disabled_names and config.is_tool_enabled("send_to_platform_channel")` BEFORE the registry-build for-loop.
- [ ] The `provider.get_tools(...)` call inside the factory loops branches on `isinstance(provider, BuiltinToolProvider)`. The branch passes `connector_account_ids=config.connector_account_ids` to `BuiltinToolProvider` instances; other providers in the list are called with the existing 3-arg signature (no `connector_account_ids` kwarg).
- [ ] AFTER the registry-build for-loops (built-in + MCP), IF `connector_attached AND send_tool_enabled AND "send_to_platform_channel" in registry.tool_names`: `tool = registry.get("send_to_platform_channel"); loaded_schemas.append(tool.to_schema()); loaded_tool_names.add(tool.name)`. **Use the public `registry.tool_names` property** (verified at `the_one/tools/base.py:129-131`), NOT the private `_tools` dict.
- [ ] `agent.system_prompt` (built via the factory) uses the connector-aware composition: when `connector_account_ids` is non-empty, the prompt includes one of the two directives.
- [ ] `tests/test_factory.py::TestConnectorBaselineCarveOut::test_carveout_loads_send_tool_when_attached_and_enabled` passes: `agent._loaded_schemas` contains exactly `[<send_to_platform_channel schema>]`.
- [ ] `tests/test_factory.py::TestConnectorBaselineCarveOut::test_no_carveout_when_no_connector_accounts` passes: `agent._loaded_schemas == []`.
- [ ] `tests/test_factory.py::TestConnectorBaselineCarveOut::test_no_carveout_when_tool_operator_disabled` passes.
- [ ] `tests/test_factory.py::TestConnectorBaselineCarveOut::test_no_carveout_when_tool_per_agent_disabled` passes.
- [ ] `tests/test_factory.py::TestConnectorSystemPrompt` three tests pass.
- [ ] `tests/test_factory.py::TestFactoryToolProviderWiring::test_builtin_provider_receives_connector_account_ids` passes.
- [ ] `tests/test_config.py::TestComposeSystemPrompt` five tests pass (including `test_connector_attached_with_persona_persona_after_directive`).
- [ ] `the_one/agent/core.py:30-34` F10-baseline comment block extended with the platform-send carve-out documentation sentence.
- [ ] `tests/test_agent_search_integration.py:102-124 test_baseline_visible_at_session_start` has a `# F4 (M10) note: ...` comment pointing to the new carve-out tests in `test_factory.py` and `test_config.py`. The assertion `baseline_names == ["search_tools", "continue"]` is UNCHANGED.
- [ ] `docker exec the-one pytest tests/test_config.py tests/test_factory.py tests/test_agent_search_integration.py -x --timeout 30` passes.
- [ ] `docker exec the-one pytest -x --timeout 30` (full suite) passes. No regression on F1/F2/F3 surfaces, leg-1/leg-2 surfaces, or `test_baseline_visible_at_session_start`.
- [ ] `docker exec the-one ruff check the_one tests` clean.
- [ ] Flight log gains a "Leg Progress: factory-baseline-carveout-and-system-prompt" entry; this file's `**Status**` → `landed`.

## Verification Steps

- `docker exec the-one pytest tests/test_config.py::TestComposeSystemPrompt -v -x --timeout 30` — 4 tests pass.
- `docker exec the-one pytest tests/test_factory.py::TestConnectorBaselineCarveOut tests/test_factory.py::TestConnectorSystemPrompt tests/test_factory.py::TestFactoryToolProviderWiring -v -x --timeout 30` — 8 tests pass.
- `docker exec the-one pytest tests/test_config.py::TestGetSystemPrompt -v -x --timeout 30` — 2 existing tests still pass (byte-identical behavior).
- `docker exec the-one pytest tests/test_agent_search_integration.py::test_baseline_visible_at_session_start -v -x --timeout 30` — passes unchanged (non-connector baseline preserved).
- `docker exec the-one pytest -x --timeout 30` — full suite green.
- `docker exec the-one ruff check the_one tests` — clean.
- `grep -n "compose_system_prompt" the_one/ tests/` — at least: def in `agent/config.py`, call in `agent/factory.py`, call in `agent/config.py:get_system_prompt`, multiple test consumers.
- `grep -n "connector_account_ids" the_one/agent/factory.py` — at least 2 matches (the `connector_attached` computation and the `BuiltinToolProvider`-branch call).
- `grep -n "F4\|carve-out" the_one/agent/core.py` — at least 1 match in the comment block at L30-34 extension.

## Implementation Guidance

1. **Add the directive constants and `compose_system_prompt` to `the_one/agent/config.py`**:

   - Place the constants AFTER `BASE_PROMPT` (around line 52, after the closing `"""`) and BEFORE the `class AgentConfig(BaseModel)` declaration at line 54.
   - Place the function AFTER `BASE_PROMPT` + the constants but BEFORE the class declaration.

   ```python
   _CONNECTOR_TOOL_ENABLED_DIRECTIVE = (
       "This conversation is attached to a connector account on an external "
       "platform. Your plain-text replies in this session reach the operator "
       "only — to reply to peers on the external platform, call the "
       "`send_to_platform_channel` tool with the target (account_id, "
       "channel_id, and optional thread_id) and the content to send."
   )

   _CONNECTOR_TOOL_DISABLED_DIRECTIVE = (
       "This conversation is attached to a connector account on an external "
       "platform, but the platform-send capability is currently DISABLED by "
       "the operator. Your replies in this session reach the operator only "
       "— they do not reach the external platform. The "
       "`send_to_platform_channel` tool is not available right now. Do not "
       "claim to have sent anything to the platform."
   )


   def compose_system_prompt(
       base: str,
       persona: str,
       *,
       connector_attached: bool = False,
       send_tool_enabled: bool = False,
   ) -> str:
       """Compose the agent's system prompt.

       Mission 10 Flight 4 Leg 3. Adds a connector-aware extension point so
       agents attached to a connector account receive an explicit directive
       about how their outbound flows.

       Non-connector callers (``AgentConfig.get_system_prompt()`` for
       persistence/edit-form use; the WS handler's prompt-equivalence
       checks) pass ``connector_attached=False`` and receive byte-identical
       output to the pre-F4 ``{base}\\n\\n---\\n\\n{persona}`` shape.

       The connector-aware path inserts a directive between ``base`` and
       the persona separator:
       - ``connector_attached AND send_tool_enabled`` →
         :data:`_CONNECTOR_TOOL_ENABLED_DIRECTIVE` (instructs the agent to
         call the platform-send tool to reach peers).
       - ``connector_attached AND NOT send_tool_enabled`` →
         :data:`_CONNECTOR_TOOL_DISABLED_DIRECTIVE` (informs the agent that
         platform-send is operator-disabled and its replies stay local).
       """
       parts = [base]
       if connector_attached:
           if send_tool_enabled:
               parts.append(_CONNECTOR_TOOL_ENABLED_DIRECTIVE)
           else:
               parts.append(_CONNECTOR_TOOL_DISABLED_DIRECTIVE)
       if persona:
           parts.append("---")
           parts.append(persona)
       return "\n\n".join(parts)
   ```

2. **Simplify `AgentConfig.get_system_prompt()` at `the_one/agent/config.py:107-113`**:

   ```python
   def get_system_prompt(self) -> str:
       """Return the resolved system prompt: BASE_PROMPT, optionally
       appended with a per-agent persona via a "---" separator.

       Non-connector callers (persistence edit form, WS handler's
       prompt-equivalence checks) use this method. The factory uses
       :func:`compose_system_prompt` directly with the actual connector
       flags so its output reflects the connector state.
       """
       return compose_system_prompt(
           BASE_PROMPT,
           self.system_prompt,
           connector_attached=False,
           send_tool_enabled=False,
       )
   ```

3. **Wire `AgentFactory.create()` in `the_one/agent/factory.py`**:

   - Add the imports at the top of the file (after the existing `from the_one.agent.config import AgentConfig`):
     ```python
     from the_one.agent.config import AgentConfig, BASE_PROMPT, compose_system_prompt
     ```
   - At `factory.py:241` (after `disabled_names = ...`), compute the connector flags BEFORE the registry-build for-loop. Insert AFTER the existing `disabled_names = ...` line and the comment about session-bound freshness:
     ```python
     # F4 (M10) L3: connector carve-out flags.
     # - connector_attached: agent has at least one connector account.
     # - send_tool_enabled: the platform-send tool passes both the operator
     #   filter (not in disabled_names) AND the per-agent filter
     #   (config.is_tool_enabled). This is the SAME predicate the
     #   registry-build for-loop at L301 uses.
     # The carve-out (loading the tool's schema into the F10 baseline-
     # visible set) and the system-prompt directive both consult these
     # flags. Computed once here so the post-loop carve-out site reuses.
     connector_attached = bool(config.connector_account_ids)
     send_tool_enabled = (
         "send_to_platform_channel" not in disabled_names
         and config.is_tool_enabled("send_to_platform_channel")
     )
     ```
   - At `factory.py:299-302` (the BuiltinToolProvider loop), replace with the `isinstance`-branched call. **No new import needed** — `BuiltinToolProvider` is already imported at `factory.py:16` for the default-provider construction at L171.
     ```python
     for provider in self.tool_providers:
         if isinstance(provider, BuiltinToolProvider):
             tools = provider.get_tools(
                 tool_configs_by_name,
                 agent_overrides,
                 agent_name=name,
                 connector_account_ids=config.connector_account_ids,
             )
         else:
             # Non-builtin providers (test stubs, future provider types)
             # use the unwidened signature. Adding `connector_account_ids`
             # to the ToolProvider Protocol would force every test stub
             # to accept it; the branch keeps the change scoped.
             tools = provider.get_tools(
                 tool_configs_by_name,
                 agent_overrides,
                 agent_name=name,
             )
         for tool in tools:
             if tool.name not in disabled_names and config.is_tool_enabled(tool.name):
                 registry.register(tool)
     ```
   - At `factory.py:316`, replace `system_prompt = config.get_system_prompt()` with:
     ```python
     system_prompt = compose_system_prompt(
         BASE_PROMPT,
         config.system_prompt,
         connector_attached=connector_attached,
         send_tool_enabled=send_tool_enabled,
     )
     ```
   - AFTER the MCP tool loop (i.e. after `factory.py:313 — "registry.register(tool)"`) and BEFORE the `system_prompt = ...` assignment, insert the carve-out block:
     ```python
     # F4 (M10) L3: F10 baseline carve-out. When the agent is connector-
     # attached AND the platform-send tool is enabled (both layers), the
     # tool's schema is pre-loaded into the baseline-visible set so the
     # agent doesn't have to invoke `search_tools` to discover it. The
     # `registry.tool_names` (public @property at tools/base.py:129-131)
     # membership guard is defensive: in test scenarios where the
     # tool_providers list omits BuiltinToolProvider, the tool is absent
     # from the registry and the carve-out cannot fire — instead of
     # crashing, skip silently (the test setup is non-production).
     if connector_attached and send_tool_enabled and "send_to_platform_channel" in registry.tool_names:
         _send_tool = registry.get("send_to_platform_channel")
         loaded_schemas.append(_send_tool.to_schema())
         loaded_tool_names.add(_send_tool.name)
     ```

4. **Update the F10 baseline comment in `the_one/agent/core.py:30-34`**:

   - Existing comment (verbatim from file):
     ```python
     # F10 L1: strict baseline (§2). search_tools is the ONLY non-`continue`
     # schema visible to the LLM at session start. Additional schemas are added
     # to the model-visible set as a side effect of calling search_tools.
     # F10 follow-up: search_tools and search_mcps were merged into a single
     # tool that covers both the built-in catalog and any attached MCP servers.
     ```
   - Append after the F10-follow-up sentence:
     ```python
     # F4 (M10) carve-out: `send_to_platform_channel` is pre-loaded into the
     # visible set at AgentFactory.create() time when the agent has connector
     # accounts attached AND the operator has the tool enabled — the
     # deliberate exception so connector-attached agents don't need to
     # search_tools for it. See agent/factory.py for the carve-out site and
     # agent/config.py:compose_system_prompt for the paired prompt directive.
     ```

5. **Update `tests/test_agent_search_integration.py:102` (the `test_baseline_visible_at_session_start` function)**:

   - Add a comment above the function or at the top of the function body:
     ```python
     # NOTE (F4 M10 L3): this test pins the NON-CONNECTOR baseline
     # (search_tools + continue only). The F4 carve-out for connector-
     # attached agents (which also includes `send_to_platform_channel` in
     # the baseline-visible set) is exercised in tests/test_factory.py::
     # TestConnectorBaselineCarveOut and the prompt composition lives in
     # tests/test_config.py::TestComposeSystemPrompt.
     ```

6. **Add new tests to `tests/test_config.py`** (append after `TestBasePrompt` at line 199):

   ```python
   # ===================================================================
   # compose_system_prompt
   # ===================================================================


   class TestComposeSystemPrompt:
       """Test the F4 (M10) connector-aware system-prompt composition."""

       def test_non_connector_no_persona_returns_base_only(self):
           """Byte-identical to pre-F4 get_system_prompt with empty persona."""
           from the_one.agent.config import compose_system_prompt
           out = compose_system_prompt(BASE_PROMPT, "")
           assert out == BASE_PROMPT

       def test_non_connector_with_persona_returns_base_separator_persona(self):
           """Byte-identical to pre-F4 get_system_prompt with persona."""
           from the_one.agent.config import compose_system_prompt
           out = compose_system_prompt(BASE_PROMPT, "Custom.")
           assert out == BASE_PROMPT + "\n\n---\n\nCustom."

       def test_connector_attached_tool_enabled_includes_enabled_directive(self):
           """Enabled state: directive instructs the agent to call the tool."""
           from the_one.agent.config import (
               _CONNECTOR_TOOL_DISABLED_DIRECTIVE,
               _CONNECTOR_TOOL_ENABLED_DIRECTIVE,
               compose_system_prompt,
           )
           out = compose_system_prompt(
               BASE_PROMPT, "", connector_attached=True, send_tool_enabled=True
           )
           assert BASE_PROMPT in out
           assert _CONNECTOR_TOOL_ENABLED_DIRECTIVE in out
           assert _CONNECTOR_TOOL_DISABLED_DIRECTIVE not in out

       def test_connector_attached_tool_disabled_includes_disabled_directive(self):
           """Disabled state: directive tells the agent platform-send is off."""
           from the_one.agent.config import (
               _CONNECTOR_TOOL_DISABLED_DIRECTIVE,
               _CONNECTOR_TOOL_ENABLED_DIRECTIVE,
               compose_system_prompt,
           )
           out = compose_system_prompt(
               BASE_PROMPT, "", connector_attached=True, send_tool_enabled=False
           )
           assert BASE_PROMPT in out
           assert _CONNECTOR_TOOL_DISABLED_DIRECTIVE in out
           assert _CONNECTOR_TOOL_ENABLED_DIRECTIVE not in out

       def test_connector_attached_with_persona_persona_after_directive(self):
           """Persona appears AFTER the directive, separated by '---'."""
           from the_one.agent.config import (
               _CONNECTOR_TOOL_ENABLED_DIRECTIVE,
               compose_system_prompt,
           )
           out = compose_system_prompt(
               BASE_PROMPT,
               "Custom persona.",
               connector_attached=True,
               send_tool_enabled=True,
           )
           # Shape: base + \n\n + directive + \n\n---\n\n + persona
           assert out.index(BASE_PROMPT) < out.index(
               _CONNECTOR_TOOL_ENABLED_DIRECTIVE
           )
           assert out.index(_CONNECTOR_TOOL_ENABLED_DIRECTIVE) < out.index("---")
           assert out.endswith("Custom persona.")
   ```

7. **Add new tests to `tests/test_factory.py`** (append after the existing `TestProviderTypeMap`):

   - **Import `BuiltinToolProvider`** at the top of `tests/test_factory.py`. Verified absent from the existing import block; add: `from the_one.tools.builtins import BuiltinToolProvider`.
   - The new tests need a factory configured with `BuiltinToolProvider` to actually register the platform-send tool. The existing `factory` fixture uses `StubToolProvider` only. The new tests use a NEW module-level pytest fixture that yields the factory inside the patch context (keeps patches active during `factory.create()`).
   - The fixture must inject `ToolConfig(name="send_to_platform_channel", enabled=True|False)` into `mock_tool_repo.list()` to drive `disabled_names`. Parameterize via small fixtures per scenario.

   **Mandatory fixture shape** (the implementing agent uses this verbatim — patch-scope correctness depends on it):

   ```python
   # tests/test_factory.py — module-level fixture
   @pytest.fixture
   def factory_with_builtin_tool_configs(store: InMemoryStore):
       """Yields a factory using BuiltinToolProvider. The tool_configs
       passed to this fixture (via indirect parameterization or by
       building per-test sub-fixtures) seed `mock_tool_repo.list()`,
       which drives the factory's `disabled_names` set.

       Patches stay active for the test body because we YIELD inside the
       `with` block — matches the existing `factory` fixture pattern at
       tests/test_factory.py:115-126.
       """
       def _builder() -> AgentFactory:
           # tool_configs flow via the mock_tool_repo.list patch in _Ctx,
           # NOT through the builder — the builder just returns a fresh
           # factory wired with BuiltinToolProvider and the test's store.
           return AgentFactory(
               store=store,
               tool_providers=[BuiltinToolProvider()],
               mcp_provider=None,
           )

       mock_repo = AsyncMock()
       mock_repo.get = AsyncMock(return_value=_make_provider_config())

       def _make_with_tool_configs(tool_configs: list[ToolConfig] | None = None):
           # Return a context manager so each test can scope its own
           # tool_configs without forcing a new fixture per scenario.
           class _Ctx:
               def __enter__(self_):
                   mock_tool_repo = AsyncMock()
                   mock_tool_repo.list = AsyncMock(return_value=tool_configs or [])
                   self_._patches = [
                       patch("the_one.agent.factory.get_provider", _fake_get_provider),
                       patch("the_one.agent.factory.settings"),
                       patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
                       patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
                       patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_repo),
                       patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo),
                   ]
                   self_._active = [p.start() for p in self_._patches]
                   # settings mock setup — index 1 corresponds to the settings patch.
                   self_._active[1].agents_dir = Path("/tmp/test-agents")
                   self_._active[1].data_dir = Path("/tmp/test-data")
                   self_._active[1].ensure_dirs = lambda: None
                   return _builder()

               def __exit__(self_, *args):
                   for p in self_._patches:
                       p.stop()

           return _Ctx()

       yield _make_with_tool_configs
   ```

   Usage pattern in each test:

   ```python
   async def test_carveout_loads_send_tool_when_attached_and_enabled(
       self, factory_with_builtin_tool_configs, store: InMemoryStore
   ):
       cfg = AgentConfig(
           name="connector-agent",
           provider_config_id="test-provider",
           llm_model="stub-model",
           connector_account_ids=["acc-1"],
       )
       await store.save(cfg)
       # No ToolConfig row for send_to_platform_channel → it's not in
       # disabled_names → operator-enabled by default.
       with factory_with_builtin_tool_configs(tool_configs=[]) as factory:
           agent = await factory.create("connector-agent")
           assert "send_to_platform_channel" in agent._loaded_tool_names
           schema_names = [s["name"] for s in agent._loaded_schemas]
           assert schema_names == ["send_to_platform_channel"]
   ```

   The `_Ctx` context-manager pattern keeps `patch.start()` / `patch.stop()` symmetric and lets each test scope its own `tool_configs` cleanly. The implementing agent may simplify to per-scenario `@pytest.fixture` (one per `tool_configs` shape) if the inline context-manager feels heavy — both shapes preserve the patch-scope correctness.

8. **Run the tests**:
   - `docker exec the-one pytest tests/test_config.py::TestComposeSystemPrompt tests/test_config.py::TestGetSystemPrompt -v -x --timeout 30` — new tests pass; existing tests pass byte-identically.
   - `docker exec the-one pytest tests/test_factory.py -v -x --timeout 30` — existing factory tests + new carve-out + system-prompt + provider-wiring tests pass.
   - `docker exec the-one pytest tests/test_agent_search_integration.py::test_baseline_visible_at_session_start -v -x --timeout 30` — passes unchanged.
   - `docker exec the-one pytest -x --timeout 30` — full suite green.
   - `docker exec the-one ruff check the_one tests` — clean.

9. **Update the flight log** with a "Leg Progress: factory-baseline-carveout-and-system-prompt" entry. Capture: files modified, test count delta from leg-2 baseline (1916), any deviations, any anomalies.

10. **Flip this leg's `**Status**` to `landed`**. Do NOT commit.

## Edge Cases

- **Agent with `connector_account_ids=["acc-1"]` but the tool is BOTH operator-disabled AND per-agent-disabled**: `send_tool_enabled` is False. The disabled-directive lives in the system prompt; no schema preload. Both gating layers contribute to the False — the test exercises the operator-disabled and per-agent-disabled paths separately.

- **Agent with `connector_account_ids=["acc-1"]` but `BuiltinToolProvider` is not in `tool_providers`** (test scenario): the tool is NOT in `registry`. The defensive `"send_to_platform_channel" in registry.tool_names` guard skips the carve-out cleanly. The system prompt still gets the enabled-directive (matching the agent's `connector_attached=True` state) — but the agent has no tool to invoke; calling `send_to_platform_channel` would fail with a `KeyError` from the registry. This is a test-fixture edge case; in production the BuiltinToolProvider is always in the list (`AgentFactory.__init__` defaults to `[BuiltinToolProvider()]` at L171).

- **`AgentConfig.is_tool_enabled` returns True even when `enabled_tools` is None**: per the existing logic at `config.py:101-105`, `enabled_tools=None` means "allow all". Then `disabled_tools` is the only per-agent gate. Composes correctly with the operator gate.

- **`BASE_PROMPT` is imported at `factory.py` top**: ensure the import line doesn't introduce a circular dependency. `agent/config.py` imports from `pydantic`, not from `agent/factory.py` — no cycle. `agent/factory.py` already imports `from the_one.agent.config import AgentConfig`; widening to `from the_one.agent.config import AgentConfig, BASE_PROMPT, compose_system_prompt` is additive.

- **Existing `BASE_PROMPT` consumer at `interfaces/web/app.py:1070`**: returns the unmodified `BASE_PROMPT` constant. Unaffected — `compose_system_prompt` doesn't mutate `BASE_PROMPT`.

- **Existing `_load_config` returning a config without the `connector_account_ids` field** (pre-F4 stored agent JSON): leg 1's back-compat test confirmed the field defaults to `[]` on deserialization. `bool([])` is False → `connector_attached` is False → no carve-out, no directive. Non-connector agents are byte-identical to today.

- **`compose_system_prompt`'s back-compat assertion**: the existing `tests/test_config.py:185-191` tests assert `cfg.get_system_prompt() == BASE_PROMPT` and `cfg.get_system_prompt() == BASE_PROMPT + "\n\n---\n\nCustom prompt."`. These MUST still pass. The new `compose_system_prompt(BASE_PROMPT, "", connector_attached=False, send_tool_enabled=False)` returns `"\n\n".join([BASE_PROMPT])` which equals `BASE_PROMPT`. Verify by manual trace and by test.

- **`registry.tool_names`**: returns `list(self._tools)` per `the_one/tools/base.py:130`. The `in` check is O(n) over the list — acceptable for a registry holding ~20 tools. If performance becomes a concern (it won't), switch to `name in registry._tools` (private but O(1)).

- **MCP-attached agent that is ALSO connector-attached**: F4 doesn't change MCP behavior. Both `mcp_source_ids` and `connector_account_ids` populate independently. The MCP tool loop at `factory.py:309-313` is unchanged; the connector carve-out happens after.

- **Mid-session enable/disable**: documented in the flight log Flight Director Notes. The factory's prompt composition fires at `factory.create()`. The cached `Session.agent` keeps the prompt; the new prompt applies at the next `factory.create()`. Not a leg-3 test concern; F5 covers the WS-restore-after-edit flow.

## Files Affected

- `the_one/agent/config.py` — add `_CONNECTOR_TOOL_ENABLED_DIRECTIVE`, `_CONNECTOR_TOOL_DISABLED_DIRECTIVE`, `compose_system_prompt`; simplify `AgentConfig.get_system_prompt`
- `the_one/agent/factory.py` — compute `connector_attached` + `send_tool_enabled`; `isinstance(provider, BuiltinToolProvider)`-branched `get_tools` call; post-loop carve-out; `compose_system_prompt` invocation
- `the_one/agent/core.py` — extend F10 baseline strict comment with F4 carve-out documentation
- `tests/test_config.py` — `TestComposeSystemPrompt` class (5 tests including the persona+directive shape)
- `tests/test_factory.py` — `TestConnectorBaselineCarveOut` (4 tests), `TestConnectorSystemPrompt` (3 tests), `TestFactoryToolProviderWiring` (1 test)
- `tests/test_agent_search_integration.py:102` — add F4-carve-out comment on `test_baseline_visible_at_session_start`
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/flight-log.md` — append leg-progress entry
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/legs/03-factory-baseline-carveout-and-system-prompt.md` — flip status to `landed`

---

## Post-Completion Checklist

**Per agentic-workflow batched-review model: do NOT commit; defer to flight-end.**

- [ ] All acceptance criteria verified
- [ ] Full test suite passes (`docker exec the-one pytest -x --timeout 30`)
- [ ] Lint clean (`docker exec the-one ruff check the_one tests`)
- [ ] Update `flight-log.md` with a "Leg Progress: factory-baseline-carveout-and-system-prompt" entry
- [ ] Set this leg's `**Status**` to `landed`
- [ ] Signal `[HANDOFF:review-needed]` — do NOT commit

---

## Citation Audit

22 code-location citations verified. 2 drifted-but-repaired; remaining 20 OK.

| Citation | Status | Evidence |
|---|---|---|
| `the_one/agent/config.py:9 — "BASE_PROMPT = ..."` | OK | Verified at L9 |
| `the_one/agent/config.py:99-105 (is_tool_enabled)` | **drifted → 101-107** | `def is_tool_enabled` actually at L101; body L102-107. Symbol anchor protects against drift; line range updated below. |
| `the_one/agent/config.py:107-113 (get_system_prompt)` | **drifted → 109-114** | `def get_system_prompt` actually at L109; body L110-114. Symbol anchor protects against drift. |
| `the_one/agent/core.py:30-34 (F10 baseline strict comment block)` | OK | Verified — comment at L30-34 with the SEARCH_TOOLS_SCHEMA above at L35 |
| `the_one/agent/core.py:102-111 (_compute_visible_schemas)` | OK | Verified earlier |
| `the_one/agent/factory.py:8 (AgentConfig import)` | OK | Verified at L8 |
| `the_one/agent/factory.py:171 (BuiltinToolProvider default)` | OK | Verified at L171 — `[BuiltinToolProvider()]` |
| `the_one/agent/factory.py:241 — "disabled_names = ..."` | OK | Verified earlier (leg 2 audit) |
| `the_one/agent/factory.py:257-258 (loaded_schemas / loaded_tool_names)` | OK | Verified earlier |
| `the_one/agent/factory.py:299-302 (BuiltinToolProvider loop)` | OK | Verified earlier |
| `the_one/agent/factory.py:309-313 (MCP tool loop)` | OK | Verified earlier |
| `the_one/agent/factory.py:316 — "system_prompt = config.get_system_prompt()"` | OK | Verified at L316 |
| `the_one/agent/factory.py:321-328 (Agent(...) construction)` | OK | Verified earlier |
| `the_one/tools/builtins.py:_TOOL_CLASSES` (post-leg-2: 20 entries including send_to_platform_channel) | OK | Leg 2 just landed |
| `the_one/tools/builtins.py:BuiltinToolProvider.get_tools (post-leg-2 signature with connector_account_ids kwarg)` | OK | Leg 2 just landed |
| `the_one/tools/base.py:130 (tool_names property)` | OK | Verified at L130 — `@property def tool_names(self) -> list[str]: return list(self._tools)` |
| `the_one/interfaces/web/app.py:1070 — "base_prompt": BASE_PROMPT"` | OK | Verified earlier — `/version` endpoint returns the constant |
| `tests/test_agent_search_integration.py:102-124 (test_baseline_visible_at_session_start)` | OK | Verified earlier (leg 1 audit) |
| `tests/test_config.py:7 (BASE_PROMPT import)` | OK | Verified earlier |
| `tests/test_config.py:182-191 (TestGetSystemPrompt)` | OK | Verified earlier — 2 tests |
| `tests/test_config.py:199 (TestBasePrompt — where new TestComposeSystemPrompt appends after)` | OK | Verified earlier |
| `tests/test_factory.py:48-73 (StubToolProvider — non-builtin)` | OK | Verified earlier |
| `tests/test_factory.py:94-126 (factory fixture mocking pattern)` | OK | Verified earlier — `LLMProviderRepository` + `ToolConfigRepository` mocks |
