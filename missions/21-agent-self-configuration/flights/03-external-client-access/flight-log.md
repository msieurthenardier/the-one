# Flight Log: External Client Access

Chronological record of execution. Append-only.

---

## Reconnaissance Report

Flight 3 sources its work from the Flight 2 debrief recommendations, the mission's
inherited Open Questions, and Mission 20's deferred credential decisions — all of
which cite specific code. Each was walked against current `main` (v35) before the
legs were drafted.

| Source item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Debrief rec 1 — external is a second live writer; route through `_apply_revision`; generalize DD4's base-value compare | `confirmed-live` | `surface.py:_apply_revision` takes `agent_name` as a plain string (reusable) but hard-wires `source="self"`; direct-write persist branch calls whole-row `SQLiteAgentStore.save` with **no** staleness guard; only the operator approve path has the field-scoped compare (`api.py`, DD4-of-F2) | → DD4 (honor flag) + DD5 (field-scoped CAS on the direct path) |
| Debrief rec 2 — add `source='external'`; make "no external write path addresses approval-mode/transitions" an explicit AC | `confirmed-live` | `schema.py` `agent_revisions` CHECK is frozen at `source IN ('self','restore')`; approval-mode column omitted from `projection.py` `get_my_configuration`; approve/dismiss/restore are `/api/…` operator routes | → DD3 (CHECK rebuild + `source_principal`) + DD6 (governance test) |
| Debrief rec 3 — credential store crosses the secrets boundary Flight 2 stayed inside; extend structural-projection discipline | `confirmed-live` | Flight 2 added no encrypted columns; the new external store is a secrets-bearing table; the `agt_` secret is already encrypted-at-rest inside `mcp_sources.secrets` (the reuse target for encryption) | → DD2 (encrypted store + secret-free projection) |
| Mission OQ — "what does rotation mean now that more than one principal exists?" | `confirmed-live` | `the-one rotate-api-credential` (`main.py`) is rotate-everything for the one file credential; there is **no** revoke-by-identifier despite `LocalApiCredential`'s id/secret split being built for exactly that | → DD7 (revoke-one + rotate per external principal) |
| Mission OQ — "how much do the agent's path and the external client's path share?" | `already-satisfied` (by Flight 1) | Flight 1 chose the real mounted Streamable-HTTP MCP source; the surface is out-of-process loopback-reachable at `/mcp/self-configuration/`; the credential gate + `CONFINED_SOURCE_PATHS` + `_calling_agent` already scope one credential to one agent | Transport/scoping already built; flight scope narrows to credential *delivery* + distinct principal + provenance/concurrency |
| Mission criterion — "withdrawn stops working immediately; reissue without restart" | `already-satisfied` (mechanism) | Flight 1's enable/disable mutate the in-memory `identifier→(source_id,secret)` registry live; a dropped identifier is refused on the next request with no restart | Reuse the same in-memory-registry pattern for the external registry (DD1/DD8); the *missing verb* is per-identifier revoke, not the immediacy mechanism |
| Agent-A restart-survival flag — a new in-memory source not wired into startup reconcile silently fails to re-register | `confirmed-live` | The `agt_` registry is rebuilt by `manage.reconcile_on_startup`; a parallel external registry needs the same wiring or persisted credentials stop resolving after restart | → DD8 (startup reconcile for the external registry) |

**Net:** the two "already-satisfied" items are what reshaped the flight — Flight 1
delivered more external-facing scaffolding than the mission text anticipated, so
Flight 3 is credential *delivery* + a distinct revocable principal + provenance/
concurrency/governance, not a from-scratch external path. Nothing was retired from
the mission's scope; the external-client criterion remains open and is this
flight's primary target.

---

## Flight Director Notes

### Planning (2026-08-26)

- **Reconnaissance run as three parallel Explore agents** over (a) the Mission 20
  credential substrate, (b) the self-config surface write-path internals, and (c)
  the external-client connection mechanics. Their maps are the evidence behind the
  Reconnaissance Report and the DD citations.
- **Operator direction (this planning session):** full scope; **distinct
  principals** (so external systems — and other agents *inside* the-one acting as
  clients — can be revoked/rotated independently); **honor the per-agent approval
  flag** for external writes; **include a HAT** as the mission nears its end. These
  fixed DD1 (distinct principal), DD4 (honor flag → forcing DD5), DD7 (per-principal
  revoke/rotate), and the optional HAT leg.
- **Agent-to-agent tuning is an in-scope external use.** "Another agent in the-one"
  tuning a different agent presents as an external principal like any other — it is
  a loopback MCP client bearing an `ext_` credential — which is a further reason
  provenance (DD3) and per-principal revoke (DD7) are load-bearing rather than
  precautionary.
- **Concurrency posture resolved by the flag choice.** Honoring the approval flag
  (DD4) means direct external writes are possible when approval is off, which puts a
  genuine second writer on the unguarded direct path — so DD5 (field-scoped CAS) is
  required, not optional. The rejected alternative (force-queue-all-external) would
  have dodged DD5 but overridden the operator's flag.
- **Legs:** two high-risk autonomous legs (both get leg-design review per the
  risk tiers — schema/CHECK migrations, a shared-interface change to
  `_apply_revision` with existing consumers, a new auth principal, concurrency, and
  a security-governance surface) plus an optional HAT.

