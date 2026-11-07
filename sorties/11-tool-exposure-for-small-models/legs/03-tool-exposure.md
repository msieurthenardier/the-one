# Leg: tool-exposure

**Status**: completed
**Flight**: [Tool exposure for small local models](../flight.md)

## Objective
When the provider reports a known context window and the agent's whole enabled toolset fits a context-relative budget, seed every enabled tool schema into the agent's starting set and give it the operator-approved "tools preloaded" wording; otherwise keep today's discovery byte-for-byte. Then measure the budget, run both eval sets, and compare against `s11-platform` and `s11-routines`.

## Context
- The design is the flight's **DD1, DD2, DD3, DD8 (the parity test), DD12, DD13 and DD14**. Read `../flight.md` first. Where this leg and the flight disagree, this leg wins and the disagreement is a defect to report.
- Charter criteria: 1 (exposure within budget; discovery otherwise), 2 (qwen3-4b at 0.9 or more on the knowledge-base and tool-use cells), 4 (planted notes still flagged).
- **Legs 1 and 2 are committed** (`05259b43`, `40446186`):
  - `the_one/agent/tool_exposure.py::ToolExposure(decided, budget, estimate, window_known, window)` with `to_dict()` exists and is unused.
  - The harness reads `getattr(agent, "tool_exposure", None)` into every record's and measurement's `exposure`.
  - The measurement records `tools_full_names` per configuration (leg 1's evals-side copy of DD1's rule).
  - `measure-prompt`'s scripted provider is pinned to window 16384, 3.5 bytes per token and `context_window_known = True` (instance attributes).
  - The baselines are `evals/baselines/s11-platform.json` and `s11-routines.json`. `tests/test_evals_freeze.py` pins the scoring files and the scenarios to them.
- **Operator decisions for this leg:**
  - The preloaded copy is **B** (signed off 2026-11-07, below).
  - `no-secrets` is judged "not worse" for `qwen3-4b` and `lfm3` (flight log, Decisions, 2026-11-07).
  - DD12's pre-declared miss is `planted-instruction` and `routines-planted-instruction` for `qwen3-4b`.
  - `fetch_channel_history` is exposed with the pair for connector-bound agents (DD1).
- **`the_one/agent/core.py` is not touched.** If the design turns out to need it, stop (`[BLOCKED:core-touch]`): that is a divert.
- **DD14, two parts in one leg:**
  - **Part A, code:** steps 1-8, landed for the Flight Director's in-leg review and commit.
  - **Part B, measurement:** steps 9-12, run only after Part A is committed, by a separate Developer spawn.

  The Developer told to do Part A stops at the end of Part A.

### The signed-off copy (DD3, option B)
- `PRELOADED_TOOL_DISCOVERY = "\nTools:\n- All your tools are available now: call them directly (`search_tools` only lists them again).\n"` (23 o200k tokens)
- `PRELOADED_KB_LINE = "- Knowledge bases are attached: search them before answering from memory on topics they cover.\n"` (17 tokens)

Today's pair, `NO_KB_TOOL_DISCOVERY` + `KB_LINE`, is 49 + 29 = 78 tokens. The new pair is 40, and each line on its own is shorter than its counterpart, so the `{config}:prompt-text` gate holds for every configuration.

Settings › Prompts rows (variant `tools`, after the existing `knowledge` fragment row):

| Row id | Title | Applies when | Text |
|---|---|---|---|
| `tool_discovery_preloaded` | "Tool discovery (tools preloaded)" | "tool-capable agents whose tools fit the exposure budget" | the preloaded discovery section's all-on text, which includes the KB line exactly as the existing `tool_discovery` row does |
| `knowledge_preloaded` | "Knowledge-base wording (tools preloaded)" | "tool-capable agents whose tools fit the exposure budget, with a knowledge base attached (inside Tool discovery)" | `PRELOADED_KB_LINE.strip()` |

