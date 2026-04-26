# Flight: Browser Test Foundation

**Status**: landed
**Mission**: [UI Maturity](../../mission.md)

## Contributing to Criteria

- [x] Automated browser tests cover the critical user flows and fail on regression, runnable both locally and in CI
- [ ] Critical user flows (start a new chat, create and configure an agent, add and verify a provider) progress without dead-ends, unexplained errors, or unclear next steps *(this flight provides the regression net; subsequent flights polish the flows themselves)*

---

## Pre-Flight

### Objective

Stand up Playwright (Python binding) as the project's browser-testing toolchain and lock in the patterns subsequent flights will reuse: per-test app lifecycle, isolated data directories, stub LLM, marker scheme, and CI integration. Cover the three M03-era critical flows (provider setup, agent CRUD, chat) as baseline regression tests so future restructuring (F3 app shell, F4-6 alignment) breaks them visibly when it should. Visual-regression snapshots are intentionally deferred to F2 — snapshotting the pre-redesign UI is wasted work.

### Open Questions

_(all resolved during planning — see Design Decisions)_

### Design Decisions

**Playwright Python binding (not JS)**: Use `playwright` PyPI package with `playwright install` for browsers. Keeps toolchain unified with existing pytest infrastructure; matches AIAT pattern; no Node.js dependency.
- Rationale: Architect noted JS adds a separate toolchain for no benefit at this scale.
- Trade-off: Slightly less mature than the JS binding but functionally complete; the Python community has caught up.

**Pytest marker scheme — `@pytest.mark.browser`**: Parallel to existing `@pytest.mark.live`. `addopts` extended to exclude both by default (`-m "not live and not browser"`).
- Rationale: Browser tests are slow and require browsers installed; default `pytest tests/` should remain fast (~6s).
- Trade-off: Three test categories (default unit, live AIAT, browser) — slightly more complex mental model, but mirrors existing convention.

**App lifecycle — per-test subprocess on random port**: Each test fixture starts a fresh `uvicorn` subprocess with `THE_ONE_DATA_DIR` pointing at a `tmp_path` directory and `THE_ONE_PORT` set to a free port (via `socket.bind(('', 0))`). The fixture polls `GET /api/info` on the chosen port until 200 (timeout ~10s) before yielding to the test — uvicorn's lifespan handler runs `init_db` and `migrate_json_to_sqlite`, which is not instantaneous on first run. Browser navigates to `http://127.0.0.1:{port}` (not `localhost`) to avoid IPv6 first-attempt delay on WSL2. Teardown sends SIGTERM and waits for clean exit.
- Rationale: Strongest isolation. No shared `_sessions` dict, no DB reuse, no state bleed between tests. Matches the per-test isolation that made the M01-M03 unit tests reliable.
- Trade-off: ~1-2s startup cost per test. Acceptable for a baseline of ~3-5 flow tests; revisit batching if the suite grows past ~20 tests.

**LLM determinism — `mock` provider type (dev-mode-gated)**: Add a fifth provider type `mock` alongside the existing four (`ollama`, `openai-compatible`, `openai`, `anthropic`). Implemented as `MockProvider(LLMProvider)` in `the_one/llm/mock.py`, returning scripted responses from a config field (with a sensible default), supporting both text and tool-call replies. Dual-purpose: serves browser tests AND gives the user an offline/demo-ready LLM for dev work.

Implementation surface:
- `the_one/llm/mock.py` — `MockProvider` class (~30-50 LOC). `complete()` reads scripted responses from `LLMProviderConfig.config` (the existing per-provider JSON dict at `db/models.py:23`); falls back to a fixed default if none provided. Returns canonical `Message` with optional `tool_calls: list[ToolCall]` — format is provider-agnostic, no `tool_schema()` override needed. Inherits the base class `max_context_tokens = 128_000` default (sufficient for tests).
- `the_one/llm/registry.py` — add `"mock"` to the `loaders` dict (eager registration; no optional-extras `ImportError` path since mock has no extra dependencies).
- `the_one/agent/factory.py` `_PROVIDER_TYPE_MAP` — add `"mock": "mock"` mapping (one-line change).
- `the_one/db/models.py` — add `"mock"` to the provider type `Literal` (one-token change).
- `the_one/interfaces/web/api.py`:
  - New `GET /api/providers/types` endpoint — returns the list of allowed provider types, omitting `mock` when `settings.dev_mode` is false. The Admin UI fetches this on area init instead of using the hardcoded `PROVIDER_TYPES` array in `admin.js:22-27`.
  - `create_provider` (`api.py:437`) and `update_provider` (`api.py:448`) — both reject when the resulting `type == "mock"` and `settings.dev_mode` is false (return 400). Pydantic Literal validation alone won't catch this once `mock` is in the type enum. Update-path rejection prevents type-changing an existing provider to `mock` after DEV_MODE is turned off.
  - `test_provider` (`api.py:502`) — add `mock` branch returning `{"status": "ok", "detail": "Mock provider (dev mode)"}`.
  - `list_provider_models` (`api.py:555`) — add `mock` branch returning the model list from `LLMProviderConfig.config` (e.g., `["mock-fast", "mock-thinking"]`); falls back to a default like `["mock-default"]` if config has no `models` key.
