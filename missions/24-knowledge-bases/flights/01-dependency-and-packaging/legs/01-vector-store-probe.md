# Leg: vector-store-probe

**Status**: completed
**Flight**: [Dependency and Packaging Decision](../flight.md)

## Objective

Add both vector-store candidates to the runtime dependency closure and prove
each one loads and functions inside the frozen Windows bundle, via permanent
`doctor` probes — establishing the whole frozen-build verification chain before
Leg 2 commits anything irreversible.

## Context

**From the flight's design decisions:**

- DD-3 — `sqlite-vec` and `usearch` are evaluated as **peers**. This leg answers
  only what the apparatus can observe: *does each candidate package and load in
  the frozen Windows bundle*, plus its measured wheel-bytes cost. The choice
  between them is Flight 2's, made with a seam and a real corpus. `sqlite-vec`
  performs exhaustive brute-force KNN with no ANN index; `usearch` provides HNSW.
- DD-4 — verification runs via `fly execute -c ci/tasks/windows-installer-build.yml
  -i repo=. -o installer=./out` (`ci/README.md:106`), which freezes on the real
  `windows-worker` and runs `dist\the-one\the-one.exe doctor` as a gate that
  throws on non-zero (`ci/tasks/windows-installer-build.yml:47-49`).
- DD-5 — the probes are permanent regression gates, not scaffolding.
- DD-6 — this leg builds **no seam and no abstraction**. The probes call each
  library directly. The storage seam is Flight 2's.
- DD-7 — the vector-store probes gate **only when frozen**. `enable_load_extension`
  genuinely varies across Python builds, so a dev-host failure would be a false
  alarm.

