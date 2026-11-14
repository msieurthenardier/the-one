# Leg: specs-and-close

**Status**: completed
**Flight**: [Window Chrome](../flight.md)

## Objective

Make the flight's acceptance artifacts match what legs 1–3 built:
- the crew spec `windows-window-chrome`, made final and runnable;
- the operator spec `windows-native-frame-splash`, revised for Flight 6's SC9 walk;
- a small `resize` helper command that spec step 8 needs;
- the operator-preview captures;
- the documentation and mission updates;
- the full gates.

After this leg, the Flight Director runs the flight-end review, the commit, the preview and
the close-gate behavior run.

## Context

- **Legs 1a, 1b, 2 and 3 have landed, uncommitted.** Read their flight-log entries,
  which carry the values and deviations, and the `the_one/agents.md` blocks "Windows test
  copy" (1a, 1b), "Window chrome (M25 F5)" (2) and the first-launch size and doctor
  sections (3).
- **The draft crew spec** `tests/behavior/windows-window-chrome.md` was written at
  planning, before the apparatus existed. It must now match the real helper and the
  observed behaviour:
  - **Step 1 (launch):**
    - the capture series starts right after `launch` begins, because the helper refuses
      an unrecorded tree;
    - the expected first-launch values follow the OS app theme read by `doctor-host`
      (Light on this host);
    - the drawer clause goes, and the viewport check (`innerWidth` of 1280 or more)
      stays.
  - **Step 2 (the read-back):** GET `/api/window/chrome` is judged on `last_applied` and
    `pending: false`, never on `requested` alone.
  - **Step 3 (Ctrl K):** `front`, then a CDP-derived body `click`, then `keys ^k`, then
    `keys {ESC}`.
  - **Steps 5 and 6:** the inactive state uses own window A. Auto uses CDP
    `Emulation.setEmulatedMedia`.
  - **Step 7:** the theme persists at request time, so no 10-second wait is needed. The
    sequence is × to the tray, then `stop`, then a relaunch with the series.
  - **Step 8:** the live floor test uses the new `resize` command, because a drag cannot
    start on the invisible resize border (leg 3).
  - **Step 9:** a caption `click --double`, then the minimize button `click`, then
    `show-window --restore`, then `drag --caption`.
  - **Step 11:** the snapshot comparison plus `focus-restore`.
  - **Throughout:** the precise helper commands are named in each Action, so the Executor
    has nothing to work out.
  - The spec runs on the **frozen** build at the close gate (`launch --frozen`).
- **The operator spec** `tests/behavior/windows-native-frame-splash.md` (M15) is
  operator-driven. Its Preconditions say it targets a dedicated test host on 8484. The
  operator's only Windows machine is their daily driver, and at Flight 6 they walk
  **their own installed build**. Its step 9 is stale under the credential gate (its own
  "Known gap" note). SC9's operator-only checks (flight DD11's last row) join it.
- **Mission artifacts:**
  - the "Window chrome mechanism" open question (`mission.md`, around line 227) is
    answered by DD1;
  - the Known Issue "Ctrl K in WebView2" (around line 266) now has crew evidence: leg 1b
    premise 9, and the close gate re-checks it on the frozen build;
  - SC9 stays open for Flight 6.

  The Flight Director checks off Flight 5 in `mission.md` at landing; this leg does not.
- **The operator preview (flight DD12)** needs captures of the test copy, made in this
  leg and saved for the Flight Director:
  - both themes, active and inactive;
  - the splash in both themes;
  - the first-launch window.

## Inputs

