# Flight Debrief: Library completion and a stateful pilot

**Date**: 2026-10-15
**Flight**: [Library completion and a stateful pilot](flight.md)
**Status**: landed
**Duration**: 2026-10-15 (planned, executed and HAT-closed the same day)
**Legs Completed**: 9 of 9: eight autonomous legs plus the HAT. Six autonomous legs were planned; two were split at design review.
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
Every objective in the flight spec was met.

- **The Design language page is retired**, along with the dev-only page mechanism. Its token and type reference moved into the control catalogue.
- **The regression apparatus exists:**
  - `tests/test_ui_ownership.py`: a string tokenizer, a file-state assertion and an exact two-way allowance. It starts at 275 rows / 610 uses.
  - `HTML_SINK_ALLOWANCE`: an exact per-file count of every HTML-string sink, starting at 93 sinks in 17 files.
  - `scripts/ui_capture.py`: a scratch instance, full-page captures in both themes, and safety refusals.
- **The library gained 14 controls:**
  - `icon`, `editorShell`, `section`, `dangerZone`;
  - `confirm` (moved in, with `App.confirmDelete` kept as an alias), `infoButton`, `secretInput`;
  - `status`, `flash`, `copyButton`/`copyField`, `consentLink` (moved in, with an alias), `progress`, `chip`;
  - and extensions to `field`, `toggle`, `checkbox` and `emptyState`.

  Each has a catalogue row, owned classes, and contract tests in Chromium and WebKit.
- **The provider editor, models panel and providers section are rebuilt on the library under DD1** (mount once, patch through handles). All three files are at **zero** HTML sinks and **zero** reuse-allowance rows. DD1's divert criterion never fired: a held pull survives a refresh, with the same node and a working Cancel.
- **Totals at landing:** reuse allowance 243 rows / 504 uses, down from 275 / 610. Sinks 75 in 14 files, down from 93 in 17.
- **Squawks 0139, 0189 and 0190 are closed.** One real bug is fixed: after a Save, the API key field kept the typed plaintext and re-sent it on the next Save.
- **HAT:** every step passed. The operator approved the before/after capture set and confirmed every DD8 canonical version. Three HAT fixes landed:
  - the special treatment of the retired address was removed;
  - the shell's Test button is standard size;
  - the Pull button is standard size.

### Mission Criteria Advanced
- **"The app has no design-language page…": met** (checked in `mission.md`).
- **"Every kind of control is defined once in the library":** advanced. The editor and form, feedback and value controls exist, and the provider surfaces use only them.
- **"A change to one control's definition reaches every place" (the reuse check at zero exceptions):** advanced. The check is live and only shrinks, from 610 to 504 uses.
- **"No UI markup is built from HTML strings":** advanced, from 93 to 75 sinks.
- **"Each control's styles are owned":** advanced. The page-only and provider-only CSS is deleted, and owned classes are declared.
- **"Every migrated surface looks as it did before":** met for the provider surfaces, with the operator's approval of the capture set.
- **"Keyboard and role in both engines":** met for every control built. The progressbar defect was caught and fixed at review.
- **"Catalogue documents every control; a control without an entry and contract tests fails the gate":** met. The rule was rewritten off the deleted page.
- **"Existing behaviour holds":** met for this flight. Every gate was green.

## What Went Well
- **DD8 decided up front, with a mock-up canvas built from the real CSS.** The operator chose the switch and label placement from interactive artboards in minutes. Every visible difference afterwards traced to a DD8 line, and the HAT had only one spec-fidelity miss.
- **Apparatus before controls, controls before the pilot.** The reuse and sink ledgers and the "before" captures existed before any rendered file changed, so every later claim ("zero in these files", "looks the same") had evidence.
- **The stateful pilot first, with an explicit divert criterion (DD1).** It proved patch-in-place on the hardest surface, the streaming pull, before the editor depended on it.
- **A design review on every high-risk leg.** All six returned "approve with changes", and every one found something real:
  - unlisted test breakages;
  - an armed-rule specificity bug;
  - secret-handling rules;
  - the key re-mask bug.

  Two of them correctly split legs (02 into 02/03, 07 into 07/08).
- **The FD checked the work, not just the reports.**
  - Viewing a "before" PNG showed the danger zone below the fold, so full-page capture was added before any rendered file changed.
  - Reading leg 07's report caught two shortcuts that leg 08 then fixed: a raw `h1` query that routed around the reuse check, and `force=True` on toggle clicks.
