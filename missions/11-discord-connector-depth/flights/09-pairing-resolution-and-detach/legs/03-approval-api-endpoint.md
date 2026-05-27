# Leg: approval-api-endpoint

**Status**: completed
**Flight**: [Pairing Resolution + Connectors-Screen Detach](../flight.md)

## Objective

Land two POST endpoints — `approve` and `dismiss` — that transition a `pending_approvals` row to its terminal state; on `approve`, also mutate `account.config["allowlist"]["peers"]` (idempotent add) so subsequent DMs from the peer flow through L1's resolver as `Permit`.

## Context

**Why this leg.** L2 created the `pending_approvals` storage layer + dispatcher emit. L4 (next) renders the banner in the Chat UI and POSTs click handlers to these endpoints. L3 wires the action edge: API → repo `mark_approved` / `mark_dismissed` + the allowlist mutation that turns approval into actual access.

**Endpoint shape (flight §6, locked at planning)**:
- `POST /api/connector-accounts/{account_id}/peer-approvals/{approval_id}/approve` — flip status `pending → approved`; add `peer_id` to `account.config["allowlist"]["peers"]` (idempotent); return the updated `pending_approval` row.
- `POST /api/connector-accounts/{account_id}/peer-approvals/{approval_id}/dismiss` — flip status `pending → dismissed`; do NOT mutate allowlist; return the updated row.

Body is empty (action is in the URL path); response is the updated approval row as JSON.

**Authorization** (flight §6 lock): operator-only. Single-user local-tool security posture — same as every other endpoint on `/api/`. No auth check beyond whatever middleware the router already applies.

**Idempotency** (cycle-2 architect):
- `approve` on an already-`approved` row returns the existing row, 200. The repo's `mark_approved` is idempotent-on-self-target per L2 design.
- `dismiss` on an already-`dismissed` row returns the existing row, 200.
- `approve` on a `dismissed` row (or `dismiss` on an `approved` row) → 409 Conflict (terminal-state mismatch; the repo raises `ValueError`).

**Allowlist mutation idempotency**: if `peer_id` is already in `account.config["allowlist"]["peers"]`, the add is a no-op. The repo update is unconditional (still a write) — keep it that way to match existing mutation patterns at `_inbound.py:432-438` and the pairing-code endpoint (single mutation site, single round-trip through `model_validate`, single `repo.update`).

**Race semantics** (flight §3, cycle-2 architect note): approval-while-detach is acceptable — the peer becomes allowlisted, even if no agent is currently attached. No defensive check at L3.

**No account-type gating**: this endpoint operates on `pending_approvals` rows, which only exist for connector types whose plugin's `resolve()` returns `NeedsPairing` (currently Discord — L1). The endpoint does NOT check `account.type == "discord"`. If a future test or operator action creates a pending_approvals row against a non-Discord account, the endpoint still consumes it. Account-type gating belongs at the plugin layer (resolve hook), not the API layer.

