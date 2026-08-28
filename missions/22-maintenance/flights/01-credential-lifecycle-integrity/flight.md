# Flight: Credential lifecycle integrity and observability

**Status**: completed
**Mission**: [Post-Mission-21 Maintenance](../../mission.md)

## Contributing to Criteria
- [x] `rotate_encryption_key` DB↔key-file handoff has a recovery path, logs, and a fault-injection test (B8-rotate)
- [x] `ext_` mint/revoke leaves a durable trace; tombstone decision recorded (B8-ext-credential-trace)
- [x] OAuth callback verified through the gate; mechanism chosen; middleware-inclusive test (S5 + S5b)

---

## Pre-Flight

### Objective
Make the encrypted-credential lifecycle trustworthy end to end: a key rotation
that cannot strand the database on a key the process does not hold, an external
credential whose issuance and revocation can be reconstructed after the fact, and
an OAuth callback that is proven — not assumed — to cross the credential gate.

### Open Questions

These are why the findings are a flight rather than squawks. Each has the
Architect's recommended default; confirm or override at flight start, then move
the answer to Design Decisions.

- [x] **Q1 — Rotation handoff ordering.** → *Resolved 2026-08-28: (a) two-phase sidecar — see Design Decisions.* Today `rotate_encryption_key` commits all
      five re-encrypted corpora, *then* writes the key file, *then* installs the key
      in memory, with the last two steps unguarded. Options: (a) two-phase — write
      the new key to a `.new` sidecar *before* the DB commit, promote it after, and
      teach the encryptor to try the sidecar on `InvalidToken` at startup so a crash
      between commit and promote is self-healing; (b) key-file-first — persist the
      key before the commit and make startup tolerate a key-ahead state by trying
      both keys; (c) keep the order and on key-file failure attempt a best-effort
      re-encrypt back to the old key. **Recommended: (a)** — it is the only option
      where every crash point leaves a recoverable state without a retry loop.
- [x] **Q2 — `ext_` revocation record.** → *Resolved 2026-08-28: log lines including cascade points; no tombstone — see Design Decisions.* Log line only, or add a `revoked_at`
      tombstone to `agent_external_credentials` (migration v38, `delete()` becomes
      an update, `load_all` and the startup reconcile filter on it)? **Recommended:
      log line in this flight; tombstone only if the operator wants a durable
      revocation record before the next `ext_` client is issued.** Record the
      decision either way.
- [x] **Q3 — OAuth callback mechanism.** → *Resolved 2026-08-28: (A) exempt the state-guarded callback path — see Design Decisions.* If live verification confirms the
      `SameSite=Strict` cookie is withheld on the IdP's cross-site redirect: exempt
      `GET /api/oauth/callback` from the gate (it is guarded by a single-use,
      unguessable `state` and performs no privileged action beyond resolving the
      pending flow — confirm that during the leg), or complete the exchange via
      `postMessage` from `window.opener` so the callback page needs no session.
      **Recommended: gate exemption**, provided the handler is confirmed to mint
      nothing and to be idempotent on replay.

### Design Decisions

**Q1 — Rotation handoff: two-phase sidecar**: `rotate_encryption_key` writes the
new key to `encryption.key.next` (atomic, `0o600`, via `_write_key_atomic`) *before*
the DB commit, commits, then promotes `.next → encryption.key` with `os.replace`
and `install_key`. A startup reconcile in the app lifespan (before any request)
handles a leftover `.next`: probe the first encrypted row — decrypts under `.next`
→ promote it; otherwise → delete it; no encrypted rows → promote. While `.next`
exists, `get_encryptor` loads both keys (`MultiFernet([next, current])`) so reads
never fail before the reconcile runs.
- Rationale: the only option where every crash point — including a hard kill
  between commit and promote — leaves a state the app repairs itself on next start.
  (b) reverse-re-encrypt and (c) surface-to-operator both depend on the fault being
  transient and noticed.
- Trade-off: one new startup step and a two-key read mode; a CLI process started
  during the crash window would encrypt new rows under the canonical key while
  `.next` is pending — negligible for a single-operator app, documented in the leg.

**Q2 — `ext_` trace: log lines, including cascade points; no tombstone**:
`logger.info` at mint / revoke / rotate (`api.py` routes) with agent name, credential
identifier, and label — never the secret — and at the two cascade points where
credential rows disappear without an explicit revoke (self-configuration surface
disable, agent delete), so every disappearance is logged. Route layer owns the
lines (one layer, consistently). No `revoked_at` column.
- Rationale: `agent_external_credentials.source_id` is `ON DELETE CASCADE`, so a
  tombstone would record operator revokes but not cascades — a half-record unless
  the FK also changed. A queryable audit trail is an events table, which is its own
  initiative alongside the Advisory logging sweep. The log-line format chosen here
  becomes the convention that sweep inherits.
