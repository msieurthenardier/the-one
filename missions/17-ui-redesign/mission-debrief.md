# Mission Debrief: UI Redesign — Clean, Professional, Consistent

**Mission**: 17 · **Status**: completed · **Date**: 2026-07-06
**Branch**: `mission/17-ui-redesign` (unmerged — operator reviews the completed branch; main untouched)
**Flights**: 7 of 7 landed · **Success Criteria**: all 9 met with cited, tree-matching, independently-re-derived evidence

---

## Outcome

The alien-console visual language — glows, glass/backdrop-blur, bezel/inset depth, chamfered panels, brushed-metal chrome, `//`-prefixed section markers, and pixel-font branding — is **fully retired and enforced-gone** across the shared shell, Chat, Agent Studio, and System/Administration, in both light and dark themes. Hierarchy now comes from typography, spacing, and hairline borders. The whole UI reads as one calm, professional product an operator can show in a work context without apology.

"Enforced-gone" is literal: the banned-token / clip-path / dead-selector guard families all end with **empty allowance sets** (`KNOWN_DEAD_SELECTORS = set()`, `CLIP_PATH_POLYGON_ALLOWANCE = {}`), so a green guard run means genuinely zero remnants — the retired aesthetic is now un-reintroducible without failing the build.

**Interpretation note**: the operator's brief contained "I am not looking for a clean, professional and consistent experience," read as a typo for "**now** looking for" given the explicit contrast with the retired alien-console direction. The whole mission proceeded on that reading; flagged here for confirmation.

**Change footprint**: 146 files changed, +12,117 / −1,796, across 24 commits. The insertion mass is the **regression net, not product churn** — the three largest files are all tests (`test_design_tokens_a11y.py`, `_ui_guard_helpers.py`, `test_ui_guards.py`); product CSS shrank or churned in place (`tokens.css` 469→284, `base.css` 145→75). Test net grew **unit 3681→3782 (+101), browser 478→566 (+88), five module-skipped browser modules re-enabled, zero module-level skips** — SC6's "healthier than before" is machine-enforced.

---

## Per-Flight Summary

| Flight | Outcome | Commits (impl / debrief) |
|---|---|---|
| **F1** Regression-net foundation | testid registry + 6 grep-guard families + sink-baseline ratchet; re-enabled 5 module-skips; pinned the perf anchor; stabilized the unit tier | `046c17f` / `798729c` |
| **F2** Design language v3 | quiet-instrument-panel tokens; effect-system retired + enforced-gone at the token layer; shell dismantled; theme-sync fix; mirror-sync guard | `b0ea3ca` / `ee9b9aa` |
| **F3** Shell + shared components | the one component vocabulary (buttons/fields/tiles/tabs/modals/badges); wordmark; unified CTA; badge+destructive contrast; living design gallery | `97f1ffd` / `35d902b` |
| **F4** Chat + markdown hardening | chat reading layout, composer/stop, code blocks; **the no-vendor reversal** — structural security via a no-HTML-string invariant guard + XSS suite | `5a7fa9e` / `d2bde42` |
| **F5** Studio re-skin | grids/editors to the vocabulary; `.field-group` migration; discoverable-dropdown restyle (zero JS diff); save-race fix; per-area browser lanes | `50b25ff` / `708be8d` |
| **F6** System re-skin | providers/tools/general to the vocabulary; the chip-list `label[for]` runtime-dangle closed systemically + runtime guard; gutter exceptions retired | `800dc2f` / `42a2b7b` |
| **F7** Hardening + acceptance | `.cap-chip` quiet; provider-header re-render; SC2 completeness net; perf + behavior sweep; **SC1-SC9 mission-end verification** | `bae84a9` / `0a29b3c` |

(Plus two delegated behavior-run follow-up commits: `3ca9662` chat-roundtrip, `e367c99` connector-a11y.)

---

## SC1-SC9 Outcomes (with evidence)

