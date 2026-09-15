"""Production embedding backend: the bundled ``potion-retrieval-32M`` static
model (M24 F02 L03, DD-1).

Canonical home of the constants and offline-load guards Flight 1's ``doctor``
probe introduced (``the_one/diagnostics.py``, now retargeted here) and of
:class:`LocalStaticBackend`, the seam's one production implementation. The
guards move here so they protect every production load, not only the probe —
the probe (``the_one.diagnostics._probe_embedding_model``) now constructs a
**fresh** ``LocalStaticBackend`` and calls it rather than duplicating the load
path.

Three places must still agree on the packaged directory: ``pyproject.toml``'s
package-data glob, ``packaging/windows/the-one.spec``'s ``collect_data_files``
entry, and :data:`EMBEDDING_MODEL_DIRNAME` here (used via
``importlib.resources.files(EMBEDDING_PACKAGE)``).

Per the ``probe-must-not-pass-by-download`` convention, :func:`resolve_model_dir`
is INCAPABLE of passing by network fetch: it asserts the packaged directory and
weights file exist BEFORE any loader call, and :func:`force_hf_offline` sets
both the env var and the already-bound ``huggingface_hub.constants`` attribute
so a hub fetch cannot succeed even if the existence checks were bypassed.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from importlib.resources import files as _resource_files

import numpy as np

from the_one.embeddings._backend import EmbeddingModelMissingError, EmbedResult

EMBEDDING_PACKAGE = "the_one.embeddings"
EMBEDDING_MODEL_DIRNAME = "potion-retrieval-32M"
EMBEDDING_WEIGHTS_FILENAME = "model.safetensors"
# DD-1: potion-retrieval-32M is a 512-dimension model.
EMBEDDING_DIM = 512
# DD-1: model2vec's `encode()` defaults to max_length=512; the backend passes
# this explicitly rather than relying on the default, and reuses it as the
# character-length pre-filter for the truncation-count second pass (a text of
# <= MAX_TOKENS characters cannot exceed MAX_TOKENS tokens).
MAX_TOKENS = 512


def force_hf_offline() -> None:
    """Make a Hugging Face hub fetch impossible for the rest of this process.

    Setting the environment variable is not sufficient on its own:
    ``huggingface_hub.constants.HF_HUB_OFFLINE`` is evaluated ONCE at import
    time, so if anything has already imported the package the variable is
    read too late. Both are therefore set — the env var for the
    not-yet-imported case (the normal one, since model2vec is imported
    lazily), and the already-bound constant for the case where it is not.
    """
    os.environ["HF_HUB_OFFLINE"] = "1"
    constants = sys.modules.get("huggingface_hub.constants")
    if constants is not None:
        constants.HF_HUB_OFFLINE = True


def resolve_model_dir() -> tuple[object, int]:
    """Resolve and validate the packaged model directory.

    Returns ``(model_dir, weights_bytes)`` where ``model_dir`` is the
    ``importlib.resources`` traversable path and ``weights_bytes`` is the
    on-disk size of :data:`EMBEDDING_WEIGHTS_FILENAME`.

    Raises :class:`EmbeddingModelMissingError` — and never reaches
    ``from_pretrained`` — when either guard fails:

    - **Guard #1**: the packaged directory does not exist (a missing or
      tree-shaken package-data glob).
    - **Guard #2**: the directory exists but ``model.safetensors`` is
      absent (a partial glob / truncated asset).

    Forces the process offline (:func:`force_hf_offline`) BEFORE returning,
    so the ``model2vec`` import that follows binds
    ``huggingface_hub.constants.HF_HUB_OFFLINE`` already set.
    """
    model_dir = _resource_files(EMBEDDING_PACKAGE).joinpath("data", EMBEDDING_MODEL_DIRNAME)
    resolved = str(model_dir)

    if not model_dir.is_dir():
        raise EmbeddingModelMissingError(
            f"packaged model directory not found at {resolved} — the "
            f"embeddings/data/**/* package-data glob (pyproject.toml) or the "
            f"collect_data_files entry (the-one.spec) did not ship it"
        )
    weights = model_dir.joinpath(EMBEDDING_WEIGHTS_FILENAME)
    if not weights.is_file():
        raise EmbeddingModelMissingError(
            f"{EMBEDDING_WEIGHTS_FILENAME} missing from {resolved} — model2vec's "
            "loader validates the five-file layout, so a partial glob fails here"
        )
    weights_bytes = weights.stat().st_size

    force_hf_offline()
    return model_dir, weights_bytes


class LocalStaticBackend:
    """Production :class:`~the_one.embeddings._backend.EmbeddingBackend`:
    the bundled float16 ``potion-retrieval-32M`` model, wrapped at the
    seam boundary as ``float32``.

    Satisfies the Protocol structurally (``structural-Protocol-satisfaction``)
    — this class does not inherit from it.
    """

    def __init__(
        self,
        *,
        model: object,
        model_id: str,
        dim: int,
        native_dtype: str,
        weights_bytes: int,
        model_dir: str,
    ) -> None:
        self._model = model
        self.model_id = model_id
        self.dim = dim
        self.native_dtype = native_dtype
        self.weights_bytes = weights_bytes
        self.model_dir = model_dir

    @classmethod
    def load(cls) -> LocalStaticBackend:
        """Resolve the packaged directory (raising ``EmbeddingModelMissingError``
        per the two DD-5 guards) and load the model via model2vec."""
        model_dir, weights_bytes = resolve_model_dir()

        from model2vec import StaticModel

        try:
            model = StaticModel.from_pretrained(str(model_dir))
        except Exception as exc:
            # The two guards above already proved the directory and weights
            # file exist, so a failure here is a genuine load error (a
            # corrupt or unreadable weights file) rather than a missing
            # asset — re-raised with the same path/size context the caller
            # (the doctor probe) would otherwise have no way to attach,
            # since this method does not return partial state on failure.
            raise RuntimeError(
                f"{exc.__class__.__name__}: {exc} (path={model_dir}, "
                f"{EMBEDDING_WEIGHTS_FILENAME}={weights_bytes:,} bytes)"
            ) from exc
        return cls(
            model=model,
            model_id=EMBEDDING_MODEL_DIRNAME,
            dim=model.dim,
            native_dtype=str(model.embedding.dtype),
            weights_bytes=weights_bytes,
            model_dir=str(model_dir),
        )

    def embed(self, texts: Sequence[str]) -> EmbedResult:
        """Synchronous, CPU-bound. Callers run this under ``asyncio.to_thread``.

        ``use_multiprocessing=False`` (R20): model2vec's default spawns a
        process pool above 10,000 texts, which is a hazard inside a uvicorn
        worker or a PyInstaller bundle. The model already L2-normalises its
        output — this method does not re-normalise; a norm outside
        tolerance is a defect to surface (the doctor probe does), not to
        hide here.
        """
        texts = list(texts)
        if not texts:
            return EmbedResult(np.zeros((0, self.dim), dtype=np.float32), 0)

        # A text of <= MAX_TOKENS characters cannot exceed MAX_TOKENS
        # tokens, so the second tokenisation pass (measured at ~27% of
        # embed wall time) is skipped entirely for short-input batches.
        long_texts = [t for t in texts if len(t) > MAX_TOKENS]
        if long_texts:
            token_ids = self._model.tokenize(long_texts, max_length=None)
            truncated = sum(1 for ids in token_ids if len(ids) > MAX_TOKENS)
        else:
            truncated = 0

        vectors = self._model.encode(
            texts,
            use_multiprocessing=False,
            max_length=MAX_TOKENS,
            show_progress_bar=False,
        )
        vectors = np.asarray(vectors, dtype=np.float32).reshape(len(texts), self.dim)
        return EmbedResult(vectors, truncated)
