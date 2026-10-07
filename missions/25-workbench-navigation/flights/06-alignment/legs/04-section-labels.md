# Leg: section-labels

**Status**: completed
**Flight**: [Alignment](../flight.md)

## Objective

Restyle every section label in the app with the operator's chosen **"Eyebrow with a
rule"** (option D, 2026-10-06, flight DD13). The labels are small, semibold, letter-spaced
uppercase text in `--fg-tertiary`, followed by a hairline that runs to the container's
edge. The rule applies to:
- the group labels in left-hand lists and navs (`App.ui.listPane` captions: Library and
  Chats; `App.ui.navGroups` captions: Settings);
- the section headers inside editors and Settings pages (`.section-title`).

## Context

- **What the operator reported:** "the headers on the left navigation aren't great. They
  are hard to distinguish from the menu items themselves… its all of them including in the
  configuration pages for the agents/providers/etc."
- **The options page:** `https://claude.ai/artifact/HBur9t8QP7nguottk6VKAr`. Its option D
  CSS is the reference for this leg:
  - **Group label (`.cap`):** `display: flex; align-items: center; gap: 8px; padding: 16px
    10px 6px` (the first group `padding-top: 10px`); `font-size: 10px; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase; color: var(--fg-tertiary)`.
    `::after { content: ""; flex: 1; height: 1px; background: var(--border) }`.
  - **Section header (`.sec`):** the same treatment with `gap: 10px; margin: 22px 0 10px`.
    The first one in its container has `margin-top: 0`.
- **The shared rules today** (`components.css`):
  - `.ui-list-pane-caption, .ui-nav-groups-caption` (about line 638): 11px medium
    `--fg-muted`, padding `var(--space-3) 10px var(--space-1)`;
  - `.section-title` (about line 408): the "quiet label (v3)" recipe, 12px medium
    `--fg-secondary`, `margin: 24px 0 12px`, `:first-child` `margin-top: 0`. Its comment
    says no uppercase and no letter-spacing;
  - `h2.section-title` (line 429) bumps real headings to `--font-size-h3`. The design
    review found it is dead in production: only the Design language demo
    (`typography-section.js`, about lines 94–147) wears it;
  - `.editor-section + .editor-section` (about line 1448) draws a `border-top` divider
    between editor sections, `padding-top: 16px`.
- **Where `.section-title` is used.** About 50 sites, across:
  - the editors: `provider-editor.js`, `tools-editor.js`, `mcp-server-editor.js`,
    `general-tab.js`, `self-configuration-tab.js`, `knowledge-section.js`,
    `connector-editor.js`;
  - `knowledge-settings-page.js`;
  - the Design language page sections.
- **The variants and overrides:**
  - `.danger-zone-title` (`components.css` about line 1456): `color: var(--status-danger)`;
  - `.section-title-row` (`admin.css` about line 611): a flex row of a `span.section-title`
    and an info icon (`tools-editor.js` about line 171, "Test connection");
  - `.editor-prompt-block .section-title` (`admin.css` about line 447);
  - `.telemetry-strip .section-title` (`admin.css` about line 774; a Design language
    gallery sample, `status-section.js`);
  - `kb-panel-title` (`knowledge-section.js` about line 749): a `div.section-title` whose
    text is the item's `path_or_url`;
  - `.area-studio .section-description` (`studio.css` about line 41): `margin-top: -4px`,
    sitting flush under a section title.
- **The reference spec's §3 group-label style** (11px medium `--fg-muted`) becomes an
  **operator-accepted deviation for SC8**. Record it in the flight log, and in leg 6's
  §15 and §13 sweep.
