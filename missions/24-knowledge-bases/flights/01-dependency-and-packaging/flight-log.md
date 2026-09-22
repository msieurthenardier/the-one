# Flight Log: Dependency and Packaging Decision

**Flight**: [Dependency and Packaging Decision](flight.md)

## Summary

In flight, and **blocked on an expired Concourse credential**.

Leg 1 (`vector-store-probe`) is landed, including its frozen-Windows acceptance
run — see *Frozen Windows Verification — Leg 1* below and the `usearch` anomaly
that run surfaced.

Leg 2 (`embedding-model-and-probe`) has landed everything producible on the
host: the float16 generator and its `make` target, the 62.56 MiB model directory
on disk (**untracked by design** — a human stages it), `model2vec` locked into
the closure, the unconditional `embedding model` probe with its tests, wheel and
frozen packaging wired, both CI lanes asserting the new line by name, and all
four `doctor` enumerations corrected for the eighth gate. `make test-unit` is
green at 3,948 / 10 skipped / 469s and `pip-audit` is clean.

Its acceptance run is not done: the `fly` token for team `the-one` expired
2026-09-07 21:42 UTC, one day before the leg ran. Concourse itself is healthy.
**An operator runs `fly -t the-one login` and the flight resumes** — the frozen
`doctor` line, the frozen peak RSS and the installer-size delta all read off that
single run.

---

## Leg Progress

### Leg 1 — `vector-store-probe` — implementation landed (host side)

Everything producible on the host is done: dependencies added and locked, both
probes written and registered, tests green, spec and both CI lanes wired, the
four stale doctor enumerations corrected. The leg's *acceptance* still needs the
`fly execute` frozen-Windows run (DD-7 makes both probes frozen-only, so their
real signal only exists in the bundle) — that step is the Flight Director's, and
is not yet performed. Not committed: this flight defers review and commit until
after the last autonomous leg.

**Dependency closure — measured, not estimated.** `uv lock` resolved in 876 ms
with **no conflict of any kind**, in particular none against `numpy`, which the
leg flagged as the stop-and-report risk. Four packages added (131 total, from
127); `tqdm`, which `usearch` also requires, was already in the closure and is
therefore not an addition.

win_amd64 **cp311** wheel bytes — cp311 is what both installer paths build on;
`uv.lock` also carries cp312/cp313 rows per package, which are not the ones that
ship:

| package | version | wheel | bytes |
|---|---|---|---|
| `sqlite-vec` | 0.1.9 | `sqlite_vec-0.1.9-py3-none-win_amd64.whl` | 292,804 |
| `usearch` | 2.26.2 | `usearch-2.26.2-cp311-cp311-win_amd64.whl` | 343,513 |
| `numkong` | 7.8.2 | `numkong-7.8.2-cp311-cp311-win_amd64.whl` | 492,060 |
| `numpy` | 2.4.6 | `numpy-2.4.6-cp311-cp311-win_amd64.whl` | 12,608,406 |
| **total** | | | **13,736,783 (13.10 MiB)** |

The three figures the leg predicted from PyPI (`sqlite_vec` 292,804, `usearch`
343,513, `numkong` 492,060) came back exact. `numpy` was the unquantified one:
**12.6 MB**, i.e. 92% of the whole delta. The vector stores and their native dep
are 1,128,377 bytes (1.08 MiB) between them — the store choice in Flight 2 moves
about 1 MB, while `numpy` dominates and arrives with Leg 2's embedding backend
regardless. `numpy` resolves to 2.4.6 under Python < 3.12 and 2.5.3 at or above
it; the installer is cp311, so 2.4.6 is the shipped row.

**`pip-audit` clean against the widened release closure.** Run locally rather
than discovered at the gate, using the exact `pr-lint.yml` command
(`uv export --no-dev --no-emit-project --extra gui --extra all-llms` →
`pip-audit --disable-pip -r`): *No known vulnerabilities found*, 131 packages,
3.2 s. No version floors needed for the new packages.

**Two probes, both frozen-only (DD-7), neither able to raise.** `sqlite-vec`
opens a bare `sqlite3.connect(":memory:")`, loads `vec0`, re-disables extension
loading immediately, then inserts a 4-dim vector at rowid 42 and asserts the
`WHERE embedding MATCH ? AND k = ?` query hands that rowid back. `usearch`
builds `Index(ndim=4)`, adds key 7 as an `np.float32` array, searches, and
asserts the key returns. Both go through one shared
`_vector_probe_outcome(name, reason)` helper that implements the house gating
idiom — hard failure when frozen, `ok=True` with a `skipped —` detail otherwise —
so the two probes cannot drift apart on gating. Neither ever skips the *work*;
only failure is downgraded.

Host output (Linux dev host, non-frozen — informational, not the acceptance
signal):

```
  sqlite-vec: OK — vec0 v0.1.9 loaded from <venv>/site-packages/sqlite_vec/vec0; KNN round-trip returned rowid 42
  usearch: OK — HNSW round-trip returned key 7 (numkong=yes, simd=haswell)
RESULT: PASS
```

The `numkong=` field is the cycle-2 finding made observable: `usearch` swallows
its own numkong `ImportError`, so a bundle missing `numkong._numkong` would still
import, still answer searches by dynamic dispatch, and still print a clean `OK`.
The flag in the detail line is what makes a degraded bundle visible in the frozen
`doctor` output.

**Every counter-intuitive API detail the two design-review cycles established
was re-verified in this venv before being coded against**, and all held:
`loadable_path()` is extensionless; a plain list binds as `ProgrammingError`;
`serialize_float32` works; vec0 KNN needs the explicit `k = ?`; `Index()` needs
an explicit `ndim`; `add`/`search` assert on `np.ndarray`; keys return as
`np.uint64`. The PyInstaller collection claim was re-verified independently in a
throwaway env: `collect_dynamic_libs('sqlite_vec')` → `[]`,
`collect_data_files('sqlite_vec')` → `[]`, the same with
`includes=['*.so','*.dll','*.dylib']` → `[]`, and only
`collect_dynamic_libs('sqlite_vec', search_patterns=['*.dll','*.dylib','*.so'])`
returns the file — landing it at dest `sqlite_vec`, exactly where
`loadable_path()` will look under `_MEIPASS`.

**Spec**: `sqlite_vec_bins` added and wired into the *shared* `binaries` list
(reaching both `a_cli` and `a_gui` via `_analysis_kwargs`), not into one
`Analysis`. `upx_exclude` went from `[]` to `["vec0*", "compiled*", "_numkong*"]`,
covering all three native artifacts. No spec entry for `usearch` or `numkong` —
both are ordinary importable extension modules, and the probes' lazy imports are
plain `import` statements, so PyInstaller's module graph reaches them.

**The apparatus hole from design-review cycle 2 is closed.** Both lanes now
assert by name. `.github/workflows/windows-installer.yml` gained
`grep -q "sqlite-vec: OK"` and `grep -q "usearch: OK"`.
`ci/tasks/windows-installer-build.yml` — DD-4's actual apparatus, which read
only `doctor`'s exit code — now captures the output, echoes it, gates on the exit
code, and then asserts both probe lines by name.

**Tests**: `tests/test_doctor.py` 23 → **42 passed in 1.25 s** (+19; baseline was
23 / 1.35 s). Full unit gate green: **3,935 passed, 10 skipped, 557 deselected in
455.91 s** against the ~455 s / 3,910-test baseline — the new probes cost no
measurable wall-clock time, because the round-trips are a 4-dimension vector each
and the only new import weight (`numpy`) is paid once per process. Nothing in the
new coverage was skipped: all 42 doctor tests ran, since this host has
`enable_load_extension` compiled in. Coverage per probe: real success round-trip, frozen failure,
unfrozen downgrade, wrong/empty answer treated as failure, and a
never-raises test that monkeypatches the underlying library to raise and asserts
`run_doctor` still returns an int and emits a `FAIL` line instead of propagating.
Plus a `sqlite-vec` test asserting extension loading is left *disabled*, and one
asserting the missing-`enable_load_extension` build path.

