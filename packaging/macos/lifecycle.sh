#!/usr/bin/env bash
# Lifecycle driver for the hosted macOS runner (Mission 32 Flight 3 leg 6; DD2-DD5, DD13).
# Build-time tooling, never imported by the_one/. Unlike probe/probe.sh (observations only), this
# JUDGES: every step writes one "PASS <id> ..." or "FAIL <id> ..." row to SUMMARY.txt, with the
# evidence in the row. The workflow's final check fails the job on any line that starts with FAIL.
#
#   lifecycle.sh APP_N APP_N1 APP_ID VERSION_N VERSION_N1 OUT_DIR
#
#     APP_N / APP_N1   absolute paths of the built "GleepGlorp AI.app" for versions N and N+1 (the
#                      build-directory copies; they are copied to $M32_INSTALL_DIR, never launched)
#     APP_ID           the bundle id (build.env APP_ID); the quit Apple event addresses it
#     VERSION_N/N1     what /api/window/state and /api/info must report after each install
#     OUT_DIR          evidence directory; SUMMARY.txt gets the rows, L<n>/ the per-step files
#
# Environment (all optional): M32_INSTALL_DIR (/Applications), M32_PRODUCT_PORT (8484, the
# product's own port; the runner is disposable and the Linux rehearsal uses another),
# M32_DATA_DIR (the default data dir), M32_APP_LOG ("$HOME/Library/Logs/GleepGlorp AI/app.log"),
# M32_DMG_N (the N .dmg: L0 mounts it and copies the .app out; absent -> the build-dir copy, said in
# the L0 row; N+1 has no .dmg, so L9 installs it from the build dir), M32_CRASH_DIR ("$HOME/Library/Logs/DiagnosticReports"), M32_EXE_PRODUCT (the-one),
# M32_BUDGET (a step is skipped once this many seconds have passed; the 850 default is unchanged by
# L9b because the workflow always passes its bound minus 200 s, now up to 1250 s; only the rehearsal
# uses the default), M32_L9B_PORT (the drawer step's own port, 8486), M32_SCALE (multiplies
# the series offsets and settle sleeps; the rehearsal uses a small value; it never changes a
# bound), M32_STOP_WAIT (seconds between TERM and KILL, 8).
#
# Steps (leg 6 / DD13), each against the app installed in $M32_INSTALL_DIR, run as a child
# (`bash lifecycle.sh --run L<n> ...`) under its own hard cap, so the worst case is the sum of the
# caps plus the install, not a count of inner calls. A step that finds no app running starts one
# (so one failure does not cascade into nine) and says so in its evidence:
#   L1 launch + install route + first-paint series   L2 close button   L3 reopen (+ Cmd-W, info)
#   L4 second process   L5 geometry across Cmd-Q   L6 quit Apple event   L7 the-one quit --wait
#   L8 Cmd-Q keystroke   L9 upgrade to N+1 with data   L9b the GleepGlorp drawer (M36 F3 L9)
#   L10 trash (data survives)
# L9b runs between L9 and L10 (L10 deletes the app): it quits the running N+1, launches a SECOND,
# throwaway instance of it on its own port (M32_L9B_PORT, 8486) and scratch data dir under its step
# directory, in dev mode, seeds a scripted mock GleepGlorp (scripts/gleepglorp_drawer_seed.py, run with
# the runner's python3; the desktop app creates the credential), drives Jump to (Cmd K) to Settings and
# then "Ask GleepGlorp", sends one message, waits for `--check-fill` to exit 0 (the fill reached
# `filled`, no agent was created) and presses Esc. The proof is the HTTP API plus screenshots; focus
# after Esc and the CSS width (inferred from the window size) are screenshot-only. L1-L10 are unchanged.
# The log lines asserted are exactly leg 4's AC5 table (flight-log.md, ### macos-dock-mode).
#
# Rules: the log is read from the entry shim's redirect by BYTE OFFSET per step; apps are
# addressed by path (open -a PATH), System Events by `first process whose unix id is <pid>`;
# pids come from /api/window/state and are stopped only by that pid; every external call goes
# through tl <seconds>.
#
# bash 3.2 (the runner's bash may be): no mapfile, no ${x,,}, no [[ =~ ]] captures, no
# associative arrays, no arrays at all (so no empty-array expansion).
# shellcheck disable=SC2317  # functions are called indirectly (the --run dispatch)
set -u

SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
# shellcheck source=lib.sh
. "$(dirname "$SELF")/lib.sh"

# ---- bounds (seconds) -------------------------------------------------------------------
T_OPEN=20; T_SHOT=10; T_OSA=15; T_LSAPP=10; T_QUIT=30; T_CLI=90; T_DITTO=120
# step caps (the table in README.md; the sum plus the install is the worst case)
# (M32_CAP_Ln overrides one, for the rehearsal of a cap firing)
CAP_L1="${M32_CAP_L1:-110}"; CAP_L2="${M32_CAP_L2:-50}"; CAP_L3="${M32_CAP_L3:-70}"
CAP_L4="${M32_CAP_L4:-50}"; CAP_L5="${M32_CAP_L5:-200}"; CAP_L6="${M32_CAP_L6:-130}"
CAP_L7="${M32_CAP_L7:-120}"; CAP_L8="${M32_CAP_L8:-130}"; CAP_L9="${M32_CAP_L9:-190}"
CAP_L10="${M32_CAP_L10:-70}"
CAP_L9B="${M32_CAP_L9B:-180}" # M36 F3 L9: the drawer step (stop N+1, own instance, seed, drive, quit)

MODE=main
if [ "${1:-}" = "--run" ]; then MODE=child; STEP="${2:?step}"; shift 2; fi

APP_N="${1:?usage: lifecycle.sh APP_N APP_N1 APP_ID VERSION_N VERSION_N1 OUT_DIR}"
APP_N1="${2:?app N+1}"
APP_ID="${3:?bundle id}"
VERSION_N="${4:?version N}"
VERSION_N1="${5:?version N+1}"
OUT="${6:?out dir}"
INSTALL_DIR="${M32_INSTALL_DIR:-/Applications}"
INSTALLED="$INSTALL_DIR/$(basename "$APP_N")"
EXE_NAME="${M32_EXE_PRODUCT:-the-one}"
EXE="$INSTALLED/Contents/MacOS/$EXE_NAME"
PORT="${M32_PRODUCT_PORT:-8484}"
BASE="http://127.0.0.1:$PORT"
DATA_DIR="${M32_DATA_DIR:-$HOME/Library/Application Support/the-one}"
CRED_FILE="$DATA_DIR/api-credential"
APP_LOG="${M32_APP_LOG:-$HOME/Library/Logs/GleepGlorp AI/app.log}"
CRASH_DIR="${M32_CRASH_DIR:-$HOME/Library/Logs/DiagnosticReports}"
BUDGET="${M32_BUDGET:-850}"
STOP_WAIT="${M32_STOP_WAIT:-8}"
# a non-default port or data dir has to reach the app: open --env, and the CLI's own environment
CUSTOM=0
if [ "$PORT" != 8484 ] || [ -n "${M32_DATA_DIR:-}" ]; then CUSTOM=1; fi
SUMMARY="$OUT/SUMMARY.txt"
TRACK="$OUT/tracked.pids"
PDIR="$OUT"
mkdir -p "$OUT"
touch "$TRACK" "$SUMMARY"

