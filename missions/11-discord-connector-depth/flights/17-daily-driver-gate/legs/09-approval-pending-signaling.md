# Leg: approval-pending-signaling

**Status**: completed
**Flight**: [Daily-driver validation gate](../flight.md)
**Type**: injected (UI + connector) — L3 once-over Leg E. Builds on Leg D's approve semantics. Visual acceptance: `discord-approval-flow` (with D/F).

## Objective

Make a first-time unknown DM **visible to the operator** and **acknowledged to the sender**: (1) flag the pending approval in the Chat UI's left panel, (2) show a notification badge on the top-nav **Chat** button (visible from any screen) driven by the live pending-approval count, and (3) send the unknown DMer a **one-time Discord auto-reply** telling them they're awaiting approval — so they don't get dead air.

## Context

- When an unknown user DMs without a `PAIR` prefix, `_inbound.py` (the `NeedsPairing` / no-PAIR branch, ~`:449-465`) upserts a `PendingApproval` row + emits a pending-approval audit event, then **returns WITHOUT replying** — the sender gets silence (operator-observed at F3).
- `PendingApproval` (`models.py:669`): `id, connector_id, peer_id, peer_name, preview, status (pending|approved|dismissed), received_at, resolved_at`.
- A Chat-UI pending-approval surface exists (F9 L4) — but there's no **left-panel flag** and no **cross-screen top-nav badge**.
- **Mission constraints:** no agent-loop change; no env-var seam.

## Resolved at design review (implement to these — cite file:line)

- **Send-once detection:** `upsert_pending` (`repositories.py:652-696`) does a SELECT-then-INSERT/UPDATE but its return doesn't signal create-vs-update. **Change its signature to return `(PendingApproval, created: bool)`** (caller `_inbound.py:453` becomes `approval, created = await ...` — non-breaking). The auto-reply fires only when `created is True`. *(F adds the new storage columns to this same function later — F reads E's diff, B↔C-style.)*
- **Auto-reply send shape** (insert after the upsert/created-check, before `broadcast_to_session` at `_inbound.py:459`, guarded `if created:`): `client = await account_acquire(account_id); await client.send(OutboundTarget(channel_id=envelope.channel_id, thread_id=envelope.thread_id), "<friendly text>")` — the F2 L2 precedent at `_inbound.py:588-595`. Wrap in `try/except Exception` (log + continue, like `:596-605`) so a send failure doesn't crash the pending path. `account_id` + `envelope` are in scope. **Default copy:** "Thanks for reaching out! Your message is waiting for the operator to approve you — you'll get a reply here once they do." (operator may tweak at the visual gate).
- **Count endpoint:** no list endpoint exists (only POST approve/dismiss at `api.py:2762`/`:2839`). Add `GET /api/connectors/peer-approvals/pending-count` → `{count: N}` (global `SELECT COUNT(*) FROM pending_approvals WHERE status='pending'`). Lightweight, no secret leak.
- **Top-nav badge:** the Chat button is generated in `app.js renderTopBar()` (~`:22-26`) and has **no testid** — add `data-testid="nav-chat-btn"` + a badge `<span>` child. **POLL** the count endpoint every **10s** (the Chat WS is session-scoped — `broadcast_to_session`, `sessions/_broadcast.py:42` — no global push channel; poll is correct). Badge hidden at count 0.
- **Left-panel flag (NOT the F9 banner):** the F9 L4 pending surface is the message-area banner (`pending-approval-banner.js`); the left panel is rendered by `renderSessionList`/`buildSessionItem` (`history-buckets.js:45-111`). Add a **pinned "Pending approvals" section ABOVE the "Chat History" heading** in `renderSessionList` (pending approvals aren't sessions — don't shoehorn them into the recency buckets).

## Acceptance Criteria

