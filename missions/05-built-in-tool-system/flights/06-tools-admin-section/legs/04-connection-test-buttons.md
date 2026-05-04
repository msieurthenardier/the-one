# Leg: 04-connection-test-buttons

**Status**: landed
**Flight**: [Tools Admin Section](../flight.md)

## Objective

Add a connection-test surface to the per-tool editor — a "Test connection" button + result panel — for `web_search` and `fetch_url` ONLY (per F6 Decision 5). Click POSTs to L1's `/api/tools/configs/{name}/test` endpoint (no body needed; backend uses fixture inputs); spinner during request; renders the response into a `<pre>` panel beneath the button (truncated tail-style at 2 KB if longer). Disables the button while in-flight to block double-fires; surfaces both 200 success (with `output` and `elapsed_ms`) and any error path into the same panel. Save/Cancel/dirty-tracking are unaffected — the test endpoint never modifies operator state. ~80 LoC inside `tools-editor.js`; the L3 scaffold already left a placeholder comment for the test section's mount point.

## Context

- **F6 mission goal — operator can verify constraints actually work**: an operator who narrows `host_allowlist` to `["docs.python.org"]` and saves wants immediate feedback that `fetch_url(https://example.com/)` now refuses. The test button surfaces the agent's view of that refusal (`[error] [constraint] host 'example.com' not in host_allowlist [...]`) directly in the editor — no need to switch to a chat session and prompt the agent.
- **F6 Decision 5** (test endpoint scope + semantics): only `web_search` and `fetch_url` are testable. Test runs against the operator's currently-saved Config (the L1 endpoint re-keys the Config dispatch so the named tool's saved row reaches `cross_configs[WebConfig]` regardless of `_TOOL_CLASSES` declaration order). Failed test = config-validity diagnostic — the panel renders the exact `[error] [constraint] ...` string the agent would see, so operators learn the agent's UX directly.
- **F6 Decision 6** (test result inline panel): result panel is a `<pre>` beneath the button (preserves whitespace + monospace for the `[error]` prefix; matches the agent's chat surface). Truncated at ~2 KB tail-style (matches the tool-output truncation pattern from F4 — operators see the most recent bytes when output overruns). Two-phase UI: button click → spinner-pending → result panel populated; button disabled in-flight (per-test idempotency).
- **F6 Decision 11** (endpoint shape): L1 ships `POST /api/tools/configs/{name}/test`. Returns `{output: str, elapsed_ms: float}` on tool-side success AND tool-side failure (constraint refusals come through as `[error] [constraint] ...` in `output`, NOT 5xx). Returns 400 on non-testable tool name (rejected by L4's button mounting), 404 on unknown tool name (cannot happen from L4 — names come from `_TOOL_CLASSES` cache), 5xx only on hard backend exceptions (L4 surfaces the HTTP status text into the same `<pre>`).
- **F6 Decision 12** (two-Reviewer-pass batching): L4 commits no docs. The "Test connection" UX gets documented at L9.
- **L3 mount-point** (per-Reviewer high — the placeholder comment was NOT actually written in L3 despite the L3 flight-log claim): the Configuration `.editor-section` ends at `tools-editor.js:108` (`html += '</div>';`) immediately before `container.innerHTML = html;` on line 110. L4 inserts the new test section emission AFTER that closing `</div>` but BEFORE `container.innerHTML = html;`. The boundary itself is the mount point — no comment to grep for.
- **provider-editor's test pattern is the canonical reference**: `provider-editor.js:316-347` ships the precedent — `.test-provider-btn` triggers a fetch, swaps the result panel through `.test-result-pending` → `.test-result-ok` / `.test-result-fail` span states. L4 follows the same shape with `.test-tool-btn` (avoiding name collision) and renders the response into a `<pre class="tool-test-output">` child INSIDE `.test-result` (the existing CSS sites `.test-result` as the announcement region; `<pre>` is the formatted-output container).
- **Existing CSS primitives** at `static/css/components.css`: `.test-result` (the result region with `aria-live="polite"`), `.test-result-pending` / `.test-result-ok` / `.test-result-fail` (status spans). L4 adds one new selector — `.tool-test-output` — for the `<pre>` formatting (monospace + max-height + scroll). All other styling reused unchanged.
- **Truncation 2 KB**: The L1 endpoint does not pre-truncate (it returns the full tool output). L4 truncates client-side: if `output.length > 2048`, render `… [truncated; showing last 2 KB]\n` + `output.slice(-2048)`. Matches the tool-output truncation contract operators already see when chatting with the agent.

## Inputs

- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` (post-L3, **491 lines** — the L3 module ended up larger than the design's 400-450 estimate). L4 widens the scaffold builder around line 108 (between Configuration section's `</div>` and `container.innerHTML = html;`) and the existing `wireEvents` function (line 271; `toolDetail` and `container` are both in lexical scope) to add the click-handler block adjacent to the existing Save handler.
- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js:316-347` — canonical test-button pattern.
- `the_one/interfaces/web/static/css/components.css` — `.test-result`, `.test-result-pending`, `.test-result-ok`, `.test-result-fail` selectors.
- `the_one/interfaces/web/static/css/admin.css` — appendable for the new `.tool-test-output` `<pre>` styling.
- `the_one/interfaces/web/api.py` (post-L1) — `POST /api/tools/configs/{name}/test` endpoint shape: 200 → `{output: str, elapsed_ms: float}`; 400 → `{detail: "Tool {name} does not support connection testing"}`; 404 → `{detail: "Tool not found: {name}"}`; 5xx → `{detail: "..."}`.
- `tests/test_db_api.py:16-35` — canonical client fixture (already used by L2/L3 asset tests).

## Outputs

- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js`:
  - **Constant** `_TESTABLE_TOOLS = ['web_search', 'fetch_url']` near the top of the IIFE (mirrors L1 backend's `_TESTABLE_TOOLS = frozenset({"web_search", "fetch_url"})` — duplicated client-side so the button mounts conditionally without a backend round-trip).
  - **Render block** added to the editor scaffold AFTER the `Configuration` `.editor-section` (replacing the L3 placeholder comment):
    ```html
    {if toolDetail.name in _TESTABLE_TOOLS:}
    <div class="editor-section tools-editor-test-section">
      <div class="section-title">Test connection</div>
      <p class="field-description tools-editor-test-help">
        Runs <code>{toolDetail.name}</code> against a fixed input using your currently-saved
        configuration. Use this to verify a narrow / denylist actually refuses, or to confirm
        that a network change still works.
      </p>
      <div class="form-actions tools-editor-test-actions">
        <button type="button" class="btn-outlined-cyan test-tool-btn" data-testid="test-tool-btn">
          {App.icon('play')} Test connection
        </button>
        <span class="test-result" aria-live="polite"></span>
      </div>
      <pre class="tool-test-output" hidden></pre>
    </div>
    {endif}
    ```
    - Fixture-input description text varies per tool; the help text uses the generic phrasing above so a future fold-in of more testable tools doesn't need to update copy. (The L1 endpoint owns the fixture mapping; L4 doesn't need to surface the literal fixture URL/query in the help text.)
    - The button uses `App.icon('play')` for visual parity with provider-editor's Test button styling.
  - **Wiring** added to the editor's existing `wireEvents` / IIFE init block:
    ```javascript
    // Mount the test button only for testable tools.
    var testBtn = container.querySelector('.test-tool-btn');
    if (testBtn) {
      var resultEl = container.querySelector('.test-result');
      var outputEl = container.querySelector('.tool-test-output');
      testBtn.addEventListener('click', function () {
        // In-flight: clear prior output, show spinner, disable button.
        resultEl.innerHTML = '<span class="test-result-pending">Testing…</span>';
        outputEl.hidden = true;
        outputEl.textContent = '';
        testBtn.disabled = true;

        fetch('/api/tools/configs/' + encodeURIComponent(toolDetail.name) + '/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}'
        })
          .then(function (r) {
            return r.json().then(function (body) {
              return { ok: r.ok, status: r.status, body: body };
            });
          })
          .then(function (resp) {
            testBtn.disabled = false;
            if (resp.ok) {
              renderTestSuccess(resp.body, resultEl, outputEl);
            } else {
              renderTestError(resp.status, resp.body, resultEl, outputEl);
            }
          })
          .catch(function (err) {
            testBtn.disabled = false;
            resultEl.innerHTML = '<span class="test-result-fail">✗ Request failed</span>';
            outputEl.hidden = false;
            outputEl.textContent = String(err && err.message ? err.message : err);
          });
      });
    }

    function renderTestSuccess(body, resultEl, outputEl) {
      // 200 → {output: str, elapsed_ms: float}. The "success" classification
      // means the HTTP request succeeded; the tool's OUTPUT may itself be
      // an [error] [constraint] ... refusal — that's still a successful test
      // (the operator learns their config blocked it).
      var ms = (body.elapsed_ms != null) ? body.elapsed_ms.toFixed(0) : '?';
      var output = String(body.output || '');
      var isToolRefusal = output.indexOf('[error]') === 0;
      var statusClass = isToolRefusal ? 'test-result-fail' : 'test-result-ok';
      var icon = isToolRefusal ? '✗ Refused' : '✓ Returned';
      resultEl.innerHTML =
        '<span class="' + statusClass + '">' + icon +
        ' (' + window.App.escapeHtml(ms) + ' ms)</span>';
      // Truncate to last 2 KB tail-style.
      var rendered = output.length > 2048
        ? '… [truncated; showing last 2 KB]\n' + output.slice(-2048)
        : output;
      outputEl.hidden = false;
      outputEl.textContent = rendered;  // textContent preserves the [error] prefix as-is
    }

    function renderTestError(status, body, resultEl, outputEl) {
      // 400 / 404 / 5xx etc. — body.detail is FastAPI HTTPException convention.
      var msg = (body && body.detail) ? String(body.detail) : 'HTTP ' + status;
      resultEl.innerHTML =
        '<span class="test-result-fail">✗ ' + window.App.escapeHtml(msg) + '</span>';
      outputEl.hidden = true;
      outputEl.textContent = '';
    }
    ```
  - **Cancel re-mount preserves test-result clear**: per L3's option-A Cancel approach (re-mount with original `toolDetail`), the new test-section + result panel start fresh on every Cancel. Operator's prior test output is cleared — matches the operator's "this is a fresh edit session" mental model. No special handling needed; the re-mount naturally clears.
  - **Save does not trigger a test**: the test button is independent. After Save, the editor's `originalToolDetail` ref is updated by the orchestrator's `onSaveSuccess` callback (L3); the test button remains mounted and continues to use the latest saved Config (since the test endpoint reads from the DB, not from the editor's in-memory state).

- `the_one/interfaces/web/static/css/admin.css` (append):
  - `.area-admin .tools-editor-test-section { /* visual separation from Configuration section — provided by .editor-section margin */ }` (likely no extra rules needed; documented for clarity).
  - `.area-admin .tools-editor-test-actions { display: flex; gap: 8px; align-items: center; }` (button + result-status side-by-side; mirrors `.form-actions` rhythm).
  - `.area-admin .tools-editor-test-help { margin-bottom: 8px; }` (small breathing room above the actions row).
  - `.area-admin .tool-test-output { display: block; max-height: 320px; overflow-y: auto; padding: 8px 10px; margin-top: 8px; background: var(--surface-elevated); border: 1px solid var(--border-strong); border-radius: 4px; font-family: var(--font-family-mono); font-size: var(--font-size-small); white-space: pre-wrap; word-break: break-word; }` — `<pre>` styling that fits long tool output without overflowing the editor.
  - `.area-admin .tool-test-output[hidden] { display: none; }` (explicit; the `hidden` attribute is canonical-but-some-CSS-resets-can-clobber).

- `tests/test_tools_test_button_assets.py` (new, 1 test — light asset/wire-up check; full UX flow is L7 Playwright):
  - `test_tools_editor_js_exposes_test_button_wiring` — assert `GET /static/js/areas/admin/tools-editor.js` body contains `_TESTABLE_TOOLS` AND `test-tool-btn` AND `/api/tools/configs/` AND a `/test'` substring (per-Reviewer low: anchor on `/test'` to ensure the trailing path segment is present, not just the literal string `/test` somewhere in a comment). Mirrors L2/L3 asset-test fixture exactly.
  - **No second test** for the inline render — `tools-editor.js` is JS-only; behavior coverage is L7 Playwright (operator clicks button → POST returns mocked output → `<pre>` populates).

## Acceptance Criteria

- [x] `tools-editor.js` defines `_TESTABLE_TOOLS = ['web_search', 'fetch_url']` constant near the top.
- [x] Test section `<div class="editor-section tools-editor-test-section">` is rendered ONLY when `toolDetail.name` is in `_TESTABLE_TOOLS`. For all 17 other tools, the section does not appear in the DOM at all.
- [x] Section title is "Test connection"; help text is generic (no per-tool fixture description).
- [x] Button DOM matches `<button type="button" class="btn-outlined-cyan test-tool-btn" data-testid="test-tool-btn">{play icon} Test connection</button>`.
- [x] Click handler clears prior output, sets `<span class="test-result-pending">Testing…</span>` in the result region, hides the `<pre>`, disables the button, then POSTs `{}` to `/api/tools/configs/{name}/test`.
- [x] **200 path**: button re-enables; result region shows `✓ Returned (Nms)` (`test-result-ok`) IF `output` does NOT start with `[error]`, OR `✗ Refused (Nms)` (`test-result-fail`) IF it does. The `<pre>` shows the full output (truncated tail-style at 2 KB if longer; truncation prefix is `"… [truncated; showing last 2 KB]\n"`).
- [x] **Non-200 path** (400/404/5xx): button re-enables; result region shows `✗ {body.detail || 'HTTP {status}'}`; `<pre>` is hidden.
- [x] **Network error path** (catch): button re-enables; result region shows `✗ Request failed`; `<pre>` shows the error message (helps with `fetch failed` diagnostics).
- [x] Button is disabled while a request is in-flight; second click during that window is a no-op.
- [x] `<pre>` uses `textContent` (NOT `innerHTML`) to set the output — preserves the literal `[error] [constraint] ...` prefix and prevents any HTML interpretation of tool output.
- [x] Save/Cancel/dirty-tracking is **unaffected** — clicking Test does NOT enable Save/Cancel; the form's snapshot is untouched.
- [x] Cancel re-mount clears the test result + `<pre>` (natural side-effect of re-mounting; no explicit code needed).
- [x] CSS additions: `.tools-editor-test-section`, `.tools-editor-test-actions`, `.tools-editor-test-help`, `.tool-test-output` (with `[hidden]` rule). All token references resolve. (Deviation: spec listed `--font-size-small`; that token is not defined in the project — used `--font-size-body-sm` (12 px) which is the closest existing token. See flight-log Deviations.)
- [x] `tests/test_tools_test_button_assets.py` ships with 1 test; passes.
- [x] Existing `tests/test_tools_admin_editor_assets.py` (L3) still passes (the script tag was already added by L3; L4 only edits the file's body).
- [x] `make test-unit` is green (modulo CSS-token deselect). (Verified via `pytest tests/ -m 'not browser and not live and not pixel' -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined` → 1040 passed, 1 skipped.)
- [x] `make rebuild` succeeds; `make verify-serving` shows `tools-editor.js` as 200 (was added in L3; L4 only modifies content).
- [x] No L0/L1/L2/L3 file is touched besides the documented edits to `tools-editor.js` and `admin.css`.
- [x] No L5 (Studio) surface is created.
- [x] No new HTML script tag is added (L3 already shipped the `tools-editor.js` `<script>`).

## Verification Steps

```bash
# 1. Module shape — TESTABLE_TOOLS constant present, fetch URL correctly wired
docker exec the-one grep -c "_TESTABLE_TOOLS" the_one/interfaces/web/static/js/areas/admin/tools-editor.js  # 1+
docker exec the-one grep -c "test-tool-btn" the_one/interfaces/web/static/js/areas/admin/tools-editor.js  # 2+ (selector + click target)
docker exec the-one grep -c "/api/tools/configs/" the_one/interfaces/web/static/js/areas/admin/tools-editor.js  # 1+ (the test fetch)
docker exec the-one grep -c "tool-test-output" the_one/interfaces/web/static/js/areas/admin/tools-editor.js  # 1+

# 2. CSS additions
docker exec the-one grep -c "tool-test-output\|tools-editor-test-section\|tools-editor-test-actions" the_one/interfaces/web/static/css/admin.css  # 3+

# 3. Targeted test
docker exec the-one pytest tests/test_tools_test_button_assets.py -x -q

# 4. Regression — L0/L1/L2/L3 untouched
docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py tests/test_factory.py tests/test_factory_disable_enforcement.py tests/test_api_tool_configs.py tests/test_enrich_schema_with_markers.py tests/test_tools_admin_grid_assets.py tests/test_tools_admin_editor_assets.py -x -q

# 5. Full unit suite
docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# 6. Static asset wiring (no new file — L4 only modifies tools-editor.js content)
make rebuild
make verify-serving  # all 7 assets including tools-editor.js → 200

# 7. Manual smoke (browser):
#    a. Open http://localhost:8484/#admin/tools/web_search → editor opens; Test connection section visible at bottom.
#    b. Click "Test connection" → spinner → result panel shows DDG results in <pre> (or [error] [constraint] ... if SSRF blocks).
#    c. Open http://localhost:8484/#admin/tools/fetch_url → similar; output is markdown of https://example.com/.
#    d. Open http://localhost:8484/#admin/tools/shell → editor opens; NO test section visible.
#    e. Disable web_search via the grid toggle → re-open editor → Test connection still WORKS (test endpoint runs against current saved config; disable is enforced at agent factory, not the test endpoint).
#    f. Set web_search's `host_denylist` to include `duckduckgo.com` → save → Test → result shows constraint refusal IN <pre> (the operator-resolved-config behavior from L1 Decision 5; note that DDG backend doesn't actually use SSRF transport — the operator may see results anyway; document this if surfaced as a HAT issue).
#    g. Trigger 5xx (e.g., temporarily monkeypatch the endpoint to raise) → result region shows error message; button re-enables.

# 8. Lint
docker exec the-one ruff check tests/test_tools_test_button_assets.py
```

## Implementation Guidance

1. **Locate the mount point** in `the_one/interfaces/web/static/js/areas/admin/tools-editor.js`: find the line `html += '</div>';` that closes the Configuration `<div class="editor-section">` (around line 108), immediately before `container.innerHTML = html;` (line 110). The HTML emission for the test section is inserted between those two lines. (Per-Reviewer high: the L3 flight-log claimed an inline comment was left here as a placeholder; verification shows no such comment exists. Use the section boundary itself as the mount.)

2. **Add the `_TESTABLE_TOOLS` constant** at the top of the IIFE, alongside any other module-private constants:

   ```javascript
   var _TESTABLE_TOOLS = ['web_search', 'fetch_url'];
   ```

3. **Conditional render** in the editor scaffold builder (the function that emits the editor's `innerHTML`):

   ```javascript
   if (_TESTABLE_TOOLS.indexOf(toolDetail.name) !== -1) {
     html += '<div class="editor-section tools-editor-test-section">';
     html += '<div class="section-title">Test connection</div>';
     html += '<p class="field-description tools-editor-test-help">';
     html += 'Runs <code>' + escapeHtml(toolDetail.name) + '</code> against a fixed input using your currently-saved configuration. ';
     html += 'Use this to verify a narrow / denylist actually refuses, or to confirm that a network change still works.';
     html += '</p>';
     html += '<div class="form-actions tools-editor-test-actions">';
     html += '<button type="button" class="btn-outlined-cyan test-tool-btn" data-testid="test-tool-btn">';
     html += window.App.icon('play') + ' Test connection';
     html += '</button>';
     html += '<span class="test-result" aria-live="polite"></span>';
     html += '</div>';
     html += '<pre class="tool-test-output" hidden></pre>';
     html += '</div>';
   }
   ```

4. **Wire the click handler** INSIDE the existing `wireEvents` function (line 271 of tools-editor.js — `toolDetail` and `container` are both already in lexical scope). Add the block at the bottom of `wireEvents`, adjacent to the existing Save-handler block. The `renderTestSuccess` / `renderTestError` helpers are added at IIFE-level (NOT inside the `if` block — per-Reviewer medium: matches the pattern of other top-level helpers like `wireChipListEditor`, `chipExists`, `clearFieldErrors`):

   At IIFE-level (after the existing top-level helpers, before `window.App.admin.renderToolsEditor = renderToolsEditor;`):

   ```javascript
   function renderTestSuccess(body, resultEl, outputEl) {
     // 200 → {output: str, elapsed_ms: float}. The "success" classification
     // means the HTTP request succeeded; the tool's OUTPUT may itself be
     // an [error] [constraint] ... refusal — that's still a successful test
     // (the operator learns their config blocked it).
     var ms = (body.elapsed_ms != null) ? body.elapsed_ms.toFixed(0) : '?';
     var output = String(body.output || '');
     var isToolRefusal = output.indexOf('[error]') === 0;
     var statusClass = isToolRefusal ? 'test-result-fail' : 'test-result-ok';
     var icon = isToolRefusal ? '✗ Refused' : '✓ Returned';
     resultEl.innerHTML =
       '<span class="' + statusClass + '">' + icon +
       ' (' + ms + ' ms)</span>';
     var rendered = output.length > 2048
       ? '… [truncated; showing last 2 KB]\n' + output.slice(-2048)
       : output;
     outputEl.hidden = false;
     outputEl.textContent = rendered;  // textContent preserves [error] prefix
   }

   function renderTestError(status, body, resultEl, outputEl) {
     var msg = (body && body.detail) ? String(body.detail) : 'HTTP ' + status;
     resultEl.innerHTML =
       '<span class="test-result-fail">✗ ' + window.App.escapeHtml(msg) + '</span>';
     outputEl.hidden = true;
     outputEl.textContent = '';
   }
   ```

   At the bottom of `wireEvents`:

   ```javascript
   var testBtn = container.querySelector('.test-tool-btn');
   if (testBtn) {
     var resultEl = container.querySelector('.test-result');
     var outputEl = container.querySelector('.tool-test-output');
     testBtn.addEventListener('click', function () {
       resultEl.innerHTML = '<span class="test-result-pending">Testing…</span>';
       outputEl.hidden = true;
       outputEl.textContent = '';
       testBtn.disabled = true;

       fetch('/api/tools/configs/' + encodeURIComponent(toolDetail.name) + '/test', {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: '{}'
       })
         .then(function (r) {
           return r.json().then(function (body) { return { ok: r.ok, status: r.status, body: body }; });
         })
         .then(function (resp) {
           testBtn.disabled = false;
           if (resp.ok) renderTestSuccess(resp.body, resultEl, outputEl);
           else renderTestError(resp.status, resp.body, resultEl, outputEl);
         })
         .catch(function (err) {
           testBtn.disabled = false;
           resultEl.innerHTML = '<span class="test-result-fail">✗ Request failed</span>';
           outputEl.hidden = false;
           outputEl.textContent = String(err && err.message ? err.message : err);
         });
     });
   }
   ```

   - `ms` is no longer escaped via `escapeHtml` (numeric strings have no HTML-special chars; per-Reviewer low).
   - The `hidden` attribute is the source of truth for `<pre>` visibility; the CSS `[hidden] { display: none }` rule is documentation/defensive — modern browsers ship the rule in their UA stylesheet, but the project's CSS resets are not specifically grepped for clobbering, so the explicit rule stays as cheap insurance.

5. **Append CSS** to `the_one/interfaces/web/static/css/admin.css`:

   ```css
   .area-admin .tools-editor-test-section { /* uses default .editor-section margin */ }
   .area-admin .tools-editor-test-actions {
     display: flex;
     gap: 8px;
     align-items: center;
   }
   .area-admin .tools-editor-test-help { margin-bottom: 8px; }
   .area-admin .tool-test-output {
     display: block;
     max-height: 320px;
     overflow-y: auto;
     padding: 8px 10px;
     margin-top: 8px;
     background: var(--surface-elevated);
     border: 1px solid var(--border-strong);
     border-radius: 4px;
     font-family: var(--font-family-mono);
     font-size: var(--font-size-small);
     white-space: pre-wrap;
     word-break: break-word;
   }
   .area-admin .tool-test-output[hidden] { display: none; }
   ```

6. **Asset test** — `tests/test_tools_test_button_assets.py`:

   ```python
   """Asset wiring for the F6 L4 test buttons."""
   from __future__ import annotations
   from pathlib import Path
   from unittest.mock import patch
   import aiosqlite
   import pytest
   from fastapi import FastAPI
   from fastapi.staticfiles import StaticFiles
   from httpx import ASGITransport, AsyncClient
   from the_one.db.schema import ensure_schema
   from the_one.interfaces.web.api import router
   import the_one.interfaces.web.app as web_app
   _STATIC_DIR = Path(web_app.__file__).parent / "static"


   @pytest.fixture
   async def client(tmp_path):
       db_path = tmp_path / "test.db"
       conn = await aiosqlite.connect(str(db_path))
       conn.row_factory = aiosqlite.Row
       await conn.execute("PRAGMA foreign_keys=ON")
       await ensure_schema(conn)
       with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
           test_app = FastAPI()
           test_app.include_router(router)
           test_app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
           transport = ASGITransport(app=test_app)
           async with AsyncClient(transport=transport, base_url="http://test") as c:
               yield c
       await conn.close()


   class TestToolsTestButtonAssets:
       async def test_tools_editor_js_exposes_test_button_wiring(self, client: AsyncClient) -> None:
           resp = await client.get("/static/js/areas/admin/tools-editor.js")
           assert resp.status_code == 200
           body = resp.text
           assert "_TESTABLE_TOOLS" in body
           assert "test-tool-btn" in body
           assert "/api/tools/configs/" in body
           # Anchor on the trailing /test' so a comment mentioning /test elsewhere
           # cannot satisfy this assertion.
           assert "/test'" in body or "'/test" in body
           assert "tool-test-output" in body
   ```

7. **Run the verification block** above; paste relevant pytest summaries + manual smoke notes into the L4 flight-log entry.

## Edge Cases

- **Non-testable tool (e.g., `shell`, `read_file`)**: the `_TESTABLE_TOOLS.indexOf(...)` guard skips the entire `<div class="editor-section tools-editor-test-section">` emission. No button to find, no handler to wire. Operator never sees the section. (The L1 backend would 400 on a manual POST to `/api/tools/configs/shell/test`, but L4 never gives the operator a button to trigger that.)
- **Tool refusal vs request success**: L1 returns 200 even when the tool refuses with `[error] [constraint] ...`. L4's `renderTestSuccess` distinguishes by checking `output.indexOf('[error]') === 0`. The result region's status flips to `test-result-fail` (red) for a constraint refusal, but the `<pre>` panel still renders the refusal text — that's the operator-meaningful diagnostic per Decision 5.
- **Long output (>2 KB)**: tail-truncation matches the tool-output pattern operators see in chat. Prefix line `"… [truncated; showing last 2 KB]\n"` makes the truncation explicit. `output.slice(-2048)` is character-based; multi-byte chars at the boundary may render mid-codepoint — acceptable (the truncation banner explains the cutoff). The 2 KB ceiling matches the F4 chat-output truncation contract.
- **Empty output (`output === ""`)**: `renderTestSuccess` runs `output.indexOf('[error]')` → -1 (not 0), classifies as success, shows `✓ Returned (Nms)` and an empty `<pre>`. Acceptable — the operator sees the timing and can tell the tool ran but returned nothing meaningful.
- **`elapsed_ms` missing or null**: render `?` instead of the number. Defensive against any future endpoint variant that omits the field.
- **5xx during test (unhandled tool exception)**: `body.detail` will carry the FastAPI exception message; surfaced verbatim. The `<pre>` stays hidden because there's no tool output to show — only the error string in the `.test-result` region.
- **Network error (offline / DNS fail / fetch reject)**: caught by `.catch`; result region shows `✗ Request failed`; `<pre>` shows the error message. Operator sees both the high-level failure (status region) and the diagnostic (`<pre>`).
- **Double-click race**: button is disabled the moment the request fires; the disabled attribute is reset only when the response (success OR error path) lands. Operator can't double-fire a test even if they hammer the button.
- **Save in-flight while Test in-flight**: the two are independent fetches; both can run concurrently. Save touches the DB; Test reads from the DB. If a Save lands during a Test request that already started, the Test will use the pre-Save config (it captured at request time). Acceptable race — operator can re-Test after Save lands to verify the new config.
- **Test after disabling the tool via the grid toggle**: works fine. The disable filter at L1's factory excludes disabled tools from the AGENT REGISTRY, but the test endpoint instantiates the tool directly (bypassing the factory). An operator can disable a tool, test it (to verify a constraint), then keep it disabled. This is intentional — the test endpoint is an admin-only diagnostic surface.
- **Cancel during in-flight Test**: the L3 Cancel re-mounts the editor, which destroys the entire `<div class="editor-section">` containing the button. The pending fetch's `.then` still runs (no abort signal), but its handler reads from closure-captured `resultEl` / `outputEl` Element refs — these are now-detached Elements, NOT null. Setting `.innerHTML` / `.textContent` / `.hidden` on detached Elements is silent (DOM ops on detached nodes do not throw). No crash, no stale UI mutation in the new editor instance. **Acceptable**; documented as a benign no-op. (Future hardening: an `AbortController` could cancel the fetch on Cancel; deferred — not worth the complexity for an operator-explicit test surface.)
- **Reload page during in-flight Test**: page tear-down kills the fetch. No state to recover. Operator re-clicks Test on the fresh page.

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` — `_TESTABLE_TOOLS` constant; conditional test-section rendering replacing the L3 placeholder comment; click handler + `renderTestSuccess` + `renderTestError` inner helpers.
- `the_one/interfaces/web/static/css/admin.css` — `.tools-editor-test-section`, `.tools-editor-test-actions`, `.tools-editor-test-help`, `.tool-test-output` (+ `[hidden]` rule).
- `tests/test_tools_test_button_assets.py` — new (1 test).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `make test-unit` green (modulo CSS-token deselect)
- [ ] `make rebuild` succeeds; `make verify-serving` confirms tools-editor.js still served
- [ ] Live smoke (manual): web_search test → DDG result panel; fetch_url test → markdown panel; shell editor → no test section; disable + test → still works; truncation → 2 KB tail with banner
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
