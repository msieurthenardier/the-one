#!/bin/bash
# Gate runner, container side (packaging checks). Run by gates.sh inside ONE disposable container for one package x image.
# Env in: FORMAT=deb|appimage  WINDOW=0|1  PK=/packages  EV=/evidence
#         VER_N VER_N1 (display versions, e.g. 0.11.8 0.11.9.dev1)  DEB_N DEB_N1 APPIMG_N APPIMG_N1
#         EXTRA_APT (packages to apt-get install before the run, AC6 variants)
#         DISPLAY_MODE=wslg|xvfb (default wslg: the mounted X socket is :0; xvfb: a private Xvfb :99)
#         WENV_EXTRA (space separated K=V added to the window/probe environment)
# Everything it learns is written under $EV as plain files; score.py reads them.
# shellcheck disable=SC2164,SC2002,SC2086,SC2009,SC2034,SC2206
set -u
PORT_SERVE=8491
PORT_APP=8490
mkdir -p "$EV"
XDISP=:0; [ "${DISPLAY_MODE:-wslg}" = xvfb ] && XDISP=:99
log() { echo "[inner $(date +%T)] $*" | tee -a "$EV/inner.log"; }

useradd -m -s /bin/bash tester 2>/dev/null
install -d -o tester -g tester /home/tester/scratch /home/tester/scratch/cwd /home/tester/scratch/data
XRD=/tmp/xdg-runtime-tester
install -d -m 700 -o tester -g tester "$XRD"
# run as the non-root user, real HOME, no THE_ONE_* override unless the caller adds one
rt() { (cd /home/tester/scratch/cwd && runuser -u tester -- env -i HOME=/home/tester USER=tester \
  PATH="$PATH" LANG=C.UTF-8 XDG_RUNTIME_DIR="$XRD" "$@"); }

{
  echo "== os-release"; cat /etc/os-release
  echo "== system python3"; python3 --version; readlink -f "$(command -v python3)"
  echo "== uname"; uname -a
  echo "== dev/dri"; ls /dev/dri 2>&1
  echo "== packages"
  dpkg-query -W -f='${Package} ${Version}\n' python3 libwebkit2gtk-4.1-0 gir1.2-webkit2-4.1 gir1.2-gtk-3.0 \
    gir1.2-ayatanaappindicator3-0.1 libgirepository-2.0-0 bubblewrap libstdc++6 libgcc-s1 2>&1
} > "$EV/env.txt"

install_pkg() { # $1 = deb|appimage  $2 = n|n1  -> installs, output to $3
  local which="$2" out="$3"
  if [ "$FORMAT" = deb ]; then
    local f; [ "$which" = n ] && f="$DEB_N" || f="$DEB_N1"
    install -m 644 "$PK/$f" "/tmp/$f"
    { echo "$ apt-get install -y ./$f"; local t0=$SECONDS; apt-get install -y "/tmp/$f" 2>&1; echo "rc=$?"; echo "apt wall $((SECONDS-t0))s"; } > "$out" 2>&1
  else
    local f; [ "$which" = n ] && f="$APPIMG_N" || f="$APPIMG_N1"
    install -d /opt/m32
    cp "$PK/$f" /opt/m32/the-one.AppImage && chmod 755 /opt/m32/the-one.AppImage
    cat > /usr/local/bin/the-one <<'W'
#!/bin/sh
# containers have no FUSE: run the AppImage by extracting it first
APPIMAGE_EXTRACT_AND_RUN=1 exec /opt/m32/the-one.AppImage "$@"
W
    chmod 755 /usr/local/bin/the-one
    echo "placed $f as /opt/m32/the-one.AppImage" > "$out"
  fi
}

wait_live() { # $1 port, $2 seconds
  local i; for i in $(seq 1 "$2"); do
    curl -fsS -m 2 "http://127.0.0.1:$1/api/live" >/dev/null 2>&1 && return 0; sleep 1; done; return 1
}
stop_group() { # $1 pid (a session leader started with setsid)
  kill -TERM -- "-$1" 2>/dev/null; local i
  for i in $(seq 1 15); do kill -0 "-$1" 2>/dev/null || return 0; sleep 1; done
  kill -KILL -- "-$1" 2>/dev/null
}
start_serve() { # $1 data-dir-or-empty  $2 logfile ; echoes pid
  if [ -n "$1" ]; then
    (cd /home/tester/scratch/cwd; setsid runuser -u tester -- env -i HOME=/home/tester PATH="$PATH" LANG=C.UTF-8 \
      THE_ONE_PORT=$PORT_SERVE THE_ONE_DATA_DIR="$1" the-one serve > "$2" 2>&1 & echo $!)
  else
    (cd /home/tester/scratch/cwd; setsid runuser -u tester -- env -i HOME=/home/tester PATH="$PATH" LANG=C.UTF-8 \
      THE_ONE_PORT=$PORT_SERVE the-one serve > "$2" 2>&1 & echo $!)
  fi
}
DD=/home/tester/.local/share/the-one

