# Sortie: Honest MCP sign-in in the desktop app

**Status**: in-flight

## Charter

### Outcome
In the desktop app, signing in to an MCP server works through the system browser, and when a server simply rejects the configured key, the app says so instead of offering a sign-in.

### Why Now
On 2026-10-14 a revoked key on the Goldfinch MCP source showed up as a "Log in" button and then "Popup blocked", and a long session went into tracing it to a 401 on the key (after first chasing a protocol problem).

### Success Criteria
- [ ] In the desktop app, "Log in to {source}" in a chat opens the consent page in the system browser; finishing consent resumes the tool call; "Popup blocked" never appears.
- [ ] In the desktop app, MCP editor sign-in opens the system browser and notices completion by itself, then lists the tools without a manual re-test.
- [ ] A source whose configured key is rejected (401) by a server with no OAuth metadata shows a plain "the server rejected the configured credentials" error in the MCP editor and in chat: no sign-in button, and the source is not recorded as a sign-in server.
- [ ] In a normal browser, sign-in behaves as it does today, and real OAuth servers still sign in.

### Constraints
- pywebview stays on 5.x (6.x is blocked by the title-bar work).
- OAuth's protections do not change: the callback, the state checks and the pending-flow lifetime stay as they are.
- No new credential exemptions.

---

## Pre-Flight

### Objective
Make MCP sign-in work in the desktop app, and make a rejected key look like a rejected key. In chat and in the MCP editor, a sign-in that has a consent URL always shows it as a link ("Open sign-in page" + "Copy"), the way Claude Plan sign-in does. A `null` from `window.open` (the desktop webview always returns one, since pywebview hands the URL to the system browser) means "show the link and keep waiting", never "Popup blocked". Chat in the desktop app stops pre-opening `about:blank`. The MCP editor keeps polling for the token whether or not a window opened. Separately, when the operator configured a header and a server answers 401 with no OAuth metadata, Test connection and the chat tool call report "the server rejected the configured credentials" instead of offering a sign-in, and the source is not recorded as a sign-in server.

### Open Questions
- [x] Show the sign-in link in a normal browser too, or only when no window opened? → always, once the consent URL is known (operator, 2026-10-14; DD1)
- [x] Which configured headers count as operator-supplied credentials? → any operator header, not just `Authorization` (operator; DD4)
- [x] Server-side "open in system browser" route, or `window.open`? → `window.open`; no new route (operator agreed the leaning, 2026-10-14; DD2)
- [x] HAT server for the real sign-in path → the repo's OAuth fixture (`tests/fixtures/oauth/OAuthASStub`) run against a Windows test copy (operator; DD8)
- [x] Leg shape → one build leg plus an optional HAT leg (operator)
- [ ] Does a `window.open` called from a WebSocket handler (no user gesture) reach pywebview's `NewWindowRequested` in WebView2? → not verified; the design does not depend on it (DD2), the HAT observes it

### Design Decisions

**DD1 — Every MCP sign-in with a known consent URL shows it as a link.**
- Chat (`areas/chat.js`, the login-required group) and the MCP editor (`areas/studio/mcp-server-editor.js`, the status panel) render a consent-link block once a consent URL is known: a read-only URL field, "Open sign-in page" and "Copy" (clipboard, with the `execCommand` fallback the provider editor uses), plus one line: "Finish signing in in the browser window. This page updates when you're done."
- "Open sign-in page" is an `<a href="{url}" target="_blank" rel="noopener noreferrer">` styled as a button, not a named `window.open`: pywebview's GTK backend only hands `_blank` to the system browser (`webview/platforms/gtk.py:343-346`), and WebView2 hands any new window over (DD2). Completion never depends on `window.opener` (DD2).
- The block is DOM-built (no HTML strings: Mission 31 is removing them) in one small shared module, `static/js/consent-link.js` (`App.consentLink.build(url, {surface})`, `surface` `"chat"` or `"mcp"`), composed from existing pieces (`App.ui` button styling, a native read-only `<input>`), not a new `App.ui` factory. Its own classes (`consent-link-*`), not `plan-signin-*`. Testids are written as literals in the module, one set per surface (`chat-consent-link-url`/`-open`/`-copy`, `mcp-consent-link-url`/`-open`/`-copy`), so the registry extractor in `tests/test_ui_guards.py` sees them; registered in `docs/ui-testid-registry.md`. It loads after `ui/button.js` and before `areas/chat.js` and the studio editors in `index.html`, pinned by a load-order test in the style of `tests/test_tool_categories.py`.
- The provider editor's `buildConsentBlock` (`provider-editor.js:630`) is left alone. This is a third copy of the consent-and-copy block; the flight log notes it for Mission 31's consolidation.
- It shows in every environment, popup or not (operator).
- Rationale: one path that works whatever `window.open` returns, already proven by Claude Plan sign-in; it doubles as the fallback for a real popup blocker.
- Trade-off: a small visible addition in browsers where the popup did open.

