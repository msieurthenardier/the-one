# Leg: schema-v26-and-validator-tightening

**Status**: completed
**Flight**: [Audit-log inspector + per-connector inference config + slash-command HAT](../flight.md)

## Objective

Land schema migration v26 (`connectors.config` gains `inference_provider_config_id` + `inference_model` keys defaulting to `None`; `agents.connector_acls` per-agent `peers[*]` lose the `dm_allowed` key), tighten the Pydantic validators in lockstep (account-scope `connector.config` accepts the two new optional inference keys; per-agent `peers[*]` REJECTS `dm_allowed`), update the L1 shared helper to stop emitting `dm_allowed` on per-agent peers, scrub all remaining per-agent inline `dm_allowed` writes in tests, and update `the_one/connectors/_acl.py` docstrings/comments to reflect the per-agent-doesn't-carry-`dm_allowed` reality — paired with L3 across the v26 commit boundary.

## Context

- **Flight Technical Approach L2 sub-parts (a)–(f)** in `flight.md`: substrate-only leg pairing with L3 across the v26 commit boundary. This leg owns the schema migration, the two validator changes, the ACL helper docstring update, the L1 helper-emit retirement, the per-agent inline `dm_allowed` fixture cleanup, and the TestSchemaV26 + TestPerAgentDmAllowedStrictRejection test classes.
- **F12 footgun retirement**: per-agent `peers[*].dm_allowed` was added in F12 L3 for "structural uniformity" with account-scope. F12's debrief Architect + Developer crews both independently flagged it as a footgun ("structurally uniform but NOT consulted by ACL per the F12 L3 DM Composition Truth Table"). v26 deletes it from storage; the per-agent validator strictening enforces post-v26; the F12 footgun cannot reappear silently.
- **`v26 Backfill is None` Design Decision** (`flight.md` Design Decisions): NO backfill from current `Settings.inference_provider_config_id` env-var value. Existing connectors get explicit `None` defaults. Operator edits per-connector via UI post-migration. Connectors with `always_listen=true` BUT `inference_provider_config_id=None` fall through to the routed agent's LLM (current F7 fallback path). v26 migration emits a `logger.info` for each always_listen connector at migration time so operator sees the runtime-behavior shift at startup.
- **`Strict Validator Post-v26` Design Decision**: per-agent `connector_acls[*].peers[*]` REJECTS `dm_allowed`. Mirrors F12 L5's `guild_id`-required tightening pattern. Account-scope `connector.config.allowlist.peers[*]` is unchanged (still carries `dm_allowed`).
- **`F12 Fold-Ins — Migration-Bundled Cleanup` Design Decision**: v26 strips per-agent `dm_allowed` BUNDLED into the same migration that adds the inference keys, because v26 is already touching `agents.connector_acls` JSON.
- **L1 post-state** (per L1 leg artifact + flight log L1 LANDED entry): `tests/_acl_shape_helpers.py` exists; both `_to_v24_shape` and `_to_v24_agent_acl` emit `dm_allowed: True` on per-agent peer entries — this is the status quo L2 retires. Per the L1 artifact's Context: "L2 then (a) updates the shared helper to stop emitting `dm_allowed` on per-agent peers, (b) adds the validator change that REJECTS the field, (c) runs the v26 migration that strips it from stored data — in lockstep, single atomic boundary."
- **L1 also confirmed** post-L1 inline `dm_allowed` writes in `tests/test_connectors_routing.py`, `tests/test_connectors_commands.py`, `tests/browser/seeders.py` are ZERO (helpers deleted carried them away); writes remain in `tests/test_db_repositories.py`, `tests/test_db_api.py`, `tests/test_db_migration.py`, `tests/test_connector_history_tools.py`, `tests/test_connectors_discord.py`, `tests/browser/test_flow_studio_per_peer_dm_toggle.py`. L2 recon (below) categorized each remaining site as account-scope (KEEP) vs per-agent (REMOVE).
- **`two-symmetric-paths-in-acl` convention** (F11 lesson #5, F12 L2 codification; pulled-forward methodology lesson #4): when touching `_acl.py`, both `_admits_inbound_dm` AND `_admits_inbound_guild` are checked in lockstep. L2 recon verified that NEITHER function consumes per-agent `dm_allowed` today — both iterate per-agent peers via `p["id"] == peer_id` only, never `p["dm_allowed"]`. So the L2 code-level work in `_acl.py` is docstring/comment updates only (no runtime-code changes); the convention's lockstep requirement is satisfied trivially.
- **`_resolve_inference_provider`-signature work is L3's surface, NOT L2's**: this leg widens the validator to ACCEPT the new keys but does NOT plumb them into the dispatcher. The dispatcher (L3) reads the keys from `account.config` and passes them as kwargs to the inference resolver. L2 is substrate-only.
- **Pulled-Forward methodology lessons applied**:
  - #1 + #2 (grep-gate scope is a design decision + Phase 5c architect cycle): the post-L2 verification gates enumerate the allowed `dm_allowed` residue explicitly (only account-scope sites remain).
  - #3 (separate test-surface from production-surface recon): the L2 recon enumerates per-agent `dm_allowed` write sites separately from account-scope ones.
  - #4 (two-symmetric-paths-in-acl): both `_admits_inbound_dm` and `_admits_inbound_guild` verified at recon.
  - #6 (mechanical-prereq-leg-before-semantic-changes): L1 (helpers extraction; structural no-op) preceded this leg.

## Inputs

What exists before this leg runs:

- Branch `flight/13-audit-log-inspector-and-connector-inference-config` checked out from main at commit `26a0ddf` (F13 planning commit; F12 already landed at `9f4df4a`), with L1's uncommitted-since-`26a0ddf` edits carried forward in the working tree (per `/agentic-workflow` Phase 2d batching protocol).
- Backend test suite passes at **2783 passed / 4 skipped / 0 errors / 0 failures** (verified at L1 LANDED — structural no-op preserved baseline).
- Browser test suite passes at **443 passed / 35 skipped / 12 deselected / 2 pre-existing-main failures** (unchanged from pre-L1).
- `tests/_acl_shape_helpers.py` exists with `_to_v24_agent_acl` EMITTING `dm_allowed: True` on bare-string per-agent peer entries (the L1 status quo this leg retires).
- `the_one/db/schema.py:12` — `CURRENT_VERSION = 25`.
- `the_one/db/schema.py:1419-1565` — the v25 block (last migration block), ending with `version = 25` at line 1565. v26 inserts immediately after this line.
- `the_one/db/models.py:193-623` — the `_validate_config_reserved_keys` validator on `Connector.config`. The reserved-key validators (`pairing`, `allowlist`, `routing`, `always_listen`) are each `if "X" in value: …`-gated; `always_listen` validation is at `:604-611`. The validator strips legacy `auto_relay_platform_replies` at `:621`.
- `the_one/agent/config.py:267-461` — the `_validate_connector_acls` validator on `AgentConfig.connector_acls`. Per-agent `peers[*]` validation block at `:374-412` requires the structured shape `{id: str, dm_allowed: bool}` — both keys REQUIRED today. Post-L2: ONLY `{id}`; presence of `dm_allowed` is REJECTED.
- `the_one/connectors/_acl.py` (740 LOC): the only runtime read of `dm_allowed` is at `:491` inside `_admits_inbound_dm` (account-scope under the `admin-approved` policy). Per-agent peer iteration at `:516` (in `_admits_inbound_dm`) and `:654` (in `_admits_inbound_guild`) iterates via `p["id"] == peer_id` only — no `dm_allowed` read. Other `dm_allowed` mentions (`:11, :238, :240, :316, :406, :417, :422, :426, :481, :494, :498, :546`) are in docstrings/comments.

## Outputs

What exists after this leg completes:

- **`the_one/db/schema.py`**:
  - `CURRENT_VERSION = 26` (bumped from 25).
  - NEW migration block `if version < 26:` immediately after the v25 block (after `version = 25` at line 1565), implementing two row-rewrite passes plus the version stamp + commit + `version = 26`:
    - **Pass A** — for each row in `connectors`: parse `config` JSON; if `inference_provider_config_id` key absent, set `inference_provider_config_id = None` AND `inference_model = None`; track `changed = True`; if `config.get("always_listen") is True` at row-read time, emit `logger.info("v26: connector %s (%s) inherits None inference defaults; edit per-connector via Studio connector editor", connector_id, connector_label)`; UPDATE only when `changed`.
    - **Pass B** — for each row in `agents`: parse `connector_acls` JSON; for each `connector_acls[acct_id]` payload, iterate `payload["peers"]` list and call `entry.pop("dm_allowed", None)` per entry; track `changed = True` only when a pop actually removes the field (mirrors the v25 `UPDATE-only-when-changed` pattern at `schema.py:1463-1474`); UPDATE only when `changed`.
  - Module-level `import logging` + `logger = logging.getLogger(__name__)` added at the top of the file (currently absent — verified at recon).
- **`the_one/db/models.py`** (`_validate_config_reserved_keys`):
  - Two new shape-validators appended after the `always_listen` block (around `:611`, before the `auto_relay_platform_replies` strip at `:621`):
    - `if "inference_provider_config_id" in value: …` — must be `str | None`; non-string-non-None values REJECTED.
    - `if "inference_model" in value: …` — must be `str | None`; non-string-non-None values REJECTED.
  - Docstring updated to mention the two new optional reserved keys.
- **`the_one/agent/config.py`** (`_validate_connector_acls`, peers branch at `:374-412`):
  - Per-agent peers `extra_keys` check changed from `item_keys - {"id", "dm_allowed"}` to `item_keys - {"id"}` — `dm_allowed` is now an EXTRA key → REJECTED.
  - Per-agent peers `missing_keys` check changed from `{"id", "dm_allowed"} - item_keys` to `{"id"} - item_keys` — `dm_allowed` no longer required.
  - The `not isinstance(item["dm_allowed"], bool)` branch DELETED entirely (the field is now rejected upstream by the extra-keys check).
  - Error message on the extra-keys failure path includes the F12 footgun retirement wording: "per-agent peer entries must not carry `dm_allowed`; the per-peer DM toggle is account-scope only (F12 footgun retirement, F13 L2)" — wired in via the existing error format (the current code emits `f"connector_acls[{account_id!r}]['peers'][{i}] has unexpected keys: {sorted(extra_keys)}"`; either keep the existing format AND let the message naturally surface `['dm_allowed']` OR replace the f-string with an explicit two-line message — recon at implementation time picks the most ergonomic shape).
  - Docstring updated: the per-agent peers section currently says "list[{id: str, dm_allowed: bool}] (per-agent ``dm_allowed`` is structurally uniform with account-scope but NOT consulted by the ACL helpers — DM admission is decided at account scope per the F12 L3 Truth Table)" → updated to "list[{id: str}] (post-F13 L2: ``dm_allowed`` is REJECTED on per-agent peer entries — the F12 footgun is retired; DM admission is decided exclusively at account-scope per-peer)".
- **`the_one/connectors/_acl.py`** (docstring-only changes — no runtime code edits):
  - Module-level docstring at `:11` updated: `peers: list[{id: str, dm_allowed: bool}]` → split into two lines, one for account-scope (`list[{id: str, dm_allowed: bool}]`) and one for per-agent (`list[{id: str}]`).
  - `admits_dm_peer` docstring at `:238` — clarify the structured-dict consumption is identical at both scopes EXCEPT per-agent doesn't carry `dm_allowed`.
  - **`admits_inbound` (public dispatcher) docstring at `:316`** — keep the `peer.dm_allowed` reference (still consumed at account-scope by `_admits_inbound_dm`); the docstring already describes account-scope behavior so the existing wording is correct post-L2.
  - `_admits_inbound_dm` docstring at `:406, :417, :422-428` — the Truth Table itself is unchanged (account-scope `peer.dm_allowed` is the consumed signal); the "Per-agent peers entries' `dm_allowed` field is NOT consulted" paragraph at `:422-428` is rewritten to say "Per-agent peers entries DO NOT carry a `dm_allowed` field (F13 L2 — F12 footgun retirement). Per-agent DM granularity would require a substrate change."
  - `_admits_inbound_guild` docstring at `:546-547` — drop the `"the dm_allowed field is consulted only by _admits_inbound_dm"` parenthetical (per-agent peers don't carry it anymore; only account-scope does, which is `_admits_inbound_dm`'s concern).
- **`tests/_acl_shape_helpers.py`** — `_to_v24_agent_acl` updated:
  - The peers bare-string branch (`peers_new.append({"id": entry, "dm_allowed": True})` at `:112`) changes to `peers_new.append({"id": entry})`.
  - The peers tuple branch (`peers_new.append({"id": entry[0], "dm_allowed": entry[1]})`) changes to `peers_new.append({"id": entry[0]})` — the tuple-second-element value is DROPPED at the helper boundary (per-agent peers can't carry `dm_allowed`; if a fixture passes a tuple, the helper warns by silently dropping the second element).
  - The peers dict-pass-through branch (`peers_new.append(entry)`) stays — but post-L2 if a fixture passes `{"id": ..., "dm_allowed": ...}` dict, the validator will REJECT it downstream. The helper does NOT strip the field on dict-pass-through (intentional — the helper is a fixture translator, not a validator; fixtures using dict shape are expected to already be in the post-L2 shape).
  - Docstring updated: the `_to_v24_agent_acl` docstring is rewritten to drop the "emits dm_allowed: True on bare-string peer entries" lines and replace with "post-F13 L2: per-agent peers entries are bare `{id: str}` dicts; the `dm_allowed` field is REJECTED at per-agent scope (F12 footgun retirement via the v26 migration + Pydantic validator)."
- **`tests/test_db_repositories.py`** — per-agent inline `dm_allowed` writes scrubbed:
  - Per-agent (need REMOVAL of `dm_allowed` from each peer dict):
    - `:294, :295` (line ~289-302 — `TestSQLiteAgentStore` agent ACL round-trip)
    - `:309, :310` (load-back assertion)
    - `:327, :336` (upsert path)
    - `:493` (validator-firing test setup)
    - `:758, :779` (further per-agent ACL test)
    - `:904, :905, :916, :917` (TestAgentConfigConnectorAclsValidator populated test)
    - `:965, :972` (further ACL validator tests)
    - `:1072, :1081` (further ACL tests)
  - Account-scope (KEEP `dm_allowed` — verified at recon by `Connector(config={"allowlist": ...})` surrounding context):
    - `:1647, :1648, :1811, :1812, :1920, :1961, :1962, :1963, :2017` (all in `TestConnectorConfigValidator`, ~`:1620+`).
- **`tests/test_db_api.py`** — per-agent inline `dm_allowed` writes scrubbed:
  - Per-agent (need REMOVAL — inside `connector_acls={account_id: {…}}` envelopes):
    - `:1616, :1617, :1618` (POST `/api/agents` `connector_acls`)
    - `:1666, :1667, :1668` (response assertion mirror)
    - `:1709` (Agent B `connector_acls`)
    - `:1732` (response assertion mirror)
  - Account-scope (KEEP — inside `config={"allowlist": {…}}` or `_create_account(client, config=…)`):
    - `:1512, :1531, :2043, :2209, :2229, :2355`.
- **`tests/test_db_migration.py`** — per-agent inline `dm_allowed` writes updated to reflect post-v26 storage shape:
  - Per-agent (need REMOVAL — assertions/seeds inside `agents.connector_acls` JSON):
    - `:3527, :3539` — recon classified as ACCOUNT-SCOPE (`Connector.model_validate({"config": {"allowlist": …}})` at `:3520-3540`), KEEP. Re-verify the surrounding 5-10 lines at implementation time per Edge Case 3.
    - `:3956, :3957` — per-agent assertion in `test_v24_agents_connector_acls_rewrite` (acct-1 peers); the v24 rewrite under v26 still SETS `dm_allowed: True` then v26 in the SAME `ensure_schema` pipeline STRIPS it; assertion updates to `[{"id": "U1"}, {"id": "U2"}]`.
    - `:4270, :4313` — per-agent seed + assertion in `test_v25_agents_connector_acls_orphan_deletion`. The seed at `:4270` is v25-shape (structured dict `{"id": "U1", "dm_allowed": True}` — NOT v23-flat shape) representing legitimate pre-v26 stored data. **Decision (per cycle-1 review)**: keep the seed UNCHANGED so the test exercises v26's strip of legitimate post-v25 stored data; update ONLY the post-pipeline assertion at `:4313` from `[{"id": "U1", "dm_allowed": True}]` → `[{"id": "U1"}]`.
  - Account-scope (KEEP — inside `Connector.model_validate` or seeded as `connectors.config.allowlist`):
    - `:2876, :2955, :3527, :3539` (account-scope per recon; double-check at implementation time), `:3788, :3789, :3802, :3815, :3816, :3831, :3832, :3956-3957` (account-scope per recon — but :3956-3957 is per-agent; verify), `:4099, :4148`.
  - **NOTE — categorization caveat**: `:3527, :3539` need re-verification at implementation time. The recon classified them as account-scope (`Connector.model_validate({"config": {"allowlist": {"peers": [{"id": "U1", "dm_allowed": True}], …}}})` at `:3520-3540`), KEEP. The `:3956, :3957` are clearly per-agent (`acls = json.loads(row["connector_acls"])` at `:3947`), REMOVE. The implementing agent re-checks all test_db_migration.py sites before editing.
- **`tests/test_connector_history_tools.py`** — `:569` (`allowlist={"peers": [{"id": "user-1", "dm_allowed": True}], …}` for account-scope seed via `_seed_stub_account`): account-scope, KEEP.
- **`tests/test_connectors_discord.py`** — `:1373` (`{"id": peer_id, "dm_allowed": True}` inside an account-scope `Connector` config setup at `:1370-1377`): account-scope, KEEP.
- **`tests/browser/test_flow_studio_per_peer_dm_toggle.py`** — `:158, :236, :282, :310, :353` (all inside `peers=[…]` for `_seed_discord_with_allowlist`, which constructs account-scope allowlist): account-scope, KEEP. The browser test exists specifically to exercise the account-scope per-peer DM toggle UI; per-agent retirement does not touch this surface.
- **`tests/test_db_migration.py`** — NEW `TestSchemaV26` class appended after `TestSchemaV25` (`:3999+`, ending around `:4393`) with 5 tests:
  - `test_v26_fresh_db_shape` — fresh DB → `ensure_schema` → assert (a) `CURRENT_VERSION >= 26`; (b) constructed connector with new keys round-trips; (c) per-agent peers without `dm_allowed` validate cleanly; (d) per-agent peers with `dm_allowed` REJECTED.
  - `test_v26_idempotent_on_rerun` — two `ensure_schema` calls; assert `versions.count(26) == 1`.
  - `test_v26_legacy_v25_row_migration_strips_dm_allowed` — hand-build a v25-shape DB (`schema_version` v1..25, `agents.connector_acls` seeded with per-agent peer entries carrying `dm_allowed: True/False`); call `ensure_schema`; assert post-pipeline per-agent peers have NO `dm_allowed` key.
  - `test_v26_connector_config_inference_fields_added` — hand-build a v25-shape DB with `connectors.config` lacking the inference keys; call `ensure_schema`; assert post-pipeline each connector's config has `inference_provider_config_id: None` + `inference_model: None`.
  - `test_v26_logs_affected_always_listen_connectors` — hand-build a v25-shape DB with one connector at `config["always_listen"] = True` and one at `False`; call `ensure_schema` under `caplog.at_level(logging.INFO, logger="the_one.db.schema")`; assert exactly one `logger.info` line fired mentioning the always_listen-true connector's ID and label, and NONE for the false one.
- **`tests/test_db_repositories.py`** — NEW `TestPerAgentDmAllowedStrictRejection` class appended after `TestAgentConfigConnectorAclsValidator` (`:833-1113`) with 2 tests:
  - `test_per_agent_peers_with_dm_allowed_key_rejected` — `AgentConfig(connector_acls={"acct-a": {"peers": [{"id": "u1", "dm_allowed": True}], "channels": []}})` raises `ValidationError`; the error message references the F12 footgun retirement wording.
  - `test_per_agent_peers_without_dm_allowed_key_accepted` — `AgentConfig(connector_acls={"acct-a": {"peers": [{"id": "u1"}], "channels": []}})` succeeds; round-trips through Pydantic.
- **Test count totals**:
  - Backend: **2790 ± 2** (L1 baseline 2783 + 5 TestSchemaV26 + 2 TestPerAgentDmAllowedStrictRejection = 2790). The per-agent fixture-translator auto-application via the L1 shared helper change does NOT add or remove tests (the same test bodies pass — they just get cleaner peer entries from the helper).
  - Browser: **443 unchanged** (no browser tests added in L2; the `tests/browser/test_flow_studio_per_peer_dm_toggle.py` writes stay because they're account-scope).

## Acceptance Criteria

- [x] **AC-1** (`CURRENT_VERSION` bump): `git grep -n "^CURRENT_VERSION = " the_one/db/schema.py` returns exactly one hit: `the_one/db/schema.py:12:CURRENT_VERSION = 26`.
- [x] **AC-2** (v26 migration block exists): `git grep -n "if version < 26:" the_one/db/schema.py` returns exactly ONE hit (the start of the v26 block); `git grep -n "version = 26$" the_one/db/schema.py` returns exactly ONE hit (the closing assignment of the v26 block).
- [x] **AC-3** (v26 migration idempotency via UPDATE-only-when-changed): the v26 block's two passes each track a `changed` boolean and emit the SQL `UPDATE` ONLY when `changed` (mirrors the v25 pattern at `schema.py:1463-1474`).
- [x] **AC-4** (v26 migration logs affected always_listen connectors): `caplog`-based `TestSchemaV26.test_v26_logs_affected_always_listen_connectors` passes — `logger.info` fires per always_listen=true connector at migration time.
- [x] **AC-5** (account-scope `connector.config` validator widening): `git grep -n "inference_provider_config_id\|inference_model" the_one/db/models.py` returns the new validator-block lines for both keys (each gated on `if "X" in value:` per the existing reserved-keys validator pattern); a `Connector(config={"inference_provider_config_id": "p1", "inference_model": "m1"})` constructs successfully; a `Connector(config={"inference_provider_config_id": 123})` raises `ValidationError`.
- [x] **AC-6** (per-agent peers strict rejection): `git grep -n '"dm_allowed"' the_one/agent/config.py` returns EITHER zero hits OR only hits inside the validator's rejection-related error message and docstring; constructing `AgentConfig(connector_acls={"acct-a": {"peers": [{"id": "u1", "dm_allowed": True}], "channels": []}})` raises `ValidationError`; constructing `AgentConfig(connector_acls={"acct-a": {"peers": [{"id": "u1"}], "channels": []}})` succeeds.
- [x] **AC-7** (`_acl.py` docstring updates — code unchanged): `git diff the_one/connectors/_acl.py` shows ONLY changes to docstrings/comments; the runtime code paths (`_admits_inbound_dm:491` reading account-scope `peer_entry.get("dm_allowed", False)`; per-agent peer iteration at `:516, :654`) are byte-identical to pre-L2.
- [x] **AC-8** (L1 shared helper updated): `git grep -nE 'dm_allowed' tests/_acl_shape_helpers.py` returns hits ONLY inside `_to_v24_shape` (account-scope helper, keeps the field on all 3 branches) plus the module's docstring example for `_to_v24_shape`. Specifically `_to_v24_agent_acl`'s body has ZERO `dm_allowed` hits.
- [x] **AC-9** (per-agent inline `dm_allowed` writes scrubbed): `git grep -nE '"dm_allowed":\s*(True|False)' tests/ --include='*.py'` returns hits ONLY in the enumerated allowed-residue set:
  - `tests/_acl_shape_helpers.py` — inside `_to_v24_shape` (account-scope) and its docstring examples.
  - `tests/test_db_repositories.py:1647, 1648, 1811, 1812, 1920, 1961, 1962, 1963, 2017` — account-scope (`TestConnectorConfigValidator`).
  - `tests/test_db_api.py:1512, 1531, 2043, 2209, 2229, 2355` — account-scope (`config={"allowlist": …}` envelopes).
  - `tests/test_db_migration.py:2876, 2955, 3527, 3539, 3788, 3789, 3802, 3815, 3816, 3831, 3832, 4099, 4148` — account-scope (within `connectors.config.allowlist` reads/seeds). (Line numbers may drift slightly during edits to add the TestSchemaV26 class — the spirit is that ALL remaining hits are account-scope.)
  - `tests/test_connector_history_tools.py:569` — account-scope.
  - `tests/test_connectors_discord.py:1373` — account-scope.
  - `tests/browser/test_flow_studio_per_peer_dm_toggle.py:158, 236, 282, 310, 353` — account-scope.
  - **Zero per-agent inline writes** post-L2 (per-agent ones at `tests/test_db_repositories.py:294, 295, 309, 310, 327, 336, 493, 758, 779, 904, 905, 916, 917, 965, 972, 1072, 1081`, `tests/test_db_api.py:1616, 1617, 1618, 1666, 1667, 1668, 1709, 1732`, `tests/test_db_migration.py:3956, 3957, 4270, 4313` REMOVED).
- [x] **AC-10** (`TestSchemaV26` class added — 5 tests): `docker exec the-one pytest tests/test_db_migration.py::TestSchemaV26 -x --timeout 30 -q` runs 5 tests, all passing.
- [x] **AC-11** (`TestPerAgentDmAllowedStrictRejection` class added — 2 tests): `docker exec the-one pytest tests/test_db_repositories.py::TestPerAgentDmAllowedStrictRejection -x --timeout 30 -q` runs 2 tests, all passing.
- [x] **AC-12** (broader regression — direct consumers of touched files green): `docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py tests/test_db_api.py tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_commands.py tests/test_connectors_inbound.py tests/test_connector_history_tools.py tests/test_connectors_discord.py -x --timeout 30 -q` all green; no regressions from the per-agent fixture cleanup or the validator strictening.
- [x] **AC-13** (full backend regression): `docker exec the-one pytest tests/ --timeout 30 -q` ends at **2790 passed** (± 2; L1 baseline 2783 + 7 net) / 4 skipped / 0 errors / 0 failures.
- [x] **AC-14** (browser regression preserved): `docker exec the-one pytest tests/browser/ -m browser --timeout 30 -q` ends at **443 passed** / 35 skipped / 12 deselected / 2 pre-existing failures still present (no new browser failures from the per-agent retirement — verified for `tests/browser/test_flow_studio_per_peer_dm_toggle.py` since its sites are all account-scope and stay intact).
- [x] **AC-15** (Phase 5c grep-gate per pulled-forward lesson #2 — `_acl.py` reads): `git grep -nE 'dm_allowed' the_one/connectors/_acl.py` post-L2 returns:
  - `:491` (or post-edit equivalent line) — `if not peer_entry.get("dm_allowed", False):` (runtime read; account-scope; UNCHANGED — AC-7 enforces byte-identical code)
  - Docstring/comment references at approximately `:11 (2 hits — account-scope + per-agent split), :238, :316 (admits_inbound docstring — unchanged), :406, :417, :422-428 (rewritten paragraph), :481, :494, :498, :546-547 (rewritten parenthetical)`
  - Approximately 12-14 total hits (line numbers may drift slightly after the docstring rewrites; the contract is "only the one runtime read + account-scope-focused docstring references — zero per-agent runtime reads"). Implementing agent re-categorizes each hit post-edit.
- [x] **AC-16** (Phase 5c grep-gate — shared helper): `git grep -nE 'dm_allowed' tests/_acl_shape_helpers.py` returns hits ONLY inside the `_to_v24_shape` body (account-scope; KEEPS the field — 2 emit sites: bare-string branch + tuple branch) and its docstring examples (3 lines). Total: 5-6 hits, all inside `_to_v24_shape` or its docstring; zero inside `_to_v24_agent_acl`.

## Verification Steps

How to confirm each criterion is met:

- **AC-1**: `grep -n "^CURRENT_VERSION = " the_one/db/schema.py`.
- **AC-2**: `grep -nE "if version < 26:|^        version = 26$" the_one/db/schema.py`.
- **AC-3**: visually inspect the v26 block — both passes have `changed = False` / `if changed:` patterns.
- **AC-4**: `docker exec the-one pytest tests/test_db_migration.py::TestSchemaV26::test_v26_logs_affected_always_listen_connectors -x --timeout 30 -q`.
- **AC-5**: `docker exec the-one pytest tests/test_db_repositories.py::TestConnectorConfigValidator -x --timeout 30 -q` (existing class extended with new tests for the inference keys OR add cases inline). Also a quick interactive: `docker exec the-one python -c "from the_one.db.models import Connector; print(Connector(id='a', name='n', type='stub', config={'inference_provider_config_id': 'p1', 'inference_model': 'm1'}).config)"`.
- **AC-6**: `docker exec the-one pytest tests/test_db_repositories.py::TestPerAgentDmAllowedStrictRejection -x --timeout 30 -q`.
- **AC-7**: `git diff the_one/connectors/_acl.py` — verify ONLY docstring/comment hunks.
- **AC-8**: `git grep -nE 'dm_allowed' tests/_acl_shape_helpers.py` — inspect each hit's location (inside `_to_v24_shape` body or its docstring only).
- **AC-9**: run the literal grep `git grep -nE '"dm_allowed":\s*(True|False)' tests/ --include='*.py'` and confirm every hit is in the allowed-residue set.
- **AC-10**: as above.
- **AC-11**: as above.
- **AC-12**: literal pytest command.
- **AC-13**: `docker exec the-one pytest tests/ --timeout 30 -q | tail -5`.
- **AC-14**: `docker exec the-one pytest tests/browser/ -m browser --timeout 30 -q | tail -5`.
- **AC-15**: `git grep -nE 'dm_allowed' the_one/connectors/_acl.py` post-L2 — every hit categorizable per the AC-15 enumeration.
- **AC-16**: as AC-8.

## Implementation Guidance

1. **Capture baseline test count snapshot and confirm L1 post-state.**
   - `docker exec the-one pytest --collect-only -q tests/ 2>&1 | tail -3` — note the collected count (expected 2787 from L1 LANDED snapshot).
   - `docker exec the-one pytest tests/test_db_migration.py tests/test_db_repositories.py tests/test_db_api.py tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_commands.py -x --timeout 30 -q | tail -5` — confirm the direct-consumer suite is green pre-L2.
   - `cat tests/_acl_shape_helpers.py | grep -nE 'dm_allowed'` — confirm L1 status quo (both `_to_v24_shape` AND `_to_v24_agent_acl` emit `dm_allowed`).

2. **Add `import logging` + `logger = logging.getLogger(__name__)` to `the_one/db/schema.py` AND bump `CURRENT_VERSION` to 26.**
   - Recon confirmed the file does NOT currently `import logging`. Add at the top (alongside `import json` at `:5` + `import aiosqlite` at `:7`).
   - Add `logger = logging.getLogger(__name__)` after the imports / before `CURRENT_VERSION = …` at line 12.
   - Change line 12 from `CURRENT_VERSION = 25` to `CURRENT_VERSION = 26`. (Bundled with the import additions so the file's "version 26 is current" advertisement and the v26 block addition land in lockstep — the bump is meaningless without the block.)

3. *(merged into step 2)*

4. **Insert the v26 migration block immediately after the v25 block (after line 1565 `version = 25`).**

   The block should look like this (verbatim guidance — mirrors the v25 block's segment-guard pattern at `:1419+`):

   ```python
       if version < 26:
           # Mission 11 Flight 13 Leg 2 — connector-scope inference LLM
           # configuration substrate + per-agent ``peers[*].dm_allowed``
           # retirement (F12 footgun). Bundled into a single migration
           # since both touch the same JSON columns (connectors.config and
           # agents.connector_acls respectively).
           #
           # Pass A: connectors.config row-rewrites
           #   - Add ``inference_provider_config_id: None`` and
           #     ``inference_model: None`` to each row's config if absent.
           #     Operator edits per-connector via the Studio connector
           #     editor post-migration (F13 L4); the ``None`` defaults
           #     fall through to the routed agent's LLM at the dispatcher
           #     policy gate (F13 L3).
           #   - For each connector with ``config.get("always_listen") is
           #     True``, emit a ``logger.info`` line naming the connector
           #     ID + label so the operator sees the runtime-behavior
           #     shift at startup post-migration. Connectors with
           #     ``always_listen=false`` or absent are NOT logged (they
           #     don't run the inference gate).
           #
           # Pass B: agents.connector_acls row-rewrites
           #   - Iterate each per-account payload's ``peers`` list and
           #     ``entry.pop("dm_allowed", None)`` per entry. Idempotent
           #     (``dict.pop(key, None)`` is safe on re-run). The F12
           #     "structurally uniform but not consulted by ACL" footgun
           #     is retired: per-agent peers entries are now bare
           #     ``{id: str}`` dicts. Account-scope ``dm_allowed`` stays
           #     (DM admission is account-scope per the F12 L3 DM
           #     Composition Truth Table; the F13 L2 Pydantic validator
           #     enforces the per-agent rejection going forward).
           #
           # Idempotency: per-row UPDATE only fires when ``changed``
           # (mirrors the v25 UPDATE-only-when-changed pattern at
           # schema.py:1463-1474). Re-running ``ensure_schema`` after
           # v26 is a no-op without needing a separate segment marker.
           #
           # Row access uses POSITIONAL indexing (mirrors v24 + v25) so
           # the migration works against hand-built test fixtures that
           # don't configure ``conn.row_factory = aiosqlite.Row``.
           import json as _json

           # ---- Pass A: connectors.config row-rewrites ----
           # Defensive: skip when the connectors table is missing
           # (hand-built partial-schema test fixtures — pre-v9 fixtures
           # may not have this table; pre-v23 fixtures have
           # ``connector_accounts`` which is renamed to ``connectors``
           # by v23, so by the time v26 runs the rename has been applied).
           async with conn.execute(
               "SELECT name FROM sqlite_master WHERE type='table' "
               "AND name='connectors'"
           ) as cursor:
               connectors_table_present = (await cursor.fetchone()) is not None
           if connectors_table_present:
               # Determine whether the ``name`` column exists (added at
               # v17 per recon; absent in pre-v17 hand-built fixtures).
               async with conn.execute(
                   "PRAGMA table_info(connectors)"
               ) as cursor:
                   connector_cols = {r[1] for r in await cursor.fetchall()}
               has_name = "name" in connector_cols
               select_sql = (
                   "SELECT id, config, name FROM connectors"
                   if has_name
                   else "SELECT id, config FROM connectors"
               )
               async with conn.execute(select_sql) as cursor:
                   connector_rows = await cursor.fetchall()
               for row in connector_rows:
                   connector_id = row[0]
                   config_str = row[1] or "{}"
                   connector_label = row[2] if has_name else connector_id
                   config = _json.loads(config_str)
                   changed = False
                   if "inference_provider_config_id" not in config:
                       config["inference_provider_config_id"] = None
                       changed = True
                   if "inference_model" not in config:
                       config["inference_model"] = None
                       changed = True
                   if changed and config.get("always_listen") is True:
                       logger.info(
                           "v26: connector %s (%s) inherits None "
                           "inference defaults; edit per-connector via "
                           "Studio connector editor",
                           connector_id,
                           connector_label,
                       )
                   if changed:
                       await conn.execute(
                           "UPDATE connectors SET config = ? WHERE id = ?",
                           (_json.dumps(config), connector_id),
                       )

           # ---- Pass B: agents.connector_acls row-rewrites ----
           async with conn.execute(
               "SELECT name FROM sqlite_master WHERE type='table' "
               "AND name='agents'"
           ) as cursor:
               agents_table_present = (await cursor.fetchone()) is not None
           if agents_table_present:
               async with conn.execute(
                   "PRAGMA table_info(agents)"
               ) as cursor:
                   agents_cols = {r[1] for r in await cursor.fetchall()}
           else:
               agents_cols = set()
           if agents_table_present and "connector_acls" in agents_cols:
               async with conn.execute(
                   "SELECT name, connector_acls FROM agents"
               ) as cursor:
                   agent_rows = await cursor.fetchall()
               for row in agent_rows:
                   agent_name = row[0]
                   acls_str = row[1]
                   if not acls_str:
                       continue
                   acls = _json.loads(acls_str)
                   if not isinstance(acls, dict):
                       continue
                   changed = False
                   for _acct_id, payload in acls.items():
                       if not isinstance(payload, dict):
                           continue
                       peers = payload.get("peers")
                       if not isinstance(peers, list):
                           continue
                       for entry in peers:
                           if isinstance(entry, dict) and "dm_allowed" in entry:
                               entry.pop("dm_allowed", None)
                               changed = True
                   if changed:
                       await conn.execute(
                           "UPDATE agents SET connector_acls = ? "
                           "WHERE name = ?",
                           (_json.dumps(acls), agent_name),
                       )

           await conn.execute(
               "INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (26,)
           )
           await conn.commit()
           version = 26
   ```

   **Notes on the block:**
   - The `has_name` branch handles pre-v17 hand-built fixtures that lack the `name` column. The logger line falls back to `connector_id` as the label when `name` is absent (no test currently exercises a pre-v17 fixture through v26, but the defensive branch keeps the migration robust).
   - Both passes track `changed` per row; the SQL UPDATE only fires when `changed`. Matches the v25 pattern.
   - The `logger.info` fires ONLY when the connector got a new `inference_provider_config_id` key AND was always-listen. On rerun, `changed` is False, so the log doesn't re-fire — naturally idempotent.

5. **Widen `Connector.config`'s reserved-keys validator in `the_one/db/models.py`.**

   After the `always_listen` block at `:604-611` and BEFORE the `auto_relay_platform_replies` strip at `:621`, insert:

   ```python
           # M11 F13 L2 — connector-scope inference LLM configuration.
           # Two optional flat keys on ``config`` (sibling to
           # ``always_listen``): the LLM provider + model the policy-gate
           # inference call uses for this connector. Both default to
           # None at the v26 backfill (operator edits per-connector via
           # the Studio connector editor at F13 L4); ``None`` falls
           # through to the routed agent's LLM at the dispatcher
           # (F13 L3).
           if "inference_provider_config_id" in value:
               ipci = value["inference_provider_config_id"]
               if ipci is not None and not isinstance(ipci, str):
                   raise ValueError(
                       "config['inference_provider_config_id'] must be "
                       "a string or None; got "
                       f"{type(ipci).__name__}"
                   )
           if "inference_model" in value:
               im = value["inference_model"]
               if im is not None and not isinstance(im, str):
                   raise ValueError(
                       "config['inference_model'] must be a string or "
                       f"None; got {type(im).__name__}"
                   )
   ```

   Update the docstring at `:196-260` to mention the two new optional reserved keys (one sentence is enough: "M11 F13 L2 — ``inference_provider_config_id`` + ``inference_model`` are optional flat keys per the connector-scope inference LLM configuration design").

6. **Tighten `AgentConfig.connector_acls`'s peers validator in `the_one/agent/config.py`.**

   In `_validate_connector_acls` at `:267+`, locate the `elif key == "peers":` branch at `:374-412`. Replace the per-entry validation to reject `dm_allowed`:

   ```python
               elif key == "peers":
                   # M11 F13 L2 — per-agent peers entries are bare
                   # ``{id: str}`` dicts. The ``dm_allowed`` field is
                   # REJECTED (F12 footgun retirement; the per-peer DM
                   # toggle is account-scope only per the F12 L3 DM
                   # Composition Truth Table).
                   for i, item in enumerate(value_at_key):
                       if not isinstance(item, dict):
                           raise ValueError(
                               f"connector_acls[{account_id!r}]"
                               f"['peers'][{i}] must be a dict with "
                               f"key {{'id'}}; got "
                               f"{type(item).__name__}"
                           )
                       item_keys = set(item.keys())
                       extra_keys = item_keys - {"id"}
                       if extra_keys:
                           raise ValueError(
                               f"connector_acls[{account_id!r}]"
                               f"['peers'][{i}] has unexpected keys: "
                               f"{sorted(extra_keys)} — per-agent "
                               f"peer entries must not carry "
                               f"'dm_allowed' (the per-peer DM toggle "
                               f"is account-scope only; F12 footgun "
                               f"retirement, F13 L2)"
                           )
                       missing_keys = {"id"} - item_keys
                       if missing_keys:
                           raise ValueError(
                               f"connector_acls[{account_id!r}]"
                               f"['peers'][{i}] is missing required "
                               f"keys: {sorted(missing_keys)}"
                           )
                       if not isinstance(item["id"], str):
                           raise ValueError(
                               f"connector_acls[{account_id!r}]"
                               f"['peers'][{i}]['id'] must be a "
                               f"string; got "
                               f"{type(item['id']).__name__}"
                           )
   ```

   Also update the docstring at `:296-299` (the "peers: list[{id: str, dm_allowed: bool}]" line) to match the new shape — see Outputs.

7. **Update `tests/_acl_shape_helpers.py` — `_to_v24_agent_acl` stops emitting `dm_allowed`.**

   Locate `_to_v24_agent_acl` (around `:108+`); inside its `peers` branch:
   - Change the tuple branch (`peers_new.append({"id": entry[0], "dm_allowed": entry[1]})`) → `peers_new.append({"id": entry[0]})`. The tuple's second-element is silently dropped (the per-agent path doesn't store `dm_allowed`; the helper is structural translator, not validator).
   - Change the bare-string branch (`peers_new.append({"id": entry, "dm_allowed": True})`) → `peers_new.append({"id": entry})`.
   - The dict-pass-through branch stays unchanged.

   Update the function's docstring to drop the "emits dm_allowed: True on bare-string peer entries" lines and replace with the post-F13 L2 wording (see Outputs).

   `_to_v24_shape` (account-scope) is UNCHANGED — KEEPS the field on all 3 branches.

8. **Update `the_one/connectors/_acl.py` docstrings/comments — runtime code UNCHANGED.**

   - Module docstring at `:11`: split into `peers (account-scope): list[{id: str, dm_allowed: bool}]` AND `peers (per-agent): list[{id: str}]`.
   - `admits_dm_peer` docstring at `:238`: update to "peers entries are structured dicts (account-scope: `{id, dm_allowed}`; per-agent: `{id}` only post-F13 L2); this helper consults only the `id` field at both scopes".
   - `_admits_inbound_dm` docstring (`:386+`):
     - Line `:316` references in the public `admits_inbound` docstring: keep the `peer.dm_allowed` reference (still consumed at account-scope).
     - Truth Table block at `:402-406`: unchanged (account-scope `peer.dm_allowed` is the consumed signal).
     - `:417-420` ("`peer.dm_allowed` is the per-peer (account-scope) DM toggle…"): unchanged.
     - `:422-428` ("**Per-agent peers entries' `dm_allowed` field is NOT consulted by this Truth Table**…"): rewrite to "**Per-agent peers entries DO NOT carry a `dm_allowed` field** (F13 L2 — F12 footgun retirement; the v26 migration strips the field from stored data and the Pydantic validator at `the_one/agent/config.py:_validate_connector_acls` REJECTS it post-v26). If a future flight wants per-agent DM granularity (e.g. 'this peer can DM agent A but not agent B'), that requires a substrate change."
   - `_admits_inbound_guild` docstring at `:546-547` ("uses structured `{id, dm_allowed}` dicts (the `dm_allowed` field is consulted only by `_admits_inbound_dm`; the guild path ignores it)"): rewrite to "uses structured `{id}` dicts at per-agent scope (post-F13 L2; per-agent peers no longer carry `dm_allowed` — that field lives only at account-scope per the F12 L3 DM Composition Truth Table)".

9. **Scrub per-agent inline `dm_allowed` writes from tests.**

   **CRITICAL ORDERING NOTE**: Between completing step 6 (validator tightening) and finishing step 9 (this step), the working tree is in a TRANSIENT BROKEN STATE — the validator now REJECTS what the per-agent fixtures still write. Do NOT run pytest between steps 6-9 or you will see hundreds of validation failures. Batch all edits through step 9, then run the regression gate in step 12.

   For each per-agent site enumerated in Outputs (lines in `test_db_repositories.py`, `test_db_api.py`, `test_db_migration.py`):
   - Remove the `, "dm_allowed": True` (or `False`) key-value pair from each peer dict.
   - The shape goes from `{"id": "u1", "dm_allowed": True}` → `{"id": "u1"}`.
   - Where both write AND read-back assertion exist (e.g., `:294-310` in `test_db_repositories.py`), update BOTH.
   - For `test_db_migration.py:3956-3957`: post-pipeline assertion in `test_v24_agents_connector_acls_rewrite` — v24 still writes `dm_allowed: True` (schema.py:1370 UNCHANGED), v25 leaves alone, v26 strips. Assertion becomes `[{"id": "U1"}, {"id": "U2"}]`.
   - For `test_db_migration.py:4270, :4313`: seed at `:4270` STAYS (v25-shape stored data; legitimate pre-v26 input). Update ONLY the assertion at `:4313`: `[{"id": "U1", "dm_allowed": True}]` → `[{"id": "U1"}]`.

   **Note on test_db_repositories.py:493** (`test_validator_fires_on_malformed_inner_shape` — cycle-1 review Q1): step 1 of this test currently writes a valid `AgentConfig` with `dm_allowed: True` as the baseline before exercising the malformed branch. Post-L2 the baseline must not carry `dm_allowed` — remove the field from the baseline AgentConfig construction; the malformed-shape assertion later in the test is unaffected.

10. **Add the `TestSchemaV26` class to `tests/test_db_migration.py`.**

    Append after `TestSchemaV25` (ends around `:4393`). Model the class on `TestSchemaV25` (`:3999+`):

    ```python
    class TestSchemaV26:
        """Tests for the v26 migration that (a) adds the connector-scope
        inference LLM keys to ``connectors.config`` with ``None`` defaults
        and logs always_listen=true connectors at migration time, and
        (b) strips ``dm_allowed`` from per-agent ``connector_acls[*].
        peers[*]`` entries (F12 footgun retirement).

        Mission 11 Flight 13 Leg 2.
        """

        async def test_v26_fresh_db_shape(self, tmp_path) -> None:
            """Fresh DB → ensure_schema → v26 final shape:
            - A connector with the two new keys round-trips via Pydantic.
            - A per-agent peers entry WITHOUT ``dm_allowed`` validates.
            - A per-agent peers entry WITH ``dm_allowed`` is REJECTED.
            - Head pointer at CURRENT_VERSION (>= 26).
            """
            # … hand-build fresh DB; assert CURRENT_VERSION >= 26;
            # assert Connector(config={"inference_provider_config_id":
            # "p1", "inference_model": "m1"}) round-trips; assert
            # AgentConfig(connector_acls={"acct-a": {"peers": [{"id":
            # "u1"}], "channels": []}}) round-trips; assert
            # ValidationError on per-agent peers with dm_allowed.

        async def test_v26_idempotent_on_rerun(self, tmp_path) -> None:
            """Two ``ensure_schema`` calls leave v26 in schema_version
            exactly once; the per-row UPDATE-only-when-changed pattern
            short-circuits the second pass.
            """
            # … two ensure_schema calls; versions.count(26) == 1.

        async def test_v26_legacy_v25_row_migration_strips_dm_allowed(
            self, tmp_path
        ) -> None:
            """Hand-build a v25-shape DB with agents.connector_acls
            payloads carrying per-agent peer entries with ``dm_allowed``
            keys; run ``ensure_schema``; assert each per-agent peer
            entry post-pipeline has NO ``dm_allowed`` key.
            """
            # … seed schema_version v1..25 + agents table with
            # connector_acls JSON carrying ``"peers": [{"id": "U1",
            # "dm_allowed": True}, {"id": "U2", "dm_allowed": False}]``;
            # call ensure_schema; assert peers == [{"id": "U1"},
            # {"id": "U2"}].

        async def test_v26_connector_config_inference_fields_added(
            self, tmp_path
        ) -> None:
            """Hand-build a v25-shape DB with connectors.config rows
            lacking the inference keys; run ``ensure_schema``; assert
            each connector's config has the two new keys with None
            defaults.
            """
            # … seed schema_version v1..25 + connectors table with
            # connectors.config not having the new keys; call
            # ensure_schema; assert config["inference_provider_
            # config_id"] is None and config["inference_model"] is None.

        async def test_v26_logs_affected_always_listen_connectors(
            self, tmp_path, caplog
        ) -> None:
            """Seed a v25-shape DB with two connectors: one with
            ``always_listen=true``, one with ``always_listen=false``.
            Run ``ensure_schema`` under ``caplog.at_level(logging.INFO,
            logger="the_one.db.schema")``. Assert EXACTLY one
            ``logger.info`` line fired, mentioning the always_listen=
            true connector's ID and label.
            """
            # … hand-build DB; with caplog.at_level(logging.INFO,
            # logger="the_one.db.schema"): await ensure_schema(conn);
            # assert exactly one log record matches "v26: connector .*
            # inherits None inference defaults" and references the
            # always_listen-true connector.
    ```

    Use the `TestSchemaV25` class's hand-built-DB pattern (the schema_version-seed loop + the explicit `CREATE TABLE connectors / pending_approvals / agents` SQL) as the template for tests 3-5.

11. **Add the `TestPerAgentDmAllowedStrictRejection` class to `tests/test_db_repositories.py`.**

    Append after `TestAgentConfigConnectorAclsValidator` (ends around `:1113`):

    ```python
    class TestPerAgentDmAllowedStrictRejection:
        """M11 F13 L2 — per-agent ``connector_acls[*].peers[*]`` entries
        REJECT ``dm_allowed`` post-v26 (F12 footgun retirement). The
        per-peer DM toggle is account-scope only per the F12 L3 DM
        Composition Truth Table.
        """

        def test_per_agent_peers_with_dm_allowed_key_rejected(
            self,
        ) -> None:
            """``AgentConfig(connector_acls={…peers carrying
            dm_allowed…})`` raises ValidationError citing the F12
            footgun retirement.
            """
            with pytest.raises(Exception) as exc_info:  # ValidationError
                AgentConfig(
                    name="agent",
                    connector_acls={
                        "acct-a": {
                            "peers": [{"id": "u1", "dm_allowed": True}],
                            "channels": [],
                        },
                    },
                )
            assert "dm_allowed" in str(exc_info.value)
            assert "F12 footgun retirement" in str(exc_info.value) or \
                "F13 L2" in str(exc_info.value)

        def test_per_agent_peers_without_dm_allowed_key_accepted(
            self,
        ) -> None:
            """``AgentConfig(connector_acls={…peers as {id}…})``
            constructs cleanly and round-trips.
            """
            cfg = AgentConfig(
                name="agent",
                connector_acls={
                    "acct-a": {
                        "peers": [{"id": "u1"}],
                        "channels": [],
                    },
                },
            )
            assert cfg.connector_acls == {
                "acct-a": {"peers": [{"id": "u1"}], "channels": []},
            }
    ```

    Use `pytest` and `AgentConfig` imports already present at the file's top.

12. **Run the regression gates in order.**
    - `docker exec the-one pytest tests/test_db_migration.py::TestSchemaV26 -x --timeout 30 -q` (AC-10).
    - `docker exec the-one pytest tests/test_db_repositories.py::TestPerAgentDmAllowedStrictRejection -x --timeout 30 -q` (AC-11).
    - `docker exec the-one pytest tests/test_db_repositories.py tests/test_db_api.py tests/test_db_migration.py tests/test_connector_history_tools.py tests/test_connectors_discord.py -x --timeout 30 -q` (broad consumer green).
    - `docker exec the-one pytest tests/ --timeout 30 -q | tail -5` (full backend — AC-13).
    - `docker exec the-one pytest tests/browser/ -m browser --timeout 30 -q | tail -5` (browser preserved — AC-14).
    - Verify each AC grep gate (AC-1, AC-2, AC-5, AC-6, AC-7, AC-8, AC-9, AC-15, AC-16).

13. **Update the flight log.**
    - Append a leg-progress entry under `## Leg Progress` in `flights/13-.../flight-log.md` per the artifact's append-only convention.
    - Record: leg start/end timestamps, post-L2 test counts, any deviations from the spec's per-agent vs account-scope categorization discovered at edit-time, confirmation that the `_acl.py` runtime code is byte-identical (AC-7), confirmation that all AC grep gates pass.

## Edge Cases

- **Edge Case 1 — pre-v17 hand-built test fixtures lacking the `connectors.name` column**: the recon found at least one test (`test_v22_legacy_row_with_empty_channels_gets_dm_admission_all`) that hand-builds a connectors table without the `name` column. The v26 block's `has_name`-conditional SELECT defends against this; the logger line falls back to `connector_id` as the label. **Treatment**: covered by the conditional code in step 4. Verify at implementation time by running `docker exec the-one pytest tests/test_db_migration.py -x --timeout 30 -q` after the v26 block lands — any test that fails with `KeyError: 'name'` or `OperationalError: no such column: name` indicates the conditional needs widening.

- **Edge Case 2 — v24 migration WRITES `dm_allowed: True` to per-agent peers, v26 SAME-PIPELINE STRIPS**: the v24 migration block at `schema.py:1370` constructs per-agent peers as `[{"id": peer_id, "dm_allowed": True} for peer_id in payload["peers"]]`. The L2 migration BUNDLES the v26 strip; in the SAME `ensure_schema` pipeline, v24 first transforms a pre-v24 row to v24 shape (adds `dm_allowed`), then v25 leaves it alone, then v26 strips it. The legacy-v23-row migration test at `test_db_migration.py:3845+` (`test_v24_agents_connector_acls_rewrite`) and the v25 legacy test at `:4189+` (`test_v25_agents_connector_acls_orphan_deletion`) both seed pre-v24 data, call `ensure_schema`, and assert post-pipeline shape. After L2 these assertions update from `[{"id": "U1", "dm_allowed": True}, …]` to `[{"id": "U1"}, …]` for per-agent peers. **Treatment**: update each per-agent assertion in tests where the assertion-line numbers (3956-3957 in particular) read `connector_acls`. **Important**: the v24 migration code itself is NOT modified — the field gets written then stripped in the same pipeline (slightly wasteful but the alternative is editing the v24 block, which is immutable post-land per Flight Control discipline). Document this in the v26 block's docstring.

- **Edge Case 3 — categorization ambiguity for some test_db_migration.py sites**: the recon classified `:3527, :3539` as account-scope (`Connector.model_validate({"config": {"allowlist": {"peers": [{"id": "U1", "dm_allowed": True}], …}}})` at `:3520-3540`). The implementing agent should re-verify each test_db_migration.py site by reading the surrounding 5-10 lines before editing — the line numbers may shift slightly during edits and the categorization is the load-bearing distinction.

- **Edge Case 4 — Pydantic validator error-message format constraint**: AC-11's test `test_per_agent_peers_with_dm_allowed_key_rejected` asserts the error message contains either "F12 footgun retirement" OR "F13 L2". The validator-error-message implementation in step 6 includes BOTH strings ("F12 footgun retirement, F13 L2"). If a future leg restructures the error-message format and drops one of the strings, this assertion will fire — the assertion is intentionally permissive (`OR`) to allow either string to remain. The implementing agent should NOT relax further (e.g., to just `"dm_allowed"`) — the F12 lineage tag is the load-bearing semantic the assertion is pinning.

- **Edge Case 5 — additional per-agent `dm_allowed` writes beyond the recon enumeration**: the recon enumerated all `tests/` `"dm_allowed":\s*(True|False)` matches as of L1 LANDED state. If a NEW per-agent write surfaces during implementation (e.g., a test added in a parallel branch that the recon didn't see), fold it into the L2 cleanup in lockstep per the flight's "Acceptable variations" clause (`L2 may discover additional ACL helper consumer sites that reference per-agent dm_allowed beyond the spec's enumeration; fold into L2 in lockstep`). **At implementation time**, after step 9's cleanup, re-run the AC-9 grep and verify EVERY remaining hit is in the allowed-residue set; any unexpected per-agent residue is a fold-in.

- **Edge Case 6 — Divert clause (per `flight.md` Adaptation Criteria for L2)**: "L2's v26 migration surfaces a row that fails the strict-per-agent-`dm_allowed`-rejection validator after row-rewrite (e.g. operator's seeded data has hand-edited per-agent peers carrying the field with extra metadata)" → split into v26-row-rewrite + v27-validator-tightening, OR pre-clean during v26. The L2 design pre-cleans during v26 (the migration runs BEFORE the validator fires at next read — the validator only fires on subsequent `model_validate` calls). If a row carries extra metadata BEYOND `dm_allowed` (e.g., `{"id": "u1", "dm_allowed": True, "custom_key": "x"}`), the migration's `entry.pop("dm_allowed", None)` strips ONLY `dm_allowed` — `custom_key` survives. The validator then REJECTS the row at next read because `custom_key` is also an extra key. This is acceptable F13 behavior (the operator never had a path to write `custom_key`); if it surfaces in production, escalate to operator.

- **Edge Case 7 — operator-local `docker-compose.yml` carries `THE_ONE_INFERENCE_*` env vars** (per F11 + F12 + pulled-forward lesson #5): L2 does NOT touch the env vars (L3 owns Settings removal + the lifespan warning). The env vars stay live during L2; they continue to populate `Settings.inference_provider_config_id` (which still exists at L2 — L3 deletes it). The dispatcher's policy-gate continues consulting `settings.inference_provider_config_id` at L2 (L3 replaces with `account.config.get("inference_provider_config_id")`). **Treatment**: documented as no-op-at-L2; L3's lifespan-warning surfaces the deprecation post-L3 land.

## Files Affected

- `the_one/db/schema.py` — **MODIFIED**: add `import logging` + `logger = logging.getLogger(__name__)` at module top; bump `CURRENT_VERSION = 26` at line 12; insert v26 migration block after line 1565 (`version = 25`).
- `the_one/db/models.py` — **MODIFIED**: extend `_validate_config_reserved_keys` (in `Connector` model around `:193-623`) to accept and shape-validate two new optional reserved keys `inference_provider_config_id` and `inference_model` (insert after the `always_listen` block at `:611`, before the `auto_relay_platform_replies` strip at `:621`). Docstring updated.
- `the_one/agent/config.py` — **MODIFIED**: tighten `_validate_connector_acls` (around `:267-461`) per-agent peers branch at `:374-412` to REJECT `dm_allowed` (extra-key check). Docstring updated at `:296-299`.
- `the_one/connectors/_acl.py` — **MODIFIED (docstrings/comments only — runtime code BYTE-IDENTICAL)**: module docstring at `:11`; `admits_dm_peer` docstring at `:238`; `_admits_inbound_dm` paragraph at `:422-428`; `_admits_inbound_guild` docstring at `:546-547`. AC-7 enforces no runtime-code change.
- `tests/_acl_shape_helpers.py` — **MODIFIED**: `_to_v24_agent_acl`'s peers branch stops emitting `dm_allowed` on all 3 entry shapes (dict-pass-through stays unchanged but expected to already comply post-L2). Docstring updated.
- `tests/test_db_repositories.py` — **MODIFIED**: per-agent inline `dm_allowed` writes scrubbed at `:294, 295, 309, 310, 327, 336, 493, 758, 779, 904, 905, 916, 917, 965, 972, 1072, 1081`. NEW `TestPerAgentDmAllowedStrictRejection` class appended after `TestAgentConfigConnectorAclsValidator` (`:833-1113`) with 2 tests.
- `tests/test_db_api.py` — **MODIFIED**: per-agent inline `dm_allowed` writes scrubbed at `:1616, 1617, 1618, 1666, 1667, 1668, 1709, 1732`.
- `tests/test_db_migration.py` — **MODIFIED**: per-agent inline `dm_allowed` writes scrubbed at `:3956, 3957, 4313` (post-pipeline assertions). `:4270` seed STAYS UNCHANGED (v25-shape, NOT v23-flat — represents legitimate post-v25 stored data; the v26 migration strips it under `ensure_schema`; the test exercises the strip behavior end-to-end). NEW `TestSchemaV26` class appended at end of file (around `:4393+`) with 5 tests.
- **NO MODIFICATIONS** to:
  - `tests/test_connector_history_tools.py` (account-scope writes only).
  - `tests/test_connectors_discord.py` (account-scope writes only).
  - `tests/browser/test_flow_studio_per_peer_dm_toggle.py` (account-scope writes only — the test EXISTS to exercise account-scope per-peer DM toggle; per-agent retirement is invisible to it).
  - `tests/test_connectors_acl.py`, `tests/test_connectors_routing.py`, `tests/test_connectors_commands.py` (post-L1, NO inline `dm_allowed` writes; helper imports get cleaner peer entries via L1's updated `_to_v24_agent_acl` automatically — verify at implementation time by `git grep '"dm_allowed"' tests/test_connectors_*.py` returning ZERO post-L2).
  - `tests/browser/seeders.py` (post-L1, NO inline writes; the helper-import path picks up the L1-updated `_to_v24_agent_acl` automatically).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria (AC-1 through AC-16) verified
- [x] Tests passing — backend 2790 passed / 4 skipped / 509 deselected / 0 errors / 3 warnings; browser 443 passed / 35 skipped / 12 deselected + 2 pre-existing-main failures (no new browser failures)
- [x] Update `flights/13-.../flight-log.md` with the L2 progress entry under `## Leg Progress`
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Check off this leg in `flights/13-.../flight.md` under `### Legs`
- [x] L2 is NOT the final leg of F13 — F13 has 6 legs total (L1-L6); skip the "final leg" sub-checklist
- [x] Defer commit per `/agentic-workflow` Phase 2d: code review + commit DEFERRED to after L5 autonomous land. L2 does NOT commit standalone.

---

## Citation Audit

Per `/leg` Phase 3b: every `file:line` citation in this leg artifact verified against current code at leg design time.

| Citation | Status | Notes |
|----------|--------|-------|
| `the_one/db/schema.py:12` — `CURRENT_VERSION = 25` | OK | Verified via Read |
| `the_one/db/schema.py:1419-1565` — v25 block | OK | Verified via Read; v25 block opens at `:1419` (`if version < 25:`), closes at `:1565` (`version = 25`) |
| `the_one/db/schema.py:1463-1474` — v25 UPDATE-only-when-changed pattern | OK | Verified via Read; `changed = False` / `if changed:` shape at exact lines |
| `the_one/db/schema.py:1370` — v24 per-agent peers assignment `{"id": peer_id, "dm_allowed": True}` | OK | Verified via Read |
| `the_one/db/models.py:193-623` — `_validate_config_reserved_keys` (Connector model) | OK | Verified via Read; validator opens at `:193`, closes at `:623` |
| `the_one/db/models.py:604-611` — `always_listen` validator block | OK | Verified via Read |
| `the_one/db/models.py:621` — `auto_relay_platform_replies` strip | OK | Verified via Read |
| `the_one/agent/config.py:267-461` — `_validate_connector_acls` validator | OK | Verified via Read; validator opens at `:267`, per-agent peers branch at `:374-412` |
| `the_one/agent/config.py:374-412` — per-agent peers validation branch | OK | Verified via Read; flight spec's `:374-411` cite was 1-line short (close enough) |
| `the_one/agent/config.py:296-299` — peers docstring line | OK | Verified via Read |
| `the_one/connectors/_acl.py:11` — module docstring `peers: list[{id: str, dm_allowed: bool}]` | OK | Verified via Read |
| `the_one/connectors/_acl.py:238` — `admits_dm_peer` docstring referencing structured shape | OK | Verified via Read |
| `the_one/connectors/_acl.py:316` — `admits_inbound` docstring referencing per-peer dm_allowed | OK | Verified via Read |
| `the_one/connectors/_acl.py:386-528` — `_admits_inbound_dm` | OK | Verified via Read |
| `the_one/connectors/_acl.py:422-428` — "Per-agent peers entries' dm_allowed field is NOT consulted" paragraph | OK | Verified via Read at offset 395-428 |
| `the_one/connectors/_acl.py:491` — `peer_entry.get("dm_allowed", False)` runtime read | OK | Verified via Read; account-scope under `admin-approved` policy |
| `the_one/connectors/_acl.py:516` — per-agent peer iteration `any(p["id"] == peer_id for p in agent_peers)` in `_admits_inbound_dm` | OK | Verified via Read; NO `dm_allowed` read |
| `the_one/connectors/_acl.py:531-739` — `_admits_inbound_guild` | OK | Verified via Read |
| `the_one/connectors/_acl.py:546-547` — `_admits_inbound_guild` docstring with `dm_allowed` parenthetical | OK | Verified via Read |
| `the_one/connectors/_acl.py:654` — per-agent peer iteration `any(p["id"] == peer_id for p in agent_peers)` in `_admits_inbound_guild` | OK | Verified via Read; NO `dm_allowed` read — symmetric path |
| `tests/_acl_shape_helpers.py:112` — `_to_v24_agent_acl` bare-string emit `{"id": entry, "dm_allowed": True}` | OK | Verified via grep + Read context |
| `tests/test_db_migration.py:3845, 3947, 3955-3961` — `test_v24_agents_connector_acls_rewrite` per-agent assertion | OK | Verified via Read |
| `tests/test_db_migration.py:3999+` — `TestSchemaV25` class | OK | Verified via grep + Read; class opens at `:3999` |
| `tests/test_db_migration.py:4163-4187` — `test_v25_idempotent_on_rerun` pattern template | OK | Verified via Read |
| `tests/test_db_migration.py:4189-4322` — `test_v25_agents_connector_acls_orphan_deletion` (per-agent seed + assertion) | OK | Verified via Read; seed at `:4270`, assertion at `:4313` |
| `tests/test_db_repositories.py:294, 295, 309, 310, 327, 336, 493, 758, 779, 904, 905, 916, 917, 965, 972, 1072, 1081` — per-agent inline writes | OK | Verified via grep + categorized via Read of `:285-340, :485-498, :756-784, :895-925, :960-985, :1065-1085` (each inside `AgentConfig(connector_acls={…})` envelope) |
| `tests/test_db_repositories.py:1647-1648, 1811-1812, 1920, 1961-1963, 2017` — account-scope writes | OK | Verified via Read of `:1620+` (`TestConnectorConfigValidator` class) |
| `tests/test_db_repositories.py:833-1113` — `TestAgentConfigConnectorAclsValidator` class | OK | Verified via grep; new class appends after |
| `tests/test_db_api.py:1512, 1531, 2043, 2209, 2229, 2355` — account-scope writes (inside `config={"allowlist": …}` envelopes) | OK | Verified via Read |
| `tests/test_db_api.py:1616-1618, 1666-1668, 1709, 1732` — per-agent writes (inside `connector_acls={…}` envelopes) | OK | Verified via Read of `:1600-1740` |
| `tests/test_db_migration.py:2876, 2955, 3527, 3539, 3788-3832, 4099, 4148` — account-scope writes | OK | Verified via Read of surrounding context; categorization caveat for `:3527, :3539` documented in Edge Case 3 |
| `tests/test_db_migration.py:3956, 3957, 4270, 4313` — per-agent writes | OK | Verified via Read; inside `acls = json.loads(row["connector_acls"])` envelopes |
| `tests/test_connector_history_tools.py:569` — account-scope (inside `_seed_stub_account(config={"allowlist": …})`) | OK | Verified via Read of `:561-574` |
| `tests/test_connectors_discord.py:1373` — account-scope (inside `Connector(config={"allowlist": …})` factory) | OK | Verified via Read of `:1365-1378` |
| `tests/browser/test_flow_studio_per_peer_dm_toggle.py:158, 236, 282, 310, 353` — account-scope (`_seed_discord_with_allowlist(peers=[…])`) | OK | Verified via Read of `:150-160, :228-240` |
| `flight.md` Technical Approach L2 sub-parts (a)-(f) | OK | Verified via Read |
| `flight.md` Design Decisions ("v26 Backfill is `None`", "Strict Validator Post-v26", "F12 Fold-Ins") | OK | Verified via Read |
| L1 leg artifact `legs/01-methodology-foldins-and-shared-test-helpers.md` Context — "L2 then (a) updates the shared helper..." | OK | Verified via Read |

37 citations verified against current code at leg design time; no drift detected. The flight spec's `:374-411` citation for `_validate_connector_acls` was 1 line short of the actual `:374-412` block — corrected inline; immaterial drift.
