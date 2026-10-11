# Leg: current-time-tool-server

**Status**: completed
**Flight**: [Agents Know the Time](../flight.md)

## Objective

Every agent gets a `current_time` built-in tool, visible from its first turn and
exempt from the trimmed `enabled_tools` list. Every agent build and every
self-revision settle appends a date line as the last prompt layer. The line
names the tool only when the agent has it and its model can call tools. This
leg is server-side only; leg 2b does the client mirrors and the UI.

## Context

- Read [flight.md](../flight.md):
  - **DD1:** the tool;
  - **DD4:** the date layer;
  - **DD5:** `time_tool_available`;
  - **DD6:** the server half of the exemption, plus the **`whitelistExempt`
    field and Time row in `tool-categories.js`**, which belong to this leg;
  - **DD7:** only the `tool-categories.js` Time row, needed for
    `tests/test_tool_categories.py`. Tokens, badges and CSS are leg 2b.
- **Built on leg 1.** See the flight log's leg 1 entry for the as-built names.
  This leg uses:
  - `the_one/time_zones.py`: `CURRENT_TIME_TOOL_NAME`, `EffectiveZone`,
    `utcnow`, `load_effective_zone`, `is_known_zone`, `resolve`,
    `TimeZoneSetting`, `tool_lines`, `date_line`, `render_date_line`;
  - the `frozen_clock` fixture in `tests/conftest.py`.

  If an as-built name differs from the leg 1 artifact, use the as-built name
  and note it.
- **Out of scope for this leg:**
  - the badge tokens and CSS;
  - the three JS sites (drawer, Tools tab, studio save);
  - the Prompts page;
  - browser tests;
  - docs beyond `agents.md`'s server contracts.

  Leg 2b does these. Browser tests that enumerate categories will be stale
  until 2b. That is expected, because the flight commits once at the end.
  Do not "fix" them here.

## Inputs

- Leg 1 landed (uncommitted on the branch): `time_zones.py`, the routes, the
  doctor gate, the `frozen_clock` fixture.
- `the_one/tools/builtins.py::_TOOL_CLASSES` has 22 entries.
- `factory.py`'s seed tuple loop (~522-531) and `build_system_prompt` call
  (~542).
- `pending.py::apply_pending_revision` (~77-125).

## Outputs

- `the_one/tools/time_tool.py` (new): `CurrentTimeTool`, re-exporting
  `CURRENT_TIME_TOOL_NAME`.
- `the_one/tools/builtins.py`: the import, plus the entry appended last.
- `the_one/agent/config.py`:
  - `WHITELIST_EXEMPT_TOOLS`;
  - `is_tool_enabled` updated, with its docstring;
  - `compose_system_prompt(..., date_line=None)`.
- `the_one/agent/prompt_layers.py`: `time_tool_available` (async), and
  `build_system_prompt(..., tool_available=False, now=None)`.
- `the_one/agent/factory.py`: the seed tuple gains the tool, and it passes
  `tool_available`.
- `the_one/self_configuration/pending.py`: it passes `tool_available`.
- `the_one/db/_notes.py`: the `parse_notes_block` docstring.
- `the_one/interfaces/web/static/js/tool-categories.js`:
  - the Time row: `{ id: 'time', label: 'Time', tools: ['current_time'] }`,
    appended last;
  - a frozen `whitelistExempt: ['current_time']` field on `App.toolCategories`,
    with the header comment updated.
- **Tests:**
  - `tests/test_time_tool.py` (new);
  - `tests/test_prompt_layers.py`, `tests/test_config.py`,
    `tests/test_factory.py`, `tests/test_self_configuration_write.py`,
    `tests/test_connectors_inbound.py`, `tests/test_builtins.py`,
    `tests/test_search_tools.py`, `tests/test_tool_categories.py`,
    `tests/test_connector_routes.py`, the notes tests, and whatever else
    `make test-unit` turns up.
- `the_one/agents.md`: a "current_time and the date layer (M28)" section (the
  exemption, the seeding, the date layer, the two callers, the 2-second cap).
- The flight log: the leg entry.

## Acceptance Criteria

**The tool**

