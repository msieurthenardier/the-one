# Leg: trace-event-shape-and-hydration

**Status**: completed
**Flight**: [Chat Response Trace](../flight.md)

## Objective

Thread a paired `parent_message_id` + `tool_call_id` discriminator through every WebSocket `tool_call` and `tool_result` event in the broadcast path (`_broadcast_one` and `_process_and_broadcast`), mirror it in the persisted-history projection (`messages_to_ui_events`), and preserve it across the M07 OAuth `auth_required` pause-and-replay flow — so the frontend (L03) can group tool activity under per-assistant-turn trace shells and the same shape rehydrates from `session.history` on session rejoin.

## Context

- **Flight pre-commit (Design Decisions)**: `parent_message_id` is derived at PROJECTION TIME from the most recent preceding assistant `Message` — NOT a new `Message.id` field on the dataclass. The id is structural (which assistant turn owns the tool activity), not identity-bearing across rejoins. `tool_call_id` is sourced from the existing `ToolCall.id` / `ToolResult.tool_call_id` fields already on the Message dataclasses.
- **Six construction sites + the M07 auth_required event**:
  - `_broadcast_one`'s `tool_call` event construction (`app.py:646-652`)
  - `_broadcast_one`'s `tool_result` event construction (`app.py:664-670`)
  - `_process_and_broadcast`'s `tool_call` event construction (`app.py:741-743`)
  - `_process_and_broadcast`'s `tool_result` event construction (`app.py:773-779`)
  - `messages_to_ui_events`'s `tool_call` projection (`db/codec.py:103-104`)
  - `messages_to_ui_events`'s `tool_result` projection (`db/codec.py:107-113`)
  - `_auth_required_event_from_metadata` build OR its caller (`app.py:566-591`) — both the pause-emission path (in `_broadcast_one` / `_process_and_broadcast`) and the rejoin-snapshot path (`_send_pause_snapshot_if_needed` at `app.py:871-909`) emit this event; both need `parent_message_id` on the wire
- **Iteration semantics verified** (`the_one/agent/core.py:195-196` and `:250-251`): `self.messages.append(response)` precedes `yield response`, and `self.messages.append(tool_msg)` precedes `yield tool_msg`. So at broadcast time, the just-yielded message is `session.agent.messages[-1]`. The parent assistant message for a tool message can always be located by walking `agent.messages` backwards.
- **M07 OAuth path preservation**: `_send_pause_snapshot_if_needed` (`app.py:871-909`) walks `agent.messages` backwards for the last tool message with `tool_result.metadata.is_auth_required`. This walk reads `Message`/`ToolResult.metadata` directly — NOT the WebSocket event stream — so the L02 discriminator change does NOT affect the WALK itself. But the EMISSION (the `auth_required` event sent over WS) must carry `parent_message_id` so the frontend's trace shell can render the consent button INSIDE the right trace.
- **Resume-path explicit handling**: `_resume_paused_session` (`app.py:812-868`) re-enters `_broadcast_one` with messages yielded by `Agent.resume_after_auth()`. Those tool-result messages project against the same `agent.messages`, so the projection rule (look back to the most recent assistant Message) yields the same `parent_message_id` the original (paused) `tool_call` carried — automatically. The integration test in this leg verifies this round-trip.
- **L01 carry-forward (KI awareness)**:
  - Broad pytest summary completes in ~92s, but the process holds for ~90s after the summary because of pre-existing leaked AsyncMock coroutines (mission KI: "post-summary teardown wedge"). When running broad pytest in this leg, **check the SUMMARY LINE for pass/fail — NOT the exit code**. Use `timeout 600 docker exec the-one pytest … 2>&1 | tee /tmp/out.log; tail -5 /tmp/out.log` to capture the summary even if SIGTERM kills the lingering process.
  - The 2 quarantined `test_mcp_sandbox_integration.py` tests (F6-A5-deadlock symptom class) remain skipped — do NOT investigate them in this leg.
  - The chat surface's 2 `chat_with_messages` pixel baselines are still failing (mission KI #1 `.session-agent-badge` race). NOT in L02 scope; L04 fixes them.
- **L02 scope explicitly EXCLUDES**:
  - Pre-existing live-vs-replay event-shape diffs unrelated to the discriminator (e.g. `tool_result.content[:2000]` truncation in live vs untruncated in replay) — these become a Known Issue, NOT an L02 fix
  - Any frontend rendering work — that's L03
  - Any chat CSS changes — that's L03
  - The `app_with_agent` fixture race — that's L04

## Inputs

What exists before this leg runs:

- L01 landed: `tests/conftest.py` now isolates `THE_ONE_DATA_DIR` per pytest session
- Branch `flight/05-chat-response-trace` with L01 changes uncommitted
- Container `the-one` running and reachable via `docker exec`
- `the_one/interfaces/web/app.py` — broadcast paths intact at `app.py:604-809`; auth helper at `app.py:566-591`; pause snapshot at `app.py:871-909`
- `the_one/db/codec.py` — `messages_to_ui_events` at lines 85-114; `message_to_dict`/`message_from_dict` at 32-72 (already round-trip `ToolCall.id` and `ToolResult.tool_call_id` via the persisted dict shape — those fields exist; only the EVENT-STREAM projection drops them today)
- `the_one/llm/base.py` — `Message`, `ToolCall`, `ToolResult` dataclasses (lines 17-44); `ToolCall.id` and `ToolResult.tool_call_id` fields ALREADY present, no schema change needed
- `the_one/agent/core.py` — append-before-yield invariant verified (lines 195-196, 250-251)
- `tests/test_db_codec.py` — existing codec tests; will be extended with discriminator round-trip tests
- `tests/test_app_websocket_pause_resume.py` — existing M07 OAuth pause/resume integration tests; will be extended with discriminator-preservation tests

