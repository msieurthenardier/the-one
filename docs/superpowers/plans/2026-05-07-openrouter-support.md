# OpenRouter Provider Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenRouter as a first-class LLM provider type and fix the latent `Authorization: Bearer` bug in the existing `openai-compatible` path.

**Architecture:** New `OpenRouterProvider` thinly subclasses `OpenAIProvider` with a custom `base_url` and ranking headers. New `openrouter_api.py` helper mirrors `ollama_api.py` for `/models` discovery, `/auth/key` validation, and capability lookup. Schema migration v10 extends `llm_providers.type` CHECK to include `'openrouter'`. Frontend adds OpenRouter to the type dropdown, swaps Studio's model picker to a `<datalist>` combobox for ~370 models, and renders the `[no tools]` capability chip from `supported_parameters`.

**Tech Stack:** Python 3.11+, FastAPI, aiosqlite, openai==2.15.0, httpx==0.28.1, vanilla JS (no framework), pytest + Playwright.

**Companion design doc:** `docs/superpowers/specs/2026-05-06-openrouter-support-design.md` — read before implementing any task.

**Working directory note:** All paths are relative to the worktree root. Run all commands from `/Users/jdsingh/Projects/AI/the-one/.claude/worktrees/openrouter-support`. Run `pytest` via the local venv: `.venv/bin/pytest`.

**Pre-existing baseline failure:** `tests/test_execution_tools.py::TestPythonExecTool::test_env_allowlist_invariant` fails on macOS host due to `__CF_USER_TEXT_ENCODING` env var. NOT caused by this work; ignore in baselines.

---

## Task 1: Schema migration v10 + Pydantic Literal extension

**Files:**
- Modify: `the_one/db/models.py:20` (extend `LLMProviderConfig.type` Literal)
- Modify: `the_one/db/schema.py:9` (`CURRENT_VERSION = 10`)
- Modify: `the_one/db/schema.py:354` (append v10 migration block)
- Modify: `tests/test_db_migration.py` (extend with v9→v10 migration tests)

**Why this task first:** every other task depends on `'openrouter'` being a valid `LLMProviderConfig.type` Literal value AND on the DB schema accepting it. Foundation.

- [ ] **Step 1: Write failing migration test (v9→v10 idempotent + FK preserved)**

Append to `tests/test_db_migration.py`:

```python
class TestMigrationV10:
    """v9→v10: extend llm_providers.type CHECK to include 'openrouter'."""

    async def test_v10_accepts_openrouter_type(self, tmp_path):
        """A fresh schema (CURRENT_VERSION=10) must accept openrouter rows."""
        db_path = tmp_path / "v10.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await ensure_schema(conn)

        await conn.execute(
            "INSERT INTO llm_providers (id, name, type, base_url) "
            "VALUES (?, ?, ?, ?)",
            ("p1", "OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
        )
        await conn.commit()

        async with conn.execute(
            "SELECT type FROM llm_providers WHERE id = ?", ("p1",)
        ) as cursor:
            row = await cursor.fetchone()
        assert row["type"] == "openrouter"
        await conn.close()

    async def test_v10_idempotent_rerun(self, tmp_path):
        """Calling ensure_schema twice on a fresh DB is a no-op the second time."""
        db_path = tmp_path / "idem.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        await ensure_schema(conn)
        await ensure_schema(conn)  # second call must not raise

        async with conn.execute("SELECT MAX(version) FROM schema_version") as cursor:
            row = await cursor.fetchone()
        assert row[0] == 10
        await conn.close()

    async def test_v10_preserves_existing_rows_and_fk(self, tmp_path):
        """Simulate a v9 DB with an llm_providers row referenced by an agent,
        then run ensure_schema; row + FK reference must survive the rebuild."""
        db_path = tmp_path / "upgrade.db"
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")

        # Bootstrap a v9 schema by manually applying v1..v9 — easiest path
        # is to call ensure_schema on a fresh DB which lands at CURRENT_VERSION.
        # Then simulate "stuck at v9" by deleting the v10 row and re-running.
        await ensure_schema(conn)
        await conn.execute("DELETE FROM schema_version WHERE version = 10")
        await conn.commit()

        # Insert a row + agent referencing it under the v9 CHECK constraint
        # (we just dropped the v10 marker, so the table has v10 columns; the
        # v10 migration is idempotent and must still work cleanly).
        await conn.execute(
            "INSERT INTO llm_providers (id, name, type, base_url) "
            "VALUES (?, ?, ?, ?)",
            ("p-keep", "MyOllama", "ollama", "http://localhost:11434/v1"),
        )
        await conn.execute(
            "INSERT INTO agents (name, provider_config_id) VALUES (?, ?)",
            ("alice", "p-keep"),
        )
        await conn.commit()

        # Re-run migration — v10 block re-applies (idempotent rebuild)
        await ensure_schema(conn)

        async with conn.execute(
            "SELECT id, type FROM llm_providers WHERE id = ?", ("p-keep",)
        ) as cursor:
            prov = await cursor.fetchone()
        async with conn.execute(
            "SELECT name, provider_config_id FROM agents WHERE name = ?", ("alice",)
        ) as cursor:
            agent = await cursor.fetchone()
        assert prov is not None and prov["type"] == "ollama"
        assert agent is not None and agent["provider_config_id"] == "p-keep"
        await conn.close()
```

- [ ] **Step 2: Run failing test**

```bash
.venv/bin/pytest tests/test_db_migration.py::TestMigrationV10 -v
```

Expected: All three FAIL — `IntegrityError: CHECK constraint failed` on the openrouter insert (CURRENT_VERSION still 9), and idempotent test sees `MAX(version) == 9`.

- [ ] **Step 3: Extend the Pydantic Literal**

In `the_one/db/models.py:20` change:

```python
    type: Literal["ollama", "openai-compatible", "openai", "anthropic", "mock"]
```

to:

```python
    type: Literal["ollama", "openai-compatible", "openai", "anthropic", "mock", "openrouter"]
```

- [ ] **Step 4: Add the v10 migration**

In `the_one/db/schema.py:9` change `CURRENT_VERSION = 9` to `CURRENT_VERSION = 10`.

Append to the end of `ensure_schema(...)` (after the `version < 9` block, currently ending around line 353):

```python
    if version < 10:
        # Extend llm_providers.type CHECK constraint to allow 'openrouter'.
        # SQLite has no `ALTER TABLE DROP CONSTRAINT`, so rebuild the table
        # following the v6 pattern (which added 'mock'). FK enforcement is
        # ON at connection-time (connection.py:20) and `agents.provider_config_id`
        # references this table — the OFF/ON bracket prevents the DROP from
        # tripping referential integrity. INSERT OR IGNORE INTO schema_version
        # is LAST so a partial-apply leaves version=9 and the next call retries
        # cleanly.
        await conn.executescript("""\
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

- [ ] **Step 5: Run tests to verify all pass**

```bash
.venv/bin/pytest tests/test_db_migration.py -v
```

Expected: PASS for all three new v10 tests + all pre-existing tests.

- [ ] **Step 6: Commit**

```bash
git add the_one/db/models.py the_one/db/schema.py tests/test_db_migration.py
git commit -m "feat(db): add openrouter to provider type Literal + schema v10

- Extend LLMProviderConfig.type Literal to include 'openrouter'
- Add v10 migration that rebuilds llm_providers with the extended CHECK
- Foreign-keys OFF/ON bracket protects agents.provider_config_id FK
- Idempotent re-run + FK preservation pinned by tests"
```

---

## Task 2: OpenAIProvider gains `base_url` parameter

**Files:**
- Modify: `the_one/llm/openai_provider.py:17-19`
- Test: extend `tests/test_llm_registry.py` with a `base_url` round-trip assertion

**Why:** `AgentFactory.create()` already passes `base_url=provider_config.base_url` into `get_provider(...)` for every provider type. Today `OpenAIProvider.__init__` swallows it via `**kwargs`. Threading it through is a one-line fix that lets non-default OpenAI-compatible base URLs work and unblocks the `OpenRouterProvider` subclass.

- [ ] **Step 1: Write failing test**

Append to `tests/test_llm_registry.py`:

```python
class TestOpenAIProviderBaseURL:
    def test_openai_provider_accepts_base_url(self) -> None:
        """OpenAIProvider must thread base_url into the AsyncOpenAI client."""
        from the_one.llm.openai_provider import OpenAIProvider

        prov = OpenAIProvider(
            model="gpt-4o",
            api_key="sk-test",
            base_url="https://example.com/v1",
        )
        # openai SDK exposes the resolved base_url on the client
        assert str(prov.client.base_url).rstrip("/") == "https://example.com/v1"

    def test_openai_provider_default_base_url(self) -> None:
        """Without base_url the SDK uses the OpenAI default."""
        from the_one.llm.openai_provider import OpenAIProvider

        prov = OpenAIProvider(model="gpt-4o", api_key="sk-test")
        # The SDK default is https://api.openai.com/v1
        assert "openai.com" in str(prov.client.base_url)
```

- [ ] **Step 2: Run failing test**

```bash
.venv/bin/pytest tests/test_llm_registry.py::TestOpenAIProviderBaseURL -v
```

Expected: FAIL — `test_openai_provider_accepts_base_url` reports the URL is still the OpenAI default because `base_url` was swallowed by `**kwargs`.

- [ ] **Step 3: Update `OpenAIProvider.__init__`**

In `the_one/llm/openai_provider.py:17-19` replace:

```python
    def __init__(self, model: str = "gpt-4o", api_key: str | None = None, **kwargs: Any):
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
```

with:

```python
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ):
        # NOTE: any new instance attribute added here MUST also be set in
        # OpenRouterProvider.__init__ (which deliberately does NOT call
        # super().__init__() — see test_instance_attribute_parity).
        self.model = model
        client_kwargs: dict[str, Any] = {
            "api_key": api_key or os.environ.get("OPENAI_API_KEY"),
        }
        if base_url is not None:
            client_kwargs["base_url"] = base_url
        self.client = openai.AsyncOpenAI(**client_kwargs)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_llm_registry.py -v
```

Expected: PASS, including both new tests + all pre-existing.

- [ ] **Step 5: Commit**

```bash
git add the_one/llm/openai_provider.py tests/test_llm_registry.py
git commit -m "feat(llm): thread base_url through OpenAIProvider

