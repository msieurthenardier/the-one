"""Tests for the extractor seam (Flight 3 Leg 2, DD-4): the ``Extractor``
Protocol, the suffix-keyed registry, ``TextExtractor``, and the M7 mission
criterion — indexing a brand-new format needs no pipeline change.

Covers AC-1 (the registry shape), AC-2 (``TextExtractor``'s decode rules
and ``TEXT_EXTENSIONS``), and AC-3 (the stub-extractor end-to-end proof).
"""

from __future__ import annotations

import aiosqlite
import pytest

from tests._embedding_stub import StubEmbeddingBackend
from tests._extractor_stub import STUB_TEXT, StubExtractor
from the_one.config import settings
from the_one.db._write_lock import reset_for_test as reset_write_lock
from the_one.db.models import KBItem, KnowledgeBase
from the_one.db.repositories import KBChunkRepository, KBItemRepository, KnowledgeBaseRepository
from the_one.db.schema import ensure_schema
from the_one.knowledge import extractors
from the_one.knowledge.extractors import (
    ExtractionError,
    Extractor,
    clear_for_test,
    extractor_for,
    register,
    supported_extensions,
    unregister,
)
from the_one.knowledge.extractors.text import TEXT_EXTENSIONS, TextExtractor
from the_one.knowledge.indexer import IndexContext, index_item
from the_one.knowledge.settings import ChunkingSettings
from the_one.vectors import _reset_for_test as reset_vectors_module
from the_one.vectors.usearch_store import UsearchStore


@pytest.fixture(autouse=True)
def _reset_module_state():
    reset_write_lock()
    reset_vectors_module()
    yield
    reset_write_lock()
    reset_vectors_module()


@pytest.fixture(autouse=True)
def _restore_builtin_extractors():
    """Every test in this module may register/unregister extractors — make
    sure the built-ins are back afterward regardless of outcome, per AC-3's
    teardown requirement."""
    yield
    clear_for_test()
    extractors._register_builtins()


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


# ── AC-1: the registry shape ───────────────────────────────────────────


class TestRegistryShape:
    def test_import_registers_text_extractor(self) -> None:
        assert supported_extensions() == TEXT_EXTENSIONS

    def test_text_extractor_satisfies_protocol_structurally(self) -> None:
        instance = TextExtractor()
        assert isinstance(instance, Extractor)
        assert Extractor not in TextExtractor.__mro__

    def test_extractor_for_looks_up_by_lowercased_suffix(self) -> None:
        from pathlib import Path

        found = extractor_for(Path("/tmp/readme.MD"))
        assert found is not None
        assert found.name == "text"

    def test_extractor_for_unknown_suffix_returns_none(self) -> None:
        from pathlib import Path

        assert extractor_for(Path("/tmp/file.zzz")) is None

    def test_register_conflicting_suffix_different_name_raises(self) -> None:
        class _Other:
            name = "other"
            extensions = frozenset({".txt"})

            def extract(self, path):
                return ""

        with pytest.raises(ValueError, match=r"\.txt"):
            register(_Other())
        # All-or-nothing: `.txt` still belongs to `text`, not `other`.
        from pathlib import Path

        assert extractor_for(Path("/a.txt")).name == "text"

    def test_register_same_name_is_a_noop(self) -> None:
        before = supported_extensions()
        register(TextExtractor())
        assert supported_extensions() == before

    def test_register_all_or_nothing_on_partial_conflict(self) -> None:
        class _Partial:
            name = "partial"
            extensions = frozenset({".partialnew", ".txt"})  # .txt conflicts

            def extract(self, path):
                return ""

        before = supported_extensions()
        with pytest.raises(ValueError):
            register(_Partial())
        # Neither suffix was added — not even the non-conflicting one.
        assert supported_extensions() == before
        assert ".partialnew" not in supported_extensions()

    def test_unregister_removes_every_suffix_for_that_name(self) -> None:
        class _Multi:
            name = "multi"
            extensions = frozenset({".multia", ".multib"})

            def extract(self, path):
                return ""

        register(_Multi())
        assert ".multia" in supported_extensions()
        assert ".multib" in supported_extensions()
        unregister("multi")
        assert ".multia" not in supported_extensions()
        assert ".multib" not in supported_extensions()

    def test_unregister_unknown_name_is_a_noop(self) -> None:
        before = supported_extensions()
        unregister("does-not-exist")
        assert supported_extensions() == before

    def test_clear_for_test_then_reregister_builtins_restores_registry(self) -> None:
        before = supported_extensions()
        clear_for_test()
        assert supported_extensions() == frozenset()
        extractors._register_builtins()
        assert supported_extensions() == before


