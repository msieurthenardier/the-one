#!/usr/bin/env bash
# Premise driver for the hosted macOS runner (Mission 32 Flight 3 leg 2; DD9, DD10, DD11).
# Build-time tooling, never imported by the_one/. Records OBSERVATIONS, never PASS/FAIL.
#
#   probe.sh PRODUCT_APP PROBE_APP PRODUCT_BUNDLE_ID OUT_DIR
#
#     PRODUCT_APP         absolute path of "GleepGlorp AI.app" (built from main's desktop code)
#     PROBE_APP           absolute path of "M32 Probe.app" (delegate_probe.py frozen by probe.spec)
#     PRODUCT_BUNDLE_ID   today ai.gleepglorp.the-one (DD8 changes it in leg 6); recorded, and
#                         never used to address an app (apps are addressed by absolute path)
#     OUT_DIR             evidence directory; SUMMARY.txt gets one "P<n>: ..." row per premise
#
# Environment (all optional): M32_PRODUCT_PORT (default 8484, the product's own port; the runner
# is disposable), M32_SCALE (multiplies the series offsets and settle sleeps, default 1; the
# Linux rehearsal uses a small value; it never changes a bound), M32_EXE_PRODUCT / M32_EXE_PROBE
# (executable names under Contents/MacOS), M32_STOP_WAIT (seconds between TERM and KILL, 10).
#
# Structure: the main process runs each premise as a child (`bash probe.sh --run <Pn> ...`) under
# its own hard cap (tl), in the order P7, OTOOL, P8, P1, P4, P2, P3, P9, P5, P6 (P6 last: a
# Gatekeeper dialog is modal). So the worst case is the sum of the caps plus the stop waits, not
# a hand count of inner calls. Every external UI/OS call (osascript, screencapture, open, spctl,
# syspolicy_check, log show, lsappinfo) goes through tl <seconds>. Every process the driver
# starts is recorded by pid and stopped by that pid only (TERM, KILL after M32_STOP_WAIT s); a
# pid may be DISCOVERED by filtering ps on a bundle's absolute executable path.
#
# bash 3.2 (macOS /bin/bash is not used, but the runner's bash may be): no mapfile, no ${x,,},
# no [[ =~ ]] captures, no associative arrays, no arrays at all (so no empty-array expansion).
# shellcheck disable=SC2317  # functions are called indirectly (gate_wait, the --run dispatch)
set -u

SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# ---- bounds (seconds) -------------------------------------------------------------------
T_OPEN=20; T_SHOT=10; T_OSA=15; T_LSAPP=10; T_SPCTL=20; T_LOG=25; T_QUIT=15
T_DITTO=60; T_SIGN=40; T_SMALL=10; T_LNP=8
# premise caps (the table in README.md; the sum is the worst case)
CAP_P7=20; CAP_OTOOL=70; CAP_P8=120; CAP_P1=260; CAP_P4=110
CAP_P2=110; CAP_P3=180; CAP_P9=60; CAP_P5=80; CAP_P6=100

tl() { local n="$1"; shift; perl -e 'alarm shift @ARGV; exec @ARGV or die "exec failed: $!"' -- "$n" "$@"; }
now() { perl -MTime::HiRes=time -e 'printf "%.3f\n", time'; }
fsub() { awk -v a="$1" -v b="$2" 'BEGIN{printf "%.1f", b-a}'; }
SCALE="${M32_SCALE:-1}"
STOP_WAIT="${M32_STOP_WAIT:-10}"
sleep_s() { sleep "$(awk -v s="$1" -v k="$SCALE" 'BEGIN{printf "%.3f", s*k}')"; }
wait_until() { # $1 = absolute time (now() scale)
  local d
  d="$(awk -v t="$1" -v n="$(now)" 'BEGIN{d=t-n; if (d<0) d=0; printf "%.3f", d}')"
  sleep "$d"
}

# ---- the --run child ------------------------------------------------------------------
MODE=main
if [ "${1:-}" = "--run" ]; then MODE=child; PREMISE="${2:?premise}"; shift 2; fi

PRODUCT_APP="${1:?usage: probe.sh PRODUCT_APP PROBE_APP PRODUCT_BUNDLE_ID OUT_DIR}"
PROBE_APP="${2:?probe app}"
PRODUCT_BUNDLE_ID="${3:?bundle id}"
OUT="${4:?out dir}"
EXE_PRODUCT="${M32_EXE_PRODUCT:-the-one}"
EXE_PROBE="${M32_EXE_PROBE:-m32-probe}"
PRODUCT_EXE="$PRODUCT_APP/Contents/MacOS/$EXE_PRODUCT"
PROBE_EXE="$PROBE_APP/Contents/MacOS/$EXE_PROBE"
PORT="${M32_PRODUCT_PORT:-8484}"
BASE="http://127.0.0.1:$PORT"
PROBE_LOG="$HOME/Library/Logs/m32-probe/probe.log"
DATA_DIR="$HOME/Library/Application Support/the-one"
CRED_FILE="$DATA_DIR/api-credential"
SUMMARY="$OUT/SUMMARY.txt"
TRACK="$OUT/tracked.pids"
mkdir -p "$OUT"
touch "$TRACK" "$SUMMARY"

row() { # $1 = P-name  $2 = text (one line)
  local t
  t="$(printf '%s' "$2" | tr '\n' ' ' | tr -s ' ')"
  printf '%s: %s\n' "$1" "$t" >> "$SUMMARY"
  printf '%s: %s\n' "$1" "$t"
}
has_row() { grep -q "^$1:" "$SUMMARY" 2>/dev/null; }

