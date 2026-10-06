# Squawk 0122: Behavior-spec wording fixes raised by the Flight 4 close-gate Validators

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-06
**Completed**: —

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

*(written at completion)*

Edit only the named steps, Preconditions and Variants text in the five specs, and give each
spec an `Updated` line. Do not change any expectation's meaning.

## Verification

- Re-read each edited step against its run log: every expectation the run judged still
  reads the same.
- `grep` confirms no step now names `studio-description` as a testid.

## Sign-Off

*(written at completion)*
