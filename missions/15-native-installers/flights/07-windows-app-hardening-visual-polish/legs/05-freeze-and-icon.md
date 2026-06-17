# Leg: freeze-and-icon

**Status**: completed
**Flight**: [Windows Native App Hardening — Visual Polish](../flight.md)

## Objective

Give the frozen Windows app a crisp brand icon: regenerate `the-one.ico` to include the
large-icon sizes (256/128/64) it's missing, and bake it into the windowed `exe_gui` so the
window, taskbar, and Alt-Tab icon are the brand mark rather than the generic PyInstaller icon.

## Context

- **DD5** (flight): set `icon='installer-assets/the-one.ico'` on the **`exe_gui`** `EXE(...)`
  in `the-one.spec` (currently no `icon=` → generic PyInstaller icon). On Windows the window +
  taskbar icon derive from the exe. **Regenerate the `.ico` first** — it currently holds only
  16/32/48 (confirmed via Pillow), so the large-icon / Alt-Tab / high-DPI path upscales 48→256
  and looks soft. Regenerate from `static/brand/icon-512.png` to include 256 (and 64/128).
- This leg's deterministic, host-runnable part is the **icon regen + spec edit**. The
  **packaged-smoke** (build the frozen artifact on `windows-2022`, launch it, confirm the brand
  icon + that the chrome/splash web assets are in the bundle) is **Windows/Concourse-gated** and
  runs in the operator-driven phase (with Leg 7). The **splash asset** half of "confirm
  chrome/splash assets in the bundle" depends on the splash leg (Leg 4), which is spike-pending.

## Inputs

- `packaging/windows/installer-assets/the-one.ico` — currently sizes **(16,16),(32,32),(48,48)**
  only (verified with Pillow 12.2.0).
- `the_one/interfaces/web/static/brand/icon-512.png` — the 512px master to regenerate from.
- `packaging/windows/the-one.spec` — the one-dir spec. `exe_gui` is the windowed EXE
  (`the-one-app.exe`, `console=False`, the Start-menu shortcut target) at lines ~224–240; it has
  **no `icon=`** today. The spec resolves `icon=` relative to `SPECPATH` (`packaging/windows/`),
  so `icon='installer-assets/the-one.ico'` is the correct relative path.
- The web static tree (incl. `static/brand/**` and the Leg-2 chrome JS/CSS) is already collected
  into the bundle via `collect_data_files("the_one", includes=["interfaces/web/static/**/*"])`
  (spec lines ~111–113) — so the chrome assets ride along already; the splash asset (Leg 4)
  must too, once the splash lands.

## Outputs

- `packaging/windows/installer-assets/the-one.ico` regenerated to include **256, 128, 64** (and
  keep 48/32/16) from the `icon-512.png` master.
- `the-one.spec` `exe_gui` carries `icon='installer-assets/the-one.ico'`.
- A small, reproducible regen step (a committed script or a documented one-liner) so the `.ico`
  can be re-derived from the master, not a hand-edited binary.

## Acceptance Criteria

- [ ] `the-one.ico` contains sizes **256, 128, 64, 48, 32, 16** (verifiable with Pillow:
      `Image.open(ico); ico.info['sizes']` includes `(256,256)`), regenerated from
      `static/brand/icon-512.png` (downscales only — no upscaling).
- [ ] `the-one.spec`'s **`exe_gui`** `EXE(...)` sets `icon='installer-assets/the-one.ico'`
      (path relative to `SPECPATH`); `exe_cli` is left as-is (DD5 targets the windowed exe).
- [ ] The spec still **statically validates** on this Linux host:
      `.venv/bin/python -m py_compile packaging/windows/the-one.spec` succeeds (the spec can't
      be *frozen* off-Windows — the native-dep collect_* calls need Windows — but it must parse).
- [ ] The regen is **reproducible**: a committed helper (e.g.
      `packaging/windows/regenerate_icon.py`) or a documented command produces the same `.ico`
      from the master, so the asset isn't an opaque hand-edit.
- [ ] No regression: the existing host-native test suite is unaffected (this leg touches only a
      binary asset + the spec; run the desktop suites as a smoke).

## Verification Steps

