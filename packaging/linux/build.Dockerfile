# Build image for the Linux packages (Mission 32 Flight 2, DD2). One pinned container builds
# both the AppImage and the .deb, locally and on the hosted runner.
#
#   docker build -f packaging/linux/build.Dockerfile -t m32/linux-build:f2 <context>
#
# <context> holds only requirements-closure.txt (build.sh writes it with `uv export`). The
# freeze itself runs later, in `docker run`, with no network.
#
# The base is ubuntu:24.04 pinned by digest (re-read at leg start 2026-10-24); the freeze
# must see a GLib 2.80 host, the one Flight 1's excludes.txt was validated on.
FROM ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8

# Compile headers for PyGObject and pycairo, plus libgirepository-2.0-0 itself, installed
# system-wide exactly as it was on the Flight 1 host. The Ayatana stack is only DOWNLOADED
# here and extracted under /opt/fallback-root: installing it system-wide would hand
# PyInstaller's gi hooks and pystray a typelib the Flight 1 build host did not have.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      gcc pkg-config libgirepository-2.0-dev libcairo2-dev gobject-introspection \
      dpkg-dev binutils file curl ca-certificates libgirepository-2.0-0 \
      desktop-file-utils appstream \
 && mkdir -p /opt/fallback-debs /opt/fallback-root \
 && cd /opt/fallback-debs \
 && apt-get download libayatana-appindicator3-1 libayatana-indicator3-7 libayatana-ido3-0.4-0 \
      libdbusmenu-gtk3-4 libdbusmenu-glib4 gir1.2-ayatanaappindicator3-0.1 \
 && for d in /opt/fallback-debs/*.deb; do dpkg -x "$d" /opt/fallback-root; done \
 && rm -rf /var/lib/apt/lists/* \
 && chmod -R a+rX /opt/fallback-debs /opt/fallback-root

# uv, pinned by digest (the version CI pins in ci/tasks/*.yml, 0.9.30).
COPY --from=ghcr.io/astral-sh/uv@sha256:538e0b39736e7feae937a65983e49d2ab75e1559d35041f9878b7b7e51de91e4 /uv /usr/local/bin/uv

# Tools: downloaded and verified here, so no runner needs a pre-seeded tools directory.
# The sha256 values are the ones in packaging/linux/README.md "Pinned tools".
RUN mkdir -p /opt/tools \
 && curl -fsSL -o /opt/tools/appimagetool-x86_64.AppImage \
      https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage \
 && curl -fsSL -o /opt/tools/runtime-x86_64 \
      https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64 \
 && echo "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0  /opt/tools/appimagetool-x86_64.AppImage" | sha256sum -c - \
 && echo "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d  /opt/tools/runtime-x86_64" | sha256sum -c - \
 && chmod 755 /opt/tools/appimagetool-x86_64.AppImage /opt/tools/runtime-x86_64

# CPython and the venv live under /opt, world-readable: the build runs as the invoking
# uid, which has no access to root's home.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python UV_LINK_MODE=copy UV_NO_PROGRESS=1
RUN uv python install 3.11.14 && chmod -R a+rX /opt/uv-python

# The hash-pinned closure (layer keyed on the file), then the freeze tools.
COPY requirements-closure.txt /tmp/requirements-closure.txt
RUN uv venv --python 3.11.14 /opt/venv \
 && uv pip install --python /opt/venv/bin/python -r /tmp/requirements-closure.txt --no-deps \
 && uv pip install --python /opt/venv/bin/python pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.8 \
 && chmod -R a+rX /opt/venv

ENV PATH=/opt/venv/bin:$PATH