- **The Accessibility Reviewer earned its place.** It found a genuine blocking defect, a cancel button inside `role=progressbar`, that the contract tests and the leg 05 design review missed.
- **The test suites are healthy.** Two full gates and a debrief gate all passed with no failures and no flakes.

## What Could Be Improved

### Process
- **Leg specs still miss tests they will break.** Design reviews added unlisted breakages for legs 01, 04, 06 and 07. The carried lesson exists but is not mechanical. Leg design should start with a grep of every moved path, renamed class and retired selector across `tests/`, `scripts/`, `Makefile` and `docs/ui-testid-registry.md`, with the hits pasted into the leg.
- **A spec-fidelity miss.** Leg 04's spec put the shell's Test button at `sm`, contradicting DD8 ("Test matches the other buttons"). Leg 06's spec left the Pull size to the old `btn-sm`. Both reached the HAT. UI leg specs should carry a "DD8 sizes and variants" check, and contract tests should assert computed sizes.
- **Plan-time sizing.** Leg 02 bundled a guard, a tokenizer, a dev tool that starts app instances, and a catalogue schema change. The capture tool's production-safety surface was visible at planning, and splitting it then would have saved a review round.
- **Accessibility review came late.** It ran once, at flight review. A "role structure" line in DD12 (required owned elements, presentational-children constraints) would have let the leg 05 design review catch the progressbar.

### Technical
- **Module-level "current mount" singletons.** `activeController` (`provider-models.js`) and `latestMount` (`provider-editor.js`) assume one provider editor is mounted. Flights 2-3 must not copy them. Extract a small mount-lifecycle helper (slot, generation, destroy) when the second consumer arrives.
- **Single-consumer factory options.** `dangerZone.beforeArm`, `consentLink.help`, and `field.host`/`setLabel` each have contract cases. Flight 2 should confirm a second consumer uses them, or prune them.
- **Large pilot files.** `provider-models.js` is 1004 lines and `provider-editor.js` is 895. They are the template Flights 2-3 copy, so name the split pattern before copying.
- **Alias shims are debt until their callers migrate:** `App.confirmDelete` (14 calls), `App.consentLink` (7), `App.showFlash` (41) and `App.icon` (30). The retired-API rows in the allowance track them; each flight should name which aliases it retires.
- **A raw query remains.** `providers-section.js` still queries `[data-field="name"]` on `~new`. It is small but a precedent.
- **Lane budget pressure.**
  - `agents` read 495 / 510 s at the debrief gate and 520 s (over) at the flight review gate. Squawk 0217 is still open, now for the third debrief running. Flight 2 adds tests there.
  - `contracts` went from 243 to 290 s (+19%; 723 → 848 tests) and will keep growing.
- **The unit tier's unexplained slowdown persists.** It read 281 s now, against 195 s at sortie 03. Nobody has profiled it with `--durations` (owed since sortie 04).

### Documentation
- Name the pilot pattern (keyed reconciliation, a controller hand-off, a generation counter, destroy on re-mount) as a convention in `the_one/agents.md`.
- Add a one-page "DD8 canonical versions" reference for leg authors: switch A, label B, copy feedback in the button, inline status-line saves, default-size Test and Pull, and the rest.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 02 split into ownership checks (02) and the capture tool (03) | Design review: the capture tool was independent and the riskiest piece | Yes: pre-split new guards and app-starting tools at plan time |
| Leg 07 split into the editor core (07) and sign-in plus close (08) | Design review: too big for one pass | Yes: split a stateful editor along its live sub-flows |
| Tiles, tabs, chip list, disclosure and key-value table moved to Flights 2-3 (DD9) | Build each control with its first consumer | Yes |
| Full-page captures with pane overflow; "before" retaken | FD saw the danger zone cut off below the fold | Yes: full-page is the default |
| Legs 02 and 03 ran concurrently | Disjoint files, saving time; docs edited last | Yes, for disjoint legs only |
| Library options added on demand (chip `size`, `emptyState.titleTag`, `field.host`/`setLabel`, `dangerZone.beforeArm`, `consentLink.help`) | First consumers needed them; each has a contract case | Yes, with a second-consumer check |
| Reuse allowance rose in leg 05 (604 → 616) | Newly owned classes counted existing debt | Yes: rises only with a flight-log reason |
| Accessible name follows visible text on Copy ("Copied") | WCAG 2.5.3 (label in name) | Yes |
| API key re-masked after Save | Bug found at leg 07 design review | n/a (a fix) |
| HAT fixes 2-3: Test and Pull at standard size | The leg 04/06 specs contradicted DD8 | Add computed-size contract assertions |
| HAT fix 1: tests and docs naming the retired address removed | Operator: no special treatment for an old address | Yes: retirement means absence, not a pinned redirect |

