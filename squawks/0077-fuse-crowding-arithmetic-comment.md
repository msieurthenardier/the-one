# Squawk 0077: Record the crowding arithmetic in `_fuse`'s docstring

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: 2026-09-18

## Report

`the_one/knowledge/retrieval.py::_fuse` implements a reserved-slot rule: when
both retrieval sides return, one result slot is reserved for a keyword-only
hit. The *mechanics* are fully self-documenting in the module — when it
fires, what it does, and the two distinct senses of "keyword side" that
produced two high-severity review findings during design.

What the module does **not** state is the quantitative justification: that
plain reciprocal rank fusion at `candidate_k = 25` makes it *mathematically
inevitable* — not merely likely — that any chunk appearing in both result
lists outranks a keyword-only rank-1 hit. `2/(60+r) > 1/61` holds for all
`r <= 61`, so five both-list chunks displace the exact-term hit to rank 6 and
out of a five-result window.

That arithmetic exists only in `flight.md`'s DD-3 and a one-line test
comment. A maintainer six months out would know the rule fires and how, but
would have to take "this is structurally necessary, not just prudent" on
faith — or dig through the flight archive to check it is not an overcautious
guard that could safely be deleted. Given the rule exists precisely to
satisfy a mission criterion, that is the wrong thing to leave implicit.

One or two sentences in `_fuse`'s docstring closes it.

## Evidence

`the_one/knowledge/retrieval.py::_fuse` — implements the rule; no arithmetic
in the docstring.
`missions/24-knowledge-bases/flights/05-agent-query/flight.md`, DD-3 — carries
the arithmetic.
`tests/test_kb_retrieval.py` — the strict-bar test's comment carries a
one-line version ("each score >= 2/61, keyword-only hit scores 1/66").

## Corrective Action

Added two sentences to `the_one/knowledge/retrieval.py::_fuse`'s docstring,
appended after the existing reserved-slot-rule paragraph and before the
closing `"""` — no restructuring of the existing prose. The addition states
the inequality (`2/(60+r) > 1/61` for all `r <= 61`) and its consequence
(any both-list chunk outranks a keyword-only rank-1 hit at
`candidate_k = 25`, and five such chunks displace the exact-term hit past a
five-result window), framed as "the reserved slot is structurally
necessary, not merely prudent" per the Report's own phrasing. Kept to two
sentences and matched the module's existing voice (double-backtick code
refs, em-dash asides, no restructuring of the surrounding paragraphs).

Did not touch `_fuse`'s logic, the module docstring, or any other function —
this is a pure docstring addition. Considered also cross-referencing the
new `flight.md` DD-3 citation or the test comment, but the squawk's Report
already names those as the Evidence for where the arithmetic previously
lived only implicitly; duplicating that citation inside the docstring itself
would add a third place to keep in sync for no reader benefit, so the
docstring states the arithmetic directly instead of pointing elsewhere.

## Verification

`the_one/knowledge/retrieval.py::_fuse`'s docstring now states the
inequality and its consequence, immediately following the reserved-slot
rule it justifies. `make lint` (`ruff check` + `ruff format --check`) is
clean. `tests/test_kb_retrieval.py` (31 tests, includes the strict-bar test
whose comment carried the one-line version of this arithmetic) passes
unchanged — confirms the docstring-only edit introduced no behavioral
change.

## Sign-Off

**Reviewer**: batch Reviewer agent (**Sonnet** tier — the diff touches the encryption-rotation endpoint and a dependency floor for a package inside the shipped frozen closure, both security-sensitive surfaces per `.flightops/agent-crews/leg-execution.md`, even though every change is comment-, doc- or version-only)
**Verdict**: confirmed
**Commit**: `PENDING`
