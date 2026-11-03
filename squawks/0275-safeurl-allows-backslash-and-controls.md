# Squawk 0275: `App.safeUrl` accepts backslashes and control characters in an http(s) URL

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-27
**Completed**: 2026-11-03

## Report
`App.safeUrl` (the fail-closed URL gate for server-supplied links, used by the MCP editor's server info) checks only `^https?:` after rejecting `//`.
- It accepts an `http(s):` URL that contains `\`, a tab, a newline or another control character. The WHATWG URL parser treats `\` as `/` for special schemes and strips tabs and newlines, so such a URL can resolve to a different host than it reads.
- The scheme stays http(s) and these links open externally, so the risk is low. But the gate is meant to be fail-closed, and it no longer matches `markdown.js`'s `safeHref` after Mission 31 Flight 6 leg 07 (which rejects `\` and C0/DEL characters anywhere in an href).

Found by the leg 07 design review; outside Flight 6's surfaces (the MCP editor).

## Evidence
- `the_one/interfaces/web/static/js/app.js::safeUrl` (about `:260-273`): `if (/^\s*\/\//.test(url)) return null;` then `return /^https?:/i.test(url) ? url : null;`.
- Callers: `js/areas/studio/mcp-server-info.js:130`, `:148`.

## Corrective Action
`App.safeUrl` (`js/app.js`) now returns `null` for any URL containing `\`, a C0 control (`\u0000`-`\u001f`) or DEL, the same rule as `markdown.js`'s `safeHref`, before the existing `//` and `^https?:` checks. Ordinary http(s) URLs are unchanged. Callers (`mcp-server-info.js` x2) already drop the link/icon on `null`; `App.ui.consentLink.isSafeUrl` is a separate function and was left alone (out of the squawk's scope).

## Verification
Added to `tests/browser/test_markdown.py`: `test_safe_url_rejects_backslash_controls_and_other_schemes` (16 cases) and `test_safe_url_passes_ordinary_http_urls_unchanged` (5 cases). Falsified: yes (guard line removed, 10 reject cases failed; restored). Results are in the completion report.
Original spec: unit or browser cases: `https:\\evil.example`, `https://ok.example/\@evil`, an embedded tab and an embedded newline all return `null`; a normal `https://` URL is unchanged.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
**Deferred**: found during Mission 31 Flight 6's leg 07 design. It sits outside the flight's surfaces. Revisit at the next squawk turnaround or the next change to `App.safeUrl`.
