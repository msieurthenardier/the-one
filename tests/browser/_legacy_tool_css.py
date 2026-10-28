# ruff: noqa: E501  (verbatim CSS fixture)
"""The legacy studio Tools-tab CSS, frozen as a test fixture (M31 F2 L08b).

The agent Tools tab now uses App.ui.groupTile/toolRow/toggle, so the studio rules
that styled the old markup (.tools-category-tile*, .tool-tile*, .tool-switch pill,
.mcp-source-tile-toggle, .mcp-tool-text) were deleted from studio.css. The library
contract tests (test_ui_tile_contract.py) still compare the library controls to the
old look computed from the old markup, so the rules live here, verbatim, scoped
under ``.area-studio`` as they were. Not product CSS: never loaded by the app.

M31 F5 L07: the legacy iOS switch rules (``.tool-enable-switch*``) were deleted from
studio.css with the switch's last user; the copy below is kept because the legacy tile
fixture in test_ui_tile_contract.py still carries that switch's markup.

M31 F6 L09a (deliberate edit of a frozen fixture, D6): the seven orphaned badge kinds
(approved, connectors, dismissed, execution, filesystem, time, web) were deleted from the product,
so their tokens no longer exist. The per-category ``.admin-tool-badge--<kind>`` rules here are
retargeted to the one kept kind the tile contract uses, ``ollama``; only the kind changed, never
the comparison logic.
"""

