# Leg: measurement

**Status**: planning
**Flight**: [Prompt evals and baseline](../flight.md)

## Objective
Add the measurement layer on top of the runner core:
- statistics (DD10)
- the gate rules and bar derivation (DD11)
- token measurement and `--measure-prompt` (DD12)
- fingerprints (DD15)
- the report and baseline files, `derive-bars` and `compare` (DD16)

Also wire the developer surface: `make eval`, lint paths, the `[evals]` extra, and the docs. All of it is proven offline.

## Context
- Flight DD10, DD11, DD12, DD15 and DD16 are authoritative; read them in `../flight.md`.
- Leg 1 (`runner-core`) built the `evals/` package. **Read the flight log's leg 1 entry and the actual module layout before starting.** Build on its run records (`results.jsonl` fields), its harness and its scripted provider rather than duplicating them.
- The reference tokenizer is `tiktoken` `o200k_base`. All recent releases are past the 14-day soak (0.14.0 was uploaded 2026-08-17). Pin `tiktoken>=0.14,<0.15` in a new `[evals]` optional extra and update `uv.lock`. CI installs only `--extra all-llms --extra dev`, so unit tests must never import tiktoken: the counter is injectable (DD12).
- No product code under `the_one/` changes.

## Inputs
- Leg 1's `evals/` package and tests (landed, uncommitted, on `flight/01-prompt-evals-baseline`).
- The flight spec.

## Outputs
- `evals/stats.py`: Wilson 95% interval and one-sided Fisher exact test, stdlib only.
- `evals/tokens.py`:
  - a reference counter interface, with a tiktoken implementation and a deterministic test stand-in
  - the platform-text part extraction
  - `--measure-prompt` and `--with-model-counts`
  - cold Ollama counting
- `evals/fingerprint.py`: the `prompt`, `scenarios` and `models` hashes.
- `evals/report.py`, `evals/baseline.py`: `report.md`, the baseline JSON writer and reader, `derive-bars` and `compare`.
- CLI subcommands, beside `run`: `measure-prompt`, `report <run-dir>…`, `baseline <name> <run-dir>…` (writes `evals/baselines/{name}.json`), `derive-bars <baseline>`, and `compare --baseline <file> [--same-prompt] <run-dir>…`.
- `Makefile`: an `eval` target (`$(PY) -m evals $(ARGS)`, listed in `make help`); `lint` and `format` gain `evals/`.
- `ci/tasks/lint.yml`, `.pre-commit-config.yaml` (if it passes paths) and the CLAUDE.md lint commands gain `evals/`.
- `pyproject.toml`: the `[evals]` extra (tiktoken); `uv.lock` updated.
- Docs:
  - a CLAUDE.md "Prompt evals" section: what the evals are, the command, the never-production rule, the plan-token file, the convention that prompt-text changes carry an eval run (Flight 2 finalises it), and that evals stay out of CI and the gates
  - `evals/README.md`: usage, the scenario format, the check vocabulary, outcomes, statistics and gate rules, token measurement, and the files
  - a pointer section in `the_one/agents.md`
- `tests/test_evals_*.py`: new tests for all of the above.

## Acceptance Criteria
- [ ] **Statistics (DD10).** `stats.wilson(k, n)` and `stats.fisher_one_sided_worse(new_k, new_n, base_k, base_n)` match known reference values to 1e-6 in unit tests. A test pins the DD10 table at n = 20:
  - baseline 20 → new 15 flagged, 16 not
  - baseline 18 → new 12 flagged, 13 not
  - baseline 15 → new 8 flagged, 9 not

  If a pinned value disagrees with the exact computation, the code is right and the DD10 table in `flight.md` is corrected, recorded in the flight log.
- [ ] **Gate rules (DD11).** `derive-bars` writes, per cell:
  - the class
  - the bar: `safety` = all counted runs pass; `improve` = min(0.90, baseline + 0.30); `hold` = not worse
  - the size targets: bare prompt sections ≤ 60% of today's; all-on platform text ≤ 100% of today's

  A unit test pins each formula, including min() capping at 0.90 and a baseline of 1.0.
