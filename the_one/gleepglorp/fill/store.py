"""The store for GleepGlorp's form fills (Mission 36 F3 L5, DD6).

One row per fill in ``gleepglorp_fills`` (schema v55; v56 added ``target_id`` and made
``agent_name`` nullable; no foreign keys). A fill records what
GleepGlorp wrote into the operator's agent editor as *unsaved edits*; it never writes any
configuration. The browser that applies it claims it (``sent``/``not_filled`` -> ``applying``,
with a token and a lease) and reports a coded outcome.

Every status write is conditional (``WHERE id = ? AND status ...``), checked by ``rowcount``,
so a stale claim or a late outcome never overwrites a newer state.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import aiosqlite

from the_one.db._write_lock import write_transaction
from the_one.db.models import now_iso
from the_one.gleepglorp.status_rows import dumps, get_row, list_for_session_rows, loads

STATUSES = ("sent", "applying", "filled", "partly_filled", "not_filled", "replaced")
CLAIMABLE = ("sent", "not_filled")
OUTCOME_STATUSES = ("filled", "partly_filled", "not_filled")
REASONS = ("in_chats", "stay", "editor_unavailable", "target_gone")
CLAIM_LEASE_SECONDS = 120

_COLS = (
    "id, session_id, tool_call_id, kind, action, agent_name, target_id, target_key, changes, "
    "base, status, outcome, claim_token, untrusted, untrusted_sources, created_at, claimed_at, "
    "resolved_at"
)


class FillNotFound(Exception):  # noqa: N818 - a refusal
    """No fill has that id."""


class FillClaimRefused(Exception):  # noqa: N818 - a refusal carrying the fill's status
    def __init__(self, status: str) -> None:
        super().__init__(f"Fill is {status}")
        self.status = status


class FillOutcomeRefused(Exception):  # noqa: N818 - a wrong token or not applying
    """The outcome's token is not the current claim, or the fill is not ``applying``."""


@dataclass
class NewFill:
    session_id: str
    kind: str
    action: str
    agent_name: str | None
    target_key: str
    changes: dict[str, Any]
    target_id: str | None = None
    base: dict[str, Any] | None = None
    tool_call_id: str | None = None
    untrusted: bool = False
    untrusted_sources: list[str] = field(default_factory=list)


@dataclass
class Fill:
    id: int
    session_id: str
    tool_call_id: str | None
    kind: str
    action: str
    agent_name: str | None
    target_id: str | None
    target_key: str
    changes: dict[str, Any]
    base: dict[str, Any] | None
    status: str
    outcome: dict[str, Any] | None
    claim_token: str | None
    untrusted: bool
    untrusted_sources: list[str]
    created_at: str
    claimed_at: str | None
    resolved_at: str | None


_TABLE = "gleepglorp_fills"
_loads = loads
_dumps = dumps


def _row(row: Any) -> Fill:
    return Fill(
        id=row[0],
        session_id=row[1],
        tool_call_id=row[2],
        kind=row[3],
        action=row[4],
        agent_name=row[5],
        target_id=row[6],
        target_key=row[7],
        changes=_loads(row[8], {}),
        base=_loads(row[9]),
        status=row[10],
        outcome=_loads(row[11]),
        claim_token=row[12],
        untrusted=bool(row[13]),
        untrusted_sources=_loads(row[14], []) or [],
        created_at=row[15],
        claimed_at=row[16],
        resolved_at=row[17],
    )


