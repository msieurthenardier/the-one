# Squawk 0008: Revision-history UI mislabels `external` revisions as "self-revised"

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-27
**Completed**: 2026-08-29

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

`the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js`:

- Replaced the two-way `rev.source === 'restore' ? 'restored' : 'self-revised'` ternary
  at (former) `:1011` with a three-way `if`/`else if`/`else`: `'restore'` → `restored`,
  `'external'` → `external`, plus, when `rev.source_principal` is a non-empty string,
  `external (<principal>)` (e.g. `external (ext_abc123)`) — the credential identifier,
  never the secret; anything else (including the existing `'self'` value) falls through
  to the unchanged default `self-revised`, so the change is backward-compatible for
  every existing revision row. The label is still assigned via `metaText.textContent`
  (never `innerHTML`), so the interpolated identifier is auto-escaped.
- Updated the stale header comment (former `:49-50`) from "source (self/restore)" to
  "source (self/restore/external)".
- Confirmed `entry.setAttribute('data-source', rev.source)` (former `:980`) already
  carries the raw, untransformed value — no change needed there; the new browser test
  asserts against it directly (`[data-source="external"]` / `[data-source="self"]`).

## Verification

Extended `tests/browser/test_studio_self_configuration_history.py`:

- `_seed_applied_revision` gained optional `source` (default `"self"`, unchanged
  behavior for existing callers) and `source_principal` (default `None`) parameters,
  now passed through to the `agent_revisions` INSERT (schema v37 columns).
- Added `test_history_labels_external_source_distinctly`: seeds one `source='self'`
  revision and one `source='external'` revision with `source_principal='ext_abc123'`
  on the same agent, then asserts the rendered `.history-entry-meta-text` reads
  `external (ext_abc123) · …` for the external row and `self-revised · …` for the self
  row (matched via each entry's `data-source` attribute).
- `.venv/bin/ruff check` and `.venv/bin/ruff format --check` pass on the test file.
- `THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser
  tests/browser/test_studio_self_configuration_history.py -x --timeout 120 -q` — all 4
  tests in the file pass (3 pre-existing + 1 new).

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-29; Sonnet — batch touches `api_credential.py`, the DB import graph, and self-configuration identity)
**Verdict**: confirmed
**Commit**: `{sha}` on `squawk/turnaround-2026-08-29` — PR #{pr}

Full unit suite at close-out: 4586 passed, 10 skipped, 704 deselected, 20 warnings in 557.56s (0:09:17).
**Reviewer**:
**Verdict**:
**Commit**:
