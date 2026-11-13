#!/usr/bin/env bash
# Checks against one built macOS .app and its .dmg (packaging checks, DD6, DD8).
# Run on the hosted macos-15 runner as its own step of macos-packages.yml (build.sh no longer runs
# it); every step is logged, none aborts the later ones. The window and the dock behaviour are
# lifecycle.sh's, not this script's.
#
#   checks.sh LABEL APP EXE LOGDIR
#     LABEL   A (the PyInstaller build; names the evidence directory)
#     APP     path of "GleepGlorp AI.app" (quote it: the name has a space)
#     EXE     path of the bundle's main executable (.../Contents/MacOS/the-one)
#     LOGDIR  evidence directory; files land in LOGDIR/LABEL/
# Environment (optional): M32_DMG (the .dmg to layout-check; none = that check is skipped),
# M32_PRODUCT_JSON (build.sh's product.json; default: beside the dist directory of APP, which is
# where build.sh writes it: it names the bundle and gives the audit its minimum OS),
# M32_AUDIT_ARGS (arguments for audit.py; the default is --report-only, so a false positive in
# the first hosted run cannot burn a dispatch: leg 7 flips it to enforcing).
# Exits 1 when a hard check failed (so the workflow step shows red), else 0.
set -u
LABEL="${1:?label}"; APP="${2:?app}"; EXE="${3:?exe}"; LOGDIR="${4:?logdir}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$LOGDIR/$LABEL"; mkdir -p "$OUT"
SCRATCH="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/m32-checks-$LABEL"; rm -rf "$SCRATCH"; mkdir -p "$SCRATCH/data" "$SCRATCH/cwd"
SUMMARY="$OUT/SUMMARY.txt"; : > "$SUMMARY"
FAILS=0
DMG="${M32_DMG:-}"
PJ="${M32_PRODUCT_JSON:-$(dirname "$(dirname "$APP")")/product.json}"
AUDIT_ARGS="${M32_AUDIT_ARGS---report-only}"
note() { echo "$*" | tee -a "$SUMMARY"; }
hard() { # $1 = name  $2 = 0|1 failed
  if [ "$2" = 0 ]; then note "PASS $1"; else note "FAIL $1"; FAILS=$((FAILS + 1)); fi
}
# time limit: macOS has no GNU timeout; alarm survives exec, the child gets SIGALRM (rc 142)
tl() { local n="$1"; shift; perl -e 'alarm shift @ARGV; exec @ARGV or die "exec failed: $!"' -- "$n" "$@"; }

note "== $LABEL: $APP"
{
  echo "-- sw_vers"; sw_vers 2>&1
  echo "-- uname -m"; uname -m
  echo "-- python3 (PATH)"; command -v python3; python3 --version 2>&1
  echo "-- pip"; python3 -m pip --version 2>&1
  echo "-- uv"; uv --version 2>&1
  echo "-- /usr/bin/python3 (Xcode CLT stub on a fresh Mac)"; /usr/bin/python3 --version 2>&1
  echo "-- xcode-select"; xcode-select -p 2>&1
} > "$OUT/env.txt" 2>&1

# ---- signature --------------------------------------------------------------
codesign -dv --verbose=4 "$APP" > "$OUT/codesign-dv.txt" 2>&1; echo "rc=$?" >> "$OUT/codesign-dv.txt"
codesign --verify --deep --strict -vv "$APP" > "$OUT/codesign-verify.txt" 2>&1; VRC=$?
echo "rc=$VRC" >> "$OUT/codesign-verify.txt"
note "codesign -dv rc=$(tail -1 "$OUT/codesign-dv.txt" | cut -d= -f2); verify --deep --strict rc=$VRC; $(grep -E '^Signature=|^Identifier=' "$OUT/codesign-dv.txt" | tr '\n' ' ')"
hard "codesign verify" "$VRC"

# ---- size and layout ---------------------------------------------------------
{ du -sk "$APP"; du -sh "$APP"; echo "-- top level"; ls -la "$APP/Contents" "$APP/Contents/MacOS"
  echo "-- Resources"; find "$APP/Contents/Resources" -maxdepth 1 | sort | head -40
  echo "-- depth 3"; find "$APP/Contents" -maxdepth 3 | sort | head -150
  echo "-- Info.plist"; plutil -p "$APP/Contents/Info.plist" 2>&1
  echo "-- main executable"; file "$EXE" 2>&1; lipo -archs "$EXE" 2>&1
} > "$OUT/layout.txt" 2>&1
note "size: $(du -sh "$APP" | cut -f1) ($(du -sk "$APP" | cut -f1) KB)"

