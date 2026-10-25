# Flight Log: Windows on shared metadata, and one release

**Flight**: [Windows on shared metadata, and one release](flight.md)

## Summary
*(written at landing)*

---

## Reconnaissance Report

Sources: the Flight 3 debrief (`../03-macos-app/flight-debrief.md`, Recommendations and Action Items) and the mission's Flight 4 bullets. Walked against `f98f2c7`, 2026-10-25.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| R1: per-platform boot policy out of `shell.py` | confirmed-live | `shell.py` run/_boot: 11 `darwin` + 2 `win32` reads; `window_control.py`: 4 `darwin` reads (100, 165, 170, 228) | DD1, leg 2 (operator: in flight) |
| R2: probes fail loudly with a positive control | confirmed-live (a process rule) | n/a; it applies to this flight's probe | DD5's W1-W5 rows, `FAIL not-run` |
| R3: strict version grammar end to end; `[windows]` in `product.toml` | confirmed-live | `render.py::RELEASE_RE`; `product.toml` has no `[windows]`; `pyproject.toml` `version = "0.11.8"` hard-coded | DD3, DD6 |
| R4: probe Inno's close-running-app behaviour first | confirmed-live | `the-one.iss` `CloseApplications=force` + `KillRunning` (`taskkill /F`) | DD2, leg 1 (W3, W4) |
| R5: the pywebview canary and a `lifecycle` dispatch in the bump procedure | confirmed-live | squawk 0262 open; no doc names the procedure | DD9 (0262), leg 4 |
| A1: budget the macOS runs, one spare | confirmed-live | n/a | DD8: 4 runs |
| A2: consolidate the packaging workflows and the shell helpers (Flight 3 DD8's deferral) | partially-satisfied in scope | three workflows, two with `workflow_call`; `windows-installer.yml` has neither dispatch nor `workflow_call` | DD7 composes them; shell-helper merging is deferred again (DD3's "not done here") |
| A3: Windows `PATH`-walk regression tests | partially-satisfied | `tests/test_macos_runtime_seam.py::test_windows_alias_shadowing_walks_to_the_real_python` is the only one | leg 3 adds the rest |
| A4: contributor check additions (zsh/nvm, logout, quit during boot) | confirmed-live | `tests/behavior/macos-app-install.md` (draft, 12 steps) lacks them | DD10, leg 4 |
| A5: squawks 0260, 0261, 0262 | confirmed-live (all `open`) | `squawks/026{0,1,2}-*.md` | DD9 (operator: all three) |
| M1: dynamic `pyproject` version, after Mission 31 merges | confirmed-live; its precondition was amended | Mission 31 still active; `uv.lock` records `version = "0.11.8"` | DD6; additive, rebase on `main` |
| M2: tag-triggered release of all four behind the audit; a dry run first | confirmed-live | `windows-installer.yml` is the only tag workflow | DD7, DD8 |
| M3: the contributors' check on real Macs | confirmed-live | no run log exists | DD10, leg 6 |

No item was found already satisfied. Nothing is retired.

---

## Flight Director Notes

### Planning (2026-10-25)
- **The operator's answers:**
  - Release: "lets just cut a regular (minor) release at the end, Ill wait for confirmation before we close it. If we need to iterate we can cut patches."
  - Contributors: "just publish as part of a regular release, contibutors can download."
  - Windows: "Thats fine, ill upgrade locally after the tests just the like contributors will and report any issues."
  - Boot-policy refactor: "do it in flight."
  - Gate: "the real v release is the gate."
  - Follow-up answers: "amend the charter, we can release during this flight but only after as verified as we can get it"; dry run first; squawks 0260, 0261 and 0262; "I'll log fly in for fly execute".
- **Charter amendments made in the planning commit:** Mission 31's two "no release" lines are annotated (not rewritten) with the exception. Mission 32's matching constraint is annotated, and its "release vehicle" open question is resolved.
- **The macOS upgrade test for contributors:** with no second release yet, the dry run's `.dmg` (14-day retention) serves as N and the release as N+1. If it has expired, that step runs at the first patch release.
- **Design review (Architect, Opus), cycle 1: approve with changes.** Three high issues:
  - the Windows freeze could not carry a staged version, so DD3 now freezes from `stage.py`;
  - UAC is off on the runner, so DD2's elevation half is field-only, and DD11 proposes a two-step operator upgrade;
  - the v0.11.8 → new upgrade was never rehearsed, so DD5 gains an old-to-new row and W6.
  - Plus 17 medium and low items, all applied: the `shell.py` count, lazy policy selection, behaviour equivalence, 0261 as phase 2b, an early macOS run, a later `release.yml` stub, N+2 deferred, the 0260 fixture with no golden file, `--out`, the lock lanes, environment pins, per-leg re-checks, publish hardening, artifact names, phases, small items.
- **Cycle 2: approve with changes.** One high issue: `stage.py` dies without git, which `fly execute` and possibly the Windows worker lack, so leg 3a adds a no-git fallback and a per-build `--out`.
  - Medium: tag-path input fallbacks and a YAML test; the uninstall-time quit; each lane's uv version; row-to-phase attribution.
  - Low: 14-day `windows-installer` retention, leg 6 order, the PATH-walk tests' owner, `/DAppVersion` dropped.
  - All applied. That was the last allowed cycle, so the flight goes to the operator.
- **Approved (2026-10-25), operator: "approved, I've logged in".** The Windows field upgrade takes DD11's two-step form as written (v0.11.8 → `0.12.0.dev1` → `v0.12.0`). `fly` is logged in; it is re-checked at leg 3a.
- **The plugin notice:** mission-control 1.2.3 is available (1.2.2 installed). The operator was told; the Flight Director does not update plugins.

---

## Leg Progress
*(entries added as legs run)*
