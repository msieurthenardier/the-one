#!/usr/bin/env bash
# Build GleepGlorp AI for macOS with Briefcase, ad-hoc sign, package a .dmg and run the checks.
# Spike prototype (Mission 32 Flight 1, candidate B). Meant for the hosted macos-15 runner
# (packaging-probe-macos.yml); the Linux twin is build.sh.
#
#   packaging/briefcase/build-macos.sh <version>           e.g. 0.11.8
#
# Environment:
#   M32_BUILD         build root (default $RUNNER_TEMP/m32-build, else $HOME/the-one-m32-build)
#   M32_LOGS          evidence/log directory (default $M32_BUILD/logs)
#   M32_REQUIREMENTS  the hash-pinned `uv export` closure (REQUIRED; the workflow writes it)
# Needs on PATH: python3 (3.11, setup-python), git (Briefcase clones its template), codesign.
# Briefcase is pinned to 0.4.6 and installed into its own venv, never the repo's.
set -u

VERSION="${1:?usage: build-macos.sh <version>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
M32_BUILD="${M32_BUILD:-${RUNNER_TEMP:-$HOME}/m32-build}"
M32_LOGS="${M32_LOGS:-$M32_BUILD/logs}"
REQS="${M32_REQUIREMENTS:?set M32_REQUIREMENTS to the uv export closure file}"
STAGE="$M32_BUILD/stage-briefcase-$VERSION"
VENV="$M32_BUILD/venv-briefcase"
LOG="$M32_LOGS/B"
mkdir -p "$M32_BUILD" "$LOG"
die() { echo "build-macos.sh: $*" >&2; exit 1; }

echo "== B: tool venv (python $(python3 --version 2>&1), $(uname -m))"
rm -rf "$VENV"; python3 -m venv "$VENV" || die "venv failed"
"$VENV/bin/python" -m pip install --disable-pip-version-check briefcase==0.4.6 pillow \
    > "$LOG/pip-tools.log" 2>&1 || { tail -20 "$LOG/pip-tools.log"; die "briefcase install failed"; }
"$VENV/bin/python" -m pip freeze > "$LOG/pip-freeze.txt" 2>&1
BC="$VENV/bin/briefcase"
echo "briefcase $("$BC" --version 2>&1)"

echo "== B: stage $VERSION (patches 01 and 02, staging copy only)"
python3 "$REPO/packaging/spike/stage.py" --version "$VERSION" --candidate briefcase --out "$M32_BUILD" \
    || die "stage failed (a patch did not apply?)"

# Inputs Briefcase insists on that the app tree does not have (same placeholders as build.sh).
cat > "$STAGE/LICENSE.txt" <<'L'
Placeholder license text for the Mission 32 packaging spike. Briefcase refuses to package without one.
L
printf '# Changelog\n\n## %s\n\nSpike build (Mission 32 Flight 1).\n' "$VERSION" > "$STAGE/CHANGELOG.md"

# Icons: macOS wants icon.icns; the PNG sizes are for Briefcase's template lookup.
"$VENV/bin/python" "$REPO/packaging/macos/make-icns.py" "$STAGE/icon-512.png" "$STAGE/icon.icns" \
    --png-dir "$STAGE" > "$LOG/icns.log" 2>&1 || { cat "$LOG/icns.log"; die "icns failed"; }

# The pinned closure. On macOS Briefcase hands `requires` straight to pip (no copy into a
# container like Linux), so the file is given by absolute path rather than "./closure.txt".
cp "$REQS" "$STAGE/closure.txt"
"$VENV/bin/python" - "$HERE/pyproject.toml.in" "$STAGE/pyproject.toml" "$VERSION" "$STAGE/closure.txt" <<'PY'
import json
import sys

src, dst, version, closure = sys.argv[1:5]
text = open(src, encoding="utf-8").read()
text = text.replace("@VERSION@", version).replace("@REQUIRES@", json.dumps(["-r", closure]))
open(dst, "w", encoding="utf-8").write(text)
PY

cd "$STAGE" || die "cannot enter the staging dir"
echo "== B: briefcase create / build / package"
t0=$SECONDS
for step in create build package; do
    extra=()
    # ad hoc: no Developer ID on the runner; no notarization either
    [ "$step" = package ] && extra=(--adhoc-sign --no-notarize)
    # -v: pip's output must name the package a wheel is missing for
    # ${extra[@]+...}: an empty array is an unbound variable under `set -u` in macOS's bash 3.2
    "$BC" "$step" macOS app --no-input -v ${extra[@]+"${extra[@]}"} > "$LOG/briefcase-$step.log" 2>&1
    RC=$?
    echo "briefcase $step rc=$RC ($((SECONDS - t0)) s so far)"
    if [ "$RC" != 0 ]; then tail -60 "$LOG/briefcase-$step.log"; die "briefcase $step failed"; fi
done

APP="$(find "$STAGE" -maxdepth 6 -name 'GleepGlorp AI.app' -type d | head -1)"
[ -n "$APP" ] || die "no GleepGlorp AI.app found under $STAGE"
{ echo "app: $APP"; find "$STAGE/dist" -maxdepth 1 -type f -exec ls -l {} \; 2>&1; } > "$LOG/artifacts.txt" 2>&1
cat "$LOG/artifacts.txt"

echo "== B: checks"
bash "$REPO/packaging/spike/macos-checks.sh" B "$APP" "$APP/Contents/MacOS/GleepGlorp AI" "$M32_LOGS"
