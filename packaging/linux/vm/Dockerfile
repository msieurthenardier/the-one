# QEMU/KVM runner for the Mission 32 fresh-VM apparatus (Flight 2, leg 4, DD9).
# Pinned base digest (debian:13 as pulled 2026-10-24).
FROM debian@sha256:4c25275446ca371766b8b093c696782eabce06263fccacb8d5d813b3dc44b308
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      qemu-system-x86 qemu-system-gui qemu-utils ovmf \
      openssh-client python3 xorriso genisoimage ca-certificates \
 && rm -rf /var/lib/apt/lists/*
# Runs as the invoking uid (docker run --user); no entrypoint magic.
