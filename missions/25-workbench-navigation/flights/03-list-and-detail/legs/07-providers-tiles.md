# Leg: providers-tiles (7)

**Status**: completed
**Flight**: [List and Detail](../flight.md)

## Objective

Render the Settings › Providers list as **tiles**, matching Built-in tools, instead of the
leg 5b table. This is the operator's decision at the DD14 checkpoint (2026-10-05): "It works
better for built-in tools than it does for providers, maybe make the providers tiles instead
of rows to match."

Everything else about the Providers page stays as leg 5b and the behavior-gate fix left it:
- the page header with "Add provider";
- the intro line;
- the editor opening **below** the list, in the page scaffold's item section;
- the breadcrumb close;
- DD8 focus;
- the empty state;
- "Used by" counts from data;
- every route.

Only the list's presentation changes, from table rows to a tile grid.

## Context

- **Flight decisions**
  - **DD7**, amended by this leg: items open below their list. The list's *form* for
    Providers changes from the reference spec §8.2 table to tiles.
  - **DD8:** the single focus rule after Cancel, close or delete.
  - **DD9:** `App.usage.providerAgents` and the agents list for "Used by".
- **Reference spec §8.2** draws Providers as a table (Name · Type · Status · Used by). After
  this leg the build deviates from it **by operator decision**. The Flight Director records
  that in the reference spec §13 as an operator-approved deviation, and in the flight DD7
  note. The Developer does not edit `missions/**`.
- **Built-in tools is the pattern to match** (`areas/admin/tools-grid.js:tileHtml`, about
  line 87):
  - `<div class="entity-tile tool-tile [active]" data-testid="tool-card" role="listitem">`;
  - a corner category badge (`.entity-tile-badge`);
  - the **name as the item link** (`<a class="entity-tile-name tool-tile-link" href>`, with
    `aria-current="page"` when open);
  - a description line, and the enable switch.

  The grid is `<div class="entity-tile-grid" role="list" aria-label="…">`, and the CSS is
  `.area-admin .tool-tile*` (`css/admin.css`, about lines 320–345). The open tool's tile
  keeps the selected wash (`.entity-tile.active`).
- **The current Providers list** is in `areas/admin/providers-table.js` (238 lines):
  - a DOM-built table;
  - `renderProvidersTable(listEl, state)`, idempotent through a signature, which re-renders
    the list section only and restores focus to the same provider's link;
  - `setProvidersSelection` in place;
  - `providerLinks` and `providerRowIndex` (the focus targets for DD8);
  - `sortedProviders`;
  - the `KNOWN_BADGE_TYPES` badge mapping, with `App.ui.badge({text, kind})`;
  - the zero-provider empty state (`providers-empty`, `providers-empty-add`).
- **Consumers in `areas/admin.js`:**
  - `renderProvidersTableNow` (about line 458);
  - `setProvidersSelection` (about lines 494 and 1144);
  - `focusProviderRowNear` (about line 590, through `App.admin.providerLinks`);
  - `focusClosedItem`'s `providerRowIndex` (about line 913);
  - `openItemLink` (about line 931, `a.providers-table-link`);
  - the comment at about line 263.
- **Pre-Flight-3 history.** `providers-grid.js` (deleted in leg 5b) rendered `<button>`
  tiles with the base URL as meta. **Do not restore it.** Its button-tile and `listbox`
  semantics were retired for the link-as-item model; the new tiles follow Built-in tools.

## Design (Flight Director)

### Module
`git mv areas/admin/providers-table.js areas/admin/providers-list.js`; a rename, so blame
follows. Rename the exports:

| Old | New |
|---|---|
| `renderProvidersTable` | `renderProvidersList` |
| `setProvidersSelection` | unchanged |
| `providerLinks` | unchanged |
| `providerRowIndex` | unchanged |
| `sortedProviders` | unchanged |

In `admin.js`, `renderProvidersTableNow` becomes `renderProvidersListNow`. Update the
`index.html` script tag and the cache-busting test's note.

