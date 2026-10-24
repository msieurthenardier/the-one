# Leg: linux-pyinstaller-build

**Status**: completed
**Flight**: [Choose the packaging toolchain](../flight.md)

## Objective
Build the candidate-neutral spike harness (staging step, container images) and freeze GleepGlorp AI for Linux with PyInstaller (candidate A). The output is an AppImage and a `.deb` at two versions, with the host GTK/WebKit stack excluded from the bundle, ready for leg 2 (`linux-pyinstaller-gates`) to measure.

## Context
- **Flight design decisions this leg implements:**
  - DD1 (A's Linux formats);
  - DD3 (shared staging; the pinned dependency closure; packaging stays outside `the_one/` and the root `pyproject.toml`);
  - DD4 (no commit under `the_one/`; an app-side patch, if needed, is a diff under `packaging/linux/patches/` that the staging step applies to the copy only);
  - the build half of DD5: the pinned interpreter and the container baselines.

  Read the flight's DD1-DD5 before starting.
- **This leg is the first half of a split** (Flight Director, after the leg design review): build here, gates in leg 2. Leg 3 (`linux-briefcase`) reuses `packaging/spike/` unchanged, so keep the harness candidate-neutral, with no PyInstaller assumption in the staging step or the images.
- **Location (a Flight Director call, stronger than DD3's "gitignored"):** the staging copies, build venvs, bundles and packages live under `$M32_BUILD` (default `$HOME/the-one-m32-build/`). Logs and screenshots live under `$M32_EVIDENCE` (default `$HOME/the-one-m32-evidence/`). Both are outside the repo and under `$HOME` (never `/tmp`), so `.gitignore` is not changed.
- **Package naming (a Flight Director call):**
  - the Debian package is `gleepglorp-ai`;
  - the bundle lives in `/opt/gleepglorp-ai/`;
  - the `.desktop` file is `gleepglorp-ai.desktop` (`Name=GleepGlorp AI`);
  - the command stays `the-one`, installed as `/usr/bin/the-one`, a symlink;
  - the AppImage file is `GleepGlorp_AI-<version>-x86_64.AppImage`;
  - the icon is `the_one/interfaces/web/static/brand/icon-512.png`, installed at `hicolor/512x512/apps/gleepglorp-ai.png`.
- **Versions:**
  - N = `0.11.8`; N+1 = `0.11.9.dev1`, which is Debian version `0.11.9~dev1` (it sorts above `0.11.8`);
  - `the-one version` prints `GleepGlorp AI v<version>`.
- **Dev host facts (verified 2026-10-23):**
  - Ubuntu 24.04.2 under WSL2 (glibc 2.39, at or below both targets), with no `sudo`, so nothing can be `apt install`ed on the host.
  - Build headers are present: `pkg-config` reports girepository-2.0 2.80.0, cairo 1.18.0 and gobject-introspection-1.0 1.80.1; `gcc` is installed.
  - uv-managed CPython 3.11.14 is available, and ships its headers.
  - Docker Desktop 29.8.2; 795 GB free.
- **The Windows recipe to borrow from** (`packaging/windows/the-one.spec`): reuse its collection contract:
  - uvicorn `collect_all`;
  - `mcp` submodules, minus `mcp.cli` and `mcp.server.fastmcp`;
  - `mcp_types`, `httpx2`, `httpcore2`, `truststore` and `opentelemetry`, plus httpx2/httpcore2 metadata;
  - pystray with `on_error="warn"`;
  - the static, seed, embedding and tzdata data;
  - `excludes=["hf_xet"]`.

  Drop the Windows-only parts: `winpty`, `pystray._win32`, and the console/windowed split. Linux has one executable serving the CLI and `app`, so a single `Analysis` is enough. **Unlike the Windows spec, the Linux spec must not put the repo root on `sys.path`, or import `the_one` from it.** That would bundle unpatched code and the repo's version instead of the staged copy. `packaging/windows/frozen_entry.py` imports `the_one.main`, so it can be reused as the entry script by path (its `freeze_support()` is harmless on Linux).
- **The gi hazard (flight DD2 gate 3), to handle here:**
  - PyInstaller's gi hooks bundle requested typelibs and their shared-library closure, and its gi runtime hook points `GI_TYPELIB_PATH` into the bundle.
  - The bootloader sets `LD_LIBRARY_PATH` to the bundle directory, which WebKit's helper processes inherit.
  - So A's recipe must exclude the host GTK/GLib/GObject/girepository/WebKit/JavaScriptCore stack and its dependencies, point gi at the host typelib directory, and keep `LD_LIBRARY_PATH` from offering bundled duplicates to `WebKitWebProcess`. Do all of it in one runtime hook plus the exclude list.

  Leg 2 measures the result. This leg proves the bundle's contents.

## Inputs
- The branch `flight/01-choose-packaging-toolchain` in `/home/cprch/projects/the-one-worktrees/m32-installers`. Never touch `/home/cprch/projects/the-one` (Mission 31 is active there).
- `packaging/windows/the-one.spec` and `frozen_entry.py` (reference; unchanged).
- The closure: `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt` (the same arguments as `scripts/windows_test_copy.py::CLOSURE_UV_EXPORT_ARGS`).
- `ubuntu:26.04` and `debian:13` images.

## Outputs
- `packaging/spike/` (candidate-neutral):
  - `stage.py`;
  - `images/ubuntu-26.04.Dockerfile` and `images/debian-13.Dockerfile`, with two targets each: `baseline` (a stock desktop) and `bare` (the distro image plus `python3` only);
  - `README.md`, which says this is spike tooling, not product.
- `packaging/linux/`:
  - `the-one.spec`;
  - `rthook_host_gtk.py` (the single runtime hook);
  - `excludes.txt` (the exclude list, by library family, commented);
  - `build.sh` (venv, freeze, both wrappers, one version per call);
  - `AppRun`, the `.desktop` template and the `DEBIAN/control` template;
  - `README.md` (spike prototype, Mission 32 Flight 1, not wired into CI; pinned tool versions and checksums);
  - `patches/`, only if needed.
- `$M32_BUILD/`: four packages (AppImage and `.deb`, at N and N+1) and the bundle trees. Not committed.
- The flight log: a `### linux-pyinstaller-build` entry.

## Acceptance Criteria
- [ ] **AC1 — Staging never touches the repo.**
  - `packaging/spike/stage.py --version 0.11.9.dev1 --candidate linux` produces `$M32_BUILD/stage-linux-0.11.9.dev1/`, holding `the_one/` with `__version__ = "0.11.9.dev1"`, and `icon-512.png` reachable for the wrappers.
  - It applies `packaging/linux/patches/*.diff` in name order, if any exist.
  - It exits non-zero if the `__version__` line does not match exactly once, or if the output path resolves inside the repo.
  - Afterwards, `git status --porcelain -- the_one/ pyproject.toml uv.lock` is empty.
- [ ] **AC2 — The container images exist, and their contents are recorded.**
  - **`baseline`:** the distro's GNOME desktop metapackage, `ubuntu-desktop-minimal` on 26.04 and `task-gnome-desktop` on Debian 13. Try it with its default recommends first. If that pulls `snapd` or fails headless, install the metapackage with `--no-install-recommends` plus its Recommends list minus `snapd` and service-only packages, and log the exact substitution.
  - **`bare`:** the distro image plus `python3` only.
  - Harness-only observation tools (`procps`, `dbus-x11` or `dbus-run-session`, an X screenshot tool, `curl`) are added in a separate final layer of each image, listed in the log apart from the stock contents.
  - For every image, the flight log records: the Python version; whether `gir1.2-webkit2-4.1`, `libwebkit2gtk-4.1-0` (or its t64 name), `gir1.2-gtk-3.0`, `gir1.2-ayatanaappindicator3-0.1`, `libgirepository-2.0-0` and `bubblewrap` are installed (`dpkg -l`); and that `node` and `uv` are absent.
- [ ] **AC3 — A freezes with Python 3.11, the pinned closure and the staged code.**
  - The build venv under `$M32_BUILD` is a uv-managed CPython 3.11. It installs the exported closure with `--no-deps`, then pinned PyInstaller (version recorded in the README).
  - The spec reads the staged copy (from an environment variable, never the repo root).
  - The build log shows Python 3.11.x.
  - The frozen `the-one version` prints `GleepGlorp AI v0.11.9.dev1` for the N+1 build and `v0.11.8` for N.
  - No path under the repo root appears in the bundle's `PYZ` table of contents (checked with `pyi-archive_viewer` or by grepping the bundle).
  - Neither PyInstaller, `appimagetool` nor any build tool appears in `uv.lock` or the root `pyproject.toml`.
- [ ] **AC4 — The gi premise is recorded before and after excludes.** The flight log lists the bundle's `libwebkit2gtk*`, `libjavascriptcoregtk*`, `libgtk-3*`, `libglib-2.0*`, `libgobject-2.0*`, `libgirepository*` and `*.typelib` files twice: from a first build with no excludes, and from the final build. The final build contains none of them, and contains no other library from `excludes.txt`'s families.
- [ ] **AC5 — Four packages, correctly formed.**
  - An AppImage for each of N and N+1, built by a pinned `appimagetool` release under `--appimage-extract-and-run`, with a pinned runtime file (`--runtime-file`). Both SHA-256 sums go in the README.
  - The AppImage's `AppRun` does not put the AppDir ahead of the system directories on `PATH`.
  - A `.deb` for each of N and N+1 (`dpkg-deb --build --root-owner-group`), with `Package: gleepglorp-ai`, `Version: 0.11.8` / `0.11.9~dev1` and `Architecture: amd64`.
  - `Depends:` declares the WebKitGTK 4.1 runtime and its typelib, the GTK 3 typelib, `libgirepository-2.0-0`, the Ayatana AppIndicator typelib and `python3`. Alternatives (`a | b`) cover the t64 renames seen in AC2.
  - `dpkg-deb -I` and `dpkg-deb -c` show the control fields and the `/opt/gleepglorp-ai/`, `/usr/bin/the-one`, `.desktop` and icon paths.
  - No maintainer scripts are needed. If one is added, its reason is logged.
- [ ] **AC6 — Lint, unit gate and forbidden paths.**
  - `.venv/bin/ruff check packaging/` and `ruff format --check packaging/` pass.
  - `make test-unit` passes, with the skip count recorded.
  - `git diff --stat mission/32-installers` shows no change under `the_one/`, `tests/`, `.github/`, `ci/`, `pyproject.toml` or `uv.lock`.

## Verification Steps
- AC1: run `stage.py`; `grep -n __version__ $M32_BUILD/stage-linux-0.11.9.dev1/the_one/__init__.py`; then `M32_BUILD=$PWD/x stage.py …` must exit non-zero; then the `git status` command.
- AC2: `docker build --target baseline|bare …`, then `docker run --rm <img> sh -c 'python3 --version; dpkg -l <pkgs> 2>&1 | tail -n +6; command -v node uv; echo rc=$?'`. Paste the output.
- AC3: the head of the build log; `$M32_BUILD/…/the-one version` for both builds; the archive-viewer or grep check; `grep -i -E 'pyinstaller|appimagetool' uv.lock pyproject.toml` finds nothing.
- AC4: `find <bundle> \( -name 'libwebkit2gtk*' -o … -o -name '*.typelib' \)` before and after.
- AC5: `ls -l` the four packages; `sha256sum` the pinned tools; `dpkg-deb -I` and `-c` excerpts; `cat AppDir/AppRun`.
- AC6: the commands named in the criterion.

## Implementation Guidance

1. **Set up the worktree.** Create the worktree venv for lint and the unit gate (`uv venv` + `pip install -e ".[all-llms,dev]"`, as the project normally does). Read and record the operator's default data dir path once, with `.venv/bin/python -c "from the_one.config import settings; print(settings.data_dir)"`. This leg starts no app instance on the host; leg 2 uses the path for its safety check.
2. **Write `stage.py`.**
   - Stdlib only, with arguments `--version`, `--candidate` and `--out`.
   - Use `shutil.copytree` with an ignore for `__pycache__`.
   - Rewrite the version with a regex that must match exactly once.
   - Apply patches with `patch -p1 -d <copy>` (or `git apply --directory`); fail on any reject.
   - Resolve `--out` and refuse paths inside `git rev-parse --show-toplevel`.
3. **Write the two images per distro** (multi-stage `bare` and `baseline` targets, then an `observe` layer on each).
   - Use `DEBIAN_FRONTEND=noninteractive`, and never start systemd.
   - Tag them `m32/ubuntu-26.04:{bare,baseline}` and `m32/debian-13:{bare,baseline}`.
4. **Build the venv and freeze without excludes.**
   - `uv venv --python 3.11 $M32_BUILD/venv-pyi`; then `uv export …` into a requirements file; then `uv pip install --python $M32_BUILD/venv-pyi/bin/python -r req.txt --no-deps`; then `pyinstaller==<pin>`.
   - PyGObject and pycairo compile from source against the host headers. If that fails, log the error and stop with `[BLOCKED:…]` rather than switching interpreters.
   - Write `the-one.spec` from the Windows contract (Context), with one `Analysis` on `packaging/windows/frozen_entry.py` and `pathex=[<staging dir>]`.
   - Build, then record AC4's "before" listing.
5. **Add the exclude list and the runtime hook, and rebuild.**
   - `excludes.txt` covers the library families GLib/GObject/GIO, GTK3/GDK, WebKit2GTK/JavaScriptCore, girepository, cairo/pango/harfbuzz/fontconfig/freetype, gdk-pixbuf, and their X11/Wayland/EGL dependencies. Use the AppImage project's excludelist as the reference, but match by family prefix. The spec filters `a.binaries` against it, and drops `*.typelib` from `a.datas`.
   - `rthook_host_gtk.py` runs before PyInstaller's gi hook, or overrides it:
     - set `GI_TYPELIB_PATH` to `/usr/lib/x86_64-linux-gnu/girepository-1.0:/usr/lib/girepository-1.0`;
     - remove the bundle directory from `LD_LIBRARY_PATH`, restoring `LD_LIBRARY_PATH_ORIG` when PyInstaller saved one, so child processes, including WebKit's helpers, never see the bundle's libraries;
     - add a comment explaining why each line exists.
   - Record AC4's "after" listing. The hook only needs to be correct for leg 2 to measure. If, after three exclude-list attempts, the bundle still holds a library from the excluded families that the freeze cannot run without, stop iterating and log it for leg 2 to score.
6. **Wrap.** Write `build.sh <version>`, which stages, freezes and wraps one version. Run it for N and N+1.
   - **AppImage:** `AppDir/usr/lib/gleepglorp-ai/` holds the bundle. `AppRun` execs `"$APPDIR/usr/lib/gleepglorp-ai/the-one" "${@:-app}"` with `PATH` untouched. Add the `.desktop` file and the icon, then run the pinned `appimagetool --appimage-extract-and-run --runtime-file <pinned runtime> AppDir out.AppImage`.
   - **`.deb`:** a staging root with `opt/gleepglorp-ai/`, `usr/bin/the-one -> /opt/gleepglorp-ai/the-one`, `usr/share/applications/gleepglorp-ai.desktop` (`Exec=the-one app`) and `usr/share/icons/hicolor/512x512/apps/gleepglorp-ai.png`, plus `DEBIAN/control` filled from the template.
7. **Check AC3 and AC5, then AC6.** Write the leg's flight-log entry with every listing and excerpt, and set the leg to `landed`.

## Edge Cases
- **A t64-renamed library package** (`libwebkit2gtk-4.1-0t64` and similar): use the names AC2 found, as `Depends:` alternatives.
- **`ubuntu-desktop-minimal` pulls `snapd` or a service that fails during install**: use the logged substitution (AC2). Never use `--privileged` or run systemd.
- **The PyInstaller gi hook re-sets `GI_TYPELIB_PATH` after the custom hook**: order the runtime hooks so the custom one wins, or set `hooksconfig={"gi": {...}}` to stop the typelib collection. Prove it by reading `GI_TYPELIB_PATH` inside the frozen app with a debug environment print, logged once.
- **The bundle needs a library from an excluded family that the host lacks** (for example, a newer `libffi` or `libstdc++`): do not exclude it if the host might lack it. `excludes.txt` lists only families that every target baseline provides, which AC2's `dpkg -l` shows.
- **An app-side change is needed to freeze or start**: write it as `packaging/linux/patches/NN-<slug>.diff` against `the_one/`, have `stage.py` apply it, and log the reason. Never edit `the_one/`.

## Files Affected
- `packaging/spike/` (new): `stage.py`, `images/*.Dockerfile`, `README.md`.
- `packaging/linux/` (new): `the-one.spec`, `rthook_host_gtk.py`, `excludes.txt`, `build.sh`, `AppRun`, the templates, `README.md`, and `patches/` if needed.
- `missions/32-installers-everywhere/flights/01-choose-packaging-toolchain/flight-log.md`: the leg entry.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked against the worktree at `4892b1f` on 2026-10-23, then re-checked by the leg design review:
- `packaging/windows/the-one.spec`: the repo-root `sys.path` insert and `from the_one import __version__` (spec lines 34-49, which the Linux spec must not copy), and the collection contract quoted in Context.
- `packaging/windows/frozen_entry.py`: `from the_one.main import cli_entry`; `freeze_support()` before `cli_entry()`.
- `scripts/windows_test_copy.py::CLOSURE_UV_EXPORT_ARGS`: as quoted.
- `the_one/__init__.py`: a single `__version__ = "0.11.8"`. `the-one version` prints `GleepGlorp AI v<version>` (per the design review).
- `the_one/interfaces/web/static/brand/icon-512.png` exists (the only packaging icon asset is `packaging/windows/installer-assets/the-one.ico`).
