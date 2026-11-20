# Squawk 0391: Remove the type-ignore sites in the proposals code

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: —

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
*(written at completion)*

## Verification
The five comments are gone (or each that must stay carries a one-line reason);
`ruff check` clean; the proposals unit files
(`tests/test_gleepglorp_proposals_*.py`) pass unchanged.

## Sign-Off
*(written at completion)*
