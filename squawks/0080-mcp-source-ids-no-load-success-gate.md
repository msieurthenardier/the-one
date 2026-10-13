# Squawk 0080: Studio agent save writes `mcp_source_ids` with no load-success gate

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: 2026-10-13

## Report

`collectFormData` builds `mcp_source_ids` by walking
`[data-mcp-source-toggle][data-mcp-source-id]` and keeping the checked ones,
**unconditionally** — there is no check that the MCP source list actually
loaded. `refreshMcpSourcesCache`'s `.catch` keeps the prior cache
(`self._allMcpSources || []`), which on a first mount after a failed fetch is
`[]`. The MCPs tab then renders zero rows, every row is trivially unchecked, and
the next save PUTs `mcp_source_ids: []` as though the operator had deliberately
detached every MCP server.

This is the **same defect shape as squawk 0050** (`kb_ids: []` on every save),
one field over, and it was found while designing the fix for that one: Mission
24 Flight 6's DD-4 closes the `kb_ids` path on both sides (a client-side
load-success marker plus a server-side keep-on-omit in `update_agent`), and
`mcp_source_ids` has neither.

Unlike squawk 0050 at the time it was filed, this one is **not latent** —
`mcp_source_ids` is functional today.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio.js::collectFormData` —
  `data.mcp_source_ids = []` then filled from the checked toggles, with no
  equivalent of DD-4's `data-kb-list-loaded` gate.
- `the_one/interfaces/web/static/js/areas/studio.js::refreshMcpSourcesCache` —
  `.catch(function () { self._allMcpSources = self._allMcpSources || []; })`;
  the promise always resolves, so a caller cannot distinguish success from
  failure.
- `the_one/interfaces/web/api.py::update_agent` — preserves `mcp_overrides`,
  `self_revision_requires_approval` and (as of Flight 6 Leg 2) `kb_ids` on
  omission. **`mcp_source_ids` is not preserved.**
- Precedent for the shape: `squawks/0050-*.md`.

## Disposition

**Deferred**: found mid-flight during Mission 24 Flight 6 Leg 3's design review,
outside that flight's chartered surface. Folding it into the leg in hand would
have widened a leg already tiered high on three caches, and it is not
`grounding` — it does not sit in Flight 6's path.

**Revisit when**: the MCP attach surface is next touched, or at the first
planning conversation that can take the pair together. Note that the fix likely
needs **both halves**, mirroring DD-4 — a client-side load-success gate *and* a
server-side keep-on-omit in `update_agent`. The server half changes omission
semantics on a shared interface with existing consumers, so if that proves true
this **fails the squawk qualification gate on blast radius** and should be
escalated to a flight rather than completed as a squawk. Squawk 0050 took
exactly that path: filed as a squawk, then absorbed into Flight 6 once it turned
out to need a design decision (DD-4).

## Corrective Action

Client-side only, in `the_one/interfaces/web/static/js/areas/studio.js`. Added
`self._mcpSourcesLoaded` (false at start, set true by `loadAllImpl` and by a
successful `refreshMcpSourcesCache`; a later failed refresh does NOT reset it,
because the last good cache is what the MCPs tab keeps rendering).
`collectFormData` now builds `mcp_source_ids` from the checked toggles only when
the flag is true (or in create mode); otherwise it sends the agent's stored
`mcp_source_ids` (`self._selectedAgent`) back unchanged.

Why not omit the key like `kb_ids`: `update_agent` preserves an omitted `kb_ids`
but NOT `mcp_source_ids` (the `AgentConfig` default `[]` would wipe it), and
adding a server-side keep-on-omit changes a shared interface's omission
semantics, which this squawk's disposition flagged as escalation territory.
Sending the stored value needs no server change.

Findings: (1) `kb_ids` has no remaining bug (client marker plus server
keep-on-omit). (2) The failure path is narrower than the report implies:
`loadAll` always runs first and its failure blanks the whole Studio area
(squawk 0014), so a refresh failure normally leaves a good cache. The gate is
therefore defensive, and the regression test cannot fail without the fix
(it pins the end-to-end behaviour only).

## Verification

- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh tests/browser/test_studio_mcps_tab.py -m browser -x --timeout 60`: 11 passed (includes new `test_save_after_failed_mcp_sources_fetch_keeps_attachments`).
- `tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py`: 285 passed.
- `ruff check` / `ruff format` on the test file: clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget. Reviewer note (non-blocking, accepted): the new browser test is an end-to-end pin only and passes with or without the fix, because the guarded state (an editor mounted with no successful MCP list load) is unreachable in a browser while a failed `loadAll` blanks the area (squawk 0014); `studio.js` has no unit seam. The gate is defensive.
