# Squawk 0077: Record the crowding arithmetic in `_fuse`'s docstring

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: —

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

*(written at completion)*

## Verification

*(written at completion — expected: the docstring states the inequality and
its consequence; `make lint` clean)*

## Sign-Off

*(written at completion)*