Previously swallowed by **kwargs. Required by OpenRouterProvider subclass
and useful for any OpenAI-compatible base_url override on the openai type."
```

---

## Task 3: OllamaProvider Authorization fix + ollama_api headers param

**Files:**
- Modify: `the_one/llm/ollama_provider.py:23-30` (constructor + `_auth_headers` helper)
- Modify: `the_one/llm/ollama_provider.py:60-64` (thread headers into `complete()` httpx client)
- Modify: `the_one/llm/ollama_provider.py:135` (thread headers into `stream()` via ollama_api)
- Modify: `the_one/llm/ollama_api.py:108-138` (`show_model` accepts `headers`)
- Modify: `the_one/llm/ollama_api.py:170-211` (`chat_stream` accepts `headers`)
- Create: `tests/test_ollama_provider_auth.py`

**Why:** The `openai-compatible` provider type maps to `OllamaProvider` in `_PROVIDER_TYPE_MAP`. Without an Authorization header, no authenticated server (Together, Groq, Fireworks, …) works. Treat empty/whitespace as "no key" so OSS Ollama (which rejects `Authorization: Bearer ` empty) stays working.

- [ ] **Step 1: Create `tests/test_ollama_provider_auth.py`**

```python
"""Authorization header behavior for OllamaProvider (openai-compatible target)."""
from __future__ import annotations

import json
import pytest
import httpx

from the_one.llm.base import Message, Role
from the_one.llm.ollama_provider import OllamaProvider


def _capture_handler(captured: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )
    return handler


@pytest.mark.asyncio
class TestOllamaAuthHeader:
    async def test_complete_sends_authorization_with_api_key(self, monkeypatch):
        """With api_key set, OllamaProvider.complete must send Authorization."""
        captured: list[httpx.Request] = []
        # Monkeypatch httpx.AsyncClient to inject a MockTransport
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_capture_handler(captured))
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        prov = OllamaProvider(
            model="m",
            base_url="http://localhost:11434/v1",
            api_key="sk-test-key",
        )
        await prov.complete([Message(role=Role.USER, content="hi")])
        assert captured, "no request captured"
        assert captured[0].headers.get("authorization") == "Bearer sk-test-key"

    async def test_complete_no_authorization_when_api_key_none(self, monkeypatch):
        captured: list[httpx.Request] = []
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_capture_handler(captured))
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        prov = OllamaProvider(model="m", base_url="http://localhost:11434/v1")
        await prov.complete([Message(role=Role.USER, content="hi")])
        assert "authorization" not in {k.lower() for k in captured[0].headers.keys()}

    async def test_complete_empty_string_api_key_sends_no_auth(self, monkeypatch):
        captured: list[httpx.Request] = []
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_capture_handler(captured))
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        prov = OllamaProvider(model="m", base_url="http://localhost:11434/v1", api_key="")
        await prov.complete([Message(role=Role.USER, content="hi")])
        assert "authorization" not in {k.lower() for k in captured[0].headers.keys()}

    async def test_complete_whitespace_api_key_sends_no_auth(self, monkeypatch):
        captured: list[httpx.Request] = []
        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_capture_handler(captured))
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        prov = OllamaProvider(model="m", base_url="http://localhost:11434/v1", api_key="   ")
        await prov.complete([Message(role=Role.USER, content="hi")])
        assert "authorization" not in {k.lower() for k in captured[0].headers.keys()}
```

- [ ] **Step 2: Run failing tests**

```bash
.venv/bin/pytest tests/test_ollama_provider_auth.py -v
```

Expected: FAIL — `OllamaProvider.__init__` doesn't accept `api_key`; the patched httpx will fire but the Authorization header is missing (or constructor TypeErrors).

- [ ] **Step 3: Update `OllamaProvider.__init__`**

In `the_one/llm/ollama_provider.py:23-30` replace:

```python
    def __init__(
        self,
        model: str = "",
        base_url: str = "http://localhost:11434/v1",
        **kwargs: Any,
    ):
        self.model = model
        self.base_url = ollama_api.ensure_v1(base_url or "http://localhost:11434/v1")
```

with:

```python
    def __init__(
        self,
        model: str = "",
        base_url: str = "http://localhost:11434/v1",
        api_key: str | None = None,
        **kwargs: Any,
    ):
        self.model = model
        self.base_url = ollama_api.ensure_v1(base_url or "http://localhost:11434/v1")
        self.api_key = api_key

    def _auth_headers(self) -> dict[str, str]:
        """Return ``{Authorization: Bearer <key>}`` only when api_key is
        present and non-empty after strip. Empty / whitespace / None all
        produce ``{}`` so OSS Ollama (which rejects empty bearer) keeps
        working unchanged."""
        key = (self.api_key or "").strip()
        return {"Authorization": f"Bearer {key}"} if key else {}
```

- [ ] **Step 4: Thread headers into `complete()`**

In `the_one/llm/ollama_provider.py` find the `httpx.AsyncClient(timeout=300)` call inside `complete()` (around line 60) and replace:

```python
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
```

with:

```python
        async with httpx.AsyncClient(timeout=300, headers=self._auth_headers()) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
```

- [ ] **Step 5: Update `ollama_api.show_model` and `ollama_api.chat_stream` to accept `headers`**

In `the_one/llm/ollama_api.py:108` change `show_model` signature and httpx call:

```python
async def show_model(
    base_url: str,
    model: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
```

Inside, change:

```python
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{url}/api/show", json={"model": model})
```

to:

```python
        async with httpx.AsyncClient(timeout=30, headers=headers or {}) as client:
            resp = await client.post(f"{url}/api/show", json={"model": model})
```

In `the_one/llm/ollama_api.py:170` change `chat_stream` signature:

```python
async def chat_stream(
    provider_url: str,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
```

Inside, change:

```python
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream(
                "POST", f"{url}/chat/completions", json={**body, "stream": True}
            ) as resp:
```

to:

```python
        async with httpx.AsyncClient(timeout=600, headers=headers or {}) as client:
            async with client.stream(
                "POST", f"{url}/chat/completions", json={**body, "stream": True}
            ) as resp:
```

- [ ] **Step 6: Pass headers from `OllamaProvider.stream()`**

In `the_one/llm/ollama_provider.py` find the `ollama_api.chat_stream(self.base_url, body)` call (around line 135) and change to:

```python
        async for chunk_dict in ollama_api.chat_stream(
            self.base_url, body, headers=self._auth_headers()
        ):
```

- [ ] **Step 7: Add stream + show_model auth-header tests**

Append to `tests/test_ollama_provider_auth.py`:

```python
@pytest.mark.asyncio
class TestOllamaApiHeadersParam:
    async def test_show_model_passes_headers(self, monkeypatch):
        from the_one.llm import ollama_api
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"capabilities": ["completion"]})

        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        await ollama_api.show_model(
            "http://localhost:11434", "model-x", headers={"Authorization": "Bearer x"}
        )
        assert captured[0].headers.get("authorization") == "Bearer x"

    async def test_chat_stream_passes_headers(self, monkeypatch):
        from the_one.llm import ollama_api
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, text="data: [DONE]\n\n")

        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

        async for _ in ollama_api.chat_stream(
            "http://localhost:11434/v1",
            {"model": "m", "messages": []},
            headers={"Authorization": "Bearer y"},
        ):
            pass
        assert captured[0].headers.get("authorization") == "Bearer y"
```

- [ ] **Step 8: Run all tests, verify pass**

```bash
.venv/bin/pytest tests/test_ollama_provider_auth.py tests/test_llm_registry.py -v
```

Expected: All pass. Also ensure pre-existing tests still pass:

```bash
.venv/bin/pytest tests/ -m 'not browser and not live and not pixel' -q --tb=line 2>&1 | tail -15
```

Expected: previous baseline 1074 → 1080+ now passing (4 new auth tests added).

- [ ] **Step 9: Commit**

```bash
git add the_one/llm/ollama_provider.py the_one/llm/ollama_api.py tests/test_ollama_provider_auth.py
git commit -m "fix(llm): thread Authorization header through OllamaProvider

Adds api_key kwarg + _auth_headers() helper. Empty/whitespace strings
treated as 'no key' to preserve OSS Ollama compat. Threaded into
complete(), stream(), ollama_api.show_model(), ollama_api.chat_stream().
Unblocks the openai-compatible path against authenticated servers."
```

---

## Task 4: openrouter_api helpers (list_models, verify_key, get_model_capabilities)

**Files:**
- Create: `the_one/llm/openrouter_api.py`
- Create: `tests/test_openrouter_api.py`

**Why:** Single source of truth for both the admin model-list endpoint and the Studio capability lookup. Cache keyed on `(base_url, sha256(api_key)[:16])` to avoid cross-account list bleed.

- [ ] **Step 1: Write failing tests in `tests/test_openrouter_api.py`**

```python
"""Tests for openrouter_api helper module."""
from __future__ import annotations

import time

import httpx
import pytest

