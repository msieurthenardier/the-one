# Flight Debrief: System / Admin Re-skin

**Date**: 2026-07-06
**Flight**: [System / Admin Re-skin](flight.md)
**Status**: completed
**Legs Completed**: 5 of 5

## Outcome Assessment

### Objectives Achieved

The System area (General / LLM Providers / Built-in Tools) — the mission's LAST surface — renders the v3 quiet vocabulary in both themes. The 6 provider-editor rows + the shared renderField emitter migrated to `.field-group` with label-association; the badge eyebrows quieted; the `.area-admin` gutter exceptions retired; the `.section-title` overload resolved (documented); and — the flight's strongest engineering — the F5 chip-list `label[for]` runtime-dangle **closed systemically** (admin + all studio consumers) with a runtime DOM guard. Product-code touch was small and surgical (admin.css + 4 JS editors + tools-form-helpers); the bulk of the diff is artifacts + the SC7 behavior spec/run log + two test files. Commit `800dc2f`.

### Mission Criteria Advanced

SC1 (system surfaces to vocabulary, eyebrows quieted — one `.cap-chip` cross-area survivor → F7), SC3 (system consumes the vocabulary, rows migrated, gutter retired, section-title documented), SC5 (editors keyboard-operable + the chip-list `label[for]` runtime-dangle CLOSED systemically + a runtime guard), SC7 (system-provider-config gate PASSED both themes 20/20 — the green system down-payment). F6 shares delivered; mission-end verification at F7.

## What Went Well

