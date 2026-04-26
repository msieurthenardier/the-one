# Leg: 08-ci-integration

**Status**: completed
**Flight**: [Browser Test Foundation](../flight.md)

## Objective

Wire browser tests into the Concourse pipeline by replacing `python:3.11-slim` with `mcr.microsoft.com/playwright/python` in the existing `test` task and adding a second pytest invocation for browser tests. Update project documentation (CLAUDE.md, agents.md) to reflect the new browser test marker, the `mock` provider type, the `THE_ONE_DEV_MODE` env var, and the provider-type extension checklist (per leg 02 action item). Run a verify-tests-fail-when-broken sanity check. Time-boxed: if Concourse integration proves harder than expected, fall back to documented local-only run path with a follow-up.

## Context

- This is the **last autonomous leg** of Flight 01. After it lands, the flight transitions to flight-level code review and a single bundled commit (per agentic-workflow protocol).
- Per the flight design (`flight.md` "CI integration time-boxed to one leg, local-only fallback"): replace the test container's image, add browser tests to the existing test task, NOT a post-deploy task (would mutate prod data via the live `the_one_data` volume).
- **Current pipeline state** (`ci/pipeline.yml:80-100`): `test` task uses `image_resource: python:3.11-slim` (line 99) wrapped in a `docker:cli` container that runs `docker run` against the host Docker socket. Test command is `pip install --no-cache-dir '.[dev]' -q && python -m pytest tests/ --tb=short -q`.
- **Image change**: `mcr.microsoft.com/playwright/python:v1.58.0-jammy` is the dev environment's Playwright version (1.58.0 confirmed via `pip show playwright` in leg 01). Pin to this exact tag for reproducibility. Image is ~6 GB uncompressed (per architect's M04 mission validation); first pull on a Concourse worker takes 5-10 minutes, subsequent runs use the worker's image cache.
- **Test commands** in the new image:
  - The Playwright Python image has Python 3.11+ and Chromium pre-installed
  - `pip install --no-cache-dir '.[dev]' -q` installs the project (and its `playwright` package) — but Chromium is already cached at `/ms-playwright`, so `playwright install` would be a no-op
  - Run two pytest invocations: default (existing) + browser
  - Both must pass; `sh -exc` halts on first failure
- **Documentation updates owed**:
  - **CLAUDE.md**: browser test command in Commands section, browser tests in Testing section, mention of `mock` provider type and `THE_ONE_DEV_MODE`, mention of `__MASKED__` sentinel (M03 debrief immediate item)
  - **the_one/agents.md**: browser-test fixture conventions (new section), provider type extension checklist with SQLite CHECK constraint as the 6th layer (per leg 02 action item)
  - No README exists in this project
- **Sanity check**: per the flight checkpoints, intentionally break a `data-testid` value and confirm the right test fails with a useful error. Then revert. This validates the regression net actually catches regressions.
- **Action items from this flight** to fold into agents.md or note in flight log for debrief:
  - Schema CHECK constraint as 6th layer of provider-type extension (leg 02)
  - admin.js base_url validation bug fix (leg 05)
  - Browser test fixture conventions (legs 03/04)
  - Mock provider as a dev-mode-gated production type (legs 02-04)

## Inputs

- Branch `flight/01-browser-test-foundation`, legs 01-07 landed (uncommitted)
- `ci/pipeline.yml` exists with `test` task at line 80-100
- `CLAUDE.md` Testing section at line 105+; Commands section at line 22-25
- `the_one/agents.md` exists (architecture reference, ~50+ LOC seen)
- Test baseline: 350 passed, 16 deselected; 8 browser tests passing

## Outputs

- `ci/pipeline.yml` — `test` task updated:
  - Image changed from `python:3.11-slim` to `mcr.microsoft.com/playwright/python:v1.58.0-jammy`
  - Test command extended to also run `pytest -m browser tests/browser/ --tb=short -q`
- `CLAUDE.md` — additions:
  - Browser test command in the Commands section
  - Browser test marker explanation in the Testing section
  - `mock` provider type + `THE_ONE_DEV_MODE` env var note
  - `__MASKED__` sentinel mention (in the provider config / encryption context)