**Why both candidates stay in the closure during this leg:** each must load or
the build legitimately fails — you do not ship a dependency that cannot load.
Whichever loses the Flight 2 decision is removed from the closure then. The only
pure waste in the interim is `numkong` (usearch's native dep); `numpy` arrives
with Leg 2's embedding backend regardless.

**Codebase patterns this leg must follow:**

- `ProbeResult` is a 3-field dataclass — `name`, `ok`, `detail`
  (`the_one/diagnostics.py:44-51`).
- **These probes must never raise.** `_probe_model_catalog` states it as an
  explicit contract in its docstring (`the_one/diagnostics.py:247`): *"Never
  raises — all exceptions are caught."* Note this is not universal —
  `_probe_interpreter` (`:276-290`) catches only `FrozenInterpreterError` — but
  it is the right contract here, because an escaping exception would take down
  `doctor` entirely and break the CI gate for reasons unrelated to the library
  under test.
- The frozen-only idiom is implemented **inside** each probe, not by `run_doctor`,
  which unconditionally ANDs every gate (`all_ok = all(g.ok for g in gates)`).
  The idiom: on failure, `return ProbeResult(name, False, …)` when `is_frozen()`,
  else `return ProbeResult(name, True, f"skipped — {reason}")`.
- `_probe_model_catalog` (`the_one/diagnostics.py:230-273`) is the closest
  template — it exists because an import-only check misses a data file that was
  tree-shaken out of the bundle, and it *forces an actual resolution* rather than
  trusting an import. These probes do the same for a loadable native library.

## Inputs

- `mission/24-knowledge-bases` at `e26c334`, flight branch cut from it
- Concourse reachable, authenticated, `windows-worker` `state: running`
- `uv` 0.10.0 on PATH
- `the_one/diagnostics.py` with five existing gates and no vector-store probe
- `tests/test_doctor.py` asserting `run_doctor(out=buf) == 0` on the host
- No `sqlite-vec`, `usearch`, `numpy` or `numkong` anywhere in `uv.lock`

## Outputs

- Both candidates in `[project] dependencies` with `uv.lock` regenerated
- Two new probes in `the_one/diagnostics.py`, registered in `run_doctor`'s gates
- Tests covering each probe's pass, fail, and skipped-when-unfrozen paths
- PyInstaller spec carrying whatever collection each library needs, plus
  `upx_exclude` entries for their native binaries
- A green frozen Windows build with both probes reporting OK
- Measured wheel-bytes cost recorded in the flight log

## Acceptance Criteria

- [x] `sqlite-vec` and `usearch` are declared in `[project] dependencies` and `uv.lock` is regenerated to match
- [x] Two probes exist following the `ProbeResult` pattern, are registered in `run_doctor`'s gate list, and neither can raise — each catches every exception and reports through `ProbeResult`
- [x] The `sqlite-vec` probe opens a bare `sqlite3` connection, enables extension loading, loads the extension, and completes a real vector round-trip — insert then nearest-neighbour query — asserting a concrete returned value, not merely absence of exception
- [x] The `usearch` probe builds an in-memory index, adds a vector under a known id, searches, and asserts that id comes back
- [x] Both probes always attempt the real work, and downgrade only *failure* when unfrozen — matching the house pattern, where a working host reports a success detail and a broken host reports `ok=True` with a `skipped —` detail. They never skip the work merely because the host is unfrozen
- [x] `make test-unit` is green, and `tests/test_doctor.py` covers each probe's pass, fail, and skipped paths
- [x] `the-one.exe doctor` returns `RESULT: PASS` in a bundle frozen on `windows-worker`, with both probe lines present in the output — *met on the Leg 1 frozen run and re-confirmed on both Leg 2 runs*
- [x] Both CI lanes assert the new probe lines **by name**, not merely on the aggregate result — `.github/workflows/windows-installer.yml`'s packaged-smoke greps, and the Concourse task in `ci/tasks/windows-installer-build.yml`. The Concourse lane currently reads only `doctor`'s exit code, which means DD-4's designated apparatus could not detect a probe silently dropped from the gates list — the precise failure DD-5 exists to prevent
- [x] `pip-audit` is clean against the widened release closure, checked locally before the PR rather than discovered by the pre-merge gate
- [x] The measured added-package list and win_amd64 wheel bytes are recorded in the flight log, summed from the `size` fields of the `win_amd64` wheel entries in the regenerated `uv.lock`

## Verification Steps

- **Dependencies**: `grep -E 'sqlite-vec|usearch' pyproject.toml` and `grep -cE '^name = "(sqlite-vec|usearch|numpy|numkong)"' uv.lock`
- **Probes never raise**: unit test that monkeypatches the underlying library call to raise, asserting `run_doctor` still returns an int and emits a FAIL line rather than propagating
- **Round-trips**: unit tests asserting the `sqlite-vec` query returns the inserted row and the `usearch` search returns the known id
- **Frozen gating**: unit tests monkeypatching `diagnostics.is_frozen` to both values, asserting `ok=True` + `skipped` when unfrozen and `ok=False` when frozen-and-broken
- **Unit gate**: `make test-unit` — baseline ~455s / 3,910 tests; record the delta
- **Frozen build**: `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out` from a clean tree; the task's own step 4/6 gate throws if `doctor` exits non-zero. Capture the full `doctor` stdout into the flight log.
- **Release closure audit**: `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt > /tmp/rr.txt && pip-audit --disable-pip -r /tmp/rr.txt` — the same command `.github/workflows/pr-lint.yml:62-69` runs on every PR, which **fails on any finding**. Run it locally; do not discover findings at the gate.
- **Named-line assertions**: run `doctor` and confirm both probe lines appear; then confirm each CI lane greps for them, by inspecting the two workflow/task files after editing
- **Wheel cost**: sum the `size` fields of the `win_amd64` wheel entries added to `uv.lock`. Take the **cp311** rows throughout — `uv.lock` carries cp311/cp312/cp313 `win_amd64` entries per package and cp311 is what both installer paths build on. Expected from PyPI today: `sqlite_vec` 292,804 + `usearch` (cp311) 343,513 + `numkong` (cp311) 492,060, plus `numpy` (cp311)

## Implementation Guidance

1. **Add the dependencies, regenerate the lock**
   - Append both to `[project] dependencies` in `pyproject.toml` (the list ends at line 71), each with a comment saying *why* it is present, matching the existing house style where every dependency line carries its rationale.
   - Regenerate `uv.lock` with `uv`. Expect `numpy` and `numkong` to arrive transitively via `usearch`.

2. **Write the `sqlite-vec` probe**
   - Use a **bare `sqlite3.connect(":memory:")`**, not `aiosqlite` and not the app's connection factory. Three reasons: every existing probe is synchronous while the app's DB layer is async; `aiosqlite`'s extension methods are thin proxies onto the same `sqlite3.Connection`, so a bare connection tests the identical C-level capability; and the app's factory would create directories and WAL sidecars in the operator's data dir as a side effect of running a diagnostic.
   - Guard `enable_load_extension` with `hasattr` before calling it — it is compiled out on some Python builds, and its absence must read as `skipped` on a dev host and as a failure only when frozen.
   - Re-disable extension loading after the probe completes.
   - **`sqlite_vec.loadable_path()` returns an extensionless path** (`<pkgdir>/vec0`); SQLite appends `.dll`/`.so`/`.dylib` itself. An `os.path.exists()` check against it therefore *always* reports missing — do not write one. Emit the path plus the caught `sqlite3.OperationalError`, which already names the file it actually resolved.
   - **The table DDL and the bind format.** Create with
     `CREATE VIRTUAL TABLE vt USING vec0(embedding float[N])`. Bind the query
     vector with `sqlite_vec.serialize_float32(v)` — the package ships that
     helper — or as a JSON string. **Never bind a plain Python list**: it raises
     `sqlite3.ProgrammingError: Error binding parameter 1: type 'list' is not
     supported`.
   - **vec0 KNN requires an explicit `k` constraint**: omitting both `k = ?` and `LIMIT` raises `OperationalError: A LIMIT or 'k = ?' constraint is required on vec0 knn queries`. Prefer `k = ?` — `LIMIT`-only needs SQLite ≥ 3.41. `distance` must be selected explicitly; `SELECT *` returns only `rowid` and the vector column. A verified working shape: `SELECT rowid, distance FROM vt WHERE embedding MATCH ? AND k = ?`.
   - **Record for Flight 2, do not act on it here**: the app's real connection factory never enables extension loading, so this probe proves *capability*, not *integration*. Wiring the load into the app's own connections is Flight 2's work.

3. **Write the `usearch` probe** — build a tiny in-memory index, add one vector under a known id, search, and assert that id returns. Three API facts the obvious implementation gets wrong:
   - `Index()` constructs fine with the default `ndim=0`, but the first `add` then raises `ValueError: The number of vector dimensions doesn't match!`. Pass `Index(ndim=N)` explicitly.
   - `Index.add()` and `Index.search()` assert `isinstance(vectors, np.ndarray)` — a plain Python list raises `AssertionError: Expects a NumPy array`. Pass `np.asarray(v, dtype=np.float32)` to both.
   - Keys come back as `np.uint64` (via `matches.keys`, `matches[0].key`, or `matches.to_list()`), and the index's default `dtype` is `ScalarKind.BF16` — so assert on the **key**, never on the returned vector.
   - **Surface whether numkong actually loaded.** `usearch/__init__.py:15-32` wraps the numkong import in `try: … except ImportError: pass`, so a frozen bundle missing `numkong._numkong` still imports and still answers searches via dynamic dispatch — the probe would report a plain `OK` over a degraded bundle. Put `usearch.compiled.USES_NUMKONG` (or `hardware_acceleration()`) into the detail string so the doctor line makes that visible. Same fail-open class DD-5 legislates against, one layer down.
   - **Do not call `usearch.sqlite_path()`.** `usearch/__init__.py` ships a `BinaryManager` that downloads `usearch_sqlite.{dll,so,dylib}` from GitHub releases at runtime. Normal `Index` usage never touches it, and this probe must not either — a probe that can satisfy itself by downloading is the same fail-open DD-5 wrote an invariant against.

4. **Register both in `run_doctor`** — add to the gates list alongside the existing five. Keep the emitted names short and stable; CI greps them by name.

5. **Wire the PyInstaller spec.** The answer is settled — do not re-derive it. The Windows native set is `sqlite_vec/vec0.dll`, `usearch/compiled.cp311-win_amd64.pyd`, and `numkong/_numkong.cp311-win_amd64.pyd`.
   - **Only `sqlite_vec` needs a spec entry.** `usearch.compiled` and `numkong._numkong` are ordinary importable extension modules, so PyInstaller's module graph collects them with no configuration — verified against a real no-hook onedir build.
   - **`collect_data_files` does not work for `vec0` and must not be used.** All three of `collect_data_files('sqlite_vec')`, the same with `includes=['*.so','*.dll','*.dylib']`, and plain `collect_dynamic_libs('sqlite_vec')` return `[]`. Two independent causes: `collect_data_files` unconditionally appends `**/*<suffix>` for every `importlib.machinery.all_suffixes()` to its excludes, and excludes override includes — so `.so` can never be collected as data; and `collect_dynamic_libs`'s default `PY_DYLIB_PATTERNS` expects `lib*.so`, while the file is `vec0.so`. The blocked suffix set is `.so`, `.abi3.so` and `.cpython-311-*.so` — it never contains `.dll` or `.dylib` — so a `collect_data_files` entry would appear to work on Windows and macOS while silently shipping nothing **on Linux**.
   - **Use** `collect_dynamic_libs("sqlite_vec", search_patterns=["*.dll", "*.dylib", "*.so"])` and put the result in **`binaries`**, not `datas`. The pattern to copy is `winpty_bins` — the `collect_dynamic_libs` call at `the-one.spec:90` **and** its wiring as `*winpty_bins` in the shared `binaries` list at `:182`, which reaches both `a_cli` and `a_gui` through `_analysis_kwargs` (`:203`). Add to that shared list, not to one `Analysis`. Do **not** copy `seed_datas`. Routing through `binaries` also submits the library to binary-dependency scanning, which it needs for the MSVC runtime and which `datas` skips entirely.
   - **Write the patterns portably** even though this spec lives under `packaging/windows/`. The mission requires all three platforms to work, and a Windows-only-by-accident entry is exactly the silent asymmetric failure this flight exists to prevent.
   - Add all three native artifacts to `upx_exclude` (currently `[]` at `the-one.spec:274`) — `vec0*`, `compiled*` (usearch) and `_numkong*`. The Outputs section says "their native binaries" and the UPX hazard applies to every one of them, not just the collected library. This takes effect **only once `vec0` is collected into `binaries`** — `upx_exclude` is consulted solely for `EXTENSION` and `BINARY` typecodes, so it is a dead no-op against anything in `datas`. UPX-packed native libraries are a known load-failure source; no toolchain in either CI path currently provides UPX, so this is free insurance rather than a live fix.

6. **Extend the CI greps** — `.github/workflows/windows-installer.yml:72-74` currently asserts `child spawn: OK`, `desktop shell: OK`, and `RESULT: PASS` (line 71 is the `doctor | tee` invocation itself). Add both probe lines, so a probe that vanishes from the build fails loudly instead of passing on the aggregate. Name the probes `sqlite-vec` and `usearch` verbatim so the greps read `grep -q "sqlite-vec: OK"` — short, stable, and unambiguous against the existing five lines.

7. **Update the stale surfaces** — four enumerations of what `doctor` checks go stale when gates are added: `run_doctor`'s own docstring (`the_one/diagnostics.py:295`), which already claims "child spawn + interpreter" when five gates exist; `the_one/main.py:51-52`; `README.md:52`; and `docs/windows-install.md:127`.

8. **Write the tests.** `tests/test_doctor.py` is currently 23 passed / 1.35s and host `run_doctor` exits 0 with five OK gates — that is the baseline to move deliberately. Cover, for each probe: the success path, a monkeypatched-failure path asserting `run_doctor` still returns an int and emits FAIL rather than propagating, and the unfrozen downgrade. Guard the real extension-loading test with `skipif(not hasattr(sqlite3.Connection, "enable_load_extension"))` — `tests/test_doctor.py` is not in the curated Windows lane (`ci/tasks/windows-tests.yml:55-69`) today, but that file's own maintenance note says platform-divergent tests belong there, and the guard lets it be added later without reopening DD-7's false-alarm concern.

## Edge Cases

- **`enable_load_extension` absent from the build** — `hasattr` guard; `skipped` unfrozen, failure when frozen.
- **Extension loads but the vector query returns nothing** — must be a failure, not a pass. This is the `_probe_model_catalog` lesson: prove the capability resolves a real value, since a load that silently no-ops is exactly the failure mode a probe exists to catch.
- **The native library is missing from the bundle** — the frozen path resolution differs from the source-tree path; this is the specific regression the probe defends against. Report the `loadable_path()` value together with the caught `sqlite3.OperationalError`, which names the file SQLite actually tried. Do **not** `os.path.exists()` the bare `loadable_path()` — it is extensionless and always absent.
- **A probe raises** — forbidden by the probe contract. Any escaping exception would take down `doctor` entirely, breaking the CI gate for reasons unrelated to the thing under test.
- **`numpy` version conflict** — `numpy` is new to the closure; if any existing pin conflicts, stop and report rather than force-resolving.
- **`usearch`'s Windows-only DLL directory call is unverified.** `usearch/__init__.py:24` calls `os.add_dll_directory(...)` against numkong's extension directory on Windows only. The "no spec entry needed" conclusion was reached against a one-dir build that may not have exercised that path. PyInstaller does write a real on-disk `.pyd`, so it should hold — but treat it as unproven until the `fly execute` run says otherwise, and if `usearch` fails to import in the frozen bundle, this is the first thing to look at.

## Files Affected

- `pyproject.toml` — two dependency lines with rationale comments
- `uv.lock` — regenerated
- `the_one/diagnostics.py` — two probes, gate registration, docstring correction
- `tests/test_doctor.py` — pass/fail/skipped coverage for both probes
- `packaging/windows/the-one.spec` — collection entries and `upx_exclude`
- `.github/workflows/windows-installer.yml` — two added grep assertions
- `ci/tasks/windows-installer-build.yml` — named-line assertions on the Concourse lane, which today checks only the exit code
- `the_one/main.py` — usage text describing what `doctor` checks
- `README.md`, `docs/windows-install.md` — the other two enumerations of doctor's checks
- flight log — measured wheel cost, `doctor` output, decision evidence

## Citation Audit

Verified against working tree at `e26c334`:

- `the_one/diagnostics.py:44-51` `ProbeResult` — confirmed
- `the_one/diagnostics.py:230-273` `_probe_model_catalog` — confirmed; the "Never raises" contract is at `:247`. An earlier draft cited `:230-262`, which truncated the function
- `the_one/diagnostics.py` `run_doctor` gates / `all_ok = all(g.ok for g in gates)` — confirmed
- `tests/test_doctor.py` `run_doctor(out=buf) == 0` host assertion and `monkeypatch.setattr(diagnostics, "_probe_*", …)` pattern — confirmed
- `pyproject.toml:71` end of `dependencies`; `:105-106` package-data — confirmed
- `packaging/windows/the-one.spec:125` `seed_datas`; `:274` `upx_exclude=[]` — confirmed
- `ci/tasks/windows-installer-build.yml:47-49` doctor gate — confirmed
- `ci/README.md:106` `fly execute` invocation — confirmed
- `.github/workflows/windows-installer.yml:72-74` grep assertions — corrected from an earlier `:71-73`, which pointed at the `doctor | tee` line
- `.github/workflows/pr-lint.yml:61-69` release-closure `uv export` + `pip-audit`, fails on findings — confirmed (`:61` is the export half the verification step reproduces)
- `packaging/windows/the-one.spec:90` `winpty_bins` via `collect_dynamic_libs`, wired at `:182` into the shared `binaries` list reaching both Analyses via `:203` — confirmed as the pattern to copy for `vec0`
- `the_one/diagnostics.py:276-290` `_probe_interpreter` catches only `FrozenInterpreterError` (at `:288`) — corrected from an earlier `:276-289`, which cut the final return
- `the_one/main.py:33,51` `run_doctor` call site and usage text — confirmed
- `uv.lock` contains none of `sqlite-vec`, `usearch`, `numpy`, `numkong` — confirmed by grep

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing — *42 doctor tests; full suite 3,935 / 10 skipped at leg close*
- [x] Update flight-log.md with leg progress entry, including measured wheel cost and captured `doctor` output
- [x] Set this leg's status to `completed` (in this file's header) — *at the flight commit, 2026-09-09*
- [x] Check off this leg in flight.md
- [x] Do NOT commit — the flight defers review and commit until after the last autonomous leg

## Flight Director Audit — 2026-09-09

Every acceptance criterion above was met and evidenced in the flight log at
leg close (see *Leg 1 — `vector-store-probe`*, *Frozen Windows Verification —
Leg 1* and the `usearch` correction), but the checkboxes in this artifact were
never ticked. Reconciled during the flight-end pass so the artifact matches
the log; no substantive change.
