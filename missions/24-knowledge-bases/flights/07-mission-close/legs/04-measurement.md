# Leg: measurement

**Status**: completed
**Flight**: [Mission Close](../flight.md)

## Objective

Take the two measurements Mission 24 asked for and never took: whether Windows
`usearch` build and save cost are linear in N (Flight 2's 1M/3M figures are
200k extrapolations that Flight 3's flush cadence was sized against), and
whether `RRF_K` / `candidate_k` / the Flight 5 DD-3 reserved slot are load-bearing
constants or arbitrary ones.

## Context

**This leg produces numbers and a recorded interpretation.** It changes product
code only where the numbers demand it. Two mission open questions close here.

**DD-5 narrows the Windows claim deliberately.** Three Windows rungs test
whether Windows cost is **linear in N** — *not* an N-independent Windows/Linux
ratio, which would need matching Linux rungs. The flight does not re-measure
Linux, because nothing downstream depends on the ratio: Flight 3's flush
cadence was sized against **absolute Windows figures**, and the ratio was only
ever the means of producing them. Per `mission.md:255`'s standing rule, Linux
numbers are discounted explicitly rather than quietly compared against.

**DD-10's premise was false and has been corrected upstream.** The flight
originally claimed the bench script records nothing about SIMD or numkong
linkage. It has recorded it since **Flight 2 Leg 5** (`c315cf5`):
`bench_vector_store.py:102` imports `_usearch_acceleration` and `host_facts()`
(`:210-225`) emits `"usearch_acceleration"` — the same function the `doctor`
probe uses. The supporting evidence was a `grep 'simd\|simsimd\|numkong'`
that returns nothing because the identifier is `usearch_acceleration`, which
contains none of those substrings.

**The hazard is still real; the gap is narrower.** `usearch` swallows its own
numkong `ImportError` (Flight 1 log `:93-95`) — a bundle missing
`numkong._numkong` still imports, still answers searches, and still prints a
clean `OK`. Every published Windows wheel is `simd=serial` with zero `nk_*`
refs (`mission.md:249-252`). What is **actually** missing is **per-cell**
visibility: `host_facts()` is printed once by the parent and is never called
in a `--child` invocation, whose whole stdout contract is one rendered
markdown row. A forked cell therefore cannot report the backend it ran under.
**Numbers measured under an unrecorded backend are not measurements — and a
parent-only record does not cover a per-cell fork.**

**DD-4 forbids a quality claim.** The sweep answers *"are these constants
load-bearing?"*, never *"is this value better."* There is no relevance ground
truth in the tree and this leg does not manufacture any.

Legs 1, 2a and 2b have landed but are **not committed**. Do not revert or
re-stage them.

## Inputs

- `scripts/bench_vector_store.py` — `--corpus`/`--n` (default 1_000_000)/
  `--cells`/`--k`/`--seed`/`--data-dir`/`--out`/`--child`; per-cell child
  processes for clean `peak_rss_MB`; `host_facts()` at `:210-225` **already**
  emits `usearch_acceleration` via the `_usearch_acceleration` import at
  `:102`; `_TABLE_HEADERS`/`render_row` at `:738-796` — the seam AC-3 changes
- `ci/tasks/windows-installer-build.yml` — the task shape to mirror: per-build
  venv (never the persistent `C:\Python311`), and an explicit `$LASTEXITCODE`
  check after **every** native command
- `ci/tasks/windows-tests.yml` — the worker-probe task AC-1 re-runs
- `ci/README.md:78` — `fly -t the-one execute -c <task> -i repo=.`
- `the_one/knowledge/retrieval.py` — `RRF_K = 60` (`:93`), `_candidate_k`
  (`:160`), `SEMANTIC_QUERY_TIMEOUT = 2.0` (`:112`), the Flight 5 DD-3 reserved slot
- `the_one/knowledge/indexer.py:49-51` — **Flight 3's flush cadence
  constants**: `FLUSH_MIN_CHUNKS = 2000`, `FLUSH_MIN_SECONDS = 15.0`,
  `FLUSH_SAVE_MULTIPLIER = 10.0`, consumed adaptively as
  `max(FLUSH_MIN_SECONDS, FLUSH_SAVE_MULTIPLIER × last_flush_seconds)`. These
  are what AC-12/AC-13 gate on
- `flights/02-storage-and-embedding-foundation/flight-log.md:1654-1657` — the
  raw full-precision Windows/Linux 200k table AC-8 compares against; `:1659-1661`
  — the per-metric ratio spread AC-7 cites
- `flights/02-storage-and-embedding-foundation/flight-log.md:~2135-2143` —
  build 59/60: a multi-hour `fly execute` killed because the **client** died
  (host OOM), fixed by relaunching detached
- `the_one/diagnostics.py:378-415 — _usearch_acceleration`; `tests/test_doctor.py:596-650`
  — the `USES_NUMKONG` monkeypatch precedent (AC-4)
- `tests/test_kb_manager.py` — `conn` / real `UsearchStore` / `chunk_repo` /
  `_make_manager` fixtures: the right wiring precedent for AC-14's sweep,
  because `IndexingManager` already keeps vector ids and chunk ids aligned
  *(`tests/test_kb_retrieval.py` pairs a real repo with a **stub** store and
  does not)*

## Outputs

- `ci/tasks/windows-vector-bench.yml`
- Per-cell backend visibility in the bench script's table output (the
  host-level field already exists)
