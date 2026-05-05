# Leg: 05-admin-pass-rotation

**Status**: completed
**Flight**: [Debrief Follow-ups](../flight.md)

## Objective

Rotate the local Concourse admin password (currently `ZTul+YLaMh9j0SbvB8clMTQe`, exposed in `the-one`'s git history at `594d2c4` via `.claude/settings.local.json` Bash allowlist entries) and verify the old password no longer authenticates. Same procedure as Flight 01 Leg 06 but for the `admin` user / `main` team. Coordinate with the epipen project since the admin credential is shared infrastructure.

## Context

Flight 01 Leg 06 rotated the `the-one` team password but explicitly deferred the admin password rotation as "a separate cross-project decision (shared with epipen team)". Flight 01 debrief recorded this as an open action item.

The admin credential gates:
- `fly -t local login -u admin` for both projects
- The `main` team in local Concourse
- Any team-creation / admin-only operations

Both `the-one` and `epipen` use `local` as their fly target name. Rotating the admin password requires:
1. Concourse-local infrastructure update (`docker-compose.yml` env var via `concourse-local/.env`)
2. Restart of the web container
3. Both downstream projects (`the-one`, `epipen`) update any places that reference admin credentials (typically only operator's `~/.fly/targets.yml` cache via `fly login`; neither project's `.env` should reference the admin pass)

This is a guided-manual leg — same protocol as Flight 01 Leg 06. Flight Director walks the operator through verification rather than spawning an autonomous Developer.

## Inputs

- Local Concourse instance running at `http://localhost:8080`
- `/home/cprch/projects/concourse-local/.env` (contains `CONCOURSE_ADMIN_PASS=ZTul...`)
- `/home/cprch/.fly/targets.yml` (contains cached admin login token)
- The epipen project's working tree (for the operator to verify epipen's admin-pass references, if any)

## Outputs

- New strong random admin password generated
- `concourse-local/.env` updated with new `CONCOURSE_ADMIN_PASS`
- `concourse-local-web` container recreated with new env
- Old admin password rejected; new admin password authenticates
- `.fly/targets.yml` admin token refreshed via `fly login -t local -u admin`
- Coordination note logged for epipen (operator updates epipen's local fly target if it caches admin creds)

## Acceptance Criteria

- [x] New strong admin password generated (≥24 chars, alphanumeric, no operator-typed)
- [x] `concourse-local/.env` contains the new `CONCOURSE_ADMIN_PASS`; old value (`ZTul+YLaMh9j0SbvB8clMTQe`) is gone from the active config
- [x] `concourse-local-web` container recreated (`docker compose up -d web`) and healthy
- [x] `fly -t local login -c http://localhost:8080 -u admin -p '<NEW_ADMIN>'` succeeds
- [x] `fly -t test-old-admin login -c http://localhost:8080 -u admin -p 'ZTul+YLaMh9j0SbvB8clMTQe'` fails with auth error
- [x] Operator confirms epipen-side coordination: epipen audit returned zero matches for `ZTul|CONCOURSE_ADMIN_PASS|admin.*password|fly.*-u admin` — admin is operator-direct, no epipen project-file references. No remediation needed.
- [x] DO NOT rewrite git history. Old admin password remains in `the-one`'s git history at `594d2c4`; rotation invalidates the practical risk on this private single-dev repo.

## Verification Steps

- Generate new password: `openssl rand -base64 30 | tr -d '/+=' | head -c 32` (run in a private/cleared terminal — do not log the value)
- Update `concourse-local/.env`: replace `CONCOURSE_ADMIN_PASS=ZTul...` with the new value
- Restart web: `cd /home/cprch/projects/concourse-local && docker compose up -d web`
- Wait for ATC to come up: `until curl -sf http://localhost:8080/api/v1/info > /dev/null; do sleep 2; done`
- Verify new pass: `fly -t local login -c http://localhost:8080 -u admin -p '<NEW_ADMIN>'` — should succeed
- Verify old pass rejected: `fly -t test-old-admin login -c http://localhost:8080 -u admin -p 'ZTul+YLaMh9j0SbvB8clMTQe'` — should return `oauth2: access_denied`
- Operator audits epipen's working tree: `grep -rE "ZTul|admin.*pass" /home/cprch/projects/epipen/ 2>/dev/null` (in epipen's project) — should return zero matches OR only matches in gitignored config the operator must manually update

