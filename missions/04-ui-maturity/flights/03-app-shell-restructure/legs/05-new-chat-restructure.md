# Leg 05 — New-Chat Restructure

**Status**: completed
**Type**: discovery-via-HAT (interactive)
**Depends on**: legs 01-04

---

## Discovery summary (captured during execution)

The pre-leg state had three pain points the user named when walking through the new-chat flow:

1. **The agent dropdown was passive.** Sitting in the sidebar header next to "+ new", it controlled what the *next* `+ new` click would create — a relationship invisible from the UI. Users could not reasonably guess that selecting an agent in the dropdown would only seed a future click rather than affect the current conversation.
2. **`+ new` lived in the wrong context.** Placed in the sidebar header, it created a fresh session with whatever agent happened to be in the dropdown. The user wanted "+ new" to mean "another conversation with the agent I'm currently talking to" — i.e., bound to the conversation, not to a sidebar setting.
3. **Cold entry silently auto-created.** Landing on Chat with zero sessions instantly produced a session using the dropdown's agent — denying the user any moment of intentional choice. A welcome state was missing.

User intent (verbatim direction):
- *"switching agents from the dropdown starts a new conversation"*
- *"to start a new conversation with the same agent is the new button, but then the new button needs to be in the context of the current conversation"*
- *"first ever, we probably need a 'select an agent from the dropdown to start a new conversation'... we have a big open space to engage and educate the user rather than little buttons and dropdowns"*

---

## Affordance reassignment (the contract delivered)

| Control | Pre-leg behavior | Post-leg behavior |
|---|---|---|
| Sidebar agent dropdown | Seeds next `+ new` click | Reflects current session's agent. **Changing it starts a new conversation** with the chosen agent. |
| Header "New Chat" button | (sidebar) creates with dropdown's agent | Lives in conversation header, right-justified next to the agent name. **Creates with the *current* agent.** Lucide `square-pen` icon + label. |
| Cold entry, no sessions | Silent auto-create | Welcome canvas (centered: "Hello." + agent listbox or setup guidance). |
| Last-session-delete | Auto-creates a replacement | Returns to welcome canvas. |

Programmatic dropdown sync (post `session_joined`) sets `agentSelect.value = currentAgentName` without firing `change` (browsers only fire `change` on user input), so the sync is safe.

---

## Welcome canvas — state-aware content

One unified centered canvas replaces both the prior "+ new" sidebar flow AND the top-of-chrome `chat-no-providers` setup banner. Greeting "Hello." is constant; body adapts:

| State | Prompt | Body |
|---|---|---|
| No providers + no agents | (hidden) | "Add a provider in **Settings**, then create an agent in **Agent Studio** to start chatting." |
| No providers (agents present) | (hidden) | "Add a provider in **Settings** to start chatting." |
| Has providers, no agents | (hidden) | "Create an agent in **Agent Studio** to start chatting." |
| Ready (providers + agents, no current session) | "Which agent would you like to chat with?" | Agent listbox (full-row click, keyboard arrows, focus-visible accent ring) |

Inline links use `href="#admin"` / `href="#studio"` and route via the existing hash router. The `role="listbox"` is set only in the ready state (no options to navigate in setup-incomplete states).

---

## Cosmetic sweep delivered alongside the restructure

User-driven during the same interactive leg (collected as 11 tweaks across two passes):

1. **Area renames** — Chat → "Agent Chat", Studio → "Agent Studio", Admin → "Settings". IDs/slugs preserved (`chat`, `studio`, `admin`) so existing hash URLs do not break.
2. **Theme toggle** removed from the topbar; lives only at Settings → System → Appearance. Compact variant of `App.theme.renderToggle()` was unused after this and was deleted (along with its CSS).
3. **Sidebar bottom border** removed.
4. **Agent name** restyled from a chip to an `<h2>`-sized header.
5. **`+ new` → "New Chat"** with Lucide `square-pen` icon, right-justified via `margin-left: auto`.
6. **Status chicklet** removed (no more "connecting…" / "connected" text). Auto-reconnect runs silently on disconnect.
7. **Header bottom border** removed.
8. **Telemetry overlay** — chrome-free; floats lower-right of the conversation, ghosted (`opacity: 0.4`) by default. Hover/focus-within reveals the `in / out / ctx` breakdown via a `max-width 0 → 280px` transition; mouse-away contracts and fades back. Tabbable container; no inner button.
9. **Chat-history sidebar** gains a `Chat History` heading and groups sessions by recency: Today / Yesterday / Last 7 Days / Last 30 Days / Older. Each group is a `role=group` with `aria-labelledby` pointing at its heading; the listbox role moves to the group level so screen readers announce the section.
10. **Per-message attribution** — small muted-mono labels below each user / assistant bubble: "You" right-aligned, agent name left-aligned. Live messages use `currentAgentName`; history-replayed messages use the agent name from `session_joined`.
11. **"Thinking…" indicator** — assistant-styled bubble with the existing braille-spinner animation (`⣾⣽⣻⢿⡿⣟⣯⣷` × 120ms). Appears on send, removed on assistant message / tool_call / done / error / chat switch / session delete / WS close.

