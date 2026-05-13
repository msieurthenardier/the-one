# Leg: 03-mcp-sources-polish

**Status**: landed
**Flight**: [Studio Polish](../flight.md)
**Mode**: Vibe (interactive, operator-driven)

## Objective

Polish the MCP Sources area of Studio — the MCP Servers tile grid + the MCP Server editor (single 1670-line file holding the source-detail form, connection-test flow, OAuth interactions, and the per-tool list) — composing the alien-dashboard design-language vocabulary onto `.content-panel` interior. Wire `.indicator-led--{state}` at three pinned consumer sites for connection-state visibility (one autonomous-eligible sub-task isolated from the open-ended polish vibe). M07-landed MCP UI structure is preserved — this is cosmetic-consistency only.

## Mode: Vibe Leg

This is an interactive leg. The operator iterates on aesthetic choices in the browser; the Flight Director makes edits in real-time and reloads. No autonomous Developer spawn for the vibe rounds — but the **LED wire-up sub-task is known-finite scope** (3 consumer sites pinned in the pre-leg audit), so it MAY be lifted into an autonomous Developer pass at operator discretion. Cadence per Flight 3.5: "land dark, port light" — anchor dark first, port light at leg close as a value-swap exercise.

Acceptance is qualitative for the polish vibe ("operator approves") + mechanical for the LED wire-up (grep verifies the three pinned sites carry the primitive with the documented posture-to-state mapping).

## Starting State (working-tree carry-in)

