#!/usr/bin/env bash
# Set (or update) the the-one pipeline on the local Concourse.
# Secrets are resolved by Concourse from Vault at runtime (see ci/the-one.pipeline.yml) —
# nothing secret is passed here.
set -euo pipefail

TARGET="${FLY_TARGET:-the-one}"
PIPELINE="${PIPELINE:-the-one}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

fly -t "$TARGET" set-pipeline \
  -p "$PIPELINE" \
  -c "$HERE/the-one.pipeline.yml" \
  "$@"

echo
echo "Unpause with: fly -t $TARGET unpause-pipeline -p $PIPELINE"
echo "(pass --non-interactive to skip the apply prompt)"