## Implementation Guidance

This is a guided-manual leg. The Flight Director walks the operator through each step one at a time, waits for confirmation, and proceeds. Do NOT spawn an autonomous Developer.

**Steps** (Flight Director presents one at a time):

1. **Generate new password**: `openssl rand -base64 30 | tr -d '/+=' | head -c 32`. Operator copies the value privately. Do NOT log it.

2. **Update `concourse-local/.env`**: Edit the `CONCOURSE_ADMIN_PASS` line with the new value. `.env` is gitignored.

3. **Recreate the web container**:
   ```bash
   cd /home/cprch/projects/concourse-local && docker compose up -d web
   ```
   Briefly interrupts any in-flight pipeline (epipen included).

4. **Wait for ATC**:
   ```bash
   until curl -sf http://localhost:8080/api/v1/info > /dev/null 2>&1; do sleep 2; done; echo "ATC ready"
   ```

5. **Verify new pass**:
   ```bash
   fly -t local login -c http://localhost:8080 -u admin -p '<NEW_ADMIN>'
   ```
   Should succeed (`logging in to team 'main'... target saved`).

6. **Verify old pass rejected**:
   ```bash
   fly -t test-old-admin login -c http://localhost:8080 -u admin -p 'ZTul+YLaMh9j0SbvB8clMTQe'
   ```
   Should fail with `error: oauth2: "access_denied" "Invalid username or password"`.

7. **Coordinate with epipen**:
   - Operator audits the epipen project: `grep -rE "ZTul|CONCOURSE_ADMIN_PASS" /home/cprch/projects/epipen/ 2>/dev/null | grep -v ".git/"`.
   - Most likely outcome: zero matches. The admin pass is typically operator-direct (no project file references it).
   - If epipen has a reference (e.g., a Makefile or script that calls `fly -t local login -u admin -p '...'`), update that reference now. If epipen tracks the value in `.env`, update there.
   - Log the audit result in flight-log.

8. **DO NOT rewrite git history**. Old password remains in `the-one`'s git history at `594d2c4` and prior commits. For a private single-dev repo with localhost-only Concourse, the rotation eliminates the practical risk.

## Edge Cases

- **Operator's terminal logs the password**: most shells log to history. Operator should `unset HISTFILE` before generating the password OR use `read -s NEW_PASS` and reference `$NEW_PASS` in commands.
- **Active pipelines depend on cached admin creds**: pipelines authenticate via the team-user (`the-one` user, not admin) so this rotation should not affect running builds. If the operator has an admin-credentialed CI step somewhere, it would need updating — out of scope for this leg, surface as a finding if observed.
- **`fly` target cache stale after rotation**: `~/.fly/targets.yml` caches tokens, not passwords. `fly login` in step 5 refreshes the token. If the operator has multiple targets pointing at admin (e.g., another machine), each must `fly login` independently.
- **epipen has its own admin reference**: handle inline during step 7. If epipen requires more than a one-liner update, surface as a separate epipen-side maintenance task — do NOT expand scope of this leg.

## Files Affected

- `/home/cprch/projects/concourse-local/.env` — update `CONCOURSE_ADMIN_PASS` (gitignored, no commit)
- (Possibly) `/home/cprch/projects/epipen/.env` or scripts — update admin-pass reference if any (gitignored, out-of-tree from `the-one`)
- (Out of scope for this leg) `/home/cprch/.fly/targets.yml` — refreshed by `fly login`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] New admin password authenticated successfully
- [x] Old admin password verified to no longer authenticate
- [x] epipen audit logged (zero matches — operator-direct credential)
- [x] Update flight-log.md with leg progress entry (do NOT log the new password)
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] DO NOT commit — deferred to flight close (this leg produces no committed code changes; `concourse-local/.env` is out-of-tree from `the-one` and gitignored)