Two test-mechanics notes worth carrying forward: `sqlite3.Connection` is an
immutable C type, so neither `monkeypatch.setattr` nor `delattr` works on it —
the missing-method build is simulated by swapping the module reference
`diagnostics.sqlite3`, and the enable/disable call sequence is observed through a
delegating proxy connection rather than by patching a bound method. Both are
easy to get wrong in a way that passes for the wrong reason: a failed
`setattr` inside the probe is caught by the probe's own broad `except` and
downgraded to `ok=True` on an unfrozen host, so a naive assertion on `ok` passes
while testing nothing.

**Stale surfaces corrected** (four, as the leg specified): `run_doctor`'s
docstring (said "child spawn + interpreter" when there were five gates; now names
all seven and which five are frozen-only), `the_one/main.py` usage text,
`README.md`, and `docs/windows-install.md`.

**Not done in this leg, by instruction**: no `fly execute`, no frozen build, no
commit. The frozen `doctor` stdout and the `RESULT: PASS` evidence the leg's
acceptance criteria require are still outstanding and belong to that run.

---

## Decisions

*(runtime decisions not in the original plan)*

### Flight Director Notes

**Phase file loaded**: `.flightops/agent-crews/leg-execution.md` — structure
validated (`## Crew`, `## Interaction Protocol`, `## Prompts`; six prompt
subsections, twelve fence markers).

**Prerequisites cleared at flight start.** Concourse had been verified DOWN
three times during planning and design review. Operator started Docker and
authenticated; the API now answers and reports three workers running, including
`windows-worker` (`platform: windows`, Concourse 2.5) — the flight's only hard
external dependency. `uv` 0.10.0 confirmed on PATH. Flight moved
`planning` → `in-flight`; mission moved `planning` → `active`.

**Branch**: `flight/01-dependency-and-packaging`, cut from
`mission/24-knowledge-bases` at `e26c334`, **not** from `main`. Mission 24 uses a
long-running mission branch; flights merge back into it and the mission merges to
`main` once. This departs from the `.flightops/ARTIFACTS.md` git convention,
which describes flight branches without a mission-branch layer — the operator
chose to carry the exception rather than amend the convention file.

**Leg 1 risk tier: HIGH.** Two independent triggers, either sufficient on its
own:
1. *Shared-interface change with existing consumers.* The leg adds entries to
   `run_doctor`'s gate list, and `run_doctor`'s exit code and stdout are consumed
   in four places — `the_one/main.py:33` (CLI exit), `tests/test_doctor.py`
   (asserts `== 0` on the host), `.github/workflows/windows-installer.yml:72-74`
   (greps named lines), and `ci/tasks/windows-installer-build.yml:47-49` (throws
   on non-zero). Adding a gate changes a contract four consumers depend on.
2. *Dependency-closure change.* New runtime dependencies reach every install, the
   frozen bundle, and `pr-lint.yml`'s release-closure `pip-audit`, which fails on
   any finding.

A third, weaker signal: the probe enables SQLite extension loading, a native-code
load path, which is security-adjacent even though the probe re-disables it.

**Leg 1 design review, cycle 1 — `approve with changes`.** The reviewer verified
empirically (throwaway venvs, real PyInstaller onedir builds) rather than from
documentation, and the high-severity findings justified the HIGH tier on their
own:

- The leg's PyInstaller guidance was **wrong and would have failed silently on
  two platforms**. `collect_data_files('sqlite_vec')` returns `[]`: PyInstaller
  appends `**/*<suffix>` for every `importlib.machinery.all_suffixes()` to its
  excludes, and excludes beat includes. `.dll` merely happens not to be in that
  list on Windows, so the entry would have appeared to work there while shipping
  nothing on Linux and macOS. Corrected to
  `collect_dynamic_libs("sqlite_vec", search_patterns=["*.dll","*.dylib","*.so"])`
  into `binaries` — plain `collect_dynamic_libs` also misses it, because its
  default patterns expect `lib*.so` and the file is `vec0.so`.
- `upx_exclude` is consulted only for `EXTENSION`/`BINARY` typecodes, so the
  leg's instruction to exclude a `datas`-collected library was a dead no-op —
  self-resolving once the collection moved to `binaries`.
- The `usearch` probe as written would not have run: `Index()` needs an explicit
  `ndim`, and `add`/`search` assert on `np.ndarray` rather than accepting lists.
  Both failures would have surfaced as a caught exception → `ok=False` in the
  frozen bundle → a packaging failure that wasn't one.
- Two of the leg's own acceptance criteria contradicted each other on whether an
  unfrozen host skips the work or runs it and downgrades failure. Resolved to the
  house pattern: always attempt, downgrade only failure.

Also corrected: `numkong` is a third native package (`usearch` needs no spec
entry at all — the module graph collects it); `sqlite_vec.loadable_path()` is
extensionless so an existence check always reports missing; vec0 KNN requires an
explicit `k` constraint; the `pip-audit` release gate was unmentioned in
verification; two stale doctor enumerations were missing from Files Affected; and
three citations were off (`windows-installer.yml:71-73` → `:72-74`,
`_probe_model_catalog` `:230-262` → `:230-273`, and a claim that every existing
probe catches all exceptions, which `_probe_interpreter` does not).

Three reviewer questions answered in the revision: spec patterns written
**portably** despite living under `packaging/windows/` (the mission requires all
three platforms, and a Windows-only-by-accident entry is the exact failure class
this flight exists to catch); wheel bytes summed from `uv.lock`'s per-wheel
`size` fields; and gating follows the house pattern.

Changes are substantive, so a second design-review cycle follows per the
workflow's re-review rule.

**Leg 1 design review, cycle 2 — `approve with changes`.** Cycle 1's corrections
all verified correct in a scratch venv, including the detail that mattered most:
`collect_dynamic_libs("sqlite_vec", search_patterns=[...])` returns dest folder
`sqlite_vec`, and `loadable_path()` is `dirname(__file__)/vec0`, so under a
frozen one-dir bundle it resolves `_MEIPASS/sqlite_vec/vec0` — the collected file
lands exactly where the probe will look. Collecting to a useless location would
have passed the spec edit and still failed the probe.

One high-severity gap remained and is now closed: the leg never stated the vec0
`CREATE VIRTUAL TABLE` DDL or the `MATCH` bind format, and binding a plain Python
list raises `ProgrammingError: type 'list' is not supported`. Now specified —
`vec0(embedding float[N])` with `sqlite_vec.serialize_float32(v)`.

Two findings worth recording beyond their fixes:

1. *The apparatus had a hole.* AC-8's grep assertions defend only the GitHub
   tag-gated release lane. DD-4's actual apparatus — the Concourse task — reads
   only `doctor`'s exit code, so a probe silently dropped from the gates list
   would still pass `fly execute`. That is exactly the failure DD-5 exists to
   prevent, in the apparatus meant to prove DD-5. The leg now requires named-line
   assertions on **both** lanes, and `ci/tasks/windows-installer-build.yml` joins
   Files Affected.
2. *`usearch` has its own fail-open.* Its numkong import is wrapped in
   `except ImportError: pass`, so a bundle missing `numkong._numkong` still
   imports and still answers searches by dynamic dispatch — reporting a clean
   `OK` over a degraded bundle. The probe now surfaces `USES_NUMKONG` in its
   detail line.

**Correction to cycle 1, carried into the leg**: the `collect_data_files` silent
failure is **Linux-only**, not Linux and macOS. `all_suffixes()` blocks `.so`,
`.abi3.so` and `.cpython-311-*.so`; it never contains `.dylib` on any platform.
Cycle 1 overstated the blast radius; the prescription is unchanged.

Also corrected: `upx_exclude` now covers all three native artifacts rather than
`vec0` alone (Outputs and step 5 had disagreed); `the-one.spec:90` was only half
the pattern, with the wiring at `:182`; `pr-lint.yml:61-69` not `:62-69`;
`_probe_interpreter` is `:276-290` not `:276-289`; and AC-9 now pins the cp311
wheel rows, since `uv.lock` carries cp311/cp312/cp313 entries per package.

