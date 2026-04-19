# Flight: Test Infrastructure & CI Hardening

**Status**: in-flight
**Mission**: [Structural Foundation](../../mission.md)

## Contributing to Criteria

- [ ] Core modules (agent loop, tool registry, LLM registry) have unit tests that run in isolation; integration tests validate the agent step cycle end-to-end
- [ ] The Concourse pipeline runs the full test suite as a hard gate before deployment (no swallowed failures)

---

## Pre-Flight

### Objective

Add comprehensive unit tests for all core modules (agent loop, tool registry, LLM registry, config, factory, store, behaviors, builtins), create a mock LLM provider for deterministic agent loop testing, convert the standalone IAAT script to pytest-based AIAT (AI Acceptance Tests), and harden the Concourse pipeline by removing `|| true`, de-hardcoding paths, and DRYing up duplicated docker run blocks.

### Open Questions

- [x] Test scope → all modules, including pre-existing ones (ToolRegistry, LLM registry)
- [x] Agent loop testing → mock-based with a FakeLLM provider, testing iteration/branching deterministically
- [x] IAAT conversion → rename to AIAT, convert to pytest, keep as integration tests that require a live agent
- [x] CI duplication → DRY up the docker run env blocks into a shared script or env file

### Design Decisions

**FakeLLM for agent loop tests**: Create a minimal `FakeLLM(LLMProvider)` that returns pre-scripted `Message` responses. No mock library — just a class with a list of responses. This is consistent with the project's "no frameworks" philosophy and makes tests self-documenting.
- Rationale: The agent loop is the most critical code and is currently only tested by live AIAT. Deterministic tests for iteration limits, tool execution flow, direct action bypass, continue signal, and error handling are high-value.
- Trade-off: Tests don't validate real LLM wire format — that's AIAT's job.

**AIAT stays as integration tests with a `live` marker**: Convert `tests/iaat.py` to `tests/test_aiat.py` using pytest conventions. Mark all AIAT tests with `@pytest.mark.live` so they're skipped by default (`pytest tests/`) and run explicitly (`pytest -m live`). This lets the CI test step run unit tests as a hard gate without needing a live agent.
- Rationale: AIAT tests require a running agent with an LLM. They can't run in CI's test step (no Docker, no Ollama). Keeping them as pytest tests with a marker gives a unified test runner.
- Trade-off: AIAT tests aren't in the CI gate — they're run manually or by a separate job.

**Shared deploy script for CI**: Extract the duplicated docker run env blocks (deploy, rollback, auto-rollback) into a `ci/deploy.sh` script parameterized by image tag. All three jobs call the same script.
- Rationale: The current pipeline has the same 15-line env var block duplicated 3 times. A change to one must be manually replicated. DRYing up reduces maintenance risk.
- Trade-off: Slightly more indirection in the pipeline — you need to read `deploy.sh` to understand what env vars are set.

**Concourse path variable**: Replace hardcoded `/home/cprch/projects/the-one` with a `((workspace-path))` Concourse variable, injected into tasks via `params: { WORKSPACE_PATH: ((workspace-path)) }` and referenced as `$WORKSPACE_PATH` in shell scripts. The `((...))` syntax is interpolated at `fly set-pipeline` time into the task params, then available as an env var at runtime.
- Rationale: 5 occurrences of a hardcoded absolute path. If the project moves, the pipeline breaks.
- Trade-off: One more secret to manage.

**AIAT uses httpx instead of requests**: The original `iaat.py` uses `requests`, which is not in project dependencies. The AIAT conversion switches to `httpx` (already a core dependency) to avoid adding another dep.
- Rationale: Zero new dependencies. httpx API is similar to requests.
- Trade-off: None.

**Known bug: auto-rollback missing `--network`**: The current auto-rollback block in `pipeline.yml` is missing `--network concourse-local_default`, which is present in deploy and rollback. The `deploy.sh` extraction will fix this by applying the same docker run command consistently.
- Rationale: Bug found during design review.

### Prerequisites

- [x] Flight 2 (Core Module Isolation) completed — all modules to test exist
- [x] `pytest>=8.0` in dev dependencies
- [x] `ruff>=0.6` in dev dependencies
- [ ] `pytest-asyncio` added to dev dependencies (needed for async agent loop tests)

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Two parallel concerns: **testing** and **CI hardening**.

