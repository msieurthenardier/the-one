# Leg: 04-auto-rollback-correctness

**Status**: completed
**Flight**: [Pre-Mission-06 Quick Wins](../flight.md)

## Objective

Make the Concourse `auto-rollback` path actually verify the rollback succeeded — re-run the health-check after the rollback container starts, and fail loudly when the deploy-time health-check loop exhausts all 12 attempts (rather than silently falling through to a connection-refused selftest error). Also handle "no rollback image exists" explicitly on first deploy.

## Context

Maintenance report findings 8.2 and 8.3 (see `maintenance/2026-05-04.md`).

- **8.2**: `ci/deploy.sh:7-21` re-tags `the-one:rollback` → `the-one:latest` and runs `docker rm -f` + `docker run -d`, but never re-runs the health-check. `ci/pipeline.yml:91-113` runs `auto-rollback` `on_failure` and exits without re-invoking the health-check task. The script unconditionally prints "Rolled back to previous image" on the success path. A failed rollback is therefore reported as success — false-positive recovery signal. Operators get the wrong status.
- **8.3**: `ci/pipeline.yml:73-80` health-check loop `break`s on first success but if all 12 attempts fail, the loop exits and falls through to the selftest curl. Selftest fails with connection-refused; diagnostics are buried. Operator sees "SELFTEST FAILED" with a connection error rather than a clear "app never came up after 60s" message. Triage is slower.

Both are CI/CD reviewer findings; both are HIGH because they corrupt the operator's mental model of the deploy state.

## Inputs

- `ci/pipeline.yml` (existing; health-check loop at lines 73-80 per CI/CD reviewer evidence; auto-rollback wiring at lines 91-113)
- `ci/deploy.sh` (existing; rollback path at lines 7-21)

## Outputs

- `ci/deploy.sh` rollback path: after `docker run -d`, polls the app's `/api/info` (or equivalent) and exits non-zero if it doesn't come up within a bounded timeout
- `ci/deploy.sh` rollback path: on first deploy where `the-one:rollback` doesn't exist, emits a clear diagnostic and exits non-zero
- `ci/pipeline.yml` health-check loop: tracks `up=true|false`; after the loop, if `up=false`, exits 1 with explicit "app never came up after Ns" message BEFORE attempting selftest

## Acceptance Criteria

- [x] `ci/deploy.sh` rollback branch — the existing `|| { echo "No rollback image found"; exit 1; }` guard at line 8 is improved: diagnostic explicitly distinguishes "first deploy / never tagged" from other failure modes; suggests next steps to operator
- [x] `ci/deploy.sh` rollback branch performs a post-rollback health check after the `docker run -d`. Retries match the existing pipeline pattern (12 attempts × 5s = 60s). Uses `curl -sf http://localhost:8484/api/info` (deploy.sh runs ON the deploy host, so localhost is correct here)
- [x] `ci/deploy.sh` rollback branch exits non-zero when post-rollback health check fails. Because `set -e` is active and the `auto-rollback` pipeline task uses `sh -exc`, the non-zero exit propagates and the `echo "Rolled back to previous image"` at `ci/pipeline.yml:113` is NOT reached
- [x] `ci/pipeline.yml` health-check task at lines 73-80 tracks an `up=true|false` flag (initialized `up=false` before the loop, set `up=true` in the success branch). After the loop, if `up=false`, exits 1 with explicit "ERROR: app never came up after 60s" message BEFORE attempting the selftest curl. Preserves existing flag style: `curl -sf "${APP_URL}/api/info"` (NOT `-fsS`; NOT `localhost:8484` — pipeline task runs in a separate curl container and reaches the app via the parameterized `${APP_URL}`)
- [x] Light verification: `sh -n ci/deploy.sh` (syntax check) + `fly validate-pipeline -c ci/pipeline.yml` (pipeline schema check) both pass
- [ ] Manual failure injection (faster path): rename the running container before deploy so `docker rm -f the-one` succeeds but the new `docker run` fails on port collision. Health-check loop should print "ERROR: app never came up after 60s" and exit 1; auto-rollback then runs and is also verified by its own health check (deferred — gated behind live Concourse trigger; out of scope for lightweight verification path agreed in design review)
- [ ] Manual rollback simulation: `docker tag busybox:latest the-one:rollback` (canonical broken image), trigger a deploy that fails, watch auto-rollback exit non-zero with a clear "rollback failed health check" message; the `echo "Rolled back to previous image"` at pipeline.yml:113 is NOT printed (deferred — gated behind live Concourse trigger; out of scope for lightweight verification path agreed in design review)

## Verification Steps

- `cd ~/projects/the-one && cat ci/deploy.sh` — review rollback path; verify post-rollback health check + first-deploy guard
- `cd ~/projects/the-one && cat ci/pipeline.yml` — review health-check task; verify `up` flag and explicit timeout message
- `cd ~/projects/the-one && fly -t local set-pipeline -p the-one -c ci/pipeline.yml --non-interactive --check-creds`
- `cd ~/projects/the-one && fly -t local trigger-job -j the-one/deploy -w` — full deploy succeeds
- Manual failure-injection test: temporarily change `--host` to an invalid IP in `docker-compose.yml`; trigger deploy; verify "app never came up after 60s" is printed and pipeline exits non-zero (rollback also runs and is also verified by its own health check)

## Implementation Guidance