- `the_one/interfaces/web/static/js/areas/admin.js`:
  - Replace hardcoded `PROVIDER_TYPES` with a fetch against `GET /api/providers/types` on area `init()` or `activate()`.
  - Add `mock` entries to `TYPE_BADGE_COLORS` (muted gray, e.g., `#888`) and `TYPE_DEFAULTS` (`{ base_url: '', showBaseUrl: false, showApiKey: false }`). Mock has no `api_key`, so the existing `__MASKED__` sentinel logic in update is naturally inert for mock.
- `the_one/config.py` — add `dev_mode: bool = False` to `Settings` (populated by `THE_ONE_DEV_MODE`).

- Rationale: Simpler than HTTP-level stubbing, dual-use (offline dev + tests), avoids the "track Ollama API surface" maintenance burden, sidesteps the autoload path entirely. Production-code-for-tests is acceptable because the same code is genuinely useful outside testing.
- Trade-off: Browser tests no longer exercise the real Ollama HTTP serialization. Mitigation: existing AIAT live tests (`tests/test_aiat.py`) cover that path against a real instance — coverage isn't lost, just not duplicated in the browser suite. Adding a fifth provider type slightly expands the type-extension checklist (M03 debrief noted this checklist exists implicitly).

**Visual snapshots deferred to F2**: Playwright supports `expect(page).to_have_screenshot()` but Flight 1 will not use it. F2 introduces the design language; snapshotting the current pre-redesign UI is wasted effort.
- Rationale: Snapshot baselines built against the current UI would all need to be invalidated and rebuilt in F2. F2 hand-off includes establishing the snapshot pattern against the new design.
- Trade-off: F1 doesn't lock in visual regression. Acceptable — flow regression is the F1 goal; visual regression is F2's.

**CI integration time-boxed to one leg, local-only fallback**: One leg adds browser tests as part of the existing Concourse `test` task (running app + Playwright together inside the test container against `THE_ONE_DATA_DIR=/tmp/test-data`), NOT as a post-deploy task against the live instance. Running browser tests against the deployed app would mutate production state (creating providers/agents/sessions in the live `the_one_data` volume). The image switches from `python:3.11-slim` to `mcr.microsoft.com/playwright/python` (~6 GB uncompressed, includes Python + Node.js + browsers). If integration slips beyond the leg budget, fall back to a documented local-only run command and capture the unfinished work as known issues for a follow-up.
- Rationale: Architect flagged this as the highest-risk piece (heavy image, novel toolchain in CI, potential network/ephemeral-port conflicts in Concourse workers). Test-container approach keeps test data isolated and matches the existing `test`-task pattern. Time-boxing avoids the leg dragging the whole flight.
- Trade-off: Local-only means regressions only surface when developers run the suite. Acceptable as a temporary state — mission criterion is "runnable both locally and in CI," and local-only satisfies the local half while documenting the CI gap. The 6 GB image will dominate Concourse build time on first pull; cached on subsequent runs.

**Test directory layout — `tests/browser/`**: New subdirectory under `tests/`, with its own `conftest.py` for browser-specific fixtures. Root `conftest.py` is unchanged.
- Rationale: Browser tests have distinct fixture needs (subprocess lifecycle, page object, seeders) that don't belong in the root conftest. Subdirectory keeps imports clean (`from tests.browser.conftest import ...` if needed).
- Trade-off: Slight discoverability cost — developers need to know browser tests live in a subdirectory. Mitigated by clear file naming (`test_flow_*.py`).

**Layered fixture stack**: Three parallel fixtures, each spawning its own subprocess with its own port and `tmp_path` and `THE_ONE_DEV_MODE=true`. "Layered" refers to setup state baked into each, not shared subprocess:
- `app_clean`: empty DB, app running. Used by first-start / provider-setup test.
- `app_with_provider`: DB pre-seeded (via API call to the just-spawned subprocess) with a `mock` provider. Used by agent-creation test.
- `app_with_agent`: DB pre-seeded with mock provider + agent (via API). Used by chat test.

