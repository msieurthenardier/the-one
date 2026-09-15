# Leg: embedding-seam-and-settings

**Status**: completed
**Flight**: [Storage and Embedding Foundation](../flight.md)

## Objective

Land the embedding seam — a Protocol, the bundled-model production backend
carrying Flight 1's offline guards, a process singleton with a KB-gated
warm-up, and a test-only second implementation — together with the
deterministic chunker and the two app-wide knowledge settings records behind
`GET`/`PUT /api/knowledge-settings`, and rewrite the `doctor` embedding probe
to call the backend instead of duplicating its load path.

## Context

- Flight DD-1 (seam shape, `EmbedResult.truncated` and how it is computed,
  the 1e-3 norm tolerance, `use_multiprocessing=False`, fresh backend in the
  probe, singleton + reset, warm-up gated on "any KB exists" and kicked by KB
  creation), DD-2 (one valid backend, one valid `model_id`; 422 otherwise),
  DD-6 (two `app_metadata` JSON records, defaults on read, route prefix
  `/api/knowledge-settings`, chunking changes apply to future indexing only),
  DD-7 (chunker policy and defaults), DD-11 (the probe's new detail line and
  the three test changes).
- Depends only on Leg 1 (landed) for the DB layer and on Leg 2's
  `ChunkRecord` shape (`the_one/db/_kb_types.py`, frozen dataclass `seq,
  text, char_start, char_end`) as the chunker's output type. Nothing here
  touches `the_one/vectors` (Leg 4) or the CI lanes (Leg 2 already added the
  `fts5` assertion; the embedding probe's `embedding model: OK` grep is
  unchanged by this leg).
- Empirical facts from planning and design review, verified on this host:
  `StaticModel.encode(…)` defaults `use_multiprocessing=True` above 10,000
  texts and `max_length=512`; `StaticModel.tokenize(sentences,
  max_length=None) -> list[list[int]]` returns uncapped token ids (a 6,000-
  char text tokenised to 3,000 ids, capped to 512 with `max_length=512`);
  the model's `embedding.dtype` is `float16`, `median_token_length` is 7;
  float16 output upcast to float32 has max |1 − ‖v‖| = 1.83e-4; `tokenize`
  and `encode` never mutate tokenizer state (thread-safe under
  `asyncio.to_thread`). No `hypothesis` in the dev extra — the chunker's
  determinism test uses a seeded generated corpus.

## Inputs

- `the_one/diagnostics.py:622-629` (`_EMBEDDING_PACKAGE`,
  `_EMBEDDING_MODEL_DIRNAME`, `_EMBEDDING_WEIGHTS_FILENAME`, `_EMBEDDING_DIM`,
  `_EMBEDDING_PROBE_TEXT`), `:712-725` (`_force_hf_offline`), `:728-838`
  (`_probe_embedding_model` — the two DD-5 guards, the load + encode, the
  detail line; `run_doctor` now starts at `:840`).
- `the_one/embeddings/__init__.py` — docstring-only, says "No seam lives
  here (DD-6)"; `the_one/embeddings/data/potion-retrieval-32M/` (five files).
- `packaging/windows/the-one.spec:245-254` — the `"the_one.embeddings"`
  hiddenimports comment ("NOTHING imports `the_one.embeddings` as a module").
- `tests/test_doctor_embedding_model.py` — `TestRealLoad` (`:44`; `:58`
  asserts `"float16 vector" in result.detail`), `TestOfflineInvariant`
  (`:84`; `:112` monkeypatches `diagnostics._EMBEDDING_MODEL_DIRNAME`;
  `:135-147` the `_StubModel` whose `encode(text: str) -> list[float]`
  accepts no kwargs), `TestPeakRss*` (unchanged).
