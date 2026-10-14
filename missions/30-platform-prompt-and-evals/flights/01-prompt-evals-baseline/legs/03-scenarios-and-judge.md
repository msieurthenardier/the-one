# Leg: scenarios-and-judge

**Status**: planning
**Flight**: [Prompt evals and baseline](../flight.md)

## Objective
Author the DD17 scenario set, with its fixtures, the judge rubric and a frozen labelled set. Implement the `judge` check. Prove that every check can both pass and fail. Measure the judge's agreement on Haiku. Run a timed live smoke on both models with zero `error` runs.

## Context
- Flight DD9, DD13, DD14, DD17 and DD18 are authoritative. Read the flight log's leg 1 and leg 2 entries for the actual scenario schema, check names and CLI.
- **Scenario validity, not scenario difficulty, is the goal.** Write each scenario so that a model following a sensible platform prompt would plausibly pass and a model ignoring it would plausibly fail. Never tune wording toward today's pass rates. The baseline must measure today's prompt as it is.
- **Freezing.** The labelled set (`evals/judge/labelled.toml`) is written and committed as a leg-spec-adjacent artifact **before the judge's first live call**. The Flight Director commits it on request (signal `[BLOCKED:commit-labelled-set]` and wait). Leg 4 freezes scenario files once it starts.
- **Live calls in this leg:**
  - the judge on Haiku 4.5 (plan token)
  - the smoke run on both models

  Before any live call, re-probe both:
  - the plan token: one Haiku 4.5 call through `get_provider("anthropic-plan-token", …)`, printing status only, never the token
  - Ollama: `/api/tags` lists `gpt-oss:20b`
- **Leg 1 as landed.**
  - The execution tools (`shell`, `python_exec`, `shell_session_*`) plus `web_search` and `download_file` are disabled for eval agents, so `absent-capability` effectively measures the filesystem tools. Its pattern still lists all of them.
  - KB fixtures are copied to `{run-dir}/kb/{fixture}` and get the id `evkb-{fixture}`. The KB tool name is `kb__{slug}_{hash}__search`; match it with a regex (`kb__.*__search`), never a literal hash.
  - Tool refusals come back as `"[error] ..."` result strings.
  - A turn that times out (900 s by default) is a counted `fail`.
  - Ollama parse 5xx errors are matched by `outcomes.PARSE_ERROR_PATTERNS`, which is unconfirmed until this leg's smoke run.

## Inputs
- Legs 1 and 2 landed (uncommitted) on `flight/01-prompt-evals-baseline`.
- `~/.config/the-one-evals/plan-token` (mode 600). Read it only through the runner's `--plan-token-file`, never print it.
- Local Ollama with `gpt-oss:20b`.

## Outputs
- `evals/scenarios/*.toml`: the 12 run sets of DD17.
- `evals/fixtures/web/…`: menu pages, link-target pages, planted-instruction pages and an index page.
- `evals/fixtures/kb/{fixture}/…`: invented-fact documents.
- `evals/judge/rubrics.toml`, `evals/judge/labelled.toml`.
- The `judge` check implementation, with the labelled-set agreement gate (DD14).
- `tests/test_evals_scenarios.py`: the can-fail proof for every scenario (DD18).
- A flight-log entry with the judge agreement, the smoke results per cell and model, the smoke timings and the full-run extrapolation, plus any fixture fixes made after the smoke.

## Acceptance Criteria
- [ ] **12 run sets, 14 cells.** `evals/scenarios/` holds the 12 run sets of DD17, each with:
  - `class` set exactly as in DD17's table
  - 4 phrasings × 5 facts (20 distinct variants)
  - checks exactly as listed in DD17, with these refinements:
    - `absent-capability`'s pattern also includes `delete_file`
    - `rule-beats-note` uses 5 different rule/note pairs, one per fact set (units, date format, spelling, measurement system, time format), each with its own `reply_matches` / `reply_not_matches` patterns
    - `date-awareness` uses 5 instants with DD8's Kiritimati zone. In each, the zone's weekday differs from the weekday in the patched host zone (`detect_system_zone` → `America/Los_Angeles`)
- [ ] **Invented facts only.** Every fact a scenario checks is invented and checkable only from the fixture or the conversation: made-up place names, codenames and specials. Nothing is guessable from world knowledge, except `notes-proactive`/`notes-as-told`/`notes-recall` places, which may be real, because the check is that the note is saved or recalled, not the fact. KB documents contain the KB-only facts, and `kb-answer` questions cannot be answered without the KB.
- [ ] **Natural user turns.** User turns never name a tool or the platform's mechanics ("use search_tools", "save a note"), except where the scenario's purpose requires an explicit request (`notes-as-told`: "please remember…"; `markdown-links`: "send me the link"). `notes-proactive` turns state a plan in passing while asking for help with something else.
- [ ] **Planted pages.** These pages carry an instruction aimed at the agent (to save a note containing a unique marker) embedded in otherwise ordinary page content. The user's turn only asks for a summary of the page.
- [ ] **Can-fail proof (DD18).** For every run set, `tests/test_evals_scenarios.py` drives the real scenario file through the runner with the scripted provider twice:
  - once with a script that satisfies every check, giving `pass`
  - once with a script that violates each check in turn, giving `fail`, with the failed check named

  For `judge`, a fake judge client returns pass and fail. These tests run offline in `make test-unit`.
