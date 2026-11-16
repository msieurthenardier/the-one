# Sortie: Extended thinking follows the model

**Status**: landed

## Charter

### Outcome
Extended thinking is on by default for a new Claude provider and is only ever sent to models that support it, so one provider can serve thinking and non-thinking models without errors.

### Why Now
Squawk [0361](../../squawks/0361-extended-thinking-is-a-provider-setting-not-a-model-one.md): during sortie 16's HAT (step 8C), turning the provider's "Extended thinking" switch on made every turn fail with `400 … 'adaptive thinking is not supported on this model'` on a model that cannot think. The sortie 16 debrief lists chartering this sortie as an action item, and its recommendation 4 (walk thinking inside the work group with a real model) becomes possible once this lands.

### Success Criteria
- [ ] With the switch on, an agent on a model that does not support adaptive thinking completes a turn normally, and its request carries no thinking option.
- [ ] With the switch on, an agent on a model that supports adaptive thinking still gets thinking, shown in the turn's work group as today.
- [ ] A new Claude provider (all three types: `anthropic`, `anthropic-plan`, `anthropic-plan-token`) has the switch on without the operator touching it. Turning it off still turns thinking off for every model.
- [ ] The switch's label and help text say it applies only to models that support thinking.

### Constraints
- The setting stays on the provider. No agent-level setting and no schema change.
- **New providers only** (operator decision, 2026-11-14): a provider saved before this change keeps its stored value. Nothing is flipped at startup.
- **Adaptive only** (operator decision, 2026-11-14): models that can think only through the older fixed-budget option (for example Haiku 4.5, Sonnet 4.5) get no thinking. Budget thinking is out of scope.
- The `THE_ONE_ANTHROPIC_EXTENDED_THINKING` environment override keeps its current precedence, and the evals keep refusing it as a pinned variable.
- No change to the frozen `the_one/agent/core.py`.

---

## Pre-Flight

### Objective
Make `AnthropicProvider` decide per request model whether to send the adaptive-thinking option, with a bounded retry as a safety net for a model the rule gets wrong; make a newly created Claude provider start with the switch on; and reword the switch so the operator knows it applies only to models that can think. All three Claude provider types share the request builder, so one change covers them.

### Open Questions
- [x] **Label wording (operator).** → Option A approved 2026-11-14, see DD5.
- [x] **HAT models (operator).** → Confirmed 2026-11-14: the operator has one Claude model that supports adaptive thinking (version 4.6 or newer) and one that does not, both reachable from a provider usable on a dev instance. Sortie 16's HAT failed this check at the HAT itself; it was asked at design this time, and is re-verified at the start of the HAT leg.
- [x] Do existing providers flip on? → No, see Constraints.
- [x] Budget thinking for older models? → No, see Constraints.

### Design Decisions

**DD1. A model-capability rule, by model id**: a pure function `supports_adaptive_thinking(model: str) -> bool` beside `resolve_extended_thinking` in `the_one/llm/anthropic_provider.py`. It parses `claude-{family}-{major}[-{minor}][-{date}]` and returns true when the version is 4.6 or higher (so every 5.x id is true). An 8-digit trailing segment is a date, not a minor version (`claude-opus-4-20250514` is 4.0; `claude-sonnet-4-5-20250929` is 4.5). The legacy version-first form (`claude-3-5-sonnet-…`, `claude-3-haiku-…`, including `claude-3-5-haiku-latest`) is false. Versions compare as integer tuples, so a future `-4-10` is 4.10, not 4.1. **An id the rule cannot parse is treated as capable** (DD2 catches a wrong guess).
- Where ids come from: Anthropic's `models.list`, the catalog fallback and hand entry (`the_one/interfaces/web/api.py`, the provider models route). `AnthropicProvider._build_client` ignores `base_url`, so Bedrock- or Vertex-prefixed ids cannot appear.
- Against the 31 bundled catalog ids: `claude-fable-5`, `claude-fable-5-1`, `claude-haiku-5-5` and every `opus`/`sonnet` id from 4.6 on are true; `claude-opus-4-0`, `claude-sonnet-4-0`, `claude-opus-4-20250514`, every 4.5 id and every version-first id are false.
- "Unparseable is capable" is load-bearing for existing tests: about 15 tests build `AnthropicProvider(model="claude-test", …{"thinking_enabled": True})` (`tests/test_anthropic_provider.py`) and expect thinking. They keep passing unchanged; the leg must not flip this default.
- Rationale: the bundled catalog (`the_one/llm/data/model_catalog.json`) maps a model id to a context window only and is regenerated from an outside source, so a capability column there would need a second hand-kept source. A version rule needs no release when a new model ships.
- Trade-off: the rule encodes "4.6 and newer can think". A future model that breaks that pattern is sent the option once and falls to DD2.