from the_one.llm import openrouter_api


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test gets a clean module-level cache."""
    openrouter_api._models_cache.clear()
    yield
    openrouter_api._models_cache.clear()


def _mock_async_client(monkeypatch, handler):
    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


@pytest.mark.asyncio
class TestListModels:
    async def test_returns_data_array(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": "m1"}, {"id": "m2"}]})
        _mock_async_client(monkeypatch, handler)

        result = await openrouter_api.list_models("https://openrouter.ai/api/v1", "k1")
        assert result == [{"id": "m1"}, {"id": "m2"}]

    async def test_sends_authorization_when_key_set(self, monkeypatch):
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"data": []})
        _mock_async_client(monkeypatch, handler)

        await openrouter_api.list_models("https://openrouter.ai/api/v1", "sk-123")
        assert captured[0].headers.get("authorization") == "Bearer sk-123"

    async def test_no_authorization_when_key_empty(self, monkeypatch):
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"data": []})
        _mock_async_client(monkeypatch, handler)

        await openrouter_api.list_models("https://openrouter.ai/api/v1", "")
        assert "authorization" not in {k.lower() for k in captured[0].headers.keys()}

    async def test_raises_on_500(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")
        _mock_async_client(monkeypatch, handler)

        with pytest.raises(httpx.HTTPStatusError):
            await openrouter_api.list_models("https://openrouter.ai/api/v1", "k1")

    async def test_raises_on_network_error(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("nope")
        _mock_async_client(monkeypatch, handler)

        with pytest.raises(httpx.RequestError):
            await openrouter_api.list_models("https://openrouter.ai/api/v1", "k1")

    async def test_cache_keyed_on_base_url_and_api_key_hash(self, monkeypatch):
        call_count = {"n": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        _mock_async_client(monkeypatch, handler)

        # Two calls with the same (base_url, api_key) — only ONE upstream fetch
        await openrouter_api.list_models("https://openrouter.ai/api/v1", "key-A")
        await openrouter_api.list_models("https://openrouter.ai/api/v1", "key-A")
        assert call_count["n"] == 1

        # Different api_key on same base_url — separate cache entry
        await openrouter_api.list_models("https://openrouter.ai/api/v1", "key-B")
        assert call_count["n"] == 2

    async def test_cache_ttl_expiry(self, monkeypatch):
        call_count = {"n": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(200, json={"data": []})
        _mock_async_client(monkeypatch, handler)

        await openrouter_api.list_models("https://openrouter.ai/api/v1", "k")
        # Force expiry by rewriting the cache entry's timestamp
        for k in list(openrouter_api._models_cache.keys()):
            payload, _ = openrouter_api._models_cache[k]
            openrouter_api._models_cache[k] = (payload, time.time() - 999)

        await openrouter_api.list_models("https://openrouter.ai/api/v1", "k")
        assert call_count["n"] == 2


@pytest.mark.asyncio
class TestVerifyKey:
    async def test_returns_dict_on_success(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"label": "test"}})
        _mock_async_client(monkeypatch, handler)

        result = await openrouter_api.verify_key("https://openrouter.ai/api/v1", "good")
        assert result == {"data": {"label": "test"}}

    async def test_raises_on_401(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "Invalid"}})
        _mock_async_client(monkeypatch, handler)

        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await openrouter_api.verify_key("https://openrouter.ai/api/v1", "bad")
        assert excinfo.value.response.status_code == 401


@pytest.mark.asyncio
class TestGetModelCapabilities:
    async def test_returns_supported_parameters_as_frozenset(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [
                {"id": "m1", "supported_parameters": ["tools", "reasoning"]},
            ]})
        _mock_async_client(monkeypatch, handler)

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "m1"
        )
        assert caps == frozenset({"tools", "reasoning"})

    async def test_fail_open_on_fetch_error(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")
        _mock_async_client(monkeypatch, handler)

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "m1"
        )
        assert caps is None

    async def test_fail_open_on_missing_model(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": "other"}]})
        _mock_async_client(monkeypatch, handler)

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "missing"
        )
        assert caps is None

    async def test_fail_open_on_missing_supported_parameters(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": "m1"}]})  # no key
        _mock_async_client(monkeypatch, handler)

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "m1"
        )
        assert caps is None

    async def test_fail_open_on_empty_supported_parameters(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [
                {"id": "m1", "supported_parameters": []},
            ]})
        _mock_async_client(monkeypatch, handler)

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "m1"
        )
        assert caps is None
```

- [ ] **Step 2: Run failing tests**

```bash
.venv/bin/pytest tests/test_openrouter_api.py -v
```

Expected: ALL FAIL — module doesn't exist yet (ImportError) or has no `_models_cache`.

- [ ] **Step 3: Create `the_one/llm/openrouter_api.py`**

```python
"""OpenRouter REST API client.

Helpers for the model-list (``/models``), key-verification (``/auth/key``),
and capability lookup endpoints. Mirrors ``the_one/llm/ollama_api.py`` shape.

Design contract:
- ``list_models`` / ``verify_key`` raise on failure (caller translates to HTTP).
- ``get_model_capabilities`` is a separate fail-open wrapper for the Studio
  capability chip — returns ``None`` on any error or absent capability data.

Cache:
- ``_models_cache`` keyed on ``(base_url, sha256(api_key)[:16])``, TTL 300s.
- Hashing the api_key avoids cross-account list bleed if two configs share a
  base_url with different keys.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx

_CACHE_TTL = 300  # seconds
_models_cache: dict[tuple[str, str], tuple[list[dict[str, Any]], float]] = {}


def _cache_key(base_url: str, api_key: str | None) -> tuple[str, str]:
    raw = (api_key or "").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return (base_url.rstrip("/"), digest)


def _auth_headers(api_key: str | None) -> dict[str, str]:
    key = (api_key or "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


async def list_models(base_url: str, api_key: str | None) -> list[dict[str, Any]]:
    """Fetch and cache ``GET {base_url}/models``.

    Raises:
        httpx.HTTPStatusError: on 4xx / 5xx response.
        httpx.RequestError: on network failure.
        ValueError: on JSON parse failure.
    """
    cache_key = _cache_key(base_url, api_key)
    cached = _models_cache.get(cache_key)
    if cached is not None and (time.time() - cached[1]) < _CACHE_TTL:
        return cached[0]

    url = base_url.rstrip("/") + "/models"
    async with httpx.AsyncClient(timeout=30, headers=_auth_headers(api_key)) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, dict) or "data" not in data:
        raise ValueError(f"Unexpected payload shape from {url}: missing 'data' key")
    models = data["data"]
    if not isinstance(models, list):
        raise ValueError(f"Unexpected 'data' type from {url}: {type(models).__name__}")
    _models_cache[cache_key] = (models, time.time())
    return models


async def verify_key(base_url: str, api_key: str) -> dict[str, Any]:
    """Probe ``GET {base_url}/auth/key`` for actual key validity.

    Raises:
        httpx.HTTPStatusError: on 401 (invalid key) / 4xx / 5xx.
        httpx.RequestError: on network failure.
    """
    url = base_url.rstrip("/") + "/auth/key"
    async with httpx.AsyncClient(timeout=15, headers=_auth_headers(api_key)) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def get_model_capabilities(
    base_url: str,
    api_key: str | None,
    model: str,
) -> frozenset[str] | None:
    """Return ``supported_parameters`` for ``model`` as a frozenset.

    Returns ``None`` on:
    - any fetch failure (mirrors ollama_api.get_model_capabilities semantics)
    - model not found in the listing
    - missing ``supported_parameters`` field
    - empty ``supported_parameters`` list

    The caller (Studio capability chip) treats ``None`` as "unknown" and
    renders no chip, ensuring fail-open behavior.
    """
    try:
        models = await list_models(base_url, api_key)
    except (httpx.HTTPError, ValueError):
        return None

    for entry in models:
        if entry.get("id") == model:
            params = entry.get("supported_parameters")
            if not isinstance(params, list) or len(params) == 0:
                return None
            return frozenset(p for p in params if isinstance(p, str))
    return None
```

- [ ] **Step 4: Run tests, verify pass**

```bash
.venv/bin/pytest tests/test_openrouter_api.py -v
```

Expected: All 13 tests pass.

- [ ] **Step 5: Commit**

```bash
git add the_one/llm/openrouter_api.py tests/test_openrouter_api.py
git commit -m "feat(llm): add openrouter_api helpers

- list_models with (base_url, sha256(api_key)[:16]) keyed 300s cache
- verify_key against /auth/key for actual key validation
- get_model_capabilities fail-open wrapper for Studio chip
- Helpers raise; endpoints translate (Decision 7)"
```

---

## Task 5: OpenRouterProvider class

**Files:**
- Create: `the_one/llm/openrouter_provider.py`
- Create: `tests/test_openrouter_provider.py`

**Why:** First-class provider class with the empty-string opt-out (Decision 5) so the OpenAI SDK does not leak `OPENAI_API_KEY` into OpenRouter. Adds optional `HTTP-Referer` / `X-Title` ranking headers from `config: dict`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_openrouter_provider.py`:

```python
"""Tests for OpenRouterProvider."""
from __future__ import annotations

import os

import httpx
import pytest

from the_one.llm.base import Message, Role


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Each test starts with no OPENAI_API_KEY / OPENROUTER_API_KEY in env."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


class TestNoLeakInvariant:
    def test_no_leak_with_api_key_none(self, monkeypatch):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked")
        prov = OpenRouterProvider(model="m", api_key=None)
        # Empty-string opt-out: api_key MUST NOT be the OpenAI env value.
        assert prov.client.api_key == ""

    def test_no_leak_with_empty_string_api_key(self, monkeypatch):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked")
        prov = OpenRouterProvider(model="m", api_key="")
        assert prov.client.api_key == ""

    def test_uses_openrouter_env_when_arg_none(self, monkeypatch):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")
        prov = OpenRouterProvider(model="m", api_key=None)
        assert prov.client.api_key == "sk-or-env"

    def test_explicit_arg_wins_over_env(self, monkeypatch):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
        prov = OpenRouterProvider(model="m", api_key="sk-explicit")
        assert prov.client.api_key == "sk-explicit"


class TestBaseUrl:
    def test_default_base_url(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(model="m", api_key="x")
        assert "openrouter.ai/api/v1" in str(prov.client.base_url)

    def test_custom_base_url_honored(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(
            model="m", api_key="x", base_url="https://example.com/api/v1"
        )
        assert "example.com/api/v1" in str(prov.client.base_url)


class TestRankingHeaders:
    def test_referer_header_set_when_config_referer(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(
            model="m", api_key="x", config={"referer": "https://myapp.example"}
        )
        # The SDK exposes default_headers as a Mapping
        assert prov.client.default_headers.get("HTTP-Referer") == "https://myapp.example"

    def test_title_header_set_when_config_title(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(
            model="m", api_key="x", config={"title": "MyApp"}
        )
        assert prov.client.default_headers.get("X-Title") == "MyApp"

    def test_no_ranking_headers_when_config_empty(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(model="m", api_key="x", config={})
        # default_headers always has SDK-internal headers but should NOT have these
        assert "HTTP-Referer" not in prov.client.default_headers
        assert "X-Title" not in prov.client.default_headers

    def test_no_ranking_headers_when_config_keys_empty_string(self):
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = OpenRouterProvider(
            model="m", api_key="x", config={"referer": "", "title": ""}
        )
        assert "HTTP-Referer" not in prov.client.default_headers
        assert "X-Title" not in prov.client.default_headers


class TestInstanceAttributeParity:
    def test_subclass_has_all_parent_instance_attrs(self):
        """If OpenAIProvider.__init__ ever adds a new self.X, this test fails
        and forces the OpenRouterProvider author to mirror or refactor."""
        from the_one.llm.openai_provider import OpenAIProvider
        from the_one.llm.openrouter_provider import OpenRouterProvider

        parent = OpenAIProvider(model="m", api_key="x")
        sub = OpenRouterProvider(model="m", api_key="x")
        parent_attrs = set(vars(parent).keys())
        sub_attrs = set(vars(sub).keys())
        missing = parent_attrs - sub_attrs
        assert missing == set(), (
            f"OpenRouterProvider missing parent attrs {missing}. "
            "Mirror in __init__ or refactor toward env_var_name pattern."
        )


@pytest.mark.asyncio
class TestStreaming:
    async def test_stream_without_trailing_usage_chunk(self):
        """If upstream omits the trailing usage chunk, stream must not crash
        and final StreamChunk must report usage=None."""
        from the_one.llm.openrouter_provider import OpenRouterProvider

        # Synthesize an SSE stream that ends with a content delta but NO
        # trailing usage chunk and NO empty-choices metadata chunk.
        sse_body = (
            'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
            'data: [DONE]\n\n'
        )

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=sse_body,
                headers={"content-type": "text/event-stream"},
            )

        # Inject a MockTransport-backed httpx.AsyncClient into the SDK
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)

        # Construct the provider, then swap the SDK's underlying http client
        prov = OpenRouterProvider(model="m", api_key="x")
        # openai SDK 2.x exposes _client.* — test via the public AsyncOpenAI
        # constructor instead by rebuilding with http_client.
        import openai
        prov.client = openai.AsyncOpenAI(api_key="x", base_url=str(prov.client.base_url), http_client=client)

        chunks = []
        async for chunk in prov.stream([Message(role=Role.USER, content="hi")]):
            chunks.append(chunk)
        assert chunks  # must not be empty
        assert chunks[-1].is_final is True
        assert chunks[-1].usage is None
```