- `the_one/agents.md` — additions:
  - Browser test fixture conventions section (new top-level section near the testing/conventions area)
  - Provider type extension checklist (new section, includes 6 layers: Pydantic Literal, `_PROVIDER_TYPE_MAP`, registry loaders, API gating, frontend dropdown, AND the SQLite CHECK constraint added in v6 migration)
- Sanity check evidence: a flight log entry showing the break/revert was performed and the expected test failed
- F1 final test counts captured: full pytest, browser pytest, both clean

## Acceptance Criteria

### Pipeline change

- [x] `ci/pipeline.yml` `test` task `image_resource.source.repository` is exactly `mcr.microsoft.com/playwright/python` with tag exactly `v1.58.0-jammy` (no "or equivalent" — pinned to match the dev env's installed `playwright==1.58.0`)
- [x] `ci/pipeline.yml` `test` task command runs both `python -m pytest tests/ --tb=short -q` AND `python -m pytest -m browser tests/browser/ --tb=short -q` in sequence; chained with `&&` inside the inner `sh -c` so any failure halts
- [x] `THE_ONE_DEV_MODE=true` is set as a Concourse param AND propagated to the inner test container via `docker run -e THE_ONE_DEV_MODE="${THE_ONE_DEV_MODE}"`
- [x] **Only** the test task at `ci/pipeline.yml:82-100` is modified. The autopilot task at `ci/pipeline.yml:32-79` (which uses `python:3.11-alpine` — a different Python image) MUST NOT be touched. Verify with `git diff ci/pipeline.yml` showing changes scoped to the test task only.

### Documentation: CLAUDE.md

- [x] Commands section includes `pytest -m browser tests/browser/` (or equivalent — matches the existing AIAT pattern at line 25)
- [x] Testing section explains the `browser` marker (parallel to existing `live` marker), notes the `addopts` exclusion, and points to `tests/browser/conftest.py` for fixture documentation
- [x] Architecture or Configuration section mentions the `mock` provider type, gated by `THE_ONE_DEV_MODE=true`
- [x] Provider/Encryption context mentions the `__MASKED__` sentinel used by the provider edit form (M03 debrief immediate item)

### Documentation: the_one/agents.md

- [x] New section: "Browser test fixtures" — documents `app_clean`, `app_with_provider`, `app_with_agent` fixtures, the `mock` provider type's role in tests, and the `tests/browser/` layout
- [x] New section: "Provider type extension checklist" — six-layer audit list:
  1. Pydantic `Literal` in `db/models.py` `LLMProviderConfig.type`
  2. `_PROVIDER_TYPE_MAP` in `agent/factory.py`
  3. Registry `loaders` dict in `llm/registry.py`
  4. SQLite `CHECK` constraint in `db/schema.py` (requires a migration when extended)
  5. API gating / branches in `interfaces/web/api.py` (`create_provider`, `update_provider`, `test_provider`, `list_provider_models`, `GET /providers/types`)
  6. Frontend handling in `interfaces/web/static/js/areas/admin.js` (`PROVIDER_TYPES` source, `TYPE_DEFAULTS`, `TYPE_BADGE_COLORS`)

### Sanity check (verify tests fail on regression)

- [x] Temporarily change one `data-testid` value (e.g., `setup-banner` → `setup-banner-broken` in `chat.js`) AND run the corresponding flow test; confirm `test_first_start_provider_setup_flow` fails with a clear "locator did not find element" or timeout error
- [x] Revert the change immediately
- [x] Re-run the test to confirm it passes again (no lingering damage)
- [x] Document the break/revert evidence in flight log

### Suite-level

- [x] Default `pytest tests/` still passes: 350 passed, 16 deselected
- [x] `pytest -m browser tests/browser/` still passes: 8 passed
- [x] `ruff check` and `ruff format --check` clean for any source files modified by this leg (this leg touches only YAML, Markdown, and possibly chat.js for the sanity-check break-and-revert — no Python source changes expected, so the AC is trivially satisfied)
- [x] **CI integration verification status documented**: either the pipeline is verified working in Concourse (operator runs `fly` to set the pipeline and triggers the `test` job) OR the leg notes that operator verification is pending, with a concrete follow-up step

## Verification Steps

1. **Pipeline diff sanity**: `git diff ci/pipeline.yml` shows ONLY the test-task image and command lines changed; no other jobs touched
2. **Doc completeness**: `grep -n "browser\|mock\|THE_ONE_DEV_MODE\|__MASKED__" CLAUDE.md` returns matches in expected sections
3. **Agents.md completeness**: `grep -n "Provider type extension\|Browser test fixtures" the_one/agents.md` returns matches
4. **Sanity check executed and documented**: Flight log shows the intentional break, the failing test output (truncated), and the revert
5. **All tests pass post-leg**: `pytest tests/ --tb=short -q --timeout=60` → 350/16 deselected; `pytest -m browser tests/browser/ -v --timeout=60` → 8 passed
6. **Local-only run instructions verified** (manual): a fresh dev follows the CLAUDE.md instructions and gets to running browser tests successfully

## Implementation Guidance

### 1. Update `ci/pipeline.yml` test task

Find the `test` task block at lines 82-100. Modify ONLY the `image_resource` and the test command. Leave everything else (params, source mounts, etc.) untouched.

```yaml
- task: test
  privileged: true
  config:
    platform: linux
    image_resource:
      type: registry-image
      source:
        repository: mcr.microsoft.com/playwright/python
        tag: v1.58.0-jammy
    params:
      DOCKER_HOST: ((docker-host))
      WORKSPACE_PATH: ((workspace-path))
      THE_ONE_DEV_MODE: "true"
    run:
      path: sh
      args:
        - -exc
        - |
          docker run --rm \
            -e THE_ONE_DEV_MODE="${THE_ONE_DEV_MODE}" \
            -v "${WORKSPACE_PATH}:/src:ro" \
            mcr.microsoft.com/playwright/python:v1.58.0-jammy \
            sh -c "cp -r /src /work && cd /work && pip install --no-cache-dir '.[dev]' -q && python -m pytest tests/ --tb=short -q && python -m pytest -m browser tests/browser/ --tb=short -q"
```

> **Why two pytest invocations**: The default `pytest tests/` invocation excludes `browser` tests via `addopts`. To also run them, a separate `pytest -m browser tests/browser/` invocation is needed. Both run in sequence via `&&` — first failure halts.

> **Why pin the image tag** (`v1.58.0-jammy`): Matches the dev env's installed Playwright version (1.58.0). Untagged `latest` would risk version drift between dev and CI.

> **Image size warning**: First pull on a fresh Concourse worker is ~6 GB uncompressed. Subsequent runs use cache. If this becomes a problem, the worker can be pre-warmed or the image can be migrated to a smaller custom one.

### 2. Update `CLAUDE.md`

**Commands section** (around line 22-25): Add browser test command after the `pytest -m live` line:

```markdown
pytest -m live tests/test_aiat.py                   # AIAT (needs running instance)
pytest -m browser tests/browser/                    # Browser tests (needs THE_ONE_DEV_MODE=true)
```

**Testing section** (around line 105): Extend after the AIAT subsection:

```markdown
**Browser tests** are end-to-end browser-driven tests using Playwright. They are excluded from default runs via `addopts = "-m 'not live and not browser'"` in `pyproject.toml`.

- **`@pytest.mark.browser`** marks browser tests — all live in `tests/browser/`
- Run browser tests: `pytest -m browser tests/browser/`
- Each test spawns its own app subprocess on a random port with an isolated `tmp_path` data_dir; teardown via SIGTERM
- Mock LLM responses are deterministic via the `mock` provider type (see below)
- See `tests/browser/conftest.py` for fixture documentation
```

**Configuration section**: CLAUDE.md has Configuration at line 74. Add the dev mode + mock provider note as a new subsection immediately after the existing Configuration paragraph (the `mock` type is a Configuration concern — it's gated by an env var; the architectural plumbing is already covered in the Architecture section's LLM layer discussion):

```markdown
### Dev mode and the mock provider

When `THE_ONE_DEV_MODE=true` is set, a fifth provider type `mock` becomes available alongside `ollama`, `openai-compatible`, `openai`, and `anthropic`. The mock provider returns deterministic scripted responses sourced from its `LLMProviderConfig.config["response"]` field — defaults to `"Mock response from the mock provider."` if no `response` key is set. Used by browser tests for deterministic chat flows; also useful for offline dev work and demos.

- Backend rejects mock-typed creates/updates with HTTP 400 when dev mode is off
- UI dropdown filters out `mock` when dev mode is off (driven by `GET /api/providers/types`)
- Existing mock providers continue to render correctly in the admin UI even after dev mode is later disabled (the `TYPE_DEFAULTS`/`TYPE_BADGE_COLORS` entries are unconditional)
```

**`__MASKED__` sentinel** (M03 debrief immediate item) — the existing CLAUDE.md mentions encryption only briefly at line 52 (`Encryption (the_one/encryption.py)`). Add a new subsection immediately AFTER the existing encryption paragraph:

```markdown
### `__MASKED__` sentinel for API key updates

The provider edit form sends the literal string `__MASKED__` as the `api_key` field when the user has not modified it. The backend (`update_provider` in `interfaces/web/api.py`) detects this sentinel and preserves the existing stored key rather than overwriting it with the masked display value. Anyone touching the provider edit form needs to know this contract.
```

### 3. Update `the_one/agents.md`

**Add a new section** (place toward the end, near the testing/conventions area):

```markdown
## Browser test fixtures

Browser tests live in `tests/browser/` (with fixtures in `tests/browser/conftest.py` and seeders in `tests/browser/seeders.py`) and use Playwright (Python binding) to drive a real Chromium session against a per-test app subprocess. Three layered fixtures:

| Fixture | Setup | Use for |
|---------|-------|---------|
| `app_clean` | Fresh subprocess + empty DB + `THE_ONE_DEV_MODE=true` | First-start / setup-flow tests |
| `app_with_provider` | + 1 mock provider seeded via API | Agent CRUD tests |
| `app_with_agent` | + 1 agent referencing the mock provider | Chat tests |

Each test gets its own subprocess on a random port (via `socket.bind(('', 0))`) with an isolated `tmp_path` data_dir. Teardown sends SIGTERM, escalates to SIGKILL after 10s if needed. Browser navigates to `http://127.0.0.1:{port}` (not `localhost`) to avoid IPv6 first-attempt delay on WSL2.

**Playwright fixtures (`playwright_instance`, `browser`) are module-scoped, NOT session-scoped.** Originally session-scoped during F1 leg 03 design; switched to module scope during implementation because session scope kept the asyncio loop alive across modules and broke the leg-01 standalone smoke test (`test_smoke.py` creates its own `sync_playwright()` context). Module scope still amortizes Chromium across tests within the same module while keeping the standalone smoke test green.

The `mock` provider type (production code, dev-mode-gated) provides deterministic LLM responses without external services — see "Provider type extension checklist" below for the full type wiring.

Tests rely on `data-testid` attributes on load-bearing UI elements rather than CSS classes, so the tests survive UI redesigns. Each flow leg adds 3-5 testids on a budget.
```

**Add a new section: Provider type extension checklist**

```markdown
## Provider type extension checklist

To add a new LLM provider type, six layers must coordinate. Missing any one of them causes either silent rejection (validation) or runtime errors.

> **History**: The M04 flight that added the `mock` provider type initially missed the SQLite CHECK constraint (#4 below) during state-machine reachability audit. First test run failed with `IntegrityError: CHECK constraint failed`, requiring schema migration v6. The checklist below is the post-incident enumeration.

1. **Pydantic `Literal`** — `db/models.py` `LLMProviderConfig.type`. Add the new value to the `Literal[...]` tuple. Without this, `model_validate` rejects.
2. **`_PROVIDER_TYPE_MAP`** — `agent/factory.py`. Add `"<type>": "<registry-name>"`. Without this, `AgentFactory.create()` raises `ValueError` for agents pointing at the new type.
3. **Registry `loaders` dict** — `llm/registry.py:_try_load_builtin`. Add `"<type>": lambda: __import__("the_one.llm.<provider_module>", fromlist=["_"])`. Without this, `get_provider("<type>")` raises a misleading `ImportError("requires extra dependencies")`.
4. **SQLite `CHECK` constraint** — `db/schema.py` (table definition AND migration). The `llm_providers` table's `CHECK (type IN (...))` clause hard-codes allowed values. Adding a new type requires a schema migration (see v6 for the pattern: `PRAGMA foreign_keys=OFF` + table rebuild). Without this, `INSERT` fails with `IntegrityError: CHECK constraint failed`.
5. **API gating / branches** — `interfaces/web/api.py`:
   - `create_provider` and `update_provider` — add type-specific gating if the new type has a precondition (e.g., dev-mode flag for `mock`)
   - `test_provider` — add a branch returning health/test result for the new type
   - `list_provider_models` — add a branch returning the model list (may query an upstream API or read from `LLMProviderConfig.config`)
   - `GET /api/providers/types` — include or exclude based on any feature gating
6. **Frontend handling** — `interfaces/web/static/js/areas/admin.js`:
   - `PROVIDER_TYPES` is fetched from `/api/providers/types` (post-leg-02), so the type appears in the dropdown when allowed by the API
   - Add `TYPE_DEFAULTS["<type>"] = { base_url, showBaseUrl, showApiKey }` (unconditional — needed for editing existing providers even if the type is later hidden from creation)
   - Add `TYPE_BADGE_COLORS["<type>"]` for the type badge in the provider list

When all six layers are aligned, an integration test posting a provider with the new type round-trips successfully through DB persistence, factory resolution, and UI rendering.
```

### 4. Sanity check (break-and-revert)

Pick one `data-testid` to break — `setup-banner` is a good candidate (small change, clear failure signal). **Order matters: capture failure output BEFORE reverting** (the revert leaves no permanent artifact, so the only evidence the sanity check happened is the captured output in the flight log).

```bash
# 1. Note the current state — uncommitted leg changes are expected; sanity check
#    adds one more temporary edit on top.

# 2. Break the testid in chat.js — temporarily change `setup-banner` → `setup-banner-broken`
# (use Edit tool to make the surgical change at chat.js:218)

# 3. Run the affected test with FIXED flags so failure is reproducible.
#    Use exactly: `pytest -m browser tests/browser/test_flow_provider_setup.py -v --timeout=60`
#    No --cov, no other flags.

# 4. CAPTURE the failing output to a file or scratch buffer. Save the relevant
#    8-15 lines (the locator timeout error + the failing assertion line) BEFORE
#    moving on. This is the only evidence the sanity check ran.

# 5. Revert chat.js to its leg-05 state (use Edit tool)

# 6. Re-run to confirm green:
#    `pytest -m browser tests/browser/test_flow_provider_setup.py -v --timeout=60`

# 7. Quote the captured failure output (8-15 lines) in the flight log under
#    leg 08 in a "Sanity check" subsection.
```

The captured failure output is part of the leg's deliverable; without it, the AC ("Sanity check executed and documented") is not met.

### 5. Final test runs

```bash
pytest tests/ --tb=short -q --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
ruff check the_one/ tests/
```

### 6. Operator verification of CI (out-of-session, expected default)

The leg lands WITHOUT the operator running `fly` to verify the Concourse pipeline change in production — this is the expected default for autonomous execution. The flight log MUST flag this as a follow-up. The operator's verification (out of session, post-flight):

```bash
fly -t self set-pipeline -p the-one -c ci/pipeline.yml
fly -t self trigger-job -j the-one/deploy
fly -t self watch -j the-one/deploy
```

Watch the test task; confirm both pytest invocations pass (default + browser). Document the result in this flight's debrief.

> **Optional pre-commit smoke check** for the implementing developer (~30 seconds): `docker pull mcr.microsoft.com/playwright/python:v1.58.0-jammy` from a host with Docker available. Confirms the tag exists in the Microsoft registry and is pullable. If the pull fails, fix the tag in pipeline.yml before completing the leg.

## Edge Cases

- **Concourse worker image cache**: First run pulls 6 GB. If the worker has limited disk, the pull may fail with "no space left on device". Mitigation: ensure worker has at least 20 GB free before triggering. Document in the leg's "operator verification" follow-up.

- **Playwright Python image entrypoint**: The image's default entrypoint may not match what `docker run ... sh -c "..."` expects. The `mcr.microsoft.com/playwright/python` image's Dockerfile sets `WORKDIR /` and no entrypoint, so `sh -c "..."` works. Verified via image documentation; trust but verify on first CI run.

- **`-m browser` invocation when no browser tests exist**: `pytest -m browser tests/browser/` returns exit code 5 ("no tests collected") when zero tests match. Currently we have 8 browser tests, so this isn't a concern — but if the suite ever becomes empty, the pipeline would fail mysteriously. Acceptable risk for now.

- **`THE_ONE_DEV_MODE` env var propagation**: The Concourse `params:` block sets it for the outer `sh` script, then it's passed via `docker run -e THE_ONE_DEV_MODE="${THE_ONE_DEV_MODE}"` to the inner test container. Without the explicit `-e`, the inner container wouldn't see it. This is a common Docker gotcha; the leg's pipeline.yml example includes it.

- **Browser test data dir isolation**: Each test uses `tmp_path` (a pytest builtin) which lives under the test container's filesystem. No interaction with the host's `~/.the-one/` or the deployed app's data volume. The `app_clean` fixture overrides `THE_ONE_DATA_DIR` per-test.

- **Documentation drift**: If a future leg adds a 6th provider type without consulting the agents.md checklist, the bug pattern from leg 02 will repeat. The checklist itself is documentation-rot-prone. F2 onward should treat this as a tested invariant — e.g., a unit test that asserts `len(_PROVIDER_TYPE_MAP) == len(LLMProviderConfig.__pydantic_fields__["type"].annotation.__args__)`. Out of scope for this leg.

- **Sanity check leaves the repo in a known-good state**: After break-and-revert, the working tree should have only the leg's intended changes. Run `git diff --stat` to verify only expected files differ.

- **No effect on existing AIAT or unit-test runs in CI**: The unit-test invocation (`pytest tests/`) is unchanged; AIAT (`live` marker) is unchanged. Only the test task's IMAGE changes (now Playwright-Python instead of generic Python). The slim Python image gave us ~50MB pulls; the new image is 100x larger but only the first run pays the full cost.

## State-Machine Reachability Audit

This leg introduces:
- **CI pipeline state**: image change. No new states; pipeline still progresses test → build-and-deploy → health-check.
- No production code changes.
- Documentation additions are not state.

Lower layers verified:
- Concourse worker has Docker socket mount (line 91-92 of pipeline.yml params): the test task already does `docker run` from within the docker:cli outer container. The pattern is unchanged.
- Image registry availability: `mcr.microsoft.com` is Microsoft's public registry, no auth required for the playwright/python image. ✓

No existing tests pin behavior this leg breaks. ✓ Pass.

## Cache Freshness Contract

This leg introduces no new caches. CI image cache is managed by Concourse worker, not by application code. ✓ Pass.

## Files Affected

- `ci/pipeline.yml` — test task image and command updated (~5 lines)
- `CLAUDE.md` — additions (~30-40 lines: command, testing section extension, dev mode + mock provider, `__MASKED__` sentinel)
- `the_one/agents.md` — additions (~80-100 lines: browser test fixtures section, provider type extension checklist)
- (no source code changes)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing: `pytest tests/` shows 350 passed, 16 deselected; `pytest -m browser tests/browser/` shows 8 passed
- [x] Sanity check (break-and-revert) executed and documented in flight log with failure output
- [x] Operator-verification status of CI pipeline documented (verified OR flagged as follow-up)
- [x] `ruff check` clean
- [x] Update flight-log.md with leg progress entry (status, what was done, sanity check evidence, CI verification status, any anomalies)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off this leg in flight.md (happens at flight-level commit time per agentic-workflow protocol)
- [x] Do NOT commit (flight-level review and commit happen NEXT — this leg is the last autonomous one)
- [x] Signal `[HANDOFF:review-needed]`