### Tile anatomy (DOM-built through `App.ui.util.el`, as now; no HTML-string sink)

```
<p class="settings-intro">A provider is an account or server that runs models. …</p>
<div class="entity-tile-grid provider-tile-grid" role="list" aria-label="Providers">
  <div class="entity-tile provider-tile [active]" role="listitem" data-id="{id}">
    <App.ui.badge text={type} kind={type|unknown}> + extra class "provider-tile-badge"   (no wrapper span)
    <a class="entity-tile-name provider-tile-link" href="#settings/providers/{id}"
       data-testid="provider-card" data-id="{id}" title="{name}" [aria-current="page"]>{name}</a>
    <span class="provider-tile-url">{base_url}</span>   (omitted when empty)
    <span class="provider-tile-used">{n} agents | 1 agent | —</span>
  </div>
  …
</div>
```

The design review (cycle 1) settled four points in this anatomy:
- **No `.entity-tile-badge` wrapper.** That class is absolutely positioned with mono,
  uppercase, letter-spaced and padded type (`components.css:954-967`), which would
  double the badge's padding and bring back the uppercase eyebrow. Instead, the
  `App.ui.badge` element itself takes the class `provider-tile-badge`. `App.ui.badge` takes
  no extra class (`js/ui/feedback.js:30-45`), so call
  `node.classList.add('provider-tile-badge')` after creating it. **Do not extend
  `App.ui.badge`**: that is a control-library change with its own demo, inventory and
  contract-test obligations.
  - The class only positions the badge: `position:absolute; top:8px; right:8px`. The tile
    is already `position:relative` (`.entity-tile`).
  - The class must not set `background` or `color`; those belong to `.badge--{kind}`.
  - `.badge` has no `text-transform`, so the badge stays quiet lowercase in its own font
    with no override.
- **The URL line is not `.entity-tile-description`.** That class is a two-line clamp with
  `min-height:2.4em` (`components.css:934-943`). `.provider-tile-url` is a single line:
  `display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis`, in
  `--fg-secondary` on the tile surface.
- **The name link clears the badge.** Give `.provider-tile-link` a
  `max-width: calc(100% - 128px)`, provider-only. The widest badges are
  `openai-compatible` and `anthropic-plan`, about 105–115px plus the 8px offset. If the
  link rules are grouped with `.tool-tile-link`, keep this clearance out of the group:
  `.tool-tile-link`'s `max-width:100%` must not apply to the provider link.
- **The "Used by" line** (`.provider-tile-used`) is a single line in **`--fg-secondary`**,
  not `.entity-tile-meta`. `.entity-tile-meta` is `--fg-muted`, which fails AA on the active
  tile's wash in both themes: 4.14 dark and 4.07 light over `--bg`, lower over `--surface`.
- **`provider-tile-grid`** is the hook the geometry test and `_lists.providers_list` scope
  to.

- **Sort:** A–Z by name (`sortedProviders`), unchanged.
- **The name link is the item link**, as on tools. The testid `provider-card` stays on the
  link, so `_lists`' `self_named` row matching and the registry entry keep working. The tile
  itself is **not** a click target; a click on the tile's empty space does nothing, as on
  tools.
- **Badge:** the same `KNOWN_BADGE_TYPES` → `App.ui.badge` kind mapping as the table,
  positioned in the tile corner by `.provider-tile-badge` (see the anatomy notes above). Do not reintroduce the retired
  uppercase eyebrow; the prv spec asserts a quiet lowercase badge.
- **Base URL line:** shows `base_url` when non-empty, single-line with an ellipsis. It tells
  same-type providers apart, which answers checkpoint question 8 for this page. When empty,
  for example `anthropic-plan`, omit the line; never print "—" for it.
- **"Used by":** `usedByText` is unchanged: "—" until agents load, "1 agent", or
  "{n} agents".
