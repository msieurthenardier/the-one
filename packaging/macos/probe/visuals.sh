#!/usr/bin/env bash
# Charts and widgets in WKWebView, and the native bridge (Mission 35 Flight 2 leg 8, AC7).
# Build-time tooling, never imported by the_one/. Observation only: it writes PASS / FAIL / INFO
# rows to SUMMARY.txt in lifecycle.sh's style but never fails the step (the workflow step is
# `continue-on-error`); a person reads the rows and the screenshots.
#
#   visuals.sh APP APP_ID OUT_DIR
#
#     APP       absolute path of the installed product "GleepGlorp AI.app"
#     APP_ID    the bundle id (build.env APP_ID); the quit Apple event addresses it
#     OUT_DIR   evidence directory; SUMMARY.txt gets the rows, the PNGs and logs sit beside it
#
# Environment (all optional): M35_VISUALS_PORT (8491; any port at or above 8490, never 8484 or
# 8485), M35_RELAUNCH_WAIT (seconds to wait after a quit before relaunching, 95: a crash record
# written while the page was hidden is only read as stale after 90 s), M35_SCALE (multiplies the
# settle sleeps only, never a bound; it is handed to lib.sh as M32_SCALE).
#
# What it does: it launches the installed product with dev mode, a scratch port and a scratch
# data dir and cwd, creates the credential, seeds a mock provider, an agent and one session
# (created last, so Chats joins it on load) holding a chart, a running counter widget and a
# bridge-check widget that tries `window.webkit.messageHandlers.jsBridge.postMessage` with a
# pywebview window move and `messageHandlers.browserDelegate.postMessage('print')`, and prints
# its own results in large text (BRIDGE: and PRINT:). It then records, as rows:
#   V1 native_bridge from GET /api/window/state (expect "removed")
#   V2 the window position as early as the script can observe it (right after the app is up,
#      before the settle wait) against the final one (no move), and the window count (a print
#      sheet or dialog would add a window; the widget's PRINT: result is in the screenshot)
#   V3 screencapture of the chat in the light and the dark appearance
#   V4 the next-launch check after the quit Apple event; V5 after `the-one quit --wait`:
#      relaunch, let the seeded chat open, screenshot, and look for a widget crash record in
#      WebKit's localStorage on disk (INFO only: a read-only sqlite3 can miss an entry still in
#      the -wal file; the screenshot, with no "stopped responding last time", is the check)
#
# bash 3.2 (the runner's bash may be): no mapfile, no ${x,,}, no [[ =~ ]] captures, no
# associative arrays, no arrays at all.
# shellcheck disable=SC2034,SC2317  # globals are read by lib.sh
set -u

SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
APP="${1:-}"
APP_ID="${2:-}"
OUT="${3:-}"
if [ -z "$APP" ] || [ -z "$APP_ID" ] || [ -z "$OUT" ]; then
  echo "usage: visuals.sh APP APP_ID OUT_DIR" >&2
  exit 2
fi
if [ "$(uname -s)" != "Darwin" ]; then
  echo "visuals.sh: this driver needs macOS (WKWebView, System Events, screencapture); refusing on $(uname -s)" >&2
  exit 2
fi

PORT="${M35_VISUALS_PORT:-8491}"
case "$PORT" in '' | *[!0-9]*) echo "visuals.sh: bad port $PORT" >&2; exit 2 ;; esac
if [ "$PORT" -lt 8490 ]; then
  echo "visuals.sh: port $PORT refused (use 8490 or higher; 8484 and 8485 belong to the operator)" >&2
  exit 2
fi
M32_SCALE="${M35_SCALE:-1}" # lib.sh reads M32_SCALE (and reassigns SCALE from it) when sourced
export M32_SCALE
RELAUNCH_WAIT="${M35_RELAUNCH_WAIT:-95}"

# shellcheck source=../lib.sh
. "$(dirname "$SELF")/../lib.sh"