- `tests/test_doctor.py:48-60` — the autouse fixture that stubs
  `_probe_embedding_model` for every `run_doctor` call; `TestEmbeddingProbeGating`
  (`:816`; its source-inspection test `test_does_not_use_the_frozen_only_helper`
  at `:852-863` — line 727 now falls inside Leg 2's `TestProbeFts5`).
- `the_one/db/repositories.py` — `AppMetadataRepository` (`get`/`set`,
  `set` inside `write_transaction`), `KnowledgeBaseRepository` (no `count`
  today; `count_by_status` at `:542` is the item repo's).
- `the_one/interfaces/web/app.py:244-262` (the `create_task` loop block)
  and `:314-326` (the guarded `ConnectorManager` start; the warm-up goes
  after it); `the_one/interfaces/web/api.py:1390-1396` (`create_knowledge_base`),
  `:1400-1417` (`update_knowledge_base`, the merge-then-revalidate PUT
  precedent), `:350` (`/config`, the read-only client-config precedent).
- `tests/conftest.py` — `FakeLLM` / `StubTool` (the stub precedent);
  `tests/test_lifespan.py` (`:104`, `:133`, `:168` — the lifespan test
  shapes with `_isolated_data_dir`).
- `the_one/platform/sandbox/factory.py:52-72` — `_reset_selection_log_state`
  (the reset-seam precedent).
- `the_one/agents.md` — `### Diagnostics` section (the `embedding model`
  row and the probe-contract paragraph), the `### Knowledge storage`
  subsection Leg 2 creates.

## Outputs

- `the_one/embeddings/_backend.py` (new): `EmbedResult` (frozen dataclass:
  `vectors: np.ndarray`, `truncated: int`), `EmbeddingBackend`
  (`@runtime_checkable` Protocol: `model_id: str`, `dim: int`,
  `embed(texts: Sequence[str]) -> EmbedResult`), `NORM_TOLERANCE = 1e-3`,
  `EmbeddingModelMissingError(RuntimeError)`.
- `the_one/embeddings/local.py` (new): the canonical home of
  `EMBEDDING_PACKAGE`, `EMBEDDING_MODEL_DIRNAME`, `EMBEDDING_WEIGHTS_FILENAME`,
  `EMBEDDING_DIM`, `MAX_TOKENS = 512`, `force_hf_offline()`,
  `resolve_model_dir() -> tuple[Path-like, int]` (the two DD-5 guards;
  raises `EmbeddingModelMissingError` with the probe's current messages),
  `class LocalStaticBackend` with `model_id`, `dim`, `native_dtype: str`,
  `weights_bytes: int`, `model_dir: str`, classmethod `load()`, and
  `embed()`.
- `the_one/embeddings/__init__.py`: rewritten docstring (the seam lives
  here now; the three-places-agree note stays), re-exports,
  `get_embedding_backend() -> EmbeddingBackend`, `async warm_up() -> None`,
  `_reset_for_test()`.
- `the_one/knowledge/__init__.py`, `settings.py` (new):
  `EmbeddingSettings`, `ChunkingSettings`, `KnowledgeSettings` (Pydantic),
  `EMBEDDING_KEY = "knowledge.embedding"`, `CHUNKING_KEY =
  "knowledge.chunking"`, `async load_knowledge_settings(conn) ->
  KnowledgeSettings`, `async save_knowledge_settings(conn, settings)`.
- `the_one/knowledge/chunking.py` (new): `chunk_text(text, *, size_chars,
  overlap_chars) -> list[ChunkRecord]`.
- `the_one/diagnostics.py`: `_probe_embedding_model` rewritten to
  `LocalStaticBackend.load()` + `embed([...])`; the five underscored
  constants and `_force_hf_offline` are **removed** from `diagnostics.py`
  (nothing outside it and the one test file imports them — design review
  verified); the probe imports the plain names from
  `the_one.embeddings.local`; new detail line per DD-11.
- `the_one/db/repositories.py`: `KnowledgeBaseRepository.count() -> int`.
- `the_one/interfaces/web/api.py`: `# ── Knowledge settings ──` banner,
  `GET /knowledge-settings`, `PUT /knowledge-settings`;
  `create_knowledge_base` schedules `warm_up()`.
- `the_one/interfaces/web/app.py`: warm-up task after the connector-manager
  block, gated on `KnowledgeBaseRepository.count() > 0`, in its own
  `try/except` like its neighbours.
- `packaging/windows/the-one.spec:245-254`: comment rewritten (the package
  is now imported as a module; the hiddenimports entry stays because
  `importlib.resources.files` is still how the data dir is reached).
- `tests/_embedding_stub.py` (new): `StubEmbeddingBackend(dim=8,
  truncate_over_chars=None)`.
- Tests: `tests/test_embeddings.py`, `tests/test_knowledge_settings.py`,
  `tests/test_chunking.py` (new); `tests/test_doctor_embedding_model.py`
  updated per DD-11; `tests/test_lifespan.py` + `tests/test_db_api.py`
  additions.
- `the_one/agents.md`: Diagnostics section updated for the rewritten probe;
  `### Knowledge storage` gains the seam, the settings keys, the chunker.
- Flight log entry; leg ticked in `flight.md`.

## Acceptance Criteria

- [x] AC-1 `isinstance(LocalStaticBackend.load(), EmbeddingBackend)` and
      `isinstance(StubEmbeddingBackend(), EmbeddingBackend)` are both `True`
      (structural satisfaction, no inheritance); the stub returns identical
      vectors for identical inputs across instances and processes-worth of
      calls (seeded by a stable hash of the text), unit-norm within 1e-6,
      shape `(n, dim)`, `float32`.
- [x] AC-2 `LocalStaticBackend.embed(["a", "b"])` returns `vectors` of shape
      `(2, 512)`, dtype `float32`, every row's norm within `1e-3` of 1.0, and
      `truncated == 0`; for one input of 6,000 characters `truncated == 1`
      and the vector is still unit-norm. `encode` is called with
      `use_multiprocessing=False`, `max_length=512`, `show_progress_bar=False`
      (asserted by a stub model capturing kwargs). The truncation count
      comes from `tokenize(max_length=None)` applied only to inputs longer
      than 512 characters (asserted by a stub whose `tokenize` records what
      it was given).
- [x] AC-3 `resolve_model_dir()` raises `EmbeddingModelMissingError` — and
      `from_pretrained` is never reached — when the packaged directory is
      absent (the existing `test_missing_packaged_directory_fails_rather_than_downloading`,
      retargeted to `the_one.embeddings.local`) **and** when the directory
      exists but `model.safetensors` is absent (a **new** test: point
      `EMBEDDING_MODEL_DIRNAME` at a `tmp_path` directory holding the other
      four files — design review found guard #2 has no test anywhere in the
      tree today); `force_hf_offline()`
      sets both the env var and the already-imported constant (existing
      test, retargeted).
- [x] AC-4 `get_embedding_backend()` returns the same object on repeated
      calls; `_reset_for_test()` makes the next call build a new one; the
      loader is invoked at most once across concurrent first calls.
- [x] AC-5 Warm-up: at lifespan startup with zero knowledge bases the loader
      is not called; with one KB it is called exactly once, under
      `asyncio.to_thread`, after `ConnectorManager.start_all`; `POST
      /api/knowledge-bases` on a cold process kicks it exactly once and a
      second POST does not kick it again; a loader failure is logged and
      does not fail startup or the POST. (All with a monkeypatched loader —
      no real model load in these tests.)
- [x] AC-6 `_probe_embedding_model` constructs a fresh `LocalStaticBackend`
      (never `get_embedding_backend()`) and its detail on this host reads
      `512-dim float16 model → float32 seam, norm 1.0000, truncated=0
      (model.safetensors=64,605,272 bytes, peak RSS …) from …/potion-retrieval-32M`;
      `ok=False` with the same messages as today when the directory or
      weights are missing; never raises; `TestEmbeddingProbeGating`'s
      source-inspection test still passes; both CI lanes' `embedding model:
      OK` greps are unaffected; `tests/test_doctor_embedding_model.py`
      performs exactly the two real loads it performs today.
- [x] AC-7 `chunk_text`: for a seeded corpus of 200 generated texts (mixed
      paragraph lengths, long unbroken lines, CRLF, unicode), every chunk
      satisfies `text[char_start:char_end] == chunk.text`, `len(chunk.text)
      <= size_chars` unless the chunk is a single unbreakable run longer
      than `size_chars` (then it is split hard at `size_chars`), `seq` is
      `0..n-1` contiguous, consecutive chunks overlap by at most
      `overlap_chars` characters and by at least one character when the
      previous chunk was **full** (defined as `len(chunk.text) ==
      size_chars`, a hard cap hit — a window closed early by a paragraph
      boundary is not "full" and carries no overlap guarantee), chunk
      boundaries fall on paragraph or line
      or sentence boundaries when one exists within the window, an empty or
      whitespace-only text yields `[]`, and calling twice yields equal
      lists. Defaults are `size_chars=1000`, `overlap_chars=150`.
- [x] AC-8 `load_knowledge_settings` returns defaults on an empty
      `app_metadata`, the stored values when present, and defaults plus a
      logged warning when a stored value is invalid JSON or fails
      validation; `save_knowledge_settings` writes both keys and a
      round-trip is equal. Validation: `size_chars` outside 200–2000,
      `overlap_chars` above 50 % of `size_chars`, `backend != "local"`,
      `model_id != "potion-retrieval-32M"`, `dim != 512` each raise
      `ValidationError`.
- [x] AC-9 `GET /api/knowledge-settings` returns `{"embedding": {...},
      "chunking": {...}, "notes": [...]}` with defaults on a fresh DB; `PUT`
      with `{"chunking": {"size_chars": 800, "overlap_chars": 100}}` updates
      chunking only, leaves embedding unchanged, and a following `GET` shows
      it; `PUT` with an invalid value returns 422 and changes nothing; `PUT`
      with `{"embedding": {"backend": "ollama"}}` returns 422 whose detail
      names the mission amendment.
- [x] AC-10 `make test-unit` green with every seam-consumer test running
      against `StubEmbeddingBackend`; wall time within the band Leg 2
      established; ruff clean.

## Verification Steps

- AC-1–4: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_embeddings.py tests/test_doctor_embedding_model.py -x --timeout 120`.
- AC-5: `… tests/test_lifespan.py tests/test_db_api.py -x --timeout 120`.
- AC-6: `… tests/test_doctor.py tests/test_doctor_embedding_model.py -x
  --timeout 120`; `.venv/bin/the-one doctor` shows the new line;
  `grep -c "real load\|from_pretrained" tests/test_doctor_embedding_model.py`
  sanity-checks the load count (read the file; two tests load).
- AC-7: `… tests/test_chunking.py -x --timeout 60`.
- AC-8–9: `… tests/test_knowledge_settings.py tests/test_db_api.py -x --timeout 120`.
- AC-10: `make test-unit`; `ruff check the_one/ tests/`; `ruff format --check
  the_one/ tests/`.

## Implementation Guidance

1. **`_backend.py`.** `EmbedResult` frozen dataclass. `EmbeddingBackend`
   Protocol with a docstring stating the contract: `float32`, `(n, dim)`,
   unit-norm within `NORM_TOLERANCE` (float16 tolerance, ~2e-4 measured,
   never exact), sync and CPU-bound — callers use `asyncio.to_thread`.
   Structural per `structural-Protocol-satisfaction`; no ABC.

2. **`local.py`.** Move the five constants (drop the leading underscore).
   `diagnostics.py` imports the plain names it still uses
   (`EMBEDDING_DIM`, `EMBEDDING_WEIGHTS_FILENAME`) and drops the rest; the
   tests that monkeypatched `diagnostics._EMBEDDING_MODEL_DIRNAME` now
   monkeypatch `the_one.embeddings.local.EMBEDDING_MODEL_DIRNAME` (the
   backend reads it from there). No re-binding aliases. `resolve_model_dir()` performs guard #1 (directory
   exists) and guard #2 (weights file exists) and returns `(model_dir,
   weights_bytes)`; it calls `force_hf_offline()` **before** returning so
   the import that follows binds the constant offline. `LocalStaticBackend.load()`:
   `resolve_model_dir()` → `from model2vec import StaticModel` →
   `StaticModel.from_pretrained(str(model_dir))` → record `native_dtype =
   str(model.embedding.dtype)`, `dim = model.dim`, `model_id =
   EMBEDDING_MODEL_DIRNAME`. `embed(texts)`: `texts = list(texts)`; if empty
   return `EmbedResult(np.zeros((0, dim), np.float32), 0)`; `long = [t for
   t in texts if len(t) > MAX_TOKENS]`; `truncated = sum(len(ids) >
   MAX_TOKENS for ids in model.tokenize(long, max_length=None))` if `long`
   else 0; `vectors = model.encode(texts, use_multiprocessing=False,
   max_length=MAX_TOKENS, show_progress_bar=False)`; `np.asarray(vectors,
   dtype=np.float32)` reshaped to `(n, dim)`. Do not re-normalise. Add a
   `norms_ok()`-style helper only if a test needs it — the probe computes
   its own norm.

3. **`__init__.py`.** Module-level `_backend: EmbeddingBackend | None`,
   `_lock = threading.Lock()` (the loader runs in a worker thread and the
   singleton must be safe against two `to_thread` first-calls),
   `get_embedding_backend()` (double-checked under the lock; builds
   `LocalStaticBackend.load()` — the `knowledge.embedding` record has
   exactly one valid value per DD-2, so no dispatch yet; leave a one-line
   comment where a future backend would be chosen), `async warm_up()`
   (`if _backend is not None or _warming: return`; set `_warming`; `await
   asyncio.to_thread(get_embedding_backend)` in `try/except Exception:
   logger.exception(...)`; clear `_warming` in `finally`), `_reset_for_test()`.
   Rewrite the docstring: the seam lives here; keep the "three places must
   agree" paragraph.

4. **Probe rewrite** in `diagnostics.py`. Keep the function name and the
   `name = "embedding model"` string. Body: `try: backend =
   LocalStaticBackend.load() except EmbeddingModelMissingError as exc:
   return ProbeResult(name, False, str(exc))` (the messages are the ones the
   guards raise — keep their wording so the existing failure tests match on
   substrings), `except Exception as exc: ProbeResult(name, False, f"{cls}:
   {exc} (path=…, weights=…)")`; then `result = backend.embed([
   _EMBEDDING_PROBE_TEXT])`; `vector = result.vectors[0]`; `norm =
   float(np.linalg.norm(vector))`; peak RSS as today; detail
   `f"{backend.dim}-dim {backend.native_dtype} model → float32 seam, norm
   {norm:.4f}, truncated={result.truncated} ({EMBEDDING_WEIGHTS_FILENAME}=
   {backend.weights_bytes:,} bytes, peak RSS {rss}) from {backend.model_dir}"`.
   Fail if `backend.dim != EMBEDDING_DIM`, if `abs(norm - 1.0) >
   NORM_TOLERANCE` (message: "model output is not unit-norm"), or if
   `result.vectors.dtype != np.float32`. Never call
   `get_embedding_backend()` here.

