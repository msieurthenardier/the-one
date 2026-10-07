# Leg: mission-close

**Status**: in-flight
**Flight**: [Alignment](../flight.md)

## Objective

Close Mission 25. The leg has four parts:
- **Record acceptance:** the reference spec's register and deviations sweep (§15 and §13),
  the mission's success criteria, and the Known Issues.
- **Re-run** the behavior specs this flight touched.
- **Run every gate.**
- **Update the published design system.**

The operator answered the release question (DD9) after the walk: **a patch release,
v0.10.1**, cut after the merge.

## Context

- **Legs 1a–4d** are committed (`52f7612`), and leg 5 (the light walk) is accepted. Its
  inline batch is committed with leg 5.
- **The operator's acceptance record** is in the flight log ("Decisions" and leg 5):
  - SC8: the operator's own v0.10.0 use, plus the light walk (DD18);
  - SC9: "All fine";
  - the decision sheet: all kept, plus #225 for narrow widths.
- **Operator-accepted SC8 deviations from this flight:**
  - DD13: section labels, against §3's group label;
  - DD14: 12-hour times, against §5.1's Today `HH:MM`;
  - DD15: start pages, against the root empty states in §6 and §7;
  - DD16: the composer's width, against §5.5's 760px.

  DD10's "Available models" label is additive.
- **The Known Issue "Ctrl K in WebView2"** (mission.md, carried from Flight 4 DD9 to
  Flight 5). The operator's SC9 answer covered Ctrl K in the packaged app ("All fine",
  2026-10-06), so it closes.

## Acceptance Criteria

**Developer (autonomous):**
- [ ] **§15 sweep** (`missions/25-workbench-navigation/reference/reference-spec.md`):
  - every register row A1–A32 gains its resolution: the flight and DD or leg that settled
    it, or "accepted as is" or "carried" with a reason;
  - each resolution is found in the flight logs and debriefs (`flights/*/flight-log.md`,
    `flight-debrief.md`) and cited there;
  - add a Status column, or a "Resolution" line per row, whichever keeps the table
    readable.
- [ ] **§13 additions:**
  - a short "Operator-accepted deviations (Flight 6)" table after D1–D5, covering DD13,
    DD14, DD15 and DD16, each with what the board drew, what ships, and the operator's
    words or date;
  - D1–D5 stand unchanged.
- [ ] **mission.md:**
  - the Known Issue "Ctrl K in WebView2" is marked closed, with the evidence: the
    operator's SC9 answer, plus the Flight 5 test-copy finding (9) that a real Ctrl+K
    opens the palette;
  - the open questions still unchecked are resolved or carried, each with a pointer;
  - **do NOT tick the SC checkboxes or the Flight 6 line.** The Flight Director does that
    after the gates.
- [ ] **Docs.**
  - **Read through** `CLAUDE.md` and `the_one/agents.md`: every behaviour Flight 6 changed
    is described. Fix any gap.
  - **The 422s** (DD4, under Settings item pages).
  - **`App.focusAfter`** (DD2).
  - **The WebSocket cancel contract** (DD5).
  - **The section labels** (DD13).
  - **12-hour times** (DD14).
  - **The start pages** (DD15).
  - **The composer's width** (DD16).
  - **`text_select`** (DD17).
  - **The MCP error** (DD19).
  - Keep the CLAUDE.md additions brief. It already carries the detail in places.
- [ ] **Gates**, all with `THE_ONE_TEST_NETNS=1`, run one at a time after the Flight
  Director's behavior runs finish (the Flight Director says when):
  - `TEST_TIMEOUT=3000 make test-unit`;
  - all six browser lanes, with `contracts` under `THE_ONE_REQUIRE_WEBKIT=1` and `shared`
    under `TEST_TIMEOUT=3600`;
  - the static guards;
  - `ruff check` and `ruff format --check`.

  Record each with its counts and duration in the flight log. A failure is investigated
  and fixed, or reported to the Flight Director. Never skip it.

**Flight Director:**
- [ ] **Behavior re-runs** on dedicated instances (ports 8487 and up, scratch data dirs,
  never 8484 or 8485):
  - **Chat:** `start-a-chat` and `chat-roundtrip` (leg 2's WebSocket changes; `start-a-chat`
    step 2 was re-authored in 4b);
  - **Re-authored in leg 4c:** `list-and-detail`, `workbench-navigation`,
    `shell-navigation-smoke` and `studio-agent-crud`;
  - **Provider page:** `system-provider-config` (the 422 display, the labels, focus).

  Not re-run, with the reason:
  - `jump-to-palette` (wording only, leg 3, and no product change touches the palette);
  - `windows-window-chrome` (wording only, leg 3);
  - `windows-native-frame-splash` (the operator's SC9 answer);
  - `kb-studio-round-trip` (only `kb-panel-title`'s opt-out class changed, and it renders
    as before).
- [ ] **Each run log is committed.** A failing step is fixed (a new commit, never an
  amend) or accepted by the operator as a known issue.
- [ ] **The published design system**
  (`https://claude.ai/artifact/51jpj1RcXp18MehEQAteWs`) describes the DD13 label recipe
  (SC7).
- [ ] **mission.md SC1–SC10** are ticked with their evidence. The flight is marked
  `landed` (Phase 3), then the flight debrief, then the mission debrief.
- [ ] **PR #227** is marked ready and merged. Then v0.10.1 is released as v0.10.0 was:
  - a release branch bumping the version;
  - a PR, merged;
  - the tag, the Windows installer workflow, and the release notes.

## Files Affected

- `missions/25-workbench-navigation/reference/reference-spec.md`,
  `missions/25-workbench-navigation/mission.md`.
- `CLAUDE.md`, `the_one/agents.md` (gaps only).
- `tests/behavior/*/runs/*.md` (the run logs).
- The flight log.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
