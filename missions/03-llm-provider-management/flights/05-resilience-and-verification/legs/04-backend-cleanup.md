# Leg: backend-cleanup

**Status**: completed
**Flight**: [Resilience & Verification](../flight.md)

## Objective

Bundle five small cleanup items that don't interact with each other: remove the misleading `OllamaProvider` model default, switch the masked-API-key check from a fragile `startswith("***")` to a `__MASKED__` sentinel, normalize `test_provider` error handling, fix two pre-existing test-collection errors, and apply `ruff format` to `the_one/interfaces/web/app.py` to clear the drift Leg 02 deferred.

## Context

Flight 05 lists these five items in its Checkpoints and design decisions:

> - bannerEl refactored to dedicated boolean state flag *(handled in Leg 03)*
> - **OllamaProvider default removed**
> - **Masked API key uses `__MASKED__` sentinel**
> - **test_provider error handling clarified (keep 200-with-status for expected errors, HTTPException for unexpected failures)**
> - **workspace/test_agent.py collection error resolved**

A second collection error was discovered during flight prerequisite verification — `tests/test_tool_registry.py:7` imports `from tests.conftest import StubTool`, but `tests/` is not a Python package (`tests/__init__.py` does not exist), so the import fails. Sibling tests in the same directory (e.g. `test_session_lifecycle.py:16`) successfully use `from conftest import FakeLLM` — that's the codebase convention. The `tests.conftest` form is the bug. Adding this fix to the cleanup leg.

A third item carried over from Leg 02's debrief: `ruff format --check the_one/interfaces/web/app.py` is currently failing on `main` due to pre-existing drift in regions Leg 02 did not modify. Leg 02 deliberately did not fold a global `ruff format` pass into its scope ("only check, don't aggressively reformat unrelated regions"). This leg picks that up — it's the natural home for a one-shot format pass.

### Design notes

**OllamaProvider default**: `the_one/llm/ollama_provider.py:24` declares `model: str = "qwen2.5:7b"`. The `AgentConfig` is the source of truth for model selection; the constructor default is a misleading fallback that masks configuration errors. Change to `model: str = ""`. If anyone constructs an `OllamaProvider` without specifying a model, Ollama will return a clear error rather than silently using `qwen2.5:7b`.

**Masked API key sentinel**: `the_one/interfaces/web/api.py:457` checks `incoming_key.startswith("***")`. A real API key starting with `***` would be silently discarded. Switch to a sentinel value `"__MASKED__"` — no real key will ever be that exact string. Frontend (`admin.js`) sends `"__MASKED__"` when the user hasn't modified the API-key field; backend checks `incoming_key == "__MASKED__"`.

The frontend pre-fills the edit form's API-key input with the masked display value (current behavior, see `admin.js:480`). The cleanest way to detect "user didn't touch the field" is: capture the pre-filled value on form open, compare on submit, and substitute `"__MASKED__"` if equal.

**test_provider error normalization**: `the_one/interfaces/web/api.py:534-535` catches all exceptions as `{"status": "error", "detail": str(e)}` (HTTP 200). Per the flight design decisions: expected errors (connection failures, auth failures, HTTP errors from the upstream provider) should keep returning 200 with `status: "error"` so the frontend's "Test Connection" button can render a friendly message inline. Unexpected errors (programming errors, missing imports, internal failures) should bubble up as HTTP 500 so they're visible in logs and don't masquerade as user-fixable issues.

The taxonomy:
- **Expected** (200 with status:error): `httpx.HTTPError` and subclasses (`ConnectError`, `TimeoutException`, `HTTPStatusError`); `openai.OpenAIError` and subclasses (`AuthenticationError`, `APIConnectionError`, `APIError`); `anthropic.AnthropicError` and subclasses.
- **Unexpected** (HTTP 500): everything else (`ImportError`, `AttributeError`, `KeyError`, generic `Exception`).

**workspace/test_agent.py**: The file has 4 lines and references an undefined `run_tests`, but the actual collection failure is even more fundamental — pytest cannot import the file because it has the same basename as `tests/test_agent.py`, causing an "import file mismatch" error. Excluding `workspace/` from collection resolves both the basename collision and the undefined-symbol issue. The directory is agent scratch space and should not be discovered by the test runner. Add a pyproject `tool.pytest.ini_options.norecursedirs` setting.

**tests/test_tool_registry.py import**: change `from tests.conftest import StubTool` to `from conftest import StubTool` to match the existing convention (`tests/test_session_lifecycle.py:16` already uses this form).

