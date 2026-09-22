# Flight: Dependency and Packaging Decision

**Status**: completed
**Mission**: [Knowledge Bases](../../mission.md)

## Contributing to Criteria

- [ ] The default embedding backend works on a fresh install with no account, no network, and no external service running *(partial — this flight proves the backend and its model survive the freeze and load offline; the seam and its API land in Flight 2)*
- [ ] Existing installs upgrade with no data loss, the unit gate stays green, and the frozen Windows installer still builds and runs *(partial — this flight establishes the frozen-build gate the rest of the mission is measured against)*

---

## Pre-Flight

### Objective

Prove in the real frozen Windows bundle that the knowledge-base dependency
closure packages and loads — the vector store extension and the bundled static
embedding model — and land that proof as permanent `doctor` probes alongside a
settled dependency set. Every later flight in the mission then inherits a
frozen-build regression gate instead of discovering packaging failures at
release closure.

### Open Questions

- [x] Which embedding model → DD-1
- [x] How the model file clears GitHub's per-blob limit → DD-2
- [x] Which vector store, and on what evidence → DD-3
- [x] How a flight branch gets frozen-Windows verification → DD-4
- [x] Whether the probes are throwaway or permanent → DD-5
- [x] Whether this flight builds any of the mission's seams → DD-6
- [x] Which probes gate on a dev host → DD-7

### Design Decisions

**DD-1 — Embedding model: `potion-retrieval-32M` (512 dimensions), weights converted to float16**
- Rationale: it is the retrieval-tuned member of the family and the best
  performing static retrieval model available; this mission exists for retrieval
  quality over a document corpus. float16 halves the asset and static embeddings
  tolerate half precision well.
- Trade-off: 512 dimensions roughly doubles per-chunk vector storage against the
  256d `potion-base-8M`. At the mission's corpus ceiling that is **1.5–12 GB of
  vectors depending on chunk size** — ~3 GB at 2,000-char chunks, ~6 GB at
  1,000, ~12 GB at 512. Chunk size is still an open mission question and drives
  this figure at least as hard as dimensionality does, so it is a range, not the
  single "~4 GB" this spec previously asserted.
- Consequence: at these volumes an exhaustive scan per query is the binding
  constraint, not storage. See DD-3.

**DD-2 — Model delivery: float16 weights committed as package data, produced by a generator script**
- Rationale: the published `model.safetensors` is **123.2 MiB**, over GitHub's
  hard 100 MiB per-blob limit — a certain push rejection, not a risk. float16
  brings it to roughly 62 MiB, clearing the limit with plain git: no LFS, no
  `.gitattributes`, and no change to either CI checkout. Conversion is performed
  by a committed script following the `scripts/refresh_model_catalog.py` +
  `make refresh-model-catalog` generator precedent, so the asset is reproducible
  rather than a mystery binary. The script calls
  `StaticModel.from_pretrained(repo, quantize_to="float16").save_pretrained(dest)`
  rather than hand-rolling a safetensors rewrite, so `config.json`'s
  `embedding_dtype` stays consistent with the tensors it describes.
  **The committed unit is a model *directory*, not a file** — model2vec's loader
  validates a layout requiring `model.safetensors`, `tokenizer.json` and
  `config.json` together, and `save_pretrained` also emits `modules.json`. The
  `pyproject.toml` package-data glob and the spec's `collect_data_files`
  `includes=` must therefore cover the whole folder (~63 MiB, of which
  `tokenizer.json` is 1.49 MB). Packaging then mirrors `model_catalog.json`
  exactly: a `pyproject.toml` package-data glob for the wheel path plus an
  explicit `collect_data_files` entry in the PyInstaller spec, which the spec's
  own comments record as necessary because package-data does not cover the
  frozen path.
- Trade-off: ~62 MiB lives in git history permanently and is not practically
  reversible once pushed. For scale, the largest currently tracked file is
  `the_one/interfaces/web/static/brand/gleepglorp_med.png` at 1.7 MB — this is
  roughly 36× that, against an 82 MB `.git`.
