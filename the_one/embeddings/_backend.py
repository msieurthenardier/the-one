"""The embedding seam: a structural Protocol, its result shape, and its
missing-model error (M24 F02 L03, DD-1).

Two implementations satisfy :class:`EmbeddingBackend` today:
``the_one.embeddings.local.LocalStaticBackend`` (production, the bundled
``potion-retrieval-32M`` model) and ``tests._embedding_stub.StubEmbeddingBackend``
(test-only, deterministic hash-seeded vectors). Both satisfy the Protocol
*structurally* — neither inherits from it — per the
``structural-Protocol-satisfaction`` convention (``the_one/agents.md``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

# DD-1: float16 output upcast to float32 measures max |1 - ||v|| | = 1.83e-4 on
# the bundled model. "Unit-norm" anywhere in this seam's contract means within
# this tolerance, never exact.
NORM_TOLERANCE = 1e-3


@dataclass(frozen=True)
class EmbedResult:
    """The output of one :meth:`EmbeddingBackend.embed` call.

    ``vectors``: ``float32``, shape ``(len(texts), dim)``, unit-norm within
    :data:`NORM_TOLERANCE`. ``truncated``: the count of inputs the tokenizer
    cut at the backend's max token length (DD-1) — model2vec's ``encode()``
    returns vectors only, so a backend that wants this count runs a second
    tokenisation pass; it is exposed here so a caller (Flight 3's ingest
    pipeline) can log which chunks were embedded from a truncated view of
    their text rather than silently lose the information.
    """

    vectors: np.ndarray
    truncated: int


class EmbeddingModelMissingError(RuntimeError):
    """Raised when the backend's model cannot be resolved on disk.

    Never raised for a network failure — see
    ``the_one.embeddings.local.resolve_model_dir`` and the
    ``probe-must-not-pass-by-download`` convention: this error exists so a
    missing or partial packaged asset fails loudly and locally instead of
    falling through to a hub fetch.
    """


@runtime_checkable
class EmbeddingBackend(Protocol):
    """Structural contract every embedding backend satisfies.

    - ``model_id``: a stable identifier for the loaded model.
    - ``dim``: the embedding width.
    - ``embed(texts)``: synchronous and CPU-bound — callers run it under
      ``asyncio.to_thread``, never await it directly. Returns an
      :class:`EmbedResult` whose ``vectors`` are ``float32``, shape
      ``(len(texts), dim)``, and unit-norm within :data:`NORM_TOLERANCE`
      for any input that yields at least one token. A text that tokenises
      to zero ids (e.g. a very long run of a single unsupported character)
      yields a zero-norm row rather than a unit-norm one — passed through
      as-is, never hidden; callers that care about that edge (Flight 3's
      ingest pipeline) filter on vector norm themselves.

    Implementations MUST NOT inherit from this Protocol — satisfaction is
    structural (``structural-Protocol-satisfaction``); ``isinstance(obj,
    EmbeddingBackend)`` works via ``@runtime_checkable`` regardless.
    """

    model_id: str
    dim: int

    def embed(self, texts: Sequence[str]) -> EmbedResult: ...