# the exact log lines (leg 4's AC5 table); grep -F substrings
T_INSTALL='macos dock: delegate installed (route=subclass, app nap activity held)'
T_LOADED='macos: main window shown after page load'
T_LOADED_ANY='macos: main window shown after'
T_HIDE='dock: window hidden on close'
T_REOPEN='reopen: decision=show'
T_RECV='terminate: applicationShouldTerminate received (decision=drain-then-reply)'
T_DSTART='terminate: drain started'
T_DDONE='terminate: drain done in'
T_REPLY='terminate: reply sending'
T_WILL='terminate: applicationWillTerminate (AppKit exiting)'

# ---- rows ------------------------------------------------------------------------------------
emit() { # $1 = PASS|FAIL|INFO  $2 = id  $3 = text (one line)
  local t
  t="$(printf '%s' "$3" | tr '\n' ' ' | tr -s ' ' | cut -c1-900)"
  printf '%s %s %s\n' "$1" "$2" "$t" >> "$SUMMARY"
  printf '%s %s %s\n' "$1" "$2" "$t"
}
has_row() { grep -qE "^(PASS|FAIL) $1 " "$SUMMARY" 2> /dev/null; }
S_OK=1; S_EV=""; SD="$OUT"
step_begin() { S_OK=1; S_EV=""; SD="$OUT/$1"; mkdir -p "$SD"; }
# chk LABEL RC: RC is a variable or a literal 0/1, never a bare $? next to a command substitution
chk() {
  if [ "$2" = 0 ]; then S_EV="$S_EV [ok: $1]"; else S_EV="$S_EV [BAD: $1]"; S_OK=0; fi
}
inf() { S_EV="$S_EV [$1]"; }
yes0() { if "$@"; then echo 0; else echo 1; fi; } # runs a test; prints 0 when it held (for chk)
step_end() { # $1 = id  $2 = title
  if [ "$S_OK" = 1 ]; then emit PASS "$1" "$2:$S_EV"; else emit FAIL "$1" "$2:$S_EV"; fi
}

# ---- the app's HTTP surface --------------------------------------------------------------
live() { curl -fsS -m 2 "$BASE/api/live" > /dev/null 2>&1; }
api_get() { curl -s -m 5 -H "Authorization: Bearer $(cred)" "$BASE$1" 2> /dev/null; }
api_post() { # $1 = path  $2 = json body; prints "<code> <body>"
  local out rc
  out="$(curl -s -m 8 -X POST -w '\n%{http_code}' -H "Authorization: Bearer $(cred)" \
    -H 'Content-Type: application/json' -d "$2" "$BASE$1" 2>&1)"; rc=$?
  [ "$rc" = 0 ] || { echo "curl-rc=$rc"; return 0; }
  echo "$(printf '%s\n' "$out" | tail -1) $(printf '%s\n' "$out" | sed '$d' | tr -d '\n' | cut -c1-160)"
}
jget() { # $1 = key: the JSON object on stdin -> value (true/false/null for the JSON ones)
  python3 -c '
import json, sys
try:
    v = json.load(sys.stdin).get(sys.argv[1])
except Exception:
    sys.exit(0)
print("true" if v is True else "false" if v is False else "null" if v is None else v)
' "$1" 2> /dev/null
}
sget() { api_get /api/window/state | jget "$1"; }
cur_pid() { local p; p="$(sget pid)"; case "$p" in '' | *[!0-9]*) echo "" ;; *) echo "$p" ;; esac; }
have_pid() { [ -n "$(cur_pid)" ]; }
poll_state() { # $1 = key  $2 = wanted value  $3 = seconds; sets POLL_VAL
  local i=0 max=$(($3 * 4))
  POLL_VAL=""
  while [ "$i" -le "$max" ]; do
    POLL_VAL="$(sget "$1")"
    [ "$POLL_VAL" = "$2" ] && return 0
    sleep 0.25; i=$((i + 1))
  done
  return 1
}
listeners() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2> /dev/null | sort -u | tr '\n' ' ' | sed 's/ *$//'; }

# ---- the app's log, by byte offset ---------------------------------------------------------
log_size() { local n; n="$(wc -c < "$APP_LOG" 2> /dev/null | tr -d ' ')"; echo "${n:-0}"; }
log_seg() { tail -c +"$(($1 + 1))" "$APP_LOG" > "$2" 2> /dev/null || : > "$2"; }
wait_log() { # $1 = offset  $2 = text  $3 = seconds
  local i=0 max=$(($3 * 4)) f="$SD/.waitlog"
  while [ "$i" -le "$max" ]; do
    log_seg "$1" "$f"
    grep -qF -- "$2" "$f" && return 0
    sleep 0.25; i=$((i + 1))
  done
  return 1
}
seg_order() { # $1 = segment file; rest = substrings that must appear in this order; sets ORD_MISS
  local f="$1" t n last=0
  shift
  ORD_MISS=""
  for t in "$@"; do
    n="$(grep -nF -- "$t" "$f" | awk -F: -v l="$last" '$1 > l { print $1; exit }')"
    if [ -z "$n" ]; then ORD_MISS="$t"; return 1; fi
    last="$n"
  done
  return 0
}

