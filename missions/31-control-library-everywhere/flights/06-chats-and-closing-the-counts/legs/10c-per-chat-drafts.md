# Leg: per-chat-drafts

**Status**: completed
**Flight**: [Chats, and closing every count to zero](../flight.md)
**Origin**: HAT step 4 (operator, 2026-10-28). Staged images and typed text followed the operator to another chat. Operator choice: "Per-chat drafts". New behaviour, so it goes through the fix-vs-feature gate.

## Objective
Each conversation keeps its own unsent draft: the message-box text and the staged images.
- Switching away from a chat saves its draft.
- Coming back restores it.
- Opening another chat, or a pending new chat, shows that chat's draft, which is empty if it has none.
- Drafts live in memory for this window only; a reload loses them.

## Context
- **There is one composer for the whole area.**
  - `App.ui.composer` is built once in `areas/chat.js` and reached through `ctx.composer`: `getValue`/`setValue` and `send.setInputValue` (which re-fits).
  - Staged images are a closure array in `areas/chat/attachments.js`: `stagedImages`, `clearStagedImages`, `prependStaged`, `staged()`, `renderAttachments`.
- **Nothing clears or swaps either one on a conversation change today.**
  - The chat state machine's transitions (`areas/chat/session-flow.js`: join, pending/pick, leave, start) and `discardHeld` (which now discards the held queue, leg 10a) are where a switch happens.
  - `session-flow.js` ~286 clears staged images once a start succeeds. Around ~320-329, a failed start puts the message and the first held message back into an empty box.
- **The draft key.** A joined chat uses its session id. A pending new chat uses `~new/{agent}`; on the first send, the session that creates takes over its draft, which by then is empty because the send consumed it. A chat that is "starting" uses its client id, which is also the session id.

## Design (to confirm at design review)
- **Storage.** `state.drafts[key] = { text, images }`, in memory, in `areas/chat.js` state.
- **Save.** Save the outgoing chat's draft at the single point where the active conversation changes, before the composer is reused. Find that seam in `session-flow.js`. Store the current text and a copy of the staged images. An empty draft deletes its key.
- **Restore.** When the new conversation becomes active (pending, joining or joined), restore its draft with `setInputValue(text)` plus a new `attachments.setStaged(images)` that re-renders the chips. With no draft, clear both.
- **Interactions.**
  - **Sending:** a successful send already clears its text and images, so the draft becomes empty.
  - **The held queue (10a):** held messages are not part of the draft and are still discarded on a switch.
  - **Delete:** deleting a chat drops its draft.
  - **Reconnect and re-join of the same chat:** the draft is untouched, since the same key stays active.
  - **Leaving Chats and coming back** (to Agents, say): restore the open chat's draft. Check this: the area may tear down the composer, or keep it.
  - **A failed start:** keep today's behaviour (the message goes back into the box) under the pending key.
- **Accessibility.** The staged-image live announcement ("Image staged") must not re-announce on a restore. A restore is silent. The message box keeps today's focus rules, so no focus jump on a restore.

## Acceptance Criteria
- [ ] In chat A, type text and stage two images, then open chat B: B's composer is empty with no chips. Return to A: the text and both images are back. Sending from A clears A's draft.
- [ ] A pending new chat starts empty. A draft typed in it survives a trip to another chat and back, to the same pending agent.
- [ ] A held-queue message is not carried in a draft (10a's discard on a switch still holds). Deleting a chat drops its draft.
- [ ] A restore makes no "Image staged" announcement and moves no focus.
- [ ] Browser tests cover these cases (chats lanes). CLAUDE.md "Chat composer" and `the_one/agents.md` are updated. Add ledger row 50.

## Verification
`THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats -x` and `--lane chats-transcript -x`; the static guards; then the HAT re-walks it.

## Design Review Amendments (cycle 1, Developer/Sonnet, 2026-10-28: approve with changes; these take precedence)
- **One helper, `switchDraft(newKey)`, in `session-flow.js`.** There is no single seam: `clearConversation` runs after `chatState` has already moved. So the helper keys off a tracked owner, `state.draftOwner`.
  1. If `newKey === draftOwner`, return. This makes a same-id re-join (`rejoinForUpdate`, `session_updated`) a no-op that keeps the caret and the chips.
  2. Save `{text: composer.getValue(), images: staged().slice()}` under `draftOwner`. An empty draft deletes the key.
  3. Restore `drafts[newKey]`, or empty when there is none, through `setInputValue` and a new silent `attachments.setStaged(images)` (`stagedImages = images.slice(); renderAttachments()`; it never announces).
  4. Set `draftOwner = newKey`.
- **Call sites:**
  - `pickAgent`: `n:{agent}`.
  - `openConversation`: `s:{id}`.
  - `resetToIdle` and `clearConversation`: `null`. Idle clears the text and chips: text typed into the welcome state has nothing to attach to.
  - Each call goes after 10a's held-queue discard.
  - The socket reconnect re-join does NOT call it.
- **Keys.** `state.drafts` is `Object.create(null)`, and keys carry a prefix: `s:{id}` for a session, `n:{agent}` for a pending new chat.
- **Promotion.** While a chat is `starting`, the key stays `n:{agent}`. On `session_joined` with `fromStart` (socket.js ~174), set `draftOwner = 's:'+id` without touching the composer. Anything typed while starting carries over. A test covers it.
- **Deletes and pruning.**
  - `session_deleted` drops `drafts['s:'+id]`, whether or not that chat is open. The `join_failed` and `heal` paths drop the failed chat's draft.
  - Each `session_list` prunes draft keys that are not `draftOwner`, not `n:` keys, and not in the listed ids. This covers a delete from another tab or a purge.
- **Image reads in flight.** `addFiles` captures `draftOwner` at its start. In `onload`, if the owner has changed, the image is pushed silently into `drafts[captured].images` instead of the current chips.
- **Unchanged:**
  - A failed start restores into an empty box under `n:{agent}`.
  - A switch away while `starting` loses a failed start's message (existing behaviour, stated).
  - The chat area is never destroyed, so leaving Chats and coming back keeps the composer as it is. That only gets a test.
- **Tests.** New `tests/browser/test_flow_chat_drafts.py`, added to the `chats-transcript` list in `scripts/run-tests.sh` (`chats_transcript_pat`), with `tests/test_run_tests_lanes.py` passing. Cover:
  - text and two images in chat A, then B is empty, then A again is restored;
  - a restore leaves `chat-attachments-status` text unchanged and moves no focus;
  - a pending draft survives a trip to a chat and back, and a trip to Agents and back;
  - deleting the open chat, and a non-open one;
  - text typed while starting survives the promotion;
  - a same-id `session_updated` keeps the caret and the chips.

  Also scan the existing tests that assume text carries across a switch (`test_flow_chat_composer*`, `_image_attach`, `_start_flow`, the picker tests).
- **Status:** ready.
