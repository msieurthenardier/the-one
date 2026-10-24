#!/usr/bin/env bash
# Mission 32 fresh-VM apparatus driver. See README.md.
#   vm.sh up <distro> [--visible] | status | base-hash <distro> [--check] | down <distro>
#   vm.sh ssh <distro> <cmd...> | session-env <distro> | copy-in <distro> <file> <dest> | prep <distro>
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "$0")/lib.sh"

run_dir() { echo "$M32_VM/run/$1"; }
cname() { echo "m32-vm-$1"; }
base_name() {
  case "$1" in
    debian) echo debian-13-base ;;
    ubuntu) echo ubuntu-26.04-base ;;
    *) die "unknown distro '$1' (debian|ubuntu)" ;;
  esac
}

cmd_up() {
  local distro=$1 visible=0
  shift
  [ "${1:-}" = "--visible" ] && visible=1
  local base port rd name
  base=$(base_name "$distro"); port=$(port_for "$distro"); rd=$(run_dir "$distro"); name=$(cname "$distro")
  [ -f "$M32_VM/$base.qcow2" ] || die "no base image $M32_VM/$base.qcow2 (run provision-$distro.sh)"
  if [ -n "$(docker ps -aq --filter name=m32-vm-)" ]; then
    docker ps -a --filter name=m32-vm- --format 'already present: {{.Names}}' >&2
    die "one guest at a time: run 'vm.sh down' on the existing one first"
  fi
  wait_available_ram 8
  rm -rf "$rd"; mkdir -p "$rd"
  ensure_dirs_key
  qemu_img create -q -f qcow2 -b "/vm/$base.qcow2" -F qcow2 "/vm/run/$distro/overlay.qcow2"
  cp "$M32_VM/$base.vars.fd" "$rd/vars.fd"; chmod u+w "$rd/vars.fd"
  qemu_base_args /run/vm/overlay.qcow2 /run/vm/vars.fd
  docker_qemu "$name" "$port" "$rd" ro "$visible" 1 -- "${QEMU_ARGS[@]}" >/dev/null
  echo "$distro up: container $name, ssh 127.0.0.1:$port, overlay $rd/overlay.qcow2"
}

cmd_down() {
  local distro=$1 name rd
  name=$(cname "$distro"); rd=$(run_dir "$distro")
  if [ -S "$rd/qmp.sock" ]; then
    python3 "$HERE/qmp.py" --sock "$rd/qmp.sock" raw quit >/dev/null 2>&1 || true
    sleep 1
  fi
  docker stop -t 5 "$name" >/dev/null 2>&1 || true
  docker rm -f "$name" >/dev/null 2>&1 || true
  rm -rf "$rd"
  echo "$distro down"
}

cmd_status() {
  docker ps -a --filter name=m32- --format 'container {{.Names}}  {{.Status}}  {{.Ports}}'
  local d
  for d in debian ubuntu; do
    [ -f "$(run_dir "$d")/overlay.qcow2" ] && ls -l "$(run_dir "$d")/overlay.qcow2"
  done
  return 0
}

cmd_base_hash() {
  local distro=$1 check=${2:-} base
  base=$(base_name "$distro")
  if [ "$check" = "--check" ]; then
    (cd "$M32_VM" && sha256sum -c "$base.sha256")
  else
    (cd "$M32_VM" && sha256sum "$base.qcow2" "$base.vars.fd" | tee "$base.sha256")
  fi
}

cmd_ssh() {
  local distro=$1
  shift
  ssh "${SSH_OPTS[@]}" -p "$(port_for "$distro")" "$VM_USER@127.0.0.1" "$@"
}

cmd_session_env() {
  local distro=$1 uid
  uid=$(cmd_ssh "$distro" id -u)
  echo "export XDG_RUNTIME_DIR=/run/user/$uid"
  echo "export WAYLAND_DISPLAY=wayland-0"
  echo "export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus"
}

cmd_copy_in() {
  local distro=$1 file=$2 dest=$3
  scp "${SSH_OPTS[@]}" -P "$(port_for "$distro")" "$file" "$VM_USER@127.0.0.1:$dest"
}

# prep: wait until SSH and the user session bus are up (the guest is ready to drive).
# The GNOME welcome dialog ("Skip" / "Take Tour") is stock first-login behaviour and
# shows once per overlay: dismiss it with `qmp.py -d <distro> key esc`.
cmd_prep() {
  local distro=$1 n
  for n in $(seq 1 60); do
    cmd_ssh "$distro" true 2>/dev/null && break
    sleep 5
  done
  for n in $(seq 1 60); do
    cmd_ssh "$distro" "test -S /run/user/\$(id -u)/bus" 2>/dev/null && break
    sleep 5
  done
  [ "$n" -lt 60 ] || die "$distro: session bus never appeared"
  echo "$distro ready"
}

verb=${1:-}
[ -n "$verb" ] || { sed -n '2,5p' "$0"; exit 2; }
shift
case "$verb" in
  up) cmd_up "$@" ;;
  down) cmd_down "$@" ;;
  status) cmd_status ;;
  base-hash) cmd_base_hash "$@" ;;
  ssh) cmd_ssh "$@" ;;
  session-env) cmd_session_env "$@" ;;
  copy-in) cmd_copy_in "$@" ;;
  prep) cmd_prep "$@" ;;
  *) die "unknown verb '$verb'" ;;
esac
