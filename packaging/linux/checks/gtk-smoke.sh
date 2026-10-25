#!/bin/bash
# Real-GTK smoke test of a built .deb (Mission 32 Flight 2 leg 3, DD12). Host side.
# usage: gtk-smoke.sh <ubuntu-26.04|debian-13> --deb FILE [--control | --takeover-from OLD.deb] [--evidence DIR]
# One disposable container m32-gtk-smoke-<distro>[-control]: non-root user, private Xvfb :99 (no
# window manager), no --privileged, no --network host. --control = the Flight 1 package, which has
# no state/quit routes: it only proves the harness can see the unmapped-window trap.
# --takeover-from OLD.deb = the version takeover (DD13): install and start OLD, upgrade to --deb over it,
# launch the new one and check whether it replaces OLD (a this-tree build) or only focuses it (Flight 1's).
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
DISTRO=${1:?distro}; shift
DEB="" OLD="" CONTROL=0 EVR="$HOME/the-one-m32-evidence/f2/leg3"
while [ $# -gt 0 ]; do case $1 in
  --deb) DEB=$2; shift 2;; --control) CONTROL=1; shift;; --takeover-from) OLD=$2; shift 2;; --evidence) EVR=$2; shift 2;;
  *) echo "unknown arg $1" >&2; exit 2;; esac; done
[ -f "$DEB" ] || { echo "need --deb FILE" >&2; exit 2; }
SUFFIX=""; [ "$CONTROL" = 1 ] && SUFFIX="-control"
if [ -n "$OLD" ]; then
  [ -f "$OLD" ] || { echo "need --takeover-from FILE" >&2; exit 2; }
  SUFFIX="-takeover-$(basename "$OLD" .deb | tr -c 'A-Za-z0-9.\n' '_')"
fi
EV="$EVR/$DISTRO$SUFFIX"
rm -rf "$EV"; mkdir -p "$EV"; chmod 777 "$EV"
NAME="m32-gtk-smoke-$DISTRO$SUFFIX"
docker rm -f "$NAME" > /dev/null 2>&1 || true
docker run --rm --name "$NAME" \
  -v "$(dirname "$DEB"):/packages:ro" -v "$(dirname "${OLD:-$DEB}"):/packages-old:ro" -v "$EV:/evidence" -v "$HERE/gtk-smoke-inner.sh:/inner.sh:ro" \
  -e DEB="$(basename "$DEB")" -e OLD="${OLD:+$(basename "$OLD")}" -e CONTROL="$CONTROL" -e EV=/evidence \
  "m32/$DISTRO:baseline" bash /inner.sh > "$EV/container.log" 2>&1 || echo "container rc=$?" >> "$EV/container.log"
cat "$EV/result.txt" 2>/dev/null || { echo "no result.txt; see $EV/container.log"; exit 1; }
grep -q '^OVERALL PASS' "$EV/result.txt"
