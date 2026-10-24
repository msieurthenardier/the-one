# Packaging check images (Mission 32 Flight 2, DD8): the container images the gate suite runs in.
#   docker build --target baseline -t m32/ubuntu-26.04:baseline -f ubuntu-26.04.Dockerfile .
#   docker build --target bare     -t m32/ubuntu-26.04:bare     -f ubuntu-26.04.Dockerfile .
# baseline = a stock GNOME desktop's packages (ubuntu-desktop-minimal, default
#            recommends, with snapd held out so the install does not need a service).
# bare     = the distro image plus python3 only.
# Both end in an "observe" layer of harness-only tools (not part of the stock contents).
# Never run these with --privileged, and never start systemd in them.

FROM ubuntu:26.04 AS bare-core
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/*

FROM ubuntu:26.04 AS baseline-core
ENV DEBIAN_FRONTEND=noninteractive
# Hold snapd so the metapackage's default recommends cannot pull it (it needs a
# running service). Everything else in ubuntu-desktop-minimal installs as shipped.
RUN apt-get update \
 && printf 'Package: snapd\nPin: release *\nPin-Priority: -1\n' > /etc/apt/preferences.d/no-snapd \
 && apt-get install -y ubuntu-desktop-minimal python3 \
 && rm -rf /var/lib/apt/lists/*

# Harness-only observation tools, kept in their own final layer.
FROM bare-core AS bare
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends procps dbus-x11 dbus-user-session xvfb xauth x11-apps scrot curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

FROM baseline-core AS baseline
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends procps dbus-x11 xvfb xauth x11-apps scrot curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
