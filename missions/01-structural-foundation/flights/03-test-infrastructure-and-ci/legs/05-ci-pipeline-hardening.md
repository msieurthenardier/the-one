# Leg: ci-pipeline-hardening

**Status**: completed
**Flight**: [Test Infrastructure & CI Hardening](../flight.md)

## Objective

Harden the Concourse CI pipeline by removing `|| true` from the test step, replacing hardcoded paths with a `((workspace-path))` variable, and extracting duplicated docker run blocks into a shared `ci/deploy.sh` script.

## Context

- The test step currently has `|| true` which swallows test failures — the pipeline deploys even if tests fail
- 5 occurrences of `/home/cprch/projects/the-one` are hardcoded in pipeline.yml
- The docker run env block (13 env vars, network, volume mounts) is duplicated 3 times (deploy, rollback, auto-rollback)
- The auto-rollback block is missing `--network concourse-local_default` (bug)
- `((workspace-path))` Concourse variable has already been set in Vault as a pre-execution step

## Inputs

- `ci/pipeline.yml` — current pipeline with hardcoded paths and `|| true`
- Concourse variable `((workspace-path))` already set in Vault

## Outputs

- `ci/deploy.sh` — shared deploy script accepting image tag argument
- `ci/pipeline.yml` — hardened pipeline using deploy.sh and workspace-path variable

## Acceptance Criteria

- [x] `ci/deploy.sh` created — accepts image tag arg (e.g., `latest`, `rollback`), reads config from env vars, runs single `docker run` command
- [x] `ci/deploy.sh` is executable (`chmod +x`)
- [x] `|| true` removed from test step
- [x] Test step uses `$WORKSPACE_PATH` instead of hardcoded path
- [x] Test step `params` includes `WORKSPACE_PATH: ((workspace-path))`
- [x] `compileall` removed from test step (pytest imports modules)
- [x] Deploy step uses `ci/deploy.sh latest` instead of inline docker run for the deploy container
- [x] Build step still uses inline docker commands (build needs docker-in-docker, different from deploy)
- [x] Rollback step uses `ci/deploy.sh rollback`
- [x] Auto-rollback step uses `ci/deploy.sh rollback` (also fixes missing `--network` bug)
- [x] All 5 occurrences of `/home/cprch/projects/the-one` replaced with `$WORKSPACE_PATH`
- [x] Deploy, rollback, auto-rollback `params` include `WORKSPACE_PATH: ((workspace-path))`
- [x] `fly validate-pipeline -c ci/pipeline.yml` passes
- [x] No hardcoded paths remain in pipeline.yml (except image references)

## Verification Steps

- `fly validate-pipeline -c ci/pipeline.yml` — valid YAML
- `grep -r '/home/cprch' ci/pipeline.yml` — no matches
- `grep '|| true' ci/pipeline.yml` — no matches
- `head -1 ci/deploy.sh` — starts with `#!/bin/sh` or `#!/usr/bin/env sh`
- `test -x ci/deploy.sh` — is executable

## Implementation Guidance

1. **Create `ci/deploy.sh`**
   ```sh
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
   ```

2. **Modify `ci/pipeline.yml` test step**
   - Remove `|| true` from the pytest command
   - Remove `python -m compileall -q the_one/ &&` (unnecessary)
   - Replace `/home/cprch/projects/the-one` with `$WORKSPACE_PATH`
   - Add `WORKSPACE_PATH: ((workspace-path))` to params

3. **Modify `ci/pipeline.yml` build-and-deploy step**
   - Replace hardcoded paths with `$WORKSPACE_PATH` in the build section
   - Replace the inline docker run deploy block with `${WORKSPACE_PATH}/ci/deploy.sh latest`
   - The build commands (docker build, docker tag rollback) stay inline — only the final deploy uses the script
   - Add `WORKSPACE_PATH: ((workspace-path))` and `CONCOURSE_PASS: ((concourse-pass))` to params

4. **Modify `ci/pipeline.yml` rollback step**
   - Replace inline docker run with `${WORKSPACE_PATH}/ci/deploy.sh rollback`
   - Add `WORKSPACE_PATH: ((workspace-path))` and `CONCOURSE_PASS: ((concourse-pass))` to params

5. **Modify `ci/pipeline.yml` auto-rollback step**
   - Replace inline docker run with `${WORKSPACE_PATH}/ci/deploy.sh rollback`
   - This also fixes the missing `--network` bug
   - Add `WORKSPACE_PATH: ((workspace-path))` and `CONCOURSE_PASS: ((concourse-pass))` to params

## Edge Cases

- **deploy.sh needs CONCOURSE_PASS env var**: The `((concourse-pass))` interpolation happens in pipeline params, so deploy.sh receives it as `$CONCOURSE_PASS`. This is a different mechanism from the inline `((concourse-pass))` which was interpolated by Concourse directly into the script.
- **Build step docker-in-docker**: The build step runs docker build inside a container. It needs the host path for the volume mount, so it uses `$WORKSPACE_PATH` directly. The deploy.sh script runs inside a container that has `$DOCKER_HOST` pointing to the host Docker daemon.
- **deploy.sh must be accessible from Concourse tasks**: Tasks mount `$WORKSPACE_PATH` as a volume, so the script at `${WORKSPACE_PATH}/ci/deploy.sh` is accessible.

## Files Affected

- `ci/deploy.sh` — Create (new)
- `ci/pipeline.yml` — Modify (remove || true, de-hardcode, use deploy.sh)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] `fly validate-pipeline -c ci/pipeline.yml` passes
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
