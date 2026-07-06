# Flight Debrief: Hardening & Mission-End Acceptance

**Date**: 2026-07-06
**Flight**: [Hardening & Mission-End Acceptance](flight.md)
**Status**: completed
**Legs Completed**: 4 of 4 (01-consistency-fixes, 02-sc2-completeness-and-docs, 03a-empirical, 03b-verdict)

## Outcome Assessment

### Objectives Achieved

The acceptance flight closed the mission: it fixed the two deferred cross-area items, closed the SC2 contrast-completeness hole, brought the docs fully current, ran the one owed behavior gate (chat-roundtrip dark) plus the SC8 perf re-run and the two mandatory re-runs, and performed the **SC1-SC9 mission-end verification — all nine boxes checked against cited, tree-matching evidence.** Product footprint was deliberately tiny (2 source files, ~16 lines) — the sign that Flights 1-6 did their jobs completely, so the hardening flight had little to harden. Commit `bae84a9`.

### Mission Criteria — ALL NINE MET (checked in mission.md)

Every SC verified with cited evidence in the flight-log SC-evidence ledger. Independently confirmed by both a general Reviewer and an Accessibility Reviewer (the latter re-ran the SC2 probe + verified the cap-chip quiet live + ran the H1 regression test — re-deriving evidence, not trusting the log).

## What Went Well

- **The empirical/verdict leg split (3a → 3b) — the flight's key methodological win.** Isolating the exclusive-instance, judgment-bearing measurements (perf on 8485 + the four Witnessed behavior runs, FD-sequenced never overlapping) into 3a from the verdict that consumes them (3b: full suites + guard audit + SC1-SC9 box-checking) enforced "measure, then judge, with the judge unable to rush the measurement." This mattered concretely for SC8: the raw +23% surfaced in 3a as a *diagnosis to settle*, and 3b consumed the already-resolved retained-heap verdict rather than re-litigating it under time pressure.
- **The SC7 cite-vs-rerun rule — a cache-invalidation rule for test evidence.** "A cited prior-flight run is valid for a mission-end check ONLY if no code the gate exercises changed since." F7's own Leg-1 diffs landed inside two gated surfaces (provider-editor.js → system-provider-config; the shared `renderCapabilityChips` → studio-agent-crud), correctly invalidating those citations and forcing re-runs, while connector-editor-a11y (surface untouched) was legitimately cited. Elegantly, the system-provider-config re-run *doubled as the behavior-level proof of the H1 fix* — the invalidation wasn't overhead, it was the evidence that closed the fix.
- **The SC8 raw-vs-retained diagnosis — transparent, not silent.** Raw 2s-settle read +23% (over the ≤20% budget). Rather than silent-pass or false-divert, a forced-GC retained-heap measurement showed **+0.99% (2,593,937→2,619,614 B — flat, no leak)**; per-chunk heap stayed non-monotonic during cycling (the growth was end-capture transient garbage), and the denominator effect is quantified (~586 KB absolute ≈ the baseline's +439 KB, reading as 23% only because the lean 2.5 MB dev heap is a smaller denominator than the baseline's 6.7 MB live instance). The raw over-budget figure is recorded verbatim in perf-result-f7.md and surfaced to the operator; the box rests on retained + latency (p50 0.10ms). A model of transparent-not-silent verification.
- **The SC2 CSS-driven completeness net — the sharpest decision, genuine hardening during an acceptance flight.** The mirror-sync guard is strictly mirror→CSS, so a literal-hex fg token in tokens.css but absent from the mirror slips *both* nets. The new assertion enumerates from tokens.css (source of truth) and defines "gated" conjunctively (literal-hex AND mirrored AND referenced by a real contrast assertion). Probe-tested: a planted `--fg-probe` fails by name. This makes SC2's "ALL palette tokens, exceptions documented" machine-true, not prose-asserted.
- **The two fixes — proportionate, architecturally leveraged.** The `.cap-chip` quiet is one un-scoped rule governing both admin + studio (via the shared `renderCapabilityChips`) — the right proof-of-one-vocabulary for SC3. The H1 fix's key judgment: re-render the *whole* header (title AND subtitle), because the subtitle (`type · base_url`) goes stale by the identical mechanism — textContent-only on display-only nodes, provably invisible to snapshot/dirty tracking.
- **The guard audit was green AND honest**: `KNOWN_DEAD_SELECTORS = set()`, `CLIP_PATH_POLYGON_ALLOWANCE = {}` — empty exception sets, so green means genuinely zero remnants, not a suppressed allowance.

