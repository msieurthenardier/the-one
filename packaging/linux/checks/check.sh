#!/bin/bash
# Forwarding shim for the old name; deleted in Flight 2 leg 9.
exec bash "$(cd "$(dirname "$0")" && pwd)/gates.sh" "$@"