Provider-setup test uses the `mock` type — exercises the same UI and provider-CRUD code path the real types use, just with deterministic responses. Pre-seeding done via API calls (HTTP) rather than direct DB writes — exercises the real code path and is robust to schema changes. No api_key required for `mock` type, so encryption-key persistence is not exercised in browser tests (covered separately by unit tests).
- Rationale: Each flow test focuses on the UI under test, not the prerequisite setup. `app_with_agent` tests should not re-test provider-setup UI.
- Trade-off: Three fixtures to maintain, three subprocess startups per flow run. Worth it for test clarity and isolation.

### Prerequisites

- [x] M03 complete and on `main` (provider management exists; needed for setup flow)
- [x] Pytest and the existing test suite passing on `main` — baseline at flight start: **336 passed, 8 deselected** (`pytest tests/ --tb=short -q`). Re-run at flight start; if count differs, investigate before proceeding (M03 debrief flagged stale prerequisite numbers as a recurring failure mode)
- [x] No port conflicts on the random-port range used by test fixtures (check `lsof -i :8484` and the ephemeral range typically used by `socket.getsockname` after `bind(('', 0))`)
- [x] Linux browser dependencies installable in the dev environment (`playwright install chromium` requires apt packages on Linux — Chromium-only is sufficient for F1; firefox/webkit deferred)
- [x] Concourse instance reachable from dev machine (only required for CI integration leg)

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified *(re-run `pytest tests/ --tb=short -q` at flight start; expect 336 passed, 8 deselected)*
- [x] Validation approach defined
- [x] Legs defined (tentative; planned one-at-a-time during execution)

---

## In-Flight

### Technical Approach

The flight introduces Playwright as a dev dependency and a `mock` provider type as production code, then builds out the test fixture stack and three baseline flow tests. The final leg attempts CI integration with a local-only fallback.

Test infrastructure lives under `tests/browser/`:

```
tests/browser/
├── conftest.py                       # Browser fixtures: app subprocess, page, seeders
├── seeders.py                        # API-based DB seeders for app_with_provider / app_with_agent
├── test_flow_provider_setup.py
├── test_flow_agent_crud.py
└── test_flow_chat.py
```

Mock provider lives in production code paths (it is not a test fixture):

```
the_one/llm/mock.py                   # MockProvider class
the_one/llm/registry.py               # registry update (add "mock")
the_one/agent/factory.py              # _PROVIDER_TYPE_MAP update
the_one/db/models.py                  # provider type enum update
the_one/interfaces/web/api.py         # type-list filter (hide mock when DEV_MODE off), test/discovery branches
the_one/config.py                     # add THE_ONE_DEV_MODE setting
```

Each browser test follows the same shape:
1. Fixture spawns app subprocess with `THE_ONE_DEV_MODE=true`, isolated `THE_ONE_DATA_DIR`, random port; polls `/api/info` until ready; yields `(page, base_url)` to the test
2. Test navigates to area, performs UI actions, asserts on DOM state
3. Implicit await on Playwright's auto-wait — no explicit `time.sleep`
4. WebSocket interactions wait on the corresponding DOM update (e.g., `.message-assistant` content rendered), not on the WS event itself
5. Browser navigates to `http://127.0.0.1:{port}` (not `localhost`) to avoid IPv6 first-attempt delay on WSL2

**Selector strategy**: The current UI has very few `id` and zero `data-testid` attributes — tests will need to use class selectors (`.area-{id}`, `.admin-provider-card`, etc.). Each flow leg includes a small `data-testid` pass on the elements its test depends on (~3-5 attributes per leg) so the tests survive the F2/F3 redesign without re-selectoring. Without this, the regression net dissolves the moment F2 starts.

### Checkpoints

- [x] Playwright installed and `pytest -m browser` runs an empty selection cleanly
- [x] Mock provider passes its own unit tests; can be created via `POST /api/providers` with `THE_ONE_DEV_MODE=true`; rejected when `THE_ONE_DEV_MODE` unset
- [x] App subprocess fixture starts and stops the app reliably across 5+ consecutive runs (with wait-for-ready loop on `/api/info`)
- [x] All three flow tests pass against the current UI
- [x] Tests fail predictably when the underlying flow is broken (manual verification: break a `data-testid` value or remove a button, confirm the right test fails with a useful error)
- [x] CI integration either passes in Concourse OR is documented as deferred with a clear local-only run path

### Adaptation Criteria

**Divert if**:
- Playwright Python binding cannot be made to work in WSL2 (the dev environment) — fall back to JS binding and revisit toolchain unification later
- Mock provider's tool-call schema diverges from what real providers emit such that the agent loop behaves differently — pivot to making `MockProvider` mimic the real provider's tool-call format more closely
- The random-port subprocess fixture proves flaky (e.g., race conditions on app startup despite the wait-for-ready loop) — switch to a single shared subprocess with strict between-test cleanup