- [ ] **Step 2: Run failing tests**

```bash
.venv/bin/pytest tests/test_openrouter_provider.py -v
```

Expected: ALL FAIL (`ModuleNotFoundError: the_one.llm.openrouter_provider`).

- [ ] **Step 3: Create `the_one/llm/openrouter_provider.py`**

```python
"""OpenRouter provider — thin OpenAIProvider subclass.

Uses the OpenAI Python SDK against ``https://openrouter.ai/api/v1`` with
optional ranking headers (``HTTP-Referer``, ``X-Title``) and the empty-string
api_key opt-out so that ``OPENAI_API_KEY`` env var cannot leak into the
OpenRouter client.

The constructor deliberately does NOT call ``super().__init__()``; that
would trigger the OpenAI SDK env-var fallback. See
``test_instance_attribute_parity`` — if a parent attribute is added later,
that test fails and forces a sync.
"""
from __future__ import annotations

import os
from typing import Any

import openai

from the_one.llm.openai_provider import OpenAIProvider
from the_one.llm.registry import register_provider


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
        # Override constructor entirely — do NOT call super().__init__() —
        # so the parent's OPENAI_API_KEY env-var fallback does not leak to
        # OpenRouter. Pinned by test_no_leak_of_openai_env_var.
        self.model = model

        # Empty-string opt-out (Decision 5): openai 2.15.0 reads
        # OPENAI_API_KEY ONLY when api_key is None. Coerce to "" so the
        # SDK skips the env fallback. Empty key → upstream 401 with a
        # clear message that the agent loop surfaces verbatim.
        resolved_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if resolved_key is None:
            resolved_key = ""

        cfg = config or {}
        headers: dict[str, str] = {}
        # referer / title are validated at the POST /api/providers
        # boundary (Decision 6); this code trusts the saved value but
        # still skips empty strings so absent headers stay absent.
        if cfg.get("referer"):
            headers["HTTP-Referer"] = cfg["referer"]
        if cfg.get("title"):
            headers["X-Title"] = cfg["title"]

        client_kwargs: dict[str, Any] = {"api_key": resolved_key, "base_url": base_url}
        if headers:
            client_kwargs["default_headers"] = headers
        self.client = openai.AsyncOpenAI(**client_kwargs)


register_provider("openrouter", OpenRouterProvider)
```

- [ ] **Step 4: Run tests, verify pass**

```bash
.venv/bin/pytest tests/test_openrouter_provider.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add the_one/llm/openrouter_provider.py tests/test_openrouter_provider.py
git commit -m "feat(llm): add OpenRouterProvider with empty-string opt-out

- Subclass of OpenAIProvider with custom base_url and ranking headers
- api_key='' opt-out prevents OPENAI_API_KEY env-var leak (Decision 5)
- Optional HTTP-Referer / X-Title from config dict
- Instance-attribute parity test guards against future drift"
```

---

## Task 6: Registry loader + factory map

**Files:**
- Modify: `the_one/llm/registry.py:24-39` (add `openrouter` loader)
- Modify: `the_one/agent/factory.py:15-21` (add `_PROVIDER_TYPE_MAP` entry)
- Modify: `tests/test_llm_registry.py` (add openrouter lazy-load test)

**Why:** Make `get_provider("openrouter")` work via the standard registry path, and let `AgentFactory.create()` translate the DB type to the registry name.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_llm_registry.py`:

```python
class TestLazyLoadOpenRouter:
    def test_get_openrouter_lazy_loads(self):
        """get_provider('openrouter') should lazy-import the openrouter_provider module."""
        from the_one.llm.openrouter_provider import OpenRouterProvider

        prov = llm_registry.get_provider("openrouter", model="m", api_key="x")
        assert isinstance(prov, OpenRouterProvider)
```

In `tests/test_factory.py`, append:

```python
class TestProviderTypeMap:
    def test_openrouter_in_provider_type_map(self):
        from the_one.agent.factory import _PROVIDER_TYPE_MAP

        assert _PROVIDER_TYPE_MAP.get("openrouter") == "openrouter"
```

- [ ] **Step 2: Run failing tests**

```bash
.venv/bin/pytest tests/test_llm_registry.py::TestLazyLoadOpenRouter tests/test_factory.py::TestProviderTypeMap -v
```

Expected: FAIL — `Unknown LLM provider 'openrouter'` and `_PROVIDER_TYPE_MAP` missing the key.

- [ ] **Step 3: Add the registry loader**

In `the_one/llm/registry.py:25-30` change:

```python
    loaders = {
        "openai": lambda: __import__("the_one.llm.openai_provider", fromlist=["_"]),
        "anthropic": lambda: __import__("the_one.llm.anthropic_provider", fromlist=["_"]),
        "ollama": lambda: __import__("the_one.llm.ollama_provider", fromlist=["_"]),
        "mock": lambda: __import__("the_one.llm.mock", fromlist=["_"]),
    }
```

to:

```python
    loaders = {
        "openai": lambda: __import__("the_one.llm.openai_provider", fromlist=["_"]),
        "anthropic": lambda: __import__("the_one.llm.anthropic_provider", fromlist=["_"]),
        "ollama": lambda: __import__("the_one.llm.ollama_provider", fromlist=["_"]),
        "mock": lambda: __import__("the_one.llm.mock", fromlist=["_"]),
        "openrouter": lambda: __import__("the_one.llm.openrouter_provider", fromlist=["_"]),
    }
```

Also update the error message branch (line 34-38) so an `openrouter` ImportError mentions the correct extra:

```python
    if name in loaders:
        try:
            loaders[name]()
        except ImportError as e:
            extra = "openai" if name == "openrouter" else name
            raise ImportError(
                f"Provider '{name}' requires extra dependencies. "
                f"Install with: pip install 'the-one[{extra}]'"
            ) from e
```

- [ ] **Step 4: Add the factory map entry**

In `the_one/agent/factory.py:15-21` change:

```python
_PROVIDER_TYPE_MAP = {
    "ollama": "ollama",
    "openai-compatible": "ollama",
    "openai": "openai",
    "anthropic": "anthropic",
    "mock": "mock",
}
```

to:

```python
_PROVIDER_TYPE_MAP = {
    "ollama": "ollama",
    "openai-compatible": "ollama",
    "openai": "openai",
    "anthropic": "anthropic",
    "mock": "mock",
    "openrouter": "openrouter",
}
```

- [ ] **Step 5: Run tests, verify pass**

```bash
.venv/bin/pytest tests/test_llm_registry.py tests/test_factory.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add the_one/llm/registry.py the_one/agent/factory.py tests/test_llm_registry.py tests/test_factory.py
git commit -m "feat(llm): wire openrouter into registry + factory map

- Registry lazy-loader for 'openrouter' (uses [openai] extra, NOT a
  non-existent [openrouter] extra)
- AgentFactory _PROVIDER_TYPE_MAP entry for openrouter -> openrouter"
```

---

## Task 7: API endpoints — types, models, test, validation

**Files:**
- Modify: `the_one/interfaces/web/api.py:715` (`/types` endpoint adds `openrouter`)
- Modify: `the_one/interfaces/web/api.py:737-805` (`POST /providers`, `PUT /providers/{id}` validate `referer` / `title`)
- Modify: `the_one/interfaces/web/api.py:841-902` (`POST /providers/{id}/test` adds openrouter branch)
- Modify: `the_one/interfaces/web/api.py:904-978` (`GET /providers/{id}/models` adds openrouter branch)
- Modify: `tests/test_provider_api.py` (extend with openrouter coverage + sanitization tests)

**Why:** Operator-facing surface. Validation lives at the trust boundary (Decision 6). Test endpoint differentiates "key set" vs "no key" status (Decision 8).

- [ ] **Step 1: Look up the existing endpoint shape (read context)**

```bash
.venv/bin/python3 -c "import inspect, the_one.interfaces.web.api as a; print(inspect.getsource(a.list_provider_types))"
.venv/bin/python3 -c "import inspect, the_one.interfaces.web.api as a; print(inspect.getsource(a.test_provider))"
.venv/bin/python3 -c "import inspect, the_one.interfaces.web.api as a; print(inspect.getsource(a.list_provider_models))"
.venv/bin/python3 -c "import inspect, the_one.interfaces.web.api as a; print(inspect.getsource(a.create_provider))"
```

This is reference reading — adapt the new code below to fit the existing handler pattern (the line numbers may have drifted).

- [ ] **Step 2: Write failing tests**

Append to `tests/test_provider_api.py` a `class TestOpenRouterApi:` block:

```python
class TestOpenRouterTypes:
    @pytest.mark.asyncio
    async def test_types_includes_openrouter(self, client):
        resp = await client.get("/api/providers/types")
        assert resp.status_code == 200
        types = resp.json()
        values = {t["value"] for t in types}
        assert "openrouter" in values


class TestOpenRouterValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_referer",
        [
            "https://x.com\r\nX-Injected: 1",
            "https://x.com\nX-Injected: 1",
            "https://x.com\x00",
            "not-a-url",
            "ftp://example.com",
        ],
    )
    async def test_referer_invalid_rejected_with_422(self, client, bad_referer):
        body = {
            "name": "OR",
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "k",
            "config": {"referer": bad_referer},
        }
        resp = await client.post("/api/providers", json=body)
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_title",
        [
            "with\r\nbreak",
            "with\nbreak",
            "with\x00null",
            "x" * 65,  # too long
        ],
    )
    async def test_title_invalid_rejected_with_422(self, client, bad_title):
        body = {
            "name": "OR",
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "k",
            "config": {"title": bad_title},
        }
        resp = await client.post("/api/providers", json=body)
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_round_trip_omits_empty_config_keys(self, client):
        body = {
            "name": "OR",
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "k",
            "config": {"referer": "", "title": ""},
        }
        resp = await client.post("/api/providers", json=body)
        assert resp.status_code in (200, 201), resp.text
        prov_id = resp.json()["id"]

        get_resp = await client.get(f"/api/providers/{prov_id}")
        cfg = get_resp.json()["config"]
        assert "referer" not in cfg
        assert "title" not in cfg

    @pytest.mark.asyncio
    async def test_round_trip_preserves_valid_config(self, client):
        body = {
            "name": "OR",
            "type": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "k",
            "config": {"referer": "https://myapp.example", "title": "MyApp"},
        }
        resp = await client.post("/api/providers", json=body)
        assert resp.status_code in (200, 201), resp.text
        prov_id = resp.json()["id"]

        get_resp = await client.get(f"/api/providers/{prov_id}")
        cfg = get_resp.json()["config"]
        assert cfg.get("referer") == "https://myapp.example"
        assert cfg.get("title") == "MyApp"
```

- [ ] **Step 3: Run failing tests**

```bash
.venv/bin/pytest tests/test_provider_api.py::TestOpenRouterTypes tests/test_provider_api.py::TestOpenRouterValidation -v
```

Expected: FAIL — types missing `openrouter`; validation accepts CRLF; etc.

- [ ] **Step 4: Add `openrouter` to the `/types` endpoint**

Find the existing `list_provider_types` handler in `the_one/interfaces/web/api.py:715-735` (the body returns a list of `{value, label}` dicts; mock entry is filtered by `dev_mode`). Append `{"value": "openrouter", "label": "OpenRouter"}` to the static list. The OpenRouter entry must NOT be filtered by `dev_mode` (it's a real, always-available provider).

If the existing code looks like:

```python
TYPES = [
    {"value": "ollama", "label": "Ollama"},
    {"value": "openai-compatible", "label": "OpenAI-compatible"},
    {"value": "openai", "label": "OpenAI"},
    {"value": "anthropic", "label": "Anthropic"},
]
# (mock added conditionally on dev_mode)
```

Add `{"value": "openrouter", "label": "OpenRouter"}` immediately after `anthropic`.

- [ ] **Step 5: Add validation helpers near the top of `the_one/interfaces/web/api.py` (just below the `_TESTABLE_TOOLS` constant around line 68):**

```python
# OpenRouter ranking-header validation (Decision 6).
# httpx 0.28.1 does NOT sanitize CR/LF/NUL in header values, so we reject
# them at the API boundary before storing.
_FORBIDDEN_HEADER_CHARS = ("\r", "\n", "\x00")
_OPENROUTER_TITLE_MAX = 64


def _validate_openrouter_config(config: dict | None) -> dict:
    """Sanitize the openrouter ranking-header config.

    - Rejects ``referer`` / ``title`` with CR/LF/NUL.
    - Requires ``referer`` to parse as ``http(s)://`` URL with non-empty netloc.
    - Bounds ``title`` length to 64.
    - Empty strings are dropped from the returned dict (absent stays absent
      on round-trip).

    Raises ``HTTPException(422, ...)`` on validation failure.
    """
    from urllib.parse import urlparse

    cfg = dict(config or {})
    referer = cfg.get("referer")
    if isinstance(referer, str):
        if any(c in referer for c in _FORBIDDEN_HEADER_CHARS):
            raise HTTPException(
                status_code=422,
                detail="config.referer contains a forbidden control character",
            )
        if referer.strip() == "":
            cfg.pop("referer", None)
        else:
            parsed = urlparse(referer)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise HTTPException(
                    status_code=422,
                    detail="config.referer must be an http(s):// URL",
                )

    title = cfg.get("title")
    if isinstance(title, str):
        if any(c in title for c in _FORBIDDEN_HEADER_CHARS):
            raise HTTPException(
                status_code=422,
                detail="config.title contains a forbidden control character",
            )
        if title.strip() == "":
            cfg.pop("title", None)
        elif len(title) > _OPENROUTER_TITLE_MAX:
            raise HTTPException(
                status_code=422,
                detail=f"config.title must be ≤ {_OPENROUTER_TITLE_MAX} chars",
            )

    return cfg
```

- [ ] **Step 6: Wire validation into the `POST /providers` and `PUT /providers/{id}` handlers**

Inside both `create_provider` and `update_provider`, after the request body is parsed and BEFORE the row is written to the repo, add:

```python
    if body.type == "openrouter":
        body.config = _validate_openrouter_config(body.config)
```

(`body` is the Pydantic model the existing handler already parses; the field name may be `payload`, `provider`, etc. — match the existing convention in the file.)

- [ ] **Step 7: Add the openrouter branch to `GET /providers/{id}/models`**

In `list_provider_models` (~line 904), find the `if provider.type == "ollama": ...` branch and append a sibling branch:

```python
    elif provider.type == "openrouter":
        from the_one.llm import openrouter_api
        try:
            raw = await openrouter_api.list_models(provider.base_url, provider.api_key)
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            raise HTTPException(status_code=502, detail=f"OpenRouter unreachable: {e}")
        return [
            {
                "id": m.get("id"),
                "name": m.get("name", m.get("id")),
                "supported_parameters": m.get("supported_parameters") or [],
                "context_length": m.get("context_length"),
                "description": m.get("description", ""),
                "capabilities": m.get("supported_parameters") or [],  # alias for Studio chip
            }
            for m in raw
        ]
```

NOTE: `provider.api_key` is the DECRYPTED key (the repo `get(...)` already decrypts it).

- [ ] **Step 8: Add the openrouter branch to `POST /providers/{id}/test`**

In `test_provider` (~line 841), find the existing branches (`if provider.type == "ollama": ...`, `elif provider.type == "openai": ...`, etc.) and append:

```python
    elif provider.type == "openrouter":
        from the_one.llm import openrouter_api
        key = (provider.api_key or "").strip()
        try:
            if key:
                await openrouter_api.verify_key(provider.base_url, key)
                models = await openrouter_api.list_models(provider.base_url, key)
                return {
                    "status": "ok",
                    "detail": f"Connected. Key valid; {len(models)} models available.",
                }
            else:
                models = await openrouter_api.list_models(provider.base_url, "")
                return {
                    "status": "ok",
                    "detail": (
                        f"Reachable. Add an API key to enable chat. "
                        f"{len(models)} models available."
                    ),
                }
        except httpx.HTTPStatusError as e:
            body = (e.response.text or "")[:200]
            return {
                "status": "error",
                "detail": f"HTTP {e.response.status_code}: {body}",
            }
        except httpx.RequestError as e:
            return {"status": "error", "detail": f"Network error: {e}"}
        except Exception as e:  # noqa: BLE001 — endpoint must never 5xx
            return {"status": "error", "detail": str(e)}
```

- [ ] **Step 9: Run tests, verify pass**

```bash
.venv/bin/pytest tests/test_provider_api.py -v
```

Expected: All new tests pass; pre-existing tests still pass.

- [ ] **Step 10: Commit**

```bash
git add the_one/interfaces/web/api.py tests/test_provider_api.py
git commit -m "feat(api): wire openrouter into /types, /models, /test, CRUD validation

- /types lists openrouter (always, regardless of dev_mode)
- POST/PUT validate config.referer (URL + control chars) and
  config.title (max 64, control chars) per Decision 6
- /models calls openrouter_api.list_models, translates to 502 on failure
- /test differentiates 'key set' (verify_key) vs 'no key' (reachable only)
  per Decision 8"
```

---

## Task 8: Factory integration test

**Files:**
- Create: `tests/test_factory_openrouter.py`

**Why:** End-to-end check that a stored encrypted `openrouter` row + agent referencing it leads to an `OpenRouterProvider` instance with the decrypted key wired through. Catches every wiring change at once.

- [ ] **Step 1: Write the test**

```python
"""End-to-end factory integration for the openrouter provider type."""
from __future__ import annotations

import pytest
import aiosqlite
from cryptography.fernet import Fernet

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import LLMProviderRepository, SQLiteAgentStore
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor


@pytest.mark.asyncio
async def test_factory_resolves_openrouter_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    # Set up isolated DB + encryptor
    db_path = tmp_path / "test.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    enc = Encryptor(Fernet.generate_key())
    prov_repo = LLMProviderRepository(conn, enc)
    agent_store = SQLiteAgentStore(conn)

    # Insert an openrouter provider config with a plaintext-then-encrypted key
    cfg = LLMProviderConfig(
        id="p-or",
        name="OR",
        type="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-stored",
        config={"referer": "https://myapp.example", "title": "MyApp"},
    )
    await prov_repo.create(cfg)

    # Insert an agent referencing it
    agent_cfg = AgentConfig(
        name="alice",
        provider_config_id="p-or",
        llm_model="anthropic/claude-3.5-sonnet",
    )
    await agent_store.save(agent_cfg)

    # Patch settings + the get_connection / get_encryptor singletons
    # used by AgentFactory.create
    from the_one.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from the_one.db import connection as _conn_mod
    monkeypatch.setattr(_conn_mod, "_connection", conn)
    from the_one import encryption as _enc_mod
    monkeypatch.setattr(_enc_mod, "_encryptor", enc, raising=False)
    # If get_encryptor caches by data_dir, also reset its singleton attr
    if hasattr(_enc_mod, "_encryptor_singleton"):
        monkeypatch.setattr(_enc_mod, "_encryptor_singleton", None)

    # Provide a tool-providers list with no tools (avoids touching the
    # filesystem allowlist in this test)
    factory = AgentFactory(store=agent_store, tool_providers=[])
    agent = await factory.create("alice")

    # Assert llm is an OpenRouterProvider with the decrypted key
    from the_one.llm.openrouter_provider import OpenRouterProvider
    assert isinstance(agent.llm, OpenRouterProvider)
    assert agent.llm.client.api_key == "sk-stored"
    assert agent.llm.model == "anthropic/claude-3.5-sonnet"
    assert "openrouter.ai" in str(agent.llm.client.base_url)
    # Ranking headers came through
    assert agent.llm.client.default_headers.get("HTTP-Referer") == "https://myapp.example"
    assert agent.llm.client.default_headers.get("X-Title") == "MyApp"

    await conn.close()
