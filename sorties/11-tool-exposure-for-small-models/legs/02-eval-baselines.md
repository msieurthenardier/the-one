# Leg: eval-baselines

**Status**: completed
**Flight**: [Tool exposure for small local models](../flight.md)

## Objective
Record the new same-prompt baselines on the unchanged product: `evals/baselines/s11-platform.json` (the main scenario set) and `evals/baselines/s11-routines.json` (the routines set), each from n=20 runs on `haiku`, `qwen3-4b` and `lfm3`. Then re-point the freeze test at `s11-platform`, add the s11 baseline-file test, name the new baselines in the docs, and report today's true rates for the operator checkpoint.

## Context
- The design is the flight's **DD9** (the baselines), **DD10** (leg 2's part), **DD4** (the hostname probe) and the divert criteria under Adaptation Criteria. Read `../flight.md` first. Where this leg and the flight disagree, this leg wins and the disagreement is a defect to report.
- **Leg 1 landed and committed** (`05259b43`):
  - fixtures are served as `http://town.example` (`evals/fixtures.py::FIXTURE_HOSTNAME`) through `harness.fixture_host_patch`, with a nonce self-test;
  - the default presets are `haiku`, `qwen3-4b`, `lfm3`;
  - measurement documents are schema 2 (`tools_full`, `tools_full_names`, `prompt_text`, `exposure`);
  - `build_baseline` writes schema 2 from a schema-2 measurement;
  - the claims cells are `report` class, and `planted-instruction` / `routines-planted-instruction` carry `exposed_if`;
  - `tests/test_evals_freeze.py` pins a literal `SCENARIOS_FINGERPRINT`.
- **The probe was done before this leg was handed over.** The Flight Director ran `tool-discovery` and `planted` at n=4 on the three default models (`evals/runs/s11-probe`) through the full harness, and the operator approved the hostname. See the flight log for the result and the approved name. If the operator chose a different name than `town.example`, that change is this leg's first step (step 1 below); otherwise skip it.
- **No product change.** The prompt is today's. These are same-prompt baselines of new scenario sets (CLAUDE.md "Prompt evals": never compared across sets).
- The runs spend plan quota (haiku) and take hours (qwen3-4b is the slow one). They are local-only and never touch port 8484 or the operator's data directory; the evals enforce that.

## Inputs
- Branch `sortie/11-tool-exposure-for-small-models` at `05259b43` or later.
- Ollama `0.40.14` at `http://localhost:11434` with:
  - `qwen3:4b-instruct-2507-q4_K_M` (digest prefix `0edcdef34593eac1`);
  - `lfm3:1.7b-q4_K_M` (digest prefix `b36a103fe2f8fbe9`).
- The plan token at `~/.config/the-one-evals/plan-token` (the probe used it).
- Do not upgrade Ollama, re-pull a model, or edit `evals/models.toml` for the rest of the sortie.

## Outputs
- Gitignored run directories `evals/runs/s11-base-main` and `evals/runs/s11-base-routines`, each with its `measure.json` and `report.md`.
- `evals/baselines/s11-platform.json`, `evals/baselines/s11-routines.json` (committed by the Flight Director after the operator checkpoint).
- `tests/test_evals_freeze.py`: the scenarios pin is re-pointed.
- `tests/test_evals_baseline_file.py`: an s11 test.
- `evals/README.md`, `CLAUDE.md` ("Prompt evals"): the current baselines are named.
- A flight-log entry with the rates table.

