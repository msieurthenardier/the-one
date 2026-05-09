# Leg: 01-oauth-frontend-strip

**Status**: landed
**Flight**: [OAuth simplification + Test connection button](../flight.md)

## Objective

Delete every frontend code path that supported the GitHub-legacy non-DCR OAuth manual-entry flow — the F1 `mcp-oauth-section` UI block in the MCP-source editor, the manual-entry sub-form in `oauth-modal.js`, and the `oauth_manual_registration_required` WebSocket handler in `chat.js` — leaving F5's spec-compliant DCR happy path as the only OAuth UI surface.

## Context

L0 (oauth-backend-strip) landed in this same flight. After L0, the backend has no `/api/oauth/manual-register` endpoint, no `config.oauth.*` validator, no `ManualOAuthClientProvider`, no `registration_method` discriminator, and no `oauth_client_secret` write paths. L1 closes the loop: every JavaScript surface that produced or consumed those backend artifacts is removed in lockstep.

L1 is purely deletion + 1 surgical test edit. There is no new behavior introduced. After L1 the source-editor renders no OAuth section at all (regular `streamable-http` sources have only `url` + `headers`); the OAuth modal renders the standard consent flow only (no manual-entry toggle); chat.js drops the manual-entry chat handler; two browser test files retain only their non-manual-flow tests.

Key learnings from prior legs (flight log Phase 1b recon + L0 anomaly A1):

- L0 already deleted two browser test functions (`test_create_streamable_http_source_with_oauth` in `test_flow_studio_mcp_editor.py`, `test_manual_register_submission_persists_dcr_credentials` in `test_oauth_modal_flow.py`) because their Python code referenced backend paths L0 was deleting. L1 must NOT re-delete these — they're already gone. The remaining tests in those files are L1's surgical-edit scope only.
- Recon classified `tests/browser/test_oauth_modal_flow.py` as a manual-flow file in its entirety, but in fact it has 2 non-manual tests (`test_modal_closes_on_auth_resolved_event` is one) that test the standard OAuth modal — those stay. Only manual-flow tests are deleted.
- The `MASKED_SENTINEL` constant in `mcp-server-editor.js:33` is used by NON-OAuth code paths (the operator-supplied env-var sensitive-key save logic) and must NOT be deleted.
- `mcp-server-editor.js` line 226 has `if (sk === 'oauth_client_secret') continue;` — this is a per-key skip in the editor's render loop; deleting the OAuth section makes the skip dead-letter and the line is removed.

## Inputs

What exists before this leg runs:

- Branch `flight/6_5-oauth-simplification` with L0 landed (uncommitted)
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` (943 LOC) — contains the F1 `mcp-oauth-section` block across 4 regions:
  - Line 9: HTML-shape comment
  - Line 24: `secrets["oauth_client_secret"]` payload-key comment
  - Line 122: HTML insertion `<div class="editor-section mcp-oauth-section ... data-testid="mcp-oauth-section">`
  - Line 226: `if (sk === 'oauth_client_secret') continue;` in the editor's render-keys loop
  - Lines 269-271: form-population read of `oauth.issuer_url`, `oauth.client_id`, `oauth.redirect_uri`, `oauth_client_secret`
  - Lines 276-326: form-population write — 6-field UI render (Issuer URL, Client ID, Scopes chip-list, Redirect URI, Client Secret with eye/lock controls)
  - Lines 356-357: field-id list arrays referencing `oauth-issuer-url`, `oauth-client-id`, `oauth-redirect-uri`, `oauth-client-secret`
  - Lines 368-373: chip-list state seed for `oauth-scopes`
  - Lines 525-526: `oauthEye` event handler bind for the client-secret reveal eye
  - Lines 692-772: form-population block on edit-mode (re-render of OAuth fields when source loads)
  - Lines 891-938: save-mode payload assembly that builds `config.oauth = {...}` + `secrets.oauth_client_secret = MASKED_SENTINEL | value | ''`
- `the_one/interfaces/web/static/js/oauth-modal.js` (371 LOC) — contains:
  - Module docstring (lines 5-22) referencing `/api/oauth/manual-register` and `oauth_manual_registration_required`
  - Lines 42-54: HTML-shape comment showing the `oauth-modal-manual-toggle-btn` + `oauth-modal-manual-form` structure
  - Lines 83, 88: `buildAndAttach(opts, /*manualMode=*/false)` — main path stays, `manualMode` parameter goes
  - Lines 91-104: `openManual` function — DELETE entirely (the public API export goes too at line 368)
  - Lines 123-176: manual-form HTML rendering inside `buildAndAttach` (toggle button, form, 3 input fields, submit button)
  - Lines 198, 255, 280-303, 357: manual-form event handlers (toggle click, submit POST to `/api/oauth/manual-register`, manual-mode rendering branch)
  - Line 368: `openManual: openManual,` in the public API object