- [ ] **AC1.** `CurrentTimeTool` exists with these properties:
  - `name == "current_time"`;
  - a description that says it returns the current date, time and UTC offset
    in the operator's time zone, or in an optional named zone;
  - `parameters` = `{"type": "object", "properties": {"zone": {"type":
    "string", "description": "Optional IANA time zone name, e.g. Asia/Tokyo.
    Omit for the operator's time zone."}}, "required": []}`;
  - the default `_EmptyConfig`;
  - a constructor `__init__(self, config=None, cross_configs=None,
    agent_name=None, *, now=None, zone_source=None)` that calls `super()`.
  - `execute(self, zone: str | None = None, **kwargs)` is `async`. When `now`
    or `zone_source` is None, it looks up `time_zones.utcnow` and
    `time_zones.load_effective_zone` **at call time**.
- [ ] **AC2.** Output, under `frozen_clock` (2026-10-10T22:45:12Z) with the
      operator zone `America/Los_Angeles`:
  - `execute()`, `execute(zone=None)`, `execute(zone="")` and
    `execute(zone="America/Los_Angeles")` all return exactly
    `"\n".join(tool_lines(now, la))`.
  - `execute(zone="Asia/Tokyo")` returns:
    - Tokyo's two lines;
    - an empty line;
    - `Operator's time zone:`;
    - LA's two lines.

    Joined with `\n`, it is asserted exactly.
  - `execute(zone="US/Pacific")` (an alias) succeeds. Its block is labelled
    `US/Pacific`, because the label is the requested key, and the operator
    block follows (the keys differ).
  - `execute(zone="Mars/Olympus_Mons")` raises `ValueError` with exactly
    `Unknown time zone 'Mars/Olympus_Mons'. Use an IANA name such as Asia/Tokyo or Europe/Paris.`
    The echoed value is truncated to 64 characters.
  - `execute(zone="localtime")` and a non-string `zone` (`5`) raise the same
    kind of error. A non-string is echoed as `<invalid>`.
  - With an unnamed system zone, `EffectiveZone(None, timezone.utc)`, the
    label reads `(system time zone, UTC+00:00)`.
- [ ] **AC3.** Through the agent loop, a raised `ValueError` becomes a tool
      result with `is_error` True. `core.py:~630` wraps it as `"[error] Tool
      execution failed: <msg>"`, so assert with `in`/`endswith`, never
      equality, in the style `tests/test_notes_tools.py` uses (`r.is_error and
      "…" in r.content`). Use the existing `FakeLLM` agent-loop pattern. The
      64-character echo cap keeps the message short under the governor.
- [ ] **AC4.** `_TOOL_CLASSES` gains `"current_time": CurrentTimeTool`
      **last**. Both `BuiltinToolProvider.get_tools()` paths return 23 tools.
      The ordering-is-policy assertion still holds.
  - `tests/test_builtins.py:~54` (comment), `64`, `68`, `72` and `123` are
    updated: 22 → 23, and `current_time` added to any name list.
  - Check `tests/test_tools_test_button_assets.py` and any per-tool table
    (tool editor, test button, `tool_configs` seeding) for a row the new tool
    needs. `tests/test_api_tool_configs.py` adapts through
    `len(_TOOL_CLASSES)`.

**Exemption and seeding**

- [ ] **AC5.** `config.py` gains `WHITELIST_EXEMPT_TOOLS:
      frozenset[str] = frozenset({CURRENT_TIME_TOOL_NAME})`, imported from
      `the_one.time_zones`. `is_tool_enabled(name)` returns:
  - True for `current_time` with `enabled_tools=["read_file"]`;
  - True with `enabled_tools=[]`;
  - False with `disabled_tools=["current_time"]`, whatever the whitelist.

  Other names are unchanged. The `is_tool_enabled` docstring and the comment
  above `UNGATED_TOOL_PREFIXES` state the exemption, and that an empty
  whitelist no longer blocks *every* built-in. `tests/test_config.py` covers
  the three cases. `tests/test_connector_routes.py:~434`'s wording or assertion
  is corrected if it claims an empty whitelist blocks all built-ins.
- [ ] **AC6.** In `factory.py`, `CURRENT_TIME_TOOL_NAME` joins the seed tuple
      beside `SEND_TO_PLATFORM_CHANNEL_TOOL_NAME` and
      `FIND_PLATFORM_DESTINATION_TOOL_NAME`, seeded only if registered. Factory
      tests show:
  - a default agent's `_loaded_schemas` includes `current_time` before any
    search (`tests/test_factory.py:~1143`: 2 → 3, and the dedup test still
    finds each seeded name exactly once);
  - an agent with `enabled_tools=["read_file"]` has `current_time` in its
    registry and its seed;
  - an agent with `disabled_tools=["current_time"]` has it in neither;
  - with a `tool_configs` row `current_time` `enabled=False`, it is in neither.