- Rejected: Git LFS at float32. The repo has LFS hooks installed but nothing
  tracked, and `.github/workflows/windows-installer.yml` uses
  `actions/checkout@v5` without `lfs: true` — so the tag-gated release build
  would freeze a ~130-byte pointer file while the Concourse lane, whose git
  resource does fetch LFS, stayed green. A silent, asymmetric packaging failure
  is precisely what this flight exists to prevent.

**DD-3 — Vector store: `sqlite-vec` and `usearch` evaluated as peers, decided on measurement in Leg 1**
- Corrected rationale: `sqlite-vec` performs **exhaustive brute-force KNN**; it
  has no ANN index and ANN remains upstream future work. Its genuine advantages
  are that vectors stay disk-backed rather than materialising in RAM, and that
  they live inside the SQLite file the app already backs up and migrates. Those
  are real and they are not a complexity improvement — an earlier draft of this
  spec framed the choice as index-versus-scan, which was wrong.
- Consequently `usearch` (2.4 MB, HNSW, wheels for Windows, macOS and Linux) is
  evaluated as a peer in this flight rather than held as a divert target. It
  satisfies the mission's vectors-and-ids-only constraint natively — it is an
  id→vector index that returns ids, never documents — and at the DD-1 volumes an
  approximate index is structurally the right shape.
- **What this flight decides, and what it does not.** Leg 1 answers only the
  question its apparatus can actually observe: *does each candidate package and
  load in the frozen Windows bundle*, plus its measured wheel-bytes delta. The
  choice between them moves to Flight 2. An earlier draft listed query latency
  "against a synthetic corpus sized at the DD-1 range" as a criterion here, but
  the read path in DD-4 is `doctor`'s exit code and per-probe lines — there is
  no harness in this flight capable of benchmarking 1.5–12M vectors, and DD-6
  forbids building the seam that would make the single-file trade-off concrete.
  Stating a criterion with no apparatus is how a flight ends up unable to
  produce its own deliverable.
- Flight 2 inherits the decision with both candidates proven to package, the
  storage seam in place, and a real corpus to measure against. Its criteria:
  query latency at realistic scale; whether the single-file property is
  retained, and if not what the rebuild-from-SQLite and crash-consistency story
  costs. That second cost — a second artifact outside SQLite's backup and
  migration path — is the real price of leaving the database file, not the
  vectors-only constraint, which `usearch` satisfies natively.
- Closure note: `usearch` requires `numpy`, `tqdm` and the native `numkong`.
  On win_amd64/cp311 the usearch wheel itself is 343 KB — an earlier draft cited
  2.4 MB, which is the manylinux wheel and so the wrong platform for the
  installer this flight defends.

**DD-4 — Verification apparatus: `fly execute` against the existing Windows task**
- Act path: `fly -t the-one execute -c ci/tasks/windows-installer-build.yml
  -i repo=. -o installer=./out`, documented at `ci/README.md:106`. It runs the
  identical task file on the Concourse `platform: windows` worker against the
  working tree — provisioning Python 3.11, installing the locked closure via
  `uv export`, freezing with PyInstaller, and executing
  `dist\the-one\the-one.exe doctor` as a gate that throws on non-zero (step 4/6).
- Read path: `run_doctor` in `the_one/diagnostics.py` emits one
  `  {name}: {status} — {detail}` line per probe and returns 0 only when every
  gate passes; the task reads that exit code. Both new probes are observable
  through an existing surface with no test-only seam added.
- Rationale: this needs no git resource, no deploy key, no MinIO secrets, no
  branch tracking, and leaves nothing to tear down. An earlier draft specified a
  branch-tracking pipeline, which was more infrastructure than the repository
  already requires — `ci/windows-installer.pipeline.yml` is in any case
  superseded by `ci/the-one.pipeline.yml`, and both pin `branch: main`.
- Trade-off: `-i repo=.` uploads the working tree per run, so once DD-2's asset
  is committed each run ships ~62 MiB to the worker. Run from a clean tree, as
  `ci/README.md` already advises.

**DD-5 — The probes are permanent deliverables, not scaffolding**
- Rationale: `_probe_model_catalog` exists in this codebase for exactly this
  failure mode — its docstring records that an import-only check misses a data
  file tree-shaken out of the bundle, and that the resulting failure is silent
  and fail-open. A bundled model and a loadable extension are the same hazard
  one layer out. Permanent probes convert this flight from a spike into a
  regression gate the whole mission inherits.
