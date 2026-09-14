# Squawk 0047: `agents.md` has no diagnostics/`doctor` section or the three Flight 1 conventions

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-12
**Completed**: 2026-09-14

## Report

`the_one/diagnostics.py` grew from ~330 to 866 lines in Mission 24 Flight 1
(three new probes, native-library loading, an offline-fetch guard, a Windows
ctypes path) and `the_one/agents.md` — the canonical internals reference — has
no section for it at all. The flight rediscovered several of its invariants
from source (extensionless `loadable_path()`, the `_vector_probe_outcome`
frozen-only gating idiom). Three conventions the flight debrief names as
load-bearing also need entries in "Project Conventions":

- `probe-must-not-pass-by-download` — assert the packaged path exists via
  `importlib.resources` *before* any loader that can fall back to a network
  fetch, and force offline in-process (`HF_HUB_OFFLINE` env var **and**
  `huggingface_hub.constants.HF_HUB_OFFLINE`, which is bound at import).
- `report-what-you-got` — a probe or its test asserts on the concrete resolved
  value in the emitted detail line (dtype off the array, bytes off the file,
  `numkong=yes|no`), never on a bare `ok`.
- `autouse-fixture + dedicated-real-load-file` — an unconditional gate that
  loads something expensive gets a function-scoped autouse patch in the shared
  test file and exactly one real load in its own file (pytest has no opt-out
  from autouse; module scope cannot take `monkeypatch`).

The section should also carry the stub-`ctypes.WinDLL` test pattern for
Windows-only branches (`tests/test_doctor_embedding_model.py::TestPeakRssWindowsBranch`).

## Evidence

- `grep -n -i diagnostics the_one/agents.md` → no matches; `wc -l the_one/diagnostics.py` → 866
- `the_one/diagnostics.py:_vector_probe_outcome` — the shared frozen-only gating helper; `_force_hf_offline`, `_probe_embedding_model`, `_peak_rss_bytes` — the invariants to document
- `missions/24-knowledge-bases/flights/01-dependency-and-packaging/flight-debrief.md` — Recommendations 3 and 4

## Corrective Action

Added two pieces to `the_one/agents.md`, matching its existing voice/layout:

1. **`### Diagnostics (`the-one doctor` / `the_one/diagnostics.py`)`** — a new
   subsection under `## Subsystem contracts`, placed after the existing
   `### Dev iteration` subsection (the last one in that `##` section, right
   before the `---` delimiter that precedes `## Provider type extension
   checklist`). Covers: what `run_doctor` is and its exit-code/stdout
   contract; the three consumers of that contract (`the_one/main.py`,
   `tests/test_doctor.py`, `.github/workflows/windows-installer.yml` +
   `ci/tasks/windows-installer-build.yml`); the eight gates as a table
   (frozen-only vs unconditional); the `ProbeResult` / never-raises /
   assert-a-concrete-value probe contract; the `_vector_probe_outcome`
   frozen-only gating idiom and why `_probe_embedding_model` deliberately
   does not use it; the offline invariant (`importlib.resources` existence
   check before `from_pretrained`, `_force_hf_offline` setting both the env
   var and the already-bound `huggingface_hub.constants.HF_HUB_OFFLINE`);
   the `numkong=` / `_numkong_extension_state()` diagnostic and the
   Windows `simd=serial` upstream-wheel explanation; `_peak_rss_bytes()`
   (POSIX KiB-vs-bytes trap, Windows ctypes HANDLE-truncation lesson);
   packaging notes (`collect_dynamic_libs` vs `collect_data_files` for
   `sqlite_vec`, the `the_one.embeddings` hiddenimports entry, `upx_exclude`
   entries); and the test conventions (autouse fixture, dedicated real-load
   file, immutable-`sqlite3.Connection` module-swap trick, Windows-branch
   stub pattern).