---

## Server-side fixes uncovered during the leg

1. **WebSocket subscriber leak on session switch** (`app.py` join handler). Joining a new session did NOT discard the WS from the prior session's subscribers — broadcasts to the old session (e.g. an in-flight `Loading model...`) bled into the new session's UI. Fixed by mirroring the `new_session` handler's discard step in `join`.
2. **Anthropic provider rejection of `temperature` for newer Claude models** (e.g. Opus 4.x, Sonnet 4.x). 400 error caused the agent loop to crash, which crashed the WS handler before `done` fired, which left the `thinking` indicator stuck forever. Fixed by catching `BadRequestError` in `AnthropicProvider.complete()` and retrying once without `temperature` if the message contains "temperature".
3. **`_process_and_broadcast` exception path** never sent `done`. Wrapped the agent step loop in `try/except`; any exception now emits `{"type": "system", "content": "Agent error: <exc>"}` followed by the normal `done`, so the client can recover its UI.
4. **Mock provider** got an optional `delay_ms` config knob (default 0) so E2E tests can deterministically exercise the thinking indicator without depending on real LLM latency.
5. **Client `ws.onclose`** now hides the thinking indicator and resets `busy` / re-enables the send button. Auto-reconnect runs 2s later. Defense-in-depth against any disconnect mid-response.

---

## Tests added

`tests/browser/test_flow_new_chat.py` — 11 Playwright tests:

- Welcome canvas content for all three setup states (no providers / no agents / ready)
- Picking an agent from the welcome listbox starts a session
- Sidebar dropdown change starts a new conversation with the chosen agent
- Header "New Chat" button starts a fresh conversation with the current agent
- Deleting the last session returns to welcome (no auto-create)
- Chat-history "Today" group renders
- "You" / agent attribution labels render under user / assistant bubbles
- Telemetry overlay starts collapsed and expands on focus
- Thinking indicator appears on send and clears on response (uses `delay_ms=800` mock provider)

Existing test maintenance:
- All `.status` "connected" waits removed (chicklet is gone) — switched to badge-text or picker-visible signals.
- `test_flow_provider_setup.py` rewritten to assert against `.chat-welcome-guidance` text (replaces the dropped `[data-testid="setup-banner"]`).
- Tests that relied on auto-create-on-load now bootstrap via the welcome listbox click (test_flow_chat, test_flow_keyboard, test_flow_hash_routing).

---

## Test counts after leg

- Browser: **32 passing** (was 21 pre-flight; +11 leg-05 tests).
- Unit: **393 passing** (unchanged).

---

## Files changed

**JS:**
- `the_one/interfaces/web/static/js/areas/chat.js` — large restructure (welcome canvas, view-state machine, attribution, thinking indicator, history grouping, telemetry overlay wiring, dropdown semantics flip)
- `the_one/interfaces/web/static/js/areas/admin.js` — area rename labels (Settings)
- `the_one/interfaces/web/static/js/areas/studio.js` — area rename labels (Agent Studio)
- `the_one/interfaces/web/static/js/app.js` — topbar theme-toggle mount removed
- `the_one/interfaces/web/static/js/theme.js` — compact variant + multi-mount sync removed (now-unused after topbar mount strip; full variant only)
- `the_one/interfaces/web/static/js/icons.js` — `square-pen` icon added (Lucide v0.265.0)

**CSS:**
- `the_one/interfaces/web/static/css/chat.css` — welcome canvas, links/guidance, history group labels, agent-name-as-h2, header without border, telemetry overlay (chrome-free hover-driven), attribution labels, thinking indicator italic-muted variant, dropped `.chat-no-providers` rules
- `the_one/interfaces/web/static/css/components.css` — dropped `.theme-toggle-compact` rules (dead code)

**Server:**
- `the_one/interfaces/web/app.py` — WS join-handler subscriber-leave fix; `_process_and_broadcast` try/except wrapper
- `the_one/llm/anthropic_provider.py` — temperature-deprecation retry
- `the_one/llm/mock.py` — optional `delay_ms` config knob

**Tests:**
- `tests/browser/test_flow_new_chat.py` (new, 11 tests)
- `tests/browser/test_flow_chat.py`, `test_flow_keyboard.py`, `test_flow_hash_routing.py`, `test_flow_provider_setup.py` (updated for new flow)

---

## Out of scope (deliberate, captured for future flights)

- **Response streaming** (assistant content rendered chunk-by-chunk as it arrives instead of in a single bubble after `done`). User-deferred to a future mission.
- **Markdown / code-block rendering** in assistant messages. User-deferred.
- **Pre-naming** sessions before first message.
- **Search / filter** in the welcome agent listbox (defer until agent count justifies it).
- **Form-primitive extraction** (the F2-debrief item) — leg 05's work didn't naturally consolidate any primitives, so this stays scheduled for F3.5.

---

## Acceptance

User said "looks good" after the welcome / dropdown / + new flow landed; "looks good. I just did a chat and its stuck on 'Thinking'" surfaced the WS leak + Anthropic temperature bug; "perfect" / "looks good" again after each cosmetic pass. Final user direction: "lets wrap it up. will need a debrief."
