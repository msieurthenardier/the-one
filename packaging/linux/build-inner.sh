#!/usr/bin/env bash
# Container side of build.sh (Mission 32 Flight 2): freeze, assemble the AppImage fallback,
# wrap the AppImage and the .deb. Runs as the invoking uid inside the m32/linux-build image,
# with no network. Mounts: /packaging (ro), /stage (ro), /out (rw).
#   build-inner.sh [--no-excludes]
# Names, paths and the version come from /stage/rendered/build.env (build.sh renders it from
# packaging/product.toml); the rendered templates are in /stage/rendered/.
set -euo pipefail

NO_EXCLUDES="${1:-}"
HERE=/packaging/linux
OUT=/out
R=/stage/rendered
# Only machine-safe values go in build.env; refuse anything else before sourcing it.
if grep -qvE '^[A-Z][A-Z0-9_]*=[A-Za-z0-9._/+~:-]*$' "$R/build.env"; then
    echo "build.env has a line outside KEY=safe-value" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
. "$R/build.env"
set +a
export HOME="$OUT/home" UV_CACHE_DIR="$OUT/home/uv-cache" PYINSTALLER_CONFIG_DIR="$OUT/home/pyi-config"
mkdir -p "$HOME"

WORK="$OUT/linux-$VERSION"
PKGS="$OUT/packages"
APPIMAGE="$PKGS/$FILE_STEM-$VERSION-x86_64.AppImage"
DEB="$PKGS/${PACKAGE}_${DEB_VERSION}_amd64.deb"
FB_ROOT=/opt/fallback-root/usr/lib/x86_64-linux-gnu
SONAMES=(libgirepository-2.0.so.0 libdbusmenu-glib.so.4 libdbusmenu-gtk3.so.4
         libayatana-ido3-0.4.so.0 libayatana-indicator3.so.7 libayatana-appindicator3.so.1)
TYPELIB=AyatanaAppIndicator3-0.1.typelib

rm -rf "$WORK"; mkdir -p "$WORK" "$PKGS"

