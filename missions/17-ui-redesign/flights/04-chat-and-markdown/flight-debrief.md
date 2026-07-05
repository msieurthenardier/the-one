# Flight Debrief: Chat Re-skin + Markdown Hardening

**Date**: 2026-07-05
**Flight**: [Chat Re-skin + Markdown Hardening](flight.md)
**Status**: completed
**Duration**: 2026-07-04 → 2026-07-05 (4 legs)
**Legs Completed**: 4 of 4

## Outcome Assessment

### Objectives Achieved

The Chat area is re-skinned to the quiet vocabulary (tinted user turns replacing the loud full-accent bubble, agent prose on a reading column, composer/stop/code-blocks/disclosures to the vocabulary — 509 chat elements/theme swept, 0 alien remnants) AND the mission's markdown-security intent is delivered **structurally without vendoring any library**: `markdown.js` hardened, its no-HTML-string invariant locked by a probe-tested guard, and a +29-case XSS regression suite landed. The `App.markdown` facade (parse→AST/19 NodeTypes, render→DocumentFragment) is preserved verbatim; `test_markdown.py` stayed green throughout. shell-navigation-smoke re-passed 6/6 after the re-skin.

### Mission Criteria Advanced

SC1 (chat surface to vocabulary, 0 remnants), SC3 (chat consumes the vocabulary), SC4 (reading layout + first-class streaming stop + legible markdown/code + tool traces out of flow), SC5 (composer/stop/disclosures keyboard-operable, CDP-evidenced) — F4 shares delivered; mission-end verification pending.

## What Went Well

- **The no-vendor mission-level reversal — the flight's centerpiece and a model Flight-Director call.** The planning DD (vendor marked+DOMPurify) rested on a false premise: the survey found `markdown.js` is already a fail-closed DOM-builder that never parses an untrusted HTML string, so XSS is impossible *by construction*. An independent security-architect review confirmed vendoring would *worsen* posture (forcing an HTML-string→sanitize→fragment seam — reintroducing the `innerHTML`-class operation the codebase deliberately eliminated — and breaking the streaming partial-buffer contract) for a CommonMark-completeness gain that is UI-polish, not an impediment. The reversal was made at the cheapest point (mid-**planning**, as a pre-flight prerequisite — so the flight executed with zero diverts), independently confirmed, fully documented, and the mission constraint was **annotated as commentary rather than silently rewritten**. Security posture is now *stronger* than the mission planned for.
- **CI-integrity retargeted to a durable structural lock.** Vendor hash-pinning ("the file we audited ships") had no file to pin, so it was retargeted to a no-HTML-string invariant guard ("the property we rely on can't silently erode") — a tighter control that survives refactors and fires on the precise regression (a reintroduced `innerHTML` seam) that reopens the threat class. Probe-tested both directions. The strongest single artifact in the flight.
- **Composited-a11y-gate discipline (F3 lesson) executed precisely**: every text-bearing wash got an `_alpha_composite`-reconstructed body-AA gate in both themes (3 new + 3 re-used), each authored as rgba-over-a-single-known-surface so the one-layer helper can reconstruct it; solids deliberately NOT composite-gated (fg-ladder sweep covers them). The `.msg.user.api` inheritance regression (saturated cyan bubble inheriting near-white `--fg` → ~1.2:1 dark) was caught and pinned — exactly the second-order hazard leg-time gating exists to catch.
- **Facade-preservation instinct**: the copy-button re-skin was kept CSS-only precisely so `renderCodeBlock`'s DOM-built markup — and the invariant guard + facade net — stayed untouched. The re-skin routed *around* the load-bearing subsystem, not through it.
- **z-index regression** (shorter composer slid the queued-chip × under the telemetry HUD) root-caused by revert-bisection and fixed by principle (interactive region stacks above passive readout), not pixel-tuning.

## What Could Be Improved

