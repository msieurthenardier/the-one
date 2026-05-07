# OpenRouter Provider Support — Design

**Date:** 2026-05-06
**Status:** Approved (brainstorming complete; awaiting implementation plan)

## Summary

Add OpenRouter (https://openrouter.ai) as a first-class LLM provider type, and fix a latent bug in the existing `openai-compatible` path that swallows `api_key` and prevents authenticated use against any OpenAI-compatible server (Together, Groq, Fireworks, DeepInfra, OpenRouter via the generic path, etc.).

OpenRouter is OpenAI-API-compatible and routes to ~300 hosted models from many vendors. The integration uses the official OpenAI SDK with a custom `base_url`, optional ranking headers (`HTTP-Referer`, `X-Title`), and a model-discovery endpoint that returns per-model metadata including a `supported_parameters` array (which exposes whether a model supports `tools`).

## Goals

- Operators can configure OpenRouter via the existing Admin → Providers UI with sensible defaults and the same encrypted-credential plumbing as other providers.
- Studio's model picker remains usable against ~370 live models (datalist combobox with native filter; per-browser variance acknowledged in §Frontend).
- The Studio capability chip (`[no tools]`) stays accurate for OpenRouter models, mirroring the existing Ollama capability detection. **Fail-open semantics** (mirrors `ollama_api.get_model_capabilities`): chip surfaces only when capability data is present AND `"tools"` is absent. Missing field, empty `supported_parameters` list, or fetch failure → no chip (treated as "unknown").
- Fix the `openai-compatible` `Authorization: Bearer` bug so authenticated OpenAI-compatible servers work via that path going forward.
- Operators who leave the OpenRouter `api_key` blank cannot accidentally leak their `OPENAI_API_KEY` env var to OpenRouter. Implementation enforces this via a **non-empty placeholder** passed to the SDK when no key is set. The OpenAI SDK's env-var fallback is triggered ONLY when `api_key is None`; passing any non-None value skips the fallback. The original design considered an empty-string opt-out, but `openai>=2.16` raises `OpenAIError` at construction on empty strings (and the only workaround is a private SDK kwarg). A placeholder string is public-API-clean and lets upstream return a clean 401.
- Operator-supplied `referer` / `title` strings cannot inject HTTP headers via embedded CR/LF/NUL bytes. (httpx 0.28.1 does NOT sanitize header values — verified empirically.)

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
| 5 | Non-empty placeholder `api_key` (NOT `None`, NOT `""`) for `OpenRouterProvider` when no key is set | The OpenAI SDK falls back to `OPENAI_API_KEY` env var on `api_key is None`. Passing any non-None value skips the fallback. An empty string was the original choice but `openai>=2.16` raises `OpenAIError` at construction on `api_key=""` (private `_enforce_credentials=False` kwarg is the only escape — unsafe to depend on). A non-empty placeholder (`_NO_KEY_PLACEHOLDER`) is public-API-clean; placeholder on the wire → upstream 401 → operator sees the right failure. |
| 6 | Sanitize `referer` / `title` at the `POST /api/providers` boundary, not in the provider class | httpx (0.28.1) sends CR/LF/NUL through verbatim. Validation belongs at the trust boundary (form/API), not at every consumer. Reject control chars; require `referer` to parse as `http(s)://`-scheme URL. |
| 7 | Helper functions raise typed exceptions; endpoints translate to HTTP. Capability-lookup uses a separate fail-open path. | Eliminates the helper-returns-`None`-vs-endpoint-returns-502 contradiction. The capability lookup keeps fail-open semantics by catching the typed exception locally. |
| 8 | `/api/v1/models` is treated as PUBLIC for connection probing; `/api/v1/auth/key` is the canonical key-validity probe | Verified against the live API (2026-05-06): `/models` returns 200 without `Authorization`; `/auth/key` returns 401 without a valid key. Test endpoint hits `/auth/key` for actual key validation, falls back to `/models` if api_key is unset (operator who hasn't entered a key still gets a meaningful "reachable, no key set" status). |

## Architecture

### New components

**`the_one/llm/openrouter_provider.py`** — `OpenRouterProvider`, thin subclass of `OpenAIProvider`.

```python
# Sentinel used when neither the constructor arg nor OPENROUTER_API_KEY is set.
# A non-empty placeholder satisfies the SDK's public contract; openai>=2.16
# raises OpenAIError on api_key="" (the private _enforce_credentials=False
# kwarg is the only escape but is unsafe to depend on across SDK versions).
_NO_KEY_PLACEHOLDER = "openrouter-no-key-set"


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
        # Override the constructor entirely (do NOT call super().__init__()) so
        # the parent's OPENAI_API_KEY env-var fallback does not leak to
        # OpenRouter. See parent-instance-attribute invariant test below.
        self.model = model

        # No-leak invariant (Decision 5): the openai SDK reads
        # OPENAI_API_KEY ONLY when ``api_key is None``. We never let
        # ``None`` reach the SDK constructor; if both the explicit arg
        # and OPENROUTER_API_KEY are unset, we pass _NO_KEY_PLACEHOLDER.
        # Empty-string is also a no-no on openai>=2.16 (raises at
        # construction). The placeholder is public-API-clean and produces
        # an obvious 401 upstream.
        resolved_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if resolved_key is None or resolved_key == "":
            resolved_key = _NO_KEY_PLACEHOLDER

        cfg = config or {}
        headers: dict[str, str] = {}
        # `referer` / `title` are validated at the POST /api/providers
        # boundary (Decision 6); this code trusts the saved value but
        # still skips empty strings so absent headers stay absent on the
        # wire.
        if cfg.get("referer"):
            headers["HTTP-Referer"] = cfg["referer"]
        if cfg.get("title"):
            headers["X-Title"] = cfg["title"]
        client_kwargs: dict[str, Any] = {"api_key": resolved_key, "base_url": base_url}
        if headers:
            client_kwargs["default_headers"] = headers
        self.client = openai.AsyncOpenAI(**client_kwargs)
```

All currently-inherited methods (`complete`, `stream`, `tool_schema`, `_to_api_message`) read only `self.model` and `self.client`, so the override-without-super pattern is safe TODAY. Pinned by `tests/test_openrouter_provider.py::test_instance_attribute_parity` — asserts `set(vars(OpenRouterProvider("x")).keys()) >= set(vars(OpenAIProvider("x", api_key="y")).keys())` so any future addition to `OpenAIProvider.__init__` (e.g. `self.organization`, `self.timeout`) breaks the test and forces the subclass author to either mirror the field or refactor toward an `env_var_name` constructor parameter (the cleaner long-term shape; deferred).

**`the_one/llm/openrouter_api.py`** — Helper module mirroring `the_one/llm/ollama_api.py`:

- `async def list_models(base_url: str, api_key: str | None) -> list[dict]` — Fetches `GET {base_url}/models`. Sends `Authorization: Bearer …` only when `api_key` is non-empty (the endpoint is PUBLIC; auth is optional and only filters per-user availability). **Raises** on failure: `httpx.RequestError` and `httpx.HTTPStatusError` propagate; `ValueError` on JSON-parse failure. Endpoints translate to HTTP per the existing pattern; the capability lookup wraps in its own try/except for fail-open semantics.
- `async def verify_key(base_url: str, api_key: str) -> dict` — Hits `GET {base_url}/auth/key` with `Authorization: Bearer …`. Returns the JSON dict on success; raises on 401/network failure. Used by the Test Connection endpoint to actually probe key validity (vs `/models` which is public and would falsely report "ok" with an invalid key).
- `async def get_model_capabilities(base_url: str, api_key: str | None, model: str) -> frozenset[str] | None` — Wraps `list_models`, looks up the model row, returns its `supported_parameters` as a `frozenset`. Returns `None` on **fetch failure**, **missing `supported_parameters` field**, or **empty list** (Decision 7 — capability-lookup retains fail-open semantics so the chip stays silent on uncertainty). Mirrors `ollama_api.get_model_capabilities` shape exactly so the Studio frontend can dispatch on `caps is None ? "unknown" : "tools" in caps` uniformly across providers.
- Per-process `_models_cache: dict[tuple[str, str], tuple[list[dict], float]]` keyed by `(base_url, sha256(api_key)[:16])`, 300s TTL. Hashing the key avoids cross-account list bleed in the rare multi-config-same-base-url case (single-user app today; cheap to do correctly now).
- Single source of truth for both the admin model-list endpoint and the Studio capability lookup.

**OpenRouter `/models` payload shape** (verified live 2026-05-06 against `https://openrouter.ai/api/v1/models`, 368 models):

- Top-level: `{"data": [...]}`. Each entry has `id`, `canonical_slug`, `name`, `created`, `description`, `context_length`, `architecture`, `pricing`, `top_provider`, `per_request_limits`, `supported_parameters`, `default_parameters`, `supported_voices`, `knowledge_cutoff`, `expiration_date`, `links`.
- `supported_parameters` is reliably present as a list (366/368 non-empty; 2/368 empty list; 0 null; 0 missing). Treat empty list and missing field both as "unknown" → no chip.
- `"tools"` is the literal string in the array (274/368 models support tools at the time of measurement).

### Modified components

**`the_one/llm/openai_provider.py`** — `OpenAIProvider.__init__` gains `base_url: str | None = None` and threads it into `AsyncOpenAI(base_url=base_url, api_key=...)` when set. One-line addition; fixes a latent gap (the parameter was swallowed by `**kwargs` previously). **Note for future authors**: any new instance attribute added here MUST also be set in `OpenRouterProvider.__init__` (see parent-instance-attribute parity test).

**`the_one/llm/ollama_provider.py`** — `OllamaProvider.__init__` gains `api_key: str | None = None`. New `_auth_headers()` helper returns `{"Authorization": f"Bearer {key}"}` when `key = (self.api_key or "").strip()` is non-empty, `{}` otherwise. Empty-string and whitespace-only api_key values are treated as "no key" so OSS Ollama servers (which reject `Authorization: Bearer ` with empty value) keep working. Threaded into both `httpx.AsyncClient(headers=...)` calls in `complete()` and `stream()`.

**`the_one/llm/ollama_api.py`** — `chat_stream()` and `show_model()` accept an optional `headers: dict | None = None` parameter and merge into the request, so the auth header propagates to capability lookup and SSE streaming. `get_model_capabilities()` continues to fail-open on 404 (OpenRouter has no `/api/show`).

**`the_one/llm/registry.py`** — `_try_load_builtin()` gains an `"openrouter"` loader that imports `the_one.llm.openrouter_provider`. The lazy-import error message points to the `[openai]` extra (NOT a non-existent `[openrouter]` extra) since OpenRouter rides the `openai` package: `f"Provider 'openrouter' requires the OpenAI SDK. Install with: pip install 'the-one[openai]'"`.

**`the_one/agent/factory.py`** — `_PROVIDER_TYPE_MAP` gains `"openrouter": "openrouter"`.

**`the_one/db/models.py`** — `LLMProviderConfig.type` Literal extended to include `"openrouter"`.

**`the_one/db/schema.py`** — New migration v10 (see below). `CURRENT_VERSION = 10`.

**`the_one/interfaces/web/api.py`**:
- `GET /api/providers/types` — append `{value: "openrouter", label: "OpenRouter"}`. Always visible (not gated by `dev_mode`, unlike `mock`).
- `GET /api/providers/{id}/models` — new branch for `provider.type == "openrouter"` that calls `openrouter_api.list_models(base_url, decrypted_api_key)`. Response shape: `[{id, name, supported_parameters, context_length, description}]`. Translates `httpx.RequestError` / `httpx.HTTPStatusError` to HTTP 502 (existing pattern). `ValueError` → HTTP 502 with the parse-error detail.
- `POST /api/providers/{id}/test` — new branch:
  - If `decrypted_api_key` is non-empty: call `openrouter_api.verify_key(base_url, key)`. On success, also call `list_models(...)` to surface model count. Returns `{status: "ok", detail: "Connected. Key valid; NNN models available."}`.
  - If `decrypted_api_key` is empty: call only `list_models(base_url, "")`. Returns `{status: "ok", detail: "Reachable. Add an API key to enable chat. NNN models available."}`. Operator gets unambiguous "you haven't entered a key yet" status instead of a misleading green check.
  - Catches `httpx.HTTPStatusError` (returns `{status: "error", detail: f"HTTP {e.response.status_code}: {e.response.text[:200]}"}`), `httpx.RequestError` (returns `{status: "error", detail: f"Network error: {e}"}`), generic `Exception` (returns `{status: "error", detail: str(e)}`). Never raises 5xx.
- `POST /api/providers` and `PUT /api/providers/{id}` — sanitize `body.config.referer` and `body.config.title` BEFORE storing (Decision 6). Reject with HTTP 422 if either contains `\r`, `\n`, or `\x00`. `referer` additionally must parse as `urllib.parse.urlparse(value).scheme in {"http", "https"}` and have a non-empty `netloc`. `title` is plain text, max 64 chars (OpenRouter's documented limit). Empty strings → omit the key from `config` (so absent stays absent on round-trip).
- Pull/load/unload/delete/status — **unchanged**. Already gated by `_get_ollama_base_url()`; OpenRouter is a hosted gateway with no model lifecycle endpoints.

**Frontend — admin (`static/js/areas/admin/provider-editor.js`, `provider-models.js`)**:
- `getTypeDefaults("openrouter")` returns `{base_url: "https://openrouter.ai/api/v1", api_key_required: false}`. (Required-flag `false` because `/models` works without a key — operators can save a no-key config and use free-tier models. The Test Connection endpoint surfaces the "no key set" status.)
- `KNOWN_BADGE_TYPES` extended with `"openrouter"`. Badge styling reuses the existing `--accent-color` token via the same class scaffolding the `openai` badge uses (no new token required for v1; if visual differentiation matters later, add `--accent-openrouter` in a follow-up).
- When `type === "openrouter"`, the form renders two extra optional inputs below `api_key`:
  - "App URL (optional)" → `config.referer` — client-side validation rejects strings containing `\r`, `\n`, `\x00`, and requires `https://` or `http://` prefix when non-empty. Server re-validates per Decision 6.
  - "App Name (optional)" → `config.title` — client-side validation rejects strings containing `\r`, `\n`, `\x00` and trims to 64 chars.
- Empty inputs serialize to omitted keys (not empty strings) so the provider sees the header as absent.
- Edit-mode round-trip preserves `config.referer` / `config.title`. Pinned by a SAVE → reload → assert-absent → re-save → assert-still-absent test (catches future regressions where a form refactor starts emitting `""` and OpenRouter's app-rankings telemetry records blanks).
- Type-change behavior (`ollama → openrouter` on an existing row): preserve `name`, `api_key`, `config`; reset `base_url` to the new type's default; clear `model` if it doesn't appear in the new type's model list. Decision deliberately leaves user-entered values intact — operators who switch types likely want their key/config carried over.

**Frontend — Studio (`static/js/areas/studio/general-tab.js`, `studio.js`)**:
- The current `<select id="studio-model">` stays the default for all provider types.
- When `provider.type === "openrouter"`, the picker swaps to `<input id="studio-model" list="studio-model-list">` paired with `<datalist id="studio-model-list">`. Datalist `<option>` elements populate from the cached `/api/providers/{id}/models` payload.
- **Lifecycle**: the swap REPLACES the existing `#studio-model` node (`oldNode.replaceWith(newNode)`) rather than toggling visibility, so there is never more than one element with that id and stale event listeners are GC'd with the orphaned node. Toggling provider type back-and-forth must end up with exactly one `#studio-model` element (pinned by a browser test that switches twice).
- **Datalist UX caveat**: native `<datalist>` filter behaviour varies (Safari starts-with; Chrome substring; Firefox positional). At ~370 OpenRouter entries with shared namespaces (`anthropic/`, `openai/`, …), this is acceptable for v1 but flagged as a future enhancement candidate (custom-input + filtered list, ~30 lines).
- The `modelCapsBy[modelId]` cache shape is `dict[str, frozenset[str] | None]`. `null` means "unknown / unfetched" (no chip). `frozenset()` means "fetched but no capabilities listed" (still no chip — Decision 7 fail-open). `frozenset({"tools", …})` means "tools supported" (no chip). Only `frozenset(...)` that is non-empty AND lacks `"tools"` renders the red `[no tools]` chip. Same dispatch logic as Ollama, just sourced from `supported_parameters` instead of `/api/show capabilities`.

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

Pattern follows v6 exactly — including the `PRAGMA foreign_keys=OFF` / `=ON` bracket. The connection is opened with `PRAGMA foreign_keys=ON` (`the_one/db/connection.py:20`), and `agents.provider_config_id` references `llm_providers(id)` — without disabling FK enforcement during the rebuild, the `DROP TABLE llm_providers` step fails (or, depending on aiosqlite's commit semantics, leaves dangling references). Use `executescript` for the rebuild + `INSERT OR IGNORE INTO schema_version` LAST per the v8/v9 convention:

```python
if version < 10:
    await conn.executescript("""
        PRAGMA foreign_keys=OFF;

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
- **`openrouter_api.list_models` / `verify_key`**: do NOT swallow exceptions. `httpx.RequestError`, `httpx.HTTPStatusError`, and `ValueError` propagate to callers. Decision 7 — endpoints (which know the user-facing surface) translate; the helper stays pure.
- **`openrouter_api.get_model_capabilities`**: separate fail-open helper for the capability lookup specifically. Wraps `list_models` in try/except; returns `None` on any exception, missing `supported_parameters`, or empty list. Mirrors `ollama_api.get_model_capabilities` shape so frontend dispatch is uniform across providers.
- **`/api/providers/{id}/test` endpoint**: see api.py spec above — catches `httpx.HTTPStatusError`, `httpx.RequestError`, `Exception` separately and returns differentiated messages. Never raises 5xx.
- **`/api/providers/{id}/models` endpoint**: catches `httpx.HTTPStatusError` / `httpx.RequestError` / `ValueError`, returns 502 on upstream failure (existing pattern preserved).
- **`__MASKED__` sentinel**: fully inherited from the generic api_key handling. No OpenRouter-specific code.
- **No-leak invariant**: `OpenRouterProvider.__init__` does NOT call `super().__init__()` and uses a **non-empty placeholder** (`_NO_KEY_PLACEHOLDER = "openrouter-no-key-set"`) when neither `api_key` arg nor `OPENROUTER_API_KEY` env is set. The OpenAI SDK reads `OPENAI_API_KEY` ONLY when `api_key is None`; passing any non-None value skips the fallback. Empty string was the original choice but `openai>=2.16` raises at construction on `api_key=""`. Pinned by `tests/test_openrouter_provider.py::test_no_leak_with_api_key_none`.
- **Header-injection invariant**: control characters (`\r`, `\n`, `\x00`) in `referer` / `title` rejected at the API boundary (Decision 6). httpx 0.28.1 verified to NOT sanitize header values — verbatim CRLF goes on the wire. Pinned by `tests/test_provider_api.py::test_referer_with_crlf_rejected`.

## Test plan

| Test file | Coverage |
|---|---|
| `tests/test_openrouter_provider.py` (new) | `httpx.MockTransport` injected via `AsyncOpenAI(http_client=...)`. Cover: `base_url` honored, `default_headers` set when `config.referer`/`config.title` non-empty, headers omitted when blank, tool schemas inherited unchanged, streaming/complete paths work end-to-end. **`test_no_leak_of_openai_env_var`** — set `OPENAI_API_KEY="sk-leaked"` in env, leave `OPENROUTER_API_KEY` unset, construct `OpenRouterProvider(api_key=None)`; assert `provider.client.api_key == ""` (NOT `"sk-leaked"`). **`test_no_leak_with_empty_string_api_key`** — same setup but pass `api_key=""`; same assertion. **`test_instance_attribute_parity`** — assert `set(vars(OpenRouterProvider("x"))) >= set(vars(OpenAIProvider("x", api_key="y")))` so a future addition to `OpenAIProvider.__init__` forces the subclass author to mirror or refactor. **`test_stream_without_trailing_usage`** — mock SSE that omits the `usage` chunk; assert no crash and `usage is None` flows through. |
| `tests/test_openrouter_api.py` (new) | `list_models` cache hit/miss/TTL behavior keyed on `(base_url, sha256(api_key)[:16])`; concurrent calls share an in-flight fetch (or independently fetch — pick and pin). `Authorization: Bearer` header sent only when `api_key` is non-empty. **`test_helper_raises_on_500`** — pin that the helper does NOT swallow `HTTPStatusError`. **`test_get_model_capabilities_fail_open`** — pin that the capability-lookup wrapper returns `None` for: fetch failure, missing model, missing `supported_parameters`, empty `supported_parameters` list. **`test_verify_key_401`** — pin that `verify_key` raises on 401 with the upstream error message preserved. |
| `tests/test_provider_api.py` (extend) | `/types` includes `openrouter` (always, regardless of `dev_mode`). CRUD roundtrip with `config.referer`/`config.title`. **`test_referer_with_crlf_rejected`** — POST with `referer="https://x\r\nX-Injected: 1"` returns 422. **`test_referer_with_lf_rejected`**, **`test_referer_with_nul_rejected`**, **`test_referer_with_non_url_rejected`** — same 422. **`test_title_max_length`** — 65 chars → 422; 64 chars → 200. **`test_round_trip_omits_empty_config_keys`** — POST with empty referer/title → reload → assert keys absent → re-PUT → assert keys still absent. `/models` calls `openrouter_api.list_models`; `/test` with valid key calls `verify_key`; `/test` with empty key calls only `list_models` and surfaces the "no key set" status. |
| `tests/test_factory_openrouter.py` (new) | End-to-end factory integration: store an encrypted `openrouter`-typed `LLMProviderConfig`, an agent referencing it, then `AgentFactory.create("name")` and assert the returned `Agent.llm` is an `OpenRouterProvider` with the decrypted key wired through. Catches every wiring change at once. |
| `tests/test_llm_registry.py` (extend) | `get_provider("openrouter")` lazy-loads, returns `OpenRouterProvider` instance. ImportError message references `[openai]` extra (NOT `[openrouter]`). |
| `tests/test_db_migrations.py` (extend) | v9→v10 migration runs cleanly with FK enforcement on (mirrors connection.py setup); idempotent re-run is safe; existing rows preserved through table rebuild; `agents.provider_config_id` references survive. |
| `tests/test_ollama_provider_auth.py` (new) | `OllamaProvider(api_key="…")` sends `Authorization: Bearer …` on `complete`, `stream`, `chat_stream`, `show_model`. **`test_empty_string_api_key_sends_no_auth`** — `api_key=""` → no `Authorization` header (OSS Ollama compat). **`test_whitespace_api_key_sends_no_auth`** — `api_key="   "` → no `Authorization` header. Verify via `httpx.MockTransport`. |
| `tests/test_openrouter_tool_call_shapes.py` (new) | Captured-fixture regression: SSE transcripts captured from real OpenRouter responses for at least one model per upstream provider (OpenAI-routed, Anthropic-routed, Llama-routed). Assert `OpenAIProvider`'s tool-call parser handles each verbatim. Catches the once-a-year drift where an upstream model returns `arguments` as a dict instead of a JSON string. |
| `tests/browser/test_flow_admin_openrouter.py` (new) | Open Admin → New Provider → pick OpenRouter → fields render with defaults → save → verify in grid → edit → fields round-trip. Type-change flow: edit an existing `ollama` provider, switch type to `openrouter`, assert `name`/`api_key`/`config` preserved, `base_url` reset to OpenRouter default. |
| `tests/browser/test_flow_studio_openrouter_picker.py` (new) | Studio: provider with mocked OpenRouter `/models` payload → datalist combobox renders → typing filters → selecting a model with `tools` shows no warning → selecting a model without `tools` shows red `[no tools]` chip → selecting a model with empty `supported_parameters` shows NO chip (fail-open). **Lifecycle test**: switch provider type ollama → openrouter → ollama → openrouter; assert exactly one `#studio-model` element exists at every step. |

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

None at design-approval time after the 2026-05-06 adversarial-review revision pass. Library/API questions verified empirically:

- `openai` SDK `AsyncOpenAI.__init__`: `api_key=None` → reads `OPENAI_API_KEY` env; non-None values (including a placeholder string) skip the env fallback. `openai==2.15.0` accepted empty strings; `openai>=2.16` raises on empty strings (use a non-empty placeholder). `default_headers={dict}` merges into the request header set (verified — `HTTP-Referer` and `X-Title` arrive on the wire).
- `httpx==0.28.1`: header values containing `\r`/`\n`/`\x00` are NOT sanitized — application must validate at the trust boundary.
- OpenRouter live API (2026-05-06): `/api/v1/models` is public (no auth required, returns `{"data": [...]}` with 368 models); `/api/v1/auth/key` requires a valid key (returns 401 otherwise); `supported_parameters` reliably present as a list (366/368 non-empty, 2/368 empty, 0 null/missing).
