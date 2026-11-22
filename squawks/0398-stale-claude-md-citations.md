# Squawk 0398: Code and the MCP README cite CLAUDE.md sections that no longer exist

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: 2026-11-21

## Report
Several files cite `CLAUDE.md` sections that are gone, some before squawk 0397 pared `CLAUDE.md`
back and the rest by it. Found by the 2026-11-21 turnaround's Reviewer. Repoint each citation to the
doc that now holds the material (usually `the_one/agents.md`). Where the cited material, such as the F3
sandbox catalog message text, is in no doc, write it into `the_one/agents.md` from the code. Doc and
comment only.

## Evidence
- `the_one/mcp/README.md:15`, `:354`, `:398`, `:491`: "`CLAUDE.md`'s F3 contracts §5/§7",
  "F3 (MCP Sandbox) Contracts" section, contract #5.
- `the_one/mcp/__init__.py:8`: `See CLAUDE.md "F2 (MCP Client Foundation) Contracts" for invariants.`
- `the_one/self_configuration/credentials.py:42`: "two processes sharing a data dir" is already
  unsupported per CLAUDE.md's ….
- `the_one/db/schema.py:798`: a comment citing a rule "in CLAUDE.md".

## Corrective Action
Repointed each citation to the doc that now holds the material (comment and doc only; Mission 36
Flight 4 Leg 4a):
- `the_one/mcp/README.md` (four citations): the F3 sandbox boundary catalog (§5, contract #5) now
  points at `the_one/agents.md` "Sandbox seam — platform-wide" item 4 (the `SandboxError`
  boundary), with the verbatim message text in `the_one/mcp/errors.py`; the `HOME=/tmp` override
  (§7) points at item 6 "HOME policy" of the same section.
- `the_one/mcp/__init__.py`: `the_one/agents.md` "MCP F2 Client Foundation".
- `the_one/self_configuration/credentials.py`: `SECURITY-MODEL.md` "Single-process-at-a-time
  assumption".
- `the_one/interfaces/web/static/js/areas/admin/system-page.js` (comment): `SECURITY-MODEL.md`
  "Agent notes (M27 F2)".

No cited contract was missing from the docs: the sandbox catalog's text lives in
`the_one/mcp/errors.py` (item 4 says so), so nothing needed writing into `the_one/agents.md`. The
`the_one/db/schema.py:798` citation named in the report no longer matches the grep (no `CLAUDE.md`
citation in that file at this commit); it is outside this leg's MCP and self-configuration scope.

## Verification
`grep -rn 'CLAUDE.md' the_one/ scripts/ evals/` shows only citations of sections `CLAUDE.md` has
("Per-area browser test lanes", "Prompt evals") or historical "moved from CLAUDE.md" notes in
`the_one/agents.md`; each repointed heading exists in its target (grep of `^### Sandbox seam`,
`^### MCP F2 Client Foundation` in `the_one/agents.md`; "Single-process-at-a-time assumption" and
"### Agent notes (M27 F2)" in `SECURITY-MODEL.md`).

The `the_one/db/schema.py` citation was repointed to `the_one/agents.md` in Mission 36 Flight 4
Leg 1b (Batch A, `f4ee1a12`).

## Sign-Off
**Reviewer**: the Flight 4 Batch A and Batch B Reviewers (Sonnet, security tier).
**Verdict**: confirmed; both batches signalled `[HANDOFF:confirmed]`, and the citations are
repointed to headings that exist.
**Commit**: the `db/schema.py` part is in `f4ee1a12` (Batch A), on
`flight/04-mcp-servers-and-providers`. The rest is in the Batch B checkpoint commit on the same
branch.
