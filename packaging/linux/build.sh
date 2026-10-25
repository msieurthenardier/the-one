#!/usr/bin/env bash
# Build GleepGlorp AI for Linux: stage on the host, render the packaging templates, then freeze
# and wrap (AppImage and .deb) inside the pinned build container (Mission 32 Flight 2, DD2, DD6).
#
#   packaging/linux/build.sh [--version X] [--no-excludes]
#
# The version defaults to __version__ in the_one/__init__.py (via packaging/render.py);
# --version X (e.g. 0.11.9.dev1) overrides it for a test build. The old positional form,
# `build.sh 0.11.8 [--no-excludes]`, still works with a warning.
#
# Environment:
#   M32_BUILD      build root, outside the repo (default $HOME/the-one-m32-build/f2)
#   M32_FROM_HEAD  "1" = stage `git archive HEAD` instead of the working tree
#
# Staging, rendering and `uv export` run on the host, not in the container: the checkout may be
# a git worktree whose .git file points outside the mounted tree. The container gets the staged
# copy (with the rendered files in rendered/), packaging/ (read-only; the spec loads
# ../windows/frozen_entry.py) and an output dir.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

VERSION="" NO_EXCLUDES="" POSITIONAL=""
while [ $# -gt 0 ]; do
    case "$1" in
        --version) VERSION="${2:?build.sh: --version needs a value}"; shift 2 ;;
        --version=*) VERSION="${1#--version=}"; shift ;;
        --no-excludes) NO_EXCLUDES=--no-excludes; shift ;;
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

M32_BUILD="${M32_BUILD:-$HOME/the-one-m32-build/f2}"
IMAGE=m32/linux-build:f2
CTX="$M32_BUILD/ctx"
RENDER=(python3 "$REPO/packaging/render.py" --repo "$REPO")

if [ -z "$VERSION" ]; then
    VERSION="$("${RENDER[@]}" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')"
fi
STAGE="$M32_BUILD/stage-linux-$VERSION"
# A rebuild of the same tree renders the same files: the release date is the last commit's.
SOURCE_DATE_EPOCH="$(git -C "$REPO" log -1 --format=%ct)"
export SOURCE_DATE_EPOCH

mkdir -p "$M32_BUILD" "$CTX"

echo "== stage $VERSION"
if [ "${M32_FROM_HEAD:-}" = 1 ]; then
    SRC="$M32_BUILD/src-head"
    rm -rf "$SRC"; mkdir -p "$SRC"
    git -C "$REPO" archive HEAD the_one | tar -x -C "$SRC"
    echo "staging from HEAD $(git -C "$REPO" rev-parse --short HEAD)"
    export M32_SOURCE="$SRC"
fi
python3 "$REPO/packaging/stage.py" --version "$VERSION" --target linux --out "$M32_BUILD"

echo "== render"
R="$STAGE/rendered"
mkdir -p "$R"
rnd() {   # rnd <template> <output> [--set K=V ...]
    local tpl="$1" out="$2"; shift 2
    "${RENDER[@]}" --template "$HERE/$tpl" --set "version=$VERSION" "$@" > "$R/$out"
}
rnd build.env.in build.env
rnd AppRun.in AppRun
rnd control.in control
rnd deb.desktop.in deb.desktop
rnd metainfo.xml.in metainfo.xml
# the AppImage's own entry: kept with its runtime placeholders for AppRun to fill ...
rnd appimage.desktop.in integration.desktop.in
# ... and the AppDir root copy (what appimagetool validates): paths as AppRun sees them
rnd appimage.desktop.in appimage-root.desktop --set APPIMAGE_EXEC=AppRun --set APPIMAGE_PATH=AppRun \
    --set ICON_PATH="$("${RENDER[@]}" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["desktop_id"])')"

echo "== build image"
(cd "$REPO" && uv export --frozen --no-dev --no-emit-project --extra gui --extra all-llms \
    --format requirements-txt > "$CTX/requirements-closure.txt")
docker build -q -f "$HERE/build.Dockerfile" -t "$IMAGE" "$CTX" > /dev/null
echo "image: $IMAGE $(docker image inspect --format '{{.Id}}' "$IMAGE")"

echo "== build $VERSION in the container"
docker run --rm --name "m32-build-${VERSION//[^A-Za-z0-9_.-]/_}" -u "$(id -u):$(id -g)" \
    -v "$REPO/packaging:/packaging:ro" -v "$STAGE:/stage:ro" -v "$M32_BUILD:/out" \
    "$IMAGE" /packaging/linux/build-inner.sh ${NO_EXCLUDES:+"$NO_EXCLUDES"} \
    2>&1 | tee "$M32_BUILD/build-$VERSION.log"

echo "packages: $M32_BUILD/packages"
