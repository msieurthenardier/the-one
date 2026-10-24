#!/bin/bash
# Container side of gtk-smoke.sh. Env in: DEB (file in /packages), CONTROL=0|1, OLD (file in /packages-old,
# takeover mode), EV=/evidence.
# shellcheck disable=SC2015,SC2164,SC2206,SC2034
set -u
PORT=8490
mkdir -p "$EV"
log() { echo "[smoke $(date +%T)] $*" | tee -a "$EV/inner.log"; }
RES="$EV/result.txt"; : > "$RES"
FAILS=0
check() { # $1 name, $2 0|1 (1 = pass), $3 detail
  if [ "$2" = 1 ]; then echo "PASS $1 $3" >> "$RES"; else echo "FAIL $1 $3" >> "$RES"; FAILS=$((FAILS+1)); fi
}
na() { echo "N/A  $1 $2" >> "$RES"; }

useradd -m -s /bin/bash tester 2>/dev/null
install -d -o tester -g tester /home/tester/scratch /home/tester/scratch/cwd
XRD=/tmp/xdg-runtime-tester; install -d -m 700 -o tester -g tester "$XRD"
DATA=/home/tester/scratch/data
rt() { (cd /home/tester/scratch/cwd && runuser -u tester -- env -i HOME=/home/tester USER=tester \
  PATH="$PATH" LANG=C.UTF-8 XDG_RUNTIME_DIR="$XRD" "$@"); }

apt-get update > "$EV/apt-update.txt" 2>&1
apt-cache policy python3-xlib > "$EV/xlib-policy.txt" 2>&1
apt-get install -y python3-xlib >> "$EV/xlib-policy.txt" 2>&1 || { echo "OVERALL FAIL (python3-xlib)" >> "$RES"; exit 0; }
install -m 644 "/packages/$DEB" "/tmp/$DEB"
apt-get install -y "/tmp/$DEB" > "$EV/install.txt" 2>&1 || { echo "OVERALL FAIL (install)" >> "$RES"; exit 0; }
rt the-one version > "$EV/version.txt" 2>&1

# private display, no window manager
install -d -m 1777 /tmp/.X11-unix
(setsid runuser -u tester -- Xvfb :99 -screen 0 1920x1080x24 > "$EV/xvfb.log" 2>&1 & echo $! > "$EV/xvfb.pid")
for _ in $(seq 1 20); do DISPLAY=:99 xwininfo -root > /dev/null 2>&1 && break; sleep 0.5; done
XPID=$(cat "$EV/xvfb.pid")

WENV=(DISPLAY=:99 GDK_BACKEND=x11 PYWEBVIEW_GUI=gtk
      WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1 WEBKIT_DISABLE_COMPOSITING_MODE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 LIBGL_ALWAYS_SOFTWARE=1
      THE_ONE_PORT=$PORT THE_ONE_DATA_DIR=$DATA)

APPPG=""
launch() { # $1 = tag ; sets APPPG (a session leader started with setsid)
  (cd /home/tester/scratch/cwd; setsid runuser -u tester -- env -i HOME=/home/tester PATH="$PATH" LANG=C.UTF-8 \
     XDG_RUNTIME_DIR="$XRD" "${WENV[@]}" dbus-run-session -- the-one app > "$EV/app-$1.log" 2>&1 &
   echo $! > "$EV/app-$1.pgid")
  APPPG=$(cat "$EV/app-$1.pgid")
}
wait_live() { local i; for i in $(seq 1 "$1"); do curl -fsS -m 2 "http://127.0.0.1:$PORT/api/live" > /dev/null 2>&1 && return 0; sleep 1; done; return 1; }
cred() { tr -d '[:space:]' < "$DATA/api-credential" 2>/dev/null; }
api() { curl -sS -m 5 -H "Authorization: Bearer $(cred)" "$@"; }
toplevel() { DISPLAY=:99 xwininfo -root -tree 2> /dev/null | grep -E ' "GleepGlorp AI"' | head -1 | awk '{print $1}'; }
mapstate() { DISPLAY=:99 xwininfo -id "$1" 2> /dev/null | sed -n 's/.*Map State: //p'; }
xsize() { DISPLAY=:99 xwininfo -id "$1" 2> /dev/null | awk '/Width:/{w=$2} /Height:/{h=$2} END{print w"x"h}'; }
group_gone() { # $1 pgid, $2 seconds
  local i; for i in $(seq 1 "$2"); do kill -0 -- "-$1" 2> /dev/null || return 0; sleep 1; done; return 1; }
