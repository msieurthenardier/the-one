# Squawk 0097: Exhausted collision-widening returns a colliding name, which silently overwrites a registered tool

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: —

## Report

When `compute_tool_names`' widening loop exhausts every length in
`_HASH_LENGTHS`, it returns the last computed set best-effort rather than
raising — deliberately, so the rest of the attachment still builds. But that set
may contain two identical names, and tool registration is a plain dict
assignment with no duplicate check. The second registration overwrites the
first, so an agent **silently loses one knowledge base's search tool** with no
error anywhere — no raise, no log at the registration site, nothing in the UI.

Astronomically unlikely to fire. Trivially cheap to make loud. The failure mode
is silence, which is what makes it worth closing rather than tolerating.

## Evidence

- `the_one/knowledge/tool_provider.py:202-205` — "Exhausted widening —
  astronomically unlikely … Best-effort: return the last computed set rather
  than raising", returning a possibly-colliding mapping.
- `the_one/tools/base.py:189` — `self._tools[tool.name] = tool`, an unguarded
  dict assignment: last writer wins, silently.

## Corrective Action

*(written at completion)*

Make the exhausted-widening path loud — a WARNING/ERROR naming both colliding
kb_ids at the point the colliding set is returned. Scoped to that path; this
squawk does **not** change `ToolRegistry.register`'s general contract, which
other callers depend on.

## Verification

Force the collision the way the Mission 24 Architect did — monkeypatch the
discriminator to collapse at every length — and assert the diagnostic fires.

## Sign-Off

*(written at completion)*
