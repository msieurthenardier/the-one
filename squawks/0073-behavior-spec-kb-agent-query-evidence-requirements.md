# Squawk 0073: `kb-agent-query-round-trip`'s assertions depend on evidence the spec never requires

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: 2026-09-18

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

Edited `tests/behavior/kb-agent-query-round-trip.md` in place (step numbering
and the `**Status**`/`**Last Run**` header untouched — the recorded 8/8 run
remains valid for what it tested):

1. **Step 9** — Actions now require an immediate `GET
   /api/agents/kbq-attached` after the blacklisting `PUT`, confirming `kb_ids`
   still equals `[kb_id]` before driving any turn. Expected Results names the
   distinguishing assertion explicitly: this readback is what tells a working
   blacklist apart from a silent `kb_ids` wipe, since the two produce a
   byte-identical `tool_result`.
2. **Step 2** — Actions now require issuing the trigger `POST` and the status
   polling loop from a single shell invocation, recording a wall-clock
   timestamp for the trigger response and for every poll sample. Expected
   Results now judges the 60 s bound from those recorded timestamps rather
   than from wall-clock impression.
3. **Step 7** — Actions now require confirming, from the `POST
   /api/chat/sessions` create response and/or the `session_joined` frame,
   that the session belongs to `kbq-detached` before driving the turn.
   Expected Results states that confirmation as its own assertion.
4. **Steps 7 and 9** — Actions in both rows now require capturing the
   matching `tool_result`'s content in full, verbatim, with byte count
   recorded against the captured string's length as the completeness
   criterion (the same criterion the first run used ad hoc). Expected
   Results in both rows notes the capture was complete, so the "contains
   neither X nor Y" absence claims are provable rather than inferred from an
   excerpt.
5. **Preconditions** — added two pinned bullets alongside the existing `/ws`
   protocol block: `POST /api/chat/sessions`'s request shape
   (`{"agent_name": "<name>"}`), and the nested `tool_result` shape — a
   `role: "tool"` message carries a top-level `content` string *and* a
   nested `tool_result` object, and only the nested object carries
   `is_error` and `tool_call_id`, which every isolation assertion (Steps 7
   and 9) depends on.

**Step 6 widened** beyond the five required changes, per the additional
instruction: the row now drives two turns. The first uses an empty
`search_tools` query (unfiltered), asserting both a `kb:KBQ-test:`-grouped
entry and a `built-in:`-grouped entry appear in the same result — making the
groups' distinctness demonstrable rather than inferred, since the original
`KBQ-test`-narrowed query structurally cannot surface a `built-in:` entry.
The second turn keeps the original narrowed-query assertion (`kb__KBQ-test__search`
grouped under `kb:KBQ-test:`).

No steps were renumbered, no `Out of Scope`/`Variants`/header content
changed, and no other file under `tests/behavior/` was touched.

## Verification

- `git diff -- tests/behavior/kb-agent-query-round-trip.md` reviewed: only Preconditions and Steps 2, 6, 7, 9 changed; step count, numbering, and the `**Status**`/`**Last Run**` header are unchanged.
- This squawk did not re-run the behavior test (`/mission-control:behavior-test kb-agent-query-round-trip`) — that is a live-instance run against a dedicated dev port/data-dir per CLAUDE.md's SAFETY RULE, and re-running was not requested as part of this implementation pass. The expected verification is a future re-run passing with no Flight-Director-supplied evidence requirements beyond the spec text; that re-run is left for the Flight Director / next test cycle.
- Markdown-only change; not a `ruff`-scanned path — `make lint` (`ruff check the_one/ tests/ scripts/`) is unaffected and was run clean as part of this batch regardless.

## Sign-Off

**Reviewer**: batch Reviewer agent (**Sonnet** tier — the diff touches the encryption-rotation endpoint and a dependency floor for a package inside the shipped frozen closure, both security-sensitive surfaces per `.flightops/agent-crews/leg-execution.md`, even though every change is comment-, doc- or version-only)
**Verdict**: confirmed
**Commit**: `d76d173`
