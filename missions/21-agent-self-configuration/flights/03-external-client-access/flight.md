# Flight: External Client Access

**Status**: completed
**Mission**: [Agent Self-Configuration](../../mission.md)

## Contributing to Criteria

- [ ] An external client can be granted access scoped to a single agent; that
      access can be withdrawn and reissued without restarting the platform, and a
      withdrawn credential stops working immediately.
- [ ] No read path anywhere returns secret material in the clear — extended here
      to the new external-credential store (a further secrets-bearing surface).
- [ ] The operator sets, per agent, whether self-revisions apply directly or wait
      for approval — and no principal reachable through the surface (agent **or**
      external client) can change that setting or the revision transitions.

---

## Pre-Flight

### Objective

Open the existing self-configuration surface to **external clients** — tools
outside the platform, and other agents inside it — each granted access scoped to
exactly one agent. Flight 1 already built the transport (a mounted
Streamable-HTTP MCP server, loopback-reachable at `/mcp/self-configuration/`),
the confinement (a gate-scoped credential admitted only to that mount), and live
withdraw/reissue (an in-memory registry mutated without restart). This flight
adds the three things that are genuinely missing: a way to **mint and deliver** a
credential to an external principal distinct from the agent's own; **per-principal
revoke and rotate** so one external system can be cut off without disturbing the
agent or any other client; and the **provenance, concurrency, and governance**
guarantees that a second live write-principal demands — external writes are logged
as `external` with the principal's identity, honor the per-agent approval flag,
cannot clobber a concurrent write, and cannot reach the operator's control plane.

### Open Questions

- [x] Is an external credential the agent's own `agt_` token re-delivered, or a
      distinct principal? → **DD1**
- [x] Where do external credentials live, and how are they kept secret-free on the
      way out? → **DD2**
- [x] How does an external write get distinct provenance in the revision log? →
      **DD3**
- [x] Do external writes honor the per-agent approval flag, or take a fixed
      posture? → **DD4**
- [x] With a genuine second live writer, how is the whole-row last-writer-wins
      clobber closed on the direct-write path? → **DD5**
- [x] What stops an external principal from reaching the approval-mode setting or
      the approve/dismiss/restore transitions? → **DD6**
