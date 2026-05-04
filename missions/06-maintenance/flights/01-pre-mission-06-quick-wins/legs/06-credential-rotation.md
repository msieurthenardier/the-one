# Leg: 06-credential-rotation

**Status**: completed
**Flight**: [Pre-Mission-06 Quick Wins](../flight.md)

## Objective

Rotate the local Concourse `the-one` team password and the Concourse admin password (currently exposed in git history at commit `594d2c4` and earlier), update `.env` to the new values, and verify the old passwords no longer work. Do NOT rewrite git history.

## Context

Maintenance report finding 1.1 + CICD-M4 (see `maintenance/2026-05-04.md`).

- **1.1**: Commit `594d2c4` ("Gitignore .claude/ directory") deletes `.claude/settings.local.json`, but the prior add-commits retain plaintext `PRRARX6dpNqOdJAHZlVsihQppIGBBcRu` (the-one team) and `ZTul+YLaMh9j0SbvB8clMTQe` (Concourse admin) embedded in Bash allowlist `fly login -p '...'` strings. Verified by Flight Director via `git show 594d2c4 -- .claude/settings.local.json | grep ZTul`.
- **Mitigating context**: Repo is PRIVATE on GitHub (`isPrivate: true`); passwords are for LOCAL Concourse (`http://localhost:8080`) — exploitable only by someone with BOTH repo read access AND access to the operator's localhost network. Practical exposure low.
- **Architect calibration**: Action Required (rotate), NOT Critical (don't rewrite history). History rewrite on a single-dev private repo is high-risk-low-reward.

`.env` also contains `THE_ONE_CONCOURSE_PASS=PRRARX...` plaintext; CICD-M4 flagged. Same rotation closes both.

## Inputs

- Local Concourse instance running at `http://localhost:8080` (per `concourse-local` project in projects.md)
- `/home/cprch/projects/the-one/.env` (existing; contains current `THE_ONE_CONCOURSE_PASS`)
- Knowledge of how to rotate passwords in the local Concourse setup (see `/home/cprch/projects/concourse-local/`)

## Outputs

- New `the-one` team password generated and applied to Concourse local team
- New Concourse admin password (if the operator chooses to rotate it; recommended)
- `/home/cprch/projects/the-one/.env` updated with the new `THE_ONE_CONCOURSE_PASS`
- Old passwords no longer authenticate against local Concourse
- `fly` CLI works with the new password (verified by `fly -t the-one login` success)
- Pipeline still set/triggers correctly with the new credential

## Acceptance Criteria

- [x] New strong random password(s) generated (≥24 chars, alphanumeric+symbols, no operator-typed)
- [x] Local Concourse instance accepts the new the-one team password and rejects the old (`PRRARX6dpNqOdJAHZlVsihQppIGBBcRu`)
- [x] `.env` contains the new `THE_ONE_CONCOURSE_PASS`; `git status` shows `.env` is dirty but gitignored (no commit needed)
- [x] `fly -t the-one login -c http://localhost:8080 -n the-one -u the-one -p "${NEW_PASS}"` succeeds
- [ ] `fly -t local login -c http://localhost:8080 -u admin -p "${NEW_ADMIN_PASS}"` succeeds (if admin rotated) — admin password NOT rotated; deferred as separate cross-project decision (shared with epipen team)
- [x] Pipeline can be re-set: `fly -t the-one set-pipeline -p the-one -c ci/pipeline.yml --non-interactive` succeeds
- [x] Pipeline can be triggered: `fly -t the-one trigger-job -j the-one/deploy` succeeds (or returns expected status)
- [x] Old passwords verified to no longer work: `fly -t old-test login -p "${OLD_PASS}"` returns auth failure

## Verification Steps

- Generate new password: `openssl rand -base64 30 | tr -d '/+=' | cut -c1-32`
- Apply via the local Concourse rotation procedure (see `concourse-local` project)
- `cat /home/cprch/projects/the-one/.env | grep THE_ONE_CONCOURSE_PASS` — shows new value, NOT `PRRARX...`
- `fly -t the-one login -c http://localhost:8080 -n the-one -u the-one -p "${NEW_PASS}"` — succeeds
- `fly -t test-old login -c http://localhost:8080 -n the-one -u the-one -p 'PRRARX6dpNqOdJAHZlVsihQppIGBBcRu'` — fails with auth error
- `fly -t the-one set-pipeline -p the-one -c /home/cprch/projects/the-one/ci/pipeline.yml --non-interactive` — succeeds

## Implementation Guidance

1. **Generate new strong passwords**
   - Generate one for the `the-one` team: `openssl rand -base64 30 | tr -d '/+=' | head -c 32`
   - Optionally generate one for `admin` (recommended, since the admin password is also in history)

2. **Rotate the `the-one` team password in local Concourse**
   - The exact procedure depends on how the local Concourse is configured. Check `/home/cprch/projects/concourse-local/` for setup details. Typical paths:
     - Update `concourse-local/docker-compose.yml` env vars `CONCOURSE_LOCAL_USER_THE_ONE` (or similar)
     - Restart Concourse: `docker compose restart concourse-web` (in the concourse-local project)
     - OR if Concourse is configured via `fly set-team`: run `fly -t local set-team -n the-one --local-user the-one --basic-auth-password "${NEW_PASS}"`
   - Verify the new password works.

3. **Rotate the admin password (recommended)**
   - Same procedure as above for the `main` team / admin user.
   - Verify the new password works.

4. **Update `.env`**
   - Open `/home/cprch/projects/the-one/.env`
   - Replace `THE_ONE_CONCOURSE_PASS=PRRARX6dpNqOdJAHZlVsihQppIGBBcRu` with `THE_ONE_CONCOURSE_PASS=${NEW_PASS}`
   - Save. `.env` is gitignored — no commit.
   - (Future improvement, OUT OF SCOPE for this leg: move to a system keychain or `pass`. Surface as a follow-up if interest.)

5. **Re-set the pipeline with the new credential**
   - From `/home/cprch/projects/the-one/`: `fly -t the-one login -c http://localhost:8080 -n the-one -u the-one -p "${NEW_PASS}"`
   - `fly -t the-one set-pipeline -p the-one -c ci/pipeline.yml --non-interactive`
   - `fly -t the-one trigger-job -j the-one/deploy -w` (or whatever the existing trigger is)
   - Confirm successful pipeline run.

6. **Verify old passwords no longer work**
   - `fly -t test login -c http://localhost:8080 -n the-one -u the-one -p 'PRRARX6dpNqOdJAHZlVsihQppIGBBcRu'`
   - Should return an auth failure.

7. **DO NOT rewrite git history**
   - Tempting but counter-productive: `git filter-repo` / BFG would rewrite all collaborators' branches, invalidate all signed commits, and require force-pushes. For a single-dev private repo with localhost-only Concourse, the rotation eliminates the practical risk.
   - The old passwords remain in git history as a record. If the repo ever goes public or gains collaborators, surface as a separate decision at THAT time.

## Edge Cases

- **Concourse refuses the new password**: depending on how local Concourse is configured (env var vs. `fly set-team` vs. external auth), the rotation procedure differs. Worst case: rebuild the Concourse container with the new env var.
- **Active pipeline jobs reference the old credential**: if Concourse caches credentials per-build, currently-running builds may continue with the old password. Wait for them to finish, then verify the new flow.
- **The `fly` target name in `.env`**: confirm the env var name expected by the project (likely `THE_ONE_CONCOURSE_PASS` per Inspector evidence). Do not rename without checking consumers (`Makefile`, `docker-compose.yml`, scripts).
- **Other operators / agents accessing local Concourse**: if `the-one` or other agents had embedded the old password somewhere else, they'll break. Search the codebase for `PRRARX` or `ZTul` to confirm `.env` and `.claude/` are the only consumers (the latter is gitignored now).

## Files Affected

- `/home/cprch/projects/the-one/.env` — update `THE_ONE_CONCOURSE_PASS` (gitignored, no commit)
- Local Concourse configuration in `/home/cprch/projects/concourse-local/` — update env vars or run `fly set-team` (out-of-tree from the-one)
- Possibly `/home/cprch/.fly/targets.yml` — clear stale local fly targets if needed

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] New password authenticated successfully
- [ ] Old password verified to NO LONGER authenticate
- [ ] Pipeline re-set and triggered successfully with new credential
- [ ] `.env` updated; `.env.example` unchanged (placeholder values)
- [ ] Update flight-log.md with leg progress entry (do NOT log the new password)
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: update flight.md status to `landed` and check off flight in mission.md
- [ ] Commit all changes together (code + artifacts) — `.env` is gitignored, so this leg likely produces no committed code changes
