"""``SqliteVecStore`` — the ``sqlite-vec``/``vec0``-backed ``VectorStore``
(Flight 2 Leg 4, DD-3/DD-4/DD-10).

One shared virtual table, ``kb_vectors``, lives in the main app database
(``kb_id TEXT partition key, embedding <dtype>[dim] distance_metric=cosine``)
— created here with ``CREATE VIRTUAL TABLE IF NOT EXISTS``, never by a v40+
migration, because the column dtype is a measured (DD-4) choice and the
table only exists at all when this backend is the configured one.

**Extension loading discipline (DD-10, mirrors ``diagnostics._probe_sqlite_vec``)**:
``open()`` enables extension loading, loads ``vec0`` via
``sqlite_vec.loadable_path()``, and disables loading again in a
``finally`` — extension loading stays OFF for the rest of the
connection's life. ``sqlite_vec.load(conn)`` is deliberately NOT used
here: on an ``aiosqlite.Connection`` that call does not raise, but it
creates never-awaited coroutines and loads nothing (verified) — the
correct call is ``await conn.load_extension(str(sqlite_vec.loadable_path()))``,
which ``aiosqlite`` proxies to the underlying thread.

``open()`` uses double-checked locking under ``write_transaction`` (the
``get_embedding_backend()`` shape): the outer ``if self._loaded: return``
avoids paying the lock on the fast path, and the INNER re-check (once the
lock is held) is what makes two concurrent ``open()`` calls load the
extension exactly once — without the inner check, both callers would pass
the outer check before either sets the flag, and the second would redo the
whole body (including a second extension load) after the first releases
the lock.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Literal

import aiosqlite
import numpy as np

from the_one.db._write_lock import write_transaction
from the_one.vectors._store import VectorStoreError, VectorStoreMismatchError, quantize_int8

_VALID_DTYPES = ("float32", "int8")


class SqliteVecStore:
    """``VectorStore`` over a shared ``vec0`` virtual table.

    Structurally satisfies the ``VectorStore`` Protocol (no inheritance,
    per ``structural-Protocol-satisfaction``).
    """

    backend = "sqlite-vec"

    def __init__(
        self,
        conn: aiosqlite.Connection,
        *,
        dtype: Literal["float32", "int8"],
        dim: int = 512,
    ) -> None:
        if dtype not in _VALID_DTYPES:
            raise ValueError(f"SqliteVecStore dtype must be one of {_VALID_DTYPES}, got {dtype!r}")
        self.conn = conn
        self.dtype = dtype
        self.dim = dim
        self._col = "float" if dtype == "float32" else "int8"
        self._loaded = False

    async def open(self) -> None:
        if self._loaded:
            return
        async with write_transaction(self.conn):
            # Double-checked: a concurrent opener may have finished while we
            # waited for the lock.
            if self._loaded:
                return

            if not hasattr(sqlite3.Connection, "enable_load_extension"):
                raise VectorStoreError(
                    "knowledge.vector_store: this Python build has no "
                    "sqlite3.Connection.enable_load_extension (compiled out) — "
                    "the vec0 extension cannot be loaded"
                )

            import sqlite_vec

            await self.conn.enable_load_extension(True)
            try:
                await self.conn.load_extension(str(sqlite_vec.loadable_path()))
            finally:
                await self.conn.enable_load_extension(False)

            await self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS kb_vectors USING vec0("
                "kb_id TEXT partition key, "
                f"embedding {self._col}[{self.dim}] distance_metric=cosine)"
            )
            async with self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'kb_vectors'"
            ) as cur:
                row = await cur.fetchone()
            live_sql = row[0] if row is not None else "<no kb_vectors table>"
            expected = f"embedding {self._col}[{self.dim}]"
            if expected not in live_sql:
                raise VectorStoreMismatchError(
                    f"knowledge.vector_store: configured as sqlite-vec/{self.dtype} "
                    f"(dim={self.dim}), expecting {expected!r} in kb_vectors' live DDL, "
                    f"but found {live_sql!r} — the setting and the table have drifted"
                )
            self._loaded = True

    def _serialize(self, vector: np.ndarray) -> bytes:
        import sqlite_vec

        if self.dtype == "float32":
            return sqlite_vec.serialize_float32(np.asarray(vector, dtype=np.float32).tolist())
        return sqlite_vec.serialize_int8(
            quantize_int8(np.asarray(vector, dtype=np.float32)).tolist()
        )

    async def upsert(self, kb_id: str, ids: Sequence[int], vectors: np.ndarray) -> None:
        id_list = list(ids)
        if not id_list:
            return
        blobs = [self._serialize(vec) for vec in vectors]
        value_expr = "?" if self.dtype == "float32" else "vec_int8(?)"
        async with write_transaction(self.conn):
            await self.conn.executemany(
                "DELETE FROM kb_vectors WHERE rowid = ?", [(int(i),) for i in id_list]
            )
            await self.conn.executemany(
                f"INSERT INTO kb_vectors(rowid, kb_id, embedding) VALUES (?, ?, {value_expr})",
                [(int(i), kb_id, blob) for i, blob in zip(id_list, blobs, strict=True)],
            )

    async def delete(self, kb_id: str, ids: Sequence[int]) -> None:
        id_list = list(ids)
        if not id_list:
            return
        async with write_transaction(self.conn):
            await self.conn.executemany(
                "DELETE FROM kb_vectors WHERE rowid = ?", [(int(i),) for i in id_list]
            )

    async def delete_kb(self, kb_id: str) -> None:
        async with write_transaction(self.conn):
            await self.conn.execute("DELETE FROM kb_vectors WHERE kb_id = ?", (kb_id,))

    async def query(self, kb_id: str, vector: np.ndarray, k: int) -> list[tuple[int, float]]:
        blob = self._serialize(vector)
        match_expr = "?" if self.dtype == "float32" else "vec_int8(?)"
        async with self.conn.execute(
            f"SELECT rowid, distance FROM kb_vectors WHERE embedding MATCH {match_expr} "
            "AND kb_id = ? AND k = ?",
            (blob, kb_id, k),
        ) as cur:
            rows = await cur.fetchall()
        return [(int(row[0]), float(row[1])) for row in rows]

    async def count(self, kb_id: str) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM kb_vectors WHERE kb_id = ?", (kb_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def flush(self, kb_id: str) -> None:
        """No-op: ``vec0`` writes commit on ``upsert`` (DD-3)."""
        return None

    async def close(self) -> None:
        """No-op: nothing to flush or release beyond the shared connection."""
        return None
