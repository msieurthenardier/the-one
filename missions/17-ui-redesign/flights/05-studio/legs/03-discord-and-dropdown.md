# Leg: discord-and-dropdown

**Status**: completed
**Flight**: [Studio Re-skin](../flight.md)

## Objective

Re-skin connector-form-discord.js (8 `.field-row`→`.field-group`) and quiet the discoverable-dropdown's alien group-header typography — with its WAI-listbox keyboard a11y PRESERVED verbatim and a composite-a11y gate for the dropdown focus/hover wash. Split from connector-editor-core to isolate the a11y-sensitive dropdown work.

## Scope (flight DDs authoritative)

- connector-form-discord.js: 8 `.field-row`→`.field-group` with full label-association (reuse Leg 2's shared `.field-group-label` primitive in components.css for info-icon fields); consume the vocabulary; keep testids.
- **discoverable-dropdown**: the ONE alien remnant is the group-header typography (mono + uppercase + letter-spacing, studio.css `.discoverable-dropdown-group-header` ~:1546-1552) — quiet to the vocabulary label style (drop mono/uppercase/letter-spacing). **PRESERVE VERBATIM** the WAI-listbox keyboard a11y: `role="combobox"`/`aria-autocomplete`/`aria-haspopup`/`aria-controls`/`aria-activedescendant` on the input, `role="listbox"`/`role="option"`/`aria-selected`, ArrowUp/Down/Enter/Escape/Tab handlers, roving `aria-activedescendant` (discoverable-dropdown.js:181-194,503-605). CSS/typography ONLY. Grep-confirm the roles/handlers intact at leg end. Keep the stale-entry line-through+opacity treatment.
- Composite-a11y gate (both themes): the dropdown focus/hover wash — `--fg` text on `--accent-translucent` (studio.css:1565). `_alpha_composite` rgba-over-one-known-surface; mirror in lockstep if a new token.

## Acceptance Criteria

- [x] discord-form `.field-row`→`.field-group` with label-association (guards green); both themes (CDP visual + focus). **4 real render sites** (not 8 — grep-inflated, same as Legs 1-2): Bot status, Additional Config, Bot Token, Invite link — all migrated to stacked `.field-group`; the 3 info-icon rows reuse Leg 2's `.field-group-label`; Bot Token's info-icon `<button>` un-nested from inside its `<label>` (a11y fix).
- [x] discoverable-dropdown group-header quieted (no mono/uppercase/letter-spacing); vocabulary surface + hairline + shadow-popover confirmed (CDP computed style: Geist font, `text-transform: none`, `letter-spacing: normal`, weight 500, both themes)
- [x] discoverable-dropdown WAI-listbox a11y UNCHANGED — grep-confirmed roles (combobox/listbox/option) + keyboard handlers (Arrow/Enter/Escape/Tab) intact; the JS file has ZERO git diff; `test_flow_studio_connector_discoverable_dropdown.py` green
- [x] dropdown-wash composite gate green both themes (`test_discoverable_dropdown_hover_item_text_passes_body_aa`: `--fg` on `--accent-translucent` over `--surface`)
- [x] connector/discord browser slice green via run-tests.sh (26); unit lane green (3779 passed / 0 failed); ruff clean; label-association guards green; sink baseline honest (unchanged — class-string edits only, no innerHTML→createElement)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