- Pillow check: `.venv/bin/python -c "from PIL import Image; im=Image.open('packaging/windows/installer-assets/the-one.ico'); print(sorted(im.info['sizes']))"` → includes `(256, 256)`.
- `.venv/bin/python -m py_compile packaging/windows/the-one.spec` → exits 0.
- `grep -n "icon=" packaging/windows/the-one.spec` → shows `icon='installer-assets/the-one.ico'`
  inside the `exe_gui` block (and only there).
- Desktop suites smoke: `.venv/bin/python -m pytest tests/test_desktop_shell.py tests/test_desktop_chrome.py -q --timeout=30`.
- **Windows/Concourse-gated (operator phase, with Leg 7):** the `windows-2022` packaged-smoke
  builds the frozen artifact, launches `the-one-app.exe`, and confirms the brand icon renders on
  the window/taskbar and the chrome (and, once landed, splash) web assets are present in
  `dist/the-one/`. Recorded in the flight log / Leg 7 HAT.

## Implementation Guidance

1. **Regen script** — add `packaging/windows/regenerate_icon.py` (or extend an existing
   packaging helper) that opens `the_one/interfaces/web/static/brand/icon-512.png`, and writes
   `installer-assets/the-one.ico` with `sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)]`
   via Pillow (`img.save(out, format="ICO", sizes=[...])`). Pillow downsamples each size from the
   512 master with a high-quality filter (LANCZOS). Run it to produce the new `.ico`.
   - If the master has alpha/non-square issues, handle them (convert to RGBA; the brand icon is
     already square 512×512). Keep it simple and deterministic.
2. **Spec edit** — add `icon='installer-assets/the-one.ico',` to the `exe_gui` `EXE(...)` block
   only. Leave `exe_cli` unchanged (per DD5; the console exe's icon is immaterial to the
   windowed UX). Add a one-line comment referencing DD5.
3. **Validate** — Pillow size check + `py_compile` the spec + the desktop-suite smoke.
4. **Do NOT** attempt a PyInstaller freeze on this Linux host — the native-dep collect_* calls
   require Windows; the packaged-smoke is the Windows-runner's job. Note this in the flight log.

## Edge Cases

- **Inno installer icon** — RESOLVED at design review: `the-one.iss` already points **all four**
  icon references at `installer-assets\the-one.ico` (`SetupIconFile`, `UninstallDisplayIcon={app}\the-one.ico`,
  and both shortcut `IconFilename`s; the `.ico` is also copied to `{app}` by `[Files]`). So the
  regen improves the installer icon **automatically — no re-pointing needed**. BUT the `.iss`
  carries a now-stale comment (~lines 41–43: "The exe carries no embedded icon resource (the
  Leg-2 .spec omits EXE(icon=)), so point at the installed .ico") — after this leg sets
  `icon=` on `exe_gui`, that statement is wrong for the windowed exe. **Update that comment**
  to: the windowed exe now embeds the icon; `UninstallDisplayIcon` still uses the separately
  installed `{app}\the-one.ico` for Add/Remove-Programs registration (which is correct).
- **`.ico` is a committed binary** — it's tracked in git (not a gitignored snapshot artifact);
  regenerating + committing it is expected. The regen script makes the change auditable.
- **UPX on the exe** — `exe_gui` has `upx=True`; baking an icon into an upx-compressed exe is
  standard (PyInstaller embeds the icon before/independent of upx). No action; flag for the
  packaged-smoke if the icon doesn't appear.

## Files Affected

- `packaging/windows/installer-assets/the-one.ico` — regenerated (adds 256/128/64).
- `packaging/windows/the-one.spec` — `exe_gui` gains `icon='installer-assets/the-one.ico'`.
- `packaging/windows/regenerate_icon.py` (new) — reproducible regen helper (path-relative to
  `__file__` / runnable from repo root).
- `packaging/windows/the-one.iss` — update the stale "exe carries no embedded icon resource"
  comment (no icon-reference re-pointing needed; all four already use `the-one.ico`).

---

## Post-Completion Checklist

**Per this flight's batched model — set status to `landed` (NOT `completed`); do NOT commit or
signal `[COMPLETE:leg]`. The packaged-smoke + splash-asset-bundling confirmation are
Windows-gated and tracked for the operator phase — note them in the flight-log entry.**

- [x] `.ico` regenerated with 256/128/64; Pillow check passes
- [x] `exe_gui` icon set; spec `py_compile`s
- [x] Windows-gated items (packaged-smoke icon render + asset-in-bundle) listed for the operator phase
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`; check off this leg in flight.md (noting the Windows-gated remainder)
