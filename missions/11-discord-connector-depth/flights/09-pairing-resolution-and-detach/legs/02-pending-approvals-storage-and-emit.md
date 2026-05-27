# Leg: pending-approvals-storage-and-emit

**Status**: completed
**Flight**: [Pairing Resolution + Connectors-Screen Detach](../flight.md)

## Objective

Land the `pending_approvals` storage layer (table + migration v21 + Pydantic model + repository) and wire the inbound dispatcher's NeedsPairing arm to upsert a pending-approval row + broadcast a `pending-approval` UI event when an unknown DM arrives without a `PAIR ` prefix.

## Context

**Why this leg.** L1 made the Discord plugin's `resolve` hook return `NeedsPairing` for unknown DMs; the dispatcher's existing handler at `the_one/connectors/_inbound.py:410-449` consults `_validate_pairing_prefix` and (a) success → adds peer to allowlist + permits; (b) failure → audit-deny + return. L2 splits the failure branch in two: (b1) failure WITH `PAIR ` prefix → existing audit-deny path (failed pairing attempt); (b2) failure WITHOUT `PAIR ` prefix → emit a pending-approval (upsert row + broadcast event + audit with `reason="pending_approval"`). L3 wires the approve/dismiss endpoints; L4 renders the banner; this leg ships everything below the dispatcher line.

**Design Decision §2 (storage shape, locked at flight planning, cycle-2 architect ratified)**: separate `pending_approvals` table with FK CASCADE on `connector_account_id`, CHECK constraint on `status` (`pending|approved|dismissed`), and dedup-at-insert (UPDATE the pending row in place when one already exists for `(account, peer, status='pending')`). Schema is committed in §2 of `flight.md`; reproduce verbatim in the migration block — do not invent shape.

**Discriminator: `text.startswith("PAIR ")`**. `_validate_pairing_prefix` returns `(False, text)` for three different cases — no `PAIR ` prefix at all, prefix present but wrong code, prefix present but account has no code configured. The dispatcher needs to distinguish "no prefix → Discord-native approval candidate" from "prefix failed → just a wrong-code attempt." Easiest discriminator: import `_PAIR_PREFIX` from `the_one/connectors/_pairing.py` (same package; underscore is package-private not module-private — same convention as `_default_permit` imported in `_inbound.py:152`) and check `envelope.text.startswith(_PAIR_PREFIX)`.

**Dedup semantics (cycle-2 architect MEDIUM, locked)**: ONE pending row per `(connector_account_id, peer_id)` while status='pending'. Subsequent DMs from the same peer while the pending row is still pending → UPDATE in place (refresh `preview`, `received_at`, `peer_name`). Approve/dismiss consumes the row (status flips); the next DM from a now-non-allowlisted peer creates a fresh row that may coexist with the historical approved/dismissed rows. Dedup scope is **status='pending' only**.

**Where the event surfaces**. The dispatcher resolved a chat_session at step 5 (`_inbound.py:374`-ish). The broadcast targets that session id via `broadcast_to_session(session_row.id, event)` (`_inbound.py:911` precedent). Any WS subscribers of that session see the event live; on next restore, L4's session-restore merge surfaces it via the timestamp-merge into `history`. **L2 does not touch session-restore** — that's L4's surface. L2 ships the LIVE-broadcast wire and the storage; L4 wires replay.

**Audit-log shape**. The audit entry for the pending-approval emit follows the existing shape at `_inbound.py:416-425`: `{"outcome": "deny", "peer_id": ..., "ts": ..., "reason": "pending_approval"}`. The reason literal `"pending_approval"` is contractual — F11's audit inspector will key on it (parallel to the existing `"invalid_pairing"` literal). The agent does not step; outbound is not emitted; `last_inbound_at` is not bumped (matches the existing Deny / NeedsPairing-failure semantics documented at `_inbound.py:46-48`).

