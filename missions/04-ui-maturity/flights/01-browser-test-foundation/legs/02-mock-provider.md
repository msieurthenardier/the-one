# Leg: 02-mock-provider

**Status**: completed
**Flight**: [Browser Test Foundation](../flight.md)

## Objective

Add a fifth provider type `mock` to the LLM provider system, gated by a new `THE_ONE_DEV_MODE` env var. The mock provider returns deterministic scripted responses, has no external dependencies, and serves both browser tests and offline dev work. UI exposes the new type only when dev mode is on; backend rejects `mock`-typed creates and updates when dev mode is off.

## Context

- Subsequent legs (03-08) use this `mock` type to drive deterministic browser tests against the real app. No HTTP-level stubbing of Ollama needed.
- The flight design (see `flight.md` "LLM determinism — `mock` provider type" section) calls out specific implementation surface across `llm/`, `agent/`, `db/`, `interfaces/web/`, `config.py`, and `admin.js`.
- **Leg 01 outcome**: pytest now uses `--import-mode=importlib` and `pythonpath = ["tests"]`. New tests added in this leg should use absolute imports (e.g., `from the_one.llm.mock import MockProvider`) and follow the bare-`conftest` import pattern only if needed for `FakeLLM`/`StubTool` (this leg's tests probably won't need them).
- M03 debrief flagged a "provider type extension checklist" implicit in the codebase. This leg is the first time that checklist is exercised after M03; if anything is missing or surprising, capture it in the flight log so `the_one/agents.md` can be updated in leg 08 documentation.

## Inputs

- Branch `flight/01-browser-test-foundation`, leg 01 landed (uncommitted; flight uses single-commit-at-end pattern)
- Existing files in their pre-leg state:
  - `the_one/llm/base.py` — `LLMProvider` ABC, `Message`, `ToolCall` (no changes needed)
  - `the_one/llm/registry.py:24-37` — `_try_load_builtin` with `loaders` dict
  - `the_one/llm/ollama_provider.py` — pattern to mirror
  - `the_one/agent/factory.py:15-20` — `_PROVIDER_TYPE_MAP`
  - `the_one/db/models.py:20` — provider type `Literal[...]`
  - `the_one/config.py` — `Settings` class (env_prefix `THE_ONE_`)
  - `the_one/interfaces/web/api.py:420-604` — provider CRUD endpoints
  - `the_one/interfaces/web/static/js/areas/admin.js:22-41` — hardcoded `PROVIDER_TYPES`, `TYPE_DEFAULTS`, `TYPE_BADGE_COLORS`
- Test baseline: 336 passed, 9 deselected (post-leg-01)

## Outputs

**Production code**:
- `the_one/llm/mock.py` (new, ~50-80 LOC) — `MockProvider` class, registers itself with `register_provider("mock", MockProvider)` at module bottom (matches `ollama_provider.py:114` pattern)

**Out of scope for this leg** (intentional non-goals to keep scope contained):
- Admin UI for editing mock provider's `config` (scripted responses, model list). The Add Provider form creates mock providers with default `config={}`. Tests/seeders that need scripted responses POST `config` directly via the API. UI for editing mock-provider scripted responses (would require a JSON editor widget) is out of scope — flag for a later flight if the need emerges.
- A "record calls" inspection mode on `MockProvider` (à la `FakeLLM` in `tests/conftest.py:32`). Not needed for this flight's tests; revisit if leg 04+ flow tests need to verify "agent sent the right messages to the LLM".
- `the_one/llm/registry.py` — `mock` added to `loaders` dict
- `the_one/agent/factory.py` — `"mock": "mock"` added to `_PROVIDER_TYPE_MAP`
- `the_one/db/models.py` — `"mock"` added to provider type `Literal`
- `the_one/config.py` — `dev_mode: bool = False` field on `Settings`
- `the_one/interfaces/web/api.py`:
  - New `GET /api/providers/types` endpoint returning the allowed provider types based on `settings.dev_mode`
  - `create_provider` — reject `type == "mock"` when `not settings.dev_mode` (HTTP 400)
  - `update_provider` — reject when resulting `type == "mock"` and `not settings.dev_mode` (HTTP 400)
  - `test_provider` — add `mock` branch returning `{"status": "ok", "detail": "Mock provider (dev mode)"}`
  - `list_provider_models` — add `mock` branch returning models from `provider.config["models"]` (default `["mock-default"]`)