5. **Test changes in `test_doctor_embedding_model.py`** (DD-11): `:58`
   `"float16 vector"` → `"float16 model → float32 seam"` and add
   `"truncated=0"`; `_StubModel` gains `embedding` (a small float16 array),
   `dim`, `tokenize(sentences, max_length=None)` returning short id lists,
   and `encode(sentences, **kwargs)` returning a 2-D float16 unit array; the
   `_capture` stub and the missing-directory test retarget their
   monkeypatches to `the_one.embeddings.local`. No new real loads.

6. **Stub backend** `tests/_embedding_stub.py`: `dim` default 8; vector for
   a text = `np.random.default_rng(int(hashlib.sha256(text.encode()).hexdigest()[:16], 16))
   .standard_normal(dim)`, normalised, `float32`; `truncated` = number of
   texts longer than `truncate_over_chars` when set. Document that it is
   the seam's second implementation and why (DD-1).

7. **Settings.** `ChunkingSettings` with `size_chars: int = Field(1000,
   ge=200, le=2000)`, `overlap_chars: int = Field(150, ge=0)` and a
   `model_validator` enforcing `overlap_chars <= size_chars // 2`.
   `EmbeddingSettings` with **plain `str` fields plus `field_validator`s**
   — not `Literal`s: a `Literal` mismatch yields pydantic's generic
   "Input should be 'local'" and `Field(description=…)` never reaches
   `errors()` (design review verified on pydantic 2.13); a validator that
   raises `ValueError("non-LLM local embeddings are the product; a
   provider-delegating backend was removed from Mission 24 at Flight 2
   planning — see mission.md")` does surface it. Same shape for `model_id`
   (must equal `EMBEDDING_MODEL_DIRNAME`) and `dim` (must equal
   `EMBEDDING_DIM`). The routes take `Request`, so no OpenAPI enum is lost. `KnowledgeSettings(embedding, chunking)`.
   `load_knowledge_settings`: read both keys via `AppMetadataRepository`;
   for each, `None` → default; else `model_validate_json`; on
   `ValidationError`/`ValueError` log a warning naming the key and use the
   default. `save_knowledge_settings`: two `set()` calls (two transactions;
   the records are independent by DD-6).

