"""Regenerate the bundled float16 ``potion-retrieval-32M`` embedding model.

This script is invoked by ``make refresh-embedding-model``, which runs it
host-native against the repo venv.  It downloads ``minishlab/potion-retrieval-32M``
from the Hugging Face hub once, quantizes the weights to float16 via model2vec's
own ``quantize_to`` parameter, writes the five-file model directory to
``the_one/embeddings/data/potion-retrieval-32M/``, and then **reloads that
directory from disk** to verify the artifact three ways before returning 0.

Why float16 (M24 F01 DD-1 / DD-2)
    The published ``model.safetensors`` is a single ``F32`` tensor of shape
    ``[63091, 512]`` — 129,210,456 bytes, over GitHub's hard 100 MiB per-blob
    limit and therefore a certain push rejection.  float16 halves the only
    payload exactly, to 64,605,272 bytes (61.61 MiB), which clears the limit on
    plain git: no LFS, no ``.gitattributes``, and no change to either CI
    checkout.  Static embeddings tolerate half precision well — see the
    correctness check below, which measures rather than assumes it.

Why ``quantize_to=`` and not a hand-rolled safetensors rewrite
    ``config.json`` carries an ``embedding_dtype`` field describing the tensors.
    Rewriting the safetensors file directly would leave that field free to
    disagree with what it describes.  Letting model2vec quantize keeps the two
    consistent by construction.

The committed unit is a DIRECTORY, not a file
    ``save_pretrained`` emits exactly five files — ``README.md``,
    ``config.json``, ``model.safetensors``, ``modules.json`` and
    ``tokenizer.json`` — and model2vec's loader validates that layout.  A
    partial ``pyproject.toml`` glob or ``collect_data_files`` include therefore
    fails at load rather than degrading silently.

Reproducibility contract
    Re-running against the same upstream revision reproduces the same bytes,
    **independently of the destination path**.  ``save_pretrained`` embeds the
    destination basename in ``README.md``'s front-matter, heading and code
    samples, so the explicit ``model_name=`` argument below pins that string to
    ``MODEL_NAME`` instead of letting it track ``--out``.  Without it, writing
    to a scratch directory and writing to the package directory produce
    different bytes for identical weights.

What the correctness check actually discriminates
    Cosine similarity between the fp32 and fp16 encodings is ~1.000000 to six
    decimals for a normalising static model, so a check framed as "does float16
    hurt quality" is a rubber stamp.  Worse, cosine is scale-invariant and
    ``modules.json`` adds a ``Normalize`` module, so a **wrong scale** also
    scores 1.000000, and a **wrong dtype** (quantization silently skipped, or
    applied as bfloat16/int8) scores ~1.0 as well.  So the check asserts three
    independent things:

    (a) **Dtype, directly** — ``config.json``'s ``embedding_dtype`` is
        ``float16`` *and* the safetensors header's own dtype is ``F16``.  This
        is what catches a skipped or mis-targeted quantization; the fp32 case
        would otherwise be caught only by the 100 MiB size gate, and int8 would
        slip both.
    (b) **Magnitude** — max and mean absolute value of the reloaded embedding
        matrix against upstream, within fp16 rounding tolerance.  This is what
        catches a rescale, which cosine cannot see.
    (c) **Semantic sanity** — mean cosine >= 0.9999, min >= 0.999 and
        recall@1 == 1.0 over the inline corpus below.  recall@1, not @10: at a
        ~40-string corpus, k=10 is a quarter of the corpus and would pass for a
        badly degraded model.

    All three compare against the directory **reloaded from disk**, not against
    the in-memory quantized object.  Comparing in-memory would test the
    quantizer and not the artifact, and a botched *write* (wrong layout, a
    subfolder slip) would pass.

Network
    Exactly one fetch.  The fp32 model is pulled once; the quantized load is
    served from the local hub cache (``force_download=False``); the verification
    reload runs under ``HF_HUB_OFFLINE=1`` against the absolute output path, so
    it cannot satisfy itself by downloading.

When to re-run
    Only when the upstream model or the target dtype changes.  The output is a
    62 MiB tracked binary; re-running for no reason writes a second copy of it
    into git history permanently.

Usage::

    python scripts/refresh_embedding_model.py
    python scripts/refresh_embedding_model.py --out /tmp/scratch-model
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from pathlib import Path

import numpy as np

# Upstream model id and the on-disk directory name.  MODEL_NAME is passed to
# save_pretrained explicitly so README.md's contents do not track --out; see the
# reproducibility contract above.
UPSTREAM_REPO = "minishlab/potion-retrieval-32M"
MODEL_NAME = "potion-retrieval-32M"

# The five files save_pretrained emits.  model2vec's loader validates this
# layout, so the packaging globs must cover all of them.
EXPECTED_FILES = (
    "README.md",
    "config.json",
    "model.safetensors",
    "modules.json",
    "tokenizer.json",
)

EXPECTED_DIM = 512

# GitHub rejects any single blob at or over 100 MiB.  The size gate is the whole
# basis of DD-2 and is checked here as well as by hand before `git add`.
GITHUB_BLOB_LIMIT = 100 * 1024 * 1024

# fp16 has an 11-bit significand, so the worst-case relative rounding error on a
# single value is 2**-11 ~= 4.9e-4.  1e-3 gives one bit of headroom on aggregate
# statistics while still failing hard on a rescale (which moves these by orders
# of magnitude, not by parts per thousand).
FP16_REL_TOL = 1e-3

# Quality floors — see (c) in the module docstring.
MIN_MEAN_COSINE = 0.9999
MIN_MIN_COSINE = 0.999

# Paths resolved repo-relative from this file's location.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUT = _REPO_ROOT / "the_one" / "embeddings" / "data" / MODEL_NAME

# Verification corpus: 40 short strings, deliberately spread across several
# topics so recall@1 is a real question rather than a formality.  Committed
# inline (not read from a file) so the check travels with the script.
SAMPLE_TEXTS: tuple[str, ...] = (
    "how do I reset my password",
    "the deployment pipeline failed on the windows worker",
    "recipe for sourdough starter maintenance",
    "quarterly revenue grew twelve percent year over year",
    "the cat knocked the mug off the table again",
    "install the latest nvidia driver on ubuntu",
    "meeting notes from the tuesday architecture review",
    "symptoms of vitamin d deficiency in adults",
    "python asyncio event loop already running error",
    "best hiking trails near the north cascades",
    "how to renew a expired passport by mail",
    "sqlite write-ahead logging and crash consistency",
    "the flight was delayed four hours in reykjavik",
    "tax deduction rules for a home office",
    "explain gradient descent to a beginner",
    "chord progression for a twelve bar blues",
    "why is my sourdough loaf so dense",
    "kubernetes pod stuck in crashloopbackoff",
    "history of the transcontinental railroad",
    "convert a pdf to markdown on the command line",
    "signs that a used car has flood damage",
    "difference between a mutex and a semaphore",
    "how long to roast a whole chicken",
    "the treaty of westphalia and state sovereignty",
    "regular expression to match an email address",
    "training plan for a first half marathon",
    "what causes the northern lights",
    "git rebase versus git merge tradeoffs",
    "how to prune an overgrown apple tree",
    "the economics of rent control in cities",
    "debug a memory leak in a node process",
    "identify a bird by its song in the morning",
    "setting up two factor authentication",
    "the chemistry of caramelization versus maillard",
    "typescript generic constraints explained",
    "how tides work and why there are two a day",
    "restore a deleted branch from the reflog",
    "insulating an attic in a cold climate",
    "the rules of offside in association football",
    "compress a video without losing much quality",
)


def _safetensors_header(path: Path) -> dict:
    """Read the JSON header of a safetensors file without loading the tensors.

    The format is an 8-byte little-endian header length followed by that many
    bytes of UTF-8 JSON.  Reading it directly is how the dtype recorded in the
    file itself — as opposed to the dtype ``config.json`` claims — is checked.
    """
    with path.open("rb") as fh:
        (header_len,) = struct.unpack("<Q", fh.read(8))
        return json.loads(fh.read(header_len).decode("utf-8"))


def _cosine_stats(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Return (mean, min) row-wise cosine similarity between two matrices."""
    a64 = np.asarray(a, dtype=np.float64)
    b64 = np.asarray(b, dtype=np.float64)
    a_norm = a64 / np.linalg.norm(a64, axis=1, keepdims=True)
    b_norm = b64 / np.linalg.norm(b64, axis=1, keepdims=True)
    sims = np.sum(a_norm * b_norm, axis=1)
    return float(sims.mean()), float(sims.min())


