#!/usr/bin/env bash
# Shared helpers for the Mission 32 VM apparatus (sourced, not run).
# shellcheck shell=bash disable=SC2034,SC2054

M32_VM="${M32_VM:-$HOME/the-one-m32-vm}"
M32_IMAGE="${M32_IMAGE:-m32/qemu}"
VM_USER=tester
# TEST-ONLY guest password (lowercase alphanumeric so `qmp.py type` needs no shift).
VM_PASSWORD=m32testpw
VM_KEY="$M32_VM/id_m32"
SSH_OPTS=(-i "$VM_KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
  -o LogLevel=ERROR -o ConnectTimeout=5 -o BatchMode=yes -o IdentitiesOnly=yes)
OVMF_CODE=/usr/share/OVMF/OVMF_CODE_4M.fd
OVMF_VARS_TEMPLATE=/usr/share/OVMF/OVMF_VARS_4M.fd
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() { echo "error: $*" >&2; exit 1; }

port_for() {
  case "$1" in
    provision) echo 2290 ;;
    debian) echo 2291 ;;
    ubuntu) echo 2292 ;;
    *) die "unknown distro '$1' (debian|ubuntu)" ;;
  esac
}

ensure_dirs_key() {
  mkdir -p "$M32_VM/run"
  if [ ! -f "$VM_KEY" ]; then
    ssh-keygen -q -t ed25519 -N '' -C m32-vm-test -f "$VM_KEY"
  fi
}

# qemu_img <args...>: run qemu-img through the runner image (non-root, /vm = $M32_VM rw).
qemu_img() {
  docker run --rm --user "$(id -u):$(id -g)" -v "$M32_VM:/vm" --entrypoint qemu-img "$M32_IMAGE" "$@"
}

# in_image <cmd...>: run an arbitrary tool from the runner image against /vm.
in_image() {
  docker run --rm --user "$(id -u):$(id -g)" -v "$M32_VM:/vm" -w /vm --entrypoint "$1" "$M32_IMAGE" "${@:2}"
}

# Fixed-resolution virtio-vga, tablet pointer, user-mode net with an SSH hostfwd.
# qemu_base_args <disk-container-path> <vars-container-path>
qemu_base_args() {
  QEMU_ARGS=(
    -machine q35,accel=kvm -cpu host -m "${M32_RAM:-6144}" -smp "${M32_SMP:-4}"
    -drive "if=pflash,format=raw,unit=0,readonly=on,file=$OVMF_CODE"
    -drive "if=pflash,format=raw,unit=1,file=$2"
    -drive "file=$1,if=virtio,format=qcow2,discard=unmap,cache=unsafe"
    -device "virtio-vga,xres=1280,yres=800"
    -device qemu-xhci -device usb-tablet
    -netdev "user,id=n0,hostfwd=tcp:0.0.0.0:22-:22"
    -device virtio-net-pci,netdev=n0
    -qmp unix:/run/vm/qmp.sock,server=on,wait=off
    -name guest
  )
}

# docker_qemu <container-name> <host-port> <run-dir> <vm-mount-mode ro|rw> <visible 0|1> <detach 0|1> -- <qemu args...>
docker_qemu() {
  local name=$1 port=$2 rundir=$3 mode=$4 visible=$5 detach=$6
  shift 7
  local -a d=(docker run --name "$name" --user "$(id -u):$(id -g)"
    --group-add "$(stat -c %g /dev/kvm)" --device /dev/kvm
    -p "127.0.0.1:$port:22"
    -v "$M32_VM:/vm:$mode" -v "$rundir:/run/vm" --entrypoint qemu-system-x86_64)
  [ "$detach" = 1 ] && d+=(-d --rm) || d+=(--rm)
  if [ "$visible" = 1 ]; then
    d+=(-e DISPLAY=:0 -e HOME=/tmp -e XDG_CACHE_HOME=/tmp -v /mnt/wslg/.X11-unix:/tmp/.X11-unix:ro)
    set -- "$@" -display gtk
  else
    set -- "$@" -display none
  fi
  "${d[@]}" "$M32_IMAGE" "$@"
}

wait_available_ram() {
  local need=${1:-8} waited=0
  while :; do
    local avail
    avail=$(free -g | awk '/^Mem:/{print $7}')
    if [ "$avail" -ge "$need" ]; then
      [ "$waited" -gt 0 ] && echo "RAM wait: ${waited}s, now ${avail} GB available"
      return 0
    fi
    [ "$waited" -ge 1800 ] && die "only ${avail} GB available after 30 min"
    echo "waiting for RAM: ${avail} GB < ${need} GB"
    sleep 60
    waited=$((waited + 60))
  done
}

make_seed() { # make_seed <dir-with-user-data+meta-data> <out.iso>
  in_image genisoimage -quiet -output "$2" -volid CIDATA -joliet -rock "$1/user-data" "$1/meta-data"
}
