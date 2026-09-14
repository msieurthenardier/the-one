# Flight Debrief: Dependency and Packaging Decision

**Date**: 2026-09-12
**Flight**: [Dependency and Packaging Decision](flight.md)
**Status**: landed
**Duration**: 2026-09-06 (planning) – 2026-09-09 (single flight commit `fa51fb3`), across three sessions split by an expired `fly` token and a Windows-update host restart
**Legs Completed**: 2 of 2

## Outcome Assessment

### Objectives Achieved

The flight did exactly what it was chartered to do and nothing more: it proved,
in a PyInstaller bundle frozen on a real Windows worker, that the knowledge-base
dependency closure packages and loads — both vector-store candidates
(`sqlite-vec`, `usearch`) and the bundled float16 `potion-retrieval-32M` static
embedding model — and landed that proof as three permanent `doctor` probes that
every later flight in the mission inherits as a regression gate. Eight gates
`OK`, `RESULT: PASS`, on four frozen runs (two per leg). Both CI lanes (the
GitHub tag-gated release workflow and the Concourse task DD-4 actually uses) now
assert all three new probe lines by name rather than reading only the aggregate
exit code.

The numbers the flight existed to produce, all measured rather than estimated:

| Measurement | Value |
|---|---|
| Installer, before / after the asset | 71,239,095 → 141,827,664 bytes (+67.32 MiB, roughly doubled) |
| Inno compile time, before / after | 59.1 s → 123.3 s / 117.0 s |
| `model.safetensors` (float16) | 64,605,272 bytes — predicted to the byte from the published header |
| Frozen Windows peak working set during the embedding probe | 247.1 MiB (host: 261.3 MiB checkout, 210.8 MiB wheel) |
| win_amd64 wheel cost, Leg 1 / Leg 2 | 13.10 MiB (92 % of it `numpy`) / 8.24 MiB (`hf-xet` 4.03 MB the largest) |
| Dependency closure | 127 → 139 packages, zero resolver conflicts, `pip-audit` clean |

Two findings with mission-level weight surfaced along the way and are recorded
in the flight log with evidence:

- **`usearch`'s published Windows wheel is built without numkong linkage** —
  verified by reading the binaries directly (0 `nk_*` symbol refs and `serial`
  as the only ISA string on Windows, against 54 refs and seven ISAs on Linux).
  This is an upstream characteristic across every version from 2.16.0 to
  2.26.2, not a packaging defect. It means `simd=serial` *is* usearch on the
  operator's primary platform, permanently.
- **The Windows branch of `_peak_rss_bytes()` had never executed anywhere** and
  failed on first contact with an undeclared-`restype` ctypes HANDLE
  truncation (`GetLastError=6`). Reproduced on the worker, fixed in-leg, and
  covered by two host-runnable tests that stub `ctypes.WinDLL`.

### Mission Criteria Advanced

- *"The default embedding backend works on a fresh install with no account, no
  network, and no external service running"* — partially. The backend and its
  model now provably survive the freeze and load offline (`HF_HUB_OFFLINE=1`
  set in-process, packaged path asserted before `from_pretrained`). The seam and
  its API are Flight 2.
- *"Existing installs upgrade with no data loss, the unit gate stays green, and
  the frozen Windows installer still builds and runs"* — partially. This flight
  establishes the frozen-build gate the rest of the mission is measured
  against; it touches no schema and no data.
- Mission open questions on model choice (DD-1), model delivery (DD-2) and the
  vector-store *evidence* (DD-3) are closed. The store *choice* is deliberately
  Flight 2's, with both candidates proven to package and their wheel bytes and
  the Windows SIMD finding recorded as its inputs.

## What Went Well

- **Sequencing on reversibility, not on component boundaries.** Leg 1 carried
  the cheap, revertible dependency bump and proved the whole apparatus
  (`fly execute` → frozen bundle → `doctor` gate → by-name CI assertions)
  before Leg 2 committed the one thing in the mission that cannot be undone
  without a history rewrite. Leg 1's design review caught three PyInstaller and
  API misconceptions on an artifact where redoing work cost nothing.
