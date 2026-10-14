# Leg: runner-core

**Status**: planning
**Flight**: [Prompt evals and baseline](../flight.md)

## Objective
Build the `evals/` package's runner core. It loads declarative scenarios, then drives each run through the real `AgentFactory`, prompt assembly and agent loop in a contained scratch environment. Each run is scored by program checks and recorded durably and resumably. Everything is proven offline with a sequence-scripted provider.

## Context
- Flight design decisions DD1–DD9, DD13, DD18 and DD19 are authoritative; read them in `../flight.md` first. This leg builds those decisions, except what leg 2 owns: statistics (DD10), the gate rules (DD11), token measurement (DD12), fingerprints (DD15) and the full baseline/report layout (DD16). This leg writes only `results.jsonl`, the transcripts and a minimal plain-text summary.
- No product code under `the_one/` changes in this leg. The runner only imports `the_one.*`.
- The operator's real data directory and home must never be touched. That is a hard safety requirement (DD3, DD19).
- The plan token must never appear in any output, file or exception text this package writes (DD4).
- Scenario authoring is leg 3. This leg ships only the minimal scenario files and fixtures its own tests need, under `tests/fixtures/evals/`, not `evals/scenarios/`.

## Inputs
- The flight spec at `bb54636`, plus the planning commits on `flight/01-prompt-evals-baseline`.
- The product modules named in the flight's Citation Audit:
  - `the_one/agent/factory.py::AgentFactory`
  - `the_one/agent/core.py::Agent.step`
  - `the_one/agent/_context.py::TurnContext` / `current_turn`
  - `the_one/notes/tools.py`
  - `the_one/db/repositories.py`: `AgentNoteRepository`, `AgentRuleRepository`, `ToolConfigRepository`, `LLMProviderRepository`, `KnowledgeBaseRepository`, `KBItemRepository`
  - `the_one/knowledge/manager.py::IndexingManager`
  - `the_one/time_zones.py`
  - `the_one/tools/_web_config.py`, `the_one/tools/filesystem.py::FilesystemConfig`, `the_one/tools/execution.py::ExecutionConfig`
  - `the_one/llm/anthropic_plan_provider.py`, `the_one/llm/ollama_provider.py`
  - `the_one/interfaces/cli.py::_run_cli`, the reference for driving an agent: `init_db`, `reconcile_pending_key`, `SQLiteAgentStore`, `AgentFactory(store).create`, and `TurnContext` per step
  - `the_one/config.py::_default_data_dir`

## Outputs
- `evals/__init__.py`, `evals/__main__.py` (the CLI) and the modules below (split as you see fit; these names are suggestions):
  - `evals/scenario.py`: the TOML loader and validation (DD2)
  - `evals/env.py`: start-up order, guards, the scratch data directory and home, environment pinning, the token reader and redactor, lock and sweep (DD3, DD4, DD19)
  - `evals/models.py`: presets, `LLMProviderConfig` rows and effective-value recording (DD4)
  - `evals/fixtures.py`: the local HTTP fixture server and KB fixture indexing (DD7, DD17 KB note)
  - `evals/harness.py`: the per-run agent setup, the clock and zone, the tool-free wrapper and the conversation driving (DD3, DD6, DD8)
  - `evals/checks.py`: the DD13 check vocabulary, except `judge` (registered here as a stub that raises `NotImplementedError`; leg 3 implements it)
  - `evals/scripted.py`: the sequence-scripted provider (DD18)
  - `evals/outcomes.py`: the run outcome classification, backoff, results.jsonl, resume and transcripts (DD5)
- `evals/models.toml`, with the `haiku` and `gpt-oss` presets.
- `tests/test_evals_*.py`: unit tests, offline (no network, no real model, no tiktoken), plus `tests/fixtures/evals/` test scenarios and fixtures.
- `pyproject.toml`: pytest `pythonpath` gains `"."` (DD1).
- `.gitignore`: `evals/runs/` and `evals/.cache/`.

## Acceptance Criteria
- [ ] `python -m evals run --help` prints the run options: `--models`, `--scenarios`, `--scenarios-dir`, `--n`, `--run-dir` / `--resume`, `--plan-token-file`, `--dry-run`.
- [ ] `--dry-run` prints the planned runs (scenario × variant × model) and the count of LLM calls, without building any agent.
- [ ] **Scenario loader (DD2).**
  - It loads TOML scenarios with phrasings × facts expanding to distinct variants (DD9).
  - It rejects an unknown check name, malformed check parameters, seeded notes without `notes_enabled = true`, and a variant count below n, each with a one-line error naming the file and field.
  - `{fixture_base}` is substituted in turn text and check parameters (DD7).
