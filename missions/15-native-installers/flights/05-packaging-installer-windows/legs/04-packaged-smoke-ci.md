# Leg: packaged-smoke-ci

**Status**: completed
**Flight**: [Packaging & Installer — Windows](../flight.md)

## Objective

Stand up a `windows-2022` CI job that **builds the frozen one-dir from the Leg-2
`.spec`**, **builds the Inno installer from the Leg-3 `.iss`** (uploading it as an
artifact), and **proves the spawn-fix against the packaged binary** (DD5 layer 3):
frozen `the-one doctor` exits 0 with "child spawn: OK", frozen `the-one serve` answers
`/api/info` 200 with the right version, and the single-instance probe recognizes the
frozen instance — the spawn-fix's only real proof.

## Context

This is the **final autonomous leg** and the flight's load-bearing *verification*. Legs
1–3 produced the runtime seam, the `.spec`, and the `.iss` — all authored on this
Linux host but **never built against a real frozen binary**. Leg 4 closes that gap by
running the freeze + smoke on a GitHub `windows-2022` runner, which is the **only**
apparatus that exercises a real PyInstaller bundle (DD5: no Witnessed behavior test
this flight — the rendered-window GUI HAT doesn't exist yet; the operator's manual
installer HAT is F9). The `the-one doctor` subcommand (Leg 1) is the apparatus the CI
reads: its exit code + "child spawn: OK" line prove `clean_subprocess_env` + PATH
augmentation work on the packaged binary, not just the checkout.

**This leg authors CI YAML — its proof runs post-push on GitHub, not on this host.**
Like Legs 2–3 it can't be executed locally (no Windows runner, no `iscc`, no
PyInstaller-on-Linux). The deliverable is a correct, `actionlint`-clean workflow job;
the **green run is observed when the flight's PR opens** and CI executes. A red smoke
is the flight's central-risk signal (the Divert criterion: if `doctor` stays red on the
packaged binary, escalate — that's the whole-mission spawn gate).

**Absorbs the iscc build (Flight Director decision, see flight-log Decisions).** The
flight.md Verification line ambiguously referenced "(Leg 5)" for the `iscc` installer
build; it is consolidated **here** — this job already provisions `windows-2022` and
builds the one-dir the installer consumes, so adding Inno-install + `iscc` + artifact
upload here avoids a second Windows job.

## Inputs

What exists before this leg runs (post-Leg-3):

- `packaging/windows/the-one.spec` — builds `dist/the-one/` (one-dir, `the-one.exe` +
  `_internal/`). Requires `pip install -e ".[gui,all-llms]"` + `pip install
  pyinstaller` on the runner (the existing `windows` job installs only
  `.[all-llms,dev]` — **no `[gui]`** — so this job needs its own install line).
- `packaging/windows/the-one.iss` — Inno script; `iscc /DAppVersion=<v>
  packaging\windows\the-one.iss` → `packaging/windows/Output/the-one-setup-<v>.exe`.
  Requires **Inno Setup ≥6.3** (for the `x64compatible` arch token).
- `the_one/diagnostics.py` (Leg 1) — `the-one doctor` / `python -m the_one doctor`:
  spawns a probe child through the real env, prints a `child spawn: OK/FAIL` line,
  exits non-zero on failure. The CI reads exit code + stdout.
- `the_one/interfaces/web/app.py:1634` — `@app.get("/api/info")` returns a JSON body
  including `version` (= `the_one.__version__`, 0.2.0).
- `the_one/interfaces/app.py:_select_port` (Flight 4) — the single-instance probe:
  GETs `/api/info`, returns `(port, True)` when a the-one of **our version** already
  answers (DD4 case b). `_wait_until_serving` polls `/api/info` until 200.
- `the_one/__init__.py:3` — `__version__ = "0.2.0"` (injected into the installer
  filename via `iscc /DAppVersion`).
- `.github/workflows/test.yml` — jobs `test` (ubuntu), `browser` (ubuntu, inline
  git-diff path-filter), `windows` (windows-2022, curated subset), `bwrap` (ubuntu).
  This leg adds a **new `windows-packaged-smoke` job** to this file (does not modify
  the existing `windows` job).

## Outputs

- `.github/workflows/test.yml` — a new `windows-packaged-smoke` job.
- `packaging/windows/README.md` — extended with a "CI packaged-smoke" note describing
  what the job proves and how to read a failure.