- The landed working tree (legs 1a–3), and the scratch root
  `C:\Users\<user>\AppData\Local\Temp\the-one-f5\` with its venv and `dist\`.
- `tests/behavior/windows-window-chrome.md` (draft) and
  `tests/behavior/windows-native-frame-splash.md`.
- `missions/25-workbench-navigation/mission.md`.
- `.flightops/ARTIFACTS.md` "Behavior Test — Spec", the format.

## Outputs

- **`scripts/windows_test_copy.py`:** `resize --width W --height H` (outer size).
  - It calls `SetWindowPos` on the gate tree's main window with `SWP_NOMOVE |
    SWP_NOZORDER | SWP_NOACTIVATE`.
  - It applies the identity check and the hands-off check first.
  - It refuses non-positive or absurd sizes (below 100 or above 10000).
  - It reports the requested size and the resulting rect.

  Add a pure argument-validation function with a unit test in
  `tests/test_windows_test_copy.py`.
- **`tests/behavior/windows-window-chrome.md`:**
  - `Status: active`;
  - the steps rewritten as described in Context, with each Action naming the helper
    commands;
  - Preconditions referencing `the_one/agents.md` "Windows test copy" for the safety
    rules, rather than duplicating them;
  - a "Revised" line.

  Keep the spec's structure: Intent, Preconditions, Observables Required, Steps, Out of
  Scope, Variants.
- **`tests/behavior/windows-native-frame-splash.md`:**
  - **Revised Preconditions:** the operator, on their own installed build, at Flight 6.
    Their installed app is the target, so port 8484 and their data dir are expected here
    and only here, because the operator drives it. The old "dedicated test host" wording
    goes.
  - **Step 9 rewritten:** a plain browser without a handoff is refused (not
    authenticated), and shows no window controls. The custom-control check is moot since
    Mission 15's revert.
  - **SC9 steps added** (the operator observes; there is no crew apparatus):
    1. the title bar matches the workbench in Light and in Dark;
    2. it follows a theme change made in Settings › Appearance at once;
    3. in Auto, it follows a **real** OS theme flip;
    4. an inactive window's title text is dimmer;
    5. snap layouts work: hover the maximize button for the flyout, snap to halves and to
       thirds, and use Win+arrows;
    6. the first launch after the upgrade keeps the existing window size;
    7. a fresh profile (an operator choice: rename `window-state.json`) opens at about
       1440×900, centred;
    8. Ctrl K opens Jump to;
    9. the splash matches the theme, and the main window replaces it with no gap.
  - **A note:** the first launch after the upgrade may show a light frame or a white page
    area once when the OS theme and the app preference differ (flight DD4). It is not a
    defect.
  - **Variants:** scaling above 100% and several monitors (`CenterScreen` uses the
    monitor under the mouse) as optional operator checks.
  - **A "Revised" line.**
- **`mission.md`:**
  - check off the "Window chrome mechanism" open question with a one-line answer (DD1:
    tinted native bar; operator, 2026-10-06);
  - update the "Ctrl K in WebView2" Known Issue with the crew evidence (leg 1b premise 9:
    a real `SendInput` Ctrl+K opened Jump to in the WebView2 test copy), leaving it open
    for the close-gate frozen re-check and the operator's Flight 6 confirmation;
  - leave SC9 unchecked, with a one-line "Flight 5's part" note.
- **Preview captures** (no PII: scratch data dirs only), saved as PNG under the scratch
  root's `evidence\preview\` and copied to
  `/tmp/claude-1000/-home-<user>-projects-the-one/0eb14466-3200-4ca3-9529-5ff071966eae/scratchpad/f5preview/`:
  - `light-active.png`, `light-inactive.png`, `dark-active.png`, `dark-inactive.png`:
    the whole test-copy window through `capture --window`;
  - `splash-light.png`, `splash-dark.png`: a frame of the splash from a launch series;
  - `first-launch.png`: a first-launch window on a fresh dir;
  - a `README.txt` listing what each shows and the sampled caption values.
- **The doc sweep.** Confirm that these agree with the code and with each other:
  - `CLAUDE.md`: the desktop launcher, the doctor gate count and the apparatus sentence;
  - `the_one/agents.md`: Window chrome, the footgun note, the doctor gates, Windows test
    copy and first-launch size.

  Fix any drift. If `SECURITY-MODEL.md` enumerates routes, add `/api/window/chrome`
  (behind the credential gate).
- **The flight log:** a "Leg 4: specs-and-close" entry.

## Acceptance Criteria

- [ ] **`resize` works:** it exists with its validation unit test. On the test copy, a
  saved 400×250 launches at 640×360, `resize --width 400 --height 250` leaves it at
  640×360 (±2), and `resize --width 1000 --height 700` gives 1000×700 (±2).
- [ ] **CI's needle check, verbatim.** The PowerShell `foreach` from
  `ci/tasks/windows-installer-build.yml`, with all five needles, runs against the frozen
  doctor's output on Windows, unchanged, and passes. The command and its result are in
  the flight log.
- [ ] **`windows-window-chrome` is `active`:**
  - every Action names helper commands that exist;
  - every Expected Result matches what legs 1b–3 observed;
  - step 8 uses `resize`;
  - no step relies on `requested` alone, on a drawer check or on a drag over the
    invisible border;
  - the format matches ARTIFACTS.md.
- [ ] **A dry run of the crew spec.** Every step runs once on the **frozen** test copy,
  in one bracketed session. Any step that cannot be executed as written is fixed in the
  spec. This is not the Witnessed run; that is the Flight Director's close gate.
- [ ] **`windows-native-frame-splash` is revised** as listed in Outputs, with its
  structure kept.
- [ ] **`mission.md`:** the open question checked off, the Known Issue updated, SC9 still
  open with its note.
- [ ] **The seven preview PNGs and `README.txt`** are in the scratchpad's `f5preview/`
  folder, with sampled caption values in the README.
- [ ] **The doc sweep** is done, and any drift found is fixed and listed in the flight
  log.
- [ ] **Gates:**
  - `ruff check` and `ruff format --check` pass;
  - `TEST_TIMEOUT=3000 make test-unit` passes;
  - **all six browser lanes** pass under `THE_ONE_TEST_NETNS=1`:
    - `chats`, `agents`, `library` and `settings`;
    - `contracts` with `THE_ONE_REQUIRE_WEBKIT=1`;
    - `shared` with `TEST_TIMEOUT=3600`.

    Run them in the background and record each lane's count and time.
  - Every Windows session's snapshot comparison is clean, or shows only an allowed
    change.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_windows_test_copy.py -x
  --timeout 30`.