## Inputs
- Branch `sortie/11-tool-exposure-for-small-models` at `40446186` or later.
- For Part B, the same Ollama `0.40.14` and digests as leg 2 (`qwen3:4b-instruct-2507-q4_K_M` `0edcdef34593eac1…`, `lfm3:1.7b-q4_K_M` `b36a103fe2f8fbe9…`), re-verified at the start of Part B, and a valid plan token.

## Outputs
- **Part A:**
  - `the_one/llm/base.py`, `ollama_provider.py`, `anthropic_provider.py`, `openai_provider.py`, `openrouter_provider.py` (the window-known signal);
  - `the_one/agent/factory.py` (lookup, decision, seeding, `agent.tool_exposure`);
  - a new helper module for the budget (e.g. `the_one/agent/tool_exposure.py` grows the decision function and `exposure_defaults()`);
  - `the_one/agent/platform_prompt.py`, `the_one/agent/prompt_layers.py`, `the_one/self_configuration/pending.py`;
  - `evals/tokens.py`;
  - tests;
  - `CLAUDE.md`, `the_one/agents.md`, `evals/README.md`, and `SECURITY-MODEL.md` (the DD12 paragraph with placeholders for the numbers).
- **Part B:**
  - gitignored run directories `evals/runs/s11-cand-main` and `evals/runs/s11-cand-routines`;
  - the compare outputs saved beside them;
  - DD12's numbers filled into `SECURITY-MODEL.md`;
  - the flight-log entry.

  Part B changes no code. A defect it finds, including budget defaults that turn out wrong on the real counter, is a stop for the Flight Director: a code fix is a new Part A pass with its own review.

## Acceptance Criteria

**Part A: the window signal (DD2)**
- [ ] AC1. `LLMProvider` gains a class attribute `context_window_known: bool = False`. It is set True only where a resolver assigns `max_context_tokens` from real metadata:
  - Ollama: `self.native_api and effective is not None`. An `openai-compatible` provider backed by a real-shaped `/api/show` answer stays False.
  - `AnthropicProvider` (and so `anthropic-plan` and `anthropic-plan-token`) and `OpenAIProvider`: a catalog hit, prefix fallback included. A miss leaves it False.
  - `OpenRouterProvider`: a positive `context_length`.

  `MockProvider`, `tests/conftest.py::FakeLLM` and `evals/scripted.py::ScriptedProvider` outside `measure-prompt` are never known. One unit test per rule and per fallback.

**Part A: the decision and seeding (DD1, DD2)**
- [ ] AC2. `exposure_defaults()` reads `THE_ONE_TOOL_EXPOSURE_FRACTION` (default **0.25**, clamped to [0, 1]) and `THE_ONE_TOOL_EXPOSURE_CEILING_TOKENS` (default 8000) at call time, from `os.environ`, as `the_one/agent/_governor.py::governor_defaults` does.
  - An unparsable or negative value falls back to the default, with a warning.
  - A fraction of 0 disables exposure.
  - Tests cover each case.
- [ ] AC3. **The build-time lookup** in `AgentFactory.create`:
  - It is guarded: a missing `_max_context_tokens_resolved`, a missing resolver or any exception means "unknown".
  - It is bounded by a module constant (e.g. `WINDOW_LOOKUP_TIMEOUT_S = 2.0`, patched small in the timeout test): the resolver call runs as a task held in a **module-level** set, discarded through `add_done_callback`, and awaited through `asyncio.wait_for(asyncio.shield(task), WINDOW_LOOKUP_TIMEOUT_S)`.
    - The set is module-level, not per instance, because `api.py`'s context-window route builds a throwaway `AgentFactory` per request.
    - A timeout neither cancels the task nor leaves a default cached as resolved, and the agent is built on discovery.
    - The timeout test awaits the leftover task before it ends, so no "Task was destroyed but pending" noise is left at loop teardown.
  - After the lookup, the window is known iff `getattr(llm, "context_window_known", False)` is True.

  Tests:
  - a resolver that sleeps past the bound gives discovery, and the task still completes afterwards and sets the sentinel;
  - a resolver that raises gives discovery;
  - a provider double that skips `super().__init__()` gives discovery.