T_OPEN=20; T_SHOT=10; T_OSA=15; T_LSAPP=10; T_QUIT=30; T_CLI=90
EXE="$APP/Contents/MacOS/${M32_EXE_PRODUCT:-the-one}"
BASE="http://127.0.0.1:$PORT"
WORK="$HOME/m35-visuals"
DATA_DIR="$WORK/data"
CWD="$WORK/cwd"
CRED_FILE="$DATA_DIR/api-credential"
SUMMARY="$OUT/SUMMARY.txt"
TRACK="$OUT/tracked.pids"
PDIR="$OUT"
mkdir -p "$OUT" "$DATA_DIR" "$CWD"
touch "$TRACK" "$SUMMARY" "$OUT/.marker"

emit() { # $1 = PASS|FAIL|INFO  $2 = id  $3 = text (one line)
  local t
  t="$(printf '%s' "$3" | tr '\n' ' ' | tr -s ' ' | cut -c1-900)"
  printf '%s %s %s\n' "$1" "$2" "$t" >> "$SUMMARY"
  printf '%s %s %s\n' "$1" "$2" "$t"
}

api_get() { curl -s -m 5 -H "Authorization: Bearer $(cred)" "$BASE$1" 2> /dev/null; }
jget() { # $1 = key: the JSON object on stdin -> value
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
live() { curl -fsS -m 2 "$BASE/api/live" > /dev/null 2>&1; }

cleanup() { stop_all; }
trap cleanup EXIT

# ---- the scratch instance: credential, then a headless serve to seed through -------------------
export THE_ONE_PORT="$PORT" THE_ONE_DATA_DIR="$DATA_DIR" THE_ONE_DEV_MODE=true
cd "$CWD" || exit 2
tl 60 "$EXE" rotate-api-credential > "$OUT/credential.txt" 2>&1
if [ -z "$(cred)" ]; then
  emit FAIL V0 "no credential created in $DATA_DIR ($(head -c 200 "$OUT/credential.txt" | tr '\n' ' '))"
  exit 0
fi

# `app` has to be passed when launching by path: the frozen entry adds it only with no arguments
"$EXE" serve > "$OUT/seed-serve.log" 2>&1 &
SERVE_PID=$!
track "$SERVE_PID" seed-serve
if ! gate_wait 60 live; then
  emit FAIL V0 "the seeding serve did not come up on port $PORT (see seed-serve.log)"
  exit 0
fi

SEED_RC=0
tl 60 python3 - "$BASE" "$(cred)" > "$OUT/seed.txt" 2>&1 << 'PYEOF' || SEED_RC=$?
import datetime
import json
import sys
import urllib.request

base, cred = sys.argv[1], sys.argv[2]


def post(path, body):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + cred, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


CTR = (
    '<div style="height:120px;font:20px sans-serif">counter <b id=c>0</b></div>'
    "<script>window.__n=0;setInterval(function(){window.__n++;"
    "document.getElementById('c').textContent=window.__n;},50);</script>"
)
BRIDGE = (
    '<div id=r style="font:bold 40px sans-serif;height:140px">BRIDGE: pending</div>'
    '<div id=p style="font:bold 40px sans-serif;height:70px">PRINT: pending</div>'
    "<script>(function(){var out;try{var mh=window.webkit&&window.webkit.messageHandlers"
    "&&window.webkit.messageHandlers.jsBridge;"
    "if(!mh){out='undefined';}else{"
    "mh.postMessage(JSON.stringify({funcName:'pywebviewMoveWindow',params:[5,5],id:'m'}));"
    "out='posted';}}catch(e){out='threw '+e.name;}"
    "document.getElementById('r').textContent='BRIDGE: '+out;"
    "var pr;try{var bd=window.webkit&&window.webkit.messageHandlers"
    "&&window.webkit.messageHandlers.browserDelegate;"
    "if(!bd){pr='undefined';}else{bd.postMessage('print');pr='posted';}}"
    "catch(e){pr='threw';}"
    "document.getElementById('p').textContent='PRINT: '+pr;})();</script>"
)
CHART = json.dumps(
    {
        "type": "line",
        "title": "Seeded chart",
        "x": {"values": [1, 2, 3, 4]},
        "series": [{"name": "a", "values": [3, 5, 4, 7]}],
    }
)
text = (
    "Chart and widgets:\n\n```chart\n" + CHART + "\n```\n\n```widget\n" + CTR
    + "\n```\n\n```widget\n" + BRIDGE + "\n```\n\nDone.\n"
)
prov = post("/api/providers", {"name": "mock-v", "type": "mock", "base_url": "", "config": {}})
post(
    "/api/agents",
    {
        "name": "visuals",
        "provider_config_id": prov["id"],
        "llm_model": "mock-default",
        "system_prompt": "x",
    },
)
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
msgs = json.dumps(
    [
        {"role": "user", "content": "show", "created_at": now},
        {"role": "assistant", "content": text, "created_at": now},
    ]
)
s = post(
    "/api/chat/sessions",
    {
        "agent_name": "visuals",
        "title": "visuals",
        "updated_at": now,
        "created_at": now,
        "platform": None,
        "messages": msgs,
    },
)
print("seeded session", s["id"])
PYEOF
stop_pid "$SERVE_PID"
if [ "$SEED_RC" != 0 ]; then
  emit FAIL V0 "seeding failed rc=$SEED_RC: $(tail -c 300 "$OUT/seed.txt" | tr '\n' ' ')"
  exit 0
fi
emit INFO V0 "seeded: $(tail -1 "$OUT/seed.txt")"

# ---- launching the app ------------------------------------------------------------------------
launch_app() { # $1 = tag. Sets L_PID ("" when it never came up)
  tl "$T_OPEN" open -a "$APP" --env "THE_ONE_PORT=$PORT" --env "THE_ONE_DATA_DIR=$DATA_DIR" \
    --env "THE_ONE_DEV_MODE=true" > "$OUT/$1.open" 2>&1
  L_PID=""
  POS_EARLY=""
  if gate_wait 90 live; then
    L_PID="$(sget pid)"
    case "$L_PID" in '' | *[!0-9]*) L_PID="" ;; esac
    # the earliest observable window position: poll until the window exists (about 8 s at most)
    if [ -n "$L_PID" ]; then
      local i
      for i in 1 2 3 4 5 6 7 8; do
        window_state "$L_PID"
        POS_EARLY="$(printf '%s' "$WS_NOTE" | sed -n 's/.*pos=\([0-9-]*,[0-9-]*\).*/\1/p')"
        [ -n "$POS_EARLY" ] && break
        sleep 1
      done
    fi
    sleep_s 4
  fi
  [ -n "$L_PID" ] && track "$L_PID" "$1"
}
local_storage_keys() { # prints every widget crash-record key found in WebKit's localStorage on disk
  local f
  find "$HOME/Library" -path '*LocalStorage*' -newer "$OUT/.marker" -type f 2> /dev/null \
    | while read -r f; do
      case "$f" in
        *.localstorage | *localstorage.sqlite3 | *.sqlite3)
          tl 10 sqlite3 -readonly "$f" "select key from ItemTable" 2> /dev/null | grep '^widget-running:'
          ;;
      esac
    done
}