```

- [ ] **Step 2: Run the test, may need fixture adjustment**

```bash
.venv/bin/pytest tests/test_factory_openrouter.py -v
```

If the test fails with "encryption key fixture mismatch" or similar, inspect `the_one/encryption.py::get_encryptor` to confirm the right singleton-reset path (the test above patches the module's `_encryptor` if it exists). If the actual cache attr name differs, update the monkeypatch line in Step 1's test code.

Expected (after any fixture tuning): PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_factory_openrouter.py
git commit -m "test(factory): pin end-to-end openrouter provider resolution

Stores an encrypted openrouter row + agent, calls AgentFactory.create,
asserts the returned Agent.llm is an OpenRouterProvider with the
decrypted key, model, base_url, and ranking headers all wired through."
```

---

## Task 9: Frontend admin — TYPE_DEFAULTS, badge, optional fields, validation

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/admin.js:166-173` (TYPE_DEFAULTS)
- Modify: `the_one/interfaces/web/static/js/areas/admin/providers-grid.js:21` (KNOWN_BADGE_TYPES)
- Modify: `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` (render optional fields when type=openrouter; client-side validation)

**Why:** Operator-facing form. Pre-fills `base_url`. Renders two optional inputs for `App URL` / `App Name`. Client-side rejects control chars and non-URL referer (server still re-validates).

- [ ] **Step 1: Extend `TYPE_DEFAULTS` in `admin.js`**

In `the_one/interfaces/web/static/js/areas/admin.js:166` find the `TYPE_DEFAULTS` object:

```javascript
    var TYPE_DEFAULTS = {
      'ollama': { base_url: 'http://localhost:11434/v1', showBaseUrl: true, showApiKey: false },
      'openai-compatible': { base_url: '', showBaseUrl: true, showApiKey: true },
      'openai': { base_url: 'https://api.openai.com/v1', showBaseUrl: false, showApiKey: true },
      'anthropic': { base_url: 'https://api.anthropic.com', showBaseUrl: false, showApiKey: true },
      'mock': { base_url: '', showBaseUrl: false, showApiKey: false }
    };
```

Add a sibling entry **before** the closing brace:

```javascript
      'openrouter': { base_url: 'https://openrouter.ai/api/v1', showBaseUrl: true, showApiKey: true, showOpenRouterConfig: true }
```

(Comma after the previous entry — JS object-literal comma rules.)

- [ ] **Step 2: Extend `KNOWN_BADGE_TYPES`**

In `the_one/interfaces/web/static/js/areas/admin/providers-grid.js:21` change:

```javascript
  var KNOWN_BADGE_TYPES = ['ollama', 'openai-compatible', 'openai', 'anthropic', 'mock'];
```

to:

```javascript
  var KNOWN_BADGE_TYPES = ['ollama', 'openai-compatible', 'openai', 'anthropic', 'mock', 'openrouter'];
```

- [ ] **Step 3: Render optional `referer` / `title` fields when type=openrouter**

In `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`, locate the form-rendering function (look for where `defaults.showApiKey` / `defaults.showBaseUrl` gate field visibility — around line 121-226). After the `api_key` field's HTML block, add a conditional that renders two extra inputs when `defaults.showOpenRouterConfig`:

```javascript
      // OpenRouter ranking headers (Decision 3) — operator-configurable
      // optional inputs. Empty values are dropped at save time so the
      // server sees the headers as absent.
      if (defaults.showOpenRouterConfig) {
        var refererVal = (provider && provider.config && provider.config.referer) || '';
        var titleVal = (provider && provider.config && provider.config.title) || '';
        html += ''
          + '<div class="field-row">'
          + '  <label for="prov-referer">App URL (optional)</label>'
          + '  <input type="text" id="prov-referer" class="field-input"'
          + '         data-field="config.referer"'
          + '         placeholder="https://your-app.example.com"'
          + '         value="' + escapeAttr(refererVal) + '" />'
          + '  <small class="field-hint">Sent as HTTP-Referer for OpenRouter app rankings.</small>'
          + '</div>'
          + '<div class="field-row">'
          + '  <label for="prov-title">App Name (optional, max 64)</label>'
          + '  <input type="text" id="prov-title" class="field-input"'
          + '         data-field="config.title"'
          + '         maxlength="64"'
          + '         value="' + escapeAttr(titleVal) + '" />'
          + '  <small class="field-hint">Sent as X-Title for OpenRouter app rankings.</small>'
          + '</div>';
      }
```

(Adapt to the file's existing string-concat style; the surrounding code uses `'+ ...'` chains.)

- [ ] **Step 4: Wire the inputs into the save payload**

Find where the form's submit / save handler reads field values (search for the existing `data-field="api_key"` reading pattern). Where the save payload's `config` is assembled, add:

```javascript
      if (typeSelect.value === 'openrouter') {
        var refererInput = formEl.querySelector('[data-field="config.referer"]');
        var titleInput = formEl.querySelector('[data-field="config.title"]');
        var cfg = {};
        var ref = refererInput ? refererInput.value.trim() : '';
        var ttl = titleInput ? titleInput.value.trim() : '';
        // Client-side validation — server re-validates per Decision 6
        if (ref && /[\r\n\x00]/.test(ref)) {
          App.showFlash(formEl, 'App URL contains an invalid control character.', true);
          return;
        }
        if (ref && !/^https?:\/\//i.test(ref)) {
          App.showFlash(formEl, 'App URL must start with http:// or https://.', true);
          return;
        }
        if (ttl && /[\r\n\x00]/.test(ttl)) {
          App.showFlash(formEl, 'App Name contains an invalid control character.', true);
          return;
        }
        if (ref) cfg.referer = ref;
        if (ttl) cfg.title = ttl;
        payload.config = cfg;  // empty {} is fine — server treats absent keys as absent
      }
```

- [ ] **Step 5: Type-change preservation**

When the operator changes `type` on an existing provider (the `<select id="prov-type">` change handler around line 226), preserve `name`, `api_key`, `config` and reset only `base_url` to the new type's default. Find the existing `typeSelect.addEventListener('change', ...)` and ensure it does NOT clobber `api_key` or `config`. If the existing handler resets `base_url` from `TYPE_DEFAULTS[newType].base_url`, that's already correct — just make sure no `api_key` / `config` reset is added.

(If the existing handler already preserves user fields, this step is a no-op verification.)

- [ ] **Step 6: Manual verification (no JS unit tests in repo today)**

Run the Docker container against the worktree code path (mount the worktree explicitly):

```bash
# Quick smoke check via the live admin endpoints — proves the data path
.venv/bin/python3 -c "
from the_one.config import settings
import asyncio
from the_one.interfaces.web.api import router
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

async def go():
    app = FastAPI(); app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://t') as c:
        r = await c.get('/api/providers/types')
        print(r.json())

asyncio.run(go())
"
```

Expected: output includes `{'value': 'openrouter', 'label': 'OpenRouter'}`.

The full visual check is deferred to the browser test in Task 11.

- [ ] **Step 7: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/admin.js \
        the_one/interfaces/web/static/js/areas/admin/providers-grid.js \
        the_one/interfaces/web/static/js/areas/admin/provider-editor.js
git commit -m "feat(admin): openrouter provider type in form, badge, optional headers

- TYPE_DEFAULTS entry pre-fills base_url and exposes showOpenRouterConfig
- KNOWN_BADGE_TYPES includes openrouter
- Form renders optional App URL / App Name when type=openrouter
- Client-side validation rejects control chars and non-URL referer
- Empty inputs serialize to omitted config keys (Decision 6)"
```

---

## Task 10: Frontend Studio — datalist swap, capability cache, lifecycle

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/studio.js:739-810` (model-picker capability cache + render)
- Modify: `the_one/interfaces/web/static/js/areas/studio/general-tab.js:70-72` (rendering the `<select>` — extend to also render a `<datalist>` variant)

**Why:** Studio's existing `<select id="studio-model">` works fine at <50 entries. At ~370 OpenRouter models, datalist combobox is the cheap fix (Decision 2). Capability cache shape generalizes from Ollama's `capabilities` field to also accept OpenRouter's `supported_parameters`.

- [ ] **Step 1: Generalize the capability cache in `studio.js`**

In `the_one/interfaces/web/static/js/areas/studio.js:786-790` find:

```javascript
            if (Object.prototype.hasOwnProperty.call(models[i], 'capabilities')) {
              modelCapsBy[modelId] = models[i].capabilities;
            }
```

and replace with:

```javascript
            // Capability cache shape: dict<model_id, frozenset|null>.
            // - Ollama: server returns models[i].capabilities (list of strings)
            // - OpenRouter: server returns models[i].supported_parameters (list of strings)
            //               The /models endpoint aliases supported_parameters → capabilities
            //               for backwards compat, so this single read works for both.
            // - Other providers: field absent → cache entry stays unset → no chip.
            // Empty list = "fetched but no caps known" → still no chip (fail-open).
            var caps = models[i].capabilities;
            if (Array.isArray(caps) && caps.length > 0) {
              modelCapsBy[modelId] = caps;
            } else if (Array.isArray(caps) && caps.length === 0) {
              modelCapsBy[modelId] = null;  // explicit "fetched, no caps" → no chip
            }