**DD2 — `window.open` stays the way to reach the system browser; `null` never ends the flow.**
- No new server route: Mission 19 DD-1 kept "open in system browser" out of the API, and a route that opens a URL on the host from any authenticated caller is a new capability this sortie does not need. pywebview 5.x already sends a `window.open(url)` to the system browser (`webview/platforms/edgechromium.py::on_new_window_request`, `OPEN_EXTERNAL_LINKS_IN_BROWSER` default True; the shell sets no `webview.settings`, `shell.py:637-680`, `:852-856`).
- **Chat:** `startLoginFlow` no longer returns on a `null` popup. In a browser it keeps today's click-time `about:blank` pre-open (to keep the gesture) and navigates that popup when the consent URL arrives, as now. In the desktop webview (DD3) it skips the pre-open. It keeps today's early return when the consent URL is already known (`chat.js:1228`: open/navigate, no second `/api/oauth/start`); otherwise it POSTs `/api/oauth/start`.
  - **Per-flow state:** a map keyed by chat session id + source id holds `{consentUrl, startedHere, autoOpened}`. `startLoginFlow` sets `startedHere`. A frame with `consent_url` stores it and renders DD1's block in place of the "Log in" button (the block owns any further click while the flow is pending). It makes one best-effort `window.open(consent_url, '_blank')` only when `startedHere`, no popup is held, and not `autoOpened`.
  - **Replays:** the frame replayed on join/reconnect is rebuilt from the tool result's metadata (`app.py:1928`, `:2588`), so its `consent_url` is always `None`; the consent frame itself is broadcast once (`mcp/oauth/handlers.py:129-141`). When a replay with no URL arrives for a source whose state holds a `consentUrl`, the group is re-rendered with the block from the map, not the "Log in" button, so a reconnect neither loses the link nor offers a second `/api/oauth/start` (which would evict the pool, `api.py:4774`).
  - **Clearing:** the map entry is cleared on `auth_resolved` and `auth_failed` in the ungated part of the handler, beside `closeOauthPopup` (above the frame gate at `chat.js:1775`), so a session switch cannot strand it. On `auth_failed` the block is removed (its URL is dead); the group's "Log in" button and today's "OAuth failed: …" message stay for a retry.
  - The "Popup blocked" message is removed.
- **MCP editor:** `launchConsentPopup` renders DD1's block, then tries `window.open`; on `null` it does not `settle()` but starts the same `has_access_token` polling (500 ms, `CONSENT_WAIT_MS` 2 minutes).
  - **Mounting:** the status panel gets two children: a status-text element (which `'Awaiting sign-in…'` / `'Finalizing sign-in…'`, `mcp-server-editor.js:1947`, `:1956`, now write to instead of `statusEl.textContent`) and the block's own container. `renderRetryUi` (`:1905`, today `statusEl.innerHTML = ''`) clears the status text and the retry area only. The block stays visible until success; it is removed on a failed/expired result and on the 2-minute timeout (its URL is dead), and the retry "Sign in" starts a fresh flow.
  - **Polling:** once the block is shown, polling runs to `CONSENT_WAIT_MS` whether or not a popup exists or closes (today it stops about 3 s after the popup closes, so a browser user who closes the popup and finishes through the link would be missed). The `popup.closed` grace logic applies only when a popup handle exists, and only to update the status text.
  - **Null guards:** every use of the popup handle is guarded: the grace logic, `onOAuthMessage`'s failed/expired arms and the success finalize (`popup.closed` / `popup.close()`, `mcp-server-editor.js:1933`, `:1939`, `:1953`, `:1967`).
  - The "Popup blocked" message is removed. The auto-run path (`noAutoPopup`) is unchanged until its "Sign in" button is clicked: the click calls `launchConsentPopup`, which renders the block then.