# ---- crash reports -------------------------------------------------------------------------
crash_list() {
  # shellcheck disable=SC2012  # globs with an expected-empty result; names are the OS's own
  ls -1 "$CRASH_DIR"/*the-one*.ips "$CRASH_DIR"/*GleepGlorp*.ips \
    "$CRASH_DIR"/Retired/*the-one*.ips "$CRASH_DIR"/Retired/*GleepGlorp*.ips 2> /dev/null | sort -u
}
crash_dirs_state() { # sets CRASH_NOTE (what was readable) and returns 1 when a directory exists but cannot be listed
  local d bad=0
  CRASH_NOTE=""
  for d in "$CRASH_DIR" "$CRASH_DIR/Retired"; do
    if [ ! -d "$d" ]; then
      CRASH_NOTE="$CRASH_NOTE [$d: absent]"
    elif ls -1 "$d" > /dev/null 2>&1; then
      CRASH_NOTE="$CRASH_NOTE [$d: readable]"
    else
      CRASH_NOTE="$CRASH_NOTE [$d: UNREADABLE]"; bad=1
    fi
  done
  return "$bad"
}
crash_new() { crash_list | comm -13 "$1" - 2> /dev/null; } # $1 = the list taken before

# ---- launching and driving the app -----------------------------------------------------------
open_run() { # $1 = out file; rest = open's own arguments (flags, then -a PATH). Sets RC
  local f="$1"
  shift
  if [ "$CUSTOM" = 1 ] && [ "${DEV_MODE:-0}" = 1 ]; then
    # L9b only: its own instance runs in dev mode (the mock provider is dev-mode gated)
    runrc "$f" "$T_OPEN" open "$@" --env "THE_ONE_PORT=$PORT" --env "THE_ONE_DATA_DIR=$DATA_DIR" \
      --env "THE_ONE_DEV_MODE=true"
  elif [ "$CUSTOM" = 1 ]; then
    runrc "$f" "$T_OPEN" open "$@" --env "THE_ONE_PORT=$PORT" --env "THE_ONE_DATA_DIR=$DATA_DIR"
  else
    runrc "$f" "$T_OPEN" open "$@"
  fi
}
cli_run() { # $1 = bound; rest = a command run with the port and data dir the app was given
  local n="$1"
  shift
  if [ "$CUSTOM" = 1 ]; then
    tl "$n" env "THE_ONE_PORT=$PORT" "THE_ONE_DATA_DIR=$DATA_DIR" "$@"
  else
    tl "$n" "$@"
  fi
}
launch_app() { # $1 = tag; L_SERIES=1 takes the first-paint series. Sets L_PID, L_SECS, L_RC; rc 0 when up
  local tag="$1" t0 off
  t0="$(now)"
  open_run "$SD/$tag.open" -a "$INSTALLED"
  L_RC=$RC
  if [ "${L_SERIES:-0}" = 1 ]; then
    : > "$SD/series.tsv"
    for off in 1 3 5; do
      wait_until "$(awk -v t="$t0" -v o="$off" -v k="$SCALE" 'BEGIN{printf "%.3f", t + o * k}')"
      shot "$SD/first-paint-+${off}s.png"
      printf '+%ss bytes=%s live=%s visible=%s;' "$off" "$SHOT_BYTES" \
        "$(live && echo 200 || echo no)" "$(sget visible)" >> "$SD/series.tsv"
    done
  fi
  L_PID=""
  if gate_wait 60 live; then
    gate_wait 10 have_pid && L_PID="$(cur_pid)"
  fi
  [ -z "$L_PID" ] || track "$L_PID" "app:$tag"
  L_SECS="$(fsub "$t0" "$(now)")"
  [ -n "$L_PID" ]
}
ensure_app() { # the app is running (started when a step before it left none); sets APP_PID, ENS_NOTE
  ENS_NOTE=""
  APP_PID="$(cur_pid)"
  if [ -n "$APP_PID" ] && live; then return 0; fi
  L_SERIES=0
  if launch_app ensure; then
    APP_PID="$L_PID"; ENS_NOTE="started the app first (pid $APP_PID, up in ${L_SECS}s)"
    poll_state visible true 25 || ENS_NOTE="$ENS_NOTE; window not visible after 25 s"
    return 0
  fi
  APP_PID=""; ENS_NOTE="could not start the app (open $(rcnote "$L_RC" "$SD/ensure.open"))"
  return 1
}
ensure_visible() { # a hidden window is brought back with open -a before a step that needs it
  [ "$(sget visible)" = true ] && return 0
  open_run "$SD/ensure-visible.open" -a "$INSTALLED"
  poll_state visible true 15
}
sys_events() { # $1 = out file  $2 = pid  rest = AppleScript lines (-e ...) run with `p` the process
  local f="$1" pid="$2"
  shift 2
  runrc "$f" "$T_OSA" osascript \
    -e 'tell application "System Events"' \
    -e "set p to first process whose unix id is $pid" \
    "$@" \
    -e 'end tell'
}
ax_parse() { # $1 = window_state's note: sets AX_X AX_Y AX_W AX_H (empty when unreadable)
  AX_X="$(printf '%s' "$1" | sed -n 's/.*pos=\(-*[0-9][0-9]*\),.*/\1/p')"
  AX_Y="$(printf '%s' "$1" | sed -n 's/.*pos=-*[0-9][0-9]*,\(-*[0-9][0-9]*\).*/\1/p')"
  AX_W="$(printf '%s' "$1" | sed -n 's/.*size=\([0-9][0-9]*\)x.*/\1/p')"
  AX_H="$(printf '%s' "$1" | sed -n 's/.*size=[0-9][0-9]*x\([0-9][0-9]*\).*/\1/p')"
}
exit_note() { if [ -n "${WE_SECS:-}" ]; then echo "${WE_SECS} s"; else echo "still alive"; fi; } # after wait_exit
absdiff() { awk -v a="$1" -v b="$2" 'BEGIN{d=a-b; if (d<0) d=-d; print d}'; }
within() { [ "$(absdiff "$1" "$2")" -le "$3" ]; } # $1 $2 = the two values  $3 = tolerance
cmd_q() { # $1 = out file  $2 = pid: raise the app and press Cmd-Q through System Events
  sys_events "$1" "$2" -e 'set frontmost of p to true' -e 'delay 0.5' \
    -e 'keystroke "q" using command down'
}
drain_checks() { # $1 = log offset  $2 = pid  $3 = tag: the path-T quit asserts of steps 6-8
  local seg="$SD/$3.log" rc crash
  wait_exit "$2" 70
  rc=$?
  chk "exited within 70 s ($(exit_note))" "$rc"
  sleep_s 3
  log_seg "$1" "$seg"
  seg_order "$seg" "$T_RECV" "$T_DSTART" "$T_DDONE" "$T_REPLY"
  rc=$?
  chk "log: received, drain started, drain done, reply sending, in order${ORD_MISS:+ (missing: $ORD_MISS)}" "$rc"
  if grep -qF -- "$T_WILL" "$seg"; then inf "applicationWillTerminate logged"; else inf "applicationWillTerminate not logged"; fi
  if live; then chk "/api/live refused after the exit" 1; else chk "/api/live refused after the exit" 0; fi
  sleep_s 5
  crash="$(crash_new "$SD/crash-before.txt" | tr '\n' ' ')"
  crash_dirs_state; rc=$?
  chk "crash report directories readable:$CRASH_NOTE" "$rc"
  if [ -z "$crash" ]; then chk "no new crash report" 0; else chk "no new crash report ($crash)" 1; fi
}

