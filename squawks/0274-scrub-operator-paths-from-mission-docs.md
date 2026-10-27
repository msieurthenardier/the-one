# Squawk 0274: Remove the operator's username and home paths from mission docs

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-27
**Completed**: —

## Report
Older Flight Control artifacts quote absolute paths that carry the operator's username and home directory (WSL home paths, Windows profile paths). The operator asked (2026-10-27, sortie 06 debrief) that paths in planning docs be de-identified. Replace them with placeholders (`<home>`, `<user>`, `<repo>`, `<main checkout>`) without changing meaning. Sortie 06's own flight log was scrubbed on its debrief branch.

## Evidence
- `grep -rln "<operator username>" missions/` lists 119 files at `3b3d42a` (the literal username is not repeated here); examples: `missions/01-structural-foundation/flights/01-architecture-blueprint/legs/01-target-architecture.md`, `missions/16-llm-provider-hardening/flights/02-anthropic-tool-input-schema/legs/01-sanitize-tool-schema.md`, `missions/25-workbench-navigation/flights/05-window-chrome/legs/01b-windows-apparatus-input.md`.
- Also check `sorties/`, `squawks/`, `maintenance/`, `tests/behavior/` runs and `docs/`.

## Corrective Action
*(written at completion)*

## Verification
`grep -rn` for the username and its home-path forms over the artifact directories returns nothing; a spot-read of edited files shows the placeholders keep each sentence's meaning.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
