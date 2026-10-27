# Squawk 0275: `App.safeUrl` accepts backslashes and control characters in an http(s) URL

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-27
**Completed**: —

## Report
`App.safeUrl` (the fail-closed URL gate for server-supplied links, used by the MCP editor's server info) checks only `^https?:` after rejecting `//`.
- It accepts an `http(s):` URL that contains `\`, a tab, a newline or another control character. The WHATWG URL parser treats `\` as `/` for special schemes and strips tabs and newlines, so such a URL can resolve to a different host than it reads.
- The scheme stays http(s) and these links open externally, so the risk is low. But the gate is meant to be fail-closed, and it no longer matches `markdown.js`'s `safeHref` after Mission 31 Flight 6 leg 07 (which rejects `\` and C0/DEL characters anywhere in an href).

Found by the leg 07 design review; outside Flight 6's surfaces (the MCP editor).

## Evidence
- `the_one/interfaces/web/static/js/app.js::safeUrl` (about `:260-273`): `if (/^\s*\/\//.test(url)) return null;` then `return /^https?:/i.test(url) ? url : null;`.
- Callers: `js/areas/studio/mcp-server-info.js:130`, `:148`.

## Corrective Action
*(written at completion)*
Likely: reject any `\`, C0 control or DEL in the URL, mirroring `safeHref`, and add the boundary cases to the `App.safeUrl` tests.

## Verification
*(written at completion)*
Unit or browser cases: `https:\\evil.example`, `https://ok.example/\@evil`, an embedded tab and an embedded newline all return `null`; a normal `https://` URL is unchanged.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
**Deferred**: found during Mission 31 Flight 6's leg 07 design. It sits outside the flight's surfaces. Revisit at the next squawk turnaround or the next change to `App.safeUrl`.