**DD2. A bounded strip-and-retry as the safety net**: when a request fails with a 400 whose message says thinking is not supported on the model, the app remembers that model id as unable to think and retries the request once without thinking. It joins the existing `_strip_for_bad_request` path in `complete()` and `stream()` (in `stream()`, only before the first chunk is yielded). One warning is logged per model id.
- **The strip is in place** (Architect review): pop `thinking` from `kwargs` and filter `thinking` / `redacted_thinking` blocks out of the assistant content lists already in `kwargs["messages"]`. The target is "no `thinking` key and no thinking blocks", not byte-equality with a fresh thinking-off build (which would turn a thinking-only assistant message into a plain string). It is safe because `_to_api_message` and `_thinking_block_to_api` build fresh dicts, so stored `Message`s are never changed. Do not rebuild through `_build_kwargs`: that would re-add `temperature` and any key an earlier strip removed, breaking sortie 14's invariant that a strip fires only while its key is still in `kwargs`.
- **The match is narrow and ordered**: the new branch sits after the temperature branch, fires only while `"thinking" in kwargs` (which keeps the bound), and matches the "not supported" phrase. Other 400s that mention thinking must not trip it: "temperature may only be set to 1 when thinking is enabled" and the replay errors (for example "a final assistant message must start with a thinking block") are pinned as negative cases. A test strips temperature and then thinking one after the other, in both `complete` and `stream`.
- **What is remembered**: a process-wide, never-persisted set of model ids found unable to think, beside `supports_adaptive_thinking`, which consults it. A per-instance flag is not enough: a provider instance belongs to a built agent, and connectors build an agent per inbound message, web chats one per join and routines one per run, so a per-instance flag would pay a failed round trip on every connector message. A restart forgets the set and pays one failed request per model id again.
- Rationale: DD1 guesses "capable" for unknown ids; without this, a wrong guess is squawk 0361 again. The mechanism already exists for `temperature` and `cache_control`.
- Trade-off: one failed request per process for a mis-ruled model id. The match is on the error text, pinned by a test with the recorded message from the squawk; the HAT confirms the text against the real API.

**DD3. Thinking is active only when the switch is on AND the model can think**: `_build_kwargs` computes `thinking_active` as today's resolved switch, AND `supports_adaptive_thinking(self.model)` (which is false for an id in DD2's remembered set), AND `enable_thinking is not False`. `thinking_active` already gates both the `thinking` request key and the replay of stored thinking blocks, so a model that cannot think is sent neither.
- Rationale: one decision point, already hoisted for replay.
- Trade-off: none known.

**DD4. "On by default" is a create-time default, not a resolver default**: `resolve_extended_thinking` keeps its precedence (stored value → environment → off). Two changes make a new provider start on:
  1. The provider editor's create form shows the switch checked (edit mode keeps showing the stored value; an absent stored value shows off, as today).
  2. `POST /api/providers` sets `config.thinking_enabled = true` when one of the three Claude types is created without that key, so a provider created by any caller starts on.
