# packaging/linux/checks - the Linux package check suite

Product check tooling for the Linux packages (Mission 32 Flight 2, DD8): container gates for a
built `.deb` or AppImage, and a real-GTK smoke test. Nothing here knows which tool built a
package. The staging step shared with the macOS build is `packaging/stage.py`; the macOS checks
are `packaging/macos/checks.sh`.

Images: `images/{ubuntu-26.04,debian-13}.Dockerfile` have targets `baseline` (the distro's GNOME
desktop metapackage) and `bare` (distro image plus `python3`), each ending in a separate
"observe" layer of harness-only tools (Xvfb, xwd, scrot, ...). Tags `m32/<distro>:{baseline,bare}`.

```
docker build --target baseline -t m32/ubuntu-26.04:baseline \
    -f packaging/linux/checks/images/ubuntu-26.04.Dockerfile packaging/linux/checks/images
```

## Gates

`gates.sh <candidate> <deb|appimage> <ubuntu-26.04|debian-13> <baseline|bare> --n N [--n1 N1]
[--pkgdir DIR] [--evidence DIR] [--display wslg|xvfb] [--env K=V]... [--variant NAME]
[--extra-apt "pkgs"] [--pkg-n FILE] [--pkg-n1 FILE]` runs ONE disposable container
(`m32-gate-<format>-<distro>-<image>`, no `--privileged`, no `--network host`) from
`m32/<distro>:<image>`, mounts the packages read-only and `gates-inner.sh`, writes evidence to
`$M32_EVIDENCE/<candidate>/<format>/<distro>-<image>/` and scores it with `score.py`.

- **Display.** The window phase (gate 3, single instance, screenshot) runs only on `baseline`.
  `--display wslg` mounts `/mnt/wslg/.X11-unix` (display `:0`); `--display xvfb` starts a private
  `Xvfb :99 -screen 0 1920x1080x24` inside the container, so a hosted runner needs no desktop.
  The default is `wslg` when `/mnt/wslg/.X11-unix/X0` exists, else `xvfb`.
- Package file names follow `gleepglorp-ai_<N>_amd64.deb` and `GleepGlorp_AI-<N>-x86_64.AppImage`;
  `--pkg-n`/`--pkg-n1` override them.
- `--env K=V` (repeatable) adds to the window run's environment, which `gates-inner.sh` otherwise
  builds with `env -i`; `--variant NAME` changes only the evidence subdirectory; `--extra-apt`
  installs packages first, so `host-libs.txt` reflects them; `--env THE_ONE_PKG_ABI_PROBE=1` is
  probe mode (run the frozen app's ABI probe, scored with `score.py --probe`; an AppImage probe
  excludes stderr lines also seen in the `.deb` control run on the same image).
- `gates-inner.sh` (container side): non-root `tester` user, in order: install N, gate 4 (no
  `THE_ONE_DATA_DIR`, before seeding), seed an agent, install N+1, serve again (upgrade), `doctor`
  pinned and unpinned, gate 2, window checks. It records `host-libs.txt` (`ldconfig -p` per
  fallback soname) and each process's `/proc/<pid>/environ`.
- `score.py EVDIR --format F --distro D --image I --n N [--n1 N1]` scores a directory mechanically
  and prints one summary line (`G1p G1u G2 G3 G4 upgrade single`). Gate 1 treats any "skipped"
  doctor gate as a failure (window chrome's `skipped (not Windows)` excepted). Gate 3 is per
  soname: a fallback library must come from `/usr/lib` when the host resolves it and from the
  AppImage only when it does not; WebKitWebProcess maps nothing from the AppImage and its loader
  variables name no package path.
- `xwd2png.py` converts the `xwd` dump to PNG (Pillow).

## Real-GTK smoke

`gtk-smoke.sh <ubuntu-26.04|debian-13> --deb FILE [--control] [--evidence DIR]` runs
`gtk-smoke-inner.sh` in one container (`m32-gtk-smoke-<distro>[-control]`) on a private
`Xvfb :99` with no window manager: the window maps, a close request hides or exits as designed,
a second launch shows the first window, `the-one quit` and `POST /api/window/quit` exit the app,
and the window size survives a relaunch. `--control` runs an older package that lacks the state
and quit routes; it only proves the harness can see the unmapped-window trap.

## Post-freeze audit

`packaging/linux/audit.py` is not run from here: `build-inner.sh` runs it on the PyInstaller
bundle right after the freeze and fails the build on an `excludes.txt` match, a `*.typelib`, or
an ELF needing a `GLIBC_` version above 2.39. See `packaging/linux/README.md`.

## Debug variables and the `M32_` namespace

The variables the shipped hook reads are `THE_ONE_PKG_DEBUG`, `THE_ONE_PKG_FORCE_FALLBACK` and
`THE_ONE_PKG_ABI_PROBE` (the app ignores unknown `THE_ONE_` names). The build-time variables
(`M32_BUILD`, `M32_STAGE`, `M32_SOURCE`, `M32_FROM_HEAD`, `M32_NO_EXCLUDES`, `M32_ICNS`,
`M32_REQUIREMENTS`, `M32_LOGS`, `M32_VM`, `M32_EVIDENCE`) never ship and keep their names.

## Container facts that shape the evidence

- `doctor` runs under `xvfb-run`: the pystray `gtk` backend needs an X display to initialise Gtk.
- `/proc/<pid>/maps` of the app is read as the app's own user: Docker drops `CAP_SYS_PTRACE`.
- Window runs set `WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1`, `WEBKIT_DISABLE_COMPOSITING_MODE=1`,
  `WEBKIT_DISABLE_DMABUF_RENDERER=1`, `LIBGL_ALWAYS_SOFTWARE=1` (Docker blocks the namespaces
  WebKit's sandbox needs; no GPU).
- The AppImage runs with `APPIMAGE_EXTRACT_AND_RUN=1` (no FUSE in containers).
- The main window is created hidden and only maps after a focus request, so the screenshot is
  taken after the `POST /api/window/focus` call.