**404 vs 400 semantics**:
- Unknown `account_id` → 404 (matches existing `_connector_repo().get(account_id)` KeyError → HTTPException(404) pattern at `api.py:2520, 2553-2555`).
- Unknown `approval_id` → 404.
- `approval_id` exists but `connector_account_id` doesn't match the URL's `account_id` → 404 (the resource doesn't exist at this URL; not exposing the actual account id is a tiny defense-in-depth even under the single-user local-tool posture).
- Terminal-state mismatch (approve a dismissed row) → 409 Conflict.

## Inputs

- L2 outputs: `PendingApprovalRepository`, `PendingApproval` model, `mark_approved` / `mark_dismissed` methods on the repo, schema v21.
- `the_one/interfaces/web/api.py:74-77` — `_connector_repo()` factory pattern; L3 adds a parallel `_pending_approval_repo()`.
- `the_one/interfaces/web/api.py:34-43` — repo-import block; L3 extends with `PendingApprovalRepository`.
- `the_one/interfaces/web/api.py:25-33` — model-import block; L3 extends with `PendingApproval` (used by the response-type annotation, though FastAPI will accept `dict` too — pick `dict[str, Any]` to match the project's existing return shapes at `api.py:2570` and `api.py:2530`).
- `the_one/interfaces/web/api.py:2527-2570` — `generate_connector_account_pairing_code` endpoint; precedent for: 404 on unknown account, `_connector_repo` usage, `account.model_copy(update={"config": new_config})` + `ConnectorAccount.model_validate(updated.model_dump())` + `await repo.update(updated)` pattern.
- `the_one/interfaces/web/api.py:2573-2634` — `list_attached_agents_for_connector_account` endpoint; precedent for nested-resource URL convention.
- `tests/test_db_api.py:1355-1497` — `TestConnectorAccountPairingCodeAndAttached` class; L3 adds a parallel `TestConnectorAccountPeerApprovals` class.
- `tests/test_db_api.py:1384-1412` — `_isolation` autouse fixture pattern; L3's new class redeclares it verbatim (class-scoped autouse does not propagate).
- `tests/test_db_api.py:1414-1422` — `_create_account` helper pattern.

## Outputs

- `the_one/interfaces/web/api.py` — new helpers (`_pending_approval_repo()`); new endpoints (`approve_peer_approval`, `dismiss_peer_approval`); imports extended for `PendingApproval` (model) and `PendingApprovalRepository`. Endpoint URLs use `peer-approvals` (kebab-case noun, matching `pairing-code` and `attached-agents` siblings).
- `tests/test_db_api.py` — new `TestConnectorAccountPeerApprovals` class with ~10 endpoint tests.
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — append L3 progress entry.

L3 does NOT touch: `the_one/db/*` (storage already complete from L2), connector dispatcher (no inbound-side change), any static JS (L4 is the UI).

## Acceptance Criteria

- [ ] `_pending_approval_repo()` factory in `api.py` constructs a `PendingApprovalRepository(conn)` from `get_connection()`. No encryptor (mirrors `_chat_repo` shape).
- [ ] `POST /api/connector-accounts/{account_id}/peer-approvals/{approval_id}/approve` exists with these properties:
  - 404 when `account_id` is unknown.
  - 404 when `approval_id` is unknown.
  - 404 when `approval_id` exists but its `connector_account_id` does not match the URL's `account_id`.
  - 409 Conflict when the approval is currently `dismissed` (terminal-mismatch).
  - 200 + updated approval row JSON when the approval was `pending` (status flips to `approved`, `resolved_at` set, peer added to allowlist).
  - 200 + existing approval row JSON when the approval was already `approved` (idempotent; allowlist mutation re-applied as no-op).
  - Allowlist mutation is idempotent: re-approval does NOT duplicate `peer_id` in `account.config["allowlist"]["peers"]`.
  - Allowlist mutation preserves all other `config` keys (e.g. `pairing`, `intents`, `channels`).
  - Empty/missing `account.config["allowlist"]` is initialized to `{"peers": [<peer_id>], "channels": []}` (mirrors dispatcher pattern at `_inbound.py:428-438`).
- [ ] `POST /api/connector-accounts/{account_id}/peer-approvals/{approval_id}/dismiss` exists with parallel properties:
  - 404 / 409 semantics identical to `approve` (with the terminal targets swapped).
  - 200 + updated row when `pending`; 200 + existing row when already `dismissed`.
  - Does NOT mutate `account.config["allowlist"]`.
- [ ] Response shape — JSON dict with keys: `id`, `connector_account_id`, `peer_id`, `peer_name`, `preview`, `received_at`, `status`, `resolved_at`. Field names match the Pydantic model.
- [ ] New tests pass:
  - approve happy path (pending → approved + allowlist add).
  - approve idempotent on already-approved.
  - approve 409 on dismissed.
  - approve 404 on unknown account / approval / cross-account.
  - approve preserves other config keys.
  - approve idempotent allowlist (re-approve does not duplicate peer_id).
  - dismiss happy path (pending → dismissed, no allowlist mutation).
  - dismiss idempotent on already-dismissed.
  - dismiss 409 on approved.
  - dismiss 404 on unknown account / approval / cross-account.
- [ ] Existing tests pass unchanged (`test_db_api.py`, `test_connectors_inbound.py`, `test_db_repositories.py`).

## Verification Steps

```bash
# Run the new endpoint tests
docker exec the-one pytest tests/test_db_api.py -k "PeerApprovals" -x --timeout 30 -v

# Pre-existing API tests must remain green
docker exec the-one pytest tests/test_db_api.py -x --timeout 30

# L2 outputs untouched
docker exec the-one pytest tests/test_db_repositories.py tests/test_connectors_inbound.py tests/test_db_migration.py -x --timeout 30 -q

# Full suite (baseline post-L2: 2689)
docker exec the-one pytest --timeout 60 -q
```

Expected: all green; suite count rises by ~10.

## Implementation Guidance

### Sub-step A — Helper + imports

1. Edit `the_one/interfaces/web/api.py:25-43`:
   - Add `PendingApproval` to the `from the_one.db.models import (...)` tuple (alphabetical).
   - Add `PendingApprovalRepository` to the `from the_one.db.repositories import (...)` tuple (alphabetical).

2. Add helper adjacent to `_connector_repo` (`api.py:74-77`). Mirrors `_chat_repo` (no encryptor) since `PendingApprovalRepository` does not handle secrets:

```python
async def _pending_approval_repo() -> PendingApprovalRepository:
    conn = await get_connection()
    return PendingApprovalRepository(conn)
```

### Sub-step B — Endpoints

Add after `generate_connector_account_pairing_code` (`api.py:2570`) and before `list_attached_agents_for_connector_account` (`api.py:2573`), or alongside as a coherent block:

```python
@router.post(
    "/connector-accounts/{account_id}/peer-approvals/{approval_id}/approve"
)
async def approve_peer_approval(
    account_id: str,
    approval_id: str,
) -> dict[str, Any]:
    """Approve a pending peer-approval; add the peer to the account allowlist.

    M11 F9 L3 — Discord-native peer-approval action endpoint. Flips the
    pending_approvals row to ``status='approved'`` and adds
    ``approval.peer_id`` to ``account.config['allowlist']['peers']``
    (idempotent — duplicates are not appended). On an already-approved
    row, returns the existing row (the allowlist mutation is re-applied
    as a no-op, matching the repo's mark_approved idempotency contract).
    On a dismissed row, raises 409 (terminal-state mismatch).
    """
    conn_repo = await _connector_repo()
    try:
        account = await conn_repo.get(account_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Connector account not found: {account_id}"
        )

    approval_repo = await _pending_approval_repo()
    try:
        approval = await approval_repo.get(approval_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Pending approval not found: {approval_id}"
        )
    if approval.connector_account_id != account_id:
        raise HTTPException(
            status_code=404, detail=f"Pending approval not found: {approval_id}"
        )

    try:
        updated_approval = await approval_repo.mark_approved(approval_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Idempotent allowlist mutation. Initialize allowlist if missing /
    # empty (mirrors the dispatcher pattern at _inbound.py:428-438).
    new_config = dict(account.config)
    allowlist = dict(new_config.get("allowlist") or {})
    peers = list(allowlist.get("peers") or [])
    if approval.peer_id not in peers:
        peers.append(approval.peer_id)
    allowlist["peers"] = peers
    allowlist.setdefault("channels", [])
    new_config["allowlist"] = allowlist
    updated_account = account.model_copy(update={"config": new_config})
    updated_account = ConnectorAccount.model_validate(updated_account.model_dump())
    await conn_repo.update(updated_account)

    return updated_approval.model_dump()


@router.post(
    "/connector-accounts/{account_id}/peer-approvals/{approval_id}/dismiss"
)
async def dismiss_peer_approval(
    account_id: str,
    approval_id: str,
) -> dict[str, Any]:
    """Dismiss a pending peer-approval; do not mutate the allowlist.

    M11 F9 L3. Mirrors approve_peer_approval sans the allowlist mutation.
    Same 404 / 409 / 200-idempotent semantics.
    """
    conn_repo = await _connector_repo()
    try:
        await conn_repo.get(account_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Connector account not found: {account_id}"
        )

    approval_repo = await _pending_approval_repo()
    try:
        approval = await approval_repo.get(approval_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Pending approval not found: {approval_id}"
        )
    if approval.connector_account_id != account_id:
        raise HTTPException(
            status_code=404, detail=f"Pending approval not found: {approval_id}"
        )

    try:
        updated_approval = await approval_repo.mark_dismissed(approval_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return updated_approval.model_dump()
```

### Sub-step C — Tests

Add `class TestConnectorAccountPeerApprovals:` to `tests/test_db_api.py` after `TestConnectorAccountPairingCodeAndAttached`. Mirror the `_isolation` autouse fixture pattern verbatim. Add a `_create_account` helper (or reuse via a shared helper if the project conventions allow — check whether `TestConnectorAccountPairingCodeAndAttached`'s helper is private to that class; if so, redeclare).

Add a second helper `_create_pending_approval(client, account_id, peer_id="peer-1", peer_name="Test Peer", preview="hello")` that constructs a row via the repository directly (since there is no public endpoint to create one — the dispatcher emit path is the only producer in production). Use:

```python
async def _create_pending_approval(
    self,
    account_id: str,
    peer_id: str = "peer-1",
    peer_name: str = "Test Peer",
    preview: str = "hello",
) -> str:
    from the_one.db.connection import get_connection
    from the_one.db.repositories import PendingApprovalRepository

    conn = await get_connection()
    repo = PendingApprovalRepository(conn)
    approval = await repo.upsert_pending(
        connector_account_id=account_id,
        peer_id=peer_id,
        peer_name=peer_name,
        preview=preview,
    )
    return approval.id
```

Tests (one function each, mirroring the existing class's shape):

1. `test_approve_pending_returns_approved_row` — pending → POST approve → 200 + body has `status="approved"` + `resolved_at` not null.
2. `test_approve_pending_adds_peer_to_allowlist` — POST approve → GET account → `config.allowlist.peers` contains `peer_id`.
3. `test_approve_pending_idempotent_does_not_duplicate_peer_id` — POST approve twice → allowlist still contains `peer_id` exactly once.
4. `test_approve_preserves_other_config_keys` — pre-existing config keys (`pairing`, `intents`) survive. Mirror the existing `test_generate_pairing_code_preserves_other_config_keys`.
5. `test_approve_already_approved_returns_200_idempotent` — POST approve, POST approve → both 200 + same `id`.
6. `test_approve_on_dismissed_returns_409` — POST dismiss, POST approve → second is 409.
7. `test_approve_unknown_account_returns_404` — POST against fake account id → 404.
8. `test_approve_unknown_approval_returns_404` — POST against fake approval id → 404.
9. `test_approve_cross_account_approval_returns_404` — approval belongs to account-A; POST against account-B → 404.
10. `test_dismiss_pending_returns_dismissed_row` — POST dismiss → 200 + `status="dismissed"`.
11. `test_dismiss_does_not_mutate_allowlist` — POST dismiss → GET account → allowlist unchanged.
12. `test_dismiss_already_dismissed_returns_200_idempotent` — parallel to #5.
13. `test_dismiss_on_approved_returns_409` — parallel to #6.
14. `test_dismiss_unknown_account_returns_404` / `test_dismiss_unknown_approval_returns_404` / `test_dismiss_cross_account_approval_returns_404` — parallels to #7-#9.

That's 14 tests. Land all 14 to match the granularity of `TestConnectorAccountPairingCodeAndAttached`. Optionally add a 15th — `test_approve_pending_with_none_valued_allowlist_peers_initializes_list` — exercises the `list(allowlist.get("peers") or [])` defensive coercion (Edge Cases bullet). Cheap; ~15 LOC.

### Sub-step D — Flight log

Append to `flight-log.md`:

```
### {date} — L3 approval-api-endpoint (landed)

**Status**: ready → in-flight → landed

**Changes made**:
- `the_one/interfaces/web/api.py` — added `PendingApproval` to models import; added `PendingApprovalRepository` to repositories import; added `_pending_approval_repo()` factory; added `approve_peer_approval` and `dismiss_peer_approval` endpoints with 404 / 409 / 200-idempotent semantics; approve mutates `account.config["allowlist"]["peers"]` idempotently.
- `tests/test_db_api.py` — added `TestConnectorAccountPeerApprovals` class with 10-14 endpoint tests.

**Test outcomes**: new endpoint tests pass (14 or 15 depending on the optional None-allowlist test); pre-existing test_db_api.py tests pass; L2 outputs untouched. Suite count post-L3: 2689 → 2689 + N (verify actual).

**Anomalies**: {none expected; document any encountered.}
```

## Edge Cases

- **Account exists but has no `allowlist` key in `config`** — initialize to `{"peers": [<peer_id>], "channels": []}` (mirrors the dispatcher's pattern at `_inbound.py:428-431`).
- **Account's `config["allowlist"]` is `None`** (vs missing key) — `dict(new_config.get("allowlist") or {})` handles both.
- **Approval row was already approved before the API call (race: two clicks)** — second call returns 200 with the existing approved row; allowlist mutation is idempotent; no duplicate peer added.
- **Concurrent approve + dismiss** — first writer wins; second call sees terminal state ≠ target → 409. Single-user local-tool posture makes this vanishingly rare; no additional locking required.
- **`account.config["allowlist"]["peers"]` is `None`** — `list(allowlist.get("peers") or [])` handles it.
- **Cross-account ID smuggling** (operator types in URL bar) — the explicit `connector_account_id` mismatch → 404 check prevents exposing approval data across account boundaries. Defense-in-depth only; the single-user trust posture means this is mostly hygienic.
- **`peer_id` contains special characters** — stored as TEXT; preserved verbatim. No HTML/SQL escaping needed at the repo layer (parameterized queries handle SQL); the Chat UI's L4 render is responsible for HTML-escaping the preview/peer_name display.
- **Pydantic `model_validate` raises ValidationError on round-trip** — would surface as 500. The pairing-code endpoint has the same pattern (line 2568) and trusts the validator; mirror that posture. If validation surfaces a real bug, fix at the model layer, not here.
- **Partial-failure window between `mark_approved` and `conn_repo.update`** — if `mark_approved` commits but the subsequent allowlist mutation/`repo.update` raises (validation error, disk error), the approval row is terminal=`approved` while the allowlist was NOT updated. Recovery: next inbound DM from the peer triggers a fresh `pending` row (the existing `approved` row is `status='approved'`, not consumed by `upsert_pending`'s dedup which keys on `status='pending'`); operator re-approves; correct state restored. The misleading history is the cost. The pairing-code endpoint at `api.py:2527-2570` shares the same no-transaction-wrap posture; L3 matches the codebase convention rather than introducing a one-off transaction abstraction. If a future flight needs cross-table atomicity, that's a substrate refactor, not an L3 concern.
- **Response body on idempotent self-target** — when re-approve hits an already-approved row, the response returns the existing row verbatim: `resolved_at` is the timestamp of the FIRST approve, NOT the timestamp of the re-call. Same for dismiss. This is the operator-observable contract — the UI can rely on `resolved_at` being stable across idempotent calls.

## Files Affected

- `the_one/interfaces/web/api.py` — 2 import additions + 1 helper + 2 endpoints (~120 LOC).
- `tests/test_db_api.py` — 1 new class with ~10-14 tests (~250 LOC).
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — append L3 entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All new tests pass; pre-existing tests pass unchanged
- [ ] Update flight-log.md with L3 progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

8 citations verified against current code at leg design time:
- `the_one/interfaces/web/api.py:25-43` (imports) — OK
- `the_one/interfaces/web/api.py:74-77` (`_connector_repo` factory) — OK
- `the_one/interfaces/web/api.py:80-82` (`_chat_repo` factory; no-encryptor precedent) — OK
- `the_one/interfaces/web/api.py:2527-2570` (`generate_connector_account_pairing_code`) — OK
- `the_one/interfaces/web/api.py:2573-2634` (`list_attached_agents_for_connector_account`) — OK
- `tests/test_db_api.py:1355-1497` (`TestConnectorAccountPairingCodeAndAttached`) — OK
- `the_one/connectors/_inbound.py:428-438` (allowlist mutation pattern) — OK
- L2 outputs (PendingApprovalRepository, mark_approved/mark_dismissed, PendingApproval model) — landed.