- Completion stays token-based: chat already gets `auth_resolved` and resumes (`api.py::oauth_callback`); the editor polls (Mission 8 F4 pattern). No `postMessage` dependency is added.
- The auto-open from a WebSocket handler may not reach the system browser in WebView2 (no user gesture). Not verified; the link's click is a gesture, so the flow works either way. The HAT records which happens.

**DD3 — One shared desktop-webview check.**
- `theme.js::isDesktopWebview` (`theme.js:66-68`: `window.chrome.webview` or `window.pywebview`) is exposed as `App.desktop.isWebview()`. `theme.js` creates `window.App` (`:167`) and loads first (`index.html:13`), and `app.js` extends `App` in place, so the export is available to every later script; `theme.js` calls the shared function itself. `window.chrome.webview` exists at document start in WebView2 (`agents.md` "Windows test copy" findings), so the check is valid at click time.
- Used only to skip chat's `about:blank` pre-open (DD2). Nothing else branches on it.
- Rationale: the check already exists and is proven; a second copy would drift.

**DD4 — "Credentials rejected" is its own result when the operator supplied headers and the server has no OAuth metadata.**
- **Operator-supplied:** `build_request_headers(source)` (`streamable_http.py:153`) is non-empty: any `config.headers` row or non-OAuth-managed secret (`OAUTH_MANAGED_SECRET_KEYS`, `mcp/oauth/storage.py`). Any header counts (operator). This includes per-agent header overrides the tool provider applies (`_tool_provider.py:179`) and the self-configuration loopback's `secrets["Authorization"]` (`self_configuration/constants.py:87`, `manage.py:191,200`).
- **The type:** `MCPCredentialsRejected(MCPConnectionError)` in `mcp/errors.py`. A subclass, so every existing `MCPConnectionError` catch handles it gracefully: the agent build's Path A skip (`_tool_provider.py:312-337`), `_tool.py:168` (the tool result reads "[error] MCP source … unavailable: MCPCredentialsRejected: …"), `_build_and_test_no_auth_mcp`'s typed arm (`api.py:3428`). Phase A's `except MCPConnectionError` (`api.py:3840`) normally cannot see it (Phase A has an OAuth provider attached); in the corner where `build_oauth_provider_for_source` returns `None` (no chat session id, or `dcr_credentials` without a `client_id`, `provider_factory.py:103-107`) it can, and since the message carries none of the token-failure markers that arm returns an error and clears nothing. The class carries `# noqa: N818` like its siblings. Message: "{source name} rejected the configured credentials (401). Check the headers for this MCP server in Library › MCP servers, or the agent's MCPs tab if it overrides them."
- **Chat / pool path** (`mcp/client.py`): one factory, `_signin_signal(resource_metadata_url)`, builds the 401 result and is the only place `MCPAuthRequired` is constructed for a 401. Both routes call it: `_auth_required_since` (passing `AuthRecord.last_resource_metadata`, `_signin_record.py:39`) and `_classify_failure` row 0 for `DiscoverSignInRequired` (passing `exc.resource_metadata_url`, `client.py:424-432`; the route a no-era Goldfinch-shaped server takes: discover 401 then initialize 401, `_negotiate.py:96,113`). It returns `MCPCredentialsRejected` when operator headers are present, the 401 carried no `resource_metadata`, and the client has no OAuth provider attached (`self._auth_provider is None`, `client.py:247`; the pool attaches one only when `dcr_credentials` exist, `provider_factory.py:103-107`); otherwise `MCPAuthRequired` as today. The three `except* (OAuthFlowError, OAuthTokenError)` arms (`:566,:856,:995`) only run with a provider attached, so they keep `_oauth_flow_auth_required()`. `build_request_headers` is imported function-locally in `client.py`, so `tests/test_imports.py::test_import_agent_core_does_not_load_mcp_oauth` stays green. When `list_tools` / `call_tool` on a warm client raise `MCPCredentialsRejected`, the client marks itself dead (the existing `_mark_dead()`), so a corrected header (including an agent override) takes effect on the next acquire instead of after the pool reaps the entry. A mid-session rejection reaches the agent loop's generic arm (`core.py:630`, `[error] Tool execution failed: …`), not `_tool.py:168`, which wraps only `acquire`.
- **Test connection** (`api.py::test_mcp_connection`), three paths:
  - (a) **Cached `no_auth`** (`api.py:3713`, the usual "key worked, then was revoked" case): the `MCPClient` rule fires, `_build_and_test_no_auth_mcp`'s typed arm returns `{"status": "error", "error": "MCPCredentialsRejected: …"}`. The cached `no_auth` posture stays: the server is still a header-auth server; the key is what's wrong.
  - (b) **DD9 fall-through** (`from_fallthrough=True`, `api.py:3737-3750`): `_build_and_test_no_auth_mcp` gains a branch (merged into the `except MCPAuthRequired` arm at `:3423`, or a new arm before the typed arm at `:3428`) that treats `MCPCredentialsRejected` like `MCPAuthRequired` and returns `_SIGNIN_REQUIRED`, so Phase B decides with its own discovery evidence. A 2026-07-28-only OAuth server that sends a bare 401 still signs in.
  - (c) **Probe `oauth` → Phase B** (the Goldfinch-after-reset case). *In-flight amendment (leg 01 design review, 2026-10-14): the rule applies only when Phase B was entered from this request's probe `"oauth"` verdict or the DD9 fall-through, which sent the operator headers and got 401 (the rejection evidence; Phase B's own requests carry no operator headers and still do not); not after Phase A's stale-token fall-through.* The probe still returns `"oauth"` on a 401 (Mission 29 DD9 unchanged; `test_probe_oauth_when_operator_headers_insufficient` keeps its assertion). The classification happens inside `_drive_flow_test`, where `provider` and the caught `exc` are both in scope (httpx2 runs the auth flow inline, so `exc` is the SDK's own exception, not a group). When `exc` is an `OAuthRegistrationError` from a failed `/register` (its message starts "Registration failed:", which excludes `check_registration_usable`'s post-2xx error, `oauth2.py:100-110`), operator headers are present, `provider` is an `OAuthClientProvider` (it is typed `httpx2.Auth | None`), and `provider.context.protected_resource_metadata` and `provider.context.oauth_metadata` are both `None` (`oauth2.py:162-163`; with every discovery GET answered 401 the SDK sets neither and falls through to `/register`, `utils.py:234`, `:299-303`), it sets a private sentinel exception on `consent_url_future`; the outer handler maps the sentinel to `{"status": "error", "error": "MCPCredentialsRejected: …"}` and removes `_cache.auth_posture`. Any other failure (a PRM 5xx/429, a transport error) keeps today's `RuntimeError` → `auth_flow_error` / `consent_url_timeout`.
- **Why (c) removes the posture while (a) keeps `no_auth`:** in (a) an earlier probe saw a 200 with these headers, which proves a header-auth server; in (c) no request has ever succeeded, so the app does not know what the server is, and removing the posture lets the next Test classify it fresh instead of asserting `no_auth` on no evidence. It is bookkeeping, so the source is not recorded as a sign-in server (charter): nothing in the UI reads `auth_posture`, the pool only checks `no_auth` (`_pool.py:203`), and `api.py:3725` re-probes on both `None` and `"oauth"`.
- **UI:** `mcp-error.js::mcpErrorMessage` gains a class rule written exactly `cls === 'MCPCredentialsRejected'` (the form `tests/test_mcp_error_classes_pinned.py::_recognised_classes` recognises), ahead of the `MCPConnectionError` rules: headline "The server rejected the configured credentials. Check the headers on this MCP server." The raw text stays under "Technical details". The editor's status light has only success/idle states from `_cache.tools` (`mcp-server-editor.js:561-566`), so a source with cached tools still shows "Connected" beside the error; pre-existing, not changed here.
- Rationale: the operator gave a key; the server refused it and offers no sign-in. Saying so is the honest result. The chat path needs no discovery, because without an OAuth provider (no `dcr_credentials`) chat sign-in cannot start anyway (`oauth_start` 400s, `api.py:4757`).
- Trade-off: a server that uses both a static header and OAuth but publishes no metadata at all gets "rejected" instead of an unreachable sign-in. The self-configuration loopback answering 401 now reads "rejected" instead of a login button that cannot work.

**DD5 — No schema, route or credential-gate change.**
- No new `auth_posture` value, no new route, no change to `/api/oauth/callback`, state checks or `_TTL_SECONDS` (charter constraints). `SECURITY-MODEL.md` needs no change.

**DD6 — Tests.**
- **Fixtures:** `tests/fixtures/mcp/asgi_401.py` gains an option to answer a bare 401 (`resource_metadata=None` → no `WWW-Authenticate`); today it always sends `resource_metadata` (`:69`, `:84`). Its discovery paths 401 too, to model Goldfinch. `OAuthASStub` (`tests/fixtures/oauth/`, a real threaded server) gains a matching "bare 401, no metadata" mode, so the HAT runs one server for both walk items. Test-connect path (c) cannot reach an ASGI fixture (`_drive_flow_test` builds its own `httpx2.AsyncClient`): its unit tests patch `api.httpx2.AsyncClient` with a `MockTransport` answering 401 everywhere and use a real `OAuthClientProvider`, as `tests/test_oauth_test_connection_endpoint.py:289` does.
- **Unit:** `MCPClient` raises `MCPCredentialsRejected` vs `MCPAuthRequired` across operator headers × `resource_metadata` × provider attached, on both routes (`_auth_required_since`, and `DiscoverSignInRequired` with and without a remembered era); `core._execute_tool` and `_tool.py` render it as an error result with no `is_auth_required` metadata; the agent build's Path A skips it without crashing; test-connect paths (a), (b) and (c) with their negative cases (no operator headers → `auth_flow_error`; metadata present → sign-in; PRM 5xx → `auth_flow_error`); the self-configuration loopback's 401 gives `MCPCredentialsRejected` and its posture stays `no_auth`.
- **Browser:** extend `tests/browser/test_oauth_modal_flow.py` (lane `shared`): `window.open` stubbed to `null` still POSTs `/api/oauth/start`, shows no "Popup blocked", renders the block when the consent URL arrives; `App.desktop.isWebview` stubbed true (not `window.chrome.webview`, which would also make `theme.js` POST `/api/window/chrome`) → no `about:blank` call; a replayed frame with a null URL after the consent frame keeps the link block and does not auto-open; `auth_failed` removes the block. Extend `tests/browser/test_flow_studio_mcp_editor.py` (lane `mcp`): `window.open` → `null` renders the block, polls, lists tools after `has_access_token` flips; the block survives the status-text updates and the popup closing, and polling continues; the `MCPCredentialsRejected` headline (and `tests/test_mcp_error_classes_pinned.py` stays green). New browser tests go in these two files, not new files: a file's name picks its lane (`test_mcp_*` → `agents`, `test_flow_chat*` → `chats`, `mcp` is an explicit list, `scripts/run-tests.sh:180-184`), and `chats` has about 12 s of budget left. Existing assertions that change, named in the leg: `test_oauth_modal_flow.py::test_button_click_opens_popup_with_window_open_features` (still one call in browser mode) and `test_flow_studio_mcp_editor.py::test_create_streamable_http_auto_run_auth_required_does_not_open_popup`.
- `consent-link.js` is not an `App.ui` factory, so no inventory row or contract test; the sink check in `tests/test_ui_guards.py` must stay clean; the load-order test pins its position.

**DD7 — Docs.**
- `the_one/agents.md`: "MCP error translation" (the new result, its rule and the single `_signin_signal` factory), "MCP F2 Client Foundation" (DD9 note: paths (a)-(c)), "Desktop launcher" (`App.desktop.isWebview`, `window.open` → system browser, the sign-in link). `CLAUDE.md`'s MCP paragraph gains one sentence. `docs/ui-testid-registry.md` registers the new testids.

**DD8 — HAT on the Windows desktop with the OAuth fixture.**
- A Windows test copy (`scripts/windows_test_copy.py`, ports ≥ 8490, never 8484/8485, scratch data dir) of the leg's build, with `OAuthASStub` (`tests/fixtures/oauth/`) running on the dev box (reachable at 127.0.0.1 through WSL mirrored networking). A small runner may be needed to start it standalone, with a way to invalidate issued tokens (the stub issues a fixed token) so chat can reach `auth_required` on a source that already has `dcr_credentials`.
- Walk: editor sign-in in the system browser → tools listed with no re-test; chat "Log in" → system browser → tool call resumes, and a reconnect does not reopen the browser; a source with a wrong header against a bare-401 server (`OAuthASStub`'s bare-401 mode from DD6, or Goldfinch with a bad key) → "credentials rejected" in the editor and in chat, no login button; one check in a normal browser that the popup still opens.
- This is the only check in the real WebView2 engine (squawk 0138).

### Citation Audit

Verified against the working tree at `d2c98b1`:

| Citation | Status |
|---|---|
| `static/js/areas/chat.js:1213,1222-1225` — `openConsentPopup(url || 'about:blank')`; `startLoginFlow` returns after "Popup blocked" on a null popup, before `POST /api/oauth/start` | verified |
| `static/js/areas/studio/mcp-server-editor.js:1851-1855` — null popup → "Popup blocked", `settle()`, no polling; `:1886` `CONSENT_WAIT_MS = 120000`; `:1965` polls `has_access_token` | verified |
| `static/js/theme.js:66-68` — `isDesktopWebview()` is `window.chrome.webview || window.pywebview`, private to the IIFE | verified |
| `static/js/areas/studio/provider-editor.js:462,485,630` — `openConsentPopup` ignores the return; `buildConsentBlock` renders `plan-signin-url` / `-open-btn` / `-copy-btn` | verified |
| `.venv/.../webview/platforms/edgechromium.py:226-232` — `on_new_window_request` sets `Handled=True`, `webbrowser.open(uri)` when `OPEN_EXTERNAL_LINKS_IN_BROWSER` | verified |
| `interfaces/web/api.py:3900-3952` — `_drive_flow_test` posts with `auth=provider`; exception → `auth_flow_error: …`; `provider` in scope | verified |
| `interfaces/web/api.py:4757-4761` — `oauth_start` 400s without `dcr_credentials` | verified |
| `.venv/.../mcp/client/auth/oauth2.py:162-163` — `OAuthContext.protected_resource_metadata` / `oauth_metadata` default `None`, set only on discovery success (`:360`) | verified |
| `mcp/transports/streamable_http.py:153-188` — `build_request_headers` merges `config.headers` + non-managed secrets | verified |
| `mcp/_signin_record.py:39` — `AuthRecord.last_resource_metadata` | verified |
| `mcp/client.py:364,401-433` — `_auth_required_since` feeds `_classify_failure`; `except* (OAuthFlowError, OAuthTokenError)` arms at `:566,:856,:995` | verified |
| `mcp/errors.py` — `MCPClientError` base; `MCPAuthRequired` subclass | verified |
| `agent/core.py` `_execute_tool` — `MCPAuthRequired` → auth metadata; generic `Exception` → `[error] Tool execution failed: {e}` | verified |
| `static/js/mcp-error.js:10-30` — class-prefix headline rules, generic fallback | verified |
| `mcp/client.py:424-432` — `_classify_failure` row 0 builds `MCPAuthRequired` from `DiscoverSignInRequired` directly, bypassing `_auth_required_since` (Architect, cycle 1) | verified |
| `mcp/_tool_provider.py:312-337` — agent-build Path A catches `MCPAuthRequired` and `(SandboxError, MCPConnectionError, MCPVersionMismatch)` only | verified (Architect) |
| `mcp/_tool.py:168` — `except (SandboxError, MCPConnectionError, MCPVersionMismatch)` | verified |
| `interfaces/web/api.py:3423-3429` — `_build_and_test_no_auth_mcp`: `MCPAuthRequired` → `_SIGNIN_REQUIRED` when `from_fallthrough`; typed `MCPConnectionError` arm returns `"{type}: {e}"` | verified |
| `mcp/client.py:247` — `self._auth_provider: httpx2.Auth | None` | verified |
| `tests/fixtures/mcp/asgi_401.py:69,84` — always sends `WWW-Authenticate: Bearer resource_metadata=…` | verified |
| `.venv/.../mcp/client/auth/utils.py:234,299-303` — AS-metadata 4xx → try next; `/register` non-2xx → `OAuthRegistrationError` | verified (Architect) |
| `static/js/theme.js:167` / `index.html:13` — `theme.js` creates `window.App` and loads first | verified (Architect) |

### Prerequisites
- [x] pywebview 5.4 in the venv; `<6` pin in `pyproject.toml` (verified)
- [x] OAuth fixture `tests/fixtures/oauth/` exists and serves PRM/AS metadata/DCR/authorize/token (verified)
- [ ] Windows test copy apparatus works on this host (`scripts/windows_test_copy.py`): re-verify at the HAT leg's start (external session: the operator's Windows desktop)

### Pre-Flight Checklist
- [x] All open questions resolved (the WebView2 auto-open question is HAT-observed by design)
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified (Windows apparatus: at HAT time)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
One build leg changes the two JS sign-in paths (chat, MCP editor) and adds the shared consent-link module and `App.desktop.isWebview`; adds `MCPCredentialsRejected` and its classification points (the single `_signin_signal` factory in `MCPClient`; the fall-through branch in `_build_and_test_no_auth_mcp`; the sentinel in `_drive_flow_test`); adds the fixture options; adds the `mcp-error.js` rule; updates docs and tests. The optional HAT leg walks the result on the Windows desktop against the OAuth fixture and a no-metadata 401 server.

### Checkpoints
- [ ] Unit tier green with the new classification tests
- [ ] Browser lanes `shared` and `mcp` green with the new sign-in tests
- [ ] Full gate green
- [ ] HAT on Windows: all four walk items pass

### Adaptation Criteria

**Divert if**:
- The SDK's `OAuthContext` metadata is not reachable or not reliable after a failed Phase B (DD4's evidence), so a different "no metadata" signal is needed.
- Reaching the system browser from the desktop webview turns out to need a server route after all.

**Acceptable variations**:
- Exact wording of messages and the link's helper line.
- Whether the HAT uses `asgi_401.py` or Goldfinch for the no-metadata 401 server.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `honest-sign-in` - DD1-DD7: sign-in link and no "Popup blocked" in chat and the MCP editor; desktop check; `MCPCredentialsRejected` through the single `_signin_signal` factory and test-connect paths (a)-(c); error headline; fixture option; tests; docs. Mid-leg checkpoint: the backend classification (DD4) lands with its unit tests green before the JS work starts.
- [ ] `hat-and-alignment` *(optional)* - DD8: guided HAT on the Windows desktop with the OAuth fixture, fixes as needed

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
The charter's four criteria, observed in the HAT (DD8) on the Windows desktop app, plus the unit and browser tests named in DD6.