- [ ] **AC7.** `self_configuration/projection.py`'s tool list
      (`describe_my_capabilities`) includes `current_time` for a trimmed agent,
      and excludes it when disabled. That follows from `is_tool_enabled` with no
      code change; a test proves it.
- [ ] **AC8.** `tests/test_search_tools.py:~960` and any other `search_tools`
      count or name assertion are updated for the new registry member.
  - **Expected** (design review): `SearchTools` still lists a seeded tool as a
    match, so the string becomes `Found 3 tools:`, with `current_time` in the
    `built-in:` list.
  - `loaded_names == {"read_file", "write_file"}` still holds, because
    `_on_search_match` dedupes against the seed.
  - Verify with a run.

**The date layer**

- [ ] **AC9.** `compose_system_prompt(base, persona, *, rules=(), notes=None,
      date_line=None)`:
  - with `date_line=None`, the output is byte-identical to today. Every
    existing composer test passes unmodified.
  - with `date_line="X"`, the output is the previous output plus
    `"\n\n---\n\nX"`.
  - the result always starts with `base`.
- [ ] **AC10.** `prompt_layers.time_tool_available(registry, llm) -> bool`
      (`async def`):
  - returns False without calling `llm.supports_tools` when
    `CURRENT_TIME_TOOL_NAME not in registry.tool_names`;
  - returns the awaited value of `asyncio.wait_for(llm.supports_tools(),
    timeout=2.0)` otherwise;
  - returns **True** on `asyncio.TimeoutError` or any other exception **from
    the provider call** (including `llm` being None, an `AttributeError`). This
    fails open, like the loop does;
  - returns **False** when `registry` is None, or when reading
    `registry.tool_names` raises (FD decision: a broken registry means the tool
    is absent);
  - wraps the whole body, so the helper never raises;
  - reads `SUPPORTS_TOOLS_TIMEOUT_S` (a module global) at call time, so a
    monkeypatch takes effect.

  Tests use small hand-written fakes, no mock libraries:
  - an LLM whose `supports_tools` returns False;
  - one that raises;
  - one that `await asyncio.sleep(10)`s. Patch the timeout to 0.05 through a
    module constant `SUPPORTS_TOOLS_TIMEOUT_S = 2.0` so the test is fast.
  - one that counts calls, for the tool-absent case: 0 calls.
- [ ] **AC11.** `build_system_prompt(agent_name, persona, *, conn=None,
      tool_available=False, now=None)` composes:
  - base, persona, rules, notes as today;
  - plus `date_line=time_zones.date_line(now or time_zones.utcnow(), await
    time_zones.load_effective_zone(conn), tool_available=tool_available)`.

  Any exception while building the date line is logged at WARNING with
  `exc_info=True`, and the layer is omitted. Rules and notes are still applied.
  Tests (`tests/test_prompt_layers.py`) under `frozen_clock`:
  - the layer is last;
  - the with-tool and without-tool wordings are asserted exactly;
  - a setting stored as `Asia/Kolkata` changes the date line's date and zone;
  - a forced failure (monkeypatch `time_zones.load_effective_zone` to raise)
    leaves a prompt with rules and no date layer, plus a warning in `caplog`;
  - the notes block is still parsed correctly by `parse_notes_block` when the
    date layer follows it.
- [ ] **AC12.** `AgentFactory.create` calls
      `time_tool_available(registry, llm)` after the seed blocks and passes
      `tool_available=` to `build_system_prompt`. Tests:
  - a default agent's `system_prompt` ends with the with-tool date line;
  - an agent with `disabled_tools=["current_time"]` ends with the without-tool
    line, and `"current_time"` does not appear anywhere in its prompt;
  - an agent whose provider's `supports_tools()` returns False ends with the
    without-tool line. Use the factory test pattern of patching `get_provider`
    to a fake whose `supports_tools` is False.
  - on that same chat-only agent, `agent._build_degraded_messages()[0].content`
    (the request the model actually gets, `core.py:~433-465`) contains the
    without-tool date line, and does not contain `current_time`.
