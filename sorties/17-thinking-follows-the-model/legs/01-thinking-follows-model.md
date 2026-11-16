# Leg: thinking-follows-model

**Status**: completed
**Flight**: [Extended thinking follows the model](../flight.md)

## Objective
Send the adaptive-thinking option only to Claude models that support it, recover once from a model the rule gets wrong, make a newly created Claude provider start with the switch on, and reword the switch's help text.

## Context
- Flight DD1 (the model-id rule), DD2 (the in-place strip-and-retry and the process-wide memory), DD3 (`thinking_active`), DD4 (the create-time default, route and form), DD5 (wording, option A: the label stays "Extended thinking"), DD6 (the eval record), DD7 (verification).
- Operator decisions in the charter: **new providers only** (no stored row is changed, nothing runs at startup) and **adaptive only** (no fixed-budget thinking).
- This is the only autonomous leg. A required HAT leg follows. Nothing is committed in this leg (the flight commits once, after review).
- The Architect reviewed the flight against the code on 2026-11-14 (flight log, "Architect design review, cycle 1"); this leg adds no decision beyond the flight's.

## Inputs
- Branch `sortie/17-thinking-follows-the-model` from `main` at `85292a4e`. The tree holds the sortie's planning files, an edit to squawk 0361, and an untracked `env.sh` (not ours; leave it).
- `the_one/llm/anthropic_provider.py` with `resolve_extended_thinking`, `_build_kwargs`, `_strip_for_bad_request`, `_strip_cache_markers` (the nearest exemplar for a strip with a remembered state).
- The recorded error from squawk 0361: `Error code: 400 … 'adaptive thinking is not supported on this model'`.

## Outputs
- `the_one/llm/anthropic_provider.py`: `supports_adaptive_thinking`, the process-wide set, the new strip branch, the `thinking_active` change.
- `the_one/interfaces/web/api.py`: the create-time stamp in `create_provider`.
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js`: the create default and the help text.
- `evals/models.py`: the model-aware record.
- Tests (below) and docs (below).

## Acceptance Criteria
1. [ ] `supports_adaptive_thinking(model)` is a pure module-level function in `anthropic_provider.py`. It is true for a `claude-{family}-{major}[-{minor}][-{date}]` id whose version is 4.6 or higher, false for a lower version and for the version-first form (`claude-3-…`), and true for an id it cannot parse. A trailing 8-digit segment is a date, not a minor version; `-latest` is not a version segment. Versions compare as integer tuples (`4-10` is higher than `4-6`). It is false for any id in the process-wide "found unable to think" set.
2. [ ] A table test covers every `anthropic` id in `the_one/llm/data/model_catalog.json` (read from the file, with the expected value per id written in the test), plus `claude-test`, an empty string, `claude-sonnet-4-10`, and a new-form `-latest` id.
3. [ ] In `_build_kwargs`, `thinking_active` is the resolved switch AND `supports_adaptive_thinking(self.model)` AND `enable_thinking is not False`. For a model that cannot think with the switch on, the built request has no `thinking` key and no `thinking` / `redacted_thinking` block in any message. For a capable model the request is unchanged from today. Tested on all three provider classes (`anthropic`, `anthropic-plan`, `anthropic-plan-token`).
4. [ ] A 400 whose text says adaptive thinking is not supported makes `_strip_for_bad_request` (a) add `self.model` to the process-wide set, (b) pop `thinking` from `kwargs`, (c) remove every `thinking` / `redacted_thinking` block from assistant content lists in `kwargs["messages"]`, (d) log one warning, and return true. The branch sits after the temperature branch and fires only while `"thinking"` is in `kwargs`.
5. [ ] The retry is bounded: a second "not supported" 400 after the strip is re-raised (in `complete` and in `stream`). In `stream`, no strip happens once a chunk has been yielded (the existing `yielded_any` gate).
6. [ ] The strip composes: a request that draws the temperature 400 and then the thinking 400 succeeds on the third attempt with neither key, in `complete` and in `stream`.
7. [ ] Negative cases: a 400 reading "temperature may only be set to 1 when thinking is enabled" takes the temperature branch only and leaves `thinking` in place; a 400 reading "a final assistant message must start with a thinking block" strips nothing and is re-raised; neither adds the model to the set.
8. [ ] After one instance has recorded a model id, a **new** provider instance for the same model id builds its first request without thinking (no failed request). The set is never persisted. Tests reset it (a fixture, or an explicit clear) so no test leaks into another.
9. [ ] Stored `Message` objects are unchanged by the strip (assert on the input messages after a stripped retry).
10. [ ] `POST /api/providers` for each of the three Claude types returns and stores `config.thinking_enabled == true` when the body's `config` has no `thinking_enabled` key, when `config` is absent, and when the value is `null`. An explicit `false` or `true` is kept. A non-Claude type's `config` is untouched. The stamp is in the route, not on `LLMProviderConfig` or the repository: a provider created through the repository directly has no key.
11. [ ] `PUT /api/providers/{id}` stamps nothing: changing a stored non-Claude provider's type to a Claude type leaves `thinking_enabled` absent, and a PUT that omits it on a Claude provider keeps the stored value.
12. [ ] The provider editor's **create** form shows the Extended thinking switch checked whenever it is visible (whichever Claude type is chosen, including after switching type back and forth), and saving without touching it stores `thinking_enabled: true`. The **edit** form shows the stored value (absent shows unchecked), and opening an existing provider is not dirty.
13. [ ] The switch's label is still exactly "Extended thinking". Its help text is exactly: `When on, models that support adaptive thinking (Claude models from version 4.6 on) reason step by step before answering. Older models on this provider answer without it.`
14. [ ] `evals/models.py::effective_values` records `thinking` as the resolved switch AND `supports_adaptive_thinking(llm.model)`. The offline eval tests pass; no baseline file changes.
15. [ ] `resolve_extended_thinking` and the `THE_ONE_ANTHROPIC_EXTENDED_THINKING` precedence are unchanged; `evals/env.py` still lists the variable as pinned.
16. [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes with the expected skip count (15 under netns), and the `providers` browser lane passes. `ruff check` and `ruff format --check` are clean.
17. [ ] Docs are updated (see Implementation Guidance step 7).

## Verification Steps
- Criteria 1-9, 14, 15: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_anthropic_provider.py tests/test_anthropic_prompt_caching.py tests/test_evals_*.py -x --timeout 30` (plus any new test file).
- Criteria 10, 11: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_provider_api.py tests/test_provider_repository.py -x --timeout 30`.
- Criteria 12, 13: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane providers`, and the static guards `tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py`.
- Criterion 16: `THE_ONE_TEST_NETNS=1 make test-unit`, read `-rs` if the skip count is not 15; `ruff check the_one/ tests/ scripts/ evals/` and `ruff format --check the_one/ tests/ scripts/ evals/`.
- Falsification: for criteria 3, 4, 7 and 10, show each new test fails with its fix removed by editing (never by restoring a file), then put the fix back. Report yes or no per test.