- **Probe invariant — the embedding probe must be incapable of passing by
  download.** `model2vec`'s `_resolve_folder` returns the local directory only
  if it exists, then falls through to `snapshot_download()`. On a networked
  worker a model directory tree-shaken out of the bundle would otherwise produce
  a *passing* probe that fetched the weights over the network — structurally the
  same fail-open as the missing-seed case `_probe_model_catalog` was written
  against, which is the precedent this DD rests on. The probe therefore asserts
  the packaged path resolves and exists via `importlib.resources` **before**
  calling `from_pretrained`, and runs with `HF_HUB_OFFLINE=1` set in-process.
  `huggingface_hub` ships in the closure; it is never permitted to fetch.
- Trade-off: two more gates that can fail a build.

**DD-6 — This flight proves dependencies; it does not build the mission's seams**
- Rationale: the embedding backend seam, the vector storage seam, and the v40
  migration are Flight 2. The probes here load the model and the store directly,
  with no abstraction between. A packaging flight that starts designing
  interfaces stops being able to answer the packaging question cleanly.
- Trade-off: probe internals will need a light rewrite in Flight 2 to call
  through the seam rather than around it.

**DD-7 — Probe gating: embedding unconditional, vector store frozen-only**
- Rationale: `run_doctor` has no conditional-gating machinery — every gate in
  its list is unconditionally ANDed, and the frozen-only behaviour of
  `_probe_desktop_shell` and `_probe_llm_providers` is implemented *inside* each
  probe, which returns `ok=True` with a `"skipped"` detail when `is_frozen()` is
  False. That pattern exists because those probes target **optional extras** that
  may legitimately be absent on a dev host. `model2vec` and the vector store go
  into base `dependencies`, and the model file is package data present in every
  checkout — so an unfrozen embedding-probe failure is a genuine defect, most
  usefully a missing package-data glob in a non-editable wheel install, which a
  frozen-only gate would never catch. The vector-store probe stays frozen-only
  because `enable_load_extension` genuinely varies across Python builds and
  would produce false failures on some dev hosts.
- Resolved interaction with the unit gate: `tests/test_doctor.py` asserts
  `run_doctor(...) == 0` on the host, so an unconditional embedding probe would
  make every `make test-unit` run load ~62 MiB. There are **16 `run_doctor(` call
  sites across 7 classes**, not one, so a **function-scoped `autouse` fixture**
  in that file patches the embedding probe, and the dedicated real-load test
  lives in its **own file** — pytest offers no opt-out from an autouse fixture,
  and a module-scoped fixture cannot take the function-scoped `monkeypatch` at
  all. The gate stays honest — the real load is genuinely covered — without
  charging every unit run for it.
- Trade-off: the dedicated load test is the only host-side proof of the real
  asset, so it must not itself be skipped or mocked.

### Prerequisites

- [x] **Concourse reachable at `localhost:8080`, team `the-one`** — was verified
      DOWN at planning time and again at design review (`dial tcp
      127.0.0.1:8080: i/o timeout`). **Now satisfied**: operator started Docker
      and authenticated; the API answers and three workers report `running`.
- [x] A Concourse worker with `platform: windows` registered and healthy —
      `windows-worker`, `platform: windows`, `state: running`, Concourse 2.5
- [x] `uv` available locally to regenerate `uv.lock` — uv 0.10.0
- [x] The model downloadable once, locally, for conversion and commit — *fetched once in Leg 2; the generator's second load reads the hub cache*

*(Deploy-key, MinIO and branch-pipeline prerequisites were dropped with DD-4.)*

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified — Concourse and the Windows worker confirmed live at flight start
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Sequenced so the cheap, reversible work proves the apparatus before the
expensive, irreversible asset lands.

Both vector-store candidates are small on Windows — `sqlite-vec` 292 KB with no
dependencies, `usearch` 343 KB — so they go first: add them, write the store
probe, and verify the whole chain (`fly execute`, the frozen bundle, the
`doctor` gate) before anything irreversible lands. This is not zero-stakes:
`usearch` pulls `numpy` (~15 MB on win_amd64) and the native `numkong`, so Leg 1
already moves real weight. The point of the ordering is reversibility, not size —
a dependency bump can be reverted with a commit, a 62 MiB blob in history cannot.

