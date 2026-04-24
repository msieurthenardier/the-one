# Leg: uat-and-alignment

**Status**: completed
**Flight**: [Chat Evolution](../flight.md)

## Objective
End-to-end verification of the full chat evolution feature set.

## Context
- Legs 01-03 implemented: schema V2, persistence bridge, agent picker UI
- This is a guided UAT — human performs verification, Flight Director guides

## Acceptance Criteria
- [x] Fresh start: no prior sessions, create session, send messages, verify sidebar
- [x] Server restart: sessions persist, history intact, conversation continues
- [x] Agent picker: create agent in Studio, switch to Chat, select it, verify config active
- [x] Default agent: sessions with no agent selection work and persist
- [x] Multiple agents: sessions for different agents coexist, correct history per session
- [x] Delete session: removed from sidebar and DB
- [x] REST API: `POST /api/chat` with and without `agent_name`
- [x] Stale data: create agent in Studio, switch to Chat, dropdown is fresh
- [x] UX: visible agent badge in header, agent subtitle on session items

## Verification Steps

1. **Fresh start** — Delete DB file, start server, verify Chat loads with empty sidebar, create session, send a message, verify it appears
2. **Session persistence** — Send a few messages, restart the server, verify sessions appear in sidebar, rejoin and see full history, send another message to confirm context intact
3. **Agent picker** — Go to Studio, create a test agent with a distinctive system prompt, switch to Chat, verify the agent appears in dropdown, select it and create new session, verify the agent badge shows in header and session list
4. **Default agent** — Create a session without selecting an agent, verify it works and persists across restart
5. **Multiple agents** — Create sessions with different agents, verify each has its own history, switching between them shows correct messages
6. **Delete session** — Delete a session from sidebar, verify it's gone, verify it's gone from DB (`/api/chat/sessions`)
7. **REST API** — `curl -X POST http://localhost:8080/api/chat -H 'Content-Type: application/json' -d '{"message":"hello"}'` — verify response
8. **Stale dropdown** — Create new agent in Studio, switch to Chat without refreshing, verify dropdown has new agent
9. **Visual check** — Agent badge visible in content header, agent subtitle on each session item, dropdown styled correctly

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