- **The lanes:** `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh
  --lane <lane>`, with the environment variables above, each in the background and
  polled.
- **The dry run** on the frozen copy: `setup`, then `freeze`, then the spec's steps
  through the helper, bracketed.
- **The specs:** re-read against ARTIFACTS.md's format and against the flight-log
  values.

## Implementation Guidance

1. **Read** the four leg entries in the flight log and the `agents.md` blocks.
2. **Add `resize`** with its test.
3. **`setup` and `freeze`** on the current tree.
4. **Rewrite the crew spec,** then dry-run it on the frozen copy step by step, fixing the
   spec wherever reality differs. Record the dry run briefly in the flight log. Make the
   preview captures during the same session.
5. **Revise the operator spec.**
6. **Update `mission.md`.**
7. **The doc sweep.**
8. **The gates.** Run the lanes in the background while you do steps 5–7. Run CI's
   `foreach` verbatim.
9. **Write the flight-log entry,** mark the leg `landed`, and signal `[LAND:leg]`.

## Edge Cases

- **A spec step proves non-executable even after a fix.** Mark it in the spec as
  operator-only (moved to `windows-native-frame-splash`), and say so in the flight log.
  Never leave an unexecutable step in an active crew spec.
- **The operator is active or the session is locked** during the dry run. Follow the
  helper's rules, and report `[BLOCKED:…]` with whatever finished.
- **A lane fails.** Investigate. Fix it if it is caused by this flight's changes;
  otherwise record it with the failing test name, and rerun once to tell a flake from a
  failure.
- **The preview captures must not include operator content.** `capture --window` is
  confined to the tree's frame bounds by the helper; keep it that way.

## Files Affected

- `scripts/windows_test_copy.py`, `tests/test_windows_test_copy.py`: `resize`.
- `tests/behavior/windows-window-chrome.md`, `tests/behavior/windows-native-frame-splash.md`.
- `missions/25-workbench-navigation/mission.md`.
- `CLAUDE.md`, `the_one/agents.md` (sweep fixes only), and `SECURITY-MODEL.md` if it
  lists routes.
- The flight log: the Leg 4 entry. This leg file: status.

## Citation Audit

Checked on 2026-10-06:
- **`mission.md`:** "Window chrome mechanism" (line 227), "Known Issues" (line 257),
  "Ctrl K in WebView2" (around line 266), SC9 (line 129).
- **`tests/behavior/windows-native-frame-splash.md`:** Preconditions "Known gap" and step
  9.
- **`ci/tasks/windows-installer-build.yml`:** the needle `foreach` (line 113, now five
  needles after leg 3).
- **The helper's commands:** as listed in the flight log's leg 1a and 1b entries.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
