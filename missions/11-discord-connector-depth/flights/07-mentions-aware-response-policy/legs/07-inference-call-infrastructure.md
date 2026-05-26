# Leg: inference-call-infrastructure

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

Build `the_one/connectors/_inference.py:run_engagement_inference(...)` — the standalone async function that decides whether the bot should engage with an inbound that wasn't explicitly addressed. New `Settings.inference_provider_config_id` AND `Settings.inference_model` fields (paired — provider config row scopes auth + base_url; model name scopes per-call routing). New `fallback_llm_model` parameter on the function (the dispatcher passes the routed agent's `llm_model` alongside the provider id for the fallback path). Filtered session-history projection; hand-tuned prompt template (per Flight DD §9); strict output parsing; safe-default-False error handling. Fully testable in isolation via stub providers. L8 wires it into the dispatcher.

## Context

- **Flight DD §9 verbatim** — function lives at `the_one/connectors/_inference.py:run_engagement_inference(account, envelope, session_messages, settings, provider_repo, fallback_provider_config_id, fallback_llm_model) -> bool`. Filtered session history: `Role.USER` + `Role.ASSISTANT` (non-empty content AND no tool_calls), last 20 entries. Operator-typed turns (`visibility == "operator"`) prefixed with `[operator] ` so the inference LLM can distinguish operator-typed steering from peer messages. Prompt template per DD §9 (exact text below). Output parsing: lowercase + strip → first token compared against `"yes"`/`"no"`; anything else → False. Temperature 0.0, max_tokens 10. Any exception → False (silence is the safe default).
- **Model source — Flight DD §9 extension (cycle-1 review caught this gap)** — `LLMProviderConfig` (`the_one/db/models.py:18-54`) has NO `model` field; provider configs scope auth (base_url + api_key + config) but NOT the per-call model name (the agent loop sources `model` from `AgentConfig.llm_model` at `agent/factory.py:272-278`). The inference path therefore needs the model name from somewhere. Resolution: pair the existing `settings.inference_provider_config_id` with a new `settings.inference_model: str | None`; both must be set (or both unset) for the settings path to fire. The fallback path receives `fallback_llm_model: str | None` from the dispatcher (the routed agent's `llm_model`). Both unset → return None (no inference). If one of the pair is set but not the other → log + return None (operator misconfiguration; surfaced as silence per the safe-default discipline).
- **Provider resolution shape (DD §9)** —
  - Reads `settings.inference_provider_config_id`.
  - Unset → fall back to the routed agent's LLM (resolved via the `fallback_provider_config_id` parameter passed from the dispatcher).
  - Set and resolves successfully → use that provider.
  - Set but resolution raises (provider row deleted, encryptor failure) → treat as inference-no (silence) and log. Does NOT fall back to the routed agent (operator misconfiguration is surfaced via the audit log + log warning).
  - Fallback (routed-agent) provider misconfigured → treat as inference-no (silence) with the same safe-default. The routed agent's primary path will surface the provider error separately when an engaged turn tries to run `step()`.
- **Settings layer (recon-confirmed)** — `Settings` is `pydantic.BaseSettings` at `the_one/config.py`, env-backed (`THE_ONE_*` env vars + `.env`). **NOT DB-persisted**; no migration needed. L7 adds TWO new fields: `inference_provider_config_id: str | None = None` AND `inference_model: str | None = None`. Both default None; both must be set (or both unset) for the settings path to fire. Backed by env vars `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` and `THE_ONE_INFERENCE_MODEL` respectively.
- **L7 / L8 boundary** — L7 ships the inference function + the new settings field + tests. L7 does NOT touch the dispatcher. L8 imports `run_engagement_inference` into `_inbound.py` and consults it at the policy gate per DD §1 decision tree step 4.
- **Channel name resolution** — L7 reuses `the_one.connectors.post_step_metadata.resolve_channel_name(cache, channel_id)` (added by L3). That helper returns `None` on miss; L7's caller wraps with `or envelope.channel_id` so the prompt always has a channel identifier.
- **Pre-step cache snapshot** — L7's inference call runs BEFORE the post-step binding (the gate at step 11.5 decides engaged-vs-silent before step 12 fires). The inference function calls `_get_account_cache_snapshot` async (same pattern L3 uses post-step) to fetch the cache for channel-name resolution. The pool lock is separate from the session lock, so awaiting from inside the gate's flow is safe.

## Inputs

- L1–L6 landed uncommitted. `Message.peer_name`, `channel_id`, `channel_name` all exist; the lifted `post_step_metadata.py` exists with `resolve_channel_name`; L5's `account.config["always_listen"]` exists; L6's `AgentConfig.connector_always_listen` exists.
- `the_one/config.py` — `Settings` class declaration with current fields (host, port, dev_mode, data_dir). L7 appends `inference_provider_config_id`.
- `the_one/db/repositories.py:LLMProviderRepository.get(provider_id)` (around line 1038) — raises `KeyError` on miss; returns `LLMProviderConfig`.
- `the_one/agent/factory.py:122-129` — `_PROVIDER_TYPE_MAP` (provider-type-to-registry-name map); `the_one/agent/factory.py:258-278` — the `LLMProviderConfig` → `LLMProvider` instance construction pattern (model name + base_url + api_key + config → `get_provider(...)`). L7 mirrors this pattern in a small internal helper.
- `the_one/llm/base.py:262-270` — `LLMProvider.complete()` abstract method with signature `(messages, tools, temperature, max_tokens) -> Message`.
- `the_one/connectors/__init__.py` — `OPERATOR_VISIBILITY = "operator"` constant.
- `the_one/connectors/post_step_metadata.py:resolve_channel_name(cache, channel_id) -> str | None` (L3 addition).
- `the_one/connectors/_pool.py:_get_account_cache_snapshot(account_id) -> _DiscoverableCacheSnapshot | None` (L3 caller pattern).
- `the_one/connectors/base.py:InboundEnvelope`, `the_one/db/models.py:ConnectorAccount` — type signatures for the function.
- `the_one/llm/mock.py` — MockProvider used by the test pattern (recon-confirmed at `_connector_dispatch_helpers.py:70-130`).
- Existing tests for connectors-private modules at `tests/test_connectors_post_step_metadata.py` (L1's relocated file) — style precedent.

## Outputs

- `the_one/config.py`:
  - **ADD** two paired fields to `Settings`:
    ```python
    # M11 F7 L7: inference provider + model for the engagement-policy gate.
    # Both must be set (or both unset) for the settings path to fire at the
    # L8 dispatcher gate. Unset → fall back to the routed agent's
    # configured LLM (the dispatcher passes the agent's llm_model alongside
    # the provider id). Backed by env vars
    # ``THE_ONE_INFERENCE_PROVIDER_CONFIG_ID`` and ``THE_ONE_INFERENCE_MODEL``.
    inference_provider_config_id: str | None = None
    inference_model: str | None = None
    ```
- New file `the_one/connectors/_inference.py`:
  - Module docstring citing M11 F7 L7 + Flight DD §9.
  - Imports: `Settings`, `LLMProviderRepository`, `LLMProviderConfig`, `get_provider`, `_PROVIDER_TYPE_MAP` (or its symbol if exported), `Message`, `Role`, `InboundEnvelope`, `ConnectorAccount`, `OPERATOR_VISIBILITY`, `_get_account_cache_snapshot`, `resolve_channel_name`, `logger`.
  - Module-level prompt template constant `_INFERENCE_PROMPT_TEMPLATE` containing the exact text from DD §9 (preserved verbatim, with `{filtered_session_history_as_turns}`, `{peer_name}`, `{channel_name}`, `{inbound_text}` placeholders).
  - Private helper `_filter_session_history(messages: list[Message], limit: int = 20) -> list[Message]` — projects `Role.USER` + `Role.ASSISTANT` with non-empty content AND no tool_calls (drops tool calls / tool results entirely); takes the last `limit` entries from the filter result.
  - Private helper `_render_history_for_prompt(filtered: list[Message]) -> str` — converts the filtered list to a turn-by-turn string. Each turn: `"user: {content}"` or `"assistant: {content}"`. Operator-typed USER turns (visibility == OPERATOR_VISIBILITY) get the `[operator] ` prefix on the content: `"user: [operator] {content}"`. Most-recent-last ordering.
  - Private async helper `_resolve_inference_provider(settings, provider_repo, fallback_provider_config_id, fallback_llm_model) -> LLMProvider | None` — implements DD §9's provider-resolution semantic with the model-source extension:
    - Settings path: BOTH `settings.inference_provider_config_id` AND `settings.inference_model` must be non-None to fire. If only one is set, log + return None (operator misconfiguration). If both set, resolve the provider config (provider_repo.get) → construct via `get_provider(...)` with `model=settings.inference_model`. On any exception → log + return None (does NOT fall back to fallback path; surfaced as silence per DD §9).
    - Fallback path: only used when BOTH settings fields are unset. Requires BOTH `fallback_provider_config_id` AND `fallback_llm_model`. If either is None, return None. Otherwise resolve provider config and construct with `model=fallback_llm_model`.
    - Both paths fail → None.
  - Public async function `run_engagement_inference(account, envelope, session_messages, settings, provider_repo, fallback_provider_config_id, fallback_llm_model) -> bool`:
    1. Resolve cache snapshot via `_get_account_cache_snapshot(account.id)`; resolve channel_name = `resolve_channel_name(snapshot.cache if snapshot else None, envelope.channel_id) or envelope.channel_id`.
    2. Filter history via `_filter_session_history(session_messages)`; render via `_render_history_for_prompt`.
    3. Format the prompt template with `peer_name` (from envelope), `channel_name` (from step 1), `inbound_text` (envelope.text), and the rendered history.
    4. Resolve the provider via `provider = await _resolve_inference_provider(...)`. If None → log a warning and return False.
    5. Build a single `Message.user(prompt)` message and call `result = await provider.complete(messages=[Message.user(prompt)], tools=None, temperature=0.0, max_tokens=10)` inside a `try/except`. Any exception → log warning + return False.
    6. Parse the response defensively: `text = (result.content or "").strip().lower(); first = text.split()[0] if text else ""`. Return `first == "yes"`. Anything else (including `result.content is None`, empty string, "no", "maybe", "uncertain", multi-word "yes, ...") → False.
- New tests in `tests/test_connectors_inference.py`:
  - `test_filter_session_history_drops_tool_calls` — list with USER, ASSISTANT-with-tool-calls, TOOL, ASSISTANT-plaintext → filter result has USER + ASSISTANT-plaintext only.
  - `test_filter_session_history_drops_empty_content` — ASSISTANT with `content=""` and no tool_calls → filtered out.
  - `test_filter_session_history_keeps_only_last_n` — list of 30 messages → result has 20.
  - `test_render_history_for_prompt_operator_prefix` — USER message with visibility=OPERATOR_VISIBILITY → prompt line includes `[operator] ` prefix; visibility=None → no prefix.
  - `test_render_history_for_prompt_ordering` — input ordering matches output ordering (most-recent-last).
  - `test_resolve_inference_provider_uses_settings_when_both_id_and_model_set` — `settings.inference_provider_config_id="prov-a"` AND `settings.inference_model="model-a"` → repo lookup is for "prov-a"; constructed provider uses `model="model-a"`; fallback id/model is ignored.
  - `test_resolve_inference_provider_returns_none_when_settings_id_set_but_model_unset` — id set, model unset → log + None (operator misconfiguration). Does NOT silently fall back.
  - `test_resolve_inference_provider_returns_none_when_settings_model_set_but_id_unset` — model set, id unset → log + None. Symmetric.
  - `test_resolve_inference_provider_falls_back_when_settings_both_unset` — both settings fields None; `fallback_provider_config_id="prov-b"` AND `fallback_llm_model="model-b"` → repo lookup is for "prov-b"; constructed provider uses `model="model-b"`.
  - `test_resolve_inference_provider_returns_none_on_settings_resolution_failure_no_fallback` — settings.inference_provider_config_id="missing-prov", settings.inference_model="x", AND fallback_provider_config_id="working-prov" AND fallback_llm_model="y" → provider_repo.get raises KeyError on "missing-prov" → helper returns None (does NOT fall back to the working fallback per DD §9). Actively verify by passing a working fallback that would resolve.
  - `test_resolve_inference_provider_returns_none_when_fallback_id_missing` — settings fully unset, fallback id missing → None.
  - `test_resolve_inference_provider_returns_none_when_fallback_model_missing` — settings fully unset, fallback id set but fallback_llm_model None → None (the pairing invariant applies to fallback too).
  - `test_run_engagement_inference_returns_true_on_yes` — stub provider returns Message with content="yes" → function returns True.
  - `test_run_engagement_inference_returns_false_on_no` — content="no" → False.
  - `test_run_engagement_inference_returns_false_on_garbage` — content="maybe" or "uncertain" → False.
  - `test_run_engagement_inference_returns_false_on_multiword_response` — content="yes, the agent should respond" → False (only single-word "yes" engages).
  - `test_run_engagement_inference_returns_true_on_yes_with_surrounding_whitespace` — content="  YES  " → True (lowercase + strip).
  - `test_run_engagement_inference_returns_false_on_provider_exception` — provider.complete raises → function returns False without crashing.
  - `test_run_engagement_inference_returns_false_on_provider_resolution_failure` — provider_repo.get raises → function returns False.
  - `test_run_engagement_inference_returns_false_on_none_content` — provider returns Message with content=None → function returns False without AttributeError. Defensive against codec corner cases.
  - `test_run_engagement_inference_end_to_end_happy_path` — cross-cutting integration: real Message list with mixed roles + visibility tags, real-shaped envelope, MockProvider returning "yes" through the full `_resolve_inference_provider` resolution (no monkeypatching) → returns True. Covers the happy path that the unit tests slice apart.
  - `test_run_engagement_inference_uses_channel_id_when_cache_miss` — cache returns None for the channel; prompt uses raw envelope.channel_id as channel_name fallback.
  - `test_run_engagement_inference_uses_cache_label_when_present` — cache has a matching channel; prompt uses the friendly label.
  - `test_run_engagement_inference_filters_history_before_prompt` — session_messages has 30 entries with mixed roles; the prompt's history section reflects the filtered last-20-USER-or-ASSISTANT-plaintext.

## Acceptance Criteria

- [x] `the_one/config.py:Settings` has both `inference_provider_config_id: str | None = None` AND `inference_model: str | None = None` fields with paired M11 F7 L7 docstring (env-var names `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` and `THE_ONE_INFERENCE_MODEL`).
- [x] `the_one/connectors/_inference.py` exists with the prompt template constant, three private helpers (`_filter_session_history`, `_render_history_for_prompt`, `_resolve_inference_provider`), and the public `run_engagement_inference` async function per DD §9. The function signature includes `fallback_llm_model: str | None` (the dispatcher passes the routed agent's `llm_model` for the fallback path).
- [x] Prompt template matches Flight DD §9's exact text verbatim (including the strong-bias-toward-no language, the four yes-criteria bullets, and the "When in doubt, no" closing).
- [x] Output parsing: lowercase + strip → split → first token compared against `"yes"`; only single-word "yes" returns True. Multi-word, garbage, exception → False.
- [x] Provider resolution implements the paired-fields semantic: settings path requires BOTH `inference_provider_config_id` AND `inference_model` set; fallback path requires BOTH `fallback_provider_config_id` AND `fallback_llm_model` set; partial pairs → None; settings.id missing-resolution → None (does NOT fall back to fallback); fallback path only fires when settings fully unset.
- [x] All 23 new tests in `tests/test_connectors_inference.py` pass. (Shipped 24 — see deviation note in flight log L7 entry.)
- [x] `docker exec the-one pytest tests/test_connectors_inference.py -x --timeout 30` passes.
- [x] Full suite at leg-end: `docker exec the-one pytest -x --timeout 60` — no L7-introduced regressions.
- [x] Flight log L7 entry under `## Leg Progress` documents the leg; leg checked off in `flight.md`; leg artifact status set to `landed`.

## Verification Steps

- `python -c "from the_one.connectors._inference import run_engagement_inference; print('OK')"` prints `OK`.
- `python -c "from the_one.config import Settings; s = Settings(); print(s.inference_provider_config_id, s.inference_model)"` prints `None None` (defaults).
- `python -c "import os; os.environ['THE_ONE_INFERENCE_PROVIDER_CONFIG_ID']='prov-a'; os.environ['THE_ONE_INFERENCE_MODEL']='model-a'; from the_one.config import Settings; print(Settings().inference_provider_config_id, Settings().inference_model)"` prints `prov-a model-a` (env binding works).
- `grep -n "_INFERENCE_PROMPT_TEMPLATE\|STRONG BIAS TOWARD" the_one/connectors/_inference.py` returns the prompt template.
- Targeted: `docker exec the-one pytest tests/test_connectors_inference.py -x --timeout 30` — all 19 green.
- Full suite: `docker exec the-one pytest -x --timeout 60` — all green.

## Implementation Guidance

1. **Add the Settings fields** in `the_one/config.py`. Append after `data_dir`:
   ```python
   # M11 F7 L7: inference provider + model for the engagement-policy gate.
   # When BOTH are set, the L8 dispatcher gate at decision-tree step 4 uses
   # this provider+model for the inference call ("does this message warrant
   # an agent response?"). When BOTH are unset, falls back to the routed
   # agent's configured LLM (the dispatcher passes the agent's llm_model
   # alongside the provider id). Partial pairs (only id OR only model set)
   # → log + None (operator misconfiguration; surfaced as silence per
   # Flight DD §9's safe-default discipline). Backed by env vars
   # ``THE_ONE_INFERENCE_PROVIDER_CONFIG_ID`` and ``THE_ONE_INFERENCE_MODEL``.
   inference_provider_config_id: str | None = None
   inference_model: str | None = None
   ```

2. **Create `the_one/connectors/_inference.py`**. Module docstring opens with M11 F7 L7 + Flight DD §9 attribution. Imports per Outputs.

3. **Define the prompt template constant** as a module-level string literal:
   ```python
   _INFERENCE_PROMPT_TEMPLATE = """\
   You are deciding whether an AI agent should respond to a message in a chat conversation.

   Recent conversation context (most recent last):
   {filtered_session_history_as_turns}

   New message from {peer_name} in {channel_name}:
   {inbound_text}

   Should the agent respond? Respond with exactly one word: "yes" or "no".

   STRONG BIAS TOWARD "no". An overly chatty bot is annoying — silence is the default. Only respond "yes" when there is high confidence (beyond a reasonable doubt) that the agent should engage. Pass on borderline cases.

   "yes" criteria — at least one must clearly hold:
   - The message is unambiguously directed at the agent (by name, implicit reference, or direct question that no human in the conversation has answered)
   - The message is a question that the agent's persona is clearly well-suited to answer AND no other participant has answered
   - The recent context shows the agent is mid-conversation about this topic
   - The operator has explicitly indicated (in operator-only messages tagged visibility="operator") that the agent should engage with this kind of message

   When in doubt, "no".
   """
   ```
   Use the exact DD §9 wording. Keep the template a raw multi-line string for readability.

4. **Implement `_filter_session_history(messages, limit=20)`**:
   ```python
   def _filter_session_history(messages: list[Message], limit: int = 20) -> list[Message]:
       """Project Role.USER + Role.ASSISTANT (plaintext only) from the session history.

       Drops:
       - Role.TOOL messages (tool results)
       - Role.ASSISTANT messages with non-empty tool_calls
       - Messages with empty content (regardless of role)

       Returns the last `limit` entries from the filtered list.
       """
       filtered = [
           m for m in messages
           if m.role in (Role.USER, Role.ASSISTANT)
           and m.content
           and not m.tool_calls
       ]
       return filtered[-limit:]
   ```

5. **Implement `_render_history_for_prompt(filtered)`**:
   ```python
   def _render_history_for_prompt(filtered: list[Message]) -> str:
       """Render the filtered session history as the prompt-template substring.

       Each turn becomes one line: ``user: ...`` or ``assistant: ...``.
       Operator-typed USER turns (visibility == OPERATOR_VISIBILITY) get the
       ``[operator] `` prefix on the content so the inference LLM can
       distinguish operator-steering messages from peer messages per DD §9.
       """
       lines: list[str] = []
       for m in filtered:
           role_label = "user" if m.role == Role.USER else "assistant"
           content = m.content
           if m.role == Role.USER and m.visibility == OPERATOR_VISIBILITY:
               content = f"[operator] {content}"
           lines.append(f"{role_label}: {content}")
       return "\n".join(lines)
   ```

6. **Implement `_resolve_inference_provider`** with the paired-fields semantic:
   ```python
   async def _resolve_inference_provider(
       settings: Settings,
       provider_repo: LLMProviderRepository,
       fallback_provider_config_id: str | None,
       fallback_llm_model: str | None,
   ) -> LLMProvider | None:
       """Resolve which LLM provider+model runs the inference call per DD §9.

       Settings path (both set) → use settings.inference_provider_config_id
         + settings.inference_model. On resolution OR construction failure →
         return None (does NOT fall back to fallback path; operator
         misconfiguration is surfaced via silence + log).
       Settings partial (one set, one not) → log + None.
       Settings both unset, fallback both set → use fallback id + model.
       Fallback partial or both unset → None.
       """
       settings_id = settings.inference_provider_config_id
       settings_model = settings.inference_model
       # Pairing invariant for settings path.
       if (settings_id is None) != (settings_model is None):
           logger.warning(
               "inference: settings partial pair — inference_provider_config_id=%r "
               "inference_model=%r (both must be set or both unset)",
               settings_id, settings_model,
           )
           return None
       if settings_id is not None:
           target_id, target_model = settings_id, settings_model
       elif fallback_provider_config_id is not None and fallback_llm_model is not None:
           target_id, target_model = fallback_provider_config_id, fallback_llm_model
       else:
           return None
       try:
           config = await provider_repo.get(target_id)
       except Exception:
           logger.warning(
               "inference: provider resolution failed for id=%r",
               target_id,
               exc_info=True,
           )
           return None
       try:
           # Mirror the agent/factory.py:258-278 construction pattern.
           # Note: _PROVIDER_TYPE_MAP is currently private to agent/factory.py;
           # importing it across the connector→agent boundary is a layering smell
           # that L7 accepts (single-caller, single source-of-truth) — a future
           # refactor could lift the map to the_one/llm/registry.py if a third
           # caller emerges (YAGNI bias from agents.md).
           registry_name = _PROVIDER_TYPE_MAP[config.type]
           return get_provider(
               registry_name,
               model=target_model,
               base_url=config.base_url,
               api_key=config.api_key,
               config=config.config,
           )
       except Exception:
           logger.warning(
               "inference: provider construction failed for id=%r model=%r",
               target_id, target_model,
               exc_info=True,
           )
           return None
   ```
   Important: import `_PROVIDER_TYPE_MAP` from `the_one.agent.factory` (underscore-prefixed private; YAGNI on lifting to a shared module). Import `get_provider` from `the_one.llm` (the public re-export at `the_one/llm/__init__.py`, not directly from `the_one.llm.registry`).

7. **Implement `run_engagement_inference(...)` per Outputs step list**. Wrap the `provider.complete(...)` call in a `try/except Exception` returning False on any failure.

8. **Add tests** in `tests/test_connectors_inference.py`. Stub providers via `MockProvider(config={"response": {"content": "yes"}})`. For tests that need to inject a provider directly (bypassing the full `_resolve_inference_provider` resolution path), monkeypatch `_resolve_inference_provider` to return a pre-built MockProvider.

9. **Run targeted tests** then full suite. Update flight log under `## Leg Progress`. Check off in flight.md. Set L7 status to `landed`.

## Edge Cases

- **`session_messages` is empty** — `_filter_session_history` returns []; `_render_history_for_prompt` returns ""; the prompt template's `{filtered_session_history_as_turns}` placeholder becomes empty. The LLM sees a prompt with no history; the strong-bias-no should produce "no" for ambiguous cases. Test optional: implicit in the no-history test path.
- **Channel name with special characters** — the cache label is rendered verbatim in the prompt. No escaping. Same shape as L4's provider projection.
- **Provider returns Message with `content=None`** — `text = result.content.strip().lower()` raises AttributeError. Defensive: handle as `content = result.content or ""`. Add a test for this path (`content=None` → False).
- **Provider returns Message with `content=""`** — `text.split()` → []; `first = ""` → not "yes" → False. Safe.
- **Logger reference** — import `logger = logging.getLogger(__name__)` at module top, following the existing `_inbound.py` pattern.
- **Concurrent inference calls** — the function is stateless (no shared mutable state); concurrent calls are safe. The pool's `_get_account_cache_snapshot` takes a brief lock; multiple concurrent inference calls serialize on that lock but the lock is brief.
- **Settings caching** — pydantic BaseSettings reads env at instantiation; once `settings = Settings()` is constructed, the value is fixed for that process. Changing the env var at runtime requires a process restart. Acceptable for L7 (operator-deployment-time config).
- **Provider type not in `_PROVIDER_TYPE_MAP`** — `_resolve_inference_provider` catches the KeyError in the generic Exception handler; returns None; inference returns False. Safe default.
- **Prompt template length under huge histories** — the filter caps at last 20 messages; with typical content lengths (~200 chars per turn) the prompt stays under ~6k chars. Well below context limits for any modern LLM. Not pinned by test; design constraint is the filter cap.
- **L7 / L8 dependency direction** — L8 imports `run_engagement_inference` from `_inference`; `_inference` does NOT import from `_inbound`. No circular dependency.
- **`account` parameter as full ConnectorAccount (not just account_id)** — the function signature accepts the full row even though only `account.id` is used today. Rationale: the dispatcher (L8) already has the resolved row; passing the full row leaves room for future inference signals to read `account.config` (e.g., an inference-prompt-customization field, a per-account inference temperature). YAGNI doesn't apply to read-only fields the caller already has on hand; the cost is zero.
- **`fallback_llm_model=None` from the dispatcher** — when the routed agent has no `llm_model` configured (rare; usually defaulted at AgentConfig), the dispatcher passes None and the fallback path returns None (the function treats this as "no inference provider available"). The bot defaults to silent on non-mentioned messages, which is the F7-default mentioned-only behavior — safe and conservative.

## Files Affected

- `the_one/config.py` — ADD `inference_provider_config_id` field to Settings.
- `the_one/connectors/_inference.py` — NEW file with prompt template + helpers + `run_engagement_inference`.
- `tests/test_connectors_inference.py` — NEW file with 19 tests.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND L7 entry.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (targeted + full suite)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [ ] Commit all changes — DEFERRED per F7 flight-level commit ordering.

## Citation Audit

Citations verified against current code at design time via the F7 L7 reconnaissance pass:

- `the_one/config.py:Settings` (verified — BaseSettings, env-backed, no DB persistence).
- `the_one/db/repositories.py:LLMProviderRepository.get` (verified — raises KeyError on miss).
- `the_one/agent/factory.py:122-129` (verified — `_PROVIDER_TYPE_MAP`).
- `the_one/agent/factory.py:258-278` (verified — provider construction pattern).
- `the_one/llm/base.py:LLMProvider.complete` (verified — `(messages, tools, temperature, max_tokens)`).
- `the_one/connectors/__init__.py:OPERATOR_VISIBILITY` (verified — string `"operator"`).
- `the_one/connectors/post_step_metadata.py:resolve_channel_name` (verified — L3 addition).
- `the_one/connectors/_pool.py:_get_account_cache_snapshot` (verified — L3 pattern).
- `the_one/llm/mock.py:MockProvider` (verified — test-pattern precedent at `_connector_dispatch_helpers.py`).
- DD §9 prompt template text — preserved verbatim per the flight design.
