# Leg: freeze-integration

**Status**: completed
**Flight**: [Windows Native App Hardening — Desktop Presence & Lifecycle](../flight.md)

## Objective

Make the PyInstaller freeze include pystray + Pillow (so the tray works in the installed
app), add a **non-GUI frozen import check** for the desktop shell to the packaged-smoke,
update user-facing docs for the new lifecycle, and reconcile the stale leg-number
reference in the spec docstring.

## Context

- Flight DD7: pystray + Pillow are new freeze inputs; the spec's per-package `collect_*`
  pattern will NOT auto-cover them. Explicit collection contract required.
- **Frozen proof is deferred:** this host is headless Linux; the `windows-2022`
  packaged-smoke (in `.github/workflows/windows-installer.yml`) runs only on a `v*` tag
  (day-to-day Windows builds run in the local Concourse pipeline on `main`). So this
  leg's freeze changes are **proven at the next tag / the Leg-6 operator HAT**, not on
  the F6 PR. This leg's autonomous acceptance is the *correctness* of the recipe + the
  smoke step + docs; mark the "frozen builds+launches green" criterion as HAT/tag-gated.
- The packaged-smoke already runs `the-one doctor`; extending the doctor with a
  desktop-shell import line gives a **headless** frozen check that exercises the
  pystray/Pillow collection without needing a GUI.

## Inputs

- `packaging/windows/the-one.spec` — the freeze contract (existing `collect_*` calls +
  `hiddenimports` list + `datas` for web static; a docstring at ~line 21 with a stale
  "Leg 4's CI packaged-smoke" reference).
- `.github/workflows/windows-installer.yml` — the tag-gated packaged-smoke (the `doctor`
  grep gate at the "Packaged-smoke (a) — frozen doctor" step).
- `the_one/diagnostics.py` — `run_doctor` (prints diagnostic lines + `RESULT: PASS`).
- Docs: `CLAUDE.md`, `README.md`, `agents.md` (whichever document the `the-one app`
  / desktop behavior).

## Outputs

- `packaging/windows/the-one.spec` — pystray + Pillow collection (per DD7); tray PNG in
  `datas` **only if not already covered** by the existing web-static collection (verify
  first); docstring leg-number reconciled.
- `the_one/diagnostics.py` — a desktop-shell import check line in `run_doctor` (imports
  `the_one.interfaces.desktop.tray` + `pystray`/`PIL`, reports OK/skip).
- `.github/workflows/windows-installer.yml` — the packaged-smoke asserts the new doctor
  desktop line (grep), so a freeze that drops pystray/Pillow fails the smoke.
- Docs updated for the tray/background-run lifecycle.
- `tests/` — a unit test for the new doctor desktop-shell check (host-native, mocked).

## Acceptance Criteria

- [ ] `packaging/windows/the-one.spec` collects pystray + Pillow:
      **`collect_submodules("pystray", on_error="warn")`** (the `on_error="warn"` is
      mandatory — without it the platform-only pystray backends abort the freeze), and
      Pillow via the hooks-contrib PIL hook (or explicit `collect_submodules("PIL")` +
      `_imaging` if a plugin is missed). (Verified by inspection — entries present,
      `on_error="warn"` set, the leg log states which PIL approach was used.)
- [ ] The tray icon PNG is bundled: **either** confirmed already covered by the existing
      web-static `datas` collection (cite the spec line that collects
      `interfaces/web/static`), **or** an explicit `datas` entry is added. (Verified by
      inspection; state which.)
- [ ] `the-one doctor` prints a **desktop-shell** line that imports
      `the_one.interfaces.desktop.tray` (which lazily imports pystray + PIL) and reports
      OK, or `skipped` when `[gui]` is absent. **Gate only when frozen** — `is_frozen()`
      → a failed import is `RESULT: FAIL`; non-frozen → informational, `skipped` keeps
      `RESULT: PASS`. Doctor never crashes. (Host-native here: line shows, `RESULT: PASS`.)
- [ ] `.github/workflows/windows-installer.yml`'s packaged-smoke greps the new doctor
      desktop line (so a freeze missing pystray/Pillow fails). (Verified by inspection.)
- [ ] Docs (`CLAUDE.md`/`README.md`/`agents.md`) describe: close-to-tray + background
      run, **Quit from the tray menu is the real exit**, single-instance focus
      (`/api/window/focus`), and `window-state.json` under the data dir. (Verified by
      inspection.)
- [ ] The stale leg-number references are corrected (reworded WITHOUT a leg-number):
      `the-one.spec:20-21`, `the_one/diagnostics.py:17`, and the inline `the-one.spec:85`
      "Leg-4 build note" comment.
- [ ] **(HAT/tag-gated, NOT provable on this PR):** the frozen `windows-2022` build
      includes pystray/Pillow and the frozen `the-one doctor` desktop line passes. Logged
      as deferred to the next tag build / the Leg-6 operator HAT.
- [ ] Host-native suite still green (the new doctor test + Leg 1-4 suites).

## Verification Steps

- `python -m pytest tests/ -k "doctor or desktop or window or tray or launcher" -x --timeout=30 -q`
  (host-native — NOT docker) — green.
- `python -m the_one doctor` (or `the-one doctor`) — prints the desktop-shell line and
  `RESULT: PASS` on this host (the `[gui]` stack may be absent here → the line should
  read a clean "skipped: gui extra not installed", NOT a traceback).