- Measured ladder results with a recorded interpretation
- Sweep results with DD-4's boundary stated
- Flight 3's flush constants either re-confirmed or changed with evidence
- Two mission open questions closed

## Acceptance Criteria

**Worker (prerequisite, re-verified at run time)**

- [x] AC-1 — **First step**: `fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=.`
      runs green. A planning-time confirmation is not a run-time one — the
      `fly` login expires and the worker is shared with `build-windows-installer`,
      which auto-triggers after `ci` passes. If this fails, stop and report;
      it is a worker problem, not a bench-task bug.

**Backend recording (DD-10)**

- [x] AC-2 — **Confirm and REUSE the existing host-level field. Do not build a
      second one.** `bench_vector_store.py:102` already imports
      `_usearch_acceleration`; `host_facts()` (`:210-225`) already emits
      `"usearch_acceleration"`. Verify it appears in a parent run's output and
      move on. *(An earlier draft of this criterion told you to build this from
      scratch, on a falsified premise — see Context. Building a second,
      differently-named field is the specific failure to avoid.)*
- [x] AC-3 — **This is the leg's real backend work: per-cell visibility.** The
      backend must appear in **every** cell's row, including `--child`
      invocations. A `--child` run never calls `host_facts()` at all — its
      entire stdout is `render_row(rows[0])` — so the field must become a
      **column threaded through `_TABLE_HEADERS` / `render_row`**
      (`:738-796`), which both the parent's direct path and each child's
      row-print path go through. Extending `host_facts()` cannot reach a child
      and does not satisfy this.
- [x] AC-4 — A run whose numkong import fails still completes and records the
      degraded backend rather than erroring. `_usearch_acceleration` is already
      documented "never raises" and already degrades gracefully — so this is a
      **verification**, not an implementation. Precedent for exercising it:
      `tests/test_doctor.py:596-650` monkeypatches `USES_NUMKONG`.

**The Windows ladder (DD-5)**

- [x] AC-5 — `ci/tasks/windows-vector-bench.yml` exists, invocable by
      `fly -t the-one execute -c ci/tasks/windows-vector-bench.yml -i repo=.`,
      and provisions a **fresh per-run venv** — never the persistent
      `C:\Python311` site-packages (`ci/README.md:95-99`, build 606657's stale
      `hf_xet`).
- [x] AC-6 — Every native command in the task checks `$LASTEXITCODE`
      explicitly. `$ErrorActionPreference = "Stop"` does **not** make PowerShell
      react to a native executable's exit code — builds 606657 and 606698 both
      ran past failed installs for exactly this reason.
