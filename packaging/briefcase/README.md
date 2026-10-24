# packaging/briefcase - Briefcase on Linux (candidate B)

**Spike prototype, Mission 32 Flight 1. Not wired into CI, publishes nothing.**
It builds GleepGlorp AI as a Briefcase Linux *system package*: one `.deb` per target distro,
built in Briefcase's Docker image for that distro, running on the distro's own Python and the
desktop's own GTK 3 / WebKitGTK 4.1.

Pinned: **Briefcase 0.4.6** (PyPI 2026-10-13), installed in its own tool venv
`$M32_BUILD/venv-briefcase` (`uv venv --python 3.12 ...; uv pip install briefcase==0.4.6`), never in
the repo's `.venv`, `uv.lock` or the root `pyproject.toml`. Briefcase clones its template from GitHub at
build time (host `git` needed) and needs Docker.

## Build

```
packaging/briefcase/build.sh 0.11.9.dev1            # ubuntu:26.04 and debian:13 .debs
M32_TARGETS=ubuntu:26.04 packaging/briefcase/build.sh 0.11.8
packaging/briefcase/build.sh 0.11.9.dev1 --appimage # also tries Briefcase's AppImage (fails, see below)
```

Output under `$M32_BUILD` (outside the repo): `packages-briefcase/the-one_<ver>-1~<vendor>-<codename>_amd64.deb`
(`the-one_0.11.9.dev1-1~ubuntu-resolute_amd64.deb`, `...~debian-trixie...`), logs in
`briefcase-logs-<ver>/`. The package is named `the-one`, not `gleepglorp-ai`: Briefcase derives it from
`app_name`. `formal_name = "GleepGlorp AI"` is the menu name; the `.desktop` file is
`ai.gleepglorp.the-one.desktop`.

## What `build.sh` does

1. `packaging/spike/stage.py --candidate briefcase` copies `the_one/` to the staging dir, rewrites
   `__version__`, and applies `patches/*.diff` (DD4: staging copy only, never `the_one/`).
2. Adds what Briefcase insists on: a placeholder `LICENSE.txt` and `CHANGELOG.md`, `icon-<size>.png`
   derived from the staged `icon-512.png`, and `closure.txt` (the same hash-pinned
   `uv export --no-dev --no-emit-project --extra gui --extra all-llms` that candidate A installs).
3. Fills `pyproject.toml.in` into the staging root as `pyproject.toml` (the version is the script argument).
4. For each target: `briefcase create|build|package linux system --target T --no-input --adhoc-sign`.

## Config facts that matter

- **Hash-pinned closure**: `requires = ["-r", "./closure.txt"]` plus
  `requirement_installer_args = ["--no-deps", "--require-hashes"]`. A `requires` entry is one pip
  argument and cannot carry `--hash`, but Briefcase copies a path-like entry into the bundle so the build
  container can read it. `--no-deps` matches A (`uv pip install --no-deps`); without it pip also resolves
  huggingface-hub's `hf-xet`, which the lock leaves out.
- **Build image**: `system_requires` (`pkg-config`, `libcairo2-dev`, `libgirepository-2.0-dev`,
  `gobject-introspection`) lets pip compile pycairo and PyGObject 3.56 in the container (the only
  source builds; the rest are wheels).
- **Runtime `Depends`**: `system_runtime_requires` lists `python3` (Briefcase adds only `libc6` and
  `libpython3.<minor>`) plus the WebKitGTK / GTK / girepository / AppIndicator / cairo stack. No `a | b`
  alternatives: the list is pasted unquoted into a Dockerfile line.
- **`allow_subprocesses = true`** is set, but in Briefcase 0.4.6's Linux system template it has no
  effect: the C launcher sets `sys.executable` to `/usr/bin/the-one` regardless. See the flight log.
- The launcher runs the module `the_one` as `__main__`; the `.desktop` `Exec` is fixed to
  `/usr/bin/the-one %F`. Neither is configurable (the module only through `BRIEFCASE_MAIN_MODULE`).

## Patches (DD4)

- `01-bare-start-opens-window.diff`: `the-one` with no arguments runs `app` (the desktop window) instead of
  the terminal chat; `the-one chat` still runs the chat. Needed because the `.desktop` `Exec` cannot carry
  an argument.
- `02-briefcase-counts-as-frozen.diff`: `is_frozen()` is true inside a Briefcase system app (marker:
  `<prefix>/lib/<name>/app_packages` beside the launcher), and `_bundle_dir()` returns `None` there (the
  launcher dir is `/usr/bin`; stripping it from `PATH` would be wrong). Without it `resolve_python()`
  returns the launcher itself, so `python_exec`, MCP stdio and the shell tool would re-launch the app.

## Other files

- `run-gates.sh <label>`: runs `packaging/spike/check.sh` over the four deb x image combinations.
- `probe.sh <label> <pkgdir> <version>`: the `sys.executable` / `is_frozen` / child `PATH` / `.env`
  probes and the bare-launch (desktop entry) window check.