The model asset follows on a proven apparatus: a generator script converts the
published weights to float16, the result is committed as package data, and
`pyproject.toml` plus the PyInstaller spec are wired to carry it down both the
wheel and frozen paths. `tokenizers` is a Rust extension and the store ships a
native loadable library; both are the same packaging-survival class as the
documented M16 frozen-provider tree-shake, so both get explicit declarations
rather than relying on static analysis. `upx=True` with an empty `upx_exclude`
is currently a no-op because no toolchain in either CI path provides UPX, but
the native store library and the tokenizers/safetensors binaries are added to
`upx_exclude` in the same edit as cheap insurance against a future UPX install.

Probes follow the existing `_probe_*` shape and are registered in `run_doctor`'s
gate list, each carrying its own gating branch per DD-7. The embedding probe
loads the bundled model from its packaged location and embeds a fixed short
string, asserting a concrete resolved value — vector length 512, non-zero
norm — rather than merely "no exception". A header-only check would prove the
data file survived but would not prove the `tokenizers` extension did, which is
the actual hazard. It must not touch the network, and must prove the offline
local-path load specifically.

### Checkpoints

- [x] Dependency closure resolves; `uv.lock` regenerated; `make test-unit` stays green against its ~455s / 3,910-test baseline — *Leg 2 close: 139 packages, no conflict; 3,948 passed / 10 skipped in 469.35s*
- [x] Vector-store probe passes in the frozen Windows bundle; both candidates measured against DD-3's four criteria and the choice recorded with evidence — *both probes `OK` on three frozen runs; per DD-3 as amended the choice itself is Flight 2's, with wheel bytes and the `usearch`/`numkong` finding recorded as its input*
- [x] Model asset converted and reachable through the packaged path — verified from a **non-editable wheel install** (`pip install .` into a scratch venv), not only from a source checkout — *converted, verified, and left untracked; **committed by a human**, see the flight log's terminal handoff*
- [x] `the-one.exe doctor` returns `RESULT: PASS` in the frozen bundle with both new probes present and gating — *2026-09-09, eight gates `OK`, three by-name assertions in the task*
- [x] Installer size and freeze duration recorded before and after the asset lands — a number the operator agreed to in the abstract but has never seen — *before: 71,239,095 bytes, Inno 59.1s (Leg 1). After: 141,827,664 bytes (+70,588,569 = +67.32 MiB), Inno 123.3s / 117.0s on two runs*
- [x] Peak RSS recorded during the embedding probe in the frozen bundle — the input Flight 2 needs for the float16/int8 vector-storage decision — *the probe self-reports it in its detail line; host figures 261.3 MiB (checkout) / 210.8 MiB (wheel). Frozen: **247.1 MiB** on `windows-worker`, after a `ctypes` HANDLE-truncation defect in the Windows branch was found by the first frozen run and fixed*
- [x] **Measured dependency closure recorded** — the actual added-package list and win_amd64 wheel bytes from the regenerated `uv.lock`, against the mission's stated figure. Verified additions absent from the lock today: `model2vec`, `numpy`, `joblib`, `cloudpickle`, `safetensors`, `tokenizers`, `huggingface-hub`, `fsspec`, `hf-xet`, `numkong`, `sqlite-vec`, `usearch`
- [x] float16 conversion **correctness** verified by the generator against the reloaded artifact — dtype asserted directly in both `config.json` and the safetensors header, magnitude compared against upstream, and cosine/recall@1 as sanity checks over a committed sample
- [x] `pip-audit` clean against the `--extra gui --extra all-llms` release closure — *clean at Leg 2 close, including all seven new surfaces*

### Adaptation Criteria

**Divert if**:
- Neither vector-store candidate loads in the frozen CPython 3.11 bundle. Next
  on the shelf: `faiss-cpu` (19.5 MB, Windows wheels, real ANN).
- `pip-audit` reports findings in the new closure that cannot be cleared by
  raising version floors.
