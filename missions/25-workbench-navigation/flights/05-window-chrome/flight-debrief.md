# Flight Debrief: Window Chrome

**Date**: 2026-10-06
**Flight**: [Window Chrome](flight.md)
**Status**: landed
**Duration**: 2026-10-06 (planning, five legs, the close gate and this debrief, all on one day)
**Legs Completed**: 5 of 5 (leg 1 was split into 1a and 1b at its design review)
**Plugin version**: 1.2.0

## Outcome Assessment

### Objectives Achieved

The desktop window now looks like part of the workbench, verified on the operator's own
Windows 11 desktop through a test copy.
- **The title bar.** The native title bar takes the workbench's colours (caption
  `--surface`, title `--fg`, border `--border`) in both themes and follows every theme
  change, including Auto. Its title text dims to `--fg-muted` when another window is in
  front.
- **The first frame.** It is already in the right colours: a persisted launch theme, a
  themed splash and background, and the window created hidden, then tinted, then shown,
  with the splash kept until the main window is on screen.
- **Size.** A fresh install opens at 1440×900, centred, with a 640×360 floor that keeps
  Windows snap layouts working.
- **Unchanged:** drag, maximize, minimize, restore and close-to-tray.
- **Diagnostics.** `the-one doctor` has a tenth gate, `window chrome`, and both CI needle
  lists check it.

The close gate, `windows-window-chrome` on the frozen build, passed **11 of 11**
checkpoints (run `2026-10-06-20-06-24`). The operator's installed app and data were
unchanged after every one of the six crew sessions.

### Mission Criteria Advanced

