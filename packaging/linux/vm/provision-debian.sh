#!/usr/bin/env bash
# Provision the Debian 13 GNOME base: pinned generic cloud image + task-gnome-desktop.
# Output: $M32_VM/debian-13-base.qcow2 and debian-13-base.vars.fd (both made read-only).
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "$0")/lib.sh"

DEB_DIR=https://cloud.debian.org/images/cloud/trixie/20261021-2638
DEB_FILE=debian-13-generic-amd64-20261021-2638.qcow2
DEB_SHA512=70ef6adc1c16155f8d575731b37d0f976d1c60b6144ac3f57914a3f4b30b202b69584d5d143aa39da0f0fe81df9e5b698909c0d94c7d91c6f6c4bb6581ead5f0
BASE=debian-13-base
TIMEOUT_S=${PROVISION_TIMEOUT:-3000}

ensure_dirs_key
[ -e "$M32_VM/$BASE.qcow2" ] && die "$BASE.qcow2 exists; remove it deliberately to re-provision"
mkdir -p "$M32_VM/dl"
if ! echo "$DEB_SHA512  $M32_VM/dl/$DEB_FILE" | sha512sum -c - >/dev/null 2>&1; then
  curl -sSfL -o "$M32_VM/dl/$DEB_FILE" "$DEB_DIR/$DEB_FILE"
  echo "$DEB_SHA512  $M32_VM/dl/$DEB_FILE" | sha512sum -c -
fi
wait_available_ram 8

RUN="$M32_VM/run/provision-debian"
rm -rf "$RUN"; mkdir -p "$RUN/seed"
cp "$M32_VM/dl/$DEB_FILE" "$M32_VM/$BASE.qcow2"
chmod u+w "$M32_VM/$BASE.qcow2"
qemu_img resize "/vm/$BASE.qcow2" 30G
docker run --rm --user "$(id -u):$(id -g)" -v "$M32_VM:/vm" --entrypoint cp "$M32_IMAGE" \
  "$OVMF_VARS_TEMPLATE" "/vm/$BASE.vars.fd"

PUBKEY=$(cat "$VM_KEY.pub")
cat >"$RUN/seed/meta-data" <<META
instance-id: m32-debian-provision
local-hostname: m32-debian
META
sed -e "s|@PUBKEY@|$PUBKEY|" -e "s|@PASSWORD@|$VM_PASSWORD|" -e "s|@USER@|$VM_USER|" \
  "$HERE/debian-user-data.in" >"$RUN/seed/user-data"
make_seed "/vm/run/provision-debian/seed" /vm/run/provision-debian/seed.iso

qemu_base_args "/vm/$BASE.qcow2" "/vm/$BASE.vars.fd"
echo "provisioning Debian (first boot installs task-gnome-desktop, then powers off; max ${TIMEOUT_S}s)"
docker_qemu m32-vm-provision-debian "$(port_for provision)" "$RUN" rw 0 0 -- \
  "${QEMU_ARGS[@]}" -no-reboot -cdrom /run/vm/seed.iso &
QPID=$!
SECONDS=0
while kill -0 "$QPID" 2>/dev/null; do
  if [ "$SECONDS" -ge "$TIMEOUT_S" ]; then
    docker stop m32-vm-provision-debian >/dev/null || true
    die "provisioning timed out"
  fi
  sleep 20
done
wait "$QPID" || true
chmod a-w "$M32_VM/$BASE.qcow2" "$M32_VM/$BASE.vars.fd"
"$HERE/vm.sh" base-hash debian
echo "Debian base ready in ${SECONDS}s"