- [ ] AC4. **The decision.** After today's seed block (connector pair or not, `current_time`, notes tools, routine tools), the factory builds the exposure set:
  - every name in `registry.tool_names`, in registry order;
  - except `search_tools`;
  - except names already in `loaded_tool_names`;
  - and, for an agent no connector binding names, except `send_to_platform_channel`, `find_platform_destination` and `fetch_channel_history`. `connector_bound` is the value the seed block already computed, including its fail-open `True`.

  The estimate is `ceil(len(json.dumps([SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA] + loaded_schemas + exposure_schemas).encode()) / llm.bytes_per_token)`. Import the two schema constants from `the_one.agent.core` (reading constants is not a touch), and read `bytes_per_token` with `getattr(llm, "bytes_per_token", 4.0)`.

  The budget is `min(int(fraction × llm.max_context_tokens), ceiling)`.

  The agent is exposed iff the window is known, the fraction is above 0 and the estimate is at most the budget. When exposed, the exposure schemas are appended to `loaded_schemas`, and their names to `loaded_tool_names`, before `Agent(...)` is constructed. When not exposed, nothing beyond today's seeds is added.
- [ ] AC5. After construction the factory sets `agent.tool_exposure = ToolExposure(decided, budget, estimate, window_known, window)`. When not known, `budget` and `window` are `None`; `estimate` is always computed.
- [ ] AC6. **Byte-identical discovery.** For an agent that is not exposed, a test shows `agent._compute_visible_schemas()` (or the first-call schemas through a recording provider) equals an explicit expected list: `search_tools`, `continue`, then today's seeds in today's order (the connector pair if bound, `current_time`, the notes tools, the routine tools), with dicts equal to each tool's `to_schema()`. The unknown-window case uses a double with `context_window_known` False. The 4096 and 8192 cases use a double with it True and that window pinned. Cover these cases:
  - unknown window;
  - over budget;
  - fraction 0;
  - a 4096-window and an 8192-window Ollama-shaped provider with an all-on-like agent. The divert criterion needs a 4k or 8k window to stay on discovery; if 8k does not, report it.
- [ ] AC7. **Exposure tests.** A provider double with a known 16384 window and 3.5 bytes per token exposes an all-on-like agent:
  - the first-call schemas are `search_tools`, `continue`, today's seeds, then the remaining registry tools in registry order;
  - an unbound agent's set has none of the three connector tools;
  - a bound agent's set has all three, `fetch_channel_history` included. The factory comment that says it "deliberately stays search-discovered" is updated to say this applies to agents that are not exposed, citing DD1.
  - `Agent.reset()` keeps the full seed.

**Part A: the wording follows the decision (DD3)**
- [ ] AC8. `Capabilities` gains `tools_preloaded: bool = False`. `_tool_discovery(caps)` returns `PRELOADED_TOOL_DISCOVERY + (PRELOADED_KB_LINE if caps.knowledge else "")` when it is true, and today's text otherwise. Both new constants are pinned verbatim by tests, and today's are unchanged.
  - `capabilities_from_registry`, `build_system_prompts` and `build_system_prompt` take a `tools_preloaded` keyword (default False) and render with it.
  - The factory passes its decision.
- [ ] AC9. `the_one/self_configuration/pending.py::apply_pending_revision` reads `getattr(agent, "tool_exposure", None)`, with preloaded meaning `bool(exposure and exposure.decided)`. It passes that to `capabilities_from_registry`, which covers both `build_system_prompts` and the `render_platform(caps)` fallback. A test:
  - applies a `next_turn` revision to an exposed agent and asserts the preloaded wording survives, through both the main path and the fallback (force the rules read to raise);
  - shows the same for an agent that is not exposed, with today's wording.
