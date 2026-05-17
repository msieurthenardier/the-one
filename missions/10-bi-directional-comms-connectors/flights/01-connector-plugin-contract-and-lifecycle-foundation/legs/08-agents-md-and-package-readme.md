# Leg: agents-md-and-package-readme

**Status**: landed
**Flight**: [Connector Plugin Contract and Lifecycle Foundation](../flight.md)

## Objective

Document the connector subsystem in `the_one/agents.md` (parallel to the provider-type extension checklist) and in a new `the_one/connectors/README.md` (parallel to `the_one/mcp/README.md`). Capture: the connector-type six-layer coordination checklist, subsystem decisions and invariants from this flight, the Known Issues that future flights must respect, and the package-level entry-point reference. Pure documentation leg — no code changes, no new tests.

## Context

This is leg 8 (final) of Flight 1 of Mission 10. Legs 1-7 landed the persistence floor, the protocol contract, the registry, the lifecycle pool, and the end-to-end regression baseline. This leg writes the documentation that makes the subsystem maintainable — without it, the next operator or contributor to touch the connector code has no anchored entry point, no checklist for adding a new connector type, and no way to discover the design decisions that shaped what they're modifying.

### What "documentation" means here

Two artifacts:

1. **`the_one/agents.md`** — append a new section after the provider-type extension checklist (currently the last subsystem-extension content in the file). Documents:
   - The **connector-type six-layer coordination checklist** parallel to the provider-type one at `agents.md:251-267`
   - The **Connector subsystem decisions-and-invariants** section (the equivalent of the implicit-but-not-explicit invariants the MCP code maintains)
   - A **Known Issues** subsection capturing technical debt deliberately deferred during Flight 1

