# Fresh-VM apparatus (Mission 32, Flight 2, DD9)

Stock Ubuntu 26.04 and Debian 13 GNOME guests run by QEMU/KVM inside a Docker
container, provisioned once into read-only base images and reused through fresh
qcow2 overlays. Scripts here are apparatus, not product. Nothing is installed on the
host; everything large lives under `$M32_VM` (default `$HOME/the-one-m32-vm`).

## Files

| file | what it does |
|---|---|
| `Dockerfile` | the runner image `m32/qemu` (`docker build -t m32/qemu packaging/linux/vm`), from a pinned `debian:13` digest: qemu-system-x86, qemu-system-gui, qemu-utils, ovmf, openssh-client, python3, xorriso, genisoimage |
| `lib.sh` | shared helpers (sourced) |
| `provision-debian.sh` | verifies the pinned generic cloud image, resizes it to 30G, boots it once with a NoCloud `CIDATA` seed (`debian-user-data.in`) that installs `task-gnome-desktop`, GDM autologin, dconf defaults (no lock/blank/suspend), then powers off |
| `provision-ubuntu.sh` | verifies the 26.04.1 desktop ISO, pulls `casper/vmlinuz` and `initrd` out of it, runs the installer unattended (direct kernel boot, `autoinstall` on the command line, a `CIDATA` seed ISO carrying `ubuntu-user-data.in` as `user-data` plus an empty `meta-data`, `-no-reboot`), then a disk-only first boot that waits for SSH and snap seeding and powers off |
| `ubuntu-user-data.in` | the `#cloud-config` with the installer config under `autoinstall:` (written against the schema in the installer snap `ubuntu-desktop-bootstrap` 665): source `ubuntu-desktop-minimal` (the installer's default selection), user `tester`, `ssh: install-server`, `refresh-installer: update: false`, `shutdown: poweroff`, late-commands for GDM autologin, first-run wizards off, passwordless sudo and no lock/blank/suspend |
| `vm.sh` | `up <distro> [--visible]`, `down`, `status`, `base-hash <distro> [--check]`, `ssh <distro> <cmd>`, `session-env <distro>`, `copy-in <distro> <file> <dest>`, `prep <distro>` |
| `qmp.py` | QMP client: `screendump <png>`, `key <combo>`, `type <text>`, `move <x> <y>`, `click [left\|right\|double]`, `wait-for-screen <secs>`, `raw <cmd> [json]`; `-d <distro>` picks the socket |

## Pins

- Runner base: `debian@sha256:4c25275446ca371766b8b093c696782eabce06263fccacb8d5d813b3dc44b308` (QEMU 10.0.13).
- Debian: `https://cloud.debian.org/images/cloud/trixie/20261021-2638/debian-13-generic-amd64-20261021-2638.qcow2`, sha512 `70ef6adc...ead5f0` (full value in `provision-debian.sh`), 438,566,912 bytes.
- Ubuntu: `https://releases.ubuntu.com/26.04/ubuntu-26.04.1-desktop-amd64.iso`, sha256 `601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f` (26.04.1, the point release, chosen over 26.04's `487f87fa...`), 6,482,409,472 bytes.

## Layout, firmware, display

- UEFI for both guests: read-only `OVMF_CODE_4M.fd` from the image, plus a per-base writable `<base>.vars.fd`, hashed and made read-only with the base; each run copies it into its own run dir.
- Run dir `$M32_VM/run/<distro>/` holds `overlay.qcow2`, `vars.fd` and `qmp.sock`, and is mounted at `/run/vm` in the container. `$M32_VM` is mounted read-only at `/vm`. `down` deletes the run dir.
- Display: `virtio-vga` fixed at 1280x800, no 3D (mutter renders in software), `usb-tablet` absolute pointer; `qmp.py` scales to the 0-32767 range from that size. Clicks land exactly where aimed.
- Guests: 6144 MB RAM, 4 vCPU, `-cpu host`, user-mode networking; guest SSH is QEMU hostfwd `0.0.0.0:22` inside the container, published only on `127.0.0.1:2291` (debian), `2292` (ubuntu); `2290` is provisioning (both provision scripts).
- SSH uses a throwaway ed25519 key `$M32_VM/id_m32` (installed through cloud-init / autoinstall); no password needed for SSH.

## Resources

Base image sizes (sparse files): Debian base about 5.9 GB used, 30 GB virtual. The Ubuntu base is a 40 GB sparse qcow2 (installer provisioning takes about 15 min for the install run plus a few minutes of first boot). A running guest is about 2.6 GB of container RAM at the idle desktop and an overlay of a few hundred MB. `vm.sh up` refuses to start if another `m32-vm-*` container exists, and waits (up to 30 min) until 8 GB are available.

## Safety rules

- Only containers named `m32-vm-*` from image `m32/qemu`, run as the invoking uid with `--group-add` for `/dev/kvm`'s group; never `--privileged`, never `--network host`; only `/dev/kvm` is passed through; ports on `127.0.0.1` only (2290-2299).
- No root-owned files under `$M32_VM`; nothing installed on the host.
- Never port 8484/8485 on the host; never the operator data dir.
- Stop only recorded containers by exact name (`vm.sh down`).

## Test credentials (TEST ONLY)

Guest user `tester`, password `m32testpw` (lowercase alphanumeric, so `qmp.py type` needs no shift handling). It exists only inside throwaway guests and is also the sudo/polkit password (sudo is passwordless over SSH).

## Driving a guest

```bash
vm.sh up debian && vm.sh prep debian          # prep waits for SSH and the session bus
python3 qmp.py -d debian wait-for-screen 90
python3 qmp.py -d debian key esc              # first login shows the GNOME welcome dialog; esc again leaves the overview
python3 qmp.py -d debian key super; python3 qmp.py -d debian type files; python3 qmp.py -d debian key ret
python3 qmp.py -d debian screendump /path/shot.png
eval "$(vm.sh session-env debian)"            # or paste the three exports into an ssh command
vm.sh down debian
```

Prefer keyboard paths (Super, type, Enter; Files' Ctrl+L) over coordinates.

## Visible session (the closing walk, through WSLg)

`vm.sh up debian --visible` adds `-display gtk` with `DISPLAY=:0` and `/mnt/wslg/.X11-unix` mounted read-only. The exact command it runs (debian, rundir `$M32_VM/run/debian`):

```bash
docker run --name m32-vm-debian --user "$(id -u):$(id -g)" --group-add "$(stat -c %g /dev/kvm)" \
  --device /dev/kvm -p 127.0.0.1:2291:22 -v "$M32_VM:/vm:ro" -v "$M32_VM/run/debian:/run/vm" \
  --entrypoint qemu-system-x86_64 -d --rm -e DISPLAY=:0 -e HOME=/tmp -e XDG_CACHE_HOME=/tmp \
  -v /mnt/wslg/.X11-unix:/tmp/.X11-unix:ro m32/qemu \
  -machine q35,accel=kvm -cpu host -m 6144 -smp 4 \
  -drive if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,unit=1,file=/run/vm/vars.fd \
  -drive file=/run/vm/overlay.qcow2,if=virtio,format=qcow2,discard=unmap,cache=unsafe \
  -device virtio-vga,xres=1280,yres=800 -device qemu-xhci -device usb-tablet \
  -netdev user,id=n0,hostfwd=tcp:0.0.0.0:22-:22 -device virtio-net-pci,netdev=n0 \
  -qmp unix:/run/vm/qmp.sock,server=on,wait=off -name guest -display gtk
```

(The overlay is created first with `qemu-img create -f qcow2 -b /vm/debian-13-base.qcow2 -F qcow2`.)
