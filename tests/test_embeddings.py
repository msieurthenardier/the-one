"""Tests for the embedding seam (M24 F02 L03, DD-1): the Protocol, the
production backend's guards and ``embed()`` contract, and the process
singleton. Real ``model2vec`` loads never happen here — every test either
stubs ``model2vec.StaticModel`` (mirroring
``tests/test_doctor_embedding_model.py``'s technique) or uses
``tests/_embedding_stub.py``'s ``StubEmbeddingBackend``, per the leg's
"no new real loads outside test_doctor_embedding_model.py" rule.
"""

from __future__ import annotations

import threading

import numpy as np
import pytest

from tests._embedding_stub import StubEmbeddingBackend
from the_one import embeddings
from the_one.embeddings import get_embedding_backend, schedule_warm_up, warm_up
from the_one.embeddings._backend import EmbeddingBackend, EmbeddingModelMissingError
from the_one.embeddings.local import EMBEDDING_DIM, LocalStaticBackend
from the_one.embeddings.local import force_hf_offline as _force_hf_offline
from the_one.embeddings.local import resolve_model_dir as _resolve_model_dir


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Every test starts and ends with a clean process-wide backend slot."""
    embeddings._reset_for_test()
    yield
    embeddings._reset_for_test()


class _StubStaticModel:
    """A ``model2vec.StaticModel`` stand-in whose ``encode``/``tokenize``
    calls are captured for assertion, following
    ``test_doctor_embedding_model.py``'s established stub technique.
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim
        self.embedding = np.zeros((1, dim), dtype=np.float16)
        self.encode_calls: list[dict] = []
        self.tokenize_calls: list[dict] = []
        # A map from text -> fake token-id list length, so a test can force
        # a specific truncation outcome deterministically.
        self.token_lengths: dict[str, int] = {}

    def tokenize(self, sentences: list[str], max_length: int | None = None) -> list[list[int]]:
        self.tokenize_calls.append({"sentences": list(sentences), "max_length": max_length})
        return [[0] * self.token_lengths.get(s, 1) for s in sentences]

    def encode(self, sentences: list[str], **kwargs: object) -> np.ndarray:
        self.encode_calls.append({"sentences": list(sentences), "kwargs": kwargs})
        unit = np.zeros(self.dim, dtype=np.float16)
        unit[0] = 1.0
        return np.tile(unit, (len(sentences), 1))


def _backend_with_stub_model(stub: _StubStaticModel) -> LocalStaticBackend:
    """Construct a ``LocalStaticBackend`` directly around a stub model,
    bypassing ``load()`` (and therefore any real filesystem/model2vec
    interaction) entirely — the point of exercising ``embed()`` in
    isolation from the load path.
    """
    return LocalStaticBackend(
        model=stub,
        model_id="potion-retrieval-32M",
        dim=stub.dim,
        native_dtype=str(stub.embedding.dtype),
        weights_bytes=12345,
        model_dir="/fake/model/dir",
    )


# ─────────────────────────────────────────────────────────────────────────
# AC-1 — structural Protocol satisfaction, stub determinism
# ─────────────────────────────────────────────────────────────────────────


class TestProtocolSatisfaction:
    def test_local_backend_satisfies_the_protocol_structurally(self) -> None:
        stub_model = _StubStaticModel()
        backend = _backend_with_stub_model(stub_model)
        assert isinstance(backend, EmbeddingBackend)
        # Structural, not nominal — the class does not inherit the Protocol.
        assert EmbeddingBackend not in type(backend).__mro__

    def test_stub_backend_satisfies_the_protocol_structurally(self) -> None:
        backend = StubEmbeddingBackend()
        assert isinstance(backend, EmbeddingBackend)
        assert EmbeddingBackend not in type(backend).__mro__


class TestStubEmbeddingBackend:
    def test_deterministic_across_instances(self) -> None:
        a = StubEmbeddingBackend(dim=8)
        b = StubEmbeddingBackend(dim=8)
        result_a = a.embed(["hello", "world"])
        result_b = b.embed(["hello", "world"])
        np.testing.assert_array_equal(result_a.vectors, result_b.vectors)

    def test_shape_dtype_and_unit_norm(self) -> None:
        backend = StubEmbeddingBackend(dim=8)
        result = backend.embed(["one", "two", "three"])
        assert result.vectors.shape == (3, 8)
        assert result.vectors.dtype == np.float32
        norms = np.linalg.norm(result.vectors, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-6)
        assert result.truncated == 0

    def test_empty_texts(self) -> None:
        backend = StubEmbeddingBackend(dim=8)
        result = backend.embed([])
        assert result.vectors.shape == (0, 8)
        assert result.vectors.dtype == np.float32
        assert result.truncated == 0

    def test_truncated_count(self) -> None:
        backend = StubEmbeddingBackend(dim=8, truncate_over_chars=5)
        result = backend.embed(["short", "this-is-long-enough"])
        assert result.truncated == 1

    def test_different_texts_yield_different_vectors(self) -> None:
        backend = StubEmbeddingBackend(dim=8)
        result = backend.embed(["alpha", "beta"])
        assert not np.allclose(result.vectors[0], result.vectors[1])