stop_group() { kill -TERM -- "-$1" 2> /dev/null; group_gone "$1" 10 || kill -KILL -- "-$1" 2> /dev/null; }

cat > /tmp/wmdelete.py <<'PY'
import sys
from Xlib import display, X, protocol
d = display.Display(":99")
w = d.create_resource_object("window", int(sys.argv[1], 16))
ev = protocol.event.ClientMessage(window=w, client_type=d.intern_atom("WM_PROTOCOLS"),
    data=(32, [d.intern_atom("WM_DELETE_WINDOW"), X.CurrentTime, 0, 0, 0]))
w.send_event(ev, event_mask=0)
d.flush(); d.sync()
PY

# first poll for the window to exist and report state
boot() { # $1 tag ; leaves APPPG, WID
  launch "$1"
  wait_live 120 && echo live > "$EV/$1.live" || echo "NOT live" > "$EV/$1.live"
}
wait_exit() { # $1 seconds -> 0 if the app group is gone
  group_gone "$APPPG" "$1"; }

if [ -n "${OLD:-}" ]; then
  # ---- version takeover (DD13): OLD running, upgraded in place to DEB, then a new launch ----
  log "takeover from $OLD to $DEB"
  install -m 644 "/packages-old/$OLD" "/tmp/$OLD"
  apt-get install -y --allow-downgrades "/tmp/$OLD" > "$EV/install-old.txt" 2>&1 || { echo "OVERALL FAIL (install old)" >> "$RES"; exit 0; }
  rt the-one version > "$EV/version-old.txt" 2>&1
  boot o
  [ "$(cat "$EV/o.live")" = live ] && check takeover-old-live 1 "$(head -c 60 "$EV/version-old.txt")" || check takeover-old-live 0 "old not live"
  OLDPG=$APPPG
  cli() { # $1 = output tag, rest = the-one args
    local tag=$1; shift
    (cd /home/tester/scratch/cwd; runuser -u tester -- env -i HOME=/home/tester PATH="$PATH" LANG=C.UTF-8 \
       XDG_RUNTIME_DIR="$XRD" THE_ONE_PORT=$PORT THE_ONE_DATA_DIR=$DATA the-one "$@") > "$EV/cli-$tag.txt" 2>&1; echo $? > "$EV/cli-$tag.rc"; }
  visible_state_t() { api "http://127.0.0.1:$PORT/api/window/state" 2> /dev/null | sed -n 's/.*"visible": *\(true\|false\).*/\1/p'; }
  oldver() { api "http://127.0.0.1:$PORT/api/info" 2> /dev/null | sed -n 's/.*"version": *"\([^"]*\)".*/\1/p'; }
  OV=$(oldver); echo "$OV" > "$EV/old-version.txt"
  sleep 8   # let the old window finish booting
  # the real upgrade: the new package replaces the files under the running old process
  install -m 644 "/packages/$DEB" "/tmp/$DEB"
  apt-get install -y --allow-downgrades "/tmp/$DEB" > "$EV/install.txt" 2>&1 || { echo "OVERALL FAIL (install new)" >> "$RES"; exit 0; }
  rt the-one version > "$EV/version-new.txt" 2>&1
  NV=$(sed -n 's/.* v\([^ ]*\).*/\1/p' "$EV/version-new.txt" | head -1)
  kill -0 -- "-$OLDPG" 2> /dev/null && check takeover-old-survives-upgrade 1 "old v$OV still running after the package upgrade" || check takeover-old-survives-upgrade 0 "old gone after install"
  T0=$(date +%s)
  launch n; NEWPG=$APPPG
  if [ "$OV" = 0.11.8 ]; then KIND=flight1; else KIND=thistree; fi
  echo "$KIND old=$OV new=$NV" > "$EV/takeover-kind.txt"
  if [ "$KIND" = flight1 ]; then
    # Flight 1's N has no quit route: the new launch focuses it and exits; N keeps running
    if group_gone "$NEWPG" 30; then check takeover-f1-new-exits 1 "new launch exited by itself in $(( $(date +%s) - T0 ))s"; else check takeover-f1-new-exits 0 "new launch still running"; stop_group "$NEWPG"; fi
    kill -0 -- "-$OLDPG" 2> /dev/null && check takeover-f1-old-focused-not-replaced 1 "old v$OV still running" || check takeover-f1-old-focused-not-replaced 0 "old was replaced/killed"
    [ "$(oldver)" = "$OV" ] && check takeover-f1-still-old-version 1 "server still v$OV" || check takeover-f1-still-old-version 0 "version now '$(oldver)'"
    grep -q 'restart GleepGlorp AI' "$EV/app-n.log" && check takeover-f1-restart-hint 1 "$(grep -h 'restart GleepGlorp AI' "$EV/app-n.log" | head -1 | head -c 140)" || check takeover-f1-restart-hint 0 "no restart hint in app-n.log"
    stop_group "$OLDPG"
  else
    # a this-tree N: the new launch quits it, waits for its pid, then serves as the new version
    if group_gone "$OLDPG" 90; then check takeover-old-exits 1 "old group gone in $(( $(date +%s) - T0 ))s"; else check takeover-old-exits 0 "old still running after 90s"; stop_group "$OLDPG"; fi
    GOT=""; for _ in $(seq 1 90); do GOT=$(oldver); [ "$GOT" = "$NV" ] && break; sleep 1; done
    [ -n "$NV" ] && [ "$GOT" = "$NV" ] && check takeover-new-serving 1 "server answers v$GOT" || check takeover-new-serving 0 "server version '$GOT', expected '$NV'"
    kill -0 -- "-$NEWPG" 2> /dev/null && check takeover-new-process-alive 1 "new launch is the running app" || check takeover-new-process-alive 0 "new launch exited"
    VISN=""; for _ in $(seq 1 60); do [ "$(visible_state_t)" = true ] && { VISN=1; break; }; sleep 0.5; done
    [ -n "$VISN" ] && check takeover-new-window-visible 1 "visible=true" || check takeover-new-window-visible 0 "window not visible"
    cli tq quit --wait
    APPPG=$NEWPG
    wait_exit 15 && check takeover-new-quits 1 "the-one quit ended the new instance" || { check takeover-new-quits 0 "still running"; stop_group "$NEWPG"; }
  fi
  kill "$XPID" 2> /dev/null
  [ "$FAILS" = 0 ] && echo "OVERALL PASS (takeover)" >> "$RES" || echo "OVERALL FAIL ($FAILS)" >> "$RES"
  exit 0
