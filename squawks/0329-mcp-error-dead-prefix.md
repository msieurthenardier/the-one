# Squawk 0329: `mcp-error.js` still matches a prefix nothing emits

**Status**: deferred
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-04
**Completed**: —

## Report
The plain-headline regex in `mcp-error.js` still has a `fetchMcpSourceTools: HTTP` alternative. Sortie 09 removed `fetchMcpSourceTools` (the tile now uses `testMcpAsAgent`/`saveMcpCredentials` through `App.api.fetchJson`, whose failures read "Server error …"). So that alternative is dead text. Behaviour is unaffected, because the `Server error` alternative still matches. One browser test still pins the dead string.

## Evidence
- `the_one/interfaces/web/static/js/mcp-error.js:21` — `if (/^(fetchMcpSourceTools: HTTP|Server error)\b/.test(text.trim())) {`
- `tests/browser/test_studio_mcps_tab.py:568` — `"fetchMcpSourceTools: HTTP 500",`
- `grep -rn fetchMcpSourceTools the_one/` finds nothing else.

## Corrective Action
*(written at completion)* Planned: drop the `fetchMcpSourceTools: HTTP` alternative; change the test case at `test_studio_mcps_tab.py:568` to a `Server error 500` text (or remove that parametrization if a `Server error` case already exists).

## Verification
`tests/browser/test_studio_mcps_tab.py` (lane `agents`) and the static guards pass.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
**Deferred**: cosmetic, no behaviour change. Logged from the sortie 09 debrief — revisit at the next squawk turnaround or the next change to `mcp-error.js`.