- [x] What does rotation mean now that more than one principal exists (the
      mission's inherited open question)? → **DD7**
- [x] How does the external registry survive a restart? → **DD8**
- [x] What happens to an external credential when the operator disables the surface
      for its agent — does it outlive the operator's decision? → **DD9**

### Design Decisions

**DD1 — An external client is a distinct principal, not the agent's own token
re-delivered.** Each grant mints a new credential with its own identifier (a new
`ext_` prefix so its type is legible at a glance, mirroring the `loc_`/`agt_`
convention), resolving to exactly one agent's surface but tagged as external. A
new `CredentialSource` — `ExternalAgentCredentialSource`, `name=
"self-configuration-external"` — registers on the same seam
(`api_credential.py:register_source`) and is added to
`CONFINED_SOURCE_PATHS` (`the_one/self_configuration/constants.py`) pointing at
the **same** mount path `/mcp/self-configuration`, so it inherits Flight 1's
confinement (403 off-mount, WS refused) unchanged.
- Rationale: the agent's own `agt_` credential is one-per-agent and its lifecycle
  is welded to enable/disable; revoking it to cut off an external client would
  also sever the agent's own path. Distinct principals are what make
  per-external-system and per-agent-to-agent revoke/rotate possible at all — the
  operator's stated need. A distinct source name also gives the gate a clean
  provenance signal (`caller.source == "self-configuration-external"`) that DD3
  consumes without inspecting the token.
- Trade-off: a second registry and a second reconcile path to maintain (DD8);
  more surface than re-delivering the existing token. Accepted — it is the
  minimum that supports independent revocation.

**DD2 — External credentials live in a new secrets-bearing table with a
structural, secret-free projection; the secret is returned exactly once, at mint.**
A new `agent_external_credentials` table holds one row per grant:
`(identifier PK, agent_name REFERENCES agents(name) ON DELETE CASCADE,
secret_encrypted, label, created_at, revoked_at NULLABLE, last_used_at NULLABLE)`.
The secret is Fernet-encrypted at rest via the existing `Encryptor`
(`repositories.py:_encrypt_secrets_blob` family), never stored or logged in the
clear. The mint endpoint returns the full `ext_<id>.<secret>` bearer **and** the
surface URL once; no read path returns it again. The list endpoint builds a
purpose-built projection (`identifier`, `label`, `agent_name`, `created_at`,
`revoked_at`, `last_used_at`) that never touches the secret column — the same
structural discipline the mission requires of every other secrets-bearing record.
- Rationale: this is the "further secrets-bearing table" the mission named and the
  mission-19 debrief flagged for a shared secrets-column helper. Structural
  projection (build the dict, never serialize the row) is the mission's mandated
  approach over masking. Encrypting at rest is free by reusing the existing
  column-encryption path — the same asymmetry the Flight-1 debrief noted between
  the encrypted `agt_` secret and the plaintext file credential lands on the
  encrypted side here.
- Trade-off: a new migration and a new repository. Accepted — a dedicated store is
  what lets a grant carry an operator-legible `label` and independent lifecycle.

**DD3 — External writes are logged as `source='external'` with the principal's
identifier recorded.** A v-next migration rebuilds the `agent_revisions` table to
widen `CHECK (source IN ('self','restore'))` to include `'external'`, and adds a
nullable `source_principal TEXT` column recording the external credential's
identifier (safe to log by Mission 20's id/secret split; NULL for `self`/
`restore`). Widening the source domain is **five touch-points, not two** — the
Architect flagged that the two `source="self"` literals are only the writes; the
reads break too if the model isn't widened in lockstep:
1. The `agent_revisions` `CHECK (source IN ('self','restore'))` → add `'external'`
   (table-rebuild migration, see below) and add the `source_principal` column.
2. `AgentRevision.source` — widen the Pydantic `Literal["self","restore"]`
   (`models.py:708`) to include `"external"`, and add a `source_principal` field;
   otherwise every read of an external row raises `ValidationError` → 500 through
   `_row_to_model`.
3. `AgentRevisionRepository.append` — thread `source`/`source_principal` through
   the signature and the INSERT (currently the applied-log writer).
4. `AgentRevisionRepository.upsert_pending_revision` — the second hard-coded
   `source="self"` (`repositories.py:1056`), parameterized for the queued branch.
5. `_apply_revision` (`surface.py`) — accept and forward `source`/`source_principal`
   from the calling tool to both (3) and (4).
- Rationale: debrief rec 2. Distinct provenance is what makes an audit of "which
  external system tuned this agent" possible, and it is load-bearing once
  agent-to-agent tuning is a supported use. The source domain was pre-provisioned
  at two values in v34; a third principal needs the table-rebuild ceremony (SQLite
  cannot `ALTER … ADD CHECK`). Enumerating all five sites up front is the direct
  application of Flight 2's "citation-density is not design-completeness" lesson —
  the 19-columns/18-values class of miss lives exactly in this kind of half-threaded
  widening.
- Trade-off: a table-rebuild migration on `agent_revisions`. The **v23 rebuild**
  (`schema.py:961-1160`) is the precedent — `foreign_keys=OFF` envelope, CREATE-new
  / INSERT-SELECT / DROP / RENAME, version stamp `INSERT OR IGNORE` last. The
  self-FK `restored_from` is the subtlety: declare it against the new table and let
  `ALTER … RENAME TO` rewrite the reference (modern `legacy_alter_table` OFF);
  INSERT-SELECT under `foreign_keys=OFF` tolerates out-of-order self-referential
  rows. Leg 2 **must** include a migration test that seeds a `restored_from` chain
  (a restore row pointing at an earlier revision) and asserts it survives the
  rebuild with the FK intact — the flight's own Divert-if names this risk, so it is
  pinned with a test rather than reasoned.

**DD4 — External writes honor the per-agent approval flag, exactly as the agent's
own writes do.** There is no per-source posture override; `_apply_revision` reads
`self_revision_requires_approval` identically for every principal. When approval
mode is on, an external write enqueues a `pending` row (tagged `external`) the
operator approves or dismisses; when off, it applies directly.
- Rationale: the operator's explicit choice, and it keeps a single governance
  control rather than forking approval semantics per principal. The operator
  already decides per agent whether *any* self-revision waits; an external client
  is just another writer under that same decision.
- Trade-off: honoring the flag means direct external writes are possible (approval
  off), which puts a genuine second live writer on the unguarded direct-write
  path — forcing DD5. (The alternative, force-queue-all-external, would have
  sidestepped DD5 but overrides the operator's flag; rejected.)

**DD5 — The direct-write path becomes a field-scoped compare-and-swap, closing the
last-writer-wins clobber on that path.** Today the persist branch of
`_apply_revision` does `config.model_copy(update={field: text})` →
`SQLiteAgentStore.save` (a whole-row upsert, no guard) — safe only under a single
writer. This flight replaces that with an atomic, base-value-guarded UPDATE:
`UPDATE agents SET {field}=?, updated_at=? WHERE name=? AND {field}=:base_value`.
Zero rows affected → the field drifted under the writer → a fail-closed *stale*
result (see the tool-result shape below).
- **Scope honesty (Architect):** this hardens the **direct-write branch only**. The
  operator **approve** path (`api.py:1143`), **restore**, and **Studio edit** (`PUT
  /api/agents/{name}`) still whole-row `save`. Approve is mutually exclusive with
  direct writes (the flag gates queued-vs-direct), but a Studio edit runs in *any*
  mode and can still clobber a freshly-applied external direct write on the *other*
  field. That residual is the debrief's "whole-row LWW now has N consumers" debt;
  DD5 closes one writer, accepted at single-operator scale — the claim is **not**
  "every principal."
- **Stale result is a tool result, not an HTTP 409 (Architect).** The operator
  approve path returns HTTP 409 because it is an HTTP request; an external/agent
  write is a **FastMCP tool call** whose result is JSON-RPC, so "return a 409" is
  unimplementable at that layer. Instead a CAS miss returns a truthful,
  non-retry-inducing tool result mirroring the pending branch's shape:
  `{applied_to_store: false, effective: "stale", field, current_value,
  proposed_value}` — returned identically to the external MCP client and to the
  agent's own in-turn call, so neither is invited into a rewrite loop.
- Rationale: debrief rec 1. An atomic field-CAS both guards the revised field
  against drift **and** avoids the whole-row clobber where a concurrent write to the
  *other* field would be lost by a full-row save. It is genuinely new code — **not**
  a copy of `set_self_revision_requires_approval` (that targeted UPDATE has *no*
  base-value guard); its nearest relative is Flight 2's approve-path *non-atomic*
  compare-then-save, which this improves by making the compare and the write one
  atomic statement.
- Trade-off: `_apply_revision`'s persist branch no longer round-trips a full
  `AgentConfig` through `save`, so the `next_turn` in-memory propagation and the log
  append must be re-sequenced around the targeted UPDATE while preserving Flight 2's
  "saved before logged" ordering (the log row is appended only after the CAS reports
  one row changed). Leg 2's design review confirms that ordering.

**DD6 — External principals reach only the four-tool confined MCP surface; the
operator control plane stays 403 for them, asserted explicitly.** The external
credential is confined (DD1) to `/mcp/self-configuration`, whose four tools are the
write allowlist by construction — none can address `self_revision_requires_approval`
(the read projection omits it, `projection.py`) or the revision transitions
(approve/dismiss/restore are `/api/agents/{name}/self-configuration/…` operator
routes, off-mount, hence 403 for a confined source). This flight makes that an
explicit acceptance criterion with a regression test: an `ext_` credential is
refused (403) on the approval-mode PUT and on approve/dismiss/restore, and its
`get_my_configuration` projection contains no approval-mode field.
- Rationale: debrief rec 2 — approval mode's by-construction safety is now
  load-bearing for a governance control against a *non-operator* principal, so the
  invariant must be tested, not merely reasoned. Reusing the existing confined
  4-tool surface means the guarantee holds without new enforcement code; the test
  pins it.
- Trade-off: none of consequence — this is asserting an existing property.

**DD7 — Rotation now means two things: rotate-everything (unchanged) for the
operator credential, and per-principal revoke-one / reissue for external
credentials.** This settles the mission's inherited open question. Mission 20's
`the-one rotate-api-credential` (rotate-everything; drops all sessions) is
retained as-is for the operator credential. External credentials add: **revoke**
(stamp `revoked_at`, evict the identifier from the in-memory registry → refused on
the next request, no restart) and **rotate** (revoke the old + mint a new
credential for the same `label`/agent, returning the new secret once). Revoke and
rotate are per-identifier and never touch the operator credential or the agent's
own `agt_` path.
- Rationale: the mission's success criterion demands withdraw + reissue with
  immediate effect and no restart; the in-memory registry already delivers
  immediacy (Flight 1's enable/disable proved it). "Rotate everything" was the
  only meaning available when one principal existed; a second principal makes
  "revoke one" both meaningful and necessary.
- Trade-off: rotate-as-revoke+mint changes the identifier. A caller that pinned the
  old identifier must take the newly-returned credential — acceptable and expected
  for a rotation.

**DD8 — The external registry rebuilds from the store at lifespan startup; revoked
rows are not loaded.** A startup reconcile (paralleling `manage.reconcile_on_startup`
for the `agt_` registry) repopulates the external `identifier → (agent_name,
secret)` registry from every non-revoked `agent_external_credentials` row, and
`register_source` wires the new source idempotently by list membership (mirroring
`register_credential_source_once`).
- Rationale: agent A's reconnaissance flagged exactly this — a new in-memory source
  that is not wired into startup reconcile silently fails to re-register after a
  restart, and every persisted credential would stop resolving. The persisted-and-
  reconciled shape is what makes "survives restart" true for external credentials
  while "revoked stops working immediately" stays true (revoked rows are skipped on
  load and evicted live on revoke).
- Trade-off: one more startup path to keep in step with the store schema.

**DD9 — An external credential dies with the surface: resolution is gated on the
surface being enabled, and disable/delete tears the credential down.** The
Architect caught that if the external registry resolved `identifier → agent_name`
directly, an `ext_` credential would keep working after the operator disabled
self-configuration for that agent — making the external path *more* privileged than
the agent's own, which DD9-of-Flight-1 (`_calling_agent` refuses unless
`row.id in config.mcp_source_ids`) already severs for the `agt_` path. So: (a)
external resolution in `_calling_agent` re-checks that the agent's surface is
currently enabled and refuses (`PermissionError`) otherwise, exactly as the agent's
own path does; and (b) `manage.disable` and `cascade_delete`/`cascade_rename` tear
down that agent's external credentials the same way they already unregister the
`agt_` credential and supersede pending revisions — evict every one of the agent's
identifiers from the external registry and stamp `revoked_at`.
- Rationale: an external principal must never outlive the operator's decision to
  close the surface. This keeps the external path exactly as revocable as, and no
  more privileged than, the agent's own — the mission's "the operator stays in
  charge throughout" made concrete for the second principal.
- Trade-off: `manage.disable` and the agent-teardown paths gain an
  external-credential step; each teardown call-site must be surveyed (the Flight 2
  lesson — "an invariant is only as good as the number of call-sites you surveyed",
  which there needed *both* surface-disable paths). Leg 1 enumerates them.

### Prerequisites

- [x] Flights 1 and 2 landed and merged — the surface, the four tools, the
      `agt_` credential, the confinement map, the `agent_revisions` log, approval
      mode, and the operator control plane all exist on `main`.
- [ ] Migrations are at v35 on `main`; this flight adds the external-credential
      table (Leg 1) and the `agent_revisions` source-CHECK rebuild + `source_principal`
      column (Leg 2) as sequential versions — verify the head version before each
      leg writes its migration.
- [ ] The `tests/test_self_configuration_surface.py` out-of-process `MCPClient`
      path is the template for exercising an external client over loopback with a
      bearer; confirm it still runs before Leg 1 builds on it.
- [ ] For the optional HAT leg: a dev instance on a non-8484 port with a scratch
      data dir (never the operator's real data dir), and a loopback MCP client to
      stand in for the external tool.

### Pre-Flight Checklist

- [x] All open questions resolved or deferred to a named leg
- [x] Design decisions documented
- [ ] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

The flight reuses everything Flight 1 built for transport and confinement and adds
a parallel credential *family* for external principals. Leg 1 stands up the
external-credential store, its `CredentialSource`, its registry + startup
reconcile, the operator mint/list/revoke/rotate endpoints, the ext→agent *routing*
resolution in `_calling_agent` (gated on surface-enabled, DD9), and the
disable/delete teardown — at the end of Leg 1 an operator can grant a scoped
credential, hand it to a loopback MCP client, that client can authenticate and call
`get_my_configuration`, and a revoked or surface-disabled credential is refused on
the next request. Leg 2 makes external *writes* first-class: it runs the
`agent_revisions` CHECK-rebuild migration to admit `external` (plus the
`source_principal` column), threads all five provenance touch-points (DD3), replaces
the direct-write whole-row save with the field-scoped compare-and-swap + stale
tool-result (DD5), honors the approval flag (DD4), and pins the governance invariant
(DD6) with a regression test. Leg 3 puts an operator Studio panel over Leg 1's
endpoints (grant with copy-once secret, list, revoke, rotate). The optional HAT
drives the whole thing live.

Both migrations are table-touching: Leg 1's is an additive `CREATE TABLE`
(→ v36); Leg 2's is a rebuild ceremony on `agent_revisions` (→ v37) that must
preserve existing rows and the `restored_from` self-reference (the v23 rebuild is
the precedent; a seeded `restored_from`-chain test pins it). Each migration is
created and executed in the same leg, verified against the live SQLite schema, not
mocks. `_calling_agent` is touched by both Leg 1 (routing) and Leg 2 (log
threading) — an intentional, stated overlap, not a boundary slip.

### Checkpoints

- [ ] An operator can mint an `ext_` credential scoped to one agent; the secret is
      returned once and never again; the list projection carries no secret.
- [ ] A loopback MCP client bearing the `ext_` credential reaches exactly that
      agent's four tools and is 403 on every off-mount path and on WS.
- [ ] Revoke evicts the credential immediately (next request refused, no restart);
      rotate returns a fresh secret for the same principal; neither disturbs the
      agent's own `agt_` path or another external credential.
- [ ] Disabling the surface for an agent refuses that agent's external credentials
      on the next request and tears them down (DD9); an `ext_` credential is never
      more privileged than the agent's own path.
- [ ] An external write is logged `source='external'` with the principal's
      identifier, and honors the approval flag (queues when on, applies when off).
- [ ] A direct write whose field drifted under it fails closed (409 stale) via the
      field-scoped CAS; a concurrent write to the other field is not clobbered.
- [ ] An `ext_` credential is 403 on approval-mode PUT and on approve/dismiss/
      restore, and its config projection omits the approval-mode field.
- [x] The Studio panel grants a credential (copy-once secret + URL), lists active
      grants secret-free, revokes, and rotates — over Leg 1's endpoints.
- [ ] Docs updated (`SECURITY-MODEL.md` external-credential source + store and its
      scope; `agents.md`/`CLAUDE.md`; any client-facing URL/port note).

### Adaptation Criteria

**Divert if**:
- The `agent_revisions` CHECK-rebuild cannot preserve the `restored_from` self-FK
  cleanly under SQLite's table-rebuild constraints — stop and re-plan the
  provenance representation (e.g. a separate provenance column set) before writing
  Leg 2's migration.
- The field-scoped CAS cannot be reconciled with the `next_turn` in-memory
  propagation without breaking Flight 2's "saved before logged" ordering — escalate
  DD5 to a scoped design decision rather than forcing it inline.

**Acceptable variations**:
- Rotate implemented as revoke+mint vs. in-place secret replacement, provided the
  identifier semantics in DD7 hold and the old secret stops working immediately.
- `last_used_at` tracking dropped if it adds a per-request write on the hot path;
  it is a convenience, not a criterion.

### Legs

> **Note:** Tentative until each is designed. Risk-tiered per `/agentic-workflow`.

- [x] `external-credential-grant` — the `agent_external_credentials` table +
      migration (v36), the `ExternalAgentCredentialSource` + in-memory registry +
      startup reconcile (DD8) + `CONFINED_SOURCE_PATHS` entry (DD1), the secret-free
      store projection (DD2), the operator mint/list/revoke/rotate endpoints (DD7),
      the **external-principal *routing* resolution in `_calling_agent`** (ext
      identifier → agent, gated on surface-enabled per DD9), and the disable/delete
      teardown of external credentials (DD9). At leg end a loopback MCP client can
      authenticate with an `ext_` credential and **read** config, and a revoked or
      surface-disabled credential is refused on the next request. **High-risk**
      (schema, secrets, new auth principal on the gate seam) → leg design review.
      *(Boundary note per Architect: the ext→agent routing lives here — Leg 1's read
      end-state depends on it; only the `source`/`source_principal` log threading is
      deferred to Leg 2. Both legs touch `_calling_agent`.)*
- [x] `external-write-provenance-and-concurrency` — the `agent_revisions`
      source-CHECK rebuild + `source_principal` column (v37) and the full five
      touch-point `source`/`source_principal` threading (DD3), honoring the approval
      flag for external writes (DD4), the field-scoped compare-and-swap + stale
      tool-result on the direct-write path (DD5), and the governance-invariant
      regression tests (DD6 — `ext_` is 403 on the operator control plane and its
      projection omits approval mode). Includes the `restored_from`-chain migration
      test (DD3). **High-risk** (state-machine/CHECK migration, shared-interface
      change with existing consumers, concurrency, security) → leg design review.
- [x] `external-credential-studio-ui` — a Studio panel on the self-configuration
      tab to **grant** a credential (copy-once secret reveal + the surface URL),
      **list** active grants (label, agent, created/last-used, secret-free per DD2),
      **revoke**, and **rotate**, over Leg 1's endpoints. Follows Flight 2's Studio
      surface idiom (the self-configuration tab, its testids, the design-language
      tokens). **Lower-risk** (additive UI over settled endpoints, single surface) —
      the flight-end Reviewer covers it; no separate leg-design review unless the
      copy-once-secret handling turns out to need one.
- [x] `uat-and-alignment` *(optional)* — guided HAT: the operator grants a
      credential (via the Studio panel) to a loopback MCP client, the client reads
      and writes, the operator sees the revision logged as `external` with the
      principal's identity (queued or applied per the flag), then revokes and watches
      the next call refused — all without restart. Look-and-feel fixes applied inline.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (`make test-unit`; relevant browser/live lanes)
- [ ] Documentation updated

### Verification

The flight is verified when: an operator can grant, list, revoke, and rotate an
`ext_` credential scoped to one agent from the platform; a loopback MCP client
bearing that credential reaches exactly that agent's four self-config tools and
nothing else; its writes are logged as `external` with the principal's identity,
honor the approval flag, and fail closed on drift; revoke and rotate take effect on
the next request with no restart and without disturbing any other principal; and no
external path can reach the approval-mode setting, the revision transitions, or any
secret — including the new credential store's own secrets.