- [x] **Discord one-time auto-reply:** when a `PendingApproval` row is **newly created** (first unknown DM), the bot sends the sender a single Discord DM (e.g. "Thanks — your message is awaiting the operator's approval; you'll get a reply once approved."). **Send-once:** only on new-row creation, NOT on every subsequent DM while still pending (the upsert dedups — only the create path replies). Sent via the connector's outbound (`account_acquire → client.send` to the DM channel), in the inbound pending branch. No reply on repeat DMs while pending.
- [x] **Top-nav Chat badge:** the top-nav "Chat" button shows a notification badge with the **count of pending approvals** (`PendingApproval` where status=pending, across connectors). Visible from any screen. Updated live — pushed via the existing WS channel if one exists, else a lightweight poll. Clears to 0 when none pending.
- [x] **Chat left-panel flag:** the pending approval is flagged in the Chat UI's left panel (the sessions/conversations list) so it reads as "needs action" (an indicator on the pending item / a pending-approvals entry). Reuses/extends the F9 L4 pending surface.
- [x] **Count source:** a backend read-path returns the pending-approval count (and/or list) — a small endpoint or extend an existing one. No secret leak.
- [x] Full backend + browser suites green; tests for the auto-reply send-once, the count endpoint, the badge render.

## Verification Steps

- Auto-reply: an unknown DM creates a pending row → exactly one Discord DM sent to the sender; a second DM from the same (still-pending) sender → NO new reply (upsert, no new-row).
- Badge: with N pending approvals, the Chat nav button shows badge=N; approving/dismissing decrements; 0 → no badge.
- Left-panel: the pending item is flagged in the Chat left panel.
- Behavior: `discord-approval-flow` steps 2-3 (Chuck R gets the auto-reply; the-one shows badge + flag).

## Implementation Guidance

1. **Auto-reply (connector):** in the inbound pending-approval branch (`_inbound.py` ~`:449-465`), on the **new-row** path (the upsert returns created-vs-existing, or check the row was newly inserted), send a one-time DM via the connector's outbound send (mirror the existing outbound-from-inbound shape — F2 L2 `account_acquire → client.send`). Guard so it fires only on creation. Keep the message generic + friendly; no secrets.
2. **Count endpoint (backend):** add/extend a read-path for the pending-approval count (e.g. `GET /api/connectors/peer-approvals/pending-count` or extend the existing peer-approvals list endpoint). Used by the badge.
3. **Top-nav badge (frontend):** find the top-nav Chat button; add a badge element bound to the pending count (WS push if the Chat WS carries approval events, else poll the count endpoint on an interval). Scope to pending approvals now; shape so it could generalize later.
4. **Left-panel flag (frontend):** extend the Chat left-panel rendering (the F9 L4 pending surface / the sessions list) to flag pending approvals.
5. Tests: auto-reply send-once (unit, stub the connector send); count endpoint; badge render (browser).

## Edge Cases

- **Send-once:** the upsert dedups one row per (connector, peer). Only the CREATE replies — a repeat DM while pending must not re-reply (avoid spam). Confirm the upsert exposes created-vs-existing.
- **Auto-reply failure:** if the Discord send fails (rate limit, etc.), don't crash the inbound path — log + continue (the pending row still exists for the operator).
- **Badge across connectors:** the count is global (all connectors) — the operator wants one "something needs action" signal.
- **No secret leak** in the count endpoint / the auto-reply.

## Files Affected

- `the_one/connectors/_inbound.py` (~`:449-465`) — one-time auto-reply on new pending row.
- `the_one/interfaces/web/api.py` — pending-approval count read-path.
- `the_one/interfaces/web/static/js/` — top-nav Chat badge + Chat left-panel pending flag (the nav module + the chat area / F9 L4 surface).
- `tests/…` — auto-reply send-once, count endpoint, badge browser test.

---

## Post-Completion Checklist
- [ ] All acceptance criteria verified
- [ ] Tests passing (backend + browser)
- [ ] Flight log updated; leg status `landed` (→ `completed` at DM-cluster commit)
- [ ] Commit deferred to DM-cluster batch (after the `discord-approval-flow` behavior test)