# ---- pid registry ----------------------------------------------------------------------
track() { printf '%s %s\n' "$1" "$2" >> "$TRACK"; }
alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }
pids_for() { # $1 = absolute executable path: pids whose command line starts with it
  ps -axo pid=,command= 2>/dev/null | awk -v exe="$1" '
    { p = $1; sub(/^ *[0-9]+ +/, ""); if (index($0, exe) == 1) print p }'
}
stop_all() { # TERM every tracked pid still alive, wait up to STOP_WAIT, then KILL the rest
  local p l i any
  any=0
  while read -r p l; do
    if alive "$p"; then kill -TERM "$p" 2>/dev/null; any=1; fi
  done < "$TRACK"
  [ "$any" = 1 ] || return 0
  i=0
  while [ "$i" -lt "$STOP_WAIT" ]; do
    any=0
    while read -r p l; do alive "$p" && any=1; done < "$TRACK"
    [ "$any" = 0 ] && return 0
    sleep 1; i=$((i + 1))
  done
  while read -r p l; do
    if alive "$p"; then kill -KILL "$p" 2>/dev/null; echo "killed $p ($l)" >> "$OUT/quiesce.log"; fi
  done < "$TRACK"
}
stop_pid() { # one pid: TERM, KILL after STOP_WAIT
  local p="$1" i=0
  alive "$p" || return 0
  kill -TERM "$p" 2>/dev/null
  while [ "$i" -lt "$STOP_WAIT" ]; do alive "$p" || return 0; sleep 1; i=$((i + 1)); done
  kill -KILL "$p" 2>/dev/null
  echo "killed $p" >> "$OUT/quiesce.log"
}
listener() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1; }
quiesce() { # $1 = label; sets Q_NOTE when something was still there
  local l
  Q_NOTE=""
  stop_all
  l="$(listener)"
  if [ -n "$l" ]; then Q_NOTE="[$1: something (pid $l) listens on $PORT]"; echo "$1: listener $l" >> "$OUT/quiesce.log"; fi
}

# ---- small helpers -----------------------------------------------------------------------
runrc() { # $1 = file  $2 = bound  rest = command; sets RC; appends rc=N to the file
  local f="$1" b="$2"
  shift 2
  tl "$b" "$@" > "$f" 2>&1
  RC=$?
  echo "rc=$RC" >> "$f"
}
rcnote() { # $1 = rc  $2 = file: "rc=0" / "rc=142 (bound fired)" / "rc=1 err: first line"
  local e
  case "$1" in
    0) echo "rc=0" ;;
    142) echo "rc=142 (bound fired)" ;;
    *) e="$(grep -v '^rc=' "$2" 2>/dev/null | head -1 | cut -c1-110)"; echo "rc=$1 err: $e" ;;
  esac
}
cred() { tr -d '[:space:]' < "$CRED_FILE" 2>/dev/null; }
cred_prefix() { cred | cut -d. -f1; }
http() { # $1 = path  $2 = 1 for the bearer credential; prints "<code> <body>" or a reason
  local out rc c code body
  if [ "${2:-0}" = 1 ]; then
    c="$(cred)"
    [ -n "$c" ] || { echo "no-credential"; return 0; }
    out="$(curl -s -m 3 -w '\n%{http_code}' -H "Authorization: Bearer $c" "$BASE$1" 2>&1)"; rc=$?
  else
    out="$(curl -s -m 3 -w '\n%{http_code}' "$BASE$1" 2>&1)"; rc=$?
  fi
  [ "$rc" = 0 ] || { echo "curl-rc=$rc"; return 0; }
  code="$(printf '%s\n' "$out" | tail -1)"
  body="$(printf '%s\n' "$out" | sed '$d' | tr -d '\n' | cut -c1-200)"
  echo "$code $body"
}
http_post() { # $1 = path (authenticated POST, empty body)
  local c out rc
  c="$(cred)"
  [ -n "$c" ] || { echo "no-credential"; return 0; }
  out="$(curl -s -m 5 -X POST -w '\n%{http_code}' -H "Authorization: Bearer $c" "$BASE$1" 2>&1)"; rc=$?
  [ "$rc" = 0 ] || { echo "curl-rc=$rc"; return 0; }
  echo "$(printf '%s\n' "$out" | tail -1) $(printf '%s\n' "$out" | sed '$d' | tr -d '\n' | cut -c1-200)"
}
shot() { # $1 = png path -> sets SHOT_BYTES
  tl "$T_SHOT" screencapture -x "$1" > "$1.txt" 2>&1; SHOT_RC=$?
  SHOT_BYTES="$(wc -c < "$1" 2>/dev/null | tr -d ' ')"
  [ -n "$SHOT_BYTES" ] || SHOT_BYTES=0
}
front_pid() { # sets FRONT_ASN, FRONT_PID (empty when lsappinfo fails)
  FRONT_ASN="$(tl "$T_LSAPP" lsappinfo front 2>&1 | head -1)"
  FRONT_PID="$(tl "$T_LSAPP" lsappinfo info -only pid "$FRONT_ASN" 2>&1 | sed -n 's/.*"pid"=\([0-9][0-9]*\).*/\1/p' | head -1)"
}
front_note() { # $1 = expected pid -> "front=PID (matches)|(expected X)|(unknown: ASN)"
  front_pid
  if [ -z "$FRONT_PID" ]; then echo "front=unknown(${FRONT_ASN:-no lsappinfo output})"
  elif [ "$FRONT_PID" = "$1" ]; then echo "front=$FRONT_PID (the app)"
  else echo "front=$FRONT_PID (expected $1: mismatch)"; fi
}
gate_wait() { # $1 = seconds (polled every 0.25 s); rest = command that succeeds when up
  local n="$1" i=0 max
  shift
  max=$((n * 4))
  while [ "$i" -lt "$max" ]; do "$@" && return 0; sleep 0.25; i=$((i + 1)); done
  return 1
}

