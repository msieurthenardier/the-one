# Squawk 0336: `evals/README.md` omits the secrets layer from platform prompt text

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-07
**Completed**: 2026-11-14

## Report
`evals/README.md`'s list of platform prompt text does not include the secrets prompt layer `the_one/db/_secrets.py` (added in sortie 10). `CLAUDE.md`'s "Prompt evals" paragraph does include it. A contributor who goes by the README could change the secrets layer without the eval comparison the convention requires.

## Evidence
- `evals/README.md:299`: "Platform prompt text is `the_one/agent/platform_prompt.py`, the rules and notes layers in `the_one/db/_rules.py` and `the_one/db/_notes.py`, …" (no `_secrets.py`).
- `CLAUDE.md` "Prompt evals": "the rules, notes and secrets layers in `the_one/db/_rules.py`, `the_one/db/_notes.py` and `the_one/db/_secrets.py`".
- Found at the sortie 11 debrief (`sorties/11-tool-exposure-for-small-models/flight-debrief.md`, Documentation).
- Also check `evals/README.md:236`, which describes what the `platform` part measures, for the same omission.

## Corrective Action
In `evals/README.md`: the "## Convention" list of platform prompt text now says "the rules, notes and secrets layers in `the_one/db/_rules.py`, `the_one/db/_notes.py` and `the_one/db/_secrets.py`", matching `CLAUDE.md`. For the "Token measurement" paragraph (the `platform` part list), a check of `evals/` found no measured configuration with secret grants (no `secret_ids` or `_secrets` use under `evals/`), so the layer is not one of the measured parts. The README now says so in one sentence instead of claiming the layer is measured.

## Verification
`grep -n "_secrets" evals/README.md` names the layer wherever `CLAUDE.md` does. The existing doc and eval tests pass: `.venv/bin/python -m pytest tests/ -q -x --timeout 60 -k "evals or docs"`.

Done: `grep -n "_secrets" evals/README.md` names the layer in the Convention list and the Token measurement note. Ran `tests/test_evals_cli.py` and the other doc-reading unit files (`test_routine_log_vocabulary.py`, `test_studio_editor_contracts_static.py`, `test_store_static.py`, `test_shell_write_hook.py`): 141 passed. The broad `-k "evals or docs"` run over `tests/` was not run (full-suite runs are left to the Flight Director).

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
