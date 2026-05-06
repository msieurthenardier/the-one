# OpenRouter Provider Support — Design

**Date:** 2026-05-06
**Status:** Approved (brainstorming complete; awaiting implementation plan)

## Summary

Add OpenRouter (https://openrouter.ai) as a first-class LLM provider type, and fix a latent bug in the existing `openai-compatible` path that swallows `api_key` and prevents authenticated use against any OpenAI-compatible server (Together, Groq, Fireworks, DeepInfra, OpenRouter via the generic path, etc.).

OpenRouter is OpenAI-API-compatible and routes to ~300 hosted models from many vendors. The integration uses the official OpenAI SDK with a custom `base_url`, optional ranking headers (`HTTP-Referer`, `X-Title`), and a model-discovery endpoint that returns per-model metadata including a `supported_parameters` array (which exposes whether a model supports `tools`).

## Goals

- Operators can configure OpenRouter via the existing Admin → Providers UI with sensible defaults and the same encrypted-credential plumbing as other providers.
- Studio's model picker remains usable against ~300 models (datalist combobox with native filter).
- The Studio capability chip (`[no tools]`) stays accurate for OpenRouter models, mirroring the existing Ollama capability detection.
- Fix the `openai-compatible` `Authorization: Bearer` bug so authenticated OpenAI-compatible servers work via that path going forward.
- Operators who leave the OpenRouter `api_key` blank cannot accidentally leak their `OPENAI_API_KEY` env var to OpenRouter.

## Non-goals (YAGNI)

- BYOK (bring-your-own-key) routing within OpenRouter.
- Pricing display from `/models` payload (`pricing.prompt`, `pricing.completion`).
- OpenRouter's `models: [...]` array request format for fallback routing.
- Per-request cost surfacing in Chat usage telemetry.
- `/credits` / `/generation` endpoint integration.
- A shared `OpenAICompatibleProvider` base class refactor (deferred to a separate flight).
- Auto-migrating existing `openai-compatible` users to the `openrouter` type — manual per-config decision.

## Design decisions (locked)

| # | Decision | Rationale |
|---|---|---|
| 1 | First-class `openrouter` type AND fix `openai-compatible` path | Cleanup is small and unblocks future Together/Groq/Fireworks users; OpenRouter polish (headers, model picker, capability chip) needs a dedicated class anyway. |
| 2 | Studio model picker uses native `<input list> + <datalist>` for OpenRouter only | Cheap (no JS framework), works at 300+ entries, doesn't disturb the `<select>` for other provider types. |
| 3 | Optional `HTTP-Referer` / `X-Title` headers are operator-configurable via existing `config: dict` extension | The mock provider already uses `config: dict` for provider-specific knobs; matches the established pattern. Empty values omit the headers. |
| 4 | `openai-compatible` cleanup is the minimum-viable Authorization fix in `OllamaProvider` | Doesn't require a refactor; doesn't regress vLLM/llama.cpp users with loose-format tool args; composes cleanly with first-class OpenRouter. |

## Architecture

### New components

**`the_one/llm/openrouter_provider.py`** — `OpenRouterProvider`, thin subclass of `OpenAIProvider`.

```python
class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"

    def __init__(
        self,
        model: str = "",
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        config: dict | None = None,
        **kwargs: Any,
    ):
        # Override the constructor entirely (do NOT call super().__init__()) so the
        # parent's OPENAI_API_KEY env-var fallback does not leak to OpenRouter.
        self.model = model
        resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        cfg = config or {}
        headers: dict[str, str] = {}
        if cfg.get("referer"):
            headers["HTTP-Referer"] = cfg["referer"]
        if cfg.get("title"):
            headers["X-Title"] = cfg["title"]
        client_kwargs: dict[str, Any] = {"api_key": resolved_key, "base_url": base_url}
        if headers:
            client_kwargs["default_headers"] = headers
        self.client = openai.AsyncOpenAI(**client_kwargs)
```

All inherited methods (`complete`, `stream`, `tool_schema`, `_to_api_message`) read only `self.model` and `self.client`, so the override-without-super pattern is safe.

**`the_one/llm/openrouter_api.py`** — Helper module mirroring `the_one/llm/ollama_api.py`:

- `async def list_models(base_url: str, api_key: str | None) -> list[dict] | None` — Fetches `GET {base_url}/models`, returns the parsed `data: [...]` array. Returns `None` on `httpx.HTTPStatusError` / `httpx.RequestError` / `ValueError` (fail-open, mirrors `ollama_api.get_model_capabilities`).
- Per-process `_models_cache: dict[str, tuple[list[dict], float]]` keyed by `base_url`, 300s TTL.
- Single source of truth for both the admin model-list endpoint and the Studio capability lookup.

### Modified components

**`the_one/llm/openai_provider.py`** — `OpenAIProvider.__init__` gains `base_url: str | None = None` and threads it into `AsyncOpenAI(base_url=base_url, api_key=...)` when set. One-line addition; fixes a latent gap (the parameter was swallowed by `**kwargs` previously).

**`the_one/llm/ollama_provider.py`** — `OllamaProvider.__init__` gains `api_key: str | None = None`. New `_auth_headers()` helper returns `{"Authorization": f"Bearer {self.api_key}"}` when set, `{}` otherwise. Threaded into both `httpx.AsyncClient(headers=...)` calls in `complete()` and `stream()`.

**`the_one/llm/ollama_api.py`** — `chat_stream()` and `show_model()` accept an optional `headers: dict | None = None` parameter and merge into the request, so the auth header propagates to capability lookup and SSE streaming. `get_model_capabilities()` continues to fail-open on 404 (OpenRouter has no `/api/show`).

**`the_one/llm/registry.py`** — `_try_load_builtin()` gains an `"openrouter"` loader that imports `the_one.llm.openrouter_provider`.

**`the_one/agent/factory.py`** — `_PROVIDER_TYPE_MAP` gains `"openrouter": "openrouter"`.

**`the_one/db/models.py`** — `LLMProviderConfig.type` Literal extended to include `"openrouter"`.

**`the_one/db/schema.py`** — New migration v10 (see below). `CURRENT_VERSION = 10`.

**`the_one/interfaces/web/api.py`**:
- `GET /api/providers/types` — append `{value: "openrouter", label: "OpenRouter"}`. Always visible (not gated by `dev_mode`, unlike `mock`).
- `GET /api/providers/{id}/models` — new branch for `provider.type == "openrouter"` that calls `openrouter_api.list_models(base_url, decrypted_api_key)`. Response shape: `[{id, name, supported_parameters, context_length, description}]`.
- `POST /api/providers/{id}/test` — new branch instantiates `OpenRouterProvider`, calls `openrouter_api.list_models(...)` once. Returns `{status: "ok", detail: "Connected (NNN models available)"}` on success, `{status: "error", detail: str(e)}` on failure.
- Pull/load/unload/delete/status — **unchanged**. Already gated by `_get_ollama_base_url()`; OpenRouter is a hosted gateway with no model lifecycle endpoints.

**Frontend — admin (`static/js/areas/admin/provider-editor.js`, `provider-models.js`)**:
- `getTypeDefaults("openrouter")` returns `{base_url: "https://openrouter.ai/api/v1", api_key_required: true}`.
- `KNOWN_BADGE_TYPES` extended with `"openrouter"`. Badge color picked in `tokens.css` (minor styling decision; suggest reusing an existing accent or adding a single new token).
- When `type === "openrouter"`, the form renders two extra optional inputs below `api_key`:
  - "App URL (optional)" → `config.referer`
  - "App Name (optional)" → `config.title`
- Empty inputs serialize to omitted keys (not empty strings) so the provider sees the header as absent.
- Edit-mode round-trip preserves `config.referer` / `config.title`.

**Frontend — Studio (`static/js/areas/studio/general-tab.js`, `studio.js`)**:
- The current `<select id="studio-model">` stays the default for all provider types.
- When `provider.type === "openrouter"`, the picker swaps to `<input id="studio-model" list="studio-model-list">` paired with `<datalist id="studio-model-list">`. Datalist `<option>` elements populate from the cached `/api/providers/{id}/models` payload.
- The `modelCapsBy[modelId]` cache is generalized to also accept OpenRouter's `supported_parameters` array. Downstream `"tools" in caps` check unchanged. Red `[no tools]` chip continues to render based on this lookup.

## Data flow — operator → first agent.step()

1. Operator opens **Admin → Providers → New Provider**.
2. Picks **OpenRouter** from the type dropdown.
3. Form pre-fills `base_url=https://openrouter.ai/api/v1`. Operator pastes `api_key`. Optionally fills `App URL` and `App Name`.
4. **Submit** → `POST /api/providers` → type validator accepts `openrouter` → repo Fernet-encrypts `api_key` → row stored with `config={"referer": ..., "title": ...}`.
5. Operator clicks **Test Connection** → backend instantiates `OpenRouterProvider` → calls `openrouter_api.list_models(...)` → returns `{status: "ok", detail: "Connected (300 models available)"}`.
6. Operator clicks **Models** tab → `GET /api/providers/{id}/models` hits `openrouter_api.list_models` (cache miss → fetch → cache 300s) → renders list with capability chips.
7. Operator opens **Studio → New Agent** → picks the OpenRouter provider.
8. Studio's model-picker becomes a `<datalist>` combobox. Operator types `claude` → datalist filters to matching entries → operator selects `anthropic/claude-3.5-sonnet`.
9. Capability chip renders. If the model lacks `"tools"` in `supported_parameters`, the red `[no tools]` chip surfaces (silent-fallback warning).
10. Operator saves the agent. User chats in Chat area.
11. `AgentFactory.create()` resolves provider config from DB → decrypts `api_key` → calls `get_provider("openrouter", model=..., api_key=..., base_url=..., config={referer, title})` → `OpenRouterProvider` instance constructed → headers attached → `Agent.step(user_input)` runs.

## Schema migration v10

SQLite has no `ALTER TABLE ... DROP CONSTRAINT`, so extending the `CHECK` on `llm_providers.type` requires a table rebuild. Pattern mirrors v6 (which added `"mock"`).

Pattern follows v6 exactly (column shapes, `executescript` for the rebuild, `INSERT OR IGNORE INTO schema_version` LAST per the v8/v9 convention):

```python
if version < 10:
    await conn.executescript("""
        CREATE TABLE llm_providers_new (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK (
                type IN ('ollama', 'openai-compatible', 'openai',
                         'anthropic', 'mock', 'openrouter')
            ),
            base_url TEXT NOT NULL,
            api_key TEXT,
            config TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        INSERT INTO llm_providers_new
            (id, name, type, base_url, api_key, config, created_at, updated_at)
            SELECT id, name, type, base_url, api_key, config, created_at, updated_at
            FROM llm_providers;

        DROP TABLE llm_providers;
        ALTER TABLE llm_providers_new RENAME TO llm_providers;

        PRAGMA foreign_keys=ON;
    """)
    await conn.execute(
        "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (10,)
    )
    await conn.commit()
    version = 10
```

Column shapes (`name TEXT NOT NULL`, `config TEXT DEFAULT '{}'`, `created_at TEXT NOT NULL DEFAULT (datetime('now'))`) match the existing v6 rebuild verbatim — the only diff is the CHECK adding `'openrouter'`. `schema_version` table has only the `version` column (no `applied_at`). `INSERT OR IGNORE` is LAST so partial failure leaves version=9 and retry is clean.

## Error handling

- **Provider class**: inherits OpenAI SDK exception surface. No custom catches in `OpenRouterProvider`; errors propagate to the agent loop where existing patterns wrap them.
- **`openrouter_api.list_models`**: catches `httpx.HTTPStatusError`, `httpx.RequestError`, `ValueError` (JSON parse). Returns `None` on failure (fail-open, mirrors `ollama_api`).
- **`/api/providers/{id}/test` endpoint**: catches `Exception`, returns `{status: "error", detail: str(e)}`. Never raises 5xx.
- **`/api/providers/{id}/models` endpoint**: returns 502 on upstream failure (existing pattern preserved).
- **`__MASKED__` sentinel**: fully inherited from the generic api_key handling. No OpenRouter-specific code.
- **No-leak invariant**: `OpenRouterProvider.__init__` does NOT call `super().__init__()` and falls back only to `OPENROUTER_API_KEY`, never `OPENAI_API_KEY`.

## Test plan

| Test file | Coverage |
|---|---|
| `tests/test_openrouter_provider.py` (new) | `httpx.MockTransport` injected via `AsyncOpenAI(http_client=...)`. Cover: `base_url` honored, `default_headers` set when `config.referer`/`config.title` non-empty, headers omitted when blank, tool schemas inherited unchanged, streaming/complete paths work end-to-end. **Pin no-leak invariant**: with `OPENAI_API_KEY` set in env but `OPENROUTER_API_KEY` unset and `api_key=None`, the constructed client's `api_key` attribute does not equal the OpenAI env value. |
| `tests/test_openrouter_api.py` (new) | `list_models` cache hit/miss/TTL behavior, error fail-open returns `None`, `Authorization: Bearer` header included in upstream request. |
| `tests/test_provider_api.py` (extend) | `/types` includes `openrouter` (always, regardless of `dev_mode`), CRUD roundtrip with `config.referer`/`config.title`, `/models` calls cache helper, `/test` returns ok/error correctly. |
| `tests/test_llm_registry.py` (extend) | `get_provider("openrouter")` lazy-loads, returns `OpenRouterProvider` instance. |
| `tests/test_db_migrations.py` (extend) | v9→v10 migration runs cleanly; idempotent re-run is safe; existing rows preserved through table rebuild. |
| `tests/test_ollama_provider_auth.py` (new) | `OllamaProvider(api_key="…")` sends `Authorization: Bearer …` on `complete`, `stream`, `chat_stream`, `show_model`. Verify via `httpx.MockTransport`. |
| `tests/browser/test_flow_admin_openrouter.py` (new) | Open Admin → New Provider → pick OpenRouter → fields render with defaults → save → verify in grid → edit → fields round-trip. |
| `tests/browser/test_flow_studio_openrouter_picker.py` (new) | Studio: provider with mocked OpenRouter `/models` payload → datalist combobox renders → typing filters → selecting a model with `tools` shows no warning → selecting a model without `tools` shows red `[no tools]` chip. |

## Files touched (estimated)

**Backend (Python):**
- `the_one/llm/openrouter_provider.py` (new, ~50 lines)
- `the_one/llm/openrouter_api.py` (new, ~70 lines)
- `the_one/llm/openai_provider.py` (~3-line edit)
- `the_one/llm/ollama_provider.py` (~10-line edit)
- `the_one/llm/ollama_api.py` (~5-line edit, optional `headers` param)
- `the_one/llm/registry.py` (~3-line edit)
- `the_one/agent/factory.py` (~1-line edit)
- `the_one/db/models.py` (~1-line edit, Literal extension)
- `the_one/db/schema.py` (~30-line addition, v10 migration)
- `the_one/interfaces/web/api.py` (~40-line addition across 3 endpoints)

**Frontend (JS/CSS):**
- `static/js/areas/admin/provider-editor.js` (~30-line addition)
- `static/js/areas/admin/providers-grid.js` (~5-line edit, badge entry)
- `static/js/areas/studio/general-tab.js` (~20-line addition, datalist branch)
- `static/js/areas/studio/studio.js` (~15-line edit, capability cache generalization)
- `static/css/tokens.css` (~3-line addition, badge color)

**Tests:** see Test plan table above (~6 new files + 3 extensions).

## Open questions

None at design-approval time. Implementation plan will surface library/API questions (e.g., does `AsyncOpenAI.default_headers` accept the dict format we expect — Context7 lookup before writing the provider class).
