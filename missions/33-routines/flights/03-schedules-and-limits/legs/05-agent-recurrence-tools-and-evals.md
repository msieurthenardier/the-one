# Leg: agent-recurrence-tools-and-evals

**Status**: ready
**Flight**: [Schedules and Limits](../flight.md)

## Objective

Teach the agent the calendar recurrence (flight DD8): rewrite the routine
tools' schedule description to the canonical DD1 shape with the relative
start, and prove with evals that the change, together with leg 2's new
limits sentence and leg 4's new schedule sentences in tool results, does
not regress the routines scenarios.

## Context

- **Legs 2 and 4 have landed** (read their flight-log entries):
  - leg 2 changed `_LIMITS_SENTENCE` to "At most 50 active routines and 5
    changes a turn. Your operator may need to approve.";
  - leg 4 switched the tools to the service's normalizer (canonical,
    relative and legacy shapes all accepted), changed the sentences in tool
    results to `recurrence_text.describe`, and mapped the stored shape back
    to `kind` in `evals/harness.py::_collect_routines`.
- **What changes here:** `the_one/routines/tools.py::_SCHEDULE_SHAPES` (and
  `_SCHEDULE_SCHEMA`'s description, which embeds it) documents only the
  canonical shape and the relative start (DD5: the aliases stay accepted
  but undocumented, so they cost no tokens). Suggested text (tune for
  brevity; the measured cost is recorded):

  ```
  {"start":{"in":{"amount":N,"unit":"minutes|hours|days"}}} for a one-off after a delay;
  {"start":{"date":"YYYY-MM-DD","time":"HH:MM"}} for a one-off at a time; add
  "repeat":{"every":N,"unit":"minute|hour|day|week|month|year"} to repeat
  (weeks also take "days":[0-6, 0 is Monday]), and optionally
  "ends":{"kind":"on","date":"YYYY-MM-DD"} or {"kind":"after","count":N}.
  ```

  `tests/test_routine_tools.py` pins the description text; update its
  assertions in this leg.
- **The evals** (Mission 30 convention; `evals/README.md`):
  - **Session checks first** (external sessions, never printed):
    `curl -s 127.0.0.1:11434/api/tags` lists `gpt-oss:20b`;
    `~/.config/the-one-evals/plan-token` exists.
  - `make eval ARGS="measure-prompt --json evals/runs/m33f3-measure.json"`:
    the routines-on configuration's size (Flight 2: the routine tools added
    853 tokens), and the bare, all-on and tool-free prompts.
  - **`m30-platform`:** routines are off in every `m30-platform` scenario,
    so the routine tool text is never in those prompts. If `measure-prompt`
    shows the routines-off prompt fingerprint and sizes identical to
    `m30-platform`'s, record that and skip the full `m30-platform` run (no
    measured text changed). If they differ, run the full set and compare as
    Flight 2's leg 4 did (`compare --baseline evals/baselines/m30-platform.json`).
    *(FD: refines DD8's "compare against both", recorded as a deviation.)*
  - **`m33-routines`:** run the routines set on both models with the same
    run counts as the baseline (20 runs per cell):
    `make eval ARGS="run --models haiku --scenarios-dir evals/routines/scenarios --run-dir evals/runs/m33f3-routines-haiku"`
    and the `gpt-oss` equivalent (they may run in parallel), then
    `make eval ARGS="compare --baseline evals/baselines/m33-routines.json evals/runs/m33f3-routines-haiku evals/runs/m33f3-routines-gpt-oss"`,
    output kept as `evals/runs/m33f3-compare.txt` (gitignored). The scenario
    fingerprint covers scenario TOML, fixtures and judge only, so it matches
    the baseline; no re-baseline.
  - **Gate:** `compare` exits 0 (no hard failure); `routines-follow-up`,
    `routines-no-spam` and `routines-planted` within their bars on both
    models; `routines-planted` still non-vacuous on gpt-oss with every
    scheduled routine flagged. `routines-planted-instruction` is
    best-effort; report it.
  - **If `routines-follow-up` regresses** (the model fails to produce the
    new shape): first check the refusal text the model got; adjust the
    description (not the checks); re-run. Two attempts, then
    `[BLOCKED:eval-regression]` with the numbers.
- **Load:** the model runs take hours of wall time and load the host. Do
  not run any browser lane during them, and record start/end load; no lane
  budget is read during this leg.

## Inputs

- Flight spec DD5, DD8; legs 2 and 4 in the flight log.
- `the_one/routines/tools.py`, `tests/test_routine_tools.py`,
  `evals/README.md`, `evals/baselines/m33-routines.json`,
  `evals/baselines/m30-platform.json`, Flight 2's
  `legs/04-routine-evals.md` and its flight-log entry (the commands and
  their output shape).

## Outputs

- The rewritten schedule description; updated tool tests.
- `evals/runs/m33f3-*` (gitignored; never committed).
- `evals/README.md`: one line on the routines tool shape change, if the
  README describes the shapes.
- Flight log entry: session checks, the token cost (before and after), the
  `m30-platform` decision, the per-cell table for both models against the
  baseline, and the gate result.

## Acceptance Criteria

- [ ] AC1. The tool descriptions document only the canonical shape and the
      relative start; the legacy shapes are still accepted (an existing
      alias test passes).
- [ ] AC2. `measure-prompt` ran; the routines-on token cost is recorded
      against Flight 2's 853; the routines-off fingerprint and sizes are
      recorded against `m30-platform` with the run-or-skip decision.
- [ ] AC3. The routines set ran on haiku and gpt-oss at 20 runs per cell;
      `compare --baseline evals/baselines/m33-routines.json` exits 0, with
      the three named cells within their bars on both models.
- [ ] AC4. `tests/test_routine_tools.py`, `tests/test_evals_*.py` pass;
      ruff clean; `THE_ONE_TEST_NETNS=1 make test-unit` passes after the
      model runs finish (15 skipped).
- [ ] AC5. Nothing under `evals/runs/` is staged; no baseline changes.

## Verification Steps

- AC1: the tool tests; `list_tools`-style output in a test.
- AC2-AC3: the run directories and `evals/runs/m33f3-compare.txt`.
- AC4-AC5: the commands; `git status --short evals/`.

## Edge Cases

- The plan token or Ollama unavailable: `[BLOCKED:eval-session]`, never a
  partial gate.
- A cell's bar missed by noise: re-run that cell once and report both
  readings; do not tune checks.

## Files Affected

- `the_one/routines/tools.py`, `tests/test_routine_tools.py`,
  possibly `evals/README.md`, the flight log.

## Citation Audit

Checked at `49a5051a` plus leg 2's working tree:
- `tools.py::_SCHEDULE_SHAPES` (the five legacy kinds), `_SCHEDULE_SCHEMA`
  (embeds it), `_LIMITS_SENTENCE` (leg 2's new text) — verified.
- `evals/README.md` routines scenarios table and `--scenarios-dir` usage;
  Flight 2 leg 4's commands — verified.
