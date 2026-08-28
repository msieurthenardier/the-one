# Squawk 0010: MCP server-supplied `websiteUrl` / icon `src` rendered without a URL-scheme allowlist

**Status**: open
**Type**: defect
**Severity**: grounding
**Reported**: 2026-08-27
**Completed**: —

## Report

The Studio MCP Server editor renders two values that come straight from the MCP
server's `initialize()` response — `serverInfo.websiteUrl` as a clickable link and
`icons[0].src` as an `<img>` — through `escapeAttr()` only. `escapeAttr` neutralises
HTML metacharacters but does not restrict the URL scheme, unlike the chat renderer's
`safeHref()`, which fails closed on `javascript:` / `data:` / `vbscript:` / `file:`.
A hostile or compromised MCP server can therefore return `websiteUrl: "javascript:…"`
and get a live executable link in the app's own origin; a click runs attacker JS whose
same-origin `fetch()` calls carry the HttpOnly session cookie — full authenticated
`/api/*` (mint `ext_` credentials, edit agent prompts, rotate keys). The `<img src>`
path is fetched by the operator's browser outside the app's SSRF-guarded transport,
so an attacker-chosen `src` can probe internal LAN hosts/ports on render, no click
needed. Found by the 2026-08-27 routine-maintenance Security Reviewer (S1).

Fix: route both `websiteUrl` and `icons[].src` through the same fail-closed scheme
allowlist `markdown.js` already uses (`http:`/`https:` only for these), dropping the
element entirely when the scheme is rejected.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:341` —
  `html += '<img class="mcp-server-icon" src="' + escapeAttr(icons[0].src) + '"'`
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:360` —
  `'<a href="' + escapeAttr(websiteUrl) + '" target="_blank" rel="noopener noreferrer">'`
- `the_one/interfaces/web/static/js/markdown.js:104` — `function safeHref(href)` — the
  existing fail-closed allowlist, not reused here.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion — a browser/DOM test feeding a `javascript:` `websiteUrl` and a
non-http icon `src` through the server-info renderer and asserting neither element
carries the hostile URL)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
