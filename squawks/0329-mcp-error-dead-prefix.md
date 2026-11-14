# Squawk 0329: `mcp-error.js` still matches a prefix nothing emits

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-04
**Completed**: 2026-11-14

## Report
The plain-headline regex in `mcp-error.js` still has a `fetchMcpSourceTools: HTTP` alternative. Sortie 09 removed `fetchMcpSourceTools` (the tile now uses `testMcpAsAgent`/`saveMcpCredentials` through `App.api.fetchJson`, whose failures read "Server error …"). So that alternative is dead text. Behaviour is unaffected, because the `Server error` alternative still matches. One browser test still pins the dead string.

## Evidence
- `the_one/interfaces/web/static/js/mcp-error.js:21` — `if (/^(fetchMcpSourceTools: HTTP|Server error)\b/.test(text.trim())) {`
- `tests/browser/test_studio_mcps_tab.py:568` — `"fetchMcpSourceTools: HTTP 500",`
- `grep -rn fetchMcpSourceTools the_one/` finds nothing else.

## Corrective Action
Grep over the repo (source, tests, scripts, packaging, `tests/behavior`; docs history in `missions/` and `sorties/` excluded) found `fetchMcpSourceTools` only in `mcp-error.js` and the one test case. Changed the regex in `the_one/interfaces/web/static/js/mcp-error.js` to `/^Server error\b/`. Removed the `fetchMcpSourceTools: HTTP 500` case from `tests/browser/test_studio_mcps_tab.py`, because a `Server error 500 Internal Server Error: boom` case with the same expected headline already exists.

## Verification
`THE_ONE_TEST_NETNS=1 ... run-tests.sh tests/browser/test_studio_mcps_tab.py -m browser -k mcp_error`: 3 passed. `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`: 396 passed. `ruff check` and `ruff format --check` on the test file pass. The rest of the file was not run (one browser file at a time, targeted).

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`

## Disposition
**Deferred**: cosmetic, no behaviour change. Logged from the sortie 09 debrief — revisit at the next squawk turnaround or the next change to `mcp-error.js`.
Completed in the 2026-11-14 turnaround.