# ---- the local-network prompt (leg 3b) ---------------------------------------------------------------
# A "would like to find and connect to devices on your local network" alert is owned by a system
# agent, not by the app. This reads the alert's owner, window name, texts and buttons through System
# Events (one bounded call), and, when $2 is 1, presses Allow (else Don't Allow). Records only.
# Sets LNP_NOTE ("none seen" or the owner/texts/pressed button) and LNP_SEEN (1 when any alert
# window of those agents exists). The output file is "<tag>-lnp.txt".
lnp_check() { # $1 = tag  $2 = 1 to dismiss
  local f="$PDIR/$1-lnp.txt" click=false
  [ "${2:-0}" = 1 ] && click=true
  runrc "$f" "$T_LNP" osascript \
    -e "set doClick to $click" \
    -e 'set out to ""' \
    -e 'tell application "System Events"' \
    -e 'repeat with pn in {"UserNotificationCenter", "CoreServicesUIAgent", "SecurityAgent", "NotificationCenter", "universalaccessd"}' \
    -e 'if exists process pn then' \
    -e 'tell process pn' \
    -e 'repeat with w in windows' \
    -e 'set tx to ""' \
    -e 'set bn to ""' \
    -e 'try' \
    -e 'repeat with t in (static texts of w)' \
    -e 'set tx to tx & (value of t as text) & " / "' \
    -e 'end repeat' \
    -e 'end try' \
    -e 'try' \
    -e 'repeat with b in (buttons of w)' \
    -e 'set bn to bn & (name of b as text) & ","' \
    -e 'end repeat' \
    -e 'end try' \
    -e 'set pressed to "none"' \
    -e 'if doClick then' \
    -e 'try' \
    -e 'perform action "AXPress" of (first button of w whose name is "Allow")' \
    -e 'set pressed to "Allow"' \
    -e 'on error' \
    -e 'try' \
    -e 'perform action "AXPress" of (first button of w whose name begins with "Don")' \
    -e 'set pressed to "Dont Allow"' \
    -e 'end try' \
    -e 'end try' \
    -e 'end if' \
    -e 'set out to out & pn & " | " & (name of w as text) & " | " & tx & " | buttons " & bn & " | pressed " & pressed & linefeed' \
    -e 'end repeat' \
    -e 'end tell' \
    -e 'end if' \
    -e 'end repeat' \
    -e 'end tell' \
    -e 'return out'
  LNP_SEEN=0
  if [ "$RC" = 0 ] && grep -v '^rc=' "$f" | grep -q '|'; then LNP_SEEN=1; fi
  if [ "$LNP_SEEN" = 1 ]; then
    LNP_NOTE="$(grep -v '^rc=' "$f" | tr '\n' ';' | cut -c1-300)"
  else
    LNP_NOTE="none seen ($(rcnote "$RC" "$f"))"
  fi
}
window_state() { # $1 = pid: "windows=N visible=B frontmost=B pos=x,y size=wxh" through System Events
  local f="$PDIR/window-state-$$-$RANDOM.txt"
  runrc "$f" "$T_OSA" osascript \
    -e 'tell application "System Events"' \
    -e "set p to first process whose unix id is $1" \
    -e 'set r to "windows=" & (count of windows of p) & " visible=" & (visible of p) & " frontmost=" & (frontmost of p)' \
    -e 'try' \
    -e 'set {x, y} to position of window 1 of p' \
    -e 'set {w, h} to size of window 1 of p' \
    -e 'set r to r & " pos=" & x & "," & y & " size=" & w & "x" & h' \
    -e 'end try' \
    -e 'return r' \
    -e 'end tell'
  WS_NOTE="$(grep -v '^rc=' "$f" | head -1 | cut -c1-140)"
  [ -n "$WS_NOTE" ] || WS_NOTE="unreadable ($(rcnote "$RC" "$f"))"
  rm -f "$f"
}
focus_click() { # $1 = pid: raise the app and click the centre of its first window; sets FC_NOTE
  local f="$PDIR/focus-click-$$-$RANDOM.txt"
  runrc "$f" "$T_OSA" osascript \
    -e 'tell application "System Events"' \
    -e "set p to first process whose unix id is $1" \
    -e 'set frontmost of p to true' \
    -e 'delay 0.5' \
    -e 'set {x, y} to position of window 1 of p' \
    -e 'set {w, h} to size of window 1 of p' \
    -e 'click at {x + (w div 2), y + (h div 2)}' \
    -e 'return "clicked " & (x + (w div 2)) & "," & (y + (h div 2))' \
    -e 'end tell'
  FC_NOTE="$(grep -v '^rc=' "$f" | head -1 | cut -c1-100) $(rcnote "$RC" "$f")"
  rm -f "$f"
}

# ---- launching ----------------------------------------------------------------------
PDIR="$OUT"
prod_live() { curl -fsS -m 2 "$BASE/api/live" > /dev/null 2>&1; }
launch_product() { # $1 = tag; rest = extra open args. Sets LP_PID, LP_RC, LP_T0, LP_UP (0 = up)
  local tag="$1" before
  shift
  : > "$PDIR/$tag.stdout"; : > "$PDIR/$tag.stderr"
  before="$PDIR/$tag.before"; pids_for "$PRODUCT_EXE" > "$before"
  LP_T0="$(now)"
  runrc "$PDIR/$tag.open" "$T_OPEN" open -n --stdout "$PDIR/$tag.stdout" --stderr "$PDIR/$tag.stderr" "$@" "$PRODUCT_APP"
  LP_RC=$RC
  LP_PID=""
  if gate_wait 12 new_pid "$PRODUCT_EXE" "$before"; then
    LP_PID="$NEW_PID"; track "$LP_PID" "product:$tag"
  fi
  LP_UP=1
  if [ -n "$LP_PID" ]; then gate_wait 40 launch_up && LP_UP=0; fi
  [ "${LNP_SKIP:-0}" = 1 ] || lnp_check "$tag" 1
  return "$LP_UP"
}
launch_up() { alive "$LP_PID" && prod_live; }
new_pid() { # $1 = exe  $2 = before-file: sets NEW_PID to the first pid not in the file
  local p
  NEW_PID=""
  for p in $(pids_for "$1"); do
    if ! grep -qx "$p" "$2" 2>/dev/null; then NEW_PID="$p"; return 0; fi
  done
  return 1
}
launch_probe() { # $1 = tag; $2 = mode (wait|destroy); rest = extra open args (before --args)
  local tag="$1" mode="$2" before
  shift 2
  rm -f "$PROBE_LOG"
  before="$PDIR/$tag.before"; pids_for "$PROBE_EXE" > "$before"
  LB_T0="$(now)"
  runrc "$PDIR/$tag.open" "$T_OPEN" open -n "$@" "$PROBE_APP" --args "$mode"
  LB_RC=$RC
  LB_PID=""
  if gate_wait 12 new_pid "$PROBE_EXE" "$before"; then
    LB_PID="$NEW_PID"; track "$LB_PID" "probe:$tag"
  fi
  LB_UP=1
  if [ -n "$LB_PID" ]; then gate_wait 20 probe_up && LB_UP=0; fi
  [ "${LNP_SKIP:-0}" = 1 ] || lnp_check "$tag" 1
  return "$LB_UP"
}
probe_up() { alive "$LB_PID" && grep -q 'webview.start begin' "$PROBE_LOG" 2>/dev/null; }
save_probe_log() { cp "$PROBE_LOG" "$PDIR/$1-probe.log" 2>/dev/null || echo "(no probe log)" > "$PDIR/$1-probe.log"; }
wait_exit() { # $1 = pid  $2 = seconds (polled every 0.25 s); sets WE_SECS ("" when it did not exit)
  local t0 i=0 max
  t0="$(now)"
  max=$(($2 * 4))
  WE_SECS=""
  while [ "$i" -lt "$max" ]; do
    if ! alive "$1"; then WE_SECS="$(fsub "$t0" "$(now)")"; return 0; fi
    sleep 0.25; i=$((i + 1))
  done
  return 1
}
cap_hit() { # the child's ALRM/TERM handler: say so, clean up, leave
  has_row "$PREMISE" || row "$PREMISE" "premise cap of ${M32_CAP:-?} s reached; partial evidence in $OUT"
  stop_all
  exit 0
}

