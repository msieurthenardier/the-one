# Leg: first-start-and-model-default

**Status**: completed
**Flight**: [Agent Integration & Hardening](../flight.md)

## Objective

Show a non-blocking banner in Chat when no providers are configured, and remove the hardcoded `qwen2.5:7b` model default so new agents start with an empty model field.

## Context

- The mission success criterion requires first-start guidance when no providers are configured
- Currently, creating a chat session with no providers silently fails or shows a generic error (handled by Leg 3's graceful error catching)
- `AgentConfig.llm_model` defaults to `"qwen2.5:7b"` — inappropriate for users who don't use that model
- The DB schema also defaults `llm_model` to `'qwen2.5:7b'` in CREATE TABLE statements
- Studio already has a "Choose a model" placeholder in the dropdown — handles empty model gracefully
- The `ollama_provider.py` constructor default of `"qwen2.5:7b"` is a provider-level fallback and should remain (it's only used if someone constructs a provider without specifying a model)

## Inputs

- `the_one/interfaces/web/static/js/areas/chat.js` — WebSocket connect flow, content DOM
- `the_one/agent/config.py` — `AgentConfig.llm_model` default (line 77)
- `the_one/db/schema.py` — schema v4 CREATE TABLE defaults (lines 30, 141)
- `the_one/db/repositories.py` — fallback on read (line 102)
- Tests referencing the default

## Outputs

- Chat area shows a banner when no providers are configured
- Model default is empty string throughout the stack
- Banner dismisses automatically when providers become available

## Acceptance Criteria

- [ ] Chat area shows a styled banner "No providers configured — set one up in Admin to start chatting" when `/api/providers` returns an empty list
- [ ] Banner appears on initial connect and when switching to Chat via activate()
- [ ] Banner disappears when providers become available (checked on activate)
- [ ] `AgentConfig.llm_model` default changed from `"qwen2.5:7b"` to `""`
- [ ] DB schema defaults changed from `'qwen2.5:7b'` to `''` in both CREATE TABLE statements
- [ ] Repository fallback changed from `"qwen2.5:7b"` to `""` when reading agents
- [ ] All existing tests pass (update test assertions for new default)

## Verification Steps

- `grep -rn "qwen2.5:7b" the_one/` should only match `ollama_provider.py` (constructor default)
- `python -m pytest tests/ --timeout=30 -x -q` passes
- Manually: start with no providers → see banner → add provider → switch to Chat → banner gone

## Implementation Guidance

1. **Add first-start banner to `chat.js`**:
   - Add a `checkProviders()` function that fetches `/api/providers` and shows/hides a banner
   - Banner DOM: a div with class `chat-no-providers` inside the messages area (or above it), containing the message text
   - Call `checkProviders()` in the `onopen` handler after setting status to "connected"
   - Also call `checkProviders()` in the `activate()` method
   - If providers exist, remove the banner (if present) — use a module-scoped reference
   - If no providers, show the banner and optionally disable the input

2. **Add banner CSS** to `styles.css`:
   - `.chat-no-providers` — centered, muted color, padding, distinct from message bubbles

3. **Change model default** in `config.py`:
   - `llm_model: str = ""` (line 77)

4. **Change schema defaults** in `schema.py`:
   - Line 30: `llm_model TEXT DEFAULT ''`
   - Line 141: `llm_model TEXT DEFAULT ''`
   - Note: This only affects new databases. Existing databases keep their current values.

5. **Change repository fallback** in `repositories.py`:
   - Line 102: `llm_model=row["llm_model"] or ""` (was `or "qwen2.5:7b"`)

6. **Update tests**:
   - `test_config.py:19` — change assertion from `"qwen2.5:7b"` to `""`
   - `test_schema.py` — do NOT change `_LEGACY_SCHEMA_V1` — it's a historical fixture for migration tests
   - Test data in `test_auto_load.py`, `test_provider_api.py`, `test_ollama_api.py` should NOT change — these use the model name as test fixture data, not as defaults

## Edge Cases

- **Existing databases**: Schema migration is not needed — existing agents keep their current `llm_model` values. Only new agents get empty default.
- **OllamaProvider constructor**: Keeps `model: str = "qwen2.5:7b"` as a provider-level fallback — this is appropriate for the provider's own default, separate from agent config.
- **Banner with existing sessions**: If sessions exist but no providers, banner should still show (sessions would fail to chat anyway).

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat.js` — First-start banner
- `the_one/interfaces/web/static/styles.css` — Banner styling
- `the_one/agent/config.py` — Model default change
- `the_one/db/schema.py` — Schema default change
- `the_one/db/repositories.py` — Read fallback change
- `tests/test_config.py` — Updated assertion
