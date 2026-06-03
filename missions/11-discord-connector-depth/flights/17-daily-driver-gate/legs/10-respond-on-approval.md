# Leg: respond-on-approval

**Status**: completed
**Flight**: [Daily-driver validation gate](../flight.md)
**Type**: injected (substrate + connector) — L3 once-over Leg F. After Legs D + E. Visual acceptance: `discord-approval-flow` (with D/E).

## Objective

When the operator approves a pending peer, the bot **proactively answers the peer's ORIGINAL message** (option ii) — not just a greeting — so the peer's first question gets answered the moment they're approved, closing the loop: unknown DM → "you're pending" (E) → operator approves (D) → **bot answers their first question** (F).

## Context

- After Leg D, `approve_peer_approval` (`api.py:2826`) adds the peer as allowed (`{id}`). Today it does NOT message the peer — they'd have to DM again.
- `PendingApproval` (`models.py:669`) stores only a truncated `preview` of the first message — not enough to faithfully replay. **Option (ii) (operator-chosen)** requires persisting the **full original first message** (+ enough envelope context to re-dispatch it: peer_id, channel_id, is_dm).
- The cleanest replay: on approve, reconstruct the inbound and run it through the normal `dispatch_inbound` (routing → agent.step → outbound send) now that the peer is admitted — reusing all existing logic rather than a bespoke step+send path. (Design review to confirm re-dispatch vs bespoke.)
- **Mission constraints:** no agent-loop change (re-dispatch uses the existing dispatcher; it does not modify `agent/core.py`); no env-var seam.

## Resolved at design review (implement to these — cite file:line)