- **The human `git add` handoff for the 62 MiB asset.** The leg spec forbade any
  agent from staging the model directory unattended; the Developer left it
  untracked and stated the exit state explicitly; the human staged it into the
  single flight commit. The irreversible act got a human decision point exactly
  where the risk was.
- **Empirical verification before coding, and the probes report what they got.**
  Every counter-intuitive API detail (`loadable_path()` is extensionless, vec0
  KNN needs an explicit `k = ?`, a plain list binds as `ProgrammingError`,
  `Index()` needs `ndim`, `collect_data_files('sqlite_vec')` returns `[]`)
  was re-verified in a scratch venv before being coded against, and all held.
  Three separate fail-opens were caught in one leg — the HF download path, the
  numkong dynamic-dispatch fallback, the immutable-`sqlite3.Connection`
  monkeypatch — and in all three the fix was the same shape: make the check
  *report the value it actually got* rather than merely whether it got one.
  The `numkong=` field entered Leg 1 as a low-severity review suggestion and is
  what surfaced the Windows SIMD finding at all.
- **The divert trigger was demoted before it could become theatre.** DD-1's
  "float16 measurably degrades retrieval quality" was recognised during Leg 2
  design as unfalsifiable (cosine drift 1.000000 to six decimals for a
  normalising static model), reframed as a conversion-correctness assertion,
  and then — when cycle 2 showed cosine and recall cannot detect a wrong scale or
  a wrong dtype either — rebuilt on direct dtype assertions plus a magnitude
  comparison. The generator's real output confirmed the second finding was
  necessary: cosine 1.000000, recall@1 1.0, exactly the numbers that would have
  rubber-stamped a broken artifact.
- **Predictions landed on the number.** The float16 tensor size was computed
  from a ranged fetch of the published safetensors header and came out exact.
  The three vector-store wheel sizes read from PyPI came back byte-identical in
  `uv.lock`. `uv lock` resolved with no conflict against `numpy`, the one
  flagged resolver risk.
- **The append-only log convention paid off.** The Flight Director's first
  diagnosis of the `usearch` anomaly (a swallowed `ImportError` on DLL
  resolution) was wrong. It was left in place, marked superseded, and corrected
  in a separate section with the binary-analysis table. A reader can see what
  was believed, why, and what replaced it.
- **The `hiddenimports` gap was caught by reading, not by a failed build.**
  `the_one.embeddings` is reached only by name through
  `importlib.resources.files(...)`, invisible to PyInstaller's static analysis;
  without the entry the bundle would have shipped 62 MiB of weights that nothing
  could address. Same failure class as the M16 frozen-provider tree-shake.
- **The unit gate got faster while gaining the real model load.** The
  function-scoped `autouse` fixture in `tests/test_doctor.py` plus the dedicated
  real-load file meant sixteen `run_doctor(` call sites did not each pay a
  ~2 s model load. The one genuine 62 MiB load lives in its own file whose
  docstring says it must never be skipped or mocked.

## What Could Be Improved

### Process

- **Platform-only code paths are a known blind spot the review cycles cannot
  cover.** API facts got pre-verified in scratch venvs; the Windows-only
  `_peak_rss_bytes()` branch could not be, and it failed on its first frozen
  execution. This is arguably unavoidable without a Windows dev host, but it
  should be *named* in a leg's Edge Cases ("this branch has never executed;
  the first frozen run is its first test") so the first run is budgeted as a
  diagnostic run rather than treated as an anomaly. The same discipline was
  applied to `usearch`'s `add_dll_directory` path and worked.
- **Both Leg 2 review cycles found high-severity issues in sections rewritten
  for the previous cycle.** The operator's call to proceed past the max-cycles
  escalation was correct in hindsight (the remaining risk was fixture mechanics
  that pytest adjudicated in seconds, and the flight-end review still covered
  the code) and the human interview confirmed it. But the pattern — a revision
  introducing a new class of error the reviewer then catches — is exactly the
  signature the escalation rule exists to surface, and the log should keep
  recording it when it recurs.