def _recall_at_1(query: np.ndarray, corpus: np.ndarray) -> float:
    """Fraction of rows whose nearest corpus neighbour is its own index.

    ``query`` is the fp16 encoding, ``corpus`` the fp32 one.  A perfect score
    means quantization never moved a text closer to a *different* text than to
    itself — the property retrieval actually depends on.
    """
    q = np.asarray(query, dtype=np.float64)
    c = np.asarray(corpus, dtype=np.float64)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    c /= np.linalg.norm(c, axis=1, keepdims=True)
    nearest = np.argmax(q @ c.T, axis=1)
    return float((nearest == np.arange(len(q))).mean())


def verify(out_path: Path, upstream_matrix: np.ndarray, upstream_vectors: np.ndarray) -> list[str]:
    """Reload the written directory and check it three ways.

    Returns a list of breach descriptions; an empty list means the artifact is
    good.  Everything here is measured against the reloaded-from-disk model, so
    a bad *write* fails just as loudly as a bad quantization.
    """
    from model2vec import StaticModel

    breaches: list[str] = []

    # Layout first — a missing file makes every later check meaningless.
    missing = [name for name in EXPECTED_FILES if not (out_path / name).is_file()]
    if missing:
        return [f"model directory is missing {missing} (expected exactly {list(EXPECTED_FILES)})"]
    extra = sorted(p.name for p in out_path.iterdir() if p.name not in EXPECTED_FILES)
    if extra:
        breaches.append(f"unexpected extra files in the model directory: {extra}")

    # (a) Dtype, from both places that record it.
    config = json.loads((out_path / "config.json").read_text(encoding="utf-8"))
    config_dtype = config.get("embedding_dtype")
    if config_dtype != "float16":
        breaches.append(f"config.json embedding_dtype is {config_dtype!r}, expected 'float16'")

    header = _safetensors_header(out_path / "model.safetensors")
    tensor_names = [k for k in header if k != "__metadata__"]
    header_dtypes = {name: header[name].get("dtype") for name in tensor_names}
    if set(header_dtypes.values()) != {"F16"}:
        breaches.append(f"safetensors header dtypes are {header_dtypes}, expected every tensor F16")

    # Size gate — DD-2's whole basis.  Checked here as well as by hand.
    weights_bytes = (out_path / "model.safetensors").stat().st_size
    if weights_bytes >= GITHUB_BLOB_LIMIT:
        breaches.append(
            f"model.safetensors is {weights_bytes:,} bytes (>= GitHub's {GITHUB_BLOB_LIMIT:,}-byte "
            "per-blob limit) — DD-2 is invalidated; stop and report"
        )

    # Reload from disk, offline.  HF_HUB_OFFLINE makes a download impossible, so
    # a directory that failed to write cannot be papered over by a hub fetch.
    os.environ["HF_HUB_OFFLINE"] = "1"
    reloaded = StaticModel.from_pretrained(str(out_path.resolve()))

    if reloaded.dim != EXPECTED_DIM:
        breaches.append(f"reloaded model dim is {reloaded.dim}, expected {EXPECTED_DIM}")

    reloaded_matrix = np.asarray(reloaded.embedding)
    if reloaded_matrix.shape != upstream_matrix.shape:
        breaches.append(
            f"reloaded embedding shape {reloaded_matrix.shape} != upstream {upstream_matrix.shape}"
        )
        return breaches

    # (b) Magnitude — the rescale check cosine cannot perform.
    up_abs = np.abs(np.asarray(upstream_matrix, dtype=np.float64))
    re_abs = np.abs(np.asarray(reloaded_matrix, dtype=np.float64))
    up_max, re_max = float(up_abs.max()), float(re_abs.max())
    up_mean, re_mean = float(up_abs.mean()), float(re_abs.mean())
    if not np.isclose(re_max, up_max, rtol=FP16_REL_TOL, atol=0.0):
        breaches.append(
            f"max |embedding| drifted: upstream {up_max:.8f} vs reloaded {re_max:.8f} "
            f"(rtol {FP16_REL_TOL}) — the weights have been rescaled, not merely rounded"
        )
    if not np.isclose(re_mean, up_mean, rtol=FP16_REL_TOL, atol=0.0):
        breaches.append(
            f"mean |embedding| drifted: upstream {up_mean:.8f} vs reloaded {re_mean:.8f} "
            f"(rtol {FP16_REL_TOL}) — the weights have been rescaled, not merely rounded"
        )

    # (c) Semantic sanity against the committed corpus.
    reloaded_vectors = np.asarray(reloaded.encode(list(SAMPLE_TEXTS)))
    mean_cos, min_cos = _cosine_stats(reloaded_vectors, upstream_vectors)
    recall1 = _recall_at_1(reloaded_vectors, upstream_vectors)
    if mean_cos < MIN_MEAN_COSINE:
        breaches.append(f"mean cosine {mean_cos:.6f} < {MIN_MEAN_COSINE}")
    if min_cos < MIN_MIN_COSINE:
        breaches.append(f"min cosine {min_cos:.6f} < {MIN_MIN_COSINE}")
    if recall1 != 1.0:
        breaches.append(f"recall@1 {recall1:.4f} != 1.0")

    print("  verification:")
    print(f"    config.json embedding_dtype : {config_dtype}")
    print(f"    safetensors header dtypes   : {header_dtypes}")
    print(f"    reloaded dim                : {reloaded.dim}")
    print(f"    max |embedding|             : upstream {up_max:.8f} / reloaded {re_max:.8f}")
    print(f"    mean |embedding|            : upstream {up_mean:.8f} / reloaded {re_mean:.8f}")
    print(
        f"    cosine over {len(SAMPLE_TEXTS)} texts        : "
        f"mean {mean_cos:.6f} / min {min_cos:.6f}"
    )
    print(f"    recall@1                    : {recall1:.4f}")
    return breaches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_OUT,
        help=f"Output directory for the model (default: {_DEFAULT_OUT})",
    )
    parser.add_argument(
        "--repo",
        default=UPSTREAM_REPO,
        help=f"Upstream Hugging Face model id (default: {UPSTREAM_REPO})",
    )
    args = parser.parse_args(argv)

    from model2vec import StaticModel

    # One network fetch: the fp32 model.  The quantized load below reads the
    # same hub cache (force_download=False), so nothing is downloaded twice.
    print(f"Fetching {args.repo} (float32) …")
    try:
        upstream = StaticModel.from_pretrained(args.repo)
    except Exception as exc:  # noqa: BLE001 — the message is the whole diagnostic
        print(f"ERROR: fetch failed — {exc}", file=sys.stderr)
        print(
            "Hint: this script needs network access exactly once. Ensure HF_HUB_OFFLINE "
            "is not set in your environment.",
            file=sys.stderr,
        )
        return 1

    upstream_matrix = np.array(upstream.embedding, dtype=np.float32, copy=True)
    upstream_vectors = np.asarray(upstream.encode(list(SAMPLE_TEXTS)))
    print(f"  upstream embedding: shape {upstream_matrix.shape}, dtype {upstream_matrix.dtype}")

    print("Quantizing to float16 …")
    quantized = StaticModel.from_pretrained(args.repo, quantize_to="float16", force_download=False)

    out_path: Path = args.out
    print(f"Writing {out_path} (model_name={MODEL_NAME!r}) …")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    quantized.save_pretrained(out_path, model_name=MODEL_NAME)

    total = 0
    for name in sorted(p.name for p in out_path.iterdir()):
        size = (out_path / name).stat().st_size
        total += size
        print(f"    {name:<20} {size:>12,} bytes")
    print(f"    {'TOTAL':<20} {total:>12,} bytes ({total / 1024 / 1024:.2f} MiB)")

    breaches = verify(out_path, upstream_matrix, upstream_vectors)
    if breaches:
        print("", file=sys.stderr)
        print("ERROR: conversion-correctness check failed:", file=sys.stderr)
        for breach in breaches:
            print(f"  - {breach}", file=sys.stderr)
        return 1

    print("")
    print(f"OK — {out_path} verified ({len(EXPECTED_FILES)} files, {total:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