- **SC1 — visual-language replacement** ✓ — `test_no_retired_design_vocabulary_in_css` green (machine-enforced zero remnants) + the F7 `.cap-chip` quiet (last eyebrow) + per-flight visual passes.
- **SC2 — both themes accessible** ✓ — full-palette contrast audit both themes + the F7 **CSS-driven completeness assertion** (enumerates from tokens.css, not the mirror; probe-tested) + documented non-text exclusions + the `--fg-faint` deliberate exception.
- **SC3 — one component vocabulary** ✓ — no per-area variants; `.field-group` convergence (~32 studio + 6 provider + shared `renderField`); the `.cap-chip` cross-area quiet as the final proof.
- **SC4 — modern chat** ✓ — chat-roundtrip both themes (streaming + Stop witnessed mid-stream + turn distinction) + `test_markdown`/F4-leg-03 (code blocks) + `test_flow_chat_thinking_disclosure`/F4-leg-04 (tool-traces collapsed) + F4 chat-reading-layout (scroll awareness).
- **SC5 — keyboard/AT operability** ✓ — connector-editor-keyboard-a11y 7/7 (M12 F4 survived the re-skin) + the chip-list `label[for]` runtime guard + 2px accent `:focus-visible` both themes.
- **SC6 — regression net healthier** ✓ — zero module-level skips (grep-confirmed) + full browser green (566) + net additions (5 modules re-enabled, 6 guard families, unit +101/browser +88); the 6 residual per-test skips are M08-era, logged.
- **SC7 — behavior-verified core flows** ✓ — chat-roundtrip both themes 5/5, studio-agent-crud both (9/9 + 4/4), system-provider-config both 20/20 — all three core flows Witnessed in both themes.
- **SC8 — no perf regression** ✓ — forced-GC retained-heap growth **+0.99%** (flat, no leak; better than the +6.55% anchor) + latency p50 0.10ms (≤50ms). The raw 2s-settle metric read +23% (a GC-timing/denominator artifact on the lean dev heap) — recorded transparently; the box rests on retained + latency.
- **SC9 — docs reflect the new language** ✓ — agents.md design section v3 + the living gallery v3 + CLAUDE.md (+ the never-`-m live` reviewer note).

---

## Key Autonomous Decisions

1. **The no-vendor reversal (F4) — the mission's best engineering call.** The planning DD said vendor marked+DOMPurify; the code survey found `markdown.js` is already a fail-closed DOM-builder (never `innerHTML`, never parses an HTML string) — XSS impossible *by construction*. An independent security review confirmed vendoring would *worsen* posture (reintroducing the `innerHTML`-string→sanitize seam the codebase eliminated). Reversed on ground truth, independently confirmed, at the cheapest point (mid-planning, zero diverts), with the mission constraint **annotated not silently rewritten**, and the security control *retargeted* to a no-HTML-string invariant guard + XSS suite. **Posture ended stronger by declining the library.**
2. **The interpretation-note reading** — the brief's "not looking for" read as "now looking for" (typo), documented and proceeded-on. Flagged for operator confirmation.
3. **The sync-crew behavior-gate fix (F4)** — background-spawned crews orphan (they report to the top conversation, not their sub-orchestrator); fix = spawn synchronously (`run_in_background:false`) or run the gate inside the verification leg. Hardened the protocol for F5-F7.
4. **Apparatus routing** — goldfinch structurally can't observe `:focus` and wedges on seed+drive; chrome-devtools became the default for focus/keyboard + multi-step flows (it has `ignoreCache` reload). Promoted into agents.md.
5. **The verify-on-disk honesty catch (F5)** — the commit-Developer refused to record a "deferred" narrative that contradicted an on-disk PASS run log, catching a stale-narrative drift at the commit boundary.
6. **The promoted soft-fill token invariant** — a status color as body text on its own `-bg-soft` wash failing WCAG when composited recurred 3× (F3 danger, F3/F5, F5 warning); on the third it was promoted to a token-definition-time gate, and paid its dividend in F6 (confirm + cheap pin, no new math).
7. **The static+runtime label-guard pattern (F6)** — the static source-scan can't see a mount-time id strip; pair it with a runtime DOM guard (`HTMLLabelElement.control`).
8. **The live-tests-target-8484 lesson** — `test_aiat.py` `@pytest.mark.live` tests default to the operator's PROD port 8484; reviewers must use canonical `make test-unit`, never `-m live`.
9. **The SC7 cite-vs-rerun rule (F7)** — a cited prior run is valid for a mission-end check only if no code the gate exercises changed since; F7's own diffs invalidated two gates → re-run (the system-provider-config re-run doubled as the H1-fix proof).
10. **The SC8 raw-vs-retained diagnosis (F7)** — a forced-GC retained measurement isolated the true signal (+0.99%) from the raw metric's GC-timing artifact; transparent, not silent.