- **The branch layout departed from `.flightops/ARTIFACTS.md` and then the PR
  departed from the departure.** The flight branch was cut from a long-running
  `mission/24-knowledge-bases` branch with the stated intent that flights merge
  to it and the mission merges to `main` once. PR #195 was opened against
  `main`. The human interview settled it: **the mission-branch layer stands and
  the PR is retargeted** to `mission/24-knowledge-bases`. Action item below.
- **Flight Director carried an unchecked number into the leg twice.** The
  `run_doctor(` call-site count (17 across six classes) was wrong; the reviewer
  corrected it to 16 across seven (the seventeenth match was a substring in a
  test *name*). A one-line `grep -c` before writing a count into a spec.

### Technical

- **`hf-xet` (4.03 MB) is dead weight.** A Rust transfer accelerator the
  offline-by-construction app never invokes. It rode in with
  `huggingface-hub`. The largest single Leg 2 addition, and the flight log
  already names it as a Flight 2 removal candidate.
- **numkong's 1.15 MB `.pyd` is dead weight on Windows.** `usearch` imports
  it unconditionally and cannot call it. Removing it only trades bytes for a
  swallowed `ImportError`; recorded, no action.
- **DD-6's "light rewrite" estimate is directionally off on both sides** (per
  the Architect). The embedding probe's load path (`_force_hf_offline()`, the
  `importlib.resources` path guard, the `from_pretrained` call) is precisely
  what Flight 2's embedding seam needs internally, so that rewrite is a
  mechanical swap. The two vector-store probes build their own throwaway
  table/index and were never meant to integrate; they likely need **no change**
  when the storage seam lands and stay as capability gates alongside it.
- **The sdist path is untested.** `pip install .` builds a wheel directly under
  PEP 517, so the package-data glob is proven for the wheel only. Nothing ships
  an sdist today; note it rather than fix it.
- **`the_one/diagnostics.py` grew 2.6× (≈330 → 866 lines) and has no section
  in `the_one/agents.md`.** Pre-existing gap, enlarged by this flight: eight
  gates, native-library loading, an offline-fetch guard and a Windows ctypes
  path now live in a file with no canonical architecture reference. The flight
  itself rediscovered several of its invariants (extensionless
  `loadable_path()`, the `_vector_probe_outcome` gating idiom) from source.
- **Three probes hand-roll the same try/except/detail scaffolding.** Not a
  defect under DD-6, but a fourth or fifth probe of this shape is the point at
  which the never-raises/detail-formatting boilerplate should be factored.