- **A library control changes.** The `listPane` and `navGroups` captions are `App.ui` CSS,
  so the `contracts` lane runs in both engines. The dev-mode Design language page shows
  the controls and must show the new style. The **published design system** (mission
  SC7: "the in-repo design reference and the published design system both describe the
  change") is updated at mission close by the Flight Director, not in this leg.
- **Contrast is already measured.** The design review computed `--fg-tertiary` at 6.02,
  5.66 and 5.37 (dark) and 6.32, 6.05 and 5.75 (light) on `--bg`, `--surface` and
  `--surface-elevated`: all above 4.5:1.

## Flight Director Decisions (design review cycle 1)

- **D1. The title-row rule runs past the info icon.** In `.section-title-row`, the rule
  sits on the **row's** `::after` (after the icon, `flex: 1`), and the row's
  `.section-title` suppresses its own `::after`. A flex-item span's own `::after` would
  collapse to zero width, and keeping the rule on the span would push the icon to the far
  edge.
- **D2. One rule per section boundary.** The `.editor-section + .editor-section` divider
  is removed **where the section opens with a section title** (a `.section-title` or a
  `.section-title-row` as its first child), because the title's rule now marks the
  boundary and the two lines would stack about 16px apart. A section with no leading
  title keeps its divider. `:has()` is acceptable (both engines support it), or a modifier
  class set by the builder. The vertical spacing between sections is unchanged.
- **D3. The danger zone stays red.** `.danger-zone-title` keeps `--status-danger` for
  its text, and its rule is `--status-danger` too. The rule is decorative, so it is not
  contrast-bearing.
- **D4. The provider models sub-labels stay quiet.** `.admin-pf-section-label`
  ("Running", "Available") and `.admin-pf-models-title` keep their current recipe: they
  are sub-labels inside one section, not section headers.
- **D5. The opt-out modifier is `.section-title--plain`.** It keeps the old quiet recipe
  (12px medium `--fg-secondary`, sentence case, no rule). Apply it to `kb-panel-title` (a
  file path in capitals would be unreadable) and to the telemetry strip's title. The
  inventory (step 1) may add others; each is listed in the flight log with its reason.
- **D6. Delete the dead `h2.section-title` bump.** Every `.section-title` takes one
  visual treatment whatever its element; `h2` keeps only its heading semantics. Rewrite
  the Design language typography demo to show the new recipe and the `--plain` opt-out,
  not the retired element split.

## Inputs

Legs 1a, 1b, 2 and 3's uncommitted work. This leg runs after leg 2, and edits shared CSS
that 1a and 1b may also touch (`admin.css`, `components.css`, `tools-editor.js`).

## Acceptance Criteria

- [ ] **The group labels.** `.ui-list-pane-caption` and `.ui-nav-groups-caption` render as
  option D, with the rule filling to the caption's content edge (the 10px right padding
  stays).
  - **The first visible group** has `padding-top: 10px`, and every later group's label has
    16px. Hidden groups must not count: a list whose first group is `hidden` still gives
    its first **visible** group 10px. Use a sibling rule (for example
    `.ui-list-pane-group:not([hidden]) ~ .ui-list-pane-group > .ui-list-pane-caption {
    padding-top: 16px }` over a 10px default), never `:first-of-type`.
  - **Long labels.** The text never wraps or truncates (`white-space: nowrap`, and the
    text does not shrink). The `::after` rule has `min-width: 0` and shrinks to zero
    first.
  - The ids, `aria-labelledby` wiring and the caption's left alignment with the item text
    are unchanged.
  - **Probe** (both engines, `contracts` lane, `test_ui_*`): computed font-size 10px,
    weight 600, `text-transform: uppercase`, letter-spacing 0.8px within 0.05px, and the
    colour equal to `--fg-tertiary`. A visible `::after` rule with height 1px, a width
    above 0, and the colour equal to `--border`. The first-visible-group padding, with
    the first group hidden.
- [ ] **The section headers.**
  - `.section-title` renders as option D: `display: flex; align-items: center; gap: 10px;
    margin: 22px 0 10px`, `:first-child` `margin-top: 0`, the same type, and the `::after`
    rule. `h2.section-title` takes the same treatment (D6).
  - **The variants:**
    - `.danger-zone-title`: the text and the rule in `--status-danger` (D3);
    - `.section-title-row`: the rule on the row, after the info icon (D1), and the icon
      keeps its place beside the text;
    - `.editor-prompt-block` stays laid out correctly;
    - `.section-title--plain`: the old quiet recipe, no rule (D5).
  - **The divider** (D2): no editor section shows a divider and a title rule together.
  - **`.section-description`** still sits visibly attached under its title (a 4–6px gap),
    adjusted from `margin-top: -4px` if needed.
  - **Probe** (browser test in the `settings` lane):
    - a provider editor section header and a Built-in tools editor section header have
      the computed values above;
    - the danger-zone title's text and rule colours are `--status-danger`;
    - the Built-in tools "Test connection" row: the rule's left edge is right of the info
      icon's right edge;
    - the second editor section has no `border-top`.
- [ ] **Uses that are not section headers.** The inventory lists every `.section-title`
  site as a header or not. Each non-header (a single control's label, inline text, or
  dynamic text such as a path) is restyled or given `.section-title--plain`. The list and
  the decisions go in the flight log.
- [ ] **Contrast.** The `--fg-tertiary` pairs above are audited in
  `tests/test_design_tokens_a11y.py` (add them if they are not already there).
- [ ] **The Design language page** shows the new style in its typography and controls
  sections (D6). Update any copy there that describes the "quiet label" recipe.
