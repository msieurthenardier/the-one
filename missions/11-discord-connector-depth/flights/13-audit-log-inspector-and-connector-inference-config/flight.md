# Flight: Audit-log inspector + per-connector inference config + slash-command HAT

**Status**: landed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [ ] **#10** — All six platform-side slash commands end-to-end validated against the real Discord bot (verify-only this flight; ephemeral cleanup + autocomplete polish explicitly out of scope per operator decision at planning — current "all visible" behavior stays)
- [ ] **#12** — The mentions-aware response policy's *operator surface* — F7 shipped the policy gate + the `Settings.inference_provider_config_id` field but no UI; F13 closes the gap by relocating inference configuration onto the connector account itself (operator's framing: "the LLM has to be set up first, and each connection may choose a different LLM, to me this is simply a property of the connector") and ships the connector-editor Provider + Model selector
- [ ] **#15** — Audit-log inspector for `session_metadata["routing"]` records that F7 populates; lives in the Chat UI per-session panel per F7 OQ #8 default ("the operator already lives there when debugging routing"); connector-agnostic but exercised against Discord in this mission

Three F12 carry-forward debt items fold in: shared test-fixture translator module extraction, two new agents.md M11 conventions codification, and per-agent `peers[*].dm_allowed` retirement via v26 migration (closes the footgun both the Developer and Architect debrief crews flagged independently).

---

## Pre-Flight

### Objective

Close M11's three remaining operator-facing surfaces — connector-scoped inference LLM configuration, audit-log inspector, and slash-command verification — while folding in F12 debrief carry-forward items that share the substrate surface F13 touches. Specifically: (a) **relocate inference LLM selection from `Settings` to `connector_account.config`** per operator framing — each connector chooses its own inference LLM; Settings env vars are retired entirely; schema migration v26 adds `inference_provider_config_id: str | None` + `inference_model: str | None` to `connectors.config` (backfilled `None` per operator decision; existing env-var values become no-ops with one-time startup warning); the dispatcher's policy-gate inference call (`_inbound.py:269-275`, `_inference.py:167+`) reads from connector first, falls back to the routed agent's LLM if the connector's value is unset; the connector editor's policy section gains a Provider dropdown (sourced from existing `/api/providers`) + Model text input, conditional on `always_listen=true`. (b) **expose `session_metadata["routing"]`** by extending the existing `GET /api/chat/sessions/{session_id}` response (currently strips `session_metadata` at `api.py:3246`'s `_session_summary()`) and render a collapsible Chat UI per-session "Routing" panel that renders each routing entry (timestamp, agent, scope, reason, disposition) with expandable nested `policy` dict for `policy-silent` entries surfacing inference_provider_id / inference_model / always_listen flags. (c) **HAT walk** the 6 slash commands against the real Discord bot — verify-only per operator decision; all 6 stay channel-visible (current behavior); ephemeral cleanup + Discord-native autocomplete explicitly deferred to a future flight. (d) **F12 carry-forward fold-ins** layered as a mechanical prereq leg (F11/F12 pattern of mechanical-prereq-leg-before-semantic-changes): extract `tests/_acl_shape_helpers.py` consolidating `_to_v24_shape` / `_to_v24_agent_acl` / `_to_v24_allowlist` / `DEFAULT_TEST_GUILD_ID` from 4+ test files; codify `column-aware-index-create-for-rewind-paths` + `test-translator-helpers-for-shape-evolution` in `agents.md` M11; and the v26 migration also strips per-agent `peers[*].dm_allowed` (F12 footgun) with Pydantic validator tightening to **reject** the field on per-agent peer entries post-v26.

### Open Questions

All resolved at planning (Phase 3 + Phase 4) before leg design.

- [x] Where should inference LLM selection persist? → see DD: Inference Persistence Lives on the Connector (operator: "simply a property of the connector")
- [x] Slash-command verification scope? → see DD: Slash Verification Is Verify-Only (operator: "All visible (current behavior)")
- [x] F12 carry-forward fold-ins? → see DD: F12 Fold-Ins (operator: "Translator helpers + 2 conventions + per-agent dm_allowed retirement")
- [x] v26 backfill strategy? → see DD: v26 Backfill is `None` (operator: "operator edits per-connector post-migration")
- [x] Settings env-var deprecation? → see DD: Settings Removed Entirely (operator: "Remove from Settings entirely")
- [x] Per-agent `dm_allowed` validator strictness? → see DD: Strict Validator Post-v26
- [x] Audit-log inspector surface? → Chat UI per-session panel per F7 OQ #8 default (operator did not redirect at planning)

### Design Decisions

**Inference Persistence Lives on the Connector** *(operator-directed at Phase 3)*: F7's `Settings.inference_provider_config_id` (project-wide pointer) is the wrong shape. Operator framing: "the LLM has to be set up first, and each connection may choose a different LLM, to me this is simply a property of the connector." Two new optional fields land on `connectors.config`:
- `inference_provider_config_id: str | None = None` — pointer to an existing `LLMProviderRepository` row
- `inference_model: str | None = None` — model identifier (free-form; provider-type determines whether a model list is queryable, e.g. Ollama vs OpenAI-compatible)

Dispatcher resolution at runtime: connector.config → if `None`, fall back to the routed agent's configured LLM (same fallback F7's Settings path used). Settings consultation removed entirely.
- **Rationale**: Each connector can use a small / fast / cheap model for the inference gate (e.g. `qwen2.5:7b` for Discord, GPT-4-mini for Slack) independently of the agent's primary LLM. Matches F7's trade-off note ("If the operator later wants per-account divergence...") promoted to canonical shape.
- **Trade-off**: Two fields per connector × N connectors instead of one project-wide pointer. Worth it — the operator-mental-model alignment ("the connector picks its inference LLM") matches how the connector editor already surfaces other connector-scoped concerns (allowlist, always_listen, system-prompt directives).

**Settings Removed Entirely** *(operator-directed at Phase 4)*: `Settings.inference_provider_config_id` + `Settings.inference_model` deleted from `the_one/config.py:31-32`. Env vars `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` + `THE_ONE_INFERENCE_MODEL` become no-ops. One-time startup warning if either env var is set post-v26 (using `os.environ.get` directly for the deprecation check, since the Settings fields no longer exist) telling the operator the value won't apply and pointing at the connector editor.
- **Rationale**: Pydantic BaseSettings with the field removed would either ignore the env var silently (current `extra="ignore"` default) or error (`extra="forbid"`). Neither is the right message. An explicit one-time-at-startup log warning is the right operator UX.
- **Trade-off**: The operator's local `docker-compose.yml` HAT env vars carry the inference fields (per F11 + F12 operator-local-state preservation discipline). Those env vars become dead weight post-F13; the warning surfaces it. Operator removes them from docker-compose.yml on their own schedule (not staged by F13's commits).