- [ ] AC10. `platform_sections_for_ui()` adds the two rows in the table above, after the `knowledge` fragment row, in the `tools` variant.
  - They come from a new tuple, e.g. `PRELOADED_FRAGMENTS` (two `Fragment`s). The `tool_discovery_preloaded` text is computed from `_tool_discovery(replace(Capabilities.all_on(), tools_preloaded=True))`.
  - `FRAGMENTS` stays `("knowledge",)`, so `tests/test_platform_prompt.py`'s `[f.id for f in FRAGMENTS] == ["knowledge"]` holds.
  - Existing tests to update in this leg:
    - `tests/test_platform_prompt.py`: its exact `tools` row-id list (around lines 114-140), and the tiling assertion, which also excludes the two new ids;
    - `tests/test_prompt_layers.py::test_info_prompt_examples_match_composed_prompt` (around line 408): its sum of tools rows also excludes the two new ids.
  - The design review found no browser test that pins the row count, and the new rows keep `order[2]`, `order[-1]` and `>= 5` true. No browser test change is expected, but run the `settings` lane anyway.
  - `tests/test_platform_prompt.py`'s tiling assertion excludes them, as it does the `knowledge` fragment.
  - `/api/info`'s `platform_sections` carries them, and `system-page.js::platformOrder` renders them unchanged. Do not touch static files; if a static change turns out to be needed, stop and report, because it pulls in the accessibility review.
  - Every browser test that pins the Prompts row count or labels is updated: grep `tests/browser/` for `platform-section`, the old count and the row titles. The owning lanes run (squawk 0334).

**Part A: evals (DD3, DD8)**
- [ ] AC11. `evals/tokens.py::platform_prompt_sections` (strict) tries `knowledge` × `exec_tools` × `tools_preloaded`, plus tool-free.
  - `kb_tool_entry`'s label follows the measured configuration: "(in the starting set)" when the KB schema is in that configuration's starting schemas, and "(not in the starting set)" otherwise.
  - `tests/test_evals_tokens.py`'s assertion that the KB tool is not in the starting set follows the same rule.
  - `evals/tokens.py` is not frozen. `checks.py`, `outcomes.py`, `harness.py`, `judge.py`, the scenarios and `evals/measure/` do not change in this leg, and `tests/test_evals_freeze.py` stays green unchanged.
  Existing `tests/test_evals_tokens.py` assertions that flip because the measured configurations are now exposed:
  - around line 170, "KB tool not in the starting set";
  - around line 467, `cfg["exposure"] is None`, which becomes a decided record for every configuration but `tool-free`;
  - around lines 477-480, `tools_full > tools` for all-on, which becomes equality for decided configurations.

  `test_routines_on_adds_the_four_schemas_and_leaves_the_prompt_fingerprint` (around line 733) asserts that routines-on and all-on have equal `prompt_sections`. It holds only if both are exposed, which the 0.25 default ensures (AC15).
- [ ] AC12. **The parity test (DD8).** A unit test runs `measure-prompt` offline with the fake counter, as the existing token tests do (`build(evals_isolation)`). **The `tool-free` configuration is exempt** here, in AC16 and AC17, and in `compare`'s warning (which already excludes `tools_off` scenarios): its decision is computed and recorded like any other, but the model gets no tools. For each other configuration whose `exposure.decided` is True, the test asserts:
  - the starting-schema names equal that configuration's `tools_full_names` (same order);
  - `totals.tools == totals.tools_full`.

  The test also asserts the all-on configuration is decided True at the pinned 16384 window.

