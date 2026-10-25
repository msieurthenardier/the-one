# Leg: vm-apparatus

**Status**: completed
**Flight**: [Linux packages](../flight.md)

## Objective
Build the fresh-VM apparatus (DD9): stock Ubuntu 26.04 and Debian 13 GNOME guests, run by QEMU/KVM inside a Docker container, provisioned once and reused through fresh overlays, with helpers to act (QMP keyboard and mouse, SSH) and observe (QMP screendump, SSH, the app's API inside the guest). Then use Flight 1's existing packages to answer the install-side premises that could divert the flight, before any hosted spend.

## Context
- **Flight DDs:** DD9 (the apparatus, the guests, act and observe, resources, safety, the premise table), DD10 (the closing walk uses these guests through WSLg).
- **Can run beside legs 2 and 3.** It touches only `packaging/linux/vm/` (new), `.gitignore` if needed, and its own flight-log section. It touches no `the_one/`, no `tests/` and no other `packaging/` file.
- **Planning probe:** KVM works in a container (`--device /dev/kvm`, API 12, nested `Y`). Host: 20 cores, 15 GB RAM, about 786 GB free on `/home`.
- **Packages for the probes:** Flight 1's builds, untouched, at `$HOME/the-one-m32-build/packages/`:
  - `gleepglorp-ai_0.11.8_amd64.deb` and `gleepglorp-ai_0.11.9~dev1_amd64.deb` (N and N+1);
  - `GleepGlorp_AI-0.11.8-x86_64.AppImage` and `GleepGlorp_AI-0.11.9.dev1-x86_64.AppImage`.

  Copy them into the guest; never modify them. They lack this flight's app changes (no-tray hide, quit, state route), so this leg probes only the install, upgrade, remove, launch and render premises. Relaunch recovery is leg 6.
- **Images, checked at design time:**
  - Ubuntu: `https://releases.ubuntu.com/26.04/ubuntu-26.04-desktop-amd64.iso`, sha256 `487f87faaf547ea30e0aba4d5b53346292571256b25333a978db1692bcee9dd2`. A point release, `ubuntu-26.04.1-desktop-amd64.iso` (sha256 `601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f`), also exists. **Use 26.04.1,** the current release a user downloads today, and record the choice.
  - Debian: `https://cloud.debian.org/images/cloud/trixie/latest/debian-13-generic-amd64.qcow2` (200, about 439 MB). Pin the dated directory's URL and its `SHA512SUMS` entry at leg start, not `latest`.
- **Operator decisions:** the Ubuntu guest comes from the desktop ISO's autoinstall, so App Center and the seeded snaps are present (2026-10-24). No terminal for installs under test.

## Phases (one leg, three Developer sessions)
Design review cycle 1 sized this leg at more than one session. It runs as three sequential phases. Each is a separate Developer spawn, ends with a checkpoint entry in this leg's flight-log section, and leaves the leg `in-flight` until phase C lands it.

- **Phase A — runner, helpers, Debian.** AC1, AC3, AC4 on Debian, and AC6 so far. Debian is the easy guest, and it proves the helpers.
- **Phase B — the Ubuntu guest.** AC2, and AC4 on Ubuntu, within its own 2-hour box and its own `[BLOCKED:ubuntu-autoinstall]`.
- **Phase C — the premises.** AC5 on both guests, and AC6 final. The leg then lands.

## Inputs
- Docker; `/dev/kvm`.
- Network, for the image downloads and the guests' apt and snap traffic during provisioning and installs.
- Flight 1's packages, above.
- WSLg X socket (`/mnt/wslg/.X11-unix`), only for the optional visible display.

## Outputs
- **`packaging/linux/vm/Dockerfile`:** the QEMU runner image `m32/qemu`. It is based on a pinned `debian:13` digest, with `qemu-system-x86`, `qemu-system-gui` (a separate package, needed for `-display gtk`) and its GTK libraries, `qemu-utils`, `ovmf`, `openssh-client`, `python3`, `xorriso` (to pull the kernel and initrd out of the ISO) and `genisoimage` (for the seed ISO).
- **Firmware: UEFI for both guests (decided).** OVMF `OVMF_CODE` is read-only from the image. Each base gets its own writable `OVMF_VARS` copy, made at provisioning and stored beside the base image (`<distro>-base.vars.fd`). It is part of the base: hashed and made read-only with it, and copied (not shared) into each run's overlay dir. Otherwise the installed system's NVRAM boot entry is lost at the next boot.
- **The container runs as the invoking user:** `docker run --user "$(id -u):$(id -g)" --group-add "$(stat -c %g /dev/kvm)" --device /dev/kvm`. Every file it creates on the host (overlays, the QMP socket, dumps) is owned by the operator's uid, never root. `qemu-img` runs through the same image, also non-root, so nothing on the host needs `qemu-utils`.
- **`packaging/linux/vm/` scripts.** POSIX/bash plus stdlib Python; the names are suggestions:
  - **`provision-ubuntu.sh`:** downloads and verifies the ISO into `$M32_VM` (default `$HOME/the-one-m32-vm`), and installs it unattended into `ubuntu-26.04-base.qcow2` (30-40 GB sparse).
    - It uses the desktop installer's autoinstall: direct kernel boot of the ISO's `casper/vmlinuz` and `initrd` with `autoinstall` and a NoCloud `ds=` on the kernel command line, plus a `CIDATA` seed ISO carrying `autoinstall.yaml`.
    - **The seed is a NoCloud `CIDATA`-labelled ISO** holding `user-data` (a `#cloud-config` with the installer config under a top-level `autoinstall:` key, `version: 1`) and an empty `meta-data`. With that label no `ds=` is needed on the command line, which avoids the `;` escaping problem; the command line carries `autoinstall`. It is never a bare `autoinstall.yaml`.
    - **Before writing it, the Developer reads the installer's own autoinstall schema from the ISO** (inside its squashfs or installer snap): the 26.04 desktop installer is `ubuntu-desktop-bootstrap`, a Flutter UI over the subiquity backend, and its schema differs from the server one. Expect `source: id: ubuntu-desktop` (the default, non-extended selection) and `identity`.
    - The autoinstall:
      - sets the user `tester`, with a lowercase alphanumeric test-only password from the README, so `qmp.py type` needs no shift handling;
      - adds `openssh-server`, the only package beyond "stock", recorded;
      - sets `refresh-installer: {update: no}` and `shutdown: poweroff`;
      - in `late-commands` (`curtin in-target --target=/target -- …`): GDM autologin, `gnome-initial-setup-done`, and screen lock and blanking off through a dconf default.
    - **The install run uses `-no-reboot`.** A reboot under `-kernel`/`-initrd` would re-enter the live ISO. After poweroff, a second QEMU run boots from the disk alone (no `-kernel`), finishes first boot, and powers off. That disk plus its vars file is the base.
  - **`provision-debian.sh`:** downloads and verifies the generic image. **It first runs `qemu-img resize` to 30G** (the cloud image's virtual disk is about 3 GB; cloud-init's growpart extends the root filesystem). It then boots with a NoCloud `CIDATA` seed (user `tester` with the same password, `openssh-server`, sudo).
    - `apt-get install task-gnome-desktop` with default recommends, then GDM autologin and initial setup off, then a shutdown.
    - The result is `debian-13-base.qcow2`.
  - **`vm.sh`:**
    - `up <distro> [--visible]`: a fresh overlay `qemu-img create -f qcow2 -b <base> -F qcow2`, started in a container `m32-vm-<distro>` with `--device /dev/kvm`, `-m 6144 -smp 4`, `-device virtio-vga`, `-device qemu-xhci -device usb-tablet`, user-mode networking with an SSH hostfwd, the container port published only on `127.0.0.1:<2290-2299>`, and a QMP UNIX socket in a bind-mounted run dir.
      - QEMU's SSH hostfwd listens on the container's interface (`hostfwd=tcp:0.0.0.0:22-:22`), and Docker publishes it only on `127.0.0.1`.
      - The display is fixed, so click coordinates are reproducible: `virtio-vga` with `xres=1280,yres=800` (or an EDID-fixed mode), the same on both guests. With no 3D, mutter uses software rendering; record it, since P5 depends on it.
      - `--visible` adds `-display gtk` with `DISPLAY=:0` and `/mnt/wslg/.X11-unix` mounted read-only. Default: `-display none`.
      - Disks use `discard=unmap`, so sparse files stay sparse.
    - `status`: running guest, ports, overlay.
    - `base-hash <distro> [--check]`: records or verifies the sha256 of the base image and its vars file.
    - `down <distro>`: QMP `quit`, `docker stop` by name, and the overlay deleted.
    - `ssh <distro> <cmd>`.
    - `session-env`: prints the exports for the logged-in session (`XDG_RUNTIME_DIR=/run/user/<uid>`, `WAYLAND_DISPLAY`, `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus`).
    - `copy-in <distro> <file> <dest>`.
  - **`qmp.py`:** a small QMP client.
    - `screendump <png>` with `format: png` (QEMU 7.1 or later; the image has 10.x).
    - `key <combo>` (`send-key`).
    - `type <text>` (key events per character).
    - `move <x> <y>`, `click [left|right|double]`: `input-send-event` with an `abs` event per axis (scaled 0-32767 from the fixed resolution), then `btn` down and up with a short delay. A double click is two press/release pairs within GNOME's double-click time.
    - `wait-for-screen <secs>`: waits until two dumps a second apart match **outside the top bar** (the clock changes), within a small pixel tolerance for the caret and cursor. It has a timeout and a non-zero exit code on timeout.
  - **`README.md`:** what each script does; the image URLs and pins; disk and RAM use; the safety rules; the test user's password, marked test-only; how to run a visible session for the walk.
- **`.gitignore`:** none needed if everything lives under `$HOME/the-one-m32-vm/`. Never put images in the repo.
- **Evidence** under `$HOME/the-one-m32-evidence/f2/leg4/`: screendumps and command outputs per premise.
- **A flight-log section,** `### vm-apparatus`.

## Acceptance Criteria
- [ ] **AC1 — runner image and helpers.**
  - `docker build -t m32/qemu packaging/linux/vm` succeeds from a pinned base digest.
  - `vm.sh up`/`down`, `ssh`, `session-env`, `copy-in`, and every `qmp.py` verb work against both guests. One evidence line per verb.
  - `shellcheck` from `$HOME/the-one-m32-build/tools/shellcheck-0.10.0/` passes on the scripts, and `ruff check`/`ruff format --check` on `qmp.py`.
- [ ] **AC2 — the Ubuntu 26.04 base.**
  - Provisioned unattended from the verified ISO.
  - After boot it autologs in to a GNOME session (screendump).
  - `snap list` shows the seeded snaps, including App Center (`snap-store` or its 26.04 name).
  - Record (not assert) whether `gir1.2-ayatanaappindicator3-0.1`, `libgirepository-2.0-0` and `libfuse2t64` are installed. These presences decide which fallback paths the real desktops exercise, and they are a finding, not a pass/fail.
  - `openssh-server` is the only addition beyond the default selection; recorded.
  - The base image is never written to after provisioning: every run uses an overlay, and the base's sha256 is recorded before the first run and checked at leg end.
- [ ] **AC3 — the Debian 13 base.**
  - Provisioned from the pinned generic image plus `task-gnome-desktop`.
  - Autologin to GNOME (screendump).
  - Record (not assert) whether `libgirepository-2.0-0` (for example through `python3-gi`), the Ayatana packages and `libfuse2t64` are installed. Flight 1's baselines were containers, not desktops.
  - `gnome-software`, its PackageKit plugin and the `packagekit` daemon package are installed (asserted).
  - Base sha256 recorded and checked, as for Ubuntu.
- [ ] **AC4 — act and observe work on a Wayland GNOME session**, on both guests:
  - QMP keystrokes open Activities and type a search;
  - an absolute click lands where aimed (open an app from the grid);
  - a screendump shows the result;
  - `loginctl show-session` over SSH reports `Type=wayland`.
- [ ] **AC5 — the install-side premises, each answered with evidence** (screendumps at every dialog, plus SSH reads):

  | # | premise | how | answer recorded |
  |---|---|---|---|
  | P1 | double-click installs a local `.deb` without a terminal | in Files: `~/Downloads/gleepglorp-ai_0.11.8_amd64.deb`, then double-click; App Center (Ubuntu) or GNOME Software (Debian); Install; the polkit password typed by QMP | `dpkg -s gleepglorp-ai` → installed, 0.11.8 |
  | P2 | the same path upgrades to a newer local `.deb` | double-click `…0.11.9~dev1…deb`; the software centre offers Install or Update | version 0.11.9~dev1 |
  | P3 | the software centre lists the installed package and removes it | search or "Installed"; Remove | `dpkg -s` → not installed; record whether the package appears at all (AppStream metainfo question) |
  | P4 | Files runs an executable AppImage (in a **fresh overlay**, so the P1-P2 `.deb` install cannot share its data dir or menu entries) | Files → Properties → "Executable as Program"; double-click; over SSH record `ldconfig -p | grep libfuse.so.2`, `command -v fusermount3`, and the AppImage's stderr | the app's server answers `/api/live` inside the guest, and a window or browser appears (screendump); or what Files shows when FUSE is missing |
  | P5 | WebKitGTK renders with no GPU | the P1 `.deb` launched from the app grid | the screendump shows the Chats start page ("Hello."), not a blank window |
  | P6 | the sandbox under each distro's policy | over SSH, in the session env: `sysctl kernel.apparmor_restrict_unprivileged_userns` (Ubuntu), `bwrap --unshare-user --ro-bind / / true; echo $?`, and `ps` for WebKit's `bwrap`-wrapped web process | values recorded; no pass/fail |

  - **P1 is a divert criterion** (Adaptation Criteria): if a stock desktop cannot install the local `.deb` without a terminal, stop and emit `[BLOCKED:divert-deb-install]` with the evidence. Only after one retry, once `snap changes` (Ubuntu) or PackageKit has gone quiet.
  - The `.deb` pulls its dependencies from the distro mirrors during P1 and P2. A mirror or network failure is environmental: retry it, and record it as such, not as a product result.
  - **P2 and P3 are recorded as answered either way.** A "no" sets up leg 7's AppStream metainfo work (DD9 premise table). Retry P3 with metainfo in leg 11 before any divert.
  - **P4 and P5 failures** are recorded, with what fallback the guide would need. They are not diverts in this leg.
- [ ] **AC6 — safety and resources.**
  - Only `m32-vm-*`/`m32/qemu` containers, run as the invoking uid; no `--privileged`, no `--network host`; only `/dev/kvm` passed through.
  - `find $HOME/the-one-m32-vm -not -user "$(id -u)"` is empty.
  - Published ports are on `127.0.0.1` only.
  - One guest at a time: `free -g` is checked before each `up` (at least 8 GB available), and peak RAM is sampled with `docker stats --no-stream` during each run.
  - Nothing this leg started listened on 8484 or 8485 on the host.
  - Nothing this leg ran wrote to the operator data dir (`/home/cprch/.local/share/the-one`). Its newest mtime is recorded at leg start and end. A change while the operator's own app is running is not this leg's, so note it but don't fail on it.
  - No container left running at leg end.
  - Everything large lives under `$HOME/the-one-m32-vm/`, with total disk use recorded.
  - `git status --porcelain -- packaging/linux/vm` shows only this leg's files. Other legs are editing other paths concurrently.

## Verification Steps
- AC1: the build log; one invocation per helper verb; the `shellcheck` and `ruff` output.
- AC2/AC3: provisioning logs, `snap list`/`dpkg -l` output, screendumps, the sha256 lines.
- AC4: screendumps before and after; `loginctl` output.
- AC5: the evidence folder per premise; the answer table in the flight log.
- AC6: `docker ps -a --filter name=m32-`, `free -g` samples, `du -sh $HOME/the-one-m32-vm`.

## Implementation Guidance
1. **Download and verify both images first;** they are large. Record URLs, sizes and checksums.
2. **The Ubuntu autoinstall is the riskiest part.**
   - The 24.04+ desktop ISO installer (`ubuntu-desktop-bootstrap`/subiquity) honours `autoinstall` on the kernel command line, with a NoCloud seed (`ds=nocloud;s=/cdrom/…` or a `CIDATA`-labelled ISO).
   - Boot the ISO by extracting `casper/vmlinuz` and `casper/initrd` (`xorriso -osirrox on` or `7z`), then QEMU `-kernel`/`-initrd`/`-append "… autoinstall ds=nocloud …"` with the ISO as `-cdrom` and the seed ISO as a second drive.
   - Run headless, watching screendumps for progress. Expect one or two iterations, and record each in the flight log.
   - If autoinstall cannot be made to work in reasonable time (about 2 hours of attempts), stop and emit `[BLOCKED:ubuntu-autoinstall]` with what was tried. The Flight Director goes back to the operator, whose alternative was the cloud image plus seeded snaps, logged as a deviation.
3. **GDM autologin:** `/etc/gdm3/custom.conf` (`[daemon] AutomaticLoginEnable=true`, `AutomaticLogin=tester`) on both. gnome-initial-setup off: `~tester/.config/gnome-initial-setup-done` containing `yes`. Screen lock and blanking off for the test user, by `gsettings` through the session or by a dconf profile, so screendumps don't go black. All recorded as apparatus settings, not product.
4. **Snapshot discipline:** the base images are read-only after provisioning (`chmod a-w`). Every `up` makes a new overlay.
5. **Then the premises (phase C), in this order:** P1, P5 (on the `.deb` P1 installed), P2, P3, then a fresh overlay for P4, then P6. Ubuntu first, then Debian.
6. **Flight-log section:** the image pins, the provisioning iterations, the AC5 answer table, resource numbers, and anything leg 6 or leg 11 must know (screen coordinates of common targets are not stable, so prefer keyboard paths: Super, then type, then Enter; Files' Ctrl+L, then a path, then Enter).

## Edge Cases
- **The App Center may refuse local `.deb` files, or need a confirmation for an "unverified" package.** Record exactly what it shows. That is the evidence P1 exists to produce.
- **The polkit dialog** may appear on a secure surface where the typed password is still accepted by QMP keys. Verify by result, not by screendump alone.
- **Snap refreshes on first boot** may hold App Center busy. Wait for `snap changes` to settle before P1 (`snap watch --last=auto-refresh` or polling), and record the wait.
- **GNOME's "Software" may need its first-run setup.** Note that as stock behaviour.
- **QEMU `-display gtk` under WSLg** may fail. `--visible` is optional for this leg; the closing walk needs it. Record whether it works, and print the exact QEMU command line for both guests in the README, so the walk is reproducible.
- **GNOME pointer handling on Wayland:** absolute `usb-tablet` events should land exactly. If they don't, prefer the keyboard paths, and record it.
- **Nested virtualisation performance:** a slow guest is fine. Use generous waits, polled by screen stability rather than fixed sleeps.

## Files Affected
- `packaging/linux/vm/Dockerfile`, `provision-ubuntu.sh`, `provision-debian.sh`, `vm.sh`, `qmp.py`, `README.md`, the autoinstall and cloud-init templates (all new)
- `missions/32-installers-everywhere/flights/02-linux-packages/flight-log.md` (own section only)

## Citation Audit
Checked at `980415e`:
- No `packaging/linux/vm/` exists yet. Verified.
- Flight 1 packages present under `$HOME/the-one-m32-build/packages/`: four files plus `SHA256SUMS`. Verified.
- Image URLs and checksums above: fetched 2026-10-24. Verified.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