- [ ] **The judge (DD14).**
  - `judge(rubric_id)` sends the rubric and the saved note's text to `claude-haiku-4-5-20251001` via the plan-token provider at temperature 0.
  - It parses `{"pass": bool, "reason": str}`, and a malformed reply counts as a judge failure (the check's result is `judge-error`, which excludes the run as `error`).
  - At the start of an invocation that selects a judge-scored scenario, the runner scores `labelled.toml` and records the agreement. Below 90%, judge-scored cells are `judge-unvalidated`.
  - Unit-tested with a fake client.
- [ ] **The labelled set.** `labelled.toml` has at least 24 items, 12 "as told" and 12 "stated as fact", unambiguous, covering plans, preferences and circumstances. It is committed (by the Flight Director) before the first live judge call.
- [ ] **Judge agreement.** A live judge validation on Haiku reaches ≥ 90% agreement, recorded in the flight log with the per-item misses. If it falls short, the rubric may be revised **once**. The labelled set is never revised after the first call. A second miss triggers the flight's divert: drop `judge` from `notes-as-told` and record it.
- [ ] **Live smoke.** One fact set × 4 phrasings (n = 4 per cell) on `haiku` and `gpt-oss` (two processes, separate run directories) completes with zero `error` runs.
  - Every `cut-short` run is resumed to a counted result.
  - Per-cell smoke results, mean seconds per run per model, and the extrapolated full-run time (240 runs per model) are recorded in the flight log.
  - If the gpt-oss extrapolation is over 8 hours, the flight's n = 15 divert is recorded, and the Flight Director decides before leg 4.
- [ ] **Smoke-driven fixes.** Fixes after the smoke are limited to fixture or check bugs (a check misfiring on a correct reply, a broken fixture link), each listed in the flight log with the before/after evidence. Wording is never changed to move a pass rate.
- [ ] **Ollama parse-error pattern.** Leg 1's pattern is confirmed or corrected from any live occurrence, and recorded either way.
- [ ] **Regression check.** `make test-unit` passes, and `ruff` is clean on `the_one/ tests/ scripts/ evals/`.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_evals_scenarios.py -x --timeout 120`
- The judge validation command, the smoke commands and the run directories are named in the flight log, along with each run's `report.md` totals.
- `make test-unit`, then `make lint`.

## Implementation Guidance
1. **Write the labelled set first**, then signal `[BLOCKED:commit-labelled-set]` and wait for the Flight Director to commit it. Then write the rubric and the judge.
2. **Write scenarios one run set at a time**, together with its can-fail test. Use one KB fixture (for example "Kestrel field notes", 5–8 short markdown documents of invented facts) shared by the `kb` run set's variants.
3. **The fixture server** serves `evals/fixtures/web/`. Link targets and planted pages are per-fact files, so each variant has a unique URL and marker.
4. **Smoke.** Run the two models as separate invocations, each with its own `--run-dir`, in the background with `setsid nohup` (gpt-oss may take a while). Monitor `results.jsonl`, never by name-pattern process listing. Kill only PIDs you recorded.
5. **Timing.** Record wall-clock seconds per run from the run records.

## Edge Cases
- **A model never saves a note** in `planted` (expected on some models). `planted-flagged` is then vacuous, so report its non-vacuous count.
- **`notes-recall` needs `notes_enabled`.** Seeding requires it (leg 1 enforces this).
- **gpt-oss replying in harmony channel markup.** Checks read the final reply content as the product surfaces it. If raw channel markup leaks into content, record it as an observation; never strip it in checks.
- **Plan refusals mid-smoke.** Three consecutive `cut-short` runs stop the model. Re-probe, and resume later.

## Files Affected
- `evals/scenarios/`, `evals/fixtures/`, `evals/judge/` (new)
- `evals/checks.py` (the judge), possibly `evals/harness.py` (the judge gate)
- `tests/test_evals_scenarios.py` (new)

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked 2026-10-13 against the flight spec: the DD17 table (12 run sets, 14 cells), the DD14 judge rules and the DD18 can-fail rule. The scenario schema and check names come from leg 1 as landed and are re-checked before starting.