**ruff format on app.py**: Run `ruff format the_one/interfaces/web/app.py` once. The diff should consist entirely of whitespace/wrapping changes, no behavioral edits.

## Inputs

What exists before this leg:

- Branch `flight/05-resilience-and-verification` with uncommitted changes from legs 01-03 in the working tree.
- `the_one/llm/ollama_provider.py:24` — `model: str = "qwen2.5:7b"` default.
- `the_one/interfaces/web/api.py`:
  - `update_provider` handler around line 445-462 — uses `startswith("***")` check at line 457.
  - `test_provider` handler around line 499-537 — generic `except Exception`.
- `the_one/interfaces/web/static/js/areas/admin.js`:
  - Form-rendering at line 480 — pre-fills `apiKeyValue` from `provider.api_key` (the masked GET response).
  - Form-submit at line 592-601 — sends `api_key: apiKey` directly.
- `tests/test_tool_registry.py:7` — broken import.
- `workspace/test_agent.py` — broken self-mod artifact (4 lines).
- `pyproject.toml:[tool.pytest.ini_options]` — currently has `asyncio_mode = "auto"`, `addopts = "-m 'not live'"`, `markers = [...]`. No `norecursedirs` or `collect_ignore`.
- `the_one/interfaces/web/app.py` — pre-existing format drift per Leg 02's debrief.
- `the_one/agents.md:70` — the line that mentions `qwen2.5:7b default` (one-line update needed to reflect the OllamaProvider change).

## Outputs

What exists after this leg completes:

- `the_one/llm/ollama_provider.py` — `model: str = ""` (default removed).
- `the_one/interfaces/web/api.py`:
  - `update_provider` checks `incoming_key == "__MASKED__"` instead of `startswith("***")`.
  - `test_provider` distinguishes expected upstream errors (200 with `status: "error"`) from unexpected internal errors (HTTP 500 via `HTTPException`).
- `the_one/interfaces/web/static/js/areas/admin.js`:
  - Form captures the originally pre-filled API-key value on open.
  - On submit, if the input value is unchanged from the pre-filled value, the payload's `api_key` is replaced with `"__MASKED__"`.
- `tests/test_tool_registry.py:7` — `from conftest import StubTool`.
- `pyproject.toml` — `[tool.pytest.ini_options]` excludes `workspace/` from collection (via `norecursedirs` or equivalent).
- `the_one/interfaces/web/app.py` — formatted by `ruff format`.
- `the_one/agents.md` — line 70 updated (drop `qwen2.5:7b default` mention).
- `pytest -q` runs cleanly with **zero collection errors** and the full suite green.

## Acceptance Criteria

