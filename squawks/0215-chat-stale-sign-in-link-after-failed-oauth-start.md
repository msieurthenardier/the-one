# Squawk 0215: A failed `/api/oauth/start` can leave a stale sign-in link in chat

**Status**: deferred
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: —

## Report
In chat, when the "Log in" click's `POST /api/oauth/start` fails, `abandon()` deletes the per-flow entry and closes the popup, but a link block that was already rendered for that flow stays in the DOM. A later replayed `auth_required` (reconnect) then shows "Log in" again while the stale block may remain beside it. Benign (the flow already failed), but confusing. Noted by the sortie 04 leg-01 Developer and the flight Reviewer.

## Evidence
- `the_one/interfaces/web/static/js/areas/chat.js::startLoginFlow` — `abandon()` (~l.1254-1257): `delete loginFlows[key]; closeOauthPopup(sourceId);`, no DOM reset.
- The `auth_failed` path already resets the group (`resetLoginGroups`), so the fix pattern exists.

## Corrective Action
*(written at completion)*
Likely: have `abandon()` reset that source's login group the way `auth_failed` does (remove the block, un-hide "Log in").

## Verification
A browser test in `tests/browser/test_oauth_modal_flow.py`: stub `/api/oauth/start` to fail after a consent block is shown; assert the block is gone and "Log in" is visible.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition
**Deferred**: found mid-flight in sortie 04, outside its charter — revisit at the next squawk turnaround or the next change to chat's sign-in flow.