## Key Learnings
- **A decision catalogue settled with the operator up front, with interactive mock-ups for the contested items, converts "make it consistent" into a binding spec.** It was the highest-leverage step of the flight.
- **An exact two-way ratchet (fail on rise and on fall) keeps the ledger honest, but it needs a tokenizer exclusion list** (testids, comments, regex literals) **and a file-state assertion**, or it counts noise.
- **"Zero" claims can be gamed by routing around a guard.** The raw `h1` query is the example. The FD reading of reports, not just the gates, is what caught it.
- **Size and variant fidelity is invisible to DOM-shape tests.** Equal-height assertions are cheap and would have caught both HAT fixes.
- **Measured test metrics** (debrief gate, rc 0, no flakes):
  - unit tier: 6705 passed, 14 skipped (netns), 281 s;
  - browser total: 2054 passed, 4 skipped, 1092 s parallel.
  - Lane wall times against budgets, in seconds:

    | Lane | Wall | Budget |
    |---|---|---|
    | routing | 498 | 600 |
    | agents | 495 | 510 |
    | chats | 335 | 360 |
    | mcp | 333 | 360 |
    | providers | 299 | 420 |
    | contracts | 290 | 390 |
    | shared | 261 | 300 |
    | library | 249 | 300 |
    | settings | 227 | 300 |

  - Against sortie 04: unit +52 tests and 7 s faster; browser 1052 → 1092 s, within the observed ±10% host variance (this flight's own gates read 1041 and 1152 s).

## Methodology Observations
Plugin version: mission-control 1.2.0.
- **agentic-workflow, Phase 2a (leg design).** It asks for a design review per high-risk leg. In a flight where every leg is high-risk, that means a review round before each leg: six reviews, all "approve with changes".
  - Benefit: every review found real issues.
  - Cost: roughly one extra agent cycle per leg.
  - Expected: guidance on batching reviews for legs designed together (reviews of legs 04-07 ran while legs 01-03 implemented, which worked well), and on when a leg can skip a second review cycle after its fixes are folded in.
- **agentic-workflow, Phase 2a.** "List the tests the leg will break" is a carried lesson, not a step. Four legs still missed breakages that their reviews then found.
  - Expected: a mechanical leg-design step (a grep of moved and renamed identifiers across tests, scripts and registries).
  - Cost: review rework and addenda.
- **flight, Phase 4 (crew interview) and the HAT.** The skill puts a HAT at the end of a flight. The operator's DD8 checkpoint (choosing canonical versions) was moved into the flight-design interview instead of a mid-flight stop, so the flight could run to the HAT unattended. That worked, and it could be named as an option: decisions needing operator taste go in the design interview when the run is meant to be autonomous.
- **agentic-workflow, Phase 2d.** The crew file makes the Accessibility Reviewer optional. In a UI flight it found the only blocking issue. Expected: guidance to always enable it for flights whose legs build interactive controls.
- **The merge step.** Merging a plan PR from the FD session was refused by the harness's auto-mode classifier ("merge without review"), so the flight branched from the unmerged mission branch. The flight skill does not say where a flight branches from when its mission plan PR is still open. A sentence on that would remove the guesswork.

## Recommendations
1. **Re-plan Flight 2 before it starts.** As listed, it bundles the agent editor and six tabs, the connector and knowledge editors, five Settings pages, the `studio.js` (4181 → ≤ 800 lines) and `admin.js` splits, five new controls and four squawks. Either split it (the controls and the agent editor first; then the connector, knowledge and Settings pages) or lead with a behaviour-free restructure leg that splits `studio.js`. Also assign the top allowance and sink files to Flights 2-4 explicitly, so "zero in Flight 4" is planned rather than residual.
2. **Make DD8 test-enforced.** Add computed-size and variant assertions (equal height with neighbours; `sm` only where DD8 says so) to the contract template for every size-bearing control. Add a role-structure line to DD12.
3. **Resolve squawk 0217 (the `agents` lane budget) before Flight 2**, since that lane takes the agent-editor tests. Plan the contracts lane's split at about 1000 tests.
4. **Extract the mount-lifecycle helper** when the second editor adopts the pilot pattern, and document the pattern in `agents.md` together with a one-page DD8 reference.
5. **Track alias retirement per flight** (`App.confirmDelete`, `App.consentLink`, `App.showFlash`, `App.icon`). Consider fixing squawks 0220 and 0221 in Flight 2, before the patterns spread to more surfaces.
