# Leg: 07-flow-test-chat

**Status**: completed
**Flight**: [Browser Test Foundation](../flight.md)

## Objective

Add the third end-to-end browser flow test: starting from an app pre-seeded with a `mock` provider AND an agent, drive Chromium through the chat flow — connect WebSocket, see auto-created session with the agent badge, send a user message, see the mock provider's deterministic assistant response render. This completes the regression net for the three M03-era critical flows. Add `data-testid` attributes for the chat input, send button, and per-message rendering.

## Context

- This is the **third and final flow test** before the CI integration leg. After this lands, the regression net for provider-setup, agent-CRUD, and chat is complete.
- Uses the `app_with_agent` fixture from leg 04 (mock provider + agent already seeded). The agent has `system_prompt = "You are a test agent."` and references the mock provider with no scripted response config — so the mock provider's default `complete()` returns `"Mock response from the mock provider."`.
- **WebSocket flow** (verified): `chat.js:263-385`
  - `connect()` opens `ws://host/ws`. On `onopen`, status text changes from "connecting..." to "connected" (`chat.js:267-273`)
  - Then chains: `checkSetupState()` → `fetchAgents()` → `ws.send({action: 'list_sessions'})`
  - Server responds with `session_list` event. If no current session AND setup complete (= an agent exists), auto-sends `{action: 'new_session'}` (line 286-293) — uses `agentSelect.value` if a non-default agent is selected; otherwise omits agent_name (server uses default)
  - Server creates session, responds with `session_joined` event → `currentSessionId` set, `currentAgentName` set, `updateAgentBadge` writes to `.session-agent-badge`, history rendered (empty for new session), session list refreshed
  - User types and clicks Send → `ws.send({message: text})` → server runs agent step → emits `user`, `usage`, `assistant`, `done` events
  - Each event triggers `addMsg(cls, text)` to append a `.msg.{cls}` div in `.messages`. `done` event re-enables the send button (busy=false)
- **Mock provider response**: Per leg 02, `MockProvider.complete()` returns `Message.assistant(content="Mock response from the mock provider.", ...)` when `config["response"]` is unset. The leg-04 seeder doesn't set `config["response"]`, so this default applies.
- **Agent selector** (`.agent-select`, line 22): The auto-created session uses `agentSelect.value` (`chat.js:290-292`). The dropdown is populated by `fetchAgents()` which runs in the WebSocket onopen chain *before* `list_sessions` is sent. With one seeded agent, the dropdown's only option is "test-agent" and `agentSelect.value === "test-agent"` by the time `list_sessions` arrives — so the auto-created session uses the seeded agent. Test verifies by asserting the agent badge reads "test-agent" after `session_joined`.

- **`.session-agent-badge` selector**: `chat.js:36, 76-78`. `agentBadgeEl.textContent = name || 'default'`. Set on `session_joined`.

- **Status element**: `.status` (line 35). Changes from "connecting..." to "connected" on WebSocket open.

## Inputs

- Branch `flight/01-browser-test-foundation`, legs 01-06 landed (uncommitted)
- `tests/browser/conftest.py` has `app_with_agent` fixture (subprocess + 1 mock provider + 1 agent named "test-agent" with model "mock-default")
- Mock provider returns deterministic default response when no `config["response"]` set
- Test baseline: 350 passed, 15 deselected (post-leg-06)

## Outputs

- `tests/browser/test_flow_chat.py` (new) — single end-to-end chat flow test
- `the_one/interfaces/web/static/js/areas/chat.js` — add `data-testid` attributes to:
  - The chat text input (`data-testid="chat-input"`)
  - The Send button (`data-testid="chat-send-btn"`)
  - Each message element rendered via `addMsg` (`data-testid="message"`)
- (3 testids added — within budget)

## Acceptance Criteria

### data-testid attributes