At kickoff the working tree carries uncommitted operator vibe scratch (logged in flight-log under `### Leg 03 kickoff (2026-05-13)`):
- `the_one/interfaces/web/static/css/studio.css` (+84 lines) — `.mcp-tool-item` per-tool tile restructured to compose `--glass-bg` / `--glass-gleam` / `--glass-border` / `--bezel-shadow` / `--panel-radius`. New summary-line layout with `mcp-tool-summary-text` (name + truncated description on one line, 100-char ellipsis) + `mcp-tool-chevron` chevron + `mcp-tool-body` expansion section with dashed top-border.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` (+34 lines) — `renderToolsListHtml()` rebuilt to emit the new tile structure (summary with name + preview, body with full description + input schema collapsible). Two `renderCapabilityFlags(...)` calls dropped from the post-test status text.

**Treat as Leg 03's starting point** — do NOT revert. The vibe iteration continues from here.

## Surfaces in Scope

1. **MCP Servers tile grid** — `static/js/areas/studio/mcp-servers-grid.js` (117 lines). Tile DOM at `mcp-servers-grid.js:renderMcpServersGrid — "var html = '<button class=\"entity-tile mcp-source-tile\""`. Currently `[type-badge][name][meta]`. Polish: tile spacing rhythm, badge treatment (stdio vs streamable-http), connection-state slot (LED consumer #3, see below).

2. **MCP Server editor** — `static/js/areas/studio/mcp-server-editor.js` (1670 lines). Polish surfaces:
   - **Editor header** — Refresh-connection / Reset-connection button pair + last-updated timestamp (`mcp-server-editor.js:renderEditor — "mcp-connection-actions"`).
   - **Connection-status banner** — `mcp-tools-status` block (currently a text-only line: "✓ Connected. Server exposes N tools." OR "Click Refresh connection above…"). LED consumers #1 + #2 land here.
   - **Tools list** — already restructured into glass-tile pattern via the working-tree vibe scratch; cosmetic polish continues from there.
   - **Form sections** — Identity + Type-specific config (stdio vs streamable-http) + Environment/Headers KV table + Sandbox section (stdio-only) + Danger Zone. Polish: section-divider treatment, field-row hierarchy.

Out of scope:
- Structural change to M07 UI (cosmetic-only per mission spec — no removed `data-testid` hooks, no removed form fields, no behavior change)
- Native `<select>` migration at `mcp-server-editor.js:506, :533` (Leg 04 territory; if a `<select>` rule is touched cosmetically it's still here, but no `<select>` → `App.dropdown` swap)
- Studio dirty-gate parity (Leg 05)
- Routing fixes (Leg 06)
- Snapshot baseline regen (Leg 07)
- Knowledge-tab anything (stub-polish-deferred per flight spec; unrelated surface)

## LED wire-up (pre-leg audit results)

Three consumer sites, pinned per the Architect design review's requirement to isolate the wire-up from the open-ended polish vibe:

### Consumer #1: editor-mode success state

**Site**: `mcp-server-editor.js:renderEditor — "<span class=\"mcp-tools-success\">✓ Connected.</span>"` (currently at line 446-451 in HEAD; line numbers will shift once the working-tree scratch lands).

**Condition**: `source.config._cache && Array.isArray(source.config._cache.tools)` — i.e. the source has been successfully test-connected at least once and the cached tools list survived.

**State**: `.indicator-led--success` immediately before the `<span class="mcp-tools-success">✓ Connected.</span>` text. Compose as `<span class="indicator-led indicator-led--success"></span>` followed by a literal space. (No `aria-hidden` attribute — conforming to the canonical sitewide LED pattern at `provider-models.js:347, :376` which omits it. The LED is decorative state that's redundant with the adjacent text + count, so screen readers reading the surrounding content already convey the state.)

### Consumer #2: editor-mode idle state

**Site**: `mcp-server-editor.js:renderEditor — "Click <strong>Refresh connection</strong> above"` (currently at line 456-458 in HEAD; same shift caveat).

**Condition**: source exists (post-create) but `_cache` absent or `_cache.tools` missing/empty.

**State**: `.indicator-led--idle` prefixing the "Click Refresh connection above…" text.

### Consumer #3: tile-grid connection state

**Site**: `mcp-servers-grid.js:renderMcpServersGrid — "'<button class=\"entity-tile mcp-source-tile\"'"` tile-render loop at `mcp-servers-grid.js:80-102`. NEW slot — does not exist today.

**Slot shape**: Add `<span class="indicator-led indicator-led--{state}"></span>` as the first child of the `<button>`, **before** the existing `entity-tile-badge`. Existing markup order (badge → name → meta) is preserved after the LED. (No `aria-hidden` — same canonicity rationale as consumer #1.)

**Posture-to-state mapping** (derived from `_cache` write sites in `the_one/interfaces/web/api.py`):

| Cached state | LED state | Vocabulary anchor |
|---|---|---|
| `_cache.tools` is an array (any length, including empty) | `success` | All three full-test cache-write sites (`_build_and_test_no_auth_mcp` ~line 1083, `_build_and_test_stdio_mcp` ~line 1171, oauth Phase A ~line 1389) write `tools` only on successful `list_tools()`. Tools-array-present ⟺ last test succeeded. Empty array (server connected, zero tools) classifies as `success` to match the existing editor banner ("✓ Connected. Server exposes 0 tools.") rendered by the current `Array.isArray(cache.tools)` guard at `mcp-server-editor.js:444`. |
| `_cache.auth_posture === "oauth"` AND no `tools` field | `warning` | The `_probe_auth_posture` path at `api.py:1335` writes `_cache` with only `auth_posture: "oauth"` (no `tools`) when an OAuth source has been posture-detected but not yet successfully connected. This is the ONLY production write path that leaves a `_cache` entry without `tools`. |
| No `_cache` at all | `idle` | Source persisted but never test-connected. |

**No `danger` state today.** Codebase trace confirms no production cache-write path leaves a `_cache` with a missing `tools` field AND no `auth_posture === "oauth"`. Failed `list_tools()` calls do NOT clear the existing cache — they leave the pre-existing state intact (or the never-cached absence intact). If a future cache-write path introduces this state, the helper's final fallback should add the `danger` branch back; until then it would be dead code.

**Implementation helper**: extract a `function mcpSourceLedState(source) { ... }` returning one of `'success' \| 'warning' \| 'idle'` and reuse from both `mcp-servers-grid.js` (per-tile) and `mcp-server-editor.js` (editor status banner — replaces the current 2-state `cache.tools ? success : idle` branch).

Place the helper in a small new export on `window.App.studio` OR inline in each consumer (single function, ~15 LOC). Prefer the shared helper to keep the posture mapping in one place — both consumers read the same `source.config._cache` shape, and grid-vs-editor parity is a hard requirement (a green tile that opens to an idle editor is a bug).

### Dynamic re-render path

After `/test/connect` resolves, `mcp-server-editor.js` re-renders the status block dynamically (see `mcp-server-editor.js — "mcp-test-connection"` button handler around line 1039+ in HEAD). The LED in consumer #1 must update in this path too. The cleanest hookup: re-evaluate `mcpSourceLedState(source)` after the source-config refetch that already happens post-test, and re-render the LED + status text together.

## Iteration Axes (cover at least)

- **Grid tile visual weight** — currently `.entity-tile` inherits Flight 2 glass; verify it composes with the new LED slot at the leading edge without breaking the existing `entity-tile-badge` rhythm.
- **Editor header chrome** — Refresh-connection + Reset-connection button pair + last-updated timestamp. Currently sits in a `.field-row` + `.mcp-connection-actions`; polish target is unifying the visual weight of action-pair vs the form sections below.
- **Connection-status banner** — once LED is wired, the banner has icon (LED) + verb ("Connected." / "Refresh to discover…") + count. Polish the spacing + color/weight relationship.
- **Section-divider rhythm** — many editor sections (Identity, Type config, Environment, Headers, Sandbox, Tools, Danger Zone). Current dividers are `.editor-section` + `.section-title`; verify they read as a coherent stack on the alien-dashboard chrome.
- **Form field-row hierarchy** — label-input contrast, info-icon positioning (`.kv-info-btn` etc.), help-hint typography (`.form-hint`, `.mcp-command-hint`).
- **Sandbox section (stdio-only)** — gated visibility via `.is-hidden`. Verify the section visually integrates when shown and disappears cleanly when hidden.
- **Empty grid state** — `.empty-canvas` CTA when zero MCP servers (`mcp-servers-grid.js:65-77`). Already inherits Flight 2 polish from prior agents-grid work; smoke-check parity.
- **Danger Zone delete button** — `.btn-muted-destructive` styling at the bottom of the editor.
- **Per-tool tile body** — schema collapsible (`<details class="mcp-tool-schema">`) inside the new tile body. Working-tree scratch added the tile shell; the inner schema collapsible may need its own polish pass.

## Acceptance Criteria

- [ ] **Polish (operator-approved)**: MCP Servers grid + MCP Server editor read on-brand in both themes; operator confirms dark + light at leg close.
- [ ] **LED wire-up complete**: `.indicator-led--{success|warning|idle}` appears at all three pinned consumer sites with the documented posture-to-state mapping.
- [ ] **Posture-to-state helper**: A single `mcpSourceLedState(source)` function (shared between grid + editor) encapsulates the posture mapping. Grid-vs-editor parity verified: a tile's LED state matches the editor's LED state when the tile is opened (no logic split between consumers).
- [ ] **No structural change to M07 UI**: grep verifies all existing `data-testid` hooks on the editor + grid surfaces survive. Specifically: `data-testid="mcp-source-card"`, `data-testid="mcp-test-status"`, `data-testid="mcp-test-connection"`, `data-testid="mcp-tools-list"`, `data-testid="mcp-tools-last-updated"`, `data-testid="reset-mcp-connection-btn"`, `data-testid="delete-mcp-source-btn"`, `data-testid="back-mcp-source-btn"`, `data-testid="cancel-mcp-source-btn"`, `data-testid="save-mcp-source-btn"`, `data-testid="new-mcp-source-btn"`, `data-testid="new-mcp-source-btn-empty"`, `data-testid="mcp-command-runtime"`, `data-testid="mcp-command-custom"`, `data-testid="mcp-kv-table"`, `data-testid="mcp-kv-thead"`, `data-testid="mcp-kv-tbody"`, `data-testid="kv-add-row-btn"`, `data-testid="mcp-sandbox-section"`, `data-testid="mcp-command-hint"`, `data-testid="mcp-kv-sensitive-info"`. (Cross-check via `grep -c "data-testid=\"mcp-" the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js` — pre-leg count is the floor. The dynamic `data-testid="mcp-consent-btn"` set at runtime on the OAuth consent button via `setAttribute` is counted by the source-string grep but is not in this enumerated list because it's a transient hook, not a stable structural attribute.)
- [ ] **No new native `<select>` introduced** (Leg 04 migrates the existing 4 Studio sites; do not add a 5th).
- [ ] **No new files**: all edits land in `studio.css` + `mcp-server-editor.js` + `mcp-servers-grid.js`. Helper placement on `window.App.studio.*` if shared; in-file otherwise.
- [ ] **Reduced-transparency posture preserved**: no new fixed gradients/glows that bypass shell tokens. Token additions, if any, land in BOTH theme blocks in `tokens.css`.
- [ ] **No regression in narrow test gate**: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30` is green (same 4-module gate Legs 01–02 used).
- [ ] **No regression in MCP-related tests**: `docker exec the-one pytest tests/test_mcp_client.py tests/test_mcp_stdio_test_connect.py tests/test_mcp_connection_reset.py tests/test_oauth_test_connection_endpoint.py -x -q --timeout 30` stays green. (Adding LED markup is presentation-only — no backend touch — so these should be stable, but verify after each non-trivial change.)
- [ ] **Browser smoke check**: navigate to Studio → MCP Sources, open an existing source, observe LED state in grid + editor matches; click Refresh connection on a known-good source and observe LED transitions through `idle` / `warning` / `success` cleanly (no `danger` in production today per the posture-mapping table); theme-toggle exercised both directions; console clean.
- [ ] **Flight log updated** with vibe-iteration outcomes (CSS rule sites touched, JS markup changes, posture-to-state mapping decisions, helper placement, anomalies).