## Implementation Guidance

1. **The rule and the set** (`the_one/llm/anthropic_provider.py`, beside `resolve_extended_thinking`)
   - A module-level `set[str]` of model ids found unable to think, with a small private helper to clear it for tests.
   - `supports_adaptive_thinking(model)`: check the set first, then parse. Keep the parser small and total: it never raises on any string.

2. **`thinking_active`** (`_build_kwargs`)
   - Add the capability check to the existing expression. Nothing else in `_build_kwargs` or `_to_api_message` changes: `thinking_active` already gates the `thinking` key and the replay.

3. **The strip branch** (`_strip_for_bad_request`)
   - Order: temperature, then thinking, then `cache_control`.
   - Match the lowered text for the "not supported" phrase together with "thinking"; pin the squawk's recorded message in a test. Keep the match narrow (criterion 7).
   - Strip in place. Do **not** rebuild through `_build_kwargs` (it would re-add `temperature` and other keys earlier strips removed, breaking the loop's bound).
   - Filter only `content` values that are lists on `role == "assistant"` messages. Tool-result and user messages are left alone.

4. **The create stamp** (`create_provider` in `the_one/interfaces/web/api.py`)
   - After validation, for the three Claude types, set `config["thinking_enabled"] = True` when the key is absent or `None`. Build a new config dict (do not mutate the validated model's dict in place); the plan-token branch's `model_copy(update=…)` just below is the pattern.
   - Use the route's existing type constants where they exist; do not add a default to `LLMProviderConfig`.

5. **The editor** (`provider-editor.js`)
   - `checked`: in edit mode the stored value (as today); in create mode `true`.
   - The switch is built once and shown or hidden on type change, so one initial value covers every Claude type. Check that the create form's dirty baseline still treats an untouched new form as it does today.
   - Replace `THINKING_DESC` with criterion 13's sentence.

6. **Tests**
   - New unit tests go in `tests/test_anthropic_provider.py` (or a sibling file if it reads better). Every new test that builds a provider clears the environment override with `monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)`, as the existing thinking tests do.
   - The existing tests that build `AnthropicProvider(model="claude-test", …{"thinking_enabled": True})` and expect thinking must keep passing unchanged ("unparseable is capable").
   - **Rewrite** (rename over delete-and-readd) in `tests/browser/test_flow_provider_editor.py`: `test_thinking_toggle_shown_for_anthropic_unchecked_by_default` (now checked by default on create) and `test_thinking_toggle_info_icon_tooltip`'s pinned sentence. Add: an untouched create saves `thinking_enabled: true`; an existing provider stored with `false` opens unchecked and clean.
   - Grep `tests/`, `tests/browser/`, `scripts/` and `tests/behavior/` for `thinking_enabled`, `pf-thinking-enabled`, `Extended thinking`, and the old sentence, and for exact-dict assertions on a created Claude provider's `config`; update every pin the stamp or the wording moves, and run the owning lane of each hit.

7. **Docs**
   - `the_one/agents.md`, the extended-thinking paragraph ("Anthropic specifics (M16 F10)"): add the model rule, the retry and its process-wide memory, and the create-time default with "new providers only".
   - `CLAUDE.md`, "LLM layer" notes: one short paragraph, "Extended thinking follows the model (sortie 17)", pointing at `agents.md`.
   - `.env.example`: the override comment now says it applies only to a provider with no stored value (providers created before sortie 17 that never saved the switch, and key-less providers such as the evals').
   - `tests/behavior/extended-thinking-tool-turn.md`: the precondition says the switch is on by default for a new provider; add one edge-case line (a provider with the switch on, used by a model that cannot think, completes a turn with no thinking item and no error). Add an `Updated` note; do not change the step table's ids.
   - `docs/` — check for any page that states the old default or the old help text.

## Edge Cases
- **A thinking-only assistant message** (thinking blocks, no text, no tool calls): after the in-place filter its content list is empty. Check what the thinking-inactive build produces for the same stored message and make the stripped request acceptable to the API in the same way (for example by dropping the empty assistant message); state what you chose and why in the flight log. Do not send an empty content list.
- **`enable_thinking=False`** from the caller keeps turning thinking off for any model.
- **Mock provider and non-Claude types**: untouched by the stamp and the rule.
- **Model id with whitespace or upper case**: the parser must not raise; treat what it cannot parse as capable.
- **Two instances racing on the first 400**: both may pay one failed request; the set makes the outcome the same. No lock is needed.
- **The plan providers' error translation** wraps `super().complete/stream`; the strip happens inside `super()`, so a stripped retry never reaches the translation. Confirm with one plan-provider retry test.

## Files Affected
- `the_one/llm/anthropic_provider.py` - the rule, the set, `thinking_active`, the strip branch
- `the_one/interfaces/web/api.py` - the create-time stamp
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js` - create default, help text
- `evals/models.py` - the model-aware record
- `tests/test_anthropic_provider.py`, `tests/test_provider_api.py`, `tests/browser/test_flow_provider_editor.py`, eval tests as needed
- `the_one/agents.md`, `CLAUDE.md`, `.env.example`, `tests/behavior/extended-thinking-tool-turn.md`
- `sorties/17-thinking-follows-the-model/flight-log.md` - the leg's outcome

## Citation Audit
Checked against the working tree at `85292a4e` on 2026-11-14.

- `the_one/llm/anthropic_provider.py::resolve_extended_thinking` - stored value, then env, then `False`; takes no model - verified
- `the_one/llm/anthropic_provider.py::AnthropicProvider._build_kwargs` - `thinking_active = resolve_extended_thinking(self._thinking_enabled_config) and enable_thinking is not False`, computed once before the message loop; `kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}` when active - verified
- `the_one/llm/anthropic_provider.py::AnthropicProvider._to_api_message` - an assistant message becomes a content list when it has tool calls, or when `thinking_active and msg.thinking`; thinking blocks are appended first, only when `thinking_active`; the dicts are built fresh - verified
- `the_one/llm/anthropic_provider.py::AnthropicProvider._strip_for_bad_request` - lowered-text match; temperature branch requires `"temperature" in kwargs`; then `cache_control` → `_strip_cache_markers`; returns bool - verified
- `the_one/llm/anthropic_provider.py::AnthropicProvider.complete` / `stream` - `kwargs` built once, then a `while True` loop that re-runs after a strip; `stream` strips only while `not yielded_any` - verified
- `the_one/llm/anthropic_plan_provider.py` `complete` / `stream` - wrap `super()` and translate errors after it returns or raises - verified
- `the_one/interfaces/web/api.py::create_provider` - `LLMProviderConfig.model_validate(data)`, then the plan-token `model_copy(update=…)` stamp, then `repo.create(provider)` - verified
- `the_one/interfaces/web/api.py::update_provider` - merges `existing.model_dump()` with the body and re-validates; no create-time stamping - verified
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js` - `checked: !!(isEdit && provider.config && provider.config.thinking_enabled)`; the save writes `payload.config.thinking_enabled = !!h.thinking.control.checked` when `defaults.showThinkingEnabled`; `THINKING_DESC` is the help text - verified
- `tests/browser/test_flow_provider_editor.py::test_thinking_toggle_shown_for_anthropic_unchecked_by_default` and `::test_thinking_toggle_info_icon_tooltip` - pin unchecked-on-create and the old sentence - verified
- `evals/models.py::effective_values` - `out["thinking"] = resolve_extended_thinking(llm._thinking_enabled_config)` - verified
- `the_one/agents.md` "Anthropic specifics (M16 F10)" paragraph and `.env.example` override comment - exist as described - verified

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