apt-get update > "$EV/apt-update.txt" 2>&1; echo "rc=$?" >> "$EV/apt-update.txt"

if [ -n "${EXTRA_APT:-}" ]; then
  log "extra apt: $EXTRA_APT"
  # shellcheck disable=SC2086
  { apt-get install -y $EXTRA_APT 2>&1; echo "rc=$?"; } > "$EV/extra-apt.txt" 2>&1
fi
# Which fallback sonames does the HOST resolve, before the app is installed? (ldconfig, not dpkg)
{
  for so in libgirepository-2.0.so.0 libdbusmenu-glib.so.4 libdbusmenu-gtk3.so.4 libayatana-ido3-0.4.so.0 \
            libayatana-indicator3.so.7 libayatana-appindicator3.so.1; do
    if ldconfig -p | grep -q -F "$so "; then echo "$so yes $(ldconfig -p | grep -F "$so " | head -1 | sed 's/.*=> //')"; else echo "$so no -"; fi
  done
  for t in AyatanaAppIndicator3-0.1.typelib AppIndicator3-0.1.typelib; do
    if compgen -G "/usr/lib/*/girepository-1.0/$t" >/dev/null || [ -e "/usr/lib/girepository-1.0/$t" ]; then echo "$t yes"; else echo "$t no"; fi
  done
} > "$EV/host-libs.txt"

# ---- N installed -----------------------------------------------------------
log "install N"
install_pkg "$FORMAT" n "$EV/install-N.txt"
rt the-one version > "$EV/version-N.txt" 2>&1; echo "rc=$?" >> "$EV/version-N.txt"

# ---- probe mode (flight 2 AC4): after the install, run the ABI probe instead of the flow ----
case " ${WENV_EXTRA:-} " in *" THE_ONE_PKG_ABI_PROBE=1 "*)
  log "ABI probe"
  # shellcheck disable=SC2206
  WENV=(DISPLAY=$XDISP GDK_BACKEND=x11 PYWEBVIEW_GUI=gtk PYSTRAY_BACKEND=gtk
        WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1 WEBKIT_DISABLE_COMPOSITING_MODE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 LIBGL_ALWAYS_SOFTWARE=1
        THE_ONE_DATA_DIR=/home/tester/scratch/data ${WENV_EXTRA:-})
  (cd /home/tester/scratch/cwd; runuser -u tester -- env -i HOME=/home/tester PATH="$PATH" LANG=C.UTF-8 \
     XDG_RUNTIME_DIR="$XRD" "${WENV[@]}" timeout 120 dbus-run-session -- the-one version \
     > "$EV/probe.stdout" 2> "$EV/probe.stderr"; echo "rc=$?" > "$EV/probe.rc")
  log "probe done"; exit 0;;
esac

# ---- gate 4 (default data dir, nothing seeded yet) + upgrade part 1 ---------
log "gate 4: rotate-api-credential with no override"
rt the-one rotate-api-credential > "$EV/gate4-rotate.txt" 2>&1; echo "rc=$?" >> "$EV/gate4-rotate.txt"
SP=$(start_serve "" "$EV/serve-N.log"); echo "$SP" > "$EV/serve-N.pid"
if wait_live $PORT_SERVE 90; then echo live > "$EV/serve-N.state"; else echo "NOT live" > "$EV/serve-N.state"; fi
ls -la "$DD" > "$EV/gate4-ls.txt" 2>&1
CRED=$(cat "$DD/api-credential" 2>/dev/null | tr -d '[:space:]')
echo "${CRED%%.*}" > "$EV/cred-prefix-N.txt"
curl -sS -m 20 -X POST -H "Authorization: Bearer $CRED" -H 'Content-Type: application/json' \
  -d '{"name":"m32-upgrade-agent","description":"seeded under N"}' \
  "http://127.0.0.1:$PORT_SERVE/api/agents" > "$EV/seed-agent.txt" 2>&1; echo " http_rc=$?" >> "$EV/seed-agent.txt"
