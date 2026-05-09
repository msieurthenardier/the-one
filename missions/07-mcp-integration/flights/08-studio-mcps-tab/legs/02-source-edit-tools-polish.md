# Leg: 02-source-edit-tools-polish

**Status**: completed
**Flight**: [Studio MCPs tab + inspector polish](../flight.md)

## Objective

Two small UI additions to the Studio MCP source-edit page's Tools section, both consuming L1's `/test/connect` capabilities response: (a) render a one-line "Server supports: tools, resources, …" capability-flags status above the tool list after a successful Test connection; (b) inside each tool's existing `<details>` panel, add a nested `<details>Input schema</details>` containing a pretty-printed `<pre>` JSON dump of `tool.input_schema`. UI-only on top of L1; no API changes; no backend work.

## Context

- **L1 already extended `/test/connect`** to include a `capabilities` field in the Phase A success response (verified at `the_one/interfaces/web/api.py:887` post-L1 — `"capabilities": capabilities`). The shape is `MCPClient.server_capabilities`'s output: a JSON-serialized dict with keys `tools`, `resources`, `prompts`, `logging`, `completions`, `experimental` (per the MCP spec; some keys may be `None` if the server didn't announce that capability).
- **The render site is `mcp-server-editor.js::handleTestConnection`** at `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:822-914`. The `data.status === 'ok'` branch (lines 842-871) already renders status text + a `<details>`-per-tool list. L2 extends this branch with:
  - Capability flags rendered into `statusEl.innerHTML` (or a new dedicated element).
  - Per-tool nested `<details>Input schema</details>` injected inside the existing tool `<details>` panel between the description and the closing tag.