# ---- L1 ------------------------------------------------------------------------------------
l1() {
  step_begin L1
  local mark pid p rc
  mark="$(log_size)"
  L_SERIES=1
  launch_app launch
  rc=$?
  chk "started: pid ${L_PID:-none} in ${L_SECS}s (open $(rcnote "$L_RC" "$SD/launch.open"))" "$rc"
  inf "first paint series: $(cat "$SD/series.tsv" 2> /dev/null)"
  pid="$L_PID"
  # the route line first: if the delegate did not install, every later row is explained by it
  wait_log "$mark" "$T_INSTALL" 15
  chk "log: $T_INSTALL" $?
  # the main window must have waited for its page (HAT P1): the fallback line means the page
  # never reported loaded and the splash was covered by an unpainted window
  wait_log "$mark" "$T_LOADED_ANY" 35
  chk "log: $T_LOADED_ANY" $?
  log_seg "$mark" "$SD/.loaded"
  if grep -qF -- "$T_LOADED" "$SD/.loaded"; then rc=0; else rc=1; fi
  chk "log: $T_LOADED ($(grep -F -- "$T_LOADED_ANY" "$SD/.loaded" | tail -1 | cut -c1-120))" "$rc"
  poll_state visible true 25
  chk "visible: true (read $POLL_VAL)" $?
  p="$(sget tray)"
  chk "tray: dock (read $p)" "$(yes0 test "$p" = dock)"
  p="$(sget version)"
  chk "version $VERSION_N (read $p)" "$(yes0 test "$p" = "$VERSION_N")"
  inf "mode=$(sget mode)"
  p="$(pids_for "$EXE" | tr '\n' ' ')"
  case " $p" in
    *" $pid "*) rc=0 ;;
    *) rc=1 ;;
  esac
  [ -n "$pid" ] || rc=1
  chk "state pid ${pid:-none} is a process under $INSTALLED (pids: $p)" "$rc"
  step_end L1 "launch from the installed app"
}

# ---- L2 ------------------------------------------------------------------------------------
l2() {
  step_begin L2
  local mark pid
  ensure_app; chk "app running${ENS_NOTE:+ ($ENS_NOTE)}" $?
  pid="$APP_PID"
  if [ -n "$pid" ]; then
    ensure_visible || inf "window was not visible before the click"
    mark="$(log_size)"
    sys_events "$SD/close.txt" "$pid" -e 'click button 1 of window 1 of p'
    chk "close button AXPress ($(rcnote "$RC" "$SD/close.txt"))" "$RC"
    poll_state visible false 10
    chk "visible: false after the close (read $POLL_VAL)" $?
    alive "$pid"
    chk "process $pid alive" $?
    live
    chk "/api/live 200" $?
    wait_log "$mark" "$T_HIDE" 5
    chk "log: $T_HIDE" $?
    chk "same pid in the state route ($(sget pid))" "$(yes0 test "$(sget pid)" = "$pid")"
  fi
  step_end L2 "close button hides the window"
}

# ---- L3 ------------------------------------------------------------------------------------
l3() {
  step_begin L3
  local mark pid v
  ensure_app; chk "app running${ENS_NOTE:+ ($ENS_NOTE)}" $?
  pid="$APP_PID"
  if [ -n "$pid" ]; then
    if [ "$(sget visible)" = true ]; then
      sys_events "$SD/hide.txt" "$pid" -e 'click button 1 of window 1 of p'
      poll_state visible false 10 || inf "could not hide the window first"
    fi
    mark="$(log_size)"
    open_run "$SD/reopen.open" -a "$INSTALLED"
    chk "open -a ($(rcnote "$RC" "$SD/reopen.open"))" "$RC"
    poll_state visible true 15
    chk "visible: true after the reopen (read $POLL_VAL)" $?
    chk "same pid (state $(sget pid), expected $pid)" "$(yes0 test "$(sget pid)" = "$pid")"
    sleep_s 2
    front_pid
    chk "lsappinfo front is the app (front=${FRONT_PID:-unknown})" "$(yes0 test "$FRONT_PID" = "$pid")"
    wait_log "$mark" "$T_REOPEN" 5
    chk "log: $T_REOPEN" $?
    shot "$SD/reopened.png"
    # Cmd-W: informational only (it did nothing on the probe app); then put the window back
    sys_events "$SD/cmd-w.txt" "$pid" -e 'set frontmost of p to true' -e 'delay 0.5' \
      -e 'keystroke "w" using command down'
    sleep_s 3
    v="$(sget visible)"
    emit INFO L3i "Cmd-W on the main window: keystroke $(rcnote "$RC" "$SD/cmd-w.txt"), visible=$v afterwards"
    if [ "$v" != true ]; then
      open_run "$SD/after-cmd-w.open" -a "$INSTALLED"
      poll_state visible true 15 || inf "window not restored after Cmd-W"
    fi
  fi
  step_end L3 "reopen from the Dock path"
}

# ---- L4 ------------------------------------------------------------------------------------
l4() {
  step_begin L4
  local pid second during after rc
  ensure_app; chk "app running${ENS_NOTE:+ ($ENS_NOTE)}" $?
  pid="$APP_PID"
  if [ -n "$pid" ]; then
    ensure_visible || inf "window was not visible before the second launch"
    pids_for "$EXE" > "$SD/before.pids"
    open_run "$SD/second.open" -n -a "$INSTALLED"
    chk "open -n ($(rcnote "$RC" "$SD/second.open"))" "$RC"
    second=""
    if gate_wait 12 new_pid "$EXE" "$SD/before.pids"; then second="$NEW_PID"; track "$second" "app:second"; fi
    sleep_s 2
    during="$(listeners)"
    front_pid
    inf "second process: ${second:-none seen (it may have exited before it could be listed)}"
    rc=1
    if [ -n "$FRONT_PID" ] && { [ "$FRONT_PID" = "$pid" ] || [ "$FRONT_PID" = "$second" ]; }; then rc=0; fi
    chk "frontmost is the app (front=${FRONT_PID:-unknown}, first $pid, second ${second:-none})" "$rc"
    if [ -n "$second" ]; then
      wait_exit "$second" 20; rc=$?
      chk "second process $second exited ($(exit_note))" "$rc"
    fi
    after="$(listeners)"
    rc=1
    if [ "$during" = "$pid" ] && [ "$after" = "$pid" ]; then rc=0; fi
    chk "one listener on $PORT, the first process (during: ${during:-none}; after: ${after:-none})" "$rc"
    rc=1
    if [ "$(sget visible)" = true ] && [ "$(sget pid)" = "$pid" ]; then rc=0; fi
    chk "visible: true and the same pid" "$rc"
    shot "$SD/after-second.png"
  fi
  step_end L4 "second launch focuses the first"
}

