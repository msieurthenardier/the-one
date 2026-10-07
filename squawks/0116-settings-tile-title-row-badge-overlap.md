# Squawk 0116: Settings tile names truncate early (Providers) or can run under the badge (Built-in tools)

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-05
**Completed**: 2026-10-06

## Report

Both kinds of Settings tile place the name link and the badge differently. In both, the
badge is absolutely positioned in the tile's top-right corner. Neither tile lays its name and
badge out as one row.

- **Provider tiles** (M25 F3 leg 7). The name link always reserves 128px for the widest
  badge, `openai-compatible`. So a provider with a short badge (`mock`, `ollama`) still
  truncates its name about 80px before it needs to. At the 1024px minimum width, a
  three-column grid turns a moderately long name such as "Anthropic (work account)" into an
  ellipsis even though there is space beside a short badge.
- **Tool tiles.** The name link has `max-width: 100%`, and the category badge
  (`.entity-tile-badge`, absolute `top: 8px; right: 8px` in `components.css`) sits over the
  same row. A tool name long enough to reach the corner runs under the badge. The current
  built-in names are short enough that this does not show at the supported widths. But
  nothing prevents it, and a longer name or a narrower column would show the overlap.

The fix is mechanical: lay out the tile's title row as a flex row (name link
`min-width: 0; flex: 1 1 auto` with its ellipsis, badge `flex: none`). The name then takes
whatever width the actual badge leaves, and can never pass under it. The same rule serves
both tile kinds. This is a layout fix with no design decisions: the tile anatomy and the
badge stay as they are.

The leg 7 Reviewer and the Flight Director noticed this during the leg 7 review and the
behavior re-runs, outside leg 7's charter.

## Evidence

- `the_one/interfaces/web/static/css/admin.css`:
  - `.area-admin .provider-tile-link { max-width: calc(100% - 128px); }`, which is a fixed
    reserve, whatever the badge;
  - `.area-admin .provider-tile-badge { position: absolute; top: 8px; right: 8px; }`;
  - `.area-admin .tool-tile-link { max-width: 100%; }`.
- `the_one/interfaces/web/static/css/components.css`: `.entity-tile-badge` is absolute in the
  tile corner.
- The markup:
  - `the_one/interfaces/web/static/js/areas/admin/providers-list.js`: the link, then the badge
    via `App.ui.badge` plus `provider-tile-badge`;
  - `the_one/interfaces/web/static/js/areas/admin/tools-grid.js`: the
    `entity-tile-name tool-tile-link` anchor and the category badge.
- The background is in `missions/25-workbench-navigation/flights/03-list-and-detail/legs/07-providers-tiles.md`.
- **M25 F3 debrief.** The Architect and the Developer independently traced this to the two
  tile builders: `providers-list.js` builds tiles with the DOM, while `tools-grid.js` uses
  HTML strings and `innerHTML`.
  - The structural fix is an `App.ui` entity-tile factory that both grids consume. It needs
    design (a demo, an inventory row and contracts), so it is recommended for Flight 6 or
    the next mission.
  - This squawk stays the squawk-sized fix: a flex title row in both tile kinds. Fixing only
    one kind leaves the other wrong.

## Corrective Action

Both Settings tile kinds (`providers-list.js`, `tools-grid.js`) put the name and badge in a `.tile-title-row` flex row (`admin.css`): the name takes `flex: 1 1 auto; min-width: 0` with the ellipsis, the badge is `flex: none` and no longer absolutely positioned; the `calc(100% - 128px)` reserve is removed. `tests/test_design_tokens_a11y.py` pins the new rules.

Commit: pending the Flight 6 legs 1-3 commit.

## Verification

A browser test should seed one provider with a long name and a short badge (`mock`), and
one tool tile in a narrowed grid. It should then assert that each name link's right edge
sits left of its badge's left edge (bounding boxes), and that the provider name is not
truncated when the space beside the badge fits it. Both themes, at 1024px and 1440px.

## Sign-Off

**Reviewer**: pending the Flight 6 leg review
