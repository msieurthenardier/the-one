#!/bin/bash
# Gate runner, host side: the container gate suite for a built package (DD8).
# usage: gates.sh <candidate> <format:deb|appimage> <distro:ubuntu-26.04|debian-13> <image:baseline|bare> \
#                 --pkgdir DIR --n VER --n1 VER [--evidence DIR] [--pkg-n FILE] [--pkg-n1 FILE]
#                 [--env K=V]... [--variant NAME] [--extra-apt "pkgs"] [--display wslg|xvfb]
# --display wslg mounts WSLg's X socket; xvfb starts a private Xvfb :99 in the container (the
# hosted runner path). Default: wslg when /mnt/wslg/.X11-unix/X0 exists, else xvfb.
# --env K=V (repeatable) adds K=V to the window run's environment (gates-inner.sh uses env -i), e.g.
# THE_ONE_PKG_DEBUG=1, THE_ONE_PKG_FORCE_FALLBACK=1, LD_BIND_NOW=1; THE_ONE_PKG_ABI_PROBE=1 runs the ABI probe only.
# --variant NAME only changes the evidence subdir (<distro>-<image>-NAME); --extra-apt installs
# packages in the container before the run (IMAGE stays baseline/bare, so every check still runs).
# --pkg-n / --pkg-n1 name the package files for N and N+1 when a candidate's names differ from
# gleepglorp-ai_<ver>_amd64.deb / GleepGlorp_AI-<ver>-x86_64.AppImage (e.g. per-distro .debs).
# One disposable container per call (name m32-gate-...), non-root test user, no --privileged,
# no --network host. Window runs only on `baseline`.
# shellcheck disable=SC2015
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
CAND=$1 FORMAT=$2 DISTRO=$3 IMAGE=$4; shift 4
PKG="$HOME/the-one-m32-build/packages" VN="" VN1="" PKN="" PKN1="" WX="" DISP="" VARIANT="" XAPT="" EVR="${M32_EVIDENCE:-$HOME/the-one-m32-evidence}"
while [ $# -gt 0 ]; do case $1 in
  --pkgdir) PKG=$2; shift 2;; --n) VN=$2; shift 2;; --n1) VN1=$2; shift 2;; --evidence) EVR=$2; shift 2;;
  --pkg-n) PKN=$2; shift 2;; --pkg-n1) PKN1=$2; shift 2;;
  --env) WX="$WX $2"; shift 2;; --variant) VARIANT=$2; shift 2;; --display) DISP=$2; shift 2;; --extra-apt) XAPT=$2; shift 2;;
  *) echo "unknown arg $1" >&2; exit 2;; esac; done
[ -n "$VN" ] && [ -n "$VN1" ] || { echo "need --n and --n1" >&2; exit 2; }
EV="$EVR/$CAND/$FORMAT/$DISTRO-$IMAGE${VARIANT:+-$VARIANT}"
case "$DISP" in "") if [ -S /mnt/wslg/.X11-unix/X0 ]; then DISP=wslg; else DISP=xvfb; fi;; wslg|xvfb) ;; *) echo "bad --display $DISP" >&2; exit 2;; esac
rm -rf "$EV"; mkdir -p "$EV"
WINDOW=0; [ "$IMAGE" = baseline ] && WINDOW=1
NAME="m32-gate-$FORMAT-$DISTRO-$IMAGE${VARIANT:+-$VARIANT}"
ARGS=(--rm --name "$NAME" -v "$PKG:/packages:ro" -v "$EV:/evidence" -v "$HERE/gates-inner.sh:/inner.sh:ro"
  -e FORMAT="$FORMAT" -e WINDOW="$WINDOW" -e DISPLAY_MODE="$DISP" -e WENV_EXTRA="${WX# }" -e EXTRA_APT="$XAPT" -e PK=/packages -e EV=/evidence
  -e DEB_N="${PKN:-gleepglorp-ai_${VN}_amd64.deb}" -e DEB_N1="${PKN1:-gleepglorp-ai_${VN1/.dev/~dev}_amd64.deb}"
  -e APPIMG_N="${PKN:-GleepGlorp_AI-${VN}-x86_64.AppImage}" -e APPIMG_N1="${PKN1:-GleepGlorp_AI-${VN1}-x86_64.AppImage}")
[ "$WINDOW" = 1 ] && [ "$DISP" = wslg ] && ARGS+=(-v /mnt/wslg/.X11-unix:/tmp/.X11-unix)
docker run "${ARGS[@]}" "m32/$DISTRO:$IMAGE" bash /inner.sh > "$EV/container.log" 2>&1 || echo "container rc=$?" >> "$EV/container.log"
case " $WX " in *" THE_ONE_PKG_ABI_PROBE=1 "*)
  # the .deb run of the same probe on the same image (pure host libraries) is the control
  PX=(); CTL="$EVR/$CAND/deb/$DISTRO-$IMAGE-probe"
  [ "$FORMAT" = appimage ] && [ -d "$CTL" ] && PX+=(--control "$CTL")
  case " $WX " in *" THE_ONE_PKG_FORCE_FALLBACK=1 "*) PX+=(--expect-fallback);; esac
  "${PYTHON:-python3}" "$HERE/score.py" "$EV" --probe --format "$FORMAT" --distro "$DISTRO" --image "$IMAGE" "${PX[@]}"; exit;;
esac
[ -f "$EV/window.xwd" ] && "${PYTHON:-python3}" "$HERE/xwd2png.py" "$EV/window.xwd" "$EV/window.png" > "$EV/window-png.txt" 2>&1 || true
"${PYTHON:-python3}" "$HERE/score.py" "$EV" --format "$FORMAT" --distro "$DISTRO" --image "$IMAGE" --n "$VN" --n1 "$VN1"