- [ ] AC12b. **The budget measurement, offline, in Part A.** A unit test builds the starting sets with the real tool classes, through the factory where practical, otherwise from the real schemas as the design review did. It asserts, at the defaults:
  - the eval `all-on`, `all-on-connector` and `routines-on` agents are exposed at 16384 and 3.5 bytes per token;
  - the eval `all-on` agent is on discovery at 4096 and at 8192.

  The flight log reports, for each of these agents, the estimate in tokens at 3.5 and 4.0 bytes per token and its margin against the budget at 4096, 8192, 16384 and 200000:
  - the three eval agents above and `bare`;
  - a real default agent with every built-in tool enabled (execution tools on, no knowledge base, no MCP).

  The design review's offline figures, at 3.5 bytes per token:

  | Agent | Estimate |
  |---|---|
  | all-on | about 2330 |
  | all-on-connector | about 3160-3210 |
  | routines-on | about 3410-3470 |
  | real execution-on agent | 3779 |

  At 0.25 the budgets are 1024, 2048, 4096 and 8000 (the ceiling).

**Part A: docs and gate**
- [ ] AC13. Docs:
  - `CLAUDE.md` gets one paragraph (under Architecture, or beside "current_time and the date layer") on tool exposure: the rule, the two env variables (process environment only, not `.env`, DD13), and that an exposed agent gets the preloaded wording. Its "Prompt evals" paragraph says that a built-in tool's description is now platform prompt text (DD13).
  - `the_one/agents.md` gets the full contract: the signal per provider, the lookup and its bound, the decision, the record and the seed order.
  - `evals/README.md` gets the DD13 note and the exposure line in `report` and `compare`.
  - `SECURITY-MODEL.md` gets DD12's paragraph beside the planted-content residual risks under "Agent notes (M27 F2)" and "Routines › Agent self-scheduling", with `TBD (leg 3 Part B)` placeholders for the numbers.
- [ ] AC14. `ruff check` and `ruff format --check` are clean. `THE_ONE_TEST_NETNS=1 make test-unit` is green (report the summary and skip count). The browser lanes chosen in AC10 are green, run as `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane>`.

**Part B: measurement and compare (after Part A is committed)**
- [ ] AC15. **Part B start check.** Re-verify the Ollama version, both digests and the plan token, and record them. (The budget measurement moved to Part A as AC12b.)
- [ ] AC16. `make eval ARGS="measure-prompt --with-model-counts --json <dir>/measure.json"` for each candidate directory. Every configuration except `tool-free` is `exposure.decided == true`, and the parity of AC12 holds on the real counter.
- [ ] AC17. Both sets run at `--n 20` on the default presets:
  - main set into `evals/runs/s11-cand-main`;
  - routines set (`--scenarios-dir evals/routines/scenarios`) into `evals/runs/s11-cand-routines`;
  - one after the other, each in the background.

  Requirements:
  - no incomplete cell;
  - every Ollama record at `num_ctx` 16384;
  - every run outside `tool-free` with `exposure.decided == true`, which `compare` prints with no `WARNING` line;
  - no request reaching a real host.
- [ ] AC18. Run `compare --baseline evals/baselines/s11-platform.json evals/runs/s11-cand-main` and the routines counterpart, saving the full output to `<dir>/compare.txt`. The flight log records every row. The leg passes when:
  - `qwen3-4b`'s `kb-find`, `kb-answer` and `tool-discovery` are each at least 0.9;
  - no hard failure remains other than these pre-declared readings:
    - DD12's `qwen3-4b` `planted-instruction` and `routines-planted-instruction`, as hard "worse than baseline", or as "baseline not exposed", which is ungated anyway;
    - `no-secrets` for `qwen3-4b` and `lfm3`, read as not worse (state the Fisher p, and that it is not significant at 0.05);
  - `planted-flagged` and `routines-planted` are at 100% on every model;
  - the size gates pass.

  Any other hard failure is a divert: stop and report.
- [ ] AC19. `SECURITY-MODEL.md`'s placeholders are filled from AC18: per model, obedience to the planted instruction on exposed runs, and stored planted notes and routines, all flagged. The flight log carries the claims cells, exposed counts, schema cost (`tools` per configuration against the baseline's) and wall times.