# ---- L5 ------------------------------------------------------------------------------------
l5() {
  step_begin L5
  local pid scr sw sh tw th tx ty a1 a2 f0 x1 y1 w1 h1 mark rc
  ensure_app; chk "app running${ENS_NOTE:+ ($ENS_NOTE)}" $?
  pid="$APP_PID"
  if [ -n "$pid" ]; then
    ensure_visible || inf "window was not visible before the resize"
    # the display first: a target that does not fit would be clamped and tell us nothing
    runrc "$SD/screen.txt" "$T_OSA" osascript -l JavaScript \
      -e 'ObjC.import("AppKit"); var f = $.NSScreen.mainScreen.frame; Math.round(f.size.width) + "," + Math.round(f.size.height)'
    scr="$(grep -v '^rc=' "$SD/screen.txt" | head -1 | tr -d ' ')"
    sw="${scr%%,*}"; sh="${scr##*,}"
    case "$sw$sh" in
      '' | *[!0-9]*) sw=1024; sh=768; inf "screen size unreadable ($(rcnote "$RC" "$SD/screen.txt")); assumed 1024x768" ;;
    esac
    inf "screen ${sw}x${sh}"
    tw="$(awk -v s="$sw" 'BEGIN{printf "%d", s * 0.7}')"; th="$(awk -v s="$sh" 'BEGIN{printf "%d", s * 0.7}')"
    tx="$(awk -v s="$sw" 'BEGIN{printf "%d", s * 0.1}')"; ty="$(awk -v s="$sh" 'BEGIN{printf "%d", s * 0.1 + 30}')"
    window_state "$pid"; f0="$WS_NOTE"
    inf "before: $f0; target ${tw}x${th} at $tx,$ty"
    sys_events "$SD/set-frame.txt" "$pid" \
      -e "set position of window 1 of p to {$tx, $ty}" \
      -e "set size of window 1 of p to {$tw, $th}"
    chk "set position and size ($(rcnote "$RC" "$SD/set-frame.txt"))" "$RC"
    sleep_s 2
    window_state "$pid"; a1="$WS_NOTE"
    ax_parse "$a1"; x1="$AX_X"; y1="$AX_Y"; w1="$AX_W"; h1="$AX_H"
    rc=1
    if [ -n "$w1" ] && [ -n "$x1" ]; then rc=0; fi
    chk "AX frame read back after the set ($a1)" "$rc"
    chk "the set changed the frame (before: $f0)" "$(yes0 test "$a1" != "$f0")"
    cksum "$DATA_DIR/window-state.json" > "$SD/window-state.before" 2> /dev/null || echo absent > "$SD/window-state.before"
    mark="$(log_size)"
    crash_list > "$SD/crash-before.txt"
    cmd_q "$SD/cmd-q.txt" "$pid"
    chk "Cmd-Q keystroke ($(rcnote "$RC" "$SD/cmd-q.txt"))" "$RC"
    wait_exit "$pid" 70; rc=$?
    chk "exited after Cmd-Q ($(exit_note))" "$rc"
    sleep_s 3
    cksum "$DATA_DIR/window-state.json" > "$SD/window-state.after" 2> /dev/null || echo absent > "$SD/window-state.after"
    cp "$DATA_DIR/window-state.json" "$SD/window-state.json" 2> /dev/null
    rc=1
    if [ -f "$DATA_DIR/window-state.json" ] && ! cmp -s "$SD/window-state.before" "$SD/window-state.after"; then rc=0; fi
    chk "window-state.json exists and changed ($(head -c 120 "$SD/window-state.json" 2> /dev/null | tr '\n' ' '))" "$rc"
    log_seg "$mark" "$SD/cmd-q.log"
    inf "terminate lines after Cmd-Q: $(grep -cF 'terminate:' "$SD/cmd-q.log")"
    L_SERIES=0
    launch_app relaunch
    rc=1
    if [ -n "$L_PID" ] && [ "$L_PID" != "$pid" ]; then rc=0; fi
    chk "relaunched: pid ${L_PID:-none} in ${L_SECS}s" "$rc"
    if [ -n "$L_PID" ]; then
      poll_state visible true 25 || inf "window not visible after the relaunch"
      sleep_s 2
      window_state "$L_PID"; a2="$WS_NOTE"
      ax_parse "$a2"
      rc=1
      if [ -n "$AX_W" ] && [ -n "$AX_X" ]; then rc=0; fi
      chk "AX frame after the relaunch ($a2)" "$rc"
      if [ -n "$AX_W" ] && [ -n "$w1" ]; then
        # System Events' frame against System Events' frame only (its title bar is its own)
        rc=1
        if within "$w1" "$AX_W" 2 && within "$h1" "$AX_H" 2; then rc=0; fi
        chk "size within 2 px (${w1}x${h1} -> ${AX_W}x${AX_H})" "$rc"
        rc=1
        if within "$x1" "$AX_X" 40 && within "$y1" "$AX_Y" 40; then rc=0; fi
        chk "position within 40 px, allowing for a clamp ($x1,$y1 -> $AX_X,$AX_Y)" "$rc"
      else
        chk "frames comparable" 1
      fi
    fi
  fi
  step_end L5 "window geometry survives Cmd-Q and a relaunch"
}

# ---- L6 ------------------------------------------------------------------------------------
l6() {
  step_begin L6
  local pid mark mine others rc
  ensure_app; chk "app running${ENS_NOTE:+ ($ENS_NOTE)}" $?
  pid="$APP_PID"
  if [ -n "$pid" ]; then
    # only the installed copy may be running: an Apple event addressed by id reaches whichever
    # registered copy LaunchServices picks, and the build-directory copies are never launched
    mine="$(pids_for "$EXE" | tr '\n' ' ')"
    others="$(pids_for "$APP_N/Contents/MacOS/$EXE_NAME" | tr '\n' ' ')$(pids_for "$APP_N1/Contents/MacOS/$EXE_NAME" | tr '\n' ' ')"
    rc=1
    if [ -z "$others" ]; then rc=0; fi
    chk "only the installed copy runs (installed: $mine; build-dir copies: ${others:-none})" "$rc"
    mark="$(log_size)"
    crash_list > "$SD/crash-before.txt"
    runrc "$SD/quit.txt" "$T_QUIT" osascript -e "tell application id \"$APP_ID\" to quit"
    chk "quit Apple event ($(rcnote "$RC" "$SD/quit.txt"))" "$RC"
    drain_checks "$mark" "$pid" quit-event
  fi
  step_end L6 "quit Apple event drains, then exits"
}

