# Leg: agent-picker-ui

**Status**: completed
**Flight**: [Chat Evolution](../flight.md)

## Objective
Users can choose which agent to use when creating a new chat session, via a dropdown in the Chat sidebar.

## Context
- Leg 02 established: DB-backed sessions with `agent_name`, `new_session` WebSocket action accepts `agent_name`, `session_joined` response includes `agent_name`, `list_sessions` returns `agent_name` from DB
- Design Decision D4: Agent picker is a dropdown in sidebar header, bound per-session. Agent chosen at session creation, not switchable mid-conversation.
- Design Decision D8: UX feedback on state-changing actions (learned from Flight 03)
- `/api/agents` REST endpoint already exists in api.py — returns list of stored agents
- Studio area's flash toast pattern can be referenced for UX feedback if needed

## Inputs
- `the_one/interfaces/web/static/js/areas/chat.js` — current sidebar with "+ new" button, session list grouped by source, WebSocket handlers
- `the_one/interfaces/web/static/styles.css` — current Chat area styles
- `the_one/interfaces/web/app.py` — WebSocket handlers already return `agent_name` in `session_joined` and `session_list` responses

## Outputs
- Agent `<select>` dropdown in sidebar header (next to "+ new" button)
- Dropdown populated from `/api/agents` with "default" always first
- `new_session` sends `agent_name` from dropdown selection
- Session list items show agent name as dimmed subtitle
- Content header shows current session's agent name as badge
- Dropdown refreshed on `activate()` (switching to Chat area)

## Acceptance Criteria
- [x] Agent dropdown in Chat sidebar with "default" + all stored agents
- [x] Dropdown fetches `/api/agents` on connect and on area activate
- [x] Creating session with specific agent sends `agent_name` in `new_session` WebSocket message
- [x] Session list shows which agent each session uses (agent name subtitle)
- [x] Active session header displays current agent name as badge
- [x] `session_joined` response's `agent_name` is read and displayed (`null` from server maps to "default" in UI via `|| 'default'`)
- [x] Switching to Chat after creating agent in Studio shows new agent in dropdown
- [x] Existing chat functionality not broken (send, receive, tool calls, session switching)
- [x] CSS styles for agent picker, session agent badge, content header badge

## Verification Steps
- Open browser, navigate to Chat — dropdown visible with "default" option
- Create agent in Studio → switch to Chat → new agent appears in dropdown
- Select agent from dropdown → click "+ new" → new session created with that agent
- Session list items show agent name subtitle
- Content header shows agent badge for current session
- Send messages — normal chat flow works unchanged

## Implementation Guidance

1. **Sidebar header restructure** (`chat.js`)
   - Replace current `<button class="new-chat">+ new</button>` layout
   - New structure: title on first line, then a row with `<select class="agent-select">` + `<button class="new-chat">+ new</button>`
   - Select starts with `<option value="">default</option>`

2. **`fetchAgents()` function** (`chat.js`)
   - Fetch `/api/agents` — returns array of full config objects, use `.name` property for option value/label
   - "default" never appears in API response — the synthetic default option (value="") handles it
   - Preserve current selection across refreshes
   - Call on WebSocket connect and on `activate()`
   - Catch fetch errors silently (agents list is nice-to-have)

3. **`new_session` click handler** (`chat.js`)
   - Read `agentSelect.value`
   - If non-empty, include `agent_name` in the WebSocket message
   - `ws.send(JSON.stringify({ action: 'new_session', agent_name: selected }))`

4. **`renderSessionList` update** (`chat.js`)
   - Remove source-based grouping (flat list — `list_sessions` from DB has no `source` field, so grouping by source is broken; also remove `.session-group` CSS rules as cleanup)
   - Each session item: two-line layout with title (span) and agent name subtitle (span, dimmed)
   - Agent name shows `s.agent_name || 'default'`

5. **`session_joined` handler** (`chat.js`)
   - Read `data.agent_name`, store as `currentAgentName`
   - Call `updateAgentBadge(data.agent_name)` to set content header badge text

6. **Content header badge** (`chat.js`)
   - Add `<span class="session-agent-badge"></span>` after status in header
   - `updateAgentBadge(name)` sets textContent to `name || 'default'`

7. **`renderHistory` update** (`chat.js`)
   - `messages_to_ui_events` in codec.py sets `source: "restored"` on user messages. The current `renderHistory` prefix logic (`ev.source !== 'web'`) would show `[restored]` prefix. Fix: also exclude `"restored"` from prefix logic (treat like web messages)

8. **`activate()` update** (`chat.js`)
   - If WebSocket is open, call `fetchAgents()` to refresh dropdown
   - Store `_fetchAgents` reference for use in activate

9. **CSS additions** (`styles.css`)
   - `.area-chat #sidebar-header` — change to flex-direction: column with gap
   - `.area-chat .sidebar-actions` — flex row for select + button
   - `.area-chat .agent-select` — styled select matching dark theme
   - `.area-chat .session-item-text` — flex column for title + agent subtitle
   - `.area-chat .session-item-title` — overflow ellipsis
   - `.area-chat .session-item-agent` — small, dimmed text
   - `.area-chat .session-agent-badge` — small badge in content header

## Edge Cases
- **No agents created yet**: dropdown shows only "default" — still functional
- **Agent deleted after dropdown populated**: session creation may fail, but agent picker refreshes on activate
- **Very long agent name**: overflow hidden with ellipsis in both dropdown and session subtitle

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat.js` — agent picker, session badges, activate refresh
- `the_one/interfaces/web/static/styles.css` — agent picker + badge CSS

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