2. **Three new `### `kebab-name`` entries under `## Project Conventions`** —
   `probe-must-not-pass-by-download`, `report-what-you-got`, and
   `autouse-fixture + dedicated-real-load-file` — appended to the end of the
   `### Project-wide` group, immediately before `### Mission-specific (M16)`
   (these are general project-wide patterns, not mission-scoped, so they
   belong in that group rather than a new Mission-specific subsection). Each
   carries a one-paragraph statement, an Applies-to/Does-not-apply pair, a
   worked example citing `file:symbol`, and a `Source:` line back to the
   M24 F01 flight (DD-5, DD-7, and the flight-debrief's Key Learnings /
   Recommendations §3 respectively).

Shape rationale: the squawk's report and the flight-debrief both frame this
as "the flight rediscovered invariants from source that should have been
written down the first time" — so the section is written as an internals
reference (function-by-function, with the *why* behind each non-obvious
choice) rather than a narrative retelling of the flight, matching how the
adjacent `### Self-configuration surface contract` and encryption-rotation
subsections in the same `## Subsystem contracts` section are written. Cited
by `file:symbol` throughout per the task instruction, since line numbers in
`the_one/diagnostics.py` will drift.

Net size: `the_one/agents.md` grew from 1544 to 1616 lines (+72, all
additive — no existing line touched). The file's own convention is long,
unwrapped paragraph lines rather than hard-wrapped prose, so each "line" in
that delta is typically a dense multi-sentence paragraph; the added prose is
proportionate to the two deliverables' scope even though the raw line count
reads lower than a hard-wrapped 120–200 line estimate would.

### Review pass (post-first-draft corrections)

A review of the first draft found five inaccuracies — all in claims that were
copied without checking against source. Fixed in `the_one/agents.md`:

1. The "Probe contract" paragraph claimed every `_probe_*` wraps its body in
   a broad `except Exception` and never raises. False for two of the eight:
   `_probe_child_spawn` catches only `(OSError, subprocess.SubprocessError)`
   and `_probe_interpreter` catches only `FrozenInterpreterError` — an
   unexpected exception from either propagates out of `run_doctor`. Reworded
   to name the six broad-catch probes and the two narrow-catch probes
   explicitly.
2. The `upx_exclude` enumeration listed 5 entries; the spec
   (`packaging/windows/the-one.spec`) has 6 — `"_hf_xet*"` (hf-xet Rust
   transfer core) was missing. Corrected the list and the framing sentence
   ("three vector-store artifacts plus the embedding closure's three native
   payloads").
3. Three places (the `autouse-fixture + dedicated-real-load-file` convention
   entry, and two spots in the Diagnostics section) said `tests/test_doctor.py`
   has "16 `run_doctor(` call sites". A verified `grep -n "run_doctor("` count
   is 18 (excluding the file's own explanatory comment at line 35 and one
   test-method name, `test_skip_keeps_result_pass_in_run_doctor`, whose name
   happens to end in the substring `run_doctor(` right before its `self`
   parameter — not an actual call). Corrected all three to 18. The same stale
   "16" also appears in a comment at `tests/test_doctor.py:~35` and in
   `tests/test_doctor_embedding_model.py`'s module docstring (line 4) — both
   are OUTSIDE this squawk's doc-only scope (source-file comments, not
   `agents.md`) and are left untouched here; they are a separate squawk
   candidate for a follow-up source-comment fix.
4. The "Frozen-only gates downgrade..." sentence implied every frozen-only
   probe's skip detail uses the `"skipped — ..."` em-dash form. Only the
   shared `_vector_probe_outcome` helper (used by `_probe_sqlite_vec` and
   `_probe_usearch`) uses that form; `_probe_desktop_shell`,
   `_probe_llm_providers`, and `_probe_model_catalog` each emit a
   parenthesized `"skipped (...)"` form instead. Reworded to state both forms
   accurately, with each probe's actual detail string quoted.
5. This artifact's own Corrective Action said `agents.md` grew from 1545
   lines; the verified pre-change count (`git show HEAD:the_one/agents.md |
   wc -l`) is 1544. Corrected — the delta (+72, to 1616) was already right.

## Verification

Doc-only change confirmed: `git status --short` shows only
`squawks/0047-agents-md-diagnostics-section.md` and `the_one/agents.md`
modified. `ruff check the_one/ tests/` → `All checks passed!` (expected and
unaffected, since no Python file changed).

