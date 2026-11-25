# Squawk 0407: A replaced proposal's card keeps its Approve and Dismiss buttons

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-24

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
Root cause: the store withdraws the replaced proposal inside `insert`, but `propose_change`
(`the_one/gleepglorp/proposals/tool.py`) pushed only the NEW proposal's `proposal_changed` frame.
The client keeps each card's view as last received, so the replaced card kept `status: "pending"`
until a reload's `proposals_snapshot`.

Fix: after `repo.insert`, the tool lists the chat's proposals, and for each one now `withdrawn` with
`result = {"reason": "replaced", "by": <new id>}` it pushes that proposal's view through the
existing `push_proposal_changed` frame, before the new proposal's frame. The client already folds a
withdrawn view in place (`stateOf` / `renderWithdrawn`), so no client change. No frame shape, store,
lifecycle or schema change. A previously `failed` open proposal that is replaced is covered too.
Browser test `test_a_replaced_proposal_folds_its_card_live_without_a_reload` added to
`tests/browser/test_flow_chat_proposals.py`.

## Verification
Test falsified: with the loop emptied the new test failed (the old card still showed Approve and
Dismiss); with the fix restored it passed.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane gleepglorp-chat`: 83 passed.
- `pytest tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_gleepglorp_proposals_store.py tests/test_gleepglorp_proposals_api.py tests/test_gleepglorp_proposals_tool.py`: 433 passed.
- `ruff check` and `ruff format --check` on `the_one/gleepglorp` and the test file: clean.

Original check:
A browser test: two proposals for the same target in one chat; after the second arrives, the
first card shows the folded "Withdrawn · … replaced" line with no Approve or Dismiss button,
without a reload.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku), batch review of squawks 0403, 0404, 0405, 0407, 0408, 0409 and 0410; Accessibility Reviewer (Sonnet) for 0407 and 0408
**Verdict**: confirmed. The Accessibility Reviewer's two non-blocking notes predate this fix in the card code and are logged as squawks 0411 (a pushed fold drops focus) and 0412 ("below" shown while the new card is held).
**Commit**: `squawk: turnaround 2026-11-24` on squawk/turnaround-2026-11-24
