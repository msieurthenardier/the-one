# Squawk 0122: Behavior-spec wording fixes raised by the Flight 4 close-gate Validators

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-06
**Completed**: 2026-10-06

## Report

Every close-gate run at Mission 25 Flight 4 passed (96 of 96), but the Validators flagged
wording that a driver had to work out, or that a stricter Validator could misjudge. These
are clarifications to the specs, with no behaviour change:
- **`jump-to-palette`:**
  - Step 8: "lands on Chats" — the hash is `#chats/{last chat}` with the picker over it.
  - Step 9: name "Description (`id` `studio-description`)". It has no testid, and an
    Executor's testid selector failed.
  - Step 12: count dialogs while the confirm is open.
  - Variants: the expected scrim alpha per theme (Light 0.3, Dark 0.5), and which
    element's colour "where text legible" reads.
- **`shell-navigation-smoke`:**
  - Step 2: the baseline option is inferred (the radiogroup cannot be read without
    navigating) and confirmed at step 6's pre-state.
  - Step 8: require a true reload, proven by a lost window marker, not a same-document
    hash change.
  - Step 9: `#admin/` is rewritten before the first observable sample; assert "not
    `#admin/` at first sample and after the reload".
  - Preconditions: an empty instance takes the setup-guidance branch.
- **`chat-roundtrip`:**
  - Step 3: name `GET /api/chat/sessions` as the "nothing is created yet" check, and note
    that the Dark variant sees the Light run's session.
  - Step 4: bound "tinted, not a loud fill" (for example background alpha at most 0.15,
    with legible text), and sample right after Send.
- **`start-a-chat`:**
  - Frames are judged per step, and the report lists each step's frame actions; a recorder
    restart adds a reload sequence.
  - Step 11's "in the drawer header's right corner" is geometric: the toggle is not a DOM
    descendant of the drawer.
- **`workbench-navigation`:**
  - Set a fresh `window` marker before each step that needs one, because steps 10 and 11
    reload.
  - Step 13: while the dialog is open the hash reads the previous entry.
  - Name the screenshot and accessibility snapshot as the primary evidence; the current
    text is goldfinch fallbacks.

## Evidence

The Validator closings in `tests/behavior/{jump-to-palette,shell-navigation-smoke,chat-roundtrip,start-a-chat,workbench-navigation}/runs/2026-10-06-06-01-26.md`.

## Corrective Action

Wording only, in the five specs, each with an `Updated` line and no expectation changed:
- `jump-to-palette`: step 8's hash is `#chats/{chatId}` with the picker over it; step 9 and
  its expectations name the field by `id` `studio-description` (no `data-testid`, select by
  `#studio-description`); step 12 counts dialogs while the confirm is open; the Variants
  state the scrim alpha (Light 0.3, Dark 0.5) and which element's colour the "where" text
  check reads.
- `shell-navigation-smoke`: an empty instance takes the setup-guidance branch
  (Preconditions); step 2's baseline is inferred (the `theme-preference` key) and confirmed
  at step 6's pre-state; step 8 requires a true reload proven by a lost `window` marker;
  step 9 asserts "not `#admin/` at the first sample and after the reload".
- `chat-roundtrip`: step 3 names `GET /api/chat/sessions` as the "nothing is created yet"
  check and notes the Dark variant sees the Light run's session; step 4 bounds "tinted"
  (background alpha at most 0.15, legible text) and says to sample right after Send.
- `start-a-chat`: frames are judged per step with each step's frame actions listed, and a
  recorder restart adds a reload sequence; step 11's "drawer header's right corner" is a
  geometric criterion; step 13 names the Description field by `id`.
- `workbench-navigation`: a fresh `window` marker before each step that needs one; step 13
  says the hash reads the previous entry while the dialog is open; the screenshot and
  accessibility snapshot are named the primary evidence (the goldfinch text is the
  fallback), and the apparatus line names the CDP Chromium.
**Skipped:** none of the squawk's items. The Validators' other notes (the Dark "fresh
context" record, the pending-row wash threshold, the step 14 lapse, the Dark scrim as an
open question) are not in the squawk's list and were left alone. `list-and-detail.md` was
not touched (leg 1a owns it).

Commit: pending the Flight 6 legs 1-3 commit.

## Verification

- Each edited step re-read against its run log (`.../runs/2026-10-06-06-01-26.md`): every
  expectation the run judged still reads the same.
- `grep -n "studio-description" tests/behavior/*.md`: each hit names it as an `id`; none as a
  testid.

## Sign-Off

**Reviewer**: Developer agent, Mission 25 Flight 6 leg 3 (the flight-end review confirms)
**Verdict**: confirmed
**Commit**: pending the Flight 6 legs 1-3 commit