launch_app first
if [ -z "$L_PID" ]; then
  emit FAIL V0 "the app did not come up on port $PORT within 90 s (see first.open)"
  exit 0
fi
sleep_s 12 # the chat opens, the widgets run

# ---- V1 / V2: the bridge ----------------------------------------------------------------------
NB="$(sget native_bridge)"
if [ "$NB" = removed ]; then emit PASS V1 "native_bridge=$NB"; else emit FAIL V1 "native_bridge=${NB:-unreadable} (expected removed)"; fi
POS_FIRST="$POS_EARLY" # recorded inside launch_app, before the settle wait and the widgets
emit INFO V2 "window position recorded as soon as the app window was up: ${POS_FIRST:-unreadable}"
window_state "$L_PID"; WS_AFTER="$WS_NOTE"
emit INFO V2 "window state after the bridge-check widget ran: $WS_AFTER"
POS_AFTER="$(printf '%s' "$WS_AFTER" | sed -n 's/.*pos=\([0-9-]*,[0-9-]*\).*/\1/p')"
WINS="$(printf '%s' "$WS_AFTER" | sed -n 's/.*windows=\([0-9]*\).*/\1/p')"
sleep_s 5
window_state "$L_PID"
POS_LATER="$(printf '%s' "$WS_NOTE" | sed -n 's/.*pos=\([0-9-]*,[0-9-]*\).*/\1/p')"
if [ -n "$POS_FIRST" ] && [ "$POS_FIRST" = "$POS_AFTER" ] && [ "$POS_FIRST" = "$POS_LATER" ]; then
  emit PASS V2 "no window move: pos $POS_FIRST at window-up, $POS_AFTER after the widget ran, $POS_LATER 5 s later (a pywebview move to 5,5 would show)"
