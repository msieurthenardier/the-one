#!/usr/bin/env bash
# Build GleepGlorp AI for macOS with PyInstaller, sign ad hoc and make a .dmg (Mission 32
# Flight 3 leg 6). Meant for the hosted macos-15 runner (macos-packages.yml); every step is
# rehearsable on Linux with shims for codesign, hdiutil, ditto and the rest.
#
#   packaging/macos/build.sh [--version X] [--from-head]
#
# The version defaults to __version__ in the_one/__init__.py (via packaging/render.py);
# --version X (e.g. 0.11.9.dev1) overrides it for a test build. The old positional form,
# `build.sh 0.11.8`, still works with a warning. --from-head stages `git archive HEAD`
# instead of the working tree. The checks are NOT run here: macos-packages.yml runs
# packaging/macos/checks.sh as its own step.
#
# Environment:
#   M32_BUILD         build root (default $RUNNER_TEMP/m32-build, else $HOME/the-one-m32-build)
#   M32_LOGS          evidence/log directory (default $M32_BUILD/logs)
#   M32_REQUIREMENTS  the hash-pinned `uv export` closure (REQUIRED; the workflow writes it)
#   M32_SKIP_DMG=1    skip the .dmg (the N+1 build and probe mode; M32_SKIP_CHECKS=1 is an alias)
#   M32_REUSE_VENV=1  keep an existing build venv instead of rebuilding it (the N+1 build)
#
# Writes $M32_BUILD/macos-<version>/build.env (VERSION, APP_ID, APP, DMG; shell-quoted, source
# it) and product.json (the rendered values the spec reads).
# Needs on PATH: python3 (3.12, setup-python), codesign, hdiutil, ditto, perl.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
die() { echo "build.sh: $*" >&2; exit 1; }

VERSION="" POSITIONAL="" FROM_HEAD=0
while [ $# -gt 0 ]; do
    case "$1" in
        --version) [ $# -ge 2 ] || die "--version needs a value"; VERSION="$2"; shift 2 ;;
        --version=*) VERSION="${1#--version=}"; shift ;;
        --from-head) FROM_HEAD=1; shift ;;
        -*) echo "build.sh: unknown option $1" >&2; exit 2 ;;
        *)
            if [ -n "$POSITIONAL" ]; then echo "build.sh: more than one positional version" >&2; exit 2; fi
            POSITIONAL="$1"; shift ;;
    esac
done
if [ -n "$POSITIONAL" ]; then
    if [ -n "$VERSION" ]; then
        echo "build.sh: --version and a positional version together" >&2; exit 2
    fi
    echo "build.sh: a positional version is deprecated; use --version X" >&2
    VERSION="$POSITIONAL"
fi

M32_BUILD="${M32_BUILD:-${RUNNER_TEMP:-$HOME}/m32-build}"
M32_LOGS="${M32_LOGS:-$M32_BUILD/logs}"
REQS="${M32_REQUIREMENTS:?set M32_REQUIREMENTS to the uv export closure file}"
SKIP_DMG="${M32_SKIP_DMG:-${M32_SKIP_CHECKS:-0}}"
REUSE_VENV="${M32_REUSE_VENV:-0}"
VENV="$M32_BUILD/venv-pyi"
LOG="$M32_LOGS/A"
mkdir -p "$M32_BUILD" "$LOG"
tl() { local n="$1"; shift; perl -e 'alarm shift @ARGV; exec @ARGV or die "exec failed: $!"' -- "$n" "$@"; }

if [ -z "$VERSION" ]; then
    VERSION="$(python3 "$REPO/packaging/render.py" --repo "$REPO" --json \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')" \
        || die "could not read the version"
fi
STAGE="$M32_BUILD/stage-macos-$VERSION"
WORK="$M32_BUILD/macos-$VERSION"
# A rebuild of the same tree renders the same files: the release date is the last commit's.
if SDE="$(git -C "$REPO" log -1 --format=%ct 2>/dev/null)" && [ -n "$SDE" ]; then
    SOURCE_DATE_EPOCH="$SDE"; export SOURCE_DATE_EPOCH
fi

mkdir -p "$WORK"
python3 "$REPO/packaging/render.py" --repo "$REPO" --json --set "version=$VERSION" > "$WORK/product.json" \
    || die "render failed for version $VERSION"