```

Note: the api endpoint already aliases `supported_parameters → capabilities` per Task 7 Step 7, so the front-end change is just the empty-list handling.

- [ ] **Step 2: Add datalist swap in the model-picker render**

Find where the model `<select>` is rendered in `general-tab.js:70-72`:

```javascript
    html += '<div class="field-row"><label for="studio-model">Model</label>';
    html += '<select id="studio-model" class="field-input field-select" data-field="llm_model">';
```

Replace with a function that emits either `<select>` or `<input list> + <datalist>` depending on the *current* selected provider type. The provider-type lookup happens at render time using the form's `#studio-provider` value.

```javascript
    // Provider-type-aware model picker. OpenRouter has ~370 models, so we
    // swap to a <datalist>-backed <input> for native filter UX. Other
    // provider types keep the <select> for click-pick simplicity.
    html += '<div class="field-row"><label for="studio-model">Model</label>';
    var providerType = (function () {
      if (!cfg || !cfg.provider_config_id) return '';
      var prov = (state.providers || []).find(function (p) { return p.id === cfg.provider_config_id; });
      return prov ? prov.type : '';
    })();
    if (providerType === 'openrouter') {
      html += '<input type="text" id="studio-model" class="field-input"'
        + '       list="studio-model-list" data-field="llm_model"'
        + '       value="' + escapeAttr(cfg.llm_model || '') + '"'
        + '       placeholder="Type to filter (e.g. anthropic/claude)" />';
      html += '<datalist id="studio-model-list"></datalist>';
    } else {
      html += '<select id="studio-model" class="field-input field-select" data-field="llm_model">';
      html += '</select>';
    }
```

(Match the existing template-string style; the snippet above uses string concat to match the file's pattern. `state.providers` is the front-end's current providers list — search the file for the actual variable name and adjust.)

- [ ] **Step 3: Update `fetchModelsForProvider` in `studio.js` to populate the datalist when present**

In `studio.js:773-790` find the loop that builds `<option>` entries for the `<select>`:

```javascript
        .then(function (models) {
          modelCapsBy = {};
          var html = '<option value="" disabled>Choose a model</option>';
          for (var i = 0; i < models.length; i++) {
            var modelId = models[i].id || models[i].name;
            var sel = modelId === currentVal ? ' selected' : '';
            html += '<option value="' + escapeAttr(modelId) + '"' + sel + '>' + escapeHtml(modelId) + '</option>';
            if (Object.prototype.hasOwnProperty.call(models[i], 'capabilities')) {
              modelCapsBy[modelId] = models[i].capabilities;
            }
          }
          selectEl.innerHTML = html;
```

Replace with logic that branches on the element type:

```javascript
        .then(function (models) {
          modelCapsBy = {};
          var isInput = selectEl.tagName === 'INPUT';
          var datalistEl = isInput ? document.getElementById('studio-model-list') : null;
          var optsHtml = '';
          if (!isInput) {
            optsHtml = '<option value="" disabled>Choose a model</option>';
          }
          for (var i = 0; i < models.length; i++) {
            var modelId = models[i].id || models[i].name;
            if (isInput) {
              optsHtml += '<option value="' + escapeAttr(modelId) + '">' + escapeHtml(modelId) + '</option>';
            } else {
              var sel = modelId === currentVal ? ' selected' : '';
              optsHtml += '<option value="' + escapeAttr(modelId) + '"' + sel + '>' + escapeHtml(modelId) + '</option>';
            }
            // Capability cache (see Task 10 Step 1)
            var caps = models[i].capabilities;
            if (Array.isArray(caps) && caps.length > 0) {
              modelCapsBy[modelId] = caps;
            } else if (Array.isArray(caps) && caps.length === 0) {
              modelCapsBy[modelId] = null;
            }
          }
          if (isInput) {
            datalistEl.innerHTML = optsHtml;
            // For <input>, value was set in the template via cfg.llm_model;
            // ensure dataset.pendingValue is honored too
            if (currentVal) selectEl.value = currentVal;
          } else {
            selectEl.innerHTML = optsHtml;
            if (currentVal && !selectEl.querySelector('option[value="' + CSS.escape(currentVal) + '"]')) {
              var customOpt = '<option value="' + escapeAttr(currentVal) + '" selected>' + escapeHtml(currentVal) + ' (custom)</option>';
              selectEl.insertAdjacentHTML('beforeend', customOpt);
            }
          }
```

Keep the rest of the `.then` block as-is.

- [ ] **Step 4: Lifecycle — replace node on type-change rather than toggle visibility**

When the provider selector changes, the model-picker may need to swap between `<select>` and `<input>`. The cleanest path is a re-render of the parent `.field-row`. If the existing code re-renders the entire form on provider-change (search for `renderEditor` / `mountForm` in `general-tab.js`), no extra work needed — the renderer already produces the right element. If it does NOT re-render, add a `swapModelPicker(newType)` helper that:

1. Finds the existing `#studio-model` element.
2. Creates a fresh element of the appropriate tag type (per Step 2's branch).
3. `oldNode.replaceWith(newNode)` — guarantees only one element with that id and frees stale listeners.
4. Re-attaches the change listener (`renderModelCapabilities`).

Wire it into the provider-select change handler if not already.

- [ ] **Step 5: Verify the `renderCapabilityChips` helper handles `frozenset({})` correctly**

The chip renderer is in `the_one/interfaces/web/static/js/areas/admin/...` (search for `renderCapabilityChips`). It is called as `renderer(caps)` where `caps` may now be `null` or a list. The current code in `studio.js:744-749` already short-circuits on `caps === undefined || caps === null` — that's the fail-open path for OpenRouter's empty-list case (Step 1 normalizes empty to null).

- [ ] **Step 6: Manual smoke test**

Spin up the worktree's local server (no Docker; the venv has uvicorn):

```bash
.venv/bin/python3 -m the_one.interfaces.web.server &
SERVER_PID=$!
sleep 2
curl -s http://localhost:8484/api/providers/types | head
kill $SERVER_PID 2>/dev/null
```

Expected: `openrouter` in the types response.

Full visual check is deferred to the browser test in Task 11.

- [ ] **Step 7: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/studio.js \
        the_one/interfaces/web/static/js/areas/studio/general-tab.js
git commit -m "feat(studio): datalist combobox for openrouter model picker

- Provider-type-aware render: <select> for ollama/openai/etc., <input> +
  <datalist> for openrouter (~370 models, native filter UX)
- Capability cache normalized: empty list → null (fail-open, no chip),
  non-empty list → cache entry, absent field → unset (no chip)
- Lifecycle: replaceWith() swaps node identity so stale listeners are GC'd"
```

---

## Task 11: Browser tests (admin flow + studio picker)

**Files:**
- Create: `tests/browser/test_flow_admin_openrouter.py`
- Create: `tests/browser/test_flow_studio_openrouter_picker.py`

**Why:** Pin the user-facing flows; catch regressions where a CSS / event-listener change breaks the form.

- [ ] **Step 1: Look at existing browser-test patterns**

```bash
ls tests/browser/
.venv/bin/python3 -c "import inspect, importlib; m = importlib.import_module('tests.browser.conftest'); print([x for x in dir(m) if not x.startswith('_')])"
head -60 tests/browser/conftest.py
```

The conftest fixture spawns a uvicorn subprocess on a random port with an isolated `tmp_path` data_dir; teardown via SIGTERM. Each test gets a fresh app + browser context.

- [ ] **Step 2: Write the admin flow test**

Create `tests/browser/test_flow_admin_openrouter.py`:

```python
"""Browser flow: admin → new openrouter provider → save → edit → round-trip."""
from __future__ import annotations

import pytest


@pytest.mark.browser
async def test_admin_openrouter_create_and_round_trip(page, app_url):
    """Open Admin → Providers → New, pick OpenRouter, fill fields, save,
    re-open in edit mode, assert all fields round-tripped."""
    await page.goto(f"{app_url}/")
    # Navigate to Admin → Providers
    await page.click("text=Admin")
    await page.click("text=Providers")
    await page.click("text=New Provider")

    # Pick OpenRouter type
    await page.select_option("#prov-type", value="openrouter")

    # Verify base_url pre-fills
    base_url_input = page.locator("[data-field='base_url']")
    assert "openrouter.ai/api/v1" in (await base_url_input.input_value())

    # Fill fields
    await page.fill("[data-field='name']", "OR Test")
    await page.fill("[data-field='api_key']", "sk-or-test")
    await page.fill("[data-field='config.referer']", "https://myapp.example")
    await page.fill("[data-field='config.title']", "MyApp")

    # Save
    await page.click("text=Save")
    await page.wait_for_selector("text=OR Test", timeout=5000)

    # Click into the newly-created provider to edit
    await page.click("text=OR Test")

    # Assert fields round-tripped
    assert await page.input_value("[data-field='name']") == "OR Test"
    assert await page.input_value("[data-field='base_url']") == "https://openrouter.ai/api/v1"
    assert await page.input_value("[data-field='config.referer']") == "https://myapp.example"
    assert await page.input_value("[data-field='config.title']") == "MyApp"
    # api_key should show __MASKED__ (existing pattern)
    masked = await page.input_value("[data-field='api_key']")
    assert masked == "__MASKED__" or masked == ""


@pytest.mark.browser
async def test_admin_referer_with_crlf_blocked_client_side(page, app_url):
    """Pasting a CRLF into App URL must trigger the client-side validation
    flash before the save fires."""
    await page.goto(f"{app_url}/")
    await page.click("text=Admin")
    await page.click("text=Providers")
    await page.click("text=New Provider")
    await page.select_option("#prov-type", value="openrouter")
    await page.fill("[data-field='name']", "Bad")
    await page.fill("[data-field='api_key']", "k")
    # JS .fill() doesn't honor \r\n — use evaluate to set the raw value
    await page.evaluate(
        "document.querySelector('[data-field=\"config.referer\"]').value = "
        "'https://x.com\\r\\nX-Injected: 1'"
    )
    await page.click("text=Save")
    # Either the client-side flash fires OR the server returns 422 — both acceptable
    flash = await page.locator(".flash-error, .flash").first.text_content(timeout=3000)
    assert "control character" in flash.lower() or "invalid" in flash.lower()
```

- [ ] **Step 3: Write the studio picker test**

Create `tests/browser/test_flow_studio_openrouter_picker.py`:

```python
"""Browser flow: studio model picker for openrouter (datalist combobox)."""
from __future__ import annotations

import json

import pytest


@pytest.mark.browser
async def test_studio_openrouter_picker_renders_datalist(page, app_url, mock_openrouter_models):
    """With an openrouter provider stored, opening the agent editor must
    render an <input id=studio-model> + <datalist> combo (not a <select>),
    and the datalist must populate with mocked model entries."""
    # mock_openrouter_models is a fixture (defined below or in conftest) that
    # pre-populates a stored openrouter provider AND stubs /api/providers/{id}/models
    # to return a synthetic 3-model payload including one with tools and one
    # without.
    await page.goto(f"{app_url}/")
    await page.click("text=Studio")
    await page.click("text=New Agent")
    await page.select_option("#studio-provider", value=mock_openrouter_models["provider_id"])

    # Wait for model list to load
    await page.wait_for_selector("#studio-model-list option", timeout=5000)

    # Element must be <input>, NOT <select>
    tag = await page.evaluate("document.getElementById('studio-model').tagName")
    assert tag == "INPUT"

    # Datalist must contain the mocked entries
    options = await page.eval_on_selector_all(
        "#studio-model-list option", "els => els.map(e => e.value)"
    )
    assert "anthropic/claude-3.5-sonnet" in options
    assert "no-tools-model" in options


@pytest.mark.browser
async def test_studio_openrouter_no_tools_chip(page, app_url, mock_openrouter_models):
    """Selecting a model without 'tools' in supported_parameters must
    surface the red [no tools] chip."""
    await page.goto(f"{app_url}/")
    await page.click("text=Studio")
    await page.click("text=New Agent")
    await page.select_option("#studio-provider", value=mock_openrouter_models["provider_id"])
    await page.wait_for_selector("#studio-model-list option", timeout=5000)

    # Type the no-tools model and dispatch input event
    await page.fill("#studio-model", "no-tools-model")
    await page.dispatch_event("#studio-model", "change")

    chip = page.locator(".model-capabilities .capability-chip-no-tools")
    await chip.wait_for(timeout=3000)
    assert await chip.count() == 1


@pytest.mark.browser
async def test_studio_openrouter_empty_caps_shows_no_chip(page, app_url, mock_openrouter_models):
    """A model with empty supported_parameters must NOT render a chip
    (fail-open semantics)."""
    await page.goto(f"{app_url}/")
    await page.click("text=Studio")
    await page.click("text=New Agent")
    await page.select_option("#studio-provider", value=mock_openrouter_models["provider_id"])
    await page.wait_for_selector("#studio-model-list option", timeout=5000)

    await page.fill("#studio-model", "empty-caps-model")
    await page.dispatch_event("#studio-model", "change")

    # No chip element should be rendered
    chip_count = await page.locator(".capability-chip-no-tools").count()
    assert chip_count == 0


@pytest.mark.browser
async def test_studio_picker_lifecycle_on_type_switch(page, app_url, mock_two_providers):
    """Switching provider ollama → openrouter → ollama → openrouter must
    leave exactly one #studio-model element each step."""
    await page.goto(f"{app_url}/")
    await page.click("text=Studio")
    await page.click("text=New Agent")
    sequence = [
        mock_two_providers["ollama_id"],
        mock_two_providers["openrouter_id"],
        mock_two_providers["ollama_id"],
        mock_two_providers["openrouter_id"],
    ]
    for prov_id in sequence:
        await page.select_option("#studio-provider", value=prov_id)
        # Allow render
        await page.wait_for_timeout(200)
        count = await page.locator("#studio-model").count()
        assert count == 1, f"Found {count} #studio-model elements after switching to {prov_id}"
```

The `mock_openrouter_models` and `mock_two_providers` fixtures need to be added to `tests/browser/conftest.py`. They prepopulate the test app's DB with the right rows and stub the upstream `/models` calls (use the existing `httpx.MockTransport` injection point or pre-seed the HTTP cache by calling `openrouter_api._models_cache[...]` directly).

- [ ] **Step 4: Add fixtures to `tests/browser/conftest.py`**

(Read existing fixtures first to match the established patterns.)

```python
@pytest.fixture
async def mock_openrouter_models(app_url, http_client, monkeypatch):
    """Create a stored openrouter provider AND seed the openrouter_api cache
    with synthetic models (one with tools, one without, one with empty caps)."""
    from the_one.llm import openrouter_api

    # Seed the helper cache so list_models doesn't go upstream
    openrouter_api._models_cache.clear()
    fake_models = [
        {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet",
         "supported_parameters": ["tools", "reasoning"], "context_length": 200000,
         "description": ""},
        {"id": "no-tools-model", "name": "Tools-less",
         "supported_parameters": ["max_tokens"], "context_length": 8192,
         "description": ""},
        {"id": "empty-caps-model", "name": "Empty Caps",
         "supported_parameters": [], "context_length": 4096, "description": ""},
    ]
    # Use the same cache key shape as the helper produces
    cache_key = openrouter_api._cache_key("https://openrouter.ai/api/v1", "test-key")
    import time
    openrouter_api._models_cache[cache_key] = (fake_models, time.time())

    # Create a provider via the REST API
    resp = await http_client.post("/api/providers", json={
        "name": "OR Mock",
        "type": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "test-key",
    })
    assert resp.status_code in (200, 201), resp.text
    provider_id = resp.json()["id"]
    yield {"provider_id": provider_id, "models": fake_models}
    openrouter_api._models_cache.clear()


@pytest.fixture
async def mock_two_providers(http_client, mock_openrouter_models):
    """openrouter (from mock_openrouter_models) plus a second ollama provider
    so the lifecycle test can switch between them."""
    resp = await http_client.post("/api/providers", json={
        "name": "Local Ollama",
        "type": "ollama",
        "base_url": "http://localhost:11434/v1",
        "api_key": "",
    })
    assert resp.status_code in (200, 201), resp.text
    yield {
        "openrouter_id": mock_openrouter_models["provider_id"],
        "ollama_id": resp.json()["id"],
    }
```

- [ ] **Step 5: Run the browser tests**

```bash
.venv/bin/playwright install chromium 2>&1 | tail -3
.venv/bin/pytest -m browser tests/browser/test_flow_admin_openrouter.py tests/browser/test_flow_studio_openrouter_picker.py -v --tb=short
```

Expected: PASS. If `playwright install` fails on macOS due to missing system deps, run `make test-browser` from the main repo root after ensuring the worktree is mounted (or skip the browser tests for this iteration and revisit on Linux/CI — note in the commit message).

- [ ] **Step 6: Commit**

```bash
git add tests/browser/test_flow_admin_openrouter.py \
        tests/browser/test_flow_studio_openrouter_picker.py \
        tests/browser/conftest.py
git commit -m "test(browser): admin openrouter flow + studio picker lifecycle

- admin: create + edit round-trip; CRLF in App URL blocked client-side
- studio: datalist renders for openrouter; [no tools] chip shows for
  models lacking 'tools'; empty supported_parameters → no chip;
  type-switch ping-pong leaves exactly one #studio-model element"
```

---

## Final verification

- [ ] **Run full unit test suite**

```bash
.venv/bin/pytest tests/ -m 'not browser and not live and not pixel' --tb=line -q 2>&1 | tail -10
```

Expected: previous baseline + ~30 new tests, 1 pre-existing macOS-specific failure (`test_env_allowlist_invariant`), zero new failures.

- [ ] **Run lint**

```bash
.venv/bin/ruff check the_one/ tests/
.venv/bin/ruff format --check the_one/ tests/
```

Expected: clean.

- [ ] **Update CLAUDE.md if needed**

Skim `CLAUDE.md` and add a one-line note in the LLM-layer section if the openrouter type's existence isn't already implied by the existing prose. Do NOT add a marketing description; one line under "Persistence" or "LLM layer" suffices:

```
LLMProviderRepository supports five built-in types: ollama, openai-compatible,
openai, anthropic, mock, plus openrouter (added 2026-05-07).
```

- [ ] **Final commit (if CLAUDE.md changed)**

```bash
git add CLAUDE.md
git commit -m "docs: note openrouter provider type in CLAUDE.md"
```

---

## Self-review checklist

**Spec coverage (every section in the design doc maps to a task):**
- ✅ Goals (no-leak, header-injection, datalist UX) — Task 5 (no-leak), Task 7 (header validation), Task 10 (datalist)
- ✅ Decision 1 (first-class type) — all tasks
- ✅ Decision 2 (datalist for openrouter only) — Task 10
- ✅ Decision 3 (ranking headers via config dict) — Task 5, Task 9
- ✅ Decision 4 (openai-compatible Authorization fix) — Task 3
- ✅ Decision 5 (empty-string opt-out) — Task 5
- ✅ Decision 6 (sanitize at API boundary) — Task 7
- ✅ Decision 7 (helpers raise; capability lookup fails open) — Task 4
- ✅ Decision 8 (/auth/key for real key probing) — Task 4, Task 7
- ✅ OpenRouterProvider class — Task 5
- ✅ openrouter_api helpers — Task 4
- ✅ openai_provider base_url — Task 2
- ✅ ollama_provider Authorization + headers param — Task 3
- ✅ registry + factory — Task 6
- ✅ db/models.py + schema v10 — Task 1
- ✅ /types, /models, /test, POST/PUT validation — Task 7
- ✅ Frontend admin (TYPE_DEFAULTS, badge, optional fields, type-change) — Task 9
- ✅ Frontend Studio (datalist, capability cache, lifecycle) — Task 10
- ✅ Test plan: provider tests (Task 5), api tests (Task 4), provider_api extensions (Task 7), llm_registry extensions (Task 6), db_migrations (Task 1), ollama_provider_auth (Task 3), factory integration (Task 8), browser flows (Task 11)
- ❌ Tool-call regression captured-fixture test (`tests/test_openrouter_tool_call_shapes.py`) — NOT in this plan; deferred. Rationale: requires real captured SSE transcripts from production OpenRouter responses across upstream providers (OpenAI/Anthropic/Llama). The implementation is parser-validation only — no functional behavior depends on it. Capturing real fixtures is best done after operator-driven validation post-merge. Listed in design doc as "captured from real OpenRouter responses" so synthesizing in the plan would be an empty exercise. Mark as a follow-up task after first OpenRouter live use.

**Placeholder scan:** none.

**Type consistency:** confirmed — `_models_cache` keyed on `tuple[str, str]` everywhere; `caps` is `frozenset[str] | None`; `get_model_capabilities` signature consistent across helper, test, and frontend dispatch.