- **Storage = additive migration v29** (D took v28): `ALTER TABLE pending_approvals ADD COLUMN` for `original_message TEXT`, `channel_id TEXT`, `thread_id TEXT`, `is_dm INTEGER` (nullable, simple additive — NOT a row-rewrite). Update `PendingApproval` model (`models.py:670`) + `PendingApprovalRepository._row_to_model` (`repositories.py:743`) + `upsert_pending` (add the new params — **reads E's diff, which already changed the return to `(row, created)`**). Store the fields in the inbound pending branch (`_inbound.py:453-458`) where `envelope` is in scope (`envelope.channel_id/thread_id/text`; `is_dm=True` for the DM-originated pending). `original_message` = full `envelope.text` (NOT the truncated `preview`).
- **Replay = re-dispatch via `dispatch_inbound`** (the right mechanism — reuses routing→session→policy-gate→agent.step→outbound). In `approve_peer_approval` (`api.py:2826`), AFTER `mark_approved` + the allowlist add (so admission passes): `from the_one.agent.factory import get_factory; factory = get_factory()` — **guard `if factory is None: log + return`** (the `_discord.py:1033-1050` pattern; do NOT construct a bare `AgentFactory()` — it has `store=None` and 404s every agent). Reconstruct `InboundEnvelope(platform=account.type, account_id=approval.connector_id, channel_id=approval.channel_id, thread_id=approval.thread_id, peer_id=approval.peer_id, peer_name=approval.peer_name, text=approval.original_message, raw={"is_dm": True})` — **`raw={"is_dm": True}` is required** (the policy gate checks `envelope.raw.get("is_dm") is True`, `_inbound.py:218`; without it the replay may not engage). Then `await dispatch_inbound(account_id, envelope, factory=factory)`.
- **Background + failure-safe:** wrap the replay in `asyncio.create_task` + a module-level `_inflight_replay_tasks` set (mirror `_inflight_save_warm_tasks`, `api.py:2437`/`:2575-2577`) so the approve HTTP response returns immediately and an agent/send error doesn't fail the approval. The approval (mark_approved + allowlist add) commits BEFORE the task is created.
- **Send-once:** `mark_approved` (`repositories.py:718`) is idempotent (early-returns if already approved) — a concurrent double-approve → one task. Mark approved before the replay task.
- **Legacy rows (no `original_message`):** in the background task, `if not approval.original_message: log.info(...); return` — approval still succeeded, just no proactive answer. No crash.

## Acceptance Criteria

- [x] **Persist the original message + replay context** on `PendingApproval` (a new field e.g. `original_message` + whatever envelope context — `channel_id` — is needed to re-dispatch; preview stays for display). Migration (vN) if a column add is needed; design picks column-add vs JSON. Truncation only for `preview`, full text for replay.
- [x] **On approve, the bot answers the original message:** `approve_peer_approval` (after adding the peer) reconstructs the inbound from the stored original message + context and runs it through `dispatch_inbound` (or the agreed replay path) → the peer receives the agent's answer to their first question on Discord. The peer is admitted (Leg D), so admission passes; routing → agent.step → outbound send all happen via the normal path.
- [x] **Send-once / no double-processing:** the original message is replayed exactly once on approval (not re-stored as a new pending, not double-sent). After replay, the pending row is terminal (status=approved); the original-message field can be cleared/retained per design.
- [x] **Failure-safe:** if the replay/send fails (agent error, rate limit, pool cold), the approval still succeeds (the peer is approved); the failure is logged, not fatal to the approve request. (Approval and response are decoupled — approval must not roll back on a response failure.)
- [x] Full backend suite green; tests for: original-message persisted, approve triggers a re-dispatch/answer, failure-safe (approve succeeds even if replay fails), send-once.

## Verification Steps

- Persist: an unknown DM creates a pending row carrying the full original message + channel context.
- Approve → answer: approving the peer re-dispatches the original message → the agent's reply is sent to the peer's DM (stub the connector send in unit tests; live in the behavior test).
- Failure-safe: force the replay to fail → the approve request still returns success + the peer is approved.
- Behavior: `discord-approval-flow` step 5 (bot answers Chuck R's original question after approval).

## Implementation Guidance

1. **Persist original message:** extend `PendingApproval` (`models.py:669`) with the full original message + the replay context (`channel_id`, `is_dm`, anything `dispatch_inbound` needs that isn't already on the row). Set it in the inbound pending branch (`_inbound.py` ~`:449-465`) where the row is created. Migration if a column add (follow the v28 pattern / the migrations module).
2. **Replay on approve:** in `approve_peer_approval` (`api.py:2826`), after adding the peer, reconstruct the `InboundEnvelope` from the stored fields and call `dispatch_inbound` (the same entry the gateway uses) — so routing/step/send happen normally now that the peer is admitted. Do this in a way that doesn't block the approve HTTP response on the agent step (consider `asyncio.create_task`, like Leg A's save-warm) — surface failures via logs, not the approve response.
3. **Send-once + terminal:** mark the pending approved before/after replay so it can't be replayed twice; decide whether to clear the stored message.
4. **Failure isolation:** wrap the replay so an agent/send error doesn't fail the approval.
5. Tests: persisted original message; approve→re-dispatch (stub the dispatcher/send); failure-safe; send-once.

## Edge Cases

- **No original message stored** (legacy pending row from before this leg): approve still works; just no proactive answer (fall back to a simple greeting or nothing — design picks; don't crash).
- **Decouple approval from response:** the approval MUST commit even if the response fails (the operator's action succeeded). Background the replay.
- **The replayed message must be admitted** — it is, because Leg D added the peer as allowed before the replay. Confirm ordering (add-peer THEN replay).
- **No agent-loop change:** re-dispatch uses the existing `dispatch_inbound`; do not alter the agent loop.

## Files Affected

- `the_one/db/` + `the_one/db/models.py` — `PendingApproval` original-message + context fields; migration if needed.
- `the_one/connectors/_inbound.py` (~`:449-465`) — persist the original message on row creation.
- `the_one/interfaces/web/api.py` (`approve_peer_approval` ~`:2826`) — replay the original message via `dispatch_inbound` after adding the peer; background + failure-safe.
- `tests/…` — persist, replay, failure-safe, send-once.

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing (backend; full suite green — 2935 passed / 4 skipped / 536 deselected)
- [x] Flight log updated; leg status `landed` (→ `completed` at DM-cluster commit)
- [x] Commit deferred to DM-cluster batch (after the `discord-approval-flow` behavior test)
