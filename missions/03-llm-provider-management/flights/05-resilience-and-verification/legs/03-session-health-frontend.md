# Leg: session-health-frontend

**Status**: completed
**Flight**: [Resilience & Verification](../flight.md)

## Objective

Render the new session-health states from Leg 02 in the chat UI: show a dedicated banner for `agent_deleted` and `provider_missing` sessions, disable chat input while a session is degraded, and re-enable it when the user joins a healthy session — without conflicting with the existing global setup banner.

## Context

Flight 05 design decision **"Session health validation: three states on join"** specifies the UX:

- `agent_deleted` → banner: *"This agent has been deleted. Chat history is preserved but new messages cannot be sent."* History rendered read-only; input disabled.
- `provider_missing` → banner: *"This agent's provider is missing. Configure a provider in Studio to continue this conversation."* Input disabled. Once the provider is fixed, the next join attempt returns `ok` and chat resumes.
- `ok` → no session banner; input enabled.

The decision also notes: *"Session health banners are per-session state, distinct from the global setup banner (`checkSetupState`). They use a separate DOM element to avoid conflicts with the existing `chat-no-providers` banner."*

Flight 05 also calls out one cleanup item explicitly tied to this leg in the In-Flight Checkpoints list:

> - [ ] bannerEl refactored to dedicated boolean state flag

Today, `the_one/interfaces/web/static/js/areas/chat.js` uses the truthiness of the `bannerEl` DOM-reference variable as a proxy for "setup is incomplete":

- `chat.js:252`: `else if (!currentSessionId && !bannerEl) { ... auto-create session ... }`
- `chat.js:342`: `if (bannerEl) return; // setup not complete`

This conflation breaks once we add a second banner: the session-health banner being present would falsely signal "setup incomplete" and block the new-chat button + auto-create. The refactor introduces a dedicated `setupIncomplete` boolean that tracks the meaning explicitly. `bannerEl` then becomes a pure DOM reference with no semantic overload.

Leg 02 has landed: the backend `join` action now sends `status: "ok" | "agent_deleted" | "provider_missing"` via the new `_build_session_joined_ok` and `_build_session_joined_degraded` helpers. **However**, two other `session_joined` emission sites in `app.py` still emit hand-rolled dicts that LACK the `status` field:

- The `new_session` action handler (`app.py` ~line 682)
- The auto-join fallback inside the message-handling branch (`app.py` ~line 724)