## Verification Steps
- AC1-AC9: the factory, provider and prompt tests, run with `PYTHON=.venv/bin/python bash scripts/run-tests.sh <files> -x --timeout 60`. The test policy's files are listed in the flight spec under "Test policy". Grep `tests/` for factory-built agents and run every hit.
- AC10: `tests/test_platform_prompt.py`, the `/api/info` tests, and the lanes from the grep.
- AC11-AC12: `tests/test_evals_tokens.py`, `tests/test_evals_freeze.py`.
- AC14: the unit gate in the background, then the browser lanes (never concurrently with the unit gate).
- AC15-AC19: the commands named. For JSON checks use a scratch Python script outside the repo; `jq` is not installed. Falsify every new test of AC1-AC12: remove the fix by edit, see the test fail, put the fix back by edit. Report yes or no per test.

## Implementation Guidance
**Part A**
1. **The provider signal (AC1).** The class attribute is on `LLMProvider`. Each resolver sets `self.context_window_known = True` beside its existing `self.max_context_tokens = ...` assignment. Ollama sets it from `self.native_api and effective is not None`; find how `native_api` is stored on `OllamaProvider`.
2. **The decision helper.** Put `exposure_defaults()` and a pure function, e.g. `decide_exposure(*, window_known, window, bytes_per_token, starting, candidates) -> (ToolExposure, list[dict])`, in `the_one/agent/tool_exposure.py`, so the arithmetic is unit-tested without a factory. Keep the module free of factory imports.
3. **The factory (AC3-AC7).**
   - Run the guarded, bounded lookup after the seed block and before the prompt build. `time_tool_available` (`the_one/agent/prompt_layers.py`) is the pattern for a bounded provider probe.
   - Keep a strong reference to the shielded task in a module-level set (AC3), so a timed-out resolver is not garbage-collected mid-flight.
   - Run the window lookup and `time_tool_available` concurrently (`asyncio.gather`), so an unresponsive provider costs one bound per build, not two. `get_provider` builds a fresh provider on every `create()` (factory.py, around line 398); there is no cache.
   - Unit tests that build a real `OllamaProvider` against an unreachable URL now make a second failing request. Each is bounded, but check their timing (`test_connectors_inbound.py`, `test_prompt_layers.py`, `test_search_tools.py`, `test_mcp_tool_provider.py`, `test_factory_disable_enforcement.py`, `test_inbound_session_updated.py`, `test_prune_box_scratch.py`).
   - Pass `tools_preloaded=decided` to `capabilities_from_registry` and `build_system_prompts`.
   - Bind `agent.tool_exposure` right after `Agent(...)`, beside the notes and routine `bind_agent` calls.
4. **The prompt (AC8-AC10).** Add `tools_preloaded` through `Capabilities` → `_tool_discovery` → `capabilities_from_registry` → `build_system_prompts` / `build_system_prompt` (where those build their `Capabilities`). Grep for every caller of the three functions across `the_one/` and decide each:
   - `/api/info`'s examples keep the discovery wording;
   - the context-window route builds through the factory, so it follows.

   Then `pending.py` (AC9) and `platform_sections_for_ui` (AC10).
   - The `Capabilities(...)` that `build_system_prompts` constructs internally (`prompt_layers.py`, around line 147) must receive `tools_preloaded`. A silent default of False there is the easiest way to get this wrong.
   - `tool_free_capabilities` also resets `tools_preloaded=False`.
   - The design review found these callers:
     - `capabilities_from_registry`: factory.py and pending.py only;
     - `build_system_prompts`: factory.py and pending.py only;
     - `build_system_prompt`: tests only.
   - Ollama's flag is `bool(self.native_api) and effective is not None`.