fi

if [ "$CONTROL" = 1 ]; then
  log "control"
  boot c
  sleep 25
  grep -h -i 'tray' "$EV/app-c.log" > "$EV/tray-line.txt" 2>&1
  WID=$(toplevel); echo "wid=${WID:-none}" > "$EV/control-window.txt"
  if [ -n "$WID" ]; then DISPLAY=:99 xwininfo -id "$WID" >> "$EV/control-window.txt" 2>&1; ST=$(mapstate "$WID"); else ST=none; fi
  code=$(api -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/window/state"); echo "state route http $code" >> "$EV/control-window.txt"
  [ "$code" = 404 ] && na route "(404 on control, as expected)" || check control-route 0 "state route answered $code"
  [ "$ST" = IsUnMapped ] && check control-trap2-unmapped 1 "toplevel $WID is $ST with no focus request" || check control-trap2-unmapped 0 "toplevel state '$ST'"
  na step5-quit "n/a on control"
  if [ -n "$WID" ]; then
    DISPLAY=:99 python3 /tmp/wmdelete.py "$WID" 2>> "$EV/wmdelete.err"
    if wait_exit 15; then echo "control: WM_DELETE_WINDOW exited within 15s" >> "$RES"; else echo "control: WM_DELETE_WINDOW did NOT exit within 15s (trap 1 reproduced, or unmapped window ignores it)" >> "$RES"; fi
  fi
  stop_group "$APPPG"; kill "$XPID" 2> /dev/null
  [ "$FAILS" = 0 ] && echo "OVERALL PASS (control)" >> "$RES" || echo "OVERALL FAIL" >> "$RES"
  exit 0
fi

# ---- step 1: boot, tray decision ----
log "step 1"
boot a
[ "$(cat "$EV/a.live")" = live ] && check step1-live 1 "" || check step1-live 0 "server not live"

# ---- step 2: visible via route and via X ----
log "step 2"
VIS=""
for _ in $(seq 1 40); do
  S=$(api "http://127.0.0.1:$PORT/api/window/state" 2> /dev/null); echo "$S" > "$EV/state-a.json"
  case "$S" in *'"visible":true'*|*'"visible": true'*) VIS=1; break;; esac; sleep 0.5; done