# ---- P7 ----------------------------------------------------------------------------------
p7() {
  mkdir -p "$OUT/P7"
  runrc "$OUT/P7/xcode-select.txt" "$T_SMALL" xcode-select -p
  local xr="$RC"
  runrc "$OUT/P7/python3.txt" "$T_SMALL" /usr/bin/python3 --version
  local pr="$RC"
  row P7 "xcode-select -p $(rcnote "$xr" "$OUT/P7/xcode-select.txt") path=$(head -1 "$OUT/P7/xcode-select.txt" | cut -c1-80); /usr/bin/python3 --version $(rcnote "$pr" "$OUT/P7/python3.txt") $(head -1 "$OUT/P7/python3.txt" | cut -c1-60)"
}

# ---- OTOOL: LC_BUILD_VERSION minos of every Mach-O in the product bundle ---------------------
otool_read() {
  local d="$OUT/OTOOL" t0 n=0 f
  mkdir -p "$d"
  t0="$SECONDS"
  # one `file` pass over every regular file; a path may hold spaces, hence -print0
  # shellcheck disable=SC2016  # $1 expands in the inner sh, on purpose
  tl 30 sh -c 'find "$1" -type f -print0 | xargs -0 file' sh "$PRODUCT_APP" > "$d/file.txt" 2> "$d/file.err"
  grep 'Mach-O' "$d/file.txt" | sed 's/: [^:]*Mach-O.*$//' | sort -u > "$d/macho.txt"
  : > "$d/minos.tsv"
  while IFS= read -r f; do
    [ "$((SECONDS - t0))" -lt 55 ] || { echo "stopped after $n files (time)" >> "$d/note.txt"; break; }
    tl 5 otool -l "$f" 2> /dev/null | awk -v f="$f" '
      /cmd LC_BUILD_VERSION/ { want = "minos" }
      /cmd LC_VERSION_MIN_MACOSX/ { want = "version" }
      want != "" && $1 == want { print $2 "\t" f; want = ""; found = 1 }
      END { if (!found) print "none\t" f }' >> "$d/minos.tsv"
    n=$((n + 1))
  done < "$d/macho.txt"
  # sortable value: major*10000 + minor*100 + patch
  awk -F'\t' '$1 != "none" { split($1, v, "."); printf "%d\t%s\t%s\n", v[1]*10000 + v[2]*100 + v[3], $1, $2 }' "$d/minos.tsv" | sort -n > "$d/sorted.tsv"
  { echo "minos  count"; cut -f2 "$d/sorted.tsv" | sort | uniq -c | awk '{print $2 "  " $1}'; } > "$d/table.txt"
  local max
  max="$(tail -1 "$d/sorted.tsv" | cut -f2)"
  echo "max=${max:-none}" > "$d/max.txt"
  tail -3 "$d/sorted.tsv" | cut -f2,3 >> "$d/max.txt"
  row OTOOL "$(wc -l < "$d/macho.txt" | tr -d ' ') Mach-O files, $n read; max minos=${max:-none}; table: $(tr '\n' ';' < "$d/table.txt" | tr -s ' ' | cut -c1-200); unreadable/no-version: $(grep -c '^none' "$d/minos.tsv")"
}

# ---- P8: the environment of an open-launched app ---------------------------------------------
env_forms() { # $1 = pid  $2 = dir/tag; sets ENV_ROW
  local pid="$1" t="$2" asn k v out
  runrc "$t.ps-eww" "$T_SMALL" ps eww -p "$pid"
  runrc "$t.ps-E" "$T_SMALL" ps -Eww -p "$pid" -o command=
  asn="$(tl "$T_LSAPP" lsappinfo find pid="$pid" 2>&1 | head -1)"
  runrc "$t.lsappinfo" "$T_LSAPP" lsappinfo info -only pid,bundlepath,LSEnvironment "$asn"
  ENV_ROW=""
  for k in PATH SHELL HOME TMPDIR M32_PROBE_ENV; do
    v="$(cat "$t.ps-eww" "$t.ps-E" 2> /dev/null | grep -o " $k=[^ ]*" | head -1 | cut -c1-90)"
    ENV_ROW="$ENV_ROW ${v:- $k=(not seen)}"
  done
  out="forms: ps-eww $(wc -c < "$t.ps-eww" | tr -d ' ')B, ps-E $(wc -c < "$t.ps-E" | tr -d ' ')B, lsappinfo $(wc -c < "$t.lsappinfo" | tr -d ' ')B;$ENV_ROW"
  ENV_ROW="$out"
}
p8() {
  local d="$OUT/P8"
  mkdir -p "$d"; PDIR="$d"
  if launch_product product-plain; then
    sleep_s 2
    env_forms "$LP_PID" "$d/product-plain"
    row P8 "product via open (no --env), pid $LP_PID: $ENV_ROW"
  else
    row P8 "product via open (no --env): not up (open rc=$LP_RC pid=${LP_PID:-none}); no capture"
  fi
  stop_pid "$LP_PID"
  if launch_probe probe-env wait --env M32_PROBE_ENV=1; then
    sleep_s 2
    env_forms "$LB_PID" "$d/probe-env"
    save_probe_log probe-env
    row P8 "probe via open --env M32_PROBE_ENV=1, pid $LB_PID: $ENV_ROW; probe log: $(grep -o 'env M32_PROBE_ENV=[^ ]*' "$d/probe-env-probe.log" | head -1) (does open --env pass variables)"
  else
    row P8 "probe via open --env: not up (open $(rcnote "$LB_RC" "$d/probe-env.open") pid=${LB_PID:-none}); no capture"
  fi
  stop_pid "$LB_PID"
}