- Trade-off: durable only as long as the host log file is retained; nothing
  queryable in the DB.

**Q3 — OAuth callback: exempt `GET /api/oauth/callback` from the credential gate**:
add the path to `EXEMPT_PATHS` (`middleware.py`), making it the second exemption
beside `GET /api/live`. The single-use, unguessable `state` is the credential: the
handler already 401s on a missing/unknown state, mints nothing, and a replay reaches
the "Login expired" branch. `SECURITY-MODEL.md`'s "exactly one exemption" line is
updated to two, with this reasoning. The session cookie stays `SameSite=Strict`.
- Rationale: the IdP → app redirect is a cross-site navigation, on which a `Strict`
  cookie is withheld by spec — so today the callback 401s before `_state.resolve`
  runs and the flow times out. Relaxing the cookie to `Lax` reopens the M20 decision
  (`middleware.py:~232`); a `postMessage` relay still needs the callback exempt and
  adds a route, JS, and failure modes for no security gain.
- Trade-off: one more unauthenticated route; its only mutation is resolving a
  pending flow the caller cannot name without `state`.
- Verification without a real IdP: `localhost` and `127.0.0.1` are different sites —
  a browser-lane test signs in on `http://localhost:<port>`, then navigates the popup
  to `http://127.0.0.1:<port>/api/oauth/callback?code=…&state=…`; the browser
  withholds the `Strict` cookie exactly as after an IdP redirect. A live IdP run is
  a bonus, not a prerequisite.

### Prerequisites
- [x] Squawk 0011 (`encryption.py` atomic key-file write) landed — PR #178, merged 2026-08-28 — Leg 1 builds on the `O_CREAT|O_EXCL` write it introduces
- [x] Squawk 0012 (`_require_long_lived_caller` explicit source check) landed — PR #178, merged 2026-08-28 — so Leg 3's gate-exemption change is reviewed against an auth path that holds by construction

### Pre-Flight Checklist
- [x] All open questions resolved (Q1–Q3) — 2026-08-28
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined (fault-injection test + `.next` reconcile tests for Leg 1; log-capture test incl. cascade points for Leg 2; middleware-inclusive unit test + `localhost`→`127.0.0.1` cross-site browser test for Leg 3)
- [x] Legs defined (during `/agentic-workflow`)

---

## In-Flight

### Technical Approach

**Leg 1 — Safe `rotate_encryption_key` handoff (B8-rotate).**
Evidence: `the_one/interfaces/web/api.py:5500` `rotate_encryption_key` re-encrypts
five credential corpora. The DB side *is* atomic — all five updates sit in one
`try` / single `conn.commit()` / `except: rollback(); raise` block
(`api.py:5654-5680`). But steps 5–6 (`api.py:5719-5729`: temp-file write + fsync +
`os.replace` of the key file) and step 7 (`api.py:5731` `encryptor.install_key`)
run *after* the commit with no `except` — the `try/finally` there only closes the
fd. If write/fsync/replace fails (disk full, permission, cross-device), the
database is committed under the new key while the on-disk key file and the
in-memory encryptor stay on the old one: every credential becomes
`InvalidToken`-undecryptable, with no log line and no recovery path.
`Encryptor.install_key` (`the_one/encryption.py:45`) has no logging either; per
`the_one/agents.md` (M21 override-storage section) rotation propagates to every
by-reference store app-wide, agent overrides included.
Fix per Q1 (recommended two-phase sidecar): write the new key to a sidecar before
the commit; promote after; startup/`get_encryptor` tries the sidecar on
`InvalidToken` and promotes it; wrap steps 5–7 in a guarded block that logs
`logger.exception` with what state was reached; `logger.info` on success (key id or
fingerprint, corpora counts — never key material). Test: inject an `os.replace`
fault after a successful commit and assert credentials remain decryptable and the
failure is logged. Architect's severity note: Action Required, not Critical, only
because the corpora are re-enterable credentials — treat it as the flight's
load-bearing leg.

