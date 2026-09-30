# Squawk 0102: MCP source editor's Server section shows a stale version after Refresh connection

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-30
**Completed**: 2026-09-30

## Report

After updating an MCP server (Sonos MCP 0.3.0 → 0.5.0 on the operator's
production instance) and clicking **Refresh connection** in the Studio MCP
source editor, the Server section still showed version 0.3.0. The refresh had
persisted the new `serverInfo` to `config._cache` correctly — navigating away
and back re-mounted the editor and showed 0.5.0. Only the in-place repaint is
missing.

Repro: open an existing MCP source whose server reports a new `serverInfo`
version since the last refresh; click Refresh connection; the tools list and
"Last updated" repaint, the Server section does not.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js::renderMcpSourceEditor` —
  `html += renderServerInfoSection(cache);` runs only at mount.
- `mcp-server-editor.js::handleTestConnection` repaints only
  `[data-testid="mcp-tools-list"]` and `[data-testid="mcp-tools-last-updated"]`.
- `mcp-server-editor.js::onTestConnectSuccess` refetches `GET /api/mcp-sources/{id}`
  but only uses the result for `oauth_active` → `syncResetButtonVisibility`.
- Backend is correct: `the_one/interfaces/web/api.py::_build_and_test_stdio_mcp` /
  `_build_and_test_no_auth_mcp` write `server_info` into `config._cache` on every
  successful connect.

## Corrective Action

In-place repaint of the Server section after a successful Refresh connection,
confined to `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js`:

- New `cacheHasServerInfo(cache)`: the mount-time gate, extracted so both the
  mount path (`renderMcpSourceEditor`) and the repaint use the same condition.
- New `syncServerInfoSection(container, cache)`: re-renders via the existing
  `renderServerInfoSection` and applies a targeted DOM mutation. It replaces the
  existing `[data-testid="mcp-server-info-section"]` node, inserts it before
  `.mcp-tools-section` when it did not exist yet (first-ever refresh), or removes
  it when the cache no longer qualifies. Nothing needs re-wiring: the section's
  only interactive parts are native `<details>` elements.
- `wireEditorEvents`'s `onTestConnectSuccess`: already refetched
  `GET /api/mcp-sources/{id}`, and now also calls
  `syncServerInfoSection(container, refreshed.config._cache)`. The editor is
  not fully re-rendered, so dirty form state is preserved.
- `source.config._cache` is deliberately **not** overwritten in memory.
  `hasOAuthState`'s cache-presence fallback reads it, so syncing it would change
  Reset-button visibility on later refreshes, which is outside this squawk's scope.

No backend, schema or shared-interface change.

## Verification

- New browser test
  `tests/browser/test_flow_studio_mcp_editor.py::test_server_info_section_repaints_after_refresh`.
  It seeds a streamable-http source with no cache and stubs `/test/connect` plus
  the per-id GET refetch (the same pattern as
  `test_reset_button_reappears_after_post_oauth_refresh`). The first Refresh
  shows the section with `v0.3.0` above the Tools section (insert path). The
  stub's reported version then changes to `0.5.0`, and a second Refresh without
  leaving the editor shows `v0.5.0` (replace path).
- Fail-before: with the JS change reverted (`git checkout` of the editor file
  only), the new test FAILS (`Locator expected to have count '1'`: the section
  never appears after refresh).
- Pass-after: with the fix, `run-tests.sh --lane studio -k test_flow_studio_mcp_editor`
  gives **52 passed**, covering the whole MCP editor file including the
  server-info scheme tests, the Reset-after-refresh test and the auto-run tests.
- `ruff check the_one/ tests/ scripts/` and `ruff format --check` on the touched
  test file are clean.

## Sign-Off

Independent Reviewer: `[HANDOFF:confirmed]`, no blocking issues. The mount gate is equivalent to the original, the replace/insert/remove logic and escaping are sound, race exposure is the same as the existing Reset-button sync, and not overwriting `source.config._cache` in memory was upheld. The new test passed on re-run. Non-blocking note: a refresh collapses any open `<details>` disclosure in the Server section. This is cosmetic and not logged.

Commit: squawk/0102 on branch `squawk/0102-mcp-server-info-stale-after-refresh`.
