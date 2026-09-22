# Squawk 0080: Studio agent save writes `mcp_source_ids` with no load-success gate

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-17
**Completed**: —

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