1. **`ci/deploy.sh` rollback path**
   - Current shape (verified): `deploy.sh` line 7-9 has `if [ "$TAG" = "rollback" ]; then docker tag the-one:rollback the-one:latest || { echo "No rollback image found"; exit 1; }; fi`. Lines 11-21 unconditionally do `docker rm -f the-one` + `docker run -d the-one:latest` for BOTH forward-deploy and rollback paths.
   - **Improve the existing first-deploy guard**: replace the terse `echo "No rollback image found"` with a more actionable diagnostic that explains first-deploy vs never-tagged AND suggests next steps:
     ```sh
     if [ "$TAG" = "rollback" ]; then
       docker tag the-one:rollback the-one:latest 2>/dev/null || {
         echo "ERROR: No rollback image found (the-one:rollback). Either this is the first deploy (rollback was never tagged) or the rollback tag was lost. Cannot roll back. Manual recovery required: redeploy a known-good build via 'fly trigger-job'."
         exit 1
       }
     fi
     ```
   - **Add a post-rollback health check** after the existing `docker run -d` (lines 12-21). Only run it when `TAG = rollback` — the forward-deploy path is followed by the pipeline-side health check at pipeline.yml:73-80, so it doesn't need its own guard:
     ```sh
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
     ```
   - **Note**: deploy.sh runs ON the deploy host (where the container exposes `-p 8484:8484`), so `http://localhost:8484` is the correct URL inside this script. Use `curl -sf` (consistent with the existing pipeline pattern), NOT `-fsS`.
   - **The pipeline-side `echo "Rolled back to previous image"` at `ci/pipeline.yml:113`** stays — it's informational. It only runs if deploy.sh exits 0 (because the pipeline task uses `sh -exc`, so deploy.sh's non-zero exit propagates and the echo is never reached on rollback failure). No edit needed in pipeline.yml for this part.

2. **`ci/pipeline.yml` health-check task**
   - Locate the health-check loop at lines 73-80. Current shape (verified):
     ```sh
     echo "Waiting for app to start..."
     for i in $(seq 1 12); do
       if curl -sf "${APP_URL}/api/info" > /dev/null 2>&1; then
         echo "App is up after attempt $i"
         break
       fi
       echo "Attempt $i/12 — not ready, waiting 5s..."
       sleep 5
     done
     ```
   - Add an `up=false` initialization before the loop and `up=true` inside the success branch:
     ```sh
     echo "Waiting for app to start..."
     up=false
     for i in $(seq 1 12); do
       if curl -sf "${APP_URL}/api/info" > /dev/null 2>&1; then
         echo "App is up after attempt $i"
         up=true
         break
       fi
       echo "Attempt $i/12 — not ready, waiting 5s..."
       sleep 5
     done
     if [ "$up" != "true" ]; then
       echo "ERROR: app never came up after 60s. Pipeline failing fast."
       exit 1
     fi
     ```
   - **Preserve the existing curl shape**: `curl -sf "${APP_URL}/api/info"` (NOT `-fsS`; NOT `localhost:8484` — the pipeline task runs in a curl container and reaches the deployed app via the parameterized `${APP_URL}`).
   - The selftest curl that follows now only runs in the success-path. The `on_failure: { task: auto-rollback }` wiring continues to fire when this task exits non-zero.

3. **Verify the auto-rollback `on_failure` chain**
   - In `ci/pipeline.yml`, confirm that the deploy task's `on_failure: { task: auto-rollback }` triggers the auto-rollback task when health-check fails.
   - Confirm the auto-rollback task exits non-zero when its own health check (added in step 1) fails — pipeline reports a clear "rollback also failed" status rather than green-on-broken-rollback.

4. **Test the failure path end-to-end**
   - Temporarily break the docker-compose configuration (e.g., bind to port 65535 which the host won't bind successfully).
   - Trigger the deploy job.
   - Verify the pipeline output contains "app never came up after 60s" and (if rollback fires) "Rolled-back container failed health check" or "Rolled back to previous image and verified healthy."
   - Restore docker-compose.

## Edge Cases

- **First deploy** (no `the-one:rollback` image exists yet): the explicit guard in step 1 catches this. Without the guard, `docker tag` exits with a non-fatal-looking error and the pipeline silently proceeds to a partial state.
- **Health-check timeout vs network slowness**: 12 × 5s = 60s is the same window already in use; if the new explicit failure mode trips false positives on slow CI workers, raise to 24 × 5s = 120s (match production tolerance).
- **Selftest depends on a live LLM provider**: if selftest fails for a reason OTHER than "app down" (e.g., LLM provider throttling), the pipeline should distinguish "app didn't come up" (now caught earlier) from "selftest specific failure" (preserved at the selftest curl).
- **Concurrent triggers**: if two deploys race, the rollback image may be in an inconsistent state. Out of scope for this leg; surface as a future improvement if observed.

## Files Affected

- `ci/deploy.sh` — rollback path: first-deploy guard + post-rollback health check
- `ci/pipeline.yml` — health-check task: `up` flag + explicit timeout message; remove fall-through to selftest in the failure case

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified (including manual failure-injection test)
- [ ] Pipeline succeeds on healthy build
- [ ] Pipeline fails-fast with clear message on simulated health-check failure
- [ ] Rollback verifies its own health, exits non-zero on failure
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: update flight.md status to `landed` and check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
