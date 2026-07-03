# Flight Debrief: Design Language v3 — Tokens and Type

**Date**: 2026-07-03
**Flight**: [Design Language v3 — Tokens and Type](flight.md)
**Status**: completed
**Duration**: 2026-07-03 (single day, 5 legs)
**Legs Completed**: 5 of 5 (no diverts)

## Outcome Assessment

### Objectives Achieved

The alien-console effect system is retired and **enforced-gone**: tokens.css 469→284 lines (quiet-instrument-panel ladders, both themes designed separately, zero hex adjustments from the design-review target table); base.css 145→75 (shell chrome/chamfer/mask physically removed); ~130 consumer declarations swept from all component CSS plus the api.py inline-CSS blind spot; `.section-title` `//` markers quieted CSS-wide; banned-token guard + backtick tripwire + mirror-sync guard all probe-tested; full-palette AA parametrization with the phantom fg-faint exception replaced by honest band tests; cross-tab theme sync ADDED (both directions, regression-tested); Makefile port plumbing + ownership check + port-suffixed pidfiles (the squatter class of false-success closed, plus an earned `make down` drain-race fix); agents.md v3 design section + apparatus doctrine; behavior gate `shell-navigation-smoke` 6/6 on the redesigned build.

### Mission Criteria Advanced

SC1/SC2/SC9 token-layer share delivered (mission-end verification pending); SC5 focus system pinned and verified intact after the sweep; SC6 net stayed green throughout (sinks 95/95 zero-diff).

## What Went Well

- **Neutralize-then-remove staging** — the standout reusable technique for token retirement: inert-but-valid values kept every suite green through the churn, made removals confirm-sameness, and the definition-name set diff protected consumer-less tokens the definitions test can't see.
- **Zero-adjustment palette**: pin ladder roles + AA gates at flight level, let the suite arbitrate hexes — the design-research table survived contact untouched.
- **Guards land with the churn they protect** (mirror-sync with the rewrite; banned-token once the tree was clean), all mutation-probe-tested; the **count-anchored self-expiring allowance** for the tab L-bracket forces its own cleanup at F3.
- **Premise corrections kept working**: the theme-listener "set propagates" claim (false — no listener existed) and the Playwright color-scheme prediction (inverted) were both caught by verify-ground-truth-first discipline.
- **Port-squatter chain**: anomaly → never-touch-operator decision → 8485 mission instance → ownership check + pidfile-per-port + drain-race fix, with mission docs updated in lockstep.
- Both close reviews (general + a11y) confirmed with zero issues; a11y reviewer independently verified no focus selector lost its indicator.

## What Could Be Improved

- **Foreseeable-consequence pass**: retiring the light theme's dark rail made the dark wordmark illegible — derivable at design time by asking "what sits ON surfaces whose colors change."
- **Flake-disposition protocol**: Leg 4's "one full run, 0 failures" AC forced a 12.5-min rerun over two isolated-green load flakes; verification legs should pre-specify the disposition rule.
- **Apparatus-premise probe for focus states**: goldfinch structurally cannot observe `:focus-visible` (`document.hasFocus()` always false); Leg 4 recovered via a CDP-driven page, but the flight assigned the evidence to an apparatus that could never produce it.
- **Grep-zero has blind spots**: inline CSS outside static/css (api.py), hardcoded JS text (ALL-CAPS titles), and extra `::before` eyebrow rules were caught only by design review or the visual pass — future re-skin legs enumerate non-CSS consumers explicitly.

## Deferred-Items Ledger (Flight 3 owns unless noted)

1. **Tab L-bracket chamfer** (`components.css:~764-769`) — delete with the tabs rebuild; the guard allowance fail-stales and must be removed together.
2. **Wordmark contrast — REQUIREMENT**: dark wordmark illegible on the light rail; new treatment designed in both themes, AA-verified.
3. **Badge on-color gating**: 10 measured sub-AA pairs (table in flight-log Decisions); retune fills/inks AND gate in the a11y suite.
4. **`--panel-radius*` alias migration**: ~33 refs (components 14, chat 7, admin 6, studio 6) → `--radius-*`, then delete aliases.
5. **Section-title semantics** + admin `-pf-*` mono-uppercase label treatment — component-vocabulary work; also the heading-weight design note (real `<h2>`s using .section-title lost visual weight).
6. **CTA state-split unification** (mission KI), **dead `connector-test-status` queries + `KNOWN_DEAD_SELECTORS` entry** — studio rebuild bundle (with F1's test re-simplification note).

## Apparatus-Doctrine Debt (F3's first docs-touching leg)

Missing from agents.md (printToPDF-as-default already landed): (a) progressive captureScreenshot wedge → **UnknownVizError escalation** (reload worsens, not clears); (b) **PDF fill-palette cross-check** technique (decompressed content streams) for theme evidence under print-CSS muting; (c) **goldfinch can never observe focus states** — use a CDP-driven page for `:focus-visible` proof (most urgent — every F4-6 leg needs focus evidence).

## Key Learnings

1. Neutralize-then-remove is the template for large-scale token retirement.
2. A flight that pins structure and delegates values to a suite-arbitrated leg gets zero-rework palettes.
3. Verify-ground-truth-first absorbs spec premise errors at near-zero cost.
4. `make`-managed multi-instance dev needs port-suffixed state files; ownership checks must fail on unresolvable pids.
5. Guard allowances should be count-anchored and self-expiring.

## Recommendations

1. **(F3)** Execute the deferred ledger above as first-class scope; badges fix-then-gate.
2. **(F3-6, per leg)** Guard churn at higher intensity: markup rewrites WILL diff testid registry and ratchet sink baseline DOWN — expected direction stated per leg, exact-diff output as worklist, JS diffs justified in flight logs.
3. **(F4)** `App.markdown` facade is the seam; vendor manifest + CI integrity + XSS suite land in the SAME leg as the swap; sink baseline ratchets down as sites consolidate to the sanitizer chokepoint.
4. **(All)** shell-navigation-smoke at every flight close (F2: 6/6); all verification on 8485; pixel snapshots advisory-regenerate at flight close; never run pytest as root (six root-owned baselines had to be deleted).
5. **(Watch)** Browser suite 12:33 with two load-timing flakes needing reruns; consider per-area lanes or root-causing before F4 grows the suite.

## Test Metrics

- **Unit**: 3721 passed / 10 skipped, 335s (debrief re-run confirms flight-log 327s) — flat vs F1 (3681/333s) despite +40 tests; 0 failures; flake-free.
- **Browser**: 533 / 0 / 6-skip, 12:33 (TEST_TIMEOUT=3600); +1 test vs F1; 2 isolated-green load flakes on the first run.
- **Guards/a11y slice**: 93 green. **Sinks**: 95/95 zero-diff. **Perf**: not re-measured (no runtime changes); F1 baseline stands.