## Verification Steps

1. **LED grep sentinel** (mechanical): `grep -c "indicator-led" the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js` — expect ≥3 total matches (1 for editor success state, 1 for editor idle state, 1 for grid tile slot; helper if shared may surface additional matches).
2. **Helper grep sentinel**: `grep -n "mcpSourceLedState" the_one/interfaces/web/static/js/areas/studio/*.js` — expect ≥2 matches (definition + at least one consumer); ≥3 if both grid + editor consume from the shared definition site.
3. **data-testid floor**: `grep -c "data-testid=" the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js` — measure pre-leg, then post-leg should be `>=` pre-leg.
4. **Narrow gate**: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30`.
5. **MCP regression sweep**: `docker exec the-one pytest tests/test_mcp_client.py tests/test_mcp_stdio_test_connect.py tests/test_mcp_connection_reset.py tests/test_oauth_test_connection_endpoint.py -x -q --timeout 30`.
6. **Manual browser sweep** (operator-driven):
   - Open Studio → MCP Sources with at least 2 saved sources (one with cached tools, one without).
   - Verify per-tile LED state matches `_cache` shape per the mapping table above.
   - Open a source with cached tools → editor LED reads success.
   - Open a source without cached tools → editor LED reads idle.
   - Click Refresh connection on a known-good source → LED transitions through any intermediate state cleanly + lands success. (Note: today's production cache shape only produces `success` / `warning` / `idle` — see the posture-to-state mapping table; no `danger` transition is expected.)
   - Toggle theme both directions; verify LED reads correctly under each theme (glows + base colors are token-driven so this should be free).
   - Console clean across all transitions.

## Implementation Guidance

1. **Build the posture-to-state helper first** (autonomous, ~15 LOC):
   - Either as `window.App.studio.mcpSourceLedState = function (source) { ... }` at the top of `mcp-servers-grid.js` (the smaller file, easier to find) OR as a private helper in each consumer (duplicates ~15 LOC).
   - **Recommend shared placement on `window.App.studio.mcpSourceLedState`** — single source of truth for posture mapping. Mirror the pattern used by other studio helpers (e.g., `App.studio.renderMcpServersGrid`).
   - Logic (3-state — `danger` removed per design review; no production cache-write path produces it):
     ```js
     function mcpSourceLedState(source) {
       var cache = (source && source.config && source.config._cache) || null;
       if (!cache) return 'idle';
       if (Array.isArray(cache.tools)) return 'success';
       if (cache.auth_posture === 'oauth') return 'warning';
       return 'idle';
     }
     ```
   - The `Array.isArray(cache.tools)` check (any array, including empty) matches the existing editor-banner guard at `mcp-server-editor.js:444` — zero-tools servers classify as `success` to preserve UX parity with today's banner.

2. **Wire consumer #3 first** (grid tile LED slot). Add the LED span inside the tile-render loop in `mcp-servers-grid.js:renderMcpServersGrid` — first child of the `<button>`, before `entity-tile-badge`. Smoke-check: tiles for saved sources render with the LED in the right slot in both themes.

3. **Wire consumers #1 + #2** (editor connection-status banner). Replace the existing 2-state `cache && Array.isArray(cache.tools) ? successInner : idleInner` branch in `mcp-server-editor.js:renderEditor` with the LED-prefixed equivalent. Use the same helper.

4. **Wire the dynamic re-render path**. After `/test/connect` resolves, re-evaluate `mcpSourceLedState(source)` post-refetch and rerender the LED alongside the existing `statusEl.innerHTML = …` write at `mcp-server-editor.js — "Server exposes <strong>"` (around line 1601 in HEAD; will drift with the working-tree scratch).

5. **Then operate the vibe iteration** on grid spacing, editor header polish, section-divider rhythm, form-row hierarchy. Operator drives in dark first; port light at vibe-close.

6. **CSS placement**: all new MCP-specific styling goes in `studio.css` under `.area-studio`. If the LED slot needs spacing inside `.mcp-source-tile`, add `.area-studio .mcp-source-tile .indicator-led { ... }` — do NOT modify the global `.indicator-led` rule in `components.css`.

## Edge Cases

- **`_cache` with `tools: []` (empty array)**: server returned zero tools. Helper classifies as `success` (matches existing editor banner UX: "✓ Connected. Server exposes 0 tools."). Rationale: the connection succeeded; an empty catalog is a server-side reality, not a connection failure. The user-facing distinction is "did we reach the server" — the count is conveyed separately by the banner text.
- **Stdio cache write doesn't set `auth_posture`**: `_build_and_test_stdio_mcp` writes `tools/capabilities/server_info/instructions/last_updated` but no `auth_posture` (HTTP-only concept). Mapping handles this correctly: stdio source with tools → success (first branch matches before any `auth_posture` check).
- **Source mid-OAuth-consent**: between user clicking Test connection on an OAuth source and the consent popup resolving, `_cache.auth_posture` may already be set to `"oauth"` but `tools` not yet populated. Helper returns `warning`. Confirm this is the desired transient state.
- **`source.config` is `null`/undefined**: defensive guards in the helper handle this (`source && source.config && source.config._cache`). Returns `idle`.
- **Grid tile LED interferes with existing aria-selected**: the `aria-selected="{true|false}"` attribute is on the `<button>`. Adding a child LED span doesn't affect aria — verify visually that the active-tile treatment (currently the V3b accent-translucent state from Flight 2) still reads clearly with the LED visible.
- **`.content-panel` mask-image fade at top**: any new elevated treatment near the editor top may interact with the 8px mask. Visually verify (same caveat as Leg 02).
- **Working-tree scratch shifts line numbers**: the Leg 03 citation references HEAD line numbers for the LED consumer sites. Once the working-tree scratch lands those numbers will drift by ~17 lines in the affected region of `mcp-server-editor.js`. Use the snippet form (`"<span class=\"mcp-tools-success\">"` etc.) to locate the actual current line during implementation.
- **Schema collapsible inside the new tool tile body**: `<details class="mcp-tool-schema">` nested inside the working-tree's new `.mcp-tool-body`. Two collapsibles nested — verify keyboard/click semantics don't get stuck (open outer + click inner summary shouldn't collapse outer).
- **No new tokens needed in theory**: `--status-success`, `--status-warning`, `--status-danger`, `--status-{state}-glow`, `--fg-muted` are all defined and the LED primitive (`components.css:864-877`) is canonical. If the operator wants a Studio-specific glow intensity, add a token — but the default should be the canonical primitive.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js` — add LED slot to tile render; add shared posture-to-state helper (if shared placement chosen).
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — replace 2-state status-text branch with LED-prefixed equivalent; update dynamic re-render path post-/test/connect; continue working-tree vibe iteration on form/section polish.
- `the_one/interfaces/web/static/css/studio.css` — continue vibe iteration on grid + editor surfaces; add `.area-studio .mcp-source-tile .indicator-led { spacing }` rule if needed.
- `the_one/interfaces/web/static/css/tokens.css` — IF the operator introduces new tokens (default: none expected; the existing `--status-*` palette covers the LED states).
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight-log.md` — append a "Leg 03 progress" entry under `## Leg Progress` mirroring the Leg 01 / Leg 02 entries' shape (Status / Implemented / Verification / Anomalies / Functional Batches if any).