# ---- P1: first paint --------------------------------------------------------------------------
series() { # $1 = tag  $2 = t0  $3 = cap seconds  $4 = with-api (1/0)  rest = marks (seconds after t0)
  local tag="$1" t0="$2" cap="$3" api="$4" m target el lv st tsv
  tsv="$PDIR/$tag-series.tsv"
  shift 4
  : > "$tsv"
  for m in "$@"; do
    target="$(awk -v t0="$t0" -v m="$m" -v k="$SCALE" 'BEGIN{printf "%.3f", t0 + m * k}')"
    wait_until "$target"
    el="$(fsub "$t0" "$(now)")"
    if awk -v e="$el" -v c="$cap" -v k="$SCALE" 'BEGIN{exit !(e > c * k)}'; then
      printf 'cut\t%s\t(past the %s s series cap)\n' "$m" "$cap" >> "$tsv"; break
    fi
    shot "$PDIR/$tag-$m.png"
    lv="-"; st="-"
    if [ "$api" = 1 ]; then lv="$(http /api/live 0)"; st="$(http /api/window/state 1)"; fi
    printf '%s\t%s\tshot_rc=%s\tbytes=%s\tlive=%s\tstate=%s\n' "$m" "$el" "$SHOT_RC" "$SHOT_BYTES" "$lv" "$st" >> "$tsv"
  done
}
first_live() { awk -F'\t' '$5 ~ /^live=200/ { print "+" $1 "s"; exit }' "$1"; }
quit_product() { # quits the tracked product LP_PID with `the-one quit`; sets QP_NOTE
  local f="$PDIR/$1-quit.txt"
  runrc "$f" "$T_QUIT" "$PRODUCT_EXE" quit
  if wait_exit "$LP_PID" 15; then QP_NOTE="quit $(rcnote "$RC" "$f"), exited in ${WE_SECS}s"
  else QP_NOTE="quit $(rcnote "$RC" "$f"), still alive after 15 s (stopped by pid)"; stop_pid "$LP_PID"; fi
}
p1() {
  local d="$OUT/P1" which
  mkdir -p "$d"; PDIR="$d"
  LNP_SKIP=1 # the series marks must not be delayed; the prompt is read after them
  for which in cold warm; do
    if [ "$which" = cold ]; then rm -rf "$DATA_DIR"; fi
    if launch_product "$which"; then
      series "$which" "$LP_T0" 45 1 1 2 3 5 10 20 30
      if [ "$which" = cold ]; then
        # PLN: read the alert (owner, texts, buttons) and screenshot it BEFORE dismissing it
        shot "$d/pln.png"
        lnp_check pln-read 0
        row PLN "after the product's first launch: alert windows $LNP_NOTE; screenshot ${SHOT_BYTES}B (pln.png)"
        lnp_check pln-dismiss 1
        row PLN "dismissal attempt: $LNP_NOTE"
      fi
      quit_product "$which"
      row P1 "$which: up (pid $LP_PID); first /api/live=200 at $(first_live "$d/$which-series.tsv"); marks: $(awk -F'\t' '{printf "+%s %s %s; ", $1, $4, ($5 ~ /^live=200/ ? "live" : "not-live")}' "$d/$which-series.tsv"); $QP_NOTE; stderr lines: $(wc -l < "$d/$which.stderr" | tr -d ' ')"
    else
      row P1 "$which: not up (open $(rcnote "$LP_RC" "$d/$which.open"), pid=${LP_PID:-none}); stderr: $(head -c 150 "$d/$which.stderr" | tr '\n' ' ')"
      stop_pid "$LP_PID"
    fi
    quiesce "P1/$which"
  done
  if launch_probe control wait; then
    series control "$LB_T0" 20 0 1 2 3 5 10
    sleep_s 1
    lnp_check control 1
    save_probe_log control
    row P1 "control (probe data-URL window, no server): up (pid $LB_PID); $(awk -F'\t' '{printf "+%s %sB; ", $1, $4}' "$d/control-series.tsv"); $(grep -o 'window loaded event[^)]*)' "$d/control-probe.log" | head -1)"
  else
    save_probe_log control
    row P1 "control: probe not up (open $(rcnote "$LB_RC" "$d/control.open"), pid=${LB_PID:-none})"
  fi
  stop_pid "$LB_PID"
}

# ---- P4: reopen and second instance -------------------------------------------------------------
p4() {
  local d="$OUT/P4" before r1 r2 np
  mkdir -p "$d"; PDIR="$d"
  if launch_probe probe wait; then
    pids_for "$PROBE_EXE" | sort > "$d/probe-pids-before.txt"
    runrc "$d/probe-open-a.txt" "$T_OPEN" open -a "$PROBE_APP"
    r1="$RC"; sleep_s 3
    pids_for "$PROBE_EXE" | sort > "$d/probe-pids-after.txt"
    save_probe_log probe
    row P4 "probe (route $(probe_route "$d/probe-probe.log")): open -a on the running app $(rcnote "$r1" "$d/probe-open-a.txt"); pids before [$(tr '\n' ' ' < "$d/probe-pids-before.txt")] after [$(tr '\n' ' ' < "$d/probe-pids-after.txt")]; reopen log: $(grep -c 'reopen:' "$d/probe-probe.log") line(s) $(grep 'reopen:' "$d/probe-probe.log" | head -1 | cut -c1-100)"
  else
    row P4 "probe: not up (open $(rcnote "$LB_RC" "$d/probe.open"), pid=${LB_PID:-none})"
  fi
  stop_pid "$LB_PID"
  if launch_product first; then
    pids_for "$PRODUCT_EXE" | sort > "$d/product-pids-before.txt"
    runrc "$d/product-open-a.txt" "$T_OPEN" open -a "$PRODUCT_APP"
    r2="$RC"; sleep_s 3
    pids_for "$PRODUCT_EXE" | sort > "$d/product-pids-after.txt"
    row P4 "product: open -a on the running app $(rcnote "$r2" "$d/product-open-a.txt"); pids before [$(tr '\n' ' ' < "$d/product-pids-before.txt")] after [$(tr '\n' ' ' < "$d/product-pids-after.txt")]; state: $(http /api/window/state 1)"
    # open -n: a second process that asks the first to focus and exits
    before="$d/second.before"; pids_for "$PRODUCT_EXE" > "$before"
    : > "$d/second.stdout"; : > "$d/second.stderr"
    runrc "$d/second.open" "$T_OPEN" open -n --stdout "$d/second.stdout" --stderr "$d/second.stderr" "$PRODUCT_APP"
    np=""
    if gate_wait 10 new_pid "$PRODUCT_EXE" "$before"; then np="$NEW_PID"; track "$np" "product:second"; fi
    if [ -n "$np" ]; then wait_exit "$np" 12 || true; fi
    sleep_s 1
    front_pid
    shot "$d/after-open-n.png"
    row P4 "product: open -n $(rcnote "$RC" "$d/second.open"): second pid=${np:-none} $(if [ -n "$np" ]; then if [ -n "$WE_SECS" ]; then echo "exited ${WE_SECS}s after appearing"; else echo "still alive after 12 s"; fi; fi); focus lines in the first's log: $(cat "$d/first.stdout" "$d/first.stderr" 2> /dev/null | grep -c 'window/focus'); second's own output ($(cat "$d/second.stdout" "$d/second.stderr" 2> /dev/null | wc -c | tr -d ' ') B): $(cat "$d/second.stdout" "$d/second.stderr" 2> /dev/null | tail -1 | cut -c1-100); lsappinfo front pid=${FRONT_PID:-unknown} (first=$LP_PID second=${np:-none}); screenshot ${SHOT_BYTES}B"
    stop_pid "$np"
  else
    row P4 "product: not up (open $(rcnote "$LP_RC" "$d/first.open"), pid=${LP_PID:-none})"
  fi
  stop_pid "$LP_PID"
}