- **Selection:** `setProvidersSelection` toggles `.active` on the open provider's tile and
  `aria-current="page"` on its link, in place, never by a rebuild. That is exactly the tool
  tile's treatment. The shared `.entity-tile.active` paints the wash
  `--accent-translucent-hover` (`components.css:921-925`). The forced-colours selected cue
  already covers it (`components.css:1649-1650`, `.entity-tile.active`), so no new
  forced-colours rule is needed.
- **Delete the table's forced-colours block** in `admin.css` (about lines 178–181) along
  with the table rules. It existed only for the table.
- **Idempotence and focus restore:** the existing signature rule stays, and the **row
  model now includes `base_url`**, so an edited URL rebuilds the tile and never goes stale.
  An unchanged data set keeps the DOM; a changed one rebuilds the grid children only and
  restores focus to the same provider's link.
- **Grid layout:** reuse `.entity-tile-grid`'s responsive columns. The review computed two
  columns at both 1440 and 1024 inside `.settings-list` (816px content at 1440); the
  `.settings-list .entity-tile-grid` override at `admin.css:126` applies automatically.
  Built-in tools behaves the same.
- **CSS for the tile:** a **separate `.area-admin .provider-tile` ruleset**, written in
  tokens only. Mirror `.tool-tile`'s quieted surface, its hover neutraliser
  (`:not(.active):hover`) and `cursor: default`. Mirror `.tool-tile-link`'s ink, hover
  underline and `:focus-visible` ring as well.
  - Do **not** group with `.tool-tile` in a way that carries `.tool-tile`'s
    `padding-bottom:36px`. That is the toggle's corner, and it stays tools-only.
  - Grouping only the link rules (`.tool-tile-link, .provider-tile-link`) is fine.
- **Loading, failed and empty states:** unchanged.
- **Nothing else in the list section changes:**
  - the item section;
  - `mountProviderItem`;
  - the breadcrumb;
  - Cancel and create, and DD8 focus, all of which go through `providerLinks`;
  - the dirty guard;
  - `openItemLink`, whose selector must change from `a.providers-table-link` to
    `a.provider-tile-link`.

### CSS
- **Delete** the `.area-admin .providers-table*` rules (`css/admin.css`, about lines
  133–170) and any `.providers-table-row.is-selected` or forced-colours rules that name the
  table.
- **Add** the `.provider-tile*` rules described above.
- `tests/test_token_definitions.py` must stay green.

### Tests (Developer)
- **`tests/browser/_lists.py`:**
  - `providers_table(page)` becomes **`providers_list(page)`**, the Providers grid
    (`role=list`, `aria-label="Providers"`), scoped inside `.settings-list` so it cannot
    collide with any other list; update its docstring;
  - update the module docstring's Providers paragraph (lines 75–90).
  - This is a helper rename: update **every** consumer listed under Files Affected.
- **Invert by renaming** (rename over delete-and-re-add, so blame shows the intent shift):
  - `test_flow_settings_items.py::test_providers_table_anatomy_and_used_by_counts` becomes
    `test_providers_tile_anatomy_and_used_by_counts`. It asserts:
    - the tile grid (`role=list`, label "Providers");
    - one tile per provider, A–Z;
    - each tile: the name link (`provider-card`, href, `data-id`), the lowercase type badge,
      the base URL line (present when set, absent when empty) and "Used by";
    - no `<table>` and no `th scope=row`.
  - `test_flow_provider_grid.py`'s anatomy assertions (lines 61–80: `th[scope="row"]`,
    `tbody tr`) are inverted to tile anatomy in the same way.
  - `tests/test_design_tokens_a11y.py::test_providers_table_pairs_pass_body_aa` and
    `test_providers_table_rules_consume_the_gated_pairs` become tile equivalents. Rename
    them; do not delete. They gate exactly the inks the tile paints:
    - the name (`--fg`) and the URL and "Used by" (`--fg-secondary`) on the tile surface
      (`--surface`);
    - the **active** tile's same inks on `--accent-translucent-hover`, which is the token
      `.entity-tile.active` actually paints.

    That fill *replaces* the tile's `--surface`, so the rgba composites over the page ground
    `--bg`. Gate it over **both** `--bg` and `--surface`, the worse ground, so a future
    ground change stays covered.
    - Use that token's own alphas, **0.16 dark and 0.13 light**, in a new dict. Do not use
      `_ACCENT_TRANSLUCENT_ALPHA` (0.10 and 0.08), which belongs to `--accent-translucent`.
    - The review computed the tightest pair as `--fg-secondary` on the wash over
      `--surface`: 5.49 dark and 6.01 light. Put the numbers in a one-line comment.
    - `--accent-translucent-hover` is listed in `_CONTRAST_EXEMPT` (about line 1268) as "no
      text pair of its own". Update that note to cite this consumer, the ground and the
      alphas.
    - The badge pairs are already gated by the existing `--badge-ink-*` tests.
  - In the same file, the forced-colours parametrized table (about lines 960–975) has two
    entries for `.area-admin .providers-table-row.is-selected > td` and `> th`. **Remove
    them**: the rule they pin is deleted, and the `.entity-tile.active` entries already
    cover the tile.
