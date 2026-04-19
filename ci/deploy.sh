#!/usr/bin/env sh
set -eu

TAG="${1:?Usage: deploy.sh <image-tag>}"

# For rollback: re-tag the rollback image as latest
if [ "$TAG" = "rollback" ]; then
  docker tag the-one:rollback the-one:latest || { echo "No rollback image found"; exit 1; }
fi

docker rm -f the-one 2>/dev/null || true
docker run -d \
  --name the-one \
  --restart unless-stopped \
  -p 8484:8484 \
  -v "${WORKSPACE_PATH}:/workspace" \
  -e THE_ONE_LLM_PROVIDER=ollama \
  -e THE_ONE_LLM_MODEL=qwen2.5:7b \
  -e THE_ONE_LLM_BASE_URL=http://host.docker.internal:11434/v1 \
  -e THE_ONE_HOST=0.0.0.0 \
  -e THE_ONE_WORKSPACE_DIR=/workspace \
  -e THE_ONE_CONCOURSE_TARGET=local \
  -e THE_ONE_CONCOURSE_PIPELINE=the-one \
  -e THE_ONE_CONCOURSE_URL=http://host.docker.internal:8080 \
  -e THE_ONE_CONCOURSE_USER=the-one \
  -e THE_ONE_CONCOURSE_PASS="${CONCOURSE_PASS}" \
  -e THE_ONE_CONCOURSE_TEAM=the-one \
  --network concourse-local_default \
  --add-host host.docker.internal:host-gateway \
  the-one:latest
