# Squawk 0096: `compute_tool_names`' docstring asserts set-independence unconditionally; the widening loop is the exception

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: 2026-11-03
**Related**: 0098, 0099: docstring and doc claims that overstate the knowledge/vector code; complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

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

`compute_tool_names`' docstring (`the_one/knowledge/tool_provider.py`) now names the
uniqueness-widening loop (step 4) as the exception to set-independence.

## Verification

Read-back against the code: no collision, the name depends only on `(kb.name, kb.id)`;
under a forced hash collision the loop widens only the colliding names, as the docstring
now says. Doc-only change; unit tier run at the end of the batch.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