8. **Routes.** `_knowledge_settings_conn()` helper like `_kb_repo`. `GET`:
   `load` → `{"embedding": …, "chunking": …, "notes": ["Chunking changes
   apply to items indexed after the change; existing chunks are not
   re-chunked.", "The embedding backend is fixed to the bundled local
   model in this release."]}`. `PUT`: `Request` body (house style) — a dict
   with optional `embedding` and/or `chunking` keys; merge each present
   key's dict onto `current.<key>.model_dump()` and re-validate the whole
   `KnowledgeSettings` (the merge-then-revalidate shape at `api.py:1398-1420`);
   422 on `ValidationError` with `e.errors(include_context=False)`; save;
   return the same shape as `GET`. Unknown top-level keys → 422.

9. **Warm-up wiring.** `KnowledgeBaseRepository.count()` — one `SELECT
   count(*)`. In `app.py` after the connector-manager block: `try: if await
   KnowledgeBaseRepository(conn).count() > 0: asyncio.create_task(warm_up())
   except Exception: logger.exception("embedding warm-up scheduling
   failed")`. Both call sites are fire-and-forget: `asyncio.create_task(
   warm_up())` with no handle kept — cancelling the task would not stop the
   worker thread `to_thread` already started, so tracking buys nothing
   (design review). In `create_knowledge_base` after `repo.create(kb)`: the
   same call — `warm_up` is idempotent, so no bookkeeping in the route.