<!-- Leg entries, review findings, and decisions are appended below during execution. -->

### Design Review — Architect, cycle 1 (2026-08-26)

Spawned one Architect agent to cross-reference the spec against `main` (v35). It
verified every cited location (CURRENT_VERSION, the v34 CHECK, the two `source="self"`
literals, the whole-row `save`, the targeted-UPDATE precedent, `PRAGMA foreign_keys=ON`
on the real connection, the confinement gate, the approval-mode projection omission).
**Verdict: approve with changes.** Findings and dispositions:

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| 1 | high | Leg-boundary bug — Leg 1's "read config" end-state needs ext→agent resolution in `_calling_agent`, but the spec placed that in Leg 2; as scoped, Leg 1 tool calls would fail | **Fixed** — routing resolution moved to Leg 1; only `source`/`source_principal` log threading stays in Leg 2; overlap stated in Technical Approach + Leg 1 boundary note |
| 2 | med | DD5 "409 stale" is a category error on the MCP tool path — a tool call returns JSON-RPC, not HTTP 409 | **Fixed** — DD5 now defines a tool-result shape (`applied_to_store:false, effective:"stale", field, current_value, proposed_value`) returned to external client and agent alike |
| 3 | med | DD5 overclaims "every principal" — CAS hardens only the direct path; approve/restore/Studio-edit still whole-row save, and Studio edit can clobber a fresh external write on the other field | **Fixed** — DD5 scope-honesty bullet; claim narrowed to the direct-write path, residual named as accepted single-operator debt |
| 4 | med | Surface-disable governance gap — a direct ext→agent_name map would let an `ext_` credential outlive `manage.disable`, more privileged than the agent's own path | **Fixed** — new **DD9**: ext resolution gated on surface-enabled; disable/delete/rename tear down the agent's external credentials |
| 5 | med | DD3 incomplete — widening `source` is five touch-points (model `Literal` at `models.py:708`, model field, `append`, `_row_to_model`, `upsert_pending_revision`), not two literals; unwidened model → 500 on read | **Fixed** — DD3 enumerates all five; the "citation-density ≠ completeness" lesson cited |

Suggestions taken: the **v23 rebuild** named as the `agent_revisions` table-rebuild
precedent and a seeded `restored_from`-chain migration test pinned in Leg 2 (DD3);
DD5's precedent framing corrected (the atomic field-CAS is new, *not* a copy of the
guardless `set_self_revision_requires_approval`). Product fork raised — Studio UI for
external-credential management — **resolved by the operator: its own leg** (Leg 3,
`external-credential-studio-ui`).

Changes were substantive (a new DD, a leg boundary move, a new leg). A second review
cycle is available if the operator wants it before execution; the fixes are localized
and citation-backed, so the recommendation is to proceed to execution and let the two
high-risk legs' own design reviews (per `/agentic-workflow` risk tiers) catch anything
downstream.

### Orchestration start (2026-08-27) — /agentic-workflow

- Phase file `leg-execution.md` loaded and validated (Crew / Interaction Protocol /
  Prompts present; Developer + Reviewer + optional Accessibility Reviewer prompts).
- Mission `active`, flight transitioned `ready → in-flight`. Branch
  `flight/03-external-client-access` created off `main` @ b942395.
- **Leg plan:** 3 autonomous — `external-credential-grant` (L01),
  `external-write-provenance-and-concurrency` (L02), `external-credential-studio-ui`
  (L03) — plus optional HAT `uat-and-alignment` (L04). `legs_completed = 0`.
- Env-conflict check: this flight adds no new network service/port — it reuses the
  existing loopback server and MCP mount. The HAT uses a non-8484 port + scratch data
  dir (Flight 2 precedent). No conflict at planning.
- Starting Leg 1 design (2a).

### Leg 1 design — `external-credential-grant` (2026-08-27)

- **Risk tier: HIGH** → leg-design review (2a steps 3-4). Triggers: v36 schema
  migration; a secrets-bearing table; a new auth principal registered on the gate
  seam; an interface change to `_calling_agent` (shared with the surface tools).