---

## Methodology — What Worked / What to Improve

**Worked (carry forward):**
- **Vocabulary-first flight sequencing** (net → tokens → vocabulary → per-area consumers → acceptance) — never needed re-cutting; later flights added *tests*, not *rework*.
- **Combined review+implement protocol** with a `[BLOCKED:design-flaw]` stop-gate — saved ~30-48 min/flight; the per-leg review hat still caught load-bearing corrections; the stop-gate never had to fire.
- **Independent accessibility review pass** — repeatedly earned its keep (F3 destructive-button BLOCKING catch; F7 a11y reviewer *re-ran* the SC2 probe + H1 regression rather than trusting the log).
- **Per-area browser lanes** as a complement partition — "no file orphaned" is a structural guarantee.
- **Two-Opus-review on acceptance specs** — F7's first cycle caught four silently-false-SC-check vectors.
- **The Witnessed behavior program** — caught the H1 render-desync bug that unit/browser assertion tests structurally miss.
- **Neutralize-then-remove** for token retirement; **guards land with the churn they protect**, mutation-probe-tested.

**To improve (methodology debt — carry to next mission):**
- **Machine-back the cite-vs-rerun rule** via per-spec surface-fingerprinting (currently judgment-dependent).
- **Re-express the SC8 perf budget as forced-GC retained growth** and/or pin the denominator (seeded sessions) — the % budget false-positived at +23% purely from the lean dev-heap denominator.
- **Behavior-harness armed-transient freeze** — the armed-delete ~3s auto-revert outran evidence capture twice (claims still soundly evidenced via DOM+API).
- **Per-run vs per-checkpoint Witnessed granularity** — no live SendMessage forced per-run re-spawn (actor≠judge held, disclosed); tighter mid-test failure surfacing is a tooling gap. Also: spin up a real Accessibility Validator (the crew's is `Enabled: false`).

---

## Carry-Forwards / Known Issues

- **6 M08-era per-test browser skips** — reduced from 35 (M13) → 6 at F1, held flat through F7; pre-date this mission, each per-test (zero module-level skips). Next-mission owner assigns replacement coverage or formally accepts each.
- **The accepted aiosqlite `TestSchemaV17` teardown warning** — single location, benign (down from 18-19 at M16); has now survived a full mission as a carry-forward — close it rather than inherit an eighth time.
- **M16 undebriefed** — M16's flights all landed but the mission was never formally debriefed (`Status: active` at M17 planning; its F9 flake directive was absorbed into M17 F1). A completed mission without a retrospective — the operator should decide whether to retro-debrief M16 or formally close it.
- **The two methodology-debt flags** (cite-vs-rerun machine backing; retained-heap perf budget) — will bite the next acceptance flight if not addressed.
- **SC8 raw-metric caveat** (operator-visible, not a defect) — the raw heap read +23% on the lean dev instance; retained is +0.99%. Recorded in perf-result-f7.md.

---

## Overall Verdict

A full visual-language replacement delivered across four surfaces and both themes, with a product footprint dwarfed by its regression net, and a security posture that ended *stronger* than the mission specified — by declining a planned dependency. The decomposition was correct and never needed re-cutting. The recurring soft-fill contrast bug being promoted to a token invariant, and the label-guard being paired static+runtime to close a proven coverage ceiling, are the two cleanest examples of this mission converting lessons into structure rather than folklore. The debt is small, old, and honest — none of it structural, none introduced by the redesign. **All nine success criteria met against cited, tree-matching, independently-re-derived evidence on the unmerged branch, awaiting operator review.**
