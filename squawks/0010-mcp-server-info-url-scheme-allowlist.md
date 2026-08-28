# Squawk 0010: MCP server-supplied `websiteUrl` / icon `src` rendered without a URL-scheme allowlist

**Status**: completed
**Type**: defect
**Severity**: grounding
**Reported**: 2026-08-27
**Completed**: 2026-08-27

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

`safeHref()` in `markdown.js` is a module-private closure function — it is not on the
public `window.App.markdown` API (`parse`/`render`/`NodeType` only), so it wasn't
reachable from `mcp-server-editor.js`. Added a sibling shared helper, `safeUrl()`, in
`app.js` next to `escapeHtml`/`escapeAttr` (the file that already owns and exports
those shared escaping primitives via `window.App.*`), exported as `window.App.safeUrl`.
It mirrors `safeHref`'s fail-closed/anchored/case-insensitive scheme match and its
protocol-relative (`//host`) rejection, but is narrower on purpose: only `http:`/
`https:` pass (no `mailto:`/`tel:`/relative/fragment — those markdown-link affordances
don't apply to a server-supplied website link or icon `src`). Returns the URL
unchanged on pass or `null` on rejection; callers must drop the attribute/element, not
substitute a placeholder that still renders live.

Wired `renderServerInfoSection()` in `mcp-server-editor.js` to route both untrusted
fields through it:
- `icons[0].src` → `safeUrl()` result gates the `<img>` emission entirely; on rejection
  no `<img>` element is emitted (previously: `escapeAttr()` only, so a `javascript:`/
  `data:` src still rendered — the browser fetches `<img src>` outside the app's
  SSRF-guarded transport, no click needed).
- `websiteUrl` → `safeUrl()` result gates the `<a href>`; on rejection the raw string
  still renders as escaped inert text (not a link, not dropped) so the operator can see
  what the server claimed without it being clickable in the app's own origin.

## Verification

Added two browser tests (Playwright, mirroring the existing `_seed_mcp_source` +
`config._cache` pattern already used by `test_cached_tools_render_on_initial_mount`)
in `tests/browser/test_flow_studio_mcp_editor.py`:
- `test_server_info_website_and_icon_reject_unsafe_schemes` — seeds
  `server_info.websiteUrl = "javascript:alert(document.cookie)"` and
  `icons[0].src = "javascript:alert(1)"`; asserts `img.mcp-server-icon` has zero
  matches (element dropped) and `.mcp-server-website` has zero `<a>` children while
  still containing the raw string as text.
- `test_server_info_website_and_icon_allow_https` — seeds `https:` values for both
  fields; asserts the `<img src>` and `<a href>` render live with the expected
  attribute values (allow-list isn't a blanket drop).

Commands run:
- `THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser
  tests/browser/test_flow_studio_mcp_editor.py -x --timeout 300` — 49 passed (full
  file, including the 2 new tests and the 47 pre-existing ones — no regressions).
- `THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_ui_guards.py -x --timeout 60` — 14 passed (innerHTML dynamic-sink freeze
  and testid registry unaffected by this change).
- `make lint` — ruff, all checks passed.
- `make format-check` — ruff format, no changes needed (JS files aren't covered by
  the Python-only formatter; hand-checked indentation/style against the surrounding
  code instead).

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-27)
**Verdict**: confirmed
**Commit**: `squawk/turnaround-2026-08-27` — PR pending (sha recorded on close)