Symbol verification — every symbol named in the new `agents.md` section was
`grep -n`'d against its source file to confirm it exists (all found, ≥1 hit
each; counts below are total occurrences, not just the definition):

- `the_one/diagnostics.py`: `run_doctor` (1), `ProbeResult` (44),
  `_build_subprocess_env` (3), `is_frozen` (9), `_probe_child_spawn` (2),
  `_probe_interpreter` (2), `_probe_desktop_shell` (3),
  `_probe_llm_providers` (4), `_probe_model_catalog` (5),
  `_probe_sqlite_vec` (2), `_probe_usearch` (2), `_probe_embedding_model` (2),
  `_vector_probe_outcome` (8), `_force_hf_offline` (2),
  `_numkong_extension_state` (2), `_usearch_acceleration` (3),
  `_peak_rss_bytes` (3), `detect_runtimes` (2) — 18/18 found.
- `the_one/main.py`: `cli_entry` — found (`def cli_entry()` at line 10).
- `tests/test_doctor.py`: `_stub_embedding_probe` fixture,
  `TestEmbeddingProbeGating`, `test_does_not_use_the_frozen_only_helper` —
  all found.
- `tests/test_doctor_embedding_model.py`: `TestRealLoad`,
  `test_probe_loads_the_committed_weights`, `TestOfflineInvariant`,
  `TestPeakRssWindowsBranch` — all found.
- `packaging/windows/the-one.spec`: `collect_dynamic_libs`,
  `sqlite_vec_bins`, `embedding_datas`, `hiddenimports`, `upx_exclude`, and
  the six `upx_exclude` glob entries (`"vec0*"`, `"compiled*"`,
  `"_numkong*"`, `"tokenizers*"`, `"_safetensors_rust*"`, `"_hf_xet*"`) — all
  found.

Total: every symbol cited in the new section resolves to real source —
zero dangling references.

### Review-fix verification (this pass)

- **`run_doctor(` call-site count**: `grep -n "run_doctor(" tests/test_doctor.py`
  returns 20 matching lines. Excluding line 35 (the file's own explanatory
  comment, `# every \`\`run_doctor(\`\` call in this file`) and line 193 (the
  test method name `test_skip_keeps_result_pass_in_run_doctor(self, ...)`,
  a substring match on the method name, not a call) leaves **18** actual
  `run_doctor(...)` call expressions — matches the reviewer's count. All
  three `agents.md` occurrences of the stale "16" corrected to 18.
- **`upx_exclude` entry count**: `sed -n '391,399p' packaging/windows/the-one.spec`
  shows 6 glob strings (`"vec0*"`, `"compiled*"`, `"_numkong*"`,
  `"tokenizers*"`, `"_safetensors_rust*"`, `"_hf_xet*"`) — checked 6/6 against
  `agents.md`'s corrected enumeration (both the Diagnostics section's
  packaging-notes bullet and this artifact's own symbol-verification bullet
  above).
- **Except-clause check, all eight probes** (`grep -n "except Exception\|except ("
  the_one/diagnostics.py`, cross-referenced against each `_probe_*`'s line
  range):
  - Broad `except Exception` (never raises): `_probe_desktop_shell` (line
    154), `_probe_llm_providers` (line 200), `_probe_model_catalog` (line
    255), `_probe_sqlite_vec` (line 398), `_probe_usearch` (line 529),
    `_probe_embedding_model` (lines 708/755).
  - Narrow catch (CAN propagate): `_probe_child_spawn` (line 77,
    `except (OSError, subprocess.SubprocessError)`), `_probe_interpreter`
    (`except FrozenInterpreterError`, no bare `except Exception` in the
    function body).
  - 6 broad / 2 narrow, matching the corrected "Probe contract" paragraph.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), leg-execution crew — two review cycles; cycle 1 raised three blocking factual mismatches on 0047 against `diagnostics.py`/the spec, all fixed and re-verified in cycle 2
**Verdict**: confirmed — `[HANDOFF:confirmed]` for the batch, 2026-09-14
**Commit**: squawk/turnaround-2026-09-14 (sha recorded in the PR)