echo "== toolchain"
echo "Python: $(python --version 2>&1 | cut -d' ' -f2)"
echo "PyInstaller: $(pyinstaller --version)"
echo "== bundled library versions (float with 24.04 updates)"
dpkg-query -W -f='${Package} ${Version}\n' libglib2.0-0t64 libgirepository-2.0-0 2>&1
for f in /opt/fallback-debs/*.deb; do dpkg-deb -f "$f" Package Version | paste -sd' '; done

echo "== freeze $VERSION"
if [ "$NO_EXCLUDES" = "--no-excludes" ]; then export M32_NO_EXCLUDES=1; fi
M32_STAGE=/stage pyinstaller --noconfirm --clean --distpath "$WORK/dist" --workpath "$WORK/work" \
    "$HERE/the-one.spec" > "$WORK/pyinstaller.log" 2>&1
BUNDLE="$WORK/dist/the-one"
test -x "$BUNDLE/the-one"
if [ "$NO_EXCLUDES" != "--no-excludes" ]; then
    echo "== bundle audit"
    python "$HERE/audit.py" "$BUNDLE" --excludes "$HERE/excludes.txt"
fi
SIZE_KB="$(du -sk "$BUNDLE" | cut -f1)"

echo "== fallback set"
FB="$WORK/fallback"
rm -rf "$FB"; mkdir -p "$FB/lib" "$FB/girepository-1.0"
# libgirepository: the system copy (installed system-wide, as on the Flight 1 host).
cp -L "$(ldconfig -p | awk '/libgirepository-2\.0\.so\.0 /{print $NF; exit}')" "$FB/lib/libgirepository-2.0.so.0"
# the Ayatana stack: extracted from the downloaded debs, real files named by soname
for s in "${SONAMES[@]:1}"; do cp -L "$FB_ROOT/$s" "$FB/lib/$s"; done
cp -L "$FB_ROOT/girepository-1.0/$TYPELIB" "$FB/girepository-1.0/$TYPELIB"
chmod 644 "$FB/lib/"* "$FB/girepository-1.0/"*

# NEEDED walk: a fallback library may need only glibc, libffi.so.8, a family excludes.txt
# leaves to the host, or another fallback library.
python - "$FB/lib" "$HERE/excludes.txt" <<'PY'
import fnmatch, subprocess, sys
from pathlib import Path
libdir, excl = Path(sys.argv[1]), sys.argv[2]
pats = []
for line in open(excl, encoding="utf-8"):
    line = line.split("#", 1)[0].strip()
    if line:
        pats.append(line)
glibc = {"libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0", "librt.so.1", "ld-linux-x86-64.so.2"}
own = {p.name for p in libdir.iterdir()}
bad = []
for lib in sorted(libdir.iterdir()):
    out = subprocess.run(["readelf", "-d", str(lib)], capture_output=True, text=True, check=True).stdout
    needed = [l.split("[")[1].rstrip("]") for l in out.splitlines() if "(NEEDED)" in l]
    print(f"NEEDED {lib.name}: {' '.join(needed)}")
    for n in needed:
        if n in glibc or n in own or n == "libffi.so.8" or any(fnmatch.fnmatch(n, p) for p in pats):
            continue
        bad.append((lib.name, n))
if bad:
    print("NEEDED walk FAILED:", bad)
    sys.exit(1)
print("NEEDED walk OK")
PY
(cd "$FB/lib" && ls -l && sha256sum -- * ../girepository-1.0/*)

echo "== validate"
validate() {   # validate <desktop file>...
    for f in "$@"; do desktop-file-validate "$f" && echo "desktop-file-validate OK: $f"; done
}
# the integration template holds runtime placeholders: validate it filled with sample values
sed -e 's|@APPIMAGE_EXEC@|"/home/u/My App/G.AppImage"|' -e 's|@APPIMAGE_PATH@|/home/u/My App/G.AppImage|' \
    -e 's|@ICON_PATH@|/home/u/.local/share/icons/x.png|' "$R/integration.desktop.in" \
    > "$WORK/integration-sample.desktop"
validate "$R/deb.desktop" "$R/appimage-root.desktop" "$WORK/integration-sample.desktop"
appstreamcli validate --no-net "$R/metainfo.xml"

echo "== AppImage"
APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/icons/hicolor/512x512/apps" \
    "$APPDIR/usr/share/metainfo" "$APPDIR/usr/share/$PACKAGE"
cp -a "$BUNDLE" "$APPDIR/usr/lib/$PACKAGE"
cp -a "$FB" "$APPDIR/usr/lib/$PACKAGE-fallback"
cp "$R/AppRun" "$APPDIR/AppRun"; chmod 755 "$APPDIR/AppRun"
cp "$R/appimage-root.desktop" "$APPDIR/$DESKTOP_ID.desktop"
cp "$R/integration.desktop.in" "$APPDIR/usr/share/$PACKAGE/integration.desktop.in"
# appimagetool only validates metadata named after the desktop file (and with the network), and
# AppStream wants the file named after the component id: the id wins; we validate it above.
cp "$R/metainfo.xml" "$APPDIR/usr/share/metainfo/$METAINFO_ID.metainfo.xml"
cp /stage/icon-512.png "$APPDIR/$DESKTOP_ID.png"
cp /stage/icon-512.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/$DESKTOP_ID.png"
ln -sf "$DESKTOP_ID.png" "$APPDIR/.DirIcon"
rm -f "$APPIMAGE"
ARCH=x86_64 /opt/tools/appimagetool-x86_64.AppImage --appimage-extract-and-run \
    --runtime-file /opt/tools/runtime-x86_64 "$APPDIR" "$APPIMAGE" > "$WORK/appimagetool.log" 2>&1

echo "== deb"
ROOT="$WORK/debroot"
mkdir -p "$ROOT$(dirname "$INSTALL_DIR")" "$ROOT/usr/bin" "$ROOT/usr/share/applications" \
    "$ROOT/usr/share/icons/hicolor/512x512/apps" "$ROOT/usr/share/metainfo" "$ROOT/DEBIAN"
cp -a "$BUNDLE" "$ROOT$INSTALL_DIR"
ln -s "$INSTALL_DIR/$EXECUTABLE" "$ROOT/usr/bin/$EXECUTABLE"
cp "$R/deb.desktop" "$ROOT/usr/share/applications/$DESKTOP_ID.desktop"
cp "$R/metainfo.xml" "$ROOT/usr/share/metainfo/$METAINFO_ID.metainfo.xml"
cp /stage/icon-512.png "$ROOT/usr/share/icons/hicolor/512x512/apps/$DESKTOP_ID.png"
sed "s|@INSTALLED_SIZE@|$SIZE_KB|" "$R/control" > "$ROOT/DEBIAN/control"
find "$ROOT" -type d -exec chmod 755 {} +
rm -f "$DEB"
dpkg-deb --root-owner-group -Zzstd -z9 --build "$ROOT" "$DEB" > "$WORK/dpkg-deb.log" 2>&1

echo "== done"
ls -l "$APPIMAGE" "$DEB"