- [ ] **AC13.** `apply_pending_revision` computes
      `tool_available = await time_tool_available(getattr(agent, "tools", None),
      getattr(agent, "llm", None))` **before and outside** its existing `try`,
      and passes it to `build_system_prompt`.
  - That call sits in its own small `try/except Exception`, which sets
    `tool_available = False`, so nothing on this line can break the turn about
    to send `done`.
  - A missing `.llm` with a registry that holds the tool counts as True
    (AC10's provider fail-open). A missing registry counts as False. The rules-failure
      fallback stays `compose_system_prompt(BASE_PROMPT, persona)`, with no
      date line, as documented. Tests:
  - `tests/test_self_configuration_write.py::_StubAgent` gains `self.tools =
    ToolRegistry()` (empty, so the tool is absent) and its `_LLMShim` an
    `async def supports_tools(self): return True`;
  - the `_NEW` expectation (~524) becomes the composed prompt plus the
    without-tool date line under `frozen_clock`;
  - every `_NEW` assertion (~535-611, ~695) and ~447-456, 636-638 and 675 are
    updated deterministically;
  - one new test: a stub whose registry holds `current_time` keeps the
    with-tool wording after a settle.

  `tests/test_app_websocket_pause_resume.py::StubAgent` is updated likewise
  only if any of its tests reaches `apply_pending_revision` with a pending
  entry.
- [ ] **AC14.** `tests/test_connectors_inbound.py:~600` and every other
      whole-prompt assertion that now sees the date layer are updated
      deterministically (`frozen_clock`), never weakened to "contains".
  - Triage each of these files, which carry prompt or `messages[0]`
    assertions:
    - `tests/test_telegram_plugin.py` (`_system_prompt()` helper ~130, which
      builds `compose_system_prompt(BASE_PROMPT, persona)`);
    - `tests/test_telegram_api.py`, `tests/test_agent_rename.py`,
      `tests/test_web_session_reaper.py`, `tests/test_session_lifecycle.py`;
    - `tests/test_ws_storage_edge_shim_visibility.py`;
    - `tests/test_agent_degraded_injection.py` (about 10 hits; expect changes);
    - `tests/test_self_configuration_api.py`.

    List the outcome per file in the flight log: changed, or unaffected
    because it only checks `startswith`/`contains`.
      Exception: an assertion whose intent is only "starts with base" or
      "contains the rules" may stay as it is.
- [ ] **AC15.** `the_one/db/_notes.py::parse_notes_block`'s docstring no longer
      claims notes are the final layer, and a regression test covers it (see
      AC11).

**The client table (data only)**

- [ ] **AC16.** In `static/js/tool-categories.js`:
  - the TABLE gains `{ id: 'time', label: 'Time', tools: ['current_time'] }`
    last;
  - `App.toolCategories` gains `whitelistExempt: Object.freeze(['current_time'])`;
  - the header comment documents both.
  - `tests/test_tool_categories.py`:
    - its `_TOOL_CLASSES` parity still passes;
    - `test_categories_and_labels_in_tab_order` includes Time last;
    - a new test parses `whitelistExempt` from the file and asserts it equals
      `sorted(WHITELIST_EXEMPT_TOOLS)`.
  - The static guards pass: `tests/test_ui_guards.py`,
    `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`.

**Gate and docs**

- [ ] **AC17.** `make test-unit` is green, with the expected skip count. Ruff
      check and format are clean.
- [ ] **AC18.** `the_one/agents.md` gains the "current_time and the date layer
      (M28)" section, covering:
  - the tool contract and output;
  - `WHITELIST_EXEMPT_TOOLS`, plus the note that the client mirrors are leg 2b;
  - seeding;
  - the date layer's position and wordings;
  - the two callers of `time_tool_available` and its fail-open 2-second cap;
  - the settle fallback being date-free.

  The existing "Rules and prompt composition (M27 F1)" text that says notes are
  the last layer is updated.

## Verification Steps

- **AC1-AC3:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_time_tool.py -x --timeout 30`.
- **AC4-AC8:** `… tests/test_builtins.py tests/test_config.py tests/test_factory.py tests/test_search_tools.py tests/test_self_configuration_projection*.py tests/test_connector_routes.py -x --timeout 60`.
  Find the projection test file with `ls tests | grep projection`.
- **AC9-AC15:** `… tests/test_prompt_layers.py tests/test_self_configuration_write.py tests/test_connectors_inbound.py tests/test_notes*.py tests/test_agent_degraded_injection.py -x --timeout 60`.
- **AC16:** `… tests/test_tool_categories.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x --timeout 60`.
- **AC17:** `make test-unit` (run in the background, wait for it), then ruff.
- **AC18:** read the diff.

## Implementation Guidance

1. **The tool module.** Use the cheap `time_zones` imports. It is a leaf, so
   there is no cycle. When `zone` is given and non-empty:
   - validate it with `time_zones.is_known_zone`, then build
     `EffectiveZone(zone, ZoneInfo(zone))`;
   - append the operator block only when the requested key differs from the
     operator key.
2. **`builtins.py`:** append it last, with a comment in the style of the
   existing end-of-dict comments (M28 F1, empty Config).
3. **`config.py`:** add the constant beside `UNGATED_TOOL_PREFIXES`, and change
   the gate to `is_ungated = tool_name.startswith(UNGATED_TOOL_PREFIXES) or
   tool_name in WHITELIST_EXEMPT_TOOLS`. Check `the_one.time_zones` imports
   nothing from `the_one.agent` (leg 1's AC20 test).
4. **`compose_system_prompt`:** add the keyword and append last.
5. **`prompt_layers.py`:**
   - add `SUPPORTS_TOOLS_TIMEOUT_S`, `time_tool_available`, and the
     `build_system_prompt` keywords;
   - import `asyncio`;
   - build the date line in its own `try`;
   - import `time_zones` lazily inside the function, or at module top level
     (it is a leaf; either works).
6. **The factory:** add to the seed tuple, then compute `tool_available` just
   before step 3.
7. **`pending.py`:** compute `tool_available` before the `try`.
8. **Existing tests:**
   - run `make test-unit` early to find every break, then fix each
     deterministically with `frozen_clock`;
   - a shared helper in `tests/conftest.py`, `expected_date_layer(tool_available:
     bool) -> str` computed under the fixture's clock and zone, keeps the edits
     small;
   - list every file you edited in the flight log.
9. **`tool-categories.js`** (ES5 style, as the file is): add the row and the
   frozen field.
10. **`agents.md`** last.

## Edge Cases

- **An agent with `enabled_tools=[]`** now has exactly one built-in,
  `current_time`, plus `search_tools`. That is intended (DD6); assert it once.
- **`search_tools` results:** `current_time` is already loaded by the seed.
  Check whether `SearchTools` lists already-loaded tools in its "Found N"
  count. Update the expectation to match the real behaviour, and note it.
- **The degraded chat-only path:** the factory computes `tool_available=False`
  when `supports_tools()` is False, so the suffix after `BASE_PROMPT` carries
  the tool-free wording. `tests/test_agent_degraded_injection.py` may assert
  the degraded system message; update it with `frozen_clock`.
- **Positional recovery is handled upstream.** `Tool.bind_positional_args`
  (`base.py:~126`) binds `__positional_args__` onto declared parameters before
  dispatch, so `current_time("Asia/Tokyo")` becomes `zone="Asia/Tokyo"`.
  `**kwargs` is only a safety net. Add no special handling.
- **The tests must not be tautological.** `expected_date_layer` builds its
  string through the real `time_zones.date_line`, but at least one test
  asserts a hard-coded literal date line.
- **The comment at `tests/test_connector_routes.py:~434`** changes ("all
  built-ins" becomes "all built-ins but current_time"). Its assertion still
  holds: it concerns the send tool. No assertion change is needed.

## Files Affected

- `the_one/tools/time_tool.py`: new.
- `the_one/tools/builtins.py`, `the_one/agent/config.py`,
  `the_one/agent/prompt_layers.py`, `the_one/agent/factory.py`,
  `the_one/self_configuration/pending.py`, `the_one/db/_notes.py`.
- `the_one/interfaces/web/static/js/tool-categories.js`.
- `the_one/agents.md`.
- `tests/test_time_tool.py` (new), `tests/conftest.py` (the
  `expected_date_layer` helper), and the existing tests listed under Outputs.
- The flight log.

## Citation Audit

Checked at `afa7855` plus leg 1 (uncommitted):

- `factory.py`: seed tuple ~522-531, `build_system_prompt` ~542, imports of
  the connector tool names at 18-19.
- `pending.py::apply_pending_revision`: 77, `try` at ~105, fallback ~114.
- `tests/test_self_configuration_write.py`: `_StubAgent` 462, `_LLMShim` 480,
  `_NEW` 524.
- `tests/test_factory.py`: ~1143, `assert len(agent._loaded_schemas) == 2`.
- `tests/test_search_tools.py`: ~960, "Found 2 tools:".
- `base.py::Tool.__init__`: 81, `(config, cross_configs, agent_name)`.
- `filesystem.py::ListDirTool.execute`: `**kwargs` pattern, 433.

All present.

---

## Post-Completion

Completion steps are Flight Control protocol, driven by the execution
workflow. They are not repeated here.
