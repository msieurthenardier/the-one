# Squawk 0169: a `#chats/~new/{agent}` hash can be overridden by auto-joining the latest chat

**Status**: escalated
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

## Investigation (developer, 2026-10-11)
Not the idle auto-join. Two browser tests were written against `test_flow_new_chat.py`'s `app_with_agent` fixture:
- (a) seed one session (`seed_session`), cold-load Agents, `_nav.goto` to `chats/~new/{agent}`, wait 1.5 s: PASSES (state `pending`, no auto-join). The idle rules only run while `idle`, and `hydrateNew` sets `pending` synchronously.
- (b) FAILS (state `joined`): `start_chat` + `send_first` in the page, `_nav.set_route` to `agents/{agent}/general`, then `_nav.set_route` to `chats/~new/{agent}`; 1.5 s later the state is `joined` on the old session.
Cause: `hydrateNew` in `areas/chat.js` (~line 737), the documented AC9 "rail restore" rule (`agents.md` "The rail restore (AC9)"): a hydrate of `~new/{agent}` while `joined(id)` with `startedFrom = {agent, cid: id}` and no `pickIntent` keeps the session. That is exactly the squawk's scenario (the existing chat was started from this page). A typed or bookmarked hash is indistinguishable from the rail's own link, whose href is that same hash after a first send is interrupted by leaving Chats.
Fixing it means changing the AC9 contract (e.g. making the rail restore not depend on the `~new` hash, or having the rail link point at `sessions/{id}`), a state-machine design decision, so escalated: `[BLOCKED:exceeds-squawk-scope]`. Product code untouched; repro (b) is the test body above (test (a) is a passing guard).

Repro (b):
```python
page.goto(base); _chats.start_chat(page, agent); _chats.send_first(page, "hello")
_nav.set_route(page, f"agents/{_nav.seg(agent)}/general")
_nav.set_route(page, f"chats/~new/{_nav.seg(agent)}")
page.wait_for_timeout(1500)
assert _chats.session_state(page)["name"] == "pending"   # fails: "joined"
```

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

## Disposition
**Escalated** (2026-10-11 turnaround): this squawk fails qualification
criterion 2 (no design decisions).

The behaviour is the deliberate "rail restore (AC9)" rule in the chat area's
state machine, not a stray idle auto-join. `hydrateNew` in
`static/js/areas/chat.js` keeps a `joined(id)` session whose `startedFrom`
matches the agent, and the rail's Chats link reuses the same
`#chats/~new/{agent}` hash. So a typed or bookmarked `~new` hash can't be told
apart from the rail restore. Hash-only moves where the chat was not started in
the same page already work.

The fix needs an operator decision on the AC9 contract, for example pointing
the rail link at `#chats/{id}` so that `~new` always means a new pending chat.
That makes it a small **sortie** (`/mission-control:sortie`): one decision
cluster, the rail link plus the chat-area hydrate, with browser tests. See
the Investigation section above for the repro.
