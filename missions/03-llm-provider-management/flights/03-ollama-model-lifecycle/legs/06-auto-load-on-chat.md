# Leg: auto-load-on-chat

**Status**: completed
**Flight**: [Ollama Model Lifecycle](../flight.md)

## Objective

When a conversation starts with an unloaded Ollama model, automatically load it and show a "Loading model..." indicator in chat.

## Context

- Session creation happens in `_create_session()` (app.py ~line 104-140), which calls `factory.create(agent_name)`
- The first LLM call happens in `_process_and_broadcast()` (app.py ~line 226-301) via `agent.step(user_input)`
- The WebSocket is subscribed to the session before `_process_and_broadcast` runs, so system messages can be sent
- AgentFactory resolves `provider_config_id` to an `LLMProviderConfig` (which has `type` and `base_url`) but doesn't expose this info outside
- `ollama_api.list_running()` checks loaded models; `ollama_api.load_model()` triggers loading
- System messages use format: `{"type": "system", "content": "..."}`
- The flight spec says: "AgentFactory remains provider-agnostic" -- the auto-load check goes in the session layer

## Inputs

- `the_one/interfaces/web/app.py` -- `_create_session()` and `_process_and_broadcast()`
- `the_one/agent/factory.py` -- `AgentFactory.create()`
- `the_one/agent/config.py` -- `AgentConfig` with `provider_config_id` and `llm_model`
- `the_one/llm/ollama_api.py` -- `list_running()` and `load_model()`
- `the_one/db/repositories.py` -- `LLMProviderRepository`

## Outputs

- `the_one/interfaces/web/app.py` -- auto-load logic before first LLM call
- Tests for the auto-load behavior

## Acceptance Criteria

- [ ] When a message is sent and the agent's provider is ollama-type, check if the model is loaded via `ollama_api.list_running()`
- [ ] If model is not loaded, send `{"type": "system", "content": "Loading model..."}` to all session subscribers
- [ ] Trigger `ollama_api.load_model()` and wait for it to complete before proceeding to the LLM call
- [ ] If model is already loaded, skip the check silently (no loading message)
- [ ] Non-ollama providers skip the check entirely
- [ ] AgentFactory remains unchanged (provider-agnostic)
- [ ] Loading errors are caught and surfaced as system messages (don't crash the session)
- [ ] Existing tests pass, new tests cover the auto-load path
- [ ] No ruff violations

## Verification Steps

- `cd ~/projects/the-one && python -m pytest tests/ -x --timeout=30`
- `cd ~/projects/the-one && ruff check the_one/`

## Implementation Guidance

1. **Add auto-load check in `_process_and_broadcast()`**
   - At the start of the function, before the `agent.step()` call
   - Look up the agent's provider config: get `provider_config_id` from the agent's config, fetch the `LLMProviderConfig` from the DB
   - If `provider_config.type == "ollama"`:
     - Call `ollama_api.list_running(provider_config.base_url)`
     - Check if the agent's `llm_model` appears in the running models list
     - If not loaded:
       - Send `{"type": "system", "content": "Loading model..."}` to session
       - Call `await ollama_api.load_model(base_url, model)`
       - The load may take seconds to minutes depending on model size
   - Wrap in try/except -- if the check fails, log and proceed (don't block chat)

2. **Access agent config from session**
   - The `Session` object has an `agent` attribute. The agent has `config` or we need to store the provider config info somewhere accessible
   - Option A: Store `provider_config_id` and `llm_model` on the Session object during creation
   - Option B: Look up the agent config from the agent store using the session's agent_name
   - Option C: Store the resolved `LLMProviderConfig` on the Session
   - Choose the simplest option that doesn't change AgentFactory. Option B (re-read from agent store) is cleanest since it uses existing patterns

3. **Model name matching**
   - Ollama running models have a `name` field (e.g., `qwen2.5:7b`)
   - The agent's `llm_model` should match -- compare directly
   - Handle case where model name includes/excludes the `:latest` tag

4. **Only check on first message or when model might have changed**
   - Simple approach: check on every message (the `/api/ps` call is fast, ~<50ms)
   - The loaded state may change between messages (Ollama auto-unloads after keep_alive expires)
   - Don't cache -- always check fresh

5. **Tests**
   - Test auto-load triggers when model is not in running list
   - Test auto-load skips when model is already loaded
   - Test non-ollama provider skips check entirely
   - Test error handling when ollama is unreachable

## Edge Cases

- **Ollama unreachable**: Catch connection error, log warning, proceed to LLM call (it will fail with its own error)
- **Model name mismatch**: `qwen2.5:7b` vs `qwen2.5:7b-instruct` -- exact match only, don't try fuzzy matching
- **Multiple concurrent sessions**: Each session checks independently, Ollama handles concurrent load requests gracefully
- **Model already loading from another session**: Ollama serializes loads, the second call will wait until the first completes

## Files Affected

- `the_one/interfaces/web/app.py` -- auto-load logic in `_process_and_broadcast()`
- `tests/` -- new tests for auto-load behavior

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Commit all changes together (code + artifacts)
