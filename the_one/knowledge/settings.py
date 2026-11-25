"""App-wide knowledge-base settings: embedding + chunking + monitoring
(M24 F02 L03, DD-6; monitoring added M24 F04 L01, DD-5).

Three ``app_metadata`` JSON records (``load_knowledge_settings`` /
``save_knowledge_settings``), defaults applied on read, plus the separate
store-written ``vector_store`` record below. Nothing here is a credential
(DD-2 removed the only case that would have been), so plaintext JSON via the
existing ``AppMetadataRepository`` is correct — no encryptor, no new table.

The embedding record has exactly one valid value per DD-2 (non-LLM local
embeddings are the product; a provider-delegating backend was amended out of
Mission 24 at Flight 2 planning). ``EmbeddingSettings`` therefore uses plain
``str``/``int`` fields with ``field_validator``s that raise ``ValueError``
naming the amendment — **not** ``Literal`` fields: a ``Literal`` mismatch
would surface pydantic's generic "Input should be 'local'" message and a
``Field(description=...)`` never reaches ``.errors()`` (verified against
pydantic 2.13 at design review), so only a validator can put the amendment
context in the 422 response.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from the_one.db._write_lock import write_transaction
from the_one.db.repositories import AppMetadataRepository
from the_one.embeddings.local import EMBEDDING_DIM, EMBEDDING_MODEL_DIRNAME

logger = logging.getLogger(__name__)

EMBEDDING_KEY = "knowledge.embedding"
CHUNKING_KEY = "knowledge.chunking"
VECTOR_STORE_KEY = "knowledge.vector_store"
MONITORING_KEY = "knowledge.monitoring"


def walk_skip_counters_key(folder_item_id: str) -> str:
    """The ``app_metadata`` key holding a folder item's last completed
    walk's skip counters (DD-7, Flight 7 Leg 2, AC-11b).

    ONE shared helper, used by all four call sites: the write site
    (``manager.py``'s ``_walk_one_folder``, right after a walk completes),
    the read site (``api.py``'s ``get_kb_status``), and both cleanup sites
    (``delete_kb_item``, ``delete_knowledge_base``). A kv key derived
    independently at each site is exactly how a drifted cleanup key would
    silently leave orphaned rows behind while ``AppMetadataRepository.get``
    on the wrong key still returns ``None`` — a false green even under a
    test that asserts "no key behind" (AC-12), because it would be
    checking the same drifted key the cleanup site used, not the one the
    write site actually wrote.
    """
    return f"knowledge.walk_skips.{folder_item_id}"


# DD-9: usearch, the operator's Flight 2 decision-checkpoint choice
# (flight-log.md, "DD-9 decision checkpoint (2026-09-15)"), offers `f16`/`i8`
# natively.
_VECTOR_STORE_DTYPES: dict[str, tuple[str, ...]] = {
    "usearch": ("f16", "i8"),
}

_AMENDMENT_MESSAGE = (
    "non-LLM local embeddings are the product; a provider-delegating backend "
    "was removed from Mission 24 at Flight 2 planning — see mission.md"
)


class EmbeddingSettings(BaseModel):
    """The embedding backend/model choice. Exactly one valid combination
    exists today (DD-2); a future second bundled model would widen the
    validators below rather than switch to a ``Literal``.

    ``extra="forbid"`` (squawk 0056): a nested unknown key merged into this
    section by ``update_knowledge_settings`` must surface as a 422, not be
    silently dropped by pydantic's default ``extra="ignore"``.
    """

    model_config = ConfigDict(extra="forbid")

    backend: str = "local"
    model_id: str = EMBEDDING_MODEL_DIRNAME
    dim: int = EMBEDDING_DIM

    @field_validator("backend")
    @classmethod
    def _validate_backend(cls, value: str) -> str:
        if value != "local":
            raise ValueError(_AMENDMENT_MESSAGE)
        return value

    @field_validator("model_id")
    @classmethod
    def _validate_model_id(cls, value: str) -> str:
        if value != EMBEDDING_MODEL_DIRNAME:
            raise ValueError(_AMENDMENT_MESSAGE)
        return value

    @field_validator("dim")
    @classmethod
    def _validate_dim(cls, value: int) -> int:
        if value != EMBEDDING_DIM:
            raise ValueError(_AMENDMENT_MESSAGE)
        return value


class ChunkingSettings(BaseModel):
    """Chunking policy (DD-7). App-wide, not per-KB; changes apply to future
    indexing only — existing chunks are never re-chunked in place.

    ``extra="forbid"`` (squawk 0056): see ``EmbeddingSettings`` above — the
    same nested-unknown-key rationale applies here.
    """

    model_config = ConfigDict(extra="forbid")

    size_chars: int = Field(1000, ge=200, le=2000)
    overlap_chars: int = Field(150, ge=0)

    @model_validator(mode="after")
    def _validate_overlap(self) -> "ChunkingSettings":
        if self.overlap_chars > self.size_chars // 2:
            raise ValueError(
                f"overlap_chars ({self.overlap_chars}) must not exceed 50% of "
                f"size_chars ({self.size_chars})"
            )
        return self


class VectorStoreSettings(BaseModel):
    """The vector-store backend/dtype/model choice (Leg 4, DD-3/DD-4; the
    record is the DD-9 outcome since Leg 6).

    **Store-written, not operator-configurable**: ``update_knowledge_settings``
    already 422s any top-level key outside the accepted set —
    ``embedding``, ``chunking`` and (since Flight 4) ``monitoring`` — (see
    ``the_one/interfaces/web/api.py``), so a ``vector_store`` key in a
    ``PUT`` body is refused by that existing generic guard — no dedicated
    message is added here. ``GET /api/knowledge-settings`` surfaces this
    record read-only under ``"vector_store"``.

    The default is ``usearch``/``f16`` — the operator's DD-9 choice at the
    Flight 2 decision checkpoint (flight-log.md, "DD-9 decision checkpoint
    (2026-09-15)"): only usearch clears the operator's p95 <= 250ms bar at
    the corpus ceiling on Windows, and f16 is chosen over i8 for the
    recall margin (0.98 vs 0.9465-0.953 against the 0.95 floor). The other
    benchmarked candidate was removed from the closure in Leg 6.

    ``extra="forbid"`` (squawk 0056, for consistency with ``EmbeddingSettings``
    /``ChunkingSettings`` above): this record is never operator-written
    through the PUT route (the top-level-key guard already refuses a
    ``vector_store`` key), so this only tightens ``load_vector_store_settings``
    against a corrupted/drifted stored record — which DD-3/DD-9 already
    requires to raise rather than degrade. The only writer,
    ``save_vector_store_settings``, always writes exactly this model's
    fields via ``model_dump_json()``, so no current writer can produce an
    extra key.
    """

    model_config = ConfigDict(extra="forbid")

    backend: Literal["usearch"] = "usearch"
    dtype: str = "f16"
    dim: int = EMBEDDING_DIM
    model_id: str = EMBEDDING_MODEL_DIRNAME

    @model_validator(mode="after")
    def _validate_dtype_for_backend(self) -> "VectorStoreSettings":
        allowed = _VECTOR_STORE_DTYPES[self.backend]
        if self.dtype not in allowed:
            raise ValueError(
                f"dtype {self.dtype!r} is not valid for backend {self.backend!r} "
                f"(allowed: {allowed})"
            )
        return self


class MonitoringSettings(BaseModel):
    """Change-monitoring configuration (Flight 4 M24 F04, DD-5): whether the
    per-folder filesystem watcher is on, and how often the periodic
    reconciliation walk runs for every knowledge base that has a folder.

    Operator-configurable through ``PUT /api/knowledge-settings`` (over env
    vars, DD-5) and applied live: a change reaches the watch manager through
    an awaited hook on the same request, not only on the next indexing pass
    (unlike ``ChunkingSettings``, which is future-indexing-only).

    ``extra="forbid"`` (squawk 0056): see ``EmbeddingSettings`` above — the
    same nested-unknown-key rationale applies here.
    """

    model_config = ConfigDict(extra="forbid")

    watch_enabled: bool = True
    reconcile_interval_seconds: int = Field(300, ge=10, le=86400)


class KnowledgeSettings(BaseModel):
    """The full app-wide knowledge configuration returned by
    ``GET /api/knowledge-settings``."""

    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)


async def load_knowledge_settings(conn) -> KnowledgeSettings:
    """Read both settings records, applying defaults for an absent or
    invalid stored value.

    A stored value that fails to parse as JSON or fails validation is
    logged (naming the key) and replaced with the default rather than
    raising — a read must never fail the caller over a corrupted or
    stale-shape record.
    """
    repo = AppMetadataRepository(conn)

    embedding = EmbeddingSettings()
    raw_embedding = await repo.get(EMBEDDING_KEY)
    if raw_embedding is not None:
        try:
            embedding = EmbeddingSettings.model_validate_json(raw_embedding)
        except (ValidationError, ValueError):
            logger.warning(
                "invalid stored value for %r — using defaults", EMBEDDING_KEY, exc_info=True
            )

    chunking = ChunkingSettings()
    raw_chunking = await repo.get(CHUNKING_KEY)
    if raw_chunking is not None:
        try:
            chunking = ChunkingSettings.model_validate_json(raw_chunking)
        except (ValidationError, ValueError):
            logger.warning(
                "invalid stored value for %r — using defaults", CHUNKING_KEY, exc_info=True
            )

    monitoring = MonitoringSettings()
    raw_monitoring = await repo.get(MONITORING_KEY)
    if raw_monitoring is not None:
        try:
            monitoring = MonitoringSettings.model_validate_json(raw_monitoring)
        except (ValidationError, ValueError):
            logger.warning(
                "invalid stored value for %r — using defaults", MONITORING_KEY, exc_info=True
            )

    return KnowledgeSettings(embedding=embedding, chunking=chunking, monitoring=monitoring)


async def save_knowledge_settings(conn, settings: KnowledgeSettings) -> None:
    """Write all three records in ONE write transaction (Mission 36 F5 L4a: a failure part-way
    leaves none of them written). The records stay independent keys (DD-6)."""
    async with write_transaction(conn):
        await AppMetadataRepository.set_in_txn(
            conn, EMBEDDING_KEY, settings.embedding.model_dump_json()
        )
        await AppMetadataRepository.set_in_txn(
            conn, CHUNKING_KEY, settings.chunking.model_dump_json()
        )
        await AppMetadataRepository.set_in_txn(
            conn, MONITORING_KEY, settings.monitoring.model_dump_json()
        )


async def load_vector_store_settings(conn) -> VectorStoreSettings:
    """Read the store-written ``knowledge.vector_store`` record.

    Unlike :func:`load_knowledge_settings`, an INVALID stored record
    RAISES rather than silently falling back to the default (DD-3/DD-9):
    a corrupt or drifted vector-store record is the one setting that must
    not silently fall back, because the wrong backend would read the
    wrong on-disk data with no error at all. An ABSENT record (never
    configured) is not an error — it returns the default
    (``usearch``/``f16``).
    """
    repo = AppMetadataRepository(conn)
    raw = await repo.get(VECTOR_STORE_KEY)
    if raw is None:
        return VectorStoreSettings()
    return VectorStoreSettings.model_validate_json(raw)


async def save_vector_store_settings(conn, settings: VectorStoreSettings) -> None:
    """Write the ``knowledge.vector_store`` record. Called by the store
    dispatcher's owning code path (Leg 6), never by the operator-facing
    ``PUT /api/knowledge-settings`` route."""
    repo = AppMetadataRepository(conn)
    await repo.set(VECTOR_STORE_KEY, settings.model_dump_json())