## Acceptance Criteria
- [ ] AC1. Each run directory holds a schema-2 `measure.json` made on the unchanged prompt with `--with-model-counts` (the default presets). In every configuration, `exposure` is `null` and the measurement's `prompt` fingerprint is the same for both directories.
- [ ] AC2. Both scenario sets have run at `--n 20` on the default presets. No cell is incomplete (`baseline` refuses otherwise; resume with `--resume <dir>` until it accepts). The flight log reports each model's excluded-run count and reasons.
- [ ] AC3. Every `qwen3-4b` and `lfm3` record's `effective` shows the configured 16384 window (`num_ctx`, or whatever key `effective_values` records it under). A record that shows less is a stop: report it, do not baseline.
- [ ] AC4. No record has a non-empty `off_fixture_fetches` that went to a real host, and the fixture request logs show `town.example` paths (sample a few transcripts). Any record showing a real-host fetch is reported in the flight log.
- [ ] AC5. `evals/baselines/s11-platform.json` and `s11-routines.json` are built with `python -m evals baseline <name> <run-dir>`, then `derive-bars --size-ratio 1.0`. Each is `"schema": 2`, and its `size_targets` hold the `{config}:prompt-text` and `{config}:tools` pairs. No hand edits.
- [ ] AC6. `tests/test_evals_freeze.py`'s scenarios pin compares `fp.scenarios_fingerprint(EVALS / "scenarios", EVALS / "fixtures", EVALS / "judge")` against `s11-platform.json`'s `fingerprints.scenarios`. It no longer uses a literal: drop `SCENARIOS_FINGERPRINT` and rename the test, with a comment that leg 3 must not move it. `SCORING_DIGESTS` and `MEASURE_DIGESTS` are unchanged.
- [ ] AC7. `tests/test_evals_baseline_file.py` gains `test_s11_platform_has_every_field` and `test_s11_routines_has_every_field`, modelled on the m30 test. Each asserts:
  - `schema == 2`;
  - the three fingerprints;
  - models `{"haiku", "qwen3-4b", "lfm3"}`, and `model_digest`/`server_version` in each Ollama model's `model_info`;
  - the exact cell count per model, as built: each cell has the per-cell keys plus `not_exposed`, and none is incomplete;
  - `counted + excluded + not_exposed == 20` per cell;
  - the `size_targets` key set.

  The m30 test is unchanged.
- [ ] AC8. `evals/README.md` and `CLAUDE.md`'s "Prompt evals" paragraph name `s11-platform` and `s11-routines` as the current baselines, with `m30-platform` and `m33-routines` kept as history. They also name the default eval models (`haiku`, `qwen3-4b`, `lfm3`; `gpt-oss` kept, not default).
- [ ] AC9. The flight log's leg 2 entry has:
  - the Ollama version and both digests;
  - the run directories;
  - each model × cell rate with its Wilson interval and, for exposure cells, the exposed count;
  - the claims cells' rates;
  - the size totals (`prompt_text`, `tools`, `tools_full` for bare and all-on);
  - wall time per set;
  - the divert check, stated as a sentence: are `qwen3-4b`'s `kb-find`, `kb-answer` and `tool-discovery` each already at 0.9 or more?
- [ ] AC10. `THE_ONE_TEST_NETNS=1 make test-unit` is green, and `ruff check` / `ruff format --check` are clean.