Both of these only emit healthy sessions (per Leg 02's invariants, freshly-created sessions cannot be degraded). The frontend's `data.status || "ok"` default would handle them correctly — but the protocol gap is a contract-drift hazard. **This leg closes that gap** by routing both branches through `_build_session_joined_ok(session)` (a tiny backend addition, ~6 line diff). After this leg, every `session_joined` payload uniformly carries `status`, and the frontend's `|| "ok"` default becomes belt-and-braces rather than load-bearing.

## Inputs

What exists before this leg:

- `the_one/interfaces/web/static/js/areas/chat.js` — the `chat` area's WS message handler (`session_joined` at line 261-268), `checkSetupState` (lines 194-225), `connect` (lines 227-334), `joinSession` (lines 174-178), `send` (lines 184-192), `newChatBtn` handler (lines 341-347)
- `the_one/interfaces/web/static/styles.css:98` — existing `.area-chat .chat-no-providers` styles for the global setup banner
- `the_one/interfaces/web/static/styles.css:108-112` — existing `.input-area input/button` styles, including `:disabled { opacity: 0.4; cursor: not-allowed; }`
- Leg 02's WS protocol additions: `session_joined` always carries `status` in `{"ok", "agent_deleted", "provider_missing"}`. Backend HTTP `/api/chat` returns `{"error": "session_<status>"}` for degraded states (frontend only consumes the WS path; HTTP response is informational).

There are no frontend automated tests in this codebase — verification is manual smoke (deferred to the HAT leg).

## Outputs

What exists after this leg completes:

- `the_one/interfaces/web/app.py`:
  - The `new_session` action handler is rewritten to call `_build_session_joined_ok(session)` instead of the hand-rolled dict, and the auto-join fallback inside the message-handling branch does the same. Net effect: every `session_joined` payload now carries `status`. **No other backend changes** in this leg.
- `the_one/interfaces/web/static/js/areas/chat.js`:
  - New `setupIncomplete` boolean replaces `bannerEl` truthiness as the "setup is incomplete" signal at the two existing usage sites (lines 252, 342).
  - New `sessionBannerEl` DOM-reference variable for the session-health banner (initially `null`).
  - New `setSessionHealth(status)` helper that:
    - For `status === "ok"`: removes `sessionBannerEl` from DOM if present, enables `inputEl` and `sendBtn`, sets `sessionBannerEl = null`.
    - For `status === "agent_deleted"`: creates/updates the banner with the agent-deleted message, disables `inputEl` and `sendBtn`.
    - For `status === "provider_missing"`: same as above with the provider-missing message.
  - The `session_joined` message handler (line 261-268) calls `setSessionHealth(data.status || "ok")` after `renderHistory(data.history)` so the banner appears alongside the read-only history. It also guards against stale responses: if `data.session_id !== currentSessionId`, the message is for a superseded join and is ignored.
  - The `session_deleted` handler clears `sessionBannerEl` (the deleted session's banner shouldn't linger after the user navigates away).
- `the_one/interfaces/web/static/styles.css`:
  - New `.area-chat .chat-session-banner` rule (separate selector from `.chat-no-providers`) using `#f5a623` (the project's existing amber convention; see `.context-bar.warn` at line 96, `.studio-vram-warning`, `.admin-system-warning`).

## Acceptance Criteria

- [x] **Backend protocol gap closed**: `the_one/interfaces/web/app.py` — both the `new_session` action handler and the auto-join fallback inside the message-handling branch route through `_build_session_joined_ok(session)` instead of constructing the `session_joined` dict inline. After this leg, ALL `session_joined` payloads carry `status`. No other backend changes.
- [x] `setupIncomplete` boolean is introduced in the `init` closure scope alongside `bannerEl` and is the SOLE source of truth for "is setup incomplete":
  - `checkSetupState` sets `setupIncomplete = true` when a banner message is computed; sets `setupIncomplete = false` when no message (banner cleared).
  - The two prior `bannerEl`-as-state usages (lines 252 and 342) are rewritten to read `setupIncomplete` instead.
  - `bannerEl` continues to exist purely as the DOM-reference for the setup banner — it remains `null` when the banner is absent and an `HTMLElement` when present.
- [x] `sessionBannerEl` is a separate DOM-reference variable in the same `init` closure scope, initially `null`.
- [x] `setSessionHealth(status)` helper exists with three branches (`"ok"` clears, `"agent_deleted"` and `"provider_missing"` show banners with the exact text from the design decision):
  - Agent deleted: `"This agent has been deleted. Chat history is preserved but new messages cannot be sent."`
  - Provider missing: `"This agent's provider is missing. Configure a provider in Studio to continue this conversation."`
  - The banner element uses CSS class `chat-session-banner` (NOT `chat-no-providers` — they must remain visually and semantically distinct).
  - The banner is inserted in the same DOM position as the setup banner: `messagesEl.parentNode.insertBefore(sessionBannerEl, messagesEl)`. If the setup banner is also present, the session banner appears below it (insert AFTER `bannerEl` if `bannerEl` is non-null, AT the messagesEl insertion point otherwise).
  - Unknown statuses (anything other than the three valid values) are treated as `"ok"` — defensive against future protocol additions.
- [x] `inputEl.disabled` and `sendBtn.disabled` are toggled in lockstep:
  - On `agent_deleted` / `provider_missing`: both set `true`
  - On `ok`: both set `false`
  - The existing `busy` flag continues to control the same disabled state during message-send round-trips — the leg must NOT regress that behavior. Specifically, the `done` handler at line 328-332 sets `sendBtn.disabled = false` unconditionally; if a degraded session arrives mid-message, this would re-enable the button. Add a guard: `sendBtn.disabled = sessionBannerEl !== null` (or equivalently, only re-enable if `!sessionBannerEl`).
- [x] The `session_joined` handler at lines 261-268 calls `setSessionHealth(data.status || "ok")` AFTER `renderHistory(data.history)` so the banner placement is stable relative to the rendered history.
- [x] **Stale-join guard**: at the top of the `session_joined` handler, add `if (data.session_id !== currentSessionId) return;` to ignore responses for superseded join requests (e.g. user clicked Session A then Session B in rapid succession). `joinSession` already sets `currentSessionId` optimistically before sending the WS message (line 175), so this check is consistent with the existing optimistic-update pattern.
- [x] The `session_deleted` handler (lines 270-280) calls `setSessionHealth("ok")` if the deleted session was the current one — clears any lingering banner before the next session is auto-joined.
- [x] Visual style: `.area-chat .chat-session-banner` is added to `styles.css` with explicit visual differentiation from `.chat-no-providers`. Use `#f5a623` (the project's existing amber convention — already used in `.context-bar.warn` line 96, plus `.studio-vram-warning` and `.admin-system-warning`):
  ```css
  .area-chat .chat-session-banner {
    text-align: center;
    color: #f5a623;
    font-size: 13px;
    padding: 14px 20px;
    background: var(--surface);
    border-bottom: 1px solid #f5a623;
    flex-shrink: 0;
  }
  ```
  Do NOT introduce a new `--warn` CSS variable in this leg — that's a project-wide consolidation, out of scope.
- [x] No regression in the existing setup-banner flow:
  - With no providers configured, `checkSetupState` still shows the setup banner.
  - With no agents configured (but providers present), the setup banner appears with the agents message.
  - With both configured, the setup banner is removed.
  - The new-chat button still respects the setup-incomplete guard (now via `setupIncomplete` boolean instead of `bannerEl` truthiness).
  - The `session_list` handler's auto-create branch (line 252) still respects the same guard.
- [x] No new external dependencies. No bundlers, no transpilers, no JS frameworks. Match the existing IIFE-and-`var` style of `chat.js`.

## Verification Steps

There are no automated frontend tests, so verification is manual smoke. Defer the full end-to-end exercise to the HAT leg, but the implementer must do the following minimum smoke before signaling handoff:

- Open the running app in a browser. Confirm no console errors on chat-area load.
- Manually inspect the diff: `setupIncomplete` is the only state flag at lines 252 and 342; `bannerEl` is referenced only as a DOM reference; `sessionBannerEl` is a sibling variable; `setSessionHealth` is the only writer of `inputEl.disabled` and `sendBtn.disabled` for the degraded-session toggle (the `busy`/`done` paths are still present but consult `sessionBannerEl` before re-enabling).
- Visually confirm: with a healthy session, no session banner. With a session whose agent has been deleted (manually craft via DB or use the HAT leg), the amber banner appears with the agent-deleted text and input is disabled. Same for provider_missing.
- Run `python -c "import json; ..."` -ish syntax check is not applicable for JS; the implementer should at least load the page and confirm no JS exceptions in the console.
- `pytest -q --ignore=tests/test_tool_registry.py --ignore=workspace/test_agent.py` — backend-only smoke, must still pass.

## Implementation Guidance

0. **Close the backend protocol gap first**. In `the_one/interfaces/web/app.py`, locate the two hand-rolled `session_joined` emissions:
   - Inside the `new_session` action handler (around line 682-688): replace the inline dict with `await ws.send_json(_build_session_joined_ok(session))`.
   - Inside the auto-join fallback in the message-handling branch (around line 724-730): same replacement.
   The helpers were added in Leg 02; they're module-level functions in `app.py`. After this change, every `session_joined` carries `status`. Verify with `grep -n "type.*session_joined" the_one/interfaces/web/app.py` — only the two helper return values should match.

1. **Refactor `bannerEl` semantics** (the load-bearing frontend change). At the top of the `init` function, alongside `var bannerEl = null;` (line 13), add:
   ```javascript
   var setupIncomplete = false;
   var sessionBannerEl = null;
   ```
   Inside `checkSetupState` (lines 194-225), update the success path:
   ```javascript
   if (msg) {
     setupIncomplete = true;          // NEW
     if (!bannerEl) {
       bannerEl = document.createElement('div');
       bannerEl.className = 'chat-no-providers';
       messagesEl.parentNode.insertBefore(bannerEl, messagesEl);
     }
     bannerEl.textContent = msg;
   } else {
     setupIncomplete = false;         // NEW
     if (bannerEl) {
       bannerEl.parentNode.removeChild(bannerEl);
       bannerEl = null;
     }
   }
   ```
   Then update the two existing usages:
   - Line 252: `else if (!currentSessionId && !bannerEl)` → `else if (!currentSessionId && !setupIncomplete)`
   - Line 342: `if (bannerEl) return; // setup not complete` → `if (setupIncomplete) return; // setup not complete`

2. **Add `setSessionHealth(status)`** as a helper inside the `init` closure. Placement is up to readability — anywhere inside `init` works mechanically (closure variables `messagesEl`, `inputEl`, `sendBtn`, `bannerEl`, `sessionBannerEl` are visible regardless of order). Suggested: just above the `connect` function, after `checkSetupState`:
   ```javascript
   function setSessionHealth(status) {
     // Default unknown status to 'ok' — defensive against future protocol additions
     var msg = null;
     if (status === 'agent_deleted') {
       msg = 'This agent has been deleted. Chat history is preserved but new messages cannot be sent.';
     } else if (status === 'provider_missing') {
       msg = "This agent's provider is missing. Configure a provider in Studio to continue this conversation.";
     }

     if (msg) {
       if (!sessionBannerEl) {
         sessionBannerEl = document.createElement('div');
         sessionBannerEl.className = 'chat-session-banner';
         // Place after the setup banner if both exist; otherwise immediately above messagesEl
         var anchor = bannerEl ? bannerEl.nextSibling : messagesEl;
         messagesEl.parentNode.insertBefore(sessionBannerEl, anchor);
       }
       sessionBannerEl.textContent = msg;
       inputEl.disabled = true;
       sendBtn.disabled = true;
     } else {
       if (sessionBannerEl) {
         sessionBannerEl.parentNode.removeChild(sessionBannerEl);
         sessionBannerEl = null;
       }
       inputEl.disabled = false;
       sendBtn.disabled = false;
     }
   }
   ```

3. **Update the `session_joined` message handler** (lines 261-268). Add the stale-join guard at the top, then call `setSessionHealth` after history rendering:
   ```javascript
   if (data.type === 'session_joined') {
     // Stale-join guard: ignore responses for superseded join requests.
     // joinSession sets currentSessionId optimistically before sending; if a newer
     // join has been issued since, the response for the older one is irrelevant.
     // The auto-create paths (new_session / fallback) will not have a stale id
     // because they assign currentSessionId from data.session_id below — guard
     // accordingly: only ignore when currentSessionId is set AND mismatches.
     if (currentSessionId && currentSessionId !== data.session_id) return;

     currentSessionId = data.session_id;
     currentAgentName = data.agent_name;
     updateAgentBadge(data.agent_name);
     renderHistory(data.history);
     setSessionHealth(data.status || 'ok');
     refreshSessionList();
     return;
   }
   ```
   Note the `if (currentSessionId && ...)` form: a `currentSessionId === null` (initial connect, post-delete) must NOT be guarded out — those are legitimate first-bind cases. The guard only fires when an explicit session_id was set and a newer one supplanted it.

4. **Update the `session_deleted` handler** (lines 270-280). When the deleted session is the current one, clear the banner BEFORE the auto-`new_session` is sent (otherwise the new healthy session_joined would arrive and clear it anyway, but the brief flash is ugly):
   ```javascript
   if (data.type === 'session_deleted') {
     if (currentSessionId === data.session_id) {
       currentSessionId = null;
       messagesEl.innerHTML = '';
       setSessionHealth('ok');             // NEW — clear any session banner
       var delMsg = { action: 'new_session' };
       if (agentSelect.value) delMsg.agent_name = agentSelect.value;
       ws.send(JSON.stringify(delMsg));
     }
     refreshSessionList();
     return;
   }
   ```

5. **Guard the `done`-path re-enable** (line 328-332). Today:
   ```javascript
   else if (data.type === 'done') {
     busy = false;
     sendBtn.disabled = false;
     refreshSessionList();
   }
   ```
   New:
   ```javascript
   else if (data.type === 'done') {
     busy = false;
     // Only re-enable if no degraded session banner is active
     if (!sessionBannerEl) {
       sendBtn.disabled = false;
     }
     refreshSessionList();
   }
   ```
   Note: the `system` handler at lines 316-323 also has a `sendBtn.disabled = false` reset on error — apply the same `if (!sessionBannerEl)` guard there for consistency. Pseudocode:
   ```javascript
   } else {
     addMsg('system', data.content);
     if (busy) {
       busy = false;
       if (!sessionBannerEl) {
         sendBtn.disabled = false;
       }
     }
   }
   ```

6. **Add `.chat-session-banner` styles** to `the_one/interfaces/web/static/styles.css`. Place the rule immediately after the existing `.chat-no-providers` rule (line 98). Use `#f5a623` to match the project's existing amber convention (already in `.context-bar.warn` line 96, `.studio-vram-warning`, `.admin-system-warning`):
   ```css
   .area-chat .chat-session-banner {
     text-align: center;
     color: #f5a623;
     font-size: 13px;
     padding: 14px 20px;
     background: var(--surface);
     border-bottom: 1px solid #f5a623;
     flex-shrink: 0;
   }
   ```
   Do NOT introduce a `--warn` CSS variable — that consolidation is out of scope for this leg.

7. **Manual smoke** — load the running app, confirm no console errors. Defer the full functional verification to the HAT leg.

8. **Update flight log** with a Leg Progress entry. No new Decisions are required unless the implementer encounters a surprising interaction (e.g. the auto-create-on-empty-list branch sends `new_session` while a session_banner is present — should that be blocked? The current spec says no, because the user hasn't yet seen the degraded banner; but if observed in practice, document and flag).

## Edge Cases

- **`status` field is missing on session_joined**: After step 0 of this leg, every payload carries `status` — but defend with `data.status || "ok"` anyway, so a stale frontend talking to a freshly-deployed backend (or vice versa) degrades gracefully.
- **`status` field is an unknown value**: `setSessionHealth` treats anything other than `"agent_deleted"` and `"provider_missing"` as `"ok"`. No banner; input enabled.
- **User has both setup banner AND session banner showing**: Possible if a degraded session is restored on app load while no providers are configured (e.g. user deleted all providers). Both banners stack vertically. Acceptable visual state — the user has two real problems.
- **`session_joined` arrives mid-message-send**: Unlikely in practice (the frontend only sends `join` on user action), but if it did, the new banner would overwrite the busy state. The `done` handler's guard ensures the user isn't re-enabled into a degraded session.
- **`session_deleted` for a non-current session**: Existing behavior unchanged — only the session_list is refreshed; no banner change.
- **`new_session` succeeds with an explicit `agent_name`**: Backend session_joined arrives with `status: "ok"` (new sessions can't be degraded — `_create_session` raises on invalid agents per Leg 02). Banner clears if present.
- **WebSocket reconnect after disconnect**: `connect()` re-runs `checkSetupState`, `fetchAgents`, `list_sessions`. Any session-banner state from before the disconnect is reset by the reconnect-time `messagesEl.innerHTML = ''` cycle ... actually, the current code does NOT clear messages on reconnect — it just reconnects the socket. After reconnect, the next session_joined will refresh state. Acceptable — the banner state is a function of the most recent session_joined.
- **Disabled-input ergonomics — keydown propagation**: An `<input>` element with `disabled=true` does NOT fire `keydown` events (per the HTML spec — disabled form controls are non-interactable). The existing Enter-key path at line 337-339 (`inputEl.addEventListener('keydown', ...)`) is therefore naturally inert when the input is disabled by `setSessionHealth`. No additional guard is required in `send()`.
- **Asymmetry: `setupIncomplete` does NOT disable input**: Today's `checkSetupState` only renders/clears the global setup banner; it does NOT toggle `inputEl.disabled` or `sendBtn.disabled`. This leg preserves that pre-existing behavior — degraded-session banners disable input, setup-incomplete does not. The visual effect: with no providers configured, the user can type and hit send, and the WS handler responds with `Cannot start chat: ...` (existing error path). This asymmetry is a UX inconsistency worth fixing in a future leg, but is OUT OF SCOPE here. Documented so a future operator finds it.
- **Agent badge on `agent_deleted`**: `_build_session_joined_degraded` returns `agent_name: db.agent_name` (the deleted agent's name). The frontend's existing `updateAgentBadge(data.agent_name)` will show that name. **This is intentional** — the user should see *which* agent was deleted; the banner conveys that the agent is gone. Do NOT special-case the badge for degraded states.
- **Stale-join race**: User clicks Session A, then Session B before A's response arrives. `joinSession(A)` sets `currentSessionId = A` and sends. `joinSession(B)` then sets `currentSessionId = B` and sends. A's response arrives first; the new `if (currentSessionId && currentSessionId !== data.session_id) return;` guard discards it. B's response arrives second and is processed. No banner flash, no stale agent badge.
- **Rapid double-create on connect**: User opens the app and clicks `+ new` while `list_sessions` is still in flight. The `+ new` click sends a `new_session`. The `list_sessions` response then arrives with zero sessions and the `session_list` handler ALSO auto-sends `new_session` (lines 252-257). Two `session_joined` payloads return for two distinct fresh sessions; whichever binds `currentSessionId` first wins, and the second is silently discarded by the stale-join guard. The orphaned auto-created session lingers server-side. **This is a pre-existing concurrency edge case** (not introduced by this leg) and is OUT OF SCOPE — flagged so the HAT leg knows to verify and so a future leg can collapse the dual-creation paths.

## Files Affected

- `the_one/interfaces/web/app.py` — replace two hand-rolled `session_joined` dicts with `_build_session_joined_ok(session)` calls (in the `new_session` handler and the auto-join fallback). **Net diff: ~6 lines.**
- `the_one/interfaces/web/static/js/areas/chat.js` — add `setupIncomplete` boolean, `sessionBannerEl` ref, `setSessionHealth` helper; update `checkSetupState`, `session_joined` (incl. stale-join guard), `session_deleted`, `done`, and `system` handlers; rewrite the two `bannerEl`-as-state-flag callsites. **Net diff: ~55 lines.**
- `the_one/interfaces/web/static/styles.css` — add `.chat-session-banner` rule. **Net diff: ~10 lines.**

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Backend tests still passing (`pytest -q --ignore=tests/test_tool_registry.py --ignore=workspace/test_agent.py` green)
- [ ] Manual smoke: app loads, no JS console errors
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off the leg in flight.md yet
- [ ] Do NOT commit — Mission Control batches review and commit at end of flight