- `the_one/interfaces/web/static/js/areas/admin.js`:
  - Replace hardcoded `PROVIDER_TYPES` array with a fetch against `GET /api/providers/types` performed on area init (or first activate)
  - Add `mock` entries to `TYPE_DEFAULTS` and `TYPE_BADGE_COLORS` (always present; the dropdown filtering happens via the fetched list)

**Tests**:
- `tests/test_mock_provider.py` (new) — unit tests for `MockProvider` behavior
- `tests/test_provider_api.py` (extended) — gating tests for new `/api/providers/types` endpoint, mock-type create/update rejection, mock-type test/list_models branches

## Acceptance Criteria

### MockProvider class
- [x] `the_one/llm/mock.py` exists with `MockProvider(LLMProvider)` class
- [x] `MockProvider.name == "mock"`
- [x] `MockProvider.complete()` returns a `Message.assistant(...)` synchronously-derivable from config
  - With no config: returns content `"Mock response"` (or similar fixed default)
  - With `config["response"]` set to `{"content": "Hello"}`: returns content `"Hello"`
  - With `config["response"]` set to `{"content": "", "tool_calls": [{"id": "1", "name": "tool_a", "arguments": {"x": 1}}]}`: returns a `Message` with that tool call
- [x] `MockProvider` is registered via `register_provider("mock", MockProvider)` at module bottom
- [x] `the_one/llm/registry.py` `loaders` dict includes `"mock": lambda: __import__("the_one.llm.mock", fromlist=["_"])`

### Wiring
- [x] `the_one/agent/factory.py` `_PROVIDER_TYPE_MAP` contains `"mock": "mock"`
- [x] `the_one/db/models.py` `LLMProviderConfig.type` Literal includes `"mock"`
- [x] `the_one/config.py` `Settings` has `dev_mode: bool = False`
- [x] Setting env var `THE_ONE_DEV_MODE=true` makes `settings.dev_mode == True` (verify via a one-off test or interactive check)

### API endpoints
- [x] `GET /api/providers/types` returns 4 types (ollama, openai-compatible, openai, anthropic) when `settings.dev_mode == False`
- [x] `GET /api/providers/types` returns 5 types (above + mock) when `settings.dev_mode == True`
- [x] Each type entry has shape `{"value": "<type>", "label": "<Label>"}`
- [x] `POST /api/providers` with `type=mock` returns 400 when `settings.dev_mode == False` (detail mentions `THE_ONE_DEV_MODE`)
- [x] `POST /api/providers` with `type=mock` returns 201 when `settings.dev_mode == True`
- [x] `PUT /api/providers/{id}` changing type to `mock` returns 400 when `settings.dev_mode == False`
- [x] `POST /api/providers/{id}/test` for a mock provider returns `{"status": "ok", "detail": "Mock provider (dev mode)"}`
- [x] `GET /api/providers/{id}/models` for a mock provider with no `config["models"]` returns `[{"id": "mock-default", "name": "mock-default"}]`
- [x] `GET /api/providers/{id}/models` for a mock provider with `config={"models": ["mock-fast", "mock-thinking"]}` returns those two models

