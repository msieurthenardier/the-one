#!/usr/bin/env bash
# Build GleepGlorp AI for Linux with Briefcase: stage, generate config, build one .deb per target distro.
# Spike prototype (Mission 32 Flight 1, candidate B); not wired into CI.
#
#   packaging/briefcase/build.sh <version> [--appimage]       e.g. 0.11.8 or 0.11.9.dev1
#
# Environment (everything outside the repo, under $HOME):
#   M32_BUILD    build root (default $HOME/the-one-m32-build); needs venv-briefcase/ (see README)
#   M32_TARGETS  space-separated Docker targets (default "ubuntu:26.04 debian:13")
#   M32_PKG_OUT  where the finished packages are copied (default $M32_BUILD/packages-briefcase)
# Needs: docker, git (Briefcase clones its template), uv (for the closure export).
set -euo pipefail

VERSION="${1:?usage: build.sh <version> [--appimage]}"
WANT_APPIMAGE="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
M32_BUILD="${M32_BUILD:-$HOME/the-one-m32-build}"
BC="$M32_BUILD/venv-briefcase/bin/briefcase"
TARGETS="${M32_TARGETS:-ubuntu:26.04 debian:13}"
STAGE="$M32_BUILD/stage-briefcase-$VERSION"
OUT="${M32_PKG_OUT:-$M32_BUILD/packages-briefcase}"
LOGDIR="$M32_BUILD/briefcase-logs-$VERSION"
mkdir -p "$OUT" "$LOGDIR"

echo "== briefcase $("$BC" --version)"
echo "== stage $VERSION"
python3 "$REPO/packaging/spike/stage.py" --version "$VERSION" --candidate briefcase --out "$M32_BUILD"

# Inputs Briefcase insists on that the app tree does not have: a license file and a changelog.
cat > "$STAGE/LICENSE.txt" <<'L'
Placeholder license text for the Mission 32 packaging spike. Briefcase refuses to package without one.
L
printf '# Changelog\n\n## %s\n\nSpike build (Mission 32 Flight 1).\n' "$VERSION" > "$STAGE/CHANGELOG.md"

# Icons: Briefcase wants icon-<size>.png; derive them from the staged 512px icon.
"$REPO/.venv/bin/python" - "$STAGE" <<'PY'
import sys
from pathlib import Path
from PIL import Image
stage = Path(sys.argv[1])
src = Image.open(stage / "icon-512.png").convert("RGBA")
for size in (16, 32, 48, 64, 128, 256, 512):
    src.resize((size, size), Image.LANCZOS).save(stage / f"icon-{size}.png")
PY

# The pinned closure: the same hash-pinned `uv export` that candidate A installs (DD3).
( cd "$REPO" && uv export --frozen --no-dev --no-emit-project --extra gui --extra all-llms \
    --format requirements-txt ) > "$STAGE/closure.txt"
# `-r` plus the file keeps the hashes (a `requires` entry is one pip argument and cannot carry --hash).
# Briefcase copies a path-like requirement into the bundle so the build container can see it.
sed -e "s|@VERSION@|$VERSION|g" -e 's|@REQUIRES@|["-r", "./closure.txt"]|' \
    "$HERE/pyproject.toml.in" > "$STAGE/pyproject.toml"

cd "$STAGE"
for T in $TARGETS; do
    TAG="${T/:/-}"
    echo "== deb for $T"
    t0=$SECONDS
    rm -rf dist
    for step in create build package; do
        extra=()
        [ "$step" = package ] && extra=(--adhoc-sign)
        "$BC" "$step" linux system --target "$T" --no-input "${extra[@]}" -v \
            > "$LOGDIR/$TAG-$step.log" 2>&1 || { echo "FAILED: $step $T (see $LOGDIR/$TAG-$step.log)"; exit 1; }
        echo "   $step done ($((SECONDS - t0)) s so far)"
    done
    echo "$T build time $((SECONDS - t0)) s" | tee -a "$LOGDIR/times.txt"
    cp -v dist/*.deb "$OUT/"
done

if [ "$WANT_APPIMAGE" = "--appimage" ]; then
    echo "== AppImage"
    t0=$SECONDS
    rm -rf dist
    for step in create build package; do
        extra=()
        [ "$step" = package ] && extra=(--adhoc-sign)
        "$BC" "$step" linux appimage --no-input "${extra[@]}" -v \
            > "$LOGDIR/appimage-$step.log" 2>&1 || { echo "FAILED: appimage $step (see $LOGDIR/appimage-$step.log)"; exit 1; }
    done
    echo "appimage build time $((SECONDS - t0)) s" | tee -a "$LOGDIR/times.txt"
    cp -v dist/*.AppImage "$OUT/"
fi
echo "== done; packages in $OUT"