- `the_one/interfaces/web/static/js/areas/chat.js` line 670: WebSocket message-type branch `else if (data.type === 'oauth_manual_registration_required')` (lines 670-676)
- `tests/browser/test_oauth_modal_flow.py` (141 LOC after L0 deletion of `test_manual_register_submission_persists_dcr_credentials`):
  - Lines 101-119: `test_manual_entry_disclosure_toggles` — exercises the `oauth-modal-manual-form` and `oauth-modal-manual-toggle-btn` UI
  - Other tests: standard-modal flow tests (e.g. `test_modal_closes_on_auth_resolved_event`) — stay
- `tests/browser/test_flow_studio_mcp_editor.py` (510 LOC after L0 deletion of `test_create_streamable_http_source_with_oauth`):
  - Lines 224, 231: in `test_type_change_swaps_field_visibility`, two assertions on `[data-testid="mcp-oauth-section"]`'s `is-hidden` class on stdio↔streamable-http swap
  - Other tests: stdio source create/edit, kv-row handling, navigation gates — stay

## Outputs

What exists after this leg completes:

- `mcp-server-editor.js` no longer has any `mcp-oauth-section`, `oauth_client_secret`, `oauth-issuer-url`, `oauth-client-id`, `oauth-redirect-uri`, `oauth-client-secret`, `oauth-scopes`, or `config.oauth` references in production paths. The 4 regions enumerated in Inputs are gone. The file's `MASKED_SENTINEL` constant remains (used by non-OAuth code paths). Approximate post-strip LOC: ~750 (down from 943).
- `oauth-modal.js` no longer renders a manual-entry toggle, manual-entry form, or manual-register POST. The `openManual` function and its public-API export are gone. `buildAndAttach`'s `manualMode` parameter is removed (every call passes `false` post-strip; the parameter and all branches reading it go). Approximate post-strip LOC: ~280 (down from 371).
- `chat.js` no longer has the `oauth_manual_registration_required` WebSocket-message branch (lines 670-676 deleted; surrounding `else if` chain still well-formed).
- `tests/browser/test_oauth_modal_flow.py` no longer contains `test_manual_entry_disclosure_toggles`. The remaining tests (regular modal flow) pass.
- `tests/browser/test_flow_studio_mcp_editor.py`'s `test_type_change_swaps_field_visibility` no longer asserts on `mcp-oauth-section` visibility — those 2 lines are removed; the test still verifies `mcp-stdio-only`, `mcp-streamable-http-only`, and `kv-section-title` swaps on transport-type change.
- `grep -rn "ManualOAuth\|manual_metadata\|/oauth/manual-register\|registration_method\|oauth_client_secret\|config\.oauth\|mcp-oauth-section\|oauth_manual_registration_required\|oauth-modal-manual" the_one/ tests/` returns 0 hits (across `*.py` AND `*.js` AND `*.html`).
- All retained pytest suites (including browser tests) pass under `docker compose exec the-one pytest` (full suite). Browser tests require the dev container to be up; `make rebuild` if not.

## Acceptance Criteria