- **SC9, the window belongs to the product:** the mechanism shipped and was crew-verified
  on the packaged (frozen) build. SC9 stays **open** by its own wording ("verified by the
  operator in the packaged app") for the operator's walk at Flight 6, with
  `windows-native-frame-splash` revised to carry those checks.
- **The Known Issue "Ctrl K in WebView2":** a real `SendInput` Ctrl K opened Jump to in
  WebView2, at leg 1b, at leg 4's dry run and at the close gate (steps 3 and 9). It now
  waits only on the operator's confirmation at Flight 6.
- **SC10, operable and regression-safe** (this flight's surfaces):
  - unit tests: 5428 passed;
  - all six browser lanes passed at leg 4;
  - the UI guards passed;
  - no new control was added.
- **The mission's "window chrome mechanism" question** is closed (DD1: a tinted native
  bar, chosen by the operator on 2026-10-06).

## What Went Well

- **Premise spikes before building.**
  - Leg 1 answered thirteen premises on the real host, each with a decided fallback. None
    of the fallbacks was needed: colours exact (delta 0), repaint in 8ms, no
    default-caption frame in 121 samples, glyphs legible without attribute 20, Ctrl K
    reaching the page, a bring-to-front technique proven 5 out of 5 twice.
  - Legs 2 and 3 were then designed on observed facts, and neither needed rework on the
    platform side.
- **Design reviews caught the expensive defects before any Windows session.**
  - At planning: an input-safety gap on the live desktop, a first-post race, and DPI unit
    mixing.
  - At leg 2: a UI-thread deadlock risk with `Invoke`, the wrong delegate type, a
    splash-dismissal gap, and the backstop that would have waited on its own thread.
  - Every high-severity finding was fixed in the artifact, not in code.
- **The apparatus's safety model held for six sessions** on an in-use desktop:
  - process-tree identity;
  - one-handle kills with `audit.log`;
  - foreground and pointer gates, and the hands-off rule;
  - a key denylist;
  - capture containment with a Z-order occlusion test;
  - operator-data snapshots;
  - focus save and restore.

  Every snapshot comparison was clean, and the installed app kept PID 208344
  throughout. `input.log` showed no injection to a foreign window. Leg 1b also found and
  fixed a real defect in its own recovery rule.
- **The request and read-back pair.** `POST /api/window/chrome` with `GET` gave the
  behavior test an internal read path (HRESULTs, `pending`, `active`) beside the pixels,
  and the Validators used both.
- **Pin duplicated constants by test.** `PALETTE` is pinned against `tokens.css`, and
  `NEEDLES` against CI's `foreach` list. The second was added at the flight-end review
  after the first draft had silently missed the fifth needle.
- **The DD12 preview went out before the close gate,** with what-you-see questions and
  real captures.

## What Could Be Improved

### Process
- **The acceptance spec was written before its apparatus existed.**
  `windows-window-chrome` was drafted at planning and needed a full rewrite at leg 4. The
  leg 4 dry run found step 7's storage-flush problem. The close gate still needed two
  Orchestrator rulings (step 5's tolerance, re-showing own window A) and produced squawk
  0123's wording list. For apparatus-heavy flights, the spec should be treated as a
  sketch at planning and dry-run before the gate. This flight did that, and it should
  become the norm.
- **Leg 4 also did apparatus work.** It added `resize` and `capture --splash`. Leg 1's
  command list under-built what the close gate needed (resizing to the floor, and
  following the splash window).
- **Evidence gaps at the close gate.** The step-3 and step-9 screenshots the Executor
  listed were never saved (its script errors). The DOM reads carried both verdicts, but
  the Executor prompt should require checking that every listed path exists. That was
  added mid-run, after step 3.
- **Six design-review cycles** for legs (two each on 1a, 1b and 2), plus two at planning.
  Each found real issues, and the cost was justified on this surface. On a lower-risk
  flight the same cadence would be over-spend.

### Technical
- **`scripts/windows_test_copy.py` is 5,002 lines in one file,** about 60% of the
  flight's added lines and roughly ten times the product code. Its Windows half is
  verified only live on one host (build 26200, 100% DPI, one screen). It mirrors CI's
  closure commands without a pin test. Split it into a pure policy module (refusals,
  containment, gates, snapshot diff, key grammar) and the Windows-executing half before
  it grows. Any change to its input or kill gates should take a design review and a live
  session.
- **The lock model.** DD3 left unsaid which lock covers the theme-file write, and the
  first fix at review re-opened a persistence race. It is sound now (`_file_lock`, then
  `_lock`, with the latest theme re-read inside), but subtle.
- **Process-global singleton state** in `chrome.py`. It is fine for one main window. A
  second window would need a registry.
- **Untested, or tested only as units:**
  - Windows builds below 22000 (attribute 20 only);
  - high contrast mode;
  - scaling above 100% (pywebview multiplies a saved x/y by the scale factor);
  - several monitors;
  - window widths between 640 and 1023, which the floor now allows but nothing tests;
  - the live drag to the floor (a drag cannot start on the invisible resize border, so
    `resize` stands in).
- **CI does not run the new gate.** Concourse is unreachable, so CI's frozen doctor
  (which carries the new needle) has not run. The GitHub fallback (`windows-2022`, build
  20348) exercises only the dark-mode-only branch.

### Documentation
- **The pywebview 6.x upgrade blocker** (its `update_title_bar_theme()` would overwrite
  the app's theme on an OS theme change) is in the flight's DD7 but not in
  `the_one/agents.md`. Logged as squawk 0125.
- **`agents.md` keeps growing:** +69 lines this flight and +212 in Flight 4. The split
  recommended by routine maintenance is still outstanding.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 1 split into 1a (no input) and 1b (input and captures) at its design review | One pass could not safely carry ~20 commands, a freeze, and thirteen premises on a live desktop | Yes: split apparatus legs at the inject/no-inject boundary |
| DD6's floor is 640×360, not an enforced 1024 | Enforcing 1024 blocks Windows snap thirds and, on smaller screens, halves, which SC9 requires | Yes: the decision stands; whether to enforce 1024 is a DD12 preview question |
| The UI-thread apply uses `BeginInvoke` with a 2s bounded wait, and `tinted` may be `"pending"` | `Invoke` from a request thread can block forever across Quit | Yes: bounded waits for every UI-thread hop from a request thread |
| A `_main_shown` gate keeps the splash until the main window is visible; the backstop moved after `show()` | A hidden window can finish loading before `show()`; a backstop waiting on `_boot`'s own thread would deadlock | Yes |
| `capture --splash` (leg 4) | A plain series follows only the main window, so leg 2's "white splash" frames were the main window's page area | Yes: name the window a capture follows |
| `resize` instead of a drag to test the floor | A drag cannot start on the invisible resize border | Yes, with the live gesture left to the operator |
| The flight commit was made by the Flight Director, not a commit Developer | One `git add -A` of a tree the review had just confirmed, with the pre-commit hook passing; it saved a spawn | No: the crew file's commit Developer stays the default |
| A release is cut mid-mission | The operator's explicit instruction overrides the mission's "no release until the mission completes" (recorded in the flight log) | No: an operator-specific override |

## Key Learnings

- **Platform behaviour is a premise, not a design detail.** Writing each unknown as a
  numbered premise with a decided fallback, and spiking them all first, turned an
  uncertain flight (M15 had reverted custom chrome) into one with no platform rework.
- **Thread boundaries were the main source of defects:**
  - a request thread versus the WinForms UI thread;
  - pythonnet handlers on the message loop;
  - `_boot`'s thread versus the `loaded` handler's thread.

  Three of the leg 2 review's highs were thread-boundary issues. Flight designs that
  touch a UI toolkit should name every thread that can reach shared state, and which
  lock covers which I/O.
- **On a live desktop, the apparatus is as risky as the product.** A test helper that
  injects input next to the operator's own windows needs the same review discipline as
  product code. This flight gave it that, and the result was six clean sessions.
- **`events.shown` is not "visible".** On pywebview 5.4's hidden path it fires at the
  opacity-0 creation flash, so any code reading it as visibility is wrong.
- **WebView2 writes `localStorage` lazily.** It flushes about 5 seconds after a change,
  and more than 20 seconds after a burst. A hard kill drops the pending write; a
  graceful Quit flushes it.

## Test Metrics

- **Unit** (`TEST_TIMEOUT=3000 make test-unit` at `07a1c16`): **5428 passed**, 10
  skipped, 1820 deselected, 0 failed; pytest 674.7s, wall about 709s.
  - **Against Flight 4:** 5178 passed, 687s pytest and 715s wall; Flight 3: 5045 and
    654s. This flight adds **250 tests (+4.8%)** while the wall time dropped about 6s.
  - **Where the new tests are:** `test_windows_test_copy.py` (93 functions),
    `test_window_chrome.py` (43), `test_desktop_shell.py` (+356 lines),
    `test_window_state.py`, `test_doctor.py` and `test_api_window_chrome.py`. All are
    pure units, so they cost no measurable time.
  - No flakes seen. The 18 warnings include the known forkpty `DeprecationWarning`.
- **Browser lanes** (leg 4's full run; no browser-facing code has changed since):

  | Lane | Result | Time | Against Flight 4 |
  |---|---|---|---|
  | `chats` | 163 | 4m21s | unchanged |
  | `agents` | 134, 2 skipped | 5m29s | −10s |
  | `library` | 145, 1 skipped | 8m00s | −17s |
  | `settings` | 183 | 5m50s | +5, the new `test_flow_settings_window_chrome_signal.py` |
  | `contracts` | 646, 3 skipped | 2m48s | unchanged |
  | `shared` | 465 | 11m50s | +4 |

  - About 1736 in all, +9 against Flight 4. Lane times are flat, so no rebalancing is
    needed. `shared` is still the longest at about 12 minutes.
- **Behavior:**
  - `windows-window-chrome`: 11 of 11 on the frozen build (Executor and Validator live;
    about 17 minutes of steps after a 79-second freeze).
  - No other spec was re-run. The `theme.js` signal is gated off in ordinary browsers,
    and the `settings` and `shared` lanes covered it.

## Methodology Observations

Plugin version 1.2.0 throughout.

1. **Subagent hand-backs did not arrive.**
   - **What happened:** in the Claude Code harness, not the plugin, an agent's
     completion notification arrived without its report five times. That was the
     planning Architect's cycle 2, the leg 2 reviewer (twice), the close-gate Executor's
     `[READY]` and the debrief Developer.
   - **What it cost:** a `SendMessage` asking for a resend each time, about one to two
     minutes. Twice, a stale fallback wakeup ran after the work it watched had moved on.
   - **Expected:** a report with every completion notification.
   - **Where:** `/mission-control:flight` (design review), `/mission-control:agentic-
     workflow` (leg design review), `/mission-control:behavior-test` (Phase 2),
     `/mission-control:flight-debrief` (Phase 2).
2. **Squawk 0121's recipe was appended by hand, for the third flight running.**
   - **What happened:** the behavior crew file still lacks the CDP driver lifetime,
     PID-only kills, the report-file hand-off and the ledger.
   - **What it cost:** prompt-assembly time, and a new rule found mid-run: "verify
     every listed evidence path exists" was added after step 3's missing screenshots.
   - **Expected:** the crew file carries them.
   - **Where:** `/mission-control:behavior-test`, Phases 2 and 3; the project's crew
     file, squawk 0121, still open.
3. **The acceptance spec was drafted before its apparatus existed.**
   - **What happened:** the flight skill's Phase 5 guidance drafts behavior specs at
     planning, before legs lock. For this flight the spec's every Action changed once the
     helper existed (leg 4 rewrite plus dry run), and the close gate still produced eight
     wording fixes (squawk 0123).
   - **What it cost:** one leg of rewrite and dry run (worth it), plus two Orchestrator
     rulings at the gate.
   - **Expected:** guidance that an apparatus-dependent spec is a sketch until a dry run.
   - **Where:** `/mission-control:flight`, Phase 5; `/mission-control:agentic-workflow`,
     the behavior-test section.
4. **No place to record tolerances.**
   - **What happened:** the behavior-test skill has no place for a tolerance or
     sampling convention, so "close to" became an Orchestrator ruling recorded only in
     the run log.
   - **What it cost:** none this run (the values were exact), but a stricter Validator
     could have returned INCONCLUSIVE.
   - **Expected:** an authoring rule in `AUTHORING.md` that pixel or colour expectations
     state the aggregate, region and tolerance.
   - **Where:** the behavior-test authoring guidance.
5. **The leg split under the leg-immutability rule.**
   - **What happened:** the agentic workflow says legs are immutable once in flight, and
     the split happened while leg 1 was still `planning`, so the rule was not hit. The
     flight skill's Legs list had no place to record the split except an in-flight note
     in the flight spec.
   - **What it cost:** minor (one annotation).
   - **Where:** `/mission-control:agentic-workflow`, Phase 2a.
6. **An operator instruction overrode a mission constraint.**
   - **What happened:** the operator's "merge when ready and cut a minor release"
     overrode the mission's "no release until the mission completes". The methodology
     has no artifact field for a mission-level constraint waived by the operator, so it
     went into the flight log's Flight Director Notes.
   - **What it cost:** none.
   - **Where:** `/mission-control:agentic-workflow`, Phase 3, or the mission artifact.

## Recommendations

1. **Split `scripts/windows_test_copy.py` and pin its CI mirror.** Pure policy goes in one
   module, the Windows half in another, behind a fake-backend smoke test. The CI closure
   commands get a test like the `NEEDLES` one (squawk 0124). Any change to the input or
   kill gates takes a design review and a live session. **Important.**
2. **Before Flight 6, fold the open window-chrome items into its decision sheet:**
   - the five DD12 preview questions;
   - SC9's operator checks (a real OS theme flip, snap halves and thirds, Win+arrows, an
     upgrade against a fresh profile, scaling above 100%, several monitors, the live drag
     to the floor);
   - the window widths between 640 and 1023;
   - the known one-offs (the light first launch after an upgrade, the splash logo, the
     ghost tray icon after a hard kill).

   **Important.**
3. **Fix the crew file and spec conventions:**
   - complete squawk 0121 (the recipe, plus "verify every listed evidence path");
   - complete squawk 0123 (the window-chrome spec wording);
   - add the rule that colour or pixel expectations name their aggregate, region and
     tolerance.

   **Important.**
4. **Record the pywebview 6.x upgrade blocker in `agents.md`** (squawk 0125). **Minor.**
5. **Bring Concourse back,** so CI's frozen doctor runs the `window chrome` needle on
   every `main` push. **Minor.**

## Action Items

- [ ] Squawk 0124: pin the helper's CI-closure commands against
  `ci/tasks/windows-installer-build.yml` by test (recommendation 1)
- [ ] Squawk 0125: document the pywebview 6.x upgrade blocker in `the_one/agents.md`
  (recommendation 4)
- [ ] Squawk 0123 (already logged): the `windows-window-chrome` spec wording
- [ ] Squawk 0121 (open): the behavior crew file's CDP recipe and evidence-path rule
- [ ] Flight 6 planning: the decision sheet (recommendation 2), the operator's packaged-build
  walk of `windows-native-frame-splash`, and the Ctrl K sign-off
- [ ] Routine maintenance: the `windows_test_copy.py` split (recommendation 1), the
  `agents.md` split
- [ ] Release `v0.10.0` after PR #221 merges (the operator's instruction, 2026-10-06)