# ---- version -----------------------------------------------------------------
(cd "$SCRATCH/cwd" && tl 60 env THE_ONE_DATA_DIR="$SCRATCH/data" "$EXE" version) > "$OUT/version.txt" 2>&1
echo "rc=$?" >> "$OUT/version.txt"
note "version: $(grep -v -e NSLog -e std-nslog "$OUT/version.txt" | head -1) ($(tail -1 "$OUT/version.txt"))"
if [ ! -s "$OUT/version.txt" ] || [ "$(wc -l < "$OUT/version.txt")" -le 1 ]; then
  # a GUI stub may swallow stdout: leave the unified log's view of the process for the reader
  tl 60 log show --last 3m --style compact --predicate "process == \"$(basename "$EXE")\"" 2>&1 | tail -60 > "$OUT/unified-log.txt"
  note "version printed nothing: unified log tail saved to unified-log.txt"
fi

# ---- gate 1: doctor ------------------------------------------------------------
# the unpinned run is the only run on darwin (PYSTRAY_BACKEND does not apply); window chrome's
# "skipped (not Windows)" is the only allowed skip (score_doctor knows)
(cd "$SCRATCH/cwd" && tl 240 env THE_ONE_DATA_DIR="$SCRATCH/data" "$EXE" doctor) > "$OUT/doctor.txt" 2>&1
echo "rc=$?" >> "$OUT/doctor.txt"
python3 -c '
import json, sys
sys.path.insert(0, sys.argv[1])
import score
print(json.dumps(score.score_doctor(open(sys.argv[2], errors="replace").read())))
' "$HERE/../linux/checks" "$OUT/doctor.txt" > "$OUT/doctor-score.json" 2> "$OUT/doctor-score.err"
note "doctor score: $(cat "$OUT/doctor-score.json")"
grep -q '"pass": true' "$OUT/doctor-score.json"; hard "gate 1 doctor" $?
grep -E "desktop shell|file watcher|window chrome|python interpreter|time zones|mcp sdk|chart images" "$OUT/doctor.txt" | while IFS= read -r l; do note "  $l"; done
# strict on top of the score: the three macOS facts leg 5 and leg 4 put in the doctor, by exact text
grep -qF 'desktop shell: OK — Cocoa backend present' "$OUT/doctor.txt"; hard "doctor: desktop shell is the Cocoa backend" $?
grep -qF 'tray: dock' "$OUT/doctor.txt"; hard "doctor: tray is dock" $?
grep -qE '^ *path: ' "$OUT/doctor.txt"; hard "doctor: a path: line is present" $?

# ---- gate 2: the interpreter doctor resolved, run independently --------------------
PYP="$(sed -n 's/.*python interpreter: OK.*resolved to //p' "$OUT/doctor.txt" | head -1 | tr -d '\r')"
G2RUN=1
{ echo "resolved: $PYP"
  if [ -n "$PYP" ]; then tl 60 "$PYP" -c 'import sys; print(sys.executable, sys.prefix)' && G2RUN=0 && "$PYP" --version; fi
} > "$OUT/gate2.txt" 2>&1
note "gate 2: $(tr '\n' '|' < "$OUT/gate2.txt")"
G2=1
if [ -n "$PYP" ] && [ "$G2RUN" = 0 ] && ! grep -q -E '\.app/|Contents' "$OUT/gate2.txt"; then G2=0; fi
# the resolved interpreter must also not be the bundle's own executable
case "$PYP" in "$APP"*) G2=1 ;; esac
hard "gate 2 interpreter outside the bundle" "$G2"

