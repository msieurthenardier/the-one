# Leg: chat-ui-pending-approval

**Status**: completed
**Flight**: [Pairing Resolution + Connectors-Screen Detach](../flight.md)

## Objective

Wire the Chat UI to render `pending-approval` events as an interactive banner (with Approve / Dismiss buttons that POST to L3's endpoints), in both replay (session-restore) and live-broadcast paths. The backend `_restore_session` is extended to merge `pending_approvals` rows into the `ui_events` history by timestamp so the operator sees pending banners on rejoin.

## Context

**Why this leg.** L2 emits the live `pending-approval` event via `broadcast_to_session(session_row.id, ...)`; L3 ships approve/dismiss endpoints. L4 makes the banner visible — both the live-broadcast path (operator was watching when the DM arrived) AND the replay path (operator rejoins later). Without L4, the storage exists but the operator can't approve from the UI.

**Design Decision §2 / §5 (cycle-2 architect, locked at flight planning)**:
- Session-restore merge happens **on the BACKEND** (mirrors `app.py:505, 631`). `_restore_session` queries both messages and pending_approvals, merges by timestamp, emits one ordered UI-event stream via WebSocket. Frontend `addMsg`/`renderHistory` dispatches on event type only — no client-side merge.
- New top-level Chat UI event type `pending-approval` (6th case in the existing dispatch — was 5 in `chat.js`'s `renderHistory` at line 250-274 and ~6 in the WS onmessage dispatch around line 859+). Event shape per flight §5: `{type, approval_id, peer_name, peer_id, preview, received_at, connector_account_id, status}`.

**Banner UX shape**:
- Renders as a left-aligned message bubble (consistent with other agent/system bubbles) with `msg msg-pending-approval` classes.
- Body shows: `<peer_name>: <preview>` (HTML-escaped) plus two buttons: "Approve" (primary) and "Dismiss" (secondary link).
- After Approve is clicked → optimistic re-render with status "approved" badge; on POST failure, revert and show error.
- After Dismiss is clicked → optimistic re-render with status "dismissed" badge; on POST failure, revert.
- Already-`approved` or already-`dismissed` rows (e.g. after session-restore reads historical rows) render with the terminal-state badge and NO action buttons.

**Optimistic update vs server-truth** (decision locked here): the click handler does optimistic UI (instant feedback) and then awaits the POST. If the POST fails, revert AND surface a system error. This matches the existing pattern at chat.js around the auth-resolve flow (`Resuming…` system message at line 623) — optimistic with reconciliation. The L3 endpoints are idempotent, so a double-click race is harmless.

**Race: live broadcast arrives AFTER session-restore inserts the same row** — the operator was offline when the DM arrived; restore loads the pending row at join time; THEN a live broadcast for the same `approval_id` fires (because the dispatcher's emit was queued mid-restore). Result: two banners for the same approval. **Resolution**: keep a Set of seen `approval_id`s in chat.js; skip render if the id is already seen. This handles the restore-then-broadcast race AND the broadcast-then-restore race symmetrically.

**Backend merge algorithm**:
1. After `messages = decode_messages(db_session.messages)` and `ui_events = messages_to_ui_events(messages)`, query `pending_approval_repo.list_for_account_peer(account_id, peer_id)` IF the session has connector context (`db_session.connector_account_id is not None and db_session.peer_id is not None`).
2. Project each `PendingApproval` row to a `pending-approval` event dict (verbatim flight §5 shape; the codec needs a small projection function).
3. Merge the two lists by timestamp — `ui_events` items have `ts` field (when present); `pending-approval` events have `received_at`. Merge step does an O(n+m) interleave when both lists are pre-sorted; otherwise a single `sorted(combined, key=lambda e: e.get('ts') or e.get('received_at') or '')` is acceptable for L4 (M10 history sizes are small; revisit if perf surfaces).
4. Replace the previous `ui_events = messages_to_ui_events(messages)` with the merged list.
5. Repeat the same merge logic for the degraded-session path at `app.py:631` (`_build_session_joined_degraded`) — same surface, same shape.

**Codec projection function**: add `pending_approvals_to_ui_events(rows: list[PendingApproval]) -> list[dict]` to `the_one/db/codec.py` (parallel to `messages_to_ui_events`). The dispatcher's live-broadcast event shape and the replay shape MUST be identical — the frontend dispatches on `type` only and cannot see the difference. So the projection function is the single source of truth for the event shape; L2's dispatcher emit code can also be refactored to use this function (optional refactor; flagged as low-priority because L2 hand-built the event dict and changing that now means re-running L2's tests).

**Decision**: do NOT refactor L2's dispatcher emit to use the projection function. Add `pending_approvals_to_ui_events` for the restore path only; document the projection-function-is-canonical contract in its docstring. A future routine-maintenance pass can consolidate.

**`messages_to_ui_events` ts field**: per `codec.py:153-279`, the existing projection emits events with optional `ts` keys for live-broadcast events but NOT for replay events (replay path constructs events without a `ts` field — frontend treats `ev.ts || null`). The merge must tolerate missing `ts` on message-derived events. Resolution: use `db_session.created_at` as a fallback for messages without explicit timestamps (or accept that messages sort before pending-approvals when ts is missing). Simpler: just sort `(ts or '') ASC` and let any missing-ts events float to the top. Since the operator is the one constructing history meaning, exact interleave isn't critical; gross ordering by hour is enough.

**Two scoped concerns NOT done here**:
- L4 does NOT update the existing `messages_to_ui_events` signature. The merge happens in `_restore_session` (and `_build_session_joined_degraded`), not in the codec.
- L4 does NOT touch the live-broadcast event format at the dispatcher emit (L2's emit). The dispatcher's hand-built event dict and the codec's projection function will produce byte-identical shapes; if they drift, that's a bug.

## Inputs

- L2 outputs: `PendingApprovalRepository.list_for_account_peer(account_id, peer_id)`, `PendingApproval` model.
- L3 outputs: approve / dismiss POST endpoints at `/api/connector-accounts/{account_id}/peer-approvals/{approval_id}/{action}`.
- `the_one/interfaces/web/app.py:426-535` — `_restore_session` (replay path).
- `the_one/interfaces/web/app.py:617-632` — `_build_session_joined_degraded` (degraded replay path).
- `the_one/interfaces/web/app.py:46` — existing `messages_to_ui_events` import; extend to also import `pending_approvals_to_ui_events`.
- `the_one/db/codec.py:153-279` — `messages_to_ui_events` precedent. L4 adds `pending_approvals_to_ui_events` adjacent.
- `the_one/db/models.py:475-484` — `PendingApproval` shape (id, connector_account_id, peer_id, peer_name, preview, received_at, status, resolved_at).
- `the_one/interfaces/web/static/js/areas/chat.js:227-278` — `renderHistory` (replay dispatch). Extends with `pending-approval` case.
- `the_one/interfaces/web/static/js/areas/chat.js:859-940` — WS onmessage dispatch. Extends with `pending-approval` case.
- `the_one/interfaces/web/static/js/areas/chat.js:116-136` — `addMsg` helper.
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:1-137` — `App.chat.renderMessage` + `App.chat.renderAttribution`. L4's banner uses a DEDICATED render function (not `renderMessage`) because banners have interactive elements (buttons), not just text.
- `the_one/interfaces/web/static/css/chat.css:139, 218-261` — bubble + attribution CSS precedents.
- `tests/browser/test_flow_chat_peer_attribution.py` — browser test pattern (DOM-shape + computed-style assertions; no committed snapshot baselines).
- `tests/test_app_websocket_pause_resume.py` and similar — backend WS-event tests.

## Outputs

- `the_one/db/codec.py` — new `pending_approvals_to_ui_events(rows)` function (parallel to `messages_to_ui_events`).
- `the_one/interfaces/web/app.py` — extend `_restore_session` and `_build_session_joined_degraded` to merge pending_approvals into the history stream when the session has connector context. Add `pending_approvals_to_ui_events` to the codec import; add `PendingApprovalRepository` import + factory helper or inline construction.
- `the_one/interfaces/web/static/js/areas/chat.js` — extend `renderHistory` (replay) and WS onmessage (live) with `pending-approval` case + dedup-by-approval-id Set.
- `the_one/interfaces/web/static/js/areas/chat/pending-approval-banner.js` — NEW module exporting `App.chat.renderPendingApproval(event, callbacks)`. The render function builds the DOM, attaches click handlers, and returns the root element.
- `the_one/interfaces/web/static/css/chat.css` — banner CSS (.`msg-pending-approval` + child element styles).
- `the_one/interfaces/web/static/index.html` (or wherever the chat JS modules are listed) — add a `<script>` tag for the new `pending-approval-banner.js` module.
- `tests/test_app_pending_approval_merge.py` — NEW backend test file for the `_restore_session` merge behavior.
- `tests/browser/test_flow_chat_pending_approval.py` — NEW browser test for banner render + approve flow + dismiss flow.
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — append L4 progress entry.

## Acceptance Criteria

- [ ] `the_one/db/codec.py` exports `pending_approvals_to_ui_events(rows: list[PendingApproval]) -> list[dict[str, Any]]`. Each output event has the canonical flight §5 shape: `{type: "pending-approval", approval_id, peer_name, peer_id, preview, received_at, connector_account_id, status}`. The projection function's docstring pins the shape and notes that L2's dispatcher emit produces an identical shape independently.
- [ ] `_restore_session` queries `pending_approval_repo.list_for_account_peer(connector_account_id, peer_id)` when `db_session.connector_account_id is not None and db_session.peer_id is not None`; merges the projected events into `ui_events` by sort-key `event.get("ts") or event.get("received_at") or ""` ascending; passes the merged list as `session.history`.
- [ ] `_build_session_joined_degraded` does the same merge for the degraded-session path.
- [ ] Sessions with no connector context (operator-typed sessions) get no pending_approvals query — short-circuit on the None check.
- [ ] `chat.js` `renderHistory` dispatch handles `ev.type === 'pending-approval'` by calling `App.chat.renderPendingApproval(ev, callbacks)` and appending the returned element.
- [ ] `chat.js` WS onmessage dispatch handles `data.type === 'pending-approval'` the same way.
- [ ] Chat.js maintains a Set (`seenApprovalIds`) of approval ids; render is skipped if the id was already seen. Reset on session-change (`renderHistory` reset OR explicit `currentSessionId` change).
- [ ] `App.chat.renderPendingApproval(event, callbacks)` lives in `pending-approval-banner.js`. Renders a `<div class="msg msg-pending-approval">` containing: peer-name + preview text (HTML-escaped via DOM APIs, not `innerHTML`); two `<button>` elements ("Approve" + "Dismiss") wired to `callbacks.onApprove(approval_id)` and `callbacks.onDismiss(approval_id)`; an attribution-style label showing the received_at timestamp. For terminal-status events (`approved`/`dismissed`), buttons are hidden and a status-badge element is shown instead.
- [ ] Click handlers POST to `/api/connector-accounts/{connector_account_id}/peer-approvals/{approval_id}/{action}`; on 200, re-render the banner with the new status; on non-200, surface a `system` message ("Approve failed: …") and leave the banner in its prior state.
- [ ] Banner CSS: `.msg-pending-approval` is left-aligned (parallel to `.msg-from-peer` at chat.css:139), uses `--surface-elevated` background, distinct border accent (e.g. `var(--accent)` or a new token), buttons styled as primary/secondary. Specific token choices are flexible; key invariant is the banner is visually distinct from regular user/assistant bubbles.
- [ ] Backend tests pass (`tests/test_app_pending_approval_merge.py`):
  - Restore on a session with connector context + an in-DB pending approval → `session.history` includes the pending-approval event.
  - Restore on a session with connector context but no pending approvals → history is byte-identical to pre-L4.
  - Restore on an operator-typed session (no connector context) → history is byte-identical to pre-L4 (no DB query for pending_approvals).
  - Merge ordering: messages with older `ts` precede pending-approvals with newer `received_at`, and vice versa.
  - Degraded-session path (`_build_session_joined_degraded`) merges identically.
- [ ] Browser test passes (`tests/browser/test_flow_chat_pending_approval.py`):
  - Seed a session with connector context + a pending approval; navigate to the chat; verify the banner renders with the expected peer_name + preview + two buttons.
  - Click Approve → expect the buttons to disappear and a status-badge to appear; expect the L3 endpoint to be called (verify via subsequent GET of the account showing the peer added to the allowlist).
  - Click Dismiss (on a fresh pending approval) → expect dismissed badge.
- [ ] Existing browser tests pass unchanged (`test_flow_chat_peer_attribution.py`, `test_flow_chat_visibility_distinction.py`).
- [ ] Existing backend tests pass unchanged (`test_app_websocket_pause_resume.py` and the WS-event surface).
- [ ] Existing dispatcher tests pass unchanged.

## Verification Steps

```bash
# New backend merge tests
docker exec the-one pytest tests/test_app_pending_approval_merge.py -x --timeout 30 -v

# New browser test (slower — requires Playwright + spawning the app)
docker exec the-one pytest tests/browser/test_flow_chat_pending_approval.py -x --timeout 120 -v

# Existing browser tests (regression net)
docker exec the-one pytest tests/browser/test_flow_chat_peer_attribution.py tests/browser/test_flow_chat_visibility_distinction.py -x --timeout 120 -v

# Existing API and dispatcher tests
docker exec the-one pytest tests/test_db_api.py tests/test_connectors_inbound.py tests/test_app_websocket_pause_resume.py -x --timeout 30

# Full suite (post-L3 baseline: 2706)
docker exec the-one pytest --timeout 120 -q
```

Expected: green. Suite count rises by ~5-8 (backend + browser tests). Browser tests are slower; budget more time on the timeout.

## Implementation Guidance

### Sub-step A — Codec projection

Add to `the_one/db/codec.py` after `messages_to_ui_events`:

```python
def pending_approvals_to_ui_events(
    rows: list[PendingApproval],
) -> list[dict[str, Any]]:
    """Convert PendingApproval rows to UI event dicts.

    M11 F9 L4. Used by ``_restore_session`` and ``_build_session_joined_degraded``
    to merge pending-approval banners into the per-session history stream.

    The output event shape is identical to the live-broadcast event the
    dispatcher emits at ``the_one/connectors/_inbound.py`` (F9 L2). The
    two emit sites are independent (this projection runs on restore;
    the dispatcher's hand-built dict runs on inbound); they MUST stay
    in sync or the frontend will see drift between live and replay.
    Verified by browser tests covering both paths.
    """
    return [
        {
            "type": "pending-approval",
            "approval_id": row.id,
            "peer_name": row.peer_name,
            "peer_id": row.peer_id,
            "preview": row.preview,
            "received_at": row.received_at,
            "connector_account_id": row.connector_account_id,
            "status": row.status,
        }
        for row in rows
    ]
```

Add a direct top-level `from the_one.db.models import PendingApproval` to `codec.py`. Circular concern is unfounded (verified): `codec.py` currently only imports `the_one.llm.base`; `models.py` does not import `codec.py`. Drop the forward-reference string in the annotation if added defensively.

### Sub-step B — Backend merge

Edit `the_one/interfaces/web/app.py`:

1. Extend the codec import (line 46) to also import `pending_approvals_to_ui_events`.

2. Add a `_pending_approval_repo()` factory in `app.py` adjacent to the existing `_chat_repo()` factory at `app.py:382`. (app.py has its own factory layer — `_chat_repo` is local, not imported from api.py. Mirror that convention. L3 already added an `_pending_approval_repo()` to `api.py:86` for the endpoint; app.py gets its own copy. Both call the same `PendingApprovalRepository(conn)` shape; they don't share scope.)

3. Extend `_restore_session` (lines 496-505) to merge pending_approvals after the existing `ui_events = messages_to_ui_events(messages)` line:

```python
ui_events = messages_to_ui_events(messages)

if (
    db_session.connector_account_id is not None
    and db_session.peer_id is not None
):
    pending_repo = await _pending_approval_repo()  # or inline
    pending_rows = await pending_repo.list_for_account_peer(
        db_session.connector_account_id, db_session.peer_id
    )
    if pending_rows:
        pending_events = pending_approvals_to_ui_events(pending_rows)
        # Merge by timestamp ascending; messages use ts, approvals use
        # received_at, both ISO8601 lexicographically sortable. Missing
        # ts (replay-side messages do not carry ts) float to the top.
        combined = ui_events + pending_events
        combined.sort(
            key=lambda e: e.get("ts") or e.get("received_at") or ""
        )
        ui_events = combined
```

4. Apply the same merge in `_build_session_joined_degraded` (line 617-632) BEFORE the `messages_to_ui_events(...)` call's result is returned in the `history` field.

### Sub-step C — Frontend dispatch

Edit `the_one/interfaces/web/static/js/areas/chat.js`:

1. Add a module-scoped `seenApprovalIds` Set near the existing module-scoped state (around line 290 alongside `currentStreamingMsg`):

```javascript
var seenApprovalIds = Object.create(null);
```

(Use a plain object as a Set for IE-compat-style code; the existing file uses `Object.create(null)` for `traceShells`. Match the convention.)

2. Reset the Set on session boundaries — TWO reset points, not one:
   - **Inside `renderHistory`** at line 233 alongside the existing `traceShells = Object.create(null)` reset (covers session-join via `session_joined` handler at line 788 which calls `renderHistory`).
   - **Inside `startSession`** at line 218-225 area (covers new-chat creation, which sets `currentSessionId = null` without calling `renderHistory`). Without this second reset, a stale `approval_id` could linger across new-chat creation.

```javascript
seenApprovalIds = Object.create(null);
```

3. Extend `renderHistory` (line 227-278) — add a new branch after the `system` case:

```javascript
else if (ev.type === 'pending-approval') {
  if (seenApprovalIds[ev.approval_id]) {
    continue;  // dedup against later live broadcast or duplicate restore
  }
  seenApprovalIds[ev.approval_id] = true;
  var banner = App.chat.renderPendingApproval(ev, {
    onApprove: onApproveClick,
    onDismiss: onDismissClick,
  });
  messagesEl.appendChild(banner);
}
```

Where `onApproveClick(approval_id)` and `onDismissClick(approval_id)` are local closures defined adjacent to `renderHistory` that POST to L3's endpoints.

4. Extend the WS onmessage dispatch (around line 859-940) — add a parallel `pending-approval` case after the `system` case:

```javascript
else if (data.type === 'pending-approval') {
  if (seenApprovalIds[data.approval_id]) {
    return;
  }
  seenApprovalIds[data.approval_id] = true;
  var banner = App.chat.renderPendingApproval(data, {
    onApprove: onApproveClick,
    onDismiss: onDismissClick,
  });
  messagesEl.appendChild(banner);
  scrollToBottomIfPinned();
}
```

5. Add the click-handler closures. They look up the connector_account_id from the event (which is embedded in the banner DOM via dataset attributes set by `renderPendingApproval`):

```javascript
function onApproveClick(approval_id, connector_account_id, bannerEl) {
  // Optimistic: hide buttons, show pending state.
  bannerEl.classList.add('msg-pending-approval-acting');
  var url = '/api/connector-accounts/' + connector_account_id +
    '/peer-approvals/' + approval_id + '/approve';
  fetch(url, { method: 'POST' })
    .then(function (resp) {
      if (resp.ok) {
        return resp.json().then(function (updated) {
          App.chat.applyApprovalStatus(bannerEl, updated.status);
        });
      } else {
        bannerEl.classList.remove('msg-pending-approval-acting');
        addMsg('system', 'Approve failed: HTTP ' + resp.status);
      }
    })
    .catch(function (e) {
      bannerEl.classList.remove('msg-pending-approval-acting');
      addMsg('system', 'Approve failed: ' + (e && e.message ? e.message : e));
    });
}

// onDismissClick is symmetric — same shape, /dismiss endpoint.
```

The exact callback signature (whether it passes the banner element or looks it up by id) is an implementation detail; pick the one that minimizes coupling between `renderPendingApproval` and the click handler. The simplest shape is: `renderPendingApproval` binds the handlers to its own internal buttons, taking the callbacks as `{onApprove, onDismiss}` (signature: `(approval_id, status) => void` — the handler is responsible for the fetch+re-render).

### Sub-step D — Banner module

Create `the_one/interfaces/web/static/js/areas/chat/pending-approval-banner.js`. **Module-scope rule**: this IIFE has its own scope — it MUST NOT reach for `addMsg` or any other chat.js-local symbol directly. All cross-module communication is via the `callbacks` parameter passed in by chat.js. The fetch + error reporting (which uses `addMsg('system', ...)`) lives in chat.js, NOT here.

```javascript
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // Builds a pending-approval banner element. Returns the root element
  // (not appended). Caller (renderHistory / WS dispatch) appends.
  //
  // Callbacks shape: { onApprove(approval_id, bannerEl), onDismiss(approval_id, bannerEl) }
  // For terminal-status events (approved/dismissed), the buttons are
  // omitted and a status badge is rendered instead.
  function renderPendingApproval(event, callbacks) {
    var el = document.createElement('div');
    el.className = 'msg msg-pending-approval';
    el.setAttribute('data-testid', 'pending-approval-banner');
    el.setAttribute('data-approval-id', event.approval_id);
    el.setAttribute('data-connector-account-id', event.connector_account_id);

    // Header: peer name + received_at timestamp.
    var header = document.createElement('div');
    header.className = 'msg-pending-approval-header';
    var name = document.createElement('span');
    name.className = 'msg-pending-approval-peer-name';
    name.textContent = event.peer_name;  // DOM API, XSS-safe.
    header.appendChild(name);
    var ts = document.createElement('span');
    ts.className = 'msg-pending-approval-ts';
    ts.textContent = event.received_at;
    header.appendChild(ts);
    el.appendChild(header);

    // Body: preview.
    var preview = document.createElement('div');
    preview.className = 'msg-pending-approval-preview';
    preview.textContent = event.preview;
    el.appendChild(preview);

    // Footer: buttons (pending) OR status badge (terminal).
    var footer = document.createElement('div');
    footer.className = 'msg-pending-approval-footer';
    if (event.status === 'pending') {
      var approveBtn = document.createElement('button');
      approveBtn.type = 'button';
      approveBtn.className = 'msg-pending-approval-approve';
      approveBtn.textContent = 'Approve';
      approveBtn.addEventListener('click', function () {
        if (callbacks && callbacks.onApprove) {
          callbacks.onApprove(event.approval_id, event.connector_account_id, el);
        }
      });
      footer.appendChild(approveBtn);
      var dismissBtn = document.createElement('button');
      dismissBtn.type = 'button';
      dismissBtn.className = 'msg-pending-approval-dismiss';
      dismissBtn.textContent = 'Dismiss';
      dismissBtn.addEventListener('click', function () {
        if (callbacks && callbacks.onDismiss) {
          callbacks.onDismiss(event.approval_id, event.connector_account_id, el);
        }
      });
      footer.appendChild(dismissBtn);
    } else {
      var badge = document.createElement('span');
      badge.className = 'msg-pending-approval-badge msg-pending-approval-badge--' + event.status;
      badge.textContent = event.status;
      footer.appendChild(badge);
    }
    el.appendChild(footer);

    return el;
  }

  // Apply a new status to an existing banner (post-Approve / post-Dismiss).
  // Removes the buttons (if present) and adds the badge.
  function applyApprovalStatus(bannerEl, status) {
    var footer = bannerEl.querySelector('.msg-pending-approval-footer');
    if (!footer) return;
    while (footer.firstChild) footer.removeChild(footer.firstChild);
    var badge = document.createElement('span');
    badge.className = 'msg-pending-approval-badge msg-pending-approval-badge--' + status;
    badge.textContent = status;
    footer.appendChild(badge);
    bannerEl.classList.remove('msg-pending-approval-acting');
  }

  window.App.chat.renderPendingApproval = renderPendingApproval;
  window.App.chat.applyApprovalStatus = applyApprovalStatus;
})();
```

Add a `<script>` tag for this module in `the_one/interfaces/web/static/index.html`. The existing `message-bubble.js` script tag is at line 41-ish; `chat.js` is at line 45-ish. Place the new tag adjacent to `message-bubble.js` and BEFORE `chat.js` so the `App.chat.renderPendingApproval` binding exists when `chat.js`'s WS handler dispatches.

### Sub-step E — CSS

Add to `the_one/interfaces/web/static/css/chat.css` (near the other `.msg-*` declarations, e.g. after `.msg-from-peer` at line 139):

```css
.area-chat .msg.msg-pending-approval {
  align-self: flex-start;
  background: var(--surface-elevated);
  color: var(--fg);
  border: 1px solid var(--accent);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 80%;
}

.area-chat .msg-pending-approval-header {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-small);
}

.area-chat .msg-pending-approval-peer-name {
  font-weight: 600;
}

.area-chat .msg-pending-approval-ts {
  color: var(--fg-faint);
  font-family: var(--font-family-mono);
  font-size: var(--font-size-tiny);
}

.area-chat .msg-pending-approval-preview {
  font-style: italic;
  color: var(--fg-secondary);
}

.area-chat .msg-pending-approval-footer {
  display: flex;
  gap: 8px;
  align-items: center;
}

.area-chat .msg-pending-approval-approve {
  /* operator-affirmative — primary button styling */
  background: var(--accent);
  color: var(--fg-on-accent);
  border: 1px solid var(--accent);
  padding: 4px 12px;
  cursor: pointer;
  border-radius: 4px;
}

.area-chat .msg-pending-approval-dismiss {
  background: transparent;
  color: var(--fg-faint);
  border: 1px solid transparent;
  padding: 4px 12px;
  cursor: pointer;
  text-decoration: underline;
}

.area-chat .msg-pending-approval-badge {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-tiny);
  padding: 2px 8px;
  border-radius: 4px;
}

.area-chat .msg-pending-approval-badge--approved {
  background: var(--success-bg, #2a4a2a);
  color: var(--success-fg, #cde7cd);
}

.area-chat .msg-pending-approval-badge--dismissed {
  background: var(--surface-elevated);
  color: var(--fg-faint);
}

.area-chat .msg-pending-approval-acting {
  opacity: 0.6;
  pointer-events: none;
}
```

Token names (`--accent`, `--surface-elevated`, `--fg-on-accent`, `--fg-faint`, `--fg-secondary`) match existing tokens. `--success-bg` / `--success-fg` are NOT defined in `tokens.css` — the CSS uses literal fallbacks (`#2a4a2a`, `#cde7cd`) which suffice for L4. Do NOT add new tokens at L4 — note in the flight log that these tokens could be added at the next routine-maintenance pass; L4 stays scoped to the leg's deliverables.

### Sub-step F — Backend tests

Create `tests/test_app_pending_approval_merge.py`:

Tests (one function each):
1. `test_restore_session_with_connector_context_merges_pending_approval` — seed a session with `connector_account_id` + `peer_id`; insert a pending_approval row via the repo; call `_restore_session`; verify the returned `session.history` contains a `pending-approval` event with the expected shape.
2. `test_restore_session_with_connector_context_no_approvals_unchanged` — seed a connector session with no pending approvals; verify history is identical to pre-L4 (no pending events).
3. `test_restore_session_without_connector_context_skips_pending_approvals_query` — seed an operator-typed session; verify no DB query for pending_approvals (use a monkeypatched repo that raises if called).
4. `test_restore_session_merge_orders_by_timestamp` — seed a session with messages at t1 and t3, plus a pending approval at t2; verify history order is `[msg_t1, approval_t2, msg_t3]`.
5. `test_build_session_joined_degraded_merges_pending_approvals` — parallel to #1 but on the degraded path.
6. `test_restore_with_pre_existing_pending_in_history_does_not_dup` — seeds a session whose history (via the merge) contains a pending-approval; verify the returned `session.history` does NOT contain duplicate entries for the same `approval_id` (the backend dedup is structural — `list_for_account_peer` returns the pending row once; we're verifying that no codec quirk emits it twice).

### Sub-step G — Browser test

Create `tests/browser/test_flow_chat_pending_approval.py`. Mirror the fixture / seeder shape from `test_flow_chat_peer_attribution.py`. Tests:
1. `test_pending_approval_banner_renders_on_session_join` — seed a session with a pending approval; navigate; expect the banner element with the correct peer_name + preview + two buttons.
2. `test_pending_approval_approve_click_updates_status_and_calls_api` — click Approve; expect the buttons to be replaced with the `approved` badge; verify (via direct API check or DB query) the L3 endpoint mutated the allowlist.
3. `test_pending_approval_dismiss_click_updates_status` — same shape for Dismiss.
4. `test_pending_approval_dedup_replay_then_live_broadcast` — seed a session with a pending approval; navigate (renderHistory inserts banner #1); send a duplicate live broadcast WS event for the same `approval_id`; verify exactly ONE banner element in the DOM. Use the chat.js `seenApprovalIds` Set as the dedup mechanism.

### Sub-step H — Flight log

Append to `flight-log.md` under "Leg Progress":

```
### {date} — L4 chat-ui-pending-approval (landed)

**Status**: ready → in-flight → landed

**Changes made**:
- `the_one/db/codec.py` — added `pending_approvals_to_ui_events`.
- `the_one/interfaces/web/app.py` — extended `_restore_session` and `_build_session_joined_degraded` to merge pending_approvals into history by timestamp when the session has connector context.
- `the_one/interfaces/web/static/js/areas/chat.js` — added `seenApprovalIds` dedup Set; extended `renderHistory` and WS onmessage dispatch with the `pending-approval` case; added click handlers that POST to L3 endpoints with optimistic-update + reconciliation.
- `the_one/interfaces/web/static/js/areas/chat/pending-approval-banner.js` — NEW module: `App.chat.renderPendingApproval` + `applyApprovalStatus`.
- `the_one/interfaces/web/static/css/chat.css` — banner CSS.
- `the_one/interfaces/web/static/index.html` — added script tag for the new banner module.
- `tests/test_app_pending_approval_merge.py` — NEW backend tests.
- `tests/browser/test_flow_chat_pending_approval.py` — NEW browser tests.

**Test outcomes**: new tests pass; pre-existing browser tests and backend WS tests pass unchanged. Suite count: 2706 → {N}.

**Anomalies**: {document any token-mismatch in chat.css, banner-module script-tag location surprises, etc.}
```

## Edge Cases

- **Session has connector_account_id but no peer_id** (shouldn't happen — `_inbound.py` always sets both for connector sessions) — short-circuit on the explicit `peer_id is not None` check; skip the query.
- **Pending approval row references a peer_id that no longer matches `account.config["allowlist"]["peers"]`** — render the banner regardless; L1's resolver hits the allowlist check next inbound. L4 is read-only; consistency between approval rows and allowlist is L3's responsibility.
- **Two browser windows open on the same session, both click Approve simultaneously** — both POSTs hit L3; first wins (mutation lands); second is idempotent (returns the existing approved row); both UIs render the approved badge.
- **Operator clicks Approve, the POST is in-flight, the WS broadcasts a pending-approval for the SAME approval_id (from a duplicate dispatcher emit)** — the WS dispatch's `seenApprovalIds` check skips re-render. The optimistic-update path proceeds normally.
- **`event.preview` is empty string** — banner renders with an empty preview area. Acceptable (matches L2's "empty text edge case" disposition).
- **`event.preview` contains HTML / control characters** — `textContent` assignment escapes; no XSS surface. Validated by DOM API contract.
- **CSS tokens referenced in this leg's CSS are missing in `tokens.css`** — fallback values in the CSS rules (e.g. `var(--success-bg, #2a4a2a)`) provide a literal fallback. Document any missing-token surface in the flight log for routine-maintenance.
- **The banner module load order** — `pending-approval-banner.js` must load BEFORE `chat.js` (or be loaded async with the WS-handler check guarding against missing `App.chat.renderPendingApproval`). Easiest: ensure the script-tag order in the template matches the existing `message-bubble.js` precedent.
- **Session that has both messages and approvals, with `ts` field on some message events but not others** (replay-side messages have no `ts`; live-broadcast events have `ts`) — the sort key `(e.get('ts') or e.get('received_at') or '')` puts ts-less messages first. Acceptable.

## Files Affected

- `the_one/db/codec.py` — +25 LOC projection function.
- `the_one/interfaces/web/app.py` — +25-40 LOC across `_restore_session` and `_build_session_joined_degraded`.
- `the_one/interfaces/web/static/js/areas/chat.js` — +60-80 LOC (seenApprovalIds, two dispatch cases, two click-handler closures).
- `the_one/interfaces/web/static/js/areas/chat/pending-approval-banner.js` — NEW, ~120 LOC.
- `the_one/interfaces/web/static/css/chat.css` — +60 LOC.
- `the_one/interfaces/web/templates/<index>.html` — +1 line (script tag).
- `tests/test_app_pending_approval_merge.py` — NEW, ~200 LOC.
- `tests/browser/test_flow_chat_pending_approval.py` — NEW, ~250 LOC.
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — append L4 entry.

Estimated total: ~700-900 LOC. L4 is the largest leg in F9.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All new tests pass; pre-existing tests pass unchanged
- [ ] Update flight-log.md with L4 progress entry (template above)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

11 citations verified against current code at leg design time:
- `the_one/interfaces/web/app.py:426-535` (`_restore_session`) — OK
- `the_one/interfaces/web/app.py:617-632` (`_build_session_joined_degraded`) — OK
- `the_one/interfaces/web/app.py:46` (codec import) — OK
- `the_one/db/codec.py:153-279` (`messages_to_ui_events`) — OK
- `the_one/db/models.py:475-484` (PendingApproval; landed at L2) — OK
- `the_one/db/models.py:535` (`ChatSession.platform`) — OK
- `the_one/interfaces/web/static/js/areas/chat.js:227-278` (`renderHistory`) — OK
- `the_one/interfaces/web/static/js/areas/chat.js:859-940` (WS onmessage) — OK
- `the_one/interfaces/web/static/js/areas/chat.js:116-136` (`addMsg`) — OK
- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js:1-137` (renderMessage / renderAttribution) — OK
- `the_one/interfaces/web/static/css/chat.css:139` (.msg-from-peer precedent) — OK