# ─────────────────────────────────────────────────────────────────────────
# AC-2 — LocalStaticBackend.embed() contract
# ─────────────────────────────────────────────────────────────────────────


class TestLocalStaticBackendEmbed:
    def test_shape_dtype_and_norm_for_short_inputs(self) -> None:
        stub_model = _StubStaticModel()
        backend = _backend_with_stub_model(stub_model)

        result = backend.embed(["a", "b"])

        assert result.vectors.shape == (2, EMBEDDING_DIM)
        assert result.vectors.dtype == np.float32
        norms = np.linalg.norm(result.vectors, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-3)
        assert result.truncated == 0
        # Short inputs (<= MAX_TOKENS chars) never trigger the tokenize pass.
        assert stub_model.tokenize_calls == []

    def test_encode_called_with_required_kwargs(self) -> None:
        stub_model = _StubStaticModel()
        backend = _backend_with_stub_model(stub_model)

        backend.embed(["a", "b"])

        assert len(stub_model.encode_calls) == 1
        kwargs = stub_model.encode_calls[0]["kwargs"]
        assert kwargs["use_multiprocessing"] is False
        assert kwargs["max_length"] == 512
        assert kwargs["show_progress_bar"] is False

    def test_long_input_is_tokenized_and_counted_as_truncated(self) -> None:
        stub_model = _StubStaticModel()
        long_text = "x" * 6000
        stub_model.token_lengths[long_text] = 600  # > 512 -> truncated
        backend = _backend_with_stub_model(stub_model)

        result = backend.embed(["short", long_text])

        assert result.truncated == 1
        assert result.vectors.shape == (2, EMBEDDING_DIM)
        # Only the long subset is tokenized — a short text can never exceed
        # MAX_TOKENS tokens (each token is >= 1 character).
        assert len(stub_model.tokenize_calls) == 1
        assert stub_model.tokenize_calls[0]["sentences"] == [long_text]
        assert stub_model.tokenize_calls[0]["max_length"] is None

    def test_long_input_under_token_cap_is_not_counted(self) -> None:
        stub_model = _StubStaticModel()
        long_text = "x" * 6000
        stub_model.token_lengths[long_text] = 100  # <= 512 -> not truncated
        backend = _backend_with_stub_model(stub_model)

        result = backend.embed([long_text])

        assert result.truncated == 0

    def test_empty_texts_returns_empty_without_calling_model(self) -> None:
        stub_model = _StubStaticModel()
        backend = _backend_with_stub_model(stub_model)

        result = backend.embed([])

        assert result.vectors.shape == (0, EMBEDDING_DIM)
        assert result.vectors.dtype == np.float32
        assert result.truncated == 0
        assert stub_model.encode_calls == []
        assert stub_model.tokenize_calls == []

    def test_zero_token_text_yields_float32_zero_vector(self) -> None:
        """Edge case: a text that tokenises to zero ids. model2vec flips such
        a batch to float64 internally — the seam's ``np.asarray(...,
        dtype=np.float32)`` must fix the dtype regardless.
        """

        class _ZeroVectorModel(_StubStaticModel):
            def encode(self, sentences: list[str], **kwargs: object) -> np.ndarray:
                self.encode_calls.append({"sentences": list(sentences), "kwargs": kwargs})
                # Simulate model2vec's real behaviour: an all-zero row, and
                # the batch silently upcast to float64.
                return np.zeros((len(sentences), self.dim), dtype=np.float64)

        stub_model = _ZeroVectorModel()
        backend = _backend_with_stub_model(stub_model)

        result = backend.embed(["�" * 6000])

        assert result.vectors.dtype == np.float32
        assert np.linalg.norm(result.vectors[0]) == 0.0


# ─────────────────────────────────────────────────────────────────────────
# AC-3 — resolve_model_dir() guards, force_hf_offline()
# ─────────────────────────────────────────────────────────────────────────