## Vibe-Close Checklist

When operator says "good":

1. LED grep sentinel passes (≥3 `.indicator-led` matches across the two JS files).
2. Helper grep sentinel passes (≥2 `mcpSourceLedState` matches).
3. data-testid floor preserved (post-count ≥ pre-count on both files).
4. Theme toggle exercised both directions; light port complete; no dark-only or light-only regressions.
5. Smoke-check console clean on Studio → MCP Sources → tile-click → editor → Refresh connection flow.
6. Any new tokens added to BOTH theme blocks in `tokens.css` (default: no new tokens needed).
7. `studio.css` edits scoped under `.area-studio` (no leak to other areas).
8. No new native `<select>` added.
9. Narrow gate green; MCP-regression sweep green.
10. Flight log updated with summary of surfaces touched + LED wire-up record + posture-mapping decisions + any anomalies + opportunistic functional batches (if any landed).
11. Update leg status to `landed`.
12. **Do NOT commit per-leg.** Per agentic-workflow spec, code review + commit are deferred until after the last autonomous leg of the flight (Leg 05 today). Working-tree changes accumulate.

## Opportunistic Functional Batch (operator-directed mid-leg)

Same charter as Leg 02 (mission.md "opportunistic bug fixes only" + Leg 02's operator directive "jam in all functional things we find in this leg into it"): if functional gaps surface during the MCP Sources vibe, absorb them into Leg 03 rather than logging for later. Candidates that might surface (none committed):

- **Surface server-declared `serverInfo` + `instructions` on the editor + grid** — Leg 02 surfaced these on the agent-editor MCPs tab tile. The MCP Servers grid tiles + MCP Server editor header are natural mirror sites. If operator wants, add the subtitle line `{title||name} · v{version}` and the `title=` tooltip for `instructions` on both surfaces.
- **Refresh-connection button affordance** — the button exists for streamable-http + stdio. If a third source-type-conditional posture surfaces during vibe, decide whether to surface it as a state (LED) or as a button-disabled treatment.
- **Reset-connection confirmation modal styling** — `confirm-mcp-connection-reset` dialog (currently uses `App.confirmDialog`). If its visuals look off against the polished editor, polish it.

Anything more substantial (new fields, new endpoints, schema changes) is OUT of scope — log as Known Issue and route to a future flight per the mission's "opportunistic-only" charter.

## Post-Completion Checklist

(Per the project's leg-artifact template — Vibe legs collapse some of these into the Vibe-Close Checklist above.)

- [ ] All acceptance criteria verified (mechanical + qualitative)
- [ ] LED wire-up confirmed at all 3 pinned consumer sites with correct posture-to-state mapping
- [ ] Narrow gate + MCP regression sweep green
- [ ] Flight log updated with Leg 03 progress entry
- [ ] Leg status set to `landed` (in this file's header)
- [ ] Leg checked off in `flight.md`
- [ ] **No commit yet** — flight-end review + commit per agentic-workflow

## Citation Audit

Citations in this artifact verified against current HEAD code at design time (2026-05-13), with corrections per design review (`_cache` write-site line numbers re-confirmed against actual file content):

| Citation | Form | Resolution |
|---|---|---|
| `mcp-server-editor.js:446-451` (success state snippet) | line + snippet | OK at HEAD; will drift ~+17 lines once the working-tree scratch lands. Snippet form `"<span class=\"mcp-tools-success\">✓ Connected.</span>"` is the durable locator. |
| `mcp-server-editor.js:444` (existing `Array.isArray(cache.tools)` guard) | line + snippet | OK at HEAD. Durable locator: `"Array.isArray(cache.tools)"` — the existing 2-state branch the LED-wired version replaces. |
| `mcp-server-editor.js:456-458` (idle state snippet) | line + snippet | OK at HEAD; same drift caveat. Durable locator: `"Click <strong>Refresh connection</strong> above"`. |
| `mcp-server-editor.js:506, :533` (native `<select>` sites — Leg 04 territory) | line | Inherited from flight spec, out of scope here. |
| `mcp-server-editor.js:1039+` (testBtn dynamic-render path) | line + symbol-via-grep | OK at HEAD. Durable locator: `'[data-testid="mcp-test-connection"]'` lookup. |
| `mcp-server-editor.js:1601` (statusEl.innerHTML rewrite post-/test/connect success) | line + snippet | OK at HEAD. Durable locator: `"Server exposes <strong>"`. The `auth_required` path (~1634-1646) and error path (~1659) also rewrite `statusEl` but via DOM methods on separate branches — the LED wire-up only needs to update the success path; Phase 2 of OAuth consent re-enters this same handler with `data.status === "ok"` and lands at line 1601 again. |
| `mcp-servers-grid.js:80-102` (tile-render loop) | line + symbol | OK at HEAD — `renderMcpServersGrid` function body, tile-loop spans those lines. |
| `mcp-servers-grid.js:65-77` (empty-canvas branch) | line + snippet | OK at HEAD. Durable locator: `'class="empty-canvas"'`. |
| `components.css:864-877` (`.indicator-led` primitive) | line | OK at HEAD per the audit-time grep. |
| `provider-models.js:347, :376` (existing LED consumers — pattern reference, no `aria-hidden`) | line | OK at HEAD; non-modified by this leg. Confirmed during design review: existing usage omits `aria-hidden`; the three new sites conform (drift in prior draft corrected). |
| `api.py:_build_and_test_no_auth_mcp` (~line 1083, was ~1078 in initial draft) | symbol + line | OK at HEAD — function begins ~1056, the `persisted_config["_cache"]` write lands ~line 1083 in current code. |
| `api.py:_build_and_test_stdio_mcp` (~line 1171, was ~1160 in initial draft) | symbol + line | OK at HEAD — same function-symbol locator, `_cache` write ~line 1171. |
| `api.py:1389` oauth Phase A `_cache` write (was ~1371 in initial draft) | line + snippet | OK at HEAD. Durable locator: `'tools_cache_payload = ['` block inside the Phase A `async with MCPClient(...)`. |
| `api.py:1335` `_probe_auth_posture` `_cache` write — the only path producing `auth_posture: "oauth"` with no `tools` field | line + snippet | OK at HEAD. Durable locator: `'persisted_cache["auth_posture"] = "oauth"'`. Confirmed during design review as the sole production write path for the `warning` LED state. |
| `studio.js:301-303` (Studio inline dirty+inEditor gate — Leg 05 territory) | line | Inherited from flight spec; out of scope here. |
| `tokens.css:166, :365` (post-Leg-01 `--shell-bg` definitions) | line | OK at HEAD; not modified by this leg. Cited only as a touchpoint for the "add new tokens to both themes" reminder. |

14 citations verified clean against current code; 3 corrections applied during design review (`_cache` write-site line numbers tightened, `auth_posture` posture-probe path added as the formal `warning`-state vocabulary anchor, and a `mcp-server-editor.js:444` citation added for the existing `Array.isArray(cache.tools)` guard the helper preserves parity with). One non-citation correction also applied: `data-testid="mcp-source-name"` removed from the acceptance-criteria preservation list — that hook does not exist in the codebase.
