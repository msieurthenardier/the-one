# Leg: linux-recipe

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
Make the Linux recipe read one product-metadata source (DD6):
- `packaging/product.toml` and a stdlib renderer fill every Linux template;
- the build takes its version from `the_one/__init__.py` unless a test build overrides it;
- both packages ship `.desktop` files with the "Quit GleepGlorp AI" action, and AppStream metainfo;
- the AppImage adds itself to the application menu from `AppRun` (DD5).

A unit test pins `pyproject.toml`'s version equal to `__version__`, and the data-dir slug to `the_one/config.py`'s.

## Context
- **Flight DDs:**
  - DD6: `product.toml`, the renderer, the version source, the pin test, the slug pin; the dynamic `pyproject` version is deferred to Flight 4;
  - DD5: `AppRun` self-integration, separate desktop ids, `TryExec`, the absolute icon path, uninstall;
  - DD4: the "Quit GleepGlorp AI" desktop action runs `the-one quit` (leg 5 phase A);
  - DD9's premise table: AppStream metainfo, in case a software centre lists only components that have it (leg 4 phase C answers P3).
- **Leg 5 review notes for this leg:**
  - `StartupNotify=true` in the `.desktop` files, so GNOME passes an activation token;
  - `AppRun` and the `/usr/bin/the-one` symlink must not scrub `XDG_ACTIVATION_TOKEN`/`DESKTOP_STARTUP_ID`;
  - `AppRun` passes `quit` (and every other argument) through; with no arguments it runs `app`.
- **The build after leg 1:**
  - `packaging/linux/build.sh <version>` stages on the host, then runs `build-inner.sh` in `m32/linux-build:f2`, which:
    - freezes;
    - copies the fallback set;
    - writes the AppDir (`AppRun`, a root `.desktop` from `gleepglorp-ai.desktop.in` with `@EXEC@`, the icon, `.DirIcon`);
    - runs `appimagetool`;
    - builds the `.deb` (`/opt/gleepglorp-ai`, `/usr/bin/the-one` symlink, `.desktop`, icon, `control` from `control.in` with `@DEB_VERSION@`/`@INSTALLED_SIZE@`).
  - The package file names `gleepglorp-ai_<debver>_amd64.deb` and `GleepGlorp_AI-<ver>-x86_64.AppImage` are what `packaging/spike/check.sh` expects. **Keep them.**