# ---- L7 ------------------------------------------------------------------------------------
l7() {
  step_begin L7
  local pid mark rc
  ensure_app; chk "app running${ENS_NOTE:+ ($ENS_NOTE)}" $?
  pid="$APP_PID"
  if [ -n "$pid" ]; then
    mark="$(log_size)"
    crash_list > "$SD/crash-before.txt"
    cli_run "$T_CLI" "$EXE" quit --wait > "$SD/cli.txt" 2>&1
    rc=$?
    echo "rc=$rc" >> "$SD/cli.txt"
    chk "the-one quit --wait ($(rcnote "$rc" "$SD/cli.txt"))" "$rc"
    drain_checks "$mark" "$pid" quit-cli
  fi
  step_end L7 "the-one quit --wait"
}

# ---- L8 ------------------------------------------------------------------------------------
l8() {
  step_begin L8
  local pid mark
  ensure_app; chk "app running${ENS_NOTE:+ ($ENS_NOTE)}" $?
  pid="$APP_PID"
  if [ -n "$pid" ]; then
    ensure_visible || inf "window was not visible before Cmd-Q"
    mark="$(log_size)"
    crash_list > "$SD/crash-before.txt"
    cmd_q "$SD/cmd-q.txt" "$pid"
    chk "Cmd-Q keystroke ($(rcnote "$RC" "$SD/cmd-q.txt"))" "$RC"
    drain_checks "$mark" "$pid" cmd-q
  fi
  step_end L8 "Cmd-Q keystroke drains, then exits"
}

# ---- L9 ------------------------------------------------------------------------------------
seed_one() { # $1 = label  $2 = path  $3 = json body
  local r
  r="$(api_post "$2" "$3")"
  case "$r" in
    201*) chk "seeded $1 (201)" 0 ;;
    *) chk "seeded $1 ($r)" 1 ;;
  esac
}
has_in() { api_get "$1" | grep -qF -- "$2"; } # $1 = path  $2 = text the body must hold
l9() {
  step_begin L9
  local pid c0 c1 info provider_id rc
  ensure_app; chk "app running${ENS_NOTE:+ ($ENS_NOTE)}" $?
  pid="$APP_PID"
  if [ -n "$pid" ]; then
    c0="$(cred_prefix)"
    rc=1
    if [ -n "$c0" ]; then rc=0; fi
    chk "credential prefix before: ${c0:-none}" "$rc"
    # these routes work without dev mode: an ollama provider is not URL-validated
    seed_one provider /api/providers '{"name":"m32-seed-provider","type":"ollama","base_url":"http://127.0.0.1:11434"}'
    provider_id="$(api_get /api/providers | python3 -c '
import json, sys
for p in json.load(sys.stdin):
    if p.get("name") == "m32-seed-provider":
        print(p["id"])
' 2> /dev/null)"
    seed_one agent /api/agents "{\"name\":\"m32-seed-agent\",\"provider_config_id\":\"${provider_id:-none}\",\"llm_model\":\"seed-model\",\"system_prompt\":\"seed\"}"
    seed_one chat /api/chat/sessions '{"agent_name":"m32-seed-agent","title":"m32 seed chat"}'
    cli_run "$T_CLI" "$EXE" quit --wait > "$SD/quit-n.txt" 2>&1
    rc=$?
    chk "quit N ($(rcnote "$rc" "$SD/quit-n.txt"))" "$rc"
    wait_exit "$pid" 70; rc=$?
    chk "N exited ($(exit_note))" "$rc"
    sleep_s 3
    # replacing the app while it runs crashes the old copy (DD5): N is gone before this point
    rm -rf "$INSTALLED"
    runrc "$SD/ditto.txt" "$T_DITTO" ditto "$APP_N1" "$INSTALLED"
    chk "ditto N+1 over the installed path, from the build dir (N+1 has no .dmg) ($(rcnote "$RC" "$SD/ditto.txt"))" "$RC"
    L_SERIES=0
    launch_app upgraded
    rc=$?
    chk "N+1 launched: pid ${L_PID:-none} in ${L_SECS}s" "$rc"
    if [ -n "$L_PID" ]; then
      info="$(api_get /api/info | jget version)"
      chk "/api/info version $VERSION_N1 (read $info)" "$(yes0 test "$info" = "$VERSION_N1")"
      inf "state version $(sget version)"
      chk "seeded provider present" "$(yes0 has_in /api/providers m32-seed-provider)"
      chk "seeded agent present" "$(yes0 has_in /api/agents m32-seed-agent)"
      chk "seeded chat present" "$(yes0 has_in /api/chat/sessions 'm32 seed chat')"
      c1="$(cred_prefix)"
      rc=1
      if [ -n "$c0" ] && [ "$c0" = "$c1" ]; then rc=0; fi
      chk "credential prefix unchanged (${c0:-none} -> ${c1:-none})" "$rc"
    fi
  fi
  step_end L9 "upgrade to N+1 keeps the data and the credential"
}

