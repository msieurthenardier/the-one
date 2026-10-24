# packaging/linux - PyInstaller on Linux (candidate A)

**Spike prototype, Mission 32 Flight 1. Not wired into CI, publishes nothing.**
It freezes GleepGlorp AI with PyInstaller on Python 3.11 and wraps the one-dir bundle
as an AppImage and a `.deb`. The bundle does not carry the GTK/WebKit stack: it uses
the desktop's own WebKitGTK 4.1 through PyGObject.

## Build

```
packaging/linux/build.sh 0.11.8            # or 0.11.9.dev1; add --no-excludes for the AC4 "before" build
```

Output under `$M32_BUILD` (default `$HOME/the-one-m32-build`, outside the repo):
`packages/GleepGlorp_AI-<ver>-x86_64.AppImage`, `packages/gleepglorp-ai_<debver>_amd64.deb`,
`linux-<ver>/dist/the-one/` (the bundle). PEP 440 `0.11.9.dev1` is Debian `0.11.9~dev1`.

## Build environment (once)

```
uv venv --python 3.11 $M32_BUILD/venv-pyi
uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt > $M32_BUILD/requirements-closure.txt
uv pip install --python $M32_BUILD/venv-pyi/bin/python -r $M32_BUILD/requirements-closure.txt --no-deps
uv pip install --python $M32_BUILD/venv-pyi/bin/python pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.8
```

PyGObject 3.56.3 and pycairo 1.29.0 compile from source: the host needs
`libgirepository-2.0-dev`, `libcairo2-dev`, `gobject-introspection` and `gcc`.
Build tools are never added to `uv.lock` or the root `pyproject.toml`.

## Pinned tools

| tool | version | SHA-256 |
|---|---|---|
| PyInstaller | 6.22.3 | (PyPI) |
| pyinstaller-hooks-contrib | 2026.8 | (PyPI) |
| appimagetool | 1.9.1 (release asset; self-reports "continuous build 8c8c91f, 2025-12-04") | `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0` |
| type2-runtime (`--runtime-file`) | 20251108 | `2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d` |

Run under `--appimage-extract-and-run` (no FUSE). Tools live in
`$M32_BUILD/tools/<name>-<version>/`.

## Files

- `the-one.spec`: collection contract borrowed from `packaging/windows/the-one.spec`;
  reads the staged copy from `$M32_STAGE`, never the repo root.
- `excludes.txt`: library families left out of the bundle (host GTK/GLib/WebKit stack).
- `rthook_host_gtk.py`: points gi at the host typelibs and keeps the bundle off
  `LD_LIBRARY_PATH` for child processes (WebKit's helpers).
- `AppRun`, `gleepglorp-ai.desktop.in`, `control.in`: wrapper templates.
- `patches/`: staging-time diffs against `the_one/` if a gate needs them (none so far).

## Collection fix found by the gates (leg 2)

`the-one.spec` names `collect_submodules("gi.overrides")` in `hiddenimports`. PyInstaller's
gi hooks cannot query GI on the Ubuntu 24.04 build host, so without it the PyGObject override
modules (`GLib`, `Gtk`, ...) were not in the bundle, and pywebview's `GLib.idle_add(func, ...)`
hit the raw typelib signature (`TypeError: GLib.idle_add() takes exactly 3 arguments`): the
server started and `doctor` passed, but the window never opened. Rebuilt packages: see the
flight log's `linux-pyinstaller-gates` entry for the new checksums.
