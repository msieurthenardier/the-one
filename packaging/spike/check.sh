#!/bin/bash
# Gate runner, host side (Mission 32 Flight 1 spike). Candidate-neutral.
# usage: check.sh <candidate> <format:deb|appimage> <distro:ubuntu-26.04|debian-13> <image:baseline|bare> \
#                 --pkgdir DIR --n VER --n1 VER [--evidence DIR] [--pkg-n FILE] [--pkg-n1 FILE]
# --pkg-n / --pkg-n1 name the package files for N and N+1 when a candidate's names differ from
# gleepglorp-ai_<ver>_amd64.deb / GleepGlorp_AI-<ver>-x86_64.AppImage (e.g. per-distro .debs).
# One disposable container per call (name m32-gate-...), non-root test user, no --privileged,
# no --network host. The display is WSLg's X socket; window runs only on `baseline`.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
CAND=$1 FORMAT=$2 DISTRO=$3 IMAGE=$4; shift 4
PKG="$HOME/the-one-m32-build/packages" VN="" VN1="" PKN="" PKN1="" EVR="${M32_EVIDENCE:-$HOME/the-one-m32-evidence}"
while [ $# -gt 0 ]; do case $1 in
  --pkgdir) PKG=$2; shift 2;; --n) VN=$2; shift 2;; --n1) VN1=$2; shift 2;; --evidence) EVR=$2; shift 2;;
  --pkg-n) PKN=$2; shift 2;; --pkg-n1) PKN1=$2; shift 2;;
  *) echo "unknown arg $1" >&2; exit 2;; esac; done
[ -n "$VN" ] && [ -n "$VN1" ] || { echo "need --n and --n1" >&2; exit 2; }
EV="$EVR/$CAND/$FORMAT/$DISTRO-$IMAGE"
rm -rf "$EV"; mkdir -p "$EV"
WINDOW=0; [ "$IMAGE" = baseline ] && WINDOW=1
NAME="m32-gate-$FORMAT-$DISTRO-$IMAGE"
ARGS=(--rm --name "$NAME" -v "$PKG:/packages:ro" -v "$EV:/evidence" -v "$HERE/inner.sh:/inner.sh:ro"
  -e FORMAT="$FORMAT" -e WINDOW="$WINDOW" -e PK=/packages -e EV=/evidence
  -e DEB_N="${PKN:-gleepglorp-ai_${VN}_amd64.deb}" -e DEB_N1="${PKN1:-gleepglorp-ai_${VN1/.dev/~dev}_amd64.deb}"
  -e APPIMG_N="${PKN:-GleepGlorp_AI-${VN}-x86_64.AppImage}" -e APPIMG_N1="${PKN1:-GleepGlorp_AI-${VN1}-x86_64.AppImage}")
[ "$WINDOW" = 1 ] && ARGS+=(-v /mnt/wslg/.X11-unix:/tmp/.X11-unix)
docker run "${ARGS[@]}" "m32/$DISTRO:$IMAGE" bash /inner.sh > "$EV/container.log" 2>&1 || echo "container rc=$?" >> "$EV/container.log"
[ -f "$EV/window.xwd" ] && "${PYTHON:-python3}" "$HERE/xwd2png.py" "$EV/window.xwd" "$EV/window.png" > "$EV/window-png.txt" 2>&1 || true
"${PYTHON:-python3}" "$HERE/score.py" "$EV" --format "$FORMAT" --distro "$DISTRO" --image "$IMAGE" --n "$VN" --n1 "$VN1"