- [x] `chat.js` content-DOM template (line ~46-49) — input has `data-testid="chat-input"`, Send button has `data-testid="chat-send-btn"`
- [x] `chat.js` `addMsg(cls, text)` function (line ~80-86) — created `div.msg.{cls}` element gets `data-testid="message"` set via `el.setAttribute(...)`

### Test

- [x] `tests/browser/test_flow_chat.py` exists with one `@pytest.mark.browser` test: `test_chat_send_receives_mock_response`
- [x] Test uses `app_with_agent` and `page` fixtures
- [x] Test asserts the following sequence:
  1. Open `#chat` (default area). WebSocket connects → `.status` text becomes "connected"
  2. Wait for the agent badge to show "test-agent" (session auto-created with seeded agent)
  3. Type "hello" into `[data-testid="chat-input"]`
  4. Click `[data-testid="chat-send-btn"]`
  5. Wait for the user message to render: `[data-testid="message"]` with class `user` and text "hello"
  6. Wait for the assistant message to render: `[data-testid="message"]` with class `assistant` and text "Mock response from the mock provider."
  7. Verify the Send button is re-enabled (busy=false after `done` event)

### Suite-level

- [x] `pytest -m browser tests/browser/ -v` shows 8 passed (smoke + 2 app-fixture + 2 seeder + 3 flow)
- [x] Default `pytest tests/`: 350 passed, 16 deselected (was 15; +1)
- [x] No existing test regressions
- [x] `ruff check tests/browser/` and `ruff format --check tests/browser/` clean

## Verification Steps

1. **Test passes**: `pytest -m browser tests/browser/test_flow_chat.py -v --timeout=60`
2. **Repeat-run stability** (3 consecutive runs):
   ```bash
   for i in 1 2 3; do pytest -m browser tests/browser/test_flow_chat.py -q --timeout=60 || { echo "FAIL $i"; exit 1; }; done
   ```
3. **No regression**: `pytest tests/ --tb=short -q --timeout=60` → 350 passed, 16 deselected
4. **All browser tests**: `pytest -m browser tests/browser/ -v --timeout=60` → 8 passed
5. **Lint/format**: `ruff check tests/browser/ && ruff format --check tests/browser/`
6. **Manual sanity (optional)**: Start app with `THE_ONE_DEV_MODE=true the-one serve`, manually create a mock provider + agent, send a message, confirm assistant response renders

## Implementation Guidance

### 1. Add `data-testid` attributes to chat.js

**Content DOM template** (lines 33-49 — HTML strings inside `content.innerHTML`):

```javascript
content.innerHTML =
  '<div class="header">' +
    '<span class="status">connecting...</span>' +
    '<span class="session-agent-badge"></span>' +
    '<div class="telemetry">' +
      ...
    '</div>' +
  '</div>' +
  '<div class="messages"></div>' +
  '<div class="input-area">' +
    '<input data-testid="chat-input" placeholder="Type a message..." autocomplete="off" />' +
    '<button data-testid="chat-send-btn">Send</button>' +
  '</div>';
```

**`addMsg` function** (lines 80-86 — createElement-based):

```javascript
function addMsg(cls, text) {
  var el = document.createElement('div');
  el.className = 'msg ' + cls;
  el.setAttribute('data-testid', 'message');
  el.textContent = text;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}
```

> **Why `data-testid="message"` for every message and not per-type**: Tests can scope by Playwright's chained locator (`page.locator('[data-testid="message"].user')` or `.filter(has_text="hello")`). Adding type-specific testids (`message-user`, `message-assistant`, `message-tool`, `message-system`) would balloon the testid count beyond budget without providing meaningful new coverage.

### 2. Create `tests/browser/test_flow_chat.py`