**v26 Backfill is `None`** *(operator-directed at Phase 4)*: v26 row-rewrites `connectors.config` to add the two new keys with explicit `None` values. NO backfill from the current `Settings.inference_provider_config_id` env-var value (which would have been the safer-runtime-continuity choice). Operator framing: connectors start without inference config; operator edits per-connector via UI post-migration. Connectors with `always_listen=true` BUT `inference_provider_config_id=None` fall through to the routed agent's LLM (current F7 fallback path).
- **Rationale**: Forces the operator to make per-connector decisions explicitly; no "inherited project-wide default that no one remembers setting." Aligns with the connector-scope mental model.
- **Trade-off**: Existing always-listen connectors silently shift from "uses env-var-configured inference model" → "uses routed agent's LLM" at v26 land time. Runtime behavior changes for any connector where the env-var value differed from the routed agent's value. Migration log entry highlights the connectors affected (those with `always_listen=true`); operator reviews + acts.

**Strict Validator Post-v26** *(operator-directed at Phase 4)*: Pydantic validator for `connector_acls[*].peers[*]` REJECTS entries that carry a `dm_allowed` key post-v26. Matches F12's `guild_id`-required tightening pattern (L5). v26 migration strips the field from each per-agent peer entry; the validator enforces post-v26.
- **Rationale**: Catches drift if any future code path tries to write the field. The F12 footgun ("structurally uniform but not consulted by ACL") cannot reappear silently.
- **Trade-off**: Tests + fixtures that previously emitted `dm_allowed` on per-agent peers must update. F12's L3 translator helpers already wrote `dm_allowed=True` on per-agent peers for structural uniformity — L1 (translator-helpers extraction) updates the helper to NOT emit the field for per-agent shape. Account-scope peers KEEP `dm_allowed` (that's the consumed-by-ACL path).

**Slash Verification Is Verify-Only** *(operator-directed at Phase 3)*: Mission criterion #10 says "end-to-end validated against the real Discord bot — invoked from a real Discord client, returning correctly to the invoking user, with per-(agent, peer) permission gating exercised; responses that should be ephemeral...are ephemeral." Operator chose verify-only at planning: all 6 commands stay channel-visible (current F8 L9 behavior); no ephemeral cleanup; no autocomplete. F14 (HAT script flight) will capture the verification in re-runnable form.
- **Rationale**: F8 L9 deferred ephemeral + autocomplete to "F10 hardening" (per code comment at `_discord.py:858-859`). Operator's verify-only choice respects that deferral and bundles the actual ephemeral/autocomplete work for a future flight where the Discord-native polish can land coherently.
- **Trade-off**: M11 criterion #10's "ephemeral where appropriate" sub-bullet stays unclosed at F13 land. The criterion is marked `[~]` (partial) at F13 land; full closure happens at the future flight that ships ephemeral + autocomplete. Mission outline updated to reflect this split.

