# Flight Log: Browser Test Foundation

**Flight**: [Browser Test Foundation](flight.md)

## Summary

Flight in progress. Started 2026-04-25.

---

## Leg Progress

### Leg 01 — Scaffold Playwright (2026-04-25)

**Status**: landed

**What was done**: Added `playwright>=1.48` to `[project.optional-dependencies].dev`, registered the `browser` pytest marker, and extended `addopts` to deselect both `live` and `browser` markers by default. Created `tests/browser/conftest.py` (docstring-only, per spec) and `tests/browser/test_smoke.py` containing a single `@pytest.mark.browser` test that uses `sync_playwright` to launch Chromium against a `data:` URL and assert on title + DOM. Verified Playwright 1.58.0 was already installed in the dev env; Chromium v1208 binary was already cached at `~/.cache/ms-playwright/`, so `playwright install chromium` was effectively a no-op.

**Anomalies / deviations**:

1. **Playwright pre-installed**: The dev environment already had `playwright==1.58.0` and the chromium binary cached. Verified via `pip show playwright` and `ls ~/.cache/ms-playwright/`. No install action required.
2. **`from conftest import ...` collision (substantive deviation from spec)**: The existing tests under `tests/` use a bare `from conftest import FakeLLM, StubTool` import pattern (5 files: `test_agent.py`, `test_auto_load.py`, `test_factory.py`, `test_session_lifecycle.py`, `test_tool_registry.py`). With pytest's default `prepend` import-mode and no `tests/__init__.py`, adding `tests/browser/conftest.py` caused pytest to register the nested browser conftest in `sys.modules` as the bare module name `conftest`, shadowing `tests/conftest.py` and breaking the 5 existing test files at collection time (5 ImportErrors).

   **Resolution**: Switched pytest to `--import-mode=importlib` and added `pythonpath = ["tests"]` to `[tool.pytest.ini_options]`. This combination preserves the existing bare-`conftest` import pattern while allowing the nested `tests/browser/conftest.py` to coexist. The acceptance criterion mandating `addopts = "-m 'not live and not browser'"` is now `addopts = "-m 'not live and not browser' --import-mode=importlib"` — same marker filter, plus the import-mode flag. Documented inline in `pyproject.toml` with a comment explaining why. No source files modified.

   Alternative considered and rejected: re-exporting `FakeLLM`/`StubTool` from `tests/browser/conftest.py` (violates the spec's "docstring only" intent and creates a circular-feeling dependency between sibling conftests). The pytest-config-only fix is more surgical and standard.

**Final test counts**:
- Default `pytest tests/`: **336 passed, 9 deselected** (matches spec expectation — was 336/8 pre-leg, +1 deselected from the new browser smoke test)
- `pytest -m browser tests/browser/`: **1 passed** (smoke test, ~0.5s)

### Leg 02 — Mock Provider (2026-04-25)

**Status**: landed

**What was done**: Added a fifth provider type `mock` to the LLM stack, gated by a new `THE_ONE_DEV_MODE` env var. Created `the_one/llm/mock.py` with `MockProvider(LLMProvider)` mirroring the `ollama_provider.py` pattern (constructor takes `model`/`base_url`/`api_key`/`config`/`**kwargs`; `complete()` returns deterministic `Message.assistant(...)` from `config["response"]`). Wired the type through five lower layers: `db/models.py` Literal, `db/schema.py` (new schema migration v6 — see anomaly 1 below), `agent/factory.py` `_PROVIDER_TYPE_MAP` plus `config=` kwarg now passed to all providers, `llm/registry.py` loaders dict, and `config.py` `dev_mode: bool = False`. Added a new `GET /api/providers/types` endpoint (placed BEFORE `/providers/{provider_id}` to satisfy the FastAPI route-ordering invariant), gated `create_provider` and `update_provider` to reject `mock` typed payloads when dev_mode is off, and added `mock` branches to `test_provider` (returns `{"status": "ok", "detail": "Mock provider (dev mode)"}`) and `list_provider_models` (returns `provider.config["models"]` or `["mock-default"]`). Refactored `admin.js` to fetch provider types from the new endpoint on area init via `fetchProviderTypes()`, gated `renderProviderForm()` on the resulting promise (now delegating to `_renderProviderFormImpl`), and added `mock` entries to the always-on `TYPE_DEFAULTS` / `TYPE_BADGE_COLORS` dicts (so existing mock providers still render when dev_mode is later disabled). Added `tests/test_mock_provider.py` (5 tests) and extended `tests/test_provider_api.py` with three new test classes (`TestProviderTypesEndpoint`, `TestMockProviderGating`, `TestMockProviderRoutes`) totaling 9 new tests, including the route-ordering regression.

**Anomalies / deviations**:

1. **Missing schema migration in spec (substantive deviation)**: The leg's State-Machine Reachability Audit listed five lower layers that could foreclose the `mock` state (Pydantic Literal, `_PROVIDER_TYPE_MAP`, registry loaders, API gating, frontend dropdown) but missed the SQLite `CHECK` constraint at `db/schema.py:18,129` that hard-codes the allowed type values. First test run failed with `sqlite3.IntegrityError: CHECK constraint failed: type IN ('ollama', 'openai-compatible', 'openai', 'anthropic')`. Resolved by adding schema migration v6 (`CURRENT_VERSION` 5→6) that rebuilds `llm_providers` with the extended CHECK clause using the same `PRAGMA foreign_keys=OFF` / table-rebuild pattern established in v3 and v5. Two existing schema tests (`test_fresh_db_schema_version_is_5`, `test_idempotent_ensure_schema`) had to be updated to expect version 6. **Action for leg 08 documentation**: the M03 "provider type extension checklist" should be updated to include the SQLite CHECK constraint as the sixth layer, and the corresponding schema migration step.

2. **Pre-existing ruff errors in `tests/test_auto_load.py`**: `ruff check the_one/ tests/` reports 4 errors in this file (3 import/sorting, 1 line-length) that pre-date this leg (verified with `git stash`/`ruff check`/`git stash pop`). Not in scope to fix here. All files modified or created by this leg pass `ruff check` and `ruff format --check` cleanly.

3. **Schema CHECK string broke 100-char line limit**: The single-line `CHECK (type IN ('ollama', ..., 'mock'))` clause inside the v6 migration's executescript SQL was 102 chars. Reformatted as a multi-line `CHECK (\n    type IN (...)\n)` SQL clause to satisfy `E501`.

4. **JS promise wiring**: As predicted in the leg's Implementation Guidance, the cleanest way to gate `renderProviderForm` on the types fetch was to extract the body into `_renderProviderFormImpl` and have the public `renderProviderForm` chain `providerTypesReady.then(...)`. The `fetchProviderTypes()` is also called from `init`, with a fallback in `renderProviderForm` (`var ready = providerTypesReady || fetchProviderTypes()`) for safety if anything ever calls the form before init completes.

5. **`get_provider` factory.py call now passes `config=`**: As called out in the leg's Edge Cases, all three existing provider constructors (`OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`) accept `**kwargs`, so the new `config=provider_config.config` kwarg is silently ignored by them — verified by inspection. The `_fake_get_provider` test double in `tests/test_factory.py:59` also accepts `**kwargs`, so no test breakage.

**Final test counts**:
- `pytest tests/test_mock_provider.py`: **5 passed** (~0.02s)
- `pytest tests/test_provider_api.py -k "types or mock or Gating or MockProviderRoutes"`: **9 passed, 85 deselected**
- Full `pytest tests/`: **350 passed, 9 deselected** (~17s) — exactly matches spec target (336 baseline + 14 new)
- `pytest -m browser tests/browser/`: **1 passed** (smoke test still green, ~0.5s)
- `ruff check` and `ruff format --check`: clean on all leg-touched files (`db/schema.py`, `llm/mock.py`, `llm/registry.py`, `agent/factory.py`, `db/models.py`, `config.py`, `interfaces/web/api.py`, `tests/test_mock_provider.py`, `tests/test_provider_api.py`, `tests/test_schema.py`)

### Leg 04 — Seeders (2026-04-25)

**Status**: landed

**What was done**: Created `tests/browser/seeders.py` with the `SeededApp` dataclass (`base_url`, `provider_id`, `agent_name: str | None = None`) and two HTTP-based seeder helpers — `seed_mock_provider` (POSTs `{"name", "type": "mock", "base_url": "", "config": {}}` to `/api/providers`, asserts 201, returns provider id) and `seed_mock_agent` (POSTs `{"name", "provider_config_id", "llm_model", "system_prompt"}` to `/api/agents`, asserts 201, returns agent name). Both use `httpx.post` with a 5s timeout. Extended `tests/browser/conftest.py` with the `from browser.seeders import ...` import (matching the bare-conftest pattern enabled by leg 01's `pythonpath = ["tests"]`) and two new function-scoped fixtures at the bottom of the file: `app_with_provider` (depends on `app_clean`, yields `SeededApp` with `agent_name=None`) and `app_with_agent` (depends on `app_with_provider`, layers an agent on top, yields fully-populated `SeededApp`). Both use `yield` for symmetry with `app_clean` (so subprocess teardown remains owned by `app_clean`'s SIGTERM finally-block). Created `tests/browser/test_seeders.py` with the two sanity tests that GET `/api/providers` and `/api/agents` and assert on shape, type, id, and cross-references against the `SeededApp` fields.

**Anomalies / deviations**:

1. **Ruff import-grouping (low-severity, auto-fixed)**: First `ruff check tests/browser/` after creating the files reported `I001 [*] Import block is un-sorted or un-formatted` on both `conftest.py` and `test_seeders.py`. The leg's IG showed `from browser.seeders import ...` as a separate (first-party) import block after `from playwright.sync_api import ...`, but ruff has no first-party config in `pyproject.toml` and treats `browser` as third-party — so it wants alphabetical ordering inside the third-party block. Resolved with `ruff check --fix tests/browser/` which moved `from browser.seeders import ...` into the third-party block (above `from playwright.sync_api import ...` alphabetically). Functionally identical; ruff/format both clean afterward. No code semantics change. Could optionally add `[tool.ruff.lint.isort] known-first-party = ["browser"]` in a future cleanup leg if the sibling-package layout grows, but not warranted at this scale.

2. **No other deviations**: All AC met on the first implementation pass. No spec changes, no design deviations.

**Final test counts**:
- `pytest tests/browser/ --collect-only -q -m browser`: **5 tests collected** (smoke + 2 app-fixture + 2 seeder)
- `pytest -m browser tests/browser/test_seeders.py -v --timeout=60`: **2 passed** in **1.39s** (~0.50s setup per test for the second seeder fixture, ~0.51s for the first; teardowns 0.11s and 0.21s)
- `pytest -m browser tests/browser/ -v --timeout=60`: **5 passed** in **3.68s** (durations: setup 0.86s/0.52s/0.51s/0.48s; calls all sub-50ms; teardowns 0.16-0.21s)
- Full `pytest tests/`: **350 passed, 13 deselected** in 17.25s — exactly matches spec target (was 350/11; +2 deselected from the 2 new seeder tests)
- 3-consecutive-run stability check on `test_seeders.py`: **3/3 passed** at 1.54s, 1.43s, 1.54s — no flakiness

**Per-test timing observation (`app_with_agent`)**: Total fixture-setup time from Popen → assertion-ready is ~0.52s. Decomposes roughly as: `app_clean` subprocess startup ~0.40s (uvicorn import + lifespan including `init_db` + factory build on a fresh tmp_path), `seed_mock_provider` POST ~0.05s, `seed_mock_agent` POST ~0.05s, plus pytest fixture-resolution overhead. The compositional pattern (`app_with_agent` depends on `app_with_provider` rather than re-seeding) means the subprocess + provider setup is shared via pytest's per-test fixture caching when both fixtures are pulled in for a test — but in practice each test only requests one of the two top-level fixtures, so this just means `app_with_agent` adds ~0.05s on top of `app_with_provider`. Stability is excellent: 3/3 runs at 1.43-1.54s for the 2-test seeder file (≈0.7-0.8s/test wall-time after pytest overhead), no flakiness across runs.

### Leg 05 — Flow Test: Provider Setup (2026-04-25)

**Status**: landed

**What was done**: Added five `data-testid` attributes to load-bearing UI elements per the leg-design selector strategy — `setup-banner` on the chat first-start banner (`chat.js:217`), and `add-provider-btn`, `provider-card`, `save-provider-btn`, `test-connection-btn` on the corresponding `admin.js` elements. Created `tests/browser/test_flow_provider_setup.py` with a single `@pytest.mark.browser` test (`test_first_start_provider_setup_flow`) that drives a real Chromium session through the empty-DB onboarding flow: confirms the "Getting started" banner in Chat → navigates to Admin → LLM Providers → opens the Add form → fills name="Mock Test" + selects mock type → clicks Create → asserts the form auto-switches to edit mode (admin.js:665-670) → clicks Test Connection and asserts the result contains "Mock" → clicks Cancel → verifies the new provider card appears with the "mock" badge → navigates back to Chat and asserts the banner now reads "No agents". The test uses Playwright's `expect(...)` helpers exclusively (auto-waiting; no manual `time.sleep`).

**Anomalies / deviations**:

1. **JS form-validation bug discovered (small fix applied)**: First test run failed at the auto-switch-to-edit assertion because the Create POST never fired — the `.admin-pf-save` handler in `admin.js` (line ~613-616) unconditionally rejected empty `base_url` with `errorEl.textContent = 'Base URL is required.'`. For `mock` type, `TYPE_DEFAULTS["mock"].showBaseUrl=false` and `defaults.base_url=''`, so the field is hidden but the empty value is then re-validated as if required. Both the API (`POST /api/providers`) and the existing seeders (`tests/browser/seeders.py:50` sends `"base_url": ""`) accept the empty value for mock providers, confirming this was a UI-side regression that prevented mock providers from ever being created via the form. **Fix**: changed the validation to only enforce non-empty when `defaults.showBaseUrl` is true (one-line change in `admin.js`). This matches the established UX intent (the leg explicitly says the test should select mock and submit without filling base_url) and aligns the form with the seeder/API behavior. Did NOT redirect-to-list-after-create or otherwise modify the create-success flow — the test still exercises the actual auto-switch-to-edit UX as designed. Documented under Anomalies/Decisions below.

2. **No other deviations**: All AC met after the JS fix. Test text matched exactly ("Mock" appears in the test-result detail "Mock provider (dev mode)" from leg-02 backend).

**Final test counts**:
- `pytest -m browser tests/browser/test_flow_provider_setup.py -v --timeout=60`: **1 passed** in **1.65s**
- `pytest -m browser tests/browser/ -v --timeout=60`: **6 passed** in **5.42s** (smoke + 2 app-fixture + 2 seeder + 1 flow)
- Full `pytest tests/ --tb=short -q --timeout=60`: **350 passed, 14 deselected** in 18.05s — exactly matches spec target (was 350/13; +1 deselected from new flow test)
- 3-consecutive-run stability check on `test_flow_provider_setup.py`: **3/3 passed** at 1.69s, 1.74s, 1.62s wall-time (with `time -f` showing 2.17s, 2.28s, 2.14s including pytest overhead) — no flakiness, no timing races
- `ruff check tests/browser/` and `ruff format --check tests/browser/`: clean

**Per-test timing observation (`test_first_start_provider_setup_flow`)**: From subprocess setup → assertion-ready, total ~1.74s decomposes as: pytest fixture setup **0.86s** (Popen + uvicorn import + lifespan including `init_db` + `AgentFactory` build on a fresh tmp_path; matches the leg-04 baseline of ~0.5-0.9s for `app_clean`), test body call **0.60s** (12-step flow including 2 hash-navigation reloads, 1 select-option, 1 form-fill, 4 button clicks, 1 form Cancel, plus 5 `expect` auto-waits), teardown **0.28s** (page+context close, SIGTERM+wait on subprocess). The `expect(...).to_contain_text("Mock", timeout=5000)` for Test Connection consistently resolved sub-100ms (mock returns immediately with no I/O). Stability is excellent across 3 runs (max delta 120ms wall-time).

### Leg 07 — Flow Test: Chat (2026-04-25)

**Status**: landed

**What was done**: Added three `data-testid` attributes to load-bearing chat UI elements per the leg-design selector strategy — `chat-input` and `chat-send-btn` on the input/Send button HTML in the content-DOM template (`chat.js:47-48`), and `message` on each `addMsg`-rendered `.msg.{cls}` div via `el.setAttribute('data-testid', 'message')` (`chat.js:83`). Created `tests/browser/test_flow_chat.py` with a single `@pytest.mark.browser` test (`test_chat_send_receives_mock_response`) that uses the `app_with_agent` fixture (mock provider + agent named "test-agent" pre-seeded) and drives Chromium through the full WebSocket chat flow: navigate to base_url → wait for `.status` to become "connected" (WebSocket onopen) → wait for `.session-agent-badge` to read "test-agent" (auto-session-create with seeded agent) → fill `[data-testid="chat-input"]` with "hello" → click `[data-testid="chat-send-btn"]` → assert user message renders (`[data-testid="message"].user` with text "hello") → assert assistant message renders with the mock provider's exact default response "Mock response from the mock provider." → assert send button re-enabled after `done` event. Test uses Playwright's `expect()` exclusively with conservative auto-wait timeouts (5s for connect/badge/user msg, 10s for assistant msg).

**Anomalies / deviations**: None. Test passed on first execution after the testid edits — no chat UX bugs surfaced (in contrast to leg 05's admin.js base_url validation bug). The full WebSocket flow worked exactly as specified: `connect()` → status="connected" → `checkSetupState()` → `fetchAgents()` (populates `agentSelect.value="test-agent"`) → `list_sessions` → empty session list → auto `new_session` with `agent_name="test-agent"` → `session_joined` → badge updates → user types/sends → server emits user/usage/assistant/done events in order → addMsg renders each → `done` event re-enables send button. The `agentSelect.value === "test-agent"` race (only seeded agent + `fetchAgents` runs before `list_sessions`) resolved deterministically across all 4 test runs (1 initial + 3 stability) with no flake.

**Final test counts**:
- `pytest -m browser tests/browser/test_flow_chat.py -v --timeout=60`: **1 passed** in **1.30s**
- `pytest -m browser tests/browser/ -v --timeout=60`: **8 passed** in **8.26s** (smoke + 2 app-fixture + 2 seeder + 3 flow)
- Full `pytest tests/ --tb=short -q --timeout=60`: **350 passed, 16 deselected** in 17.99s — exactly matches spec target (was 350/15; +1 deselected from new flow test)
- 3-consecutive-run stability check on `test_flow_chat.py`: **3/3 passed** at **1.41s, 1.26s, 1.24s** wall-time (max delta 170ms) — no flakiness, no WebSocket timing races
- `ruff check tests/browser/` and `ruff format --check tests/browser/`: clean (8 files, 0 issues)

**Per-test timing observation (`test_chat_send_receives_mock_response`)**: pytest `--durations=10` reported setup=**0.95s**, call=**0.16s**, teardown=**0.22s** for total ~1.33s. The fixture setup (~0.95s) decomposes as: subprocess startup ~0.40s (uvicorn + lifespan with `init_db` + `AgentFactory` build on fresh tmp_path), `seed_mock_provider` POST ~0.05s, `seed_mock_agent` POST ~0.05s, plus Chromium context setup ~0.4s. The **test body call took just 0.16s** for the entire flow: page.goto + WebSocket connect (~50-100ms typical on localhost) + status assertion + badge assertion + 2 form interactions + 2 message assertions + send-button-enabled assertion. **User msg → assistant msg round-trip**: well under 100ms — the assistant message's `to_have_text(...)` auto-wait resolves nearly instantly because the mock provider's `complete()` is synchronous (no I/O), the agent step loop emits user→usage→assistant→done events back-to-back, and Playwright polls every ~50ms. The 10s timeout for the assistant assertion is ~100x the typical observed latency — generous safety margin for CI/WSL2 jitter without masking real bugs. Stability is excellent across 3 stability runs (max wall-time delta 170ms, all under 1.5s). No WebSocket reconnects, no race observed on `agentSelect.value === "test-agent"` (the auto-session-create path).

### Leg 06 — Flow Test: Agent CRUD (2026-04-25)

**Status**: landed

**What was done**: Added five `data-testid` attributes to load-bearing Studio elements per the leg-design selector strategy — `new-agent-btn` on the sidebar `+` button (HTML string, `studio.js:30`), `agent-empty` on the empty-state placeholder (createElement + `setAttribute`, `studio.js:81-83`), `agent-item` on each sidebar agent row (createElement + `setAttribute`, `studio.js:88-91`), `delete-agent-btn` on the editor-header Delete button (HTML string, `studio.js:200`), and `save-agent-btn` on the editor save/create button (HTML string, `studio.js:308`). Created `tests/browser/test_flow_agent_crud.py` with a single `@pytest.mark.browser` test (`test_studio_agent_crud_flow`) that uses the `app_with_provider` fixture (mock provider seeded, no agents) and drives Chromium through the 15-step CRUD sequence: empty state visible → click `+` → "New Agent" header → fill name/description → assert provider auto-selected to seeded mock id → wait for `mock-default` model option to attach → select model → fill system prompt → click Create → assert exactly one `agent-item` appears with the right name and editor switches to edit mode → edit description → Save → assert description input retains the new value after re-render → click Delete (first click → "Confirm Delete?") → click Delete again → assert empty state restored, no agent items, editor empty visible. Test uses Playwright's `expect()` exclusively; uses `to_be_attached(timeout=5000)` for the async-populated `<option>` per the leg's IG note about Playwright's option visibility model.

**Anomalies / deviations**: None substantive. Test passed on first execution after the testid edits — no Studio UX bugs surfaced (in contrast to leg 05's `admin.js` `base_url` validation bug). The Studio create-then-Save-then-Delete path was already coherent: provider auto-selects from `allProviders[0]`, model dropdown populates via the initial `fetchModelsForProvider` call after render, and the two-click delete confirm pattern (3000ms window) reliably fires both clicks well within the budget. No async race observed across the 5-runs total (1 initial + 1 verification + 3 stability) — model option always attached well under the 5s timeout. The only small thing of note: the `<option>` for `mock-default` is created synchronously inside the same render cycle that opens the editor (since the seeded provider's id is already in `allProviders`), so `to_be_attached` resolves nearly immediately; the 5s timeout is just defensive padding.

**Final test counts**:
- `pytest -m browser tests/browser/test_flow_agent_crud.py -v --timeout=60`: **1 passed** in **1.76s**
- `pytest -m browser tests/browser/ -v --timeout=60`: **7 passed** in **6.88s** (smoke + 2 app-fixture + 2 seeder + 2 flow)
- Full `pytest tests/ --tb=short -q --timeout=60`: **350 passed, 15 deselected** in 18.28s — exactly matches spec target (was 350/14; +1 deselected from new flow test)
- 3-consecutive-run stability check on `test_flow_agent_crud.py`: **3/3 passed** at **1.67s, 1.66s, 1.62s** wall-time (max delta 50ms — extremely stable)
- `ruff check tests/browser/` and `ruff format --check tests/browser/`: clean (after one auto-format pass on the new file to merge a long `expect(...).to_be_attached(timeout=5000)` call onto a single line)

**Per-test timing observation (`test_studio_agent_crud_flow`)**: From subprocess setup → assertion-ready, total ~1.76s decomposes roughly as: pytest fixture setup ~0.55s (Popen + uvicorn lifespan + `seed_mock_provider` POST ~50ms), test body call ~0.95s (15-step flow including 1 hash-navigation, 4 form-fills, 2 select_option waits, 5 button clicks across 3 distinct buttons including the two-click delete, plus 11 `expect` auto-waits — three of which involve list-count or input-value polls), teardown ~0.26s (page+context close, SIGTERM). The CRUD test is denser than the provider-setup flow (15 vs 12 assertion steps, 5 vs 4 button clicks, 4 vs 1 form-fill) but completes in similar wall-time because the mock provider responds to the model-list fetch synchronously and the JS re-renders are sub-50ms. Stability is excellent across 3 runs (max delta 50ms — tighter than leg 05's 120ms delta). No flakiness, no timing races on the `to_be_attached` model-option wait or the two-click delete confirm window.

### Leg 08 — CI Integration (2026-04-25)

**Status**: landed

**What was done**: Wired browser tests into the Concourse pipeline by surgically modifying ONLY the test task in `ci/pipeline.yml` (lines 82-100): swapped `python:3.11-slim` for `mcr.microsoft.com/playwright/python:v1.58.0-jammy` (pinned to match dev-env's `playwright==1.58.0`), added `THE_ONE_DEV_MODE: "true"` Concourse param and propagated it into the inner test container via `docker run -e THE_ONE_DEV_MODE="${THE_ONE_DEV_MODE}"`, and chained two pytest invocations with `&&` inside the inner `sh -c` (default `pytest tests/ --tb=short -q` then `pytest -m browser tests/browser/ --tb=short -q`). The autopilot task at lines 32-79 (`python:3.11-alpine`) was NOT touched — `git diff ci/pipeline.yml` confirms changes are scoped to the test task only (4 lines: +THE_ONE_DEV_MODE param, +-e propagation, image swap, command extension). Updated `CLAUDE.md` with four additions: (1) browser test command in Commands section after the `pytest -m live` line, (2) Browser tests subsection in Testing section explaining the marker + addopts exclusion + conftest reference, (3) Dev mode + mock provider subsection placed immediately after the Configuration paragraph (covers default response string, dev-mode-off behavior, type defaults invariance), (4) `__MASKED__` sentinel subsection placed immediately after the Encryption paragraph (covers the contract between provider edit form and `update_provider`). Updated `the_one/agents.md` with two new top-level sections after Continue Signal: Browser test fixtures (covers `app_clean`/`app_with_provider`/`app_with_agent` fixture stack, per-test subprocess + tmp_path isolation, the IPv6 WSL2 quirk, and a pointer to the post-incident note about module-scoped Playwright fixtures from leg 03), and Provider type extension checklist (six-layer audit list with the M04 schema-CHECK incident captured as a History callout above the list). Verified `docker pull mcr.microsoft.com/playwright/python:v1.58.0-jammy` succeeds against Microsoft's public registry — tag exists and is pullable, no auth needed. Sanity check (break-and-revert) executed: temporarily changed `setup-banner` testid in `chat.js:218` to `setup-banner-broken`, ran the provider-setup flow test, captured the failing locator-timeout output (below), reverted the testid, and re-ran to confirm green (1 passed in 1.71s).

**Sanity check evidence** — captured failure output (with `setup-banner` broken to `setup-banner-broken` in `chat.js`, before revert):

```
tests/browser/test_flow_provider_setup.py::test_first_start_provider_setup_flow FAILED [100%]

=================================== FAILURES ===================================
_____________________ test_first_start_provider_setup_flow _____________________
    @pytest.mark.browser
    def test_first_start_provider_setup_flow(app_clean: str, page: Page) -> None:
        base_url = app_clean
        # 1. Open app (defaults to #chat). Setup banner shows "Getting started".
        page.goto(base_url)
        setup_banner = page.locator('[data-testid="setup-banner"]')
>       expect(setup_banner).to_be_visible()
E       AssertionError: Locator expected to be visible
E       Actual value: None
E       Error: element(s) not found
E       Call log:
E         - Expect "to_be_visible" with timeout 5000ms
E         - waiting for locator("[data-testid=\"setup-banner\"]")
======================== 1 failed, 2 warnings in 6.18s =========================
```

The error message is exactly the kind a future regression would produce — clean locator-not-found with the testid value clearly visible — confirming the regression net catches testid drift. After revert, re-run shows `1 passed in 1.71s` (no lingering damage). The chat.js diff post-revert shows only leg 07's `chat-input`/`chat-send-btn`/`message` testids, not the temporary sanity-check edit.

**CI verification status** — operator-pending. Autonomous execution does not run `fly` against the live Concourse instance. The operator must verify out-of-session by running:

```bash
fly -t self set-pipeline -p the-one -c ci/pipeline.yml
fly -t self trigger-job -j the-one/deploy
fly -t self watch -j the-one/deploy
```

Confirm both pytest invocations in the test task pass (default `tests/` then `-m browser tests/browser/`). Document the result in this flight's debrief. First pull on a fresh worker takes 5-10 minutes for the ~6 GB Playwright image; subsequent runs use the worker cache. The `docker pull mcr.microsoft.com/playwright/python:v1.58.0-jammy` smoke check passed locally — tag exists, no registry auth needed.

**Final test counts**:
- Default `pytest tests/ --tb=short -q --timeout=60`: **350 passed, 16 deselected** in 18.70s — exactly matches spec target
- `pytest -m browser tests/browser/ -v --timeout=60`: **8 passed** in 8.28s (smoke + 2 app-fixture + 2 seeder + 3 flow) — exactly matches spec target
- Sanity-check post-revert run of `test_flow_provider_setup.py`: **1 passed** in 1.71s
- `ruff check the_one/ tests/`: 8 pre-existing errors (verified via `git stash` to be identical on the unmodified branch — none introduced by this leg; all in files this leg did not touch). Per AC line 94, this leg touched only YAML and Markdown files (chat.js was break-and-reverted), so the ruff AC is trivially satisfied for files modified by leg 08.
- `ruff format --check the_one/ tests/`: 27 pre-existing format issues (same — all pre-date Flight 01).

**Anomalies / deviations**: None substantive. Implementation matched the leg spec exactly: surgical pipeline edit (verified via `git diff` showing only the test-task block changed), four CLAUDE.md additions placed at the spec'd anchor points, two agents.md sections appended cleanly, sanity check executed in the spec'd order (capture-before-revert), test counts matched spec exactly on first run. The only out-of-band note is the optional `docker pull` smoke check passed on first attempt, which strengthens confidence in the operator-pending CI verification (the image tag is real and accessible).

### Leg 03 — App Fixture (2026-04-25)

**Status**: landed

**What was done**: Replaced the docstring-only `tests/browser/conftest.py` with the full fixture stack per spec: module-level helpers (`_free_port` using `socket.bind(('', 0))`, `_wait_for_ready` polling `/api/info` every 100ms with `proc.poll()` early-exit on subprocess death), function-scoped `app_clean` fixture (spawns `python -m uvicorn the_one.interfaces.web.app:app --host 127.0.0.1 --port {port}` with `THE_ONE_DATA_DIR={tmp_path}/the-one-data` and `THE_ONE_DEV_MODE=true`, captures stdout/stderr on startup failure for diagnostics, SIGTERM → 10s wait → SIGKILL teardown), and the Playwright fixtures (`playwright_instance`, `browser`, `page`). Created `tests/browser/test_app_fixture.py` with the two sanity tests: `test_app_clean_serves_index` (uses `app_clean` + `page`, navigates to `/`, asserts title contains "the-one") and `test_app_clean_responds_to_api_info` (HTTP-only, hits `/api/info` and asserts 200 + `version` field).

**Anomalies / deviations**:

1. **Playwright fixture scope changed from session → module (substantive deviation from spec)**: First full-suite run (`pytest -m browser tests/browser/ -v`) failed with `playwright._impl._errors.Error: It looks like you are using Playwright Sync API inside the asyncio loop. Please use the Async API instead.` on the leg-01 smoke test, but only when run *after* the new app-fixture tests in the same session. Root cause: with `playwright_instance` and `browser` at session scope, the `sync_playwright()` context (which internally pins an asyncio loop in the main thread) stays alive for the entire test session. When `tests/browser/test_smoke.py::test_playwright_loads_data_url` then calls its own standalone `sync_playwright()` from the main thread, Playwright detects the still-active loop and refuses to start a second sync greenlet driver. Confirmed by ordering: `pytest tests/browser/test_smoke.py` alone passes; `pytest -m browser tests/browser/` (which runs `test_app_fixture.py` first alphabetically, then `test_smoke.py`) fails the smoke test. **Resolution**: changed both `playwright_instance` and `browser` from `scope="session"` to `scope="module"`. The Playwright context is now torn down after `test_app_fixture.py` completes, freeing the main-thread loop before `test_smoke.py` runs. Within a single test module, fixtures are still shared (so the spawned-once-per-module Chromium amortizes across tests in that module), which preserves nearly all the speed benefit. Spec `Outputs` section was checked — it says "session-scoped" for both, but the spec also explicitly requires the existing `test_smoke.py` to keep passing without modification. Module-scoping satisfies both intents. The leg's docstring header in `conftest.py` was updated to reflect the new scope. Captured under "Decisions" below as well. Alternatives considered and rejected: (a) modifying `test_smoke.py` to use the conftest fixtures (forbidden by leg constraints — smoke test is intentionally toolchain-only and must stay self-contained); (b) disabling `pytest-asyncio` auto-mode for the browser dir (broader blast radius, would require a per-directory conftest carve-out that the existing async tests in `tests/` don't need); (c) function-scoping `playwright_instance` (~1s extra per browser test for Chromium launch, more expensive than necessary).

2. **App startup time observation**: First test of a session: app fixture takes ~1.0s from Popen → `/api/info` 200 (lifespan runs `init_db` + `migrate_json_to_sqlite` + `AgentFactory` build on a fresh empty data_dir). Subsequent tests (warm Python interpreter cache for the test runner, cold subprocess each time): also ~1.0s, dominated by uvicorn import + lifespan. Total per-test overhead (fixture startup + teardown + Playwright page setup): ~1s for `test_app_clean_responds_to_api_info`, ~1.1s for `test_app_clean_serves_index`. Two tests run in ~1.85s total (some overlap — Chromium launch happens once at module scope and amortizes across both tests). 5-run stability runs: 2.33s, 1.87s, 1.77s, 1.73s, 1.74s — first run slightly slower (cold filesystem cache for `the_one.*` modules in subprocess), then very steady. No port collisions, no flaky failures across all five runs. The 15s `_wait_for_ready` timeout has a 14x safety margin.

3. **Removed `BrowserContext` import from conftest**: The spec's import line included `BrowserContext` but the symbol isn't used as an annotation anywhere (it's only used internally as `browser.new_context()` return). Removed to keep `ruff check` clean (would have triggered F401 unused-import). The actual context handling is unchanged — `page` fixture still creates and closes a fresh `BrowserContext` per test.

**Final test counts**:
- `pytest tests/browser/ --collect-only -q -m browser`: **3 tests collected** (smoke + 2 new)
- `pytest -m browser tests/browser/test_app_fixture.py -v`: **2 passed** in ~1.85s (~0.9s/test wall-time after Chromium launch amortization)
- `pytest -m browser tests/browser/ -v`: **3 passed** in ~2.20s
- `pytest tests/`: **350 passed, 11 deselected** in ~17.6s — exactly matches spec target (was 350/9; +2 deselected from new browser tests)
- 5-consecutive-run stability check: **5/5 runs passed** (1.73s–2.33s, mean ~1.89s) — no flakiness, no port collisions
- `ruff check tests/browser/` and `ruff format --check tests/browser/`: clean (3 files, 0 issues)

---

## Decisions

_(runtime decisions not in original plan)_

### Leg 05 — Fix `admin.js` form base_url validation for hidden-field types (2026-04-25)

The leg's outputs section explicitly listed the 5 `data-testid` attributes as the only `admin.js` changes. During implementation, the test failed because the `.admin-pf-save` click handler unconditionally validated `base_url` non-empty even when the field was hidden by the type selection (mock). One-line fix to gate the non-empty check on `defaults.showBaseUrl` was applied. This is a real UX bug (mock providers were impossible to create via the form, despite the API and seeders both accepting empty `base_url`). The alternative — adding a synthetic placeholder string in the form payload for hidden fields — would have masked the bug and diverged from the seeder/API contract. The fix is consistent with the leg's "small fixable issue" guidance and the leg-design intent that selecting mock + submitting should succeed. No test other than this new flow test depended on the prior behavior.

---

## Deviations

_(departures from planned approach)_

---

## Anomalies

_(unexpected issues encountered)_

---

## Session Notes

### 2026-04-25 — Flight start

- Branch `flight/01-browser-test-foundation` created from `main`
- Flight status updated `ready` → `in-flight`
- Mission directory (`missions/04-ui-maturity/`) was untracked at flight start; will be committed with the first leg

### Flight Director Notes

**Phase file loaded**: Project-side `the-one/.flightops/agent-crews/leg-execution.md` (not the default fallback). Crew extracted: Developer (Sonnet), Reviewer (Haiku), optional Accessibility Reviewer (Sonnet). All required sections (Crew, Interaction Protocol, Prompts) present and well-formed.

**Accessibility Reviewer applicability**: F1 is a foundation flight (testing tooling + mock provider + browser tests). Leg 02 (mock provider) touches `admin.js` to swap hardcoded `PROVIDER_TYPES` for a backend fetch — this is a UI-touching change but it's behavioral, not visual. A11y review will be more valuable once F2-F6 introduce the design language and per-area UI work. For F1, plan to spawn A11y Reviewer only on legs that meaningfully change the rendered UI (likely none — even leg 02's admin.js change is fetch-and-populate, not new visual elements). Will reassess per leg.

**Leg 01 design review**: Spawned one Developer for review (Sonnet). Result: approve with low-severity changes — `tests/browser/__init__.py` was unnecessary (dropped). No second review cycle (changes were minor/cosmetic per agentic-workflow rule).

**Leg 01 implementation deviation accepted**: Developer encountered a `from conftest import FakeLLM, StubTool` collision when adding `tests/browser/conftest.py` (5 existing test files use the bare-`conftest` import pattern). Resolved with pytest config-only changes: `--import-mode=importlib` added to `addopts` plus `pythonpath = ["tests"]`. This is a well-known pytest recommendation for projects with non-package test directories (`tests/` has no `__init__.py`) and does not change the marker-filter semantics the leg required. Accepted; documented in pyproject.toml inline comment. Subsequent legs may benefit from migrating off the bare-`conftest` pattern (out of scope for this flight; flagged as future cleanup).

**Leg 02 design review**: Spawned one Developer for review (Sonnet). Result: approve with changes — 2 high-severity clarifications (call out `_fake_get_provider` `**kwargs` compatibility check; explicit Outputs note that mock UI editing is out of scope), 1 medium (tighten update_provider gating placement), several low-severity wording fixes. Also accepted the suggestion to add a route-ordering regression test (`test_types_route_does_not_collide_with_id_route`) — cheap insurance. All applied. No second review pass needed (changes were clarifications, not new design).

**Leg 02 implementation deviation accepted (schema migration v6)**: Implementing Developer hit a `sqlite3.IntegrityError: CHECK constraint failed: type IN ('ollama', 'openai-compatible', 'openai', 'anthropic')` on first test run. The leg's State-Machine Reachability Audit listed five lower layers but missed the SQLite CHECK constraint at `db/schema.py:18,129`. Developer added migration v6 using the established v3/v5 table-rebuild pattern (`PRAGMA foreign_keys=OFF` + rebuild + restore) and updated two existing schema tests to expect the new version. Deviation accepted: this is the same class of cross-cutting-infrastructure miss the M03 debrief flagged ("Schema FK choices must be audited against the application-layer state machine" — generalize to "all schema-layer constraints"). The leg already flagged the action item for leg 08 documentation: update the implicit "provider type extension checklist" in `the_one/agents.md` to add the SQLite CHECK constraint as the sixth layer. Carrying that into F1 debrief recommendations as well — the `/leg` skill's State-Machine Reachability Audit checklist should explicitly mention DB CHECK constraints alongside FK constraints.

**Leg 03 design review**: Spawned one Developer for review (Sonnet). Result: approve with changes — 1 medium (AC named a different test than the IG provided; reconciled by updating AC to match IG's `test_app_clean_responds_to_api_info`), several non-blocking suggestions. Accepted two suggestions for free: (1) drop redundant `THE_ONE_PORT` env var from the subprocess (uvicorn binds via `--port` CLI flag; nothing in `app.py` reads `settings.port` post-init), (2) add `proc.poll()` early-exit to `_wait_for_ready` so a dying subprocess fails in <1s instead of hanging the full timeout. No second review pass needed.

**Leg 03 implementation deviation accepted (Playwright scope change)**: Implementing Developer encountered a session-scoped Playwright instance keeping its asyncio loop alive across modules, breaking the leg-01 standalone smoke test (which creates its own `sync_playwright()` context). Resolved by changing the `playwright_instance` and `browser` fixtures from session→module scope. This still amortizes Chromium across the multiple tests within a single test module, while letting the standalone smoke test's own `sync_playwright()` work. Deviation accepted: tightens the scope where it was over-broad. The original spec's claim that session-scoped Playwright was safe alongside the standalone smoke test was wrong — the conflict is real, and the implementer caught it. Worth a one-line note when documenting browser fixture conventions.

**Leg 04 design review**: Spawned one Developer for review (Sonnet). Result: approve with changes — 1 medium (import path inconsistency: spec used `from tests.browser.X` instead of the established bare-`from browser.X` pattern that leg 01's `pythonpath = ["tests"]` enables; reconciled), 2 low (docstring tightening for `base_url=""` and AgentConfig defaults). Also accepted the suggestion to make `app_with_agent` compose on `app_with_provider` (rather than re-seeding) — pytest's per-test fixture caching makes this cleaner. No second review pass needed.

**Leg 04 implementation note (ruff import grouping)**: Implementing Developer's only deviation was that ruff auto-sorted `from browser.seeders import ...` into the third-party block (the project has no `known-first-party` config). Functionally identical; documented inline. Worth a note that adding `[tool.ruff.lint.isort] known-first-party = ["the_one", "browser", "conftest"]` to pyproject.toml would group these correctly — defer to leg 08 cleanup or a follow-up.

**Leg 05 design review**: Spawned two Developer reviews (Sonnet, two passes). Round 1: needs rework — the test scenario was unreachable as written because after Create, `admin.js:665-670` auto-switches the form to edit mode (rather than returning to the list). Test couldn't find a provider-card before clicking edit. Restructured: Create → exploit auto-switch to edit mode (Test Connection button now visible) → Test Connection → Cancel back to list → verify card. Round 2: approve, with one stale-edge-case cleanup. Lesson for future flow legs: trace the actual save-success path (especially for create-vs-edit branching) before writing test assertions about list state. The auto-edit-after-create UX is convenient but counterintuitive; F2 may want to revisit it.

**Leg 05 implementation deviation accepted (admin.js save-handler bug fix)**: Implementing Developer caught a real bug while writing the flow test: `admin.js`'s save handler always validated `base_url` non-empty, but `mock` type hides the field via `TYPE_DEFAULTS.mock.showBaseUrl=false`. The form would block save with "Base URL is required" even though the API accepts empty `base_url` for mock (verified by leg 04 seeders working fine). One-line fix: only enforce non-empty when `defaults.showBaseUrl` is true. This is a real UX bug, not a test workaround. Documented in flight log under leg 05 anomalies. The mission-level recommendation in the M03 debrief about "form-rendering convention divergence between admin.js and studio.js" lands exactly here — F3's form primitive extraction should consolidate this validation logic so it doesn't drift again.

**Leg 06 design review**: Spawned one Developer for review (Sonnet). Result: approve — line refs all accurate (much tighter than leg 05's), no high/medium issues, two cosmetic suggestions accepted: (1) `to_have_count(1)` after Create instead of just `to_be_visible()` (distinguishes "appeared" from "editor switched"), (2) assert `.editor-empty` visible after delete (covers editor reset, not just sidebar). No second review pass needed.

**Leg 06 implementation summary (no deviations)**: Implementing Developer landed leg 06 cleanly with no anomalies — unlike leg 05's admin.js base_url bug, the Studio CRUD flow worked correctly on first execution after testid edits. Provider auto-select, model dropdown population, two-click delete, save → re-render preservation all functioned as designed. 3/3 stability runs with max delta 50ms (tighter than leg 05's 120ms). Note for F2 contrast: studio.js is structurally cleaner around save/cancel/delete than admin.js was — admin.js's bugs may be worth deeper refactoring during F3's form primitive extraction.

**Leg 07 design review**: Spawned one Developer for review (Sonnet). Result: approve — all critical references verified (chat.js selectors, WebSocket onopen chain, mock provider integration, agent step pipeline emits user→usage→assistant→done in order, mock provider's exact default response string). Two low-severity nits applied: (1) trim the verbose (a)/(b) analysis in Context to just the verified reasoning, (2) add edge-case note explaining the model-loading element intentionally lacks `data-testid="message"` (it's a UI affordance, not a chat message; not exercised by mock provider anyway). No second review pass needed.

**Leg 07 implementation summary (no deviations)**: Implementing Developer landed leg 07 cleanly with no anomalies. Chat flow worked first-try after testid edits; agentSelect race resolved deterministically across all 4 runs (1 verification + 3 stability). Round-trip user→assistant well under 100ms (mock provider is in-process, no I/O). 3-run stability max delta 170ms — slightly higher than legs 05/06 (~50-120ms) but still well within the 5s/10s timeout budgets. No chat-side UX bugs surfaced.

**Flight progress checkpoint**: 7 of 8 autonomous legs complete. Test counts at this point: 350 passed (existing) + 14 new mock-provider tests = 350 unit-level. Browser: 8 (smoke + 2 app-fixture + 2 seeder + 3 flow). Default `pytest tests/` = 350 passed, 16 deselected. Flight is on track; only CI integration (leg 08) remains before flight-level code review and commit.

**Leg 08 design review**: Spawned one Developer for review (Sonnet). Result: approve with changes — 2 high (CLAUDE.md `__MASKED__` placement was vague: tightened to "new subsection after existing encryption paragraph at line 52"; "no other Concourse jobs modified" AC was easily missed: tightened to explicitly call out the autopilot task at lines 32-79 with `python:3.11-alpine` as off-limits), 2 medium (dropped "or equivalent" loophole on image tag — exact `v1.58.0-jammy` only; reordered sanity-check IG to capture failure output BEFORE reverting since the revert leaves no permanent artifact), several low/suggestion items folded in (default response string mentioned in CLAUDE.md note, module-scoped Playwright fixture quirk added to agents.md, M04 anecdote moved to a History callout in the provider checklist, optional `docker pull` smoke check added). No second review pass needed — changes are clarifications and structural tightening, not new design.