**Carried into implementation as an unproven assumption**: `usearch/__init__.py:24`
calls `os.add_dll_directory` on Windows only, and the "no spec entry needed"
conclusion came from a build that may not have exercised that path. Recorded in
the leg's Edge Cases as the first thing to check if `usearch` fails to import in
the frozen bundle.

**Two design-review cycles used — the workflow's maximum.** Not escalating: the
remaining items were new, small, and each arrived with an empirically verified
fix, rather than issues persisting unresolved across rounds. Leg marked `ready`;
proceeding to implementation.

Not triggered: no schema or migration change, no lifecycle or state-machine
change, no cache behavior, and nothing contradicting the flight spec or a prior
leg. Tiering high on either of the first two alone; the review is cheap relative
to a wrong leg on a surface four consumers read.

---

## Deviations

*(departures from the planned approach)*

---

## Anomalies

*(unexpected issues encountered)*

---

## Session Notes

### Planning — 2026-09-06

Prerequisite check at planning time: Concourse at `localhost:8080` was
**unreachable** (`dial tcp 127.0.0.1:8080: i/o timeout`, team `the-one`). The
flight's frozen-Windows verification depends on it. Recorded as an unsatisfied
prerequisite rather than assumed recoverable; re-verify before Leg 2.

Ephemeral infrastructure to track here rather than in version control: the
branch-tracking Concourse pipeline created for Leg 2 must be torn down at merge.
Record its name and creation time when set.


---

## Frozen Windows Verification — Leg 1

**Run**: `fly execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out`
on `windows-worker`. **Exit 0**, `BUILD OK: the-one-setup-0.8.1.exe`, installer
71,239,095 bytes, Inno compile 59.1s.

Captured `doctor` output from the frozen bundle:

```
the-one doctor — frozen-runtime spawn diagnostic
  frozen: True
  child spawn: OK — spawned via 'C:\Windows\system32\cmd.EXE', round-trip OK
  python interpreter: OK — resolved to C:\Python311\python.exe
  desktop shell: OK — pystray + PIL importable
  llm providers: OK — all 6 provider modules importable
  model catalog: OK — seed resolves claude-sonnet-4-6 -> 1000000
  sqlite-vec: OK — vec0 v0.1.9 loaded from ...\dist\the-one\_internal\sqlite_vec\vec0; KNN round-trip returned rowid 42
  usearch: OK — HNSW round-trip returned key 7 (numkong=no, simd=serial)
RESULT: PASS
```

