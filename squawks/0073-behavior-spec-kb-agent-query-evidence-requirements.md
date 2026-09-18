# Squawk 0073: `kb-agent-query-round-trip`'s assertions depend on evidence the spec never requires

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: —

## Report

The spec passed 8/8 on its first run, but three of those eight verdicts were
defensible only because the Flight Director supplied evidence requirements
mid-run that the spec text does not state. A future run following the spec
exactly could omit them and still report PASS.

**The sharp one — Step 9 can produce a false PASS.** It asserts only the
shape of the tool result (`is_error: true`, no fixture content). But a
silent `kb_ids` wipe during the full-replace `PUT` produces a
**byte-identical** error to a correctly-applied blacklist — the run log
confirms Steps 7 and 9's content match character-for-character at 67 bytes.
The spec cannot distinguish "the blacklist worked" from "the attachment was
wiped and the blacklist was irrelevant."

Note the asymmetry: Step 8 carries the same full-replace hazard but is
**self-revealing** — a wiped attachment makes the tool vanish and the row
fails visibly. Only Step 9 converts the same mistake into silence, because
its expected observable is *itself* an error.

**Four further unwritten requirements**, each supplied ad hoc:
1. Step 2's single-shell-invocation timestamp capture (without it the 60 s
   bound reverts to unjudgeable — the squawk-0069 failure mode).
2. Step 7's session-identity confirmation (an unknown-tool error proves
   nothing about isolation without knowing which agent produced it).
3. Byte-counted complete `tool_result` capture for Steps 7 and 9 (an absence
   cannot be proven from an excerpt).
4. `POST /api/chat/sessions`'s request shape and the **nested** `tool_result`
   path — neither pinned; only the nested object carries `is_error` and
   `tool_call_id`, which every isolation assertion depends on.

**Step 6 is separately weak**: "distinct from the `built-in:` group" is not
demonstrable under the row's own Actions, since a query narrowed to
`KBQ-test` structurally cannot return a `built-in:` group. The Validator
passed it on the labelling-scheme reading and flagged it "adequate, not
solid".

## Evidence

`tests/behavior/kb-agent-query-round-trip/runs/2026-09-17-22-08-29.md`,
Operator Notes. Validator's closing, same file: "Step 9 would have been
INCONCLUSIVE without the post-PUT `kb_ids` GET… the tool_result evidence
alone is symmetric between the two causes."

Steps 7 and 9 tool-result content, verbatim and identical:
`[error] Tool execution failed: 'Unknown tool: kb__KBQ-test__search'`

## Corrective Action

*(written at completion — expected: bake the post-update readback into Step
9's Expected Results; widen Step 6 to a query returning both groups, or add a
variant; write the four evidence requirements into the spec's step text and
Observables Required)*

## Verification

*(written at completion — expected: a re-run of
`/mission-control:behavior-test kb-agent-query-round-trip` passes with no
Flight-Director-supplied evidence requirements beyond the spec text)*

## Sign-Off

*(written at completion)*