# ---- L9b -----------------------------------------------------------------------------------
# M36 F3 L9 (DD11): the GleepGlorp drawer and a fill in WKWebView. No DOM access here: the proof is
# `--check-fill` (the fill row reached `filled`, which the browser posts only after it wrote the editor,
# and no agent exists) plus screenshots. No keystroke result is asserted for Esc.
L9B_SEED="$(dirname "$SELF")/../../scripts/gleepglorp_drawer_seed.py"
L9B_MSG="Fill in a new agent for me" # no characters AppleScript or the palette would treat specially
l9b_seed() { tl 60 python3 "$L9B_SEED" --base-url "$BASE" --data-dir "$DATA_DIR" --refuse-data-dir "$L9B_OLD_DATA" "$@"; }
l9b_fill_ok() { l9b_seed --check-fill > "$SD/check-fill.json" 2>&1; }
l9b_palette() { # $1 = tag  $2 = pid  $3 = text typed in Jump to (Cmd K, text, Return)
  sys_events "$SD/$1.txt" "$2" -e 'set frontmost of p to true' -e 'delay 0.7' \
    -e 'keystroke "k" using command down' -e 'delay 0.8' \
    -e "keystroke \"$3\"" -e 'delay 0.8' -e 'key code 36'
  sleep_s 1.2 # the palette closes before the next Cmd K
}
l9b() {
  step_begin L9b
  local pid old_pid rc left
  L9B_OLD_DATA="$DATA_DIR"
  # N+1 is still running from L9 (`open -a` on a running app ignores --env, so it must go first)
  old_pid="$(cur_pid)"
  if [ -n "$old_pid" ] && live; then
    cli_run "$T_CLI" "$EXE" quit --wait > "$SD/quit-n1.txt" 2>&1
    rc=$?
    chk "quit N+1 on the product port ($(rcnote "$rc" "$SD/quit-n1.txt"))" "$rc"
    wait_exit "$old_pid" 70; rc=$?
    chk "N+1 exited ($(exit_note))" "$rc"
    alive "$old_pid" && stop_pid "$old_pid"
  else
    inf "no N+1 was running on the product port"
  fi
  sleep_s 2
  chk "no listener on the product port $PORT ($(listeners))" "$(yes0 test -z "$(listeners)")"
  # the step's own instance: its own port and data dir, dev mode (child-run globals, reassigned here)
  PORT="${M32_L9B_PORT:-8486}"
  BASE="http://127.0.0.1:$PORT"
  DATA_DIR="$SD/data"
  CRED_FILE="$DATA_DIR/api-credential"
  CUSTOM=1
  DEV_MODE=1
  mkdir -p "$DATA_DIR"
  open_run "$SD/launch.open" -a "$INSTALLED"
  chk "open -a with port $PORT, a scratch data dir and dev mode ($(rcnote "$RC" "$SD/launch.open"))" "$RC"
  gate_wait 60 live
  chk "/api/live on $PORT" $?
  # the desktop app creates the credential; wait 30 s, else mint one for this data dir
  if ! gate_wait 30 test -s "$CRED_FILE"; then
    cli_run "$T_CLI" "$EXE" rotate-api-credential > "$SD/rotate.txt" 2>&1
    inf "credential absent after 30 s: rotate-api-credential ($(rcnote "$?" "$SD/rotate.txt"))"
  fi
  pid=""
  if gate_wait 10 have_pid; then pid="$(cur_pid)"; fi
  [ -z "$pid" ] || track "$pid" "app:l9b"
  rc=1
  if [ -n "$pid" ]; then rc=0; fi
  chk "the instance's pid from /api/window/state (${pid:-none})" "$rc"
  if [ -n "$pid" ]; then
    l9b_seed > "$SD/seed.json" 2> "$SD/seed.err"
    rc=$?
    chk "seed script ($(rcnote "$rc" "$SD/seed.err")) $(tail -c 200 "$SD/seed.json" 2> /dev/null)" "$rc"
  fi
  if [ -n "$pid" ] && [ "$S_OK" = 1 ]; then
    poll_state visible true 25 || inf "window not visible after 25 s"
    window_state "$pid"
    inf "window $WS_NOTE (the CSS width is inferred from this size; push mode needs 1280 or more)"
    # leave Chats (the corner button and the drawer are hidden there), then open the drawer
    l9b_palette leave-chats "$pid" "Appearance"
    shot "$SD/settings-appearance.png"
    l9b_palette open-drawer "$pid" "Ask GleepGlorp"
    shot "$SD/drawer-open.png"
    inf "drawer-open.png ${SHOT_BYTES} bytes"
    sys_events "$SD/send.txt" "$pid" -e 'set frontmost of p to true' -e 'delay 0.5' \
      -e "keystroke \"$L9B_MSG\"" -e 'delay 0.6' -e 'key code 36'
    chk "message typed and sent ($(rcnote "$RC" "$SD/send.txt"))" "$RC"
    gate_wait 90 l9b_fill_ok
    rc=$?
    chk "--check-fill exit 0 within 90 s: the fill is filled and no agent exists ($(tail -c 160 "$SD/check-fill.json" 2> /dev/null | tr '\n' ' '))" "$rc"
    sleep_s 1
    shot "$SD/fill-applied.png"
    inf "fill-applied.png ${SHOT_BYTES} bytes"
    # Esc: screenshot-only evidence (no DOM here, so focus after the close is not asserted)
    sys_events "$SD/esc.txt" "$pid" -e 'set frontmost of p to true' -e 'delay 0.5' -e 'key code 53'
    sleep_s 1
    shot "$SD/after-esc.png"
    inf "Esc sent ($(rcnote "$RC" "$SD/esc.txt")); after-esc.png ${SHOT_BYTES} bytes (focus not asserted)"
  fi
  # quit the step's instance the same way, and prove its port is free
  if [ -n "$pid" ]; then
    cli_run "$T_CLI" "$EXE" quit --wait > "$SD/quit-l9b.txt" 2>&1
    rc=$?
    chk "quit the step's instance ($(rcnote "$rc" "$SD/quit-l9b.txt"))" "$rc"
    wait_exit "$pid" 70; rc=$?
    chk "the step's instance exited ($(exit_note))" "$rc"
    alive "$pid" && stop_pid "$pid"
  fi
  sleep_s 1
  left="$(listeners)"
  chk "no listener on the step's port $PORT (${left:-none})" "$(yes0 test -z "$left")"
  tail -n 80 "$APP_LOG" > "$SD/app-log-tail.txt" 2> /dev/null || :
  rm -rf "$DATA_DIR" # a throwaway credential and database stay out of the uploaded evidence
  step_end L9b "the GleepGlorp drawer opens and a mock fill lands (WKWebView)"
}

# ---- L10 -----------------------------------------------------------------------------------
l10() {
  step_begin L10
  local pid rc
  ensure_app; chk "app running${ENS_NOTE:+ ($ENS_NOTE)}" $?
  pid="$APP_PID"
  if [ -n "$pid" ]; then
    cli_run "$T_CLI" "$EXE" quit --wait > "$SD/quit.txt" 2>&1
    rc=$?
    chk "quit ($(rcnote "$rc" "$SD/quit.txt"))" "$rc"
    wait_exit "$pid" 70; rc=$?
    chk "exited ($(exit_note))" "$rc"
    sleep_s 2
  fi
  rm -rf "$INSTALLED"
  chk "the app is gone from $INSTALL_DIR" "$(yes0 test ! -e "$INSTALLED")"
  chk "the database is still in the data dir" "$(yes0 test -f "$DATA_DIR/the-one.db")"
  chk "api-credential is still in the data dir" "$(yes0 test -f "$CRED_FILE")"
  step_end L10 "trash the app; the data stays"
}

