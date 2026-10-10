# Squawk 0169: a `#chats/~new/{agent}` hash can be overridden by auto-joining the latest chat

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-10
**Completed**: —

## Report
Seen during the Mission 27 `agent-notes-round-trip` re-run.

**Reproduction:**
1. Start with one existing chat for the agent.
2. Open the Agents destination (`#agents/notes-probe/rules-and-notes`).
3. Navigate the page to `#chats/~new/notes-probe`. In the run this was a
   Playwright `page.goto` to the same document, so only the hash changed.
4. The app joins the **existing** chat (`#chats/{id}`) instead of opening a
   pending new chat, and the next send lands in the old conversation.

**What does work:**
- The Chats list's New chat plus the picker (`App.chat.openPicker`) opens a
  pending chat correctly.
- The same hash navigation works when no chat exists yet.

**Expected:** CLAUDE.md says `#chats/~new/{agent}` is the pending new chat, so
a hash navigation, typed or bookmarked, should open it rather than auto-join.

**Next step:** confirm with a browser test before fixing. If the cause turns
out to be a design question in the chat area's idle auto-join rule, escalate.

## Evidence
- The Executor's executor_notes for run `2026-10-10-21-13-34`, step 3 (the
  first attempt): the URL became `#chats/39aae2cc…` after the hash goto, the
  message landed in that session, and `chat_sessions` gained no row.
- CLAUDE.md "Destination router": `#chats/~new/{agent}` is the pending new
  chat. `href({destination:'chats', create:true, agent})` builds it.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
