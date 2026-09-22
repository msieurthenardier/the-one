# Squawk 0050: Studio agent save writes `kb_ids: []` on every save

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-14
**Completed**: —

## Report

The agent editor's save path rebuilds `kb_ids` from the DOM by reading chips
out of `.chip-area[data-type="kb"]`. Nothing renders those chips — the
per-agent Knowledge tab is a text stub — so the selector always matches
nothing and every save PUTs `kb_ids: []`. Any `kb_ids` value set through the
API (or by a future flight before the tab exists) is silently clobbered the
next time the operator saves the agent for any unrelated reason.

Today this is latent: `kb_ids` has no runtime effect (`the_one/agent/config.py:110`
— "reference IDs only — no functional behavior yet"). It becomes a real data
loss the moment Mission 24 makes attachment functional. Same shape as the
MCP-credential clobber that `update_agent` guards against server-side.

Fix options, in the same spirit as the `mcp_overrides` guard: omit `kb_ids`
from the PUT body when the tab has not rendered a chip area (server keeps the
stored value), or have `update_agent` treat an absent key as "keep". Whichever
lands must not break the Mission 24 flight that builds the real attach tab.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio.js:2035-2044` — chip collection from `.chip-area[data-type="kb"] .chip`, comment "KB chips still use the chip-area pattern (KB tab is a stub; whenever it lands, it can pick its own selector)"
- `the_one/interfaces/web/static/js/areas/studio/knowledge-tab.js:1-21` — stub renders a single `.empty-state`, no chip area
- `the_one/db/repositories.py:209` — `json.dumps(config.kb_ids)` on the upsert; the empty list is stored verbatim
- CLAUDE.md "Watch-out: agent PUTs preserve stored MCP credential overrides server-side" — the precedent for a keep-on-omit contract
- Surfaced by Mission 24 Flight 2 reconnaissance (R17)

## Corrective Action
*(written at completion)*

## Verification
Unit: set `kb_ids=["kb-1"]` via API, PUT the agent through the same body Studio sends without a `kb_ids` key (or with the tab unrendered), GET shows `["kb-1"]` retained. Browser (studio lane): save an agent from the General tab, assert `kb_ids` unchanged.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