10. **Chunker.** Normalise `\r\n` → `\n` **without** changing offsets: work
    on the original string and treat `\r\n` as a boundary pair (simplest:
    compute boundaries on the original text, never on a transformed copy).
    Algorithm: split into paragraphs at blank-line runs; for each
    paragraph longer than `size_chars`, split at line breaks, then at
    sentence ends (`. ! ?` followed by whitespace), then hard at
    `size_chars`; pack pieces greedily into a window of `size_chars`;
    when a window closes, the next window starts at the latest boundary at
    or before `end − overlap_chars` (and after the previous start), so
    overlap ≤ `overlap_chars` and boundaries stay clean; when **no**
    boundary exists in that span (inside a hard-split unbreakable run) the
    next window starts exactly at `end − overlap_chars` — character-level
    fallback, exact overlap. Strip leading and
    trailing whitespace from each chunk's text **and adjust offsets to
    match** so `text[start:end] == chunk.text` holds. Skip whitespace-only
    chunks. `seq` from 0.

11. **Spec comment and `__init__` docstring** rewrites; **`agents.md`**:
    Diagnostics row for `embedding model` now says "via
    `LocalStaticBackend`"; `### Knowledge storage` gains three short
    paragraphs (seam, settings keys, chunker).

12. **Flight log entry**: test counts per new file, `make test-unit`
    figures, ruff, the probe's new detail line verbatim from this host, and
    any deviation.

