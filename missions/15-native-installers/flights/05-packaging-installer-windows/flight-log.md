# Flight Log: Packaging & Installer — Windows

**Flight**: [Packaging & Installer — Windows](flight.md)

## Summary

Flight planned 2026-06-14. Status: `in-flight`. Windows-first packaging — the
cross-cutting freeze runtime seam (`clean_subprocess_env` child-env sanitizer,
frozen-detection, `resolve_python` frozen fix, unencoded-I/O audit, the `the-one
doctor` diagnostic) built here and reused by F6 (macOS) / F7 (Linux), plus the
PyInstaller `.spec`, the Inno Setup installer, and a CI packaged-smoke that proves
the frozen-app child-spawn fix against the packaged binary on a `windows-2022`
runner. No legs executed yet.

---

## Leg Progress

_(none yet)_

---

## Decisions

_(runtime decisions not in the original plan will be recorded here)_

---

## Deviations

_(departures from the planned approach will be recorded here)_

---

## Anomalies

_(unexpected issues will be recorded here)_

---

## Session Notes

### 2026-06-14 — Flight Director: execution started

- Loaded `/agentic-workflow` for Flight 5 (mission 15, the-one). Crew file
  `leg-execution.md` validated (Crew / Interaction Protocol / Prompts present, all
  prompts fenced). Branched `flight/05-packaging-installer-windows` off the
  flight/04 HEAD (Flight 5 depends on Flight 4's `the-one app` entry; flights 02–04
  are stacked, not yet merged to main — following the established stacked-branch
  pattern). Flight `ready` → `in-flight`.
- Plan: 4 autonomous legs (1 frozen-runtime-seam-and-doctor, 2 pyinstaller-windows-spec,
  3 inno-windows-installer, 4 packaged-smoke-ci) implemented without per-leg commit;
  single flight review + commit after Leg 4. Leg 5 (docs-and-verify + optional HAT)
  has an interactive component — handled operator-guided at flight close.

### Flight Director Notes

_(orchestration decisions logged here as the flight proceeds)_

---

### 2026-06-14 — Flight planned

- Split from the original single "Packaging & installers" flight into one packaging
  flight per OS (Windows-first); mission flight tail reshaped (release pipeline →
  Flight 8). Operator-confirmed scope (Windows-first) and verification (CI
  packaged-smoke on the Windows runner).
- Planning recon: PyInstaller one-dir confirmed; the `.spec` hidden-import contract
  sourced from PyInstaller official docs; six unencoded-I/O sites + the
  `resolve_python`/`sys.executable` frozen footgun confirmed against current code.
- Two design-review cycles (Architect). Cycle 1 corrected the load-bearing DD2
  premise: `_build_subprocess_env` builds children from a strict allowlist, so the
  loader-path vars (`LD_LIBRARY_PATH`/`DYLD_*`/`*_ORIG`) never leak — the only
  mutated allowlisted var is `PATH`, so the spawn-fix is scoped to PATH-cleaning
  (strip the `_MEIPASS`/bundle dir + augment), no dead restore-`_ORIG` code. Also
  added DD8 (`.env`-discovery anchoring), the `factory.py:104` encoding disposition,
  the MCP `build_stdio_environ` PATH-precedence flag, the `detect_runtimes()`
  factoring note, and `freeze_support()`. Cycle 2 confirmed the corrections and
  caught one stale phrase (now fixed). Spec is codebase-validated.
- Flight marked `ready` 2026-06-14.