- **Allowlist for capability rendering**: per Design Decision §5, render only typed-presence-flag capability keys from the installed `mcp` SDK's `ServerCapabilities` model. The SDK ships these typed flags: `tools`, `resources`, `prompts`, `logging`, `completions`, `tasks`. The seventh field, `experimental`, is excluded — it's a free-form sub-namespace dict (per-server custom keys), NOT a typed presence flag, so rendering "experimental" as a chip would mislead the operator. Unknown keys (a future spec revision adding new typed flags) are ignored at L2's render layer; the allowlist must be updated when targeting a newer SDK revision. This keeps L2's UI from misrendering unexpected nested objects from the server.
- **Truthy semantic for capability flags**: `MCPClient.server_capabilities` returns `result.capabilities.model_dump(mode="json")` which yields `None` for un-announced capabilities and a (possibly empty) dict `{}` for announced ones (e.g. `{"tools": {}, "resources": None}` for a server that announces tools but not resources). The capability is "present" if its value is NOT `None`. Empty-dict (`{}`) MEANS "the server announces this capability with no sub-flags set" — which is still presence per the MCP spec. The render predicate is: `caps[key] !== null && caps[key] !== undefined`.
- **Schema render via `<pre>`**: each tool already has an outer `<details class="mcp-tool-item">` with summary + description. L2 adds a nested `<details>` inside, with summary "Input schema" and a `<pre>` body showing `JSON.stringify(t.input_schema, null, 2)`. The nested details defaults to closed (operator opens when curious). For tools without `input_schema` (or with `input_schema === null`), don't render the nested details at all — the closed-by-default UI already absorbs the absence cleanly.
- **CSS lives in `the_one/interfaces/web/static/css/studio.css:96-109`** — existing `.area-studio .mcp-tool-*` rules. L2 adds rules for the new capability-flags status and the nested schema view (`<pre>` background, monospace font, scroll for long schemas).
- **Browser tests**: existing tests in `tests/browser/test_mcp_test_connection_button.py` hit real URLs and don't mock the API. L2's verification needs a stub success response. **Pattern**: introduce `page.route()` (Playwright's request-interception API — first use in this codebase). Browser tests for L2 mock the `/api/mcp-sources/{id}/test/connect` endpoint with a synthetic `{status: "ok", tools: [...], capabilities: {...}}` payload, then assert the rendered DOM. This becomes a referenceable pattern for L3's MCPs-tab tests too.

## Inputs

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:822-914` — `handleTestConnection` function. The `data.status === 'ok'` branch needs the two render additions.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:131-138` — Tools section scaffold (status div + tools list div). The capability-flags status may render into `statusEl` or a new dedicated element; implementer chooses based on visual coherence (see Implementation Guidance).
- `the_one/interfaces/web/static/css/studio.css:96-109` — existing `mcp-tool-*` CSS rules.
- `tests/browser/test_mcp_test_connection_button.py` — existing browser tests for the Test connection button. New L2 tests live alongside or in a new sibling file.
- `the_one/interfaces/web/api.py::test_mcp_connection` (post-L1) — returns `capabilities` in the success payload. No backend changes in L2.

## Outputs

- `mcp-server-editor.js::handleTestConnection` `data.status === 'ok'` branch renders capability flags as a one-line status above (or alongside) the existing "Server exposes N tools" text.
- Each rendered tool `<details>` panel contains a nested collapsible `<details>Input schema</details>` with a `<pre>`-wrapped JSON dump (when `t.input_schema` is non-null and non-empty).
- New CSS for the capability-flags status and the nested schema view.
- New browser test file (or appended tests) exercising: capability flags render correctly for a server announcing `{tools: {}, resources: {}}` (renders "Server supports: tools, resources"); collapsible schema view opens/closes; schema content is the exact JSON the API returned; tools without `input_schema` don't get a schema view; capability-flags status is empty/hidden when no capabilities announced (server responds with all-null capabilities — pathological but documented).
- `flight-log.md` updated with L2 entry; leg status flipped to `landed`.

## Acceptance Criteria

- [ ] **L2.1** — On Test-connection success with a `capabilities` field present, the Tools section renders a one-line "Server supports: …" status listing the capabilities whose value is not `null`/`undefined`. The list is comma-separated, alphabetically ordered (or in a fixed canonical order — implementer chooses), and uses these labels: `tools`, `resources`, `prompts`, `logging`, `completions`, `tasks`. Unknown keys in the response (including `experimental`) are skipped silently.
- [ ] **L2.2** — When the server announces NO capabilities (all spec-defined keys `null` in the response), the capability-flags status is hidden or shows an explicit "Server announced no capabilities" message. The implementer chooses; a hidden status is fine if the empty state isn't useful operator information. Document the choice in the L2.1 verification step.
- [ ] **L2.3** — Each rendered tool `<details>` panel contains a nested `<details>` with summary "Input schema" and a `<pre>`-wrapped pretty-printed JSON dump (`JSON.stringify(t.input_schema, null, 2)`). The nested element defaults to closed. The schema view uses monospace font (`var(--font-family-mono, monospace)`) and respects the existing `mcp-tool-item` styling.
- [ ] **L2.4** — Tools where `t.input_schema` is `null`, `undefined`, or `{}` (an empty object) do NOT render the nested schema details — the existing description and title surface are unchanged for those tools. (Empty-dict treated same as null because the operator gains nothing from `{}` rendered as JSON.)
- [ ] **L2.5** — At least 2 browser tests in `tests/browser/test_mcp_test_connection_button.py` (or a new sibling file `tests/browser/test_mcp_source_edit_tools_polish.py` — implementer chooses based on cohesion):
  - **Test A**: capability flags render correctly for a stub `/test/connect` response with `capabilities: {tools: {}, resources: {}}` and 1 tool — assertions verify the flags one-liner contains "tools" and "resources" and NOT "prompts" / "logging" / "completions".
  - **Test B**: collapsible schema view renders, opens, and contains exact JSON — uses a stub response with one tool having `input_schema: {"type": "object", "properties": {"x": {"type": "string"}}}`. Click the schema's `<summary>`, verify the `<pre>` is visible, verify its text content is the pretty-printed JSON.
  - **Test C** (negative — covers L2.4 empty-schema branch): stub response with one tool having `input_schema: {}`. Click outer `<details>` to expand; assert `.mcp-tool-schema` element is NOT in the DOM (`expect(page.locator('.mcp-tool-schema')).to_have_count(0)`).
  - Both tests use `page.route()` to mock `/api/mcp-sources/{id}/test/connect` — this is the FIRST use of `page.route()` in the test suite; document the pattern in a code comment for future tests. Use `route.fulfill(json={...})` (Playwright Python sync API auto-sets `application/json` content-type) — cleaner than the `body=json.dumps(...)` form. The `_seed_mcp_source` helper already in the existing test file IS the same fixture pattern; copy the seed-call shape verbatim from `test_test_connection_button_visible_for_streamable_http_edit_mode` at the top of `tests/browser/test_mcp_test_connection_button.py`.
- [ ] **L2.6** — `docker exec the-one pytest -m browser tests/browser/test_mcp_test_connection_button.py -q --timeout 120` (or whatever file the new tests live in) — passes. (Browser-test runs use the playwright marker; the L1.7 default-suite gate excludes them.)
- [ ] **L2.7** — Default-suite gate: `docker exec the-one pytest tests/ -q --timeout 30 -x --ignore=tests/browser` — passes; no new failures vs L1 baseline (L0 baseline known issue still allowed).
- [ ] **L2.8** — `flight-log.md` gets a new "Leg Progress" entry naming each AC. Leg artifact's status is `landed` at end-of-leg.

## Verification Steps

1. **L2.1 + L2.2** — Open browser-test that asserts the flags one-liner. Assert the rendered text matches the spec-defined keys present in the stub response.
2. **L2.3 + L2.4** — Browser test asserts presence of nested `<details>` for tools with `input_schema`; absence for tools without.
3. **L2.5 + L2.6** — `docker exec the-one pytest -m browser tests/browser/test_mcp_test_connection_button.py -q --timeout 120 -x` passes.
4. **L2.7** — Default-suite gate passes per the canonical command.
5. **Manual smoke** (optional but recommended): start dev container, register a streamable-http MCP source against a known-public MCP (e.g. localhost-running `mcp-server-everything`), click Test connection, eyeball the rendered capability flags + schema view in Chrome devtools.
6. **L2.8** — flight-log entry present.

## Implementation Guidance

### Order of operations

1. **L2.1 + L2.2** — extend `handleTestConnection`'s success branch to render capability flags. Decide whether they go INTO `statusEl.innerHTML` (compact) or a NEW dedicated element above the tools list (more visual hierarchy). Suggested: append to `statusEl.innerHTML` after the existing "Server exposes N tools" line, on a new line via `<br>` or `<div>`. Implementer's discretion.
2. **L2.3 + L2.4** — extend the per-tool `<details>` HTML construction with a nested schema details (when `t.input_schema` is non-null AND non-empty).
3. **CSS additions** to `studio.css` for the new elements.
4. **L2.5** — write the browser tests using `page.route()` to mock the API.
5. **L2.7** — full-suite gate.

### L2.1 / L2.2 — Capability flags one-liner

In `mcp-server-editor.js::handleTestConnection`, inside the `data.status === 'ok'` branch (currently at lines 842-871), after the existing `statusEl.innerHTML = ...` assignment for "Server exposes N tools", add the capability-flags rendering.

Suggested approach: render flags into the existing `statusEl` via concatenation, OR add a new `<div class="mcp-capability-flags">` element. Either is acceptable; choose what reads best in the existing visual hierarchy.

**Scope note**: declare BOTH `SPEC_CAPABILITY_KEYS` and the `renderCapabilityFlags` helper at **module scope** — inside the file's IIFE, alongside other shared helpers (e.g. `escapeHtml`), but OUTSIDE `handleTestConnection`. This avoids re-allocating the array on every Test-connection click and keeps the helper accessible from any other function in the same IIFE that may want to render capability flags later (e.g. L3's MCPs-tab UI).

