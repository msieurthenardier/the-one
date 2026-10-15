# Squawk 0214: The OAuth callback page renders unstyled in the system browser

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: —

## Report
When MCP sign-in finishes in the system browser (the desktop app's path since sortie 04), the "Login successful / failed / expired" callback page shows unstyled. The page loads the app's own assets, but the system browser has no session cookie, and only `/api/oauth/callback` itself is credential-exempt, so those asset requests return 401. Seen in sortie 04's HAT on the Windows desktop test copy.

## Evidence
- `the_one/interfaces/web/api.py::_render_oauth_callback_page` — the page links `/static/js/theme.js`, `/static/css/fonts.css`, `/static/css/tokens.css` (~l.4544-4546).
- Test-copy log: `GET /static/js/theme.js 401`, `GET /static/css/tokens.css 401`, `GET /static/css/fonts.css 401` right after `GET /api/oauth/callback … 200` (sortie 04 flight log, H2 entry).
- `the_one/interfaces/web/middleware.py` `EXEMPT_PATHS` holds only liveness and the callback (no new exemptions wanted: sortie 04 charter constraint, SECURITY-MODEL.md).

## Corrective Action
*(written at completion)*
Likely: make the callback page self-contained (inline the few styles it needs, no `/static` references) rather than exempting static assets.

## Verification
A unit test that the rendered callback HTML references no `/static/` URL and still carries the result `postMessage`; a look at the page in a browser without a session cookie.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
**Deferred**: found mid-flight in sortie 04's HAT, outside its charter — revisit at the next squawk turnaround, or with the chat sign-in lifecycle sortie if it lands first.