## Verification Steps
`jq` is not installed on this host. Do each of the read-only checks below with a small Python script kept in your scratchpad or `/tmp`, never in the repo, run with the repo venv. The `block_shell_writes` hook refuses inline heredoc Python whose working directory is the repo.
- AC1: `jq '.schema, .fingerprints.prompt, [.configs[].exposure]' evals/runs/s11-base-*/measure.json`.
- AC2: `python -m evals report <dir>`. `baseline` succeeds.
- AC3: `jq -r 'select(.model!="haiku") | [.model, (.effective|tostring)] | @tsv' evals/runs/s11-base-*/results.jsonl | sort | uniq -c`.
- AC4: `jq -r 'select((.off_fixture_fetches|length)>0) | [.run_key, (.off_fixture_fetches|tostring)] | @tsv' evals/runs/s11-base-*/results.jsonl`.
- AC5: `jq '.schema, (.size_targets|keys)' evals/baselines/s11-*.json`.
- AC6, AC7: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_evals_freeze.py tests/test_evals_baseline_file.py -x --timeout 30`.
- AC10: the unit gate in the background; report the summary line.

## Implementation Guidance
1. **Hostname (only if the operator changed it).** Edit `evals/fixtures.py::FIXTURE_HOSTNAME`. Then recompute `tests/test_evals_freeze.py`'s `SCORING_DIGESTS` (if a scoring file changed) and `SCENARIOS_FINGERPRINT`, and run the eval tests. Record it in the flight log.
2. **Measure.** For each directory: `make eval ARGS="measure-prompt --with-model-counts --json evals/runs/s11-base-main/measure.json"`. Copy it to the routines directory too, or measure again there; the prompt is identical, so either is fine; say which. `--with-model-counts` loads each Ollama model cold: run it before the scenario runs, not alongside them.
3. **Run.**
   - Main set: `make eval ARGS="run --n 20 --run-dir evals/runs/s11-base-main"`.
   - Routines set: `make eval ARGS="run --n 20 --scenarios-dir evals/routines/scenarios --run-dir evals/runs/s11-base-routines"`.

   Run them **one after the other, never concurrently** (one Ollama, and the operator's PC). Run each in the background and wait for its completion notification. Do not poll with `sleep` loops.

   A `measure.json` must sit in the run directory before `report`/`baseline`. If `run` refuses an existing directory that holds only `measure.json`, measure into the directory after the run instead (same prompt), and say so.
4. **Resume** any incomplete cells with `--resume <dir>` (cut-short runs from transient Ollama or plan errors). A model whose breaker trips (repeated cut-shorts) is a stop to report, not something to retry indefinitely. A `401` aborts the invocation; report it, since the operator must refresh the token.
5. **Check** AC3 and AC4 before building baselines.
6. **Build** `baseline s11-platform evals/runs/s11-base-main` and `baseline s11-routines evals/runs/s11-base-routines`, then `derive-bars --size-ratio 1.0 evals/baselines/s11-platform.json` (and routines). The baseline name must be exactly these.
7. **Tests and docs** (AC6-AC8), through the edit tool.
8. **Report** (AC9). Use `python -m evals report` output for the numbers. Do not commit; the Flight Director commits after the operator has seen the numbers.

## Edge Cases
- **Claim false positives in the baseline runs:** read every claims-cell failure's detail in the transcripts. A first-person false positive (the model did not claim an action it did not perform) is reported in the flight log with the quoted text. Changing a pattern changes the scenarios fingerprint and would need a re-run, so do not change one in this leg; report it for the Flight Director to decide.
- **A model that never fetches the planted page:** `planted-instruction` is then not exposed for that model. That is expected for `qwen3-4b` under discovery, and is not incomplete. Record the exposed count.
- **haiku's judge calls** (`notes-as-told` uses `judge`): they count against plan quota like the runs.
- **The run takes many hours:** that is expected. The unit gate in step 7 can run once the runs have finished; do not run it concurrently with a model run, because both load the host.

## Files Affected
- `evals/baselines/s11-platform.json`, `evals/baselines/s11-routines.json`: new, generated.
- `tests/test_evals_freeze.py`, `tests/test_evals_baseline_file.py`.
- `evals/README.md`, `CLAUDE.md`.
- `evals/fixtures.py` and the freeze digests, only if the hostname changed.
- `sorties/11-tool-exposure-for-small-models/flight-log.md`, this leg's status.

## Citation Audit
Checked against `05259b43` (2026-11-06):
- `python -m evals measure-prompt [--with-model-counts] [--models] [--json JSON_OUT] [--run-dir]`, `run [--models] [--scenarios] [--scenarios-dir] [--n] [--run-dir | --resume]`, `baseline name run-dir... [--measure]` and `derive-bars [--size-ratio] baseline`: verified by `--help`.
- `evals/report.py::load_runs`: it refuses a run directory with no `measure.json` unless `--measure` is passed. Verified.
- `evals/baseline.py::build_baseline`: it refuses incomplete cells and writes schema 2 from a schema-2 measurement (leg 1). Verified.
- `tests/test_evals_freeze.py`: `SCENARIOS_FINGERPRINT` literal and the renamed test `test_scenarios_fixtures_and_judge_match_the_pinned_scenarios_fingerprint` (leg 1). Verified.
- `tests/test_evals_baseline_file.py::test_m30_today_has_every_dd16_field`: the model for the new tests. Verified.
- Ollama `/api/version` → `0.40.14`; `/api/tags` lists both tags with the digest prefixes above (2026-11-06). Verified.
