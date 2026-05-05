#!/usr/bin/env sh
set -eu

TAG="${1:?Usage: deploy.sh <image-tag>}"

# For rollback: re-tag the rollback image as latest
if [ "$TAG" = "rollback" ]; then
  docker tag the-one:rollback the-one:latest 2>/dev/null || {
    echo "ERROR: No rollback image found (the-one:rollback). Either this is the first deploy (rollback was never tagged) or the rollback tag was lost. Cannot roll back. Manual recovery required: redeploy a known-good build via 'fly trigger-job'."
    exit 1
  }
fi

docker rm -f the-one 2>/dev/null || true
docker run -d \
  --name the-one \
  --restart unless-stopped \
  -p 8484:8484 \
  -e THE_ONE_LLM_PROVIDER=ollama \
  -e THE_ONE_LLM_MODEL=qwen2.5:7b \
  -e THE_ONE_LLM_BASE_URL=http://host.docker.internal:11434/v1 \
  -e THE_ONE_HOST=0.0.0.0 \
  --add-host host.docker.internal:host-gateway \
  the-one:latest

# Post-rollback health check (only for rollback path; forward deploys are health-checked by the pipeline task)
if [ "$TAG" = "rollback" ]; then
  up=false
  for attempt in $(seq 1 12); do
    if curl -sf http://localhost:8484/api/info >/dev/null 2>&1; then
      up=true
      break
    fi
    sleep 5
  done
  if [ "$up" != "true" ]; then
    echo "ERROR: Rolled-back container failed health check after 60s. Manual intervention required."
    exit 1
  fi
  echo "Rollback verified healthy at http://localhost:8484/api/info"
fi