- **Windows-only ctypes code is the second Windows-branch-untestable-from-Linux
  defect class this codebase has hit** (M15 F3's PTY work was the first). The
  `TestPeakRssWindowsBranch` trick — stub `ctypes.WinDLL` with `raising=False`,
  assert the production code declared `restype`/`argtypes` *before* the call —
  is worth writing down as the standing pattern.

### Documentation

- Three conventions from this flight are load-bearing methodology and deserve
  names in `the_one/agents.md`'s Project Conventions list (see Recommendations):
  the *probe-must-not-pass-by-download* invariant, *report-what-you-got*, and the
  *autouse-fixture + dedicated-real-load-file* split.
- `docs/kb-architecture.md` still states the superseded "10s of GB per KB"
  scale target in four places (lines 8, 95, 101, 110) that `mission.md` says
  was revised down. Out of this flight's scope, but a later reader will treat
  it as current until it is corrected or retired.
- `the_one/agents.md` needs a diagnostics/`doctor` subsystem section (see
  Technical above).
- `.flightops/ARTIFACTS.md`'s git convention does not describe the
  mission-branch layer Mission 24 is using. Either the convention file gains
  the layer as an option, or the exception keeps getting re-explained in every
  flight log of this mission.

## Test Metrics

`make test-unit` on the debrief's own independent run: **3,950 passed, 10
skipped, 557 deselected, 17 warnings, 466.75 s**, exit 0, no failures, no
flakes observed. Browser lane not run — the flight touched neither Studio nor
any browser test file.

| Point | Passed | Skipped | Wall time |
|---|---|---|---|
| M23 F3 close | 3,758 | 10 | 456.03 s |
| M23 F4 close (last prior debrief) | 3,910 | 10 | 454.55 s |
| M24 F1 Leg 1 close | 3,935 | 10 | 455.91 s |
| M24 F1 Leg 2 close, before peak-RSS fix | 3,948 | 10 | 469.35 s |
| M24 F1 Leg 2 close, after peak-RSS fix | 3,950 | 10 | 453.49 s |
| **This debrief** | **3,950** | **10** | **466.75 s** |

Net for the flight: **+40 tests at flat wall time** (the 453–470 s spread is
run-to-run noise, the same band the M23 debriefs reported). The suite absorbed
three new probes, twelve new packages and a 62 MiB model asset without moving.
That is the function-scoped `autouse` fixture doing its job: an unconditional
gate across sixteen `run_doctor(` call sites would otherwise have cost roughly
30 s per run. The single real model load lives in
`tests/test_doctor_embedding_model.py` and is the only place the suite pays it.
Skip count unchanged at 10 across five readings.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Vector-store *choice* deferred from Leg 1 to Flight 2 (DD-3 amended in-flight) | Leg 1's only read path is `doctor`'s exit code and probe lines; no apparatus in this flight can benchmark 1.5–12M vectors, and DD-6 forbids building the seam that would. A criterion with no apparatus cannot be met. | Yes — a criterion must name the apparatus that measures it |
| DD-1 divert trigger demoted twice: quality-degradation → correctness assertion → dtype + magnitude with cosine/recall as sanity only | The original was unfalsifiable; the first rewrite could not detect a wrong scale (cosine is scale-invariant under `Normalize`) or a wrong dtype | Yes — a divert trigger that cannot fire is worse than none |
| `usearch` SIMD degradation fixed inside Leg 1 rather than squawked or deferred | Operator call; the defect sat inside the leg's own acceptance criterion ("packages and loads") — a silently degraded load does not satisfy its intent | No — scope interpretation, recorded as such, not a rule |
| Peak-RSS ctypes defect fixed inside Leg 2 rather than squawked | AC-12's frozen half is a Leg 2 criterion; the defect is in a Leg 2 deliverable | No — same reasoning, case by case |
| Flight branch cut from `mission/24-knowledge-bases`, not `main`; PR then opened against `main` | Operator chose a mission-branch layer for M24; the PR base did not follow | Yes — retarget PR #195; decide whether ARTIFACTS.md documents the layer |
| Both legs used the full two design-review cycles; Leg 2 escalated to the operator at max cycles and was overridden to proceed | Remaining findings were fixture mechanics pytest would adjudicate faster than a third round | No — the escalation fired correctly; the override was a judgment call, confirmed right |
| `hiddenimports` entry for `the_one.embeddings` added — not in either leg's Files Affected | Package reached only by name via `importlib.resources`; PyInstaller cannot see it | Yes — any package addressed only through `importlib.resources` needs a `hiddenimports` entry, and the spec now says why |
| A one-off `fly execute` scratch task (never committed) reproduced the Windows ctypes bug before fixing it | Each frozen build is ~10 min; a bare-interpreter task under `PYTHONPATH` answered the question in a fraction of that | Yes — when a Windows-only path fails frozen, reproduce unfrozen on the worker first |

## Key Learnings

- **A check that can satisfy itself the wrong way is the recurring hazard of
  packaging work.** Five instances in one flight: the HF download fallback, the
  numkong dynamic-dispatch fallback, the immutable-`Connection` monkeypatch, the
  cosine-only correctness check, and the tree-shaken-but-shipped model
  directory. The unifying fix is to assert on a concrete resolved value in the
  emitted output — dtype off the array, bytes off the file, the resolved path,
  `numkong=yes|no` — and to make tests read that detail line rather than `ok`.
- **The probe detail line is an observability surface, not a log message.**
  Two of the flight's three material findings (the Windows SIMD condition and
  the ctypes HANDLE bug) were readable from `doctor` stdout alone because the
  probes carry their measured values. Neither CI lane measures memory; the
  probe does, so the number exists.