# ---- serve on a scratch port: GET /api/live needs no credential ----------------------
SERVE_PID=""
stop_serve() {
  [ -n "$SERVE_PID" ] || return 0
  kill -TERM "$SERVE_PID" 2>/dev/null
  for _ in $(seq 1 15); do kill -0 "$SERVE_PID" 2>/dev/null || { SERVE_PID=""; return 0; }; sleep 1; done
  kill -KILL "$SERVE_PID" 2>/dev/null; SERVE_PID=""
}
DMG_MP=""
detach_dmg() {
  [ -n "$DMG_MP" ] || return 0
  tl 60 hdiutil detach "$DMG_MP" > "$OUT/dmg-detach.txt" 2>&1 \
    || { sleep 2; tl 60 hdiutil detach -force "$DMG_MP" >> "$OUT/dmg-detach.txt" 2>&1; }
  DMG_MP=""
}
cleanup() { stop_serve; detach_dmg; }
trap cleanup EXIT
(cd "$SCRATCH/cwd" && exec perl -e 'alarm shift @ARGV; exec @ARGV or die "exec failed: $!"' -- 240 \
  env THE_ONE_PORT=8490 THE_ONE_DATA_DIR="$SCRATCH/data" "$EXE" serve) > "$OUT/serve.log" 2>&1 &
SERVE_PID=$!
LIVE=1
for _ in $(seq 1 60); do
  if curl -fsS -m 2 http://127.0.0.1:8490/api/live > "$OUT/live.txt" 2>&1; then LIVE=0; break; fi
  kill -0 "$SERVE_PID" 2>/dev/null || break
  sleep 1
done
note "serve /api/live: $(head -c 200 "$OUT/live.txt" 2>/dev/null)"
stop_serve
hard "serve answers /api/live" "$LIVE"

# ---- gate 4: the default data dir (the runner is disposable; no override) ------------------
(cd "$SCRATCH/cwd" && unset THE_ONE_DATA_DIR && tl 60 "$EXE" rotate-api-credential) > "$OUT/gate4-rotate.txt" 2>&1
echo "rc=$?" >> "$OUT/gate4-rotate.txt"
ls -laR "$HOME/Library/Application Support/the-one" > "$OUT/gate4-ls.txt" 2>&1
note "gate 4: $(grep -v -e NSLog -e std-nslog "$OUT/gate4-rotate.txt" | head -2 | tr '\n' '|')"
grep -q "Library/Application Support/the-one/" "$OUT/gate4-rotate.txt"; hard "gate 4 data dir under Application Support" $?

# ---- the bundle audit (DD8): load paths, arm64 slices, minimum OS --------------------------
if [ -f "$PJ" ]; then
  # shellcheck disable=SC2086  # AUDIT_ARGS is a flag list on purpose
  tl 420 python3 "$HERE/audit.py" "$APP" --product-json "$PJ" $AUDIT_ARGS > "$OUT/audit.txt" 2>&1
  ARC=$?
  echo "rc=$ARC" >> "$OUT/audit.txt"
  note "audit ($AUDIT_ARGS): $(grep '^audit:' "$OUT/audit.txt" | head -1 | cut -c1-200)"
  hard "bundle audit" "$ARC"
else
  note "audit: $PJ is missing"
  hard "bundle audit (product.json present)" 1
fi

# ---- the .dmg layout (DD8): the app beside an Applications symlink ---------------------------
if [ -n "$DMG" ]; then
  BNAME="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["bundle_name"])' "$PJ" 2>/dev/null)"
  if [ -f "$DMG" ]; then DMG_RC=0; else DMG_RC=1; fi
  hard "dmg file exists ($(basename "$DMG"))" "$DMG_RC"
  MP="$SCRATCH/dmg-mount"; rm -rf "$MP"; mkdir -p "$MP"
  tl 120 hdiutil attach -readonly -nobrowse -noverify -noautoopen -mountpoint "$MP" "$DMG" > "$OUT/dmg-attach.txt" 2>&1
  ATT=$?
  [ "$ATT" = 0 ] && DMG_MP="$MP"
  hard "dmg attaches read-only" "$ATT"
  if [ "$ATT" = 0 ]; then
    ls -la "$MP" > "$OUT/dmg-layout.txt" 2>&1
    D1=1; if [ -n "$BNAME" ] && [ -d "$MP/$BNAME.app" ]; then D1=0; fi
    hard "dmg holds $BNAME.app" "$D1"
    D2=1; if [ -L "$MP/Applications" ] && [ "$(readlink "$MP/Applications")" = /Applications ]; then D2=0; fi
    hard "dmg Applications is a symlink to /Applications" "$D2"
    note "dmg: $(wc -c < "$DMG" | tr -d ' ') bytes; $(tr '\n' '|' < "$OUT/dmg-layout.txt" | cut -c1-200)"
  fi
  detach_dmg
else
  note "dmg layout: skipped (no M32_DMG)"
fi

note "== $LABEL done: $FAILS hard check(s) failed"
[ "$FAILS" = 0 ]