**Schema versioning**. `CURRENT_VERSION = 20` at `the_one/db/schema.py:12`. L2 bumps to 21 and adds an `if version < 21:` migration block at the tail of `ensure_schema`. New table is a fresh CREATE (no rename ceremony — there's nothing to migrate from). The block also goes into `SCHEMA_V1`-equivalent eventual coverage path? No: per the v17/v18/v20 precedent, migrations land ONLY in the migration block; `SCHEMA_V1` is the v1-fresh-DB scaffold and new tables added in v2+ migrations are reached by the migration block on fresh DBs too (because `version < 21` runs after the SCHEMA_V1 path applies to a brand-new DB). Verify by reading the v17/v18/v20 migrations: they don't touch SCHEMA_V1, and fresh-DB tests pass.

## Inputs

- `the_one/db/schema.py:12` — `CURRENT_VERSION = 20`.
- `the_one/db/schema.py:770-787` — v20 migration tail; v21 inserts after this block.
- `the_one/db/schema.py:69, 88, 121` — FK CASCADE precedents (`kb_items`, `chat_sessions` paths).
- `the_one/db/models.py:116-...` — `ConnectorAccount` Pydantic model (Pydantic v2 shape with `BaseModel`, `Field`, `Literal`). The new `PendingApproval` model lives in the same module, mirroring `KBItem` (line 75) for status-bearing shape.
- `the_one/db/repositories.py:504-616` — `ConnectorAccountRepository` (async aiosqlite CRUD with `_row_to_model`). `PendingApprovalRepository` mirrors this shape sans encryptor (no secrets to encrypt).
- `the_one/connectors/_inbound.py:410-449` — NeedsPairing handler arm; L2 extends the `if not success:` branch.
- `the_one/connectors/_inbound.py:392-393` — resolver discovery (unchanged).
- `the_one/connectors/_inbound.py:911` — `broadcast_to_session(session_row.id, event)` precedent.
- `the_one/connectors/_inbound.py:152, 157, 164` — existing imports (extend in same import block).
- `the_one/connectors/_pairing.py:15` — `_PAIR_PREFIX = "PAIR "` (constant L2 imports for the discriminator).
- `the_one/db/models.py:14` — `now_iso()` helper for `received_at` / `resolved_at` timestamps.
- `tests/test_db_migration.py:2263` — `TestSchemaV20` pattern; L2 adds `TestSchemaV21`.
- `tests/test_db_repositories.py` — repo test patterns.
- `tests/test_connectors_inbound.py` — dispatcher emit test patterns.
- `tests/test_pairing_prefix.py` — must remain green; the existing PAIR-prefix-success and PAIR-prefix-failure paths are unchanged.

## Outputs

- `the_one/db/schema.py` — `CURRENT_VERSION = 21`; new `if version < 21:` block adding the `pending_approvals` table with FK CASCADE + CHECK constraint.
- `the_one/db/models.py` — new `PendingApproval(BaseModel)` Pydantic model with seven fields.
- `the_one/db/repositories.py` — new `PendingApprovalRepository` class with `get`, `upsert_pending`, `list_for_account_peer`, `list_by_account`, `mark_approved`, `mark_dismissed`. No factory helper at this layer — the dispatcher constructs the repo inline (the existing `_chat_repo()` factory at `interfaces/web/app.py` is used for API-edge construction; L3 will add a parallel `_pending_approval_repo()` factory there when it lands the endpoint, but L2 stays out of `app.py`).
- `the_one/connectors/_inbound.py` — extended NeedsPairing arm: discriminate by `_PAIR_PREFIX`; on no-prefix path, upsert pending row + `broadcast_to_session` event + audit-log `reason="pending_approval"`. Construct the new repo INLINE adjacent to the existing `acc_repo` / `chat_repo` construction at `_inbound.py:327-330` — DO NOT add a parameter to `dispatch_inbound`'s signature (the function constructs its own repos from `get_connection()` per the established pattern; adding a kwarg would force updates across ~30+ call sites including 2 in `_discord.py:837, 911` and ~28 across test files). New imports inside the function-local import block at `_inbound.py:320-324`: extend the `from the_one.db.repositories import (...)` tuple with `PendingApprovalRepository`. Module-level import: `from ._pairing import _PAIR_PREFIX` adjacent to the existing `_validate_pairing_prefix` import.
- `tests/test_db_migration.py` — new `TestSchemaV21` class with fresh-DB / idempotent / FK-CASCADE / CHECK-constraint tests.
- `tests/test_db_repositories.py` — new repo tests (insert + upsert dedup; mark_approved/dismissed lifecycle; list filters).
- `tests/test_connectors_inbound.py` — new dispatcher tests covering both arms of the new branch (no-prefix → pending-approval emit; with-prefix-wrong-code → existing deny).
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — append L2 progress entry.

L2 does NOT touch: `the_one/db/codec.py` (no `messages_to_ui_events` change; L4 will own session-restore merge), `interfaces/web/app.py` (no API endpoints; L3 owns those), any static JS (L4 owns Chat UI). The dispatcher emit is the only production wiring beyond storage.

## Acceptance Criteria

- [ ] `CURRENT_VERSION = 21` in `the_one/db/schema.py`.
- [ ] `ensure_schema(conn)` on a fresh DB creates a `pending_approvals` table with columns `(id TEXT PRIMARY KEY, connector_account_id TEXT NOT NULL REFERENCES connector_accounts(id) ON DELETE CASCADE, peer_id TEXT NOT NULL, peer_name TEXT NOT NULL, preview TEXT NOT NULL, received_at TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('pending','approved','dismissed')), resolved_at TEXT)`.
- [ ] The v21 migration is idempotent: running `ensure_schema` twice on a fresh DB produces a single row in `schema_version` for v21.
- [ ] FK CASCADE works: deleting a row from `connector_accounts` removes its dependent `pending_approvals` rows (verified by integration test with `PRAGMA foreign_keys=ON`).
- [ ] CHECK constraint rejects an INSERT with `status='banana'` (verified by integration test).
- [ ] `PendingApproval` Pydantic model lives in `the_one/db/models.py` with fields: `id: str`, `connector_account_id: str`, `peer_id: str`, `peer_name: str`, `preview: str`, `received_at: str` (default `now_iso`), `status: Literal["pending", "approved", "dismissed"]` (default `"pending"`), `resolved_at: str | None` (default `None`).
- [ ] `PendingApprovalRepository` exposes: `async def get(self, approval_id: str) -> PendingApproval` (raises `KeyError`), `async def upsert_pending(self, *, connector_account_id, peer_id, peer_name, preview) -> PendingApproval`, `async def list_for_account_peer(self, account_id, peer_id) -> list[PendingApproval]` (sorted oldest-first), `async def list_by_account(self, account_id) -> list[PendingApproval]` (sorted oldest-first), `async def mark_approved(self, approval_id) -> PendingApproval`, `async def mark_dismissed(self, approval_id) -> PendingApproval`. All mutators set `resolved_at = now_iso()` for terminal transitions and return the updated row.
- [ ] `upsert_pending` dedup: calling it twice for the same `(account_id, peer_id)` while the first row is `status='pending'` returns the SAME `id` (the row was updated in place — `preview`, `peer_name`, and `received_at` refresh to the latest call's values). Calling it a third time after `mark_approved` produces a NEW row with a different `id`.
- [ ] `mark_approved(id)` flips `status` from `pending` to `approved` and sets `resolved_at` to a non-null ISO timestamp; idempotent on an already-approved row (no error, no further mutation). Calling on a `dismissed` row raises (or transitions, pick one consistently — pick: raises `ValueError`, matching the state-machine reachability audit's terminal-state semantics from cycle-2 architect).
- [ ] `mark_dismissed(id)` mirrors `mark_approved` with the dismissed target; same idempotency / terminal-state semantics.
- [ ] Dispatcher emit path: when `outcome` is `NeedsPairing` AND `_validate_pairing_prefix` returns `success=False` AND `envelope.text` does NOT start with `_PAIR_PREFIX`, the dispatcher calls `pending_approval_repo.upsert_pending(...)` with `preview=envelope.text[:200]`, then calls `broadcast_to_session(session_row.id, {...})` with the canonical `pending-approval` event shape (per flight §5), then appends the audit-log entry `{"outcome": "deny", "peer_id": ..., "ts": ts, "reason": "pending_approval"}` to `session_metadata["audit"]`, then returns (no agent.step, no last_inbound_at bump).
- [ ] Dispatcher emit path: when `envelope.text` DOES start with `_PAIR_PREFIX` (failed pairing attempt — wrong code, etc.), the EXISTING behavior is preserved byte-identically — audit `reason: outcome.reason or "invalid_pairing"` and return without touching pending_approvals.
- [ ] Existing PAIR-prefix-success tests pass unchanged (`tests/test_pairing_prefix.py`).
- [ ] Existing dispatcher tests pass unchanged EXCEPT `TestF6Gating::test_needs_pairing_with_no_prefix_denies` (~`tests/test_connectors_inbound.py:1865`), which is intentionally updated (rename + assertion inversion) to assert the new pending-approval emit shape. The test now serves as one of the three new dispatcher-emit tests rather than being added alongside.
- [ ] State-machine reachability audit: the v21 schema's `pending → approved | dismissed` lifecycle is terminal; no triggers, no upstream caches that would foreclose the `pending` state. Cycle-2 architect ratified this; rec re-verify at L2 implementation via the new tests.
- [ ] New dispatcher tests cover: (a) no-prefix path emits pending-approval (storage row + broadcast event + audit entry); (b) wrong-code path follows the existing deny path unchanged; (c) upsert dedup at dispatcher level — two consecutive unknown DMs from the same peer produce ONE `pending_approvals` row.
- [ ] New repo tests cover: get, upsert (new + dedup-update), list filters, mark_approved/dismissed (success + idempotent + terminal-state ValueError), FK CASCADE behavior.
- [ ] New schema-migration tests under `TestSchemaV21` cover: fresh-DB-includes-table, migration-idempotent-on-rerun, FK CASCADE delete works, CHECK constraint rejects bad status.
- [ ] No production code outside the files listed in **Outputs** is modified.

## Verification Steps

```bash
# Run the new migration tests
docker exec the-one pytest tests/test_db_migration.py::TestSchemaV21 -x --timeout 30 -v

# Run the new repo tests (names will reflect the new class)
docker exec the-one pytest tests/test_db_repositories.py -k "pending_approval" -x --timeout 30 -v

# Run dispatcher tests (new + existing — existing must remain green)
docker exec the-one pytest tests/test_connectors_inbound.py -x --timeout 30 -v

# Existing pairing-prefix tests must remain unchanged
docker exec the-one pytest tests/test_pairing_prefix.py -x --timeout 30 -v

# Discord plugin tests still pass (L1's tests should not regress)
docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30 -v

# Full suite at leg-end (per the phase prompt's discipline)
docker exec the-one pytest --timeout 60 -q
```

Expected: all green. Suite baseline pre-F9 is 2669 passed (per F8 debrief). L2 adds tests; the count goes up.

## Implementation Guidance

### Sub-step A — Schema migration (v21)

1. Edit `the_one/db/schema.py:12` — change `CURRENT_VERSION = 20` → `CURRENT_VERSION = 21`.

2. Append a new migration block at the tail of `ensure_schema` (after the v20 block):

```python
    if version < 21:
        # Mission 11 Flight 9 Leg 2: pending_approvals table for the
        # Discord-native peer-approval flow. New table (no ALTER, no
        # rename ceremony). FK CASCADE on connector_account_id mirrors
        # the kb_items / chat_sessions precedent (schema lines 69, 88).
        # CHECK constraint pins the three-state lifecycle to surface
        # data corruption immediately rather than letting it propagate
        # silently. Idempotent: ``CREATE TABLE IF NOT EXISTS`` + the
        # ``if version < 21:`` short-circuit guarantee re-runs are no-ops.
        # PRAGMA foreign_keys is NOT toggled here — no existing FK
        # behavior changes, no table-rename ceremony.
        await conn.executescript("""\
CREATE TABLE IF NOT EXISTS pending_approvals (
    id TEXT PRIMARY KEY,
    connector_account_id TEXT NOT NULL
        REFERENCES connector_accounts(id) ON DELETE CASCADE,
    peer_id TEXT NOT NULL,
    peer_name TEXT NOT NULL,
    preview TEXT NOT NULL,
    received_at TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'approved', 'dismissed')),
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_approvals_account_peer_status
    ON pending_approvals (connector_account_id, peer_id, status);
""")
        await conn.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (21,)
        )
        await conn.commit()
        version = 21
```

The `idx_pending_approvals_account_peer_status` index supports the upsert-dedup query (`WHERE connector_account_id=? AND peer_id=? AND status='pending'`).

3. Bump the hard-coded literal at `tests/test_db_migration.py:241`: change `assert CURRENT_VERSION == 20` → `assert CURRENT_VERSION == 21`; update the inline error message accordingly (the `"must be 20"` substring) and append a v21 line to the preceding migration-history comment block (`v21 added pending_approvals table (M11 F09 L02 — Discord-native peer-approval storage)`).

4. Verify by running `docker exec the-one pytest tests/test_db_migration.py -x --timeout 30` once before writing new tests — existing migration tests must still pass with `CURRENT_VERSION=21`.

### Sub-step B — Pydantic model

Add to `the_one/db/models.py` (after `ConnectorAccount`, before `ToolConfig`):

```python
class PendingApproval(BaseModel):
    """A pending Discord-native peer-approval row.

    M11 F9 L2 — Discord-native approval flow primary path. Created by
    the inbound dispatcher when an unknown DM arrives without a
    ``PAIR `` prefix; consumed (via ``mark_approved``) by the API
    endpoint at F9 L3 ``POST /api/connector-accounts/{account_id}/
    peer-approvals/{approval_id}/approve``; rendered by the Chat UI
    at F9 L4.

    Dedup: at most ONE row per ``(connector_account_id, peer_id)``
    with ``status='pending'`` at any time; the dispatcher's emit path
    upserts. ``approved`` and ``dismissed`` rows are terminal and
    persist as history; a new ``pending`` may coexist with them after
    the operator removes a peer from the allowlist.
    """

    id: str
    connector_account_id: str
    peer_id: str
    peer_name: str
    preview: str
    received_at: str = Field(default_factory=now_iso)
    status: Literal["pending", "approved", "dismissed"] = "pending"
    resolved_at: str | None = None
```

The `Literal` import is already present at the top of `models.py`; verify before adding any new imports.

### Sub-step C — Repository

Add to `the_one/db/repositories.py` (after `ConnectorAccountRepository` at line 616, before `ToolConfigRepository`):

```python
class PendingApprovalRepository:
    """Async CRUD for pending Discord-native peer approvals.

    M11 F9 L2. No encryptor (no secrets to encrypt). Mirrors
    ``ConnectorAccountRepository`` connection-passing shape sans the
    encryptor argument.

    Dedup contract (cycle-2 architect §2): ``upsert_pending`` enforces
    ONE row per ``(connector_account_id, peer_id, status='pending')``
    via an UPDATE-in-place when the index matches, INSERT otherwise.
    Terminal-state transitions (``mark_approved``, ``mark_dismissed``)
    raise ``ValueError`` if invoked on an already-terminal row OTHER
    than the same target (idempotent on self-target — calling
    ``mark_approved`` on an approved row is a no-op).
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def get(self, approval_id: str) -> PendingApproval:
        async with self.conn.execute(
            "SELECT * FROM pending_approvals WHERE id = ?", (approval_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise KeyError(f"Pending approval not found: {approval_id}")
        return self._row_to_model(row)

    async def upsert_pending(
        self,
        *,
        connector_account_id: str,
        peer_id: str,
        peer_name: str,
        preview: str,
    ) -> PendingApproval:
        """Upsert a pending row keyed by (account, peer, status='pending').

        If a pending row already exists for (account, peer), UPDATE
        ``peer_name``, ``preview``, ``received_at`` in place and return
        the updated row. Otherwise INSERT a fresh row with a new uuid
        and ``status='pending'``.
        """
        async with self.conn.execute(
            "SELECT id FROM pending_approvals "
            "WHERE connector_account_id = ? AND peer_id = ? AND status = 'pending' "
            "LIMIT 1",
            (connector_account_id, peer_id),
        ) as cur:
            existing = await cur.fetchone()
        ts = now_iso()
        if existing is None:
            new_id = uuid.uuid4().hex  # 32-char full hex (matches connectors/_session.py:184 — same world: dispatcher-created, web-API-referenced)
            await self.conn.execute(
                "INSERT INTO pending_approvals "
                "(id, connector_account_id, peer_id, peer_name, preview, "
                " received_at, status, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL)",
                (new_id, connector_account_id, peer_id, peer_name, preview, ts),
            )
            await self.conn.commit()
            return await self.get(new_id)
        approval_id = existing["id"]
        await self.conn.execute(
            "UPDATE pending_approvals "
            "SET peer_name = ?, preview = ?, received_at = ? "
            "WHERE id = ?",
            (peer_name, preview, ts, approval_id),
        )
        await self.conn.commit()
        return await self.get(approval_id)

    async def list_for_account_peer(
        self, account_id: str, peer_id: str
    ) -> list[PendingApproval]:
        async with self.conn.execute(
            "SELECT * FROM pending_approvals "
            "WHERE connector_account_id = ? AND peer_id = ? "
            "ORDER BY received_at ASC",
            (account_id, peer_id),
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def list_by_account(self, account_id: str) -> list[PendingApproval]:
        async with self.conn.execute(
            "SELECT * FROM pending_approvals "
            "WHERE connector_account_id = ? "
            "ORDER BY received_at ASC",
            (account_id,),
        ) as cur:
            return [self._row_to_model(r) for r in await cur.fetchall()]

    async def mark_approved(self, approval_id: str) -> PendingApproval:
        return await self._transition(approval_id, "approved")

    async def mark_dismissed(self, approval_id: str) -> PendingApproval:
        return await self._transition(approval_id, "dismissed")

    async def _transition(
        self, approval_id: str, target: Literal["approved", "dismissed"]
    ) -> PendingApproval:
        current = await self.get(approval_id)  # raises KeyError
        if current.status == target:
            return current  # idempotent on self-target
        if current.status != "pending":
            raise ValueError(
                f"Pending approval {approval_id} is {current.status}; "
                f"cannot transition to {target}"
            )
        await self.conn.execute(
            "UPDATE pending_approvals SET status = ?, resolved_at = ? "
            "WHERE id = ?",
            (target, now_iso(), approval_id),
        )
        await self.conn.commit()
        return await self.get(approval_id)

    def _row_to_model(self, row: aiosqlite.Row) -> PendingApproval:
        return PendingApproval(
            id=row["id"],
            connector_account_id=row["connector_account_id"],
            peer_id=row["peer_id"],
            peer_name=row["peer_name"],
            preview=row["preview"],
            received_at=row["received_at"],
            status=row["status"],
            resolved_at=row["resolved_at"],
        )
```

**Import additions** at the top of `repositories.py`: add `PendingApproval` to the existing `from .models import (...)` block; add `import uuid` (the dominant in-codebase convention — 3 of 4 uuid call sites use `import uuid; uuid.uuid4().hex`; only `tools/_session_registry.py:45` uses `from uuid import uuid4`); add `Literal` to the existing `typing` import IF not already present (verify before adding).

### Sub-step D — Dispatcher emit

Edit `the_one/connectors/_inbound.py`:

1. **Add imports**:
   - **Module-level**: from `._pairing` extend the existing `from the_one.connectors._pairing import _validate_pairing_prefix` (line ~155) to also import `_PAIR_PREFIX`. Underscore-prefix is package-private not module-private — same convention as `_default_permit` imported at line 152.
   - **Function-local** (inside `dispatch_inbound`'s import block at lines 320-324): extend the existing `from the_one.db.repositories import (ChatSessionRepository, ConnectorAccountRepository, SQLiteAgentStore)` tuple with `PendingApprovalRepository`. Keep the alphabetical-ish ordering (`Pending...` goes between `Chat...` and `Connector...` alphabetically — but follow whatever ordering the existing tuple uses).

2. **Construct the repo inline** at line ~330, alongside the existing repos. `dispatch_inbound` constructs `acc_repo`, `chat_repo`, `agent_store` from `get_connection()` at lines 327-331. Add ONE line:
   ```python
   approval_repo = PendingApprovalRepository(conn)
   ```
   adjacent to the existing constructions. **Do NOT add a parameter to `dispatch_inbound`'s signature** — adding a kwarg would force updates across ~30+ call sites (`_discord.py:837, 911` + ~28 across test files). Inline construction matches the established pattern.

3. **Modify the NeedsPairing arm** at `_inbound.py:410-449`. Replace the `if not success:` block (rename variable `pending_approval_repo` → `approval_repo` in code below if you prefer brevity; the leg is not prescriptive on local-variable shortening):

```python
        if not success:
            if envelope.text.startswith(_PAIR_PREFIX):
                # Failed PAIR attempt (wrong code, malformed prefix, or
                # account-has-no-code). Existing audit-deny path.
                await chat_repo.append_to_session_metadata(
                    session_row.id,
                    "audit",
                    {
                        "outcome": "deny",
                        "peer_id": envelope.peer_id,
                        "ts": ts,
                        "reason": outcome.reason or "invalid_pairing",
                    },
                )
                return
            # No PAIR prefix — Discord-native approval candidate (F9 L2).
            approval = await approval_repo.upsert_pending(
                connector_account_id=account.id,
                peer_id=envelope.peer_id,
                peer_name=envelope.peer_name,
                preview=envelope.text[:200],
            )
            await broadcast_to_session(
                session_row.id,
                {
                    "type": "pending-approval",
                    "approval_id": approval.id,
                    "peer_name": approval.peer_name,
                    "peer_id": approval.peer_id,
                    "preview": approval.preview,
                    "received_at": approval.received_at,
                    "connector_account_id": approval.connector_account_id,
                    "status": approval.status,
                },
            )
            await chat_repo.append_to_session_metadata(
                session_row.id,
                "audit",
                {
                    "outcome": "deny",
                    "peer_id": envelope.peer_id,
                    "ts": ts,
                    "reason": "pending_approval",
                },
            )
            return
```

The success path below this (lines 427-449) is unchanged.

4. **Verify no other dispatcher branch needs to know about pending-approvals**. The Deny and Permit arms are untouched. The pending-approval emit ONLY fires in the NeedsPairing-with-no-PAIR-prefix branch.

### Sub-step E — Tests

1. **Migration tests** in `tests/test_db_migration.py` — add `class TestSchemaV21:` after `TestSchemaV20`:
   - `test_v21_fresh_db_includes_pending_approvals_table` — fresh DB, ensure_schema, verify table + columns + CHECK constraint + FK + index.
   - `test_v21_migration_idempotent_on_rerun` — ensure_schema twice; v21 row appears exactly once; table is still well-formed.
   - `test_v21_fk_cascade_deletes_dependent_rows` — INSERT account + INSERT approval referencing it; DELETE account; SELECT pending_approvals returns 0 rows.
   - `test_v21_check_constraint_rejects_bad_status` — INSERT with `status='banana'` raises `aiosqlite.IntegrityError` (assert on the exception class only; CHECK-constraint failure messages vary across SQLite versions and are not stable).

2. **Repo tests** in `tests/test_db_repositories.py` — class or test-function block (mirror the existing pattern in the file):
   - `test_pending_approval_repo_upsert_creates_new_row` — call `upsert_pending`; verify row, fields, status='pending'.
   - `test_pending_approval_repo_upsert_dedup_updates_in_place` — call `upsert_pending` twice; verify ONE row, second call returned same id, fields updated to second call's values.
   - `test_pending_approval_repo_upsert_after_approve_creates_new_row` — upsert, mark_approved, upsert again with same (account, peer); verify TWO rows total, second has a new id and status='pending'.
   - `test_pending_approval_repo_get_raises_keyerror_for_unknown_id` — `get("does-not-exist")` raises.
   - `test_pending_approval_repo_mark_approved_flips_status_and_sets_resolved_at` — upsert + mark_approved; verify status, resolved_at non-null.
   - `test_pending_approval_repo_mark_approved_idempotent_on_already_approved` — second call to mark_approved returns the same row, doesn't error.
   - `test_pending_approval_repo_mark_approved_on_dismissed_row_raises_valueerror` — terminal-state guard.
   - `test_pending_approval_repo_mark_dismissed_mirrors` — symmetric test set for dismissed.
   - `test_pending_approval_repo_list_for_account_peer_returns_oldest_first` — verify ORDER BY received_at.
   - `test_pending_approval_repo_list_by_account_returns_all_for_account` — verify scope.

3. **Dispatcher tests** in `tests/test_connectors_inbound.py`:

   **a. Invert the existing test** at `TestF6Gating::test_needs_pairing_with_no_prefix_denies` (~line 1865) — rename to `test_needs_pairing_with_no_prefix_emits_pending_approval` and update assertions to:
   - The audit entry's `reason` is `"pending_approval"` (not `"unknown_peer"`/`"invalid_pairing"`).
   - One pending_approvals row exists for `(account.id, "peer-1")` with `status="pending"`, `preview="hello"`, `peer_name=<envelope.peer_name>`.
   - A `pending-approval` UI event was broadcast to the session id (mock or capture `broadcast_to_session` for the assertion — check whether the existing fixture provides such a hook; if not, add one symmetric to how the existing `messages_to_ui_events`-via-broadcast is tested elsewhere).
   - History remains free of USER/ASSISTANT messages (the existing assertion at line 1857 stays).

   The rename + assertion inversion documents the state-machine intent shift in git blame (per the `/leg` skill's state-machine reachability audit guidance).

   **b. Add a new test** `test_needs_pairing_with_pair_prefix_wrong_code_still_denies` — same setup as the inverted test but `text="PAIR wrongcode hello"`. Verify: ZERO pending_approvals rows; audit `reason` is the `NeedsPairing.reason` if non-empty else `"invalid_pairing"`; no broadcast event. This pins the existing wrong-code Deny path explicitly (it was implicit before — wrong-code and no-prefix shared a test until L2).

   **c. Add a new test** `test_needs_pairing_no_prefix_dedup_consecutive_dms_from_same_peer` — two consecutive `dispatch_inbound` calls with the same peer + no PAIR prefix. Verify: ONE pending_approvals row (UPDATE-in-place); TWO broadcast events; the second event's `approval_id` equals the first.

   **Fixture caveat**: the dispatcher tests use `isolated_db` + `get_connection()` from the same call path the production dispatcher uses, so the new `PendingApprovalRepository` constructed inline in `dispatch_inbound` is reachable from the test's same connection (an SQLite-on-disk file per `isolated_db`). The dispatcher's own construction is sufficient; tests don't need to inject a separate repo. For verification, the test constructs its OWN `PendingApprovalRepository(conn)` on the same connection and reads rows.

   **broadcast_to_session capture**: search `tests/test_connectors_inbound.py` for existing patterns capturing `broadcast_to_session` (e.g. `broadcast_calls`, `monkeypatch.setattr` on `the_one.sessions.broadcast_to_session`). Match the existing pattern; if no precedent, monkeypatch `the_one.connectors._inbound.broadcast_to_session` to record calls into a list fixture.

4. **Confirm pre-existing tests still pass** — `test_pairing_prefix.py`, `test_connectors_discord.py`, the rest of `test_connectors_inbound.py`.

### Sub-step F — Flight log

Append to `flight-log.md` under "Leg Progress":

```
### {date} — L2 pending-approvals-storage-and-emit (landed)

**Status**: ready → in-flight → landed

**Changes made**:
- `the_one/db/schema.py` — bumped CURRENT_VERSION 20 → 21; added v21 migration block creating `pending_approvals` table + index.
- `the_one/db/models.py` — added `PendingApproval(BaseModel)`.
- `the_one/db/repositories.py` — added `PendingApprovalRepository` class with `get`, `upsert_pending`, `list_for_account_peer`, `list_by_account`, `mark_approved`, `mark_dismissed`.
- `the_one/connectors/_inbound.py` — imported `_PAIR_PREFIX` from `._pairing` and `PendingApprovalRepository` from `..db.repositories`; constructed `PendingApprovalRepository` inline in `dispatch_inbound` alongside `acc_repo` / `chat_repo`; modified NeedsPairing arm to discriminate by PAIR-prefix presence and emit pending-approval on the no-prefix branch.
- `tests/test_db_migration.py` — added `TestSchemaV21` with 4 tests.
- `tests/test_db_repositories.py` — added 10 PendingApprovalRepository tests.
- `tests/test_connectors_inbound.py` — added 3 dispatcher-emit tests.

**Cross-subsystem inspection result**: confirmed no existing dispatcher test exercises the no-PAIR-prefix branch with a NeedsPairing-returning plugin (StubPlugin uses Permit; DiscordPlugin's resolve was just added in L1).

**Test outcomes**: migration tests pass (+4), repo tests pass (+10), dispatcher tests pass (+3), pre-existing dispatcher/discord/pairing-prefix tests pass unchanged. Suite count: pre-F9 baseline 2669 → post-L2 baseline 2686 (target — verify actual).

**Anomalies**: {none expected; document any encountered.}
```

## Edge Cases

- **Account has no pairing code configured AND no allowlist entries** — `_validate_pairing_prefix` returns `(False, text)` for the "no code" reason (line 32-33). The discriminator (`text.startswith(_PAIR_PREFIX)`) is independent of the no-code condition: a peer who sends a non-PAIR-prefixed DM still becomes a pending-approval candidate (correct — even if the operator hasn't shared a code, an unknown DM should surface).
- **Account has a pairing code AND no allowlist entries AND peer DMs with valid PAIR prefix** — the EXISTING success path at line 427 fires; pairing succeeds; peer added to allowlist; permit. No pending-approval is created. (Correct — the operator pre-shared the code out-of-band.)
- **Peer is currently on a pending row, gets approved, sends a DM** — the approved row's status is terminal; the peer is now in `account.config["allowlist"]["peers"]` (L3 mutation); the resolver (L1) returns `Permit`; the dispatcher proceeds normally. No new pending row.
- **Peer is approved, then operator removes them from the allowlist, peer DMs again** — the existing approved row is historical; the resolver returns `NeedsPairing`; the discriminator branch fires; `upsert_pending` doesn't find a PENDING row (the existing one is `approved`, not `pending`) and INSERTs a fresh row. Two rows coexist (one `approved` historical, one `pending` fresh). This matches the cycle-2 architect's state-machine reachability audit.
- **Empty `envelope.text`** — `text[:200]` is `""`; `text.startswith(_PAIR_PREFIX)` is False; pending-approval emit fires with empty `preview`. The Chat UI banner shows an empty preview. Acceptable (genuine "user sent a blank DM"); not worth special-casing in this leg.
- **Very long `envelope.text`** — `text[:200]` truncates to 200 chars; the full text never enters the storage. Matches design §2 ("first ~200 chars"). The Chat UI banner shows the truncated preview.
- **Concurrent unknown DMs from two different peers on the same account** — two separate `(account, peer)` pairs; the index distinguishes them; two `pending` rows coexist. Dedup is per-peer, not per-account.
- **Race: `upsert_pending` SELECT then INSERT, with a parallel upsert sneaking between** — aiosqlite is sequential within a connection; the dispatcher holds the per-session lock (`session_locks`); the same connection serializes the SELECT + INSERT within `upsert_pending`. SQLite's default journaling makes the INSERT visible to subsequent SELECTs on the same connection. No additional locking required. Cross-process / cross-connection races are out of scope (single-user local tool posture).
- **`broadcast_to_session` raises during the emit** — the audit-log entry has already been logged (or hasn't, depending on order). Pick: broadcast BEFORE audit so a broadcast failure logs nothing (the audit is the persistence; the broadcast is the live convenience — L4 will re-populate via session-restore). Wait — actually the current pattern at line 911 broadcasts AFTER agent.step's persistence. Re-think: at this code site we WANT the audit entry persisted regardless of broadcast outcome (the operator may not be subscribed to the session). Order: upsert FIRST (must succeed; raises if storage breaks); broadcast SECOND (best-effort; wrap in try/except matching the no-eligible peer-error emit at `_inbound.py:511-531`?); audit-log THIRD (must succeed). Decision: do NOT wrap the broadcast in try/except — the no-eligible block at line 511 wraps `client.send` (network) but `broadcast_to_session` is in-process; if it raises, that's a programmer error worth surfacing. Implement as plain await; revisit at L4 if a wrap is needed.

## Files Affected

- `the_one/db/schema.py` — bump CURRENT_VERSION + add v21 migration block (~30 LOC addition).
- `the_one/db/models.py` — add `PendingApproval` Pydantic model (~25 LOC addition).
- `the_one/db/repositories.py` — add `PendingApprovalRepository` class (~120 LOC addition + 2-3 new imports).
- `the_one/connectors/_inbound.py` — 2 new imports + modify NeedsPairing arm (~30 LOC addition net; the existing 12-line `if not success:` block becomes a ~30-line branched block).
- `tests/test_db_migration.py` — add `TestSchemaV21` class (~150 LOC).
- `tests/test_db_repositories.py` — add 10 PendingApprovalRepository tests (~200 LOC).
- `tests/test_connectors_inbound.py` — add 3 dispatcher-emit tests (~150 LOC, depending on existing fixture density) AND update `TestF6Gating::test_needs_pairing_with_no_prefix_denies` (~line 1865) — this pre-existing test exercises the exact path L2 changes (StubPluginWithResolver returning NeedsPairing + `text="hello"`). Per the cycle-2 state-machine reachability audit, it must be inverted: rename to e.g. `test_needs_pairing_with_no_prefix_emits_pending_approval` and update assertions to expect the new shape (pending row inserted + broadcast event + audit `reason="pending_approval"`). The git-blame intent-shift is documented by the rename + assertion inversion (per the leg-design conventions in `.claude/skills/leg/SKILL.md` state-machine reachability audit guidance).
- `tests/test_db_migration.py:241` — bump `assert CURRENT_VERSION == 20` to `== 21`; extend the preceding migration-history comment with a v21 line.
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — append L2 progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All new tests pass; pre-existing tests pass unchanged
- [ ] Full suite passes (baseline 2669 → 2686 expected)
- [ ] Update flight-log.md with L2 progress entry (template above)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

12 citations verified against current code at leg design time:
- `the_one/db/schema.py:12` (`CURRENT_VERSION = 20`) — OK
- `the_one/db/schema.py:770-787` (v20 migration block) — OK
- `the_one/db/schema.py:69, 88, 121` (FK CASCADE precedents) — OK; line 121 is the chat_sessions FK CASCADE (verified via line 87-93 read above).
- `the_one/db/models.py:14` (`now_iso`) — OK
- `the_one/db/models.py:75-85` (`KBItem` shape precedent) — OK
- `the_one/db/models.py:116` (`ConnectorAccount` shape precedent) — OK
- `the_one/db/repositories.py:504-616` (`ConnectorAccountRepository` shape precedent) — OK
- `the_one/connectors/_inbound.py:152, 157, 164` (existing imports) — OK
- `the_one/connectors/_inbound.py:392-393` (resolver discovery) — OK
- `the_one/connectors/_inbound.py:410-449` (NeedsPairing arm) — OK
- `the_one/connectors/_inbound.py:911` (`broadcast_to_session` precedent) — OK
- `the_one/connectors/_pairing.py:15` (`_PAIR_PREFIX = "PAIR "`) — OK
- `tests/test_db_migration.py:2263` (`TestSchemaV20` pattern) — OK