- **Rewrite rather than selector-swap:** `test_flow_settings_items.py`'s `_FORCED_PROBE_JS`
  and `test_forced_colors_keep_the_open_provider_and_tool_distinct` (about lines 690–720).
  They walk `tr.providers-table-row`, `tr.cells` and `.is-selected`; rewrite them onto the
  `.provider-tile` / `.active` shape.
- **Also in `test_flow_settings_items.py`, invert or re-point by renaming:**
  - `_row_texts` (about line 55);
  - the anatomy assertions at about lines 100–143 (`thead th`, `rowheader`,
    `columnheader`);
  - `test_long_provider_name_ellipsizes` (about lines 157–172; it uses
    `a.closest('table')` and the cell). It should now assert that the link ellipsizes
    inside the tile, the tile stays inside the list, and the link's right edge never
    crosses the badge's left edge;
  - the `_in_viewport("tr.providers-table-row.is-selected")` at about line 198;
  - the "table body only" and focus-survives-re-render tests (about lines 637–660);
  - every docstring that says "table".
- **`test_router_items.py:111-135`** (used at about line 579): the armed watch that asserts
  `table.providers-table tbody tr` never loses rows, and marks nodes with `__kept`. Rewrite
  it for the grid's `role=listitem` tiles, marking the tile nodes.
- **`test_flow_provider_grid.py`:** the module docstring (lines 1–14), and lines 61, 75–80
  and 126.
- **Mechanical updates** (`tbody tr` → the tile, `providers_table` → `providers_list`):
  - `test_router_items.py` (`_arm_providers_table_watch`, about line 111, becomes a
    tile-grid watch);
  - `test_store.py`;
  - `test_flow_provider_dirty_confirm.py`;
  - `test_flow_provider_setup.py`;
  - `test_flow_admin_openrouter.py`;
  - `test_lists_helper.py`;
  - any other hit of `providers-table` or `providers_table` under `tests/`.
- **Keep green with the selectors updated only**, never weakened:
  - `test_flow_settings_items.py`'s open-below, dirty-row-asks, breadcrumb-close-focus,
    create, Cancel and DD8 focus tests, and forced-colours;
  - every test from the behavior-gate fix.
- **New test:** at 1440×900 and 1024×768 with four providers, assert:
  - the grid lays out **two columns**: the first two tiles share a top, and the third
    starts below;
  - every tile's rect sits inside the list section;
  - the open provider's editor starts below the last tile's bottom.

  This is the "below the list" geometry, now for a grid.
- **Guards:**
  - `RETIRED_SELECTORS` (`tests/test_nav_helper.py`) keeps `entity-tile` retired **for
    tests**. Tests must reach tiles through `_lists`, `provider-card` or `data-id`, never
    the `entity-tile` class.
  - Do **not** add `providers-table` to the retired list; a class is not a testid.
  - The guard matches the string `entity-tile` with a left word boundary
    (`tests/test_nav_helper.py:320`). New tests must select by `.provider-tile`,
    `.provider-tile-grid`, `provider-card` or `data-id`, **never** `.entity-tile-grid` or
    `.entity-tile.active`.