curl -sS -m 20 -H "Authorization: Bearer $CRED" "http://127.0.0.1:$PORT_SERVE/api/agents" > "$EV/agents-N.json" 2>&1
stop_group "$SP"; echo "stopped N serve pgid $SP" >> "$EV/serve-N.state"
ls -la "$DD" > "$EV/gate4-ls-after-stop.txt" 2>&1

# ---- upgrade to N+1 --------------------------------------------------------
log "install N+1"
install_pkg "$FORMAT" n1 "$EV/install-N1.txt"
rt the-one version > "$EV/version-N1.txt" 2>&1; echo "rc=$?" >> "$EV/version-N1.txt"
SP=$(start_serve "" "$EV/serve-N1.log"); echo "$SP" > "$EV/serve-N1.pid"
if wait_live $PORT_SERVE 90; then echo live > "$EV/serve-N1.state"; else echo "NOT live" > "$EV/serve-N1.state"; fi
CRED1=$(cat "$DD/api-credential" 2>/dev/null | tr -d '[:space:]')
echo "${CRED1%%.*}" > "$EV/cred-prefix-N1.txt"
curl -sS -m 20 -H "Authorization: Bearer $CRED1" "http://127.0.0.1:$PORT_SERVE/api/agents" > "$EV/agents-N1.json" 2>&1
stop_group "$SP"

# ---- gate 1 (doctor, pinned and unpinned), gate 2 ---------------------------
log "doctor (under xvfb-run: the pystray gtk backend needs an X display to init Gtk)"
rm -rf /home/tester/scratch/data && install -d -o tester -g tester /home/tester/scratch/data
SC=/home/tester/scratch/data
rt xvfb-run -a env THE_ONE_DATA_DIR=$SC PYWEBVIEW_GUI=gtk PYSTRAY_BACKEND=gtk the-one doctor > "$EV/doctor-pinned.txt" 2>&1
echo "rc=$?" >> "$EV/doctor-pinned.txt"
rt xvfb-run -a env THE_ONE_DATA_DIR=$SC PYWEBVIEW_GUI=gtk the-one doctor > "$EV/doctor-unpinned.txt" 2>&1
echo "rc=$?" >> "$EV/doctor-unpinned.txt"
# gate 2: run the interpreter doctor resolved, independently
PYP=$(sed -n 's/.*python interpreter: OK.*resolved to //p' "$EV/doctor-unpinned.txt" | head -1 | tr -d '\r')
echo "resolved: $PYP" > "$EV/gate2.txt"
if [ -n "$PYP" ]; then
  rt "$PYP" -c 'import sys; print(sys.executable, sys.prefix)' >> "$EV/gate2.txt" 2>&1
  "$PYP" --version >> "$EV/gate2.txt" 2>&1
fi
# sandbox note: what bwrap says in the container (not representative of a desktop)
{ command -v bwrap && rt bwrap --ro-bind / / --unshare-user true; echo "bwrap rc=$?"; } > "$EV/sandbox.txt" 2>&1
grep -i -E 'sandbox|bwrap|bubblewrap' "$EV/doctor-unpinned.txt" >> "$EV/sandbox.txt" 2>&1