2. **`the_one/connectors/README.md`** — new file paralleling `the_one/mcp/README.md`. Documents:
   - Subsystem layout (what's in `connectors/`)
   - The four-Protocol decomposition note (Plugin now; AllowlistResolver and CommandHandler additive in Flights 6-7)
   - Public API entry points (`acquire`, `shutdown_drain`) and where the test seams live
   - The "stub plugin is private" stance and where to import it for tests

### Six-layer checklist mirroring strategy

The provider-type checklist at `agents.md:251-267` enumerates Pydantic `Literal`, `_PROVIDER_TYPE_MAP`, registry loaders, SQLite `CHECK` constraint, API gating, frontend tokens, and an optional state-hook. The connector parallel has analogous-but-not-identical layers — Flight 1 deliberately deferred several of them:

| # | Layer | Provider equivalent | Connector status after Flight 1 |
|---|---|---|---|
| 1 | Pydantic `Literal` | `LLMProviderConfig.type` | `ConnectorAccount.type` is `str` (unconstrained); narrowed by Flight 8 |
| 2 | Type → dispatch map | `_PROVIDER_TYPE_MAP` | `ConnectorRegistry` + `register_builtin_connectors()` |
| 3 | Lazy/eager loader | `_try_load_builtin` | Eager registration via `register_builtin_connectors()` body |
| 4 | SQLite `CHECK` | `llm_providers.type CHECK(...)` | NO CHECK in v13/v14; added by Flight 8 v15 via table-rename |
| 5 | API gating | `interfaces/web/api.py` create/update/test branches | Flight 2 lands the admin REST routes |
| 6 | Frontend | `interfaces/web/static/js/areas/admin.js` | Flight 2 lands the Studio attach + Admin connector pages |
| 7 (opt) | State hook | `_init_provider_state` | Not yet needed for connectors; revisit per real plugin |

The checklist documents what a future "add Discord" or "add Slack" coordinator must touch. Flight 8's Discord work IS this checklist's first real test.

### Decisions and invariants

The "Connector subsystem" section captures what's encoded in the code but not visible from reading the code alone:

- **Typed-exception hierarchy** — 6 producer-side types in `connectors/errors.py`; mirrors the MCP precedent of 10 producer-side types collapsed into 4 consumer-side match categories. The "grow deliberately" stance.
- **Worker-task-per-entry pattern** — the connect-and-disconnect-on-same-task contract that satisfies anyio's cross-task `CancelScope.__aexit__` guard. Inherited from MCP precedent.
- **Parallel-pool-not-shared decision** — connectors get a fresh `_pool.py` rather than extracting a shared pool primitive with MCP. The extraction trigger: a **third network-keyed pool** (PTY excluded — it's process-lifecycle-keyed, structurally different).
- **Per-Protocol structural-satisfaction discipline** — `ConnectorPlugin` is the only Protocol in Flight 1. Flights 6 and 7 add `AllowlistResolver` and `CommandHandler` as separate Protocols in the same `connectors/base.py`. Real connectors structurally satisfy each Protocol they claim; integration tests assert via `isinstance(conn, AllowlistResolver)` etc.
- **Encryption-rotation invariant** — `POST /api/encryption/rotate` now covers three corpora in one atomic commit: `llm_providers.api_key`, `mcp_sources.secrets`, `connector_accounts.secrets`. Failure in any branch rolls back all three.

### Known Issues

Two carry-forward items into future flights:

1. **Deferred shared-pool extraction** — `connectors/_pool.py` duplicates ~300 LoC of structural lifecycle machinery from `mcp/_pool.py`. M07's `_shutting_down` test-isolation debt remains in MCP; connector pool ships with the fix from day one. If a third network-keyed pool emerges (e.g. a future "external workers" subsystem), extraction becomes mandatory rather than optional.
2. **Flight 3 ratification needed for `last_activity` tracking** — `_RegistryEntry.last_activity` is updated by `acquire()` on every call (warm and cold). This is "time since last `acquire()`", not "time since last platform activity." The reaper consumes it. Flight 3's inbound message dispatcher MUST call `acquire()` per inbound message for the metric to track "time since the connector was used to handle anything"; if Flight 3 uses a non-acquire-touching lookup mechanism, the reaper will prematurely evict actively-used gateway connections. Flight 3 design must either ratify (use `acquire`) or amend (add a separate touch mechanism).

### Mirror MCP's README structure

The connectors README mirrors `the_one/mcp/README.md` at the structural level. MCP's README has numbered sections (`§1. Test-seam pattern`, `§2. F4-pool-compat invariants`, etc.). Connector README sections will be similar but with content appropriate to the smaller current surface.

## Inputs

What exists before this leg runs:

- Legs 1-7 landed (uncommitted on the feature branch)
- `the_one/agents.md` exists; provider-type checklist is at L251-267
- `the_one/mcp/README.md` exists — the structural template for the new connectors README
- `the_one/connectors/` package has 6 files: `__init__.py`, `base.py`, `errors.py`, `registry.py`, `_pool.py`, `_stub.py`
- All design decisions from the flight artifact and execution surprises from the flight log are available to lift into the agents.md decisions section

## Outputs

What exists after this leg completes:

- Updated `the_one/agents.md`:
  - New "Connector type extension checklist" subsection appended after the existing "Provider type extension checklist" (around current L268)
  - New "Connector subsystem" decisions-and-invariants section after the connector-type checklist
  - New "Known Issues" subsection within the Connector subsystem section
- New file `the_one/connectors/README.md` — structurally analogous to `the_one/mcp/README.md`
- Updated `the_one/connectors/__init__.py` module docstring if needed (small touch to reference the new README; optional)
- `make lint` clean (pure docs change; tests unchanged)
- Leg status `landed`
- Flight log gains `### Leg 08: agents-md-and-package-readme` entry

## Acceptance Criteria

- [ ] `the_one/agents.md` gains a "Connector type extension checklist" section parallel in structure to the provider-type checklist at L251-267. The new section enumerates the layers a future connector author must touch, marks which are deferred to which flight (per the table in Context above), and references the relevant code paths by symbol (e.g. `connectors/registry.py:register_builtin_connectors`).
- [ ] `the_one/agents.md` gains a "Connector subsystem" decisions-and-invariants section. Documents:
    - Typed-exception hierarchy — 6 producer types in `connectors/errors.py`; "grow deliberately" stance
    - Worker-task-per-entry pattern — connect-and-disconnect-on-same-task contract; references `connectors/_pool.py:_entry_worker`
    - Parallel-pool-not-shared decision — explicit third-network-keyed-pool extraction trigger; PTY exclusion rationale
    - Per-Protocol structural-satisfaction discipline — Plugin now, AllowlistResolver + CommandHandler additive in flights 6-7
    - Encryption-rotation invariant — three corpora now atomic in `rotate_encryption_key`
- [ ] `the_one/agents.md` gains a "Known Issues" subsection (within the Connector subsystem section) with at least two entries:
    - Deferred shared-pool extraction (deferred trigger: third network-keyed pool)
    - Flight 3 acquire-per-inbound ratification needed for `last_activity` tracking
- [ ] `the_one/connectors/README.md` exists as a package-level reference doc, structurally analogous to `the_one/mcp/README.md`. Includes:
    - Top-of-file orientation paragraph (what's in `connectors/`, who reads this, what to read first)
    - Package layout — list of files with one-line descriptions
    - Four-Protocol decomposition note: `ConnectorPlugin` ships in Flight 1; `AllowlistResolver` and `CommandHandler` will land additively in Flights 6 and 7 as separate Protocols in `base.py`
    - Public API entry points: `acquire`, `shutdown_drain` (with one-line descriptions)
    - Test-side seams: `register_for_test`, `clear_for_test`, `restore_to_baseline_for_test`, `_clear_for_test` (pool); the `_stub.py` import path for tests that need the rich stub
    - Pointer back to `the_one/agents.md`'s Connector subsystem section for the full decisions / invariants / known-issues
- [ ] Both files are markdown-clean (no broken internal links, no orphan headings). Manual visual inspection or `markdownlint` if available.
- [ ] Existing tests still pass (no test changes; this leg is documentation-only)
- [ ] `make lint` clean for the whole suite
- [ ] Leg status `landed`
- [ ] `agents-md-and-package-readme` checkbox checked in flight.md's Legs section
- [ ] Flight log has `### Leg 08: agents-md-and-package-readme` entry under `## Leg Progress`
- [ ] **Flight checkbox**: leg 8 is the LAST leg — after this leg lands, the flight artifact's status should be set to `landed` (NOT `completed`) per the agentic-workflow protocol; the final commit and PR happen via the orchestrator's batch-review step, not this leg

## Verification Steps

1. **agents.md additions**:
   - `grep -n "Connector type extension checklist" the_one/agents.md` returns one match
   - `grep -n "Connector subsystem" the_one/agents.md` returns one match
   - `grep -n "Known Issues" the_one/agents.md` returns one match (or more if the existing file already had one)
   - Read the new sections end-to-end — content matches the structure documented in Acceptance Criteria

2. **connectors/README.md exists**:
   - `docker exec the-one ls the_one/connectors/README.md` returns a match
   - `wc -l the_one/connectors/README.md` returns a non-trivial line count (>30 lines)
   - File starts with a top-level heading (`# Connector runtime invariants` or similar)

3. **Internal references resolve**:
   - The agents.md "Connector subsystem" section references `connectors/_pool.py:_entry_worker` etc. — verify these symbols exist in the current code
   - The connectors README references the agents.md section by name — verify the agents.md section name is exact

4. **No code regression**:
   - `docker exec the-one pytest -x --timeout 30` clean (no test changes expected)
   - `make lint` clean

## Implementation Guidance

### Step 1: Append the "Connector type extension checklist" section to `the_one/agents.md`

Insert AFTER the existing "Provider type extension checklist" section (currently ends around L268) and BEFORE the next major section (currently "Streaming protocol" at L270). Use the same heading depth (`##` for the section, `###` for subsections within it).

The content structure should mirror the provider-type checklist:

```markdown
---

## Connector type extension checklist

Parallel to the provider-type extension checklist above. When a future
flight adds a new connector type (Flight 8 — `'discord'`; Flight 9 — the
second connector), coordinate across the following layers. Flight 1 ships
the contract scaffolding; the layers below names which flight owns each.

### Checklist

1. **Pydantic `Literal`** — `db/models.py` `ConnectorAccount.type`. Currently
   `str` (unconstrained); Flight 8 narrows to `Literal["discord"]` and adds
   the `assert set(get_args(...)) == set(CONNECTOR_TYPES)` pin alongside
   `LLMProviderConfig`'s assert.
2. **`CONNECTOR_TYPES` tuple** — `db/_connector_types.py`. Empty in
   Flight 1; Flight 8 adds `"discord"`. The tuple is the canonical
   single-source-of-truth pinned to layers 1, 3, and 4.
3. **Registry registration** — `connectors/registry.py:register_builtin_connectors`.
   Empty body in Flight 1; Flight 8 changes to call
   `register("discord", DiscordPlugin)`. Layer 2 (`CONNECTOR_TYPES`) and
   layer 3 must agree.
4. **SQLite `CHECK` constraint** — `db/schema.py` v15 migration adds the
   CHECK via the table-rename ceremony established in v6/v12. Flight 8
   lands v15 (the original "v14 CHECK" plan was renumbered after leg 2's
   v14 name-column addition).
5. **API gating / branches** — `interfaces/web/api.py`: `/api/connector-accounts/*`
   create/update/delete/test branches. Flight 2 lands the admin REST routes.
6. **Frontend** — `interfaces/web/static/js/areas/admin.js`: connector-type
   defaults, badge styles in `tokens.css` + `admin.css`. Flight 2 lands the
   Admin/Studio surfaces.
7. **`_init_*` state hook** *(optional)* — if a future plugin needs to
   capture configuration outside the base field set, expose a hook similar
   to `_init_provider_state`. Not needed in Flight 1's stub.
```

(Implementing agent: adjust the exact wording to match the prose style of the existing provider-type section. Verbatim mirroring is unnecessary; consistency in tone and structure is.)

### Step 2: Add the "Connector subsystem" section to `the_one/agents.md`

Immediately after the checklist. Five subsections documenting decisions and invariants, plus a Known Issues subsection.

```markdown
---

## Connector subsystem

Decisions, invariants, and known issues encoded by Mission 10 Flight 1. The
code in `the_one/connectors/` implements them; this section is the
human-readable index for maintainers.

### Typed-exception hierarchy

`connectors/errors.py` defines 6 producer-side types:
`ConnectorClientError` (base) → `ConnectorConfigError`,
`ConnectorConnectionError`, `ConnectorAuthRequired`,
`ConnectorRegistrationError`, `ConnectorRateLimitError`.

Mirrors MCP's pattern in shape (MCP's `mcp/errors.py` has 10 producer-side
types collapsing into 4 consumer-side match categories). Connectors start
smaller; grow deliberately when a real connector reveals a distinct error
mode that doesn't fit any existing type.

### Worker-task-per-entry pattern

`connectors/_pool.py:_entry_worker` holds the platform connection on a
single asyncio task. Connect AND disconnect run on the same task,
satisfying anyio's cross-task `CancelScope.__aexit__` guard. The eviction
path signals via `evict_event` rather than cancelling the worker — the
worker's `finally:` clause runs `plugin.disconnect(client)` on the same
task. Mirrors `mcp/_pool.py:_entry_worker`.

### Parallel-pool-not-shared decision

`connectors/_pool.py` is a fresh implementation, not a refactor of
`mcp/_pool.py` into a shared primitive. ~300 LoC of structural duplication
accepted because the alternative (extracting a generic `AsyncConnectionPool`
and retrofitting MCP) is a cross-cutting refactor that doesn't belong in a
foundation flight.

**Extraction trigger**: a **third network-keyed pool**. The existing PTY
pool at `tools/_session_registry.py` is NOT counted toward this trigger —
it is process-lifecycle-keyed (a pty either has a child process or doesn't)
with no warm-connection keep-alive / heartbeat / reconnect lifecycle. PTY,
MCP, and Connector pools share the per-entry-worker hygiene pattern
superficially but diverge structurally on what an "entry" represents and
what eviction means; that divergence is what makes a generic extraction
speculative until two true network-keyed peers exist.

### Per-Protocol structural-satisfaction discipline

`connectors/base.py` declares Protocols, plural. Flight 1 ships
`ConnectorPlugin` (4 methods) and `ConnectorClient` (1 method). Flights 6
and 7 will land **additional Protocols in the same file**:

- `AllowlistResolver` (Flight 6) — per-(agent, peer) and per-(agent,
  group/channel) ACL resolution
- `CommandHandler` (Flight 7) — platform-side command surface
  (`/agents`, `/talk-to`, `/whoami`, `/reset`, `/new`, `/help`)

A connector that supports allowlists structurally satisfies BOTH
`ConnectorPlugin` AND `AllowlistResolver`. Per-platform integration tests
(Flight 8 Discord, Flight 9 second connector) assert each Protocol the
connector claims via `isinstance(conn, ProtocolType)`. "Single contract
file" is the mission criterion; multiple Protocols in one file satisfy it.

### Encryption-rotation invariant (three corpora)

`POST /api/encryption/rotate` re-encrypts ALL credential ciphertexts in a
single atomic transaction. As of Mission 10 Flight 1 the rotation covers:

1. `llm_providers.api_key` (Mission 03)
2. `mcp_sources.secrets` (Mission 07)
3. `connector_accounts.secrets` (this mission)

A failure in any of the three UPDATE loops rolls back all three. The
single `commit()` in `interfaces/web/api.py:rotate_encryption_key` is the
authoritative commit point; the on-disk key file is replaced atomically via
`os.replace` only AFTER the DB commit succeeds.

### Known Issues

Carry-forward items future flights must respect or close:

- **Deferred shared-pool extraction**. `connectors/_pool.py` duplicates
  ~300 LoC of structural lifecycle machinery from `mcp/_pool.py`. M07's
  `_shutting_down` test-isolation debt remains in MCP; the connector pool
  ships with the fix from day one. Extraction trigger: a third
  network-keyed pool (see Parallel-pool-not-shared decision above for the
  PTY-exclusion rationale).

- **Flight 3 ratification needed for `last_activity` tracking**.
  `_RegistryEntry.last_activity` is updated by `acquire()` on every call
  (warm and cold). The reaper consumes it. This measures "time since last
  `acquire()`", not "time since last platform activity." Flight 3's
  inbound message dispatcher MUST call `acquire()` per inbound message for
  the metric to track "time since the connector was used to handle
  anything"; if Flight 3 uses a non-acquire-touching lookup mechanism, the
  reaper will prematurely evict actively-used gateway connections.
  Flight 3 design must either ratify (use `acquire` per inbound) or amend
  (add a separate touch mechanism on `_RegistryEntry`).
```

### Step 3: Create `the_one/connectors/README.md`

Mirror the structural shape of `the_one/mcp/README.md`. Open with the runtime-invariants-orientation paragraph + a pointer back to `agents.md` for project-wide conventions and the Connector subsystem decisions section.

```markdown
# Connector runtime invariants

This document is the package-level entry point for `the_one/connectors/`.
It captures the runtime invariants Flight 1 of Mission 10 establishes.
Read this BEFORE modifying anything in the package — many of the invariants
below are load-bearing for tests AND for the operator's mental model of
how connectors connect, dispatch inbound, and reap.

For project-wide conventions (`trust-the-runtime`,
`canonical-import + convenience-re-export`,
`structural-Protocol-satisfaction`, `verbatim-message-equality`,
`container-test-entrypoints-reach-via-make`), see `the_one/agents.md`'s
"Project Conventions" section.

For the connector-type extension checklist and the Connector subsystem
decisions / invariants / known issues, see `the_one/agents.md`'s
"Connector type extension checklist" and "Connector subsystem" sections.

## §1. Package layout

```
the_one/connectors/
├── __init__.py        # Public surface re-exports; canonical-import discipline note
├── base.py            # ConnectorPlugin Protocol + supporting types; future
│                      # AllowlistResolver (Flight 6) + CommandHandler (Flight 7)
├── errors.py          # 6-type exception hierarchy
├── registry.py        # ConnectorRegistry class + module-level singleton
├── _pool.py           # per-(agent, account) lifecycle pool (private)
└── _stub.py           # In-process test fixture (private; never registered)
```

## §2. Public API entry points

Production code interacts with the subsystem via two functions:

- `acquire(agent_name, account_id) -> ConnectorClient` — look up or spawn
  the warm client for `(agent, account)`. Cycle-2 race-safe; concurrent
  same-key acquires share one worker.
- `shutdown_drain() -> None` — cancel the reaper task and drain every
  warm entry. Wired into `interfaces/web/app.py:lifespan` between the MCP
  pool drain and the OAuth periodic-sweep stop.

Both are at `the_one.connectors._pool`. The pool is package-private
(`_pool.py`); higher-level entry points may be re-exported from
`__init__.py` by future flights.

## §3. Protocol decomposition

`base.py` houses multiple Protocols. Flight 1 ships:

- `ConnectorPlugin` — `connect`, `disconnect`, `doctor`,
  `normalize_session_key` (4 methods)
- `ConnectorClient` — `is_alive` (1 method)

Future flights add:

- `AllowlistResolver` (Flight 6) — for ACL-aware connectors
- `CommandHandler` (Flight 7) — for connectors that handle platform-side
  commands

Connectors structurally satisfy each Protocol they claim (per
`structural-Protocol-satisfaction` convention). Real connectors —
Discord (Flight 8), the second connector (Flight 9) — will likely
satisfy all four Protocols.

## §4. Test seams

- `registry.register_for_test(type_name, plugin_class)` — bypass the
  collision check; for tests that swap plugins
- `registry.clear_for_test()` — empty the registry (hard clear; does NOT
  re-run `register_builtin_connectors`)
- `registry.restore_to_baseline_for_test()` — empty then re-run the
  builtin discovery hook; restores the production-shaped baseline
- `_pool._clear_for_test()` — cancel reaper, empty pool, reset
  `_shutting_down`. Use in an autouse fixture
- `_stub.StubPlugin` / `_stub.StubClient` — rich in-process stub with
  recording buffers and scenario knobs. Import directly:
  `from the_one.connectors._stub import StubPlugin, StubClient`. NOT
  registered via `register_builtin_connectors`; tests register it via
  `register_for_test("stub", StubPlugin)`.

## §5. The 'stub' type name

Reserved for tests. Production code MUST NOT register `'stub'` via
`register_builtin_connectors`. The schema (v13/v14) has no CHECK
constraint on `connector_accounts.type`, so storing `'stub'`-typed rows
in tests works at the persistence layer without polluting the production
type registry. Flight 8's v15 migration adds the CHECK constraint when
`'discord'` becomes a real type to constrain — at that point `'stub'`
will need to be explicitly included in the CHECK or the test-side
seeding will fail. Future flights touching the CHECK MUST coordinate
with this README.

## §6. Encryption envelope

`connector_accounts.secrets` is a JSON-encoded dict encrypted via
Fernet-symmetric using the system-wide encryptor
(`get_encryptor(settings.data_dir)`). `ConnectorAccountRepository` holds
the encryptor as a **reference, not copy** — post-rotation
`install_key()` propagates to live repository instances. The repository's
`_secrets_to_ciphertext` / `_ciphertext_to_secrets` envelope mirrors
`MCPSourceRepository` exactly.

`_ciphertext_to_secrets` swallows `InvalidToken` and returns `{}` (the
"migration residue" case) but propagates `JSONDecodeError` (the "real
corruption" case). Same shape as MCP.

## §7. Rotation invariant

`POST /api/encryption/rotate` re-encrypts three corpora atomically:
`llm_providers.api_key`, `mcp_sources.secrets`, `connector_accounts.secrets`.
A failure in any UPDATE branch rolls back all three. See
`agents.md`'s "Connector subsystem → Encryption-rotation invariant" for
details.
```

### Step 4: Optional touch to `the_one/connectors/__init__.py`

If the existing `__init__.py` docstring doesn't already point to `README.md`, add one sentence near the bottom of the existing docstring:

```python
"""...

For package-level runtime invariants (pool, registry, encryption envelope),
see :doc:`the_one/connectors/README.md`. For project-wide conventions and
the Connector subsystem decisions, see :doc:`the_one/agents.md`.
"""
```

Skip if the docstring is already complete.

### Step 5: Verify + update artifacts

- `docker exec the-one pytest -x --timeout 30` — verify no regression (no code changed; should be a no-op pass)
- `make lint` — clean
- Append `### Leg 08: agents-md-and-package-readme` to flight-log.md under `## Leg Progress`
- Check off `agents-md-and-package-readme` in flight.md's Legs section
- Set this leg's status to `landed`
- Signal `[HANDOFF:review-needed]`; do NOT commit. The agentic-workflow batch reviewer runs after this leg.

### Step 6: Flight checkbox flip

This is the LAST leg of the flight. After signaling `[HANDOFF:review-needed]`, the agentic-workflow orchestrator will spawn the Reviewer agent across all uncommitted changes, then trigger the single end-of-flight commit. The Reviewer's role includes checking that the flight artifact's status is set to `landed` (and ticking the flight in mission.md) — this leg's implementation does NOT need to flip the flight status; that's the orchestrator + Reviewer + commit-agent's job per the agentic-workflow protocol.

## Edge Cases

- **agents.md section ordering** — the new content goes after the existing Provider type extension checklist. If a future merge inserts other sections between the two checklists, the connector-type checklist's "parallel to the provider-type checklist above" pointer becomes weaker. Documented as expected drift; future maintenance flights can re-order.
- **README markdown links** — internal links like `the_one/agents.md`'s "Connector subsystem" reference the section by name, not by ID. If the section name changes, the link in `connectors/README.md` rots. Manual care.
- **`__init__.py` docstring optional touch** — the connectors/__init__.py already references canonical-import discipline; adding the README pointer is purely additive and may not be needed if the docstring is already long. The implementing agent should judge.
- **No test changes** — this leg is documentation-only. The flight log's leg-8 entry should note "no code changes; documentation only" so future readers searching for "leg 8 implementation" find the doc artifacts immediately.
- **Code-symbol references in agents.md** — the new section references `connectors/_pool.py:_entry_worker` etc. These symbols exist as of leg 7. If any subsequent flight renames them, the agents.md references rot. Mitigation: use the symbol form (file:symbol) rather than file:line, so renames surface as undefined references rather than silent line drift.

## Files Affected

- `the_one/agents.md` — new "Connector type extension checklist" section + "Connector subsystem" section with five subsections (including Known Issues)
- `the_one/connectors/README.md` (NEW) — package-level reference doc
- `the_one/connectors/__init__.py` — optional one-sentence pointer to README (no functional change)
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` — check off `agents-md-and-package-readme`
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight-log.md` — append `### Leg 08` entry
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/legs/08-agents-md-and-package-readme.md` (this file) — status to `landed`

**NOT affected**:
- Any source code in `the_one/connectors/` — leg 8 is documentation-only
- Any test file — leg 8 is documentation-only
- The flight artifact's status — agentic-workflow orchestrator handles the flight-level transition after the batch review

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] All listed tests passing (no test changes; should be a pass-through)
- [ ] `make lint` clean
- [ ] Flight log + flight artifact updated
- [ ] Leg status `landed`
- [ ] `[HANDOFF:review-needed]`; do NOT commit

---

## Citation Audit

6 citations verified against current code at leg design time:

| Citation | Verification |
|---|---|
| `the_one/agents.md:251-267` Provider type extension checklist | OK — content matches the structural template this leg mirrors |
| `the_one/mcp/README.md` package-level reference doc | OK — read structural shape |
| `the_one/connectors/_pool.py:_entry_worker` (leg 5+6) | OK — symbol exists, single-task connect/disconnect pattern |
| `the_one/connectors/errors.py` 6-type hierarchy (leg 3) | OK — landed in leg 3 |
| `the_one/connectors/base.py` Protocols + types (leg 3) | OK — landed in leg 3 |
| `the_one/interfaces/web/api.py:rotate_encryption_key` (legs 1, 6) | OK — three-corpora rotation in atomic commit |