**`sqlite-vec` is fully proven frozen.** `vec0.dll` collected to
`_internal\sqlite_vec\`, `loadable_path()` resolved it under `_MEIPASS`, and the
KNN round-trip returned the planted rowid. The cycle-1 `collect_dynamic_libs`
correction was necessary and sufficient.

### Anomaly — `usearch` loads degraded in the frozen bundle

> **SUPERSEDED — the mechanism described below is wrong. See "Correction" at the
> end of this log.** The observation (`numkong=no, simd=serial`) is accurate and
> reproducible; the cause attributed to it is not. Kept intact rather than
> rewritten, per the append-only convention.

`numkong=no, simd=serial` frozen, against `numkong=yes, simd=haswell` on the
Linux dev host. All three native artifacts *are* bundled — the Inno file listing
shows `_internal\numkong\_numkong.cp311-win_amd64.pyd`,
`_internal\usearch\compiled.cp311-win_amd64.pyd` and
`_internal\sqlite_vec\vec0.dll` — so this is not a collection failure.

Mechanism: `usearch/__init__.py:15-32` wraps its numkong load in
`except ImportError: pass`, and on Windows a `.pyd` that cannot resolve a
dependent DLL raises exactly `ImportError` ("DLL load failed while importing").
PyInstaller's build log records
`Extra DLL search directories (AddDllDirectory): ['…numpy.libs', '…numkong']` —
a build-time search path that does not survive relocation into `_internal\`.
usearch therefore falls back to dynamic dispatch and serial SIMD: correct
answers, no hardware acceleration.

**Severity: decision-relevant, not blocking.** The bundle builds, `doctor`
passes, and usearch returns correct results. But usearch's entire case over
`sqlite-vec` is a hardware-accelerated HNSW index, and Flight 2 chooses between
them on query latency. Measuring usearch at `simd=serial` would compare a
crippled build against a healthy one and could hand the decision to `sqlite-vec`
on a false premise. **Flight 2 must not benchmark until this is resolved or
consciously accepted.**

This also settles the question cycle 2 raised and the leg carried in as an
unproven assumption: the "no spec entry needed for usearch/numkong" conclusion
was reached on Linux and is **wrong on Windows** — not because the module graph
misses the extension, but because the runtime DLL search path does.

### Methodology note — the probe detail line is what found this

The `USES_NUMKONG` addition entered the leg as a **low-severity suggestion** in
design review cycle 2. Without it this bundle reports a clean `usearch: OK`, the
build goes green, and Flight 2 silently benchmarks a degraded library. Both CI
lanes assert `usearch: OK` by name and both would have passed.

That is three fail-opens in one leg — the `HF_HUB_OFFLINE` download path, the
`numkong` dynamic-dispatch fallback, and the immutable-`sqlite3.Connection`
monkeypatch that would have made a test pass while asserting nothing. The
recurring shape is a check that can satisfy itself the wrong way, and in all
three cases the fix was to make the probe *report what it actually got* rather
than merely whether it got something.

### Flight Director call — fixing the anomaly inside Leg 1

Operator directed the numkong degradation be fixed in Leg 1 rather than deferred
to Flight 2, logged as a squawk, or resolved by dropping `usearch`.

Recorded as a **scope interpretation, not a requirements change**, so the leg is
not aborted and re-created. The leg's acceptance criterion is that each candidate
"packages and loads in the frozen Windows bundle"; a library that loads with its
acceleration silently disabled does not satisfy that criterion's intent, and the
defect sits inside the leg's own subject matter — packaging these two
dependencies. Fixing it completes the existing criterion rather than adding a new
one.

Iteration cost is the real constraint: each frozen verification is a ~10 minute
round trip on `windows-worker`. The Developer is therefore directed to spend its
first run buying *information* — surfacing the actual `ImportError` text from the
numkong load — rather than guessing at a fix. That diagnostic is also a permanent
improvement in the leg's own idiom: report what you actually got, not merely
whether you got something.

---

## Correction — the `usearch` anomaly is upstream, not a packaging defect

The anomaly section above attributes `numkong=no, simd=serial` to a dependent-DLL
resolution failure swallowed by `usearch`'s `except ImportError: pass`, and
concludes that the "no spec entry needed for usearch/numkong" finding was wrong
on Windows. **Both conclusions are incorrect.** The Flight Director wrote them
from the build-log `AddDllDirectory` line, which was a red herring.

**What is actually happening: nothing fails.** The instrumented probe now reports:

```
usearch: OK — HNSW round-trip returned key 7 (numkong=no, simd=serial;
numkong ext 7.8.2 loads fine [haswell,alder] — this usearch binary was built without numkong)
```

numkong imports cleanly inside the frozen bundle and detects the same ISAs it
detects on Linux. No exception is raised or swallowed. The `usearch` **Windows
wheel is simply built without numkong linkage**, so there is no code path that
could call it.

Verified independently by the Flight Director against the published cp311 wheels,
reading the binaries directly:

| platform | `nk_*` symbol refs | ISA strings present |
|---|---|---|
| macOS arm64 | 15 | genoa, haswell, icelake, neon, sapphire, serial, skylake |
| Linux x86_64 | 54 | genoa, haswell, icelake, neon, sapphire, serial, skylake |
| **Windows amd64** | **0** | **serial only** |

The Developer confirmed the same across usearch 2.16.0, 2.20.0, 2.25.0, 2.26.0
and 2.26.2, and further found the Windows `.pyd` has no import-table entry for
`_numkong`, an empty delay-import directory, and no `GetProcAddress`/`LoadLibrary`
in its KERNEL32 imports — so it cannot reach numkong statically or dynamically.
`USES_NUMKONG` is compile-time and is 0 in that binary. **macOS is unaffected;
Windows is the lone outlier of the three target platforms.**

No spec change was made and nothing was added to or removed from the bundle. The
original "usearch and numkong need no spec entry" conclusion stands. Changing this
would require building usearch from source on Windows, far outside DD-6.

The probe retains a permanent `_numkong_extension_state()` diagnostic that carries
the real exception text through when the numkong import genuinely fails, so a
future reader can tell an actual DLL-resolution defect from this unlinked-wheel
condition. Three tests cover it. Cost: **1 frozen run of the 3-4 budgeted** — the
static wheel analysis made the rest unnecessary.

### This changes Flight 2's input rather than blocking it

The anomaly section framed `simd=serial` as an artifact to remove before
benchmarking, on the grounds that measuring a crippled build would bias the
decision. That framing is now inverted: **`simd=serial` *is* usearch on Windows,
permanently, for every published wheel.** Benchmarking it that way on the
shipping platform is the honest comparison, and a Linux benchmark would flatter
usearch with acceleration the Windows product will never have.

Flight 2 should therefore measure on Windows, or discount Linux numbers
explicitly. This is a real and material input to the `sqlite-vec`-vs-`usearch`
choice — usearch still holds a sub-linear candidate count via HNSW, but loses the
SIMD distance kernels that are half its performance story, on the operator's own
primary platform.

**Incidental, no action taken**: numkong's 1.15 MB `.pyd` is dead weight in the
Windows bundle. `usearch/__init__.py` imports it unconditionally, so removing it
would only trade bytes for a swallowed ImportError.

### Final unit gate for Leg 1

`make test-unit`: **3,938 passed, 10 skipped, 484s** (3,935 at implementation
close, +3 for the numkong-state tests). ruff check and format clean.

---

## Leg 2 Design — `embedding-model-and-probe`

**Risk tier: HIGH.** Three triggers, any one sufficient:
1. *Dependency-closure change* — `model2vec` plus `huggingface-hub`, `fsspec`,
   `hf-xet`, `joblib`, `cloudpickle`, `safetensors`, `tokenizers`, reaching every
   install, the frozen bundle, and a `pip-audit` gate that fails the release on
   any finding. `hf-xet` is a third native extension.
2. *Shared-interface change* — a third entry in `run_doctor`'s gate list, read by
   four consumers.
3. *Irreversible write to shared history* — a ~63 MiB model directory committed to
   git. Unlike every other decision in this mission, it cannot be undone without a
   history rewrite.

**API facts verified empirically during design, not read from documentation.**
Leg 1 demonstrated the cost of unverified API guidance — the `vec0` bind format
and `usearch` `ndim` would each have cost a review cycle. So a scratch venv with
model2vec 0.9.0 was used to establish, against `potion-base-2M` as a fast proxy:

- `quantize_to` is a real `from_pretrained` parameter; the flight's DD-2 call is
  correct and hand-rolling a safetensors rewrite is unnecessary.
- `save_pretrained` emits exactly five files — `README.md`, `config.json`,
  `model.safetensors`, `modules.json`, `tokenizer.json`. The committed unit is a
  directory.
- float16 round-trips: `embedding.dtype` is `float16`, `encode()` returns
  normalized float16 vectors (norm ≈ 1.0).
- **The DD-5 offline invariant holds.** With `HF_HUB_OFFLINE=1`, a present local
  directory loads and a missing one raises `LocalEntryNotFoundError` rather than
  downloading. The env var does the real work; the path assertion is defence in
  depth and a better message.
- `from_pretrained` defaults to `force_download=True` — moot under
  `HF_HUB_OFFLINE`, but worth knowing.
- Size projection from the proxy (8.5 MB → 4.23 MB at float16): the 32M model's
  129,210,456-byte `model.safetensors` should land near 64.6 MB, total ~66 MB /
  63 MiB. Under GitHub's 100 MiB limit, but the leg requires verifying the real
  figure **before** `git add`, since DD-2's entire basis is that float16 clears it.

**One packaging distinction carried forward explicitly.** Leg 1 established that
`collect_data_files` cannot collect a native library. That lesson does **not**
transfer here: PyInstaller's `all_suffixes()` exclusion blocks only importable
extension suffixes, and every file in the model directory is `.json`,
`.safetensors` or `.md`. `collect_data_files` is genuinely correct this time, and
the leg says so, so nobody over-applies Leg 1's correction.

**Free from Leg 1**: `numpy` is already in the closure via `usearch`, so
model2vec's numpy requirement adds nothing.

**Leg 2 design review, cycle 1 — `approve with changes`.** Both claims the
reviewer was asked to break held, and one was improved on:

- **Size is now exact rather than proxied.** A ranged fetch of the published
  safetensors header returns
  `{"embeddings":{"dtype":"F32","shape":[63091,512],"data_offsets":[0,129210368]}}`
  — one tensor, no metadata. float16 halves the only payload exactly:
  **64,605,272 bytes = 61.61 MiB**, ~63.0 MiB with the tokenizer. DD-2 holds with
  ~38 MiB of margin.
- **`collect_data_files` is genuinely correct for the model directory**, verified
  end to end in a real onedir build: all five files land under `_internal/`, and
  the frozen binary loads and encodes with `HOME=/nonexistent`, no HF cache and
  `HF_HUB_OFFLINE=1` — then fails rather than downloading once the directory is
  removed. Leg 1's `collect_data_files` correction genuinely does not transfer.
  Bonus: `tokenizers` and `safetensors` extensions are collected by the module
  graph with no hook and no hiddenimports entry.

**Flight Director error corrected.** The leg's Context claimed a missing model
raises `LocalEntryNotFoundError` under `HF_HUB_OFFLINE=1`. That is what a
*relative* path raises — which is what was measured during design. An *absolute*
path, which is what `importlib.resources.files(...)` actually yields, raises
`HFValidationError` instead. No download either way, but the Edge Cases test
would have pinned the wrong exception type.

Three high-severity findings fixed:
1. Step 7 assumed a single host test to patch; `tests/test_doctor.py` has **17**
   `run_doctor(` call sites across six classes, and
   `test_passes_on_host_with_child_spawn_ok` monkeypatches nothing at all — under
   an unconditional gate it would hard-depend on the 62 MiB asset. Replaced with
   a module-scoped autouse fixture and an opt-out for the real-load test.
2. The leg dropped `upx_exclude` additions for `tokenizers`/`safetensors`/`hf_xet`
   that the flight's own Technical Approach mandates.
3. Step 4 conflated a blocking size gate with a terminal human handoff, stalling
   the Developer before steps 5-8. Split into a size gate at step 4 and a
   terminal handoff at step 9, with the exit state stated explicitly: model
   directory on disk untracked, all code uncommitted, human's `git add` landing
   in or before the flight's single commit.

Also added: a `## Files Affected` section (absent entirely, and Leg 1's review
found omissions in its own); `out/` to `.gitignore`, since 68 MB of stale
installer currently ships to the Windows worker on every `fly execute`; the model
location named as `the_one/embeddings/data/potion-retrieval-32M/`, because the
same choice appears in three files that must agree; and AC-1's byte-identity
claim narrowed, since `save_pretrained` embeds the destination basename in
`README.md`.

**DD-1's divert trigger demoted at the flight level.** It read "float16
measurably degrades retrieval quality", but measured drift is 1.000000 to six
decimals with recall@3 of 1.0000 — the trigger described a failure the
measurement cannot produce. Rewritten as a conversion-correctness assertion with
pinned thresholds. An unfalsifiable divert condition is worse than none: it reads
as diligence while guaranteeing it never fires.

Changes are substantive; a second cycle follows.

**Leg 2 design review, cycle 2 — `approve with changes`.** Two high-severity
findings, both in sections rewritten *in response to cycle 1*:

1. **The conversion-correctness check could not detect what it claimed.** Cosine
   is scale-invariant and `modules.json` applies a `Normalize` module, so a
   uniformly rescaled tensor scores 1.000000 — a wrong scale is doubly invisible.
   A wrong dtype (quantization skipped, or applied as bfloat16/int8) also scores
   ~1.0; the fp32 case would be caught only by the size gate, and int8 would slip
   both. Truncation is caught, but by `safetensors` refusing to open the file
   rather than by any threshold. Cycle 1 correctly reframed this check from
   "quality" to "correctness"; nobody then verified it detects correctness
   failures. Now rests on direct dtype assertions (`config.json` *and* the
   safetensors header) plus a magnitude comparison, with cosine and recall
   demoted to sanity checks — and `recall@1` replacing `recall@10`, which over a
   32-string corpus covered ~31% of it and would pass a badly degraded model.
2. **The fixture mechanism was mechanically impossible.** A module-scoped fixture
   cannot request the function-scoped `monkeypatch` (pytest raises
   `ScopeMismatch`), and pytest has no built-in opt-out from an autouse fixture —
   the marker workaround needs `request.node` to be the test function, but at
   module scope it is the Module. Replaced with a function-scoped autouse fixture
   and the real-load test moved to its own file, which removes the need for an
   opt-out at all.

Also corrected: the call-site arithmetic cycle 1 introduced was wrong — **16
across 7 classes**, not 17 across six; the 17th match was a substring inside the
*name* `test_skip_keeps_result_pass_in_run_doctor`. The Flight Director carried
that number into the leg twice without checking it.

Smaller fixes: the correctness check must reload the written directory rather
than compare the in-memory quantized object, or a botched *write* passes; Files
Affected named `tests/conftest.py`, where an autouse fixture would have patched
the probe across all ~3,938 tests; `.gitignore` anchored to `/out/`; the three
doctor enumerations continue into a runtimes clause rather than ending at "vector
stores", so insertion point matters; and the `tests/conftest.py:108` precedent is
a session-scoped teardown that patches nothing — evidence that autouse exists
here, not precedent for scoped patching.

Reviewer questions answered in the revision: one network fetch total (pull fp32,
quantize in-process, save, reload); the probe **self-reports peak RSS in its
detail line**, since DD-4's read path is `doctor` stdout and neither CI task
measures memory; and the untracked-asset window is safe because no CI lane runs
the unit gate on this branch — Concourse tracks `main` and `pr-lint.yml` triggers
on PRs to `main` — provided no PR opens before the human's `git add`.

Flight spec reconciled in the same pass: DD-1's trigger updated, DD-7's unit-gate
resolution rewritten (it still described a single monkeypatched host test), and
the In-Flight checkpoint's pre-amendment "cosine drift and recall@k" framing
replaced.

**Both design-review cycles now used on Leg 2 — the workflow's maximum.**
Escalating to the operator rather than proceeding unilaterally. The escalation
trigger is not that findings remain unresolved — all are fixed, and the reviewer
returned `approve with changes`, not `needs rework`. It is that **both cycles
produced high-severity findings in the sections revised in response to the
previous cycle**, which is the signature the max-cycles rule exists to surface.

**Operator decision on the escalation**: proceed to implementation. Rationale
accepted — the remaining risk sits in test and fixture design, which pytest
adjudicates in seconds and more definitively than a third review round, and the
flight-end Reviewer still covers the resulting code. Leg 2 marked `ready`.

---

## Leg 2 — `embedding-model-and-probe` — implementation landed (host side)

Everything producible on the host is done: the generator script and its `make`
target, the float16 model directory on disk (**untracked, by design — see the
terminal handoff below**), `model2vec` locked into the runtime closure, the
unconditional `embedding model` probe with its tests, `pyproject.toml` and
PyInstaller spec wiring, both CI lanes asserting the new line by name, and all
four `doctor` enumerations corrected for the eighth gate. The leg's frozen
acceptance run is **blocked on an expired Concourse token** — see below.

### The size gate passed, exactly on the predicted figure

`model.safetensors` came out at **64,605,272 bytes (61.61 MiB)** — the number
the leg predicted to the byte from the published safetensors header, not an
estimate that happened to land close. DD-2 holds with **38.4 MiB of margin**
against GitHub's 100 MiB per-blob limit. Nothing reopens.

| file | bytes |
|---|---|
| `README.md` | 3,976 |
| `config.json` | 285 |
| `model.safetensors` | 64,605,272 |
| `modules.json` | 278 |
| `tokenizer.json` | 987,283 |
| **total (5 files)** | **65,597,094 (62.56 MiB)** |

One estimate in the leg was off and it was in the safe direction: `tokenizer.json`
was projected at 1,493,150 bytes and is actually **987,283** — the leg's figure
came from a different family member. Directory total is therefore 62.56 MiB, not
the projected ~63.0 MiB.

### Conversion correctness — the check discriminates, and it says so

The generator reloads the written directory under `HF_HUB_OFFLINE=1` and checks
it three ways, exiting non-zero on any breach:

| check | measured |
|---|---|
| `config.json` `embedding_dtype` | `float16` |
| safetensors header dtype | `{'embeddings': 'F16'}` |
| reloaded dim | 512 |
| max \|embedding\| (upstream → reloaded) | 64.12273407 → 64.12500000 |
| mean \|embedding\| (upstream → reloaded) | 4.33518881 → 4.33518821 |
| cosine over 40 texts | mean 1.000000 / min 1.000000 |
| recall@1 | 1.0000 |

The cycle-2 design finding is confirmed in the data: cosine is **1.000000 to six
decimals** and recall@1 is perfect, so those two alone would have rubber-stamped
a wrong-scale or wrong-dtype artifact. The dtype and magnitude assertions are
what carry the check. Magnitude drift is 3.5e-5 relative on the max and 1.4e-7
on the mean — comfortably inside the 1e-3 fp16 tolerance, and orders of
magnitude away from what any rescale would produce.

**Reproducibility verified, not asserted.** Re-running with `--out` pointed at a
directory named `differently-named-dir` produced all five files **byte-identical**
by sha256. The explicit `model_name="potion-retrieval-32M"` argument to
`save_pretrained` is what buys that: without it the destination basename leaks
into `README.md`'s front-matter, heading and code samples.

### Dependency closure — 8 added, 8.24 MiB of Windows wheels

`uv lock` resolved in ~1.0s with **no conflict**. 131 → **139 packages**.

win_amd64 cp311/abi3 wheel bytes (the ones both installer paths actually build on):

| package | version | wheel | bytes |
|---|---|---|---|
| `model2vec` | 0.9.0 | `model2vec-0.9.0-py3-none-any.whl` | 59,865 |
| `huggingface-hub` | 1.30.0 | `huggingface_hub-1.30.0-py3-none-any.whl` | 796,795 |
| `tokenizers` | 0.23.2 | `tokenizers-0.23.2-cp310-abi3-win_amd64.whl` | 2,863,236 |
| `hf-xet` | 1.6.0 | `hf_xet-1.6.0-cp38-abi3-win_amd64.whl` | 4,033,128 |
| `safetensors` | 0.8.0 | `safetensors-0.8.0-cp310-abi3-win_amd64.whl` | 355,540 |
| `joblib` | 1.6.0 | `joblib-1.6.0-py3-none-any.whl` | 306,115 |
| `fsspec` | 2026.7.0 | `fsspec-2026.7.0-py3-none-any.whl` | 206,583 |
| `cloudpickle` | 3.1.2 | `cloudpickle-3.1.2-py3-none-any.whl` | 22,228 |
| **total** | | | **8,643,490 (8.24 MiB)** |

`numpy` is not on this list: Leg 1 already pulled it in transitively via
`usearch`, exactly as that leg recorded. So model2vec's numpy requirement costs
nothing here. `hf-xet` at 4.03 MB is the single largest addition — a Rust
transfer accelerator the app never uses, since the probe is offline by
construction. Removing it is a Flight 2 candidate, not this leg's business.

