# Leg: embedding-model-and-probe

**Status**: completed
**Flight**: [Dependency and Packaging Decision](../flight.md)

## Objective

Convert `potion-retrieval-32M` to float16, commit it as package data, and prove
it loads offline from the packaged path inside the frozen Windows bundle via a
permanent `doctor` probe — closing the flight's remaining hard-to-reverse
decision on an apparatus Leg 1 already proved.

## Context

**From the flight's design decisions:**

- DD-1 — `potion-retrieval-32M`, 512 dimensions, weights at float16.
- DD-2 — committed package data, produced by a generator script following the
  `scripts/refresh_model_catalog.py` + `make refresh-model-catalog` precedent.
  Git LFS was rejected in writing: `.github/workflows/windows-installer.yml:35`
  is `actions/checkout@v5` with no `lfs: true`, so the tag-release path would
  freeze a pointer file while Concourse stayed green.
- DD-5 — **probe invariant**: the probe must be incapable of passing by
  download.
- DD-6 — no seam, no abstraction, no storage or embedding interface. Flight 2
  owns those.
- DD-7 — this probe gates **unconditionally**, unlike Leg 1's frozen-only
  vector-store probes. `model2vec` is a base dependency and the model is package
  data present in every checkout, so an unfrozen failure is a real defect —
  most usefully a missing package-data glob in a non-editable wheel install,
  which a frozen-only gate would never catch.

**Verified empirically during leg design** (scratch venv, model2vec 0.9.0,
`potion-base-2M` as a fast proxy) — these are measurements, not assumptions:

- `StaticModel.from_pretrained(repo, quantize_to="float16").save_pretrained(dest)`
  works and is the correct call. `quantize_to` is a real `from_pretrained`
  parameter; hand-rolling a safetensors rewrite would risk `config.json`'s
  `embedding_dtype` disagreeing with the tensors.
- `save_pretrained` emits exactly **five files**: `README.md`, `config.json`,
  `model.safetensors`, `modules.json`, `tokenizer.json`. The committed unit is a
  **directory**, not a file.
- float16 round-trips correctly: resulting `embedding.dtype` is `float16`, and
  `encode()` returns float16 vectors with norm ≈ 1.0 (the model normalizes).
- **The offline guard works.** With `HF_HUB_OFFLINE=1`, a present local
  directory loads and a missing one fails rather than downloading. **The
  exception type depends on the path shape**: a missing *relative* or
  repo-id-shaped string raises `LocalEntryNotFoundError`, but a missing
  *absolute* path — which is what `importlib.resources.files(...)` yields, and
  therefore the case that actually applies here — raises
  `huggingface_hub.errors.HFValidationError` from `validate_repo_id`. The Edge
  Cases test must not pin the wrong one. The env var does the real work; the
  path-existence assertion is defence in depth and a better message.
- `from_pretrained` has `force_download: bool = True` as its default. Irrelevant
  once `HF_HUB_OFFLINE=1` is set, but worth knowing.
- **Size is exact, not projected.** The published safetensors header reads
  `{"embeddings":{"dtype":"F32","shape":[63091,512],"data_offsets":[0,129210368]}}`
  — a single tensor, no extra metadata, 88 bytes of header on a 129,210,456-byte
  file. float16 halves the only payload exactly: **64,605,272 bytes = 61.61 MiB**,
  plus `tokenizer.json` 1,493,150, `config.json` 202, `modules.json` 278 and a
  small `README.md` ⇒ **~66.1 MB / 63.0 MiB total**. DD-2 holds with ~38 MiB of
  margin. Still verify the real figure before `git add` — the gate is cheap and
  DD-2's whole basis is that float16 clears 100 MiB on plain git.

**Ground truth from Leg 1:**

- `numpy` is already in the closure — it arrived transitively via `usearch`. So
  `model2vec`'s numpy requirement is already satisfied and adds nothing.
- The frozen apparatus is proven working: `fly execute -c
  ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out`, ~10 minutes
  per run, exit 0, `doctor` gate at step 4/6.
- **Both CI lanes now assert probe lines by name** — the GitHub packaged-smoke
  greps and the Concourse task. This leg's probe line must be added to both, or
  it is unobserved in exactly the way Leg 1 fixed.
- `_vector_probe_outcome` exists as Leg 1's frozen-only gating helper. This
  probe gates unconditionally and must **not** use it.
- Baseline to move deliberately: `make test-unit` 3,938 passed / 10 skipped /
  ~484s. `tests/test_doctor.py` is 45 tests.
- Data files resolve via `importlib.resources.files(...)` — see
  `the_one/llm/model_catalog.py:249`.