**Testing** builds bottom-up — test foundational modules first, then modules that depend on them, then the agent loop (which depends on everything). Each test file mirrors the module it tests (`test_behaviors.py` for `behaviors.py`, etc.). Tests are pure-logic or filesystem-only — no LLM, no Docker, no network.

A `FakeLLM` provider enables deterministic agent loop tests. It takes a list of pre-scripted `Message` responses and returns them in sequence. Combined with simple stub tools, this lets us test all branching paths in `Agent.step()`.

A `conftest.py` provides shared fixtures: `tmp_path` for filesystem tests, `FakeLLM`, and stub tools. `pytest-asyncio` is added to dev dependencies for async test support.

**CI hardening** addresses three issues: tests that can't fail (`|| true`), hardcoded paths, and duplicated docker run blocks. The pipeline changes are mechanical but high-impact — they turn the test step from a decoration into a real gate.

**AIAT conversion** renames `iaat.py` to `test_aiat.py`, restructures as pytest test functions, and adds a `live` marker so they're excluded from default test runs.

### Checkpoints

- [x] `conftest.py` with FakeLLM and test fixtures exists
- [x] Unit tests for `behaviors.py`, `config.py` exist and pass
- [x] Unit tests for `base.py` (ToolRegistry), LLM registry exist and pass
- [x] Unit tests for `store.py`, `builtins.py`, `provider.py` exist and pass
- [ ] Unit tests for `factory.py` exist and pass (uses FakeLLM)
- [ ] Agent loop tests exist and pass (iteration, tool execution, direct actions, continue, errors)
- [ ] AIAT converted to pytest with `live` marker
- [ ] CI pipeline: `|| true` removed, paths de-hardcoded, docker run blocks DRYed
- [ ] All tests pass, lint clean

### Adaptation Criteria

**Divert if**:
- Testing a module reveals a bug in the module itself — fix the bug in the same leg, note it in the flight log

**Acceptable variations**:
- Test count may vary from estimates as edge cases are discovered
- FakeLLM may need additional features (e.g., tracking call count) beyond the minimal design
- AIAT tests may need adjustment if the live agent API has changed since the script was written

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `test-fixtures-and-behaviors` — Create `conftest.py` with FakeLLM, stub tools, and shared fixtures. Write unit tests for `behaviors.py` (extract_tool_calls, match_direct_action) and `config.py` (AgentConfig model, is_tool_enabled, get_system_prompt).
- [x] `test-registries-and-store` — Unit tests for `ToolRegistry` (register, get, schemas, unknown tool), LLM registry (register_provider, get_provider, lazy loading, unknown provider), `FilesystemConfigStore` (CRUD, missing files, invalid JSON), and `BuiltinToolProvider` (tool count, protocol compliance).
- [ ] `test-factory-and-agent-loop` — Unit tests for `AgentFactory` (default agent, named agent, unknown agent, tool filtering) and `Agent.step()` (normal flow, direct action bypass, continue signal, max iterations, tool execution, tool errors, text-embedded tool call extraction).
- [ ] `aiat-conversion` — Rename `tests/iaat.py` to `tests/test_aiat.py`. Convert to pytest functions with `@pytest.mark.live`. Register the `live` marker in `conftest.py` or `pyproject.toml`. Verify AIAT tests are skipped by default and runnable with `pytest -m live`.
- [ ] `ci-pipeline-hardening` — Remove `|| true` from test step. Replace hardcoded `/home/cprch/projects/the-one` with `((workspace-path))`. Extract shared docker run env block into `ci/deploy.sh`. Update deploy, rollback, and auto-rollback jobs to use the script.
- [ ] `verify-integration` — Run full test suite locally, verify CI pipeline syntax with `fly validate-pipeline`, deploy and confirm the test gate actually blocks on failure.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] `pytest tests/ --tb=short -q` passes (unit tests)
- [ ] `ruff check the_one/ tests/` clean
- [ ] CI pipeline valid (`fly validate-pipeline`)
- [ ] Test gate blocks deployment on failure (verified)
- [ ] AIAT tests runnable with `pytest -m live`
- [ ] Documentation updated (CLAUDE.md test commands if needed)

### Verification

The flight is verified when:
- Unit tests cover all core modules and run in <5 seconds with no external dependencies
- The CI test step fails the pipeline when a test fails (no `|| true`)
- The CI pipeline has no hardcoded paths
- Docker run env blocks appear exactly once (in `ci/deploy.sh`)
- AIAT tests run against a live agent via `pytest -m live`
- `pytest tests/` (without `-m live`) runs only unit tests