- [ ] **Start-up order (DD3, DD19).** The guard, token read, HOME switch and build happen in that order.
  - The real default data directory is computed once, before `HOME` changes, and every refusal check uses that value.
  - The runner refuses (non-zero exit, one-line message, nothing created) when `--run-dir`'s `data/` equals, contains or lies inside the real default data directory, or when `THE_ONE_DATA_DIR` names such a path.
  - Unit tests cover each refusal, with platformdirs pointed at a temp directory.
- [ ] **Environment pinning (DD4).** The runner refuses to start if any of `THE_ONE_ANTHROPIC_EXTENDED_THINKING`, `THE_ONE_REASONING_EFFORT`, `THE_ONE_OLLAMA_NUM_CTX`, `THE_ONE_STOP` or `THE_ONE_RESPONSE_FORMAT` is set. Each run records the effective provider values (thinking, reasoning effort, `num_ctx`, temperature). For Ollama presets it also records the model digest (`/api/show`) and the server version (`/api/version`).
- [ ] **Token redaction (DD4).** A unit test plants a known fake token and drives a run whose model output, tool results and an exception all contain it. The token appears in none of the files the runner writes (results, transcripts, summary), and it never appears on stdout or stderr.
- [ ] **Locks and sweeps (DD3).** Each run directory gets an `owner.lock` holding the owning PID. At start, a stale `data/` is deleted only when its owner PID is dead. A unit test shows a live owner's `data/` survives a second runner's start-up.
- [ ] **Shutdown (DD3).** Shutdown runs stop indexing → `close_vector_store()` → `close_connection()` → delete `data/`. `data/` is gone after a normal run and after a run interrupted by an exception (try/finally).
- [ ] **Per-run setup (DD3).** Each run's agent has a unique name and its own `TurnContext(session_id=…)` around every `agent.step`.
  - A conversation boundary builds a fresh agent through `AgentFactory.create`.
  - Rules and seeded notes are created through the repositories before `create()`.
  - A test shows a note saved in conversation 1 appears in conversation 2's system prompt, and that two runs never see each other's notes.
- [ ] **Tool-free runs (DD6).** In a `tools_off` run, the first LLM call carries no tool schemas, its system message starts with `CHAT_ONLY_PROMPT`, and the date line uses the tool-free wording. A unit test asserts all three via the scripted provider's recorded calls.
- [ ] **Clock and zone (DD8).** Each run sets the instant and zone before `create()`. A test with two scenarios declaring different instants and zones shows each run's date line and a `current_time` result agree with that run's own values.
- [ ] **Fixture server (DD7).**
  - It serves `fixtures/web/` on `127.0.0.1` on a free port.
  - The `ToolConfig` rows give both `http_request` and `fetch_url` `extra_allowed_hosts = ["127.0.0.1"]` and `host_allowlist = ["127.0.0.1"]`.
  - A scripted `fetch_url` to the fixture succeeds, and one to another host is refused.
  - Every fetch attempt and its target is in the transcript.
- [ ] **KB fixtures.** A KB fixture folder is registered and indexed once per invocation with the real `IndexingManager` and the bundled embedding model. The runs that attach it can find it through `search_tools` and query it. The KB name and slug are taken verbatim from the scenario. A scripted test performs search → `kb__…__search` and checks the result text.
- [ ] **Containment (DD19).**
  - `HOME` and `USERPROFILE` point at `{run-dir}/home/`.
  - The filesystem tools' `path_allowlist` is narrowed to that home.
  - `web_search` and `download_file` are disabled.
  - Execution tools (`shell`, `python_exec`, `shell_session_*`) are either contained (bwrap sandbox present, `sandbox_network_allowed` false, and `host_access` refusable by config) or disabled for eval agents. Which branch applied, and why, is recorded in every run's record and in the flight log.
  - A scripted `write_file` to `~/x.txt` lands under `{run-dir}/home/`, and one to an absolute path outside it is refused.
- [ ] **Run outcomes (DD5).** Every outcome rule is unit-tested with the scripted provider raising each exception class:
  - `fail` covers model-caused errors: `max_iterations` exhausted with no final text, a tool-call timeout, and an Ollama tool-call parse 5xx (matched on error text).
  - `cut-short` covers refused, rate-limited or connection errors, after bounded backoff; backoff is injectable so tests don't sleep.
  - Three consecutive `cut-short` runs stop that model.
  - `PlanTokenRejectedError` aborts the invocation.
  - Any other exception is `error`.
  - A safety-class check that fails on database state turns the run into `fail` even when it would otherwise be excluded, and such a run is never re-run.