```js
// Server capability keys per the installed `mcp` SDK's ServerCapabilities
// model. 'experimental' is intentionally excluded — it's a free-form
// sub-namespace dict (per-server custom keys), not a typed presence flag.
// Update this allowlist when bumping to a newer SDK that adds new typed flags.
var SPEC_CAPABILITY_KEYS = ['tools', 'resources', 'prompts', 'logging', 'completions', 'tasks'];

function renderCapabilityFlags(capabilities) {
  if (!capabilities) return '';  // capabilities key missing entirely (pre-L1 server, defensive)
  var present = SPEC_CAPABILITY_KEYS.filter(function (k) {
    var v = capabilities[k];
    return v !== null && v !== undefined;
  });
  if (present.length === 0) {
    // Pathological but documented: server announced no capabilities.
    // Render an explicit message so operators don't see a blank.
    return '<div class="mcp-capability-flags mcp-capability-flags-empty">Server announced no capabilities.</div>';
  }
  return (
    '<div class="mcp-capability-flags">' +
    'Server supports: <strong>' + present.join(', ') + '</strong>' +
    '</div>'
  );
}
```

Then in the success branch, append the rendered HTML to `statusEl.innerHTML` after the existing "Server exposes N tools" line (or render into a sibling element):

```js
statusEl.innerHTML = (
  '<span class="mcp-tools-success">✓ Connected.</span> ' +
  'Server exposes <strong>' + data.tools.length + '</strong> tool' +
  (data.tools.length === 1 ? '' : 's') + '.' +
  renderCapabilityFlags(data.capabilities)  // F8 L2
);
```

