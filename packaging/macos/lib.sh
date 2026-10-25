#!/usr/bin/env bash
# Shared helpers for the hosted-runner drivers (Mission 32 Flight 3 leg 6): sourced by
# probe/probe.sh and lifecycle.sh, never run. Build-time tooling, never imported by the_one/.
#
# The caller sets, before calling anything here:
#   TRACK   file of "<pid> <label>" lines (track appends, stop_all reads)
#   OUT     evidence directory (quiesce.log lands there)
#   PDIR    scratch directory for window_state's temp files
#   PORT / BASE / CRED_FILE   the product's port, base URL and credential file (http, cred, listener)
#   T_SHOT T_LSAPP T_OSA      the bounds (seconds) shot, front_pid and window_state use
# and optionally M32_SCALE (multiplies sleep_s only, never a bound) and M32_STOP_WAIT.
#
# bash 3.2 (the runner's /bin/bash may be): no mapfile, no ${x,,}, no [[ =~ ]] captures, no
# associative arrays, no arrays at all.
# shellcheck disable=SC2034,SC2154  # globals are set by the sourcing script

SCALE="${M32_SCALE:-1}"
STOP_WAIT="${M32_STOP_WAIT:-10}"

tl() { local n="$1"; shift; perl -e 'alarm shift @ARGV; exec @ARGV or die "exec failed: $!"' -- "$n" "$@"; }
now() { perl -MTime::HiRes=time -e 'printf "%.3f\n", time'; }
fsub() { awk -v a="$1" -v b="$2" 'BEGIN{printf "%.1f", b-a}'; }
sleep_s() { sleep "$(awk -v s="$1" -v k="$SCALE" 'BEGIN{printf "%.3f", s*k}')"; }
wait_until() { # $1 = absolute time (now() scale)
  local d
  d="$(awk -v t="$1" -v n="$(now)" 'BEGIN{d=t-n; if (d<0) d=0; printf "%.3f", d}')"
  sleep "$d"
}
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
new_pid() { # $1 = exe  $2 = before-file: sets NEW_PID to the first pid not in the file
  local p
  NEW_PID=""
  for p in $(pids_for "$1"); do
    if ! grep -qx "$p" "$2" 2>/dev/null; then NEW_PID="$p"; return 0; fi
  done
  return 1
}
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
