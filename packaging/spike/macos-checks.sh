#!/usr/bin/env bash
# Checks against one built macOS .app (Mission 32 Flight 1 spike, DD6). Candidate-neutral.
# Run on the hosted macos-15 runner by packaging/macos/build.sh (A) and
# packaging/briefcase/build-macos.sh (B); every step is logged, none aborts the later ones.
#
#   macos-checks.sh LABEL APP EXE LOGDIR
#     LABEL   A or B (B also runs the stub probe: Briefcase's launcher is not a Python)
#     APP     path of "GleepGlorp AI.app" (quote it: the name has a space)
#     EXE     path of the bundle's main executable (A: .../Contents/MacOS/the-one,
#             B: ".../Contents/MacOS/GleepGlorp AI")
#     LOGDIR  evidence directory; files land in LOGDIR/LABEL/
# The window is not tested here (DD6), except for one best-effort Finder-style `open`.
# Exits 1 when a hard check failed (so the workflow step shows red), else 0.
set -u
LABEL="${1:?label}"; APP="${2:?app}"; EXE="${3:?exe}"; LOGDIR="${4:?logdir}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$LOGDIR/$LABEL"; mkdir -p "$OUT"
SCRATCH="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/m32-checks-$LABEL"; rm -rf "$SCRATCH"; mkdir -p "$SCRATCH/data" "$SCRATCH/cwd"
SUMMARY="$OUT/SUMMARY.txt"; : > "$SUMMARY"
FAILS=0
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

# ---- B only: what is sys.executable inside Briefcase's stub? Printed first so the run's
# reader can confirm or refute the layout assumptions behind patch 02's macOS clause. Run on a
# COPY: adding the probe module to the signed bundle would break its seal.
if [ "$LABEL" = B ]; then
  PCOPY="$SCRATCH/probe-copy/$(basename "$APP")"; mkdir -p "$SCRATCH/probe-copy"
  ditto "$APP" "$PCOPY" > "$OUT/probe-ditto.txt" 2>&1
  PEXE="$PCOPY/Contents/MacOS/$(basename "$EXE")"
  APPDIR="$(find "$PCOPY/Contents/Resources" -maxdepth 1 -name app -type d | head -1)"
  if [ -n "$APPDIR" ]; then cp "$HERE/m32probe.py" "$APPDIR/"; fi
  (cd "$SCRATCH/cwd" && tl 60 env THE_ONE_DATA_DIR="$SCRATCH/data" BRIEFCASE_MAIN_MODULE=m32probe "$PEXE" a b) \
    > "$OUT/stub-probe.txt" 2>&1; echo "rc=$?" >> "$OUT/stub-probe.txt"
  note "stub probe: $(grep -c '^PROBE' "$OUT/stub-probe.txt") PROBE lines (see stub-probe.txt)"
  grep '^PROBE' "$OUT/stub-probe.txt" | head -8 | while IFS= read -r l; do note "  $l"; done
fi

# ---- version -----------------------------------------------------------------
(cd "$SCRATCH/cwd" && tl 60 env THE_ONE_DATA_DIR="$SCRATCH/data" "$EXE" version) > "$OUT/version.txt" 2>&1
echo "rc=$?" >> "$OUT/version.txt"
note "version: $(head -1 "$OUT/version.txt") ($(tail -1 "$OUT/version.txt"))"
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
' "$HERE" "$OUT/doctor.txt" > "$OUT/doctor-score.json" 2> "$OUT/doctor-score.err"
note "doctor score: $(cat "$OUT/doctor-score.json")"
grep -q '"pass": true' "$OUT/doctor-score.json"; hard "gate 1 doctor" $?
grep -E "desktop shell|file watcher|window chrome|python interpreter|time zones|mcp sdk" "$OUT/doctor.txt" | while IFS= read -r l; do note "  $l"; done

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
trap stop_serve EXIT
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
note "gate 4: $(head -2 "$OUT/gate4-rotate.txt" | tr '\n' '|')"
grep -q "Library/Application Support/the-one/" "$OUT/gate4-rotate.txt"; hard "gate 4 data dir under Application Support" $?

# ---- best effort: a Finder-style launch (no arguments), the path a double-click takes ------
# Not scored (DD6: the runner's GUI session is not reliable). Records whether the bare launch
# starts the server (so `app` was chosen) and where the window gets to.
rm -rf "$SCRATCH/data-open"; mkdir -p "$SCRATCH/data-open"
tl 30 open -n --env THE_ONE_PORT=8490 --env THE_ONE_DATA_DIR="$SCRATCH/data-open" "$APP" > "$OUT/open.txt" 2>&1
echo "open rc=$?" >> "$OUT/open.txt"
OPENLIVE=1
for _ in $(seq 1 60); do
  if curl -fsS -m 2 http://127.0.0.1:8490/api/live > "$OUT/open-live.txt" 2>&1; then OPENLIVE=0; break; fi
  sleep 1
done
note "finder-style open: live=$OPENLIVE $(head -c 120 "$OUT/open-live.txt" 2>/dev/null)"
if [ "$OPENLIVE" = 0 ]; then
  CRED="$(tr -d '[:space:]' < "$SCRATCH/data-open/api-credential" 2>/dev/null)"
  curl -s -m 5 -X POST -H "Authorization: Bearer $CRED" http://127.0.0.1:8490/api/window/focus > "$OUT/open-focus.txt" 2>&1
  note "  window focus: $(head -c 120 "$OUT/open-focus.txt")"
fi
tl 60 screencapture -x "$OUT/open-screen.png" > "$OUT/screencapture.txt" 2>&1 || true
# stop the launched app by the PID that owns the port (found by us, not by name)
OPID="$(lsof -nP -iTCP:8490 -sTCP:LISTEN -t 2>/dev/null | head -1)"
if [ -n "$OPID" ]; then kill -TERM "$OPID" 2>/dev/null; sleep 3; kill -KILL "$OPID" 2>/dev/null; fi

note "== $LABEL done: $FAILS hard check(s) failed"
[ "$FAILS" = 0 ]