- [ ] `grep -rn "mcp-oauth-section" the_one/interfaces/web/` returns 0 hits
- [ ] `grep -rn "oauth_client_secret" the_one/interfaces/web/` returns 0 hits
- [ ] `grep -rn "oauth-issuer-url\|oauth-client-id\|oauth-client-secret\|oauth-redirect-uri\|oauth-scopes" the_one/interfaces/web/` returns 0 hits
- [ ] `grep -rn "config\.oauth" the_one/interfaces/web/` returns 0 hits
- [ ] `grep -rn "openManual\|oauth-modal-manual\|manualMode" the_one/interfaces/web/static/js/oauth-modal.js` returns 0 hits
- [ ] `grep -rn "oauth_manual_registration_required" the_one/interfaces/web/static/js/areas/chat.js` returns 0 hits
- [ ] `grep -rn "/oauth/manual-register" the_one/interfaces/web/` returns 0 hits
- [ ] Combined frontend grep sweep: `grep -rn "ManualOAuth\|manual_metadata\|/oauth/manual-register\|registration_method\|oauth_client_secret\|config\.oauth\|mcp-oauth-section\|oauth_manual_registration_required\|oauth-modal-manual" the_one/interfaces/web/ tests/browser/` returns 0 hits
- [ ] `mcp-server-editor.js` MASKED_SENTINEL constant still exists at line ~33 (declared with `var MASKED_SENTINEL = '__MASKED__';`) and is referenced at least once in non-OAuth code paths (the kv-secrets save logic — verify with `grep -n "MASKED_SENTINEL" mcp-server-editor.js`)
- [ ] `oauth-modal.js` `App.oauthModal.open(opts)` (the standard, non-manual flow) is unchanged — its public-API export at line ~367 remains; only `openManual` is dropped from the export object
- [ ] `oauth-modal.js` `buildAndAttach` is now a single-arg function (`function buildAndAttach(opts)` instead of `function buildAndAttach(opts, manualMode)`); every internal call passes only `opts`
- [ ] `chat.js` WebSocket handler still has the `auth_required` and `auth_resolved` branches (those are F5's chat-path lazy-OAuth that survives F6.5); only `oauth_manual_registration_required` is removed
- [ ] `tests/browser/test_oauth_modal_flow.py` no longer defines `test_manual_entry_disclosure_toggles`; the remaining tests still pass when invoked: `docker compose exec the-one pytest tests/browser/test_oauth_modal_flow.py -v` exits 0
- [ ] `tests/browser/test_flow_studio_mcp_editor.py::test_type_change_swaps_field_visibility` no longer asserts on `[data-testid="mcp-oauth-section"]` (the 2 assertion lines at ~224 and ~231 are removed); the test still verifies the other field-visibility swaps; `docker compose exec the-one pytest tests/browser/test_flow_studio_mcp_editor.py -v` exits 0
- [ ] Manual smoke (browser, post-`make rebuild`): navigate to `#studio/mcp-sources/new`, set type=streamable-http; only `url` and headers section render — no OAuth section appears at all. The transport-type-swap behavior (stdio↔streamable-http hides/shows `mcp-stdio-only` / `mcp-streamable-http-only` blocks) still works. (Verification step is OPTIONAL since browser tests cover it; skip if browser tests pass cleanly.)
- [ ] Full test suite passes inside the dev container: `docker compose exec the-one pytest` exits 0 (modulo the same pre-existing failures L0 documented: `test_mcp_pool.py` hang + 3 `test_mcp_sandbox_integration.py` env failures — neither is in L1's scope)
- [ ] Module-level JS smoke: `oauth-modal.js` and `mcp-server-editor.js` load without ReferenceError when included in the page — verified by browser-test pass (above) since browser tests load real pages

## Verification Steps

How to confirm each criterion is met:

- **Frontend grep sweeps** (run from project root):
  ```bash
  grep -rn "mcp-oauth-section" the_one/interfaces/web/ && echo FAIL || echo OK
  grep -rn "oauth_client_secret" the_one/interfaces/web/ && echo FAIL || echo OK
  grep -rn "oauth-issuer-url\|oauth-client-id\|oauth-client-secret\|oauth-redirect-uri\|oauth-scopes" the_one/interfaces/web/ && echo FAIL || echo OK
  grep -rn "config\.oauth" the_one/interfaces/web/ && echo FAIL || echo OK
  grep -rn "openManual\|oauth-modal-manual\|manualMode" the_one/interfaces/web/static/js/oauth-modal.js && echo FAIL || echo OK
  grep -rn "oauth_manual_registration_required" the_one/interfaces/web/static/js/areas/chat.js && echo FAIL || echo OK
  grep -rn "/oauth/manual-register" the_one/interfaces/web/ && echo FAIL || echo OK
  ```
  All 7 must print `OK`.

- **Combined frontend+browser-test sweep**:
  ```bash
  grep -rn "ManualOAuth\|manual_metadata\|/oauth/manual-register\|registration_method\|oauth_client_secret\|config\.oauth\|mcp-oauth-section\|oauth_manual_registration_required\|oauth-modal-manual" the_one/interfaces/web/ tests/browser/ && echo FAIL || echo OK
  ```
  Must print `OK`.

- **MASKED_SENTINEL preservation**:
  ```bash
  grep -n "MASKED_SENTINEL" the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js
  ```
  Must show at least 2 hits (one definition, one or more non-OAuth usages — typically in the kv-secrets save block around lines 870-880 in current code).

- **`buildAndAttach` signature**: open `oauth-modal.js`, find `function buildAndAttach`, confirm exactly one `(opts)` parameter (no `manualMode` second arg).

- **`chat.js` WebSocket handler structure**: open `chat.js`, find the WebSocket message-handler `switch`/`else-if` chain. Confirm `auth_required` and `auth_resolved` cases are present and unchanged; confirm `oauth_manual_registration_required` is absent.

- **Browser tests**:
  ```bash
  docker compose exec the-one pytest tests/browser/test_oauth_modal_flow.py tests/browser/test_flow_studio_mcp_editor.py -v
  ```
  Exits 0. (If `make rebuild` is needed first, run that.)

- **Full suite**:
  ```bash
  docker compose exec the-one pytest
  ```
  Exits 0 (modulo pre-existing failures L0 documented).

## Implementation Guidance

The leg is two passes:
1. Delete (or surgically edit) the 5 frontend files in any order — they don't depend on each other at edit-time, only at runtime, and all changes are deletions of currently-active code paths.
2. Run grep sweeps + browser tests; iterate on any miss.

Edit by symbol match where possible — the line numbers in Inputs/Outputs are guidance, not contract. JS files are subject to drift; grep before editing.

### Step 1: `mcp-server-editor.js` — delete the F1 OAuth-config-editor block

Open the file; ~943 LOC. The OAuth-section code is in 6 disjoint regions; delete each in order to keep the file structurally valid mid-edit.

**Region 1: Top-of-file comments (lines 9, 24)**

- Line 9: comment listing `mcp-oauth-section` as one of the editor's HTML blocks. Delete the line (or update the comment to remove just that bullet, depending on the comment shape).
- Line 24: comment paragraph about `secrets["oauth_client_secret"]` payload key. Delete the paragraph (read 5 lines of surrounding context to confirm boundaries).

**Region 2: HTML mount + `renderOAuthFields` helper (lines 120-125 + 267-309)**

The OAuth section is split across TWO non-contiguous locations — a thin mount block in the main render, and a separate helper function that produces the inner field HTML. Delete BOTH.

- **Region 2a — Section mount, lines 120-125** (6 lines):
  ```javascript
  // ── OAuth section (streamable-http only) ──────────────────────────
  var oauthHidden = (type !== 'streamable-http');
  html += '<div class="editor-section mcp-oauth-section' + (oauthHidden ? ' is-hidden' : '') + '" data-testid="mcp-oauth-section">';
  html += '<div class="section-title">OAuth Client Configuration</div>';
  html += renderOAuthFields(source);
  html += '</div>';
  ```
  This is the entire 6-line block including the `oauthHidden` declaration. Delete in one pass.
- **Region 2b — `renderOAuthFields` helper, lines 267-309** (43 lines): the `function renderOAuthFields(source) { ... }` declaration that returns the 6-field inner HTML (Issuer URL, Client ID, Scopes chip-list, Redirect URI, Client Secret with eye/lock controls). Delete the entire function.
- After both deletions, `grep -n "renderOAuthFields\|oauthHidden\|mcp-oauth-section" mcp-server-editor.js` should return 0 hits.

**Region 3: Render-loop skip (line 226)**

- Line 226: `if (sk === 'oauth_client_secret') continue;` inside a for-loop over secret keys.
- This is a vestigial skip — once the OAuth section is gone, no UI renders `oauth_client_secret`, so the skip-to-prevent-double-render is dead.
- Delete the line.

**Region 4: Three disjoint OAuth references in `applyTransportVisibility` + `revertEditorToSource`**

The pre-review draft mistakenly grouped these as one block. They are three separate edits:

- **Region 4a — `applyTransportVisibility` mcp-oauth-section toggle, lines 692-693** (2 lines):
  ```javascript
  var oauthSection = container.querySelector('.mcp-oauth-section');
  if (oauthSection) oauthSection.classList.toggle('is-hidden', type !== 'streamable-http');
  ```
  Delete both lines. The surrounding `applyTransportVisibility` function still toggles `mcp-stdio-only` / `mcp-streamable-http-only` and the `kv-section-title` — both stay.
- **Region 4b — `revertEditorToSource` staticMap OAuth keys, lines 719-722** (4 lines):
  ```javascript
  'oauth-issuer-url': (source.config && source.config.oauth && source.config.oauth.issuer_url) || '',
  'oauth-client-id': (source.config && source.config.oauth && source.config.oauth.client_id) || '',
  'oauth-redirect-uri': (source.config && source.config.oauth && source.config.oauth.redirect_uri) || '',
  'oauth-client-secret': (source.secrets && source.secrets.oauth_client_secret) || ''
  ```
  Delete the 4 entries from `staticMap`. The other entries (name, type, command, cwd, url) stay. Watch the trailing comma on the line BEFORE the deletion (line 718 `'url': ...,`) — after delete, that line should NOT have a trailing comma if it's now the last entry, but keeping the comma is also valid JS.
- **Region 4c — `revertEditorToSource` scopesHost chip-list re-mount, lines 768-779** (12 lines):
  ```javascript
  var scopesHost = container.querySelector('[data-field="oauth-scopes"].chip-list-editor');
  if (scopesHost && scopesHost.parentNode) {
    var wrapper2 = document.createElement('div');
    wrapper2.innerHTML = helpers.renderChipListEditor('oauth-scopes',
      (source.config && source.config.oauth && source.config.oauth.scopes) || [],
      null, {});
    var newScopes = wrapper2.firstChild;
    scopesHost.parentNode.replaceChild(newScopes, scopesHost);
    if (helpers.wireChipListEditor) {
      helpers.wireChipListEditor(newScopes, function () { /* dirty-tracking handled externally */ });
    }
  }
  ```
  Delete the entire `var scopesHost = ...` through closing `}` block. The PRECEDING block re-mounting the `args` chip-list (lines ~753-767) is NOT OAuth-related and stays.

**Region 5: `collectOAuthSection` function + its call site**

The save-mode OAuth payload assembly is encapsulated in a named function `collectOAuthSection`. Delete BOTH the function declaration and its single call site.

- **Region 5a — Function declaration `collectOAuthSection`, lines 889-940** (52 lines): the entire `function collectOAuthSection(container, source, config, secrets, isEdit) { ... }` block. Includes the docstring comment lines (890-899), the field-element queries (901-905), the value reads (907-912), the `hasAnyOAuth` / `hadStoredSecret` flags (914-915), the `if (hasAnyOAuth)` branch building `config.oauth = oauth` and the `MASKED_SENTINEL` write (917-934), and the `else if (isEdit && hadStoredSecret)` stranded-secret branch (935-939). All locals (`issuerEl`, `clientIdEl`, `redirectEl`, `secretEl`, `scopesHost`, `issuer`, `clientId`, `redirect`, `secretValue`, `origSecretMasked`, `scopes`, `hasAnyOAuth`, `hadStoredSecret`, `oauth`) are function-scoped and disappear with the function. Note: this function references `MASKED_SENTINEL` — that's the OAuth-only usage of the constant; the kv-secrets save block elsewhere also uses `MASKED_SENTINEL` independently and stays.
- **Region 5b — Call site, line 854** (2 lines including the comment):
  ```javascript
  // OAuth section
  collectOAuthSection(container, source, config, secrets, isEdit);
  ```
  Inside the streamable-http branch of the save handler. Delete both the `// OAuth section` comment and the call line. The surrounding code (`config.url = urlValue; config.headers = {}; partitionKvRows(...)`) stays — that's the regular non-OAuth streamable-http save path.

**Region 6: Field-id arrays + chip-list state + event handler binding (lines 356-357, 368-373, 525-526)**

- Lines 356-357: a list of field IDs that includes `'oauth-issuer-url', 'oauth-client-id', 'oauth-redirect-uri', 'oauth-client-secret'`. Find the array and delete just those 4 entries (the surrounding non-OAuth field IDs stay).
- Lines 368-373: the `chips` object literal `{ args: [], 'oauth-scopes': [], 'sandbox-writable-paths': [] }` and the `if (scopesHost)` chip-state read for `oauth-scopes`. Delete the `'oauth-scopes': []` entry from the dict; delete the `if (scopesHost) chips['oauth-scopes'] = ...;` block.
- Lines 525-526: `oauthEye` and `oauthSecretInput` event-handler binding. Read the block (likely runs ~5-15 lines) and delete it. Adjacent eye/visibility-toggle bindings for non-OAuth password fields (if any) stay.

**After Region 6**: re-run all 7 frontend grep commands inside `mcp-server-editor.js` to confirm zero hits.

### Step 2: `oauth-modal.js` — delete manual-entry sub-form

Open the file; 371 LOC.

**Region 1: Top-of-file docstring (lines 5-22)**

- Lines 5-7 reference `/api/oauth/manual-register` and the manual-entry form.
- Lines 19-22 reference `App.oauthModal.openManual` and the `oauth_manual_registration_required` event.
- Lines 42-54: HTML-shape comment showing the manual-form structure.
- Edit the docstring to describe ONLY the standard flow (`open`, regular consent flow, modal close on `auth_resolved`). Remove the manual-related lines surgically.

**Region 2: `openManual` function + manual-mode branch (lines 91-104)**

- The `openManual` function delegates to `buildAndAttach(opts, /*manualMode=*/true)`. With `manualMode` going away (Region 4), `openManual` becomes meaningless.
- Delete the entire `function openManual(opts) { ... }` block.

**Region 3: `buildAndAttach` manual-form rendering (lines 123-176)**

- Inside `buildAndAttach`, the toggle button + `oauth-modal-manual-form` + 3 input fields (`client_id`, `auth_endpoint`, `token_endpoint`) + submit button HTML/JS.
- Delete the entire block.
- The non-manual portion of `buildAndAttach` (modal overlay creation, message element, consent-URL display, Cancel button) stays.

**Region 4: `manualMode` parameter + branches (6 references)**

`grep -n "manualMode\|/\*manualMode" oauth-modal.js` returns exactly 6 hits:
- Line 88: `buildAndAttach(opts, /*manualMode=*/false);` (inside `open`) — change to `buildAndAttach(opts);`
- Line 104: `buildAndAttach(opts, /*manualMode=*/true);` (inside `openManual`) — DELETED with `openManual` in Region 2
- Line 123: `function buildAndAttach(opts, manualMode) {` — change to `function buildAndAttach(opts) {`
- Line 170: `toggle.setAttribute('aria-expanded', manualMode ? 'true' : 'false');` — DELETED with the toggle button in Region 3
- Line 175: `form.hidden = !manualMode;` — DELETED with the manual form in Region 3
- Line 357: `if (manualMode) { ... }` branch — DELETE the entire `if (manualMode)` block (read 5-15 lines of context to find the closing brace; if there's an `else` branch, that becomes the unconditional path; if no `else`, the whole `if` block goes)

After Region 4 edits + Region 3 deletions, `grep -n "manualMode" oauth-modal.js` should return 0 hits.

**Region 5: Manual-register POST handler (lines 198, 255, 280-303)**

- The `submitBtn.setAttribute('data-testid', 'oauth-modal-manual-submit-btn')` at line 198 — gone with the manual form.
- Lines 255 (`// 400 with manual-register prompt → switch to manual-entry mode`) — gone.
- Lines 280-303: the `fetch('/api/oauth/manual-register', ...)` POST and its error/success handlers — gone.
- Read the surrounding `then`/`catch`/`finally` chain to confirm the deletions don't break the standard-flow promise chain. If a `.catch` was specifically catching manual-register errors, the standard flow's catch handles it.

**Region 6: Public API export (line ~368)**

- Find the `return { open: open, openManual: openManual, ... };` (or similar object literal) at the module's bottom.
- Drop the `openManual: openManual,` entry.

**After Region 6**: `grep -n "manual\|Manual\|/oauth/manual-register" oauth-modal.js` should return zero hits (or only English-language comment hits like "manually" in unrelated contexts — verify each remaining hit is benign).

### Step 3: `chat.js` — delete `oauth_manual_registration_required` WS handler

Find the WebSocket-message handler `else if` chain (around line 670 in current code). The chain's structure:

```javascript
} else if (data.type === 'auth_required') { ... }
else if (data.type === 'oauth_manual_registration_required') {
  // ... 4-6 lines of openManual dispatch ...
}
else if (data.type === 'auth_resolved') { ... }
```

Delete the entire `else if (data.type === 'oauth_manual_registration_required') { ... }` block (lines 670-676 in current code; 7 lines total). The `auth_required` and `auth_resolved` branches remain; the `else if` chain stays well-formed.

### Step 4: Browser tests — surgical deletions

`tests/browser/test_oauth_modal_flow.py`:

- Find the function `def test_manual_entry_disclosure_toggles(...)` at line ~101. Delete the entire function (decorator + def + body, ~19 lines).
- The file's module docstring (lines 1-15) may reference manual-flow scenarios — update the docstring's bullet list to remove manual-flow mentions.
- The other test functions in the file (e.g. `test_modal_closes_on_auth_resolved_event`) stay. Verify the file still imports cleanly: `python -c "import ast; ast.parse(open('tests/browser/test_oauth_modal_flow.py').read())"` exits 0.

`tests/browser/test_flow_studio_mcp_editor.py`:

- Find `def test_type_change_swaps_field_visibility(...)` (~line 211).
- Inside the function, find the 2 assertions on `[data-testid="mcp-oauth-section"]` (~lines 224, 231). Delete just those 2 lines.
- The test still verifies `mcp-stdio-only` / `mcp-streamable-http-only` swaps and the `kv-section-title` text change.

### Step 5: Run grep sweeps + tests

After all edits:

```bash
# 7 grep sweeps from Verification Steps section
# Combined sweep
# MASKED_SENTINEL preservation check
# Browser tests
docker compose exec the-one pytest tests/browser/test_oauth_modal_flow.py tests/browser/test_flow_studio_mcp_editor.py -v
# Full suite
docker compose exec the-one pytest
```

If browser tests fail, common modes:

- A `data-testid` selector still references a deleted element — the JS has the element but the test wasn't updated, or vice versa. Re-grep.
- The OAuth section HTML left a phantom `</div>` orphan — the editor's whole DOM is malformed. Open the page in a browser, inspect HTML, fix the boundary.
- A `MASKED_SENTINEL` reference in the kv-section save logic was accidentally caught by an over-broad grep and deleted — restore it; the OAuth-only `MASKED_SENTINEL` usage was inside the deleted save block, but kv-section save uses the same constant.

## Edge Cases

- **`MASKED_SENTINEL` is shared between OAuth and kv-secrets save logic**: the constant is declared once at the top of `mcp-server-editor.js` (line ~33) and used in both the deleted OAuth save block (Region 5 of Step 1) AND in the surviving kv-secrets save block (~line 878-879 in current code, possibly line-shifted post-strip). DO NOT delete the constant declaration. DO NOT delete the kv-secrets `secretsDict[key] = MASKED_SENTINEL;` usage. Verify post-edit with `grep -n "MASKED_SENTINEL" mcp-server-editor.js` showing >= 2 hits.
- **`config.oauth` is a JSON-payload key, not a JS-class-name**: the grep `grep -rn "config\.oauth" the_one/interfaces/web/` will catch the JS reads (`source.config.oauth`) AND the JS writes (`config.oauth = oauth`) AND any HTML/CSS references (none expected). All Python writes are gone post-L0 (the validator block is deleted). Post-L1 the field has zero readers and zero writers.
- **Mid-edit DOM validity in the editor**: deleting the OAuth section HTML insertion (Region 2 of Step 1) without also deleting the chips-host wiring (Region 6) leaves a `chips['oauth-scopes']` reference whose corresponding HTML never renders — `helpers.readChipListValue(scopesHost)` returns null, `chips['oauth-scopes']` stays empty, no crash but dead state. Order Region 6's chip-state cleanup BEFORE running any browser test that loads the editor.
- **`oauth-modal.js`'s standard flow MUST keep working**: the `App.oauthModal.open(opts)` API is consumed by F5's chat-path lazy-OAuth on `auth_required` events. After L1, the call site at `chat.js:~665` (the `auth_required` else-if branch) still calls `App.oauthModal.open(data)` and expects a regular consent modal. Verify that `buildAndAttach` (post-Region-4 single-arg form) renders the consent modal correctly when called from `open(opts)`. The browser test `test_modal_closes_on_auth_resolved_event` exercises this path and is the smoke test.
- **Browser test file size after edits**: `test_oauth_modal_flow.py` drops from 141 to ~120 LOC; `test_flow_studio_mcp_editor.py` drops from 510 to ~508 LOC (just 2 lines removed). Neither becomes empty.
- **Test docstrings and module-level comments**: both browser test files have module docstrings that may reference manual-entry scenarios as part of the file's documented coverage. Update the docstrings post-deletion so they describe what the file actually contains. (One-line edit each; the leg's grep sweep won't catch English-language description drift, so this is implementer discretion.)
- **`buildAndAttach`'s default-disclosure state**: pre-strip, the manual-form was hidden by default (`form.hidden = !manualMode`) and revealed only when the toggle button was clicked. Post-strip, no manual-form exists at all — there's nothing to hide or reveal. Verify the modal's standard flow renders the consent URL display + Cancel button at the same Y-position as before (no layout shift from the deleted toggle row).
- **`oauth-modal.js` line 357 `if (manualMode)` branch**: this is in the post-modal-build code (after `buildAndAttach`'s body). Read the surrounding code to determine if there's also an `else` branch — if yes, that else becomes the unconditional path; if the `if (manualMode)` was a conditional pre-fill of manual-form fields, the entire block goes.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — delete F1 OAuth-config-editor across multiple non-contiguous regions:
  - Region 1: comments at lines 9, 24
  - Region 2a: section mount at lines 120-125 (6 lines)
  - Region 2b: `renderOAuthFields` function at lines 267-309 (43 lines)
  - Region 3: render-loop skip at line 226 (1 line)
  - Region 4a: `applyTransportVisibility` mcp-oauth-section toggle at lines 692-693 (2 lines)
  - Region 4b: `staticMap` OAuth keys in `revertEditorToSource` at lines 719-722 (4 lines)
  - Region 4c: `scopesHost` chip-list re-mount in `revertEditorToSource` at lines 768-779 (12 lines)
  - Region 5a: `collectOAuthSection` function at lines 889-940 (52 lines)
  - Region 5b: call site at lines 853-854 (2 lines, including `// OAuth section` comment)
  - Region 6: field-id arrays at lines 356-357, chip-list state at lines 368-373, eye/secret-input handler at lines 525-526
  - MASKED_SENTINEL constant declaration at line ~33 + kv-secrets save logic at lines ~870-880 PRESERVED
- `the_one/interfaces/web/static/js/oauth-modal.js` — delete manual-entry surface across multiple regions:
  - Region 1: docstring lines 5-7, 19-22, 42-54
  - Region 2: `openManual` function at lines 91-104 (entire function)
  - Region 3: manual-form HTML rendering inside `buildAndAttach` at lines 123-176 (toggle, form, 3 input fields, submit button — ~54 lines)
  - Region 4: `manualMode` parameter + 6 references at lines 88, 104, 123, 170, 175, 357 (most deleted with their containing blocks; lines 88 + 123 are signature edits)
  - Region 5: manual-register POST + handlers at lines 198, 255, 280-303
  - Region 6: `openManual: openManual,` entry in public-API export object at line 368
  - `App.oauthModal.open` (standard flow) PRESERVED at lines ~83-90
- `the_one/interfaces/web/static/js/areas/chat.js:670-676` — delete `oauth_manual_registration_required` WebSocket-message handler (7 lines)
- `tests/browser/test_oauth_modal_flow.py` — DELETE `test_manual_entry_disclosure_toggles` function (~lines 101-119 in post-L0 file); update module docstring to drop manual-flow mentions
- `tests/browser/test_flow_studio_mcp_editor.py` — DELETE 2 assertion lines on `mcp-oauth-section` visibility inside `test_type_change_swaps_field_visibility` (lines 224 and 231 in post-L0 file; verify with `grep -n "mcp-oauth-section" tests/browser/test_flow_studio_mcp_editor.py`)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing inside the dev container (`docker compose exec the-one pytest`) — including browser tests for the two affected files
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress` → `### L1`
- [ ] Set this leg's status to `landed` in this file's header — NOT `completed`; the flight-level review + commit happens after L3
- [ ] Check off this leg in flight.md (`- [ ] 01-oauth-frontend-strip` → `- [x] 01-oauth-frontend-strip`)
- [ ] **DO NOT commit** — flight 6.5 uses per-flight commit cadence; the Reviewer + commit run after L3 (the last autonomous leg)

## Citation Audit

20 citation regions verified against current code on branch `flight/6_5-oauth-simplification` post-L0 at leg design time (2026-05-08), updated post-design-review (1 cycle):

- `mcp-server-editor.js:9,24,33` (header comments + MASKED_SENTINEL constant) — OK
- `mcp-server-editor.js:120-125` (Region 2a — section mount, 6 lines) — OK; verified by direct read
- `mcp-server-editor.js:124` (`html += renderOAuthFields(source);`) — OK; this is INSIDE the Region 2a block above
- `mcp-server-editor.js:226` (Region 3 — render-loop skip `if (sk === 'oauth_client_secret') continue;`) — OK
- `mcp-server-editor.js:267-309` (Region 2b — `function renderOAuthFields(source)` declaration, 43 lines) — OK; verified by direct read; only consumer is line 124 (which is also deleted)
- `mcp-server-editor.js:356-357,368-373,525-526` (Region 6 — field-id arrays + chip-list state + eye/secret-input handler) — OK; verified by direct grep
- `mcp-server-editor.js:692-693` (Region 4a — `applyTransportVisibility` mcp-oauth-section toggle, 2 lines) — OK; verified by direct read
- `mcp-server-editor.js:719-722` (Region 4b — `staticMap` OAuth keys in `revertEditorToSource`, 4 lines) — OK; verified by direct read
- `mcp-server-editor.js:768-779` (Region 4c — `scopesHost` chip-list re-mount in `revertEditorToSource`, 12 lines) — OK; verified by direct read
- `mcp-server-editor.js:853-854` (Region 5b — `collectOAuthSection` call site + `// OAuth section` comment, 2 lines) — OK; verified by direct read
- `mcp-server-editor.js:889-940` (Region 5a — `function collectOAuthSection` declaration, 52 lines) — OK; verified by direct read
- `oauth-modal.js:5-7,19-22,42-54` (docstring) — OK
- `oauth-modal.js:88,104,123,170,175,357` (`manualMode` references — 6 hits exact) — OK; verified by `grep -n "manualMode\|/\*manualMode" oauth-modal.js`
- `oauth-modal.js:91-104` (`openManual` function declaration, 14 lines) — OK
- `oauth-modal.js:123-176` (`buildAndAttach` manual-form rendering block) — OK
- `oauth-modal.js:198,255,280-303` (manual-register POST + handlers) — OK
- `oauth-modal.js:368` (`openManual: openManual,` in public-API export) — OK
- `chat.js:670-676` (`oauth_manual_registration_required` else-if branch, 7 lines) — OK
- `tests/browser/test_oauth_modal_flow.py` (`test_manual_entry_disclosure_toggles` function, ~19 lines) — OK post-L0; line numbers shifted; edit by function-name match.
- `tests/browser/test_flow_studio_mcp_editor.py` (2 `mcp-oauth-section` assertion lines inside `test_type_change_swaps_field_visibility`) — OK post-L0; lines confirmed at 224 and 231 in post-L0 file; edit by symbol/snippet match.

**Design review cycle 1 (2026-05-08)**: Reviewer flagged 3 high + 2 medium issues, all incorporated:
- HIGH: Region 2 was conflated — actually two non-contiguous targets (lines 120-125 mount + lines 267-309 `renderOAuthFields` helper). Split into Region 2a + 2b with explicit code excerpts.
- HIGH: Region 4 was misidentified as one block — actually three separate edits (4a `applyTransportVisibility` toggle, 4b `staticMap` OAuth keys in `revertEditorToSource`, 4c `scopesHost` chip-list re-mount). Each enumerated with line ranges and code excerpts.
- HIGH: Region 5 is the named function `collectOAuthSection` — leg now names it explicitly AND adds Region 5b for the call site at line 854 (which the original spec missed; would have caused `ReferenceError` post-strip).
- MEDIUM: `manualMode` reference enumeration was incomplete — missed line 175 (`form.hidden = !manualMode`). All 6 references now enumerated with disposition for each.
- MEDIUM (suggestion): no CSS dead-letter rules exist (verified by reviewer); no CSS edits needed.

Reviewer also confirmed:
- `App.oauthModal.open` consumer at `chat.js` (around the `auth_required` handler at lines 381-382 + close at 660, 666) is unaffected by L1 — only `openManual` is removed.
- `test_modal_closes_on_auth_resolved_event` survives L1 unchanged.
- `chat.js:670-676` is exactly 7 lines (verified `}` closing brace position).

**L0 anomaly carry-forward**: L0's anomaly A1 documented that the implementing agent's grep sweep authoritatively flagged dead-letter references in browser test files outside the leg's explicit scope. L1 inherits the same guidance — the grep sweep is the contract; the file list is guidance.