pj() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$WORK/product.json" "$1"; }
BUNDLE_NAME="$(pj bundle_name)"; APP_ID="$(pj app_id)"; EXE_NAME="$(pj bundle_executable)"
DMG_STEM="$(pj dmg_file_stem)"
if [ -z "$BUNDLE_NAME" ] || [ -z "$APP_ID" ] || [ -z "$EXE_NAME" ] || [ -z "$DMG_STEM" ]; then
    die "product.json lacks a [macos] value"
fi
APP="$WORK/dist/$BUNDLE_NAME.app"
DMG="$WORK/$DMG_STEM-$VERSION-arm64.dmg"
{
    printf 'VERSION=%q\n' "$VERSION"
    printf 'APP_ID=%q\n' "$APP_ID"
    printf 'APP=%q\n' "$APP"
    printf 'DMG=%q\n' "$DMG"
} > "$WORK/build.env"
echo "build.env: $WORK/build.env"

echo "== A: stage $VERSION"
if [ "$FROM_HEAD" = 1 ]; then
    SRC="$M32_BUILD/src-head"
    rm -rf "$SRC"; mkdir -p "$SRC"
    git -C "$REPO" archive HEAD the_one | tar -x -C "$SRC"
    echo "staging from HEAD $(git -C "$REPO" rev-parse --short HEAD)"
    export M32_SOURCE="$SRC"
fi
python3 "$REPO/packaging/stage.py" --version "$VERSION" --target macos --out "$M32_BUILD" \
    || die "stage failed"

if [ "$REUSE_VENV" = 1 ] && [ -x "$VENV/bin/pyinstaller" ]; then
    echo "== A: build venv reused (M32_REUSE_VENV=1)"
else
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
fi

echo "== A: icon"
mkdir -p "$WORK"
"$VENV/bin/python" "$HERE/make-icns.py" "$STAGE/icon-512.png" "$WORK/icon.icns" > "$LOG/icns.log" 2>&1 \
    || { cat "$LOG/icns.log"; die "icns failed"; }

echo "== A: freeze"
rm -rf "$WORK/dist" "$WORK/work"; mkdir -p "$WORK"
t0=$SECONDS
M32_STAGE="$STAGE" M32_ICNS="$WORK/icon.icns" M32_PRODUCT_JSON="$WORK/product.json" "$VENV/bin/pyinstaller" --noconfirm --clean \
    --distpath "$WORK/dist" --workpath "$WORK/work" "$HERE/the-one.spec" > "$LOG/pyinstaller.log" 2>&1
RC=$?
echo "pyinstaller rc=$RC in $((SECONDS - t0)) s"
if [ "$RC" != 0 ] || [ ! -x "$APP/Contents/MacOS/$EXE_NAME" ]; then tail -60 "$LOG/pyinstaller.log"; die "freeze failed"; fi

echo "== A: ad-hoc sign"
# Ad-hoc only (DD8); a Developer ID signature and notarization would slot in here.
codesign --force --deep -s - "$APP" > "$LOG/codesign-sign.log" 2>&1; echo "codesign sign rc=$?"

if [ "$SKIP_DMG" = 1 ]; then
    echo "== A: dmg skipped (M32_SKIP_DMG=1)"
    exit 0
fi
echo "== A: dmg"
# the drag-to-Applications layout: the .app beside a symlink to /Applications
DMGROOT="$WORK/dmg-root"
rm -rf "$DMGROOT"; mkdir -p "$DMGROOT"
ditto "$APP" "$DMGROOT/$BUNDLE_NAME.app" || die "could not stage the .app for the dmg"
ln -s /Applications "$DMGROOT/Applications"
rm -f "$DMG"
# hdiutil can fail on a busy runner: one retry, both attempts logged
HRC=1
for attempt in 1 2; do
    tl 300 hdiutil create -volname "$BUNDLE_NAME" -srcfolder "$DMGROOT" -fs HFS+ -format UDZO -ov "$DMG" \
        > "$LOG/hdiutil-$attempt.log" 2>&1; HRC=$?
    echo "hdiutil attempt $attempt rc=$HRC"
    [ "$HRC" = 0 ] && break
done
{ ls -l "$DMG" 2>&1; hdiutil verify "$DMG" 2>&1 | tail -3; } > "$LOG/dmg.txt" 2>&1 || true
cat "$LOG/dmg.txt"
if [ "$HRC" != 0 ] || [ ! -f "$DMG" ]; then die "hdiutil failed twice"; fi
