# Squawk 0255: guard the Linux build against PyInstaller's stock gi hooks and the PYZ module probe

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-24
**Completed**: —

## Report
The Linux recipe relies on two assumptions that only a full frozen build exercises, and nothing fails loudly if either changes.

1. **The stock hooks.** `packaging/linux/the-one.spec` drops PyInstaller's stock runtime hooks `pyi_rth_gi`, `pyi_rth_gio`, `pyi_rth_glib` and `pyi_rth_gtk`, because they re-point `GI_TYPELIB_PATH`/`GIO_MODULE_DIR`/`XDG_DATA_DIRS`/`GTK_PATH` into the bundle after `rthook_host_gtk.py` runs. That leaked into WebKit's helper processes, latent since Flight 1 and found in Flight 2 leg 1. A PyInstaller bump that renames or adds such a hook would bring the leak back silently.
2. **The PYZ branch.** `the_one/diagnostics.py::bundle_has_modules`' PYZ branch (`pkgutil.iter_modules` over PyInstaller's virtual paths) has no assertion. It fails safe, but a wrong "missing" would report no tray.

## Evidence
- `packaging/linux/the-one.spec:184` — `s for s in a.scripts if s[0] not in {"pyi_rth_gi", "pyi_rth_gio", "pyi_rth_glib", "pyi_rth_gtk"}`.
- `the_one/diagnostics.py::bundle_has_modules`; `tests/test_doctor.py` covers the non-frozen path only.
- The Flight 2 debrief (Technical; recommendation 4); the leg 1 log, "Two defects found and fixed here".

## Corrective Action
*(written at completion)*

## Verification
- The audit (`packaging/linux/audit.py`, or a build step) fails when the pinned PyInstaller's gi-related runtime hooks differ from the set the spec drops. It fails a deliberately altered set, with a unit test.
- The packaging checks assert that a frozen build's `bundle_has_modules` finds `pystray._appindicator` (and `pystray._xorg`) inside the PYZ.
- The existing checks (`checks/gates.sh` G3, which reads the helpers' `/proc/<pid>/environ`) still pass on a rebuilt package.

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** at Mission 32 Flight 2's debrief, on the operator's decision. Do it before any PyInstaller version bump.