class TestResolveModelDir:
    def test_missing_directory_raises_and_never_reaches_from_pretrained(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from the_one.embeddings import local as embeddings_local

        monkeypatch.setattr(
            embeddings_local, "EMBEDDING_MODEL_DIRNAME", "definitely-not-a-real-model-directory"
        )

        with pytest.raises(EmbeddingModelMissingError, match="packaged model directory not found"):
            _resolve_model_dir()

    def test_missing_weights_file_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """Guard #2: the directory exists but ``model.safetensors`` does not.

        Design review found this guard had no test anywhere in the tree —
        only guard #1 (directory absence) was covered.
        """
        from the_one.embeddings import local as embeddings_local

        fake_model_dir = tmp_path / "data" / "fake-model"
        fake_model_dir.mkdir(parents=True)
        for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "modules.json"):
            (fake_model_dir / name).write_text("{}")

        monkeypatch.setattr(embeddings_local, "_resource_files", lambda pkg: tmp_path)
        monkeypatch.setattr(embeddings_local, "EMBEDDING_MODEL_DIRNAME", "fake-model")

        with pytest.raises(EmbeddingModelMissingError, match="model.safetensors missing from"):
            _resolve_model_dir()

    def test_success_forces_offline_and_returns_weights_size(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)

        model_dir, weights_bytes = _resolve_model_dir()

        assert model_dir.is_dir()
        assert weights_bytes > 0
        import os

        assert os.environ["HF_HUB_OFFLINE"] == "1"


class TestForceHfOffline:
    def test_sets_env_var_and_already_bound_constant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        fake_constants = type(sys)("huggingface_hub.constants")
        fake_constants.HF_HUB_OFFLINE = False
        monkeypatch.setitem(sys.modules, "huggingface_hub.constants", fake_constants)

        _force_hf_offline()

        import os

        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert fake_constants.HF_HUB_OFFLINE is True


# ─────────────────────────────────────────────────────────────────────────
# AC-4 — process singleton
# ─────────────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_repeated_calls_return_the_same_object(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def _fake_load() -> StubEmbeddingBackend:
            calls["n"] += 1
            return StubEmbeddingBackend()

        monkeypatch.setattr(LocalStaticBackend, "load", staticmethod(_fake_load))

        first = get_embedding_backend()
        second = get_embedding_backend()

        assert first is second
        assert calls["n"] == 1

    def test_reset_for_test_forces_a_rebuild(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def _fake_load() -> StubEmbeddingBackend:
            calls["n"] += 1
            return StubEmbeddingBackend()

        monkeypatch.setattr(LocalStaticBackend, "load", staticmethod(_fake_load))

        first = get_embedding_backend()
        embeddings._reset_for_test()
        second = get_embedding_backend()

        assert first is not second
        assert calls["n"] == 2

    def test_concurrent_first_calls_load_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ``threading.Lock`` double-check serializes concurrent first
        calls — only ONE thread ever reaches ``LocalStaticBackend.load()``.
        A ``ready`` gate holds every thread at the same starting line so they
        genuinely race for the lock, and a small sleep inside the fake
        loader widens the window in which a buggy (unlocked) implementation
        would let a second thread slip through.
        """
        import time

        calls = {"n": 0}
        ready = threading.Event()

        def _fake_load() -> StubEmbeddingBackend:
            calls["n"] += 1
            time.sleep(0.05)
            return StubEmbeddingBackend()

        monkeypatch.setattr(LocalStaticBackend, "load", staticmethod(_fake_load))

        results: list[object] = [None] * 8

        def _worker(i: int) -> None:
            ready.wait(timeout=5)
            results[i] = get_embedding_backend()

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        ready.set()
        for t in threads:
            t.join(timeout=5)

        assert calls["n"] == 1
        assert all(r is results[0] for r in results)

    async def test_warm_up_loads_the_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def _fake_load() -> StubEmbeddingBackend:
            calls["n"] += 1
            return StubEmbeddingBackend()

        monkeypatch.setattr(LocalStaticBackend, "load", staticmethod(_fake_load))

        await warm_up()

        assert calls["n"] == 1
        assert get_embedding_backend() is not None

    async def test_warm_up_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def _fake_load() -> StubEmbeddingBackend:
            calls["n"] += 1
            return StubEmbeddingBackend()

        monkeypatch.setattr(LocalStaticBackend, "load", staticmethod(_fake_load))

        await warm_up()
        await warm_up()

        assert calls["n"] == 1

    async def test_warm_up_swallows_loader_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _explode() -> StubEmbeddingBackend:
            raise EmbeddingModelMissingError("simulated missing weights")

        monkeypatch.setattr(LocalStaticBackend, "load", staticmethod(_explode))

        await warm_up()  # must not raise

        with pytest.raises(EmbeddingModelMissingError):
            get_embedding_backend()

    async def test_schedule_warm_up_holds_the_task_handle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Squawk 0055: ``schedule_warm_up()`` must hold a reference to the
        task it creates (in ``embeddings._tasks``) until it completes, and
        discard it once done — an unreferenced ``asyncio.create_task()``
        result can be garbage-collected mid-flight per the stdlib docs.
        """
        calls = {"n": 0}

        def _fake_load() -> StubEmbeddingBackend:
            calls["n"] += 1
            return StubEmbeddingBackend()

        monkeypatch.setattr(LocalStaticBackend, "load", staticmethod(_fake_load))

        task = schedule_warm_up()
        assert task in embeddings._tasks

        await task

        assert calls["n"] == 1
        assert task not in embeddings._tasks
