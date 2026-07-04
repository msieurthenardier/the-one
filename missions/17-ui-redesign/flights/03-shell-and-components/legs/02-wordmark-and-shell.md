# Leg: wordmark-and-shell

**Status**: completed
**Flight**: [Shell and Shared Components](../flight.md)

## Objective

Replace the pixel-font banner with the set-type wordmark + compact mark (flight DD "Wordmark"), restyle topbar/sidebar nav to the vocabulary, and verify AA in both themes.

## Scope (flight DDs authoritative)

- `app.js:66` region: banner `<img>` → text wordmark ("GleepGlorp AI", Geist semibold, h3-tier, `--fg`) + optional `topbar-icon-24.png` compact mark (20-24px, `aria-hidden` with the text carrying the name). Keep the topbar landmark contract (`renderTopBar()` wiring, skip-link, aria) intact.
- **Guard delta 1**: the banner innerHTML string pinned at `test_ui_guards.py:89` updates with the app.js change (same leg).
- Topbar/sidebar nav restyle: picker buttons + section-nav to vocabulary (quiet fills, `aria-current` styling via accent text/border per the conventions; no new effects). Keep all testids.
- Both themes AA: wordmark fg on both rails (by construction `--fg`×`--nav-bg` is suite-covered — cite the pair); visual evidence both themes.

## Acceptance Criteria

- [x] `grep -rn "gleepglorp_banner" the_one/` → only brand-asset file itself (no JS/HTML refs); wordmark renders both themes (evidence)
- [x] Guard/token/a11y slice green; sink guard green with the updated pinned string
- [x] Keyboard: picker buttons focus-visible per pinned form [a11y gate]
- [x] `make test-unit` green; browser slice green (`test_flow_picker.py test_flow_hash_routing.py test_theme_toggle_cleanup.py`)
- [x] ruff clean; registry unchanged (no testid changes expected)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