- **The delegated behavior-run orphaned — the sharpest process defect.** F4 planned to delegate the chat-roundtrip Witnessed RUN "at flight close" as a background hand-off. The first delegation orphaned: **background-spawned Executor/Validator report to the top conversation, not back to their sub-orchestrator**, which had ended its turn waiting. Diagnosis + fix: spawn behavior crew **synchronously (`run_in_background: false`)** so each report returns as the tool result, OR run the gate as a synchronous sub-orchestrator *inside the verification leg* (the F3 pattern that worked). The chat-roundtrip run was ultimately deferred to F7's SC7 gate — safe here (the a11y reviewer independently drove a live streaming turn; the leg-4 dual-theme visual pass evidenced the mock done-state markup + live stop), but the orphaning is a real process defect to close.
- **Deferred obligations F7 must not lose**: the chat-roundtrip Witnessed run (spec authored + active) → F7 SC7; the "jump to latest when scrolled up" affordance (smart auto-scroll already existed; the jump-pill not built) — SC4 "scroll-position awareness" partially met, F7 confirms if it matters for acceptance.
- **Sink-ratchet prediction miss (honest)**: the flight predicted L2/L3 would ratchet the sink baseline DOWN; it didn't (the re-skin was CSS-led — no static-innerHTML→createElement migration happened), so the baseline honestly held at 92. The "migrate static template sinks while re-skinning" opportunity remains available for F5-6.
- **markdown.js header comment says "18 node-type constants" but there are 19** — pre-existing drift, not introduced by F4; one-line fix owed to F7's SC9 docs work.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Reversed the vendor DD (no library vendored) | Survey ground-truth + independent security review: existing parser already XSS-safe by construction; vendoring would worsen posture | Yes — a code-survey prerequisite that can invalidate a planning DD belongs in pre-flight; reverse on ground truth |
| CI-integrity → no-HTML-string invariant guard | No vendored file to hash-pin; the equivalent risk is invariant erosion | Yes — guard the property, not the bytes |
| chat-roundtrip Witnessed RUN deferred to F7 | Delegated background run orphaned; interaction already evidenced by proxy | Partial — run behavior gates synchronously inside the verification leg (F3 pattern), don't delegate as a post-flight tail |

## Key Learnings

1. Reversing a planning DD on execution-discovered ground truth — with independent confirmation and constraint annotation (not silent rewrite) — is correct FD behavior, and cheapest done in pre-flight.
2. Declining a library can *improve* security posture when the library would introduce the very seam the architecture excludes by construction.
3. A structural invariant guard is higher-value than a byte hash-pin — it defends the property across refactors.
4. Background-spawned behavior crews orphan from their sub-orchestrator; spawn them synchronously.

## Recommendations

1. **(F5 — next)** Studio carries three pre-identified items (not net-new discovery): the `.field-row`→`.field-group` migration (+ retire the `.area-admin .field-error` gutter exception, wire full label-association), the discoverable-dropdown decision (mission Open Question — commit custom-widget-restyle vs native during this shared-components-consuming flight), and the save-race fix (F1 debrief). Plus M07 F10 lazy-discovery label copy + connector-editor-keyboard-a11y behavior re-verify.
2. **(F5-7 behavior gates)** Run each area's SC7 spec synchronously as a sub-orchestrator inside the verification leg. F5 authors + runs Studio agent create/edit; F6 authors + runs System provider config; **F7 runs all three deferred specs (chat-roundtrip + studio + system) in both themes** — budget for it; don't let authored-but-unrun specs accumulate.
3. **(F5 — DECISION owed now)** Introduce per-area browser test lanes (chat/studio/system/shared). Browser wall crossed from the ~12.5min three-flight plateau to 13:08 this flight (+29 XSS cases); F5/F6 each add a surface's flows. Pre-flagged in F1 rec 8 / F2 rec 5 / F3 rec 5 — F4 is where the numbers justify acting, so no single verification leg pays the full 13+min tax and F7's SC6 gate isn't a monolith.
4. **(F5 docs)** Fix the markdown.js "18"→"19" node-types comment.
5. **(F5-6 standing conventions)** Carry the composited-a11y-gate discipline (rgba-over-one-known-surface; solids not composite-gated) and the "consume the vocabulary primitive directly, become a new consumer of the existing gated pair" pattern as the template.

## Test Metrics (F1 → F4)

| Metric | F1 | F2 | F3 | F4 |
|---|---|---|---|---|
| Unit passed | 3681 | 3721 | 3749 | 3759 |
| Unit wall | 5:33 | 5:35 | 5:31 | 5:34 |
| Browser pass | 532/0 | 533/0 | 533/1flake | 562/1flake |
| Browser wall | ~12.5m | 12:33 | ~12.5m | 13:08 |
| Guard/a11y slice | boot | 93 | 121 | 130 |

Unit flat-to-linear (+10 = 3 a11y gates + 2 guards); **browser wall moved for the first time since F1** (+29 XSS cases) — per-area lane now ripe. Perf not re-measured (CSS/markup-led; F1 baseline stands; SC8 is F7). Sinks held at 92 (honest — no ratchet materialized).
