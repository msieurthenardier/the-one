# Squawk 0214: The OAuth callback page renders unstyled in the system browser

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: 2026-10-25

## Report
When MCP sign-in finishes in the system browser (the desktop app's path since sortie 04), the "Login successful / failed / expired" callback page shows unstyled. The page loads the app's own assets, but the system browser has no session cookie, and only `/api/oauth/callback` itself is credential-exempt, so those asset requests return 401. Seen in sortie 04's HAT on the Windows desktop test copy.

## Evidence
- `the_one/interfaces/web/api.py::_render_oauth_callback_page` — the page links `/static/js/theme.js`, `/static/css/fonts.css`, `/static/css/tokens.css` (~l.4544-4546).
- Test-copy log: `GET /static/js/theme.js 401`, `GET /static/css/tokens.css 401`, `GET /static/css/fonts.css 401` right after `GET /api/oauth/callback … 200` (sortie 04 flight log, H2 entry).
- `the_one/interfaces/web/middleware.py` `EXEMPT_PATHS` holds only liveness and the callback (no new exemptions wanted: sortie 04 charter constraint, SECURITY-MODEL.md).

## Corrective Action
`_render_oauth_callback_page` (`the_one/interfaces/web/api.py`) no longer links anything under `/static/`: it dropped `theme.js`, `fonts.css`, `tokens.css` and the `@layer` line, and carries its styles inline with an explicit minimal subset of the design tokens (`--bg`, `--surface`, `--border`, `--fg`, `--fg-secondary`, `--fg-muted`, `--radius-lg`, `--shadow-popover`, the h1/body/tiny font sizes, the semibold/bold weights and two line heights), light by default and a `prefers-color-scheme: dark` override for the six colours, in the system font stack. A static-asset exemption was rejected (sortie 04's charter and SECURITY-MODEL.md want no new exempt paths). Accepted loss: an explicit in-app theme choice no longer reaches this page (it follows the browser's light or dark preference). The old `var(--panel-radius)` named a token that never existed, so the card now uses `--radius-lg`. Done in Mission 31 Flight 5 leg 08b (ledger row 31).

## Verification
`tests/test_oauth_callback_page_static.py` (4 tests): the rendered HTML references nothing under `/static/` (no link, no script `src`, no `@layer`), carries an inline `<style>`, a dark override, the result `postMessage` script and the verbatim success heading, and every inlined token value equals its value in `css/tokens.css` or `css/fonts.css` (colours per theme), so the subset cannot drift. `tests/test_oauth_callback_route.py` still passes. Run before the change, the first test failed (the page linked three `/static/` assets).

## Sign-Off
*(written at completion)*
**Reviewer**: Flight Director review at the leg 08b batch review
**Verdict**: `[HANDOFF:confirmed]` by the Mission 31 Flight 5 batch B4 Reviewer (Sonnet, 2026-10-25), and the fix re-review
**Commit**: the Mission 31 Flight 5 checkpoint B4 commit, `flight/5: connection status, sign-in and server info (legs 08b-09)`