## Outputs

What exists after this leg completes:

- `parent_message_id` (string) AND `tool_call_id` (string) fields present on every `tool_call` and `tool_result` event broadcast over WebSocket
- Same two fields present on the same events in `messages_to_ui_events` projection (DB rehydration → `session_joined.history` payload)
- `auth_required` event carries `parent_message_id` (it already carries `tool_call_id` via `_auth_required_event_from_metadata` reading `meta.get("tool_call_id")`)
- `session.history` (the in-memory live-replay buffer) contains events with both fields, so the rejoin payload matches what was originally broadcast
- Codec round-trip tests in `tests/test_db_codec.py` verifying both fields land on projected events
- WebSocket integration test in `tests/test_app_websocket_pause_resume.py` verifying that the resumed `tool_result` carries the same `parent_message_id` as the original paused `tool_call`
- Flight log updated with L02 entry: triage of any new failures, file diff summary, test counts before/after
- Leg artifact status: `landed`

## Acceptance Criteria

- [ ] **All six tool_call/tool_result construction sites emit both fields** (auth_required is covered by #2): Every `tool_call` event dict literal has `parent_message_id` (string) and `tool_call_id` (string) keys. Every `tool_result` event dict literal has the same two fields. Verified by reading the diff.
- [ ] **`auth_required` event carries `parent_message_id`**: The event emitted by `_auth_required_event_from_metadata` (or by its caller — implementation choice per flight Acceptable Variations; mild preference for Option A in Step 4) includes `parent_message_id` matching the parent assistant `Message`'s structural id.
- [ ] **`session.add_event` callers pass the discriminator**: `grep -n "add_event" the_one/interfaces/web/app.py` returns 6 call sites total (lines 641, 651, 669, 685, 732, 742, 778 in current code, plus the method def at 166). Of these, the 4 tool-event sites (651, 669, 742, 778 — `tc_event` × 2, `tr_event` × 2) MUST pass event dicts that already contain both fields. The 2 user/assistant sites (641, 685, 732) MUST NOT be touched. Spot-check via diff.
- [ ] **Codec round-trip test passes**: A new test in `tests/test_db_codec.py` constructs a `Message` list with an assistant message bearing 2 `ToolCall`s followed by 2 `Message.tool(ToolResult)` messages, calls `messages_to_ui_events`, and asserts that the projected events carry the expected `parent_message_id` + `tool_call_id` pair.
- [ ] **Multi-turn codec test passes**: A second new test constructs 3 assistant turns (each with a tool call) interleaved with tool results, verifies that each tool_result's `parent_message_id` matches the SAME-TURN assistant's id and is DIFFERENT from the other turns' ids.
- [ ] **Paused-and-resumed integration test passes**: A new test in `tests/test_app_websocket_pause_resume.py` constructs a session where an agent step emits an `auth_required` pause; verifies the broadcast `auth_required` event has `parent_message_id`; simulates resume; verifies the resumed `tool_result` carries the SAME `parent_message_id`. (Use the existing test file's fixture patterns — the F5-L3 test conventions there are well-established.)
- [ ] **M07 pause-snapshot rejoin test passes**: A new test verifies that `_send_pause_snapshot_if_needed`, when invoked on a session with a deferred auth-required tool, broadcasts an `auth_required` event whose `parent_message_id` matches the original paused tool_call's parent.
- [ ] **Narrow gate clean**: `timeout 60 docker exec the-one pytest tests/test_db_codec.py tests/test_app_websocket_pause_resume.py tests/test_agent.py tests/test_agent_context.py --timeout=30 -q 2>&1 | tail -3` shows N passed in ≤ 2.5s where N is `58 + new_tests_added` (4-6 new tests expected).
- [ ] **Broad pytest reaches summary**: `timeout 600 docker exec the-one pytest tests/ -m "not live and not browser and not pixel and not requires_bwrap" --timeout=30 -q --tb=line 2>&1 | tee /tmp/L02-broad.log; tail -5 /tmp/L02-broad.log` shows a clean pytest summary line. **Check the summary line, NOT the exit code** (post-summary teardown wedge is a known L01-documented pre-existing issue). New test count: L01 baseline of 1617 + L02's new tests.
- [ ] **Browser suite baseline preserved**: `timeout 600 docker exec the-one pytest tests/browser/ -m browser --timeout=30 -q 2>&1 | tail -5` shows 315 passing, 35 skipped (or +0 skip delta — L02 should not add any new skips). If new failures appear, INVESTIGATE — they likely indicate the event-shape change broke a browser-suite assumption.
- [ ] **No source-code changes outside scope**: Only `the_one/interfaces/web/app.py`, `the_one/db/codec.py`, `tests/test_db_codec.py`, `tests/test_app_websocket_pause_resume.py`, and the L02 leg + flight log artifacts are touched. Specifically NO `the_one/llm/`, NO `the_one/agent/`, NO `the_one/interfaces/web/static/` (frontend is L03), NO new `Message.id` field anywhere.
- [ ] **No new `Message.id` field**: `grep -n "id:" the_one/llm/base.py` returns the same `id:` lines as before this leg (only `ToolCall.id` already exists; no new `Message.id` field added). Confirms the projection-time-only design decision was honored.
- [ ] **`_send_pause_snapshot_if_needed` walk semantics unchanged**: The walk at `app.py:871-909` reads `agent.messages` and `tool_result.metadata` — confirm via diff that the WALK itself is untouched; only the EMITTED event payload gains `parent_message_id`.

## Verification Steps

How to confirm each criterion is met:

1. **Site coverage (Acceptance #1)**:
   ```bash
   # tool_call event construction sites:
   grep -nE '"type": "tool_call"' the_one/interfaces/web/app.py
   # Should show 2 lines (one in _broadcast_one, one in _process_and_broadcast); each adjacent block should include parent_message_id and tool_call_id.
   grep -nE '"type": "tool_call"' the_one/db/codec.py
   # Should show 1 line; the surrounding dict should include parent_message_id and tool_call_id.

   # tool_result event construction sites:
   grep -nE '"type": "tool_result"' the_one/interfaces/web/app.py
   # Should show 2 lines; each adjacent block should include both fields.
   grep -nE '"type": "tool_result"' the_one/db/codec.py
   # Should show 1 line; surrounding dict includes both fields.
   ```
   Visual inspection confirms each tool_call/tool_result event dict literal includes the two new keys.

2. **`auth_required` discriminator (Acceptance #2)**:
   ```bash
   # The function or its callers add parent_message_id:
   grep -n "parent_message_id" the_one/interfaces/web/app.py | grep -A1 -B1 "auth_required"
   ```
   Visual inspection: either `_auth_required_event_from_metadata` returns a dict with `parent_message_id`, OR the 2-3 caller sites (`_broadcast_one`, `_process_and_broadcast`, `_send_pause_snapshot_if_needed`) inject it into the returned dict before sending.

3. **`session.add_event` symmetry (Acceptance #3)**:
   ```bash
   grep -n "add_event" the_one/interfaces/web/app.py
   ```
   For every tool_call/tool_result `add_event` call: verify the event dict passed in contains both fields.

4. **Codec round-trip test (Acceptance #4 + #5)**:
   ```bash
   timeout 30 docker exec the-one pytest tests/test_db_codec.py -v --timeout=20 -q 2>&1 | tail -10
   ```
   New test names show up (e.g. `test_messages_to_ui_events_includes_discriminator`, `test_messages_to_ui_events_groups_by_turn`); both pass.

5. **Paused-and-resumed integration test (Acceptance #6 + #7)**:
   ```bash
   timeout 60 docker exec the-one pytest tests/test_app_websocket_pause_resume.py -v --timeout=30 -q 2>&1 | tail -10
   ```
   New test names show up (e.g. `test_resumed_tool_result_inherits_parent_message_id`, `test_pause_snapshot_emits_parent_message_id`); both pass.

6. **Narrow gate (Acceptance #8)**:
   ```bash
   timeout 60 docker exec the-one pytest tests/test_db_codec.py tests/test_app_websocket_pause_resume.py tests/test_agent.py tests/test_agent_context.py --timeout=30 -q 2>&1 | tail -3
   ```
   Summary line shows passed count = 58 + new tests; total wall clock ≤ 2.5s.

7. **Broad pytest reaches summary (Acceptance #9)**:
   ```bash
   timeout 600 docker exec the-one pytest tests/ -m "not live and not browser and not pixel and not requires_bwrap" --timeout=30 -q --tb=line 2>&1 > /tmp/L02-broad.log
   tail -5 /tmp/L02-broad.log
   ```
   Summary line matches `=== N passed, M skipped, … in T.Ts ===` where N = 1617 + L02's new tests (target: ~1621-1623); M = 4 (carried L01 skips, unchanged).

8. **Browser suite baseline (Acceptance #10)**:
   ```bash
   timeout 600 docker exec the-one pytest tests/browser/ -m browser --timeout=30 -q 2>&1 | tail -5
   ```
   Summary: 315 passed, 35 skipped, 12 deselected. No new failures.

9. **Scope (Acceptance #11)** — split into source + tests scope checks to disambiguate L01 carry-forward from L02 bleed:
   ```bash
   # 9a. Source check — only app.py and codec.py allowed:
   git diff --name-only main -- \
     ':(exclude)missions/' \
     ':(exclude)tests/' \
     ':(exclude)the_one/interfaces/web/app.py' \
     ':(exclude)the_one/db/codec.py'
   # Expected: empty.

   # 9b. Test scope check — only L02-scope tests + L01 carry-forward allowed:
   git diff --name-only main -- tests/ | grep -vE "^tests/(test_db_codec\.py|test_app_websocket_pause_resume\.py|conftest\.py|browser/test_flow_agent_crud\.py|browser/test_flow_provider_setup\.py|test_mcp_sandbox_integration\.py)$"
   # Expected: empty. The first 2 are L02 scope; the last 4 are L01 carry-forward and must still be present.

   # 9c. Defensive: confirm L01 carry-forward is STILL on the branch (defends against accidental `git reset --hard` etc.):
   git status --short tests/conftest.py tests/test_mcp_sandbox_integration.py tests/browser/test_flow_agent_crud.py tests/browser/test_flow_provider_setup.py
   # Expected: each line shows " M " modified vs main (or " M " for unstaged/staged depending on stage state).
   ```

10. **No `Message.id` field (Acceptance #12)**:
    ```bash
    # 10a. Primary check (catches typed-attribute form):
    grep -nE "^\s+id:" the_one/llm/base.py
    # Expected: only `    id: str` at line 19 (ToolCall.id). No new lines elsewhere.

    # 10b. Defensive broader check (catches other forms — e.g. id with default value, id assignment):
    grep -nE "(^\s*id\s*[:=]|^\s*def\s+id\b)" the_one/llm/base.py | grep -v "tool_call_id"
    # Expected: only line 19 (`    id: str`).
    ```

11. **Pause-snapshot walk unchanged (Acceptance #13)**:
    ```bash
    git diff main -- the_one/interfaces/web/app.py | grep -A3 "_send_pause_snapshot_if_needed"
    ```
    Visual inspection: the `for past_msg in reversed(session.agent.messages):` walk and the `if past_msg.role == Role.TOOL and …` conditional are unchanged. Only the eventual `websocket.send_json(…)` payload construction (which calls `_auth_required_event_from_metadata` and may inject `parent_message_id`) is modified.

## Implementation Guidance

### Step 1 — Introduce a stable id helper

Add a helper function in `the_one/interfaces/web/app.py` (place it near `_auth_required_event_from_metadata` for proximity to the other event-construction helpers):

```python
def _parent_message_id_for(session: "Session", msg_index: int) -> str:
    """Stable structural id for the assistant Message at agent.messages[msg_index].

    Used as the parent_message_id discriminator on tool_call / tool_result
    events so the frontend (L03) can group all tool activity for a single
    assistant turn under a per-turn trace shell.

    Structural, NOT identity-bearing: the id encodes WHICH assistant turn
    owns the activity, not a persistent record id. Rejoining a session from
    DB regenerates ids deterministically from the same agent.messages order.
    """
    return f"{session.id}-msg-{msg_index}"


def _find_parent_assistant_index(messages: "list[Message]") -> int:
    """Walk a message list backwards to find the index of the most recent
    Role.ASSISTANT message with tool_calls.

    Used by _broadcast_one when called in contexts (resume path) where the
    parent_message_id isn't passed in by the caller. Returns -1 if no
    assistant message with tool_calls exists in the list — caller should
    NOT call this in that situation, but the defensive return prevents
    an IndexError.
    """
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.role == Role.ASSISTANT and m.tool_calls:
            return i
    return -1
```

### Step 2 — Update `_process_and_broadcast` to plumb the id through

Track `current_turn_parent_id: str | None = None` as a local variable. Set it when we receive a Role.ASSISTANT message with tool_calls (at `app.py:739-743`). Use it when constructing the tool_call event AND when we receive subsequent Role.TOOL messages (at `app.py:759-779`).

Concrete pattern:

```python
current_turn_parent_id: str | None = None  # near `chunks_seen = False` declaration

async for msg in session.agent.step(user_input, on_chunk=_broadcast_chunk):
    if msg.role == Role.ASSISTANT:
        # ... existing usage / assistant content emission ...
        if msg.tool_calls:
            # Project the parent_message_id for this turn:
            current_turn_parent_id = _parent_message_id_for(
                session, len(session.agent.messages) - 1
            )
            for tc in msg.tool_calls:
                tc_event = {
                    "type": "tool_call",
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "parent_message_id": current_turn_parent_id,
                    "tool_call_id": tc.id,
                }
                session.add_event(tc_event)
                await _send_to_session(session, tc_event)
        # ... existing result_messages append ...
        chunks_seen = False
    elif msg.role == Role.TOOL and msg.tool_result:
        # ... existing auth_required handling — see Step 4 for that path ...
        tr_event = {
            "type": "tool_result",
            "content": msg.tool_result.content[:2000],
            "is_error": msg.tool_result.is_error,
            "parent_message_id": current_turn_parent_id,
            "tool_call_id": msg.tool_result.tool_call_id,
        }
        session.add_event(tr_event)
        await _send_to_session(session, tr_event)
        # ... existing result_messages append ...
```

### Step 3 — Update `_broadcast_one` (used in resume path)

`_broadcast_one` is called from `_resume_paused_session` (`app.py:841-845`) with messages yielded by `Agent.resume_after_auth()`. It doesn't receive a parent_message_id from its caller, so it derives one from `session.agent.messages`:

```python
async def _broadcast_one(
    session: Session,
    msg: Message,
    source: str = "step",
    chunks_seen: bool = False,
) -> None:
    # ... existing docstring ...

    # Resolve parent_message_id for any tool_call/tool_result on this msg.
    # For ASSISTANT messages with tool_calls: the parent is THIS message.
    # For TOOL messages: the parent is the most recent prior ASSISTANT with
    # tool_calls — found by walking agent.messages backwards.
    parent_idx: int = -1
    if msg.role == Role.ASSISTANT and msg.tool_calls:
        # Just-yielded ASSISTANT is agent.messages[-1] per the
        # append-before-yield invariant in agent/core.py:195-196.
        parent_idx = len(session.agent.messages) - 1
    elif msg.role == Role.TOOL and msg.tool_result is not None:
        parent_idx = _find_parent_assistant_index(session.agent.messages)
    parent_id: str | None = (
        _parent_message_id_for(session, parent_idx) if parent_idx >= 0 else None
    )

    if msg.role == Role.ASSISTANT:
        # ... existing usage emission ...
        if msg.content:
            # ... existing ...
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tc_event = {
                    "type": "tool_call",
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "parent_message_id": parent_id,
                    "tool_call_id": tc.id,
                }
                session.add_event(tc_event)
                await _send_to_session(session, tc_event)
    elif msg.role == Role.TOOL and msg.tool_result is not None:
        meta = msg.tool_result.metadata
        if meta and meta.get("is_auth_required"):
            # See Step 4 for the auth_required path with parent_id.
            event = _auth_required_event_from_metadata(meta)
            event["parent_message_id"] = parent_id  # parent_id is known here
            await _send_to_session(session, event)
            return
        tr_event = {
            "type": "tool_result",
            "content": msg.tool_result.content[:2000],
            "is_error": msg.tool_result.is_error,
            "parent_message_id": parent_id,
            "tool_call_id": msg.tool_result.tool_call_id,
        }
        session.add_event(tr_event)
        await _send_to_session(session, tr_event)
```

### Step 4 — Plumb `parent_message_id` into the `auth_required` event

Choose ONE of these mechanisms (per the flight spec's Acceptable Variations):

**Option A — Caller injects after construction**:

```python
event = _auth_required_event_from_metadata(meta)
event["parent_message_id"] = parent_id
await _send_to_session(session, event)
```

Apply at all 3 caller sites: `_broadcast_one`, `_process_and_broadcast`, `_send_pause_snapshot_if_needed`. Each site already knows the parent_id from its iteration context (or can derive it via `_find_parent_assistant_index`).

**Option B — Function takes a parameter**:

```python
def _auth_required_event_from_metadata(
    meta: dict[str, Any], parent_message_id: str | None = None
) -> dict[str, Any]:
    return {
        "type": "auth_required",
        # ... existing fields ...
        "parent_message_id": parent_message_id,
    }
```

Pick whichever you prefer. Option A keeps the function signature stable and isolates the change at the 3 caller sites; Option B is more explicit about the dependency. Both pass review.

For `_send_pause_snapshot_if_needed` (`app.py:871-909`): the existing walk uses `for past_msg in reversed(session.agent.messages):` and has NO index variable. To derive `parent_message_id` correctly, refactor the walk to track the index — either:

```python
# Pattern A: enumerate the reversed list, then convert reverse-index back to forward-index
for rev_i, past_msg in enumerate(reversed(session.agent.messages)):
    if past_msg.role == Role.TOOL and past_msg.tool_result and past_msg.tool_result.metadata and past_msg.tool_result.metadata.get("is_auth_required"):
        tool_idx = len(session.agent.messages) - 1 - rev_i
        parent_idx = _find_parent_assistant_index(session.agent.messages[:tool_idx])
        parent_id = _parent_message_id_for(session, parent_idx) if parent_idx >= 0 else None
        # ... build and send event with parent_id ...
        return

# Pattern B: forward walk with last-match tracking
last_tool_idx = -1
for i, past_msg in enumerate(session.agent.messages):
    if past_msg.role == Role.TOOL and past_msg.tool_result and past_msg.tool_result.metadata and past_msg.tool_result.metadata.get("is_auth_required"):
        last_tool_idx = i
if last_tool_idx >= 0:
    parent_idx = _find_parent_assistant_index(session.agent.messages[:last_tool_idx])
    # ...
```

Either pattern is fine. Pattern A preserves the original walk's early-exit performance characteristic (returns on first hit when walking in reverse). Pattern B is simpler to read but walks the full list. The resulting parent_id matches the original broadcast's parent_id because both derive from agent.messages positions.

**Mild preference for Option A on `_auth_required_event_from_metadata`** (per cycle-1 design review): `_auth_required_event_from_metadata`'s job is "stamp ToolResult.metadata into a payload shape"; `parent_message_id` is NOT in `meta`, it's caller context. Keeping the function signature stable and injecting from the 3 caller sites preserves the function's purpose. But Option B (parameter) is still acceptable if you prefer explicit dependencies.

### Step 5 — Update `messages_to_ui_events` (codec projection)

In `the_one/db/codec.py:85-114`, walk the message list and track the current turn's parent_id:

```python
def messages_to_ui_events(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert stored Messages to UI event format for session replay.

    F5 L02: every tool_call and tool_result event carries a paired
    `parent_message_id` + `tool_call_id` discriminator. `parent_message_id`
    is derived structurally from the index of the most recent preceding
    Role.ASSISTANT message with tool_calls — matching the projection rule
    on the live broadcast side (app.py: _broadcast_one + _process_and_broadcast).
    The frontend (L03) groups events by parent_message_id into per-turn
    trace shells.

    F5 L3: ``tool_result.metadata`` is intentionally NOT projected here.
    Pause state is in-memory only; replay shows historical
    ``auth_required`` tool_msgs as informational text without the
    Login-required affordance. See ``Agent`` class docstring.
    """
    events: list[dict[str, Any]] = []
    current_parent_id: str | None = None
    for i, msg in enumerate(messages):
        if msg.role == Role.SYSTEM:
            continue
        elif msg.role == Role.USER:
            events.append({"type": "user", "content": msg.content, "source": "restored"})
        elif msg.role == Role.ASSISTANT:
            if msg.content:
                events.append({"type": "assistant", "content": msg.content})
            if msg.tool_calls:
                # Replay-side parent_message_id format MUST match the
                # broadcast-side format from app.py. The session id is not
                # available here (codec doesn't see Session); use "replay"
                # as a stable namespace prefix instead. Frontend treats ids
                # as opaque grouping keys — namespace prefix is sufficient
                # to disambiguate.
                current_parent_id = f"replay-msg-{i}"
                for tc in msg.tool_calls:
                    events.append({
                        "type": "tool_call",
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "parent_message_id": current_parent_id,
                        "tool_call_id": tc.id,
                    })
        elif msg.role == Role.TOOL:
            if msg.tool_result:
                events.append({
                    "type": "tool_result",
                    "content": msg.tool_result.content,
                    "is_error": msg.tool_result.is_error,
                    "parent_message_id": current_parent_id,
                    "tool_call_id": msg.tool_result.tool_call_id,
                })
    return events
```

**Note on namespace prefix**: Live broadcast uses `f"{session.id}-msg-{index}"`; codec replay can't access `session.id` (codec is pure dataclass→dict). Use `f"replay-msg-{index}"` as the codec namespace. Frontend MUST treat parent_message_id as an opaque grouping key.

**Important correction from cycle-1 design review**: live and replay event shapes DO coexist within a single `session.history` after `_restore_session` (`app.py:398-406`) sets `existing.history = ui_events` on join — that replaces history with replay-shaped events, and any subsequent live `session.add_event(…)` calls then APPEND live-shaped events to the same list. The grouping outcome remains CORRECT because the distinct namespace prefixes (`{session.id}-msg-N` vs `replay-msg-N`) cannot collide, so the frontend's opaque-key grouping does not falsely merge them. But the originally-claimed "streams never mix" invariant was wrong; rely on the namespace-prefix disjointness instead.

**Invariant comment** (add at the codec call site): if a future refactor changes the live side's id format (e.g. switches from msg-index to turn-counter), the codec MUST be updated symmetrically — they are coupled by the grouping contract, even though the strings need not be identical.

### Step 6 — Codec round-trip tests

Append to `tests/test_db_codec.py` (existing pattern at lines 110+ for `messages_to_ui_events` tests):

```python
# F5 L02 — parent_message_id + tool_call_id discriminator

class TestMessagesToUiEventsDiscriminator:
    def test_single_turn_tool_call_carries_parent_message_id(self) -> None:
        tc = ToolCall(id="tc-1", name="read_file", arguments={"path": "/tmp/x"})
        tr = ToolResult(tool_call_id="tc-1", content="hi")
        msgs = [
            Message.user("read /tmp/x"),
            Message.assistant("", tool_calls=[tc]),
            Message.tool(tr),
        ]
        events = messages_to_ui_events(msgs)
        # filter to tool events
        tc_events = [e for e in events if e["type"] == "tool_call"]
        tr_events = [e for e in events if e["type"] == "tool_result"]
        assert len(tc_events) == 1
        assert len(tr_events) == 1
        # both carry the discriminator pair
        assert tc_events[0]["parent_message_id"] is not None
        assert tc_events[0]["tool_call_id"] == "tc-1"
        assert tr_events[0]["parent_message_id"] is not None
        assert tr_events[0]["tool_call_id"] == "tc-1"
        # same parent for tool_call and its result
        assert tc_events[0]["parent_message_id"] == tr_events[0]["parent_message_id"]

    def test_multi_turn_groups_distinct_parent_ids(self) -> None:
        msgs = [
            Message.user("first"),
            Message.assistant("", tool_calls=[ToolCall(id="t1", name="shell", arguments={})]),
            Message.tool(ToolResult(tool_call_id="t1", content="done1")),
            Message.user("second"),
            Message.assistant("", tool_calls=[ToolCall(id="t2", name="shell", arguments={})]),
            Message.tool(ToolResult(tool_call_id="t2", content="done2")),
        ]
        events = messages_to_ui_events(msgs)
        tc_events = [e for e in events if e["type"] == "tool_call"]
        tr_events = [e for e in events if e["type"] == "tool_result"]
        # two turns, each with one tool_call + one tool_result
        assert len(tc_events) == 2
        assert len(tr_events) == 2
        # distinct parent ids per turn
        assert tc_events[0]["parent_message_id"] != tc_events[1]["parent_message_id"]
        # cross-wiring check: each tool_result groups under ITS OWN turn's tool_call,
        # NOT the other turn's. Catches "tool_result-1 grouped with assistant-2" bugs
        # that a simple distinct-id check would miss.
        assert tr_events[0]["parent_message_id"] == tc_events[0]["parent_message_id"]
        assert tr_events[1]["parent_message_id"] == tc_events[1]["parent_message_id"]
        # And both tool_call_ids pair correctly:
        assert tr_events[0]["tool_call_id"] == "t1"
        assert tr_events[1]["tool_call_id"] == "t2"
```

### Step 7 — Pause/resume integration tests

Read `tests/test_app_websocket_pause_resume.py` first to understand the existing fixture pattern (it has well-established `F5 L3` test conventions from M07). Pay particular attention to the existing `StubAgent` (around line 45 of that file) — it supports the `_deferred_tool_calls` state pattern that `_resume_paused_session` requires for simulating resume. The new L02 tests should reuse this fixture pattern rather than building new mocks.

The new tests follow the existing pattern but assert on the `parent_message_id` field of the broadcast events.

Add tests that:
- Construct a session where an agent step yields an auth_required tool_result
- Capture the broadcast `auth_required` event from the WebSocket subscriber
- Assert `auth_required` event has `parent_message_id` matching the parent assistant message's id
- Simulate resume (clear deferred state, call `_resume_paused_session`)
- Capture the resumed `tool_result` event from the WebSocket subscriber
- Assert the resumed `tool_result` carries the SAME `parent_message_id` as the original `auth_required` event

If the existing test file's fixtures don't support this shape exactly, extend them — but stay within the file's existing conventions (`F5 L3` tests use `_MockMCPClient`-style mocks; the new tests can do the same).

### Step 8 — Run verification suite

Run in this order:
1. Codec tests narrowly: `timeout 30 docker exec the-one pytest tests/test_db_codec.py -v --timeout=20 -q`
2. Pause/resume tests narrowly: `timeout 60 docker exec the-one pytest tests/test_app_websocket_pause_resume.py -v --timeout=30 -q`
3. Narrow gate: covers both above + agent + agent_context
4. Broad pytest: per the leg's pre-leg KI awareness, **check the summary line, NOT exit code**:
   ```bash
   timeout 600 docker exec the-one pytest tests/ -m "not live and not browser and not pixel and not requires_bwrap" --timeout=30 -q --tb=line 2>&1 > /tmp/L02-broad.log
   tail -5 /tmp/L02-broad.log
   ```
   The summary line is the source of truth; the SIGTERM at 600s (if it happens) is the L01-documented teardown wedge.
5. Browser suite: `timeout 600 docker exec the-one pytest tests/browser/ -m browser --timeout=30 -q 2>&1 | tail -5` — must still show 315 passing.

### Step 9 — Update artifacts

- Flight log: append `### L02 — trace-event-shape-and-hydration` entry under Leg Progress with status `landed`, file diff summary, test counts before/after, and any session notes.
- Leg artifact: status header `in-flight` → `landed`.
- Flight artifact: check off `trace-event-shape-and-hydration` in the Legs list.
- DO NOT COMMIT — batched at flight close per agentic-workflow.

### Step 10 — Signal completion

Signal `[HANDOFF:review-needed]`. Do NOT signal `[COMPLETE:leg]` — that's reserved for after the batch commit.

## Edge Cases

- **Empty `agent.messages` at broadcast time** (extremely unlikely): `_find_parent_assistant_index` returns -1; `parent_id` is None. Don't crash — events go out with `parent_message_id: null` and the frontend handles them as "unattributed" (per L03's design choice).
- **Tool_call/tool_result race with assistant message append**: agent/core.py's append-before-yield invariant guarantees `agent.messages[-1]` is the just-yielded message at broadcast time. If a future agent refactor breaks this invariant, the `parent_message_id` derivation goes wrong silently — codec round-trip tests are the canary.
- **The `continue` virtual tool**: `agent/core.py:230-246` appends-but-does-not-yield for the `continue` signal. Since it's not yielded, _broadcast_one/_process_and_broadcast never see it; no parent_message_id derivation needed for these messages. But: the NEXT real tool_call after a `continue` should still derive its parent_message_id from the correct (preceding) assistant message — which is now further back in agent.messages. The `_find_parent_assistant_index` walk handles this naturally.

- **`_process_and_broadcast` iteration-order dependence**: the `current_turn_parent_id` local in Step 2's pattern is set only when a Role.ASSISTANT message arrives, and used for subsequent Role.TOOL messages. This depends on the iteration order invariant established by `agent/core.py:195-196, 250-251` (assistant yields BEFORE its tool_results). `_broadcast_one`'s `_find_parent_assistant_index` fallback is the more defensive pattern that survives a hypothetical reordering. If a future refactor breaks the iteration-order invariant, `_process_and_broadcast` should be re-aligned to use the same look-back walk.

- **`agent.messages` truncation / empty list**: if a future context-pruning feature truncates `agent.messages`, `_find_parent_assistant_index` may return -1 → `parent_message_id` becomes `null` on the wire. **L02→L03 contract**: L03 must handle `parent_message_id: null` events by rendering them either as standalone bubbles outside any trace shell, OR under a synthetic "unattributed" trace shell. L03's leg-design phase will pick the visual treatment. L02 should NOT crash or silently drop these events.
- **Multiple tool_calls in one assistant turn**: all tool_calls within one assistant message share the same `parent_message_id`. Same for all subsequent tool_results until the next assistant message. The `current_turn_parent_id` local in `_process_and_broadcast` is updated only when a Role.ASSISTANT message arrives.
- **The 2 sandbox tests skipped by L01 (F6-A5-deadlock)**: do NOT touch `tests/test_mcp_sandbox_integration.py` in this leg. The F6-A5 quarantines stay as-is.
- **Pre-existing live-vs-replay content truncation**: the live `tool_result.content[:2000]` truncation at `app.py:666` and `app.py:775` vs the untruncated `codec.py:110` projection IS a real divergence, but it's pre-existing and out of L02 scope. Do NOT fix it here. If a test you write trips over it, narrow the test scope to the discriminator fields only.
- **Live broadcast and codec replay produce different parent_id strings**: by design (live uses `session.id-msg-N`, codec uses `replay-msg-N`). Frontend treats them as opaque grouping keys. If a test seems to expect string equality across broadcast and replay, it's the wrong test — fix the test to assert structural equivalence (same number of distinct ids, same grouping pattern), not string equality.
- **Post-summary teardown wedge from L01 KI**: when running broad pytest, the process holds after the summary. ALWAYS check the summary line, NEVER the exit code. Pattern: `pytest … 2>&1 > /tmp/out.log; tail -5 /tmp/out.log`.

- **`tool_result.metadata` projection carve-out**: `codec.py:88-91` documents that `messages_to_ui_events` does NOT project `tool_result.metadata` (where `is_auth_required` lives), so historical paused-but-not-replayed tools surface as informational text on rejoin WITHOUT a Login-required button. L02 preserves this carve-out — discriminator fields are projected, `metadata` is NOT. The M07 OAuth consent button on rejoin comes from `_send_pause_snapshot_if_needed` re-broadcasting an `auth_required` event (which the L02 changes ensure carries the `parent_message_id`), NOT from the replay event stream. Confirm in Step 5's docstring that the existing carve-out language is preserved.

## Files Affected

- `the_one/interfaces/web/app.py` — introduce 2 helpers (`_parent_message_id_for`, `_find_parent_assistant_index`); update `_broadcast_one` (2 sites — tool_call + tool_result construction); update `_process_and_broadcast` (2 sites — tool_call + tool_result construction); update `auth_required` emission at 3 caller sites (`_broadcast_one`, `_process_and_broadcast`, `_send_pause_snapshot_if_needed`). Expected delta: ~40-60 LOC.
- `the_one/db/codec.py` — update `messages_to_ui_events` to track and emit `parent_message_id` + `tool_call_id`. Expected delta: ~15 LOC + docstring update.
- `tests/test_db_codec.py` — add `TestMessagesToUiEventsDiscriminator` class with 2 new tests. Expected delta: ~30-40 LOC.
- `tests/test_app_websocket_pause_resume.py` — add 2 new tests (one for normal step path, one for `_send_pause_snapshot_if_needed` rejoin path). Expected delta: ~50-80 LOC depending on fixture reuse.
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight-log.md` — append L02 entry.
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight.md` — check off `trace-event-shape-and-hydration` in Legs list.
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/legs/02-trace-event-shape-and-hydration.md` — status header update.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (run every verification step; capture output to flight log)
- [ ] Tests passing (codec + pause-resume + narrow gate + broad pytest summary + browser suite)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header) — NOT `completed`
- [ ] Check off this leg in flight.md
- [ ] DO NOT commit (per agentic-workflow: review + commit are batched at flight close)
- [ ] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

10 source-code citations verified against current code at leg design time:

| Citation | Class | Notes |
|---|---|---|
| `the_one/interfaces/web/app.py:566-591` (`_auth_required_event_from_metadata`) | OK | Verified — function definition begins at line 566; docstring + return at 583-591 |
| `the_one/interfaces/web/app.py:604-670` (`_broadcast_one`) | OK | Verified — function spans 604-670; `tool_call` event at 646-652; `tool_result` event at 664-670 |
| `the_one/interfaces/web/app.py:673-809` (`_process_and_broadcast`) | OK | Verified — function spans 673-809; `tc_event` construction at 741-743; `tr_event` at 773-779 |
| `the_one/interfaces/web/app.py:812-868` (`_resume_paused_session`) | OK | Verified — calls `_broadcast_one(session, msg, source="resumed")` at lines 841-842 |
| `the_one/interfaces/web/app.py:871-909` (`_send_pause_snapshot_if_needed`) | OK | Verified — walks `agent.messages` backwards for last tool with `metadata.is_auth_required` |
| `the_one/db/codec.py:85-114` (`messages_to_ui_events`) | OK | Verified — function emits `tool_call` (line 104) and `tool_result` (lines 107-113) events WITHOUT discriminator fields today |
| `the_one/db/codec.py:32-72` (`message_to_dict` / `message_from_dict`) | OK | Verified — already round-trips `ToolCall.id` (line 12) and `ToolResult.tool_call_id` (line 17) via the persisted dict shape |
| `the_one/llm/base.py:17-44` (`ToolCall`, `ToolResult`, `Message` dataclasses) | OK | Verified — `ToolCall.id: str` at line 19; `ToolResult.tool_call_id: str` at line 26; no `Message.id` field (load-bearing for the projection-time-only design) |
| `the_one/agent/core.py:195-196` (append-before-yield for assistant) | OK | Verified — `self.messages.append(response)` precedes `yield response` |
| `the_one/agent/core.py:250-251` (append-before-yield for tool) | OK | Verified — `self.messages.append(tool_msg)` precedes `yield tool_msg` |

All citations OK. No drift; no rewrites required.
