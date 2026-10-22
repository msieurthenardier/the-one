# ruff: noqa: E501  (verbatim CSS fixture)
"""The legacy studio Tools-tab CSS, frozen as a test fixture (M31 F2 L08b).

The agent Tools tab now uses App.ui.groupTile/toolRow/toggle, so the studio rules
that styled the old markup (.tools-category-tile*, .tool-tile*, .tool-switch pill,
.mcp-source-tile-toggle, .mcp-tool-text) were deleted from studio.css. The library
contract tests (test_ui_tile_contract.py) still compare the library controls to the
old look computed from the old markup, so the rules live here, verbatim, scoped
under ``.area-studio`` as they were. Not product CSS: never loaded by the app.
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

# The one studio rule the chip-list contract compares a locked chip against.
LEGACY_LOCKED_CHIP_CSS = """<style>
.area-studio .tool-row-overrides .chip[data-locked] { background: var(--surface-elevated); opacity: 0.7; cursor: default; }
</style>"""