# ---- P2: the quit Apple event, addressed by path ---------------------------------------------
quit_event() { # $1 = label  $2 = app path  $3 = pid  -> sets QE_NOTE
  local f="$PDIR/$1-quit-event.txt" osr
  if ! alive "$3"; then QE_NOTE="target pid $3 not alive; event NOT sent"; return 1; fi
  runrc "$f" "$T_OSA" osascript -e "tell application \"$2\" to quit"
  osr="$RC"
  if wait_exit "$3" 30; then QE_NOTE="osascript $(rcnote "$osr" "$f"); exited ${WE_SECS}s after the event returned"
  else QE_NOTE="osascript $(rcnote "$osr" "$f"); still alive after 30 s (stopped by pid)"; stop_pid "$3"; fi
}
p2() {
  local d="$OUT/P2"
  mkdir -p "$d"; PDIR="$d"
  if launch_product product; then
    quit_event product "$PRODUCT_APP" "$LP_PID"
    row P2 "product: $QE_NOTE; log tail: $(cat "$d/product.stdout" "$d/product.stderr" | tail -2 | tr '\n' ' ' | cut -c1-160)"
  else
    row P2 "product: not up (open $(rcnote "$LP_RC" "$d/product.open"), pid=${LP_PID:-none}); event not sent"
  fi
  stop_pid "$LP_PID"
  if launch_probe probe wait; then
    quit_event probe "$PROBE_APP" "$LB_PID"
    save_probe_log probe
    row P2 "probe (route $(probe_route "$d/probe-probe.log")): $QE_NOTE; log: terminate=$(grep -c 'terminate: applicationShouldTerminate_' "$d/probe-probe.log") reply=$(grep -c 'terminate: replying True' "$d/probe-probe.log") willTerminate=$(grep -c 'willTerminate' "$d/probe-probe.log"); signatures: $(grep -h 'signature' "$d/probe-probe.log" | cut -c11-90 | tr '\n' ';')"
  else
    save_probe_log probe
    row P2 "probe: not up (open $(rcnote "$LB_RC" "$d/probe.open"), pid=${LB_PID:-none}); event not sent"
  fi
  stop_pid "$LB_PID"
}

# ---- P3: System Events keystrokes ---------------------------------------------------------------
keystroke() { # $1 = key  $2 = out file; sets KS_RC
  runrc "$2" "$T_OSA" osascript -e "tell application \"System Events\" to keystroke \"$1\" using command down"
  KS_RC="$RC"
}
p3() {
  local d="$OUT/P3" fn s0 s1 wr qr ws0 ws1
  mkdir -p "$d"; PDIR="$d"
  # product: Cmd-W then Cmd-Q on one launch (the window hides to the tray; the app stays)
  if launch_product product; then
    runrc "$d/product-open-a.txt" "$T_OPEN" open -a "$PRODUCT_APP"
    sleep_s 2
    fn="$(front_note "$LP_PID")"
    s0="$(http /api/window/state 1)"; shot "$d/product-before.png"
    keystroke w "$d/product-w.txt"; wr="$KS_RC"; sleep_s 2
    s1="$(http /api/window/state 1)"; shot "$d/product-after-w.png"
    row P3 "product Cmd-W: $fn; state before: $s0; keystroke $(rcnote "$wr" "$d/product-w.txt"); state after: $s1; pid alive=$(alive "$LP_PID" && echo yes || echo no); shots ${SHOT_BYTES}B"
    if alive "$LP_PID"; then
      open_a_and_q product-q "$PRODUCT_APP" "$LP_PID"
      row P3 "product Cmd-Q: $fn2; keystroke $(rcnote "$qr" "$d/product-q.txt"); exited=$QEXIT; log tail: $(cat "$d/product.stdout" "$d/product.stderr" | tail -2 | tr '\n' ' ' | cut -c1-140)"
    fi
  else
    row P3 "product: not up (open $(rcnote "$LP_RC" "$d/product.open"), pid=${LP_PID:-none}); no keystroke"
  fi
  stop_pid "$LP_PID"
  # probe: a fresh launch per key (Cmd-W closes the window and may end the process)
  if launch_probe probe-w wait; then
    runrc "$d/probe-w-open-a.txt" "$T_OPEN" open -a "$PROBE_APP"
    sleep_s 2
    # focus first: raise the probe and click inside its window, then record its state
    focus_click "$LB_PID"; sleep_s 1
    fn="$(front_note "$LB_PID")"; window_state "$LB_PID"; ws0="$WS_NOTE"; shot "$d/probe-w-before.png"
    keystroke w "$d/probe-w.txt"; wr="$KS_RC"
    sleep_s 2
    if alive "$LB_PID"; then window_state "$LB_PID"; ws1="$WS_NOTE"; else ws1="process gone"; fi
    wait_exit "$LB_PID" 8 || true
    shot "$d/probe-w-after.png"; save_probe_log probe-w
    row P3 "probe Cmd-W after a click in the window ($FC_NOTE): $fn; state before: $ws0; keystroke $(rcnote "$wr" "$d/probe-w.txt"); state 2 s after: $ws1; exited=$(if [ -n "$WE_SECS" ]; then echo "yes after ${WE_SECS}s"; else echo no; fi); path=$(probe_path "$d/probe-w-probe.log"); route $(probe_route "$d/probe-w-probe.log"); shots before/after ${SHOT_BYTES}B"
  else
    row P3 "probe Cmd-W: not up (open $(rcnote "$LB_RC" "$d/probe-w.open"), pid=${LB_PID:-none})"
  fi
  stop_pid "$LB_PID"
  if launch_probe probe-q wait; then
    runrc "$d/probe-q-open-a.txt" "$T_OPEN" open -a "$PROBE_APP"
    sleep_s 2
    fn="$(front_note "$LB_PID")"
    keystroke q "$d/probe-q.txt"; qr="$KS_RC"
    wait_exit "$LB_PID" 12 || true
    save_probe_log probe-q
    row P3 "probe Cmd-Q (route $(probe_route "$d/probe-q-probe.log")): $fn; keystroke $(rcnote "$qr" "$d/probe-q.txt"); exited=$(if [ -n "$WE_SECS" ]; then echo "yes after ${WE_SECS}s"; else echo no; fi); path=$(probe_path "$d/probe-q-probe.log")"
  else
    row P3 "probe Cmd-Q: not up (open $(rcnote "$LB_RC" "$d/probe-q.open"), pid=${LB_PID:-none})"
  fi
  stop_pid "$LB_PID"
}
open_a_and_q() { # $1 = tag  $2 = app  $3 = pid: Cmd-Q keystroke, then wait for the exit
  local d="$OUT/P3"
  fn2="$(front_note "$3")"
  keystroke q "$d/$1.txt"; qr="$KS_RC"
  if wait_exit "$3" 15; then QEXIT="yes after ${WE_SECS}s"; else QEXIT="no (alive after 15 s)"; fi
}
probe_route() { # $1 = probe log: the delegate route (subclass, classAddMethods or none)
  grep -h "\] route: " "$1" 2> /dev/null | tail -1 | sed "s/.*route: //" | grep . || echo "unlogged"
}
probe_path() { # $1 = probe log: T (terminate ran), S (start returned alone) or none
  if grep -q 'terminate: applicationShouldTerminate_' "$1" 2> /dev/null; then echo "T (applicationShouldTerminate_ ran)"
  elif grep -q 'exit path S' "$1" 2> /dev/null; then echo "S (webview.start returned, no terminate)"
  else echo "none logged (still running or killed)"; fi
}