### L2.3 / L2.4 — Per-tool schema view

In the tool-rendering loop at lines 852-868, after the description block but BEFORE the closing `</details>`, inject the nested schema details:

```js
// F8 L2: nested input-schema view. Pretty-print JSON for operator
// inspection. Render only when input_schema is non-null and non-empty —
// the closed-by-default outer details already handles the no-schema
// case cleanly without an empty nested toggle.
if (t.input_schema && Object.keys(t.input_schema).length > 0) {
  var schemaJson = JSON.stringify(t.input_schema, null, 2);
  // escapeHtml the JSON to defang any control chars in property names.
  // The pretty-printed form preserves whitespace via <pre>'s default
  // rendering; no <br> conversion needed.
  html += '<details class="mcp-tool-schema">';
  html += '<summary class="mcp-tool-schema-summary">Input schema</summary>';
  html += '<pre class="mcp-tool-schema-content">' + escapeHtml(schemaJson) + '</pre>';
  html += '</details>';
}
```

**Empty-dict handling**: `Object.keys(t.input_schema).length > 0` skips both `null`/`undefined` (ignores via the `&&` short-circuit on `t.input_schema`) AND empty `{}`. This matches L2.4's spec.

### CSS additions in `studio.css`

Append after the existing `.mcp-tool-description-empty` rule (around line 109):

```css
  .area-studio .mcp-capability-flags { font-size: var(--font-size-body-sm); color: var(--fg-secondary); margin-top: 4px; }
  .area-studio .mcp-capability-flags-empty { font-style: italic; opacity: 0.7; }
  .area-studio .mcp-tool-schema { margin: 0 12px 8px 32px; }
  .area-studio .mcp-tool-schema-summary { cursor: pointer; padding: 4px 0; font-size: var(--font-size-body-sm); color: var(--fg-secondary); user-select: none; }
  .area-studio .mcp-tool-schema-summary:hover { color: var(--accent); }
  .area-studio .mcp-tool-schema-content { font-family: var(--font-family-mono, monospace); font-size: var(--font-size-body-sm); background: var(--surface-elevated); border: 1px solid var(--border); border-radius: 4px; padding: 8px; margin: 4px 0 0; overflow-x: auto; max-height: 400px; overflow-y: auto; white-space: pre; word-break: normal; }
```

