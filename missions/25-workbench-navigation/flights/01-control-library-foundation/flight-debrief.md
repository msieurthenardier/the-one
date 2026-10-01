# Flight Debrief: Control Library Foundation

**Date**: 2026-10-01
**Flight**: [Control Library Foundation](flight.md)
**Status**: landed
**Duration**: 2026-09-30 – 2026-10-01
**Legs Completed**: 6 of 6
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved

The flight laid the foundation the rest of Mission 25 builds on.

- **Mechanism settled by evidence.** A spike judged the two candidate mechanisms on six
  criteria in three engines: Chromium 145, Playwright WebKit 26.0 and WebKitGTK 2.52.6.
  ES5 factories won. The custom-element alternative passed too, so DD1's
  native-element/ES5 rationale decided the tie.
- **Native `<dialog>` stacking rule (DD8) verified.** The spike also found a real engine
  race: a stale `close` event arrives after a same-turn reopen.
- **Test apparatus made library-ready:**
  - testid extractor patterns and a value-form guard;
  - a single shared runtime label/description resolver;
  - an engine-parametrized disk harness whose load order is derived from `index.html`;
  - a pure skip/require WebKit policy;
  - a no-sudo userland WebKit route;
  - a WebKitGTK probe for the real desktop engine.
- **Deep violet app-wide** through `--accent-fill*`. Control boundaries were raised to
  3:1 (`--control-border`, `--control-thumb`), with contrast gates, a dark-only band
  exception and 17 CSS usage pins.
- **Eleven `App.ui` factories:** button, textInput, field, textarea, select, checkbox,
  toggle, badge, emptyState, listPane and menu. Each is keyboard-complete, has visible
  focus and passes contract tests in both engines.
- **Living reference and inventory.** The dev-mode Design language page was rebuilt as
  the library's living reference in both themes. `docs/ui-control-inventory.md`
  classifies every control in the app, and both are held complete by guards.
- **Published design system updated** (version 5).

### Mission Criteria Advanced

- **SC6 (control library):** foundation delivered — mechanism, core set, guards,
  reference, inventory.
- **SC7 (deep violet):** delivered app-wide. It is gated in both themes, one band-pinned
  exception is recorded, and both the in-repo reference and the published design system
  are updated.
- **SC8 (prerequisite):** the board source, provenance README and reference spec are
  committed with the mission.
- **SC10 (per-leg gate):** every library control is keyboard-operable with visible focus
  and exercised in WebKit as well as Chromium. All suites are green.

## What Went Well

- **Planning-time reviews paid for themselves.**
  - Two Architect cycles at flight level caught a regex that would have broken every
    parametric library test id (DD2), the Escape/CloseWatcher double-peel (DD8), and
    inks that would not move with their fills (DD6).
  - Per-leg Developer design reviews found high-severity issues in three of six legs
    before code was written.
- **The leg split worked.** Splitting `menu-control` out of `core-controls` concentrated
  that leg's three high issues in one reviewed leg.
- **Parallel design work cut wall-clock without contention.** Legs 2–6 were drafted and
  reviewed while earlier legs were implementing. Leg design reviews are read-only.
- **The WebKit apparatus beat its own pessimistic plan.** DD9's route 2 (post-merge
  evidence) was never needed. Route 1 worked locally through an executable-path wrapper.
- **Zero flakes on the debrief's sequential lane run.** This matches the M17-F6 finding
  that running lanes one at a time removes load-timing flakes.
- **The flight-close behavior test passed 6/6** (`shell-navigation-smoke`) in live
  SendMessage mode, which made checkpoint continuation cheap.

## What Could Be Improved

### Process

- **Unverified vocabulary claims slipped through.** DD5 listed a `.badge` vocabulary as
  existing when it did not, and the Citation Audit had no row for it. Every design
  decision that lists "existing vocabulary to reuse" needs an audit row, or "verify by
  grep" in the leg.
- **Contrast premises written from the board were wrong.** DD14's assumption that
  selected-row meta passes was off: `--fg-muted` fails 3 of 4 composites. Compute
  composites at planning, not at leg review.
- **A11y lens only at flight level.** The flight-level Accessibility Reviewer found the
  live-region announcement and forced-colors gaps. No leg review had an a11y lens.
  Consider an a11y pass in leg design review for UI legs.