# ---- P9 (informational) --------------------------------------------------------------------------
p9() {
  local d="$OUT/P9" i=0
  mkdir -p "$d"; PDIR="$d"
  if launch_probe destroy destroy; then
    while [ "$i" -lt 28 ]; do
      grep -q 'destroy: webview.start returned\|did not return' "$PROBE_LOG" 2> /dev/null && break
      sleep 1; i=$((i + 1))
    done
    save_probe_log destroy
    row P9 "worker window.destroy() on the last window: $(grep -h 'destroy: webview.start' "$d/destroy-probe.log" | head -1 | cut -c11-120); process alive=$(alive "$LB_PID" && echo yes || echo no) (waited ${i}s of 28)"
  else
    save_probe_log destroy
    row P9 "probe not up (open $(rcnote "$LB_RC" "$d/destroy.open"), pid=${LB_PID:-none})"
  fi
  stop_pid "$LB_PID"
}

# ---- P5: replace the .app while it runs -----------------------------------------------------------------
p5() {
  local d="$OUT/P5" apps target old new_after marked orc d3 sg
  mkdir -p "$d"; PDIR="$d"
  if [ -w /Applications ]; then apps="/Applications"; else apps="$HOME/Applications"; mkdir -p "$apps"; fi
  target="$apps/GleepGlorp AI.app"
  marked="$d/marked/GleepGlorp AI.app"
  echo "applications dir: $apps (writable /Applications: $([ -w /Applications ] && echo yes || echo no))" > "$d/where.txt"
  runrc "$d/ditto-1.txt" "$T_DITTO" ditto "$PRODUCT_APP" "$target"
  if [ "$RC" != 0 ]; then row P5 "ditto to $apps $(rcnote "$RC" "$d/ditto-1.txt"); nothing to replace"; return 0; fi
  : > "$d/old.stdout"; : > "$d/old.stderr"
  pids_for "$target/Contents/MacOS/$EXE_PRODUCT" > "$d/old.before"
  runrc "$d/open-old.txt" "$T_OPEN" open -n --stdout "$d/old.stdout" --stderr "$d/old.stderr" "$target"
  orc="$RC"
  old=""
  if gate_wait 12 new_pid "$target/Contents/MacOS/$EXE_PRODUCT" "$d/old.before"; then old="$NEW_PID"; track "$old" "p5:old"; fi
  if [ -z "$old" ] || ! gate_wait 40 prod_live; then
    row P5 "installed copy not up (open $(rcnote "$orc" "$d/open-old.txt"), pid=${old:-none}); no replace test"
    stop_pid "$old"; rm -rf "$target"; return 0
  fi
  mkdir -p "$d/marked"
  runrc "$d/ditto-2.txt" "$T_DITTO" ditto "$PRODUCT_APP" "$marked"
  mkdir -p "$marked/Contents/Resources"; echo m32 > "$marked/Contents/Resources/m32-marker"
  runrc "$d/sign.txt" "$T_SIGN" codesign --force --deep -s - "$marked"
  sg="$RC"
  rm -rf "$target"
  runrc "$d/ditto-3.txt" "$T_DITTO" ditto "$marked" "$target"
  d3="$RC"
  sleep_s 1
  runrc "$d/open-new.txt" "$T_OPEN" open -a "$target"
  orc="$RC"
  sleep_s 4
  pids_for "$target/Contents/MacOS/$EXE_PRODUCT" > "$d/after.pids"
  new_after="$(tr '\n' ' ' < "$d/after.pids")"
  lsof -nP -p "$old" 2> /dev/null | grep -c m32-marker > "$d/old-marker-open.txt"
  row P5 "installed copy pid $old; replaced (rm -rf + ditto of a marked copy: ditto $(rcnote "$d3" "$d/ditto-3.txt"), sign $(rcnote "$sg" "$d/sign.txt")) while running; old alive=$(alive "$old" && echo yes || echo no); open -a $(rcnote "$orc" "$d/open-new.txt"); pids now [$new_after] (same pid = the old process answered, no relaunch); old process holds the marker open: $(cat "$d/old-marker-open.txt"); marker file present: $([ -f "$target/Contents/Resources/m32-marker" ] && echo yes || echo no); state: $(http /api/window/state 1)"
  stop_pid "$old"
  for new_after in $(pids_for "$target/Contents/MacOS/$EXE_PRODUCT"); do track "$new_after" "p5:after"; stop_pid "$new_after"; done
  rm -rf "$target" "$d/marked"
}