**Acceptable variations**:
- `MockProvider` response configuration mechanism (provider config metadata field vs separate scripted-response store) — pick whatever feels cleanest during implementation
- Fixture parameter names — adjust for clarity during implementation
- Splitting `seeders.py` further if it grows past ~150 LOC
- Adding more `data-testid` attributes than the suggested 3-5 per leg if the test demands it

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `01-scaffold-playwright` — Add `playwright` to dev deps, run `playwright install chromium`, add `@pytest.mark.browser` to the `markers` list AND extend `addopts` to `-m "not live and not browser"` in `pyproject.toml`, create `tests/browser/` skeleton with a smoke test that opens the app and asserts the page title
- [x] `02-mock-provider` — Implement `MockProvider`, register in registry `loaders` dict and `_PROVIDER_TYPE_MAP`, add to provider type enum, add `THE_ONE_DEV_MODE` setting, add `GET /api/providers/types` endpoint, gate UI dropdown via fetch + backend creation/update endpoints. Unit tests cover both the gating (POST/PUT rejected when DEV_MODE off; types endpoint omits `mock` when off) AND the provider behavior (mock returns scripted text and tool-calls correctly)
- [x] `03-app-fixture` — Per-test app subprocess fixture: random free port via `socket.bind(('', 0))`, isolated `tmp_path` data_dir, `THE_ONE_DEV_MODE=true`, wait-for-ready loop polling `/api/info`, SIGTERM teardown. Validate with the leg-01 smoke test
- [x] `04-seeders` — API-based seeders for `app_with_provider` and `app_with_agent` fixtures, exercising the real `POST /api/providers` and `POST /api/agents` paths against the just-spawned subprocess
- [x] `05-flow-test-provider-setup` — Browser test for first-start provider configuration: empty DB → setup banner appears → add `mock` provider → Test Connection succeeds → mock models discovered → save → banner disappears. Add `data-testid` attributes to load-bearing elements (~3-5)
- [x] `06-flow-test-agent-crud` — Browser test for Studio agent CRUD: open Studio with seeded mock provider → create new agent with provider/model dropdown selection → save → edit → delete. Add `data-testid` attributes (~3-5)
- [x] `07-flow-test-chat` — Browser test for Chat flow: open Chat with seeded mock agent → send message → assert assistant response renders (mock returns deterministic content) → assert WebSocket events update the UI correctly. Add `data-testid` attributes (~3-5)
- [x] `08-ci-integration` — Time-boxed: replace `python:3.11-slim` with `mcr.microsoft.com/playwright/python` in the existing Concourse `test` task; tests run inside the test container (NOT against the deployed instance — would mutate prod data; per-test fixtures handle data-dir isolation via `tmp_path`). If budget exceeded, document local-only run path and file follow-up; either way, README/CLAUDE.md updated with the run command. Closes with a verify-the-tests-fail-when-broken sanity check (intentionally break a `data-testid`, confirm correct test fails with useful error, revert)

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Code merged
- [x] All existing tests still passing (`pytest tests/`) — count grew by mock-provider unit tests; capture the new baseline
- [x] All new browser tests passing locally (`pytest -m browser tests/browser/`)
- [x] Mock provider documented:
  - [x] `CLAUDE.md` — note the `mock` provider type and `THE_ONE_DEV_MODE` env var
  - [x] `the_one/agents.md` — add `mock` to the provider type extension checklist (M03 debrief item)
- [x] Browser testing documented:
  - [x] `CLAUDE.md` — Testing section updated with browser test marker and run command
  - [ ] `README.md` — note Playwright requirement and `playwright install chromium` step in dev setup
  - [x] `tests/browser/conftest.py` — top-of-file docstring documenting fixture architecture for future authors
- [x] CI status documented (passing in Concourse OR deferred with clear follow-up)
- [x] Hand-off notes for F2 captured in flight log: snapshot strategy decision (deferred from F1), `data-testid` coverage map (which elements have testids), known gap that visual regression net does not exist between F1-landing and F2-mid-flight

### Verification

- Run `pytest tests/` — passes with no new failures (browser tests excluded by default marker filter)
- Run `pytest -m browser tests/browser/` locally — three flow tests pass
- Run with `THE_ONE_DEV_MODE=true the-one serve` and confirm `mock` appears in the Admin provider-type dropdown; without the env var, `mock` is hidden and `POST /api/providers` with type `mock` returns 400
- Manually break a flow (e.g., change a `data-testid` value) and confirm the corresponding flow test fails with a clear error
- Run `playwright install chromium` from a fresh checkout and confirm browser test suite runs without further setup