### Frontend
- [x] `admin.js` no longer has the hardcoded `PROVIDER_TYPES = [...]` literal at line ~22 — replaced by a variable populated from a `fetch('/api/providers/types')` call on area init or first activate
- [x] `TYPE_DEFAULTS` includes a `"mock"` entry: `{ base_url: '', showBaseUrl: false, showApiKey: false }` (mock has no base_url or api_key inputs in the form)
- [x] `TYPE_BADGE_COLORS` includes a `"mock"` entry with a muted gray (`'#888'` or similar)
- [x] When the app is run with `THE_ONE_DEV_MODE=true`, the provider-type dropdown shows the mock option (visible verification deferred to leg 05's flow test; for this leg, just verify the endpoint+JS wiring)
- [x] When the app is run without `THE_ONE_DEV_MODE`, the provider-type dropdown does NOT show the mock option

### Tests
- [x] `tests/test_mock_provider.py` covers: default response, scripted text response, scripted tool-call response, registry registration (`get_provider("mock")` returns a `MockProvider` instance)
- [x] `tests/test_provider_api.py` extended with: types endpoint (dev_mode on and off), create rejection, create acceptance, update rejection (changing existing provider's type to mock), test_provider mock branch, list_models mock branch (default and configured)
- [x] All new tests pass; no existing test regressions
- [x] Default `pytest tests/` passes with count `≥ 350 passed, 9 deselected` (5 mock-provider unit tests + 3 types-endpoint tests including route-ordering regression + 3 gating tests + 3 mock-route tests = 14 new tests; 336 + 14 = 350)
- [x] `pytest -m browser tests/browser/` still passes

## Verification Steps

1. **Provider class**:
   ```bash
   pytest tests/test_mock_provider.py -v
   ```
2. **API endpoints (dev_mode off)**:
   ```bash
   pytest tests/test_provider_api.py -v -k "types or mock"
   ```
3. **Settings env var**: With the app stopped, run `THE_ONE_DEV_MODE=true python -c "from the_one.config import settings; print(settings.dev_mode)"` — expect `True`. Without the env var: `False`.
4. **Full suite no regression**: `pytest tests/ --tb=short -q` — expect `>= 336+N passed, 9 deselected`
5. **Browser smoke still works**: `pytest -m browser tests/browser/ -v` — expect 1 passed
6. **Manual frontend check (optional, encouraged)**:
   - Run `THE_ONE_DEV_MODE=true python -m the_one serve` (or `the-one serve`)
   - Open http://127.0.0.1:8484 in a browser, navigate to Admin → LLM Providers → Add Provider
   - Confirm `Mock (dev)` appears in the type dropdown
   - Stop the app, restart without the env var, confirm `Mock (dev)` is gone

## Implementation Guidance

### 1. Create `the_one/llm/mock.py`

Mirror the structure of `the_one/llm/ollama_provider.py:1-87`. Constructor accepts standard kwargs (`model`, `base_url`, `api_key`, plus arbitrary `**kwargs` for forward-compat) and ALSO a `config` dict. The `config` dict is the per-provider JSON config from `LLMProviderConfig.config`.

Note: looking at `factory.py:92-97`, `get_provider()` is called with `model`, `base_url`, `api_key` — but NOT `config`. The MockProvider constructor needs the response config somehow. Two options:

- **Option A (preferred)**: Pass `config` through as another kwarg from `factory.py`. Modify `_PROVIDER_TYPE_MAP` flow to also pass `config=provider_config.config` when the type is `mock`. Changes the factory slightly but is clean.
- **Option B**: Mock has a class-level/module-level "next response" override mechanism that tests can set. Doesn't require factory changes, but is global state and feels hacky.

**Use Option A.** Update `factory.py` to pass `config=provider_config.config` always (other providers can accept and ignore it via `**kwargs`).

```python
# the_one/llm/mock.py
from __future__ import annotations

from typing import Any

from the_one.llm.base import LLMProvider, Message, ToolCall, TokenUsage
from the_one.llm.registry import register_provider


_DEFAULT_RESPONSE = {"content": "Mock response from the mock provider."}


class MockProvider(LLMProvider):
    """Deterministic LLM provider for tests and offline dev work.

    Responses are sourced from the per-provider ``config`` dict:

      config = {
        "models": ["mock-fast", "mock-thinking"],   # surfaced to /api/providers/{id}/models
        "response": {                               # what complete() returns
          "content": "Hello from mock",
          "tool_calls": [
            {"id": "1", "name": "tool_a", "arguments": {"x": 1}}
          ]
        }
      }

    If ``response`` is not set, returns a fixed default content.
    Gated at the API layer by ``THE_ONE_DEV_MODE`` — this class itself does
    not check the env var; it trusts that the only callers are paths that
    have already been gated (factory + tests).
    """

    name = "mock"

    def __init__(
        self,
        model: str = "mock-default",
        base_url: str = "",
        api_key: str | None = None,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        self.model = model
        self.config = config or {}

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        response = self.config.get("response", _DEFAULT_RESPONSE)
        content = response.get("content", "")
        tool_calls = [
            ToolCall(id=tc["id"], name=tc["name"], arguments=tc.get("arguments", {}))
            for tc in response.get("tool_calls", [])
        ]
        return Message.assistant(
            content=content,
            tool_calls=tool_calls,
            usage=TokenUsage(input_tokens=0, output_tokens=len(content.split())),
        )


register_provider("mock", MockProvider)
```

### 2. Update `the_one/llm/registry.py`

Add a `mock` entry to the `loaders` dict in `_try_load_builtin`:

```python
loaders = {
    "openai": lambda: __import__("the_one.llm.openai_provider", fromlist=["_"]),
    "anthropic": lambda: __import__("the_one.llm.anthropic_provider", fromlist=["_"]),
    "ollama": lambda: __import__("the_one.llm.ollama_provider", fromlist=["_"]),
    "mock": lambda: __import__("the_one.llm.mock", fromlist=["_"]),
}
```

Mock has no optional-extras path — the `ImportError` branch will never fire for it. That's fine; the existing error message is misleading for mock (it suggests `pip install 'the-one[mock]'`) but mock will only ImportError if the file is missing entirely, which is an actual bug. Acceptable.

### 3. Update `the_one/agent/factory.py`

Add `mock` to `_PROVIDER_TYPE_MAP`:

```python
_PROVIDER_TYPE_MAP = {
    "ollama": "ollama",
    "openai-compatible": "ollama",
    "openai": "openai",
    "anthropic": "anthropic",
    "mock": "mock",
}
```

In `AgentFactory.create()` around line 92-97, also pass `config=provider_config.config`:

```python
llm = get_provider(
    registry_name,
    model=config.llm_model,
    base_url=provider_config.base_url,
    api_key=provider_config.api_key,
    config=provider_config.config,
)
```

Other providers (`OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`) accept `**kwargs` in their constructors so the extra `config=` kwarg is safely ignored. **Verify this** before calling it done — if any provider's constructor doesn't accept `**kwargs`, add it.

### 4. Update `the_one/db/models.py`

```python
type: Literal["ollama", "openai-compatible", "openai", "anthropic", "mock"]
```

One-token change.

### 5. Update `the_one/config.py`

Add `dev_mode: bool = False` to `Settings`. Suggested placement: under the Web group near the top.

```python
class Settings(BaseSettings):
    model_config = {"env_prefix": "THE_ONE_", "env_file": ".env", "extra": "ignore"}

    # Web
    host: str = "127.0.0.1"
    port: int = 8484

    # Dev mode (gates the mock provider type)
    dev_mode: bool = False

    # Paths
    ...
```

### 6. Update `the_one/interfaces/web/api.py`

**a. New types endpoint (place near the other provider routes, e.g., right before `list_providers` at line 420):**

```python
@router.get("/providers/types")
async def list_provider_types() -> list[dict[str, str]]:
    """Return the list of provider types selectable in the UI.

    The `mock` type is included only when THE_ONE_DEV_MODE is on.
    """
    types = [
        {"value": "ollama", "label": "Ollama"},
        {"value": "openai-compatible", "label": "OpenAI-Compatible"},
        {"value": "openai", "label": "OpenAI"},
        {"value": "anthropic", "label": "Anthropic"},
    ]
    if settings.dev_mode:
        types.append({"value": "mock", "label": "Mock (dev)"})
    return types
```

**Important**: This route uses `/providers/types` which collides with the `/providers/{provider_id}` path pattern at line 427. FastAPI matches routes in registration order, so `/providers/types` MUST be registered BEFORE `/providers/{provider_id}` for it to match. Place the new route physically above line 427 in the file.

**b. Gate `create_provider` (line 437):**

```python
@router.post("/providers", status_code=201)
async def create_provider(request: Request) -> dict[str, Any]:
    data = await request.json()
    if data.get("type") == "mock" and not settings.dev_mode:
        raise HTTPException(
            status_code=400,
            detail="Mock provider type requires THE_ONE_DEV_MODE=true",
        )
    if "id" not in data:
        data["id"] = uuid.uuid4().hex[:12]
    provider = LLMProviderConfig.model_validate(data)
    repo = await _provider_repo()
    await repo.create(provider)
    return _provider_response(provider)
```

**c. Gate `update_provider` (line 448):**

The check should compare the *resulting* type, not just the incoming `data["type"]`, so that an update that doesn't change the type isn't accidentally rejected. **Place the check AFTER the `existing = await repo.get(provider_id)` line at api.py:454** (so `existing.type` is in scope for the fallback). It can go before or after the masked-key check at line 459 — order is independent.

```python
incoming_type = data.get("type", existing.type)
if incoming_type == "mock" and not settings.dev_mode:
    raise HTTPException(
        status_code=400,
        detail="Mock provider type requires THE_ONE_DEV_MODE=true",
    )
```

**d. Add `mock` branch to `test_provider` (line 502):**

Add as the FIRST type check (cheapest, no I/O):

```python
if provider.type == "mock":
    return {"status": "ok", "detail": "Mock provider (dev mode)"}
elif provider.type == "ollama":
    ...
```

**e. Add `mock` branch to `list_provider_models` (line 555):**

Add before the existing branches:

```python
if provider.type == "mock":
    models = provider.config.get("models", ["mock-default"])
    return [{"id": m, "name": m} for m in models]
elif provider.type == "ollama":
    ...
```

### 7. Update `the_one/interfaces/web/static/js/areas/admin.js`

**a. Replace the hardcoded `PROVIDER_TYPES` (line 22-27) with a fetched list:**

```javascript
// Provider type list — fetched from /api/providers/types so dev-mode gating
// for the `mock` type is enforced server-side.
var PROVIDER_TYPES = [];

function fetchProviderTypes() {
  return fetch('/api/providers/types')
    .then(function (r) { return r.json(); })
    .then(function (types) { PROVIDER_TYPES = types; });
}
```

**b. Add `mock` entries to `TYPE_DEFAULTS` and `TYPE_BADGE_COLORS` (unconditionally — these are static metadata):**

> **Why unconditional**: An existing mock provider (created when dev_mode was on) must still render correctly when dev_mode is off — the dropdown filter prevents *new* mock providers, but doesn't hide *existing* ones. If `TYPE_DEFAULTS["mock"]` were missing, viewing/editing an existing mock provider with dev_mode off would crash at `admin.js:541-548` (`defaults.showBaseUrl` access on undefined).

```javascript
var TYPE_DEFAULTS = {
  'ollama': { base_url: 'http://localhost:11434/v1', showBaseUrl: true, showApiKey: false },
  'openai-compatible': { base_url: '', showBaseUrl: true, showApiKey: true },
  'openai': { base_url: 'https://api.openai.com/v1', showBaseUrl: false, showApiKey: true },
  'anthropic': { base_url: 'https://api.anthropic.com', showBaseUrl: false, showApiKey: true },
  'mock': { base_url: '', showBaseUrl: false, showApiKey: false }
};

var TYPE_BADGE_COLORS = {
  'ollama': '#2ecc71',
  'openai-compatible': '#d4a800',
  'openai': '#4a9eff',
  'anthropic': '#9b59b6',
  'mock': '#888'
};
```

**c. Call `fetchProviderTypes()` before any code that uses `PROVIDER_TYPES`.** The simplest place: in the `init` function, kick off the fetch immediately and store the promise. Then in `renderProviderForm` and any other reader, wait on the promise (or re-fetch on render — the response is small).

Pragmatic approach: fetch on area init, refetch on `activate()`, and have `renderProviderForm()` skip rendering the type dropdown until the fetch resolves (or render with an empty list briefly — the user just sees a loading state for ~50ms).

```javascript
// At the top of the init function, before the setting/categories rendering:
var providerTypesReady = fetchProviderTypes();
```

Then in `renderProviderForm` (line 440), gate the form rendering on the promise:

```javascript
function renderProviderForm(provider) {
  providerTypesReady.then(function () {
    _renderProviderFormImpl(provider);
  });
}
```

Where `_renderProviderFormImpl` is the body of the current `renderProviderForm`. This keeps the change localized.

Alternative if simpler: fetch synchronously-blocking on the first call (using `await` inside an async function) — but admin.js is currently sync-style, so use the promise pattern.

### 8. Tests

**`tests/test_mock_provider.py`** (new file):

```python
"""Unit tests for MockProvider."""

from __future__ import annotations

import pytest

from the_one.llm import get_provider
from the_one.llm.base import Message, Role
from the_one.llm.mock import MockProvider


class TestMockProviderBehavior:
    async def test_default_response_when_no_config(self) -> None:
        provider = MockProvider(model="mock-default")
        msg = await provider.complete(messages=[Message.user("hi")])
        assert msg.role == Role.ASSISTANT
        assert "Mock" in msg.content
        assert msg.tool_calls == []

    async def test_scripted_text_response(self) -> None:
        provider = MockProvider(
            model="mock-default",
            config={"response": {"content": "Hello from script"}},
        )
        msg = await provider.complete(messages=[Message.user("hi")])
        assert msg.content == "Hello from script"
        assert msg.tool_calls == []

    async def test_scripted_tool_call_response(self) -> None:
        provider = MockProvider(
            model="mock-default",
            config={
                "response": {
                    "content": "",
                    "tool_calls": [
                        {"id": "tc1", "name": "echo", "arguments": {"text": "hi"}}
                    ],
                }
            },
        )
        msg = await provider.complete(messages=[Message.user("hi")])
        assert msg.content == ""
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].id == "tc1"
        assert msg.tool_calls[0].name == "echo"
        assert msg.tool_calls[0].arguments == {"text": "hi"}

    async def test_registry_returns_mock_provider(self) -> None:
        provider = get_provider("mock", model="mock-default")
        assert isinstance(provider, MockProvider)
        assert provider.name == "mock"

    def test_max_context_tokens_inherits_default(self) -> None:
        provider = MockProvider(model="mock-default")
        assert provider.max_context_tokens == 128_000
```

**Extend `tests/test_provider_api.py`** with a new test class. Use the existing `client` fixture pattern (line 54-81). The fixture currently does NOT patch `settings.dev_mode`; you'll need to use `monkeypatch.setattr` or `patch` on `the_one.interfaces.web.api.settings` per test.

```python
class TestProviderTypesEndpoint:
    async def test_returns_4_types_when_dev_mode_off(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = False
            resp = await client.get("/api/providers/types")
        assert resp.status_code == 200
        data = resp.json()
        values = [t["value"] for t in data]
        assert set(values) == {"ollama", "openai-compatible", "openai", "anthropic"}

    async def test_returns_5_types_when_dev_mode_on(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            resp = await client.get("/api/providers/types")
        assert resp.status_code == 200
        values = [t["value"] for t in resp.json()]
        assert "mock" in values
        assert len(values) == 5

    async def test_types_route_does_not_collide_with_id_route(
        self, client: AsyncClient
    ) -> None:
        """Regression: /providers/types must be registered before /providers/{id}.

        If route ordering is reversed, FastAPI matches /providers/types
        as a get_provider call with provider_id="types" and returns 404.
        This test pins the ordering invariant.
        """
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = False
            resp = await client.get("/api/providers/types")
        assert resp.status_code == 200, (
            "GET /providers/types returned non-200 — route may have been reordered "
            "behind /providers/{provider_id}"
        )
        # Confirm body shape — not just a 200 from some other path
        assert isinstance(resp.json(), list)


class TestMockProviderGating:
    async def test_create_mock_rejected_when_dev_mode_off(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = False
            resp = await client.post(
                "/api/providers",
                json={"name": "Mock", "type": "mock", "base_url": ""},
            )
        assert resp.status_code == 400
        assert "DEV_MODE" in resp.json()["detail"]

    async def test_create_mock_accepted_when_dev_mode_on(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            resp = await client.post(
                "/api/providers",
                json={"name": "Mock", "type": "mock", "base_url": ""},
            )
        assert resp.status_code == 201
        assert resp.json()["type"] == "mock"

    async def test_update_to_mock_rejected_when_dev_mode_off(self, client: AsyncClient) -> None:
        # Create an ollama provider first (no dev_mode required)
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = False
            create_resp = await client.post(
                "/api/providers",
                json={"name": "P", "type": "ollama", "base_url": "http://localhost:11434/v1"},
            )
            provider_id = create_resp.json()["id"]
            resp = await client.put(
                f"/api/providers/{provider_id}",
                json={"name": "P", "type": "mock", "base_url": ""},
            )
        assert resp.status_code == 400


class TestMockProviderRoutes:
    async def test_test_provider_mock_returns_ok(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            create_resp = await client.post(
                "/api/providers",
                json={"name": "M", "type": "mock", "base_url": ""},
            )
            provider_id = create_resp.json()["id"]
            resp = await client.post(f"/api/providers/{provider_id}/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "Mock" in body["detail"]

    async def test_list_models_mock_default(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            create_resp = await client.post(
                "/api/providers",
                json={"name": "M", "type": "mock", "base_url": ""},
            )
            provider_id = create_resp.json()["id"]
            resp = await client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 200
        models = resp.json()
        assert len(models) == 1
        assert models[0]["id"] == "mock-default"

    async def test_list_models_mock_configured(self, client: AsyncClient) -> None:
        with patch("the_one.interfaces.web.api.settings") as mock_settings:
            mock_settings.dev_mode = True
            create_resp = await client.post(
                "/api/providers",
                json={
                    "name": "M",
                    "type": "mock",
                    "base_url": "",
                    "config": {"models": ["mock-fast", "mock-thinking"]},
                },
            )
            provider_id = create_resp.json()["id"]
            resp = await client.get(f"/api/providers/{provider_id}/models")
        assert resp.status_code == 200
        ids = [m["id"] for m in resp.json()]
        assert ids == ["mock-fast", "mock-thinking"]
```

Note on mocking: `patch("the_one.interfaces.web.api.settings")` replaces the imported `settings` reference in api.py. The `settings.dev_mode` attribute access will then return the mocked value. Verify this by running one of the tests in isolation first.

### 9. Run verification

```bash
pytest tests/test_mock_provider.py -v --timeout=30
pytest tests/test_provider_api.py -v --timeout=30 -k "types or mock"
pytest tests/ --tb=short -q --timeout=60
pytest -m browser tests/browser/ -v --timeout=30
ruff check the_one/ tests/
ruff format --check the_one/ tests/
```

## Edge Cases

- **`test_provider_api.py` existing test for `_create_provider` helper**: line 446 has a `_create_provider` helper that posts directly without dev-mode awareness. Verify the existing tests don't accidentally try to create a `mock` provider without patching settings (a quick `grep "mock" tests/test_provider_api.py` should confirm no existing test references the mock type).

- **Provider config persistence**: When mock providers are created via the API, the `config` dict is stored as JSON in the DB. The repository handles this transparently (Pydantic serializes the model). No new migration needed.

- **`AgentFactory` calling `get_provider` with `config=`**: This is a new kwarg passed to ALL providers (ollama, openai, anthropic, mock). Verified during design review: all three existing provider constructors (`ollama_provider.py:26`, `openai_provider.py:16`, `anthropic_provider.py:16`) accept `**kwargs`, so passing the extra `config=` kwarg is safe.

- **`tests/test_factory.py:59` `_fake_get_provider`**: Verified during design review that this test double accepts `**kwargs` and won't break when the new `config=` kwarg is added. If any test asserts on `get_provider`'s exact call args (e.g., via `assert_called_with`), the `config=` kwarg must be added to the expected call. Quick grep before implementation: `grep -n "get_provider" tests/test_factory.py`.

- **Conditional dropdown rendering on slow connections**: The `fetchProviderTypes()` promise needs to resolve before the form renders. If the user clicks "Add Provider" before the fetch resolves (unlikely but possible), the form should wait gracefully. The promise-then pattern in §7c handles this.

- **JS error if `PROVIDER_TYPES` is empty when used**: There are 3 places `PROVIDER_TYPES` is read in admin.js (line 465-467 the loop in renderProviderForm, plus implicit usage). All gate through `renderProviderForm`, which is called from `renderProvidersPanel` after `providerFormMode` is set by a user action (Add or Edit click). The promise gate on `providerTypesReady` ensures the array is populated before the form renders.

- **`_PROVIDER_TYPE_MAP` test exposure**: `tests/test_factory.py` may have an assertion about `_PROVIDER_TYPE_MAP` size or contents. Quick check: `grep "_PROVIDER_TYPE_MAP" tests/`. If a test pins the dict, update it.

- **Settings field ordering**: Adding `dev_mode` shouldn't affect anything (Pydantic doesn't care about field order at the model level), but `_provider_response` and `get_settings` iterate `Settings.model_fields` — adding `dev_mode` will surface it in the `/api/settings` endpoint output (visible in Admin → General). That's harmless and arguably desirable.

## State-Machine Reachability Audit

**New state introduced**: provider type `mock`.

Lower layers that could foreclose this state:
- **Pydantic Literal validation** (`db/models.py:20`): adding `"mock"` to the Literal allows it. Without this, `model_validate` rejects.
- **`_PROVIDER_TYPE_MAP`** (`agent/factory.py:15`): without `"mock": "mock"`, `AgentFactory.create()` would raise `ValueError` on agents pointing at a mock provider.
- **Registry `loaders` dict** (`llm/registry.py:24`): without `"mock"` entry, `get_provider("mock")` would raise the misleading `ImportError("Provider 'mock' requires extra dependencies. Install with: pip install 'the-one[mock]'")`.
- **API gating logic**: must reject mock-typed creates/updates when dev_mode is off, without that the type is allowed unconditionally and the gating is meaningless.
- **Frontend dropdown**: must source from the API, not hardcode.

All five lower layers are addressed by this leg's changes. ✓

**Existing tests pinning behavior**: 
- No test asserts the *count* of provider types (verified by grep above). 
- No test references the `mock` type (none can — it doesn't exist yet).
- No FK/CASCADE concerns (provider type is a string column, not a FK).

✓ Pass.

## Cache Freshness Contract

**Cache 1 — Frontend `PROVIDER_TYPES` array (admin.js)**:
- **Source of truth**: `GET /api/providers/types` (which depends on `settings.dev_mode`)
- **Rebuild trigger**: per-area-init fetch (with optional refetch on `activate()`)
- **Maximum staleness acceptable**: until next page reload. Since `settings.dev_mode` only changes via server restart with a different env var, and any server restart breaks the WebSocket and prompts a page reload anyway, this is acceptable.
- **User-action invalidation map**: no in-app action can change the provider types list. Only server-side env var change → server restart. The page-reload triggered by WS disconnect after restart naturally re-fetches.

✓ No mismatch. The cache freshness model matches the source-of-truth's mutation cadence.

**No new in-process backend caches.**

## Files Affected

- `the_one/llm/mock.py` — new file (~80 LOC)
- `the_one/llm/registry.py` — 1-line addition to `loaders` dict
- `the_one/agent/factory.py` — 1-line addition to `_PROVIDER_TYPE_MAP`, 1-line addition to `get_provider` call (passing `config=`)
- `the_one/db/models.py` — 1-token addition to provider type Literal
- `the_one/config.py` — 1-line addition (`dev_mode: bool = False`)
- `the_one/interfaces/web/api.py` — new endpoint (~15 LOC), 4 modified endpoints (gating + mock branches, ~30 LOC total)
- `the_one/interfaces/web/static/js/areas/admin.js` — replace hardcoded array (~20 LOC change), add 2 entries to existing dicts
- `tests/test_mock_provider.py` — new file (~80 LOC, 5 tests)
- `tests/test_provider_api.py` — extended with 3 new test classes (~120 LOC, ~7 tests)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing: `pytest tests/` shows ≥ 350 passed, 9 deselected; `pytest -m browser tests/browser/` shows 1 passed
- [x] `ruff check` and `ruff format --check` clean
- [x] Update flight-log.md with leg progress entry (status, what was done, any anomalies — note any provider-type extension friction for leg 08 documentation)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off this leg in flight.md (happens at flight-level commit time per agentic-workflow protocol)
- [x] Do NOT commit (flight-level review and commit happen after the last autonomous leg)
- [x] Signal `[HANDOFF:review-needed]`
