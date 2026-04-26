# Leg: 04-seeders

**Status**: completed
**Flight**: [Browser Test Foundation](../flight.md)

## Objective

Add API-based seeder helpers and two layered pytest fixtures (`app_with_provider`, `app_with_agent`) that build on `app_clean` from leg 03. Each layered fixture spawns a fresh app subprocess, POSTs a mock provider (and an agent for the second variant) via the real HTTP API, and yields a small dataclass containing the `base_url` plus the relevant entity IDs/names. Validate with sanity tests that confirm the seeded state is queryable via the API.

## Context

- This leg completes the "layered fixture stack" design decision from `flight.md` (see "Layered fixture stack"). After this leg, flow tests in legs 05-07 simply pick the appropriate fixture (`app_clean`, `app_with_provider`, `app_with_agent`) and focus on UI behavior, not setup.
- **Leg 03 outcome**: `app_clean` fixture exists in `tests/browser/conftest.py`; spawns a subprocess with `THE_ONE_DEV_MODE=true`. Browser/page fixtures are module-scoped (changed from session-scoped during implementation to keep the leg-01 standalone smoke test green). Use these as-is.
- **Leg 02 outcome**: `mock` provider type accepts `config` dict via the API. Seeders POST `type="mock"` payloads; backend validates and stores.
- **Leg 02 outcome**: `POST /api/agents` accepts an `AgentConfig` JSON body (verified at `api.py:110-118`). Required fields are minimal — `name` is the only mandatory field; `provider_config_id`, `llm_model`, `system_prompt`, etc., are optional but needed for a usable agent.
- Seeders use real HTTP endpoints (not direct DB writes). This exercises the actual code path and is robust to schema changes (e.g., the v6 migration added in leg 02 didn't require seeder updates because the API layer abstracts it).

## Inputs

- Branch `flight/01-browser-test-foundation`, legs 01-03 landed (uncommitted)
- `tests/browser/conftest.py` has `app_clean`, `browser`, `page` fixtures (from leg 03)
- `tests/browser/test_app_fixture.py` has 2 passing tests (from leg 03)
- API surface for seeding (verified in code):
  - `POST /api/providers` → returns `{"id": "...", ...}`. For `type="mock"`, requires `THE_ONE_DEV_MODE=true` (the fixture sets this).
  - `POST /api/agents` → returns full `AgentConfig` model_dump. Requires `name` field; `provider_config_id` and `llm_model` for a usable agent.
- Test baseline: 350 passed, 11 deselected (post-leg-03)

## Outputs

- `tests/browser/seeders.py` (new) — seeder functions:
  - `SeededApp` dataclass (fields: `base_url: str`, `provider_id: str`, `agent_name: str | None`)
  - `seed_mock_provider(base_url: str, name: str = "mock", config: dict | None = None) -> str` — POSTs to `/api/providers`, returns provider_id
  - `seed_mock_agent(base_url: str, provider_id: str, name: str = "test-agent", model: str = "mock-default", system_prompt: str = "You are a test agent.") -> str` — POSTs to `/api/agents`, returns agent_name
- `tests/browser/conftest.py` (extended) — two new fixtures:
  - `app_with_provider` (function-scoped) — yields `SeededApp` with `base_url` + `provider_id`, `agent_name=None`
  - `app_with_agent` (function-scoped) — yields `SeededApp` with `base_url` + `provider_id` + `agent_name`
- `tests/browser/test_seeders.py` (new) — 2 sanity tests that exercise the layered fixtures

## Acceptance Criteria

- [x] `tests/browser/seeders.py` exists with `SeededApp` dataclass and 2 seeder functions
- [x] `seed_mock_provider`:
  - POSTs `{"name": "<name>", "type": "mock", "base_url": "", "config": <config or {}>}` to `/api/providers`
  - Asserts `r.status_code == 201`
  - Returns the provider's `id` from the response
- [x] `seed_mock_agent`:
  - POSTs `{"name": "<name>", "provider_config_id": "<provider_id>", "llm_model": "<model>", "system_prompt": "<prompt>"}` to `/api/agents`
  - Asserts `r.status_code == 201`
  - Returns the agent's `name` (echoed from response)
- [x] `tests/browser/conftest.py` exports `app_with_provider` and `app_with_agent` fixtures (function-scoped)
- [x] `app_with_provider` fixture:
  - Depends on `app_clean`
  - Calls `seed_mock_provider(base_url)` (default name)
  - Yields a `SeededApp(base_url=..., provider_id=..., agent_name=None)`
- [x] `app_with_agent` fixture:
  - Depends on `app_clean`
  - Calls `seed_mock_provider(base_url)` then `seed_mock_agent(base_url, provider_id)`
  - Yields a `SeededApp(base_url=..., provider_id=..., agent_name=...)`
- [x] `tests/browser/test_seeders.py::test_app_with_provider_has_one_mock_provider` passes:
  - Uses `app_with_provider` fixture
  - GETs `/api/providers`, asserts response is a list of length 1, type is `"mock"`, id matches `SeededApp.provider_id`
- [x] `tests/browser/test_seeders.py::test_app_with_agent_has_one_provider_and_one_agent` passes:
  - Uses `app_with_agent` fixture
  - GETs `/api/providers` (length 1, mock), `/api/agents` (length 1, name matches `SeededApp.agent_name`, `provider_config_id` matches `SeededApp.provider_id`)
- [x] `pytest -m browser tests/browser/ -v` shows 5 passed (smoke + 2 app-fixture + 2 seeder)
- [x] Default `pytest tests/`: 350 passed, 13 deselected (was 11; +2 from new seeder tests)
- [x] `ruff check tests/browser/` and `ruff format --check tests/browser/` clean

## Verification Steps

1. **Fixtures + tests collect**: `pytest tests/browser/ --collect-only -q -m browser` — should show 5 tests
2. **Seeder tests pass**: `pytest -m browser tests/browser/test_seeders.py -v --timeout=60`
3. **All browser tests pass**: `pytest -m browser tests/browser/ -v --timeout=60`
4. **No regression**: `pytest tests/ --tb=short -q --timeout=60` — 350 passed, 13 deselected
5. **Lint/format**: `ruff check tests/browser/ && ruff format --check tests/browser/`

## Implementation Guidance

### 1. Create `tests/browser/seeders.py`

```python
"""API-based seeders for browser test fixtures.

These helpers POST to the real HTTP endpoints exposed by an `app_clean`
subprocess. Using HTTP (rather than direct DB writes) exercises the real
code path — including the leg-02 schema migration v6, the dev-mode gating
on the mock provider, and the API request validation.

The fixtures that consume these helpers (`app_with_provider`,
`app_with_agent`) are defined in conftest.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class SeededApp:
    """Bundles a running app's base_url with the seeded entity references.

    `agent_name` is None for `app_with_provider` (no agent was seeded);
    populated for `app_with_agent`.
    """

    base_url: str
    provider_id: str
    agent_name: str | None = None


def seed_mock_provider(
    base_url: str,
    name: str = "mock",
    config: dict | None = None,
) -> str:
    """POST a mock provider via /api/providers and return its id.

    Requires the target app to have THE_ONE_DEV_MODE=true (else the API
    rejects mock-typed creates with HTTP 400 — see leg 02 gating).

    `base_url=""` is sent because `LLMProviderConfig.base_url: str` has
    no default and Pydantic 422s if the field is omitted; the mock
    provider never connects anywhere, so the empty string is meaningless
    but valid.
    """
    payload = {
        "name": name,
        "type": "mock",
        "base_url": "",
        "config": config or {},
    }
    r = httpx.post(f"{base_url}/api/providers", json=payload, timeout=5.0)
    assert r.status_code == 201, (
        f"seed_mock_provider failed: {r.status_code} {r.text}"
    )
    return r.json()["id"]


def seed_mock_agent(
    base_url: str,
    provider_id: str,
    name: str = "test-agent",
    model: str = "mock-default",
    system_prompt: str = "You are a test agent.",
) -> str:
    """POST an agent via /api/agents and return its name.

    `provider_id` should be the id from a prior seed_mock_provider call.
    Default `model` matches the mock provider's default model.

    Optional AgentConfig fields (description, enabled_tools, kb_ids,
    mcp_source_ids, max_iterations, direct_actions) are omitted; their
    defaults from `agent/config.py` apply. `extra: "ignore"` on AgentConfig
    means the API silently drops any unknown fields.
    """
    payload = {
        "name": name,
        "provider_config_id": provider_id,
        "llm_model": model,
        "system_prompt": system_prompt,
    }
    r = httpx.post(f"{base_url}/api/agents", json=payload, timeout=5.0)
    assert r.status_code == 201, (
        f"seed_mock_agent failed: {r.status_code} {r.text}"
    )
    return r.json()["name"]
```

### 2. Extend `tests/browser/conftest.py`

Add the two new fixtures at the bottom of the file (after the existing `page` fixture). Add the `SeededApp` import at the top.

```python
# At the top of conftest.py, add (consistent with the existing bare-conftest
# import pattern enabled by leg 01's `pythonpath = ["tests"]` config):
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider

# At the bottom of conftest.py, add:


# ── Layered fixtures (seeded variants of app_clean) ───────────────────────


@pytest.fixture
def app_with_provider(app_clean: str) -> Iterator[SeededApp]:
    """An app subprocess pre-seeded with a single mock provider."""
    provider_id = seed_mock_provider(app_clean)
    yield SeededApp(base_url=app_clean, provider_id=provider_id)


@pytest.fixture
def app_with_agent(app_with_provider: SeededApp) -> Iterator[SeededApp]:
    """An app subprocess pre-seeded with a mock provider AND an agent.

    Composes on `app_with_provider` — pytest's fixture caching ensures
    `app_clean` is spawned once per test, then seeded once, then this
    fixture layers an agent on top. Cleanup is implicit via `app_clean`'s
    SIGTERM teardown (drops the entire subprocess + DB).
    """
    agent_name = seed_mock_agent(app_with_provider.base_url, app_with_provider.provider_id)
    yield SeededApp(
        base_url=app_with_provider.base_url,
        provider_id=app_with_provider.provider_id,
        agent_name=agent_name,
    )
```

> Import path: `from browser.seeders import ...` matches the bare-`conftest` pattern established by leg 01. `pythonpath = ["tests"]` puts `tests/` on `sys.path`, so `browser.seeders` resolves to `tests/browser/seeders.py`. Avoids creating a parallel import root via `tests.browser.*`.

> Compositional pattern: `app_with_agent` depends on `app_with_provider` (not directly on `app_clean`). pytest resolves both function-scoped fixtures once per test, so the subprocess is spawned once, the provider is seeded once, then the agent is layered on top. Cleaner than re-seeding.

### 3. Create `tests/browser/test_seeders.py`

```python
"""Sanity tests for the seeded fixture variants from conftest.py."""

from __future__ import annotations

import httpx
import pytest

from browser.seeders import SeededApp


@pytest.mark.browser
def test_app_with_provider_has_one_mock_provider(app_with_provider: SeededApp) -> None:
    """The app_with_provider fixture seeds exactly one mock provider via the API."""
    r = httpx.get(f"{app_with_provider.base_url}/api/providers", timeout=5.0)
    assert r.status_code == 200
    providers = r.json()
    assert len(providers) == 1
    p = providers[0]
    assert p["type"] == "mock"
    assert p["id"] == app_with_provider.provider_id
    assert app_with_provider.agent_name is None


@pytest.mark.browser
def test_app_with_agent_has_one_provider_and_one_agent(
    app_with_agent: SeededApp,
) -> None:
    """The app_with_agent fixture seeds a mock provider + an agent referencing it."""
    providers = httpx.get(
        f"{app_with_agent.base_url}/api/providers", timeout=5.0
    ).json()
    assert len(providers) == 1
    assert providers[0]["type"] == "mock"
    assert providers[0]["id"] == app_with_agent.provider_id

    agents = httpx.get(f"{app_with_agent.base_url}/api/agents", timeout=5.0).json()
    assert len(agents) == 1
    a = agents[0]
    assert a["name"] == app_with_agent.agent_name
    assert a["provider_config_id"] == app_with_agent.provider_id
    assert a["llm_model"] == "mock-default"
```

### 4. Run verification

```bash
pytest tests/browser/ --collect-only -q -m browser
pytest -m browser tests/browser/test_seeders.py -v --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
pytest tests/ --tb=short -q --timeout=60
ruff check tests/browser/
ruff format --check tests/browser/
```

## Edge Cases

- **`POST /api/agents` returns 201 with full model_dump**: Verified at `api.py:110-118`. Response body has `name`, so `r.json()["name"]` works. If a future change wraps this in a `{"agent": {...}}` envelope, the seeder will need to update.

- **`POST /api/providers` for mock type requires DEV_MODE**: The `app_clean` fixture sets `THE_ONE_DEV_MODE=true`, so this is satisfied. If a future leg adds a non-dev-mode fixture variant, mock seeding would fail there with HTTP 400 — by design.

- **Agent without `system_prompt`**: The default in `seed_mock_agent` is `"You are a test agent."`. If a flow test wants to verify the system prompt is shown to the LLM, it can override the default. Per `agent/config.py:102-104`, an empty `system_prompt` falls back to the lengthy `DEFAULT_SYSTEM_PROMPT` — passing a short test prompt is more focused.

- **`AgentConfig.model_validate` strictness**: `extra: "ignore"` in AgentConfig (line 69 of `agent/config.py`) means extra fields in the POST body are silently dropped. Seeders only send recognized fields; no risk of schema drift.

- **Fixture composition**: `app_with_agent` depends on `app_with_provider` (which depends on `app_clean`). pytest's per-test fixture caching ensures `app_clean` is spawned once per test and `app_with_provider`'s seeding runs once; `app_with_agent` just adds the agent on top. Cleaner than re-seeding and matches standard pytest convention.

- **Provider config encryption**: Mock providers have `api_key=None`, so the encryptor never sees them. No new `~/.the-one/encryption.key` is created in the test data_dir for these fixtures (verified in leg 02's API path).

- **Test name collisions**: `test_seeders.py` uses unique test names that don't collide with `test_app_fixture.py` (different module). pytest discovers them by full module path. No issue.

- **HTTPX timeout**: 5s timeout on seeder calls is generous (mock provider POSTs are sub-100ms). If a seeder ever hangs, the test fails fast with TimeoutError rather than hanging the full pytest timeout.

## State-Machine Reachability Audit

This leg introduces:
- Test-time state: seeded entities in subprocess DBs (provider rows, agent rows). All scoped to per-test `tmp_path` data_dirs from `app_clean`.

Lower layers verified:
- DB CHECK constraint on `provider.type` already includes `"mock"` (leg 02 v6 migration). ✓
- `LLMProviderRepository.create` round-trips `config` dict as JSON. ✓
- `AgentConfig.model_validate` accepts the seeder's payload shape. ✓
- API gating: `dev_mode=true` is set by `app_clean` env. ✓

No existing tests pin behavior this leg breaks. ✓ Pass.

## Cache Freshness Contract

**No new caches.** Seeders are stateless functions; fixtures hold transient `SeededApp` dataclasses for the test duration only. No new in-memory caches in production code; subprocess DBs are torn down by `app_clean`. ✓ Pass.

## Files Affected

- `tests/browser/seeders.py` — new (~70 LOC, 2 functions + 1 dataclass)
- `tests/browser/conftest.py` — extended with 2 new fixtures (~30 LOC added)
- `tests/browser/test_seeders.py` — new (~40 LOC, 2 tests)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing: `pytest tests/` shows 350 passed, 13 deselected; `pytest -m browser tests/browser/` shows 5 passed
- [x] `ruff check tests/browser/` and `ruff format --check tests/browser/` clean
- [x] Update flight-log.md with leg progress entry (status, what was done, any anomalies)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off this leg in flight.md (happens at flight-level commit time)
- [x] Do NOT commit (flight-level review and commit happen after the last autonomous leg)
- [x] Signal `[HANDOFF:review-needed]`