- [ ] **Results and resume (DD5).**
  - Each finished run is appended to `results.jsonl` immediately, recording the per-check results, outcome, timings, usage and the effective values.
  - `--resume {run-dir}` skips counted runs and re-runs `cut-short`/`error` runs with attempt + 1.
  - Each variant is scored by its final attempt.
  - A test kills a run mid-invocation (an exception after k runs) and resumes it to completion with no duplicates.
- [ ] **Checks (DD13).** Every check except `judge` is implemented with the exact DD13 semantics, and each has unit tests for pass and fail:
  - "reply" is the final assistant content of a turn, with no tool calls
  - "saved this run" excludes seeded notes
  - `reply_has_markdown_link` handles trailing slashes, autolinks, code spans and fences, and bare duplicates
  - `notes_from_untrusted_flagged` reports its non-vacuous count
  - `no_tool_call_text` uses the Ollama provider's own recovery parser plus harmony `to=functions.` markers
  - `date_line_present`
- [ ] **Scripted provider (DD18).** It plays a sequence of `Message`s, each with optional `tool_calls`, and records every call's messages and tool schemas. It is injected through the same `get_provider` wrapper as DD6. A three-step script (`search_tools` → `fetch_url` → final text) runs to completion.
- [ ] **Isolation from the product.** Nothing under `the_one/` imports `evals`; an AST-based unit test pins this. `pyproject.toml`'s pytest `pythonpath` includes `"."`, and `.gitignore` covers `evals/runs/` and `evals/.cache/`.
- [ ] **Regression check.** `make test-unit` passes, with the expected skip count of 12 on this host (more only for the documented timing-conditional skips). `.venv/bin/ruff check the_one/ tests/ scripts/ evals/` and `ruff format --check` on the same paths are clean.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_evals_*.py -x --timeout 60`
- `make test-unit`
- `.venv/bin/ruff check the_one/ tests/ scripts/ evals/ && .venv/bin/ruff format --check the_one/ tests/ scripts/ evals/`
- `.venv/bin/python -m evals run --help` and `--dry-run` against the test scenarios.
- `grep -rn "import evals\|from evals" the_one/` returns nothing; the AST test pins this.
- A manual check of a test run's output tree: no `data/` remains, and `owner.lock` and `results.jsonl` are present.

## Implementation Guidance

1. **Start from the CLI driving pattern.** Follow `the_one/interfaces/cli.py::_run_cli`:
   - `init_db()`, `reconcile_pending_key(conn, get_encryptor(settings.data_dir))`, `SQLiteAgentStore`, `AgentFactory(store=store)`
   - per turn: `token = current_turn.set(TurnContext(session_id=…))`, then `async for msg in agent.step(text)`, then `current_turn.reset(token)` in a `finally`

   Set `settings.data_dir` by assignment before any of this. `scripts/sweep_fusion_constants.py` is the precedent, and it also shows in-process `IndexingManager` use.
2. **Start-up order is safety-critical; write it as one function with the order explicit** (DD3, DD19):
   1. real default dir = `_default_data_dir()`
   2. guard
   3. read the token file (strip, never log)
   4. `os.environ["HOME"]`/`USERPROFILE` = scratch home
   5. set `settings.data_dir`
   6. sweep
   7. `init_db`

   platformdirs reads `HOME`, so step 1 must come before step 4. Check whether `settings` caches anything derived from `HOME` before step 5.
3. **Tool configuration rows** go through `ToolConfigRepository` with `ToolConfig(name=…, config=…, enabled=…)`:
   - Check `BuiltinToolProvider.get_tools` in `the_one/tools/builtins.py`: the shared Config resolves from the first tool carrying it, and the per-tool cfg from that tool's own row. Write the web rows for both `http_request` and `fetch_url`.
   - Filesystem: every filesystem tool shares `FilesystemConfig`. Find which tool's row is authoritative the same way, and narrow `path_allowlist` there; writing it on every filesystem tool's row is the safe choice.
4. **The execution-tool decision (DD19).** Inspect `the_one/tools/shell.py`, `python_exec.py` and `sessions.py` for how `host_access=true` is handled, and whether any `ExecutionConfig` field refuses it. Inspect `the_one/platform/sandbox*` to see whether bwrap or `PassthroughSandbox` is in use.
   - If host access cannot be refused by config, disable the execution tools for eval agents with `enabled=False` rows. That is the expected outcome.
   - Record the branch taken in the run records and in the flight log.
   - `absent-capability`'s pattern should then still list them; disabled tools simply never match.
5. **The provider wrapper** (DD6, DD18) is one context manager that temporarily replaces `the_one.agent.factory.get_provider` for the duration of `create()`.
   - It can either call the real `get_provider` and override `supports_tools` on the returned instance (`tools_off`), or return a scripted provider (tests).
   - Always restore it in `finally`, and keep it scoped to `create()` only.
   - The scripted provider subclasses `the_one.llm.base.LLMProvider`. Model it on `tests/conftest.py::FakeLLM`, but do not import `tests/` from `evals/`; copy the shape. It must give `supports_tools()`, a context window, and `complete()`/`stream()` behaviour compatible with `Agent._run_iterations`.
6. **Clock (DD8).** Patch `the_one.time_zones.utcnow` and `detect_system_zone` per run, mirroring `tests/conftest.py::frozen_clock`, and call `time_zones.save_setting(conn, TimeZoneSetting(mode="zone", zone=…))` before `create()`. Restore in `finally`.
7. **Provider rows (DD4).** Create `LLMProviderConfig` rows through `LLMProviderRepository` with `type`, `base_url` and `api_key` (the token, for `anthropic-plan-token`); it is encrypted at rest by the repository.
   - Check how `PROVIDER_TYPE_MAP` in the factory maps `"ollama"` to `native_api=True`.
   - Record effective values from the built provider instance after `create()` (`agent.llm`); find each one's resolved attribute, and record `None` honestly when an attribute is not exposed.
8. **Redaction.** One `Redactor` holds the token and wraps every write: JSON dumps, the summary, and log handlers. Install a logging filter on the root logger for the invocation, and redact exception strings before recording them.
9. **Ollama 5xx classification.** Find what the Ollama provider raises on a server 5xx and what the error text looks like when the model emits a malformed tool call. Look at `ollama_provider.py`'s error paths and any existing tests with such errors, and record the matched patterns in a code comment. If no evidence is available offline, match `"error parsing tool call"` and record that leg 3's live smoke must confirm it.
10. **Transcripts.** Write one JSON per run with every message (role, content, tool calls with arguments, tool results), the system prompt actually sent on the first call (from the scripted provider's records, or for live runs the first call's messages), the checks, and the outcome. Live runs capture the first call's messages by wrapping the provider's `complete`/`stream` in the same provider wrapper (record-only).
11. **Tests.** Use the `isolated_db`-style isolation in `tests/conftest.py`, or a temp `--run-dir` per test; never the real data dir. Keep each test file under ~60 s and mark nothing `live`.

## Edge Cases
- **An empty or missing token file with only Ollama presets selected.** The token is still required, because the judge needs it in leg 3, but leg 1 must allow `--models gpt-oss` with no judge-scored scenarios selected. Read the token only if a selected preset or check needs it.
- **Ctrl-C mid-run.** The `finally` path still deletes `data/` and releases the lock.
- **Tool-schema JSON in transcripts.** Store schemas only once per run (the starting set), not per call.
- **A scenario whose `n` exceeds its distinct variants.** The loader rejects it (n ≤ phrasings × facts).
- **Agent names.** They must satisfy the agent-name validation in `AgentConfig`/the store. Check the allowed characters and the length limit, and hash a long name if needed.
- **The KB fixture path.** The KB folder must not lie inside the scratch `data/` directory (the API refuses that; mirror the refusal). Use `{run-dir}/home/kb/{fixture}` copied from the fixture source, or the repo fixture path directly.

## Files Affected
- `evals/` (new package and `models.toml`)
- `tests/test_evals_*.py`, `tests/fixtures/evals/` (new)
- `pyproject.toml` (pytest `pythonpath`)
- `.gitignore`

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked 2026-10-13 against the working tree:
- `the_one/interfaces/cli.py::_run_cli` calls `init_db`, `reconcile_pending_key` and `AgentFactory(store=store)`.
- `FilesystemConfig.path_allowlist` defaults to `["~"]` (`the_one/tools/filesystem.py`).
- `ExecutionConfig.sandbox_network_allowed` (`the_one/tools/execution.py`).
- `host_access` is a parameter of `python_exec` and the session tools (`python_exec.py`, `sessions.py`).
- `ToolConfig` is in `the_one/db/models.py`, `ToolConfigRepository` in `the_one/db/repositories.py`.
- The `_TOOL_CLASSES` order in `the_one/tools/builtins.py` lists `http_request` before `fetch_url`, and includes `delete_file` (so add `delete_file` to the absent-capability pattern in leg 3).