- **Four lane failures went uninvestigated.** They recurred across Legs 1–3 and passed
  on rerun each time:
  - `test_agent_item_keyboard_select`
  - `test_editor_renders_prompt_block`
  - `test_studio_agent_crud_flow`
  - `test_sandbox_chip_add_remove_marks_form_dirty`

  They were waved through under the rerun rule. The debrief's sequential run did not
  reproduce them. Flight 2 fixes them before its test migration (F2 DD9).
- **Contingency detail in the spec went unused.** The flight spec (about 950 lines) was
  heavy with contingency text, such as the route-2 post-merge gating. Keep flight design
  decisions at contract level; contingencies need only a divert criterion.

### Technical

Debt carried forward, all recorded in the inventory or here:

- **Parallel vocabularies.**
  - Three toggle vocabularies: `.tool-enable-switch`, `.tool-switch` and `.ui-toggle`.
  - Two badge vocabularies: global `.badge--*` and the area-scoped
    `.admin-provider-badge--*` and `.msg-pending-approval-badge*`.
  - Three icon paths: `App.icon` (a string), `App.ui.util.icon` (a node), and the
    duplicate `_appendIcon`.
  - Per-editor `_el` builders alongside `util.el`.
- **`.visually-hidden` lives only in area CSS.** It is defined in `admin.css` and
  `chat.css`. Library controls depend on it, and the disk harness hides the dependency.
  Flight 2 lifts it into `components.css` (F2 DD7).
- **Listener-order coupling in the menu.** The menu resets tabindex in a second keydown
  listener that undoes `rovingFocus`. A `rovingFocus` option would remove the coupling.
  Logged as squawk 0109.
- **Stale docstring.** `ui/feedback.js` still says "listPane passes 'status'". Logged as
  squawk 0108.
- **No production consumers yet** (by design, DD13). The API has been shaped only by
  tests and demos.
- **Flight 3 constraints:**
  - `listPane.setItems` rebuilds every row, so a live store update drops focus. A keyed
    or focus-preserving update is needed.
  - A row-action slot cannot nest inside an `<a>` or `<button>` row.
  - The menu's no-portal rule plus `overflow-y:auto` list bodies means a row menu will
    clip, and the menu does not flip.

### Documentation

`agents.md` should record the WebKit behavioural traps the legs hit, because they will
recur:

- `focusout` with a `null` `relatedTarget` (WebKit does not focus a pressed button);
- Playwright treats `aria-disabled` buttons as not enabled, hence `click(force=True)`;
- WebKit's "Script error." for cross-origin-looking script errors;
- the `LD_LIBRARY_PATH` override inside Playwright's MiniBrowser wrapper.

Some of these are already in the leg entries. Flight 2's docs pass collects them into
"UI test apparatus".

## Test Metrics

The debrief's sequential run, 2026-10-01:

| Suite | Result | Wall-clock |
|---|---|---|
| Unit (`make test-unit`) | 4,929 passed, 10 skipped | 666.9s |
| chat lane | 41 passed | 99s |
| studio lane | 188 passed, 3 skipped | 500s |
| system lane | 124 passed | 228s |
| shared lane | 437 passed, 4 skipped | 186s |
| Library contracts (both engines) | 257 passed, 1 skipped (forced colors on WebKit) | 70s |

- **No failures and no flakes** on this run.
- **Unit tier vs M24-F7** (4,810 passed in 694.75s): +119 tests and 28s faster, about
  135ms per test against 144ms. Most of the growth is the new static and contrast guards.
- **Browser tier.** The shared lane grew sharply because the `test_ui_*` contract files
  fall to it. They are cheap: 257 tests in about 70s, including the WebKit doubling.
- **Studio lane.** 8:19 for 188 tests, against 7:38 for 252 at M17-F5. It is the
  slowest lane and the one Flights 2–3 touch most. Re-measure after Flight 3.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| WebKit userland libraries via `executable_path` wrapper, not `launch(env=…)` | Playwright's MiniBrowser script overwrites `LD_LIBRARY_PATH` | yes — documented in `agents.md` "UI test apparatus" |
| `core-controls` split into `core-controls` + `menu-control` (6 legs) | Leg review found all three high issues in the menu | yes — split at the highest-risk control |
| Global `.badge` vocabulary created | Assumed vocabulary did not exist | yes — "verify vocabulary by grep" in leg authoring |
| `--control-thumb` token added beyond DD7 | The thumb on the off track needed its own gated pair | n/a |
| Selected-row meta moved to `--fg-secondary` | Contrast premise corrected at leg review | yes — compute composites at planning |
| Flight-review fix round (live region, forced colors) | Accessibility Reviewer findings | a11y lens at leg review for UI legs |
| PR #217 not merged by the Flight Director | Session permission policy denied "merge without review" | record — the operator merges flight PRs in this environment |