### Docs (Developer)
- **`CLAUDE.md`, the "Settings item pages (M25 F3 L5b)" paragraph:**
  - Providers is now a tile grid (`providers-list.js`), matching Built-in tools, by the
    Flight 3 checkpoint operator decision;
  - the helper is `_lists.providers_list`;
  - drop the `th scope="row"` sentence.
- **`the_one/agents.md` line 148** (the leg 1 `_lists.py` paragraph), which names
  `providers_table(page)` and `<table aria-label="Providers">`.
- **`admin.js` comments** that say "table": about lines 220, 263, 302, 344, 441, 514, 589,
  646, 655, 888, 910, 1001 and 1035. Reword them all, not only line 263.
- **`the_one/agents.md`**, the Settings item pages bullets at about lines 1810–1815:
  - the module and API names;
  - the tile anatomy;
  - "replaced `providers-table.js`, which replaced `providers-grid.js`";
  - the operator decision.
- **`docs/ui-control-inventory.md`:** the "Data table (Providers…)" row now has no
  consumer. Update it to record that the table was retired in favour of tiles (Flight 3,
  operator checkpoint), keeping the row so the history stays visible. Add the provider tiles
  to the tile entry if the inventory has one.
- **`docs/ui-testid-registry.md`:**
  - the `provider-card` entry (line 196) becomes "the provider tile's name link (…
    `aria-current` on the open one's; the tile carries `.active`)";
  - the `editor-breadcrumb-link` entry (line 78) and the retired `back-provider-btn` entry
    (line 332) say "Providers table"; reword both;
  - update any other entry that mentions "Providers table".

## Acceptance Criteria

1. `#settings/providers` with providers shows the intro, then a **tile grid** labelled
   "Providers" (`role=list`):
   - one tile (`role=listitem`) per provider, A–Z;
   - each tile shows a corner lowercase type badge, the name as a link (`provider-card`),
     the base URL when set, and "Used by" ("—", "1 agent" or "{n} agents");
   - there is no `<table>` on the page.
2. Clicking a tile's name link opens the editor **below** the grid, at
   `#settings/providers/{id}`. That tile gets `.active`, and its link alone gets
   `aria-current="page"`. Focus goes to the editor's `h2` title, as before.
3. The selection updates in place: no grid rebuild on select or deselect. A store
   notification with unchanged data keeps the DOM, and a changed data set restores focus to
   the same provider's link.
4. DD8 focus is unchanged in behaviour:
   - the breadcrumb close focuses the closed provider's link;
   - delete focuses the nearest surviving provider's link, else "Add provider";
   - create-form Cancel and `~new` breadcrumb close focus the first provider link, else
     "Add provider".
5. Dirty editor plus another tile's link: the leave guard asks once, as before.
6. Zero providers: the empty state is unchanged (`providers-empty`).
7. Light and dark themes are legible.
   - The token a11y tests gate the tile pairs, including the active tile's `--fg` and
     `--fg-secondary` inks on `--accent-translucent-hover` over both `--bg` and `--surface`.
   - The "Used by" line is `--fg-secondary`.
   - The forced-colours selected cue applies to the open provider's tile.
   - The type badge renders lowercase: computed `text-transform: none`.
   - A long name never runs under the badge: at 1024, on an `openai-compatible` provider,
     the link's right edge is at or left of the badge's left edge.
8. At 1440×900 and 1024×768 the grid lays out two columns, every tile sits inside the list
   section, and the editor starts below the last tile.
9. Built-in tools is unchanged.
10. The gates are green:
    - `make lint` and `ruff format --check`;
    - `make test-unit`;
    - the **settings** lane and the **shared** lane (the router, store and helper tests live
      there);
    - the static guards (`tests/test_nav_helper.py`, `test_ui_library_source`, the token
      tests).