**`pip-audit` clean** against the `--extra gui --extra all-llms` release closure
(1,723-line export) — including all seven new surfaces. No floors needed raising.

### Wheel install proves the package-data glob — and the untracked directory

`pip install .` into a scratch venv built a **64,610,736-byte** wheel and
installed all five model files under
`site-packages/the_one/embeddings/data/potion-retrieval-32M/`. The probe then
loaded from that path and returned OK. Two things this settles that the leg
flagged for early verification:

1. `[tool.setuptools.packages.find] include = ["the_one*"]` **does** discover the
   new `the_one.embeddings` sub-package with no new key. Confirmed.
2. setuptools **does not** skip untracked files. The model directory is untracked
   (`??` in `git status`) and the wheel carried it anyway — PEP 517 copies from
   the source tree, not from the git index. AC-7 is therefore a genuine test of
   the glob, not an artefact of the asset already being staged.

Note the wheel path exercised here is the **wheel** only: `pip install .` builds
the wheel directly under PEP 517, so the sdist path remains untested.

### A packaging gap the leg's Files Affected did not name

`collect_data_files("the_one", includes=["embeddings/data/**/*"])` collects all
five files to `the_one/embeddings/data/potion-retrieval-32M` — verified directly
against the source tree with PyInstaller's own helper, count 5, correct
destination. But that alone would have produced a **silently broken frozen
bundle**: nothing in the codebase imports `the_one.embeddings` as a module. It is
reached only by NAME, as the string argument to
`importlib.resources.files("the_one.embeddings")`, which PyInstaller's static
analysis cannot see. The package would have been tree-shaken out of the PYZ while
`embedding_datas` faithfully shipped all 62 MiB of weights into a bundle that
could not address them.

`"the_one.embeddings"` is therefore added to `hiddenimports` with a comment
recording why. `the_one.llm` escapes the identical trap only incidentally, via
its `collect_submodules` entry. This is the same class of failure as the M16
frozen-provider tree-shake, and it is exactly what DD-5 says permanent probes
exist to catch — except here it was caught by reading, before the build.

### Probe design notes

- The detail line reads the **actual dtype off the returned array** rather than
  asserting `float16` in a message that never looked. A model whose quantization
  was silently skipped would announce itself in the line.
- It also carries `model.safetensors`'s byte size and the resolved path, so a
  truncated file or a Git-LFS pointer surfaces as a legible mismatch rather than
  an opaque load error.
- `_force_hf_offline()` sets **both** the env var and, if `huggingface_hub` is
  already imported, `huggingface_hub.constants.HF_HUB_OFFLINE`. That constant is
  evaluated once at import time, so setting the environment variable alone is too
  late in the already-imported case. Not a hypothetical: `run_doctor` under
  pytest runs in a process where the package may well already be loaded.
- Peak RSS is read from `resource.getrusage` on POSIX and `GetProcessMemoryInfo`
  via `ctypes` on Windows — `resource` does not exist on Windows, which is the
  platform the number actually matters on. `ru_maxrss` is KiB on Linux and bytes
  on macOS; both are normalised to bytes.

### Unit gate — the fixture works, and the suite got *faster*

`make test-unit`: **3,948 passed / 10 skipped / 557 deselected in 469.35s**
(wall 8m16s), against Leg 1's **3,938 / 10 skipped / ~484s** baseline.

+10 tests — 3 in `tests/test_doctor.py` (`TestEmbeddingProbeGating`) and 7 in the
new `tests/test_doctor_embedding_model.py`. The runtime **fell by ~15s**, which is
the observable that matters: an unconditional gate with 16 `run_doctor(` call
sites would have added ~2s each, ~30s, had the function-scoped `autouse` fixture
not been there. The suite does not pay the model-load cost. `tests/test_doctor.py`
plus the new file run together in **2.5s** for 55 tests, of which exactly one
performs the real 62 MiB load.

`ruff check` and `ruff format --check` clean across `the_one/`, `tests/` and
`scripts/`.

### Design notes on the test split, confirmed in practice

The cycle-2 design finding held up exactly as written. A module-scoped fixture
would have raised `ScopeMismatch` against the function-scoped `monkeypatch`, and
there is no opt-out from an autouse fixture — so the real-load test genuinely
needed its own file. It is now the sole host-side proof of the real asset, and
`tests/test_doctor_embedding_model.py` says so in its module docstring, including
that it must never be skipped or mocked.

Per Leg 1's lesson about monkeypatches swallowed by a probe's broad `except`,
every test in that file asserts on the **emitted detail**, not merely on `ok`:
the real-load test checks width, dtype, norm, weights byte-size, peak RSS and the
resolved path; the offline-capture test asserts the detail as well as the captured
`HF_HUB_OFFLINE` value, so a stub the `except` had eaten could not read as a pass.
`test_does_not_use_the_frozen_only_helper` inspects the probe's own source for
`_vector_probe_outcome` — because every other test in the file stubs the probe,
and would stay green while the real gate went silent on every dev host.

The DD-5 offline test repoints `_EMBEDDING_MODEL_DIRNAME` rather than renaming
the real directory on disk. Same filesystem miss, but the 62 MiB asset is
untracked until a human stages it, so a test that moved it could leave the tree
needing a re-download. It also installs an exploding `from_pretrained`, so the
test fails loudly if the path guard is ever removed.

### BLOCKED — frozen Windows acceptance run

**AC-10 is not met, and it is an environment blocker, not a code one.** The
`fly` token for team `the-one` **expired 2026-09-07 21:42 UTC**, one day before
this leg ran:

```
$ fly -t the-one status
please login again.
token validation failed with error: not authorized
```

Concourse itself is healthy — `GET /api/v1/info` returns 200, version 8.1.0,
worker version 2.5. Only the CLI credential is stale. The build was attempted and
exited in 0.3s at the authorization check, before uploading anything.

**To resume: an operator runs `fly -t the-one login`, then**

```
fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out > /tmp/fb2.log 2>&1
sed -n '/\[4\/6\]/,/\[5\/6\]/p' /tmp/fb2.log
```

Still outstanding behind that gate, all of them read off that one run:

- `the-one.exe doctor` → `RESULT: PASS` with `embedding model: OK` present
- the frozen probe's **peak RSS**, which on Windows comes from the
  `GetProcessMemoryInfo` branch that has never executed anywhere else
- **installer size delta** against Leg 1's 71,239,095 bytes (expect roughly
  +62–66 MiB before Inno's compression of an already-incompressible float16
  tensor; the true figure is the point of measuring)
- freeze duration delta

`/out/` was added to `.gitignore` **before** the attempt, so the run will not ship
Leg 1's stale 68 MB installer to the worker. That installer is still at
`out/the-one-setup-0.8.1.exe` and the next `fly execute -o installer=./out` will
overwrite it — the reference figure is recorded here rather than relied on from
disk. Note the on-disk file is **71,243,230** bytes while this log's Leg 1 entry
records **71,239,095**; compare the new build against the logged figure, and
treat the 4,135-byte gap as an unexplained artifact of a later Leg 1 re-run
rather than signal.

Host-side peak RSS, for what it is worth as a lower bound until the Windows
number exists: **261.3 MiB** in a source checkout, **210.8 MiB** from the wheel
install. That is whole-process peak, not the model's marginal cost.

### Exit state — the model directory is on disk and UNTRACKED

This is deliberate and is the leg's terminal handoff. `git add` of the model
directory is the one irreversible act in this mission and no agent performs it
unattended.

```
?? the_one/embeddings/
?? scripts/refresh_embedding_model.py
?? tests/test_doctor_embedding_model.py
```

Nothing is committed. Everything else completed with the directory untracked, as
the leg predicted: pytest reads the filesystem, `pip install .` copies from the
source tree, and `fly execute -i repo=.` uploads untracked non-ignored files.

**The human's `git add` must land in or before the flight's single commit** — the
`embedding model` gate is unconditional, so a commit without the asset turns the
branch red on any machine that does not already hold it. The untracked window is
safe only while no PR is open: Concourse's pipelines track `main` and
`pr-lint.yml` triggers on pull requests to `main`, so no CI lane runs the unit
gate on this branch until one is.