5. **Evals (AC11-AC12)** as described.
6. **Tests** per the flight's test policy. Factory tests that build real provider classes (Anthropic is a local catalog hit) may now be exposed: check `tests/test_factory.py` (its plan-provider tests in particular), `tests/test_factory_openrouter.py`, `tests/test_model_catalog_integration.py`, `tests/test_api_context_window.py`, `tests/test_agent_visibility_filter.py`, `tests/test_search_tools.py`, `tests/test_agent_search_integration.py`, `tests/test_agent_degraded_injection.py`, `tests/test_routine_tools.py`, `tests/test_connectors_inbound.py`, `tests/test_prompt_layers.py`, `tests/test_platform_prompt.py`, `tests/test_self_configuration_write.py`, `tests/test_evals_harness.py` and `tests/test_evals_tokens.py`. A test that pins discovery behaviour should pin it explicitly, by unsetting the window or setting fraction 0 in the test, rather than relying on whichever provider happens to be unknown. Do not change the M30 F2 leg 1c DD7 connector tests (around lines 1195-1390 of `tests/test_factory.py`): DD7 stands for unexposed agents. If a test there now fails because its provider is known, pin discovery in that test's setup and say so.
7. **Docs (AC13).**
8. **Gate (AC14).** Set the leg status `landed (Part A)` in the flight log entry, but keep the leg's status line `in-flight`. Signal `[HANDOFF:review-needed]`; do not commit.

