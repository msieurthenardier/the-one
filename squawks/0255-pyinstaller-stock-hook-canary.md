# Squawk 0255: guard the Linux build against PyInstaller's stock gi hooks and the PYZ module probe

**Status**: deferred
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
PARTIAL. PyInstaller is not installed in the repo venv and the frozen build needs the container, so neither original verification bullet can be met here. What a unit test can see is pinned instead, in new `tests/test_packaging_linux_hook_pin.py` (static, reads the files like `test_packaging_winpty_spec.py`): the spec drops exactly the four reviewed hooks, the drop sits under `if not _NO_EXCLUDES:`, and `build.Dockerfile` and `README.md` both pin the reviewed PyInstaller (`REVIEWED_PYINSTALLER = "6.22.3"`), so a version bump fails the guard with a message telling the reviewer to re-read `PyInstaller/hooks/rthooks/` for gi-related `pyi_rth_*` hooks first. Falsified by edit (restored by edit, `git diff` empty for `packaging/linux`): a hook removed from the spec set, the Dockerfile pin changed, and the `if` replaced by `if True` each FAIL the matching test.

NOT done, needs the pinned PyInstaller or a frozen build (candidate for the Flight Director to decide whether to keep open as a follow-up): (1) an audit or build step that reads the installed release's `rthooks` directory and fails when its gi-related set differs from the spec's; (2) the frozen-build assertion that `bundle_has_modules` finds `pystray._appindicator` and `pystray._xorg` in the PYZ; (3) `checks/gates.sh` G3 on a rebuilt package.

## Verification
Done: `tests/test_packaging_linux_hook_pin.py` 3 passed, plus `tests/test_packaging_audit.py` and `tests/test_doctor.py` (109 passed together); ruff clean. Not verified: the three NOT-done items above. Original criteria:
- The audit (`packaging/linux/audit.py`, or a build step) fails when the pinned PyInstaller's gi-related runtime hooks differ from the set the spec drops. It fails a deliberately altered set, with a unit test.
- The packaging checks assert that a frozen build's `bundle_has_modules` finds `pystray._appindicator` (and `pystray._xorg`) inside the PYZ.
- The existing checks (`checks/gates.sh` G3, which reads the helpers' `/proc/<pid>/environ`) still pass on a rebuilt package.

## Sign-Off
Not signed off as completed: the squawk is deferred (see Disposition). The static guard was reviewed as described below.

The static guard `tests/test_packaging_linux_hook_pin.py` was reviewed and confirmed in the 2026-11-14 turnaround: an independent Reviewer (Sonnet tier) confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues. Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`. The squawk stays open for the three items above, so it is not signed off as completed.

## Disposition
- **Logged** at Mission 32 Flight 2's debrief, on the operator's decision. Do it before any PyInstaller version bump.
- **Deferred** (2026-11-14 turnaround): partly done. The static guard (`tests/test_packaging_linux_hook_pin.py`) landed. Still open: the build-time comparison of the installed PyInstaller release's gi hooks with the spec's set, the frozen-build check that `pystray._appindicator` and `pystray._xorg` are in the PYZ, and `checks/gates.sh` G3 on a rebuilt package. **Revisit trigger:** the next Linux package build or PyInstaller bump.