- **Design refinement of DD2/DD9 recorded in the leg (Context).** Reading
  `manage.disable`/`cascade_delete`/`cascade_rename` showed that keying the store's
  FK on the **surface row's `source_id`** (`REFERENCES mcp_sources(id) ON DELETE
  CASCADE`) — rather than the flight's sketched `agent_name` FK — makes
  surface-disable and agent-delete **auto-revoke** external credentials via cascade,
  and lets external resolution **reuse `_calling_agent`'s existing DD9 refusal**
  (`row.id in config.mcp_source_ids`) instead of a re-implemented surface-enabled
  check. Agent rename is a non-event (row id stable). This is a strictly-better
  mechanism for the same DD9 intent; it also drops `revoked_at` (hard-revoke, since
  cascade hard-deletes and audit lives in the Leg 2 revision log's `source_principal`)
  and defers `last_used_at` (flight Adaptation Criteria). The flight's DD2/DD9 intent
  is unchanged; the leg makes the mechanism concrete. Flagged for the design review.
- Spawned one Developer for leg-design review.

### Leg 1 design review — Developer, cycle 1 (2026-08-27)

**Verdict: approve with changes.** The Developer verified every load-bearing claim
against `main` @ b942395 — the source_id-FK-cascade is sound (`mcp_sources.id` is
`TEXT PRIMARY KEY`; `PRAGMA foreign_keys=ON` at `connection.py:20`; `disable`/
`cascade_delete` hard-delete the row; `cascade_rename` keeps the id), `_calling_agent`
routing is source-agnostic downstream, confinement of a second same-mount source is
conflict-free, prefix routing falls `ext_` through to the new source, the v34 block is
a faithful v36 template, and the lifespan has a real registration/reconcile home
(`app.py:199-201`). Dispositions:

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| 1 | med | Mint's 409-gate keyed on `find_surface_row` would admit **orphaned** (detached) rows, minting a dormant credential that silently works on re-attach | **Fixed** — AC3 + guidance #6 now gate on **enabled** (`row.id in mcp_source_ids`), 409 on both no-row and orphaned |
| 2 | med | AC6/AC8/AC9 "MCPClient modeled on the template" understates the delta — the template derives auth from a surface row; an `ext_` standalone bearer has none | **Fixed** — Verification Steps now specify the explicit presentation path (synthetic in-memory `MCPSource` with `secrets["Authorization"]` + `surface_url()`, or a raw `streamable_http` client) |
| 3 | low | Malformed-marker fallback in `delete_mcp_source` (`api.py:~2010`) bypasses `manage.disable`'s registry eviction | **Fixed** — Edge Cases carry a defensive-comment note; harmless today (mint requires a non-None owner) |

Suggestions taken: AC1/AC9 verification now asserts `PRAGMA foreign_keys == 1` on the
connection under test (else cascade false-passes) and list empty-for-disabled /
non-empty-for-orphaned; AC11 asserts membership-based idempotency across a `_sources`
swap. Changes were localized AC/guidance clarifications, not a redesign → **no second
review cycle** (2a step 4). Leg 1 → `ready`. `[HANDOFF:review-needed]` (design final).
Proceeding to implementation (2b).

### Leg 1 implementation — Developer (2026-08-27)

**Landed.** Stood up the external-client credential principal end-to-end; a
loopback MCP client can now authenticate with an `ext_` credential and **read**
its one agent's config, and a revoked or surface-disabled credential is refused
on the next request with no restart.

**Built:**
- `constants.py` — `EXTERNAL_SOURCE_NAME = "self-configuration-external"`,
  `EXTERNAL_CREDENTIAL_PREFIX = "ext"`, and the second `CONFINED_SOURCE_PATHS`
  entry (same mount → confinement inherited unchanged, DD1).
- `schema.py` — v36 migration (`CURRENT_VERSION = 36`): `agent_external_credentials
  (identifier PK, source_id NOT NULL REFERENCES mcp_sources(id) ON DELETE CASCADE,
  secret NOT NULL, label NOT NULL, created_at NOT NULL)` + index on `source_id`,
  mirroring the v34 template (IF NOT EXISTS, version stamp `INSERT OR IGNORE` last).
- `repositories.py` — `AgentExternalCredentialRepository(conn, encryptor)`:
  `create` (secret Fernet-encrypted via `encryptor.encrypt`), `list_for_source` /
  `get` (secret-free projections — never SELECT `secret`), `delete -> bool`,
  `load_all` (decrypted `(identifier, source_id, secret)` for reconcile).
- `external_credentials.py` (NEW) — `_ext_registry: dict[identifier -> (source_id,
  secret)]`, `register` / `unregister(source_id)` (teardown) /
  `unregister_identifier(identifier)` (revoke-one) / `source_id_for` /
  `load_from_rows` / `clear_for_test`, `ExternalAgentCredentialSource` (constant-time
  compare), `register_credential_source_once` (idempotent by ACTUAL LIST MEMBERSHIP).
- `surface.py` — `_calling_agent` routes `caller.source == EXTERNAL_SOURCE_NAME` to
  the external registry, then shares the existing owner-resolution + `row.id in
  config.mcp_source_ids` DD9 refusal tail unchanged (external gate is free).
- `manage.py` — external-registry eviction added after the existing
  `unregister(row.id)` in `disable` and `cascade_delete`; `cascade_rename` needs
  nothing (row id stable).
- `api.py` — `_agent_external_credentials_repo()` + four operator routes under
  `/api/agents/{name}/self-configuration/external-credentials` (mint / list /
  revoke / rotate). Mint & rotate gate on **enabled** (`status()['enabled']`), 409
  on no-row AND orphaned (review Issue #1); revoke & rotate enforce the cross-ID
  guard (404 on a foreign identifier). Token (`ext_<id>.<secret>`) returned once at
  mint/rotate, never on any other path. Defensive comment added at the
  malformed-marker `delete_mcp_source` fallback (Edge Case / review Issue #3).
- `app.py` — lifespan registers `ExternalAgentCredentialSource` and rebuilds the
  external registry from `load_all()` (DD8), beside the existing `agt` reconcile.

**Tests (all host-native via the repo venv):**
- Migration (`test_db_migration.py::TestSchemaV36`): table shape, `source_id`
  index, idempotent re-run, v35→v36 upgrade, and the **FK cascade** — asserting
  `PRAGMA foreign_keys == 1` on the connection under test first (else AC9
  false-passes).
- Repository (`test_db_repositories.py`): secret **encrypted at rest** (raw column
  ≠ plaintext; `load_all` round-trips), secret-free `list_for_source` / `get`,
  per-source scoping, `delete -> bool` idempotency.
- Endpoint + registry lifecycle (`test_self_configuration_external.py`, NEW, 18
  tests): mint (token-once / 409-not-enabled / 409-orphaned / 404-unknown),
  secret-free list, revoke (401-after / no-disturb-others / cross-ID 404), rotate
  (old dies + new authenticates / cross-ID 404), disable & agent-delete cascade +
  registry eviction, orphaned keeps rows, startup reconcile rebuilds live / drops
  revoked (AC10), seam registration idempotent across a `_sources` swap (AC11).
- Confinement (`test_credential_gate.py`): updated the exact-map assertion for the
  second entry; added an external-source case (admitted under mount, 403 off-mount,
  WS 1008 refused) — AC7.
- Out-of-process MCPClient (`test_self_configuration_surface.py`, AC6/AC8/AC9):
  presented the standalone `ext_` bearer via a **synthetic in-memory `MCPSource`**
  (`secrets["Authorization"]` + `surface_url()`, `auth_provider=None`) per the
  review Issue #2 presentation-path note. AC6 reads the secret-free / approval-free
  projection; AC8 cross-agent isolation; AC9 orphaned surface → `MCPCallError`
  "disabled" tool refusal, disabled surface → 401 (`MCPAuthRequired`).

`make test-unit`: **4481 passed, 10 skipped (pre-existing, none mine), 0 failed.**

**Deviations from the leg spec (all within Acceptable variations / mechanical):**
- `AgentExternalCredentialRepository.create` takes primitive `identifier` / `secret`
  kwargs (not a `LocalApiCredential` object) — keeps `repositories.py` decoupled
  from `api_credential`; the endpoints pass `credential.identifier` /
  `credential.secret`. Secret stored via `encryptor.encrypt` (the single-string
  path), not the dict `_encrypt_secrets_blob` envelope — the store holds one scalar
  secret, and `load_all` uses the matching `encryptor.decrypt`.
- Fixed a pre-existing test made stale by stacking v36 on top of v35:
  `TestSchemaV35::test_v35_upgrade_from_v34_adds_column` rewound only `version = 35`,
  leaving the new v36 stamp as head so the v35 block never re-fired — changed to
  `>= 35` (mirrors the v34 test's `>= 34` rewind). No production behavior change.

**Deferred (noted for the flight-end doc pass):** the `SECURITY-MODEL.md` note on
the external-credential source + store + its scope was NOT written this leg (the
leg permits deferring it to the flight-end doc pass). Nothing else deferred; no
scope was expanded.

**For Leg 2 / the flight-end Reviewer:** `_calling_agent` returns `agent_name` as
today — Leg 2 extends it for `source_principal` provenance (the external caller's
identity is available as `caller.identifier` off the ASGI scope). The external
registry's `source_id_for` mirrors the `agt` one, so Leg 2's log threading can key
off `caller.source == EXTERNAL_SOURCE_NAME` at the tool layer.

### Leg 1 landed (2026-08-27)

Developer implemented `external-credential-grant` fully. `make test-unit`: **4481
passed / 10 skipped / 0 failed** (+34 in-lane vs Flight 2's 4447). New table v36
(`source_id` FK cascade, index), `AgentExternalCredentialRepository` (Fernet secret,
secret-free projection), `external_credentials.py` (registry + source, list-membership
idempotent), `_calling_agent` external routing, `manage.disable`/`cascade_delete`
registry eviction, four operator endpoints (enabled-gate 409, cross-ID 404, token-once),
lifespan registration + reconcile. 18 new endpoint/lifecycle tests + migration
(FK-cascade with `PRAGMA foreign_keys==1`), secret-at-rest, confinement (AC7), and
out-of-process `MCPClient` (AC6/8/9 via synthetic-`MCPSource` presentation) tests.
Minor deviations (within Acceptable variations): `create` takes primitive
`identifier`/`secret` kwargs; a pre-existing v35 migration test made stale by stacking
v36 was corrected to `>= 35` (mirrors the v34 test; no production change). Leg `landed`,
not committed (batched to flight-end). `legs_completed = 1`.

### Leg 2 design — `external-write-provenance-and-concurrency` (2026-08-27)

- **Risk tier: HIGH** → leg-design review. Triggers: v37 CHECK-rebuild migration on
  `agent_revisions`; a shared-interface change to `_apply_revision` (existing
  consumers: the agent's own write tools); state-machine/concurrency (the field-scoped
  CAS replacing whole-row save on the direct path); security-governance surface (DD6).
- Designed against real post-Leg-1 code. Refinements found while reading: (a) the
  provenance widening is **six** effective touch-points once the write tools' resolver
  is counted (model, `append`, `upsert_pending_revision` insert AND update branches,
  `_row_to_model`, `_apply_revision`, `_calling_principal`); (b) the pending-dedup
  **UPDATE** branch must also refresh `source`/`source_principal` so a re-propose by a
  different principal reflects the latest proposer; (c) the v37 migration is guarded on
  `source_principal` column presence for schema-rewind idempotency; (d) the approval
  flow preserves external provenance for free (`_transition` never rewrites `source`).
- Spawned one Developer for leg-design review.

### Leg 2 design review — Developer, cycle 1 (2026-08-27)

**Verdict: approve with changes.** Every hard part verified against the real
post-Leg-1 tree: `CURRENT_VERSION == 36`; no `PRAGMA legacy_alter_table=ON` anywhere
(self-FK rewrite-under-RENAME safe, v23 precedent); `cur.rowcount` on UPDATE already
used (`supersede_pending`); `_row_to_model` is the only `.source` reader and `GET
…/revisions` returns `model_dump()` so `source_principal` is exposed for free;
`_transition` never rewrites `source` (external provenance survives approve);
projection omits approval mode; `_apply_revision` has exactly two callers, defaulted
params break none. Dispositions:

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| 1 | med | AC9 didn't name the two tests that break: `TestSchemaV34::test_v34_fresh_db_has_agent_revisions_table` (10-column-set pin) and `test_self_configuration_write.py::test_save_failure_leaves_no_orphan_log_row` (monkeypatches `save`, now inert) | **Fixed** — AC9 + Files Affected name both; the save-failure test retargets its monkeypatch to `compare_and_set_field` |
| 2 | med | Migration rebuild-firing tests would **false-pass** via a stamp-only rewind — the `source_principal`-presence guard short-circuits the ceremony (same class as Leg 1's `>= 35` fix) | **Fixed** — Verification Steps now require the rebuild-firing tests to build a genuine `source_principal`-less v36 table (DROP + recreate at v34 shape, seed, stamp 36, `ensure_schema`); stamp-only rewind used only for the idempotency test |
| 3 | low | `INSERT … SELECT` relied on positional trailing NULL / physical column order | **Fixed** — guidance #2 names the 10 columns explicitly on both sides (v23 precedent) |

Suggestions taken: v37 CHECK test asserts `external` accepted + `source_principal`
NULL-for-self/value-for-external; stale result carries a short `message` for family
consistency; `_calling_principal`/`_calling_agent` factor through one
`_resolve_caller_and_agent` (DD9 tail run once); optional CAS `exists()` pre-check
noted; browser seed INSERTs confirmed safe-as-is (explicit columns, NULL default).
Question on the queued-then-approved external write still using whole-row `save`
(api.py approve path) — confirmed the intended DD5 scope carry, not an oversight.
Changes localized to test setup + guidance → **no second review cycle**. Leg 2 →
`ready`. `[HANDOFF:review-needed]`. Proceeding to implementation.

### Leg 2 implementation — Developer (2026-08-27)

**Landed.** External *writes* are now first-class: logged with provenance
(`source='external'` + the principal's identifier), honoring the per-agent
approval flag exactly as the agent's own writes do, with the direct-write path
hardened by a field-scoped compare-and-swap that fails closed on drift with a
truthful stale tool result — and the governance invariant (no external principal
reaches the operator control plane) pinned by regression tests.

**Built (production):**
- `db/models.py` — `AgentRevision.source` Literal widened to include
  `"external"`; new `source_principal: str | None = None` (the ext credential
  identifier for external rows, NULL for self/restore — id, never secret).
- `db/schema.py` — **migration v37** (`CURRENT_VERSION = 37`): the
  `agent_revisions` table-rebuild ceremony (v23 precedent). `executescript`
  envelope (`PRAGMA foreign_keys=OFF` → CREATE `agent_revisions_new` with the
  widened `source CHECK IN ('self','restore','external')`, nullable
  `source_principal TEXT`, the `restored_from` self-FK against the NEW table, and
  the `agent_name … ON DELETE CASCADE` FK → `INSERT … SELECT` naming all 10
  existing columns explicitly on both sides (source_principal defaults NULL) →
  DROP → RENAME (self-FK rewrites) → recreate `idx_agent_revisions_agent_status`)
  → `PRAGMA foreign_keys=ON` → version stamp `INSERT OR IGNORE` LAST. Guarded on
  `source_principal` column ABSENCE (PRAGMA table_info) for schema-rewind
  idempotency. **Deviation (mechanical, correctness fix):** the rebuild DDL runs
  in ONE `executescript` (not sequential `conn.execute` calls) — `PRAGMA
  foreign_keys=ON/OFF` is a no-op inside an open transaction, and `executescript`
  forces the COMMIT boundary the PRAGMAs need (verified: FK enforcement is ON
  after `ensure_schema`; the v21 cascade test proved a sequential-execute version
  left it OFF). This matches the v23 precedent's use of `executescript`.
- `db/repositories.py` — `AgentRevisionRepository.append` gains
  `source_principal` (INSERT column + param); `upsert_pending_revision` gains
  `source`/`source_principal`, threaded to the insert branch AND set in the
  in-place UPDATE branch (a re-propose by a different principal refreshes who
  proposed); `_row_to_model` maps the new column. New
  `SQLiteAgentStore.compare_and_set_field(name, field, base_value, new_value) ->
  bool` — the field-scoped CAS (whitelist assert on `field ∈
  {description,system_prompt}` since the column is interpolated; single guarded
  `UPDATE … WHERE name=? AND {field}=?base_value`; returns `rowcount == 1`).
- `self_configuration/surface.py` — factored `_resolve_caller_and_agent(ctx) ->
  (caller, agent_name)` running the DD9 refusal tail ONCE; `_calling_agent`
  (reads) and new `_calling_principal(ctx) -> (agent_name, source,
  source_principal)` (writes) both derive from it (`source="external"` iff
  `caller.source == EXTERNAL_SOURCE_NAME`, principal = `caller.identifier`).
  `_apply_revision` gains `source`/`source_principal` params threaded to BOTH
  `upsert_pending_revision` (approval branch) and `append`; the persist branch
  replaces whole-row `save` with the CAS — on a miss it re-reads current and
  returns `{applied_to_store:false, effective:"stale", field, current_value,
  proposed_value, message}` (returned BEFORE any `pending.record`, so a stale
  write leaves no in-memory deferral); on success it `append`s AFTER the CAS
  confirms (saved-before-logged preserved), then `next_turn` `pending.record`.
  The two write tools switch to `_calling_principal`.

**No new enforcement code for DD6/AC8** — the `ext_` 403 on the operator control
plane is an existing property of the confinement (every `/api/…` route is
off-mount); the leg pins it with tests.

**Tests (all host-native; `make test-unit`: 4507 passed, 10 skipped, 0 failed —
+26 vs Leg 1's 4481):**
- Migration (`test_db_migration.py::TestSchemaV37`, 4 new): rebuild widens the
  CHECK (`external` accepted, bogus source rejected, `source_principal` NULL for
  self/restore + value for external) and preserves existing rows; `restored_from`
  chain survives (self-FK intact, pointed-at row unchanged, ON DELETE SET NULL
  live); stamp-only-rewind idempotency (guard skips); double-ensure stamps once.
  Rebuild-firing tests use the genuine `source_principal`-less v36 setup (DROP +
  recreate at v34 shape, seed, stamp 36, `ensure_schema`) to avoid the false-pass;
  all assert `PRAGMA foreign_keys == 1`.
- CAS + provenance repo (`test_db_repositories.py`, 7 new):
  `TestCompareAndSetField` (hit writes only that field + returns True; miss on
  drift returns False + writes nothing; concurrent OTHER-field write not
  clobbered — AC5; non-whitelisted field raises); `TestAgentRevisionProvenance`
  (`_row_to_model` round-trips an external row — AC7; append defaults principal
  NULL; re-propose by a different principal updates provenance on the deduped
  row — AC7).
- Surface provenance/approval/stale (`test_self_configuration_write.py`, 7 new):
  external direct write logs `external`+principal, agent's own logs `self`+NULL
  (AC3); external write honors approval flag → pending row tagged external (AC4);
  operator approve preserves external provenance (AC4); stale direct write fails
  closed with the truthful result, store shows concurrent value, no row logged,
  identical for external and agent-own calls (AC6); projection omits approval
  mode (AC8).
- Governance (`test_credential_gate.py`, 1 parametrized × 8 routes): an `ext_`
  bearer is 403 on `PUT …/approval-mode`, `POST …/revisions/{id}/
  approve|dismiss|restore`, and the four external-credential management endpoints
  (AC8).

**Two named regressions retargeted in place (AC9):**
1. `TestSchemaV34::test_v34_fresh_db_has_agent_revisions_table` — expected column
   set gains `source_principal` (v37 rebuilds this table on a head DB).
2. `test_self_configuration_write.py` — the save-failure orphan-log test was
   renamed `test_persist_failure_leaves_no_orphan_log_row` and retargets its
   monkeypatch from `SQLiteAgentStore.save` to `compare_and_set_field` (the CAS
   direct path no longer calls `save`), preserving the saved-before-logged
   assertion.

**Test-infra note (not a spec deviation):** the shared `_as_agent` helper in
`test_self_configuration_write.py` now also patches `_calling_principal` (returning
`(name,"self",None)`) since the write tools resolve provenance through it — this
keeps every existing self-path write test green; a new `_as_external` helper drives
the external-principal tests.

**Deferred (flight-end doc pass):** the `SECURITY-MODEL.md` / `agents.md`
provenance + external-write note is NOT written this leg (the leg permits folding
it into the flight-end doc pass). Nothing else deferred; no scope expanded.

**For Leg 3 / the flight-end Reviewer:** DD5's scope is the direct-write branch
only — the operator approve path (`api.py`), restore, and Studio edit remain
whole-row writers (accepted single-operator debt, flight DD5); this leg did not
touch them. `GET …/revisions` returns `model_dump()`, so `source`/`source_principal`
are already exposed for the Studio history view Leg 3 builds over. Not committed
(batched to flight-end). `legs_completed = 2`.

### Leg 2 landed (2026-08-27)

Developer implemented `external-write-provenance-and-concurrency`. `make test-unit`:
**4507 passed / 10 skipped / 0 failed** (+26 vs Leg 1). v37 migration (table-rebuild
widening `source` CHECK to include `external` + nullable `source_principal`, guarded on
column absence), `AgentRevision` model widened, provenance threaded through
`append`/`upsert_pending_revision` (both branches)/`_row_to_model`, new
`compare_and_set_field` CAS, `_resolve_caller_and_agent` factoring + `_calling_principal`,
`_apply_revision` CAS + stale tool-result. Two named regressions retargeted in place
(the v34 column-set test; the save-failure test → monkeypatch `compare_and_set_field`).
**Deviation (sound):** the v37 rebuild DDL runs as one `executescript` (matching the
v23 precedent) because `PRAGMA foreign_keys=ON/OFF` is a no-op inside an open
transaction — a sequential-execute version left FK enforcement OFF after
`ensure_schema` (caught by the pre-existing v21 cascade test); `executescript` forces
the required COMMIT boundary. FK enforcement verified ON afterward. Note: the
Developer's first turn ended ambiguously ("waiting for the monitor"); the FD launched an
independent `make test-unit` to verify, and the Developer then re-reported LANDED with
the green result. Leg `landed`, checked off, not committed. `legs_completed = 2`.

### Leg 3 design — `external-credential-studio-ui` (2026-08-27)

- **Risk tier: LOW** (flight pre-tiering) → no leg-design review; the flight-end
  Reviewer + the crew's Accessibility Reviewer cover it. Rationale: additive UI over
  Leg 1's settled, tested mint/list/revoke/rotate endpoints; single established surface
  (the self-config tab + its `studio.js` callbacks + `agent-editor.js` wiring, exactly
  the Flight 2 idiom); no auth/gating logic in the client (server mints/scopes/revokes).
  The one sensitivity — the copy-once secret reveal — is display-only and pinned by
  explicit secret-hygiene ACs (no persistence, cleared on re-render), which is the
  flight's stated condition for skipping a separate review.
- Designed against real post-Leg-2 code (the callback idiom at `studio.js:1020-1160`,
  the tab section idiom, the a11y action-announcement bridge). Proceeding to
  implementation (2b). `legs_completed = 2`.

### Leg 2 test corroboration (FD, 2026-08-27)

The FD's independent `make test-unit` (launched during the wrap-up ambiguity) finished:
**4507 passed / 10 skipped / 0 failed**, exactly matching the Developer's report, in
**585s (9m45s)** wall-clock on an isolated run (no concurrent load) — a clean metric for
the flight debrief, addressing Flight 2's "measure on an isolated run" recommendation.

### Leg 3 landed (2026-08-27)

Developer implemented `external-credential-studio-ui`. The **External access** section
on the self-config tab: four callbacks in `areas/studio.js` (mint/list/revoke/rotate),
wired via `agent-editor.js`, rendered in `self-configuration-tab.js` (grant control,
copy-once secret reveal + URL, active-grants list with revoke/rotate), minimal
`studio.css`. New `tests/browser/test_studio_self_configuration_external.py` (8 tests).
The Developer again ended its turn on the same test-monitor-wait ambiguity as Leg 2, so
the FD verified directly: the 8 browser tests **pass** (`-m browser`, 17s); `ruff check`
clean; Leg 3 touched no Python (JS/CSS/browser-test only) so the unit suite is unchanged
(a `make test-unit` no-regression run was launched to confirm collection). Leg marked
`landed`, checked off in flight.md, not committed. `legs_completed = 3` (all autonomous
legs done). **FD note:** the Developer crew stalled on final wrap-up on both Leg 2 and
Leg 3 — ending the turn waiting on a Monitor test result that doesn't resolve within the
agent's turn. The FD completed the bookkeeping and independently verified tests each
time. Worth a debrief note (crew "Implement" prompt + Monitor interaction).

### Leg 3 landed — `external-credential-studio-ui` (2026-08-27)

Developer implemented the operator-facing **External access** section on the agent
Self-configuration tab, over Leg 1's mint/list/revoke/rotate endpoints. No backend
changes.

**What was built:**
- Four callbacks in `areas/studio.js` (`mintExternalCredential`, `fetchExternalCredentials`,
  `revokeExternalCredential`, `rotateExternalCredential`), each throwing `HTTP <status>`
  on non-OK, mirroring the self-config idiom. **Deliberately NOT routed through**
  `_refreshAgentAfterSelfConfigurationChange` — a whole-editor re-render would tear down
  the copy-once reveal before the operator copies; actions do a local list re-fetch instead.
- Wired through `agent-editor.js` into `renderSelfConfigurationTab`'s callbacks object.
- New **External access** `.editor-section` in `self-configuration-tab.js` after revision
  history: labelled grant input + Grant button, a copy-once secret reveal (readonly token
  field + Copy + surface URL + shown-once warning banner + Dismiss), and the active-grants
  list (label, `ext_<id>`, relative created-time via `formatTimeAgo`, Rotate + two-step
  Revoke). Enablement-gated on `status.enabled` (grant disabled + hint + empty list when
  the surface is off); create-mode inherits the tab's existing save-first early return.
- Secret hygiene: token held only in the reveal DOM/closure, never `localStorage`/
  `sessionStorage`, cleared on dismiss or the next full tab render. List projection is
  secret-free (asserted no secret text in list DOM). Labels rendered as text content only.
- Reused `App.confirmDelete` (confirm.js) for the two-step Revoke; the copy affordance
  mirrors provider-editor's clipboard idiom. Minimal theme-aware CSS in `studio.css`
  (tokens only). 16 new testids registered in `docs/ui-testid-registry.md`.

**Tests:** new `tests/browser/test_studio_self_configuration_external.py` — **8 browser
tests** (studio lane) covering AC1-AC8 (enablement gate on+off, grant→token-once→list-
updates + focus-on-reveal, secret-free list + no web-storage persistence, two-step revoke
+ focus-on-input + server-side gone, rotate reveals new token + identifier changes, empty/
whitespace inline rejection with no round-trip, label-as-text/no-HTML-injection, create-
mode save-first, disable cascades grants away). Existing self-config browser tests
regression-clean (tab 3/3, history 3/3, queue 5/5). `make test-unit`: **4507 passed / 10
skipped / 0 failed** (unchanged count — UI-only leg adds no Python unit tests).

**Deviations (sound):**
- **A11y announcement channel.** AC7 asks the actions be announced "via the tab's existing
  action-announcement bridge." That bridge (`pendingAction`/`actionStatus`) is structurally
  tied to the full-editor re-render, which this leg is explicitly told NOT to trigger (it
  would destroy the copy-once reveal). So the section announces through its own
  `role="status" aria-live="polite"` line — the same live-region idiom the tab's existing
  status/count lines already use — and moves focus itself (reveal Copy button after
  grant/rotate; grant input after revoke/dismiss; never the page top). Functionally
  equivalent, and the only way to keep the reveal alive. Flagged for the Accessibility
  Reviewer.
- **Two guard-test fixes during iteration.** First full `make test-unit` surfaced two
  failures, both from this leg and both fixed: (1) `studio.css` referenced a non-existent
  `--fg-primary` token → changed to `--fg` (`test_token_definitions`); (2) a code comment
  literally containing `panel.innerHTML = ''` tripped the line-based dynamic-innerHTML-sink
  classifier (`test_no_new_dynamic_innerhtml_sinks`) → comment reworded. The real
  `innerHTML = ''` list-clears are empty-string (classified static, like the tab's existing
  ones). Re-run green.

**For the flight-end Reviewer / Accessibility Reviewer / HAT:**
- Rotate is single-click (no confirm) — the leg only mandates a confirm affordance for
  Revoke; rotate immediately invalidates the old token and reveals a new one. Revisit if
  the HAT wants a rotate confirm too.
- Docs deferred to the flight-end pass: the `SECURITY-MODEL.md` note on the external-
  credential grant UI (Files Affected lists it as fold-into-flight-end).
- Not committed; no `[HANDOFF:review-needed]` signalled (per leg instruction).

### Flight-end review — Phase 2d (2026-08-27)

All three autonomous legs landed; unit no-regression confirmed (**4507 passed / 10
skipped / 0 failed**, identical to Leg 2 — Leg 3 touched no Python). Ran the flight-end
Reviewer (all uncommitted Legs 1-3) and an Accessibility Reviewer (the new UI) in
parallel; both signaled **[HANDOFF:confirmed]**.

**Code Reviewer — satisfactory, no blocking issues.** Verified every high-risk surface:
the v37 rebuild (10 explicit columns both sides, self-FK rewritten by RENAME, FK
enforcement ON after `ensure_schema` confirmed empirically, rebuild-firing tests use a
genuine `source_principal`-less table — no false-pass, chain-preservation proves the FK
live); the external store (Fernet-at-rest, secret-free projections, `source_id` FK
cascade firing, registry eviction); the field-scoped CAS (whitelist-guarded, atomic
single-column, other-field non-clobber proven, truthful stale result, saved-before-logged
preserved); provenance threaded through all writers + model round-trip; DD6 governance
403s. **Cross-leg (key concern): correct** — `_resolve_caller_and_agent` carries the
external routing AND the DD9 refusal for both read and write tools by construction.
UI/anonymization clean. Non-blocking: (1) Leg 3 leg-file checklist boxes unchecked
[resolved at flight-end commit when legs → completed]; (2) CAS whitelist uses `assert`
(not exploitable; `ValueError` more robust) [fixing]; (3) DD9 orphaned refusal tested via
read tool only (covered by construction) [leaving]; (4) SECURITY-MODEL.md/agents.md docs
deferred [doing the doc pass now]; (5) minor rotate load redundancy [leaving]; (6)
save-failure test renamed [fine].

**Accessibility Reviewer — [HANDOFF:confirmed], no blocking, 5 non-blocking.** Fixing 3
genuine SR gaps in the sensitive copy-once/revoke flow: (1) Revoke's armed-confirm state
not conveyed because an `aria-label` overrides the swapped visible text (WCAG 4.1.2);
(2) the "shown once" warning not `aria-describedby`-associated with the copy button
(1.3.1); (3) error-path focus loss on rotate/revoke rebuild (2.4.3). Leaving #4 (list
`role="group"` — at-bar/consistent with the tab's existing idiom) and #5 (shared
`.banner-warning` alpha vs the token gate — pre-existing shared component, not this leg).

**Dispatching one Developer** for the 3 a11y fixes + the CAS `assert`→`ValueError`
hardening + the deferred doc pass, then the flight-end commit.