`--surface-elevated` (project token defined in `tokens.css`) gives the schema `<pre>` a slightly raised background inside the open `.mcp-tool-item` (which uses `var(--surface)`). The `max-height: 400px` keeps long schemas from dominating the page.

### L2.5 — Browser tests with `page.route()`

Add to `tests/browser/test_mcp_test_connection_button.py` (or create `tests/browser/test_mcp_source_edit_tools_polish.py` if cohesion suffers — implementer's call). Pattern:

```python
@pytest.mark.browser
def test_capability_flags_render_for_announced_capabilities(
    app_clean: str, page: Page
) -> None:
    """L2.1: capability flags show the spec-defined keys whose values are non-null."""
    sid = _seed_mcp_source(app_clean, {
        "name": "polish-cap-source",
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp"},
        "secrets": {},
    })

    # Mock /test/connect to return a stub success payload. F8 L2 — first
    # use of page.route() in this codebase. The handler resolves with a
    # synthetic JSON body so the UI renders without a real MCP server.
    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "status": "ok",
                "tools": [{"name": "echo", "description": "echo back", "input_schema": {}}],
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": None,
                    "logging": None,
                    "completions": None,
                },
            }),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_test_connect)

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    test_btn.click()

    flags = page.locator(".mcp-capability-flags")
    expect(flags).to_be_visible(timeout=4000)
    expect(flags).to_contain_text("tools")
    expect(flags).to_contain_text("resources")
    # Negative assertions: prompts/logging/completions were null → not rendered.
    flags_text = flags.inner_text()
    assert "prompts" not in flags_text
    assert "logging" not in flags_text
    assert "completions" not in flags_text
```

Sketch for L2.3 schema-view test:

```python
@pytest.mark.browser
def test_input_schema_collapsible_renders_pretty_json(
    app_clean: str, page: Page
) -> None:
    """L2.3: input_schema renders inside a nested <details>; opens to show pretty JSON."""
    sid = _seed_mcp_source(app_clean, {...})

    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    def handle_test_connect(route):
        route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({
                "status": "ok",
                "tools": [{"name": "echo", "description": "", "input_schema": schema}],
                "capabilities": {"tools": {}, "resources": None, "prompts": None, "logging": None, "completions": None},
            }),
        )
    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_test_connect)

    page.goto(f"{app_clean}#studio/mcp-sources/{sid}")
    page.locator('[data-testid="mcp-test-connection"]').click()

    # Expand the outer tool details first.
    page.locator(".mcp-tool-item").first.click()
    schema_summary = page.locator(".mcp-tool-schema-summary")
    expect(schema_summary).to_be_visible(timeout=4000)
    schema_summary.click()
    pre = page.locator(".mcp-tool-schema-content")
    expect(pre).to_be_visible()
    # Exact JSON content match.
    expected = json.dumps(schema, indent=2)
    expect(pre).to_have_text(expected)
```

**Imports**: at the top of the test file, `import json` if not already present.

**Note on browser-test stability**: `page.route()` runs in the page context; the route handler MUST execute synchronously (no `await` allowed in the typical Python Playwright sync API). The `route.fulfill(...)` call returns immediately. If timing flakiness surfaces, use `page.wait_for_response("**/test/connect")` after clicking the button to ensure the mock fired before asserting the DOM.

## Edge Cases

- **`data.capabilities` field missing entirely** (pre-L1 server, or future API change): `renderCapabilityFlags(undefined)` returns empty string — no flags status. Existing "Server exposes N tools" text unchanged. Defensive coding because L1 is on the same branch as L2; once L0+L1+L2 commit together this can't actually happen, but the helper stays defensive against future drift.
- **Long schemas overflowing the schema-content `<pre>`**: CSS sets `max-height: 400px` + `overflow-y: auto` — the operator scrolls. No horizontal-scroll issue: `overflow-x: auto` handles wide schemas (rare but possible with deeply nested arrays of long strings).
- **JSON.stringify on a schema with a circular reference**: would throw a TypeError in the browser. MCP `input_schema` is always derived from a JSON-serializable Pydantic model, so circular refs aren't possible — but if the API ever surfaces malformed JSON, the catch handler at line 909-912 (`.catch`) handles it. The L2 schema-render code is INSIDE the `.then` callback so a JSON.stringify throw here would propagate to the catch — good behavior; renders a network-error message and the operator retries.
- **Empty `input_schema` `{}` vs missing `input_schema`**: both produce no nested details (per L2.4). The `Object.keys(...).length > 0` predicate covers both via `&& t.input_schema` short-circuit.
- **Server announces an unknown capability key** (e.g. spec revision adds `notifications`): the allowlist filters it out at render time. Operator doesn't see it. Documented behavior: the spec-key allowlist needs updating when targeting a newer MCP revision; until then, unknown keys are invisible.
- **`page.route()` doesn't fire in time**: the mock is attached via `page.route()` BEFORE `page.goto(...)`, so the route is registered when the editor page loads. Click → fetch → route handler fires. If the test still flakes, add `page.wait_for_response(url_pattern)` after the click before asserting DOM.
- **Multiple tools with input_schema** (most common case): each tool gets its OWN nested `<details>`. The CSS scopes nested details with `.mcp-tool-schema` so they don't accidentally style the parent `.mcp-tool-item`.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — extend `handleTestConnection`'s success branch with capability-flags rendering and per-tool schema-details rendering. ~25-35 lines added (mostly the `renderCapabilityFlags` helper and the nested-details HTML).
- `the_one/interfaces/web/static/css/studio.css` — append ~6 new CSS rules. ~7 lines added.
- `tests/browser/test_mcp_test_connection_button.py` (or new sibling) — append 3 browser tests (Test A capability flags, Test B schema view, Test C empty-schema negative) with `page.route()` mocking. ~120-160 lines added.
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/flight-log.md` — append L2 progress entry.
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/flight.md` — check off L2 (final commit step at flight close).
- `missions/07-mcp-integration/flights/08-studio-mcps-tab/legs/02-source-edit-tools-polish.md` — update status to `landed`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `docker exec the-one pytest -m browser tests/browser/test_mcp_test_connection_button.py -q --timeout 120 -x` passes
- [ ] Default-suite scoped run passes (no new failures vs L1 baseline)
- [ ] Manual smoke (optional but recommended): start dev container, hit Test connection against a real source, eyeball capability flags + schema view
- [ ] Update `flight-log.md` with the L2 progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT commit yet — orchestrator batches code review + commit at flight end
- [ ] Signal `[HANDOFF:review-needed]`

## Citation Audit

8 citations verified against current code at leg design time:

- `mcp-server-editor.js:822-914` (`handleTestConnection` function) — **OK**.
- `mcp-server-editor.js:842-871` (`data.status === 'ok'` branch) — **OK**.
- `mcp-server-editor.js:131-138` (Tools section scaffold) — **OK**, verified status-div + tools-list-div present.
- `mcp-server-editor.js:852-868` (per-tool render loop) — **OK**, the `<details>` build is at lines 854-867.
- `studio.css:96-109` (existing mcp-tool CSS) — **OK**.
- `api.py:887` (post-L1 `"capabilities": capabilities` line) — **VERIFIED POST-L1** by reading current file state — added by the L1 implementation.
- `tests/browser/test_mcp_test_connection_button.py` (existing test home) — **OK**, exists.
- Installed `mcp` SDK's `ServerCapabilities` typed flags (`tools`, `resources`, `prompts`, `logging`, `completions`, `tasks`) — **OK** per the SDK's `mcp.types` module (verified at design-review time); `experimental` is a free-form sub-namespace dict, not a typed presence flag.

No drift detected; no repairs needed.
