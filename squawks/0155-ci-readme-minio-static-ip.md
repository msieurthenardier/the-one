# Squawk 0155: ci/README.md documents a stale, movable MinIO address

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
The concourse-local stack moved to loopback-only port bindings with static compose-network addresses (concourse-local sortie 01, 2026-10-08). MinIO is now fixed at `172.19.0.20` in a reserved static block (`172.19.0.16`–`.31`), and the host-gateway route (`172.19.0.1:<port>`) is closed. The-one's Vault value is already correct (`172.19.0.20:9000`), but `ci/README.md` still gives `172.19.0.5:9000` as the endpoint and says the address may be reassigned on `docker compose down/up`. A reader following it would set a wrong value.

## Evidence
- `ci/README.md`, the "MinIO endpoint is a bare `host:port`" and "IP, not the compose service name" notes: `172.19.0.5`, "If `docker compose down/up` reassigns the IP…"
- concourse-local `sorties/01-loopback-only-ports/handoff-the-one.md` and its flight log: the-one `minio` `endpoint` = `172.19.0.20:9000` (already correct)

## Corrective Action
In `ci/README.md`, changed the MinIO endpoint to `172.19.0.20:9000` and replaced the "if `docker compose down/up` reassigns the IP" guidance (and its set_secret/fly snippet) with a note that the address is static and pinned in concourse-local's `docker-compose.yml`. The "IP, not service name" explanation is kept. No other statement was stale: the remaining addresses are `localhost` URLs, which still hold under loopback-only bindings.

## Verification
`grep -n "172\.19\.0\.5\|172\.19\.0\.1[^0-9]" ci/README.md` returns nothing. The edited section was read back against the handoff.

## Sign-Off

**Reviewer**: independent Reviewer (Haiku tier: docs only). It checked the README against concourse-local's sortie 01 handoff and flight log: `172.19.0.20:9000`, with no remaining `172.19.0.5` or host-gateway reference. It reviewed the same PR's maintenance-report correction in two cycles; cycle 1 blocked on the `app-url` wording, which was fixed.
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk/0155: ci/README MinIO static address` on branch `squawk/0155-ci-readme-minio-static-ip`