**Packaging note.** Unlike Leg 1's `vec0` native library, `collect_data_files`
**is** the right mechanism here: PyInstaller's exclusion of `all_suffixes()`
blocks only importable extension suffixes (`.so`, `.pyd`), and every file in the
model directory is `.json`, `.safetensors` or `.md`. The `seed_datas` entry at
`the-one.spec:125` is the shape to copy — this time genuinely.

## Inputs

- Leg 1 landed: both stores in the closure, two probes gating, frozen build green
- `the_one/diagnostics.py` with seven gates
- No `model2vec` in `uv.lock`; `numpy` already present
- Network access, once, to fetch the upstream model for conversion

## Outputs

- A committed generator script and its `make` target
- The float16 model directory committed as package data
- `model2vec` in the runtime closure, `uv.lock` regenerated
- A third probe in `the_one/diagnostics.py`, gating unconditionally
- `pyproject.toml` package-data glob and a spec `collect_data_files` entry
- Both CI lanes asserting the new probe line by name
- A green frozen Windows build with the probe reporting OK
- `/out/` gitignored, so `fly execute` stops shipping stale installers to the worker

## Acceptance Criteria

- [x] A generator script converts `potion-retrieval-32M` to float16 and writes the model directory, is wired to a `make` target, and re-running reproduces the same bytes for the same upstream input **and the same destination path** — `save_pretrained` embeds the destination basename in `README.md`'s front-matter, heading and code samples, so pass its explicit `model_name=` parameter to make the output path-independent
- [x] The generator verifies conversion correctness by **reloading the written directory** and checking it three ways, exiting non-zero on any breach: (a) `config.json`'s `embedding_dtype == "float16"` **and** the safetensors header dtype `== "F16"`; (b) raw-matrix magnitude — max and mean absolute value of the reloaded `embedding` against upstream, within fp16 rounding tolerance; (c) mean cosine ≥ 0.9999, min ≥ 0.999 and recall@1 == 1.0 over a committed sample of ≥32 strings
- [x] The model directory is committed as package data, its largest blob is verified under GitHub's 100 MiB limit **before** the commit is attempted, and `pyproject.toml` plus the PyInstaller spec both carry it *(64,605,272 bytes verified pre-`git add`; wiring done, including a `the_one.embeddings` hiddenimport the leg did not name — see the flight log. The `git add` itself is the human's, per step 9.)*
- [x] `model2vec` is in `[project] dependencies` with `uv.lock` regenerated
- [x] A probe loads the model **from the packaged path** and embeds a fixed string, asserting concrete resolved values — vector length 512 and a non-zero norm — not merely absence of exception
- [x] The probe cannot pass by downloading: it asserts the packaged path resolves and exists before calling `from_pretrained`, and runs with `HF_HUB_OFFLINE=1` set in-process
- [x] The probe gates unconditionally, and the model loads from a **non-editable wheel install** (`pip install .` into a scratch venv), not only from a source checkout
- [x] `make test-unit` green, and the host suite does not pay the model-load cost on every run — `tests/test_doctor.py` has **16** `run_doctor(` call sites across **7** classes, so a per-file `autouse` fixture patches the embedding probe, and the dedicated real-load test lives in its **own file** so no opt-out mechanism is needed. Note `test_passes_on_host_with_child_spawn_ok` (`tests/test_doctor.py:35`) monkeypatches nothing at all and would otherwise hard-depend on the 62 MiB asset being present
- [x] `pip-audit` clean against the widened release closure, which now includes `huggingface-hub`, `fsspec`, `hf-xet`, `joblib`, `cloudpickle`, `safetensors` and `tokenizers`
- [x] `the-one.exe doctor` returns `RESULT: PASS` in a bundle frozen on `windows-worker` with the probe line present, and both CI lanes assert that line by name — *met 2026-09-09 on two consecutive frozen runs after `fly` re-login; the task's by-name assertion executed and passed. See the flight log's Leg 2 frozen verification sections.*
- [x] Installer size and freeze duration recorded before and after the asset, and **the probe self-reports peak RSS in its detail line** *(the self-reporting is implemented and verified on the host — 261.3 MiB in a checkout, 210.8 MiB from the wheel. The first frozen run (AC-10) exposed a real defect in the Windows branch of `_peak_rss_bytes()` — undeclared ctypes `restype`/`argtypes` truncated `GetCurrentProcess()`'s HANDLE and the memory call failed with `ERROR_INVALID_HANDLE`, printing "peak RSS unavailable" — reproduced and confirmed on `windows-worker`, fixed (`the_one/diagnostics.py`; declared `HANDLE`/`BOOL` restypes and argtypes, plus a diagnosable failure reason threaded into the detail line), and covered by two new host-runnable unit tests (`tests/test_doctor_embedding_model.py::TestPeakRssWindowsBranch`) that stub `ctypes.WinDLL` to exercise the branch on Linux CI. The fixed function was re-verified on `windows-worker` from the unfrozen checkout — returns a positive figure (25,079,808 bytes ≈ 23.9 MiB) instead of `None` — see the flight log's "Peak RSS fix — reproduced and corrected on windows-worker" section. The frozen bundle's actual peak-RSS figure and the installer-delta re-measurement are still pending — the Flight Director re-runs the full frozen build.)* — DD-4's read path is `doctor`'s stdout, and neither CI task measures memory, so self-reporting is what makes this observable through the existing apparatus rather than a manual side-measurement. This is the input Flight 2 needs for the float16-vs-int8 vector-storage decision

## Verification Steps

- **Blob size gate**: `ls -l` the generated `model.safetensors` and confirm < 100 MiB *before* `git add`. This is the one check that cannot be done after the fact.
- **Offline invariant**: a test that removes or renames the packaged directory and asserts the probe FAILS rather than downloading; and a test asserting `HF_HUB_OFFLINE` is set during the load
- **Wheel install**: `pip install .` into a scratch venv, then run the probe from that venv — proves the package-data glob, which the frozen gate does not cover
- **Unit gate**: `make test-unit` against the 3,938 / ~484s baseline; report the delta and confirm it is not dominated by model loading
- **Audit**: `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt > /tmp/rr.txt && pip-audit --disable-pip -r /tmp/rr.txt`
- **Frozen build**: `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out > /tmp/fb.log 2>&1`, then `sed -n '/\[4\/6\]/,/\[5\/6\]/p' /tmp/fb.log`. Redirect — the log is ~1,000 lines.
- **Installer delta**: compare against Leg 1's measured 71,239,095 bytes

## Implementation Guidance

1. **Write the generator script** — `scripts/` alongside `refresh_model_catalog.py`, same docstring conventions (what it does, when to re-run, what contract it holds). Call
   `StaticModel.from_pretrained("minishlab/potion-retrieval-32M", quantize_to="float16").save_pretrained(dest)`.
   Add a `make` target mirroring `refresh-model-catalog` at `Makefile:191-193`.

2. **Add a conversion-correctness check — and make it actually discriminate.** Measured on the 2M proxy, per-text cosine(fp32, fp16) is **1.000000** to six decimals with recall@3 of **1.0000**: for a normalising static model fp16 drift is effectively zero, so a check framed as "does float16 hurt quality" is a rubber stamp.

   **Cosine alone is not enough for correctness either.** It is scale-invariant, and `modules.json` adds a `Normalize` module, so a **wrong scale** scores 1.000000 — doubly invisible. A **wrong dtype** (quantization silently skipped, or applied as bfloat16/int8) also scores ~1.0; the fp32 case would be caught only by the ≥100 MiB size gate, and int8 would slip both. **Truncation** is caught, but by `safetensors` refusing to open the file rather than by any threshold. So cosine and recall alone discriminate almost nothing they appear to.

   Check three things instead, all cheap and decisive:
   - **Dtype, directly**: `config.json`'s `embedding_dtype == "float16"` *and* the safetensors header dtype `== "F16"`.
   - **Magnitude**: max and mean absolute value of the reloaded `embedding` matrix against upstream, within fp16 rounding tolerance. This is what catches a rescale.
   - **Semantic sanity**: mean cosine ≥ 0.9999, min ≥ 0.999, **recall@1 == 1.0** over a committed inline list of ≥32 strings. Use `recall@1`, not `@10` — at a 32-string corpus, k=10 is ~31% of the corpus and passes for a badly degraded model.

   **Reload from disk before comparing.** Compare upstream fp32 against `StaticModel.from_pretrained(dest)` under `HF_HUB_OFFLINE=1`, not against the in-memory quantized object — otherwise the check tests the quantizer and not the artifact, and a botched *write* (wrong layout, subfolder slip) passes. One network fetch total: pull fp32, quantize in-process, save, reload from disk.

3. **Model location — default is `the_one/embeddings/data/potion-retrieval-32M/`**, with `the_one/embeddings/__init__.py` so `importlib.resources.files("the_one.embeddings")` resolves. Named here rather than deferred because the same choice appears in three files that must agree: the `pyproject.toml` glob, the spec's `includes=`, and the probe's `files(...)` argument. Note that `[tool.setuptools.package-data]` keys on `the_one` with globs that cross sub-package boundaries — `interfaces/web/static/**/*` is the proof — so add `embeddings/data/**/*` to the existing `the_one` key rather than creating a new key for the sub-package. This is a **location decision, not an interface decision**; DD-6 forbids seams, not directories, and a later git rename costs nothing since blobs are content-addressed.

4. **Size gate — immediately after the generator runs.** `ls -l` the emitted `model.safetensors`. If it is at or over 100 MiB, **STOP and report**: DD-2 is invalidated and DD-1 reopens with it. This is a blocking check, not a handoff — steps 5-8 continue normally once it passes.

5. **Wire packaging** — a `pyproject.toml` package-data glob covering all five files, and a `collect_data_files` entry in the spec copying `seed_datas` (`the-one.spec:125`). Both are needed: package-data covers the wheel path, `collect_data_files` covers the frozen path, and the spec's own comments explain why one does not imply the other.
   - **Also add `tokenizers*`, `_safetensors_rust*` and `_hf_xet*` to `upx_exclude`**, which the flight's Technical Approach mandates and which currently holds only Leg 1's `["vec0*","compiled*","_numkong*"]`.
   - Record in the spec comments that `tokenizers.abi3.so` and `_safetensors_rust.abi3.so` are collected by the module graph with **no hook and no hiddenimports entry** — verified against a real onedir build, and `pyinstaller-hooks-contrib` ships no hook for tokenizers, safetensors, huggingface_hub or model2vec. Without that note the next reader repeats the search.

6. **Write the probe.** Resolve the packaged directory via `importlib.resources`, assert it exists, set `HF_HUB_OFFLINE=1` in-process, load, embed a fixed short string, and assert `len(vector) == 512` and a non-zero norm. Gate unconditionally per DD-7 — do not use `_vector_probe_outcome`. Keep the never-raises contract. Report the resolved path in the detail line, as Leg 1's probes do, so a packaging failure names what it looked for.

7. **Keep the unit gate cheap — and use a mechanism pytest actually supports.** `tests/test_doctor.py` calls `run_doctor(` in **16** places across **7** classes, so patching one "host test" leaves fifteen paying the load.

   Use a **function-scoped** `autouse` fixture in `tests/test_doctor.py` taking the ordinary `monkeypatch` fixture. Do **not** use module scope: a module-scoped fixture cannot request the function-scoped `monkeypatch` (pytest raises `ScopeMismatch`), and it would need a manually managed `pytest.MonkeyPatch()` for which this repo has no precedent. Function scope costs nothing here — what is being avoided is the 62 MiB model load, not the `setattr`.

   **Put the dedicated real-load test in its own file** rather than trying to opt out of the autouse fixture. pytest has no built-in opt-out, and the usual marker workaround needs `request.node` to be the test function — at module scope it is the Module, so the opt-out is impossible at the scope originally specified. A separate file sidesteps the problem entirely.

   Leg 1 found that a naive monkeypatch against an immutable C type gets swallowed by the probe's own broad `except`, yielding a test that passes while asserting nothing — so assert on the emitted detail, not only on `ok`.

8. **Extend both CI lanes** with the new probe line by name, and update the four `doctor` enumerations Leg 1 corrected — they go stale again with a third gate. Note the arithmetic, not just the names: `the_one/diagnostics.py` currently says "the last five are frozen-only" across seven gates, and an unconditional eighth changes both the count and the split. The other three do **not** simply end at "vector stores" — each continues into a runtimes clause, and the new item must be inserted *before* it: `README.md:52` ends `…vector stores, node/uv/python on PATH)`; `the_one/main.py:51-53` ends `…external runtimes)`; `docs/windows-install.md:127-131` ends `…find any external runtimes on your PATH`.

9. **Terminal handoff — the human stages the model.** `git add` of the model directory is the one irreversible act in this mission and **no agent performs it unattended**. Everything else completes with the directory present-but-untracked: pytest reads the filesystem, `pip install .` copies from the source tree, and `fly execute -i repo=.` uploads untracked non-ignored files. Leave this exit state and say so plainly — model directory on disk and untracked (`??` in `git status`), all code changes uncommitted. **The human's `git add` must land in or before the flight's single commit**, or the unconditional gate turns the branch red on a machine without the asset.

## Edge Cases

- **`model.safetensors` ≥ 100 MiB** — stop and report; DD-2 and DD-1 reopen together.
- **The probe passes on a machine with a warm HF cache** — a false green. `HF_HUB_OFFLINE=1` plus the path assertion must be tested by actually removing the packaged directory, not by trusting the env var.
- **`tokenizer.json` missing from the glob** — model2vec's loader validates the layout, so a partial glob fails at load rather than silently degrading. Better than the Leg 1 case, but the wheel-install check is what catches it.
- **Probe raises** — forbidden. An escaping exception takes down `doctor` and breaks both CI gates for reasons unrelated to the model.
- **A truncated file or an LFS pointer in place of the weights** — report the resolved path **and** `model.safetensors`'s byte size in the probe detail line, so this surfaces as a legible mismatch rather than an opaque load error.
- **`pip install .` builds the wheel directly under PEP 517**, so AC-7 exercises package-data only; the sdist path is *not* under test. Do not read a green wheel install as proof the sdist is correct.
- **The untracked-asset window.** Between leg exit and the human's `git add`, the unconditional gate is green only on the machine holding the model. No CI lane runs the unit gate on this branch — Concourse's pipelines track `main`, and `pr-lint.yml` triggers on pull requests to `main` — so the window is safe as long as no PR is opened before the asset is staged. Opening one first would turn the gate red for a reason that has nothing to do with the code.
- **`pip-audit` finding in the new closure** — `huggingface-hub`, `fsspec` and `hf-xet` are new surfaces on a gate that fails the release. If one fires, raise the floor; if it cannot be raised, stop and report.

## Files Affected

- `scripts/{generator}.py` — new; conversion plus the correctness check
- `Makefile` — new target mirroring `refresh-model-catalog`
- `pyproject.toml` — `model2vec` dependency, and `embeddings/data/**/*` on the existing `the_one` package-data key
- `uv.lock` — regenerated
- `the_one/embeddings/__init__.py` — new, so `importlib.resources` can resolve the data
- `the_one/embeddings/data/potion-retrieval-32M/` — the committed model directory (five files)
- `packaging/windows/the-one.spec` — `collect_data_files` entry, `upx_exclude` additions, collection-contract comments
- `the_one/diagnostics.py` — the probe, gate registration, docstring arithmetic
- `tests/test_doctor.py` — function-scoped autouse patch fixture
- `tests/test_doctor_model_load.py` (or similar) — new; the dedicated real-load test, in its own file so no autouse opt-out is needed. **Not** `tests/conftest.py`: an autouse fixture there would patch the probe across all ~3,938 tests
- `.github/workflows/windows-installer.yml`, `ci/tasks/windows-installer-build.yml` — named-line assertions
- `the_one/main.py`, `README.md`, `docs/windows-install.md` — doctor enumerations
- `.gitignore` — add `/out/`, anchored. It is 68 MB, untracked and unignored today, so every `fly execute -i repo=.` ships Leg 1's stale installer to the worker against DD-4's clean-tree guidance. Anchor it so it cannot match a nested directory named `out`

## Citation Audit

Verified against the working tree at Leg 1 close:

- `scripts/refresh_model_catalog.py:1-31` generator docstring conventions — confirmed (an earlier draft cited `:1-28`, truncating it)
- `Makefile:191-193` `refresh-model-catalog` target — confirmed
- `the_one/llm/model_catalog.py:249` `importlib.resources.files` — confirmed
- `packaging/windows/the-one.spec:125` `seed_datas` — confirmed
- `.github/workflows/windows-installer.yml:35` `actions/checkout@v5`, no `lfs:` key — confirmed
- `the_one/diagnostics.py` `_vector_probe_outcome` frozen-only helper (Leg 1) — confirmed
- Leg 1 measured installer 71,239,095 bytes; unit baseline 3,938 / ~484s — confirmed from this flight's log
- `tests/test_doctor.py:35` `test_passes_on_host_with_child_spawn_ok` monkeypatches nothing — confirmed; **16** `run_doctor(` call sites across **7** classes (an earlier draft said 17 across six; the 17th match was the substring in the *name* `test_skip_keeps_result_pass_in_run_doctor` at `:165`)
- `tests/conftest.py:108` is a **session-scoped** autouse teardown that patches nothing and has no opt-out — cited as evidence that autouse is used in this repo, **not** as precedent for scoped patching or opting out
- model2vec 0.9.0 API facts — verified empirically in a scratch venv during leg design, not read from documentation

---

## Post-Completion Checklist

- [x] All acceptance criteria verified — AC-10 and AC-12 closed 2026-09-09 by two frozen runs (frozen peak RSS 247.1 MiB; installer 141,826,728 bytes, +67.32 MiB)
- [x] Tests passing — 3,950 passed / 10 skipped in 453.49s (after the peak RSS fix)
- [x] Flight log updated with sizes, quality figures, host and frozen peak RSS, and both frozen `doctor` outputs
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] Do NOT commit code — the flight commits once after review. The model directory is the sole exception and is staged by a human.