# ── AC-2: TextExtractor ─────────────────────────────────────────────────


class TestTextExtractor:
    def test_strips_utf8_bom(self, tmp_path) -> None:
        path = tmp_path / "bom.txt"
        path.write_bytes(b"\xef\xbb\xbfhello world")
        text = TextExtractor().extract(path)
        assert text == "hello world"
        assert "﻿" not in text

    def test_invalid_byte_becomes_replacement_char(self, tmp_path) -> None:
        path = tmp_path / "bad.txt"
        path.write_bytes(b"hello \xff\xfe world")
        text = TextExtractor().extract(path)
        assert "�" in text

    def test_missing_file_raises_extraction_error_chained_from_oserror(self, tmp_path) -> None:
        path = tmp_path / "does-not-exist.txt"
        with pytest.raises(ExtractionError) as exc_info:
            TextExtractor().extract(path)
        assert isinstance(exc_info.value.__cause__, OSError)

    def test_text_extensions_is_the_dd4_set(self) -> None:
        expected = {
            ".txt",
            ".text",
            ".md",
            ".markdown",
            ".rst",
            ".adoc",
            ".py",
            ".pyi",
            ".js",
            ".mjs",
            ".cjs",
            ".ts",
            ".tsx",
            ".jsx",
            ".json",
            ".jsonl",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
            ".conf",
            ".csv",
            ".tsv",
            ".sh",
            ".bash",
            ".zsh",
            ".ps1",
            ".bat",
            ".go",
            ".rs",
            ".java",
            ".kt",
            ".c",
            ".h",
            ".cc",
            ".cpp",
            ".hpp",
            ".cs",
            ".rb",
            ".php",
            ".swift",
            ".sql",
            ".xml",
        }
        assert TEXT_EXTENSIONS == frozenset(expected)

    def test_extensions_are_lowercase_with_dot(self) -> None:
        for ext in TEXT_EXTENSIONS:
            assert ext.startswith(".")
            assert ext == ext.lower()

    def test_html_htm_log_are_absent(self) -> None:
        assert ".html" not in TEXT_EXTENSIONS
        assert ".htm" not in TEXT_EXTENSIONS
        assert ".log" not in TEXT_EXTENSIONS


# ── AC-3: the M7 test — a brand-new format needs no pipeline change ──────


class TestStubExtractorEndToEnd:
    async def test_stub_extension_indexes_end_to_end(self, conn, tmp_path, monkeypatch) -> None:
        register(StubExtractor())

        monkeypatch.setattr(settings, "data_dir", tmp_path)
        store = UsearchStore(conn, dtype="f16", dim=8)
        await store.open()

        kb_repo = KnowledgeBaseRepository(conn)
        item_repo = KBItemRepository(conn)
        chunk_repo = KBChunkRepository(conn)
        await kb_repo.create(KnowledgeBase(id="kb1", name="kb1"))

        path = tmp_path / "weird.stub"
        # Content is irrelevant — StubExtractor always returns STUB_TEXT,
        # ignoring what's on disk.
        path.write_text("this is never read by the stub extractor")
        item = KBItem(id="item1", kb_id="kb1", type="file", path_or_url=str(path))
        await item_repo.create(item)

        ctx = IndexContext(
            conn=conn,
            item_repo=item_repo,
            chunk_repo=chunk_repo,
            store=store,
            backend=StubEmbeddingBackend(dim=8),
            chunking=ChunkingSettings(size_chars=200, overlap_chars=20),
        )

        outcome = await index_item(item, ctx)

        assert outcome.status == "awaiting_flush"
        assert outcome.error is None
        assert outcome.chunks >= 1

        rows = await chunk_repo.list_for_item(item.id)
        assert rows
        assert rows[0].text in STUB_TEXT  # chunked, but derived from STUB_TEXT

        assert await store.count("kb1") == outcome.chunks