# ---- tray: typelib + pinned backend load inside the bundle ------------------
ls /usr/lib/*/girepository-1.0/AyatanaAppIndicator3-0.1.typelib > "$EV/tray.txt" 2>&1
grep -i 'desktop shell' "$EV/doctor-pinned.txt" "$EV/doctor-unpinned.txt" >> "$EV/tray.txt" 2>&1

[ "$WINDOW" = 1 ] || { log "no window on this image"; exit 0; }

# ---- the window: gate 3, screenshot, single instance (AC6) -------------------
log "window (display ${DISPLAY_MODE:-wslg} $XDISP)"
if [ "${DISPLAY_MODE:-wslg}" = xvfb ]; then
  (setsid runuser -u tester -- Xvfb "$XDISP" -screen 0 1920x1080x24 > "$EV/xvfb-main.log" 2>&1 & echo $! > "$EV/xvfb-main.pid")
  for i in $(seq 1 50); do [ -S "/tmp/.X11-unix/X${XDISP#:}" ] && break; sleep 0.2; done
fi
export_env() { :; }
WENV=(DISPLAY=$XDISP GDK_BACKEND=x11 PYWEBVIEW_GUI=gtk PYSTRAY_BACKEND=gtk
      WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1 WEBKIT_DISABLE_COMPOSITING_MODE=1  WEBKIT_DISABLE_DMABUF_RENDERER=1 LIBGL_ALWAYS_SOFTWARE=1
      THE_ONE_PORT=$PORT_APP THE_ONE_DATA_DIR=$SC)
# shellcheck disable=SC2206
WENV+=(${WENV_EXTRA:-})
printf '%s\n' "${WENV[@]}" > "$EV/window-env.txt"

(cd /home/tester/scratch/cwd; setsid runuser -u tester -- env -i HOME=/home/tester PATH="$PATH" LANG=C.UTF-8 \
   XDG_RUNTIME_DIR="$XRD" "${WENV[@]}" dbus-run-session -- the-one app > "$EV/app.log" 2>&1 &
 echo $! > "$EV/app.pid")
APP=$(cat "$EV/app.pid")
wait_live $PORT_APP 120 && echo live > "$EV/app.state" || echo "server NOT live" > "$EV/app.state"

# /proc/<pid>/maps of another uid needs ptrace rights (docker drops CAP_SYS_PTRACE even for root):
# read it as the same user that owns the app
maps_of() { runuser -u tester -- cat "/proc/$1/maps" 2>/dev/null; }
# find the UI process: has libgtk-3 mapped and is not a WebKit helper
find_ui() {
  local p
  for p in /proc/[0-9]*; do
    p=${p#/proc/}
    tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q 'the-one' || continue
    maps_of "$p" | grep -q 'libgtk-3' || continue
    tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q 'WebKit' && continue
    echo "$p"
  done
}
UI=""; WEB=""
for i in $(seq 1 90); do
  UI=$(find_ui | tail -1)
  WEB=$(for p in /proc/[0-9]*; do p=${p#/proc/}; tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q 'WebKitWebProcess' && echo $p; done)
  [ -n "$UI" ] && [ -n "$WEB" ] && break; sleep 1
done
sleep 6
for p in /proc/[0-9]*; do p=${p#/proc/}; echo "pid $p gtk=$(maps_of $p | grep -c 'libgtk-3') webkit=$(maps_of $p | grep -c 'libwebkit2gtk') $(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | cut -c1-80)"; done > "$EV/maps-probe.txt" 2>&1
{ echo "ui=$UI"; echo "web=$WEB"; ps -eo pid,ppid,pgid,stat,args | grep -v grep | grep -E 'the-one|WebKit|dbus' ; } > "$EV/window-procs.txt"
[ -n "$UI" ] && maps_of "$UI" > "$EV/ui.maps"
for w in $WEB; do maps_of "$w" > "$EV/web-$w.maps"; done
[ -n "$UI" ] && runuser -u tester -- cat "/proc/$UI/environ" 2>/dev/null | tr '\0' '\n' > "$EV/ui.environ"
for w in $WEB; do runuser -u tester -- cat "/proc/$w/environ" 2>/dev/null | tr '\0' '\n' > "$EV/web-$w.environ"; done
tail -30 "$EV/app.log" > "$EV/app.log.tail"

# AC6: second launch
CREDA=$(cat "$SC/api-credential" 2>/dev/null | tr -d '[:space:]')
T0=$(date +%s.%N)
(cd /home/tester/scratch/cwd; setsid runuser -u tester -- env -i HOME=/home/tester PATH="$PATH" LANG=C.UTF-8 \
   XDG_RUNTIME_DIR="$XRD" "${WENV[@]}" dbus-run-session -- the-one app > "$EV/second.log" 2>&1 &
 echo $! > "$EV/second.pid")
S2=$(cat "$EV/second.pid"); RC2=timeout
for i in $(seq 1 100); do
  if ! kill -0 "$S2" 2>/dev/null; then RC2=exited; break; fi; sleep 0.1; done
T1=$(date +%s.%N)
[ "$RC2" = timeout ] && { kill -KILL -- "-$S2" 2>/dev/null; }
{ echo "second_state=$RC2"; echo "elapsed=$(echo "$T1 - $T0" | bc -l 2>/dev/null || python3 -c "print($T1-$T0)")"; } > "$EV/single-instance.txt"
python3 - >> "$EV/single-instance.txt" <<'PY'
import os
n = 0
for line in open("/proc/net/tcp").read().splitlines()[1:]:
    f = line.split()
    if f[3] == "0A" and int(f[1].split(":")[1], 16) in (8490, 8491):
        n += 1
print("listening sockets on 8490/8491:", n)
PY
ps -eo pid,ppid,pgid,stat,args | grep -E 'the-one' | grep -v grep >> "$EV/single-instance.txt"
curl -sS -m 10 -X POST -H "Authorization: Bearer $CREDA" "http://127.0.0.1:$PORT_APP/api/window/focus" > "$EV/focus.txt" 2>&1
sleep 4
# screenshot of the window only (never the whole WSLg desktop). Taken AFTER the focus call:
# the main window is created hidden and only maps once a focus request arrives (finding).
WID=""
for i in $(seq 1 60); do
  DISPLAY=$XDISP xwininfo -root -tree > "$EV/xwininfo-tree.txt" 2>&1
  WID=$(grep -E '"GleepGlorp AI"' "$EV/xwininfo-tree.txt" | head -1 | awk '{print $1}')
  [ -n "$WID" ] && DISPLAY=$XDISP xwininfo -id "$WID" 2>&1 | grep -q IsViewable && break; sleep 1
done
[ -n "$WID" ] && DISPLAY=$XDISP xwininfo -id "$WID" > "$EV/xwininfo-window.txt" 2>&1
echo "window id: ${WID:-none}" > "$EV/screenshot.txt"
if [ -n "$WID" ]; then DISPLAY=$XDISP xwd -id "$WID" -out "$EV/window.xwd" >> "$EV/screenshot.txt" 2>&1; fi
stop_group "$APP"

# Fallback screenshot: the forwarded WSLg X server leaves the window unmapped (xwd -> BadMatch),
# so render the same window on a private Xvfb and capture that. Same bundle, same host WebKit.
if [ ! -s "$EV/window.xwd" ]; then
  log "fallback screenshot under Xvfb"
  FD=/home/tester/scratch/data-xvfb; install -d -o tester -g tester "$FD"
  cat > /tmp/xvfb-shot.sh <<'SH'
#!/bin/bash
# inside xvfb-run: start the app, wait for the window to be viewable, dump it
the-one app > "$1/app-xvfb.log" 2>&1 &
APPPID=$!
for i in $(seq 1 120); do curl -fsS -m 2 http://127.0.0.1:8492/api/live >/dev/null 2>&1 && break; sleep 1; done
for i in $(seq 1 60); do
  W=$(xwininfo -root -tree | grep '"GleepGlorp AI"' | head -1 | awk '{print $1}')
  [ -n "$W" ] && xwininfo -id "$W" | grep -q IsViewable && break; sleep 1
done
sleep 5
C=$(cat "$THE_ONE_DATA_DIR/api-credential"); curl -s -X POST -H "Authorization: Bearer $C" http://127.0.0.1:8492/api/window/focus; echo
for i in $(seq 1 30); do W=$(xwininfo -root -tree | grep '"GleepGlorp AI"' | head -1 | awk '{print $1}'); [ -n "$W" ] && xwininfo -id "$W" | grep -q IsViewable && break; sleep 1; done
sleep 4
xwininfo -root -tree > "$1/xwininfo-tree-xvfb.txt" 2>&1
# the private Xvfb root holds only this app (-id on the ARGB window gives BadMatch)
xwd -root -out /tmp/xvfb-window.xwd 2>&1; echo "root capture; app window ${W:-none}"
kill -TERM "$APPPID" 2>/dev/null
SH
  chmod 755 /tmp/xvfb-shot.sh; chmod 777 "$EV"; rm -f "$EV/window.xwd"; chmod 1777 /tmp
  (cd /home/tester/scratch/cwd; setsid runuser -u tester -- env -i HOME=/home/tester PATH="$PATH" LANG=C.UTF-8 \
     XDG_RUNTIME_DIR="$XRD" GDK_BACKEND=x11 PYWEBVIEW_GUI=gtk PYSTRAY_BACKEND=gtk \
     WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1 WEBKIT_DISABLE_COMPOSITING_MODE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1 LIBGL_ALWAYS_SOFTWARE=1 \
     THE_ONE_PORT=8492 THE_ONE_DATA_DIR="$FD" \
     xvfb-run -a -s "-screen 0 1440x900x24" dbus-run-session -- /tmp/xvfb-shot.sh "$EV" > "$EV/screenshot-xvfb.txt" 2>&1 &
   echo $! > "$EV/app-xvfb.pid")
  XP=$(cat "$EV/app-xvfb.pid")
  for i in $(seq 1 240); do kill -0 "-$XP" 2>/dev/null || break; sleep 1; done
  rm -f "$EV/window.xwd"; cp /tmp/xvfb-window.xwd "$EV/window.xwd" 2>>"$EV/screenshot-xvfb.txt"
  echo "source=xvfb-fallback" >> "$EV/screenshot-xvfb.txt"
  stop_group "$XP"
fi
log "done"
