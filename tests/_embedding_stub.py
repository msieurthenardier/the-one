"""Test-only ``EmbeddingBackend`` implementation (M24 F02 L03, DD-1).

The seam's second implementation, mirroring the ``FakeLLM`` / ``StubTool``
precedent in ``tests/conftest.py``: every seam consumer's unit test runs
against this instead of the real ~62 MiB ``LocalStaticBackend`` load. What
keeps the seam honest — a Protocol satisfied by exactly one production shape
is not really a seam — is that this class never imports or touches
``model2vec``.

Deterministic: the vector for a given text is derived from a stable hash of
the text (``hashlib.sha256``), seeded into ``numpy``'s PCG64 generator, so
the same text always yields the same vector across instances and processes —
``StubEmbeddingBackend()`` and a fresh process both agree, which is what lets
a test assert on ranking/ordering without pinning literal float values.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import numpy as np

from the_one.embeddings._backend import EmbedResult

STUB_MODEL_ID = "stub-embedding-backend"


class StubEmbeddingBackend:
    """Deterministic, hash-seeded unit vectors. Satisfies
    :class:`the_one.embeddings.EmbeddingBackend` structurally.

    ``dim`` defaults to 8 (small, fast, distinct from the real model's 512
    so a test that accidentally used the real dim would still be legible).
    When ``truncate_over_chars`` is set, any input longer than that many
    characters counts toward ``EmbedResult.truncated`` — a cheap stand-in
    for the real backend's token-based truncation count, useful for tests
    that only need to exercise the "some inputs were truncated" path.
    """

    def __init__(self, dim: int = 8, truncate_over_chars: int | None = None) -> None:
        self.model_id = STUB_MODEL_ID
        self.dim = dim
        self._truncate_over_chars = truncate_over_chars

    def embed(self, texts: Sequence[str]) -> EmbedResult:
        texts = list(texts)
        if not texts:
            return EmbedResult(np.zeros((0, self.dim), dtype=np.float32), 0)

        rows = [self._vector_for(text) for text in texts]
        vectors = np.stack(rows).astype(np.float32)

        if self._truncate_over_chars is None:
            truncated = 0
        else:
            truncated = sum(1 for t in texts if len(t) > self._truncate_over_chars)

        return EmbedResult(vectors, truncated)

    def _vector_for(self, text: str) -> np.ndarray:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        seed = int(digest, 16)
        rng = np.random.default_rng(seed)
        vector = rng.standard_normal(self.dim)
        norm = np.linalg.norm(vector)
        if norm == 0.0:  # pragma: no cover — astronomically unlikely for standard_normal
            vector[0] = 1.0
            norm = 1.0
        return (vector / norm).astype(np.float32)