[ -n "$VIS" ] && check step2-state-visible 1 "$(head -c 200 "$EV/state-a.json")" || check step2-state-visible 0 "$(head -c 200 "$EV/state-a.json")"
WID=$(toplevel)
DISPLAY=:99 xwininfo -root -tree > "$EV/xwininfo-tree-a.txt" 2>&1
ST=$([ -n "$WID" ] && mapstate "$WID")
[ "$ST" = IsViewable ] && check step2-xwininfo-viewable 1 "toplevel $WID $ST" || check step2-xwininfo-viewable 0 "toplevel '${WID:-none}' state '$ST'"
# the tray decision is logged after the window is shown, so read it here
sleep 1
grep -h 'No system tray' "$EV/app-a.log" | head -1 > "$EV/tray-line.txt" 2>&1
[ -s "$EV/tray-line.txt" ] && check step1-tray-none 1 "$(head -c 160 "$EV/tray-line.txt")" || check step1-tray-none 0 "no 'No system tray' line"

# ---- step 3 (leg 5 phase A): none-mode close hides, relaunch shows, `the-one quit` exits ----
cli() { # $1 = output tag, rest = the-one args ; runs the CLI as the tester against the smoke instance
  local tag=$1; shift
  (cd /home/tester/scratch/cwd; runuser -u tester -- env -i HOME=/home/tester PATH="$PATH" LANG=C.UTF-8 \
     XDG_RUNTIME_DIR="$XRD" THE_ONE_PORT=$PORT THE_ONE_DATA_DIR=$DATA the-one "$@") > "$EV/cli-$tag.txt" 2>&1; echo $? > "$EV/cli-$tag.rc"; }
visible_state() { # echoes true|false|? from the state route
  api "http://127.0.0.1:$PORT/api/window/state" 2> /dev/null | tee "$EV/state-last.json" \
    | sed -n 's/.*"visible": *\(true\|false\).*/\1/p'; }
log "step 3"
PRIMARY=$APPPG
if [ -n "$WID" ]; then DISPLAY=:99 python3 /tmp/wmdelete.py "$WID" 2>> "$EV/wmdelete.err"; fi
for _ in $(seq 1 20); do [ "$(visible_state)" = false ] && break; sleep 0.5; done
HV=$(visible_state); cp "$EV/state-last.json" "$EV/state-hidden.json"
ST2=$([ -n "$WID" ] && mapstate "$WID")
if kill -0 -- "-$PRIMARY" 2> /dev/null; then check step3-close-process-alive 1 "group $PRIMARY alive after the close"; else check step3-close-process-alive 0 "the app exited on close (no hide)"; fi
[ "$HV" = false ] && check step3-close-hidden-state 1 "visible=$HV" || check step3-close-hidden-state 0 "visible='$HV'"
[ "$ST2" != IsViewable ] && check step3-close-hidden-x 1 "toplevel $WID is '$ST2'" || check step3-close-hidden-x 0 "toplevel still $ST2"
sleep 2
grep -h -i 'notif' "$EV/app-a.log" > "$EV/notice-lines.txt" 2>&1
if [ -f "$DATA/.no_tray_notice_shown" ]; then check step3-notice-marker 1 ".no_tray_notice_shown written"; else check step3-notice-marker 0 "no marker"; fi
if python3 -c "import json,sys; d=json.load(open('$DATA/window-state.json')); sys.exit(0 if d.get('width') and d.get('height') else 1)" 2> /dev/null; then
  check step3-state-saved 1 "$(tr -d '\n ' < "$DATA/window-state.json")"; else check step3-state-saved 0 "missing/empty window-state.json"; fi
