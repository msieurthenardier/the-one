#!/usr/bin/env bash
# Build GleepGlorp AI for Linux with PyInstaller: stage, freeze, wrap as AppImage and .deb.
# Spike prototype (Mission 32 Flight 1, candidate A); not wired into CI.
#
#   packaging/linux/build.sh <version> [--no-excludes]      e.g. 0.11.8 or 0.11.9.dev1
#
# Environment (all outside the repo, under $HOME):
#   M32_BUILD     build root (default $HOME/the-one-m32-build)
# Expects, under $M32_BUILD: venv-pyi/ (see README "Build environment") and
# tools/appimagetool-*/ + tools/type2-runtime-*/ (pinned; checksums in README).
set -euo pipefail

VERSION="${1:?usage: build.sh <version> [--no-excludes]}"
NO_EXCLUDES="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
M32_BUILD="${M32_BUILD:-$HOME/the-one-m32-build}"
APPIMAGETOOL="$M32_BUILD/tools/appimagetool-1.9.1/appimagetool-x86_64.AppImage"
RUNTIME="$M32_BUILD/tools/type2-runtime-20251108/runtime-x86_64"
PYI="$M32_BUILD/venv-pyi/bin/pyinstaller"

DEB_VERSION="${VERSION/.dev/~dev}"   # PEP 440 0.11.9.dev1 -> Debian 0.11.9~dev1 (sorts below 0.11.9)
WORK="$M32_BUILD/linux-$VERSION"
PKGS="$M32_BUILD/packages"
STAGE="$M32_BUILD/stage-linux-$VERSION"
APPIMAGE="$PKGS/GleepGlorp_AI-$VERSION-x86_64.AppImage"
DEB="$PKGS/gleepglorp-ai_${DEB_VERSION}_amd64.deb"

rm -rf "$WORK"; mkdir -p "$WORK" "$PKGS"
echo "== stage $VERSION"
python3 "$REPO/packaging/spike/stage.py" --version "$VERSION" --candidate linux --out "$M32_BUILD"

echo "== freeze $VERSION ($("$M32_BUILD/venv-pyi/bin/python" --version))"
if [ "$NO_EXCLUDES" = "--no-excludes" ]; then export M32_NO_EXCLUDES=1; fi
M32_STAGE="$STAGE" "$PYI" --noconfirm --clean --distpath "$WORK/dist" --workpath "$WORK/work" \
    "$HERE/the-one.spec" > "$WORK/pyinstaller.log" 2>&1
BUNDLE="$WORK/dist/the-one"
test -x "$BUNDLE/the-one"
SIZE_KB="$(du -sk "$BUNDLE" | cut -f1)"

echo "== AppImage"
APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a "$BUNDLE" "$APPDIR/usr/lib/gleepglorp-ai"
cp "$HERE/AppRun" "$APPDIR/AppRun"; chmod 755 "$APPDIR/AppRun"
sed 's|@EXEC@|AppRun app|' "$HERE/gleepglorp-ai.desktop.in" > "$APPDIR/gleepglorp-ai.desktop"
cp "$STAGE/icon-512.png" "$APPDIR/gleepglorp-ai.png"
cp "$STAGE/icon-512.png" "$APPDIR/usr/share/icons/hicolor/512x512/apps/gleepglorp-ai.png"
ln -sf gleepglorp-ai.png "$APPDIR/.DirIcon"
rm -f "$APPIMAGE"
ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run --runtime-file "$RUNTIME" \
    "$APPDIR" "$APPIMAGE" > "$WORK/appimagetool.log" 2>&1

echo "== deb"
ROOT="$WORK/debroot"
mkdir -p "$ROOT/opt" "$ROOT/usr/bin" "$ROOT/usr/share/applications" \
    "$ROOT/usr/share/icons/hicolor/512x512/apps" "$ROOT/DEBIAN"
cp -a "$BUNDLE" "$ROOT/opt/gleepglorp-ai"
ln -s /opt/gleepglorp-ai/the-one "$ROOT/usr/bin/the-one"
sed 's|@EXEC@|the-one app|' "$HERE/gleepglorp-ai.desktop.in" > "$ROOT/usr/share/applications/gleepglorp-ai.desktop"
cp "$STAGE/icon-512.png" "$ROOT/usr/share/icons/hicolor/512x512/apps/gleepglorp-ai.png"
sed -e "s|@DEB_VERSION@|$DEB_VERSION|" -e "s|@INSTALLED_SIZE@|$SIZE_KB|" "$HERE/control.in" > "$ROOT/DEBIAN/control"
find "$ROOT" -type d -exec chmod 755 {} +
rm -f "$DEB"
dpkg-deb --root-owner-group -Zzstd -z9 --build "$ROOT" "$DEB" > "$WORK/dpkg-deb.log" 2>&1

echo "== done"
ls -l "$APPIMAGE" "$DEB"