## Frozen Windows Verification — Leg 2 (first run)

**Run**: `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out`
on `windows-worker`, after the operator re-authenticated `fly` (a Windows
update had also restarted the host mid-session; Docker and Concourse came back
clean, three workers running). **Exit 0**, `BUILD OK: the-one-setup-0.8.1.exe`,
wall 9m58s (01:23:12Z → 01:33:10Z), Inno compile **123.3 s** (Leg 1: 59.1 s).
The task's by-name assertion for `embedding model: OK` executed and passed —
DD-4's apparatus observed the new gate, not just the aggregate exit code.

Captured `doctor` output from the frozen bundle (PATH and runtimes lines
elided; unchanged from Leg 1):

```
the-one doctor — frozen-runtime spawn diagnostic
  frozen: True
  child spawn: OK — spawned via 'C:\Windows\system32\cmd.EXE', round-trip OK
  python interpreter: OK — resolved to C:\Python311\python.exe
  desktop shell: OK — pystray + PIL importable
  llm providers: OK — all 6 provider modules importable
  model catalog: OK — seed resolves claude-sonnet-4-6 -> 1000000
  sqlite-vec: OK — vec0 v0.1.9 loaded from ...\dist\the-one\_internal\sqlite_vec\vec0; KNN round-trip returned rowid 42
  usearch: OK — HNSW round-trip returned key 7 (numkong=no, simd=serial; numkong ext 7.8.2 loads fine [haswell,alder] — this usearch binary was built without numkong)
  embedding model: OK — 512-dim float16 vector, norm 1.0000 (model.safetensors=64,605,272 bytes, peak RSS unavailable) from ...\dist\the-one\_internal\the_one\embeddings\data\potion-retrieval-32M
RESULT: PASS
```

**AC-10 is met.** The model directory survived the freeze as a data tree, the
probe resolved it under `_MEIPASS`, loaded it with `HF_HUB_OFFLINE=1`, and
produced the asserted 512-dim unit-norm vector. The `usearch` line now carries
the Leg 1 correction's diagnostic clause and reads as expected.

**Installer size — the number the operator agreed to in the abstract:**

| | bytes | MiB |
|---|---|---|
| Leg 1 (before asset) | 71,239,095 | 67.94 |
| Leg 2 (after asset) | 141,827,664 | 135.26 |
| **delta** | **+70,588,569** | **+67.32** |

The installer **roughly doubled**. The delta is slightly above the +62–66 MiB
estimate: the 61.6 MiB float16 tensor is incompressible as predicted, and the
remaining ~5.7 MiB is the Leg 2 dependency closure (`model2vec`, `safetensors`,
`tokenizers`, `huggingface-hub` and friends — 8.24 MiB of wheels before Inno's
compression). Inno's compile time doubled with it. Neither figure is a gate in
this flight; both are inputs the mission's Flight 2 and any later
"download-on-first-run" discussion must start from.

### Anomaly — `peak RSS unavailable` in the frozen bundle

The one figure this run was supposed to produce that no other environment can —
the Windows peak working set of the process that loaded the model — came back
`unavailable`. `_peak_rss_bytes()` (`the_one/diagnostics.py`) took its
`os.name == "nt"` branch and returned `None`, which means either
`K32GetProcessMemoryInfo` returned 0 or the branch raised and was swallowed by
its broad `except`. The host-side figures (261.3 / 210.8 MiB) were produced by
the `resource` branch, so the Windows branch has **never executed successfully
anywhere** — the leg's own log said as much, and this run is the first evidence.

Most likely cause, to be verified rather than assumed: the `ctypes` calls set
no `restype`/`argtypes`. `GetCurrentProcess()` returns a `HANDLE` pseudo-value
of `-1`; with the default `c_int` restype it is truncated to a 32-bit `-1` and
re-widened incorrectly on a 64-bit process, so the memory-info call is handed an
invalid handle and fails. The unit tests could not catch this because the
Windows branch is unreachable on the Linux host.