- **`collect_data_files` cannot collect a native library; `collect_dynamic_libs`
  needs explicit `search_patterns` when the file is not `lib*.so`.** PyInstaller
  appends every `all_suffixes()` entry to `collect_data_files`' excludes, and
  excludes beat includes. `.dll` merely happens not to be in that list, so an
  entry that silently ships nothing on Linux appears to work on Windows. The
  same lesson does *not* transfer to a directory of `.json`/`.safetensors`
  files, and Leg 2 said so explicitly to stop over-application.
- **Compute the number before running the expensive step.** The float16 tensor
  size came from a ranged fetch of the safetensors header (one tensor, F32,
  `[63091, 512]`), halved exactly. The DD-2 basis — clearing GitHub's 100 MiB
  blob limit — was known with 38 MiB of margin before the model was ever
  downloaded.
- **`huggingface_hub.constants.HF_HUB_OFFLINE` is evaluated once at import.**
  Setting the env var after the package is imported does nothing; the probe
  sets both, because `run_doctor` under pytest runs in a process where the
  package may already be loaded.
- **The frozen peak-RSS figure answers a narrower question than its label.**
  247.1 MiB is whole-process peak — `numpy` + `tokenizers` + `safetensors`
  import weight plus the model. The model is roughly a quarter of it. It is an
  input to "can the embedding backend stay warm in-process", not to the
  float16-vs-int8 vector *storage* decision, which is arithmetic on DD-1's
  dimension × chunk count × dtype width and should be computed directly.

## Recommendations

1. **Flight 2 must benchmark `sqlite-vec` against `usearch` on Windows, or
   explicitly discount Linux numbers.** Every published `usearch` Windows wheel
   is `simd=serial`; a Linux benchmark would credit usearch with acceleration
   the shipping product never has on the operator's primary platform. DD-3's
   remaining framing ("single file vs. a second artifact with its own
   crash-consistency story") should be weighed against a usearch whose margin
   over exhaustive scan is HNSW candidate pruning alone.
2. **Flight 2 should remove the losing vector-store candidate in the same
   flight it makes the choice**, and pick up the `hf-xet` trim early. Leaving
   both stores plus `numkong` in the closure past the decision point is
   exactly the drift the project's conventions guard against, and the
   installer just doubled.
3. **Name three conventions in `the_one/agents.md`**: *probe-must-not-pass-by-
   download* (assert the packaged path exists via `importlib.resources`
   before any loader that can fall back to a fetch, and force offline
   in-process), *report-what-you-got* (a probe or test asserts on the concrete
   resolved value in the emitted detail, never on a bare `ok`), and
   *autouse-fixture + dedicated-real-load-file* (an unconditional gate that
   loads something expensive gets a function-scoped autouse patch in the
   shared test file and one real load in its own file, because pytest offers
   no opt-out from autouse and module scope cannot take `monkeypatch`).
4. **Leg specs should flag never-executed platform branches by name** in Edge
   Cases so the first frozen run is budgeted as a diagnostic, and pair it with
   the unfrozen-on-worker reproduction pattern from the ctypes fix and the
   stub-`ctypes.WinDLL` test pattern, both of which belong in a new
   `the_one/agents.md` diagnostics/`doctor` section alongside the probe
   contract, the gating idiom and the eight gates.
5. **Settle the mission-branch layer in `.flightops/ARTIFACTS.md`** — either
   document it as an option or record that M24 is a one-off exception — so
   the next flight's PR is opened against the right base without a debrief
   question.

## Action Items

- [x] Retarget PR #195 from `main` to `mission/24-knowledge-bases` before merge (human interview decision) — done at debrief time.
- [ ] Add a diagnostics/`doctor` subsystem section and the three named conventions from Recommendation 3 to `the_one/agents.md` — **squawk 0047**.
- [ ] Correct or retire the "10s of GB per KB" scale claim in `docs/kb-architecture.md` — **squawk 0048**.
- [ ] Carry into Flight 2's planning inputs: Windows-only benchmarking (or explicit Linux discount), the `hf-xet` removal (**squawk 0049**, best completed against Flight 2's closure change since verification needs a frozen build), losing-candidate removal in the deciding flight, and the "247.1 MiB is whole-process, not model-marginal" caveat.
- [ ] Decide whether `.flightops/ARTIFACTS.md` documents the mission-branch layer.