cp "$DATA/window-state.json" "$EV/window-state-1.json" 2> /dev/null
# relaunch while hidden: the second `the-one app` focuses the running one and exits by itself
launch r; RELAUNCH=$APPPG
VIS2=""; for _ in $(seq 1 40); do [ "$(visible_state)" = true ] && { VIS2=1; break; }; sleep 0.5; done
[ -n "$VIS2" ] && check step3-relaunch-shows 1 "visible=true" || check step3-relaunch-shows 0 "still hidden"
WID2=$(toplevel); ST3=$([ -n "$WID2" ] && mapstate "$WID2")
[ "$ST3" = IsViewable ] && check step3-relaunch-viewable 1 "toplevel $WID2 $ST3" || check step3-relaunch-viewable 0 "toplevel '${WID2:-none}' '$ST3'"
if group_gone "$RELAUNCH" 15; then check step3-relaunch-exits 1 "second launch exited"; else check step3-relaunch-exits 0 "second launch still running"; stop_group "$RELAUNCH"; fi
# the-one quit
T0=$(date +%s); cli q quit
APPPG=$PRIMARY
if wait_exit 15; then check step3-cli-quit-exits 1 "gone in $(( $(date +%s) - T0 ))s; cli: $(head -c 80 "$EV/cli-q.txt")"; else check step3-cli-quit-exits 0 "still running after 15s; cli: $(head -c 80 "$EV/cli-q.txt")"; stop_group "$PRIMARY"; fi
[ "$(cat "$EV/cli-q.rc")" = 0 ] && check step3-cli-rc 1 "rc=0" || check step3-cli-rc 0 "rc=$(cat "$EV/cli-q.rc")"
cli n quit
grep -q 'not running' "$EV/cli-n.txt" && check step3-cli-not-running 1 "$(head -c 60 "$EV/cli-n.txt")" || check step3-cli-not-running 0 "$(head -c 80 "$EV/cli-n.txt")"

# ---- step 4: relaunch twice, compare X sizes ----
sizecycle() { # $1 tag ; echoes X size
  boot "$1"; local w s
  for _ in $(seq 1 40); do
    api "http://127.0.0.1:$PORT/api/window/state" > "$EV/state-$1.json" 2> /dev/null
    grep -q '"visible": *true' "$EV/state-$1.json" && break; sleep 0.5; done
  sleep 2; w=$(toplevel); s=$(xsize "$w"); DISPLAY=:99 xwininfo -id "$w" > "$EV/xwininfo-$1.txt" 2>&1
  DISPLAY=:99 python3 /tmp/wmdelete.py "$w" 2>> "$EV/wmdelete.err"
  sleep 1; cli "$1" quit   # the close only hides now; quit ends the process
  wait_exit 15 || { stop_group "$APPPG"; echo "quit hung ($1)" >> "$EV/inner.log"; }
  cp "$DATA/window-state.json" "$EV/window-state-$1.json" 2> /dev/null
  echo "$s"
}
log "step 4"
S1=$(sizecycle b); S2=$(sizecycle c)
[ -n "$S1" ] && [ "$S1" = "$S2" ] && check step4-size-stable 1 "S1=$S1 S2=$S2" || check step4-size-stable 0 "S1=$S1 S2=$S2"
D2=$(python3 -c "import json;d=json.load(open('$EV/window-state-b.json'));print(d['width'],d['height'])" 2>/dev/null)
D3=$(python3 -c "import json;d=json.load(open('$EV/window-state-c.json'));print(d['width'],d['height'])" 2>/dev/null)
[ -n "$D2" ] && [ "$D2" = "$D3" ] && check step4-saved-equal 1 "save2=$D2 save3=$D3" || check step4-saved-equal 0 "save2='$D2' save3='$D3'"

# ---- step 5: quit route ----
log "step 5"
boot d
for _ in $(seq 1 40); do api "http://127.0.0.1:$PORT/api/window/state" > "$EV/state-d.json" 2> /dev/null
  grep -q '"visible": *true' "$EV/state-d.json" && break; sleep 0.5; done
PIDD=$(sed -n 's/.*"pid": *\([0-9]*\).*/\1/p' "$EV/state-d.json")
Q=$(api -X POST "http://127.0.0.1:$PORT/api/window/quit"); echo "$Q" > "$EV/quit.json"
QP=$(echo "$Q" | sed -n 's/.*"pid": *\([0-9]*\).*/\1/p')
case "$Q" in *'"quit": true'*|*'"quit":true'*) [ -n "$QP" ] && [ "$QP" = "$PIDD" ] && check step5-quit-reply 1 "$Q" || check step5-quit-reply 0 "$Q pid state=$PIDD";; *) check step5-quit-reply 0 "$Q";; esac
if wait_exit 15; then check step5-quit-exits 1 "group gone within 15s"; else check step5-quit-exits 0 "still running"; stop_group "$APPPG"; fi

kill "$XPID" 2> /dev/null
[ "$FAILS" = 0 ] && echo "OVERALL PASS" >> "$RES" || echo "OVERALL FAIL ($FAILS)" >> "$RES"
exit 0