else
  emit FAIL V2 "window position changed or unreadable: $POS_FIRST at window-up, $POS_AFTER, $POS_LATER"
fi
if [ "$WINS" = 1 ]; then
  emit PASS V2 "one window only (no print dialog or other new window): $WS_NOTE"
else
  emit FAIL V2 "window count is ${WINS:-unknown}, expected 1: $WS_NOTE"
fi
tl "$T_OSA" osascript -e 'tell application "System Events" to get name of every window of (first process whose frontmost is true)' \
  > "$OUT/front-windows.txt" 2>&1
emit INFO V2 "front process windows: $(head -c 200 "$OUT/front-windows.txt" | tr '\n' ' ')"

# ---- V3: light and dark -------------------------------------------------------------------------
tl "$T_OSA" osascript -e 'tell application "System Events" to tell appearance preferences to set dark mode to false' > /dev/null 2>&1
sleep_s 4
shot "$OUT/chat-light.png"
emit INFO V3 "light appearance screenshot chat-light.png ($SHOT_BYTES bytes, rc=$SHOT_RC); expect a drawn chart, a running counter and BRIDGE: undefined and PRINT: undefined"
tl "$T_OSA" osascript -e 'tell application "System Events" to tell appearance preferences to set dark mode to true' > /dev/null 2>&1
sleep_s 4
shot "$OUT/chat-dark.png"
emit INFO V3 "dark appearance screenshot chat-dark.png ($SHOT_BYTES bytes, rc=$SHOT_RC)"
tl "$T_OSA" osascript -e 'tell application "System Events" to tell appearance preferences to set dark mode to false' > /dev/null 2>&1

# ---- V4 / V5: the next launch after each quit path ------------------------------------------------
next_launch() { # $1 = id  $2 = tag  $3 = how the quit was done
  local pid="$L_PID" keys wal
  wait_exit "$pid" 30 || emit FAIL "$1" "the app (pid $pid) did not exit within 30 s after $3"
  sleep_s 2
  keys="$(local_storage_keys | tr '\n' ' ')"
  wal="$(find "$HOME/Library" -path '*LocalStorage*' -name '*-wal' -newer "$OUT/.marker" -size +0 2> /dev/null | wc -l | tr -d ' ')"
  # INFO, not PASS/FAIL: a read-only sqlite3 may miss an entry still in the -wal file
  if [ -z "$keys" ]; then
    emit INFO "$1" "no widget crash record in localStorage on disk after $3 (caveat: $wal non-empty -wal file(s) not checkpointed, so an entry could be missed; the relaunch screenshot decides)"
  else
    emit INFO "$1" "a widget crash record is on disk after $3: $keys ($wal non-empty -wal file(s))"
  fi
  sleep "$RELAUNCH_WAIT"
  launch_app "$2"
  if [ -z "$L_PID" ]; then emit FAIL "$1" "relaunch after $3 did not come up"; return; fi
  sleep_s 12
  shot "$OUT/relaunch-$2.png"
  emit INFO "$1" "relaunch screenshot relaunch-$2.png ($SHOT_BYTES bytes): the check is a running counter and no 'stopped responding last time' on a widget"
}

tl "$T_QUIT" osascript -e "tell application id \"$APP_ID\" to quit" > "$OUT/quit-event.txt" 2>&1
next_launch V4 after-quit-event "the quit Apple event"

tl "$T_CLI" env "THE_ONE_PORT=$PORT" "THE_ONE_DATA_DIR=$DATA_DIR" "$EXE" quit --wait > "$OUT/quit-cli.txt" 2>&1
next_launch V5 after-quit-cli "the-one quit --wait"

tl "$T_CLI" env "THE_ONE_PORT=$PORT" "THE_ONE_DATA_DIR=$DATA_DIR" "$EXE" quit --wait > "$OUT/quit-final.txt" 2>&1
emit INFO V9 "done"
exit 0
