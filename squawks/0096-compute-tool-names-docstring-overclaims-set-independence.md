# Squawk 0096: `compute_tool_names`' docstring asserts set-independence unconditionally; the widening loop is the exception

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: —

## Report

The docstring states, without qualification, that a derived tool name is a pure
function of `(kb.name, kb.id)` and independent of the set it is computed with.
The collision-widening loop directly below it is exactly the case where that is
false: under a forced collision, a name computed within a set widens its
discriminator, while the same knowledge base computed alone does not — so the
two disagree.

The residual **was** recorded, in the Flight 6 flight spec. It is absent from
the docstring, which is what the next reader reaches: Flight 7's DD-13 first
draft quoted this docstring as if it were control flow and was falsified at
Architect review cycle 1. The claim has already cost one review cycle.

Practical exposure is nil (a collision needs equal truncated slugs *and* a
32-bit sha256 prefix collision, and `kb_id` is a PRIMARY KEY). This is a
documentation defect, not an operational one — but it is the kind that costs
another review cycle.

## Evidence

- `the_one/knowledge/tool_provider.py:124` — "independent of the composition of
  the set it happens to be computed with (AC-1, AC-2)", stated unconditionally.
- `the_one/knowledge/tool_provider.py:181` — `for _ in range(len(_HASH_LENGTHS)):`,
  the widening loop that makes the claim conditional.
- Mission 24 debrief, "Architect's Assessment": *"on the record in the place
  nobody reads and absent from the place everybody reads."*

## Corrective Action

*(written at completion)*

One sentence in the docstring at the point of the claim, naming the widening
loop as the exception.

## Verification

Read-back: the docstring's claim matches the function's behaviour under both the
no-collision and forced-collision cases.

## Sign-Off

*(written at completion)*