- `python -c "import ast; ast.parse(open('packaging/windows/the-one.spec').read()); print('spec parses')"`
  — the spec is valid Python.
- `grep -n "pystray\|PIL\|collect_submodules" packaging/windows/the-one.spec` — entries present.
- `git diff --stat` — scoped to `packaging/`, `.github/workflows/`, `the_one/diagnostics.py`, docs, `tests/`.

## Implementation Guidance

1. **Spec collection (DD7).** Read `packaging/windows/the-one.spec`. Add
   `collect_submodules("pystray", on_error="warn")` — **`on_error="warn"` is REQUIRED**:
   pystray's `_xorg`/`_gtk`/`_appindicator`/`_darwin` backends import Linux/macOS-only
   deps (`Xlib`/`gi`/`AppKit`) at module scope, so the collect walk would otherwise
   abort the Windows freeze — the same failure mode the spec already handles for
   `mcp.cli` at `the-one.spec:78`. (With `collect_submodules`, a standalone
   `pystray._win32` hiddenimport is **redundant but harmless** — add for clarity if you
   like; `pystray._util.win32` is also covered by the walk.) For **Pillow**: prefer the
   bundled `pyinstaller-hooks-contrib` PIL hook (it handles `_imaging` + plugins) — only
   add an explicit `collect_submodules("PIL")` / `collect_dynamic_libs("PIL")` if a
   frozen import would otherwise miss a plugin. **State in the leg log which PIL approach
   was used.** Merge into the existing `hiddenimports`/`datas`/`binaries` lists following
   the file's established pattern.

2. **Tray PNG in the freeze.** Check whether the existing `datas` already collects the
   whole `the_one/interfaces/web/static` tree (F5 bundled web static). If
   `static/brand/gleepglorp_icon.png` is already inside that collection, **do not add a
   duplicate** — note it in the leg log. If not, add a `datas` entry for the brand PNG.

3. **Doctor desktop line.** In `the_one/diagnostics.py`'s `run_doctor`, add a check that
   does `import the_one.interfaces.desktop.tray` inside a try/except: on success import
   `pystray` + `PIL` (the tray's real deps) and print `desktop shell: OK`; on
   `ImportError` print `desktop shell: skipped (gui extra not installed)`. **Gate only
   when frozen:** when `is_frozen()` (the freeze MUST include `[gui]`), a failed import
   is a **gate** → `RESULT: FAIL` (so a broken freeze is caught even beyond the smoke
   grep); when NOT frozen (a dev host may legitimately lack `[gui]`), it is informational
   — `skipped` does not fail, `RESULT: PASS` still prints. Either way `doctor` must not
   crash. Match the existing gate emit format (`"  {name}: {status} — {detail}"`,
   `diagnostics.py:163`).

4. **Smoke grep.** In `windows-installer.yml`'s "frozen doctor" smoke step, add a
   `grep -q "desktop shell: OK" doctor.out` (the frozen build HAS the `[gui]` stack, so
   it must be OK there, not skipped). This makes a freeze that drops pystray/Pillow fail.

5. **Docs.** Primary update in **`agents.md` (the Desktop launcher section, ~:24-56 —
   the canonical deep reference)**: close-to-tray + background run, Quit-from-tray is the
   real exit, single-instance focus (`/api/window/focus`), and `window-state.json`. Add a
   **brief** background-run + tray-quit mention to **`README.md` (Desktop window, ~:60-88)**
   and **`CLAUDE.md` (Desktop launcher, ~:79-81)**.

6. **Docstring fix.** Correct the stale leg-number references — **reword without a
   leg-number** (they rot every flight): `the-one.spec:20-21` ("Leg 4's CI
   packaged-smoke…"), `the_one/diagnostics.py:17` ("Leg 4's CI packaged-smoke reads
   exactly this exit code…"), and the inline `the-one.spec:85` "Leg-4 build note" comment.

## Edge Cases

- **PIL hook double-collection:** if PyInstaller's built-in PIL hook already collects
  PIL, an explicit `collect_submodules("PIL")` is redundant but harmless — prefer the
  hook; only add explicit collection if a frozen import would otherwise miss a plugin.
- **Doctor on headless host:** the `[gui]` stack (pywebview/pystray) may be absent here;
  the desktop line must degrade to "skipped", never traceback (criterion 3).
- **No new runtime state / no DB / no cache** — packaging + diagnostics only.

## Files Affected

- `packaging/windows/the-one.spec` — pystray/Pillow collection + docstring fix.
- `the_one/diagnostics.py` — desktop-shell doctor line.
- `.github/workflows/windows-installer.yml` — smoke grep for the desktop line.
- `CLAUDE.md` / `README.md` / `agents.md` — lifecycle docs.
- `tests/` — doctor desktop-line unit test.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified (frozen one is HAT/tag-gated — note in log)
- [ ] Tests passing (host-native)
- [ ] Update flight-log.md with the leg progress entry
- [ ] Set this leg's status to `landed` (completion/commit deferred to flight-end review)

## Citation Audit

3 citations to verify at implementation time (the implementer reads these files
directly): `packaging/windows/the-one.spec` (collection pattern + docstring ~:21) —
confirm against current; `.github/workflows/windows-installer.yml` (the frozen-doctor
smoke step) — confirm the grep anchor; `the_one/diagnostics.py:run_doctor` — confirm the
print/`RESULT: PASS` structure. All are stable F5 artifacts; no drift expected, but the
implementer confirms exact line anchors.