- [ ] **Docs:**
  - `the_one/agents.md`: "Section titles — quiet treatment" (about lines 1744 and
    1821–1825) describes the new label recipe, noting that the retired eyebrow is back
    with a rule, by operator decision, plus the `--plain` opt-out and D2;
  - the `components.css` comments (about line 407, the caption block and the editor
    section) and `admin.css` (about lines 209–211) match;
  - `docs/ui-control-inventory.md`: the `listPane` and `navGroups` rows describe the
    caption style if they describe it at all.
- [ ] **The pinned tests updated in place,** each change noted in the flight log:
  - `tests/browser/test_ui_nav_groups_contract.py` (about line 310), which expects
    `["11px", "500", fg_muted, "12px 10px 4px"]`, and the pitch assertion after it;
  - `tests/test_design_tokens_a11y.py` (about lines 904–905), which expects
    `color: var(--fg-muted)` in `.ui-nav-groups-caption`;
  - any list-pane caption pin, and any other test that pins the caption or the
    section-title computed style (grep for `section-title` and `caption` in `tests/`).
- [ ] **Gates:**
  - the static guards: `test_ui_guards.py`, `test_token_definitions.py`,
    `test_design_tokens_a11y.py`;
  - `TEST_TIMEOUT=3000 make test-unit`;
  - the `contracts` lane (`THE_ONE_REQUIRE_WEBKIT=1`), and the `settings`, `agents`,
    `library` and `chats` lanes;
  - `shared` (`TEST_TIMEOUT=3600`).

  All with `THE_ONE_TEST_NETNS=1`.

## Verification Steps

- The probes above, then the lanes in the background.
- A screenshot pass in both themes of the Settings nav, the Library list, the Chats list,
  a provider editor (with its danger zone), the Built-in tools editor (the "Test
  connection" row) and an agent editor tab. These are flight-log evidence only, never
  committed. The pass checks that no two lines stack, the rule never runs into a control,
  and nothing wraps oddly at 1024 wide.

## Implementation Guidance

1. **Inventory every `.section-title` site:** header or not, the variant classes, and
   which editor sections open with a title (D2).
2. **Change the shared CSS:** the caption rule, then `.section-title`, the variants, the
   opt-out and the divider.
3. **Apply `.section-title--plain`** where the inventory needs it.
4. **The probes, the pinned tests and the contrast audit.**
5. **The Design language page and the docs.**
6. **The lanes;** then mark the leg `landed` and signal `[LAND:leg]`.

## Edge Cases

- **A very long group label** (for example "Defaults for agents" in a 260px nav): the
  label text never truncates, and the rule shrinks to zero rather than wrapping the
  label.
- **Chats recency groups** (Today, Yesterday, …) use the same `listPane` caption, so they
  change too. That is intended: the operator said "all of them".
- **A group whose list is empty** (`ui-list-pane-group-empty`) keeps its empty line under
  the new label.
- **A filtered Library list** hides groups, so the first visible group can change while
  the operator types; its padding follows (the sibling rule).
- **Forced-colors mode:** the rule is a background colour. Under `forced-colors: active`
  it may vanish, which is acceptable because the label text remains.

## Files Affected

- `the_one/interfaces/web/static/css/components.css` (captions, `.section-title`,
  variants, the editor-section divider), `admin.css`, `studio.css` (overrides as needed).
- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js` (the opt-out), and
  any other JS the inventory names.
- The Design language page sections (`areas/admin/design-language/typography-section.js`,
  `status-section.js`, and any other that describes the recipe).
- Tests: the `contracts` lane probe (`test_ui_*`), a `settings` lane probe,
  `tests/test_design_tokens_a11y.py`, and the existing pins.
- `the_one/agents.md`, `docs/ui-control-inventory.md`; the flight log.

## Citation Audit

Checked on 2026-10-06 in the working tree (before legs 1a–2 land; line numbers may drift
by a few lines):
- **`components.css`:** `.section-title` (line 408), `h2.section-title` (line 429), the
  captions (line 638), `.editor-section + .editor-section` (line 1448),
  `.danger-zone-title` (line 1456).
- **`admin.css`:** `.admin-pf-models-title` (line 211), `.admin-pf-section-label` (line
  221), `.section-title-row` (line 611), `.telemetry-strip .section-title` (line 774).
- **`studio.css`:** `.section-description` (line 41).
- **JS:** `tools-editor.js` "Test connection" row (line 171), `knowledge-section.js`
  `_panelTitle` (line 749), `list-pane.js` group construction (line 572),
  `nav-groups.js` group construction (line 68).
- **Tests:** `test_ui_nav_groups_contract.py` (line 310), `test_design_tokens_a11y.py`
  (lines 904–905).

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
