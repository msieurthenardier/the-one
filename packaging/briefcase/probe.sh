#!/usr/bin/env bash
# AC0/AC3/AC4 probes for candidate B (spike tooling, Mission 32 Flight 1). One container per distro.
#   packaging/briefcase/probe.sh <label> <pkgdir> <version>      e.g. B-patched $PKGS 0.11.9.dev1
# Writes $M32_EVIDENCE/<label>/probe/<distro>/*.txt (+ window.png for the desktop-entry launch).
set -u
LABEL="${1:?label}"; PKG="${2:?pkgdir}"; VER="${3:?version}"
HERE="$(cd "$(dirname "$0")" && pwd)"
EVR="${M32_EVIDENCE:-$HOME/the-one-m32-evidence}"
M32_BUILD="${M32_BUILD:-$HOME/the-one-m32-build}"
for spec in "ubuntu-26.04 ubuntu-resolute" "debian-13 debian-trixie"; do
  set -- $spec; D=$1; TAG=$2
  EV="$EVR/$LABEL/probe/$D"; rm -rf "$EV"; mkdir -p "$EV"; chmod 777 "$EV"
  docker run --rm --name "m32-probe-$LABEL-$D" -v "$PKG:/p:ro" -v "$EV:/ev" -v "$M32_BUILD/probe-sc:/probe:ro" \
    -v /mnt/wslg/.X11-unix:/tmp/.X11-unix -e F="the-one_${VER}-1~${TAG}_amd64.deb" "m32/$D:baseline" bash -c '
set -u
apt-get update >/dev/null 2>&1; apt-get install -y "/p/$F" > /ev/apt.txt 2>&1; echo "apt rc=$?" >> /ev/apt.txt
useradd -m t; install -d -o t -g t /home/t/data /home/t/cwd; XRD=/tmp/xdg-t; install -d -m 700 -o t -g t $XRD
cp /probe/m32probe.py /probe/m32probe2.py /usr/lib/the-one/app/
rt() { (cd /home/t/cwd && runuser -u t -- env -i HOME=/home/t PATH="$PATH" LANG=C.UTF-8 XDG_RUNTIME_DIR=$XRD THE_ONE_DATA_DIR=/home/t/data "$@"); }
rt env BRIEFCASE_MAIN_MODULE=m32probe the-one a b > /ev/ac0.txt 2>&1
rt env BRIEFCASE_MAIN_MODULE=m32probe2 the-one > /ev/ac4-path.txt 2>&1
grep -E "^Exec|^Icon" /usr/share/applications/ai.gleepglorp.the-one.desktop > /ev/desktop-exec.txt
# AC3: launch the way the desktop entry does: Exec=/usr/bin/the-one %F with no files -> no arguments
which gtk-launch > /ev/gtk-launch.txt 2>&1
(cd /home/t/cwd; setsid runuser -u t -- env -i HOME=/home/t PATH="$PATH" LANG=C.UTF-8 XDG_RUNTIME_DIR=$XRD DISPLAY=:0 GDK_BACKEND=x11 \
  PYWEBVIEW_GUI=gtk PYSTRAY_BACKEND=gtk WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1 WEBKIT_DISABLE_COMPOSITING_MODE=1 \
  WEBKIT_DISABLE_DMABUF_RENDERER=1 LIBGL_ALWAYS_SOFTWARE=1 THE_ONE_PORT=8490 THE_ONE_DATA_DIR=/home/t/data \
  dbus-run-session -- /usr/bin/the-one > /ev/bare-launch.log 2>&1 < /dev/null & echo $! > /ev/bare.pid)
P=$(cat /ev/bare.pid)
for i in $(seq 1 90); do curl -fsS -m 2 http://127.0.0.1:8490/api/live >/dev/null 2>&1 && break; sleep 1; done
echo "live=$(curl -s -m 2 http://127.0.0.1:8490/api/live)" > /ev/bare-state.txt
C=$(cat /home/t/data/api-credential | tr -d "[:space:]")
sleep 5; curl -s -X POST -H "Authorization: Bearer $C" http://127.0.0.1:8490/api/window/focus >> /ev/bare-state.txt; echo >> /ev/bare-state.txt
W=""; for i in $(seq 1 40); do DISPLAY=:0 xwininfo -root -tree > /ev/xwininfo-tree.txt 2>&1
  W=$(grep "\"GleepGlorp AI\"" /ev/xwininfo-tree.txt | head -1 | awk "{print \$1}")
  [ -n "$W" ] && DISPLAY=:0 xwininfo -id "$W" 2>&1 | grep -q IsViewable && break; sleep 1; done
echo "window id: ${W:-none}" >> /ev/bare-state.txt
[ -n "$W" ] && DISPLAY=:0 xwd -id "$W" -out /ev/window.xwd >> /ev/bare-state.txt 2>&1
ps -eo pid,args | grep -E "the-one|WebKitWebProcess" | grep -v grep | cut -c1-120 >> /ev/bare-state.txt
kill -TERM -- -$P 2>/dev/null; sleep 3; kill -KILL -- -$P 2>/dev/null
chmod -R a+r /ev
' > "$EV/container.log" 2>&1
  [ -f "$EV/window.xwd" ] && "${PYTHON:-$HERE/../../.venv/bin/python}" "$HERE/../spike/xwd2png.py" "$EV/window.xwd" "$EV/window.png" >/dev/null 2>&1
  echo "== $LABEL $D"; cat "$EV/ac0.txt" "$EV/ac4-path.txt" "$EV/desktop-exec.txt" "$EV/bare-state.txt" 2>/dev/null
done
