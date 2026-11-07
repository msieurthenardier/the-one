# Squawk 0336: `evals/README.md` omits the secrets layer from platform prompt text

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-07
**Completed**: —

## Report
`evals/README.md`'s list of platform prompt text does not include the secrets prompt layer `the_one/db/_secrets.py` (added in sortie 10). `CLAUDE.md`'s "Prompt evals" paragraph does include it. A contributor who goes by the README could change the secrets layer without the eval comparison the convention requires.

## Evidence
- `evals/README.md:299`: "Platform prompt text is `the_one/agent/platform_prompt.py`, the rules and notes layers in `the_one/db/_rules.py` and `the_one/db/_notes.py`, …" (no `_secrets.py`).
- `CLAUDE.md` "Prompt evals": "the rules, notes and secrets layers in `the_one/db/_rules.py`, `the_one/db/_notes.py` and `the_one/db/_secrets.py`".
- Found at the sortie 11 debrief (`sorties/11-tool-exposure-for-small-models/flight-debrief.md`, Documentation).
- Also check `evals/README.md:236`, which describes what the `platform` part measures, for the same omission.

## Corrective Action
*(written at completion)*

## Verification
`grep -n "_secrets" evals/README.md` names the layer wherever `CLAUDE.md` does. The existing doc and eval tests pass: `.venv/bin/python -m pytest tests/ -q -x --timeout 60 -k "evals or docs"`.
