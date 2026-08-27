# Squawk 0008: Revision-history UI mislabels `external` revisions as "self-revised"

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: —

## Report

The Studio self-configuration tab's revision-history rows label a revision's source
with a two-way ternary that predates the `external` source value (added in Mission 21
Flight 3, Leg 2). Anything that is not `restore` is labeled **"self-revised"** — so a
revision made by an **external** principal is displayed as "self-revised", which is
misleading now that external clients can write. The provenance is present in the data
(the row carries `data-source="external"` and the API returns `source`/`source_principal`)
but the human-visible label collapses `self` and `external` into one.

Fix: extend the source-label mapping to render `external` distinctly (e.g. "external"),
and optionally surface the external principal identifier (`source_principal`, safe to
display — it is the credential identifier, never the secret). Purely presentational — no
backend, schema, or API change. Sourced from the Mission 21 Flight 3 debrief Action Items.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js:1011` —
  `var sourceLabel = rev.source === 'restore' ? 'restored' : 'self-revised';` (the
  else-branch swallows `source === 'external'`). The meta line is built at `:1013`
  (`sourceLabel + ' · ' + rev.status + …`). The true value is already on the element:
  `:980 — entry.setAttribute('data-source', rev.source)`.
- The header comment at `:49-50` still describes entries as showing "source
  (self/restore)" — written in Flight 2 before `external` existed.
- API already returns the fields: `GET /api/agents/{name}/self-configuration/revisions`
  returns each revision via `model_dump()`, including `source` and `source_principal`
  (M21 F03 L02).

## Corrective Action
*(written at completion)*

## Verification
*(written at completion — a DOM/browser test asserting an `external` revision row shows
the distinct label, mirroring `tests/browser/test_studio_self_configuration_history.py`)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