```python
"""End-to-end flow test: chat with mock agent.

Drives a real Chromium session through the chat flow:
- Open #chat with seeded mock provider + agent
- WebSocket connects, session auto-creates with the seeded agent
- Send "hello" message
- Assistant response renders deterministically (mock provider returns its
  default content)
- Send button re-enabled after `done` event
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from browser.seeders import SeededApp


@pytest.mark.browser
def test_chat_send_receives_mock_response(
    app_with_agent: SeededApp, page: Page
) -> None:
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name  # "test-agent"

    # 1. Open #chat. Default area is chat, so this is the home page.
    page.goto(base_url)

    # WebSocket connects → status changes to "connected".
    expect(page.locator(".status")).to_have_text("connected", timeout=5000)

    # 2. Session auto-creates with the seeded agent. Agent badge updates.
    expect(page.locator(".session-agent-badge")).to_have_text(
        agent_name, timeout=5000
    )

    # 3-4. Type and send.
    page.locator('[data-testid="chat-input"]').fill("hello")
    page.locator('[data-testid="chat-send-btn"]').click()

    # 5. User message renders.
    user_msg = page.locator('[data-testid="message"].user')
    expect(user_msg).to_have_text("hello", timeout=5000)

    # 6. Assistant message renders with the mock provider's default response.
    #    Per leg 02, MockProvider.complete() with no config["response"] returns
    #    "Mock response from the mock provider."
    assistant_msg = page.locator('[data-testid="message"].assistant')
    expect(assistant_msg).to_have_text(
        "Mock response from the mock provider.", timeout=10000
    )

    # 7. Send button re-enabled after `done` event (busy=false).
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()
```

> **Why `to_have_text` (exact) for the assistant content**: The mock provider's default response is a fixed string. Asserting exact match guards against accidental drift in `MockProvider._DEFAULT_RESPONSE`. If a future change deliberately reworks the default response, this test is the canary that signals "update the test too."

> **Timeout sizing**: WebSocket connect ~50-200ms, session auto-create ~10-50ms, message round-trip (user + mock LLM call + assistant + done) ~100-300ms. Conservative timeouts (5s for connect/badge, 10s for assistant) absorb CI/WSL2 jitter without masking real bugs.

### 3. Run verification

```bash
pytest -m browser tests/browser/test_flow_chat.py -v --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
pytest tests/ --tb=short -q --timeout=60
ruff check tests/browser/
ruff format --check tests/browser/
```

### 4. Repeat-run stability

```bash
for i in 1 2 3; do
  pytest -m browser tests/browser/test_flow_chat.py -q --timeout=60 \
    || { echo "FAILED on run $i"; exit 1; }
done
```

If flake observed, the most likely culprit is timing on the auto-session-creation race — confirm `agentSelect.value` is "test-agent" at the time `list_sessions` arrives (it should be, since `fetchAgents()` runs before `list_sessions` is sent). If the auto-session uses "default" instead, the assistant-response will still render but the agent badge assertion would fail. Diagnose specifically.

## Edge Cases

- **Agent badge text**: `chat.js:77` writes `name || 'default'`. With our seeded agent named "test-agent", the badge text is exactly "test-agent". `to_have_text("test-agent")` matches.

- **`busy` flag and send-button enable**: After `done` event, `busy=false` and `sendBtn.disabled = false` (line 376-381). The test's `to_be_enabled()` assertion auto-waits for this.

- **`session_list` empty on first load**: With empty DB the session_list is empty. Auto-creates new session. The test relies on this.

- **Mock provider's complete() ignores `messages`**: Per leg 02 design, MockProvider returns the configured response regardless of input. So sending "hello" produces the same response as sending "anything else". Test is deterministic.

- **`done` event vs assistant rendering order**: The server emits events in order: `user` (echo), `usage` (token counts), `assistant` (content), `done` (finalization). The test asserts on the assistant message first, then send-button enabled. If the order ever inverts (assistant after done), the test would still pass because both expectations are auto-waited.

- **`telemetry` updates from `usage` event** (lines 63-74, 374): The test does NOT assert telemetry — there's no testid on those elements yet, and the assertion would be brittle (token counts depend on prompt + response length). If F2 wants telemetry coverage, add a testid + count assertion separately.

- **Session deletion on test teardown**: The `app_clean` fixture (which `app_with_agent` composes on) tears down the entire subprocess on test exit. No need to manually delete sessions.

