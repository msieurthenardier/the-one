#!/usr/bin/env bash
# Run the Mission 32 gate runner over B's per-distro .debs (spike tooling, candidate B).
#   packaging/briefcase/run-gates.sh <label> [N] [N1]      e.g. B-unpatched
# Evidence goes to $M32_EVIDENCE/<label>/deb/<distro>-<image>/ ; one score line per run.
set -u
LABEL="${1:?usage: run-gates.sh <label> [N] [N1]}"; N="${2:-0.11.8}"; N1="${3:-0.11.9.dev1}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="${M32_PKGDIR:-$HOME/the-one-m32-build/packages-briefcase}"
export PYTHON="${PYTHON:-$HERE/../../.venv/bin/python}"
for spec in "ubuntu-26.04 ubuntu-resolute" "debian-13 debian-trixie"; do
  set -- $spec; DISTRO=$1; TAG=$2
  for IMAGE in ${M32_IMAGES:-baseline bare}; do
    bash "$HERE/../spike/check.sh" "$LABEL" deb "$DISTRO" "$IMAGE" --pkgdir "$PKG" --n "$N" --n1 "$N1" \
      --pkg-n "the-one_${N}-1~${TAG}_amd64.deb" --pkg-n1 "the-one_${N1}-1~${TAG}_amd64.deb"
  done
done
