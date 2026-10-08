# Squawk 0145: Four Studio fetches parse error bodies as data

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
Four reads in `areas/studio.js` do `fetch(url).then(r => r.json())` with no `r.ok` check, so a 401/404/500 JSON error body is handed to the render code as if it were the expected payload, which most likely ends in a TypeError and a blank or partial editor. Other traced Studio paths handle errors correctly. Found by routine maintenance 2026-10-08 (finding #29; the wider raw-fetch cleanup belongs to issue #207).

## Evidence
- `the_one/interfaces/web/static/js/areas/studio.js` ~1900 (`/api/tools`), ~1907 (`/api/mcp-sources?include_agent_surfaces=1`), ~1930 (`/api/agents/{name}`), ~2118 (`/api/tools/configs`)
- `App.api.fetchJson` is used nowhere in studio.js

## Corrective Action
Routed the four reads in `areas/studio.js` (`fetchTools`, `fetchMcpSources`, the agent re-fetch in `_refreshAgentAfterSelfConfigurationChange`, `fetchToolConfigs`) through `App.api.fetchJson`, so a non-ok response throws. Existing handlers cover the throw: `loadAll` shows its load-error banner/flash, the two cache refreshers (`refreshToolConfigsCache`, `refreshMcpSourcesCache`) keep their prior cache via their `.catch`, and the self-configuration refresh rejects to its callers as it already did for other failures. No caller UX changed.

## Verification
Added `test_loadall_rejects_on_tools_json_500` to `tests/browser/test_flow_studio_loadall_error.py` (JSON 500 on `/api/tools`: load-error line shown with the detail, no `pageerror`). Falsified: reverting `/api/tools` to the bare form fails it; restored, the file passes (5 passed). `node --check studio.js` clean; `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y` pass (261).
Updated `tests/test_store_static.py::test_library_fetch_sites_read_through_the_store` to pin the `?include_agent_surfaces=1` direct fetch in its new `App.api.fetchJson(...)` form (still never via `App.store`).

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the credential-gated test seams and secret echo in 422 bodies), plus a Haiku re-review of the one fix-loop change (`tests/test_store_static.py`, a static guard that pinned the pre-0145 fetch literal); unit suite 5647 passed, 1 failed before the guard fix (the guard, re-run green after), 16 skipped (10 Windows-only, 2 root-only under `THE_ONE_TEST_NETNS=1`, 4 `requires_bwrap` sandbox skips included by the run's marker set); agents lane 154 passed, 2 skipped; shared lane 465 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08` on branch `squawk/turnaround-2026-10-08`