## Key Learnings

1. **Spikes are cheap insurance.** The mechanism spike also produced a real engine race
   finding (stale `close` event) that would otherwise have surfaced in Flight 2's leave
   guard.
2. **A test seam saves a policy test.** The pure-function WebKit policy plus a
   `FORCE_UNAVAILABLE` seam let skip/require behaviour be unit-tested with no failing
   browser.
3. **Disk-harness contract tests are fast and engine-portable.** 257 tests in about 70s
   across two engines, with no app spawn. Reuse them for every library control.
4. **Single-mode evidence paths matter.** goldfinch screenshots were unavailable for the
   whole behavior run, and the doctrine's PDF + AX + computed-style path carried it.
   Keep that fallback documented and expected.

## Methodology Observations

All observations below are for mission-control 1.2.0.

- **Flight design (`/mission-control:flight`, Phase 5b design review).**
  - *What happened:* the cap of two Architect cycles met a spec whose second cycle still
    returned "approve with changes" with ten refinements.
  - *Expected:* a clear rule for applying second-cycle refinements without a third
    review.
  - *Cost:* none this time; applied directly and logged.
  - *Recorded:* the skill says to escalate to the human "if issues persist after 2
    rounds". In autonomous runs it is ambiguous whether text-only refinements count as
    "persisting". The same happened at Flight 2 planning.
- **Agentic workflow (`/mission-control:agentic-workflow`, Phase 2d / commit and PR).**
  - *What happened:* the skill's flight completion assumes the Flight Director can manage
    the PR lifecycle. Opening and marking ready worked. The mission's "flights merge to
    `main` as they land" could not be honoured autonomously: the merge was denied by the
    session's permission policy.
  - *Cost:* Flight 2 must stack on the unmerged flight branch.
  - *Recorded:* the methodology has no explicit "merge requires the operator" step for
    autonomous runs.
- **Behavior test (`/mission-control:behavior-test`, Phase 4).**
  - *What happened:* live SendMessage continuation worked well (re-spawn was not needed).
    With goldfinch screenshots unavailable, the Validator relied on PDFs, which mute the
    page background fill. The step 4 "verify on a screenshot" Expected Result was met by
    a weaker evidence basis.
  - *Cost:* none; recorded for apparatus doctrine.

## Recommendations

1. **Lead with consumers.** Make Flight 2 the library's first real consumer (rail, modal)
   and let integration drive the gaps; adopt before polishing. (Developer)
2. **Verify claims at planning.** Every design-decision claim of "existing vocabulary" or
   "contrast passes" gets a Citation Audit row or a computed ratio at planning time.
   (Architect, process)
3. **Fix flakes before migrating.** Fix the four recurring lane flakes before the test
   migration, and prefer sequential lane runs at gates. (Both)
4. **Lift the shared utility.** Move `.visually-hidden` into library CSS and retire
   parallel vocabularies (badges, toggles) as each area is touched. (Architect)
5. **Close the CI WebKit gap.** CI's WebKit install with `THE_ONE_REQUIRE_WEBKIT=1` has
   never run (Concourse unreachable). Get an operator run before relying on CI as the
   WebKit gate. (Process)

## Action Items

- [x] Squawk 0108 — `ui/feedback.js` emptyState docstring names a stale listPane role (logged 2026-10-01)
- [x] Squawk 0109 — `ui/menu.js` tabindex reset depends on keydown listener order; add a `rovingFocus` option (logged 2026-10-01)
- [ ] Fix the four recurring lane flakes — folded into Flight 2 Leg 1 (F2 DD9)
- [ ] Lift `.visually-hidden` into `components.css` — folded into Flight 2 `rail-and-shell` (F2 DD7)
- [ ] Operator: merge PR #217; run CI's browser task once (WebKit `--with-deps` on `3.11-bookworm`, `THE_ONE_REQUIRE_WEBKIT=1`)
- [ ] Operator checkpoint (after Flight 3) items: `.btn-sm` 10px label (A6); exit criterion 5 satisfied by an automated WebKitGTK probe rather than a manual packaged-app pass
