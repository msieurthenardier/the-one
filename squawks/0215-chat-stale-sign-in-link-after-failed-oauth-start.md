# Squawk 0215: A failed `/api/oauth/start` can leave a stale sign-in link in chat

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: 2026-10-28 (signed off at the Mission 31 Flight 6 landing)

## Report
In chat, when the "Log in" click's `POST /api/oauth/start` fails, `abandon()` deletes the per-flow entry and closes the popup, but a link block that was already rendered for that flow stays in the DOM. A later replayed `auth_required` (reconnect) then shows "Log in" again while the stale block may remain beside it. Benign (the flow already failed), but confusing. Noted by the sortie 04 leg-01 Developer and the flight Reviewer.

## Evidence
- `the_one/interfaces/web/static/js/areas/chat.js::startLoginFlow` — `abandon()` (~l.1254-1257): `delete loginFlows[key]; closeOauthPopup(sourceId);`, no DOM reset.
- The `auth_failed` path already resets the group (`resetLoginGroups`), so the fix pattern exists.

## Corrective Action
M31 F6 L05b: `abandon()` in `areas/chat/sign-in.js` now calls `resetLoginGroups(sourceId)`, which removes the group's `_consentBlock` and shows its `_btn` ("Sign in to {server}") again. Closes at the flight commit.

## Verification
`test_failed_oauth_start_removes_the_block_and_offers_sign_in_again[http-500|network-error]` in `tests/browser/test_oauth_modal_flow.py`: the POST is held until the consent frame is injected, then fails; the block is gone, "Sign in to Srv" is visible, and a replayed auth_required shows one button. Failed first (block still present) before the fix; passes after.

## Sign-Off
**Reviewer**: the Mission 31 Flight 6 flight-end Reviewer for the batch that carried the fix (independent of the Developer)
**Verdict**: `[HANDOFF:confirmed]`; the full gate (unit tier and all 16 browser lanes) passed at the flight's close
**Commit**: on branch `flight/06-chats-and-closing-the-counts`, in the batch commit that carried the fix (batches B1-B5 and the HAT batch), merged with the Flight 6 PR

## Disposition
**Deferred**: found mid-flight in sortie 04, outside its charter — revisit at the next squawk turnaround or the next change to chat's sign-in flow.
