# Leg: store-decision-and-closure

**Status**: completed
**Flight**: [Storage and Embedding Foundation](../flight.md)

## Objective

Close the flight on the operator's DD-9 decision (**`usearch`, dtype `f16`**,
flight log "DD-9 decision checkpoint (2026-09-15)"): remove `sqlite-vec` from
the dependency closure, the frozen bundle, the `doctor` gate list, both CI
lanes and the tree; make `usearch`/`f16` the one configured backend with the
dispatcher keeping its shape; move the `kb_vector_index` registry DDL into a
**v41** migration block so the fresh-DB shape tests own it; harden the
surviving store on the three conditions the flight-end review attached to a
`usearch` decision (atomic sidecar save, corrupt sidecar → stale, no mutation
before the re-entry guard); drop `hf-xet` from the closure (squawk 0049,
completed against this leg's commit); regenerate `uv.lock`; run `pip-audit`
on the final closure; and update every document that enumerated two vector
stores or nine `doctor` gates. The Flight Director's frozen `fly execute`
run at the end proves `RESULT: PASS` with the surviving probes.

## Context

- **Decision inputs** are in the flight log's `## Store Benchmark` tables and
  the "DD-9 decision checkpoint" entry. Nothing here re-opens the choice.
- **What the tree looks like at leg start** (Legs 1–5 committed as `c315cf5`
  + the decision entry `b86e204`; working tree clean):
  - `the_one/vectors/`: `_store.py` (Protocol, three error classes,
    `quantize_int8`), `sqlite_vec_store.py` (the loser), `usearch_store.py`
    (the winner; its `open()` still runs `CREATE TABLE IF NOT EXISTS
    kb_vector_index` — store-owned DDL, DD-3), `__init__.py` (dispatcher
    `_build_store` branching on `settings.backend`; `get_vector_store()`;
    `_reset_for_test()`).
  - `the_one/knowledge/settings.py::VectorStoreSettings`: `backend:
    Literal["sqlite-vec", "usearch"] = "sqlite-vec"`, `dtype: str =
    "float32"`, `_VECTOR_STORE_DTYPES` maps each backend to its dtypes.
    `save_vector_store_settings` has **no production caller** (verified —
    the record is only ever written by tests), so a real database normally
    holds no `knowledge.vector_store` row and `load_vector_store_settings`
    returns the model default. That default is what this leg flips.
  - `the_one/diagnostics.py`: `_probe_sqlite_vec` (line ~332),
    `_probe_usearch` (~504), the shared `_vector_probe_outcome` helper
    (~320), `run_doctor` (~806) with a nine-entry `gates` list and a
    docstring that says "nine" / "five are frozen-only".
  - `pyproject.toml` lines 71–86: the two-candidate comment block +
    `"sqlite-vec>=0.1.6"`, `"usearch>=2.16"`; **no `[tool.uv]` table exists**
    (tables present: `tool.setuptools.*`, `tool.pytest.ini_options`,
    `tool.ruff*`). `uv` 0.10.0 is on this host and its binary carries both
    `exclude-dependencies` and `override-dependencies` keys.
  - `uv.lock`: `hf-xet` 1.6.0 is pulled by `huggingface-hub` under a
    `platform_machine` marker (line ~723); `sqlite-vec` at ~2614.
  - `packaging/windows/the-one.spec`: `sqlite_vec_bins =
    collect_dynamic_libs("sqlite_vec", …)` (~220) fed into `binaries` (~294);
    `upx_exclude` (~394) carries `"vec0*"`, `"compiled*"`, `"_numkong*"`,
    `"tokenizers*"`, `"_safetensors_rust*"`, `"_hf_xet*"`; a long
    sqlite-vec collection comment (158–190) and the numkong note (191–219,
    **stays** — usearch won and imports numkong unconditionally).
  - CI lanes asserting the probe line by name: `ci/tasks/windows-installer-build.yml`
    (~60, PowerShell needle array) and `.github/workflows/windows-installer.yml`
    (~78, `grep -q "sqlite-vec: OK"`).
  - Docs enumerating the two stores / nine gates: `README.md:52`
    ("vector stores"), `docs/windows-install.md:127-129` ("load both bundled
    vector stores"), `the_one/main.py:51-53` (usage text "vector stores"),
    `the_one/agents.md` "Knowledge storage" (~1128–1138), "Diagnostics" nine-
    gate table and probe-contract paragraphs (~1255–1296, "Seven of the
    nine", "both vector-store probes"), packaging notes (~1289–1292, "six
    entries total"); `SECURITY-MODEL.md:573-590` (the DD-10 native-
    extension paragraph); `missions/24-knowledge-bases/mission.md` Known
    Issues (~311–322: the `hf-xet` dead-weight item).
  - `scripts/bench_vector_store.py` (four cells, imports `SqliteVecStore`;
    `_BYTES_PER_VECTOR` has sqlite-vec entries; two `if backend ==
    "sqlite-vec"` branches ~517/540; `sqlite_vec_version` host fact ~224;
    header docstring says "four"), `Makefile:205-207` (`bench-vector-store`
    "four DD-4 cells"), `tests/test_bench_vector_store.py` (cells named
    `sqlite-vec:float32` throughout — 20 references).
  - Tests naming the loser: `tests/test_vector_store.py` (`CELLS` with four
    cells, `_build`, `TestProtocolSatisfaction` asserts on `SqliteVecStore`,
    `TestSqliteVecOpenBehavior`, `TestMismatchDetection` — both sqlite-vec-
    only), `tests/test_doctor.py::TestProbeSqliteVec` (~419–548, imports
    `_probe_sqlite_vec`), `tests/test_vectors_dispatch.py` (`test_defaults_to_sqlite_vec_when_record_absent`,
    `test_returns_sqlite_vec_when_record_says_so`), `tests/test_knowledge_settings.py`
    (~140–158: default asserts `sqlite-vec`/`float32`; `test_sqlite_vec_valid_dtypes`;
    `test_sqlite_vec_with_f16_rejected`), `tests/test_db_api.py` (~970–1007:
    the GET response's `vector_store` block asserts `sqlite-vec`/`float32`).
  - `VectorStoreMismatchError` is raised **only** by `SqliteVecStore`'s
    live-DDL check; its only other references are the re-export and
    `TestMismatchDetection`.
- **Empirical facts verified on this host during leg design** (usearch
  2.26.2, Python 3.11):
  - `Index.save(tmp)` then `os.replace(tmp, path)` over an existing sidecar
    works and `Index.restore(path)` reads the replaced file (432-byte
    8-dim/2-vector index). `restore` loads into memory (`view=False`
    default), so no file handle stays open on the sidecar.
  - `Index.restore` on a **garbage** file raises `ValueError("Not a dense
    USearch index!")`; on a **truncated** file `RuntimeError("Failed to pull
    nodes from the stream")`; on an **empty** file `ValueError("End of file
    reached!")`. Three different exception types for one condition — the
    store must catch `Exception`, not a specific class.
  - A `vec0` virtual table **cannot be dropped without the extension
    loaded** (`DROP TABLE IF EXISTS kb_vectors` → `OperationalError: no such
    module: vec0`); the shadow tables (`kb_vectors_info/_chunks/_rowids/
    _vector_chunks00`) stay too. Every other statement on that connection
    works. Consequence: the v41 block must **not** try to drop `kb_vectors`.
    A dev database that opened the sqlite-vec store between Leg 4 and this
    leg (the delete routes are the only production path that opens a store)
    keeps an inert `kb_vectors` table forever; no release ever shipped it.
- **Three conditions recorded at the flight-end review** for a `usearch`
  decision, all carried by this leg: (1) `flush`/`rebuild_from` call
  `index.save(path)` directly — a kill mid-save destroys the last good
  generation; (2) `_ensure_loaded` lets `Index.restore`'s raw error escape,
  so a corrupt sidecar is not a `VectorStoreStaleError` and the KB is never
  marked stale; (3) `delete_kb` pops the in-memory entry and unlinks the
  sidecar **before** its first `write_transaction`, so a caller who nests it
  inside their own transaction gets the re-entry `RuntimeError` only after
  the mutation has happened.
- **DD-9 "the dispatcher keeps its shape"**: `_build_store` stays the named
  seam AC-11's tests monkeypatch; it simply has one branch.
- **`i8` stays a valid usearch dtype**, not the default — the store supports
  it natively, the benchmark's two surviving cells measure it, and nothing
  is gained by deleting a working code path. The operator's chosen dtype is
  the **default** (`f16`), and `VECTOR_STORE_KEY` records are validated
  against `("f16", "i8")`.
- **Squawk 0049** (`squawks/0049-drop-hf-xet-from-closure.md`) is completed
  by this leg: mechanism `[tool.uv] exclude-dependencies = ["hf-xet"]`
  (fallback if `uv lock` refuses the key: `override-dependencies = ["hf-xet ;
  python_version < '0'"]`), `uv.lock` regenerated, the `"_hf_xet*"`
  `upx_exclude` entry removed. `huggingface_hub` imports `hf_xet` lazily
  inside its download path only; the app forces `HF_HUB_OFFLINE=1`.
- **Behavior test**: none. No operator-visible surface; the Windows frozen
  run is the real-environment proof and is the Flight Director's.

## Inputs

- Flight log: "DD-9 decision checkpoint (2026-09-15)" entry; `## Store
  Benchmark`; "flight-end review, cycle 1" conditions list.
- Flight DD-3 (registry table moves to v41 if usearch wins; `rebuild_from`),
  DD-9 (removal list), DD-10 (the security-model paragraph to retire),
  DD-11 (gate enumerations to update), DD-13 (write-lock rule).
- `squawks/0049-drop-hf-xet-from-closure.md`.
- Windows installer size baseline: **141,827,664 bytes** (squawk 0049's
  Verification line).

## Outputs

- `sqlite-vec` gone from `pyproject.toml`, `uv.lock`, the spec, both CI
  lanes, `diagnostics.py`, `the_one/vectors/`, `scripts/`, `tests/`, docs.
- `hf-xet` gone from `uv.lock` and the spec; squawk 0049 `completed`.
- `CURRENT_VERSION = 41`; `kb_vector_index` created by the migration; the
  store's `open()` issues no DDL.
- `VectorStoreSettings` default `usearch`/`f16`; `backend` is
  `Literal["usearch"]`.
- `UsearchStore`: atomic save, corrupt-sidecar → stale, `delete_kb` guard-
  first; tests for each.
- `run_doctor`: eight gates, four frozen-only; docstring, docs and
  `agents.md` table agree.
- `pip-audit` result and the `uv.lock` diff summary in the flight log.
- Flight Director's half: frozen `fly execute` → `RESULT: PASS`, `usearch:
  OK`, `fts5: OK`, `embedding model: OK`, no `sqlite-vec:` line; installer
  size recorded against the baseline; `_hf_xet*` and `vec0*` absent from
  the bundle listing.

## Acceptance Criteria

- [x] AC-1 **Closure.** `pyproject.toml` no longer lists `sqlite-vec`; the
      candidate comment block is rewritten for one backend (usearch +
      numkong, why numkong stays); a `[tool.uv]` table excludes `hf-xet`.
      `uv lock` succeeds; `grep -c 'name = "sqlite-vec"' uv.lock` and
      `grep -c 'hf-xet' uv.lock` are both 0; `uv export --no-dev
      --no-emit-project --extra gui --extra all-llms --format
      requirements-txt` contains neither name. `usearch`, `numkong`,
      `numpy`, `model2vec` remain in the export.
- [x] AC-2 **Audit.** `pip-audit -r <that export>` (the `pr-lint.yml` job's
      exact closure) reports no vulnerabilities. If a finding fires, Leg
      2's precedent applies: raise the affected package's floor in
      `pyproject.toml`, re-lock, re-audit; if the floor cannot be raised
      (no fixed release, or the fix moves a major version), stop and
      report `[BLOCKED:pip-audit]` with the id — a log entry alone does
      not clear this criterion. The command and its summary line are
      pasted into the flight-log entry either way.
- [x] AC-3 **Tree.** `the_one/vectors/sqlite_vec_store.py` is deleted;
      `VectorStoreMismatchError` is deleted from `_store.py` and
      `__init__.py`'s `__all__`; `_build_store` constructs `UsearchStore`
      only (no `sqlite-vec` branch, no lazy import of a deleted module);
      `grep -rn -i "sqlite.vec\|SqliteVec\|vec0" the_one/ scripts/ tests/
      packaging/ ci/ .github/ Makefile pyproject.toml` returns only
      historical references inside `the_one/agents.md` prose: (i) the
      "Knowledge storage" removal note, (ii) the packaging "do not swap for
      `collect_data_files`" lesson reworded to stand without the package,
      (iii) the `report-what-you-got` rationale paragraph at
      `the_one/agents.md:~526`, which cites the Flight 1 debrief and is
      left verbatim — nothing in code, config, CI or the spec.
      `docs/kb-architecture.md:10` ("`sqlite-vec`/`usearch` over LanceDB")
      is a superseded pre-mission survey (squawk 0048's "amend, don't
      retire" pattern): append one clause to that sentence — "`sqlite-vec`
      was removed in Flight 2 Leg 6 after the benchmark; `usearch` is the
      shipped store" — and touch nothing else in that file.
- [x] AC-4 **Settings.** `VectorStoreSettings.backend` is `Literal["usearch"]`
      with default `"usearch"`; `dtype` defaults to `"f16"`; `f16` and `i8`
      validate, `float32`/`int8` raise; `load_vector_store_settings` on an
      absent record returns `usearch`/`f16`; a stored `{"backend":
      "sqlite-vec", …}` record raises (the existing invalid-record test
      re-targeted). `GET /api/knowledge-settings` on a fresh DB returns
      `vector_store.backend == "usearch"` and `dtype == "f16"`.
- [x] AC-5 **v41 migration.** `CURRENT_VERSION = 41`. The block, in the
      house shape (`if version < 41:` … `INSERT OR IGNORE INTO
      schema_version (version) VALUES (?)`, `(41,)` … `commit` … `version =
      41`), does exactly two things: `CREATE TABLE IF NOT EXISTS
      kb_vector_index (kb_id TEXT PRIMARY KEY, path TEXT NOT NULL, count
      INTEGER NOT NULL, generation INTEGER NOT NULL, dtype TEXT NOT NULL,
      dim INTEGER NOT NULL, updated_at TEXT NOT NULL)` — byte-for-byte the
      column set `UsearchStore.open()` created in Leg 4 so a database where
      the store already made the table passes through unchanged — and
      `DELETE FROM app_metadata WHERE key = 'knowledge.vector_store' AND
      json_extract(value, '$.backend') = 'sqlite-vec'` (purges a record only
      a test or benchmark could have written; a `usearch` record is kept).
      It must **not** touch `kb_vectors` (cannot be dropped without the
      module — see Context). `UsearchStore.open()` no longer executes any
      DDL (it still resolves `data_dir` and creates the `vectors/`
      directory). Tests in `tests/test_db_migration.py`: (a) a fresh DB
      lands v41 with `kb_vector_index` in `sqlite_master` and exactly that
      column set (the `test_v40_upgrade_from_fresh_db` shape, membership
      style); (b) a v40 database in which the store already created
      `kb_vector_index` with a row upgrades to 41 with the row intact; (c) a
      v40 database whose `app_metadata` holds a `sqlite-vec` vector-store
      record has the row removed after `ensure_schema`, while a `usearch`
      record survives; the existing `assert CURRENT_VERSION == 40` in the
      v40 fresh-DB test becomes `>= 40` or moves to the v41 test (house
      pattern: the newest block's test pins the exact value).
- [x] AC-6 **Atomic sidecar save.** `flush` and `rebuild_from` save to a
      temporary path inside the same directory (`<path>.tmp` — derived from
      `_path_for`'s validated result so the containment assert still
      covers it), then `os.replace(tmp, path)`, then upsert the registry
      row; on any failure before the replace the temporary file is removed
      (best-effort, in `finally`) and the previous sidecar is untouched.
      On failure `entry.dirty` stays `True` (the `= False` line is only
      reached after the registry row lands) so the next `flush` or
      `close()` retries — state this in `flush`'s docstring, together with
      the pre-existing caveat that the registry write after the replace is
      a separate step: a crash between the two leaves the sidecar one
      generation ahead of the registry, which `_ensure_loaded` reports as
      stale (fail-safe, recoverable by `rebuild_from`). Tests: a `flush`
      whose `Index.save` raises (monkeypatched) leaves the previous
      sidecar restorable at its previous `count`, the registry row at its
      previous `generation`, no `.tmp` left behind, `entry.dirty` still
      `True`, and a second `flush` after the monkeypatch is removed
      succeeds and advances `generation`; the
      `write_transaction` re-entry test for `flush` (already covered by
      `TestNoReentry` for `upsert`) needs no change.
- [x] AC-7 **Corrupt sidecar → stale.** `_ensure_loaded` wraps
      `Index.restore` in `try/except Exception`; a failure sets
      `entry.stale = True` and raises `VectorStoreStaleError` chained
      `from` the original, with the message naming the path and the
      original exception class. Tests, one each: garbage bytes, a truncated
      copy of a real sidecar, an empty file — every read/write on that KB
      raises `VectorStoreStaleError`, and `rebuild_from` recovers (query
      answers again, registry `count` correct).
- [x] AC-8 **`delete_kb` guard-first.** The `write_transaction` that
      deletes the registry row runs **first**; only after it commits does
      the method pop the in-memory entry and unlink the sidecar. Test:
      `delete_kb` called from inside a caller's `write_transaction` raises
      `RuntimeError` and afterwards the sidecar file still exists, the
      registry row is still present, and `count(kb)` still answers through
      the same store instance.
- [x] AC-9 **Doctor.** `_probe_sqlite_vec` is deleted; `run_doctor`'s
      `gates` list has eight entries in the existing order minus
      `sqlite-vec`; the docstring says eight gates, four frozen-only
      (desktop shell, llm providers, model catalog, usearch) and four
      unconditional; `_vector_probe_outcome`'s docstring and the comments
      around the gate list no longer say "both"/"two vector-store probes".
      `tests/test_doctor.py::TestProbeSqliteVec` is deleted; a new test
      asserts `"sqlite-vec:"` does **not** appear in `run_doctor` output
      (the by-name inverse of the line-present tests, so a stray re-add is
      caught); `TestProbeUsearch` and `TestUsearchAcceleration` pass
      unchanged.
- [x] AC-10 **Spec and CI lanes.** `packaging/windows/the-one.spec`: the
      `sqlite_vec_bins` collection, its `binaries` entry, and the sqlite-vec
      comment block (158–190) are removed — **keep** a two-line note that
      `collect_data_files` silently drops `.so` files (the lesson is
      general; cite the Flight 1 log rather than sqlite-vec); `upx_exclude`
      loses `"vec0*"` and `"_hf_xet*"` (four entries remain: `compiled*`,
      `_numkong*`, `tokenizers*`, `_safetensors_rust*`) and its comment is
      updated. `ci/tasks/windows-installer-build.yml` and
      `.github/workflows/windows-installer.yml` drop only the `sqlite-vec:
      OK` needle; `usearch: OK`, `fts5: OK`, `embedding model: OK` stay.
- [x] AC-11 **Benchmark keeps working on two cells.** `scripts/bench_vector_store.py`:
      `ALL_CELLS` is the two usearch cells, `_BYTES_PER_VECTOR` likewise,
      the `SqliteVecStore` import, the script's local `_build_store`
      sqlite-vec return (~438–441), both `if backend == "sqlite-vec"`
      branches (~517/540) and the now-always-true `if backend ==
      "usearch": … else:` blocks (~532–538, ~546–556) are gone — collapsed
      to straight-line usearch code, never left as guards that cannot be
      false; the `sqlite_vec_version` host fact is gone, the
      module docstring and usage examples say two cells; `Makefile`'s
      target help says two cells. `tests/test_bench_vector_store.py` is
      re-targeted to `usearch:f16` (and `usearch:i8` where a second cell is
      needed), keeping every test's intent (the AC-7 no-raw-import scan now
      lists only `usearch`); `PYTHON=.venv/bin/python bash
      scripts/run-tests.sh tests/test_bench_vector_store.py -x --timeout
      120` is green and `make bench-vector-store` prints a two-row table.
- [x] AC-12 **Vector-store tests re-targeted.** `tests/test_vector_store.py`:
      `CELLS` is the two usearch cells; `_build` has one branch;
      `TestProtocolSatisfaction` asserts on `UsearchStore` only;
      `TestSqliteVecOpenBehavior` and `TestMismatchDetection` are deleted
      (their usearch analogue — registry dtype/dim mismatch → stale — is
      already `TestUsearchStaleness`); the module docstring's `vec0`
      table-wide-rowid note is rewritten to state the disjoint-id-range
      convention on its own merits (ids come from one global
      `kb_chunks.id` sequence). `tests/test_vectors_dispatch.py`: the
      default-when-absent test asserts `UsearchStore`/`f16`; the "returns
      sqlite-vec when the record says so" test becomes "a stored `i8`
      record builds an `i8` store"; the remaining five pass unchanged.
- [x] AC-13 **Docs.** `README.md:52` and `the_one/main.py` usage text say
      "vector store" (singular); `docs/windows-install.md` says the doctor
      loads the bundled vector index (`usearch`); `SECURITY-MODEL.md`'s
      "Native SQLite extension loading" paragraph is replaced by a short
      note that **no** native SQLite extension is loaded anywhere in the
      app (the Flight 2 Leg 4 `sqlite-vec` backend was removed in Leg 6;
      `usearch` is an ordinary imported extension module, not a SQLite
      extension, and `enable_load_extension` is never called);
      `the_one/agents.md`: the "Knowledge storage" seam paragraphs describe
      one backend and note the removal + the inert-`kb_vectors` fact, the
      Diagnostics section says eight gates (table row removed, "Seven of
      the nine" → the right count of eight, "both vector-store probes" →
      the one), the packaging notes drop `sqlite_vec_bins` and say four
      `upx_exclude` entries; `missions/24-knowledge-bases/mission.md`
      Known Issues: the dead-weight item is updated (hf-xet removed by this
      leg; numkong's `.pyd` remains, unchanged reason); `squawks/0049-…md`
      gets Corrective Action, Verification results and Sign-Off, status
      `completed` (commit ref filled at the commit step).
- [x] AC-14 **Gates.** `ruff check the_one/ tests/ scripts/` and `ruff
      format --check the_one/ tests/ scripts/` clean; `tests/test_db_write_lock.py`'s
      source scan still passes (no `commit()`/`rollback()` outside the two
      allowed files — `os.replace` is not a commit); `make test-unit` green
      (the Developer runs the scoped files during the leg and the whole
      unit gate once at leg end, count and wall time recorded).
- [x] AC-15 **Frozen run (Flight Director's half, after the code review).**
      `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i
      repo=. -o installer=./out` on the reviewed tree prints `RESULT:
      PASS`, `usearch: OK`, `fts5: OK`, `embedding model: OK`, and no
      `sqlite-vec:` line; the installer size is recorded against
      141,827,664 bytes; the `dist/the-one/` listing (or the task's output)
      shows no `vec0*` and no `_hf_xet*` file. Recorded in the flight log
      with the build number. (Concourse build 606735: frozen doctor
      `RESULT: PASS`, eight gates — `usearch: OK`, `fts5: OK`, `embedding
      model: OK`, no `sqlite-vec:` line; bundle free of `hf_xet*`/`vec0*`;
      installer `the-one-setup-0.8.1.exe` = 134,790,292 bytes, baseline
      141,827,664 — −7,037,372 bytes.)

## Verification Steps

1. AC-1: `uv lock` (or `uv lock --check` after the Developer's regeneration),
   then the three `grep -c` counts and the `uv export … | grep -E
   'sqlite-vec|hf-xet'` (expect no output) and `| grep -E
   '^(usearch|numkong|numpy|model2vec)=='` (expect four lines).
2. AC-2: `uv export --no-dev --no-emit-project --extra gui --extra all-llms
   --format requirements-txt > /tmp/rel.txt && .venv/bin/pip-audit -r
   /tmp/rel.txt`. Paste the summary line.
3. AC-3: the `grep -rn` in the criterion; `python -c "import
   the_one.vectors as v; print(v.__all__)"` shows no `Mismatch`.
4. AC-4/AC-12: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
   tests/test_knowledge_settings.py tests/test_vectors_dispatch.py
   tests/test_vector_store.py tests/test_db_api.py -x --timeout 60`.
5. AC-5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
   tests/test_db_migration.py tests/test_kb_chunks.py
   tests/test_kb_types_consistency.py -x --timeout 60`; then an ad-hoc
   check on a scratch copy of a v40 database (the migration tests cover
   it; do not touch the operator's data dir).
6. AC-6/7/8: the new tests in `tests/test_vector_store.py` (name them
   `TestAtomicSave`, `TestCorruptSidecar`, `TestDeleteKbGuardFirst`).
7. AC-9: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
   tests/test_doctor.py tests/test_doctor_embedding_model.py -x --timeout
   60`; `.venv/bin/the-one doctor` on this host prints eight gate lines and
   `RESULT: PASS`.
8. AC-10: `python -c "import ast,sys; ast.parse(open('packaging/windows/the-one.spec').read())"`
   (the spec is Python — a syntax check is the most the Linux host can do;
   the frozen run is AC-15); `grep -n "sqlite-vec" ci/ .github/` empty.
9. AC-11: the scoped test file + `make bench-vector-store`.
10. AC-13: `grep -rn -i "vector stores\|both bundled vector\|nine gates\|sqlite-vec"
    README.md docs/ the_one/main.py the_one/agents.md SECURITY-MODEL.md` —
    only the explanatory removal notes remain.
11. AC-14: the two ruff commands and `make test-unit` (once, foreground,
    alone — record the count).
12. AC-15: Flight Director, after `[HANDOFF:confirmed]`.

## Implementation Guidance

Order matters: closure first (so every later test runs against the real
post-removal environment), then code, then tests, then docs.

1. **Closure.** Edit `pyproject.toml`: delete `"sqlite-vec>=0.1.6"`, rewrite
   the comment block (71–84) for one backend — keep the sentence that the
   frozen-only `doctor` probe is the regression gate for the native payload
   surviving the freeze, and say numkong stays because `usearch/__init__.py`
   imports it unconditionally (the spec's note at 191–219 is the long
   form). Add, next to the other `[tool.*]` tables:
   ```toml
   [tool.uv]
   # Squawk 0049 / M24 F02 L06: huggingface-hub pulls hf-xet (a Rust Hub
   # transfer accelerator) on x86_64/arm64. The app never downloads from
   # the Hub — the embedding model is package data and HF_HUB_OFFLINE=1 is
   # forced — and huggingface_hub imports hf_xet lazily inside its download
   # path only, so excluding it is safe and trims ~4 MB from the bundle.
   exclude-dependencies = ["hf-xet"]
   ```
   Run `uv lock`. If uv refuses `exclude-dependencies`, use
   `override-dependencies = ["hf-xet ; python_version < '0'"]` and say so
   in the flight log. Then `uv sync --extra dev --extra all-llms` (or `pip
   uninstall sqlite-vec` in the venv) so the venv matches — `import
   sqlite_vec` must fail on this host before the test work starts,
   otherwise a leftover import passes silently.
2. **Delete the loser.** `git rm the_one/vectors/sqlite_vec_store.py`.
   `_store.py`: drop `VectorStoreMismatchError`; rewrite the module
   docstring's "vec0 rowids are unique TABLE-WIDE" bullet as the disjoint-
   id convention (ids are one global sequence; a per-KB index must still
   be exercised with disjoint ranges so tests mirror production); the
   `upsert` bullet keeps "usearch.Index.add raises on a duplicate key" and
   drops the `INSERT OR REPLACE` clause; the `flush` bullet drops the
   `SqliteVecStore` sentence. `__init__.py`: one-branch `_build_store`,
   `__all__` without the mismatch error, docstring "lazy-importing each
   backend" → "lazy-importing the backend (one today; the seam keeps its
   shape for a future second one)".
3. **Settings.** `VectorStoreSettings`: `backend: Literal["usearch"] =
   "usearch"`, `dtype: str = "f16"`, `_VECTOR_STORE_DTYPES = {"usearch":
   ("f16", "i8")}`; docstring: the record is the DD-9 outcome; sqlite-vec
   was removed in Leg 6.
4. **Migration.** `schema.py`: `CURRENT_VERSION = 41`; append the v41 block
   after the v40 stamp (`version = 40`, line 2545) with a comment citing DD-3 ("store-
   owned until the decision; migration-owned after") and the vec0 fact
   from Context so nobody adds a `DROP TABLE kb_vectors` later. Then
   remove the DDL from `UsearchStore.open()` and update its module
   docstring (lines 5–8).
5. **Store hardening** (`usearch_store.py`):
   - Add `_tmp_path_for(kb_id) -> Path` returning `_path_for(kb_id)` with
     suffix `.usearch.tmp` (same directory; `_path_for` already asserted
     containment). Add a private `async def _save_atomically(self, index,
     kb_id) -> tuple[Path, int]` used by both `flush` and `rebuild_from`:
     `await asyncio.to_thread(index.save, str(tmp))`, `os.replace(tmp,
     path)` (also inside `to_thread` or inline — it is a metadata op),
     return `(path, len(index))`; `finally: tmp.unlink(missing_ok=True)`.
     Only after it returns call `_upsert_registry_row`.
   - `_ensure_loaded`: `try: index = await asyncio.to_thread(Index.restore,
     str(path)) except Exception as exc: entry.stale = True; raise
     VectorStoreStaleError(self._stale_message(kb_id, f"sidecar
     unreadable ({exc.__class__.__name__}: {exc}) at {path}")) from exc`.
   - `delete_kb`: move the `async with write_transaction(self.conn):
     DELETE …` to the top of the method, then `entry = self._kbs.get(...)`
     / pop under its lock, then unlink. Keep the existing semantics that
     a KB with no entry and no file is a no-op.
6. **Doctor.** Delete `_probe_sqlite_vec` and its imports if any become
   unused (`sqlite3` is still used by `_probe_fts5` — check before
   removing). Update `_vector_probe_outcome`'s docstring, the gate-list
   comments, `run_doctor`'s docstring (eight; four frozen-only; four
   unconditional), and the `gates` list.
7. **Spec + CI.** Per AC-10. The spec is a Python file; keep its style.
8. **Benchmark.** Per AC-11. `_package_version("sqlite-vec")` host-fact
   line goes; leave `usearch_version`.
9. **Tests.** Per AC-4/5/6/7/8/9/11/12. For AC-7's truncated case, save a
   real index via `flush`, read the file, write back the first half. For
   AC-6, monkeypatch `usearch.index.Index.save` (the class attribute) to
   raise `RuntimeError("disk full (simulated)")` for the second `flush`
   only. For AC-8, the nested call is `async with write_transaction(conn):
   await store.delete_kb("kb")` inside `pytest.raises(RuntimeError)`.
10. **Docs.** Per AC-13. In `agents.md` keep the packaging lesson about
    `collect_data_files` excluding `all_suffixes()` but reword it as a
    general PyInstaller trap (cite the Flight 1 log) since the example
    library is gone.
11. **Squawk 0049.** Fill Corrective Action (mechanism used, files),
    Verification (lock/export/grep results, unit gate, pip-audit; the
    frozen-run and installer-size lines say "Flight Director, AC-15"),
    Sign-Off Reviewer/Verdict left for the review; **Status**
    `in-progress` now, `completed` at the commit step.
12. **Flight log.** Leg 6 progress entry under `## Leg Progress` with the
    `uv.lock` diff summary (packages removed: `sqlite-vec`, `hf-xet`;
    anything else that moved, by name), the pip-audit line, the unit-gate
    figures; set this leg `landed`; check it off in `flight.md`. Do **not**
    commit; do not set `landed` on the flight (the Flight Director does
    that after AC-15).

## Edge Cases

- `uv lock` may re-resolve unrelated packages when regenerating. Record
  every version that moved in the flight log; if anything other than the
  two removals moves a **major** version, stop and report
  `[BLOCKED:lock-drift]` rather than absorbing an unreviewed upgrade.
- `exclude-dependencies` removes `hf-xet` from **every** resolution,
  including dev. Fine here (nothing calls it), but state it in the comment.
- The venv on this host still has `sqlite-vec` installed until step 1's
  sync; a test that imports it would pass by accident. Uninstall first.
- `os.replace` on Windows fails if the destination is open. `Index.restore`
  does not keep the file open (verified, `view=False`), and the store never
  memory-maps — do not introduce `view=True`.
- A `.usearch.tmp` left by a crash before the replace: `_ensure_loaded`
  never reads it; the next `flush` overwrites it. No cleanup pass needed;
  note it in the docstring.
- `_probe_fts5` opens a bare `sqlite3` connection; do not remove the
  `sqlite3` import while deleting the sqlite-vec probe.
- `tests/test_bench_vector_store.py`'s AC-7 scan asserts no raw
  `sqlite_vec`/`usearch` imports in the script — keep the tuple as
  `("usearch",)`; the scan's intent (seam-only access) is unchanged.
- The migration's `json_extract` requires the JSON1 functions — built into
  every SQLite ≥ 3.38 and already relied on? If not (check for an existing
  `json_extract` in `schema.py` or the repositories), use `value LIKE
  '%"backend": "sqlite-vec"%'` — `model_dump_json()` emits no spaces, so
  match `'%"backend":"sqlite-vec"%'` **and** the spaced form; state which
  you used.
- `TestNoReentry` is parametrised over `store`; with two cells it runs
  twice — fine.
- `the_one/agents.md` line ~526 mentions sqlite-vec inside a historical
  rationale ("five same-shaped fail-opens found in one flight"). That is
  a record of the Flight 1 debrief; leave it.

## Files Affected

- `pyproject.toml`, `uv.lock` — closure
- `the_one/vectors/sqlite_vec_store.py` — deleted
- `the_one/vectors/_store.py`, `the_one/vectors/__init__.py`,
  `the_one/vectors/usearch_store.py`
- `the_one/knowledge/settings.py`
- `the_one/db/schema.py`
- `the_one/diagnostics.py`, `the_one/main.py`
- `packaging/windows/the-one.spec`
- `ci/tasks/windows-installer-build.yml`, `.github/workflows/windows-installer.yml`
- `scripts/bench_vector_store.py`, `Makefile`
- `tests/test_vector_store.py`, `tests/test_vectors_dispatch.py`,
  `tests/test_knowledge_settings.py`, `tests/test_db_api.py`,
  `tests/test_doctor.py`, `tests/test_db_migration.py`,
  `tests/test_bench_vector_store.py`
- `README.md`, `docs/windows-install.md`, `docs/kb-architecture.md` (one
  clause), `SECURITY-MODEL.md`, `the_one/agents.md`
- `missions/24-knowledge-bases/mission.md` (Known Issues),
  `squawks/0049-drop-hf-xet-from-closure.md`
- `missions/24-knowledge-bases/flights/02-storage-and-embedding-foundation/flight-log.md`, `flight.md`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified (AC-15 is the Flight Director's)
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (the Flight Director sets `completed` after review + AC-15)
- [x] Check off this leg in flight.md
- [x] Do NOT commit — the flight-end review, the frozen run and the commit follow

## Citation Audit

Design review cycle 1 (Developer, Sonnet, 2026-09-15) — `approve with
changes`. Every line citation checked was exact or within a few lines
(the one drift: the v40 stamp is line 2545, not ~2547 — fixed). The
reviewer independently reproduced the design-time empirical claims
(`json_extract` available on this host's SQLite 3.45.1; `model_dump_json()`
emits no spaces; `.usearch.tmp` suffixing works; `uv` 0.10.0 carries both
`exclude-dependencies` and `override-dependencies`; `save_vector_store_settings`
has no production caller) and found no correctness defect in the AC-5–AC-9
hardening design. Two mediums, both fixed in the artifact: AC-3's grep
exception list omitted the `agents.md:~526` rationale paragraph the Edge
Cases already said to leave (now a named exception); `docs/kb-architecture.md:10`
names both stores and was in AC-13's grep scope with no instruction (now a
one-clause amendment per squawk 0048's pattern, in Files Affected). Two
questions answered in AC-2 (a pip-audit finding must be fixed by raising
a floor, else `[BLOCKED:pip-audit]` — Leg 2's precedent, not a log entry)
and AC-6 (`entry.dirty` stays `True` on a failed save so the next flush
retries; the sidecar-ahead-of-registry crash window is a documented
fail-safe). Suggestion applied: the benchmark's vestigial usearch/else
branches are collapsed (AC-11). No second review cycle — the changes are
clarifications, not design changes.