- The float16 conversion is **botched** — wrong dtype, wrong scale, truncated
  tensor — caught by the generator's direct assertions on `config.json`'s
  `embedding_dtype` and the safetensors header dtype, a raw-matrix magnitude
  comparison against upstream, and pinned semantic thresholds (mean cosine
  ≥ 0.9999, min ≥ 0.999, recall@1 == 1.0), with a non-zero exit on any breach.

  *Amended during Leg 2 design.* This was originally worded as "float16
  measurably degrades retrieval quality", which implies a failure mode the
  measurement cannot produce: for a normalising static model, per-text
  cosine(fp32, fp16) measures 1.000000 to six decimals and recall@3 is 1.0000.
  Keeping it as a quality-degradation trigger would have made it unfalsifiable
  theatre. Demoted to a conversion-correctness assertion, which is the failure
  that can actually occur. If it fires, DD-2 does not reopen — the conversion is
  simply wrong and gets fixed.

  *Amended again in Leg 2 design review cycle 2.* Cosine and recall alone do not
  discriminate the failures this trigger names: cosine is scale-invariant and the
  model applies a `Normalize` module, so a wrong scale scores 1.000000, and a
  wrong dtype scores ~1.0. The trigger therefore rests on direct dtype assertions
  and a magnitude comparison, with cosine and recall as sanity checks rather than
  the mechanism. `recall@1` replaces `recall@10`, which over a 32-string corpus
  covered ~31% of it and would have passed a badly degraded model.

**Acceptable variations**:
- The package path the model file lives under
- Probe naming and the wording of emitted detail lines
- Whether the generator script is wired to a `make` target or run manually

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned
> and created one at a time as the flight progresses.

- [x] `vector-store-probe` — add both store candidates, write the store probe
      with its tests, and verify the full chain in the frozen Windows bundle via
      `fly execute`. Measures both candidates against DD-3's criteria and records
      whether each candidate packages and loads, with its measured wheel-bytes
      delta. Proves the apparatus end to end before anything irreversible lands.
      Note both leg deliverables — code and unit tests — are producible on the
      host, but the leg's *acceptance* needs Concourse: the store probe is
      frozen-only-gating per DD-7, so its real signal is the `fly execute` run.
- [x] `embedding-model-and-probe` — the float16 generator script, the committed
      asset, `pyproject.toml` and spec wiring, the embedding probe with its
      tests, and frozen verification on the now-proven apparatus. Isolated in its
      own leg because the commit is the one action in this mission that cannot be
      undone without a history rewrite. **The generator script emits the model
      directory; a human stages and commits it.** No agent performs that `git add`
      unattended — an irreversible 62 MiB write to shared history is an operator
      decision, and the leg is not permitted to make it silently.

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [x] Code merged — PR #195 → `mission/24-knowledge-bases`, merge commit `1edff28`, 2026-09-14
- [x] Tests passing
- [x] Mission open questions on model choice, model delivery, and vector store closed with evidence *(the vector-store *choice* itself is deferred to Flight 2 per DD-3 as amended; this flight closes the questions by supplying the evidence — both probes' frozen results and wheel-byte deltas — that Flight 2's choice will be made on)*
- [x] Documentation updated — the spec's collection-contract comments, `run_doctor`'s stale docstring (it names two gates where five exist), and the three places that enumerate what `doctor` checks: `README.md`, `docs/windows-install.md`, and `the_one/main.py`
- [x] `.github/workflows/windows-installer.yml`'s existing `grep -q` smoke assertions extended to name both new probe lines, so the release path asserts their presence rather than only the aggregate result

### Verification

The flight succeeds when `the-one.exe doctor` returns `RESULT: PASS` in a
PyInstaller bundle frozen on a real Windows worker, with both new probes present
and gating, and when `pip-audit` is clean against the release closure the
installer ships.

**No behavior test.** The mission's behavior-test-backed criteria all concern
operator-visible or agent-visible behaviour; this flight has no such surface.
Its acceptance is an exit code from a CI-observable command that the existing
frozen-build gate already reads. Two live agents would observe nothing the exit
code does not already state unambiguously.

**Known lane conditions** carried from recent debriefs: `make test-unit` runs
~455s at 3,910 tests, and the Studio browser lane carries a standing timing
flake (squawk 0035) whose disposition is to re-run the failing test in isolation
before treating it as a regression. This flight touches neither Studio nor the
browser lane.