# ---- P6: Gatekeeper and translocation (runs LAST) -------------------------------------------------------
p6() {
  local d="$OUT/P6" q copy found ts p
  mkdir -p "$d"; PDIR="$d"
  mkdir -p "$HOME/Downloads"
  copy="$HOME/Downloads/GleepGlorp AI.app"
  runrc "$d/ditto.txt" "$T_DITTO" ditto "$PRODUCT_APP" "$copy"
  if [ "$RC" != 0 ]; then row P6 "ditto to ~/Downloads $(rcnote "$RC" "$d/ditto.txt"); no quarantine test"; return 0; fi
  ts="$(printf '%x' "$(date +%s)")"
  runrc "$d/xattr.txt" "$T_SMALL" xattr -w com.apple.quarantine "0083;$ts;Safari;" "$copy"
  runrc "$d/spctl.txt" "$T_SPCTL" spctl -a -vv -t exec "$copy"
  q="spctl $(rcnote "$RC" "$d/spctl.txt") $(grep -v '^rc=' "$d/spctl.txt" | head -2 | tr '\n' ' ' | cut -c1-140)"
  if command -v syspolicy_check > /dev/null 2>&1; then
    runrc "$d/syspolicy.txt" "$T_SPCTL" syspolicy_check distribution "$copy"
    q="$q; syspolicy_check $(rcnote "$RC" "$d/syspolicy.txt")"
  else
    q="$q; syspolicy_check absent"
  fi
  : > "$d/launch.stdout"; : > "$d/launch.stderr"
  pids_for "$copy/Contents/MacOS/$EXE_PRODUCT" > "$d/launch.before"
  runrc "$d/open.txt" 30 open --stdout "$d/launch.stdout" --stderr "$d/launch.stderr" "$copy"
  q="$q; open $(rcnote "$RC" "$d/open.txt")"
  sleep_s 8
  shot "$d/after-open.png"
  # the launched process: its own path, or an AppTranslocation path
  found=""
  for p in $(pids_for "$copy/Contents/MacOS/$EXE_PRODUCT"); do track "$p" "p6:direct"; found="$found $p(direct)"; done
  ps -axo pid=,command= 2> /dev/null | awk '/AppTranslocation/ && /Contents\/MacOS\// { print $1 }' > "$d/translocated.pids"
  while read -r p; do track "$p" "p6:translocated"; found="$found $p(translocated)"; done < "$d/translocated.pids"
  ps -axo pid=,command= 2> /dev/null | awk '/AppTranslocation/ && /Contents\/MacOS\// { sub(/^ *[0-9]+ +/, ""); print substr($0, 1, 160) }' > "$d/translocated.paths"
  runrc "$d/dismiss.txt" "$T_OSA" osascript -e 'tell application "System Events" to tell process "CoreServicesUIAgent" to click button "Done" of window 1'
  q="$q; dialog dismiss $(rcnote "$RC" "$d/dismiss.txt")"
  runrc "$d/logshow.txt" "$T_LOG" log show --last 1m --style compact --predicate 'process == "syspolicyd" OR process == "CoreServicesUIAgent"'
  row P6 "$q; process after open:${found:- none}; path: $(head -1 "$d/translocated.paths" | cut -c1-120); screenshot ${SHOT_BYTES}B; log show $(rcnote "$RC" "$d/logshow.txt")"
  stop_all
  rm -rf "$copy"
}

# ---- main ---------------------------------------------------------------------------------------------------
if [ "$MODE" = child ]; then
  trap cap_hit ALRM TERM INT
  trap 'stop_all' EXIT
  case "$PREMISE" in
    P7) p7 ;; OTOOL) otool_read ;; P8) p8 ;; P1) p1 ;; P4) p4 ;; P2) p2 ;; P3) p3 ;;
    P9) p9 ;; P5) p5 ;; P6) p6 ;;
    *) echo "probe.sh: unknown premise $PREMISE" >&2; exit 2 ;;
  esac
  exit 0
fi

# the main process: always runs every premise, in this order, each under its own cap
for need in "$PRODUCT_EXE" "$PROBE_EXE"; do
  [ -x "$need" ] || { echo "probe.sh: missing executable: $need" >&2; exit 2; }
done
trap 'stop_all; exit 0' EXIT TERM INT ALRM
{
  echo "probe.sh started $(date -u +%Y-%m-%dT%H:%M:%SZ) product=$PRODUCT_APP probe=$PROBE_APP bundle_id=$PRODUCT_BUNDLE_ID port=$PORT scale=$SCALE"
  echo "credential prefix (if any): $(cred_prefix)"
} > "$OUT/header.txt"
for entry in P7:$CAP_P7 OTOOL:$CAP_OTOOL P8:$CAP_P8 P1:$CAP_P1 P4:$CAP_P4 P2:$CAP_P2 P3:$CAP_P3 P9:$CAP_P9 P5:$CAP_P5 P6:$CAP_P6; do
  name="${entry%%:*}"; cap="${entry##*:}"
  quiesce "$name start"
  start_note="$Q_NOTE"
  t0="$SECONDS"
  M32_CAP="$cap" tl "$cap" bash "$SELF" --run "$name" "$PRODUCT_APP" "$PROBE_APP" "$PRODUCT_BUNDLE_ID" "$OUT" > "$OUT/$name.log" 2>&1
  rc=$?
  has_row "$name" || row "$name" "no row written (child rc=$rc after $((SECONDS - t0)) s; cap ${cap} s); see $name.log"
  quiesce "$name end"
  [ -z "$start_note$Q_NOTE" ] || row "$name" "quiescence: $start_note $Q_NOTE"
done
echo "== done in $SECONDS s" | tee -a "$SUMMARY"
exit 0
