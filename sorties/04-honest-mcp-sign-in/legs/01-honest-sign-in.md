# Leg: honest-sign-in

**Status**: completed
**Flight**: [Honest MCP sign-in in the desktop app](../flight.md)

## Objective
Make MCP sign-in in chat and the MCP editor show a working sign-in link instead of "Popup blocked" (in the desktop webview and everywhere else), and make a 401 from a server with no OAuth metadata, on a source with operator-supplied headers, report `MCPCredentialsRejected` instead of offering a sign-in.

## Context
- The flight spec's DD1-DD7 are the contract for this leg; read them in full before starting (`sorties/04-honest-mcp-sign-in/flight.md`). DD8 is the HAT leg, not this one.
- Diagnosis evidence and both Architect review cycles are in `sorties/04-honest-mcp-sign-in/flight-log.md`. The cycle-2 findings are already folded into DD2 and DD4; where this leg and the flight disagree, the flight wins and the leg is wrong (raise it).
- Two independent halves, done in this order with a checkpoint between them:
  1. **Backend (DD4, DD5):** `MCPCredentialsRejected`, the `_signin_signal` factory in `MCPClient`, the three Test connection paths (a)-(c), the fixture options, unit tests.
  2. **Frontend (DD1-DD3, DD4's UI bullet):** `App.desktop.isWebview`, `consent-link.js`, chat `startLoginFlow` + per-flow state, the MCP editor's `launchConsentPopup`, the `mcp-error.js` rule, browser tests.
- Lane budgets: `chats` has about 12 s of headroom, so browser tests go in `tests/browser/test_oauth_modal_flow.py` (lane `shared`) and `tests/browser/test_flow_studio_mcp_editor.py` (lane `mcp`), never in new files (a new file's name picks its lane).
- Mission 31 (planning, untracked in the working tree as `missions/31-control-library-everywhere/`) will later rewrite `chat.js` / `mcp-server-editor.js` markup. Do not touch or commit that directory. Build everything new with DOM APIs, never HTML strings.

## Inputs
- Branch `sortie/04-honest-mcp-sign-in` at `d2c98b1` (HEAD of `main`), working tree clean apart from the untracked `missions/31-control-library-everywhere/` and this sortie's artifacts.
- The flight spec's Citation Audit (verified at `d2c98b1`, line drift fixed in cycle 2).

## Outputs
- `MCPCredentialsRejected` in `the_one/mcp/errors.py`; `_signin_signal` in `the_one/mcp/client.py`; Test connection paths (a)-(c) in `the_one/interfaces/web/api.py`.
- `tests/fixtures/mcp/asgi_401.py` bare-401 option; `OAuthASStub` bare-401 mode.
- `the_one/interfaces/web/static/js/consent-link.js` (new), `App.desktop.isWebview` in `theme.js`, changes to `areas/chat.js`, `areas/studio/mcp-server-editor.js`, `mcp-error.js`, `index.html` (one script tag).
- Unit and browser tests; docs (`the_one/agents.md`, `CLAUDE.md`, `docs/ui-testid-registry.md`).
- Flight log updated; leg status `landed`.

## Acceptance Criteria

**Backend (checkpoint: all green before the frontend half starts)**
- [ ] AC1. `MCPCredentialsRejected(MCPConnectionError)` exists in `the_one/mcp/errors.py` with `# noqa: N818`; its message names the source and says the server rejected the configured credentials (401) and where to check the headers (Library › MCP servers, or the agent's MCPs tab override).
- [ ] AC2. In `the_one/mcp/client.py`, every 401-derived `MCPAuthRequired` is built through one `_signin_signal(resource_metadata_url)` factory, called from `_auth_required_since` and from `_classify_failure`'s `DiscoverSignInRequired` row. It returns `MCPCredentialsRejected` exactly when operator headers are present (`build_request_headers(self.source)` non-empty, imported function-locally), the `resource_metadata_url` is `None`, and `self._auth_provider is None`; otherwise `MCPAuthRequired` exactly as today. `_oauth_flow_auth_required` (provider attached) is unchanged.
- [ ] AC3. `_classify_failure` calls `self._mark_dead()` when its result is `MCPCredentialsRejected` and `op != "connect"` (the existing `_mark_dead` precedent inside `_classify_failure`, `client.py:449`, `:471`), so every `list_tools` / `call_tool` arm is covered.
- [ ] AC4. The agent build skips a rejected source without crashing (`_tool_provider.py` Path A catches it via `MCPConnectionError`); a tool call through `_tool.py` / `core._execute_tool` produces an error tool result with no `is_auth_required` metadata.
- [ ] AC5. Test connection path (a): a source with cached `auth_posture: "no_auth"` whose key is now rejected returns `{"status": "error", "error": "MCPCredentialsRejected: …"}` and keeps `no_auth`.
- [ ] AC6. Test connection path (b): with `from_fallthrough=True`, `_build_and_test_no_auth_mcp` returns `_SIGNIN_REQUIRED` for `MCPCredentialsRejected` exactly as for `MCPAuthRequired`, so Phase B decides.
- [ ] AC7. Test connection path (c): when Phase B was entered from **this request's** Phase 0 probe verdict `"oauth"` or the DD9 fall-through's `_SIGNIN_REQUIRED` (both of which sent the operator headers and got 401: that is the rejection evidence; Phase B's own requests do not carry operator headers, `_oauth_driver_headers`, `api.py:147-149`, and must not start to), and not from Phase A's stale-token fall-through, and `_drive_flow_test`'s failure is an `OAuthRegistrationError` whose message starts "Registration failed:", operator headers are present, `provider` is an `OAuthClientProvider`, and both `provider.context.protected_resource_metadata` and `provider.context.oauth_metadata` are `None`, the route returns `{"status": "error", "error": "MCPCredentialsRejected: …"}` and the source's `_cache.auth_posture` is removed. Every other failure (no operator headers; metadata found; PRM 5xx/429; transport error; a post-2xx `check_registration_usable` error) still returns `auth_flow_error: …` / `consent_url_timeout` as today.
- [ ] AC8. The self-configuration loopback source answering 401 yields `MCPCredentialsRejected` (it carries `secrets["Authorization"]`) and its posture stays `no_auth`.
- [ ] AC9. `tests/fixtures/mcp/asgi_401.py` can answer a bare 401 (no `WWW-Authenticate`) with GET `/.well-known/*` and POST `/register` also 401; `OAuthASStub` (`tests/fixtures/oauth/__init__.py:242`) has a `bare_401` cfg key (default off) with the same behaviour. Existing default behaviour of both is unchanged.
- [ ] AC10. `tests/test_imports.py::test_import_agent_core_does_not_load_mcp_oauth` and `tests/test_auth_posture_probe.py::test_probe_oauth_when_operator_headers_insufficient` pass unchanged.

**Frontend**
- [ ] AC11. `App.desktop.isWebview()` is defined by `theme.js` (same predicate as today's private `isDesktopWebview`, which now delegates to it) and nothing but chat's pre-open branches on it.
- [ ] AC12. `static/js/consent-link.js` exists (styles `consent-link-*` unscoped in `static/css/components.css`, since chat and the studio both render it), defines `App.consentLink.build(url, {surface})` (`surface` `"chat"` | `"mcp"`), builds with DOM APIs only: a read-only URL `<input>`, an "Open sign-in page" `<a href target="_blank" rel="noopener noreferrer">` styled as a button, a "Copy" button (clipboard, `execCommand` fallback), and the helper line; classes `consent-link-*`; literal testids `chat-consent-link-url|-open|-copy` and `mcp-consent-link-url|-open|-copy`, registered in `docs/ui-testid-registry.md`. Its `<script>` tag sits after `ui/button.js` and before `areas/chat.js`, pinned by a unit test.
- [ ] AC13. Chat: the "Popup blocked" message is gone. `startLoginFlow` keeps the browser-mode `about:blank` pre-open and navigation, skips the pre-open when `App.desktop.isWebview()`, keeps the early return when the consent URL is already known, and otherwise always POSTs `/api/oauth/start`. A per-(session id, source id) map `{consentUrl, startedHere, autoOpened}` drives: render the link block in the login-required group and hide (not remove) the "Log in" button when a consent URL is known; one best-effort `window.open(url, '_blank')` only if `startedHere && !popupHeld && !autoOpened`; a replayed frame with `consent_url: null` re-renders the block from the map; the entry clears on `auth_resolved` / `auth_failed` in the ungated handler part beside `closeOauthPopup`; `auth_failed` removes the block and un-hides "Log in", leaving "OAuth failed: …". The early return in `startLoginFlow` consults the map's `consentUrl` (not the button's original `data`). Replay idempotency holds: one `.login-required-group` per source after any number of replays.
- [ ] AC14. MCP editor: the "Popup blocked" message is gone. `launchConsentPopup` renders the block in its own container, then tries `window.open`; status text writes go to a separate status-text child inside the panel, and `data-testid="mcp-test-status"` stays on the outer panel; `renderRetryUi` clears only the status text and retry area; polling for `has_access_token` runs to `CONSENT_WAIT_MS` once the block shows, regardless of the popup; every popup-handle use is null-guarded; the block is removed on failed/expired/timeout; on success tools are listed with no manual re-test. The `noAutoPopup` path renders the block when its "Sign in" is clicked.
- [ ] AC15. `mcp-error.js` classifies `cls === 'MCPCredentialsRejected'` ahead of the `MCPConnectionError` rules with the headline "The server rejected the configured credentials. Check the headers on this MCP server."; `tests/test_mcp_error_classes_pinned.py` passes.
- [ ] AC16. In a browser with a working popup, sign-in behaves as before (popup opened at click, navigated on the consent frame, closed on `auth_resolved`), plus the link block.

**Whole leg**
- [ ] AC17. Docs updated per DD7: `the_one/agents.md` ("MCP error translation", "MCP F2 Client Foundation", "Desktop launcher"), one sentence in `CLAUDE.md`'s MCP paragraph, `docs/ui-testid-registry.md`.
- [ ] AC18. `make test-unit` green (12 skipped expected; 14 under `THE_ONE_TEST_NETNS=1`); `ruff check` + `ruff format --check` clean; static guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`) green; browser lanes `shared` and `mcp` green; the full gate `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short` ends `PARALLEL_RESULT rc=0`.

## Verification Steps
- AC1-AC10: the new and changed unit tests (see Implementation Guidance step 4); `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_client.py tests/test_mcp_signin_detection.py tests/test_mcp_test_connection_negotiation.py tests/test_mcp_connection_reset.py tests/test_oauth_test_connection_endpoint.py tests/test_mcp_tool_provider.py tests/test_auth_posture_probe.py tests/test_imports.py -x --timeout 30`, then `make test-unit`. Record the checkpoint result in the flight log before starting the frontend.
- AC11-AC16: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_oauth_modal_flow.py tests/browser/test_flow_studio_mcp_editor.py -m browser -x --timeout 60`; then `--lane shared` and `--lane mcp`; the static guards; `tests/test_mcp_error_classes_pinned.py`; the new load-order test.
- Falsify at least two new tests: (1) temporarily revert the chat replay re-render (AC13) and confirm the replay test fails; (2) temporarily make `_classify_failure`'s `DiscoverSignInRequired` row build `MCPAuthRequired` directly and confirm the discover-route rejection test fails. Restore both; record in the flight log.
- AC17: read the doc diffs. AC18: the gate's `PARALLEL_RESULT` line, recorded with per-lane times.

## Implementation Guidance

1. **Fixtures first** (AC9).
   - `tests/fixtures/mcp/asgi_401.py`: accept `resource_metadata=None` → answer 401 with no `WWW-Authenticate` (today `:69`, `:84` always send `Bearer resource_metadata="…"`). `Auth401Wrapper.__call__` passes every non-POST straight to the wrapped app (`:39-41`) and parses every POST body as JSON-RPC, so the bare mode must branch on `scope["path"]` and method **before** that passthrough: GET `/.well-known/*` → 401, POST `/register` → 401.
   - `OAuthASStub` (`tests/fixtures/oauth/__init__.py:242`, plain-dict `cfg` read by `_OAuthASHandler`): a `bare_401` cfg key, default off, under which `/mcp` answers 401 with no `WWW-Authenticate` and the PRM, AS-metadata and `/register` routes answer 401.

2. **The error type** (AC1). `the_one/mcp/errors.py`: `class MCPCredentialsRejected(MCPConnectionError):  # noqa: N818` with a docstring stating the rule (operator headers + 401 + no `resource_metadata` + no OAuth provider) and that it subclasses `MCPConnectionError` so existing graceful-skip catches handle it. Constructor takes `source_id` and `source_name` and builds the message.

3. **`MCPClient`** (AC2, AC3).
   - Add `_signin_signal(self, resource_metadata_url: str | None) -> MCPClientError`. Move the `MCPAuthRequired(...)` construction from `_auth_required_since` (`client.py:364-388`) and from `_classify_failure` row 0 (`client.py:424-432`, `DiscoverSignInRequired` → passes `exc.resource_metadata_url`) into it. Confirm with a grep that `MCPAuthRequired(` is then constructed in `client.py` only in `_signin_signal` and `_oauth_flow_auth_required`.
   - The operator-header check: `from the_one.mcp.transports.streamable_http import build_request_headers` inside the function (import guard). Only `streamable-http` sources can 401; guard on `self.source.type` before calling it.
   - `_auth_required_since`'s return annotation (`client.py:365`, `MCPAuthRequired | None`) becomes `MCPClientError | None`; its callers (`:584`, `:599`) just raise it. Update `_classify_failure`'s docstring and row-0 text, which name `MCPAuthRequired`.
   - `_mark_dead()` (`client.py:352`): inside `_classify_failure`, after computing the result, when it is `MCPCredentialsRejected` and `op != "connect"` (the precedent at `:449`, `:471`). Not at the call-site arms: the `except MCPAuthRequired: raise` arms (`:855`, `:1005`) would not see it. `_mark_dead` is a flag flip; the pool reads `is_alive` on the next acquire, so there is no mid-call eviction.
   - `self.source` is already the per-agent-overridden copy (`_tool_provider.py::_apply_override`, `:105-181`), so overrides are covered. A source whose secrets are only OAuth-managed keys gives `{}` from `build_request_headers` → not rejected; unit-test that.

4. **Unit tests for steps 2-3** (AC2-AC4, AC8). Prefer extending `tests/test_mcp_signin_detection.py` and `tests/test_mcp_client.py`; use `asgi_401.py`'s bare-401 option. Cover: operator headers × `resource_metadata` × provider attached on the `_auth_required_since` route; the `DiscoverSignInRequired` route with and without a remembered era (see `tests/test_mcp_negotiation_fallback.py` / `_mcp_signin_helpers.py` for how eras are set up); `_mark_dead` after a rejected `call_tool`; agent-build Path A skip (`tests/test_mcp_tool_provider.py`); `_tool.py` / `core._execute_tool` error result has no `is_auth_required`; the self-config loopback source (AC8).

5. **Test connection** (AC5-AC7) in `the_one/interfaces/web/api.py::test_mcp_connection` and helpers.
   - (b) `_build_and_test_no_auth_mcp` (`:3423`): when `from_fallthrough`, `MCPCredentialsRejected` returns `_SIGNIN_REQUIRED` like `MCPAuthRequired`. The arm must sit before the typed `MCPConnectionError` arm (`:3428`) or be merged into the `except MCPAuthRequired` arm. Without `from_fallthrough` it falls to the typed arm → path (a)'s error envelope (AC5).
   - (c) Record on entry to Phase B whether it came from this request's probe `"oauth"` verdict or the DD9 fall-through (a local flag; Phase A's stale-token fall-through leaves it false). Do **not** add operator headers to Phase B's requests. `_drive_flow_test` (`:3900-3940`): in its `except Exception as exc`, classify while `provider` and `exc` are in scope (closure; `source_id` and `repo` are in scope too) (httpx2 runs the auth flow inline, so `exc` is the SDK's own exception). On a match (AC7's conditions; `isinstance(provider, OAuthClientProvider)` first), set a private sentinel exception on `consent_url_future` instead of the `RuntimeError`. The outer `except` (`:3947-3950`) maps the sentinel to the `MCPCredentialsRejected:` envelope and removes `_cache.auth_posture` (mirror `_persist_oauth_posture`'s best-effort repo write, `:3315`; a small `_clear_auth_posture` helper is fine). Message text comes from `MCPCredentialsRejected` so both paths say the same thing; a test pins that the envelope text equals `f"MCPCredentialsRejected: {MCPCredentialsRejected(...)}"`. Import `OAuthClientProvider` function-locally if `api.py` does not already import it. The existing `RuntimeError` branch stays for every non-matching failure (no test or JS reads its exact text).
   - Unit tests (`tests/test_oauth_test_connection_endpoint.py` style, `:289`): patch `api.httpx2.AsyncClient` with an `httpx2.MockTransport` answering 401 on every path and a real `OAuthClientProvider`; negative cases: no operator headers; PRM 200; PRM 500; transport error; Phase B entered from Phase A's stale-token fall-through. Path (a): `tests/test_mcp_connection_reset.py`-style with cached `no_auth`. Path (b): `tests/test_mcp_test_connection_negotiation.py::test_unexpected_status_then_401_signs_in_via_discover`'s pattern, with an operator header.

6. **Checkpoint.** Run the step-4/5 files plus `tests/test_auth_posture_probe.py`, `tests/test_imports.py`, then `make test-unit`, `ruff check`, `ruff format --check`. Record the result in the flight log under this leg. Do not start step 7 until green.

7. **`App.desktop.isWebview`** (AC11). In `theme.js`, define `App.desktop = App.desktop || {}; App.desktop.isWebview = function () {...}` on the `window.App` it creates (`:167`) and have the private `isDesktopWebview` call it (or replace its uses). `theme.js` loads first (`index.html:13`); `app.js` extends `App` in place, so do not reassign `App.desktop` there.

8. **`consent-link.js`** (AC12). New file under `static/js/`. Reuse the button styling the provider editor's `buildConsentBlock` uses (`provider-editor.js:630-680`) but with `consent-link-*` classes and its own small CSS, unscoped, in `static/css/components.css` (the provider editor's rules live under `.area-studio` in `studio.css` ~`:1666`, which chat cannot use; tokens only, `tests/test_token_definitions.py`). Literal testids per surface (a two-entry map inside the module, not string concatenation). Add the `<script>` tag after `ui/button.js` (`index.html:42`) and before `areas/chat.js` (`:71`). Add a load-order unit test modelled on `tests/test_tool_categories.py:117` (regex over `index.html` script srcs).

9. **Chat** (AC13, AC16). `areas/chat.js`:
   - `openConsentPopup` / `startLoginFlow` (`:1198-1249`): remove the "Popup blocked" branch; skip the `about:blank` pre-open when `App.desktop.isWebview()`; the early return consults the map's `consentUrl` (the button's closed-over `data.consent_url` can be stale); set `startedHere` in the per-flow map keyed `chatState.activeId() + '\u0000' + source_id` **synchronously, before the `fetch`**, so a consent frame arriving before the POST returns finds the entry. (`activeId()` is the client id while starting and the session id once joined, `chat.js:31-38`; an `auth_required` exists only after a session does, so the key is the session id.)
   - The `auth_required` handler, in its post-gate branch (the frame gate is `chatState.onFrame(data).accept`, `:1780`; consent frame navigation at `:1905-1912`; replay via `renderLoginRequiredButton` / `clearLoginRequiredButton`, `:1072-1098`, `:1256-1300`): store `consentUrl` when present; render the block inside `.login-required-group` and hide the `.login-required-btn` (keep it in the DOM so `clearLoginRequiredButton`'s `.login-required-btn[data-source-id]` selector still finds the group; or switch that selector to `.login-required-group[data-source-id]`; either way one group per source after any number of replays, tested); auto-open once per the AC13 rule; on a replay with `consent_url: null` and a stored `consentUrl`, render the block from the map.
   - `auth_resolved` / `auth_failed`: clear the map entry next to `closeOauthPopup` (`:1775-1777`), above the frame gate. The DOM change for `auth_failed` (remove the block, un-hide "Log in") goes in the gated branch (`~:1923`), since it touches the DOM; a switched-away session's DOM is rebuilt on rejoin from the replayed frame with an empty map entry, which correctly shows "Log in".
   - All new nodes via DOM APIs.

10. **MCP editor** (AC14). `areas/studio/mcp-server-editor.js::launchConsentPopup` (`:1836-1990`), `renderRetryUi` (`:1903-1918`), `onOAuthMessage` (`:1921-1945`), the poll (`:1949-1971`): split the status panel into a status-text child and a block container, keeping `data-testid="mcp-test-status"` on the outer panel (tests read it with `to_contain_text`: `tests/browser/test_flow_studio_mcp_editor.py` `:823`, `:1136`, `:1418`, `:1505`, `:1535`, `:1594`, `:1930`, plus `test_mcp_test_connection_button.py`, `test_flow_studio_library_list.py`, `test_flow_studio_library_focus.py`; re-check `:1535`, `:1594`, `:1930`, which grab the panel, after the split); render the block; try `window.open`; on `null` keep going; polling runs to `CONSENT_WAIT_MS` once the block shows; null-guard every popup use (`:1933`, `:1939`, `:1953`, `:1967`); remove the block on failed/expired/timeout. The `noAutoPopup` "Sign in" button (`:2074-2106`) calls `launchConsentPopup` as today.

11. **`mcp-error.js`** (AC15): add `else if (cls === 'MCPCredentialsRejected') { headline = …; }` before the `MCPConnectionError` arms (`mcp-error.js:16-20`).

12. **Browser tests** (AC13-AC16).
   - `tests/browser/test_oauth_modal_flow.py` (lane `shared`): `window.open` stubbed to return `null` → `/api/oauth/start` POSTed, no "Popup blocked", block rendered on the consent frame; `App.desktop.isWebview` stubbed true (do not define `window.chrome.webview`, which also makes `theme.js` POST `/api/window/chrome`) → no `about:blank` call; a replay frame with `consent_url: null` after the consent frame keeps the block and does not auto-open again; `auth_failed` removes the block. Update `test_button_click_opens_popup_with_window_open_features` so it still asserts exactly one browser-mode call (rename rather than delete if its intent changes).
   - `tests/browser/test_flow_studio_mcp_editor.py` (lane `mcp`): `window.open` → `null` renders the block, polling continues and tools list after `has_access_token` flips; the block survives the status-text updates; the `MCPCredentialsRejected` headline renders. Update `test_create_streamable_http_auto_run_auth_required_does_not_open_popup` as needed (the block appears after "Sign in" is clicked).

13. **Docs** (AC17) per DD7.

14. **Gate** (AC18) and the two falsifications from Verification Steps. Record per-lane times; flag any lane over budget.

## Edge Cases
- **A source with operator headers and `dcr_credentials` (OAuth provider attached)**: never `MCPCredentialsRejected` (AC2); stays `MCPAuthRequired`.
- **A 401 that carries `resource_metadata`** with operator headers: sign-in as today.
- **stdio sources**: never reach the rule (no 401); the type guard in step 3 keeps `build_request_headers` from being called on them.
- **Two chat sessions waiting on the same source**: the per-flow key includes the session id, so a flow started in one does not auto-open in the other.
- **Session switch mid-flow**: the clear on `auth_resolved` / `auth_failed` runs above the frame gate, so a switched-away session's entry still clears.
- **Clipboard unavailable** (insecure context): the `execCommand` fallback, as in the provider editor.
- **WebView2 auto-open from a WebSocket handler**: may be swallowed; not testable here; the HAT leg observes it. Do not add a server route.

## Files Affected
- `the_one/mcp/errors.py` - `MCPCredentialsRejected`
- `the_one/mcp/client.py` - `_signin_signal`, `_mark_dead` on rejection
- `the_one/interfaces/web/api.py` - paths (b) and (c), posture removal helper
- `tests/fixtures/mcp/asgi_401.py`, `tests/fixtures/oauth/__init__.py` - bare-401 options
- `the_one/interfaces/web/static/js/theme.js` - `App.desktop.isWebview`
- `the_one/interfaces/web/static/js/consent-link.js` - new
- `the_one/interfaces/web/static/js/areas/chat.js` - sign-in flow, per-flow state
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` - `launchConsentPopup`, status panel split
- `the_one/interfaces/web/static/js/mcp-error.js` - class rule
- `the_one/interfaces/web/static/css/components.css` - `consent-link-*` styles, unscoped
- `the_one/interfaces/web/static/index.html` - script tag
- Tests: `tests/test_mcp_client.py`, `tests/test_mcp_signin_detection.py`, `tests/test_mcp_tool_provider.py`, `tests/test_oauth_test_connection_endpoint.py`, `tests/test_mcp_connection_reset.py`, `tests/test_mcp_test_connection_negotiation.py`, a load-order test, `tests/browser/test_oauth_modal_flow.py`, `tests/browser/test_flow_studio_mcp_editor.py`
- Docs: `the_one/agents.md`, `CLAUDE.md`, `docs/ui-testid-registry.md`

## Citation Audit
Developer design review (2026-10-14) re-checked and added: `client.py:365,449,471,584,599,855,1005`; `_tool_provider.py:105-181`; `asgi_401.py:39-41`; `tests/fixtures/oauth/__init__.py:242`; `chat.js:31-38,1780`; `studio.css` ~`:1666`; `api.py:147-149`. Checked against `d2c98b1` on 2026-10-14: `client.py:352` `_mark_dead`; `index.html:13/33/35/42/71/82/85` script order (theme, app, mcp-error, ui/button, areas/chat, mcp-server-editor, provider-editor); `tests/test_tool_categories.py:117` script-src regex; `tests/test_mcp_error_classes_pinned.py:58-62` (`cls === '…'` regex); `tests/test_mcp_client.py:587,1127` and `tests/test_mcp_oauth_integration.py:285` pin `OAuthFlowError` → `MCPAuthRequired` with a provider attached (unchanged by this leg). Flight-spec citations re-verified in Architect cycle 2.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
