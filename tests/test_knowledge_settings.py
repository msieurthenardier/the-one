"""Tests for the app-wide knowledge settings (M24 F02 L03, DD-6, AC-8)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from the_one.knowledge.settings import (
    CHUNKING_KEY,
    EMBEDDING_KEY,
    VECTOR_STORE_KEY,
    ChunkingSettings,
    EmbeddingSettings,
    KnowledgeSettings,
    VectorStoreSettings,
    load_knowledge_settings,
    load_vector_store_settings,
    save_knowledge_settings,
    save_vector_store_settings,
)


@pytest.fixture
async def conn(tmp_path):
    import aiosqlite

    from the_one.db.schema import ensure_schema

    db_path = tmp_path / "test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


class TestDefaults:
    async def test_defaults_on_empty_app_metadata(self, conn) -> None:
        settings = await load_knowledge_settings(conn)
        assert settings.embedding.backend == "local"
        assert settings.embedding.model_id == "potion-retrieval-32M"
        assert settings.embedding.dim == 512
        assert settings.chunking.size_chars == 1000
        assert settings.chunking.overlap_chars == 150


class TestRoundTrip:
    async def test_save_then_load_round_trips(self, conn) -> None:
        original = KnowledgeSettings(
            embedding=EmbeddingSettings(),
            chunking=ChunkingSettings(size_chars=800, overlap_chars=100),
        )
        await save_knowledge_settings(conn, original)
        loaded = await load_knowledge_settings(conn)
        assert loaded == original

    async def test_save_writes_both_keys(self, conn) -> None:
        from the_one.db.repositories import AppMetadataRepository

        await save_knowledge_settings(conn, KnowledgeSettings())
        repo = AppMetadataRepository(conn)
        assert await repo.get(EMBEDDING_KEY) is not None
        assert await repo.get(CHUNKING_KEY) is not None


class TestInvalidStoredValue:
    async def test_invalid_json_falls_back_to_default_with_warning(
        self, conn, caplog: pytest.LogCaptureFixture
    ) -> None:
        from the_one.db.repositories import AppMetadataRepository

        repo = AppMetadataRepository(conn)
        await repo.set(EMBEDDING_KEY, "not valid json{{{")

        with caplog.at_level("WARNING"):
            settings = await load_knowledge_settings(conn)

        assert settings.embedding == EmbeddingSettings()
        assert any(EMBEDDING_KEY in record.message for record in caplog.records)

    async def test_invalid_validation_falls_back_to_default_with_warning(
        self, conn, caplog: pytest.LogCaptureFixture
    ) -> None:
        from the_one.db.repositories import AppMetadataRepository

        repo = AppMetadataRepository(conn)
        await repo.set(CHUNKING_KEY, '{"size_chars": 50, "overlap_chars": 10}')

        with caplog.at_level("WARNING"):
            settings = await load_knowledge_settings(conn)

        assert settings.chunking == ChunkingSettings()
        assert any(CHUNKING_KEY in record.message for record in caplog.records)


class TestEmbeddingSettingsValidation:
    def test_default_is_valid(self) -> None:
        EmbeddingSettings()

    def test_non_local_backend_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Mission 24"):
            EmbeddingSettings(backend="ollama")

    def test_wrong_model_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Mission 24"):
            EmbeddingSettings(model_id="some-other-model")

    def test_wrong_dim_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Mission 24"):
            EmbeddingSettings(dim=256)


class TestChunkingSettingsValidation:
    def test_default_is_valid(self) -> None:
        ChunkingSettings()

    @pytest.mark.parametrize("size_chars", [199, 2001])
    def test_size_chars_out_of_bounds_rejected(self, size_chars: int) -> None:
        with pytest.raises(ValidationError):
            ChunkingSettings(size_chars=size_chars)

    @pytest.mark.parametrize("size_chars", [200, 2000])
    def test_size_chars_bounds_are_inclusive(self, size_chars: int) -> None:
        ChunkingSettings(size_chars=size_chars, overlap_chars=0)

    def test_overlap_above_half_size_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChunkingSettings(size_chars=1000, overlap_chars=600)

    def test_overlap_at_half_size_is_valid(self) -> None:
        ChunkingSettings(size_chars=1000, overlap_chars=500)


class TestVectorStoreSettingsValidation:
    """M24 F02 L04, DD-3/DD-4, AC-12."""

    def test_default_is_valid(self) -> None:
        settings = VectorStoreSettings()
        assert settings.backend == "usearch"
        assert settings.dtype == "f16"
        assert settings.dim == 512

    @pytest.mark.parametrize("dtype", ["f16", "i8"])
    def test_usearch_valid_dtypes(self, dtype: str) -> None:
        VectorStoreSettings(backend="usearch", dtype=dtype)

    @pytest.mark.parametrize("dtype", ["float32", "int8"])
    def test_usearch_with_removed_sqlite_vec_dtypes_rejected(self, dtype: str) -> None:
        """`float32`/`int8` were sqlite-vec's dtypes (removed in Leg 6) —
        neither is valid for usearch."""
        with pytest.raises(ValidationError):
            VectorStoreSettings(backend="usearch", dtype=dtype)

    def test_sqlite_vec_backend_rejected(self) -> None:
        """`backend` narrowed to `Literal["usearch"]` in Leg 6 — the
        removed backend name no longer validates at all."""
        with pytest.raises(ValidationError):
            VectorStoreSettings(backend="sqlite-vec", dtype="float32")


class TestVectorStoreSettingsPersistence:
    """AC-12: store-written, not operator-configurable — the record must
    round-trip and an absent record must default, but a stored INVALID
    record must raise (never silently fall back — DD-3/DD-9: the wrong
    backend would otherwise read the wrong on-disk data)."""

    async def test_defaults_when_record_absent(self, conn) -> None:
        loaded = await load_vector_store_settings(conn)
        assert loaded == VectorStoreSettings()

    async def test_save_then_load_round_trips(self, conn) -> None:
        original = VectorStoreSettings(backend="usearch", dtype="i8")
        await save_vector_store_settings(conn, original)
        loaded = await load_vector_store_settings(conn)
        assert loaded == original

    async def test_save_writes_the_key(self, conn) -> None:
        from the_one.db.repositories import AppMetadataRepository

        await save_vector_store_settings(conn, VectorStoreSettings())
        repo = AppMetadataRepository(conn)
        assert await repo.get(VECTOR_STORE_KEY) is not None

    async def test_invalid_stored_record_raises_rather_than_falling_back(self, conn) -> None:
        from the_one.db.repositories import AppMetadataRepository

        repo = AppMetadataRepository(conn)
        # A stale `sqlite-vec` record — the backend Leg 6 removed. `backend`
        # is now `Literal["usearch"]`, so this raises on the Literal check
        # before the dtype validator ever runs.
        await repo.set(VECTOR_STORE_KEY, '{"backend": "sqlite-vec", "dtype": "float32"}')

        with pytest.raises(ValidationError):
            await load_vector_store_settings(conn)
