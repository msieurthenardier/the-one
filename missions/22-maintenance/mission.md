# Mission: Post-Mission-21 Maintenance

**Status**: completed
**Depends on**: none (clears debt surfaced after Mission 21; touches `interfaces/web/api.py`, `interfaces/web/middleware.py`, `encryption.py`, `db/repositories.py`, and possibly `db/schema.py`)

## Outcome

Resolve the codebase-health issues identified in maintenance report
[2026-08-27](../../maintenance/2026-08-27.md) that carry a genuine design decision —
the encrypted-credential lifecycle (key rotation handoff, external-credential
revocation trace) and external-IdP OAuth callback reachability. The eight
squawk-sized findings from the same report are handled beside this mission as
squawks 0010–0017, not here. On landing, the codebase returns to **Flight Ready**
for the next capability mission.

## Context

Maintenance report [2026-08-27](../../maintenance/2026-08-27.md), triggered by the
close of [Mission 21 — Agent Self-Configuration](../21-agent-self-configuration/mission.md).
A full-codebase inspection (tool-pass Inspector, two module Inspectors, an `api.py`
gap Inspector, and a Security Reviewer) plus an Architect roundtable found the
Mission 20/21 security core sound — gate coverage, WebSocket pre-accept auth,
self-configuration identity derivation, approval gate, CAS, SSRF/sandbox all traced
and verified — and the suite green (4511 passed / 0 failed, 508s). Eleven Action
Required findings sit at the edges. Eight are pattern-copies of fixes already in the
repo and became squawks. The three here each need a decision the squawk gate
forbids: an ordering/recovery model for the key-rotation handoff, whether
external-credential revocation gets a schema tombstone, and how the OAuth callback
crosses the `SameSite=Strict` cookie boundary.

## Success Criteria

- [x] `rotate_encryption_key` cannot leave the database committed under a new key
      while the on-disk key file and in-memory encryptor remain on the old one — the
      DB↔key-file handoff has a defined recovery path, logs success and failure, and
      a test that injects a key-file write fault proves credentials stay decryptable.
      *(B8-rotate)*
- [x] Minting and revoking an `ext_` external credential leaves a durable,
      operator-readable trace (at minimum an operational log line with agent,
      credential id, label, and principal), and the tombstone question — `revoked_at`
      column via migration v38, or log-only — is decided and recorded.
      *(B8-ext-credential-trace)*
- [x] The external-IdP OAuth callback (`GET /api/oauth/callback`) is verified to
      complete end-to-end through the credential gate on a real cross-site redirect,
      the chosen mechanism (gate exemption on the state-guarded path, or
      `postMessage` from `window.opener`) is implemented, and a middleware-inclusive
      test pins it. *(S5 + S5b)*

## Stakeholders

- **Operator / maintainer** — wants the credential lifecycle trustworthy before
  issuing further `ext_` credentials to external clients, and the OAuth path
  proven before adding a second OAuth provider.

## Constraints

- Read-only findings become minimal, targeted fixes — no opportunistic refactors of
  `api.py` (its duplication clusters are documented Advisory items for a later cycle).
- Preserve the Mission 20/21 invariants: the ASGI-wide credential gate with exactly
  one exemption today (`GET /api/live`), `SameSite=Strict` on the session cookie
  except where this mission deliberately decides otherwise, field-scoped CAS on
  self-configuration writes, Fernet-encrypted `agt_`/`ext_` secrets.
- Do not duplicate the squawk batch (0010–0017) — in particular the `encryption.py`
  atomic-write fix (squawk 0011) lands separately; this mission's Leg 1 builds on it.
- A schema change (migration v38) is permitted only if the tombstone decision in
  Leg 2 chooses it, and must carry the same fresh-DB / idempotency / legacy-preservation
  test trio as v34–v37.

## Environment Requirements

- Existing Python 3.11+ host install (`pip -e ".[all-llms,dev]"`), `uv` for the
  lockfile, ruff, pytest (`make test-unit`, ~8.5 min), Playwright for the browser
  lane (`make test-browser`).
- Leg 3 verification needs either a real external IdP configured for one MCP source
  or a browser-lane test that performs a genuine cross-site top-level navigation.

## Open Questions

Resolved at flight start (see the flight's Open Questions, each with the Architect's
recommended default): the rotation handoff ordering model; log-only vs. `revoked_at`
tombstone; gate exemption vs. `postMessage` for the OAuth callback.

## Known Issues

- [x] Two encrypted columns were added after the rotation invariant was written and never joined the rotation transaction — `tool_configs.secrets` (M16 F08 L03) and `agent_external_credentials.secret` (M21 F03). Fixed in Flight 1 Leg 1 (flight-log Decision D1); the debrief should propose a structural guard so the next encrypted column cannot miss it. → Guard test landed as squawk 0018 (turnaround 2026-08-28); the `EncryptedColumn` registry refactor is carried to the next maintenance report (mission debrief, Action Items).

## Flights

> **Note:** Scaffolded from the 2026-08-27 maintenance report. One flight — the
> three findings share a subsystem (the encrypted credential corpus and its
> lifecycle) and test apparatus; S5 rides along because it starts with a live
> verification that may collapse it to a one-line exemption.

- [x] Flight 1: **Credential lifecycle integrity and observability** — safe
      `rotate_encryption_key` DB↔key-file handoff with logging and a fault-injection
      test (B8-rotate); durable `ext_` mint/revoke trace + tombstone decision
      (B8-ext-credential-trace); OAuth callback reachability through the gate with
      a middleware-inclusive test (S5/S5b).
