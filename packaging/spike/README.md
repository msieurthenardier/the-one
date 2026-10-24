# packaging/spike - Mission 32 Flight 1 spike tooling

**This is spike tooling, not product.** It is the Flight 1 measurement harness
(Mission 32); Flights 2-3 may reuse it. Flight 1 chose PyInstaller on every
platform, so only the PyInstaller recipes remain. It is not wired into CI.
The decision is recorded in the flight log.

- `stage.py --version V --candidate C [--out DIR]`: copies `the_one/` to
  `$M32_BUILD/stage-C-V/` (default `$HOME/the-one-m32-build`), rewrites
  `__version__` there, applies `packaging/C/patches/*.diff` in name order, and
  copies `icon-512.png`. It never writes into the repo, refuses an output path
  inside the repo, and fails unless exactly one `__version__` line matches.
- `images/{ubuntu-26.04,debian-13}.Dockerfile`: targets `baseline` (the distro's
  GNOME desktop metapackage) and `bare` (distro image plus `python3`), each ending in
  a separate "observe" layer of harness-only tools. Tags: `m32/<distro>:{baseline,bare}`.

```
docker build --target baseline -t m32/ubuntu-26.04:baseline -f packaging/spike/images/ubuntu-26.04.Dockerfile packaging/spike/images
```

## Gate runner (leg `linux-pyinstaller-gates`)

Nothing here knows which tool built a package.

- `check.sh <candidate> <deb|appimage> <ubuntu-26.04|debian-13> <baseline|bare> --n N --n1 N1 [--pkgdir DIR] [--evidence DIR]`
  runs ONE disposable container (`m32-gate-<format>-<distro>-<image>`, no `--privileged`, no
  `--network host`) from `m32/<distro>:<image>`, mounts the packages read-only and
  `inner.sh`, and writes evidence to `$M32_EVIDENCE/<candidate>/<format>/<distro>-<image>/`.
  The window (gate 3, single instance, screenshot) runs only on `baseline`, on WSLg's X socket.
  Package file names follow `gleepglorp-ai_<N>_amd64.deb` and `GleepGlorp_AI-<N>-x86_64.AppImage`;
  a candidate whose names differ passes `--pkg-n FILE --pkg-n1 FILE`;
  default behaviour is unchanged.
- `inner.sh` (container side): non-root `tester` user, in this order: install N, gate 4 (no
  `THE_ONE_DATA_DIR`, before seeding), seed an agent, install N+1, serve again (upgrade),
  `doctor` pinned and unpinned, gate 2, window checks.
- `score.py EVDIR --format F --distro D --image I --n N --n1 N1` scores a directory
  mechanically and writes `score.json` plus one summary line.
- `xwd2png.py` converts the `xwd` dump to PNG (Pillow).

Container facts that shape the evidence (all recorded in the flight log):

- `doctor` runs under `xvfb-run`: the pystray `gtk` backend needs an X display to initialise Gtk,
  so without one the desktop-shell gate fails for a reason that is not the package.
- `/proc/<pid>/maps` of the app is read as the app's own user: Docker drops
  `CAP_SYS_PTRACE`, so root cannot read another uid's maps.
- Window runs set `WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1`, `WEBKIT_DISABLE_COMPOSITING_MODE=1`,
  `WEBKIT_DISABLE_DMABUF_RENDERER=1`, `LIBGL_ALWAYS_SOFTWARE=1` (Docker blocks the namespaces
  WebKit's sandbox needs; no GPU). Real-desktop behaviour is Flight 2's check.
- The AppImage runs with `APPIMAGE_EXTRACT_AND_RUN=1` (no FUSE in containers).
- The main window is created hidden and only maps after a focus request, so the screenshot is
  taken after the `POST /api/window/focus` call.
