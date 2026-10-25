#!/usr/bin/env bash
# Build GleepGlorp AI for macOS with PyInstaller, sign ad hoc, make a .dmg and run the checks.
# Spike prototype (Mission 32 Flight 1, candidate A). Meant for the hosted macos-15 runner
# (macos-packages.yml); every step is rehearsable with `bash -n`.
#
#   packaging/macos/build.sh <version>           e.g. 0.11.8
#
# Environment:
#   M32_BUILD         build root (default $RUNNER_TEMP/m32-build, else $HOME/the-one-m32-build)
#   M32_LOGS          evidence/log directory (default $M32_BUILD/logs)
#   M32_REQUIREMENTS  the hash-pinned `uv export` closure (REQUIRED; the workflow writes it)
# Needs on PATH: python3 (3.11, setup-python), codesign, hdiutil, perl.
set -u

VERSION="${1:?usage: build.sh <version>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
M32_BUILD="${M32_BUILD:-${RUNNER_TEMP:-$HOME}/m32-build}"
M32_LOGS="${M32_LOGS:-$M32_BUILD/logs}"
REQS="${M32_REQUIREMENTS:?set M32_REQUIREMENTS to the uv export closure file}"
STAGE="$M32_BUILD/stage-macos-$VERSION"
VENV="$M32_BUILD/venv-pyi"
WORK="$M32_BUILD/macos-$VERSION"
APP="$WORK/dist/GleepGlorp AI.app"
DMG="$WORK/GleepGlorp_AI-$VERSION-arm64.dmg"
LOG="$M32_LOGS/A"
mkdir -p "$M32_BUILD" "$LOG"
tl() { local n="$1"; shift; perl -e 'alarm shift @ARGV; exec @ARGV or die "exec failed: $!"' -- "$n" "$@"; }
die() { echo "build.sh: $*" >&2; exit 1; }

echo "== A: stage $VERSION"
python3 "$REPO/packaging/stage.py" --version "$VERSION" --target macos --out "$M32_BUILD" \
    || die "stage failed"

echo "== A: build venv (python $(python3 --version 2>&1), $(uname -m))"
rm -rf "$VENV"; python3 -m venv "$VENV" || die "venv failed"
# the same hash-pinned closure the Windows CI ships (DD3); --no-deps
# because the export is complete (see packaging/linux/README.md)
"$VENV/bin/python" -m pip install --disable-pip-version-check --require-hashes --no-deps -r "$REQS" \
    > "$LOG/pip-closure.log" 2>&1 || { tail -40 "$LOG/pip-closure.log"; die "closure install failed (package named above)"; }
# pinned build tools, never added to uv.lock or the root pyproject.toml
"$VENV/bin/python" -m pip install --disable-pip-version-check pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.8 \
    > "$LOG/pip-tools.log" 2>&1 || { tail -20 "$LOG/pip-tools.log"; die "pyinstaller install failed"; }
"$VENV/bin/python" -m pip freeze > "$LOG/pip-freeze.txt" 2>&1

echo "== A: icon"
mkdir -p "$WORK"
"$VENV/bin/python" "$HERE/make-icns.py" "$STAGE/icon-512.png" "$WORK/icon.icns" > "$LOG/icns.log" 2>&1 \
    || { cat "$LOG/icns.log"; die "icns failed"; }

echo "== A: freeze"
rm -rf "$WORK/dist" "$WORK/work"; mkdir -p "$WORK"
t0=$SECONDS
M32_STAGE="$STAGE" M32_ICNS="$WORK/icon.icns" "$VENV/bin/pyinstaller" --noconfirm --clean \
    --distpath "$WORK/dist" --workpath "$WORK/work" "$HERE/the-one.spec" > "$LOG/pyinstaller.log" 2>&1
RC=$?
echo "pyinstaller rc=$RC in $((SECONDS - t0)) s"
if [ "$RC" != 0 ] || [ ! -x "$APP/Contents/MacOS/the-one" ]; then tail -60 "$LOG/pyinstaller.log"; die "freeze failed"; fi

echo "== A: ad-hoc sign"
codesign --force --deep -s - "$APP" > "$LOG/codesign-sign.log" 2>&1; echo "codesign sign rc=$?"

if [ "${M32_SKIP_CHECKS:-0}" = 1 ]; then
    echo "== A: dmg skipped (M32_SKIP_CHECKS=1, probe mode: saves 1-3 minutes and a hang risk)"
else
    echo "== A: dmg"
    # hdiutil can fail on a busy runner: one retry, both attempts logged, never fatal
    for attempt in 1 2; do
        tl 300 hdiutil create -volname "GleepGlorp AI" -srcfolder "$APP" -ov -format UDZO "$DMG" \
            > "$LOG/hdiutil-$attempt.log" 2>&1; HRC=$?
        echo "hdiutil attempt $attempt rc=$HRC"
        [ "$HRC" = 0 ] && break
    done
    { ls -l "$DMG" 2>&1; hdiutil verify "$DMG" 2>&1 | tail -3; } > "$LOG/dmg.txt" 2>&1 || true
    cat "$LOG/dmg.txt"
fi

# M32_SKIP_CHECKS=1 skips checks.sh entirely (the probe mode of macos-packages.yml, Mission 32
# Flight 3 leg 2): its doctor/serve/gate-4 runs would create the default data dir and a
# credential before the probe's first-launch premise (P1), and the skip saves about 5 minutes.
if [ "${M32_SKIP_CHECKS:-0}" = 1 ]; then
    echo "== A: checks skipped (M32_SKIP_CHECKS=1)"
    exit 0
fi
echo "== A: checks"
bash "$REPO/packaging/macos/checks.sh" A "$APP" "$APP/Contents/MacOS/the-one" "$M32_LOGS"