- [x] `the_one/llm/ollama_provider.py:24` declares `model: str = ""` (empty string default). All other constructor parameters and behavior unchanged.
- [x] No production or test caller constructs `OllamaProvider()` directly (verified during design review: the only sites are `the_one/llm/ollama_provider.py` itself — the class declaration and the registry call). Verify with `grep -rn "OllamaProvider(" tests/ the_one/` once before and once after the change; expected output shows only the source-file matches. If any new caller has appeared in the working tree, update it to pass an explicit `model=""` or a real model string.
- [x] `the_one/interfaces/web/api.py:457` (the `update_provider` handler) replaces `if incoming_key and incoming_key.startswith("***"):` with `if incoming_key == "__MASKED__":`. Behavior on the unchanged-key path is identical (preserves `existing.api_key`).
- [x] **`tests/test_provider_api.py::TestProviderAPI::test_update_preserves_masked_key` (lines 186-216) is updated** to send `"__MASKED__"` instead of `"***...9999"` in the PUT payload (line 206). Without this fix, the test silently keeps passing under the new sentinel — the literal string `"***...9999"` would be stored verbatim as the new key, then re-masked on read, producing identical-looking output but a corrupted stored value. The updated test must additionally verify the round-trip stored value: after the PUT, the masked GET response is `"***...9999"` (matching the ORIGINAL `"sk-mysecretkey9999"`'s mask, NOT the literal string that was sent). Optionally add a parallel test that sends a NEW key (e.g. `"sk-newkey7777"`) and verifies the masked GET response shows `"***...7777"` (the new key's mask, confirming the non-sentinel path actually replaces the key).
- [x] `the_one/interfaces/web/static/js/areas/admin.js`:
  - On form open, captures the pre-filled API-key input value into a closure-scoped variable (e.g. `var originalMaskedApiKey = apiKeyValue;`).
  - On submit, if the input's current value equals `originalMaskedApiKey` AND the form is in edit mode AND the original value is non-empty, the payload's `api_key` is set to `"__MASKED__"`. Otherwise the value is sent as-is.
  - Create-mode submits are unaffected (no pre-filled value to compare against).
  - The string `"__MASKED__"` appears as a single literal in the file — define it as a `const` near the top of the form-rendering function or inline at the comparison site (whichever matches the file's existing style; the codebase uses `var` everywhere, so `var MASKED_SENTINEL = '__MASKED__';` is fine).
- [x] `the_one/interfaces/web/api.py` `test_provider` handler is restructured so:
  - Expected upstream-failure exceptions are caught and returned as `{"status": "error", "detail": str(e)}` with HTTP 200. Specifically catch: `httpx.HTTPError` (covers `httpx.ConnectError`, `httpx.TimeoutException`, `httpx.HTTPStatusError`), and any provider-specific exceptions raised by the openai/anthropic clients during normal failure modes (use a single broad catch for `openai.OpenAIError` if importable, similarly `anthropic.AnthropicError`).
  - Unexpected exceptions (anything not in the expected list) raise `HTTPException(status_code=500, detail=str(e))`. Use a final `except Exception as e: raise HTTPException(...)` after the expected-error handlers.
  - The structure should be: per-provider `try/except` with the right exception classes per provider type, plus an outer fallback `except Exception` that maps to 500.
  - Exact exception class lookup is allowed to use a runtime `getattr` on `openai`/`anthropic` modules to avoid hard imports at the top of the file (the modules are already imported lazily inside each branch).
- [x] `tests/test_tool_registry.py:7` reads `from conftest import StubTool` (matches the convention in `tests/test_session_lifecycle.py:16`). The collection error disappears.
- [x] `workspace/` directory is excluded from pytest collection. Implement via `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  addopts = "-m 'not live'"
  markers = ["live: marks tests that call real LLM APIs (deselect with '-m \"not live\"')"]
  norecursedirs = ["workspace", ".worktrees", "node_modules", ".git"]
  ```
  Use the `norecursedirs` key (preferred over `collect_ignore_glob` because pyproject support is more idiomatic). Confirm pytest still finds all `tests/*.py` after the change.
- [x] `pytest -q` (with no `--ignore` flags) runs cleanly: **zero collection errors**, all tests pass except the 8 `live`-marked deselected ones. Approximate target: ~325-340 passed, 8 deselected — exact count varies based on tests added across legs 01-04 in this flight.
- [x] `ruff check` is clean for: `the_one/llm/ollama_provider.py`, `the_one/interfaces/web/api.py`, `tests/test_tool_registry.py`. (admin.js is JS — no ruff.)
- [x] `ruff format the_one/interfaces/web/app.py` is run once and committed (as part of the leg's working-tree changes). After running, `ruff format --check the_one/interfaces/web/app.py` is clean. Verify the diff is whitespace-only — no logic changes. If the format pass produces non-trivial logical changes, STOP and escalate.
- [x] `ruff format --check the_one/interfaces/web/api.py` and `ruff format --check the_one/interfaces/web/app.py` and `ruff format --check the_one/llm/ollama_provider.py` and `ruff format --check tests/test_tool_registry.py` and `ruff format --check pyproject.toml` (toml not formatted by ruff — skip the pyproject check) are all clean.
- [x] `the_one/agents.md:70` updated to remove the `qwen2.5:7b default` mention. Suggested replacement: `| `ollama_provider.py` | `OllamaProvider` | Local Ollama and OpenAI-compatible servers; model selection comes from agent config |`.

## Verification Steps

- `grep -rn "OllamaProvider(" tests/ the_one/` — review each construction site.
- `pytest -q` — must show zero collection errors and full suite green minus `live` markers.
- `pytest tests/test_tool_registry.py -v` — collects and runs; previously failed at collection.
- `pytest --collect-only -q workspace/` — should report no tests collected (the directory is excluded).
- `ruff check the_one/llm/ollama_provider.py the_one/interfaces/web/api.py tests/test_tool_registry.py the_one/interfaces/web/app.py` — clean.
- `ruff format --check the_one/llm/ollama_provider.py the_one/interfaces/web/api.py the_one/interfaces/web/app.py tests/test_tool_registry.py` — clean.
- Manual API smoke (deferred to HAT, not required here): edit a provider via the Admin UI without changing the API key, verify the existing key is preserved (round-trip via the masked sentinel works).
- Manual API smoke (deferred to HAT): hit `POST /api/providers/{id}/test` with a wrong API key — confirm 200 with `status: "error"`. Hit it after manually breaking an internal import — confirm 500 (only achievable in dev with intentional sabotage).

## Implementation Guidance

1. **OllamaProvider default**:
   ```python
   def __init__(
       self,
       model: str = "",
       base_url: str = "http://localhost:11434/v1",
       **kwargs: Any,
   ):
   ```
   Search for existing `OllamaProvider()` constructions and update any that relied on the default. Most callers already pass a model explicitly via `AgentFactory`.

2. **agents.md doc update**: line 70 — replace the table cell description.

3. **Masked API key sentinel — backend**: in `the_one/interfaces/web/api.py:457`:
   ```python
   if incoming_key == "__MASKED__":
       data["api_key"] = existing.api_key
   ```
   Define a module-level constant near the other constants (`_MASK_PREFIX` if one exists, or just inline — look at existing style):
   ```python
   _MASKED_API_KEY_SENTINEL = "__MASKED__"
   ```
   Use the constant in the comparison: `if incoming_key == _MASKED_API_KEY_SENTINEL:`.

4. **Masked API key sentinel — frontend**: the simplest scope-correct approach is to compute `originalMaskedApiKey` directly inside `wireProviderFormEvents` (around line 522), where `provider` is in scope, rather than threading it through from `renderProviderForm`. The two functions are siblings; `renderProviderForm` already reads `provider.api_key` at line 480 and the same value is available at submit time without re-derivation:
   ```javascript
   // Inside wireProviderFormEvents, near the top of the submit handler:
   var MASKED_SENTINEL = '__MASKED__';
   var originalMaskedApiKey = isEdit ? (provider.api_key || '') : '';

   // Then in the submit-handler body around line 593-600:
   var apiKeyInput = contentEl.querySelector('[data-field="api_key"]');
   var apiKey = apiKeyInput ? apiKeyInput.value : null;
   if (!apiKey) apiKey = null;
   // If editing and the user did not modify the pre-filled (masked) value, send the sentinel
   if (isEdit && originalMaskedApiKey && apiKey === originalMaskedApiKey) {
     apiKey = MASKED_SENTINEL;
   }
   ```
   No changes needed in `renderProviderForm`; the existing line 480 stays as-is.

5. **test_provider error normalization**: refactor the existing `try/except Exception`. Note: the per-branch `try/except` for openai/anthropic is kept for readability (each branch handles its own provider's expected error type close to the call). Both `openai.OpenAIError` and `anthropic.AnthropicError` exist in the pinned versions (openai 2.32.0, anthropic 0.79.0). Add `except HTTPException: raise` before the generic `except Exception` so any future `HTTPException` raised inside the body bubbles up unmolested:
   ```python
   @router.post("/providers/{provider_id}/test")
   async def test_provider(provider_id: str) -> dict[str, Any]:
       repo = await _provider_repo()
       try:
           provider = await repo.get(provider_id)
       except KeyError:
           raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

       try:
           if provider.type == "ollama":
               base = ollama_api.strip_v1(provider.base_url)
               async with httpx.AsyncClient(timeout=10) as client:
                   resp = await client.get(f"{base}/api/tags")
                   resp.raise_for_status()
               return {"status": "ok", "detail": "Connected to Ollama"}
           elif provider.type == "openai-compatible":
               async with httpx.AsyncClient(timeout=10) as client:
                   resp = await client.get(
                       f"{provider.base_url.rstrip('/')}/models",
                       headers=_auth_headers(provider.api_key),
                   )
                   resp.raise_for_status()
               return {"status": "ok", "detail": "Connected"}
           elif provider.type == "openai":
               import openai
               try:
                   client = openai.AsyncOpenAI(api_key=provider.api_key)
                   await client.models.list()
                   return {"status": "ok", "detail": "Connected to OpenAI"}
               except openai.OpenAIError as e:
                   return {"status": "error", "detail": str(e)}
           elif provider.type == "anthropic":
               import anthropic
               try:
                   client = anthropic.AsyncAnthropic(api_key=provider.api_key)
                   await client.models.list()
                   return {"status": "ok", "detail": "Connected to Anthropic"}
               except anthropic.AnthropicError as e:
                   return {"status": "error", "detail": str(e)}
           return {"status": "error", "detail": f"Unknown provider type: {provider.type}"}
       except httpx.HTTPError as e:
           # Expected: connection/timeout/HTTP-status from upstream
           return {"status": "error", "detail": str(e)}
       except HTTPException:
           # Pass through anything we explicitly raised (currently none in this body,
           # but future-proof so unexpected re-wrapping can't happen).
           raise
       except Exception as e:
           # Unexpected: surface as 500 so it's visible in logs, not a user-fixable issue
           raise HTTPException(status_code=500, detail=str(e))
   ```
   Note: the openai/anthropic error catches are inline (per-branch) because the exception classes are imported lazily inside those branches. The outer `except httpx.HTTPError` catches the ollama/openai-compatible paths' connection errors.

6. **tests/test_tool_registry.py import fix** — one line:
   ```python
   from conftest import StubTool
   ```

7. **pyproject.toml `norecursedirs`**: in `[tool.pytest.ini_options]`, add a `norecursedirs` line. Preserve the existing keys:
   ```toml
   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   addopts = "-m 'not live'"
   markers = ["live: marks tests that call real LLM APIs (deselect with '-m \"not live\"')"]
   norecursedirs = ["workspace", ".worktrees", "node_modules", ".git"]
   ```

8. **Run `ruff format the_one/interfaces/web/app.py`** as a single command. Inspect the diff with `git diff the_one/interfaces/web/app.py` — verify the changes are whitespace/wrapping only. If there's any line-of-code change beyond formatting, escalate.

9. **Run the full test suite** — `pytest -q` (no `--ignore` flags). Target output: zero errors, full suite passing modulo `live` deselects.

10. **Update flight log** with a Leg Progress entry. Note the test count (full suite is now collectible).

## Edge Cases

- **`OllamaProvider("")` is constructed somewhere with the empty-string default and `model` is not subsequently set**: The user gets a clear error from Ollama saying the model field is required. This is the desired behavior — fail loudly rather than silently load `qwen2.5:7b`.
- **A real API key happens to equal `__MASKED__`**: Astronomically unlikely; documented as not a concern. (The current `***`-prefix check has the same theoretical exposure but with much higher prior probability.)
- **User clears the API-key input completely on edit**: The frontend's existing `if (!apiKey) apiKey = null;` (line 594) sets it to `null`. The backend's update path applies `data["api_key"] = null`, which clears the stored key. This leg does not change that behavior — clearing the field is an explicit user action and should propagate.
- **User pastes a NEW key that happens to match the previously-masked display**: Vanishingly unlikely (the masked display has the exact form `***...{last_4}` per `_mask_api_key`), but if it happens, the sentinel substitution fires and the old key is preserved instead of the new key. Acceptable — this is a UX corner case, not a security issue.
- **`test_provider` with an `httpx.HTTPStatusError`**: `raise_for_status()` raises this for 4xx/5xx upstream responses. The leg's catch covers it via the `httpx.HTTPError` superclass.
- **`ImportError` on `import openai` or `import anthropic` inside a branch**: Falls through to `except Exception` → HTTP 500. Correct — the user can't fix a missing dependency from the UI.
- **`workspace/` excluded but tests inside it are needed**: Out of scope. The directory is agent scratch space; if a future flight needs to test agent self-modification artifacts, it can override the exclusion.
- **`ruff format` on `app.py` produces a logical change**: Stop and escalate. This must be whitespace-only.

## Files Affected

- `the_one/llm/ollama_provider.py` — drop default model.
- `the_one/interfaces/web/api.py` — masked-key sentinel + test_provider error normalization.
- `the_one/interfaces/web/app.py` — `ruff format` pass only (no logical changes).
- `the_one/interfaces/web/static/js/areas/admin.js` — frontend masked-key sentinel (changes confined to `wireProviderFormEvents`).
- `tests/test_tool_registry.py` — import fix.
- `tests/test_provider_api.py` — update `test_update_preserves_masked_key` to use the new sentinel; optionally add a parallel test for the new-key-replacement path.
- `pyproject.toml` — `norecursedirs` for pytest.
- `the_one/agents.md` — line 70 doc update.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing — `pytest -q` shows zero collection errors and the full suite green minus `live` deselects
- [x] `ruff check` and `ruff format --check` clean for all touched Python files
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off the leg in flight.md yet
- [x] Do NOT commit — Mission Control batches review and commit at end of flight