- **Concurrency:** leg 5 edits `the_one/` and `tests/` (shell, routes, CLI) at the same time. This leg touches `packaging/` (not `packaging/linux/vm/`, which is leg 4's) and its own new test files. It must not edit `packaging/spike/` (leg 8 folds it), except that `stage.py` may gain a version-reading helper if needed (say so).
- **Debug variables:** `M32_DEBUG_ENV`, `M32_FORCE_FALLBACK` and `M32_ABI_PROBE` in `rthook_host_gtk.py` are renamed in leg 8 together with the harness that sets them. Not this leg.

## Inputs
- `packaging/linux/{build.sh,build-inner.sh,build.Dockerfile,the-one.spec,rthook_host_gtk.py,AppRun,control.in,gleepglorp-ai.desktop.in,README.md}`
- `packaging/spike/stage.py` (version rewrite)
- `the_one/__init__.py::__version__`, `pyproject.toml` `version`, `the_one/config.py::_default_data_dir`
- `the_one/interfaces/web/static/brand/icon-512.png`
- No `LICENSE` file exists, and `pyproject.toml` has no `license` field. The operator chose **MIT** on 2026-10-24, so this leg adds both.

## Outputs
- **`packaging/product.toml`** (new). The keys, values as today:
  - `display_name = "GleepGlorp AI"`;
  - `summary` (one line, used for `Comment` and the Debian synopsis);
  - `description` (a short paragraph);
  - `maintainer` (as today's `control`);
  - `homepage = "https://github.com/msieurthenardier/the-one"` (required; operator, 2026-10-24);
  - `license = "MIT"` (SPDX; operator, 2026-10-24);
  - `[linux]`:
    - `package = "gleepglorp-ai"`;
    - `desktop_id = "gleepglorp-ai"`;
    - `appimage_desktop_id = "gleepglorp-ai-appimage"`;
    - `appimage_name = "GleepGlorp AI (AppImage)"`;
    - `appimage_file_stem = "GleepGlorp_AI"`;
    - `install_dir = "/opt/gleepglorp-ai"`;
    - `executable = "the-one"`;
    - `wm_class = "the-one"`;
    - `categories = "Utility;"`;
    - `quit_action_name = "Quit GleepGlorp AI"`;
    - `metainfo_id` (an AppStream component id; choose a valid reverse-DNS form, such as `ai.gleepglorp.GleepGlorpAI`, and record it; it must stay stable once shipped);
  - `icon_source = "the_one/interfaces/web/static/brand/icon-512.png"`;
  - `data_slug = "the-one"` (read-only: the unit test pins it).

  A comment at the top says what each consumer is: Linux now; macOS (Flight 3) and Windows (Flight 4) later.
- **`packaging/render.py`** (new, stdlib only: `tomllib`, Python 3.11 or newer).
  - `load(repo) -> dict`: `product.toml`, plus:
    - `version` from `the_one/__init__.py` (regex, the same as `stage.py`'s);
    - `deb_version` (`.devN` → `~devN`; any other PEP 440 pre-release form, such as `aN`, `bN` or `rcN`, is an error for now);
    - `release_date` (`YYYY-MM-DD`, from `SOURCE_DATE_EPOCH` when set, else today; `--set release_date=` overrides). The build sets `SOURCE_DATE_EPOCH` from the last commit's time (`git log -1 --format=%ct`), so a rebuild of the same tree renders the same file.
  - `render(template_text, values) -> str`: replaces `@KEY@`, where the key pattern is `@[A-Z][A-Z0-9_]*@` (uppercase only, so an email such as `noreply@invalid` is never touched; a test pins this). Any key left unreplaced is an error (exit non-zero).
  - A CLI: `render.py --repo R --template T [--set K=V ...]` prints the rendered text; `render.py --repo R --json` prints the values, for Flights 3 and 4.
  - `--set version=X` overrides the version (the N/N+1 builds).
- **Templates in `packaging/linux/`:**
  - `control.in`: `Package`, `Maintainer`, `Description` and `Homepage` from the metadata; the Flight 1 "spike prototype" wording removed.
  - `gleepglorp-ai.desktop.in` (the `.deb`'s): `Name`, `Comment`, `Icon=@DESKTOP_ID@`, `Exec=@EXECUTABLE@ app`, `TryExec=@EXECUTABLE@`, `Terminal=false`, `Categories`, `StartupWMClass`, `StartupNotify=true`, `Actions=quit;`, then `[Desktop Action quit]` with `Name=@QUIT_ACTION_NAME@` and `Exec=@EXECUTABLE@ quit`.
  - `appimage.desktop.in`: the AppImage's embedded entry, used both as the AppDir root `.desktop` (what `appimagetool` validates) and as the self-integration source.
    - It has `Name=@APPIMAGE_NAME@`, `StartupNotify=true` and the same Quit action.
    - **Three runtime placeholders, filled by `AppRun` and left alone by the renderer** (lowercase-free, uppercase names in a reserved list). They need different escapes:
      - `@APPIMAGE_EXEC@` in `Exec=@APPIMAGE_EXEC@ app` and the Quit action's `Exec=@APPIMAGE_EXEC@ quit`. It holds the path double-quoted per the Desktop Entry spec's two layers. Inside the quotes `"`, `` ` ``, `$` and `\` get a backslash (the Exec layer). Then every `\` is doubled (the string layer), and every `%` becomes `%%`. Verified in design review: `Exec="/home/u/My \\$App/G.AppImage" app` passes `desktop-file-validate` 0.27.
      - `@APPIMAGE_PATH@` in `TryExec=@APPIMAGE_PATH@`. `TryExec` takes no quoting, spaces are fine, and `$` is literal; only `\` doubles (the string layer).
      - `@ICON_PATH@` in `Icon=@ICON_PATH@`: an absolute path, unquoted, with only the string-layer escape.
    - `AppRun` skips integration entirely when the path contains a newline, a tab or any other control character.
    - The AppDir root copy (for `appimagetool`'s validation) is rendered with `Exec=AppRun app` and `Icon=@DESKTOP_ID@`, as today. The self-integration copy goes to `usr/share/gleepglorp-ai/integration.desktop.in`.
  - `metainfo.xml.in` (AppStream, `type="desktop-application"`) contains:
    - `id`, `name`, `summary`;
    - `description`, whose first paragraph is a full sentence or two;
    - `metadata_license` `CC0-1.0`, and `project_license` `@LICENSE@` (MIT);
    - `<url type="homepage">@HOMEPAGE@</url>`, required: without it `appstreamcli validate --no-net` exits 3 on `url-homepage-missing`;
    - `launchable type="desktop-id"` naming the root desktop file's id (`@DESKTOP_ID@.desktop`, which serves both packages);
    - `<content_rating type="oars-1.1"/>` and `<developer>`;
    - `<releases><release version="@VERSION@" date="@RELEASE_DATE@"/></releases>`. A release with no date is an error.

    It is installed at `usr/share/metainfo/<metainfo_id>.metainfo.xml` in the `.deb` and in the AppDir. The validation must exit 0, meaning no warnings; info and pedantic findings are allowed.
- **`LICENSE`** (new, repo root): the MIT text, `Copyright (c) 2026 msieurthenardier`.
- **`pyproject.toml`:** one additive line, `license = "MIT"`, in `[project]`. The file is shared with Mission 31, so this is the only edit; nothing else moves. `uv lock --check` must still pass (license metadata does not change the lock, but verify it).
- **`build.sh`:**
  - **Arguments:** `build.sh [--version X] [--no-excludes]`; the version defaults to `render.py`'s (`__version__`).
    - `build.sh --no-excludes` never reads the flag as a version.
    - Today's positional form (`build.sh 0.11.8 [--no-excludes]`) is still accepted, with a stderr warning: "build.sh: a positional version is deprecated; use --version X". The leg 3 and leg 8 notes use it.
    - `--version` together with a positional version is an error.
  - **Order:**
    1. Resolve the version first.
    2. Stage with that version. `stage.py` recreates the stage dir, so render after it.
    3. Render into `$STAGE/rendered/` with `--set version=<that version>`, so the staged `__version__` and the rendered one always agree. Under `M32_FROM_HEAD=1` the version must be passed explicitly.

    The stage is mounted read-only into the container, `rendered/` included, so the container needs no TOML or renderer.
  - **`build-inner.sh`** copies the rendered files and no longer hard-codes names: file names and paths come from `rendered/build.env`.
    - Only machine-safe values go in it (package name, file stem, install dir, executable, desktop ids, metainfo id, `VERSION`, `DEB_VERSION`). Display strings are used only through the rendered files.
    - The container validates the file before sourcing it: `if grep -qvE '^[A-Z][A-Z0-9_]*=[A-Za-z0-9._/+~:-]*$' build.env; then fail; fi`. Then `set -a; . ./build.env; set +a`.
- **`build.Dockerfile`:** add `desktop-file-utils` and `appstream`. `build-inner.sh` runs `desktop-file-validate` on every `.desktop` it ships and `appstreamcli validate --no-net` on the metainfo; a failure fails the build.
- **`AppRun`** (POSIX sh, `set -u`).
  - **`AppRun` is rendered from `AppRun.in`,** so its names (bundle path `usr/lib/@PACKAGE@/@EXECUTABLE@`, integration template path, `@APPIMAGE_DESKTOP_ID@`, icon name) come from the metadata like everything else. The runtime placeholders (`@APPIMAGE_EXEC@`, `@APPIMAGE_PATH@`, `@ICON_PATH@`) appear only in the integration template, not in `AppRun` itself. The tests run the rendered `AppRun`.
  - With no argument, or `app` as the first argument:
    - **Self-integration, best effort.** Every step in a subshell or with `|| true`, so it never stops the launch, and it writes only when the content changes:
      - `"$APPIMAGE"` must be set and point at an existing regular file, and `"$APPDIR"` must be set; otherwise skip;
      - the target directory is `${XDG_DATA_HOME:-$HOME/.local/share}`;
      - the icon goes to `<data>/icons/hicolor/512x512/apps/gleepglorp-ai-appimage.png` (copied with `cmp`, rewritten only on change);
      - the entry goes to `<data>/applications/<appimage_desktop_id>.desktop`, rendered from `usr/share/<package>/integration.desktop.in` by substituting the three runtime placeholders with the escaped values above.
        - **The substitution uses no `sed`.** It uses `awk` reading the values from `ENVIRON["…"]` (never `-v`, which interprets backslashes) and replacing with `index`/`substr`, so `\`, `&`, `|`, `$`, `"` and spaces pass through literally.
        - It is written atomically, with `umask 022`: a temp file in the same directory (`mktemp` if available, else a `.$$` suffix), then `mv`. The temp file is removed on any failure.
      - The entry is rewritten only when its content differs: `cmp -s` when `command -v cmp` finds it, else a `[ "$(cat a)" = "$(cat b)" ]` fallback.
    - Then it runs the app.
  - With any other argument (`quit`, `doctor`, `version`, `serve`, …): pass through with no integration.
  - **Environment:** `PATH` stays unmodified, as today, and `XDG_ACTIVATION_TOKEN`, `DESKTOP_STARTUP_ID` and `APPIMAGE`/`APPDIR` are not unset.
- **`the-one.spec`:** unchanged, apart from anything needed for the renamed or rendered paths. None expected.
- **`packaging/linux/README.md`:** product metadata, rendering, `--version`, the validation tools, self-integration, uninstall (the AppImage file, then the two user-level files).
- **Unit tests,** `tests/test_packaging_metadata.py` (new). Load `packaging/render.py` by path, as `tests/test_windows_test_copy.py` loads scripts:
  - every required key is present;
  - `data_slug` equals the slug in `the_one/config.py::_default_data_dir` (parse the source, or call `platformdirs` with `data_slug` and compare to `_default_data_dir()`);
  - `pyproject.toml`'s `version` equals `the_one.__version__` (`tomllib`);
  - `deb_version` maps `.devN` to `~devN`;
  - an unreplaced `@KEY@` raises;
  - `--set version=` overrides;
  - every template under `packaging/linux/` renders with no leftover key, except `@APPIMAGE_PATH@`/`@ICON_PATH@` in the integration template.
- **Unit tests,** `tests/test_packaging_apprun.py` (new). Run the real `AppRun` with `sh`, against a fake AppDir in `tmp_path`: a stub `usr/lib/gleepglorp-ai/the-one` that echoes its arguments, and the rendered integration template. It sets `APPIMAGE`, `APPDIR`, `HOME` and `XDG_DATA_HOME` into `tmp_path`, and covers:
  - no arguments: the entry and icon are written, `Exec`/`TryExec`/the Quit `Exec` hold the AppImage path, and the stub got `app`;
  - a second run: the file is unchanged. Set the file's mtime to an old value with `os.utime` first, then compare `st_mtime_ns`, rather than relying on timing;
  - a moved AppImage path: the entry is rewritten;
  - paths containing a space, `$`, `"`, `` ` ``, `\`, `%` and `&`: each quoted correctly per placeholder, and `desktop-file-validate` (if on the host; skip otherwise) accepts the result;
  - a path with a newline: no integration, and the app still runs;
  - `quit`: no integration, and the stub got `quit`;
  - `APPIMAGE` unset: no files, and the app still runs;
  - a read-only `XDG_DATA_HOME`: no crash, and the app still runs;
  - `XDG_ACTIVATION_TOKEN` reaches the stub.

## Acceptance Criteria
- [ ] **AC1** — `packaging/product.toml` and `packaging/render.py` exist as specified. `render.py --json` prints every value, plus `version` and `deb_version`.
- [ ] **AC2** — `build.sh` with no `--version` builds `0.11.8` packages (the current `__version__`), and `--version 0.11.9.dev1` builds the N+1 pair. The names are unchanged from leg 1's, and no name, version or path is hard-coded in `build.sh`/`build-inner.sh` any more (`grep -n "gleepglorp\|GleepGlorp" packaging/linux/build*.sh` shows none outside comments).
- [ ] **AC3** — inside the built packages (and `appimagetool.log` read):
  - the `.deb`'s `.desktop` and the AppImage's root and integration `.desktop` files pass `desktop-file-validate` (in the build log);
  - the metainfo passes `appstreamcli validate --no-net` with exit 0 (no warnings);
  - `appimagetool` accepts the AppDir. If it rejects the metainfo pairing, `<launchable>` must name the root `.desktop`. Only as a recorded last resort is `--no-appstream` passed;
  - the `.deb` contains `usr/share/metainfo/<id>.metainfo.xml`;
  - both entries carry `StartupNotify=true` and a `quit` action named "Quit GleepGlorp AI";
  - the `control` file has no "spike" wording.
- [ ] **AC4** — `AppRun` self-integration behaves as specified (`tests/test_packaging_apprun.py`, every case passing).
- [ ] **AC5** — `tests/test_packaging_metadata.py` passes, including the version pin, the slug pin, `license` matching `pyproject.toml`'s `license` (both MIT), and the `@KEY@` pattern leaving `noreply@invalid` alone. A deliberately wrong `pyproject` version makes it fail: shown once, then reverted, and recorded.
- [ ] **AC6** — no regression in the gates. These runs are slow and mostly waiting. If the session budget is short, the Developer may record the build artefacts and hand AC6 to leg 8's first step, saying so in the log; the leg then lands with AC6 marked deferred. `packaging/spike/check.sh` for the rebuilt `.deb` on `ubuntu-26.04-baseline` and the AppImage on `debian-13-baseline` (N=`0.11.8`, N+1=`0.11.9.dev1`, both built by this leg) gives the same PASS lines as leg 1 (G1 both, G2, G3, G4, upgrade, single-instance). One run each; one at a time.
- [ ] **AC7** — gates:
  - `make test-unit` passes (12 skips);
  - `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/ packaging/`;
  - `shellcheck` (`$HOME/the-one-m32-build/tools/shellcheck-0.10.0/`) on `build.sh`, `build-inner.sh` and `AppRun`;
  - no `m32-` container left running;
  - no port 8484/8485;
  - the operator data dir untouched;
  - only `packaging/` (not `vm/`, not `spike/` except a declared `stage.py` helper), `tests/test_packaging_*.py` and this flight's log changed by this leg.

## Verification Steps
- AC1: `python3 packaging/render.py --repo . --json`.
- AC2: `build.sh` runs; `ls $HOME/the-one-m32-build/f2/packages/`; the grep.
- AC3: the build log validation lines; `dpkg-deb -c`/`-f`; `--appimage-extract` and inspect.
- AC4/AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_packaging_metadata.py tests/test_packaging_apprun.py -x --timeout 30`.
- AC6: the `check.sh` score lines.
- AC7: the commands named.

## Implementation Guidance
1. `product.toml`, `render.py`, `LICENSE` and the `pyproject` license line, then the metadata tests.
2. The templates, then the rendering in `build.sh`, `build.env`, and the `build-inner.sh` changes. Rebuild the build image with the validation tools (the layers above it are cached). **Run one build early** and read `appimagetool.log` and the validator output before writing the tests, so any metainfo or `appimagetool` mismatch surfaces first.
3. `AppRun` and its tests.
4. Build N and N+1. Validate, then run the two AC6 gate runs.
5. README, then the flight-log section `### linux-recipe`. Record the metainfo id and license, and anything leg 8 (the fold) or leg 11 (the VMs) must know.

## Edge Cases
- **A `$` or backtick in the AppImage path:** quote per the Desktop Entry spec, as AC4 covers.
- **`XDG_DATA_HOME` set to a relative path:** the spec says ignore it. Fall back to `$HOME/.local/share`.
- **Two AppImages of different versions launched alternately:** the entry follows the last one launched, by design (DD5).
- **`appimagetool` and the metainfo:** `appimagetool` may warn, or fail, if the AppStream id does not match the desktop file. Make them consistent: `<launchable type="desktop-id">` names the root `.desktop` file's id.
- **`desktop-file-validate` rejects a key** (for example `StartupWMClass` placement, or `Categories` without a main category): fix the template, not the validator call.

## Files Affected
- `packaging/product.toml`, `packaging/render.py` (new)
- `packaging/linux/{build.sh,build-inner.sh,build.Dockerfile,AppRun,control.in,gleepglorp-ai.desktop.in,README.md}`
- `packaging/linux/{appimage.desktop.in,metainfo.xml.in}` (new)
- `packaging/linux/AppRun.in` (renamed from `AppRun`)
- `LICENSE` (new), `pyproject.toml` (one line)
- `tests/test_packaging_metadata.py`, `tests/test_packaging_apprun.py` (new)
- `missions/32-installers-everywhere/flights/02-linux-packages/flight-log.md` (own section)

## Citation Audit
Checked against the worktree after leg 1 landed (uncommitted):
- `build.sh`: positional `VERSION` required; staging on the host; `uv export --frozen`; `docker run … m32-build-<ver> -u uid:gid`, `packaging` read-only. Verified.
- `build-inner.sh`: hard-codes `gleepglorp-ai`, `GleepGlorp_AI`, `/opt/gleepglorp-ai`; `sed 's|@EXEC@|…|'` on `gleepglorp-ai.desktop.in`; `control.in` with `@DEB_VERSION@`/`@INSTALLED_SIZE@`. Verified.
- `AppRun`: no argument → `app`; `exec "$HERE/usr/lib/gleepglorp-ai/the-one" "$@"`; `PATH` untouched. Verified.
- `gleepglorp-ai.desktop.in`: `Exec=@EXEC@`, `Icon=gleepglorp-ai`, `StartupWMClass=the-one`; no Actions or StartupNotify. Verified.
- `control.in`: the spike wording in `Description`. Verified.
- `check.sh`: file-name defaults `gleepglorp-ai_<ver>_amd64.deb` and `GleepGlorp_AI-<ver>-x86_64.AppImage`. Verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
