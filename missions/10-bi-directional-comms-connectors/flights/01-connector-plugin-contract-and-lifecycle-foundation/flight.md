# Flight: Connector Plugin Contract and Lifecycle Foundation

**Status**: ready
**Mission**: [Bi-directional Communication Connectors](../../mission.md)

## Contributing to Criteria

This flight does not satisfy any mission criterion on its own — it lays the foundation every subsequent flight builds on. It establishes the seams that the remaining criteria are validated against:

- [ ] *(advances)* "At least two connector implementations ship in this mission, both built against a single connector-plugin contract that is the only file any future connector author needs to satisfy" — this flight ships **the contract** and a no-op reference implementation
- [ ] *(advances)* "Per-connector-account override of credentials is supported through the same resolver pattern the built-in tools and MCP sources use today" — this flight builds the **persistence + encryption envelope** layer the resolver attaches to
- [ ] *(advances)* "Credentials never appear in plaintext outside the encryption boundary" — this flight integrates `connector_accounts.secrets` into the **single-transaction Fernet rotation** that already covers LLM providers and MCP sources
- [ ] *(advances)* "Persistent connections are managed by a per-(agent, connector-account) lifecycle pool with idle-TTL reaping and transparent respawn on next use, integrated into the FastAPI lifespan" — this flight builds **the pool**
- [ ] *(advances)* "Failures isolated to the connector layer ... do not take the chat session down" — this flight defines the **typed exception hierarchy** that translates platform errors into failure-isolation envelopes
- [ ] *(advances)* "Each layer of the integration has automated coverage proving its contract" — this flight ships the **stub-driven end-to-end test** that subsequent flights inherit as their regression baseline

---

## Pre-Flight

### Objective

Stand up the connectors subsystem as a peer to `the_one/mcp/` and `the_one/tools/` — the directory, the `ConnectorPlugin` protocol, the typed exception hierarchy, the `connector_accounts` schema with encrypted credentials integrated into the existing rotation transaction, the `ConnectorAccount` Pydantic model and repository mirroring the MCP source pattern, the per-(agent, account) lifecycle pool with worker-task-per-entry, idle-TTL reaping, and FastAPI lifespan integration, and the type registry through which the rest of the system addresses connectors by name. Ship a no-op stub plugin that exercises every method on the protocol so the regression net is in place before any platform-specific code lands. Document the connector-type six-layer coordination checklist in `agents.md` parallel to the existing provider-type checklist. **No platform code, no admin UI, no agent-attach wiring** — those land in Flights 2–10. The single artifact this flight produces is the SDK on which everything subsequent depends.

### Open Questions