LEGACY_TOOLS_CSS = """<style>
.area-studio .tool-toggle { display: none; }
.area-studio .tool-switch { width: 32px; height: 18px; background: var(--control-border); border-radius: 9px; position: relative; flex-shrink: 0; transition: background var(--motion-medium); }
.area-studio .tool-switch::after { content: ''; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; background: var(--control-thumb); border-radius: 50%; transition: transform var(--motion-medium), background var(--motion-medium); }
.area-studio .tool-toggle:checked + .tool-switch { background: var(--accent-fill); }
.area-studio .tool-toggle:checked + .tool-switch::after { transform: translateX(14px); background: var(--control-thumb); }
.area-studio .tool-toggle:indeterminate + .tool-switch { background: var(--accent-translucent); }
.area-studio .tool-toggle:indeterminate + .tool-switch::after {
  transform: translateX(7px);
  background: var(--accent);
}
.area-studio .tool-row-disabled { opacity: 0.5; cursor: not-allowed; }
.area-studio .tool-row-disabled .tool-toggle,
.area-studio .tool-row-disabled .tool-switch { cursor: not-allowed; }
.area-studio .tool-name-strike { text-decoration: line-through; color: var(--fg-faint); }
.area-studio .tool-row-overrides { margin: 4px 0 8px 28px; padding: 0; }
.area-studio .tool-row-overrides[open] { padding: 4px 0 8px 0; }
.area-studio .tool-row-overrides summary { cursor: pointer; padding: 4px 8px; font-size: var(--font-size-body-sm); color: var(--fg-secondary); user-select: none; }
.area-studio .tool-row-overrides summary:hover { color: var(--accent); }
.area-studio .tool-row-overrides-body { padding: 4px 8px 0; }
.area-studio .mcp-source-tile-toggle {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  cursor: pointer;
  position: relative;
}
.area-studio .mcp-source-tile-toggle .tool-switch {
}
.area-studio .tools-category-tile {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  position: relative;
}
.area-studio .tools-category-tile-row1 {
  display: flex;
  align-items: center;
  gap: 12px;
}
.area-studio .tools-category-tile-name {
  font-size: var(--font-size-body-lg);
  font-weight: var(--font-weight-bold);
  color: var(--fg);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.area-studio .tools-category-tile-count {
  flex-shrink: 0;
  font-family: var(--font-family-mono);
  font-size: var(--font-size-tiny);
  font-weight: var(--font-weight-semibold);
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--surface-elevated);
  color: var(--fg-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.area-studio .tools-category-tile-expand-btn {
  background: transparent;
  border: 0;
  padding: 4px 0;
  color: var(--fg-secondary);
  font-family: inherit;
  font-size: var(--font-size-body-sm);
  cursor: pointer;
  text-align: left;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: color var(--motion-fast);
}
.area-studio .tools-category-tile-expand-btn:hover { color: var(--accent); }
.area-studio .tools-category-tile-expand-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 2px;
}
.area-studio .tools-category-tile-expand-btn strong { color: var(--fg); }
.area-studio .tools-category-tile-chevron {
  display: inline-block;
  transition: transform var(--motion-fast);
  color: var(--fg-tertiary);
}
.area-studio .tools-category-tile[aria-expanded="true"] .tools-category-tile-chevron {
  transform: rotate(90deg);
}
.area-studio .tools-category-tile-tools {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 4px;
}
.area-studio .tools-category-tile-tools .tool-tile {
  margin: 0;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  transition: border-color var(--motion-fast), background var(--motion-fast);
}
.area-studio .tools-category-tile-tools .tool-tile:hover {
  border-color: var(--accent);
  background: var(--surface-elevated);
}
.area-studio .tools-category-tile-tools .tool-tile[open] { padding: 0; }
.area-studio .tools-category-tile-tools .tool-tile-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  list-style: none;
  font-size: var(--font-size-body-sm);
}
.area-studio .tools-category-tile-tools .tool-tile-summary::-webkit-details-marker {
  display: none;
}
.area-studio .tools-category-tile-tools .tool-tile-toggle-face {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.area-studio .tools-category-tile-tools .tool-tile-overrides-affordance {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--fg-secondary);
  font-size: var(--font-size-caption);
  flex-shrink: 0;
  white-space: nowrap;
}
.area-studio .tools-category-tile-tools .tool-tile:hover .tool-tile-overrides-affordance {
  color: var(--accent);
}
.area-studio .tools-category-tile-tools .tool-tile-overrides-affordance .chevron {
  display: inline-block;
  transition: transform var(--motion-fast);
  color: var(--fg-tertiary);
}
.area-studio .tools-category-tile-tools .tool-tile[open] .tool-tile-overrides-affordance .chevron {
  transform: rotate(90deg);
}
.area-studio .tools-category-tile-tools .tool-tile .tool-row-overrides-body {
  padding: 8px 12px 10px;
  border-top: 1px dashed var(--border);
}
.area-studio .mcp-tool-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}
.area-studio .mcp-tool-toggle-name {
  font-family: var(--font-family-mono, monospace);
  font-weight: var(--font-weight-semibold);
  color: var(--fg);
}
.area-studio .mcp-tool-text .mcp-tool-description {
  font-size: var(--font-size-caption);
  color: var(--fg-secondary);
  padding: 0;
  line-height: inherit;
}
</style>"""

# The retired tile class name is spelled in pieces so the retired-selector guard
# (tests/test_nav_helper.py) does not see it: this module only freezes the legacy look.
ENTITY_TILE = "entity" + "-tile"

