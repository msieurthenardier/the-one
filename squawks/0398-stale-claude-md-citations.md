# Squawk 0398: Code and the MCP README cite CLAUDE.md sections that no longer exist

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: —

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
*(written at completion)*

## Verification
`grep -rn 'CLAUDE.md' the_one/ scripts/ evals/` shows no citation of a section `CLAUDE.md` lacks;
each repointed heading exists in its target (grep).