- [x] **Pool reuse vs. parallel implementation** — resolved in Design Decisions (parallel implementation with M07's test-isolation lesson applied from the start; mcp/_pool.py debt deferred to a future refactor flight, not paid down here; PTY pool excluded from the extract-if-third-pool trigger because it is process-lifecycle-keyed, not network-keyed)
- [x] **Stub plugin placement** — resolved in Design Decisions (`connectors/_stub.py` with underscore prefix, registered only via test-side injection; mirrors the `mock` LLM provider pattern; no env-var test-mode seam in production code paths; v13 schema has no CHECK constraint so the stub does not need to appear as a production-known type)
- [x] **Idle TTL default** — resolved in Design Decisions (1800 s / 30 min, overridable via `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS`)
- [x] **Connector-account ↔ agent cardinality** — resolved in Design Decisions (many-to-many: connector accounts are global identities; per-agent attachment via `AgentConfig.connector_account_ids` lands in **Flight 4**, not Flight 1)
- [x] **Session-metadata column on `chat_sessions`** — Flight 3 owns the schema migration that adds it; this flight introduces only `connector_accounts`. Architect-recommended piggyback on Flight 3's migration.
- [x] **`ConnectorPlugin` Protocol surface** — resolved in Design Decisions: 4 methods (`connect`, `disconnect`, `doctor`, `normalize_session_key`). Allowlist resolution and command-surface handling land as separate Protocols in `connectors/base.py` when Flights 6 and 7 need them.
- [x] **`merged_config()` helper** — deferred; Flight 6 decides the composition surface when per-agent overrides are wired.
- [ ] **Final method signatures on the `ConnectorPlugin` Protocol** — finalized at leg planning for the `protocol-and-errors` leg; the 4 methods are decided but the exact argument types (e.g. does `connect` take the full `ConnectorAccount` or a decrypted-credentials view?) land then.
- [ ] **Whether the stub plugin's doctor-probe returns success or a configurable success/failure response** — leg 7 decides; preference is a configurable response so failure paths can be tested end-to-end without platform mocks.

### Design Decisions

**Parallel pool implementation, not shared extraction**

- **Choice**: Build `the_one/connectors/_pool.py` as a fresh implementation, copying the worker-task-per-entry pattern from `the_one/mcp/_pool.py` but not sharing code. Apply M07's test-isolation lesson (proper `_shutting_down` reset on every `_clear_for_test` and clean shutdown) from leg 1 of pool work, so the connector pool ships without the debt M07's pool carries.
- **Rationale**: Flight 1 is foundational and already substantial. Extracting a shared `AsyncConnectionPool[T, K]` generic and refactoring the production-load-bearing MCP pool to use it is a cross-cutting refactor that doesn't belong inside a foundation flight. The M07 debrief explicitly framed the test-isolation debt as "cross-cutting refactor, deferred to follow-up architectural flight" — that framing still holds. The connector pool gets the fix from the start; mcp/_pool.py's debt remains.
- **Trade-off**: ~250–350 LoC of structural duplication between `connectors/_pool.py` and `mcp/_pool.py`. Acceptable for now; the commitment is that **if a third network-keyed pool ever emerges** (i.e. a third subsystem that holds warm network/protocol connections keyed by (agent, source) tuples), extraction becomes mandatory rather than optional. The existing PTY session registry at `the_one/tools/_session_registry.py` is **not** counted toward this trigger — it is process-lifecycle-keyed (a pty either has a child process or doesn't), with no "warm-connection-keep-alive" semantic and no heartbeat / reconnect lifecycle. PTY, MCP, and Connector pools share the "per-entry worker task" hygiene pattern superficially but diverge structurally on what an "entry" represents and what eviction means; that divergence is what makes a generic extraction speculative until we see two true network-keyed peers. Documented in the new Known Issues section of `agents.md` along with the connector-type checklist.

**Stub plugin lives at `the_one/connectors/_stub.py` with underscore prefix**

- **Choice**: In-process plugin implementing the full `ConnectorPlugin` protocol with no network I/O. Registered into the type registry only via a test-side injection hook (`register_for_test(stub_plugin)`), not via the production discovery path. Not loaded at startup.
- **Rationale**: Mirrors the `mock` LLM provider pattern. Honors the project convention that test seams are code-side stubs and dependency injection, never env-var runtime branching. The stub is a fixture, not a production type — the type registry's production codepath does not see it.
- **Trade-off**: Stub is private API (underscore prefix). Tests in other flights import it explicitly; that's the only consumer. No public re-export from `connectors/__init__.py`.

**Idle TTL default 1800 s (30 min); env override `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS`**

- **Choice**: Default 30 minutes, configurable. MCP's `MCP_POOL_IDLE_TTL_SECONDS` defaults to 300 s (5 min); the connector default is longer because persistent gateway connections (Discord, Slack Socket Mode) have meaningful reconnect cost and operators reasonably expect minutes-long gaps in conversation.
- **Rationale**: 5 minutes would churn a Discord gateway on every coffee break. 30 minutes balances "keep the connection warm during a normal multi-message thread" against "don't hold a connection open for hours on idle." Flight 9 (Slack) and Flight 8 (Discord) can revisit if real-world feel disagrees.
- **Trade-off**: A 30-minute idle TTL means a connector account that's been silent for 35 minutes pays the reconnect cost on the next inbound. Acceptable.

**Connector accounts are global; agents attach via `AgentConfig.connector_account_ids`**

- **Choice**: `connector_accounts` table has no `agent_id` column. The attachment relation lives on `AgentConfig` as `connector_account_ids: list[str]` mirroring `AgentConfig.mcp_source_ids`. Many-to-many: one account → many agents; one agent → many accounts.
- **Rationale**: Mirrors MCP. The operator registers a Discord bot identity once; multiple agents can attach to it. The alternative (account-owned-by-agent) would force the operator to re-paste the bot token for each agent — exactly the anti-pattern the M07 attach surface was designed to eliminate.
- **Trade-off**: Per-agent credential override (a mission criterion) is handled at the agent-config layer through the two-layer resolver pattern, not via account duplication. Flight 1 establishes the shape; Flight 6/7 wire ACLs on top.

**Schema version increments from 12 to 13; no CHECK constraint on `type` in v13**

- **Choice**: New v13 migration adds `connector_accounts` (id, type, config JSON, secrets JSON, created_at, updated_at) with **no CHECK constraint on `type`**. Mirror the existing `the_one/db/_provider_types.py` pattern: introduce `the_one/db/_connector_types.py` exporting `CONNECTOR_TYPES: tuple[str, ...] = ()` (empty in Flight 1), pinned to the Pydantic `Literal[...]` on `ConnectorAccount.type` via the same `assert set(get_args(...)) == set(CONNECTOR_TYPES)` invariant used in `db/models.py`. The first real connector (Flight 8 — Discord) adds `'discord'` to the tuple AND lands a v14 migration that introduces the CHECK constraint via table-rename ceremony when there's an actual type to constrain.
- **Rationale**: Two reasons. (1) The stub plugin is test-only — it satisfies the Protocol structurally but should never appear as a production-known type. Baking `'stub'` into a production CHECK constraint contradicts that stance and forces tests to either coexist with a production-known stub or work around the constraint. (2) Deferring the CHECK saves a v13 migration churn for zero immediate value (no real types yet to constrain). When Flight 8 introduces the first real type, the table-rename ceremony adds the CHECK with a meaningful constraint set, not a placeholder. Architect's review verified the `_provider_types.py` mirror is the right pattern.
- **Trade-off**: v13 → v14 will need a table-rename ceremony in Flight 8 to add the CHECK retroactively. Cost is one extra migration; benefit is no production-baked `'stub'` literal. Acceptable.

**Typed exception hierarchy: 6 types initially**

- **Choice**: `ConnectorClientError` (base) + `ConnectorConfigError` (invalid config / missing credentials) + `ConnectorConnectionError` (transport / network / handshake) + `ConnectorAuthRequired` (control-flow signal for re-auth) + `ConnectorRegistrationError` (registry / type collision / unknown type) + `ConnectorRateLimitError` (platform rate-limit response; carries retry-after metadata). Mirrors MCP's hierarchy in shape but smaller — no version-mismatch type (each platform manages its own API versioning) and no sandbox-error type (third-party APIs are platform-sandboxed).
- **Rationale**: M07's full typed-exception hierarchy at `mcp/errors.py` is 10 types accreted across 11 flights; the **consumer-side match list** in `agents.md` collapses them into 4 categories (the wording "four-typed-exceptions" refers to that consumer-side surface, not the producer hierarchy — earlier flight drafts conflated the two). The connector hierarchy ships 6 producer types from Flight 1 because Flight 10 explicitly owns rate-limit handling for both Discord and Slack outbound, and adding `ConnectorRateLimitError` upfront prevents Flight 8/9 from having to retrofit the translation path. The "grow deliberately" stance still applies for types beyond 6 — the trigger for additions is "a real connector reveals a distinct error mode that doesn't fit any existing type."
- **Trade-off**: Six types upfront might be slightly speculative for `ConnectorRateLimitError` (rate limits don't surface until real connectors land). Acceptable: the type is small, well-named, and the alternative (retrofit in Flight 8 or 9) is structurally worse.

**`ConnectorPlugin` Protocol scope is the 4 methods Flight 1's stub end-to-end test exercises — no more**

- **Choice**: `ConnectorPlugin` Protocol in Flight 1 declares exactly four methods: `connect(account, encryptor) → ConnectorClient`, `disconnect(client) → None`, `doctor(account, encryptor) → DoctorReport`, `normalize_session_key(inbound: InboundEnvelope) → SessionKey`. `runtime_checkable`. Structural satisfaction (no inheritance), per the project's `structural-Protocol-satisfaction` convention. Allowlist resolution (Flight 6) and command-surface handling (Flight 7) land **as separate Protocols in the same `connectors/base.py`** when those flights need them — `AllowlistResolver` and `CommandHandler` — so connectors structurally satisfy whichever protocols apply to the capabilities they support, without Flight 1 pre-committing the signatures.
- **Rationale**: Architect review flagged the original 6-method Protocol as pre-committing Flights 6/7's design space — the structural-satisfaction convention means every implementer must implement every method on a Protocol it claims to satisfy, so adding `resolve_allowlist` and `command_handler` to the Plugin in Flight 1 forces Flights 6/7 to live with whatever signatures Flight 1 sketched. Splitting into multiple Protocols on the same file preserves the mission criterion "single connector-plugin contract that is the only file any future connector author needs to satisfy" (multiple Protocols in one file is still one contract file) while letting each capability-flight design its own surface.
- **Trade-off**: Connectors may need to satisfy 2-4 Protocols depending on which capabilities they support. The Plugin Protocol is the only one Flight 1 ships; Discord (Flight 8) and Slack (Flight 9) end up satisfying Plugin + AllowlistResolver + CommandHandler before they fully participate. The composition is documented in `connectors/README.md` and the connector-type checklist in `agents.md`.

**Encryption envelope mirrors MCP exactly**

- **Choice**: `secrets: dict[str, Any]` field on `ConnectorAccount`, encrypted-at-rest as a ciphertext blob in the DB, decrypted at-call-time. Repository holds an `Encryptor` reference (not copy); post-rotation propagation works via the install_key path that already handles MCP and LLM provider repositories. `__MASKED__` sentinel is preserved in the update path.
- **Rationale**: Single source of truth for encryption pattern; the rotation transaction already extends by adding a third loop inside the existing single commit at `api.py:2770-2840`.
- **Trade-off**: None — pattern is established.

**Defer `AgentConfig.connector_account_ids` to Flight 4 (NOT Flight 1)**

- **Choice**: Flight 1 does NOT add the `connector_account_ids` field to `AgentConfig` in `agent/config.py`. Flight 4 adds it when the platform-send tool's factory wiring needs to read it.
- **Rationale**: Architect review flagged this as a vestigial-field smell — Flight 1 has no consumer for `connector_account_ids`, and adding it now would violate the spirit of `trust-the-runtime` (don't add machinery a runtime won't exercise). Pydantic's `extra="ignore"` semantics in `AgentConfig` mean rows persisted today round-trip cleanly once Flight 4 adds the field. The persistence-layer seam Flight 1 actually needs is the `connector_accounts` table itself; per-agent attachment is a Flight 4 concern.
- **Trade-off**: Flight 4 owns the field name and JSON schema layout. The naming convention is constrained (must mirror `mcp_source_ids`) so bikeshed risk is low.

**`merged_config()` helper deferred — connectors may have nested config**

- **Choice**: `ConnectorAccount` ships without a `merged_config()` helper in Flight 1. Connector-specific config composition (e.g. Discord intents, Slack scopes — both likely nested structures) is handled via the agent-level two-layer resolver pattern when Flight 6 wires per-agent overrides.
- **Rationale**: M07 F1's debrief flagged `MCPSource.merged_config()` as misbehaving on nested structures because it does a flat top-level dict merge. Connectors will almost certainly have nested config; mirroring `merged_config()` blindly would reproduce the same bug. Defer the composition decision until Flight 6 knows the override surface.
- **Trade-off**: Tests that want a "fully resolved config" view in Flight 1 work directly with the `.config` + `.secrets` fields. Acceptable for the stub-driven test.

### Prerequisites

- [ ] Mission status is `active` (confirmed: `dbe29cb`)
- [ ] Schema version on `main` is 12 (confirmed: `db/schema.py:11 CURRENT_VERSION = 12`)
- [ ] `mcp/_pool.py` read and the worker-task-per-entry pattern understood (confirmed: `_RegistryEntry` L67-98, `_entry_worker` L148-248, `shutdown_drain` L387-428, `acquire` L431-517)
- [ ] Encryption rotation transaction shape confirmed at `interfaces/web/api.py:2744-2853` (single atomic commit covering all encrypted corpora — verified by recon)
- [ ] Provider-type six-layer coordination checklist in `agents.md` L251-267 read and understood as the model for the connector-type checklist this flight adds
- [ ] M07 typed-exception precedent in `mcp/errors.py` (10 producer types, 4 consumer-side match categories) read and understood as the model for `connectors/errors.py`
- [ ] `the_one/db/_provider_types.py` `PROVIDER_TYPES` pattern read; `_connector_types.py` will mirror it
- [ ] **M09 maintenance recon**: verify no recent M09 commit on `main` touched `db/schema.py`, `db/models.py`, `db/repositories.py`, or `interfaces/web/api.py` around the rotation transaction; if anything moved, re-locate the cited line numbers before leg 1 begins
- [ ] No conflicting in-flight work on `db/schema.py` or `interfaces/web/api.py` on `main`
- [ ] Container test entry points (`make test`, `make lint`) operating cleanly on `main`

### Pre-Flight Checklist

- [ ] All open questions resolved (six closed in Design Decisions; two intentionally deferred to leg planning during execution)
- [ ] Design decisions documented above with rationale and trade-offs
- [ ] Prerequisites verified
- [ ] Validation approach defined (see In-Flight § Verification below)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

**Top-down**: the contract first, then the persistence layer it consumes, then the pool that the contract's clients hold, then the registry that names the contract's implementations, then the stub that exercises everything end-to-end, then the docs that lock the conventions in place.

- **`the_one/connectors/`** — new package, peer to `mcp/` and `tools/`. Package-level `__init__.py` exports the public surface: `ConnectorPlugin`, `ConnectorClient`, `ConnectorClientError` + subtypes, `ConnectorAccount`, `acquire`, `release`, `shutdown_drain`, `ConnectorRegistry`. Private modules (`_pool.py`, `_stub.py`) underscore-prefixed. Per `canonical-import + convenience-re-export`: re-exports from `__init__.py` are convenience only; code that touches Protocol identity (`isinstance(...)`, exception handlers) MUST use the canonical path `from the_one.connectors.base import ConnectorPlugin` and `from the_one.connectors.errors import <ExceptionType>`.
- **`the_one/connectors/base.py`** — the `ConnectorPlugin` Protocol with `runtime_checkable`. **Four methods** in Flight 1: `connect(account, encryptor) → ConnectorClient`, `disconnect(client) → None`, `doctor(account, encryptor) → DoctorReport`, `normalize_session_key(inbound: InboundEnvelope) → SessionKey`. Supporting types (`ConnectorClient`, `InboundEnvelope`, `OutboundTarget`, `DoctorReport`, `SessionKey`) live in the same file. **Flights 6 and 7 add separate Protocols** (`AllowlistResolver`, `CommandHandler`) in this file when those capabilities land — not now.
- **`the_one/connectors/errors.py`** — `ConnectorClientError`, `ConnectorConfigError`, `ConnectorConnectionError`, `ConnectorAuthRequired`, `ConnectorRegistrationError`, `ConnectorRateLimitError`. Each with the same docstring discipline as `mcp/errors.py`.
- **`the_one/connectors/_pool.py`** — per-(agent, account) lifecycle pool. Worker-task-per-entry. Idle-TTL reaper as a separate task. `shutdown_drain()` for lifespan integration. **Includes** `_evict_all_for_account(account_id)` analog to `mcp/_pool.py:_evict_all_for_source` — Flight 2 will call this when an operator updates a connector account's credentials, so the warm entry doesn't keep using the old token. The full `_clear_for_test` + `_shutting_down` reset path correctly implemented from the start.
- **`the_one/connectors/registry.py`** — `ConnectorRegistry` class with `register(type_name, plugin_class)`, `resolve(type_name) → ConnectorPlugin`, `types() → list[str]`. Module-level singleton instance. The production discovery path is explicit registration of built-in connector plugins at module import time; test-side `register_for_test(plugin)` and `clear_for_test()` for the stub.
- **`the_one/connectors/_stub.py`** — in-process no-op plugin satisfying only the 4-method `ConnectorPlugin` Protocol. Configurable doctor probe response (success / failure cases). Records inbound/outbound calls into a test-readable buffer so the end-to-end test can assert what flowed through. Registered only via `register_for_test` from the test fixture; never via the production discovery path.
- **`the_one/db/schema.py`** — v13 migration adds `connector_accounts` table (NO CHECK constraint on `type`; v14 in Flight 8 adds CHECK via table-rename).
- **`the_one/db/_connector_types.py`** — NEW file mirroring `_provider_types.py`. Exports `CONNECTOR_TYPES: tuple[str, ...] = ()` (empty in Flight 1) and the `assert set(get_args(...)) == set(CONNECTOR_TYPES)` invariant tying it to the Pydantic `Literal[...]` on `ConnectorAccount.type`.
- **`the_one/db/models.py`** — `ConnectorAccount` Pydantic model (mirrors `MCPSource` shape; `type: Literal[<expanded from CONNECTOR_TYPES>]`; `config: dict[str, Any]`; `secrets: dict[str, Any]`; created_at / updated_at). **No `merged_config()` helper** (deferred — see Design Decisions).
- **`the_one/db/repositories.py`** — `ConnectorAccountRepository` (mirrors `MCPSourceRepository`: list, get, create, update, delete, with `_secrets_to_ciphertext` / `_ciphertext_to_secrets` envelope and encryptor reference).
- **`the_one/interfaces/web/api.py`** — extend the rotation transaction at `api.py:2744-2853` to cover `connector_accounts.secrets` in the single atomic commit. **No new REST routes for connector accounts in this flight** — those land in Flight 2.
- **`the_one/agent/config.py`** — **NOT TOUCHED in this flight**. `AgentConfig.connector_account_ids` field lands in Flight 4 when the platform-send tool needs it.
- **`the_one/agents.md`** — append the **connector-type six-layer coordination checklist** parallel to the provider-type checklist at L251-267. Add a "Connector subsystem" section documenting: the typed-exception hierarchy (mirroring the MCP precedent), the worker-task-per-entry pattern (with the explicit parallel-pool-not-shared decision and the network-keyed third-pool extraction trigger), and the structural-Protocol-satisfaction commitment (multiple Protocols, one file). Add a new Known Issues subsection capturing the deferred-shared-pool decision so future maintainers see the rationale.
- **`the_one/connectors/README.md`** — package-level reference doc analog to `the_one/mcp/README.md`. Brief: what the package contains, what it doesn't, the canonical entry points, the Protocol decomposition (Plugin in Flight 1; AllowlistResolver, CommandHandler in Flights 6/7).

### Checkpoints

- [ ] **Checkpoint A**: Schema migration v13 applies cleanly to a v12 database; `connector_accounts` table exists with the expected columns and **no CHECK constraint** on `type`; `_connector_types.py` mirror lands with the empty tuple + literal-pinning assert; rotation transaction covers connector secrets in the same commit
- [ ] **Checkpoint B**: 6 typed exceptions exported from `connectors/errors.py`; 4-method `ConnectorPlugin` Protocol defined in `connectors/base.py`; canonical-import discipline followed in `__init__.py`
- [ ] **Checkpoint C**: `ConnectorRegistry` resolves the stub plugin via test-side injection; production discovery path lists zero connectors (no production types registered yet); `clear_for_test` restores production state across test boundaries
- [ ] **Checkpoint D**: Pool acquires a stub-backed entry, holds it warm, single-spawn semantics under concurrent acquire, evicts on `_evict_all_for_account`, evicts after idle TTL elapses, drains cleanly on `shutdown_drain()`; `_clear_for_test` resets `_shutting_down` correctly; env-var override read at call time
- [ ] **Checkpoint E**: End-to-end stub test exercises register account → save → acquire → simulated inbound → simulated outbound → reaper evict → drain, all in one test; this is the regression baseline for Flights 2–10
- [ ] **Checkpoint F**: `agents.md` connector-type checklist + Known Issues section land; `connectors/README.md` is canonical entry-point reference
- [ ] **Checkpoint G** (post-flight): `make test`, `make lint`, `make audit` all clean; no regression in MCP, LLM provider, or agent factory surfaces. Checked per-leg and verified as part of the Post-Flight Completion Checklist.

### Adaptation Criteria

**Divert if**:
- The pool extraction question reopens with a strong argument from the architect (e.g. shared pool turns out to be a 1-day extraction, not 1-2 legs) — surface as a flight-level redirect to the human
- The encryption rotation transaction shape has drifted on `main` since the mission was drafted (we read `api.py:2770-2840` as canonical; if a recent commit changed it, re-validate the extension shape before adding connector_accounts)
- The Pydantic / repository pattern has changed between MCP and what M09 maintenance landed — re-cross-reference before mirroring blindly
- A leg of work exceeds 1 day's planned scope by more than 50% — split the leg, log the deviation

**Acceptable variations**:
- Final method-name finalization on the `ConnectorPlugin` protocol can land slightly differently from what's sketched in Technical Approach as long as semantic intent is preserved
- The stub plugin's exact buffer-recording API is implementation detail; tests are the contract
- The `agents.md` checklist may grow to 7+ layers if a real-world connector reveals one we missed; document the addition with the same rigor as the provider-type checklist

### Legs

> **Note:** Tentative leg breakdown (8 legs). Legs are planned in detail one at a time as the flight progresses; this list will evolve based on discoveries during implementation. Each leg gates on `make test` and `make lint` clean before signaling completion, per the M07 F1 debrief lesson — no separate "verify everything" closer is needed.

- [ ] `schema-and-migration` — v13 migration: `connector_accounts` table (id TEXT PK, type TEXT NOT NULL, config TEXT NOT NULL, secrets TEXT NOT NULL, created_at, updated_at — **no CHECK constraint on type**). Create `the_one/db/_connector_types.py` exporting `CONNECTOR_TYPES: tuple[str, ...] = ()` and the literal-pinning assert. Extend the rotation transaction at `interfaces/web/api.py:2744-2853` to include `connector_accounts.secrets` in the single atomic commit. Test: applying v13 to a v12 database is idempotent and crash-safe; rotation re-encrypts connector secrets atomically with LLM provider + MCP source secrets; a deliberate failure injected during the rotation rolls back all three corpora together.
- [ ] `models-and-repository` — `ConnectorAccount` Pydantic model in `db/models.py` (no `merged_config()` helper — deferred per Design Decisions); `ConnectorAccountRepository` in `db/repositories.py` with CRUD + encryption envelope + `__MASKED__` sentinel handling on update + encryptor-reference (not copy) for rotation propagation. Test: round-trip a `ConnectorAccount` through the repository with encrypted secrets; `__MASKED__` on update preserves stored value; encryptor reference propagation works across an install-key cycle.
- [ ] `errors-and-protocol` — `connectors/errors.py` defines the 6 typed exceptions (`ConnectorClientError`, `ConnectorConfigError`, `ConnectorConnectionError`, `ConnectorAuthRequired`, `ConnectorRegistrationError`, `ConnectorRateLimitError`) with the docstring discipline matching `mcp/errors.py`. `connectors/base.py` defines the 4-method `ConnectorPlugin` Protocol with `runtime_checkable` and the supporting types (`ConnectorClient`, `InboundEnvelope`, `OutboundTarget`, `DoctorReport`, `SessionKey`). `connectors/__init__.py` exports the public surface with the canonical-import discipline noted. Test: a minimal in-test class structurally satisfies the Protocol; exception subclassing chain is correct; canonical-import paths work for `isinstance` and `try/except` consumers.
- [ ] `registry` — `connectors/registry.py` with module-level singleton `ConnectorRegistry`. Production discovery path: an explicit `register_builtin_connectors()` function called at module import (registers nothing in Flight 1 — Flight 8 adds 'discord', Flight 9 adds the second). Test-side: `register_for_test()`, `clear_for_test()`. Test: registry resolves a registered type; resolve on unknown type raises `ConnectorRegistrationError`; `clear_for_test` restores production state cleanly across a test boundary.
- [ ] `lifecycle-pool-core` — `connectors/_pool.py` Part 1: `_RegistryEntry` dataclass, `_entry_worker` (worker-task-per-entry pattern, anyio cross-task `CancelScope` guard respected), `acquire(agent_name, account_id)`, `_evict(key)`, `_evict_all_for_account(account_id)`, `_clear_for_test`. Apply M07's test-isolation lesson: `_clear_for_test` resets `_shutting_down` to `False` AND clears `_pool`, `_lock`, and any other module-level state to the post-import baseline. Test: pool holds an entry warm; concurrent `acquire` on the same key returns the warm entry (single-spawn semantics); `_evict_all_for_account` flushes warm entries when the account's credentials change; `_clear_for_test` round-trips cleanly across tests.
- [ ] `lifecycle-pool-reaper-and-drain` — `connectors/_pool.py` Part 2: `_resolve_ttl_seconds()` (reads `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` at call time, defaults 1800), `_reap_once()`, `_reaper_loop()`, `shutdown_drain()`. The lifespan integration is documented in code but **wired into `app.py` only in Flight 2** (when there's something to drain in production). Test: idle TTL elapses → entry is reaped; `shutdown_drain` cancels in-flight entries cleanly and leaves the pool in a re-usable state (or `_clear_for_test` does); env-var override is read at call time, not at module import (live-read invariant per `agents.md`).
- [ ] `stub-plugin-and-end-to-end-fixture` — `connectors/_stub.py` in-process stub satisfying the 4-method Protocol. Configurable doctor probe response, recording buffer for inbound/outbound, simulated reconnect failure injection. End-to-end test: create a stub `ConnectorAccount` via the repository, register the stub plugin for the test, acquire a pool entry, simulate an inbound envelope, drive the stub's outbound recording, verify the reaper evicts after a test-overridden short idle TTL, verify `shutdown_drain` returns cleanly. This test is the **regression baseline Flights 2–10 inherit** — every subsequent flight that touches the connector layer asserts this test still passes.
- [ ] `agents-md-and-package-readme` — append the **connector-type six-layer coordination checklist** to `agents.md` parallel to the provider-type checklist; add a "Connector subsystem" decisions-and-invariants section documenting the typed-exception hierarchy (with the consumer-side-vs-producer-side wording clarified), the worker-task-per-entry pattern, the parallel-pool-not-shared decision (with the explicit "third **network-keyed** pool" extraction trigger that excludes the PTY pool), and the **per-Protocol structural-satisfaction discipline**: structural satisfaction is per-Protocol, not subsystem-wide, so a connector that claims to satisfy `Plugin` + `AllowlistResolver` + `CommandHandler` MUST be asserted via `isinstance(conn, ProtocolType)` for each Protocol it claims; the per-platform integration tests (Flights 8 and 9) carry the assertions. Add a new Known Issues entry on the deferred shared-pool extraction. Write `the_one/connectors/README.md` as the package-level entry-point reference analog to `the_one/mcp/README.md`.

---

## Post-Flight

### Completion Checklist

- [ ] All 8 legs completed
- [ ] Schema migration v13 lands cleanly (no CHECK on `type`); rotation transaction covers connector secrets atomically with LLM + MCP secrets
- [ ] `_connector_types.py` mirrors `_provider_types.py` with empty tuple + literal-pinning assert
- [ ] 6 typed exceptions + 4-method `ConnectorPlugin` Protocol exported from `the_one/connectors/`
- [ ] Canonical-import discipline documented in `connectors/__init__.py` and `connectors/README.md`
- [ ] `ConnectorAccountRepository` round-trips encrypted accounts; `__MASKED__` sentinel preserved; encryptor-reference (not copy) confirmed for rotation propagation
- [ ] Lifecycle pool with worker-task-per-entry + `_evict_all_for_account` + idle-TTL reaper + shutdown drain operating against the stub
- [ ] Stub-driven end-to-end test passes and is the regression baseline for Flights 2–10
- [ ] Connector-type six-layer coordination checklist documented in `agents.md` parallel to provider-type checklist
- [ ] Known Issues section in `agents.md` captures the deferred shared-pool extraction with the "third network-keyed pool" trigger
- [ ] `the_one/connectors/README.md` is the package-level canonical entry-point reference, noting the Protocol decomposition (Plugin now; AllowlistResolver, CommandHandler in Flights 6/7)
- [ ] `make test`, `make lint`, `make audit` clean
- [ ] No regression on the existing LLM provider / MCP source / agent factory surfaces (specifically: `_compute_visible_schemas` and the agent factory's tool resolution path remain byte-identical for non-connector-attached agents)
- [ ] Flight log captures any deviations from the planned approach
- [ ] Code merged
- [ ] Mission flight checkbox ticked for Flight 1

### Verification

The flight is verified end-to-end by the stub-driven test in the `stub-plugin-and-end-to-end-fixture` leg. That test:

1. Spins up an in-memory SQLite at schema version 13
2. Saves a `ConnectorAccount` of type `'stub'` with non-trivial secrets through the repository
3. Reads the account back and asserts secrets decrypt to the original
4. Registers the stub plugin into the connector registry under test injection
5. Acquires a pool entry for `(agent_name='test-agent', account_id=<saved>)` and asserts the entry is warm
6. Simulates an inbound envelope through the stub's inbound buffer and asserts the recording reflects it
7. Simulates an outbound dispatch through the stub's outbound recording
8. Sleeps past the idle TTL (using a test-overridden short TTL) and asserts the reaper evicts the entry
9. Acquires again and asserts a fresh entry spawns
10. Calls `shutdown_drain` and asserts the pool is empty and `_shutting_down` resets correctly via `_clear_for_test`
11. Re-imports / clears for the next test and asserts no state leaks

Additional verification:
- `_compute_visible_schemas` and the agent factory remain byte-identical for non-connector-attached agents (no Flight 1 work should touch the agent loop or the factory's tool resolution path)
- Encryption rotation re-encrypts connector secrets in the same atomic commit as LLM and MCP secrets; a deliberate failure injected mid-rotation rolls back all three corpora together
- `agents.md` connector-type checklist is parallel in structure to the provider-type checklist; the structural-Protocol-satisfaction reference in the new section is the canonical citation for the subsystem