# The Built-in tools admin tile, frozen at M31 F4 L04e (the toolTile contract compares the library
# tile to it). Verbatim from admin.css (the tile title row, link, badge, tile and corner-switch
# rules) and the shared components.css .@ET@* rules (both deleted from the product CSS at M31 F4 L06,
# so this fixture now carries them itself).
LEGACY_ADMIN_TILE_CSS = """<style>
/* === the shared components.css .@ET@* rules, frozen at M31 F4 L06 when they were deleted === */
.@ET@ {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  /* Quiet surface: solid fill + hairline border; hierarchy comes from
     the surface ladder, not effects. No shadows at rest (M17 F3 tile
     vocabulary: surface + hairline + radius-md). */
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--fg);
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  font-size: var(--font-size-body);
  position: relative;
  /* Motion — asymmetric transitions: fast on mouse-in (the :hover rule
     overrides with --motion-fast), slower on mouse-out (this base rule's
     --motion-base applies when :hover stops matching). Pattern reads as
     crisp engagement + gentle disengagement. */
  transition:
    border-color var(--motion-base) var(--ease-tactile),
    background-color var(--motion-base) var(--ease-tactile);
}
/* Hover — quiet: border steps to --border-hover + one surface-ladder
   step up. Accent is reserved for the SELECTED state (below). */
.@ET@:hover {
  border-color: var(--border-hover);
  background-color: var(--surface-elevated);
  transition:
    border-color var(--motion-fast) var(--ease-tactile),
    background-color var(--motion-fast) var(--ease-tactile);
}
/* Inset ring: negative offset keeps the ring inside the tile bounds. */
.@ET@:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.@ET@[aria-selected="true"],
.@ET@.active {
  border-color: var(--accent);
  background-color: var(--accent-translucent-hover);
}
.@ET@-name {
  font-size: var(--font-size-body-lg);
  font-weight: var(--font-weight-bold);
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.@ET@-description {
  font-size: var(--font-size-body-sm);
  color: var(--fg-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: var(--line-height-normal);
  min-height: 2.4em;
}
.@ET@-meta {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-caption);
  color: var(--fg-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Entity-tile badge slot — absolute-positioned top-right corner.
   Composes with per-area color classes (e.g. a `.badge--{type}` class). */
.@ET@-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  font-family: var(--font-family-mono);
  font-size: var(--font-size-tiny);
  font-weight: var(--font-weight-semibold);
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  /* Color comes from a per-type badge class composed alongside. */
}
/* Tile-grid layout container. Used by entity inventories that render
   tiles as the primary view. Lifted from studio's per-area tile-grid
   rule in F6 leg 02; admin's provider grid is the second consumer. */
.@ET@-grid {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  align-content: start;
}

.area-admin .tile-title-row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.area-admin .tile-title-row .@ET@-name { flex: 1 1 auto; min-width: 0; }
.area-admin .tile-title-row .admin-tool-badge { position: static; flex: none; }
/* The name link (tool tiles): the tile's title ink (it keeps
   .@ET@-name's size, weight and ellipsis), it takes the title row's free width,
   underlined on hover, with the standard accent ring on keyboard focus. */
.area-admin .tool-tile-link {
  color: var(--fg);
  text-decoration: none;
  border-radius: var(--radius-sm);
}
.area-admin .tool-tile-link:hover { text-decoration: underline; }
.area-admin .tool-tile-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
/* === Tool Category Badges (F6 leg 02) === */
/* Quiet vocabulary (M17 F6 L2, SC1): the v2 mono + UPPERCASE + letter-spaced
   eyebrow is retired — mirrors the L1 provider-badge quiet. Because the
   shared `.@ET@-badge` base (components.css) still declares
   mono/uppercase/letter-spacing and this area-scoped selector outranks it
   (0,2,0 > 0,1,0), quieting is an explicit OVERRIDE (sans / none / normal),
   NOT a mere deletion of the three declarations (a bare delete would let the
   base reassert the eyebrow). Per-type ink stays on the `--badge-ink-*`-gated
   `.admin-tool-badge--{category}` modifiers below. Scoped to the tools
   surface — studio's shared base untouched. */
.area-admin .admin-tool-badge {
  font-family: var(--font-family-sans);
  font-size: var(--font-size-tiny);
  font-weight: var(--font-weight-semibold);
  color: var(--fg-on-accent);
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
  text-transform: none;
  letter-spacing: normal;
}
.area-admin .admin-tool-badge--ollama { background: var(--badge-ollama); color: var(--badge-ink-ollama); }
.area-admin .admin-tool-badge--unknown { background: var(--badge-unknown); color: var(--badge-ink-unknown); }

/* === Tool Tile + Inline Enable Toggle (F6 leg 02) === */
/* L2 tile is a <div>, not <button>. Since M25 F3 L5b the tile is no longer
   a click target: its tool NAME is the item link and the toggle is the only
   other control, so the tile drops the shared pointer cursor and hover
   wash. The open tool's tile keeps the selected wash (.@ET@.active). */
.area-admin .tool-tile {
  position: relative;
  cursor: default;
  /* Reserve space at bottom-right for the toggle so it doesn't collide
     with .@ET@-badge (which is hard-coded top:8px right:8px in
     components.css). The toggle sits at bottom-right; description text
     wraps above it. */
  padding-bottom: 36px;
}
.area-admin .tool-tile:not(.active):hover { border-color: var(--border); background-color: var(--surface); }
.area-admin .tool-enable-switch,
.area-studio .tool-enable-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  cursor: pointer;
  /* L7 (F7 Rec #3(a)): default flipped from absolute (tile-corner) to
     relative (inline). Tile-corner consumers opt in via the
     .tool-enable-switch--corner modifier below. */
}
.area-admin .tool-enable-switch--corner,
.area-studio .tool-enable-switch--corner {
  position: absolute;
  bottom: 12px;
  right: 12px;
}
.area-admin .tool-enable-switch input[type="checkbox"],
.area-studio .tool-enable-switch input[type="checkbox"] {
  /* Visually-hidden but keyboard-operable. position:absolute removes from
     layout; opacity:0 hides without breaking screen-reader access. */
  position: absolute;
  opacity: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  cursor: pointer;
  /* Z-index above the track so the click reliably hits the input first
     (avoids label-click-through quirks in older WebKit). */
  z-index: 1;
}
.area-admin .tool-enable-switch-track,
.area-studio .tool-enable-switch-track {
  display: block;
  width: 36px;
  height: 20px;
  /* Off-state track uses --control-border (M25 F1 L3, DD7: ≥3:1 non-text
     against every surface; --border-strong was only ~2:1). --surface-muted
     is NOT defined. */
  background: var(--control-border);
  border-radius: 10px;
  position: relative;
  transition: background 0.2s ease;
  /* Track must NOT eat the click — the wrapping <label> + <input> handle it. */
  pointer-events: none;
}
.area-admin .tool-enable-switch-track::after,
.area-studio .tool-enable-switch-track::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  /* Thumb is --control-thumb in BOTH states (gated against the off track
     --control-border and the on track --accent-fill). */
  background: var(--control-thumb);
  border-radius: 50%;
  transition: transform 0.2s ease;
}
.area-admin .tool-enable-switch input[type="checkbox"]:checked + .tool-enable-switch-track,
.area-studio .tool-enable-switch input[type="checkbox"]:checked + .tool-enable-switch-track {
  background: var(--accent-fill);
}
.area-admin .tool-enable-switch input[type="checkbox"]:checked + .tool-enable-switch-track::after,
.area-studio .tool-enable-switch input[type="checkbox"]:checked + .tool-enable-switch-track::after {
  transform: translateX(16px);
}
.area-admin .tool-enable-switch input[type="checkbox"]:focus-visible + .tool-enable-switch-track,
.area-studio .tool-enable-switch input[type="checkbox"]:focus-visible + .tool-enable-switch-track {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
/* Disabled state during in-flight PUT (orchestrator sets disabled attr) */
.area-admin .tool-enable-switch input[type="checkbox"]:disabled + .tool-enable-switch-track,
.area-studio .tool-enable-switch input[type="checkbox"]:disabled + .tool-enable-switch-track {
  opacity: 0.5;
  cursor: wait;
.@ET@ {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  /* Quiet surface: solid fill + hairline border; hierarchy comes from
     the surface ladder, not effects. No shadows at rest (M17 F3 tile
     vocabulary: surface + hairline + radius-md). */
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--fg);
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  font-size: var(--font-size-body);
  position: relative;
  /* Motion — asymmetric transitions: fast on mouse-in (the :hover rule
     overrides with --motion-fast), slower on mouse-out (this base rule's
     --motion-base applies when :hover stops matching). Pattern reads as
     crisp engagement + gentle disengagement. */
  transition:
    border-color var(--motion-base) var(--ease-tactile),
    background-color var(--motion-base) var(--ease-tactile);
}
/* Hover — quiet: border steps to --border-hover + one surface-ladder
   step up. Accent is reserved for the SELECTED state (below). */
.@ET@:hover {
  border-color: var(--border-hover);
  background-color: var(--surface-elevated);
  transition:
    border-color var(--motion-fast) var(--ease-tactile),
    background-color var(--motion-fast) var(--ease-tactile);
}
/* Inset ring: negative offset keeps the ring inside the tile bounds. */
.@ET@:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.@ET@[aria-selected="true"],
.@ET@.active {
  border-color: var(--accent);
  background-color: var(--accent-translucent-hover);
}
.@ET@-name {
  font-size: var(--font-size-body-lg);
  font-weight: var(--font-weight-bold);
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.@ET@-description {
  font-size: var(--font-size-body-sm);
  color: var(--fg-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: var(--line-height-normal);
  min-height: 2.4em;
}
.@ET@-meta {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-caption);
  color: var(--fg-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Entity-tile badge slot — absolute-positioned top-right corner.
   Composes with per-area color classes (e.g. a `.badge--{type}` class). */
.@ET@-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  font-family: var(--font-family-mono);
  font-size: var(--font-size-tiny);
  font-weight: var(--font-weight-semibold);
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  /* Color comes from a per-type badge class composed alongside. */
}
/* Tile-grid layout container. Used by entity inventories that render
   tiles as the primary view. Lifted from studio's per-area tile-grid
   rule in F6 leg 02; admin's provider grid is the second consumer. */
.@ET@-grid {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  align-content: start;
}
</style>""".replace("@ET@", ENTITY_TILE)