# ---- the --run child -------------------------------------------------------------------------
cap_hit() { # the child's ALRM/TERM handler: say so, clean up, leave
  has_row "$STEP" || emit FAIL "$STEP" "step cap of ${M32_CAP:-?} s reached; partial evidence in $OUT/$STEP"
  stop_all
  exit 0
}
if [ "$MODE" = child ]; then
  trap cap_hit ALRM TERM INT
  mkdir -p "$OUT/$STEP"
  case "$STEP" in
    L1) l1 ;; L2) l2 ;; L3) l3 ;; L4) l4 ;; L5) l5 ;;
    L6) l6 ;; L7) l7 ;; L8) l8 ;; L9) l9 ;; L9b) l9b ;; L10) l10 ;;
    *) echo "lifecycle.sh: unknown step $STEP" >&2; exit 2 ;;
  esac
  exit 0
fi

# ---- the main process: install N, run every step under its own cap ----------------------------
[ -d "$APP_N" ] || { echo "lifecycle.sh: missing app: $APP_N" >&2; exit 2; }
[ -d "$APP_N1" ] || { echo "lifecycle.sh: missing app: $APP_N1" >&2; exit 2; }
MNT=""
detach_dmg() { # idempotent: detach the mounted .dmg, one -force retry
  [ -n "$MNT" ] || return 0
  if ! tl 60 hdiutil detach "$MNT" > "$OUT/L0/detach.txt" 2>&1; then
    tl 60 hdiutil detach -force "$MNT" >> "$OUT/L0/detach.txt" 2>&1 || echo "detach failed: $MNT" >> "$OUT/L0/detach.txt"
  fi
  MNT=""
}
trap 'stop_all; detach_dmg; exit 0' EXIT TERM INT ALRM
SD="$OUT/L0"; mkdir -p "$SD"
{
  echo "lifecycle.sh started $(date -u +%Y-%m-%dT%H:%M:%SZ) N=$VERSION_N N+1=$VERSION_N1 app_id=$APP_ID port=$PORT scale=$SCALE"
  echo "install dir: $INSTALL_DIR; data dir: $DATA_DIR; app log: $APP_LOG"
  if [ -f "$CRED_FILE" ]; then
    echo "credential before step 1: present (created before the first launch, by checks.sh gate 4), prefix $(cred_prefix)"
  else
    echo "credential before step 1: absent"
  fi
} > "$OUT/header.txt"
cat "$OUT/header.txt"
mkdir -p "$(dirname "$APP_LOG")"

INSTALL_OK=0
DMG_N="${M32_DMG_N:-}"
pre="$(listeners)$(pids_for "$EXE" | tr '\n' ' ')"
if [ -n "$pre" ]; then
  emit FAIL L0 "something already runs before step 1: listeners/pids: $pre"
else
  rm -rf "$INSTALLED"
  SRC_NOTE=""; ATT_OK=1
  if [ -n "$DMG_N" ] && [ -f "$DMG_N" ]; then
    # the way a user installs: mount the .dmg read-only, copy the .app out of the volume
    MNT="$SD/mnt"; mkdir -p "$MNT"
    runrc "$SD/attach.txt" 60 hdiutil attach -readonly -nobrowse -noverify -noautoopen -mountpoint "$MNT" "$DMG_N"
    if [ "$RC" != 0 ]; then
      ATT_OK=0; MNT=""
      emit FAIL L0 "could not attach the .dmg $(basename "$DMG_N") (hdiutil $(rcnote "$RC" "$SD/attach.txt"))"
    else
      runrc "$SD/ditto.txt" "$T_DITTO" ditto "$MNT/$(basename "$APP_N")" "$INSTALLED"
      SRC_NOTE="from the mounted .dmg $(basename "$DMG_N") (hdiutil attach -readonly, ditto out of the volume)"
      detach_dmg
    fi
  else
    runrc "$SD/ditto.txt" "$T_DITTO" ditto "$APP_N" "$INSTALLED"
    SRC_NOTE="from the BUILD DIR copy, not the .dmg (no .dmg: ${DMG_N:-M32_DMG_N unset})"
  fi
  if [ "$ATT_OK" = 1 ]; then
    if [ "$RC" = 0 ] && [ -x "$EXE" ]; then
      INSTALL_OK=1
      emit PASS L0 "installed N $VERSION_N at $INSTALLED $SRC_NOTE ($(du -sk "$INSTALLED" 2> /dev/null | cut -f1) KB)"
    else
      emit FAIL L0 "could not install N at $INSTALLED $SRC_NOTE (ditto $(rcnote "$RC" "$SD/ditto.txt"))"
    fi
  fi
fi
if crash_dirs_state; then emit PASS LCRASH "crash report directories:$CRASH_NOTE"; else emit FAIL LCRASH "a crash report directory is unreadable, so 'no new crash report' proves nothing:$CRASH_NOTE"; fi

for entry in L1:$CAP_L1 L2:$CAP_L2 L3:$CAP_L3 L4:$CAP_L4 L5:$CAP_L5 L6:$CAP_L6 L7:$CAP_L7 L8:$CAP_L8 L9:$CAP_L9 L9b:$CAP_L9B L10:$CAP_L10; do
  name="${entry%%:*}"; cap="${entry##*:}"
  if [ "$INSTALL_OK" != 1 ]; then emit FAIL "$name" "skipped: the install failed"; continue; fi
  if [ "$SECONDS" -gt "$BUDGET" ]; then emit FAIL "$name" "skipped: the global budget of ${BUDGET} s is spent"; continue; fi
  t0="$SECONDS"
  M32_CAP="$cap" tl "$cap" bash "$SELF" --run "$name" "$APP_N" "$APP_N1" "$APP_ID" "$VERSION_N" "$VERSION_N1" "$OUT" > "$OUT/$name.log" 2>&1
  rc=$?
  has_row "$name" || emit FAIL "$name" "no row written (child rc=$rc after $((SECONDS - t0)) s; cap ${cap} s); see $name.log"
done

# nothing may be left: the app, a listener on the port
stop_all
sleep_s 1
left="$(listeners)"
if [ -n "$left" ]; then emit FAIL LEND "a listener is left on $PORT: pid $left"; else emit PASS LEND "no process or listener left"; fi
cp "$APP_LOG" "$OUT/app.log" 2> /dev/null || true
crash_list > "$OUT/crash-reports.txt"
echo "== done in $SECONDS s: $(grep -c '^PASS ' "$SUMMARY") PASS, $(grep -c '^FAIL ' "$SUMMARY") FAIL" | tee -a "$SUMMARY"
exit 0
