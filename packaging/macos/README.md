# packaging/macos - PyInstaller on macOS (candidate A)

**Flight 1 winner (Mission 32): the starting point for Flight 3 (macOS). Still a prototype, not wired into CI; ad-hoc signed; publishes nothing.**
It freezes GleepGlorp AI with PyInstaller on Python 3.11 into `GleepGlorp AI.app` and a `.dmg`.
It is built and checked by the dispatch-only workflow `.github/workflows/macos-packages.yml`
on a hosted `macos-15` (Apple Silicon) runner; it has never run on the operator's machine.

## Files

- `the-one.spec`: the collection contract of `../linux/the-one.spec` (itself from
  `../windows/the-one.spec`), minus the Linux parts, plus a `BUNDLE`. Reads the staged copy from
  `$M32_STAGE` (never the repo root). On macOS there is no gi or GTK: pywebview uses its Cocoa
  backend (`webview.platforms.cocoa`, the locked `pyobjc-*` packages) and pystray uses
  `pystray._darwin`. `excludes.txt` and `rthook_host_gtk.py` are Linux-only and are not used.
- `frozen_entry_mac.py`: the entry. `Contents/MacOS/the-one doctor|serve|version` still runs the CLI;
  a Finder/Dock launch passes no arguments (or only `-psn_*`), and the entry then appends `app`, so a
  double-click opens the window instead of the terminal `chat`. Recipe upkeep, not an app patch (DD4).
  It calls `ensure_stdio_streams()` first, as the Windows GUI entry does, because the windowed
  bootloader (`console=False`) can leave `sys.stdout` as None.
- `make-icns.py`: writes the `.icns` from the staged 512 px icon with Pillow.
- `build.sh <version>`: stage, venv, hash-pinned closure install (`--require-hashes --no-deps`),
  pinned PyInstaller, freeze, `codesign --force --deep -s -`, `hdiutil create` (one retry, 300 s
  limit), then `checks.sh`.

## Pinned tools

| tool | version |
|---|---|
| PyInstaller | 6.22.3 (same as Linux) |
| pyinstaller-hooks-contrib | 2026.8 (same as Linux) |
| Python | 3.11 (`actions/setup-python`) |
| uv (closure export) | 0.10.0 |

## Notes

- `Info.plist`: `CFBundleName`/`CFBundleDisplayName` "GleepGlorp AI", `CFBundleIdentifier`
  `ai.gleepglorp.the-one`, the staged version, `NSHighResolutionCapable`, `LSMinimumSystemVersion` 11.0.
- The executable is `Contents/MacOS/the-one` (the `.app` folder carries the display name).
- Bare `the-one` typed in a shell now opens the window (the entry cannot tell a shell from Finder),
  unlike Linux's `.deb`, where bare `the-one` is the terminal chat.
- Linux rehearsal: `py_compile`, and the spec runs through Analysis against a staged copy on Linux
  (its `BUNDLE` is a no-op there). The macOS-only parts are first exercised by the hosted run.

## Probe mode

`.github/workflows/macos-packages.yml` with `-f mode=probe` builds this app with `M32_SKIP_CHECKS=1` (skips
`checks.sh`, so the default data dir and credential do not exist before the first-launch premise), freezes the
minimal probe app and runs `probe/probe.sh`. See `probe/README.md`.
