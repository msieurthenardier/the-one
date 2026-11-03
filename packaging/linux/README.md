# packaging/linux - PyInstaller on Linux (candidate A)

**Flight 1 winner (Mission 32): the starting point for Flight 2 (Linux). Still a prototype, not wired into CI, publishes nothing.**
It freezes GleepGlorp AI with PyInstaller on Python 3.12 and wraps the one-dir bundle
as an AppImage and a `.deb`. The bundle does not carry the GTK/WebKit stack: it uses
the desktop's own WebKitGTK 4.1 through PyGObject.

## Build

```
packaging/linux/build.sh                       # version = __version__ in the_one/__init__.py
packaging/linux/build.sh --version 0.11.9.dev1 # a test build (the N+1 package of an upgrade test)
packaging/linux/build.sh --no-excludes         # the "before" build of the excludes measurement
```

`build.sh 0.11.8` (a positional version) still works and prints a deprecation warning;
`--version` together with a positional version is an error.

### Product metadata and rendering (DD6)

`packaging/product.toml` is the one source of names and display strings (also read by the
macOS and Windows recipes later). `packaging/render.py` (stdlib only) fills every `*.in`
template here: `@KEY@` with an uppercase key, so `noreply@invalid` is never touched, and a
key with no value fails the build. `render.py --repo . --json` prints the values, including
`version` (from `the_one/__init__.py`, or `--set version=X`), `deb_version` and `release_date`
(`SOURCE_DATE_EPOCH`, which `build.sh` sets from the last commit, so a rebuild renders the
same files). `build.sh` renders after staging into `$STAGE/rendered/` (mounted read-only into
the container); `build-inner.sh` takes names and paths from `rendered/build.env` (validated
against `KEY=safe-value` before it is sourced) and runs `desktop-file-validate` on every
`.desktop` it ships and `appstreamcli validate --no-net` on the metainfo; either failing fails
the build. Templates: `deb.desktop.in`, `appimage.desktop.in`, `AppRun.in`, `control.in`,
`metainfo.xml.in`, `build.env.in`. The AppStream id is `ai.gleepglorp.GleepGlorpAI` (keep it
stable once shipped), license MIT (`LICENSE`, and `license` in `pyproject.toml`).
`appimagetool` finds no metadata (it looks for a file named after the desktop id and validates
it with the network, which conflicts with AppStream's id-named file), so it prints a harmless
"metadata missing" warning; the file ships in the AppDir as `<id>.metainfo.xml`.

### AppImage self-integration (DD5)

`AppRun` with no argument or `app` first writes, best effort and only when the content
changed, `$XDG_DATA_HOME/applications/gleepglorp-ai-appimage.desktop` (an absolute
`XDG_DATA_HOME` only, else `~/.local/share`) and the icon under
`icons/hicolor/512x512/apps/`, from `usr/share/<package>/integration.desktop.in`, with the
AppImage's current path escaped per the Desktop Entry spec. A path with a control character is
skipped. Other arguments (`quit`, `doctor`, `version`, ...) pass through with no integration.
Uninstall: delete the AppImage file, then the two user-level files above.

The freeze and both wraps run inside one pinned container (`build.Dockerfile`, image
`m32/linux-build:f2`), the same locally and on the hosted runner. `build.sh` does the two
steps that need the git checkout on the host: `stage.py` (it runs `git rev-parse`; a git
worktree's `.git` file points outside the tree, so it cannot run in the container) and
`uv export`. It then runs `build-inner.sh` in the container as the invoking uid with
`packaging/` read-only, the staged copy read-only and `$M32_BUILD` read-write; no network, no
`--privileged`. `M32_FROM_HEAD=1` stages `git archive HEAD` instead of the working tree.

Output under `$M32_BUILD` (default `$HOME/the-one-m32-build/f2`, outside the repo):
`packages/GleepGlorp_AI-<ver>-x86_64.AppImage`, `packages/gleepglorp-ai_<debver>_amd64.deb`,
`linux-<ver>/dist/the-one/` (the bundle), `build-<ver>.log`. PEP 440 `0.11.9.dev1` is Debian
`0.11.9~dev1`.

### The build image

- Base `ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac`
  (`ubuntu:24.04`, re-read 2026-10-24): GLib 2.80, the host Flight 1's `excludes.txt` was
  validated on.
- `uv` 0.9.30 by digest (`sha256:538e0b39...`), CPython 3.12.12 under `/opt/uv-python`, the
  hash-pinned closure in `/opt/venv`, PyInstaller 6.22.3 and pyinstaller-hooks-contrib 2026.8.
- `appimagetool` and the type2 runtime are downloaded in the Dockerfile and checked against the
  SHA-256 values in "Pinned tools" below.
- PyGObject 3.56.3 and pycairo 1.29.0 compile from source (`libgirepository-2.0-dev`,
  `libcairo2-dev`, `gobject-introspection`, `gcc`). Build tools are never added to `uv.lock` or
  the root `pyproject.toml`.
- `libgirepository-2.0-0` is installed system-wide (as on the Flight 1 host). The Ayatana
  packages are only downloaded and extracted (`dpkg -x`) under `/opt/fallback-root`, never
  installed, so PyInstaller's gi hooks and pystray see the environment Flight 1 measured.

## AppImage library fallback (flight 2 DD1)

The bundle leaves the GTK/WebKit stack to the host, but a stock desktop may lack
`libgirepository-2.0` (Debian 13) or the Ayatana AppIndicator stack and its typelib (Debian 13;
Ubuntu 26.04 lacks only the typelib). The AppImage therefore carries a fallback set, in
`usr/lib/gleepglorp-ai-fallback/` next to (not inside) the PyInstaller bundle:

- `lib/`: six real files named by soname: `libgirepository-2.0.so.0`, `libayatana-appindicator3.so.1`,
  `libayatana-indicator3.so.7`, `libayatana-ido3-0.4.so.0`, `libdbusmenu-gtk3.so.4`,
  `libdbusmenu-glib.so.4`;
- `girepository-1.0/AyatanaAppIndicator3-0.1.typelib`.

`build-inner.sh` fails the build if any of the six needs a library outside glibc's own sonames,
`libffi.so.8`, the families in `excludes.txt` or the six themselves. The `.deb` has no fallback
directory (its dependencies pull the real packages).

`rthook_host_gtk.py` uses it host first, best effort, and never through `LD_LIBRARY_PATH`:

1. each soname is loaded by its bare name (the system loader); only when that fails is the
   AppImage copy loaded by absolute path (`RTLD_GLOBAL`, so the `_gi` extension and the typelib
   bind to it by soname). The girepository library and the Ayatana chain are separate; a chain
   stops at the first soname that loads from neither place (a bare host has no GTK).
2. the fallback typelib directory is appended to `GI_TYPELIB_PATH`, after the host directories,
   only when no host directory has an Ayatana or AppIndicator typelib. The hook then makes gi
   read the search path and drops the variable, so WebKit's helper processes inherit nothing
   under the AppImage mount.
3. PyInstaller's stock gi/gio/glib/gtk runtime hooks run after this hook and re-point
   `GI_TYPELIB_PATH`, `GIO_MODULE_DIR`, `XDG_DATA_DIRS` and `GTK_PATH` into the bundle, so
   `the-one.spec` drops those four.

Debug knobs (read by the hook in both packages, inert unless set): `THE_ONE_PKG_DEBUG=1` prints the
resulting environment and, per soname, whether it came from the host or the fallback;
`THE_ONE_PKG_FORCE_FALLBACK=1` (only with `THE_ONE_PKG_DEBUG=1`) loads all six fallback copies even when the
host has them; `THE_ONE_PKG_ABI_PROBE=1` creates a Gtk window with a WebKit view and an Ayatana
indicator, runs the main loop for four seconds, prints where the six libraries were mapped
from, and exits (run it with `LD_BIND_NOW=1`). The probe ships, inert, in both packages.

## Post-freeze audit

`audit.py` (stdlib only) runs inside `build-inner.sh` right after the freeze, before wrapping,
on the PyInstaller bundle directory only (never the fallback directory). The build fails, with
the offending paths printed, if any file's base name matches an `excludes.txt` pattern, any
`*.typelib` is present, or any ELF needs a `GLIBC_` version above 2.39 (`readelf -V`). It prints
the file count, the highest glibc found and PASS/FAIL. A `--no-excludes` build skips it. Checks
and the container gate suite live in `checks/` (see `checks/README.md`).

## Build environment outside the container (Flight 1 recipe, for reference)

```
uv venv --python 3.12 $M32_BUILD/venv-pyi
uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt > $M32_BUILD/requirements-closure.txt
uv pip install --python $M32_BUILD/venv-pyi/bin/python -r $M32_BUILD/requirements-closure.txt --no-deps
uv pip install --python $M32_BUILD/venv-pyi/bin/python pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.8
```

## Pinned tools

| tool | version | SHA-256 |
|---|---|---|
| PyInstaller | 6.22.3 | (PyPI) |
| pyinstaller-hooks-contrib | 2026.8 | (PyPI) |
| appimagetool | 1.9.1 (release asset; self-reports "continuous build 8c8c91f, 2025-12-04") | `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0` |
| type2-runtime (`--runtime-file`) | 20251108 | `2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d` |

Run under `--appimage-extract-and-run` (no FUSE). The Dockerfile downloads both and verifies
these checksums (`/opt/tools/` in the image).

## Files

- `the-one.spec`: collection contract borrowed from `packaging/windows/the-one.spec`;
  reads the staged copy from `$M32_STAGE`, never the repo root.
- `excludes.txt`: library families left out of the bundle (host GTK/GLib/WebKit stack).
- `rthook_host_gtk.py`: points gi at the host typelibs, keeps the bundle off
  `LD_LIBRARY_PATH` and the other loader variables for child processes (WebKit's helpers), and
  does the AppImage library fallback and the ABI probe.
- `build.sh`, `build-inner.sh`, `build.Dockerfile`: host staging, the container build, the image.
- `AppRun.in`, `deb.desktop.in`, `appimage.desktop.in`, `control.in`, `metainfo.xml.in`, `build.env.in`: templates (see above).
- `patches/`: staging-time diffs against `the_one/` if a gate needs them (none so far).

## Collection fix found by the gates (leg 2)

`the-one.spec` names `collect_submodules("gi.overrides")` in `hiddenimports`. PyInstaller's
gi hooks cannot query GI on the Ubuntu 24.04 build host, so without it the PyGObject override
modules (`GLib`, `Gtk`, ...) were not in the bundle, and pywebview's `GLib.idle_add(func, ...)`
hit the raw typelib signature (`TypeError: GLib.idle_add() takes exactly 3 arguments`): the
server started and `doctor` passed, but the window never opened. Rebuilt packages: see the
flight log's `linux-pyinstaller-gates` entry for the new checksums.