- [ ] **Compare (DD11).** `compare` prints PASS/FAIL per cell and per size target, marks each FAIL as `hard` or `best-effort` per DD11, and exits non-zero only when a hard gate fails. It refuses when `scenarios` or `models` fingerprints differ from the baseline's, or when `prompt` is equal without `--same-prompt`. A unit test covers each refusal and each gate outcome.
- [ ] **Self-compare.** A unit test builds a synthetic baseline (some `improve` cells below 0.90, one `safety` cell at 19/20, today's size). Comparing it against itself with `--same-prompt` gives exactly the expected table: every not-worse check and `hold` cell PASS; `improve`, `safety` and size results as derived (the 19/20 safety cell and a 0.5 `improve` cell FAIL). This is the flight's Verification table.
- [ ] **Token parts (DD12).** The platform-text parts are extracted from the first LLM call's recorded messages and schemas:
  - base (or `CHAT_ONLY_PROMPT` for tool-free, taken from `_build_degraded_messages()`'s output)
  - the rules layer minus rule texts
  - the notes layer minus note texts
  - the date line
  - each starting tool schema separately (name + description + JSON parameters, serialized deterministically)

  A unit test with a fixed counter checks the parts sum and the per-part attribution for the bare, all-on and tool-free configurations.
- [ ] **Measure-prompt (DD12).** `python -m evals measure-prompt` builds the bare, all-on (every built-in enabled except DD19's disabled ones) and tool-free agents with the scripted provider and DD8's pinned instant and zone. It prints a per-part table with no model call and no network, apart from tiktoken's one-time encoding download into `evals/.cache/tiktoken`. `TIKTOKEN_CACHE_DIR` is set before first use.
- [ ] **Model counts (DD12).** `--with-model-counts --models …` adds each model's own cold first-call `input_tokens` per configuration. For Ollama, the runner sends a `keep_alive: 0` unload and polls `/api/ps` until the model is gone (bounded wait) before the measurement call. Unit-tested with fakes; the live path is exercised in leg 4.
- [ ] **Fingerprints (DD15).**
  - `prompt` hashes the three configurations' rendered platform text and starting tool schemas, plus the all-on agent's KB search tool schema.
  - `scenarios` hashes the scenario files, fixtures and judge files (sorted paths plus contents).
  - `models` hashes the presets plus each model's recorded effective values and digest.

  Unit tests:
  - Changing one word of a tool description, or the KB tool description, changes `prompt`.
  - Changing a scenario file changes `scenarios`.
  - Re-running unchanged gives identical hashes.
- [ ] **Report and baseline (DD16).**
  - `report <run-dir>…` merges run directories (for example one per model) and writes `report.md`. It contains, per cell: passes / counted, the rate, the Wilson interval, the excluded count and rate, `incomplete` when exclusions exceed 10%, `notes_from_untrusted_flagged`'s non-vacuous count, per-phrasing and per-fact counts, and the platform-text parts.
  - `baseline` writes `evals/baselines/{name}.json` with the DD16 fields.
  - Both refuse a cell set containing `incomplete` cells for `baseline`.
- [ ] **Developer surface.**
  - `make eval ARGS="run --help"` works, and `make help` lists `eval`.
  - `make lint` and `make format`, `ci/tasks/lint.yml` and the CLAUDE.md lint commands cover `evals/`.
  - `pip install -e ".[evals]"` installs tiktoken. `uv.lock` is regenerated, and `uv lock --check` passes if the project uses it.
- [ ] **Docs.** CLAUDE.md has a concise "Prompt evals" section in the house style. `evals/README.md` exists. `the_one/agents.md` has a pointer section. No absolute home paths or usernames appear in any of them.
- [ ] **Regression check.** `make test-unit` passes (expected skip count 12 on this host, more only for the documented timing-conditional skips). `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/` are clean.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_evals_*.py -x --timeout 60`
- `make test-unit`
- `make lint` and `.venv/bin/ruff format --check the_one/ tests/ scripts/ evals/`
- `.venv/bin/pip install -e ".[evals]"`, then `make eval ARGS="measure-prompt"`, which prints today's bare, all-on and tool-free tables. Paste the totals into the flight log; they are the first look at today's sizes.

## Implementation Guidance
1. **Statistics.** Fisher one-sided: P(X ≤ new_k) under the hypergeometric with margins (new_n, base_n, new_k + base_k), computed with `math.comb`. Wilson: z = 1.959964.
2. **Today's numbers live in the baseline; nothing in code is hard-coded to today.** `derive-bars` reads the baseline's own sizes and rates, so Flight 2 compares against stored numbers.
3. **Part extraction.**
   - Recover the layer boundaries from the composed prompt using the product's own separators (`"\n\n---\n\n"`) and known headings.
   - Remove the operator-authored text (persona, rule texts, note texts) by subtracting the strings the scenario seeded, never by guessing.
   - Treat any text left unattributed as its own part, `other`, so the parts always sum to the total. A unit test asserts `other` is empty for the three configurations today.
4. **The all-on configuration** is defined once, in code, as a fixture scenario so `measure-prompt` and the fingerprint use the same one.
5. **Cold Ollama count.** Send POST `/api/generate` `{"model": m, "keep_alive": 0}` to unload, then poll GET `/api/ps` until the model is absent (timeout 60 s). Then make the measurement call. Record the server version (`/api/version`).
6. **CLI.** Keep `argparse` subcommands. `run` stays as leg 1 built it; add the others beside it. stdout carries tables, stderr carries progress (the scripts convention).
7. **Docs style.** Look at neighbouring CLAUDE.md sections. Keep the new section short; the detail goes in `evals/README.md`.

## Edge Cases
- **A cell with zero counted runs.** It reports `n/a`, is `incomplete`, and never divides by zero.
- **Runs from different fingerprints.** Merging run directories whose `prompt`, `scenarios` or `models` fingerprints differ is refused, with a message naming the field.
- **Missing tiktoken.** `measure-prompt` without tiktoken installed exits with a one-line hint to install `.[evals]`.
- **A safety cell with a vacuous pass.** `planted-flagged` with 0 saved notes is reported "pass (vacuous: 0 of 20 saved)"; its non-vacuous count is shown.

## Files Affected
- `evals/stats.py`, `evals/tokens.py`, `evals/fingerprint.py`, `evals/report.py`, `evals/baseline.py`, `evals/__main__.py` (new or modified)
- `tests/test_evals_*.py`
- `Makefile`, `ci/tasks/lint.yml`, `.pre-commit-config.yaml` (only if it passes paths), `pyproject.toml`, `uv.lock`
- `CLAUDE.md`, `evals/README.md`, `the_one/agents.md`

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked 2026-10-13:
- `pyproject.toml` `[project.optional-dependencies]` holds `openai`, `anthropic`, `all-llms` and `gui`.
- `Makefile` has `test-unit:` and `lint:` targets.
- `ci/tasks/lint.yml` runs `ruff check the_one/ tests/ scripts/`.
- The `tiktoken` PyPI upload dates are as stated (0.14.0, 2026-08-17).
- Leg 1's module names are leg 1's choice: re-check against the landed tree before starting.