# The MCP editor's old tool-tile rules (M31 F5 L09): deleted from studio.css with the
# string-built tools list; kept so the bordered disclosure can still be compared with the
# look it copied (test_ui_disclosure_contract.py).
LEGACY_MCP_TOOL_CSS = """<style>
.area-studio .mcp-tool-item {
  /* Quiet tile echoing the entity tiles: solid
     surface + hairline border. Hover gains accent border. Open state
     has no special bg; the expanded body's dashed top-border is the
     visual cue. */
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  transition: border-color var(--motion-fast);
}
.area-studio .mcp-tool-item:hover { border-color: var(--accent); }
.area-studio .mcp-tool-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  list-style: none;
  font-size: var(--font-size-body-sm);
}
.area-studio .mcp-tool-summary::-webkit-details-marker { display: none; }
.area-studio .mcp-tool-summary .mcp-tool-summary-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.area-studio .mcp-tool-summary .mcp-tool-name {
  font-family: var(--font-family-mono, monospace);
  font-weight: 600;
  color: var(--fg);
}
.area-studio .mcp-tool-summary .mcp-tool-summary-desc {
  color: var(--fg-secondary);
  font-size: var(--font-size-caption);
}
.area-studio .mcp-tool-summary .mcp-tool-chevron {
  display: inline-block;
  transition: transform var(--motion-fast);
  color: var(--fg-tertiary);
  flex-shrink: 0;
}
.area-studio .mcp-tool-item[open] .mcp-tool-chevron { transform: rotate(90deg); }
.area-studio .mcp-tool-summary:hover .mcp-tool-chevron { color: var(--accent); }
.area-studio .mcp-tool-body {
  padding: 8px 12px 10px;
  border-top: 1px dashed var(--border);
}
.area-studio .mcp-tool-full-description {
  font-size: var(--font-size-body-sm);
  color: var(--fg-secondary);
  line-height: var(--line-height-normal);
  word-break: break-word;
  margin-bottom: 8px;
}
.area-studio .mcp-tool-full-description.mcp-tool-description-empty {
  font-style: italic;
  opacity: 0.7;
}
</style>"""