11. Docs updated as listed above.

## Verification Steps
- Run the gates above, one at a time, through `scripts/run-tests.sh` with
  `THE_ONE_TEST_NETNS=1` and `PYTHON=.venv/bin/python`. Use `TEST_TIMEOUT=3600` for the
  shared lane.
- Falsify the new geometry test once: for example, mount the editor above the grid, see it
  fail, then restore.
- Falsify one inverted anatomy assertion once: for example, revert the tile to a table, see
  it fail, then restore.
- Grep `the_one/`, `tests/`, `docs/`, `CLAUDE.md` and `scripts/` for `providers-table`,
  `providers_table` and `renderProvidersTable`. Only historical notes may remain.

## Edge Cases
- **A long provider name:** ellipsize inside the tile, with the full name in `title`. The
  existing `test_long_provider_name_ellipsizes` is re-pointed at the tile.
- **A long base URL:** single line with an ellipsis; it never widens the tile.
- **Unknown provider type:** badge kind `unknown`, as today.
- **Agents never loaded:** "Used by" reads "—".
- **A provider renamed in the editor:** after save the tile re-sorts. The signature changes,
  the grid rebuilds, and focus is restored to the same provider's link if it was there.
- **One provider:** a single tile, in a grid that does not stretch it across the width.
  Match the tools grid's column sizing.
- **A create (`~new`) open:** no tile is `.active`.

## Files Affected
- `the_one/interfaces/web/static/js/areas/admin/providers-table.js`, renamed to
  `providers-list.js` (rewritten list rendering)
- `the_one/interfaces/web/static/js/areas/admin.js`: renames and the `openItemLink`
  selector
- `the_one/interfaces/web/static/index.html`: the script tag
- `the_one/interfaces/web/static/css/admin.css`
- `tests/browser/_lists.py`
- `tests/browser/test_flow_settings_items.py`
- `tests/browser/test_flow_provider_grid.py`
- `tests/browser/test_router_items.py`
- `tests/browser/test_store.py`
- `tests/browser/test_flow_provider_dirty_confirm.py`
- `tests/browser/test_flow_provider_setup.py`
- `tests/browser/test_flow_admin_openrouter.py`
- `tests/browser/test_lists_helper.py`
- `tests/test_design_tokens_a11y.py`
- `tests/test_index_asset_cache_busting.py` (the note only)
- `CLAUDE.md`
- `the_one/agents.md`
- `docs/ui-control-inventory.md`
- `docs/ui-testid-registry.md`

**Not the Developer's** (the Flight Director, for Witnessed independence). Their
`providers-table.js` filename citations also go stale and are the Flight Director's to fix:
- `tests/behavior/*.md`: `system-provider-config`, `list-and-detail` steps 18 and 20,
  `shell-navigation-smoke` steps 8 and 9, `workbench-navigation` steps 5 and 10, and
  `save-preserves-config`;
- `missions/**`.

## Citation Audit
Verified 2026-10-05 against `95d87ef`:
- `providers-table.js` exports and lines:
  - `renderProvidersTable` (about line 135);
  - `setProvidersSelection` (about line 202);
  - `providerLinks` and `providerRowIndex` (about lines 217–230);
  - `KNOWN_BADGE_TYPES` and `INTRO` (lines 46–47).
- `admin.js`:
  - `renderProvidersTableNow` at 458;
  - `setProvidersSelection` at 494 and 1144;
  - `focusProviderRowNear` at 590;
  - `focusClosedItem` at 913;
  - `openItemLink` at 931.
- `tools-grid.js`:
  - `tileHtml` at 87;
  - the grid `role="list"` at 236.
- `admin.css` `.providers-table` rules at 133–168; `.tool-tile` at 324–345.
- `_lists.providers_table` at 325.
- The consumers listed above, found by grep.

## Post-Completion
Set the status to `landed`, update the flight log with a leg entry (gates, falsifications,
deviations), and signal `[LAND:leg]`. Do not commit; the Flight Director commits after
review.