- (No `the_one/` runtime changes; this is CI + docs.)

## Acceptance Criteria

- [ ] A new job `windows-packaged-smoke` exists in `.github/workflows/test.yml`,
      `runs-on: windows-2022`, `shell: bash` (Git Bash, matching the existing `windows`
      job's PowerShell-quote-stripping rationale).
- [ ] The job installs the **GUI freeze deps**: `pip install -e ".[gui,all-llms]"`
      then `pip install pyinstaller` (the `[gui]` extra is required or the
      pywebview→pythonnet collection import-fails at build time).
- [ ] The job **builds the frozen one-dir**: `pyinstaller --noconfirm
      packaging/windows/the-one.spec`, producing `dist/the-one/the-one.exe`; the build
      step fails the job on any PyInstaller error (incl. a missing pywinpty
      `.pyd`/`winpty.dll` — the Divert trigger).
- [ ] **Packaged-smoke proof against the frozen binary** (the only real proof):
      - (a) `./dist/the-one/the-one.exe doctor` (frozen) exits **0**, and its stdout
        contains both `child spawn: OK` **and** `RESULT: PASS` (the latter also covers
        the frozen `resolve_python` interpreter gate, not just child-spawn) — asserted
        via `set -o pipefail` + grep + the doctor's own exit code.
      - (b) `./dist/the-one/the-one.exe serve` (frozen, backgrounded) is polled on
        `http://127.0.0.1:8484/api/info` until **200** **using an `httpx` Python probe**
        (not `curl` — `httpx` is already a runtime dep and is the exact path the product
        itself polls with, eliminating the Git-Bash-`curl` assumption), and the JSON
        `version` equals `the_one.__version__` (0.2.0). Times out → job fails.
      - (c) **Single-instance (decision input)**: with the frozen `serve` instance up,
        assert the Flight-4 probe, **run from the runner's installed source**, confirms
        the frozen instance advertises an our-version `/api/info` — `python -c "from
        the_one.interfaces.app import _select_port; p, ours = _select_port('127.0.0.1',
        8484); assert ours, (p, ours)"`. This proves the **input** a second frozen `app`
        launch keys on (the frozen instance answers `/api/info` with version 0.2.0 → the
        probe returns `(port, True)` → no second server). It does **not** exercise the
        frozen binary's *own* `_select_port` call — the rendered-window second-launch
        is deferred to the **F9 operator HAT** (DD5; no GUI HAT apparatus this flight).
      - The frozen `serve` process is torn down best-effort at the end
        (`taskkill //F //IM the-one.exe || true` — Windows-native, MSYS-escaped; `kill`
        on a native `.exe` under Git Bash is unreliable). Ephemeral runner → hygiene,
        not correctness; teardown failure must not fail the job.
- [ ] The job **builds the Inno installer**: installs **Inno Setup ≥6.3 pinned** (e.g.
      `choco install innosetup --version=<pinned>`), runs `iscc
      //DAppVersion=$(python -c "import the_one; print(the_one.__version__)")
      packaging/windows/the-one.iss` (note Git-Bash `//D` to avoid MSYS path-munging of
      `/D`), producing `packaging/windows/Output/the-one-setup-0.2.0.exe`, and
      **uploads it** via `actions/upload-artifact` (artifact name e.g.
      `the-one-windows-installer`).
- [ ] The job is **path-filtered** (mirroring the `browser` job's inline git-diff,
      conservative "no base → run") to packaging-relevant paths so most PRs don't pay
      the freeze cost: `packaging/**`, the seam files (`the_one/platform/env.py`,
      `the_one/platform/interpreter.py`, `the_one/platform/shell.py`,
      `the_one/mcp/transports/stdio.py`, `the_one/diagnostics.py`, `the_one/main.py`,
      `the_one/interfaces/app.py`), **plus the smoke's own pass-criteria files**
      (`the_one/__init__.py` — version asserted in proof-b + installer name;
      `the_one/config.py` — the 8484 port; `the_one/interfaces/web/app.py` — the
      `/api/info` endpoint), and `pyproject.toml`. (This flight's PR touches
      `packaging/**`, so the job runs on it.)
- [ ] `actionlint` (or a YAML parse) is clean on the edited `test.yml`; the existing
      `test`/`browser`/`windows`/`bwrap` jobs are unchanged.
- [ ] Host-native unit suite stays green (no `the_one/` runtime changes); the
      `windows-packaged-smoke` job is the only CI addition.
- [ ] **Forward-dependency closure recorded:** this leg discharges the Leg-2 and Leg-3
      forward dependencies (build the frozen one-dir; build the installer). The
      flight-log notes that the *observed green run* lands when the PR's CI executes
      (the design can't run it on this host).

## Verification Steps

- `actionlint .github/workflows/test.yml` (if available; else `python -c "import yaml,
  sys; yaml.safe_load(open('.github/workflows/test.yml'))"`) — clean.
- Read the new job and confirm: `runs-on: windows-2022`; `[gui,all-llms]` + pyinstaller
  install; `pyinstaller … the-one.spec`; the three frozen-binary assertions (a/b/c)
  with explicit exit-code/grep checks; Inno ≥6.3 install + `iscc //DAppVersion=…`;
  `upload-artifact` of the installer; the path-filter gate with the conservative
  fallback.
- Confirm the existing four jobs are byte-unchanged (git diff scoped to the added job).
- `.venv/bin/python -m pytest -m 'not live and not browser and not pixel and not
  requires_bwrap and not discord_hat' tests/ -x --timeout 60` — green (no regression;
  this leg adds no runtime code).
- Confirm no `the_one/` source edits (git diff).

## Implementation Guidance

1. **New job, not a modified one.** Add `windows-packaged-smoke` alongside `windows`
   in `test.yml`. Keep the existing `windows` curated-subset job intact.

2. **Path-filter (copy the `browser` job's pattern).** A `changes` step doing an inline
   `git diff --name-only "$BASE" HEAD | grep -qE '^(packaging/|pyproject\.toml$|the_one/platform/env\.py$|the_one/platform/interpreter\.py$|the_one/platform/shell\.py$|the_one/mcp/transports/stdio\.py$|the_one/diagnostics\.py$|the_one/main\.py$|the_one/interfaces/app\.py$|the_one/interfaces/web/app\.py$|the_one/config\.py$|the_one/__init__\.py$)'`,
   with the `pull_request` base = `github.event.pull_request.base.sha`, push base =
   `github.event.before`, and the missing/unreachable-base → run-everything fallback.
   Gate every subsequent step on `steps.changes.outputs.run == 'true'`. Needs
   `fetch-depth: 0` on checkout (like `browser`).

3. **Install + build.**
   ```bash
   pip install -e ".[gui,all-llms]"
   pip install pyinstaller
   pyinstaller --noconfirm packaging/windows/the-one.spec
   test -f dist/the-one/the-one.exe   # fail fast if the bundle name drifts
   ```

4. **Frozen doctor (proof a).**
   ```bash
   ./dist/the-one/the-one.exe doctor | tee doctor.out   # exit code is the doctor's
   grep -q "child spawn: OK" doctor.out
   grep -q "RESULT: PASS" doctor.out                    # also covers the interpreter gate
   ```
   Use `set -eo pipefail` at the top of the run block so `tee` can't mask the doctor's
   non-zero exit.

5. **Frozen serve + /api/info (proof b) — httpx poll, not curl.** Background the frozen
   serve, poll with the same library the product uses:
   ```bash
   ./dist/the-one/the-one.exe serve &
   python - <<'PY'
   import time, sys, httpx, the_one
   for _ in range(30):
       try:
           r = httpx.get("http://127.0.0.1:8484/api/info", timeout=2.0)
           if r.status_code == 200:
               assert r.json()["version"] == the_one.__version__, r.json()
               sys.exit(0)
       except Exception:
           pass
       time.sleep(1)
   sys.exit("frozen serve did not answer /api/info 200 within 30s")
   PY
   ```
   (httpx is a runtime dep — no `curl`/Git-Bash assumption, and it exercises the real
   polling path. Bump 30→60 if a cold PyInstaller unpack flakes the runner.)

6. **Single-instance (proof c).** With serve still up, assert the F4 probe (from
   source) sees the frozen instance as ours, then tear down:
   ```bash
   python -c "from the_one.interfaces.app import _select_port; p,ours=_select_port('127.0.0.1',8484); assert ours,(p,ours)"
   taskkill //F //IM the-one.exe || true   # Windows-native teardown; MSYS-escaped; best-effort
   ```
   This proves the **decision input**: the frozen instance advertises version 0.2.0 on
   `/api/info`, so a second `app` launch's `_select_port` returns `(port, True)` and
   starts no second server. It does not run the frozen binary's own `_select_port` —
   the rendered-window second-launch is F9 (DD5). `kill "$!"` on a native `.exe` under
   Git Bash is unreliable, so use `taskkill`.

7. **Inno build + artifact.**
   ```bash
   choco install innosetup --version=6.3.3 -y   # concrete published 6.3+ build (x64compatible token)
   VER=$(python -c "import the_one; print(the_one.__version__)")
   iscc //DAppVersion=$VER packaging/windows/the-one.iss
   test -f "packaging/windows/Output/the-one-setup-$VER.exe"
   ```
   (Verify `6.3.3` is published on community.chocolatey.org at build time; bump to the
   current published 6.3+ if not. The `//D` double-slash is the MSYS escape for a
   leading `/D` — do not "fix" it to `/D`.)
   Then `actions/upload-artifact@v4` with `path: packaging/windows/Output/*.exe`.
   **Git-Bash gotcha:** a bare `/DAppVersion` is mangled into a Windows path by MSYS;
   use `//DAppVersion` (double slash) **or** `MSYS2_ARG_CONV_EXCL="*"`. Note this in a
   comment so a future editor doesn't "fix" it back.

8. **Ordering.** Build one-dir → smoke (a/b/c) → Inno build + upload. If the smoke
   fails, the job fails before producing an installer (don't ship an unproven build).

9. **README note.** Add a short "CI packaged-smoke" subsection to
   `packaging/windows/README.md`: what the job proves (the DD2 spawn fix on the real
   frozen binary), and that a red `doctor` step is the flight's Divert signal.

## Edge Cases

- **windows-2022 Node/PATH** — the runner ships Node, so `doctor`'s `node --version`
  probe finds it; the smoke's pass criterion is the **child-spawn** line (`cmd /c
  echo`), which doesn't depend on Node being present. Don't make Node presence a hard
  gate.
- **pywinpty `.pyd`/`winpty.dll` missing from the bundle** — surfaces as a PyInstaller
  build error or a frozen import failure; both fail the job (the Divert trigger). The
  Leg-2 `.spec` comment already flags the `--add-binary` fallback.
- **Port 8484 already bound on the runner** — unlikely on a fresh runner; the poll
  loop's timeout fails the job clearly rather than hanging.
- **`iscc` exit on Inno <6.3** — the pinned `choco` version prevents the
  `x64compatible` token rejection; if choco's default drifts below 6.3, pin explicitly.
- **Git-Bash `/D` mangling** — covered by `//D` (guidance step 7).
- **Path-filter false-negative** — if a future change breaks the freeze but touches
  none of the filtered paths, the smoke won't run on that PR; the filter list includes
  every seam file + `packaging/**` + `pyproject.toml` (dep changes), which is the
  realistic blast radius. Document that adding a new seam file means adding it here.

## Files Affected

- `.github/workflows/test.yml` — new `windows-packaged-smoke` job.
- `packaging/windows/README.md` — CI packaged-smoke subsection.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All locally-verifiable criteria met (workflow authored + lint-clean); the
      observed-green-run dependency on the PR's CI is recorded
- [ ] Host-native unit suite green; existing CI jobs unchanged
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (this is the last autonomous leg — Flight 5's
      review + commit happen next, in Phase 2d; do NOT commit, do NOT touch flight.md)

## Citation Audit

All citations verified against current code at leg design time (2026-06-14) over the
post-Leg-3 tree: `.github/workflows/test.yml` (4 jobs; `browser` inline git-diff
path-filter pattern; `windows` job on windows-2022/bash), `the_one/diagnostics.py`
(`doctor` / `child spawn: OK`), `the_one/interfaces/web/app.py:1634` (`/api/info`),
`the_one/interfaces/app.py:_select_port` (single-instance probe, version match),
`the_one/__init__.py:3` (`__version__ = "0.2.0"`), `packaging/windows/the-one.spec`
+ `the-one.iss` (build inputs). No drift; all `OK`.