- [x] AC-7 — **The tolerance band is fixed and written to the flight log
      BEFORE the first rung runs**, and it is **per-metric, not one blanket
      percentage**: Flight 2's Windows/Linux ratios diverge 5–7× *between*
      metrics at 200k (f16 p95 19.8×, build 34.0×, restore 6.9×), so a single
      band would be far too loose for one metric and too tight for another.
      **Default, unless the Developer has a better-argued one: ±25% against the
      linear projection from this leg's own 200k rung, applied separately to
      `build_s`, `save_ms` and `p95_ms`.**
      **Ordered explicitly, because the two requirements read as contradictory
      in an earlier draft**: (1) run the 200k rung **twice** and record both;
      (2) compute the observed delta; (3) **write the band into the flight
      log**; (4) only then run 500k. Calibrating at 200k leaks no information
      about *linearity* — it measures instrument noise on a shared,
      uncontainerised worker — so it does not reintroduce the anti-pattern.
      Deciding the band after seeing **500k** is what would. State in the
      write-up that two runs bound a **single observed delta, not a variance
      estimate** — an honest limitation given the multi-hour cost.
- [x] AC-8 — The 200k rung runs and its figures are compared against Flight 2's
      recorded Windows 200k table at
      **`flights/02-storage-and-embedding-foundation/flight-log.md:1654-1657`**
      (full precision: f16 `build_s` 1155.97, `save_ms` 1907.855, `p95_ms`
      17.968; i8 `build_s` 497.12, `save_ms` 1028.898, `p95_ms` 8.458).
      "Materially" means outside AC-7's band. **If they disagree, stop** — the
      apparatus or the worker has changed and the ladder measures nothing until
      that is explained. *(The flight-debrief carries only the extrapolation
      method and caveats, not these numbers; an earlier draft cited it.)*