- **WebSocket reconnect on disconnect** (line 278): The test process holds the page open until teardown. No disconnect/reconnect cycle expected in normal flow.

- **`new_session` sent after `list_sessions` if no current session**: If the test were to run twice in the same browser context (it doesn't — `page` fixture is fresh per-test), the second run might see a `currentSessionId` carried over. Not applicable here because the page fixture creates a fresh BrowserContext per test.

- **`addMsg` for tool_call / tool_result** (chat.js:332-333): Mock provider returns no tool_calls in the default response, so no tool messages appear. Test only asserts on user + assistant messages.

- **Model-loading element doesn't get the testid**: The "Loading model…" element at `chat.js:337-340` is created via `document.createElement` directly, NOT via `addMsg`. Intentionally lacks `data-testid="message"` because it's a UI affordance, not a chat message. Mock provider doesn't trigger this path (the autoload runs only for `provider.type === "ollama"` per `app.py:363-364`), so this distinction doesn't affect the test.

- **Possible test flake on first run** if Chromium is launching for the first time in the test session. The `browser` fixture (module-scoped) launches Chromium once per test module — first test in module pays the cost (~500ms-1s extra), subsequent tests in the module are fast. No bearing on this single-test module.

## State-Machine Reachability Audit

**State exercised**: agent count 1, provider count 1 (from fixture); session count 0 → 1 (auto-created). Chat states: `busy=false` → `busy=true` (during message processing) → `busy=false` (after `done`).

Lower layers verified:
- DB: agent and provider already exist (from API seeders). No FK issues.
- `MockProvider.complete()`: returns deterministic content from `_DEFAULT_RESPONSE` constant. ✓
- WebSocket protocol: emits `user`, `usage`, `assistant`, `done` events in that order. ✓
- `_PROVIDER_TYPE_MAP["mock"] = "mock"` (leg 02): factory.py resolves to MockProvider. ✓
- Agent step loop: receives mock response, no tool_calls → loop exits → `done` event. ✓
- C-lite session reactivity: not exercised here (single message, no agent edit during chat). Out of scope.

No existing tests pin behavior this leg breaks. ✓ Pass.

## Cache Freshness Contract

**Cache 1 — `currentSessionId` JS variable** (existing):
- Source of truth: server-assigned session id from `session_joined` event
- Rebuild trigger: set on `session_joined`, cleared on `session_deleted` for current session
- User-action invalidation: switching sessions (manual click) re-issues join. ✓

**Cache 2 — `currentAgentName` JS variable** (existing):
- Source of truth: `data.agent_name` from `session_joined` event
- Rebuild trigger: every `session_joined`
- User-action invalidation: switching sessions re-renders badge. ✓
- **Mid-message limitation** (M03 C-lite contract): if the user edits the agent in Studio mid-conversation, this cached agent_name doesn't refresh until next session rejoin. Documented in M03 known issues; not exercised by this test.

**Cache 3 — `busy` flag** (existing):
- Source of truth: WebSocket events (set true in `send()`, false on `done`)
- Send button enable state mirrors this flag
- No staleness concern: synchronous JS state.

**No new caches.** ✓ Pass.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat.js` — 3 lines modified (input + send button HTML get `data-testid`, `addMsg` adds `setAttribute`)
- `tests/browser/test_flow_chat.py` — new (~50 LOC, 1 test)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing: `pytest tests/` shows 350 passed, 16 deselected; `pytest -m browser tests/browser/` shows 8 passed
- [x] 3 consecutive runs of the new flow test pass
- [x] `ruff check tests/browser/` and `ruff format --check tests/browser/` clean
- [x] Update flight-log.md with leg progress entry (status, what was done, any anomalies — note WebSocket timing observations and any UX bugs caught)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off this leg in flight.md (happens at flight-level commit time)
- [x] Do NOT commit (flight-level review and commit happen after the last autonomous leg — leg 08 is next)
- [x] Signal `[HANDOFF:review-needed]`