**Leg 2 — Durable `ext_` mint/revoke trace (B8-ext-credential-trace).**
Evidence: `the_one/db/repositories.py:1869-1941` `AgentExternalCredentialRepository`
has no `logger` call in `create` or `delete`; `delete()` (`:1928-1938`) is a hard
`DELETE FROM agent_external_credentials` returning `rowcount > 0` — no tombstone.
The mint/revoke/rotate routes (`api.py:1043-1170`) emit nothing. `agent_revisions`
carries `source_principal`, so an `ext_` principal that *wrote* leaves a trace — but
a mint-then-revoke that never performed a write leaves zero durable record. The
agent's own self-write path already shows the logging pattern to mirror
(`the_one/self_configuration/pending.py:66,98,103` — INFO with agent, field, count).
Fix: `logger.info` at mint / revoke / rotate with agent name, credential id, label,
and principal (never the secret), in the route or the repository (pick one layer,
consistently). Then apply Q2: if tombstone, migration v38 adds `revoked_at`,
`delete()` becomes an update, `load_all`/reconcile filter on `revoked_at IS NULL`,
with the fresh/idempotency/legacy test trio. Test: log-capture assertion on mint and
revoke.

**Leg 3 — OAuth callback reachability (S5 + S5b).**
Evidence: `GET /api/oauth/callback` (`api.py:2977`) is not in `EXEMPT_PATHS`
(`the_one/interfaces/web/middleware.py:186` — `frozenset({LIVENESS_PATH})`); the
session cookie is `SameSite=Strict` (`middleware.py:247`), which browsers withhold on
a cross-site top-level navigation — exactly what an IdP's redirect back is. The
gate therefore 401s before `_state.resolve()` runs and the pending flow times out.
Fails closed (no bypass), but the external-IdP OAuth flow is plausibly broken
end-to-end and nothing would notice: `tests/test_oauth_callback_route.py` omits the
middleware entirely. Three of four security review passes found this independently.
Step 1 — write the failing test first: a browser-lane test that signs in on
`http://localhost:<port>` and navigates the popup to
`http://127.0.0.1:<port>/api/oauth/callback?code=…&state=…` (cross-site, so the
`Strict` cookie is withheld) and asserts the flow resolves; plus a middleware-
inclusive unit test driving the callback with no cookie. Both should fail today
(401). Step 2 — add `GET /api/oauth/callback` to `EXEMPT_PATHS` (Q3 decision),
re-confirming in the diff that the handler mints nothing, resolves a single-use
`state`, and is replay-safe; update `SECURITY-MODEL.md`'s "exactly one exemption"
line. Step 3 — tests green; a live IdP run if one is configured, recorded in the
flight log either way.

### Checkpoints
- [x] Key-file fault after commit → credentials still decryptable, failure logged (test)
- [x] Mint + revoke of an `ext_` credential → log lines with agent / id / label / principal (test)
- [x] Tombstone decision recorded in Design Decisions (and migration v38 + tests, if chosen)
- [x] OAuth callback verified live; mechanism implemented; middleware-inclusive test green
- [x] `SECURITY-MODEL.md` updated for any new gate exemption

### Adaptation Criteria

**Divert if**: Leg 1's two-phase design turns out to need changes to how every
by-reference store receives the encryptor (beyond `get_encryptor`/`install_key`) —
stop and re-plan rather than threading a new parameter through the app; or Leg 3's
live verification shows the flow already works and the reason is something the
gate should *not* rely on (e.g. a browser quirk).

**Acceptable variations**: which layer (route vs. repository) carries the `ext_`
log lines; log field naming; whether the Leg 1 fault-injection test monkeypatches
`os.replace` or uses a read-only temp dir.

### Legs

> **Note:** Planned one at a time during `/agentic-workflow`. One finding maps to
> one leg.

- [x] `rotation-handoff-safety` - two-phase key-file handoff, logging, fault-injection test (B8-rotate)
- [x] `ext-credential-trace` - mint/revoke/rotate logging + tombstone decision (B8-ext-credential-trace)
- [x] `oauth-callback-reachability` - live verification, gate mechanism, middleware-inclusive test (S5/S5b) — *no external IdP configured; the cross-site browser test is the live verification*
- [ ] `uat-and-alignment` *(optional, not run — offered to the operator after landing)* - rotate a key and mint/revoke an `ext_` credential on the real app; walk an OAuth sign-in if an IdP is configured

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing (`make test-unit`; browser lane for Leg 3 if used)
- [x] Documentation updated (`SECURITY-MODEL.md` exemption line; `agents.md` if the encryptor gains sidecar semantics)

### Verification
A key rotation with an injected key-file fault leaves every credential decryptable
and a log entry explaining the state; a mint/revoke pair is reconstructible from
logs (and the table, if the tombstone was chosen); the OAuth callback completes
through the credential gate under a middleware-inclusive test; suite green.
