# Squawk 0050: Studio agent save writes `kb_ids: []` on every save

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-14
**Completed**: 2026-10-08

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
Already fixed in Mission 24 Flight 6 (commit 189a23a, "flight/6: Studio surfaces -- knowledge inventory, attach tab, settings panel"); the fix was never recorded here. Two parts: (1) `update_agent` in `the_one/interfaces/web/api.py` treats an omitted `kb_ids` key as "keep" (AC-7: `if "kb_ids" not in data: data["kb_ids"] = existing.kb_ids`); an explicit `kb_ids: []` still clears. (2) The agent editor's Knowledge tab is now a real per-knowledge-base attach toggle rather than a stub, and a failed knowledge-base fetch omits `kb_ids` from the save. Pinned by `tests/test_db_api.py::TestAgentKbToolNames::test_put_omitting_kb_ids_preserves_stored_value` and `::TestAgentKbToolNames::test_put_omitting_both_kb_ids_and_mcp_overrides_preserves_both`, and by the browser test `tests/browser/test_flow_studio_knowledge_attach.py::test_failed_fetch_shows_load_error_and_omits_kb_ids_from_save`. Records-only completion; no code changed.

## Verification
Run 2026-10-08 (turnaround 2026-10-08): the two `tests/test_db_api.py` pinning tests above pass (2 passed). Behavior run `tests/behavior/kb-studio-round-trip/runs/2026-09-22-01-05-35.md`, checkpoint 11 ("squawk 0050's regression net"): PASS -- description changed on the General tab with the Knowledge tab untouched, the mutation verified as landed, and `kb_ids` unchanged after save.

Original plan: set `kb_ids=["kb-1"]` via API, PUT the agent through the same body Studio sends without a `kb_ids` key (or with the tab unrendered), GET shows `["kb-1"]` retained. Browser (studio lane): save an agent from the General tab, assert `kb_ids` unchanged.

## Sign-Off

**Reviewer**: independent Reviewer (Haiku tier: records only). It confirmed the keep-on-omit logic in `update_agent`, commit 189a23a, both pinning tests passing, and checkpoint 11 PASS in `tests/behavior/kb-studio-round-trip/runs/2026-09-22-01-05-35.md`. The Flight Director corrected the test node ids, which had been missing their class prefix, and re-ran both green (2 passed).
**Verdict**: confirmed (`[HANDOFF:confirmed]` on substance; the Reviewer's two "changes requested" were the Status/Sign-Off fields, which the Flight Director writes at close-out)
**Commit**: `squawk: turnaround 2026-10-08 (2)` on branch `squawk/turnaround-2026-10-08-2`
