#!/usr/bin/env bash
# Authenticate fly CLI with Concourse on container startup, then exec the main command.
set -e

if [ -n "$THE_ONE_CONCOURSE_URL" ] && [ -n "$THE_ONE_CONCOURSE_USER" ] && [ -n "$THE_ONE_CONCOURSE_PASS" ]; then
    fly -t "${THE_ONE_CONCOURSE_TARGET:-local}" login \
        -c "$THE_ONE_CONCOURSE_URL" \
        -n "${THE_ONE_CONCOURSE_TEAM:-the-one}" \
        -u "$THE_ONE_CONCOURSE_USER" \
        -p "$THE_ONE_CONCOURSE_PASS" \
        > /dev/null 2>&1 || echo "[entrypoint] Warning: fly login failed"
fi

exec "$@"
