# Leg: evals-readiness

**Status**: ready
**Flight**: [The platform prompt](../flight.md)

## Objective
Prepare the `evals/` package to measure a changing platform prompt fairly, without touching product code:
- structural part extraction (DD10)
- frozen measurement and scoring inputs (DD12)
- stricter, connector-aware size checks (DD13)
- the vacuous count (DD14)
- a lower unit-tier cost (DD15)
- `compare` refusing unmeasured run directories (DD5.1)
- `derive-bars --size-ratio` (DD11)

## Context
- Flight DD5.1, DD10, DD11, DD12, DD13, DD14 and DD15 are authoritative; read them in `../flight.md`.
- Baseline: `evals/baselines/m30-today.json`.
  - Prompt sections: bare 595, all-on 862, tool-free 84.
  - Platform text: bare 1308, all-on 1789, tool-free 84.
  - The two connector parts in bare: 251 + 210 = 461.
- **Product code under `the_one/` must not change in this leg.** Leg 1b changes the product.
- **No captured prompt fixtures may be committed** (the operator's no-golden-files rule). Unit tests compose synthetic prompts in-test.
- `evals/scenarios/`, `evals/fixtures/`, `evals/judge/` and `evals/measure/` must not change. The scoring modules `checks.py`, `outcomes.py`, `judge.py` and `harness.py` keep their logic; any diff there is test-only, or a `_script_for`-style measurement hook if unavoidable, recorded.

## Inputs
- Flight 1 is complete. `evals/` is at its state on `flight/02-platform-prompt`.
- tiktoken is installed (`pip install -e ".[evals]"`), with its encoding cached under `evals/.cache/tiktoken`.

## Outputs
- `evals/tokens.py`: structural `extract_parts`, connector-mapped measurement variants, and new size categories.
- `evals/baseline.py` and `evals/report.py`: DD13 hard gates, DD14 vacuous count, the `measure.json` refusal, and `--size-ratio`.
- `evals/__main__.py`: a `selftest` subcommand (DD15) and the `derive-bars --size-ratio` flag.
- `tests/test_evals_*.py`: new and updated tests, including the freeze test.
- The flight log: a `evals-readiness` Leg Progress entry with the one-time tiktoken verification numbers.

## Acceptance Criteria
- [ ] **Structural extraction (DD10).**
  - `extract_parts` no longer references `BASE_PROMPT`, `CHAT_ONLY_PROMPT`, `RULES_HEADING` or `NOTES_HEADING` to find layers.
  - It splits on the product's layer separator (imported or derived from `compose_system_prompt`, not re-hard-coded where avoidable), assigns layers by the known order (platform, persona, rules, notes, date, each present per configuration) and subtracts the operator texts in every layer.
  - Platform text goes to a single `platform` part for now. Leg 1b adds section ids through a hook (a function taking the platform text and returning `[(id, text)]`), which defaults to a single part.
  - The category totals (prompt sections, tool schemas, platform text) are computed as before.
  - Unit tests with the stand-in counter cover bare, all-on, tool-free and persona-present prompts composed in-test, and pin that `unattributed` stays empty.
- [ ] **First one-time verification (DD10).** With the product untouched, `make eval ARGS="measure-prompt"` (tiktoken) reproduces `m30-today`'s sizes exactly: prompt sections 595 / 862 / 84 and platform text 1308 / 1789 / 84. The output is pasted into the flight log.
- [ ] **Freeze test (DD12).** A unit test asserts that `scenarios_fingerprint(...)` equals `m30-today.json`'s `scenarios` fingerprint. It also pins SHA-256 digests of the `evals/measure/` files and of `checks.py`, `outcomes.py`, `judge.py` and `harness.py`, as recorded at this leg's end.
  - The digests are a frozen snapshot that leg 2 must not change, so the test's message says how to update them deliberately.
  - If `harness.py` must change for DD13, change it before recording the digests, and log why.
- [ ] **Size checks (DD13).** `measure-prompt` additionally builds **bare plus connector** and **all-on plus connector**:
  - Each is built from the frozen TOML plus a connector row whose `default_agent` is the variant's own distinct agent name (a distinct attempt number).
  - The row is inserted, the variant measured, then the row deleted, so plain bare and all-on are never mapped.
  - Both are added to the prompt fingerprint and to `_script_for` (or its equivalent), with all-on plus connector getting the `search_tools` script.
- [ ] **Size gates (DD13).** `compare` reports these hard size gates, each maximum read from the baseline's `sizes`:
  - bare prompt sections ≤ derived target (357 for `m30-today`)
  - bare platform ≤ (baseline bare platform − connector parts present in the baseline's bare configuration), giving 847 for `m30-today`
  - bare plus connector platform ≤ the baseline's bare platform (1308)
  - all-on platform ≤ 1789
  - all-on plus connector platform ≤ the baseline's all-on platform (1789)

  Unit tests cover PASS and FAIL for each. A baseline without connector-variant sizes (`m30-today`) takes the "plus connector" maxima from its plain bare and all-on sizes, as stated above.
- [ ] **Vacuous count (DD14).** `compare` prints `planted-flagged`'s non-vacuous count beside its pass rate, and the same for any check reporting a non-vacuous count. Unit-tested.
- [ ] **`measure.json` refusal (DD5.1).**
  - `compare` (and `report`) refuse a run directory with no `measure.json` when no `--measure` is given, with a one-line error naming the directory.
  - `compare` warns on stderr whenever `--measure` is given.
  - Mixed prompt fingerprints across run directories are refused (already true; test kept).
  - Unit-tested.
- [ ] **`--size-ratio` (DD11).** `derive-bars --size-ratio R` (default 0.60) sets the bare prompt-sections target to R × the baseline's. The other size maxima are baseline values, ratio 1.0. Unit-tested for 0.60 and 1.0.
- [ ] **Unit-tier cost (DD15).**
  - The per-scenario "passing script passes all variants" tests run 5 variants (one per fact) in the unit tier.
  - `python -m evals selftest` runs the full can-fail suite at width 20, offline (scripted provider, no model).
  - Record `tests/test_evals_*.py` wall time before and after in the flight log.
- [ ] **Regression check.** `make test-unit` passes (expected 12 skips), and `ruff check` / `ruff format --check` on `the_one/ tests/ scripts/ evals/` are clean. `git diff --stat -- the_one/` is empty.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_evals_*.py -x --timeout 60`
- `make eval ARGS="measure-prompt"`: the totals match `m30-today` (paste them in the flight log).
- `make eval ARGS="selftest"`
- `make test-unit`, then `make lint`.
- `git diff --stat -- the_one/ evals/scenarios evals/fixtures evals/judge evals/measure` is empty.

## Implementation Guidance
1. **Read first:** `evals/tokens.py` (`extract_parts`, `measure_prompt`, `_script_for`), `evals/baseline.py` (`derive_bars`, `BARE_RATIO`, compare), `evals/report.py` (`load_runs`), `evals/fingerprint.py` and `evals/__main__.py`.
2. **The separator** is `compose_system_prompt`'s `"\n\n".join` with `"---"` parts, so the layer separator is `"\n\n---\n\n"`. Import it if the product exposes it. Otherwise derive it by composing two known layers in a test and assert they agree. Do not change product code to expose it.
3. **Known layer order.** `measure-prompt` knows each configuration's persona, rules and notes from its TOML, and a run's transcript knows its scenario. Pass the expected operator texts into `extract_parts` instead of discovering them.
4. **Distinct agent names.** Take them from the existing `RunSpec.agent_name` scheme with a reserved attempt number, for example `attempt=90` and `attempt=91`.

## Edge Cases
- **A persona containing the separator.** The splitter must tolerate it by matching operator text before splitting, or by splitting at most the known number of times. Test it.
- **A notes layer present with no notes** (`No saved notes yet.`). It counts as platform text.

## Files Affected
- `evals/tokens.py`, `evals/baseline.py`, `evals/report.py`, `evals/__main__.py` (and `evals/fingerprint.py` if the prompt fingerprint gains the variants)
- `tests/test_evals_*.py`
- the flight log

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked 2026-10-14 against the flight spec and the Architect's cycle-2 review:
- `report.load_runs` honours each directory's `measure.json` only when `measure_path is None`.
- `evals/baseline.py` has `BARE_RATIO = 0.60`.
- `RunSpec.agent_name` is `ev-{scenario.id}-{model}-{variant}-{attempt}`.
- `_script_for` exists in `evals/tokens.py`.
