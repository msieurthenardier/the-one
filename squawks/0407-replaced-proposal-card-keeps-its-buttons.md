# Squawk 0407: A replaced proposal's card keeps its Approve and Dismiss buttons

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

When GleepGlorp makes a new proposal for the same target in the same chat, the server withdraws
the open one (`result = {"reason": "replaced", "by": <new id>}`), but the old card in the chat
keeps its Approve and Dismiss buttons. An approve on it changes nothing (the server answers that
the proposal is closed), but until it is clicked the card looks as live as the new one. Found in
the Mission 36 Flight 5 HAT, step 4 (operator, 2026-11-24): proposal 2 (`fetch_url` only) was
replaced by proposal 3; the operator approved 3, then clicked Approve on 2's card.

Not specific to Flight 5's kinds: the replace rule is the one-open-per-chat rule from Flight 2.

## Evidence
- `the_one/gleepglorp/proposals/store.py` `GleepGlorpProposalRepository.insert`: "An open
  proposal that is `failed`, or has the same `target_key`, is marked `withdrawn` (`result =
  {"reason": "replaced", "by": new_id}`)".
- `static/js/areas/chat/proposal-cards.js` `stateOf` and `renderWithdrawn`: the folded
  "Withdrawn · … replaced" line exists, but only once the card's view carries `status:
  "withdrawn"`; nothing re-reads the replaced card's view when the new proposal arrives.
- HAT instance (scratch data dir, port 8486): `gleepglorp_proposals` row 2, `status withdrawn`,
  `result {"reason":"replaced","by":3}`.

## Corrective Action
*(written at completion)*

## Verification
A browser test: two proposals for the same target in one chat; after the second arrives, the
first card shows the folded "Withdrawn · … replaced" line with no Approve or Dismiss button,
without a reload.