**Flight Director call**: this is a defect in a Leg 2 deliverable against a Leg
2 acceptance criterion (AC-12's frozen half), not a new scope — it is fixed
inside this leg. A Developer is spawned to (1) reproduce on `windows-worker`
with a one-off `fly execute` task that calls the helper under the same Python
3.11 the freeze uses, (2) fix the branch — declare `restype`/`argtypes`, and
make a failed call report *why* (`GetLastError`) in the detail line rather than a
bare `unavailable`, so the next silent failure is diagnosable from `doctor`
stdout alone — and (3) add a host-runnable unit test that exercises the Windows
branch by stubbing `ctypes.WinDLL` so the `-1` handle mistake cannot recur
unnoticed. Then the frozen run is repeated once; the size and timing figures
above stand and are not re-measured. The `out/` installer on disk is now the
Leg 2 build (141,827,664 bytes) and the Leg 1 file is gone, as predicted.

## Peak RSS fix — reproduced and corrected on windows-worker

**Reproduction.** A one-off scratch task (not committed — `fly execute -c
<task.yml> -i repo=.` against `ci/tasks/windows-installer-build.yml`'s
platform/image/run shape, run twice and discarded, not part of CI) ran on
`windows-worker` under `C:\Python311\python.exe`, `PYTHONPATH` set to the repo
checkout (no `pip install` — importing `the_one.diagnostics` needs only the
stdlib and other `the_one` submodules that only lazily import optional deps,
confirmed empirically by the run succeeding). Three variants ran in the same
process:

```
CURRENT peak_rss: None
```

The unmodified `_peak_rss_bytes()` reproduced the anomaly exactly: `None`.

```
UNDECLARED GetCurrentProcess() -> -1 <class 'int'>
UNDECLARED getter() -> 0 GetLastError= 6
UNDECLARED PeakWorkingSetSize -> 0
```

A raw ctypes call mirroring the unmodified code, undeclared `restype`/
`argtypes`: `GetCurrentProcess()` returns Python `-1` (the correct pseudo-
handle value, but headed for truncation once it crosses a *declared* 32-bit
boundary elsewhere in the call chain), and `K32GetProcessMemoryInfo` fails
outright — returns `0` — with `GetLastError() == 6` (`ERROR_INVALID_HANDLE`).

```
DECLARED GetCurrentProcess() -> 18446744073709551615 <class 'int'>
DECLARED getter() -> 1 GetLastError= 6
DECLARED PeakWorkingSetSize -> 25288704
```

The same call with `GetCurrentProcess.restype = wintypes.HANDLE` /
`argtypes = []` and the getter's `restype = wintypes.BOOL` /
`argtypes = [wintypes.HANDLE, POINTER(...), wintypes.DWORD]` declared:
`GetCurrentProcess()` now returns the full 64-bit pseudo-handle
(`0xFFFFFFFFFFFFFFFF`), the getter succeeds (`1`), and
`PeakWorkingSetSize` comes back `25,288,704` bytes (≈24.1 MiB — a minimal
`python.exe -c "..."` process with no model loaded, not directly comparable to
the frozen bundle's 210–261 MiB host range). The stale `GetLastError=6` next to
a successful call is expected — Win32 does not clear the last-error code on
success, only on the next failing call.

**Root cause, as actually observed** (confirmed, not merely the leading
hypothesis): with no `restype` declared on `kernel32.GetCurrentProcess`,
ctypes marshals its return with the default `c_int` semantics rather than
pointer-width `HANDLE` semantics, so the `-1` pseudo-handle does not carry the
width Win32 expects when it is handed to the next call. With the getter's
`argtypes` also undeclared, `K32GetProcessMemoryInfo` receives a handle
argument it cannot marshal correctly and Win32 rejects it as invalid
(`ERROR_INVALID_HANDLE`, `GetLastError() == 6`) — reproduced exactly, in both
halves: the undeclared variant fails with that code, and declaring
`GetCurrentProcess.restype = wintypes.HANDLE` together with the getter's
`argtypes = [wintypes.HANDLE, POINTER(...), wintypes.DWORD]` is what turns the
call into a success (`GetCurrentProcess()` then correctly returns the
full-width pseudo-handle `0xFFFFFFFFFFFFFFFF`, and the getter accepts it).

**Fix** (`the_one/diagnostics.py`, `_peak_rss_bytes()`): declare
`GetCurrentProcess.restype = wintypes.HANDLE` / `argtypes = []`, and the
getter's `restype = wintypes.BOOL` / `argtypes = [wintypes.HANDLE,
ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD]`, on both the kernel32
and the psapi fallback path. The "never raises" contract is unchanged. The
function's return type changed from `int | None` to `tuple[int | None, str |
None]` — success is `(bytes, None)`, failure is `(None, reason)` — and the
reason is threaded into the probe's detail line, so a future Windows API
failure reads as e.g. `peak RSS unavailable (GetProcessMemoryInfo failed,
GetLastError=6)` instead of a bare `unavailable`. The `peak RSS {x} MiB`
success format is unchanged (`tests/test_doctor_embedding_model.py:64` and
both CI lanes still read it by that shape).

**Test coverage added** (`tests/test_doctor_embedding_model.py`,
`TestPeakRssWindowsBranch`): two tests monkeypatch `os.name = "nt"` and stub
`ctypes.WinDLL` (which does not exist on Linux, so it is patched onto the
module with `raising=False`, as is `ctypes.get_last_error`) to exercise the
branch from the Linux host that runs CI. The success test's fake
`K32GetProcessMemoryInfo` asserts the getter's `argtypes` were declared
(HANDLE first) and `GetCurrentProcess.restype is wintypes.HANDLE` *before*
writing a value into the counters struct and returning success — proving the
production code declares handle semantics before making the call, which is
what the reproduction showed the real bug needed. The failure test makes the
getter return `0` and asserts the returned reason string contains
`"GetLastError"` and the code (`6`). `TestPeakRss` (the pre-existing host-side
sanity test) was updated for the new tuple return.

**Verification — fixed function, unfrozen checkout, real windows-worker.** A
second one-off task ran `the_one.diagnostics._peak_rss_bytes()` (the corrected
version, from the working checkout via `PYTHONPATH`, no freeze) on
`windows-worker`:

```
FIXED peak_rss bytes: 25079808
FIXED reason: None
FIXED MiB: 23.91796875
```

`(25,079,808, None)` — a positive figure instead of `None`. This is the
unfrozen host checkout's figure (informational only — a bare interpreter with
no model loaded, not comparable to the 210–261 MiB frozen/wheel figures
already in this log). The frozen bundle's actual peak RSS during the
embedding-model probe is unmeasured by this fix-verification pass; producing
it requires the full frozen build, which the Flight Director re-runs
separately per AC-12.

**Test results.**

- Scoped: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_doctor_embedding_model.py tests/test_doctor.py -x --timeout 60`
  → **57 passed** (0 failed).
- Full: `make test-unit` → **3,950 passed / 10 skipped / 557 deselected in
  453.49s** (baseline: 3,948 passed / 10 skipped in 469.35s, from this leg's
  earlier run). The +2 is exactly the two new `TestPeakRssWindowsBranch`
  tests; nothing else moved, and the suite is not dominated by this change
  (453s is within the baseline's run-to-run noise, not a regression).

**Scope of this fix.** Only `the_one/diagnostics.py` (the
`_peak_rss_bytes()` helper and the `_probe_embedding_model()` detail-line call
site), `tests/test_doctor_embedding_model.py`, this flight log, and the leg
artifact's AC-12 note changed. No CI task YAML, the PyInstaller spec,
`pyproject.toml`, or `uv.lock` were touched. Leg status remains `landed`; the
frozen figure and installer-delta halves of AC-10/AC-12 remain the Flight
Director's to re-run.

## Frozen Windows Verification — Leg 2 (second run, after the peak RSS fix)

**Run**: same command, same worker. **Exit 0**, `BUILD OK`, wall 7m43s
(01:50:27Z → 01:58:10Z), Inno compile **117.0 s**. `RESULT: PASS`, all eight
gates `OK`; the three by-name assertions passed again. Installer
**141,826,728 bytes** — 936 bytes under the first run, build-to-build noise of
the same kind as Leg 1's 4,135-byte gap; the logged delta of +67.32 MiB stands.

The line this run existed to produce:

```
  embedding model: OK — 512-dim float16 vector, norm 1.0000 (model.safetensors=64,605,272 bytes, peak RSS 247.1 MiB) from ...\_internal\the_one\embeddings\data\potion-retrieval-32M
```

**Frozen Windows peak working set: 247.1 MiB**, whole-process, measured by
`K32GetProcessMemoryInfo` inside the PyInstaller bundle. Against the host
figures (261.3 MiB checkout, 210.8 MiB wheel) it sits in the middle — the
frozen bundle imports the same closure, so this is the model's cost plus the
interpreter's, not an outlier. This is Flight 2's float16-vs-int8 input;
combined with the 64.6 MB tensor on disk it says the model itself is roughly a
quarter of the process peak, and the remainder is `numpy` + `tokenizers` +
`safetensors` import weight that int8 storage would not recover.

**AC-12 is met. Leg 2's acceptance is complete; the leg is landed in full.**
Flight-level criteria "doctor returns RESULT: PASS in the frozen bundle",
"installer size and freeze duration recorded" and "peak RSS recorded" are all
now checked off in `flight.md`. The vector-store criterion's second clause
(both candidates measured against DD-3's criteria, choice recorded) is met to
the extent this flight's apparatus allows — DD-3 as amended moves the store
*choice* to Flight 2 — and is checked off on that basis, with the deferral
already recorded under DD-3.

### Flight Director Notes — resumption and close of Leg 2

- Session resumed 2026-09-09 after a Windows update restarted the host
  mid-flight. Operator started Docker and ran `fly -t the-one login`; token
  valid, three workers up. Phase file re-validated (`## Crew`,
  `## Interaction Protocol`, `## Prompts`; twelve fence markers).
- Ran the blocked acceptance build myself — the leg log had named it the
  Flight Director's step, and it is a verification run, not a code change.
- First run passed the gate but surfaced the `peak RSS unavailable` anomaly.
  Called it an in-leg defect (AC-12 is a Leg 2 criterion) rather than a
  squawk or new scope. Spawned one Developer (Sonnet, fix-review-issues
  shape) with the hypothesis and an instruction to reproduce on the worker
  before fixing. Hypothesis confirmed (`GetLastError=6`); fix, two
  host-runnable tests for the Windows branch, `make test-unit` 3,950 / 10
  skipped / 453.49s.
- Second frozen run read off the figure. No third run needed: the size and
  timing figures are recorded from the first run and re-confirmed by the
  second within noise.
- Both autonomous legs are now landed. Proceeding to the flight-end review
  (Phase 2d). **Reviewer tier: Haiku** — the diff touches diagnostics,
  packaging, CI task assertions and dependency locks, none of which is a
  credential, key-material, middleware-exemption or sandboxing surface.
- Still outstanding before the single commit: the human's `git add` of
  `the_one/embeddings/` (see *Exit state* above). The commit cannot go in
  without it — the `embedding model` gate is unconditional.

### Flight Director Notes — flight-end review

- Reviewer (Haiku) reviewed the full uncommitted diff plus the untracked
  generator, test file and model directory against both leg artifacts and the
  flight checkpoints. Scoped doctor suites re-run by the Reviewer: 57 passed.
  Verdict `[HANDOFF:confirmed]`, no blocking or non-blocking issues raised.
  One review cycle; no fix spawn needed.
- Reconciled Leg 1's artifact during this pass: its acceptance checkboxes had
  never been ticked although every criterion was evidenced in this log at leg
  close. Annotated in the leg artifact.
- Both leg statuses set to `completed` ahead of the single flight commit.
- **Commit is gated on the human staging `the_one/embeddings/`.** Nothing
  else about the commit is outstanding.
