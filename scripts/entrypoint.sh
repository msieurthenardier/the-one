#!/usr/bin/env bash
# Container startup: configure git, install fly CLI, authenticate with Concourse.
set -e

# Fix "dubious ownership" — workspace is owned by host user, container runs as root
git config --global --add safe.directory /workspace

# Download fly CLI from Concourse at runtime (not build time, where host.docker.internal doesn't resolve)
if [ -n "$THE_ONE_CONCOURSE_URL" ] && [ ! -f /usr/local/bin/fly ]; then
    curl -fsSL "${THE_ONE_CONCOURSE_URL}/api/v1/cli?arch=amd64&platform=linux" \
        -o /usr/local/bin/fly \
        && chmod +x /usr/local/bin/fly \
        || echo "[entrypoint] Warning: fly CLI download failed"
fi

# Authenticate fly CLI with Concourse
if [ -n "$THE_ONE_CONCOURSE_URL" ] && [ -n "$THE_ONE_CONCOURSE_USER" ] && [ -n "$THE_ONE_CONCOURSE_PASS" ]; then
    fly -t "${THE_ONE_CONCOURSE_TARGET:-local}" login \
        -c "$THE_ONE_CONCOURSE_URL" \
        -n "${THE_ONE_CONCOURSE_TEAM:-the-one}" \
        -u "$THE_ONE_CONCOURSE_USER" \
        -p "$THE_ONE_CONCOURSE_PASS" \
        > /dev/null 2>&1 || echo "[entrypoint] Warning: fly login failed"
fi

exec "$@"
