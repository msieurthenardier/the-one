"""Startup reconciliation for an interrupted encryption key rotation.

If a rotation's DB commit succeeded but the on-disk key-file promotion
failed (or the process was killed between the two), a `.next` sidecar is
left on disk and the in-memory `Encryptor` for a freshly-started process
loads it as a pending key (see `the_one.encryption.get_encryptor`). This
module samples ciphertext across every encrypted corpus and decides
whether to promote or discard that pending key, so a restart self-heals
without operator intervention.
"""

from __future__ import annotations

import aiosqlite

from the_one.encryption import Encryptor, resolve_pending_key

# (table, column) pairs for every corpus that may hold Fernet ciphertext.
# Table/column names are a fixed module constant — never built from input.
_ENCRYPTED_CORPORA: tuple[tuple[str, str], ...] = (
    ("llm_providers", "api_key"),
    ("llm_providers", "secrets"),
    ("mcp_sources", "secrets"),
    ("connectors", "secrets"),
    ("agents", "tool_overrides"),
    ("agents", "mcp_overrides"),
    ("tool_configs", "secrets"),
    ("agent_external_credentials", "secret"),
)


async def sample_ciphertexts(conn: aiosqlite.Connection, *, per_column: int = 50) -> list[str]:
    """Sample up to *per_column* non-empty values from each encrypted corpus.

    Skips a corpus whose table doesn't exist yet (pre-migration DB).
    """
    samples: list[str] = []
    for table, column in _ENCRYPTED_CORPORA:
        query = (
            f"SELECT {column} FROM {table} "  # noqa: S608 - fixed constant identifiers
            f"WHERE {column} IS NOT NULL AND {column} != '' LIMIT ?"
        )
        try:
            async with conn.execute(query, (per_column,)) as cursor:
                rows = await cursor.fetchall()
        except aiosqlite.OperationalError:
            continue
        samples.extend(row[0] for row in rows)
    return samples


async def reconcile_pending_key(conn: aiosqlite.Connection, encryptor: Encryptor) -> str:
    """Resolve any pending key on *encryptor* using ciphertext sampled from *conn*.

    Returns "absent" without querying the database when there is no pending
    key. Otherwise delegates the decision to
    :func:`the_one.encryption.resolve_pending_key`, which performs the
    promote/discard mutation.
    """
    if encryptor.pending_key is None:
        return "absent"
    samples = await sample_ciphertexts(conn)
    return resolve_pending_key(encryptor, samples)