- [x] AC-9 — The 500k rung runs, and **the Developer's first pass ENDS THERE**,
      with the measured curve in the flight log and an ordinary
      `[HANDOFF:review-needed]`. The Flight Director takes the operator's
      go/no-go on the 1M rung and spawns a **second Developer pass** for the
      remainder (AC-10 at 1M, AC-11's interpretation, AC-12).
      *(An earlier draft asked the Developer to "escalate mid-leg and resume on
      the answer." This project's signal vocabulary — `[HANDOFF:review-needed]`,
      `[HANDOFF:confirmed]`, `[BLOCKED:reason]`, `[COMPLETE:leg]` — has **no
      mid-leg checkpoint**, and `[BLOCKED:…]` is documented as "stop, revert,
      escalate", which would discard hours of real measurement. Two passes
      reuse the existing vocabulary with no process invention.)*
- [x] AC-9a — **Closed as not-required, not passed.** The operator decision
      (2026-09-20, flight log) stopped the ladder at 500k with no pass 2, so
      the self-contained-handoff requirement this AC exists for is moot —
      there is no fresh Developer to resume at 1M. The flight-log entry
      nonetheless carries the declared band, both 200k figures, and the 500k
      figures, so the record satisfies the letter of the requirement even
      though its purpose (a resumable handoff) was never exercised.
- [x] AC-10 — Each **run** rung records `peak_rss_MB` per cell from its own
      child process (200k f16/i8, 500k f16/i8 all present in the flight log).
      **Closed as deliberately-not-run for the 1M cell specifically** — the
      1M rung this AC was paired with in AC-9's pass-2 assignment
      ("AC-10 at 1M") was never run, per the operator's stop-at-500k decision;
      there is no 1M `peak_rss_MB` figure and none is implied. Flight 2's
      pre-fix cumulative-watermark figures (F2 log `:865-879`) are not
      compared against anywhere in this leg's tables.
- [x] AC-11 — The interpretation states plainly whether Windows cost is linear
      in N, and **explicitly discounts the Linux comparison** rather than
      implying one.

**Flush constants**

- [x] AC-12 — Flight 3's flush cadence constants are re-checked against the
      measured curve. Either re-confirmed with the number that confirms them,
      or changed with the number that forces the change. A silent pass is not
      an outcome.
- [x] AC-13 — **Did not fire.** Every measured flush overhead (7.39%–9.09%,
      see AC-12's table) sits well inside Flight 3's 15% divert threshold, so
      the measurement shows the cadence is imprecise-but-fine, never wrong —
      the divert trigger this AC exists to catch was checked for and not
      found. `the_one/knowledge/indexer.py` is untouched by this leg.

**The fusion sweep (DD-4)**

- [x] AC-14 — A sweep over `RRF_K` and `candidate_k` against a real corpus,
      run on Linux (it measures fusion arithmetic, not a platform), reporting:
      rank churn in the returned top-`limit` against the shipped constants,
      the Flight 5 DD-3 reserved slot's **fire rate**, and the overlap curve.
- [x] AC-15 — **No relevance judgments are manufactured and no "better" value
      is recommended.** The write-up answers whether the constants are
      load-bearing or arbitrary, and the mission open question closes as
      *"fixed, and here is the evidence the fixing is not arbitrary"* — never
      as *"tuned."*
- [x] AC-16 — The write-up states what the sweep **cannot** conclude: it would
      not catch a genuine quality regression in fusion. Named so a future
      mission that wants a real relevance benchmark knows what it is buying.
- [x] AC-17 — If the sweep shows the constants are **arbitrary** (the result
      set barely moves across the grid), say so plainly. That is a legitimate
      and useful finding, not a failed measurement.

**Gates**

- [x] AC-18 — `make test-unit` green; `ruff check` and `ruff format --check`
      clean. The bench script and CI task are both in ruff's scope
      (`the_one/ tests/ scripts/`). **Result**: ruff check/format both clean;
      `make test-unit` 4,809 passed, 10 skipped, 616 deselected, 1 failed.
      The one failure (`test_kb_watcher.py::TestStopAndDrain::test_drain_three_live_entries_under_a_second`)
      was re-run standalone and as its whole file — passed both times — and
      recorded in the flight log as a timing flake under full-suite host
      load, not a regression from this leg's changes.
- [x] AC-19 — Flight log carries: AC-7's pre-declared tolerance, every rung's
      raw figures with the recorded backend, AC-11's interpretation, AC-12's
      outcome, and the sweep's results with AC-15/AC-16's boundaries.
- [x] AC-20 — The two mission open questions are updated in `mission.md` with
      the answers and their evidence — the Windows 1M re-measure, and whether
      the fusion balance is operator-tunable or fixed.

## Verification Steps

- AC-1 — `fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=.`
- AC-2/3/4 — run the bench locally (`--corpus synthetic --n 1000 --cells usearch:f16`)
  and confirm the backend field appears in both a direct and a `--child`
  invocation. AC-4 can be exercised by monkeypatching the numkong import.
- AC-5/6 — `fly -t the-one execute -c ci/tasks/windows-vector-bench.yml -i repo=.`
- AC-8 — compare against Flight 2's debrief figures before proceeding.
- AC-14 — a script or test harness under `scripts/`; it need not be a CI task.
- AC-18 — `make test-unit` verbatim, alone, foreground.

## Implementation Guidance

1. **Re-verify the worker first (AC-1).** Everything else in this leg depends
   on it and a failure there is cheap to diagnose only if it happens before a
   new task is in play.

2. **Write the tolerance down before measuring (AC-7).** This is the leg's one
   real discipline requirement. A checkpoint whose threshold is chosen after
   the data arrives is not a checkpoint.

3. **Mirror `windows-installer-build.yml`'s two hard-won lessons** — the
   per-build venv and the per-command `$LASTEXITCODE` check. Both exist because
   a real build shipped a wrong artifact. Read its comments; they name the
   build numbers.

4. **The 200k rung is a calibration, not a data point.** Its job is to prove
   the apparatus still reproduces Flight 2's measurement. If it does not, the
   ladder is measuring something other than what it thinks.

5. **Escalate at 500k (AC-9) — do not decide.** Hand back with the curve. The
   flight names this as an operator decision point precisely because the
   remaining hours on a shared worker are a cost the operator owns.

6. **For AC-3, change `render_row`/`_TABLE_HEADERS`, not `host_facts()`.**
   A `--child` invocation prints exactly one line and never calls
   `host_facts()`. Threading the backend as a table **column** is the only
   route that reaches both the parent's direct path and every child's row.

6a. **For AC-14's sweep, both knobs are module globals read at CALL time**, so
   monkeypatching works with no import-capture problem. `RRF_K` is read inside
   `_fuse`; `candidate_k` derives from three globals
   (`_CANDIDATE_K_MULTIPLIER`, `_CANDIDATE_K_FLOOR`, `_CANDIDATE_K_CEILING`)
   via `_candidate_k(limit)`. **Prefer monkeypatching `_candidate_k` itself**
   over the three constants — one seam, and it makes the swept value explicit
   in the harness rather than implied by arithmetic.

6b. **The sweep needs a DB-backed corpus, which is heavier than the bench's.**
   `bench_vector_store.py --corpus real` inserts raw vectors straight into the
   `VectorStore` — no `kb_chunks`, no FTS5, no `kb_items`. `retrieval.search()`
   needs all three, with **chunk ids and vector ids consistent**.
   - Reuse `collect_real_corpus_chunks` (`:584-598`) for *content*.
   - For *wiring*, use **`tests/test_kb_manager.py`'s fixture shape** — `conn`,
     a real `UsearchStore(conn, …)`, `chunk_repo`, `_make_manager` — and drive
     `IndexingManager` over a real folder. **Not** `tests/test_kb_retrieval.py`:
     its one DB-backed test pairs a real `KBChunkRepository` with a **stub**
     vector store, so it never demonstrates real-store-plus-real-repo with
     aligned ids. `IndexingManager` is the production code that already solves
     that alignment; hand-gluing the bench's raw-vector path to an FTS5-only
     fixture means re-inventing it.
   - Corpus size is the Developer's call per the flight's Adaptation Criteria;
     Flight 2's real corpus was ~31k chunks.

7. **For the sweep, resist the pull toward a recommendation.** The interesting
   output is a *sensitivity surface*, not an optimum. If churn is near zero
   across the grid, the honest conclusion is "these constants do not matter
   much at this corpus size," which is worth knowing and worth saying.

8. **Do not touch `retrieval.py`'s constants** unless the sweep produces a
   reason the write-up can defend under DD-4's boundary. Changing a constant
   because a sweep showed movement is exactly the "tuned" claim DD-4 forbids.

## Edge Cases

- **Worker busy with `build-windows-installer`** — it auto-triggers after `ci`
  passes. Report contention rather than queueing indefinitely.
- **1M corpus exceeds the worker's disk budget** — check before the rung, not
  during. Flight 2's `--n` default is already 1_000_000, so the generator is
  proven at that size on *some* host, not necessarily this one.
- **A multi-hour rung killed with the `fly` CLIENT, not by a server timeout.**
  Concourse task YAML has no `timeout:` field — that is a pipeline-step
  attribute, unavailable to the ad-hoc `fly execute -c <task>` shape AC-5
  requires, and no `ci/tasks/*.yml` in this repo sets one. The real precedent
  is Flight 2's **build 59**, which died at 44 minutes because the local `fly
  execute` client process was killed (host OOM during a concurrent unit-gate
  run), taking the build's output with it. The fix, used for build 60: launch
  detached (`setsid nohup … & disown`) and poll with `fly watch -b <build>`.
  Use that pattern for every rung past 200k, and **do not run `make test-unit`
  concurrently with a rung**.
- **`numkong` present but unlinked** — the expected Windows state, not a
  failure. AC-2's field must distinguish *unlinked* from *missing* from
  *linked*, or it cannot tell a genuine DLL-resolution failure from the
  ordinary published-wheel condition (`mission.md` Known Issues says the
  `doctor` probe already makes this distinction — mirror its vocabulary).
- **Sweep over a corpus too small to fire the reserved slot** — then the fire
  rate is zero and that is a finding about the corpus, not the constant. Say
  which.

## Files Affected

- `ci/tasks/windows-vector-bench.yml` — new
- `scripts/bench_vector_store.py` — the per-cell backend column
  (`_TABLE_HEADERS`/`render_row`)
- `scripts/` — the sweep harness
- `the_one/knowledge/indexer.py` — **only** if AC-12 forces a flush-constant
  change (and AC-13 has not diverted)
- `the_one/knowledge/retrieval.py` — **only** if AC-17 forces it
- `missions/24-knowledge-bases/mission.md` — the two open questions
- `missions/24-knowledge-bases/flights/07-mission-close/flight-log.md`

## Citation Audit

Verified against the working tree on `flight/07-mission-close` (2026-09-19),
carrying Legs 1, 2a and 2b uncommitted. **None of the files this leg touches
are modified by those legs**, so unlike Leg 2b's citations these do not drift
within the flight:

| Citation | Status |
|---|---|
| `scripts/bench_vector_store.py:837-861 — _build_arg_parser` — `--corpus`, `--n` (default `1_000_000`), `--queries`, `--cells`, `--k`, `--seed`, `--data-dir`, `--out`, `--child` | verified |
| `scripts/bench_vector_store.py:102` — `from the_one.diagnostics import _peak_rss_bytes, _usearch_acceleration`; `host_facts()` `:210-225` emits `"usearch_acceleration"`, present since Flight 2 Leg 5 (`c315cf5`) | **FALSIFIES the first draft's row**, which asserted the script records nothing about SIMD/numkong on the strength of a grep that cannot match the identifier `usearch_acceleration` |
| `scripts/bench_vector_store.py:738-796 — _TABLE_HEADERS`/`render_row`; a `--child` run prints only `render_row(rows[0])` and never calls `host_facts()` (AC-3) | verified — this is the real remaining gap |
| `the_one/knowledge/indexer.py:49-51 — FLUSH_MIN_CHUNKS=2000, FLUSH_MIN_SECONDS=15.0, FLUSH_SAVE_MULTIPLIER=10.0` (AC-12/AC-13) | verified — **added**; the first draft gated on these without citing them |
| `flights/02-.../flight-log.md:1654-1657` — the Windows/Linux 200k table at full precision; `:1659-1661` — per-metric ratios (f16 p95 19.8×, build 34.0×, restore 6.9×) (AC-7/AC-8) | verified — **corrected**; the first draft cited the debrief, which carries only the method |
| `the_one/diagnostics.py:378-415 — _usearch_acceleration`, "never raises", reports `numkong=yes, simd=haswell`; `tests/test_doctor.py:596-650` monkeypatches `USES_NUMKONG` (AC-4) | verified |
| No `ci/tasks/*.yml` sets a `timeout:`; Concourse task YAML has no such field (Edge Cases) | verified |
| `ci/tasks/windows-installer-build.yml` — per-build venv with the build-606657 rationale in-comment; explicit `$LASTEXITCODE` checks with the build-606698 rationale (AC-5, AC-6) | verified |
| `ci/tasks/windows-tests.yml` — the worker probe AC-1 re-runs; `platform: windows`, `inputs: [repo]` | verified |
| `ci/README.md:78` — `fly -t the-one execute -c ci/tasks/windows-tests.yml -i repo=.`; `:92-99` — `build-windows-installer` auto-triggers after `ci`, worker uncontainerised | verified |
| `the_one/knowledge/retrieval.py:93 — RRF_K = 60`; `:112 — SEMANTIC_QUERY_TIMEOUT = 2.0`; `:160 — _candidate_k`; the reserved slot at `:220-234` | verified |
| `mission.md:249-252` — every published usearch Windows wheel is `simd=serial`, 0 `nk_*` refs vs 54 on Linux; `:255` — "benchmarks on Windows, or discounts Linux numbers explicitly" | verified |
| Flight 1 log `:93-95` — usearch swallows its own numkong `ImportError`; a missing bundle still imports and prints a clean `OK` | verified |
| Flight 2 log `:865-879` — pre-fix `peak_rss_MB` figures are cumulative process-lifetime watermarks (AC-10) | verified |
| `fly` installed at `~/.local/bin/fly`; target `the-one` token valid to 2026-09-20 22:56 UTC | verified 2026-09-19 — **re-verify at AC-1; this expires** |

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`: 4,809 passed / 1 flaky-under-load
      failure re-confirmed as non-regression in isolation; ruff check/format
      both clean)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Do **NOT** commit — the Flight Director commits after the flight-end review
- [x] Signal `[HANDOFF:review-needed]`