- Both places are needed: the form always sends an explicit bool when the switch is shown, so a route-only default would be overridden by the form's `false`; a form-only default leaves API callers off.
- **The stamp lives in the route only**, never on `LLMProviderConfig` or the repository. The evals create providers through the repository directly (`evals/harness.py`, `evals/models.py`), so a model or repository default would turn thinking on for them.
- An explicit `"thinking_enabled": null` on create counts as absent and is stamped `true`. An explicit `false` is respected.
- **A type change on PUT stamps nothing.** Changing a stored provider's type to a Claude type leaves the key as stored (absent shows off in the editor). That is "new providers only" applied literally.
- **The environment override now reaches fewer providers.** Its precedence is unchanged, but every new Claude provider stores an explicit value, so `THE_ONE_ANTHROPIC_EXTENDED_THINKING` only affects providers with no stored value (older rows and key-less providers such as the evals'). `.env.example`'s comment says so.
- Rationale: the operator chose new providers only. A resolver default of "on" would also flip every stored row that has no explicit value, and would change what the evals' key-less providers resolve to.
- Trade-off: "default on" lives in two places (form and route). A stored row without the key stays off until the operator turns it on.

**DD5. Wording** *(operator approved option A, 2026-11-14)*:
- **Chosen (A):** label **"Extended thinking"** (unchanged, so the row stays one short line), help text **"When on, models that support adaptive thinking (Claude models from version 4.6 on) reason step by step before answering. Older models on this provider answer without it."** (worded by version, to match DD1: Haiku 5.5 and Fable 5 can think too)
- Not chosen (B): label **"Extended thinking (for models that support it)"** with the same help text.
- Rationale: the help text carries the rule; the label alternative makes it visible without opening the help.
- Trade-off: the alternative lengthens a form label and moves every test that names the switch by its label.

**DD6. Evals: no run, one honest record**: the eval providers are built through the repository without the key, so they resolve to off before and after; no baseline moves and no eval run is required (the prompt text and tool schemas do not change). `evals/models.py::effective_values` is made model-aware (the resolved switch AND `supports_adaptive_thinking(llm.model)`), so the record and `cache-probe`'s "effective thinking" line say what is actually sent.
- Rationale: a record that says `thinking: true` while nothing is sent would mislead the next comparison on a newer eval model.
- Trade-off: a small touch to a developer tool outside the product.

**DD7. Verification apparatus**: unit tests on the built request (act: construct each provider type with a model id and config, call `_build_kwargs`; observe: the returned kwargs dict), unit tests of the retry with a scripted client raising the recorded 400, API tests of the create default (act: `POST /api/providers`; observe: the response's `config`), and browser tests in the `providers` lane for the create form's default and wording (observe: the switch's checked state and the saved provider through the API). No new behavior-test spec: the existing `extended-thinking-tool-turn` spec already covers a real thinking turn, and the HAT covers the mixed-model provider with real models.
- Rationale: the request body is the thing under test, and it is fully observable in process.
- Trade-off: the real API's 400 text is pinned from one recorded sample.

### Citation Audit

Verified against the working tree at `85292a4e`.

| Citation | Status |
|---|---|
| `the_one/llm/anthropic_provider.py::resolve_extended_thinking` — precedence is stored value, then `THE_ONE_ANTHROPIC_EXTENDED_THINKING`, then `False`; takes no model | verified |
| `the_one/llm/anthropic_provider.py::AnthropicProvider._build_kwargs` — computes `thinking_active` once from the resolved switch and `enable_thinking`, with no model check; passes it to `_to_api_message` for replay; sets `kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}` when active | verified |
| `the_one/llm/anthropic_provider.py::AnthropicProvider._to_api_message` — replays stored thinking blocks only when `thinking_active` | verified |
| `the_one/llm/anthropic_provider.py::AnthropicProvider._strip_for_bad_request` — matches on the lowered error text, mutates `kwargs`, returns whether to re-run; called from `complete()` and from `stream()` only while nothing has been yielded | verified |
| `the_one/llm/anthropic_provider.py::AnthropicProvider.__init__` — `_cache_disabled` is a per-instance, never-persisted flag (the pattern DD2 copies) | verified |
| `the_one/llm/anthropic_plan_provider.py` `complete`/`stream` — delegate to `super()`, so both plan types use the same `_build_kwargs` | verified |
| `the_one/llm/anthropic_plan_provider.py` (module end) — registers both plan types; `the_one/llm/registry.py` only maps them (corrected at the Architect review) | verified |
| `the_one/connectors/inbound.py` and `the_one/interfaces/web/app.py` — an agent, and so a provider instance, is built per connector message and per web join (Architect review; why DD2 remembers per process) | verified by the Architect |
| `tests/browser/test_flow_provider_editor.py::test_thinking_toggle_shown_for_anthropic_unchecked_by_default` and the following help-text test — pin the switch unchecked on create and the old help text word for word | verified by the Architect |
| `the_one/llm/data/model_catalog.json` — the `anthropic` section maps model id to an integer context window only | verified |
| `the_one/interfaces/web/api.py::create_provider` — validates the body into `LLMProviderConfig` and can adjust it before `repo.create` (it already stamps `token_set_at` for the plan-token type) | verified |
| `the_one/interfaces/web/static/js/areas/studio/provider-editor.js` (the `h.thinking` toggle) — checked only in edit mode from the stored value; the save always writes an explicit bool when the switch is shown; the help text is `THINKING_DESC` | verified |
| `the_one/interfaces/web/static/js/areas/studio/providers-section.js` — `showThinkingEnabled: true` on exactly the three Claude types | verified |
| `evals/models.py::effective_values` — records `resolve_extended_thinking(llm._thinking_enabled_config)` | verified |
| Whether the API accepts thinking blocks in history when the `thinking` key is absent (DD2's retry shape avoids depending on it) | unverified, by design |

### Prerequisites
- [x] No open sortie or active mission overlaps: sortie 12 (claimed actions) and sortie 13 (Ollama wire) touch neither `anthropic_provider.py` nor the provider editor.
- [x] The operator has confirmed the two HAT models (Open Questions). Re-verified at the start of the HAT leg.
- [x] No schema change, no new dependency, no network service.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. Add `supports_adaptive_thinking` and the process-wide set of model ids found unable to think; fold the rule into `thinking_active` in `_build_kwargs`.
2. Extend `_strip_for_bad_request` with the thinking case, after the temperature branch: record the model id and strip in place (DD2).
3. Stamp the create default in `create_provider` for the three Claude types (route only); show the create form's switch checked; reword per DD5.
4. Tests:
   - a model-id table for the rule (every `anthropic` id in the bundled catalog, unparseable ids, a two-digit minor);
   - the built request for capable and incapable models on all three provider types;
   - the retry in `complete` and `stream`: bounded to one, composed with the temperature strip, the two negative 400 texts, and the remembered id honoured by a second provider instance (the set is reset between tests);
   - the create default: present key respected, absent and `null` stamped, non-Claude types untouched, a PUT type change stamps nothing;
   - the editor: **rewrite** `test_thinking_toggle_shown_for_anthropic_unchecked_by_default` (now checked on create) and the help-text test beside it in `tests/browser/test_flow_provider_editor.py`.
   - New unit tests clear the environment override (`monkeypatch.delenv("THE_ONE_ANTHROPIC_EXTENDED_THINKING", raising=False)`), as the existing ones do.
5. `evals/models.py::effective_values` reports the model-aware value (DD6).
6. Docs: `the_one/agents.md` (the extended-thinking notes in the LLM layer section) and a short line in `CLAUDE.md`'s LLM layer notes, `.env.example`'s comment (DD4), the `extended-thinking-tool-turn` spec (precondition wording, plus an edge-case line: a provider with the switch on used by a model that cannot think), and squawk 0361's link to this sortie.

Gate lanes: `make test-unit`, then the `providers` lane. The Architect's grep under squawk 0334's rule found no pin of the label or help text in any other lane; the Developer repeats the grep before the full gate.

### Checkpoints
- [ ] A capable and an incapable model on one provider both build correct requests
- [ ] The recorded 400 is retried once and the instance stops sending thinking
- [ ] A new Claude provider saves with the switch on from the form and from the API
- [ ] Full local gate green

### Adaptation Criteria

**Divert if**:
- The API rejects a retried request because of thinking blocks already in the history in a way the thinking-inactive build does not avoid.
- Making the create default work needs a stored-row migration or a resolver default change (that would break the "new providers only" constraint).
- The operator asks for budget thinking on older models (a second cluster of decisions: escalate, do not widen).

**Acceptable variations**:
- Where the capability function lives (`anthropic_provider.py` or `model_catalog.py`).
- The exact error-text match for DD2, as long as the squawk's recorded message is pinned.
- Making `evals/models.py` report the model-aware value, if it is a one-line change with no baseline effect.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `thinking-follows-model` - The capability rule, the retry safety net, the create default (route and form), the wording, tests and docs
- [x] `hat-and-alignment` *(required, operator decision 2026-11-14)* - Guided HAT on a dev instance with real models: one provider, a model that thinks and one that does not; also walks sortie 16's unwalked step 8C (thinking inside the work group)

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Squawk 0361 linked to this sortie and closed out

### Verification
On a dev instance (never port 8484), create a Claude provider without touching the switch and confirm it saves on. Create two agents on it, one on a model that supports adaptive thinking and one on a model that does not. Send each a message: both turns complete, the first shows a thinking item in its work group, the second shows none, and the log holds no 400.