- **The chip-list `label[for]` systemic fix — the F5 carry-forward genuinely CLOSED, not deferred a third time.** Root cause correctly diagnosed as a *runtime* mount-time strip (a `<div>` placeholder isn't labelable; `mountChipListEditors` replaces it via `outerHTML=`, stripping the id) — not a source defect. The fix (`options.controlId` landing the id on the real focusable `.chip-list-input`) targets the one labelable element; all four mcp-server-editor sites (2 mount + 2 cancel/revert re-mount) repointed, placeholder-div ids dropped (safe — post-mount selectors key on `[data-field]`). **One shared-emitter fix covered admin tools + every studio chip-list consumer at once.**
- **The runtime DOM guard as the durable companion pattern** (F5-debrief lesson realized): `test_flow_chiplist_label_resolver.py` asserts resolution through `HTMLLabelElement.control` (null for non-labelable/missing) — closing exactly the coverage ceiling the static source-scan guard provably cannot reach. **Promote to methodology: static source-scan for source-visible cases + a runtime DOM guard for the mount-transform (`outerHTML`/re-mount) cases.**
- **The composite-gate-already-covered simplification — the promoted token invariant paying its dividend.** Both admin danger-on-soft-fill surfaces consume the exact `--status-danger`/`--status-danger-bg-soft` pair already gated once at the token level; the legs CONFIRMED + added a cheap source-grep pin with ZERO new `_alpha_composite` math. Gate-once-at-definition stopped per-surface rediscovery — exactly its purpose. Correctly inverted rigor: maximum on the shared emitter, a cheap pin on the composite surfaces.
- **The cross-area shared-helper `renderField` migration** (highest blast radius): the 2-path assessment (exactly 2 call sites) + the marker-class invariants (`.tools-editor-field`/`data-field-name` for `renderFieldErrors` AND `applyShowIf`; `.admin-pf-*` for provider show/hide) were load-bearing, not defensive — a bare rename would have silently broken 422 rendering + conditional visibility in BOTH lanes, invisible to any single-lane run. Both lanes re-verified green.
- **First flight since F2 with ZERO browser flakes** — the sequential-lane discipline (one browser group at a time) ran clean where F3/F4/F5 each carried a load-timing flake.

## What Could Be Improved

- **The H1-header/Name-field desync** — the SC7 behavior gate's independent Validator caught a real product bug at CP7 (both themes): after editing + saving a provider Name, the editor H1 heading doesn't re-render to the new name while the field persists it. Theme-independent → likely pre-existing, but the `.field-group` migration touched the editor render path, so **F7 must confirm it's pre-existing (git-bisect-grade) before closing.** Exactly the live-render class that unit/browser-assertion tests miss and a Witnessed run catches.
- **The `.cap-chip` cross-area eyebrow survivor** — the one remaining un-quieted eyebrow, correctly NOT quieted here: `renderCapabilityChips` is shared (`window.App.admin.renderCapabilityChips`, consumed by studio's model picker), so an area-scoped quiet would split the vocabulary into a per-area variant SC3 forbids. → F7 as a single un-scoped quiet, both lanes re-verified.
- **Per-leg self-reported unit counts are fragile** — Leg 3's 3822 was a mis-record (collected-not-selected, or a marker set that didn't exclude `requires_bwrap`), reconciled to the reproducible 3781. Treat per-leg counts as indicative; only a clean-tree verification run is authoritative.
- **The behavior crew's Accessibility Validator is disabled** (`Enabled: false`) — the base Validator judged the `[a11y]` checkpoints adequately here, but F7's a11y audit should spin up a real Accessibility Validator, not rely on the base.

## Deviations and Lessons Learned

| Item | Disposition | Standardize? |
|------|-------------|--------------|
| Badge quiet via OVERRIDE (not deletion) | Shared `.entity-tile-badge` base outranks-loses to `.area-admin` (0,2,0 > 0,1,0); a bare deletion is a no-op | Yes — when quieting an area-scoped element whose shared base declares the treatment, override with explicit values; keep area-scoped to avoid cross-area blast radius |
| `test_aiat.py` "4 failures" | `@pytest.mark.live` tests EXCLUDED from canonical `make test-unit`; default `THE_ONE_TEST_URL`→localhost:8484 (operator PROD); failed for lack of a live agent, F6-independent | Yes — **reviewers use canonical `make test-unit`, NEVER `-m live`** (it targets the operator's prod 8484). Add to CLAUDE.md testing notes |
| Static label-guard can't see mount-time strips | Paired with a runtime DOM guard | Yes — the static+runtime guard pairing is the pattern for label associations surviving `outerHTML`/re-mount |

## Key Learnings

1. Close a carry-forward at the shared source, not per-surface — one `renderChipListEditor` fix covered admin + every studio consumer.
2. The static-source guard has a structural coverage ceiling (mount-time transforms); pair it with a runtime DOM guard.
3. Gate-once-at-definition (the promoted token invariant) eliminates per-surface contrast rediscovery — confirm consumption with a cheap grep pin, don't re-derive the math.
4. Calibrate rigor to blast radius: maximum on a shared emitter, a cheap pin on a surface consuming an already-proven token.
5. A Witnessed behavior gate catches live-render bugs (the H1 desync) that assertion-level tests structurally miss.

## Recommendations (Flight 7 — the acceptance flight)

1. **`.cap-chip` un-scoped quiet** (SC1 closer) — single un-scoped quiet covering admin Ollama panel + studio model picker; re-verify both lanes both themes. Do NOT area-scope (SC3).
2. **H1-desync fix** — root-cause the editor save/re-render path; confirm pre-existing (git-bisect-grade) first; add a regression check.
3. **SC6** — re-enable the five module-skipped browser modules (+ the two F1-timeboxed unexplained-hang modules); zero module-level skips, or documented equivalent coverage.
4. **SC8** — the perf re-run via `App.perf` heap/interaction vs the pinned F1 baseline — the mission's whole CSS/markup churn lands its perf verdict here (a real measurement leg, not a spot-check).
5. **Full SC1-SC9 mission-end verification** — the three SC7 behavior gates re-confirmed both themes (chat round-trip + studio-agent-crud [F5 green] + system-provider-config [F6 green]); SC5 connector-a11y [F5 7/7]; SC2 full-palette contrast; SC9 docs (agents.md design section, gallery, CLAUDE.md). THIS is where the SC boxes get checked with cited evidence.
6. **Budget the behavior gates generously** — F6's SC7 ran ~73 min; F7's 3 flows × 2 themes is a multi-hour synchronous commitment. Sequence them (never overlap on 8485). Spin up a real Accessibility Validator.

## Test Metrics (F1 → F6)

| Metric | F1 | F2 | F3 | F4 | F5 | F6 |
|---|---|---|---|---|---|---|
| Unit passed | 3681 | 3721 | 3749 | 3759 | 3779 | 3781 |
| Unit wall | 5:33 | 5:35 | 5:31 | 5:34 | 5:30 | 5:34 |
| Browser (full) | 532 | 533 | 533/1fl | 562/1fl | 562/1fl | 565/0fl |
| Browser wall | ~12.5m | 12:33 | ~12.5m | 13:08 | 12:33 | 12:56 |

Unit +2 (the two composite source-grep pins; the chip-list runtime guard is a browser test). Unit wall flat in the 5:30-5:35 band held since F1 despite +100 tests mission-to-date. **First zero-flake browser run since F2.** Per-area lanes: system 92/2:20, studio 252/7:28, chat 49/1:37. SC7 system gate PASSED both themes 20/20. Perf (SC8) not re-measured — CSS/markup-led; F1 baseline stands; SC8 is the F7 gate.
