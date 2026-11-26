# Squawk 0429: Purge deletes an agent's chats without stopping or evicting open sessions

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-26
**Completed**: —

## Report
The agent's **Purge now** (`DELETE /api/agents/{name}/chat/sessions`) deletes every chat for the agent. It does not cancel a turn in progress, tell open windows, or evict the cached sessions. A chat open during a purge keeps its cached `Agent` and can keep running a turn for a chat that no longer exists. Sortie 20 closed exactly this gap for agent delete; Purge was outside its charter. Found by the sortie 20 debrief (`sorties/20-deleting-an-agent-deletes-its-chats/flight-debrief.md`).

## Evidence
- `the_one/interfaces/web/api.py::delete_agent_chat_sessions` (`:5195`) calls `ChatSessionRepository.delete_all_for_agent` and the two routine repositories, and nothing else.
- `the_one/interfaces/web/app.py::_evict_deleted_sessions` (`:1751`) does the cancel, the `session_deleted` broadcast and the eviction, given chat ids. Agent delete and the purge sweep use it; this route does not.

## Corrective Action
*(written at completion)*

Suggested direction: have the route collect the agent's chat ids before deleting (or have `delete_all_for_agent` return them), then call `_evict_deleted_sessions(ids)`, as `delete_agent` does.

## Verification
A route test, like sortie 20's AC8 in `tests/test_agent_delete_cascade.py`: with a cached session and an in-flight task for the agent, a purge cancels the task, a subscriber receives `session_deleted`, and the id leaves `_sessions`.

## Sign-Off
*(written at completion)*
**Reviewer**: —
**Verdict**: —
**Commit**: —