class GleepGlorpFillRepository:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def insert(self, new: NewFill) -> tuple[int, list[int]]:
        """Record a fill; returns ``(id, replaced_ids)``.

        In the same transaction every fill of the chat still in ``sent`` or ``not_filled`` is
        marked ``replaced``: it can no longer be claimed, so Fill now never puts older values
        over a newer fill. ``applying``, ``filled`` and ``partly_filled`` are left alone.
        """
        from the_one.gleepglorp import kinds

        if new.kind not in kinds.FILLABLE:
            raise ValueError(f"unsupported fill kind: {new.kind!r}")
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "SELECT id FROM gleepglorp_fills WHERE session_id = ? "
                "AND status IN ('sent', 'not_filled') ORDER BY id",
                (new.session_id,),
            ) as cur:
                older = [r[0] for r in await cur.fetchall()]
            async with self.conn.execute(
                "INSERT INTO gleepglorp_fills (session_id, tool_call_id, kind, action, "
                "agent_name, target_id, target_key, changes, base, status, untrusted, "
                "untrusted_sources, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'sent', ?, ?, ?)",
                (
                    new.session_id,
                    new.tool_call_id,
                    new.kind,
                    new.action,
                    new.agent_name,
                    new.target_id,
                    new.target_key,
                    _dumps(new.changes),
                    _dumps(new.base) if new.base is not None else None,
                    1 if new.untrusted else 0,
                    json.dumps(new.untrusted_sources),
                    now_iso(),
                ),
            ) as cur:
                new_id = int(cur.lastrowid or 0)
            replaced: list[int] = []
            for old in older:
                async with self.conn.execute(
                    "UPDATE gleepglorp_fills SET status = 'replaced', resolved_at = ? "
                    "WHERE id = ? AND status IN ('sent', 'not_filled')",
                    (now_iso(), old),
                ) as cur:
                    if cur.rowcount == 1:
                        replaced.append(old)
        return new_id, replaced

    async def get(self, fill_id: int) -> Fill | None:
        return await get_row(self.conn, _TABLE, _COLS, _row, fill_id)

    async def list_for_session(self, session_id: str) -> list[Fill]:
        return await list_for_session_rows(self.conn, _TABLE, _COLS, _row, session_id)

    async def claim(self, fill_id: int, now: datetime) -> tuple[Fill, str]:
        """Claim a fill for applying; returns ``(fill, token)``.

        Succeeds from ``sent`` or ``not_filled``, or from an ``applying`` row whose claim is
        older than the lease. Raises :class:`FillNotFound` or :class:`FillClaimRefused`.
        """
        token = secrets.token_urlsafe(18)
        stale_before = (now - timedelta(seconds=CLAIM_LEASE_SECONDS)).isoformat()
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "UPDATE gleepglorp_fills SET status = 'applying', claim_token = ?, "
                "claimed_at = ?, resolved_at = NULL, outcome = NULL WHERE id = ? AND "
                "(status IN ('sent', 'not_filled') OR (status = 'applying' AND claimed_at < ?))",
                (token, now.isoformat(), fill_id, stale_before),
            ) as cur:
                moved = cur.rowcount == 1
        fill = await self.get(fill_id)
        if fill is None:
            raise FillNotFound(fill_id)
        if not moved:
            raise FillClaimRefused(fill.status)
        return fill, token

    async def record_outcome(
        self, fill_id: int, token: str, status: str, kept: list[str], reason: str | None
    ) -> Fill:
        """Record the applier's outcome, only for the current claim of an ``applying`` fill."""
        if status not in OUTCOME_STATUSES:
            raise ValueError(f"unknown outcome status: {status!r}")
        async with write_transaction(self.conn):
            async with self.conn.execute(
                "UPDATE gleepglorp_fills SET status = ?, outcome = ?, resolved_at = ? "
                "WHERE id = ? AND status = 'applying' AND claim_token = ?",
                (status, _dumps({"kept": kept, "reason": reason}), now_iso(), fill_id, token),
            ) as cur:
                moved = cur.rowcount == 1
        fill = await self.get(fill_id)
        if fill is None:
            raise FillNotFound(fill_id)
        if not moved:
            raise FillOutcomeRefused()
        return fill


# --- the view (the contract Leg 6's client reads) --------------------------------------


PENDING_STATUSES = ("sent", "applying", "not_filled")


async def fill_view(conn: aiosqlite.Connection, fill: Fill) -> dict[str, Any]:
    """The ``fill_requested`` / ``fill_changed`` payload and the receipt's data.

    Never carries ``claim_token``. ``values`` are the stored changes as the editor needs them
    (ids for the provider, MCP servers and knowledge bases); ``changes`` and ``base`` show
    each id as the name it has now. ``stale`` lists the fields whose stored value now differs
    from ``base`` (``[{field, label, current, proposed}]``; empty for a create), computed here
    when read. ``target_gone``: a change's agent no longer exists.
    """
    from the_one.gleepglorp import kinds
    from the_one.gleepglorp.proposals.store import display_values

    labels = {f.stored: f.label for f in kinds.SPECS.get(fill.kind, ())}
    kind = kinds.get(fill.kind)
    # The kind's own title, existence, stale rows and key-clearing (``Kind.fill_extras``).
    assert kind.fill_extras is not None  # a stored fill is of a fillable kind
    extras = await kind.fill_extras(conn, fill, labels)
    warnings: list[str] = []
    if kind.warnings is not None and fill.status in PENDING_STATUSES:
        from the_one.config import settings
        from the_one.encryption import get_encryptor

        # The kind's proposal-time warnings, read from the stored row, for a fill still to be
        # applied (a ``Fill`` carries the ``action``, ``changes`` and ``target_id`` they read).
        # ``mode="fill"``: the operator saves the form, so no sentence says "after approving".
        warnings = await kind.warnings(conn, get_encryptor(settings.data_dir), fill, mode="fill")
    return {
        "id": fill.id,
        "kind": fill.kind,
        "action": fill.action,
        "agent_name": fill.agent_name,
        "target_id": fill.target_id,
        "status": fill.status,
        "outcome": fill.outcome,
        "untrusted": fill.untrusted,
        "untrusted_sources": fill.untrusted_sources,
        "created_at": fill.created_at,
        "claimed_at": fill.claimed_at,
        "resolved_at": fill.resolved_at,
        "tool_call_id": fill.tool_call_id,
        "values": fill.changes,
        "changes": await display_values(conn, fill.changes),
        "base": await display_values(conn, fill.base) if fill.base is not None else None,
        "labels": labels,
        "title": extras["title"],
        "field_count": len(fill.changes),
        "target_gone": extras["target_gone"],
        "stale": extras["stale"],
        "warnings": warnings,
        # A fill that moves a provider's type away from a key-taking type (or to a keyless one)
        # tells the editor to empty its key field: a key never follows a provider to another
        # service (M36 F4 L5b). Computed here from the stored type.
        "clears_key": extras["clears_key"],
    }
