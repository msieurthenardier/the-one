#!/usr/bin/env bash
# Provision the Ubuntu 26.04.1 desktop base by unattended autoinstall (NoCloud CIDATA seed).
# Output: $M32_VM/ubuntu-26.04-base.qcow2 and ubuntu-26.04-base.vars.fd (both made read-only).
# Two QEMU runs: (1) install from the ISO via direct kernel boot, -no-reboot, the installer powers
# off; (2) disk-only first boot (no -kernel), wait for SSH and snap seeding, power off.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "$0")/lib.sh"

ISO_URL=https://releases.ubuntu.com/26.04/ubuntu-26.04.1-desktop-amd64.iso
ISO_FILE=ubuntu-26.04.1-desktop-amd64.iso
ISO_SHA256=601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f
BASE=ubuntu-26.04-base
SOURCE_ID=${UBUNTU_SOURCE_ID:-ubuntu-desktop-minimal}
INSTALL_TIMEOUT=${INSTALL_TIMEOUT:-5400}
BOOT_TIMEOUT=${BOOT_TIMEOUT:-1200}
NAME=m32-vm-provision-ubuntu

ensure_dirs_key
[ -e "$M32_VM/$BASE.qcow2" ] && die "$BASE.qcow2 exists; remove it deliberately to re-provision"
mkdir -p "$M32_VM/dl"
if ! echo "$ISO_SHA256  $M32_VM/dl/$ISO_FILE" | sha256sum -c - >/dev/null 2>&1; then
  curl -sSfL -o "$M32_VM/dl/$ISO_FILE" "$ISO_URL"
  echo "$ISO_SHA256  $M32_VM/dl/$ISO_FILE" | sha256sum -c -
fi
wait_available_ram 8

RUN="$M32_VM/run/provision-ubuntu"
rm -rf "$RUN"; mkdir -p "$RUN/seed"
in_image xorriso -osirrox on -indev "/vm/dl/$ISO_FILE" \
  -extract /casper/vmlinuz /vm/run/provision-ubuntu/vmlinuz \
  -extract /casper/initrd /vm/run/provision-ubuntu/initrd >/dev/null 2>&1
chmod u+w "$RUN/vmlinuz" "$RUN/initrd"

PWHASH=$(openssl passwd -6 "$VM_PASSWORD")
PUBKEY=$(cat "$VM_KEY.pub")
touch "$RUN/seed/meta-data"
sed -e "s|@PUBKEY@|$PUBKEY|" -e "s|@USER@|$VM_USER|g" -e "s|@SOURCE_ID@|$SOURCE_ID|" \
  -e "s|@PWHASH@|$(printf '%s' "$PWHASH" | sed 's/[|&\\]/\\&/g')|" \
  "$HERE/ubuntu-user-data.in" >"$RUN/seed/user-data"
make_seed "/vm/run/provision-ubuntu/seed" /vm/run/provision-ubuntu/seed.iso

qemu_img create -q -f qcow2 "/vm/$BASE.qcow2" 40G
docker run --rm --user "$(id -u):$(id -g)" -v "$M32_VM:/vm" --entrypoint cp "$M32_IMAGE" \
  "$OVMF_VARS_TEMPLATE" "/vm/$BASE.vars.fd"
chmod u+w "$M32_VM/$BASE.vars.fd"

run_qemu() { # run_qemu <timeout> <extra qemu args...>; waits for container exit or times out
  local limit=$1
  shift
  qemu_base_args "/vm/$BASE.qcow2" "/vm/$BASE.vars.fd"
  docker_qemu "$NAME" "$(port_for provision)" "$RUN" rw 0 0 -- "${QEMU_ARGS[@]}" "$@" &
  local qpid=$!
  SECONDS=0
  while kill -0 "$qpid" 2>/dev/null; do
    if [ "$SECONDS" -ge "$limit" ]; then
      docker stop "$NAME" >/dev/null || true
      die "timed out after ${limit}s"
    fi
    sleep 20
  done
  wait "$qpid" || true
}

echo "install run: autoinstall from $ISO_FILE (source $SOURCE_ID); max ${INSTALL_TIMEOUT}s"
# The seed rides as a read-only virtio disk; the CIDATA label is what cloud-init matches.
run_qemu "$INSTALL_TIMEOUT" -no-reboot \
  -drive "file=/vm/dl/$ISO_FILE,media=cdrom,readonly=on,format=raw" \
  -drive "file=/run/vm/seed.iso,if=virtio,format=raw,readonly=on" \
  -kernel /run/vm/vmlinuz -initrd /run/vm/initrd -append "autoinstall quiet ---"
echo "install run finished after ${SECONDS}s"

echo "first boot (disk only): wait for SSH + snap seeding, then power off; max ${BOOT_TIMEOUT}s"
(
  for _ in $(seq 1 $((BOOT_TIMEOUT / 10))); do
    if ssh "${SSH_OPTS[@]}" -p "$(port_for provision)" "$VM_USER@127.0.0.1" \
      'sudo snap wait system seed.loaded && test -S /run/user/$(id -u)/bus' 2>/dev/null; then
      sleep 60 # let the first GNOME session settle
      ssh "${SSH_OPTS[@]}" -p "$(port_for provision)" "$VM_USER@127.0.0.1" 'sudo sync; sudo poweroff' || true
      exit 0
    fi
    sleep 10
  done
) &
run_qemu "$BOOT_TIMEOUT" -no-reboot
wait || true
chmod a-w "$M32_VM/$BASE.qcow2" "$M32_VM/$BASE.vars.fd"
"$HERE/vm.sh" base-hash ubuntu
echo "Ubuntu base ready"