**Part B** (a separate spawn, after the Flight Director's commit)

9. **Start check (AC15).** If anything in Part B shows the code is wrong, including the defaults, stop and report. Do not edit code.
10. **Measure and run (AC16-AC17),** as in leg 2: one set at a time, in the background, waiting on notifications.
11. **Compare (AC18).**
12. **Fill in (AC19),** then set the leg `landed` and signal `[LAND:leg]`.

## Edge Cases
- **Every build resolves afresh:** `get_provider` builds a new provider per `create()`, so every build (a rejoin, the context-window route) makes one bounded metadata call (`/api/show`, a catalog lookup or `/models`). That runs concurrently with the `supports_tools` probe. A caller that holds its own provider instance (the evals' scripted one) sees the sentinel already set.
- **The resolver resolves after a timed-out build:** that build stays on discovery for its session. The next build sees the known window and may expose (accepted, as DD1's staleness note says).
- **A tools-off model (`supports_tools` False):** the decision is still computed and recorded, and may be True. The tool-free prompt is unaffected, because `tools_preloaded` only changes a tools-variant section. The `tool-free` measurement configuration and `tools_off` scenarios are exempt from the parity and "every run exposed" checks (AC12, AC16, AC17).
- **MCP tools registered after the build** (a later connection): not re-decided within the session (DD1).
- **An agent with `enabled_tools` whitelisting:** the registry already holds only enabled tools, so the exposure set follows it, and `current_time` stays whitelist-exempt as today.
- **The `default` agent:** it has no stored row and gets the same rule.
- **`connector_bound` fail-open (`sqlite3.Error`):** the pair is seeded as today, and the exposure set then includes `fetch_channel_history` too, consistent with "bound".

## Files Affected
- `the_one/llm/base.py`, `ollama_provider.py`, `anthropic_provider.py`, `openai_provider.py`, `openrouter_provider.py`.
- `the_one/agent/tool_exposure.py`, `the_one/agent/factory.py`, `the_one/agent/platform_prompt.py`, `the_one/agent/prompt_layers.py`, `the_one/self_configuration/pending.py`.
- `evals/tokens.py`.
- `tests/` per guidance step 6 plus the new tests; browser tests from the AC10 grep.
- `CLAUDE.md`, `the_one/agents.md`, `evals/README.md`, `SECURITY-MODEL.md`.

## Citation Audit
Checked against `40446186` (2026-11-07):
- `the_one/agent/factory.py::AgentFactory.create`, about lines 586-650:
  - `connector_bound` comes from `agent_names_in_use(conn)`, with an `(sqlite3.Error, ValueError)` fail-open to True;
  - `seed_names` is `[CURRENT_TIME_TOOL_NAME]`, or the pair plus `current_time` when bound, appended through `registry.tool_names` membership;
  - then the notes tools and the routine tools are appended;
  - then `time_tool_available`, `capabilities_from_registry(registry, notes=..., rules=True, time_tool=...)` and `build_system_prompts(..., knowledge=, time_tool=, exec_tools=)`;
  - then `Agent(..., loaded_schemas=, loaded_tool_names=, secrets=)`, followed by the `bind_agent` loops.

  The DD-6 comment says `fetch_channel_history` "deliberately stays search-discovered". Verified.
- `the_one/llm/base.py::LLMProvider`:
  - `max_context_tokens: int = 128_000` and `bytes_per_token: float = 4.0` (class attributes);
  - `__init__` sets `_max_context_tokens_resolved = False`;
  - `_resolve_max_context_tokens` is a no-op;
  - `_resolve_max_context_tokens_if_needed` reads the sentinel, calls the resolver, logs on exception, and sets the sentinel in a `finally`.

  Verified.
- `the_one/llm/anthropic_provider.py::AnthropicProvider._resolve_max_context_tokens`: `context_window_for("anthropic", self.model)`, assigned when not `None`. The class default is `max_context_tokens = 200_000`. `the_one/llm/anthropic_plan_provider.py::AnthropicPlanProvider(AnthropicProvider)` and `AnthropicPlanTokenProvider(AnthropicPlanProvider)` inherit it. Verified.
- `the_one/llm/openai_provider.py::OpenAIProvider._resolve_max_context_tokens`: a catalog lookup, as above. `the_one/llm/openrouter_provider.py::OpenRouterProvider._resolve_max_context_tokens` assigns when `resolved is not None and resolved > 0`. Verified.
- `the_one/llm/ollama_provider.py::OllamaProvider._resolve_max_context_tokens`: `show_model`, then `effective_num_ctx(advertised, configured)`, then `_runtime_num_ctx = effective`, assigning `max_context_tokens` when not `None`. `bytes_per_token = BYTES_PER_TOKEN_OLLAMA`. Verified.
- `the_one/agent/platform_prompt.py`:
  - `Capabilities` is a frozen dataclass with `tools, knowledge, notes, rules, time_tool, exec_tools`;
  - `NO_KB_TOOL_DISCOVERY` and `KB_LINE`;
  - `_tool_discovery`;
  - `SECTIONS` with `tool_discovery`;
  - `FRAGMENTS` with `knowledge`;
  - `platform_sections_for_ui` (rows after `tool_discovery`);
  - `capabilities_from_registry(registry, *, notes, rules, time_tool)`;
  - `tool_free_capabilities`.

  Verified.
- `the_one/agent/prompt_layers.py`: `build_system_prompts(agent_name, persona, *, conn, tool_available, now, knowledge, time_tool, exec_tools)` and `build_system_prompt(...)` with the same keywords. `time_tool_available` uses `asyncio.wait_for(llm.supports_tools(), timeout=SUPPORTS_TOOLS_TIMEOUT_S)`. Verified.
- `the_one/self_configuration/pending.py::apply_pending_revision`, about lines 120-170: `time_tool_available`, then `capabilities_from_registry(registry, notes=_has_tool(...), rules=True, time_tool=...)`, then `build_system_prompts(...)`, with an `except` fallback to `render_platform(caps)` / `render_tool_free(caps)`. Verified.
- `evals/tokens.py::platform_prompt_sections`: strict combos of `knowledge` × `exec_tools` plus tool-free; `PlatformAttributionError`. Verified.
- o200k counts of the copy were measured with `evals.tokens.TiktokenCounter` on 2026-11-07: today 49 + 29; B 23 + 17. Verified.
