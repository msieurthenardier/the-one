# Squawk 0047: `agents.md` has no diagnostics/`doctor` section or the three Flight 1 conventions

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-12
**Completed**: —

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
*(written at completion)*

## Verification
Doc-only: `ruff` unaffected; review that every named symbol in the new section exists (`grep -n` each against `the_one/diagnostics.py`).

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