## What Could Be Improved

- **The SC8 percentage budget is denominator-sensitive** — it false-positived at +23% on the lean dev instance. The durable fix (methodology debt, not a mission defect): re-express SC8's budget as forced-GC retained growth (absolute + %), and/or pin the measurement to a comparable heap denominator (seeded sessions), so the anchor and the measurement use the same denominator and the caveat disappears.
- **The cite-vs-rerun rule has no machine backing** — it's applied by judgment of "what surface does this gate exercise." Per-spec surface-fingerprinting would make it enforceable rather than judgment-dependent (methodology debt).
- **Behavior-harness: the armed-delete ~3s auto-revert outran evidence capture** in two specs (load-bearing claims still soundly evidenced via synchronous DOM sampling + API). Future armed-transient UI specs should freeze/suppress the revert timer before the screenshot + a11y snapshot.
- **No live SendMessage continuation was available**, so the Witnessed loop ran at per-run (not per-checkpoint) re-spawn granularity — the actor≠judge invariant held (disclosed in each run log), but tighter mid-test failure surfacing is a tooling gap.

## Key Learnings (reusable for future acceptance flights)

1. **Adopt the cite-vs-rerun rule as an acceptance pattern** — it mechanically prevents checking a box against code that no longer exists, while permitting citation of untouched surfaces (so acceptance doesn't degenerate into re-running everything).
2. **Measure retained (forced-GC) heap, treat raw-settle as advisory** — the raw metric is denominator-sensitive on lean instances.
3. **Two-review (general + independent a11y) is worth it for acceptance** — the a11y reviewer *re-ran the load-bearing probes* rather than trusting the log.
4. **Split measurement from verdict** — the judge should consume settled evidence, unable to rush the measurement.
5. **A completeness net must enumerate from the source of truth**, not a derived mirror, or it inherits the blind spot it audits.

## The Two-Opus-Review Value (justified for an acceptance flight)

The first review cycle caught FOUR gaps, each a *silently-false-SC-check vector*: cite-vs-rerun (SC7 checked against changed code), perf-port-8484 (SC8 measured against the operator's prod app, not the branch), H1-subtitle-sibling (an incomplete fix that might pass a title-only gate), SC2-mirror-vs-CSS (a completeness net with the same blind spot as the thing it audits). The second cycle confirmed sufficiency. For a flight whose entire product is *the credibility of nine checked boxes*, catching four false-check vectors before execution is exactly where review rigor pays off.

## Test Metrics (F1 → F7)

| Flight | Unit | Browser | Note |
|---|---|---|---|
| M16 end | 3681 | 478 | SC8 anchor; 5 modules skipped |
| F1 | 3681 | 532 | 5 modules re-enabled; guard scaffolding |
| F2 | 3721 | 533 | contrast/token parametrization |
| F3 | 3743 | 533 | badge-ink pairs, mirror-sync guard |
| F4 | 3759 | 561 | markdown/XSS suite (no-vendor) |
| F5 | 3779 | 562 | per-area lanes, +6 guards |
| F6 | 3781 | 565 | label-association, runtime chip-list guard |
| **F7** | **3782** | **566** | +1 SC2 completeness net, +1 H1 regression |

Net mission delta: **unit +101, browser +88, zero module-level skips** — the machine-enforced "healthier than before" (SC6). Every increment attributable to a named guard/coverage addition; no unexplained churn. F7's own +1/+1 is consistent with an acceptance flight that verifies rather than builds.

## Recommendation

**The mission is complete.** All nine SCs met with cited evidence, independently confirmed, on the unmerged `mission/17-ui-redesign` branch. The durable regression net (6 honest guard families + the SC2 completeness net + the runtime chip-list guard) will keep each hard-won property from silently regressing. Carry the two methodology-debt flags (machine-back cite-vs-rerun; retained-heap perf budget) into the mission debrief.