**F12 Fold-Ins — Mechanical Prereq Leg + Migration-Bundled Cleanup** *(operator-directed at Phase 4)*: Three F12 debrief carry-forwards land in F13 across the leg sequence per the F11/F12 mechanical-prereq-leg-before-semantic-changes pattern:
- **L1 (mechanical, structural no-op)**: Extract `tests/_acl_shape_helpers.py` consolidating `_to_v24_shape` + `_to_v24_agent_acl` + L5's `DEFAULT_TEST_GUILD_ID` + the parallel `_to_v24_allowlist` from `tests/browser/seeders.py` (4+ test files duplicating the same shape-evolution work per F12 debrief Recommendation #3). Add two named conventions to `the_one/agents.md` M11 section at lines 405-431 (sibling to existing `dms-orthogonal-to-guild-restriction`, `backend-merged-replay`, `two-symmetric-paths-in-acl`, `studio-event-bus`): `column-aware-index-create-for-rewind-paths` (precedent: F12 L3's v21 fix) and `test-translator-helpers-for-shape-evolution` (precedent: F12 L3's `_to_v24_shape`). The M11 section structure is confirmed via grep at planning time — L1 adds 2 sibling blocks, does NOT establish the section.
- **L2 (substrate-only)**: schema v26 row-rewrite + Pydantic validator tightening + per-agent `peers[*].dm_allowed` retirement. Bundles the dm_allowed strip into v26 since v26 is already touching `agents.connector_acls` JSON. The strict-validator-post-v26 rejection lives in `the_one/agent/config.py` `_validate_connector_acls`.
- **L3 (runtime-path-only)**: Settings removal + dispatcher inference-source refactor + `test_connectors_inference.py` rework. Separated from L2 per architect cycle-1 — L2's seven concerns (substrate + validators + Settings + dispatcher + ACL + Pydantic + fixtures across 9 files) was heavier than F12 L3 + L5 combined. L2 + L3 share the v26 commit boundary as a single substrate dependency.

**L2/L3 Split Rationale** *(architect cycle-1 finding, operator-acknowledged)*: The original 4-leg shape collapsed schema + validator + Settings + dispatcher + ACL helper updates into one leg. Architect cycle-1 surfaced that `tests/test_connectors_inference.py` contains 7 distinct `Settings(inference_provider_config_id=..., inference_model=...)` constructions across lines 131-134, 230-232, 256-258, 276-278, 317-319, 569-571, 616-618 — the Settings-path / settings-partial / settings-shadows-fallback test branches (lines 219-330 + 560-630) become semantically meaningless once Settings fields are deleted. The right shape is to cull (not patch) those test branches, which is non-mechanical work that benefits from a separate leg with its own atomicity boundary. L2 ships substrate + validator; L3 ships runtime refactor + test culling. The shared v26 dependency keeps lockstep correctness; the split keeps each leg reviewable.

**`_acl.py` Axis-Level Extraction Is OUT OF SCOPE** *(operator did not redirect at planning; F12 debrief recommendation #2 was framed as "Don't do this proactively unless a concrete bug surfaces")*: The 740-LOC file with helper-level duplication stays as-is in F13. F13's only `_acl.py` touch is the small validator-driven update for the stripped per-agent peers shape (L2). The axis-level extraction stays a routine-maintenance candidate per the F12 recommendation.

**Audit-Log Inspector Surface: Chat UI Per-Session Panel** *(F7 OQ #8 default; operator did not redirect)*: Per-session panel in the Chat UI, collapsible by default. Renders the `session_metadata["routing"]` entries with per-entry expansion. Mission criterion phrases it as "connector-agnostic but exercised against Discord in this mission" — the panel itself reads any `session_metadata["routing"]` list regardless of connector type.
- **Rationale**: F7 OQ #8 already settled this with "Chat UI per-session panel as the primary surface (it's where the operator already lives when debugging routing)". F13 honors that default.
- **Trade-off**: Studio detail-page linking-to-Chat-UI surface is OUT OF F13 scope; F7 OQ #8 mentioned it as secondary. If operator surfaces a Studio-side need later, fold into a routine-maintenance pass.

**API Exposure Shape: Extend Detail-Endpoint Composition, Not the Shared Summary Helper** *(architect cycle-1 correction)*: `_session_summary()` at `the_one/interfaces/web/api.py:3246` is shared across 5 endpoints (lines 3185, 3196, 3209, 3223, 3246 — `list_chat_sessions`, `get_chat_session`, `create_chat_session`, `update_chat_session`, the helper itself). Adding `session_metadata` inside the helper would bloat every session-list-row response with potentially hundreds of routing entries. F13 attaches `session_metadata` ONLY on the detail-endpoint composition at `api.py:3195-3198` — `{**_session_summary(session), "messages": ..., "session_metadata": session.session_metadata}` — leaving the shared helper untouched. No new endpoint added.
- **Rationale**: One endpoint per session is the existing shape; introducing `/api/chat/sessions/{id}/routing` would split the data model. The detail-only injection avoids list-bloat while keeping the read-the-session pattern.
- **Trade-off**: If `session_metadata` grows large per session (e.g. very long sessions with hundreds of routing entries), client-side filtering is the right shape. F13 does NOT paginate the routing entries; if perf issues surface, a future flight adds `?since={ts}` or similar.

**Audit-Log Inspector Renders Only `routing`** *(operator-directed at Phase 5b)*: The Chat UI panel renders entries from `session_metadata["routing"]` only. Other keys (`audit` from F6 policy-gate deny/permit decisions; future `routing_override` etc.) are NOT rendered. Mission criterion #15 phrases the scope as "the `session_metadata["routing"]` records that F7 populates" — F13 honors that scope precisely.
- **Rationale**: Operator chose "Only `routing`" at planning. Smallest UI; scope-true to the criterion. Future flights extend if needed.
- **Trade-off**: `session_metadata["audit"]` (F6's ACL deny/permit per-peer decisions) stays unexposed in the Chat UI. Operator can still inspect via DB / API. Could fold into a future inspector flight if the operator surfaces a debugging need.

**Inference Fields Are Flat on `connector.config`** *(operator-directed at Phase 5b)*: `inference_provider_config_id` + `inference_model` sit at the top of `connector.config` alongside `always_listen`, NOT nested under `connector.config.policy.inference` or similar. Matches the existing `always_listen` shape; simplest validator + simplest UI binding.
- **Rationale**: F7 OQ #2's trade-off note suggested flat-per-account; operator confirmed at planning. If future inference knobs land (temperature, system-prompt-override), they sit flat alongside (and can be promoted to a nested namespace in a future flight if proliferation warrants).
- **Trade-off**: If 3+ inference-related knobs accumulate, the flat layout becomes noisy; consider promotion to nested at that point.

**`_resolve_inference_provider` Signature Change** *(architect cycle-1 finding)*: F7's `_resolve_inference_provider` at `the_one/connectors/_inference.py:167-194` currently takes a `settings: Settings` parameter and implements "settings-wins-shadows-fallback" semantics: when settings has values, fallback is ignored. F13 L3 changes the function signature — `settings` param removed; replaced with two new kwargs `connector_inference_provider_config_id: str | None` + `connector_inference_model: str | None` passed by the caller (`_inbound.py:269`) from `account.config`. Resolution order becomes: connector value (passed kwarg) → fallback (routed agent's LLM) → silence. The function docstring's three-path explanation is updated accordingly.
- **Rationale**: The "settings-wins-shadows-fallback" semantic is replaced by "connector-wins-falls-back-to-agent." Same shape (two paths plus silence) but the precedence is now per-connector instead of project-wide.
- **Trade-off**: Caller plumbing change at `_inbound.py:269+` — replaces 2 positional `settings` arg lookups with 2 kwarg passthroughs from `account.config`. Mechanical.

**v26 Migration Logs Affected Connectors** *(architect cycle-1 elevation from DD prose to Technical Approach)*: At v26 row-rewrite time, for each existing `connectors` row where `config.get("always_listen") is True`, the migration emits a `logger.info` line naming the connector ID + label, indicating the connector inherited `None` defaults for the new inference fields and the operator should edit per-connector via the Studio connector editor. Connectors with `always_listen=false` or absent are not logged (they don't run the inference gate; the field defaults don't affect runtime behavior for them).
- **Rationale**: The "v26 Backfill is `None`" decision silently shifts runtime behavior for live always_listen connectors from "uses env-var-configured inference model" to "uses routed agent's LLM." The migration log makes that shift visible to the operator at startup post-migration.
- **Trade-off**: Migration logs are written to the application log at startup, not surfaced in the UI. Operator reads `docker logs the-one` (or equivalent) post-migration. Sufficient for the single-user local tool posture; UI-side migration notifications would be over-engineering.

### Prerequisites

- [ ] F12 has landed (commit `9f4df4a` on main, verified)
- [ ] Backend test suite baseline: 2783 passed / 4 skipped / 0 errors / ~246s wall (per F12 debrief test-metrics)
- [ ] Browser test suite baseline: 443 passed / 35 skipped / 12 deselected / 2 pre-existing-main failures (NOT F12-or-F13-caused)
- [ ] M11 agents.md M11 section has F12 L2's `two-symmetric-paths-in-acl` convention block (verified at F12 debrief)
- [ ] Operator has at least one configured LLM provider in `/api/providers` (any provider type — Ollama / OpenAI-compatible / Anthropic / etc.) — required for L3's connector-editor Provider dropdown to populate during L3's browser tests AND for L5's slash-command HAT against a real Discord bot
- [ ] Operator's local `docker-compose.yml` HAT env vars continue out of F13 commits (per F11 + F12 operator-local-state preservation discipline)
- [ ] Discord bot reachable for L5 HAT (operator confirms before L5 kickoff; if blocked, L5 can stand-alone re-run at any time after F13 land without re-landing other legs)

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites listed
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

**Leg count**: 6 legs (L2 split into L2 + L3 per architect cycle-1; original L3/L4/L5 renumbered to L4/L5/L6).

**L1 — Methodology fold-ins (F12 carry-forward; mechanical structural no-op).** Single atomic leg per F11/F12 mechanical-prereq pattern. Two surfaces, both shape-only:
- **Shared test fixture module**: extract `tests/_acl_shape_helpers.py` consolidating the translator helpers currently duplicated across `tests/test_connectors_acl.py`, `tests/test_connectors_routing.py`, `tests/test_connectors_commands.py`, and `tests/browser/seeders.py`. Functions to extract: `_to_v24_shape(account_or_dict)` (normalizes flat-shape allowlist fixture data to v24 structured-tuple shape), `_to_v24_agent_acl(agent_acl_or_dict)` (parallel for per-agent), the `DEFAULT_TEST_GUILD_ID = "g-test"` constant, the `_to_v24_allowlist` alias used in browser seeders. Original sites import from the shared module; no fixture-shape changes; no test-count changes. Per F12 debrief recommendation #3.
- **agents.md conventions**: add two named M11 convention blocks as siblings to F12 L2's `two-symmetric-paths-in-acl`:
  - `column-aware-index-create-for-rewind-paths` (precedent: F12 L3's split of v21's `executescript` into `CREATE TABLE` + Python-guarded `CREATE INDEX` consulting `PRAGMA table_info(pending_approvals)` to handle the v7-strip rewind+rerun path)
  - `test-translator-helpers-for-shape-evolution` (precedent: F12 L3's `_to_v24_shape` at test-module top; promoted by L1's extraction)
- L1 is semantically a no-op; backend baseline 2783 preserved; browser baseline 443 preserved.

**L2 — Schema v26 + Pydantic validator tightening + per-agent `dm_allowed` retirement (substrate-only).** Atomic substrate leg; pairs with L3 across the v26 commit boundary. Surfaces:

**(a) Schema migration v26** (in `the_one/db/schema.py` after the v25 block). Row-rewrites:
- For each row in `connectors`: parse `config` JSON; if `inference_provider_config_id` key absent, add `inference_provider_config_id: None` and `inference_model: None`. Idempotent (key-presence guard). **Per architect cycle-1 promotion**: for each connector with `config.get("always_listen") is True`, emit `logger.info("v26: connector %s (%s) inherits None inference defaults; edit per-connector via Studio connector editor", connector_id, connector_label)` so operator sees the runtime-behavior shift at startup post-migration.
- For each row in `agents`: parse `connector_acls` JSON; for each `connector_acls[acct]` payload, iterate `peers` list and call `entry.pop("dm_allowed", None)` per entry (idempotent per architect cycle-1 wording correction — `dict.pop(key, None)` is the safe no-op-on-rerun shape; `del` would `KeyError` on second run). Track `changed = True` only when a pop actually removes the field, matching the v25 `UPDATE-only-when-changed` pattern at `schema.py:1463-1474`.
- Bump `CURRENT_VERSION = 26`. Use F12-pattern segment guards for v7-strip rewind path (verified at L2 design time via grep against `tests/test_db_migration.py`).
- NO index changes (v24 + v25 covered those).

**(b) Pydantic validators** (`the_one/db/models.py` + `the_one/agent/config.py`):
- `the_one/db/models.py` allowlist validator at line 308+: accept `inference_provider_config_id: str | None` + `inference_model: str | None` as new optional keys on `connector.config` (default `None`). Account-scope `peers[*]` shape unchanged (still carries `dm_allowed: bool`).
- `the_one/agent/config.py:269+` `_validate_connector_acls`: per-agent `peers[*]` entries REJECTED if they carry a `dm_allowed` key. Error message: "per-agent peer entries must not carry `dm_allowed`; the per-peer DM toggle is account-scope only (F12 footgun retirement, F13 L2)."

**(c) ACL helper update** (`the_one/connectors/_acl.py`): per-agent peers iteration no longer reads `dm_allowed`. Grep `the_one/connectors/_acl.py` at L2 design time to enumerate every `dm_allowed` read site; the account-scope per-peer `dm_allowed` consumption stays intact (DM Composition Truth Table unchanged at account-scope). The F12 `two-symmetric-paths-in-acl` convention applies — both `_admits_inbound_dm` and `_admits_inbound_guild` checked + updated in lockstep at recon.

**(d) Tests added**:
- `TestSchemaV26` class in `tests/test_db_migration.py`: `test_v26_fresh_db_shape` (connector.config has the two new keys with `None` defaults; per-agent peers don't carry `dm_allowed`); `test_v26_idempotent_on_rerun` (segment guards short-circuit); `test_v26_legacy_v25_row_migration_strips_dm_allowed` (per-agent peer entries lose the field); `test_v26_connector_config_inference_fields_added` (existing connectors get `None` defaults); `test_v26_logs_affected_always_listen_connectors` (verify the `logger.info` fires for always_listen=true connectors at migration time, using `caplog` fixture).
- `TestPerAgentDmAllowedStrictRejection` in `tests/test_db_repositories.py`: 2 cases verifying Pydantic validator rejects per-agent peers with `dm_allowed`. The translator helper updated in L1 stops emitting the field on per-agent shape, so existing fixtures auto-comply.

**(e) Test fixture updates**: per L1 shared `_acl_shape_helpers.py` updates — `_to_v24_agent_acl` no longer emits `dm_allowed` on per-agent peers. Backend test fixtures across `test_connectors_acl.py`, `test_connectors_routing.py`, `test_connectors_inbound.py`, `test_connectors_commands.py`, `test_db_repositories.py`, `test_db_api.py`, `tests/browser/seeders.py` (9 files enumerated per F12 L3) auto-update via the helper. **Inline per-agent `dm_allowed` writes** discovered at L2 design time via `grep -nE '"dm_allowed":\s*(True|False|true|false)' tests/ --include='*.py'` (architect cycle-1 enumerated: `tests/test_connectors_routing.py:55`, `tests/test_connectors_commands.py:271`, `tests/browser/seeders.py:127, 178`) — these are NOT covered by the translator helper and must be removed in-leg.

L2 backend test count target: **2783 + 7 net** (5 TestSchemaV26 + 2 TestPerAgentDmAllowedStrictRejection + 0 from fixture-translator-update auto-application = **2790**).

**L3 — Settings removal + dispatcher inference-source refactor + `test_connectors_inference.py` rework (runtime-path-only).** Pairs with L2 across the v26 commit boundary. Surfaces:

**(a) Settings field removal** (`the_one/config.py`):
- Delete `inference_provider_config_id: str | None = None` + `inference_model: str | None = None` from the `Settings` BaseSettings subclass at lines 31-32.
- Add an explicit startup check **in the FastAPI app's lifespan hook** (NOT module load — module load runs on every test-suite import; lifespan fires once per app start per architect cycle-1 suggestion). The hook reads `os.environ.get("THE_ONE_INFERENCE_PROVIDER_CONFIG_ID")` + `os.environ.get("THE_ONE_INFERENCE_MODEL")` and emits a single `logger.warning` if either is set, naming both env vars + directing the operator to the Studio connector editor.

**(b) Dispatcher inference-source-lookup refactor** (`the_one/connectors/_inbound.py` + `the_one/connectors/_inference.py`):
- `_inbound.py:269-275` (the `run_engagement_inference` invocation): replace the `settings.inference_provider_config_id` + `settings.inference_model` positional/kwarg lookups with `account.config.get("inference_provider_config_id")` + `account.config.get("inference_model")` lookups. Pass as new kwargs to `_inference.run_engagement_inference`.
- `_inference.py:151-194` `_resolve_inference_provider` signature change per architect cycle-1: remove `settings: Settings` param entirely; add two new kwargs `connector_inference_provider_config_id: str | None` + `connector_inference_model: str | None`. Resolution order becomes: connector kwarg value → `fallback_provider_config_id` (routed agent's LLM) → silence with audit log entry. Update function docstring's three-path explanation accordingly.
- The `policy.inference_provider_id` + `policy.inference_model` fields in `session_metadata["routing"]` audit entries still get populated — same values, just sourced from connector kwargs instead of settings.

**(c) `test_connectors_inference.py` rework** (architect cycle-1 elevated this as an explicit L3 surface — 15 occurrences of `inference_provider_config_id` / `inference_model` across 7 `Settings(inference_provider_config_id=..., inference_model=...)` constructions at lines 131-134, 230-232, 256-258, 276-278, 317-319, 569-571, 616-618):
- **Cull** (not patch) the settings-path / settings-partial / settings-shadows-fallback test branches at lines 219-330 + 560-630. These tests pin the now-removed Settings-path semantic and are semantically meaningless post-L3.
- **Rewrite** remaining tests to construct the new per-connector-kwarg shape: `_resolve_inference_provider(fallback_provider_config_id=..., connector_inference_provider_config_id=..., connector_inference_model=...)`.
- **Add new tests** for the connector-kwarg-wins-over-fallback path + the both-None-falls-to-silence path. Likely 4-6 new tests post-cull.
- `_empty_settings()` helper at line 125 retired (Settings has no inference fields).
- Settings-warning lifespan test: a new test in `tests/test_config.py` (or wherever lifespan is tested) using `caplog` to verify the warning fires under `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID=set` + does not fire under unset.

**(d) Tests delta** (architect cycle-1 revised net):
- Cull approx 10-12 settings-path tests from `test_connectors_inference.py`
- Add 4-6 new connector-kwarg-path tests
- Add 1 settings-warning lifespan test
- **Net**: -5 to -7 from `test_connectors_inference.py` rework
- L3 backend test count target: **L2 baseline 2790 − 6 net = 2784 ± 2**

L1+L2+L3 cumulative backend test count target: **2783 + 7 − 6 = 2784 ± 2** (slight net decrease vs F12 baseline because settings-path test branches are culled).

**L4 — Connector editor UI: Provider + Model selector row.** Frontend change atomic to L2 + L3's substrate. Surfaces:
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js:455-484` — the always_listen UI was confirmed at this location post-F12 (architect cycle-1). In the always_listen-conditional section (NOT a "tab" — the section is a field-row sub-block within the connector editor's main form), add two new field-rows:
  - **Inference provider** dropdown — sourced from existing `GET /api/providers`. Empty state: "— Use routed agent's LLM —" (covers the `null` fallback case). Selecting a provider populates the connector's `config.inference_provider_config_id`.
  - **Inference model** text input — free-form string. Placeholder text: "e.g. gpt-4o-mini, qwen2.5:7b" (provider-type-aware hint via small render-conditional logic). Populates `config.inference_model`.
- Conditional render: both rows visible only when `always_listen=true` on the connector (matches F7 L11's existing conditional). Hidden under `always_listen=false`.
- The save path (`collectConfig` or equivalent) writes `inference_provider_config_id` + `inference_model` into the connector.config payload alongside other config keys. Empty / unset values save as `null`.
- `data-testid` selectors: `connector-config-inference-provider-select` + `connector-config-inference-model-input`.
- CSS: no new styles — re-uses existing field-row-3-column-info-icon-as-sibling pattern from F5.

**Tests added**:
- Browser test: `tests/browser/test_flow_studio_connector_inference_provider_row.py` covering:
  - Conditional render (visible under `always_listen=true`, hidden under `always_listen=false`)
  - Provider dropdown populates from `/api/providers` (seeds at least 2 providers)
  - Selecting a provider + entering a model + save round-trips through the connector's config
  - Clearing the provider selection saves `null` (defaults back to routed-agent-LLM fallback)
- 4-6 browser tests; spec target browser count **443 + 4-6 = 447-449**.
- Existing browser tests that touch the connector editor (the F7 L11 always_listen tests) verified against the new always-listen-conditional section (no regression).

**Behavior-test spec authored inline during L4 design** *(operator-directed at planning)*: per `.claude/skills/behavior-test/AUTHORING.md`, L4's design phase authors `tests/behavior/connector-inference-provider-config-roundtrip.md` (Witnessed pattern; browser MCP apparatus). The spec exercises: navigate to Studio → open connector editor → enable `always_listen=true` → verify Provider + Model rows visible → select a provider from dropdown + enter a model → save → reopen connector → verify provider+model persisted. Run via `/behavior-test connector-inference-provider-config-roundtrip` after L4 lands and before L6 HAT — catches UI-flow regressions the unit browser tests don't.

**L5 — Audit-log inspector backend + Chat UI panel.** Atomic backend + frontend leg. **L5 recon step dropped at planning** (operator confirmed Discord-originated sessions ARE reachable from the Chat UI session picker today; no session-picker widening needed).

**(a) Backend** (architect cycle-1 correction — DO NOT extend the shared `_session_summary()` helper at `api.py:3246`): attach `session_metadata` ONLY on the detail-endpoint composition at `api.py:3195-3198`. The composition becomes `{**_session_summary(session), "messages": [...], "session_metadata": session.session_metadata}`. The shared helper at line 3246 stays untouched — `list_chat_sessions` (line 3185), `create_chat_session` (line 3209), `update_chat_session` (line 3223) keep their existing summary-only response shape.

**(b) Frontend**: Chat UI per-session panel. Surfaces:
- `the_one/interfaces/web/static/js/areas/chat.js` (or a new sibling module — implementer's call at L5 design time) — add a collapsible "Routing audit" section below the session message list (OR as a side panel; layout decision deferred to L5 design)
- **Scope**: panel renders entries from `session_metadata["routing"]` ONLY per operator decision at Phase 5b. Other keys (`audit`, future `routing_override`) are NOT rendered in F13.
- Per-entry render: a row showing timestamp (formatted), agent name (or "—" for `no-eligible`), scope (channel/thread/dm/peer/override/default/first-eligible), reason, **disposition badge** (`stepped` / `command-intercepted` / `no-eligible` / `policy-silent` with distinct CSS classes for color coding)
- Per-entry expansion: click reveals the full entry's raw fields (rule_index, match, intercept_source). For `policy-silent` entries, the expansion shows the nested `policy` dict: `outcome` (e.g. `inference-yes` / `inference-no` / `always-listen-off`), `inference_provider_id`, `inference_model`, `account_always_listen`, `agent_always_listen`
- Empty state: "No routing decisions yet" when `session_metadata["routing"]` is empty or unset
- **Real-time updates**: deferred (architect cycle-1 suggestion). MVP shape — panel fetches on open + explicit "Refresh" button. Future flight can wire a routing-update WebSocket event. Avoids re-fetching session-detail on every inbound message (which would be wasteful for chatty Discord connectors).
- CSS: leverages existing color tokens for the disposition badges (success / muted / warning / accent per token_definitions.py regression test)

**Tests added**:
- Browser test: `tests/browser/test_flow_chat_routing_audit_panel.py` covering:
  - Panel renders empty state for a session with no routing entries
  - Panel renders 1+ entries for a session with seeded routing data (multiple dispositions)
  - Per-entry expansion reveals the raw fields
  - `policy-silent` entries expand to show the nested policy dict
  - Disposition badges have the correct CSS class per disposition value
  - Refresh button re-fetches on click
- If session-picker widening folded into L5: 1-2 additional browser tests verifying Discord-originated sessions surface in the picker
- Backend test: a new test in `tests/test_db_api.py` (or wherever `GET /api/chat/sessions/{id}` is tested) verifying `session_metadata` is present in the detail response + absent in the list response (verifies the composition-only-on-detail correction).
- 5-7 browser tests + 1-2 backend tests (session-picker tests dropped — recon eliminated at planning); spec target browser count after L5 **447-449 + 5-7 = 452-456**; backend target after L5 **L3 baseline 2784 + 1-2 = 2785-2786**.

**(c) Behavior-test spec authored inline during L5 design** *(operator-directed at planning)*: per `.claude/skills/behavior-test/AUTHORING.md`, L5's design phase authors `tests/behavior/audit-log-inspector-renders-routing-entries.md` (Witnessed pattern; browser MCP apparatus). The spec exercises: navigate to Chat UI → open a session seeded with multi-disposition routing entries → verify panel renders with disposition badges → click an entry to expand → verify raw fields visible → for `policy-silent` entry, verify nested `policy` dict expansion shows `outcome` + `inference_provider_id` + `inference_model`. Run via `/behavior-test audit-log-inspector-renders-routing-entries` after L5 lands and before L6 HAT — catches UI-flow regressions the unit browser tests don't.

**L6 — Slash-command HAT against real Discord.** Operator-driven verification leg. No code changes (unless regression fix needed). **Pre-HAT gate**: both behavior tests (`connector-inference-provider-config-roundtrip` + `audit-log-inspector-renders-routing-entries`) must pass via `/behavior-test` BEFORE L6 HAT begins. Operator runs both behavior tests after L5 lands; only after both verdicts are `pass` does the operator schedule the live-Discord walkthrough. Surfaces:
- Operator opens a real Discord client connected to a guild where the-one's bot is invited
- Operator-driven walk through 6 slash commands (`/agents`, `/talk_to <agent_name>`, `/whoami`, `/new`, `/reset`, `/help`)
- For each command, operator confirms: (a) Discord registers the command (visible in Discord's slash-command UI), (b) invocation produces the expected response in the channel (current behavior is channel-visible per operator's verify-only decision), (c) per-(agent, peer) permission gating is exercised — `/talk_to` to an agent the peer is not allowed to interact with returns the appropriate denial
- HAT report appended to flight log L6 entry (`## Session Notes` subsection, dated), citing each command's verified behavior + any anomalies surfaced. Report follows F8 L11 + F12 L5 HAT-report shape — one section per command, with command-input + expected + actual + verdict.
- If anomalies surface that are F13-caused (regression vs F12 baseline): fix in-leg (this is acceptance-criteria territory, not divert). If anomalies are pre-existing (carried from F8/F9/F10/F11/F12): file as Known Issue + defer to next slash-touching flight.
- L6 explicitly does NOT modify code unless an in-leg regression fix is needed. The leg's outputs are the HAT report and the operator's verification.

**No tests added in L6**. The HAT report is the verification.

### Checkpoints

- [x] **L1 land**: backend test suite green at 2783 (no test count change — L1 is structural); browser test suite green at 443; `the_one/agents.md` M11 section (lines 405-431) has 2 new convention blocks (`column-aware-index-create-for-rewind-paths` + `test-translator-helpers-for-shape-evolution`) as siblings to existing 4 (`dms-orthogonal-to-guild-restriction`, `backend-merged-replay`, `two-symmetric-paths-in-acl`, `studio-event-bus`); `tests/_acl_shape_helpers.py` exists + is imported by 4+ test files; `git grep -nE "DEFAULT_TEST_GUILD_ID = " tests/` returns ONE definition (in `_acl_shape_helpers.py`) plus imports
- [x] **L2 land**: backend test suite green at **2790** (exact target — 5 TestSchemaV26 + 2 TestPerAgentDmAllowedStrictRejection); migration test suite green including new `TestSchemaV26`; `connector.config` accepts the 2 new optional keys; per-agent `peers[*]` validator REJECTS `dm_allowed`; `CURRENT_VERSION = 26` in `schema.py:15`; v26 migration log fires `logger.info` per always_listen=true connector at migration time; ACL helper updates verified via `git grep -nE 'dm_allowed' the_one/connectors/_acl.py` returning only account-scope read sites at `_admits_inbound_dm:496`; 2 prior tests (TestSchemaV8::test_v8_fresh_db_includes_tool_configs + TestSchemaV22::test_v22_legacy_row_without_allowlist_untouched) updated for v26 (CURRENT_VERSION bump + every-connector inference-key addition)
- [x] **L3 land**: backend test suite green at **2784 ± 2** (L2 baseline 2790 minus 6 from `test_connectors_inference.py` rework — cull 10-12 settings-path tests + add 4-6 connector-kwarg-path tests + 1 settings-warning lifespan test); `Settings.inference_provider_config_id` + `Settings.inference_model` removed from `the_one/config.py`; dispatcher reads from `account.config.inference_provider_config_id` (verified at `_inbound.py:269+`); `_resolve_inference_provider` signature changed (no `settings` param; new `connector_inference_*` kwargs); FastAPI lifespan hook fires env-var warning if `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` or `THE_ONE_INFERENCE_MODEL` is set; `git grep -nE "settings\.inference_" the_one/ tests/` returns zero hits in source files
- [x] **L4 land**: browser test suite green at **448** (5 new tests for inference provider + model row); connector editor renders Provider + Model rows under `always_listen=true` (location verified at `connector-editor.js:455-484`); rows hidden under `always_listen=false`; save round-trips through `connector.config.inference_provider_config_id` + `inference_model`; `tests/behavior/connector-inference-provider-config-roundtrip.md` spec authored + committed
- [x] **L5 land**: browser test suite green at **452-456** (5-7 new tests for audit-log inspector); backend test suite at **2785-2786** (1-2 new tests for session-detail `session_metadata` exposure + absence in list); Chat UI per-session "Routing audit" panel renders with disposition badges + per-entry expansion; empty state handled; explicit Refresh button (no auto-poll per architect cycle-1 suggestion); `tests/behavior/audit-log-inspector-renders-routing-entries.md` spec authored + committed
- [x] **Pre-L6 behavior-test gate**: both behavior tests PASS on run 2026-05-31-23-56-31 — L4 spec 8/8 (post-enhancement, includes Step 8 `(custom)` fallback verification); L5 spec 7/7. Run-1 was contaminated by stale browser cache (L5 specifically) and surfaced a real product bug in the L4 model-dropdown enhancement (recapture-on-no-provider broke GUI clear+save) — both resolved before run-2. Run logs at `tests/behavior/*/runs/*.md`.
- [~] **L6 land**: HAT walkthrough attempted; AC-1 (`/agents`) returned "No agents available" → diagnostic walk surfaced 4 pre-existing ACL/slash-sync defects (configured `config.guilds` vs `allowlist.guilds` semantic split; channel allowlist holds category id; Discord plugin doesn't pass `member_roles`; `_commands.py:_permitted_agents` calls `admits_inbound` without `guild_id`/`is_dm`/`member_roles` — broken since F7, unmasked by F12). None are F13-caused. All filed as a single cluster Known Issue in `mission.md` for the follow-on flight to address as a unit. AC-2..AC-6 not exercised (BLOCKED on the same defect). M11 criterion #10 stays open.
- [x] **Flight land**: L1-L5 committed at `20615fc` + pushed; draft PR #82 opened. L6 committed separately with HAT report + bookkeeping + 4-bug Known Issue cluster. No new flakes from F13. 2 pre-existing browser failures (since pre-F10) still present (not F13-caused). F12 carry-forward action items closed at L1+L2.

### Adaptation Criteria

**Divert if**:
- L1's `_acl_shape_helpers.py` extraction surfaces a fundamental shape mismatch between the 4+ test files (e.g. one file's `_to_v24_shape` accepts a different input shape than another) — split L1 into L1a (extract per-file with no consolidation) + L1b (reconcile shape mismatches in a separate leg)
- L2's v26 migration surfaces a row that fails the strict-per-agent-`dm_allowed`-rejection validator after row-rewrite (e.g. operator's seeded data has hand-edited per-agent peers carrying the field with extra metadata) — split into v26-row-rewrite + v27-validator-tightening, OR pre-clean during v26
- L3's `test_connectors_inference.py` rework surfaces more settings-path tests than the architect cycle-1 enumeration (15 occurrences across 7 sites) — fold the additional cull/rewrite into L3 if discovered; if scope doubles, split into L3a (Settings removal + dispatcher refactor) + L3b (test file rework)
- L4's Provider dropdown population fails because `/api/providers` returns no providers (operator hasn't configured one) — escalate to operator to seed a provider before continuing
- L5's `session_metadata` size grows large enough that the session-detail endpoint hits perf concerns (>1MB response per session) — fold a paginated routing-entries endpoint into L5 OR split into L5a (composition-only-on-detail) + L5b (paginated endpoint)
- Either behavior-test spec fails on first run after the owning leg lands — fix in-leg before signaling [HANDOFF:review-needed] (treats behavior-test verdict as part of leg acceptance criteria)
- L6 surfaces F13-caused regressions in slash-command behavior that go beyond simple in-leg fixes — split into L6a (HAT documentation) + L6b (slash-command regression fixes)

**Acceptable variations**:
- L1 may discover additional translator-helper sites the grep undercounted (similar to F11/F12's recon undercount patterns); fold into L1 in lockstep
- L2 may discover additional ACL helper consumer sites that reference per-agent `dm_allowed` beyond the spec's enumeration; fold into L2 in lockstep
- L3 may discover that `test_connectors_inference.py`'s settings-path tests have already been partially rewritten by some prior flight (unlikely); reduce cull scope correspondingly
- L4 may discover that the connector editor's always_listen location has drifted from `connector-editor.js:455-484` (e.g. F12 L5 moved it during the hierarchical-UI restructure) — adjust placement at L4 design time
- L5 layout decision (collapsible-below vs side-panel) deferred to L5 design time after L4 lands
- L6 HAT may discover Discord-side rate-limiting or registration delays — file as Known Issue, defer fix to F14 (HAT script flight) where retry + backoff substrate is in scope

### Legs

- [x] `methodology-foldins-and-shared-test-helpers` — F12 carry-forward; extract `tests/_acl_shape_helpers.py` consolidating translator helpers from 4+ test files; codify `column-aware-index-create-for-rewind-paths` + `test-translator-helpers-for-shape-evolution` in `agents.md` M11 section (siblings to existing 4 convention blocks at lines 405-431); mechanical structural no-op
- [x] `schema-v26-and-validator-tightening` — schema v26 row-rewrites `connectors.config` (add 2 new inference keys, default `None`; log per always_listen=true connector) + `agents.connector_acls` (strip per-agent `dm_allowed` via `dict.pop`); Pydantic validators tightened (account-scope accepts new inference keys; per-agent peers REJECT `dm_allowed`); ACL helper update for stripped per-agent peers shape; TestSchemaV26 (5 tests) + per-agent strict-rejection (2 tests); inline `dm_allowed` fixture cleanups in 3 enumerated test files; fixture auto-updates via L1 shared helper
- [x] `settings-removal-and-dispatcher-inference-source-refactor` — remove `Settings.inference_provider_config_id` + `Settings.inference_model`; `_resolve_inference_provider` signature change (drop `settings` param; add `connector_inference_*` kwargs); dispatcher reads from `account.config` at `_inbound.py:269+`; FastAPI lifespan hook fires env-var warning if either env var set; **cull** `test_connectors_inference.py`'s settings-path test branches (lines 219-330 + 560-630) + add 4-6 new connector-kwarg-path tests + 1 lifespan-warning test; net backend test delta -6
- [x] `connector-editor-inference-provider-and-model-row` — Studio connector editor's always_listen-conditional section (location verified at `connector-editor.js:455-484`) gains Provider dropdown + Model input rows; conditional on `always_listen=true`; save round-trips through `connector.config`; 4-6 new browser tests; **authors `tests/behavior/connector-inference-provider-config-roundtrip.md` spec inline**
- [x] `audit-log-inspector-backend-and-chat-ui-panel` — detail-endpoint composition at `api.py:3195-3198` attaches `session_metadata` (shared `_session_summary()` UNTOUCHED); Chat UI per-session "Routing audit" panel renders `session_metadata["routing"]` entries ONLY (other keys explicitly out of scope); disposition badges + per-entry expansion + nested policy-dict expansion for `policy-silent` entries; explicit Refresh button (no auto-poll); 5-7 new browser tests + 1-2 backend tests; **authors `tests/behavior/audit-log-inspector-renders-routing-entries.md` spec inline**
- [~] `slash-command-hat-against-real-discord` *(operator-driven; landed PARTIAL)* — HAT walkthrough attempted on 2026-06-01; AC-1 `/agents` blocked by pre-existing `_commands.py:_permitted_agents` defect + 3 sibling ACL/slash-sync surface bugs. Filed as Known Issue cluster in mission.md for follow-on flight. AC-2..AC-6 not exercised. Diagnostic value of L5's routing-audit panel proved out (surfaced the `command-intercepted` entry that isolated the bug to the command handler, not the dispatcher).

---

## Post-Flight

### Completion Checklist

- [ ] L1-L6 legs completed
- [ ] Code merged
- [ ] Backend test suite: **2785-2786** passed / 4 skipped / 0 errors / 0 failures (L1 baseline 2783 → L2 +7 = 2790 → L3 -6 = 2784 → L5 +1-2 = 2785-2786; L4 + L6 add no backend tests)
- [ ] Browser test suite: **452-456** passed (2 pre-existing-main failures preserved); L4 adds 4-6, L5 adds 5-7
- [x] Both behavior tests pass: `tests/behavior/connector-inference-provider-config-roundtrip.md` (PASS 8/8 — L4 enhancement adds Step 8) + `tests/behavior/audit-log-inspector-renders-routing-entries.md` (PASS 7/7)
- [ ] Migration test suite green including `TestSchemaV26`
- [ ] `the_one/agents.md` M11 section has both new convention blocks at lines 405-431 (siblings to existing 4)
- [ ] `tests/_acl_shape_helpers.py` exists + imported by 4+ test files
- [ ] `Settings.inference_provider_config_id` + `Settings.inference_model` removed from `the_one/config.py`
- [ ] `_resolve_inference_provider` signature: no `settings` param; `connector_inference_*` kwargs
- [ ] FastAPI lifespan hook logs env-var deprecation warning when present
- [ ] Connector editor renders Provider + Model rows conditional on `always_listen=true`
- [ ] Chat UI per-session "Routing audit" panel renders `session_metadata["routing"]` entries for any reachable session
- [ ] Session-detail endpoint includes `session_metadata`; session-list endpoints do NOT (verified)
- [ ] L6 HAT report appended to flight log
- [ ] Mission outline `mission.md` Flight 13 entry marked `[x]` with one-line summary
- [ ] Mission criterion #15 (audit-log inspector) closed; #12 (mentions-aware operator surface) closed; #10 (slash commands) marked `[~]` partial (ephemeral + autocomplete deferred per operator decision)
- [ ] F12 debrief action items marked `[x]`: translator-helpers extraction, 2 conventions codification, per-agent `dm_allowed` retirement

### Verification

Five independent signals confirm the flight achieved its objective:

1. **Mechanical (grep)**:
   - `git grep -nE "DEFAULT_TEST_GUILD_ID = " tests/` returns ONE def + imports (post-L1)
   - `git grep -nE "settings\.inference_provider_config_id|settings\.inference_model" the_one/ tests/` returns zero hits in source files post-L3 (allowed residue: lifespan-warning code that reads via `os.environ.get` directly)
   - `git grep -nE 'dm_allowed' the_one/db/models.py the_one/agent/config.py` returns the account-scope-only validator references (per-agent validator REJECTS the field; account-scope continues to accept it)
   - `git grep -nE 'inference_provider_config_id|inference_model' the_one/interfaces/web/static/js/areas/studio/connector-editor.js` returns the new dropdown + input handlers (post-L4)
   - `git grep -nE 'session_metadata' the_one/interfaces/web/api.py` shows the field attached only at the detail-endpoint composition (not in the shared `_session_summary()` helper)

2. **Regression (test suites)**: backend suite at 2785-2786 passing / 0 errors / 4 skipped; migration test suite green (v26 + all priors); browser suite at 452-456 passing except 2 pre-existing-main failures

3. **Semantic (composition-correctness)**: L3's connector-kwarg-path tests pass — inference resolution under (connector has values / connector None + fallback / both None) matches the documented "connector-wins-falls-back-to-agent" semantic exactly

4. **Witnessed UI flow (behavior tests)**: `/behavior-test connector-inference-provider-config-roundtrip` and `/behavior-test audit-log-inspector-renders-routing-entries` both pass via browser MCP apparatus before L6 HAT begins. These catch UI-flow regressions the unit browser tests don't reach.

5. **Operator (smoke test + L6 HAT)**: operator opens a fresh dev environment, creates a connector, sets the inference provider + model via the connector editor, enables `always_listen=true`, sends a non-mentioned message from Discord — the bot stays silent (policy gate fires); operator opens the Chat UI session panel and sees the routing audit entry with disposition `policy-silent` + the expanded `policy` dict naming the connector's chosen inference provider/model. Operator then runs `/whoami` from Discord — the routing audit shows `disposition="command-intercepted"` for the corresponding session. **L6 HAT** confirms the same flow against real Discord client invocations of all 6 slash commands.
