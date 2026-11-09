# Leg: visuals-prompt-and-evals

**Status**: landed (Part A landed; Part B pending)
**Flight**: [Charts in Chat](../flight.md)

## Objective
An agent with Rich visuals on is told, in a short platform-prompt section, how to write a ```` ```chart ```` block; an agent with it off is not. The flag reaches the prompt that is actually rendered (`build_system_prompts`), `capabilities_from_registry`, the factory and both `pending.py` paths. A new eval check and scenario set prove the default models write valid charts; the platform and routines baselines are compared; and the leg stops for the operator's decision on the prompt-size growth.

## Context
- Flight decisions **DD12** (the section, its threading, its pins, the gate lanes) and **DD13** (the check, the separate scenario set, the procedure, the mid-flight commit, sortie 12 interplay).
- Leg 3 landed `AgentConfig.rich_visuals` and recorded in the flight log **when a change takes effect**. This leg writes the test that pins that moment, now that the flag reaches the prompt.
- The checks use leg 1's `the_one.visuals.chart_spec.parse_chart`.
- **This leg has two parts, with a review and commit between them** (DD13 step 1, the flight's one planned exception to the single end-of-flight review):
  - **Part A** (autonomous): product code, pins, the eval check, the scenario set, and offline tests. It ends with `[LAND:leg]`-style reporting of Part A only. The Flight Director then runs the Batch A + B review (Reviewer and Accessibility Reviewer) over legs 1-4 Part A and commits.
  - **Part B** (quota-spending, run by a Developer spawned for it after the commit): the eval runs and measurements. It stops with a written comparison for the operator's decision, then records baselines per that decision.

## Inputs
- Legs 1-3 landed. `the_one/agent/platform_prompt.py` (`Capabilities` at `:30-45`, `SECTIONS` ending with `formatting` at `:181`, `tool_free_capabilities` at `:273-281`, `capabilities_from_registry` at `:289-311`).
- `the_one/agent/prompt_layers.py` `build_system_prompts` (`:103`, the `tools_preloaded` keyword at `:113` and passed into `Capabilities` at `:156`) and `build_system_prompt` (`:175`, `:185`, `:198`).
- `the_one/agent/factory.py:688-704`; `the_one/self_configuration/pending.py:132-167`.
- `evals/tokens.py:152-180` (capability combinations), `evals/checks.py` (the registry pattern of `_reply_matches` etc.), `evals/scenario.py:37` (`_AGENT_KEYS`), `evals/harness.py:388-397` (`AgentConfig(...)` without `rich_visuals`, so the default is on), `evals/measure/*.toml`, `tests/test_evals_freeze.py:32` (`SCORING_DIGESTS`).

## Outputs
- **Part A:**
  - `Capabilities.visuals`, the `visuals` section, and the keyword through `build_system_prompts` / `build_system_prompt` / `capabilities_from_registry` / the factory / `pending.py`;
  - updated platform-prompt pins, a timing test, `evals/tokens.py` combinations;
  - the `reply_has_valid_chart` check (and `reply_has_chart` if useful) with offline tests;
  - `rich_visuals` as an optional `[agent]` key in scenarios;
  - `evals/visuals/scenarios/*.toml` and fixtures if needed;
  - the `SCORING_DIGESTS` update with a comment;
  - an `evals/README.md` section;
  - CLAUDE.md "Prompt evals" note.
- **Part B:**
  - eval run directories (gitignored);
  - a comparison summary in the flight log;
  - after the operator decides, `evals/baselines/m35-platform.json`, `m35-routines.json` and `m35-visuals.json` (or a revised prompt and a re-run).

## Acceptance Criteria

**Part A: prompt**
- [ ] AC1. `Capabilities` gains `visuals: bool = True`. A `Section("visuals", "Rich visuals", "agents with Rich visuals on", lambda c: c.visuals, ...)` follows `formatting`. `tool_free_capabilities` keeps `visuals` unchanged.
  - The text is DD12's draft, trimmed by measurement: as short as possible while naming the tag, "`type` first", the minimal object shape, the six types and the optional keys in one line.
  - The leg records the section's token count in its flight-log entry ("### visuals-prompt-and-evals", Part A). Use the offline tokenizer if `[evals]` is installed (check with `.venv/bin/python -c "import tiktoken"`); otherwise record the character count and say so. The real `measure-prompt` runs in Part B.
- [ ] AC2. **Threading.**
  - `build_system_prompts` and `build_system_prompt` take `visuals: bool = True` and pass it into the `Capabilities(...)` they render.
  - `capabilities_from_registry` takes `visuals: bool = True`.
  - `AgentFactory.create` passes `visuals=config.rich_visuals` to both and sets `agent.rich_visuals`.
  - `pending.py` passes `visuals=getattr(agent, "rich_visuals", True)` on its main and fallback paths.
  - Nothing reads the database for it.
- [ ] AC3. **Tests:**
  - An agent built with `rich_visuals=False` has a system prompt without the section text, and one with `True` has it, for both the tool-capable and tool-free prompts.
  - The pending self-revision preview matches the agent's real prompt in both states.
  - **The timing pin:** a test reproduces leg 3's recorded "when a change takes effect" (for example, an agent saved with the switch off is built without the section at the recorded moment).
- [ ] AC4. **Platform pins updated:**
  - `tests/_platform_prompt_pins.py` and the byte-for-byte tests (`tests/test_platform_prompt.py:22-27`);
  - the "toggling changes nothing" list (`:36-41`) does **not** include `visuals`, and a new test asserts that `visuals` does change the text;
  - the UI row ids (`:123-134`) gain `visuals` **in both lists**. `tool_free_capabilities` keeps `visuals`, so `platform_sections_for_ui` (`:220`) emits it in the tools list and the tool-free list. The `free == ["identity_tool_free", "formatting"]` pin becomes `[..., "formatting", "visuals"]`. Re-check the "tile the all-on render" assertion that follows.

  Settings › Prompts shows the section once, with its "Applies when" line: `platformOrder` (`areas/admin/system-page.js:143-163`) drops a tool-free twin with the same id and equal text, and the visuals text is capability-independent. Update the `settings` lane pins (`tests/browser/test_flow_admin_settings_nav.py:244-275`: the hard-coded section-id loop and the applies-when counts) after `grep -rn "formatting" tests/` and a grep for the section count and labels (squawk 0334).

  Hard-coded prompt strings elsewhere may move too: run `tests/` with `-k prompt`, plus `tests/test_prompt_layers.py`, `tests/test_tool_exposure.py`, `tests/test_connectors_inbound.py`, `tests/test_self_configuration_write.py`, `tests/test_notes_tools.py` and `tests/test_secret_prompt_layer.py`.
- [ ] AC5. `evals/tokens.py::platform_prompt_sections` (`:167-169`) enumerates `visuals` in `(True, False)`: 16 tool combinations plus tool-free in both states. Its strict-mode message names it. `tests/test_evals_tokens.py` updates its parallel combo list (`:712-714`) and its tool-free pin (`:695`), and covers a visuals-off render. No eval-built config is visuals-off (`harness.py` has no off case unless a scenario sets the AC7 key), so the off combinations keep `measure-prompt` honest for configs that set it.

**Part A: evals**
- [ ] AC6. `evals/checks.py` gains `reply_has_valid_chart` with optional params `turn` and `types` (a list).
  - It passes when the reply holds at least one top-level chart block whose body `parse_chart` accepts, of one of `types` if given. `types` matches the parsed spec's type attribute; check the exact name in `the_one/visuals/chart_spec.py`.
  - **The block scanner mirrors the chat's parser (`markdown.js:169-185`) exactly:**
    - The opener is `^```(.*)$` at column 0, and the language is the first whitespace token of the info string, lowercase `chart` exactly, so `chart extra` counts and `Chart` does not.
    - The closer is only `^```\s*$`. `~~~` is never a fence.
    - An unterminated block runs to the end of the text, and `parse_chart` then decides.
    - **Top-level only:** a list-nested (indented) block never counts, and a chart fence quoted inside an outer fence (a ```` ```json ```` or plain ```` ``` ```` block) never counts, because the chat treats it as code.
    - Do not reuse `_strip_code` (`checks.py:224`), which strips fences and accepts `~~~`.
  - On failure the Outcome is a `fail` (not an error class), with a one-line reason naming the parser's sentence or "no chart block".
  - It is registered and validated like the other checks (`validate_params`), with offline unit tests (`tests/test_evals_checks.py` or the matching file):
    - a valid chart, an invalid one, the wrong type, no block, and two blocks of which one is valid;
    - a list-nested block, a chart inside a `json` outer fence, `~~~chart`, an indented fence, an unclosed fence, and `chart extra`;
    - a ```` ```json ```` block, which is not a chart.
- [ ] AC7. `evals/scenario.py` accepts an optional `rich_visuals` boolean under `[agent]` (added to `_AGENT_KEYS`), and `evals/harness.py` passes it to `AgentConfig`. When absent it is omitted, so the product default (on) applies.
- [ ] AC8. `evals/visuals/scenarios/` holds three scenarios in the existing TOML format, each with phrasings × facts variants as rich as `markdown-links.toml`:
  - `chart-when-asked`: data given in the message, a chart explicitly asked for; check `reply_has_valid_chart`.
  - `chart-fits-timeseries` (a time series → `types = ["line", "area"]`) and `chart-fits-shares` (shares of a whole → `types = ["pie", "bar"]`), as two files, since checks are per scenario.
  - `no-chart-unasked`: a factual question with no numbers; check `reply_not_matches` with `pattern = '(?m)^```\s*chart\b'`.

  That is four scenario files. `make eval ARGS="run --scenarios-dir evals/visuals/scenarios --dry-run"` (`evals/__main__.py:57`) loads them cleanly. No `evals/visuals/fixtures` is needed: the fixture server starts only if `<fixtures_root>/web` exists (`evals/runner.py:415`). The platform fingerprint (`evals/scenarios/`) is unchanged. `tests/test_evals_scenarios.py` gains a `VISUALS_SCENARIOS` directory parallel to `ROUTINES_SCENARIOS` (`:~595-630`): every visuals scenario loads, has no loopback dependency and has a can-fail check, following the README's `selftest` convention.
- [ ] AC9. `tests/test_evals_freeze.py::SCORING_DIGESTS` (which pins `checks.py`, `outcomes.py`, `judge.py` and `harness.py`; `scenario.py` is not pinned) is updated for `checks.py` and `harness.py`, with a comment line in the style of the existing entries: "Mission 35 F1 L4: reply_has_valid_chart and the rich_visuals agent key (operator-approved, DD13); the scenarios under evals/scenarios/ and their scoring are unchanged."
- [ ] AC10. `evals/README.md` documents the check, the `rich_visuals` key and the visuals set. CLAUDE.md "Prompt evals" names `the_one/agent/platform_prompt.py`'s visuals section as platform prompt text, and the new set's baseline once recorded.
- [ ] AC11. **Part A gate:**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes, including the offline `tests/test_evals_*.py`.
  - `THE_ONE_TEST_NETNS=1` lanes `settings` and `agents` pass.
  - The static guards pass, and `ruff` is clean.
  - **Handoff:** set the leg's status to `landed` with a note "Part A landed; Part B pending", write the Part A flight-log entry, and send your final report to the Flight Director, then **stop** (no eval runs, no commit). The Flight Director runs the flight review over legs 1-4 Part A and commits, then spawns a new Developer for Part B.

**Part B: runs (after the Flight Director's review and commit)**
- [ ] AC12. **Prerequisites re-verified at the start of Part B**, and recorded:
  - the plan token works (`~/.config/the-one-evals/plan-token`);
  - Ollama serves `qwen3-4b` and `lfm3`;
  - `[evals]` is installed;
  - sortie 12's status (if landed, which baseline it recorded, to compare against instead of `s11`).
- [ ] AC13. **Measurement and sentinel:**
  - `make eval ARGS="measure-prompt"` for bare, all-on, tool-free and routines-on, with the before (`main` numbers from `s11-platform`) and after token counts by part recorded.
  - An **n=5 sentinel** of `chart-when-asked` and of the most exposed platform cells (`markdown-links`, `notes-as-told`, `tool-discovery` or the closest) on the default models, before any n=20 set. If the sentinel shows a collapse (a platform cell well below its bar, or `chart-when-asked` below about 0.5 on haiku), stop and report.
- [ ] AC14. **The n=20 runs and comparisons.**
  - **Why plain `compare` runs** (README `:229-236`): it refuses only on a different `scenarios` or `models` fingerprint, a different token counter, or an equal `prompt` fingerprint without `--same-prompt`. The platform and routines scenario trees are untouched, and the `prompt` fingerprint (`fingerprint.py:30`, the rendered bare, all-on and tool-free text) changes because every eval agent takes the default-on section.
  - So these comparisons use plain `compare`, **never** `--same-prompt`. `--same-prompt` is only for the later `m35-*` same-prompt re-baselines.
  - Before running, quote in the flight log the exact `run`, `report`, `compare` and `baseline` command lines you will use, taken from `evals/README.md` (including its `--n` flag for 20 runs).

  The runs:
  - the platform set compared with `compare --baseline evals/baselines/s11-platform.json`;
  - the routines set with `compare --baseline evals/baselines/s11-routines.json --scenarios-dir evals/routines/scenarios` (follow the README's exact invocation);
  - the visuals set run on the default models.

  The flight log gets a table: per model and cell, the pass rate with its Wilson interval against the baseline, and every gate result. Size gates are expected to fail; say by how much.
- [ ] AC15. **Stop for the operator.** Report the comparison and the size growth, and recommend one of:
  - accept the growth and record same-prompt re-baselines;
  - cut the text and re-measure.

  After the operator decides (relayed by the Flight Director), record `evals/baselines/m35-platform.json`, `m35-routines.json` and `m35-visuals.json` with `baseline` on the accepted prompt, or apply the cut and repeat AC13-AC14. Update CLAUDE.md's "current baselines" sentence. The baseline JSON files are committed (the documented exception to the no-golden-files preference); the run directories are not. Do not commit; the Flight Director commits.
- [ ] AC16. **If sortie 12 has landed** by Part B, its recorded platform baseline replaces `s11-platform` as the comparison target. The Flight Director confirms the choice before the n=20 runs, and the flight log records it.

## Verification Steps
- AC1-AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_platform_prompt.py tests/test_prompt_layers.py tests/test_factory.py tests/test_evals_tokens.py -x --timeout 60` (adjust to the files that exist), plus the new timing test; `--lane settings`.
- AC6-AC10: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_evals_checks.py tests/test_evals_scenario.py tests/test_evals_freeze.py -x --timeout 60` (or the matching files); read the README diff.
- AC11: the gate commands.
- AC12-AC15: the run directories under `evals/runs/` and the flight-log table.

## Implementation Guidance
1. **Prompt.**
   - Add the field and section, then thread the keyword: `prompt_layers.py`'s two functions, `capabilities_from_registry`, the factory call at `:688-704`, and `pending.py:132-148` (main) and its fallback (`:165-167`).
   - Run `tests/test_platform_prompt.py` to see every pin move, and update the pins by editing (they are byte pins: regenerate the expected text from the new render, never hand-edit a string to match).
2. **Timing test:** read leg 3's flight-log finding and pin it at the layer it names.
3. **evals/tokens.py:** extend the `combos` list with `visuals` in `(True, False)` (doubling it), keep the tool-free combination in both states, and update the strict message.
4. **Check.** Follow `_reply_matches` / `_reply_has_markdown_link` (`evals/checks.py:274-300`) for shape, `_strip_code` awareness and turn selection. Find the fenced blocks with a small line scanner using the same column-0, first-token `chart` rule as the chat (or `App.markdown`'s parser rules restated), then call `parse_chart`.
5. **Scenarios:** model them on `evals/scenarios/markdown-links.toml`. Keep phrasings natural. For `chart-fits-data`, give data whose best chart is unambiguous.
6. **Freeze digests:** run `tests/test_evals_freeze.py`, copy the new digests it prints into `SCORING_DIGESTS` with the comment, and re-run.
7. **Part B:**
   - Follow `evals/README.md` exactly for `run`, `measure-prompt`, `compare` and `baseline` invocations and output paths.
   - Run long runs in the background and wait for completion notifications.
   - Never touch port 8484 or the default data directory (the eval guard refuses anyway).
   - Do not commit; the Flight Director commits.

## Edge Cases
- **The default agent and test agents with no `rich_visuals` attribute:** `getattr(..., True)`.
- **`pending.py`'s fallback when the agent has no exposure:** still passes `visuals`.
- **A chart inside a list item in an eval reply:** the check counts top-level blocks only (document it). The chat draws nested ones too, but the prompt tells the model to write a top-level block, and the check measures that.
- **Sortie 12 landed meanwhile:** compare against its baseline and record why.
- **A provider error mid-run (plan 429):** the run tool's own outcome classes apply. Report errors separately from failures.

## Files Affected
- `the_one/agent/platform_prompt.py`, `the_one/agent/prompt_layers.py`, `the_one/agent/factory.py`, `the_one/self_configuration/pending.py`
- `tests/_platform_prompt_pins.py`, `tests/test_platform_prompt.py`, the prompt-layer, factory and pending tests, the timing test, `tests/browser/test_flow_admin_settings_nav.py` (if pins move)
- `evals/checks.py`, `evals/scenario.py`, `evals/harness.py`, `evals/tokens.py`, `evals/visuals/scenarios/*.toml` (four, new), `evals/README.md`
- `tests/test_evals_checks.py` (or the matching file), `tests/test_evals_scenarios.py` (`VISUALS_SCENARIOS`), `tests/test_evals_tokens.py` (`:695`, `:712-714`), `tests/test_evals_freeze.py`
- `CLAUDE.md`, the flight log; in Part B, `evals/baselines/m35-*.json`

## Citation Audit
Verified on the flight branch at leg design (legs 1 and 3 do not touch these files):
- `the_one/agent/platform_prompt.py:30-45` — `Capabilities` (`tools`, `knowledge`, `notes`, `rules`, `time_tool`, `exec_tools`, `tools_preloaded=False`) - verified
- `the_one/agent/platform_prompt.py:181` — `Section("formatting", "Formatting", "always", _always, _const(_FORMATTING))` is the last section - verified
- `the_one/agent/platform_prompt.py:273-281` — `tool_free_capabilities` uses `replace(...)` turning off tools/knowledge/time_tool/exec_tools/tools_preloaded - verified
- `the_one/agent/platform_prompt.py:289-311` — `capabilities_from_registry(registry, *, notes, rules, time_tool, tools_preloaded=False)` - verified
- `the_one/agent/prompt_layers.py:103`, `:113`, `:156`, `:175`, `:185`, `:198` — the `tools_preloaded` keyword through both builders - verified
- `the_one/agent/factory.py:693-703`; `the_one/self_configuration/pending.py:34`, `:137`, `:140-147` — the call sites passing `tools_preloaded` - verified
- `evals/tokens.py:152-180` — `platform_prompt_sections(text, *, strict)` combos over (kb, ex, pre) plus tool-free; strict raises `PlatformAttributionError` - verified
- `evals/scenario.py:37` `_AGENT_KEYS`; `:275-276` unknown field rejected - verified
- `evals/harness.py:388-397` — `AgentConfig(...)` built without `rich_visuals` - verified
- `evals/checks.py:274-300` — `_reply_matches`, `_reply_not_matches`, `_reply_has_markdown_link` - verified
- `tests/test_evals_freeze.py:32`, `:89-90` — `SCORING_DIGESTS` and the digest assertion - verified
- `evals/measure/` — `all-on.toml`, `bare.toml`, `routines-on.toml`, `tool-free.toml` - verified