## Edge Cases

- **Empty `texts`** → `(0, dim)` float32, `truncated=0`, no model call.
- **Text that tokenises to zero ids** (e.g. a 6,000-character run of one
  letter — verified: `tokenize` returns `[]` and `encode` returns a
  zero-norm row and silently flips the batch to float64) → the seam's
  `np.asarray(…, dtype=np.float32)` fixes the dtype; the zero vector is
  passed through as-is and the Protocol docstring says so ("unit-norm for
  any input that yields at least one token"). Flight 3's pipeline skips
  chunks whose vector norm is below 0.5; not this leg's concern beyond the
  docstring and a test pinning the float32 dtype for such an input.
- **Non-string in `texts`** → let model2vec raise; the seam does not
  validate types (`trust-the-runtime`).
- **Concurrent first `get_embedding_backend()` from two threads** → the
  `threading.Lock` double-check guarantees one load.
- **`warm_up()` when the loader raises** (missing weights in a broken
  install) → logged, `_warming` cleared, the next `get_embedding_backend()`
  raises to its caller — startup and KB creation never fail on it.
- **`tokenize` on the long subset only** → the count is exact for every
  text that could exceed 512 tokens (each token ≥ 1 character).
- **A `PUT` that changes nothing** → 200, same body, no write skipped or
  special-cased.
- **Stored settings from a future version with extra keys** → Pydantic
  default `extra="ignore"` on read; do not set `forbid` on the stored
  models (the PUT route rejects unknown top-level keys itself).
- **Chunker offsets with CRLF** → the property test includes `\r\n`
  texts; `text[start:end] == chunk.text` is the invariant, so a chunk's
  text may contain `\r` — it is the file's text.
- **A single 5,000-character line with no spaces** → hard splits at
  `size_chars`, overlap still applied.
- **`test_doctor.py`'s autouse fixture** stubs `_probe_embedding_model` by
  name — unchanged by the rewrite as long as the function name stays.

## Files Affected

- `the_one/embeddings/__init__.py` — rewritten
- `the_one/embeddings/_backend.py`, `the_one/embeddings/local.py` — new
- `the_one/knowledge/__init__.py`, `settings.py`, `chunking.py` — new
- `the_one/diagnostics.py` — probe rewrite, constant re-binding
- `the_one/db/repositories.py` — `KnowledgeBaseRepository.count`
- `the_one/interfaces/web/api.py` — settings routes, warm-up kick
- `the_one/interfaces/web/app.py` — warm-up task
- `packaging/windows/the-one.spec` — comment only
- `the_one/agents.md` — Diagnostics row, Knowledge storage
- `tests/_embedding_stub.py`, `tests/test_embeddings.py`, `tests/test_knowledge_settings.py`, `tests/test_chunking.py` — new
- `tests/test_doctor_embedding_model.py` — DD-11 changes
- `tests/test_lifespan.py`, `tests/test_db_api.py` — additions
- `missions/24-knowledge-bases/flights/02-storage-and-embedding-foundation/flight-log.md`, `flight.md`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (the Flight Director sets `completed` after the flight-end review)
- [x] Check off this leg in flight.md
- [x] Do NOT commit — review and commit are deferred to the flight-end review

## Citation Audit

Design review (Developer, 2026-09-14) verified every citation against the
tree with Legs 1–2 landed and probed the model2vec claims on one real load.
`diagnostics.py` citations were uniformly +47 lines after Leg 2's
`_probe_fts5` insertion — corrected; `TestEmbeddingProbeGating` moved from
`:727` to `:816` — corrected; `api.py` route lines corrected. Two highs
fixed: the 422 message mechanism (validator, not `Literal`/`Field`
description) and the stale test-class citation. Two mediums fixed: the
constant re-binding dropped (no surviving consumer); AC-3 gains the
weights-missing test guard #2 never had.
