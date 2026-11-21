# Squawk 0391: Remove the type-ignore sites in the proposals code

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: 2026-11-21

## Report
Mission 36 Flight 2 left five `# type: ignore[...]` comments in the GleepGlorp
proposals code. Each hides a typing mismatch that a narrower type or an explicit
cast would state, so a later change cannot slip through unchecked. Raised in the
Flight 2 debrief (Developer interview).

## Evidence
- `the_one/gleepglorp/proposals/tool.py:74` — `async def execute(  # type: ignore[override]`
- `the_one/gleepglorp/proposals/shape.py:477` — `raise _bad(spec_for("agent", "provider"), ...)  # type: ignore[arg-type]`
- `the_one/gleepglorp/proposals/apply.py:322` — `return await _resolved(conn, repo, proposal_id)  # type: ignore[return-value]`
- `the_one/gleepglorp/proposals/apply.py:461` and `:482` — `flag=flag,  # type: ignore[arg-type]`

## Corrective Action
All five `# type: ignore` comments removed; no runtime behaviour changed.
- `apply.py:apply_proposal`: `cast(ProposalApplyResult, await _resolved(...))` with a reason comment (the helper returns `| None`).
- `apply.py:_apply_routine`: `flag` annotated `Flag` (imported from `routines.repository`), which fixes both `flag=flag` sites; `data` annotated `dict[str, Any]` (also clears two adjacent mypy errors).
- `shape.py` (provider branch): `cast(FieldSpec, spec_for("agent", "provider"))` with a reason comment.
- `tool.py:ProposeChange.execute`: the ignore was unnecessary (mypy accepts the override of `Tool.execute(**kwargs)`); removed, base signature untouched.

## Verification
The five comments are gone (or each that must stay carries a one-line reason);
`ruff check` clean; the proposals unit files
(`tests/test_gleepglorp_proposals_*.py`) pass unchanged.

Ran (results):
- `uvx mypy --ignore-missing-imports --follow-imports=silent the_one/gleepglorp/proposals/`: with the ignores in place 5 errors (3 pre-existing in `shape.py:612-613`, a variable `f` re-bound to a string, out of scope; 2 `dict[Literal...]` arg-type in `apply.py`); after: 3 errors (the same pre-existing `shape.py` ones). No error on any former ignore site.
- `ruff check` and `ruff format --check` on the three files: clean.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_gleepglorp_proposals_*.py -x --timeout 60`: 146 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the security tier, since the batch changed the shell-write hook and CLAUDE.md's safety rules), batch review of squawks 0368, 0379, 0384, 0385, 0391-0397
**Verdict**: confirmed; mypy re-run not repeated by the Reviewer (not installed in the venv), the Developer's `uvx mypy` result accepted
**Commit**: `squawk: turnaround 2026-11-21` on squawk/turnaround-2026-11-21
