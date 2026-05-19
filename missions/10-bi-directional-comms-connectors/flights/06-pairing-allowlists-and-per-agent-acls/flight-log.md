# Flight Log: Pairing, Allowlists, and Per-Agent ACLs

**Flight**: [Pairing, Allowlists, and Per-Agent ACLs](flight.md)

## Summary

Flight planned and transitioned to `ready` on 2026-05-18. Cycle-1 architect review: approve with changes (3 high, 5 medium). All cycle-1 issues resolved (4 via user-confirmed decisions, 4 via spec rewrite). Cycle-2 architect review: **approve**. 5 cycle-2 findings (all low/medium severity, leg-design-time concerns, none blocking) captured below for leg authors. Mission Known Issue updated for the F5 live-broadcast carry-forward (closure owned by leg 6).

---

## Reconnaissance Report

Walked every cited F6 surface against current code before drafting the spec. Source items: F1 docstring `base.py:215,224` promising F6 introduces `AllowlistResolver`; F4 hook-point at `connector_send.py:131`; F4 debrief recs #4 (`ToolProvider` widening) and Action Item "F5 leg planning: `[platform-send-ok]` sentinel"; F5 debrief recs #1, #4 and Action Items "F6 or F10: live-broadcast", "F6 architect: ToolProvider widening", "F6 prereq: F4 design-completeness for `compose_system_prompt`".

| Source item | Classification | Evidence | Recommendation |
|---|---|---|---|
| `AllowlistResolver` Protocol | confirmed-live | `connectors/base.py:224` — docstring states "F6 introduces"; not in code | Land in leg 1 |
| DM-pairing primitive | confirmed-live | grep returns zero hits across `the_one/` + `tests/` | Land in leg 1+2 (state + flow) |
| Per-agent ACLs | confirmed-live | zero scaffolding | Land in leg 1 (state) + legs 2/3 (consult sites) |
| F6 ACL hook-point in platform-send | confirmed-live | `tools/connector_send.py:131` `# F6:` comment ships | Replace in leg 3 |
| F6 inbound-gating site | confirmed-live | `connectors/_inbound.py` has no allowlist consult | Land in leg 2 |
| Studio MCPs tab pattern | already-satisfied | `studio/mcps-tab.js:34` exists; `agent-editor.js:153` consumes | Mirror in leg 5 |
| `AgentConfig.connector_account_ids` substrate | already-satisfied | `agent/config.py:135` + v17 migration + repo round-trip | Consume in leg 5 |
| `connector_accounts.config` slot | already-satisfied | `db/models.py:134` schema-loose dict | Use in leg 1 |
| `chat_sessions.session_metadata` substrate | already-satisfied | F3 L1 added | Write audit log in leg 2 |
| F4 → F6: `ToolProvider` Protocol widening | needs-human-recheck | `factory.py:315-331` is second factory-time-kwarg case; F6 resolver may add a third | Architect-review item for leg 3 |
| F4 → F6: `[platform-send-ok]` structured side-channel | partially-satisfied | F5 didn't take it; F4 ships unsymmetric. Not strictly F6 work; if F6 doesn't touch the dispatcher's success-path tagging, defer to F10 | Defer (no F6 leg touches the success-path read) |
| F5 → F6: live-broadcast WS-typed asymmetry | confirmed-live | `interfaces/web/app.py` comments + F5 debrief Tech section | Land in leg 6 (pre-step USER tagging) |
| F5 → F6: `Session.platform` cached-field staleness | confirmed-live | F5 debrief Tech section flags F6's pairing/detach may need invalidation | Test pin in leg 4 or 5 (when detach flow lands) |
| F5 → F6/F8: `compose_system_prompt` enumerate `account_id` | confirmed-live | F5 debrief Tech section, action item "F8 prerequisite" | F8 prerequisite, NOT F6 scope. F6 still adds first-class pre-prompt-injection support for resolver state IF leg design surfaces a need; otherwise this is F8 territory. Document at F6 close. |

**User-approved scope** (3 of 4 retirements approved + 1 fold-in):
- Approved retirements: items #6–9 (Studio MCPs tab, `connector_account_ids` substrate, `config` slot, `session_metadata` substrate) stay retired as already-existing substrate
- Fold-in: F5 live-broadcast gap added as leg 6
- Mission Known Issue update queued: live-broadcast asymmetry to be added to `mission.md` Known Issues as part of leg 6

---

## Flight Director Cadence Note (Leg 4+)

Given the consumed-context profile of this flight (legs 1a/1b/1c/2/3 each ran 1–2 design-review cycles), leg 4 and leg 5 transition directly to implementation without a pre-implementation Developer-agent design-review pass. Rationale: these are operator-visible Studio UI legs whose final correctness arbiter is the HAT closer (leg 7); design-review cycles for UI legs in this project (F5 precedent) caught issues that the HAT also catches. The leg artifacts ARE still subject to single-cycle review at the post-implementation batched-review step (Phase 2d) covering all autonomous legs. Operator HAT (leg 7) is the canonical authority on these surfaces.

## Leg Progress

(Legs are designed and executed one at a time. Entries added below as legs land.)

### 2026-05-18 — Leg 1a landed

**Implemented**:
- `the_one/connectors/base.py`: added three frozen+slots dataclasses (`Permit` — zero fields, `NeedsPairing(reason: str)`, `Deny(reason: str)`), the `ResolveOutcome = Permit | NeedsPairing | Deny` PEP-604 union alias, and the `_default_permit(account, envelope) -> Permit` callable, all placed between `SendResult` and the `ConnectorClient` Protocol. Revised the module docstring (formerly predicted `AllowlistResolver` + `CommandHandler` Protocols; now describes F6's actual optional-hook shape and preserves the F7 `CommandHandler` prediction at exactly one mention). Revised the `ConnectorPlugin` Protocol docstring with the same reframing (F6 = optional `resolve` hook via `getattr`; F7 = future `CommandHandler` Protocol).
- `the_one/connectors/__init__.py`: re-exported `Permit`, `NeedsPairing`, `Deny`, `ResolveOutcome` (added to import block and `__all__`). `_default_permit` deliberately NOT re-exported (private to the package; consumers in legs 2 and 3 import via the canonical `the_one.connectors.base` path).
- `the_one/connectors/README.md`: appended a `resolve` entry to §4 "Optional hooks" (parallel to `display_channel`), naming the signature, the three-outcome shape, the `_default_permit` fallback, the named-callable-fallback variation, and the F1–F5 regression-net coverage of the fallback path. Also reframed the §1 package-layout comment (line 29) and the §3 Protocol-decomposition list (former line 82) to drop the predicted-`AllowlistResolver`-Protocol framing.
- `the_one/agents.md`: reframed the four `AllowlistResolver` prose sites — the checklist item at L306 (source-code marker description), the Protocol-list line in the Connector subsystem section (L336), the structural-satisfaction prose (L339, surgical — preserved the `CommandHandler` mention in the surrounding text per design), and the outbound-contract closing sentence (L361). Also appended one sentence to the `optional-plugin-hook-via-getattr-sentinel` convention block (L98) documenting the named-callable-fallback variation (F6's `_default_permit` returns a structured `Permit()`; F3's `display_channel` uses the `None` sentinel).
- `tests/test_connectors_resolver.py`: NEW file with six type-level surface tests — smoke-import + canonical-path pin; outcome construction + equality + hashability; `ResolveOutcome` union membership; `_default_permit` return shape; stub's lack-of-`resolve` + `getattr` fallback identity; private-not-reexported invariant.
- DO-NOT-TOUCH discipline observed: `connectors/_stub.py`, `connectors/_inbound.py`, `tools/connector_send.py:131` source-code marker, the README quoted-marker text (now at line 380 after the §4 expansion; was line 363 at design time), and the `ConnectorPlugin` Protocol shape (still 4 methods: `connect`, `disconnect`, `doctor`, `normalize_session_key`) are all unchanged.

**Tests**:
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_resolver.py` — 6 passed in 0.02s.
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_pool.py tests/test_connectors_session.py` — 98 passed in 8.28s (F1/F3/F4/F5 regression net byte-identical).
- `docker exec the-one pytest -x --timeout 30` — 1987 passed, 4 skipped, 411 deselected in 131.08s; full suite green.
- `docker exec the-one ruff check the_one/connectors/base.py the_one/connectors/__init__.py tests/test_connectors_resolver.py` — All checks passed.
- `mypy` not installed in the container; ruff's pyflakes pass covers structural import / type-name issues.

**Post-condition greps** (run from project root):
- `grep -rn "AllowlistResolver" the_one/` → 2 hits, BOTH deferred to leg 3:
  - `the_one/tools/connector_send.py:131` — source-code marker (`# F6: AllowlistResolver consultation lands here.`).
  - `the_one/connectors/README.md:380` — prose in §11 "Outbound flow trace" quoting the source-code marker text. (Line shifted from the design-time citation of 363 to 380 because the §4 "Optional hooks" addition for `resolve` is larger than the design-time draft anticipated; same content site, still deferred to leg 3.)
- `grep -rn "CommandHandler" the_one/` → 6 hits, file SET matches the design-time invariant `{base.py, README.md, agents.md}` with exactly 2 hits per file. Line numbers drift from `{base.py:12, base.py:225, README.md:30, README.md:84, agents.md:337, agents.md:339}` (design-time citation) to `{base.py:19, base.py:295, README.md:30, README.md:84, agents.md:337, agents.md:339}` because the base.py module docstring grew when the F6 optional-hook framing replaced the shorter `AllowlistResolver` + `CommandHandler` joint prediction. The `agents.md:339` hit COUNT dropped from 2 → 1 by design (the bundled `Plugin + AllowlistResolver + CommandHandler` list collapsed to `ConnectorPlugin + CommandHandler` when `AllowlistResolver` was reframed). All F7 `CommandHandler` predictions remain intact at their respective sites.

**Discrepancy notes** (carry forward — none of these are blockers, but flagging for the leg author of leg 3 and for the eventual code review):
- The leg artifact's user-message implementation expectations listed README and agents.md edits separately. The README list named only the §4 "Optional hooks" append. The leg artifact's own "F1 docstring promises that contradict this leg's framing" recon (lines 18-19) AND the leg's grep post-condition both required ALSO reframing README:29 (package layout comment) and README:82 (Protocol-decomposition list). I followed the grep post-condition as the canonical contract and edited both sites. README:29 was reframed from "Future home of AllowlistResolver (Flight 6) and CommandHandler (Flight 7)" to a description naming F6's actual outcome ADT + `_default_permit` and preserving the F7 CommandHandler prediction. README:82 was reframed from the `AllowlistResolver` Protocol-list entry to the optional `resolve` hook entry.

Leg status: `landed`. Per the deferred-batched workflow for F6, no commit is made at this point — the Flight Director batches review + commit after the last autonomous leg.

### 2026-05-18 — Leg 1b landed

**Implemented**:
- `the_one/db/models.py`: appended a single `@field_validator("config", mode="after")` classmethod `_validate_config_reserved_keys` to `ConnectorAccount`, placed immediately after `_validate_session_continuation_seconds` and before `class ToolConfig`. The validator enforces ONLY the two F6-reserved top-level keys:
  - `config["pairing"]` (optional): must be a dict with exactly the keys `{"code", "issued_at"}`; `code` is a non-empty string; `issued_at` is a string containing a `T` separator (rejects date-only entries like `"2026-05-18"`) that parses through `datetime.fromisoformat(value.replace("Z", "+00:00"))`.
  - `config["allowlist"]` (optional): must be a dict with exactly the keys `{"peers", "channels"}`; each is a `list[str]` (entries validated element-wise). Empty lists permitted and preserved verbatim — distinct semantics from absent allowlist.
  - All other top-level keys pass through unchanged (the F1 schema-loose promise stays intact). Absent reserved keys = no work. The docstring documents the cycle-1 H2 closure (Pydantic v2 runs `@field_validator` on both `BaseModel(**kwargs)` construction and `model_validate(dict)`), the plaintext-pairing-code rationale, the no-whitespace-trim choice, and the empty-vs-absent allowlist distinction for leg-4 UI consumers.
- `tests/test_db_repositories.py`: added `from pydantic import ValidationError` to the import block and appended a new `TestConnectorAccountConfigValidator` class after `TestConnectorAccountRepository` with 25 tests covering: empty-config pass-through; non-reserved keys pass-through; valid pairing round-trip; valid allowlist round-trip; empty-allowlist verbatim preservation (model-level); mixed reserved + non-reserved round-trip; 8 malformed-pairing variants (non-dict, missing-code, missing-issued_at, extra key, empty code, non-string code, malformed ISO, date-only ISO); 6 malformed-allowlist variants (non-dict, missing peers, missing channels, extra key, non-list peers, non-string peer entry); pairing repo round-trip; allowlist repo round-trip; empty-allowlist repo round-trip; empty-allowlist stored as `[]` in raw JSON (not null/absent); cycle-1 H2 closure test (`test_validator_fires_on_repo_read_path`) — create a valid row via the repository, then UPDATE only the `config` column with malformed JSON via raw SQL on `connector_repo.conn`, then assert `connector_repo.get("bad")` raises `ValidationError` (the secrets ciphertext stays intact so the read reaches the config validator, not the secrets-decrypt step).
- DO-NOT-TOUCH discipline observed: `the_one/db/repositories.py` unchanged (`_row_to_model` keeps its direct-kwargs construction; Pydantic v2 runs the validator transparently); `the_one/interfaces/web/api.py` unchanged (existing `model_validate` calls at L2154 and L2218 already exercise the validator); `the_one/connectors/base.py` and `the_one/connectors/_stub.py` unchanged (orthogonal scopes — leg 1a's surface stands).

**Cycle-1 H2 closure confirmed**: `test_validator_fires_on_repo_read_path` passes — Pydantic v2's `@field_validator` fires on the repository read path via `ConnectorAccount(**kwargs)` construction at `_row_to_model`. The cycle-1 architect's concern ("validators on `dict[str, Any]` don't fire on JSON read path without explicit `model_validate`") was a Pydantic-v1-era worry and is empirically closed. No change to `repositories.py` was needed.

**Empty-allowlist preservation invariant** (for leg-4 UI consumers): `config["allowlist"] = {"peers": [], "channels": []}` round-trips verbatim through both the Pydantic layer (model construction) and the storage layer (raw JSON column inspection). Two dedicated tests pin this: `test_empty_allowlist_round_trips_through_repo` (model-level) and `test_empty_allowlist_stored_as_lists_not_null` (storage-level, raw `SELECT config` then `json.loads`). The leg-4 Studio writer MUST NOT erase a deliberate empty-lockdown back to absent — both ends of the persistence pipe pin the invariant.

**Tests**:
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py::TestConnectorAccountConfigValidator` — 25 passed in 0.91s.
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py::TestConnectorAccountRepository` — 13 passed in 1.67s (existing repo tests byte-identical).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py tests/test_db_api.py tests/test_connectors.py tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_pool.py tests/test_connectors_session.py tests/test_connectors_resolver.py` — 258 passed in 30.85s (F1/F3/F4/F5 + leg-1a regression net byte-identical).
- `docker exec the-one pytest -x --timeout 30` — 2012 passed, 4 skipped, 411 deselected in 144.33s; full suite green (+ 25 over leg-1a baseline of 1987).
- `docker exec the-one ruff check the_one/db/models.py tests/test_db_repositories.py` — All checks passed.

**Post-condition asserts** (all pass):
- `ConnectorAccount(id='1', name='n', type='stub').config == {}` — default still empty (no auto-injection).
- `ConnectorAccount(..., config={'pairing': {'code': '', 'issued_at': '2026-05-18T00:00:00Z'}})` raises `ValidationError` (empty code).
- `ConnectorAccount(..., config={'pairing': {'code': 'x', 'issued_at': '2026-05-18'}})` raises `ValidationError` (date-only rejected).
- `ConnectorAccount(..., config={'allowlist': {'peers': [], 'channels': []}}).config['allowlist'] == {'peers': [], 'channels': []}` — verbatim.
- `ConnectorAccount(..., config={'intent': 'guild_messages'}).config == {'intent': 'guild_messages'}` — non-reserved key pass-through.

Leg status: `landed`. Per the deferred-batched workflow for F6, no commit is made at this point — the Flight Director batches review + commit after the last autonomous leg.

### 2026-05-18 — Leg 1c landed

**Implemented**:
- `the_one/agent/config.py`: imports — added `field_validator` to the pydantic import line (`from pydantic import BaseModel, Field, field_validator`). New field on `AgentConfig` after `mcp_overrides` (so the override dicts cluster together): `connector_acls: dict[str, dict[str, list[str]]] | None = None` with comprehensive docstring documenting None vs `{}` semantic equivalence, the per-account-key absence-means-inherit semantics, and the empty-inner-list lockdown semantic. New `@field_validator("connector_acls", mode="after")` classmethod `_validate_connector_acls` enforcing ONLY the one invariant the annotation cannot express — exact inner-dict keys `{"peers", "channels"}` (no extras, no missing). The validator docstring documents the Pydantic v2 native enforcement of the other shape constraints (non-string outer key → `string_type`; non-dict outer value → `dict_type`; non-list inner → `list_type`; non-string inner entry → `string_type`), so the validator body stays trimmed to the one missing invariant.
- `the_one/db/schema.py`: bumped `CURRENT_VERSION = 17 → 18`. Added the v18 migration block immediately after the v17 block (PRAGMA guard + `ALTER TABLE agents ADD COLUMN connector_acls TEXT` + `INSERT OR IGNORE INTO schema_version (version) VALUES (18)` LAST — same idempotency shape as v8/v9/v10/v11/v14/v15/v17). Surgically updated 4 prediction-comment sites for the F8-CHECK renumber: the stale-pre-leg "flight 8 will land v14" prediction in the v13 block (now lists v14–v18 owners explicitly + v19 = F8 CHECK), and the three "renumbers to v18" sites in the v15/v16/v17 downstream blocks (now "renumbers to v19" + names v18 = F6 L1c — `agents.connector_acls`).
- `the_one/db/_connector_types.py`: updated the module docstring's CHECK-deferral block — F8 CHECK now via v19 table-rename; full v14–v18 owner enumeration extended with v18 → `agents.connector_acls` (F6 L1c).
- `the_one/db/repositories.py`: extended `SQLiteAgentStore.save` — added `connector_acls` to the INSERT column list (between `connector_account_ids` and `created_at`), added one `?` placeholder, added `connector_acls=excluded.connector_acls,` to the ON CONFLICT update clause, and added `json.dumps(config.connector_acls) if config.connector_acls is not None else None` to the parameter tuple. Extended `_row_to_config` — added `connector_acls=(json.loads(row["connector_acls"]) if row["connector_acls"] else None)` after the `connector_account_ids` line, with an explanatory comment about the truthiness branch distinguishing JSON-literal `"{}"` (truthy → round-trips as `{}`) from SQL-NULL (falsy → decodes to `None`).
- `the_one/agents.md:302`: connector-type extension checklist item 4 extended — `v18 by leg 1c of Flight 6 — agents.connector_acls persistence (closes the F6 per-agent ACL substrate atomically per F4 debrief rec #1)`; F8 CHECK renumbered to `**v19**`.
- `the_one/connectors/README.md`: §6 stale F8 CHECK predictions updated — `The v13/v14 schema has no CHECK constraint` → `Schema versions before v19 have no CHECK constraint on connector_accounts.type`; `Flight 8's v15 migration adds the CHECK` → `Flight 8's v19 migration adds the CHECK`.
- `tests/test_db_migration.py`: bumped `CURRENT_VERSION == 17` assertion to 18 and updated the assertion message (`M10 F06 L1c — agents.connector_acls persistence v18 migration`); extended the surrounding migration-history comment with the v18 line. Renumbered the stale-pre-leg `TestSchemaV13` docstring (`deferred to v14 in flight 8` → `deferred to v19 in flight 8`) and the related "v18 in flight 8" / "deferred to v18 (flight 08)" prose lines in the v13 cols test docstring. Rewrote the multi-line renumber chains in TestSchemaV14 and TestSchemaV15 docstrings as single-current-statement form (per the leg artifact's Implementation Guidance §7 — drop the multi-rebase chain in favor of "now lands at v19 (v14 claimed by …; v18 by F6 L1c — agents.connector_acls)"); updated TestSchemaV16 and TestSchemaV17 docstrings to the same v19 framing + v18 = F6 L1c attribution. Appended a new `TestSchemaV18` class with three tests mirroring the `TestSchemaV17` shape: `test_v18_fresh_db_includes_agents_connector_acls_column`, `test_v18_migration_idempotent_on_rerun`, `test_v18_legacy_v17_row_decodes_with_none_connector_acls`.
- `tests/test_db_repositories.py`: appended 6 round-trip tests on `TestSQLiteAgentStore` (per the leg's Outputs): `test_save_round_trips_connector_acls` (set + upsert path), `test_save_round_trips_connector_acls_none` (None default preserved), `test_save_round_trips_empty_outer_dict_connector_acls` (the JSON `"{}"` truthy-string vs SQL NULL distinguisher), `test_load_pre_v18_agent_has_none_connector_acls` (hand-write NULL row → load → None), `test_empty_per_account_acl_round_trips_through_save_load` (empty-list lockdown survives), `test_validator_fires_on_repo_read_path_connector_acls` (H2 closure: valid save → UPDATE with malformed inner shape → load raises `ValidationError`). Appended a new `TestAgentConfigConnectorAclsValidator` class with 11 direct-construction validator tests covering: default None, empty outer dict, empty per-account ACL, populated ACL, missing-channels, missing-peers, extra inner key, non-list inner value, non-string inner entry, non-dict per-account value, non-string outer key.

**Atomic-leg pattern (F4 debrief rec #1) adoption**: Pydantic field + v18 migration + repository round-trip + 7 ripple-site renumbers + 3 migration tests + 6 round-trip tests + 11 validator tests — all ship in ONE leg per F4 debrief rec #1 ("a Pydantic field intended to persist ships its migration in the SAME leg"). Framing per cycle-2 finding #4: NOT "fix for an earlier gap" — F4 L5 was the canonical pattern, leg 1c adopts it atomically from the start.

**Cycle-2 finding #5 — PerAgentACL submodel rejection**: kept the nested-dict annotation `dict[str, dict[str, list[str]]] | None` rather than introducing a new `PerAgentACL(BaseModel)` Pydantic class. Rationale: introducing a new model type would force legs 2/3/5 to import it; the field-validator pattern provides equivalent invariants (exact-keys enforcement via `_validate_connector_acls`) without the type-system widening. The validator docstring documents the rejection so future readers don't re-litigate.

**Field-validator dead-code trim**: cycle-1 design-review removed defense-in-depth `isinstance` checks from `_validate_connector_acls` after empirically verifying Pydantic v2 native rejection of non-string outer keys, non-dict outer values, non-list inner values, and non-string inner entries. The validator body stays at the one invariant the annotation cannot express — exact inner-dict keys.

**Ripple-site enumeration confirmed by post-implementation grep** (`grep -rn "v1[3-9]\|flight 8\|Flight 8" the_one/db/_connector_types.py the_one/db/schema.py the_one/agents.md the_one/connectors/README.md tests/test_db_migration.py`):
- 4 `the_one/db/schema.py` prediction-comment sites updated (v13 block + v15/v16/v17 downstream blocks)
- 1 `the_one/db/_connector_types.py` module docstring updated (full v14–v18 owner enumeration, F8 CHECK = v19)
- 1 `the_one/agents.md:302` connector-type extension checklist item 4 updated (v18 = F6 L1c; F8 CHECK = v19)
- 2 `the_one/connectors/README.md` §6 sites updated (L297 schema-range reframe; L303 v15 → v19)
- 7 `tests/test_db_migration.py` docstring/prose sites updated (CURRENT_VERSION assertion + comment block; TestSchemaV13 cols docstring; 2 prose-line renumbers in the v13-cols docstring; TestSchemaV14 multi-line chain rewrite; TestSchemaV15 multi-line chain rewrite; TestSchemaV16 docstring renumber; TestSchemaV17 docstring renumber)
- 1 new `TestSchemaV18` class appended (3 tests)
- 6 new `TestSQLiteAgentStore` round-trip tests appended
- 1 new `TestAgentConfigConnectorAclsValidator` class appended (11 tests)
- NO site in the codebase now says "v18 = F8 CHECK" or names an earlier obsolete F8 CHECK version (v14/v15/v16/v17/v18 stale predictions all canonically v19)

**Validator behavior**: `None` accepted (default); `{}` accepted (semantically same as None per leg-3 read rule); per-account entries require EXACTLY `{"peers", "channels"}` — missing key raises with operator-facing message naming the missing keys; extra key raises naming the extras; empty inner lists permitted and preserved verbatim (agent narrows to nothing for this account). Non-string outer key, non-dict outer value, non-list inner value, non-string inner entry all rejected natively by Pydantic v2's annotation before the validator runs. The H2 closure test `test_validator_fires_on_repo_read_path_connector_acls` confirms the validator fires on `_row_to_config`'s direct-kwargs `AgentConfig(**kwargs)` construction (no `model_validate` wrapper needed).

**Tests**:
- `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py::TestSchemaV18` — 3 passed in 0.44s.
- `docker exec the-one pytest -x --timeout 30 tests/test_db_migration.py` — 43 passed in 6.75s (all migration tests including the updated CURRENT_VERSION assertion + 4 renumbered downstream docstrings).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py::TestSQLiteAgentStore tests/test_db_repositories.py::TestAgentConfigConnectorAclsValidator` — 32 passed in 3.72s (12 existing TestSQLiteAgentStore tests byte-identical + 6 new round-trip tests + 11 new validator tests + 3 existing pass-throughs).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py tests/test_db_api.py` — 171 passed in 24.57s (existing tests byte-identical).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_pool.py tests/test_connectors_session.py tests/test_connectors_resolver.py` — 104 passed in 8.24s (F1/F3/F4/F5 + leg-1a regression byte-identical).
- `docker exec the-one pytest -x --timeout 30` — 2032 passed, 4 skipped, 411 deselected in 136.97s (+20 over leg-1b baseline of 2012; new tests = 3 v18 migration + 6 repo round-trip + 11 validator = 20).
- `docker exec the-one ruff check the_one/agent/config.py the_one/db/schema.py the_one/db/repositories.py the_one/db/_connector_types.py tests/test_db_migration.py tests/test_db_repositories.py` — All checks passed.

**Post-condition asserts** (all pass):
- `from the_one.db.schema import CURRENT_VERSION; assert CURRENT_VERSION == 18` — green.
- `AgentConfig(name='n').connector_acls is None` — green.
- `AgentConfig(name='n', connector_acls={'acct-a': {'peers': ['u1'], 'channels': []}})` — accepted.
- `AgentConfig(name='n', connector_acls={'acct-a': {'peers': ['u1']}})` raises `ValidationError` (missing channels).
- `AgentConfig(name='n', connector_acls={'acct-a': {'peers': [], 'channels': [], 'extra': []}})` raises `ValidationError` (extra key).
- Round-trip `{}` ↔ DB: stored as JSON literal `"{}"`, loaded as `{}` (NOT collapsed to `None`).
- Round-trip `None` ↔ DB: stored as SQL NULL, loaded as `None`.

**Test counts**: leg adds 20 tests (3 v18 migration class + 6 TestSQLiteAgentStore round-trip + 11 TestAgentConfigConnectorAclsValidator). Total suite count: 2032 passed (+20 over leg-1b baseline).

Leg status: `landed`. Per the deferred-batched workflow for F6, no commit is made at this point — the Flight Director batches review + commit after the last autonomous leg.

### 2026-05-18 — Leg 2 landed

**Implemented**:
- `the_one/connectors/_pairing.py` — NEW module with the pure helper `_validate_pairing_prefix(text, code) -> tuple[bool, str]`. Single-space separator (`PAIR <code> <message>`). Empty-code guard returns `(False, text)` to defend against malformed pairing entries that slip past leg-1b's validator. ~40 lines including docstring.
- `the_one/db/repositories.py` — added `ChatSessionRepository.append_to_session_metadata(session_id, key, value)` immediately after `update_last_inbound` (template per the leg artifact). Reads-decodes-appends-writes the full `session_metadata` column; NULL → `{}`; missing key → `[]`; preserves other keys; defensive non-dict collapse mirrors `_row_to_model`. Raises `KeyError` on missing session (matches `update_last_inbound`).
- `the_one/connectors/_inbound.py` — extended the `dispatch_inbound` module docstring with the F6 contract block (resolver-always-called, audit-shape, last_inbound_at-not-bumped-on-Deny). Added imports: `from dataclasses import replace`, `from the_one.connectors._pairing import _validate_pairing_prefix`, widened `from the_one.connectors.base import ...` to also pull `Deny`, `NeedsPairing`, `_default_permit`. Inserted the resolver-consult block (4b) between `resolve_session` (L152) and the `async with session_locks[...]` block (L155). The block consults `getattr(plugin, "resolve", _default_permit)`, branches on `Deny` / `NeedsPairing` / `Permit`, writes audit entries via `append_to_session_metadata("audit", ...)`, mutates+persists `account.config["allowlist"]` on pairing success, and produces `working_envelope` for the in-lock `agent.step` call. Single-site behavioral diff: `agent.step(envelope.text)` → `agent.step(working_envelope.text)`. Agent loop and factory unchanged.
- `tests/_connector_dispatch_helpers.py` — added `StubPluginWithResolver(StubPlugin)` with class-level `resolve_outcome` (default `Permit()`), `resolve_calls` recording buffer, and `reset_for_test` override. Imports widened to include `Permit`, `ResolveOutcome`, `StubPlugin`, `ClassVar`.
- `tests/test_connectors_inbound.py` — added `TestF6Gating` class with 8 tests + per-class autouse `_reset_resolver_stub_state` fixture. Tests cover: stub-without-resolve permits via `_default_permit` fallback; `Permit()` dispatches with audit; `NeedsPairing` + valid prefix strips/persists/dispatches with cleaned text; `NeedsPairing` + invalid prefix denies silently; `NeedsPairing` + no prefix denies; `Deny` outcome logs+returns (no `agent.step`); pairing persistence survives a fresh `ConnectorAccountRepository` instance built on the same connection; audit entries accrue in order across 3 sequential inbounds. Imports widened to include `Deny`, `NeedsPairing`, `Permit` from `the_one.connectors.base` and `StubPluginWithResolver` from the helpers module.
- `tests/test_db_repositories.py` — appended 5 tests to `TestChatSessionRepository::TestChatSessionRepository`: NULL → `{}` init, absent-key list creation, existing-list append (order preserved), other-keys preserved, missing-session raises `KeyError`.
- DO-NOT-TOUCH discipline observed: `agent/core.py`, `agent/factory.py`, `connectors/_stub.py`, `connectors/base.py` (Protocol stays at 4 methods — `resolve` is getattr-discovered), `tools/connector_send.py:131` (leg-3 marker), `connectors/README.md:380` (leg-3 marker) all unchanged.

**Dispatcher diff site**: leg 2 inserts a single new block between L152 (`resolve_session` return) and L155 (`async with session_locks[...]`). The block runs for EVERY inbound (resolver consult + audit write fire on Permit, NeedsPairing-success, NeedsPairing-failure, and Deny). The only behavioral substitution inside the existing lock body is `agent.step(envelope.text)` → `agent.step(working_envelope.text)` at L193. `working_envelope` is bound to `envelope` on Permit (identical behavior) and to `replace(envelope, text=cleaned)` on NeedsPairing-success.

**Audit shape contract**: every gate decision appends `{"outcome": "permit"|"deny", "peer_id": str, "ts": iso_str, "reason": str | None}` to `session_metadata["audit"]: list[dict]`. `reason` is `None` for default-permit, `"paired"` on NeedsPairing-success, the `Deny.reason` on Deny, the `NeedsPairing.reason` (or `"invalid_pairing"` fallback if empty) on NeedsPairing-failure. Uniform 4-key shape means the leg-4 Studio renderer can read all four keys without per-entry shape checks.

**Pairing-prefix convention**: `PAIR <code> <message>` with single-space separators, case-sensitive `PAIR`, byte-equality on code. Empty code (absent pairing.code) never matches. Future plugins can use a different convention by implementing their own `resolve` hook that does the parsing internally and returns `Permit` (auto-pair) or `Deny` directly — the `NeedsPairing` outcome is what triggers the dispatcher's default `PAIR <code>` validation.

**last_inbound_at on Deny / NeedsPairing-failure**: the dispatcher returns BEFORE entering the per-session lock on these paths, so `update_last_inbound` does not fire. Denied messages do not extend the session continuation window — deliberate.

**Race-on-concurrent-pairing (F10 known limitation)**: two peers sending `PAIR <same code> <msg>` simultaneously each read the same `account.config["allowlist"]["peers"]`, each appends their distinct peer_id, each persists via `ConnectorAccountRepository.update(account)`. SQLite last-writer-wins on the `connector_accounts.config` JSON column means one peer_id may be lost. Operator can re-pair by re-issuing the prefix. F10 hardening may add a per-account write lock.

**Tests**:
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py::TestChatSessionRepository` — 18 passed in 3.15s (13 existing + 5 new `append_to_session_metadata`).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py` — 28 passed in 5.50s (20 existing F3/F4 byte-identical + 8 new TestF6Gating).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_resolver.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_connectors_pool.py` — 84 passed in 4.30s (F1/F3/F4/F5 + leg-1a byte-identical).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py tests/test_db_migration.py` — 168 passed in 21.16s (leg-1b + leg-1c byte-identical, +5 over leg-1c baseline for the new primitive tests).
- `docker exec the-one pytest -x --timeout 30` — 2045 passed, 4 skipped, 411 deselected in 148.99s (+13 over leg-1c baseline: 5 new TestChatSessionRepository + 8 new TestF6Gating).
- `docker exec the-one ruff check the_one/connectors/_pairing.py the_one/connectors/_inbound.py the_one/db/repositories.py tests/test_connectors_inbound.py tests/test_db_repositories.py tests/_connector_dispatch_helpers.py` — All checks passed.

**Post-condition asserts** (all pass):
- `_validate_pairing_prefix('PAIR X hello', 'X')` → `(True, 'hello')`.
- `_validate_pairing_prefix('PAIR wrong hello', 'X')` → `(False, 'PAIR wrong hello')`.
- `_validate_pairing_prefix('hello', '')` → `(False, 'hello')` (empty-code guard fires).
- `hasattr(ChatSessionRepository, 'append_to_session_metadata')` → True.
- `grep -rn "AllowlistResolver\|# F6:" the_one/` shows ONLY the leg-3-deferred sites: `tools/connector_send.py:131` (`# F6: AllowlistResolver consultation lands here.`) + `connectors/README.md:380` (quoted-marker reference). The leg-2 dispatcher block does NOT add new `# F6:` markers — the F6 contract is captured in the dispatcher module docstring instead.

**Test counts**: leg adds 13 tests (5 `TestChatSessionRepository::test_append_to_session_metadata_*` + 8 `TestF6Gating::test_*`). Total suite count: 2045 passed (+13 over leg-1c baseline of 2032).

Leg status: `landed`. Per the deferred-batched workflow for F6, no commit is made at this point — the Flight Director batches review + commit after the last autonomous leg.

### 2026-05-18 — Leg 3 landed

**Implemented**:
- `the_one/tools/connector_send.py` — module docstring lines 11-13 rewritten from the "F6 territory" placeholder note to the leg-3 contract ("Channel/per-agent ACLs are consulted at execute time via a per-call account fetch (M10 F6 L3); default-permit on absence."). `__init__` (lines 89-100) widened with `connector_acls: dict[str, dict[str, list[str]]] | None = None` kwarg between `connector_account_ids` and the body; stored as `self._connector_acls`. `execute()` consult block replaces the `# F6:` marker comment at line 131: function-local imports (`settings`, `get_connection`, `ConnectorAccountRepository`, `get_encryptor`) mirror `connectors/_inbound.py:130-142`'s precedent; per-call `acc_repo.get(account_id)` fetch with `KeyError` defensive catch → `[error] [constraint] account_id <id> not found`; account-scope channel check (absent allowlist → permit; channel_id not in allowlist["channels"] → `[error] [constraint] channel_id <id> is not reachable on account <id>`); per-agent ACL channel check (None or account_id absent → inherit; empty channels list → inherit per leg-1c; non-empty + channel_id not in list → `[error] [constraint] channel_id <id> is not reachable for this agent on account <id>`).
- `the_one/tools/builtins.py` — `BuiltinToolProvider.get_tools` signature widened with `connector_acls: dict[str, dict[str, list[str]]] | None = None` (kwarg-only sibling to `connector_account_ids`). `extra_kwargs` at the `SendToPlatformChannelTool` special-case branch threads `connector_acls=connector_acls` through. Two-line change.
- `the_one/agent/factory.py` — `BuiltinToolProvider` call site at L316-321 extended with `connector_acls=config.connector_acls`. ONE-line change. `ToolProvider` Protocol UNCHANGED — cycle-2 finding #4 closed by retaining the existing `isinstance(provider, BuiltinToolProvider)` branch at L314-331 that already isinstance-branches widened kwargs.
- `the_one/connectors/README.md` — §11 step 2 prose updated from the F6 placeholder marker text ("The `# F6: AllowlistResolver consultation lands here` marker is the hook for F6's channel/thread/peer ACL.") to describe the actual leg-3 consultation: per-call `ConnectorAccountRepository.get(account_id)` reads current account state, intersects `target.channel_id` against account-scope and per-agent ACL gates, defaults permit on absent gates. Names `connector_send.py:execute` + `AgentConfig.connector_acls` as the source of truth.
- `tests/test_connector_send_tool.py` — appended new `TestF6OutboundGating` class with 9 tests + `_seed_stub_account_with_config` helper. The existing `TestPoolAcquireFailures::test_unknown_account_id_returns_keyerror_envelope` was renamed to `test_unknown_account_id_returns_constraint_envelope` to reflect the leg-3 behavioral substitution: the missing-account case now surfaces a `[error] [constraint] account_id <id> not found` envelope at the new consult site BEFORE reaching `pool_acquire` (the F6 consult intercepts the `KeyError` earlier and with a friendlier shape). All other F4 tests pass byte-identically.

**Consultation site**: `the_one/tools/connector_send.py:execute()` between the F4 account-scope check (L125) and `pool_acquire` (now around L182). The block is a single function-local imports → repo construction → defensive `try/except KeyError` → two intersection branches (account-scope, then per-agent ACL). Each branch is an EARLY RETURN; on permit, control flows through to the existing pool-acquire + client.send path unchanged. F4 success path (`PLATFORM_SEND_OK_PREFIX` envelope) preserved byte-for-byte.

**ToolProvider non-widening defense (cycle-2 finding #4 closure)**: The `ToolProvider` Protocol at `the_one/tools/base.py` stays at the existing 3-arg `get_tools` shape. The F4 pattern at `factory.py:314-331` continues to isinstance-branch on `BuiltinToolProvider`: builtin gets the widened kwargs (`connector_account_ids`, `connector_acls`); non-builtin (test stubs, future provider types) gets the unwidened signature. Leg 3 adds ONE kwarg (`connector_acls`) to the existing widened path. F8 may eventually justify Protocol widening once a third factory-time-kwarg case emerges; not yet.

**Per-call account fetch performance acceptance**: each `execute()` invocation incurs ONE `ConnectorAccountRepository.get(account_id)` round-trip (single SELECT by primary key) before pool_acquire. Trade-off documented in the flight Design Decision: snapshot-at-construction would have avoided the fetch but admitted stale state on mid-session allowlist edits. Per-call fetch is the chosen path because operator-edited allowlists must take effect immediately. SQLite read concurrency means multiple agents firing the tool simultaneously do not interfere.

**README marker closure**: the leg-1a deferred "Future home of AllowlistResolver" prose and the `# F6: AllowlistResolver consultation lands here` quoted marker were the final two sites referencing F6's planning-time framing. Both are now closed. Post-condition grep: `grep -rn "AllowlistResolver" the_one/` returns ZERO hits; `grep -n "# F6:" the_one/tools/connector_send.py` returns ZERO hits.

**Tests**:
- `docker exec the-one pytest -x --timeout 30 tests/test_connector_send_tool.py` — 38 passed in 3.41s (29 existing F4 + 9 new `TestF6OutboundGating` cases).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py tests/test_connectors_resolver.py` — 34 passed in 5.43s (leg-1a + leg-2 byte-identical).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_connectors_pool.py` — 78 passed in 4.53s (F1/F3/F4/F5 byte-identical).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py tests/test_db_migration.py tests/test_db_api.py` — 219 passed in 31.67s (leg-1b + leg-1c byte-identical).
- `docker exec the-one pytest -x --timeout 30` — 2055 passed, 4 skipped, 411 deselected in 141.52s (+10 over leg-2 baseline of 2045 — 9 new `TestF6OutboundGating` cases; the renamed existing test does not change count).
- `docker exec the-one ruff check the_one/tools/connector_send.py the_one/tools/builtins.py the_one/agent/factory.py tests/test_connector_send_tool.py` — All checks passed!

**Post-condition asserts** (all pass):
- `grep -n "# F6:" the_one/tools/connector_send.py` → ZERO hits (marker replaced).
- `grep -rn "AllowlistResolver" the_one/` → ZERO hits (leg-1a deferred sites closed).
- `python -c "from the_one.tools.connector_send import SendToPlatformChannelTool; t = SendToPlatformChannelTool(connector_acls={'a': {'peers': [], 'channels': ['c1']}}); print(t._connector_acls)"` → `{'a': {'peers': [], 'channels': ['c1']}}`.

**Test counts**: leg adds 9 tests (all `TestF6OutboundGating::test_*`). Permit-when-no-allowlist-no-acl; permit-when-channel-in-account-allowlist-no-acl; deny-when-channel-not-in-account-allowlist; deny-when-channel-in-account-but-not-in-per-agent-acl; permit-when-per-agent-acl-has-empty-channels-list (inherit); permit-when-per-agent-acl-account-id-absent (inherit); permit-when-channel-in-both-account-allowlist-and-per-agent-acl (intersection-positive); keyerror-on-mid-call-account-deletion-returns-constraint; F4-account-scope-denial-still-works (regression pin); empty-channels-lockdown-denies (leg-1b edge case). Total suite count: 2055 passed (+10 over leg-2 baseline of 2045).

**F4 contract substitution note**: the previously-named `test_unknown_account_id_returns_keyerror_envelope` test was renamed to `test_unknown_account_id_returns_constraint_envelope` to reflect the leg-3-induced behavior change. The case (account-id absent from DB) used to surface `[error] KeyError: ...` from `_pool._load_account`; post-leg-3, the F6 consult's per-call `ConnectorAccountRepository.get` raises `KeyError` first and is caught defensively → `[error] [constraint] account_id <id> not found`. Both shapes are `[error]`-prefixed (and neither shape starts with `PLATFORM_SEND_OK_PREFIX`), so the dispatcher visibility-tagger contract is preserved. The F4 success-path envelope is byte-identical.

Leg status: `landed`. Per the deferred-batched workflow for F6, no commit is made at this point — the Flight Director batches review + commit after the last autonomous leg.

### 2026-05-18 — Leg 4 landed

**Implemented**:
- `the_one/interfaces/web/api.py`:
  - Imports: added `now_iso` to the `from the_one.db.models import (...)` block.
  - New endpoint `POST /api/connector-accounts/{account_id}/pairing-code` (inserted between the DELETE handler and the `test/connect` route, near L2244). Generates an 8-hex code via `secrets.token_hex(4)`, sets `account.config["pairing"] = {"code": code, "issued_at": now_iso()}`, persists via `ConnectorAccountRepository.update`, returns `{"code": code, "issued_at": iso}`. Pre-existing reserved + non-reserved config keys (`allowlist`, `intent`, …) are preserved via `model_copy(update={"config": new_config})` + round-trip through `ConnectorAccount.model_validate(...)` so leg-1b's `@field_validator` fires on the merged payload. 404 on unknown account. Does NOT trigger warm-pool eviction (matches the existing PUT handler's contract — only `secrets` change triggers eviction).
  - New endpoint `GET /api/connector-accounts/{account_id}/attached-agents`. Returns `[{"name": str, "peers_count": int, "channels_count": int}, ...]` for agents whose `connector_account_ids` includes `account_id`. Counts derive from `agent.connector_acls[account_id]["peers"]` / `["channels"]` (0 each when the per-agent ACL is None or has no entry for this account — inherit / default-permit semantic per leg 1c). 404 on unknown account. Uses the existing `_connector_repo()` + `_agent_store()` helpers; iterates `store.list_agents()` and `store.load(name)` per agent (O(N) — acknowledged below).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` (~330 lines added):
  - Three new section renderers inserted between the Lifecycle and Test Connection sections (edit-mode only, mirroring the existing `if (!isCreate)` gates on Test Connection + Danger Zone):
    1. **Pairing** (`renderPairingSection`) — issued-at status row + `[Generate code]` / `[Regenerate code]` button + a hidden reveal row that shows the returned code in a read-only input with a Copy button (clipboard API path with execCommand fallback). The code is NOT shown on initial render even when `config.pairing` is present (leg-1b decision: stored plaintext, but no auto-display; the operator copies-on-generation or regenerates).
    2. **Account-scope allowlist** (`renderAllowlistSection`) — a checkbox `[ ] Enable account-level allowlist` gating two list editors (peers, channels). Each list has an `+ Add` button and per-row remove buttons; existing entries pre-populated from `config.allowlist`. Delegated event handling on the section so dynamically-added rows participate without rebinding. Newly-added rows auto-focus for keyboard reachability.
    3. **Attached agents** (`renderAttachedAgentsSection` + `fetchAttachedAgents` + `renderAttachedAgentsList`) — read-only list fetched from `GET /api/connector-accounts/{id}/attached-agents` on editor mount. Renders `name peers:N channels:M` rows with a deep-link `#studio/agents/{name}` (leg 5 will route this to the Connectors tab; for now the link goes to the agent editor's default tab per the existing routing fallback). Failure modes (non-OK status, network error) render an explicit error message rather than leaving the "Loading…" placeholder in place.
  - `collectConfigRows` now filters reserved keys (`pairing`, `allowlist`) — added a module-level `RESERVED_CONFIG_KEYS` map — so the arbitrary kv-table no longer renders those keys as duplicate operator-editable rows. The dedicated sections are the only writers.
  - `collectFormData` extended with the merge step. Reserved-key sources of truth: `account.config.pairing` (mirrored by the pairing button click handler into the in-memory account) and the allowlist toggle + list editors. When the allowlist toggle is OFF, the save payload OMITS `config.allowlist` (default-permit). When ON, it emits `{"peers": [...], "channels": [...]}` even when both lists are empty — the lockdown affordance (leg-1b empty-preservation invariant). The pairing key is only merged if `account.config.pairing` exists. Arbitrary non-reserved kv-table keys round-trip verbatim — no key is silently dropped.
  - `getFormSnapshot` extended to include the allowlist toggle + row state so the dirty-tracker fires on toggle / row changes. Pairing is NOT a dirty source — the pairing-code endpoint persists immediately and independently of the editor's Save button (consistent with the leg artifact's "Pairing-code click while editor is dirty" edge case).
  - `wireEditorEvents` extended (edit-mode only) to call `wirePairingEvents`, `wirePairingCopyEvents`, `wireAllowlistEvents`, then kick off `fetchAttachedAgents(container, account.id)`. The pairing handler writes the returned code into the local `account.config.pairing` mirror so a subsequent Save click round-trips through `collectFormData`'s merge step without re-fetching the account.
- `tests/test_db_api.py` — appended `TestConnectorAccountPairingCodeAndAttached` class (10 tests, plus a `_isolation` autouse fixture verbatim-copied from `TestConnectorAccountAPI` per the class-scope-doesn't-propagate convention codified in F2 L4):
  - `test_generate_pairing_code_returns_8_hex_code_and_iso_issued_at`
  - `test_generate_pairing_code_updates_account_config_pairing`
  - `test_regenerate_pairing_code_replaces_previous_code`
  - `test_generate_pairing_code_preserves_other_config_keys` (with `intent` + `allowlist` pre-existing)
  - `test_generate_pairing_code_404_on_unknown_account`
  - `test_attached_agents_empty_when_no_agents_attached`
  - `test_attached_agents_returns_attached_with_zero_counts_when_no_acl`
  - `test_attached_agents_includes_acl_peer_and_channel_counts` (3-agent scenario: with-ACL counts; no-ACL inherits zero counts; unrelated agent excluded entirely)
  - `test_attached_agents_404_on_unknown_account`
  - `test_put_account_with_empty_allowlist_lockdown_survives_get` — the leg-1b empty-preservation invariant pinned at the API edge (complements the existing repository-level and storage-level tests in `test_db_repositories.py`).
- DO-NOT-TOUCH discipline observed: `ToolProvider` Protocol unchanged; `AgentConfig.connector_acls` shape unchanged (leg 1c); the existing PUT handler at `api.py:2169-2240` unchanged (pairing + allowlist round-trip through it because both live inside `data["config"]` and leg-1b's `@field_validator` already governs the shape); `the_one/db/models.py` unchanged; `the_one/db/repositories.py` unchanged; `the_one/interfaces/web/static/js/areas/studio.js` mount-site call unchanged (the editor widens its sections without changing the mount contract); existing editor sections (Connection, Credentials, Lifecycle, Test Connection, Danger Zone) unchanged in behavior.

**Endpoint shapes** (canonical for leg-5 + leg-7 HAT consumers):
- `POST /api/connector-accounts/{id}/pairing-code` → 200 `{"code": "<8 lowercase hex>", "issued_at": "<ISO 8601 with T>"}` | 404 `{"detail": "Connector account not found: <id>"}`.
- `GET /api/connector-accounts/{id}/attached-agents` → 200 `[{"name": str, "peers_count": int, "channels_count": int}, ...]` (empty list when nothing attached) | 404 `{"detail": "Connector account not found: <id>"}`.

**Attached-agents O(N) acknowledgment**: each GET iterates `SQLiteAgentStore.list_agents()` then loads every agent via `store.load(name)` and filters by `account_id in cfg.connector_account_ids`. For the operator's typical agent count (<50) this is well under the verification budget's 30s timeout. If the count grows, a JSON-extract query against the `connector_account_ids` column would scale better — F10 territory; not a leg-4 concern.

**Leg-1b empty-preservation at the API edge**: `test_put_account_with_empty_allowlist_lockdown_survives_get` PUT-s `{config: {allowlist: {peers: [], channels: []}}}` and asserts the subsequent GET returns the allowlist verbatim (NOT absent, NOT coerced to null). This complements the existing repository-level tests in `test_db_repositories.py` (`test_empty_allowlist_round_trips_through_repo`, `test_empty_allowlist_stored_as_lists_not_null`) by pinning the round-trip at the operator-facing layer that the leg-4 Studio writer actually traverses.

**Pairing-code mirror into local `account.config`**: the pairing-button click handler updates `account.config.pairing = {code, issued_at}` in-memory after the POST returns. This is the source-of-truth `collectFormData` reads from when merging into the save payload, so a subsequent Save click round-trips the freshly-generated pairing without re-fetching the account from the server. Cancel still works the same way (re-renders from the original `account` argument, which the Flight Director / studio mount holds — leg 4 does NOT mutate that reference outside of the explicit `account.config.pairing` write on a successful POST).

**Reserved keys filtered from the kv-table**: `collectConfigRows` now skips `pairing` and `allowlist`. Without this, the kv-table would render them as JSON-stringified rows that the operator could accidentally edit, creating a save-time conflict with the dedicated section. The merge step in `collectFormData` would silently overwrite operator edits — preferable to skip rendering them altogether. The arbitrary kv-table continues to round-trip every NON-reserved key verbatim.

**Conservative-call decisions in the JS layer** (no JS unit tests; leg-7 HAT is the regression net):
- Pairing code shown ONCE per generation (not auto-displayed on initial render even when `config.pairing` is present). This matches the leg-1b decision and the operator's expected workflow (copy-on-generate, regenerate-when-forgotten).
- Deep-link to `#studio/agents/{name}` (no tab fragment yet). Leg 5 routes the Connectors tab; until then the agent editor's default-tab fallback at `studio.js:161` handles it gracefully.
- Allowlist add-button auto-focus on the newly-created row (keyboard reachability).
- Failure modes for the attached-agents fetch render an explicit error message rather than persisting the "Loading…" placeholder.
- Copy button uses `navigator.clipboard.writeText` with a `document.execCommand('copy')` fallback for older / non-secure-context environments.

**Verification budget**:
- `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py` — 61 passed in 12.25s (51 existing + 10 new).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py tests/test_db_migration.py` — 168 passed in 21.91s (leg-1b + leg-1c byte-identical).
- `docker exec the-one pytest -x --timeout 30 tests/test_connector_send_tool.py tests/test_connectors_inbound.py tests/test_connectors_resolver.py` — 72 passed in 8.80s (leg-1a + leg-2 + leg-3 byte-identical).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_connectors_pool.py` — 78 passed in 5.05s (F1/F3/F4/F5 byte-identical).
- `docker exec the-one pytest -x --timeout 30` — 2065 passed, 4 skipped, 411 deselected in 144.03s. +10 over leg-3 baseline of 2055, matching the 10 new `TestConnectorAccountPairingCodeAndAttached` cases.
- `docker exec the-one ruff check the_one/interfaces/web/api.py tests/test_db_api.py` — All checks passed.
- JS code is NOT ruff-checked (Python-only linter); `node --check` confirmed JS syntax validity. The existing editor's style (semis, `var`, JSDoc-light) is the de facto linter; new code follows it.

**Test counts**: leg adds 10 tests (5 pairing-code + 4 attached-agents + 1 empty-allowlist API-edge round-trip), matching the leg AC's "≥10" requirement. Total suite count: 2065 passed (+10 over leg-3 baseline of 2055).

Leg status: `landed`. Per the deferred-batched workflow for F6, no commit is made at this point — the Flight Director batches review + commit after the last autonomous leg.

### 2026-05-18 — Leg 5 landed

**Implemented**:
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js`: NEW module (~280 lines) mirroring `mcps-tab.js` shape. Exports `App.studio.renderConnectorsTab(panel, agent, allConnectorAccounts, callbacks)`. Each connector account renders as an `.mcp-source-tile.connector-account-tile` (visual class reuse — no new CSS introduced this leg) with a `data-connector-account-toggle` + `data-connector-account-id` checkbox on the summary line and a collapsible details body that lazily mounts the per-account ACL editor on first expand. The ACL editor uses two `chip-list-editor` wrappers (one for peers, one for channels) tagged with `data-connector-acl-account="{id}"` + `data-connector-acl-list="peers"|"channels"` for the save-flow walk. Chip add/remove behavior is wired via `App.adminFormHelpers.wireChipListEditor`, matching the canonical chip-area pattern. Stale connector_account_ids (operator deleted the account from the Connectors surface but it remains pinned on the agent) surface as a row with a "missing — account deleted" badge; the operator must explicitly un-toggle to prune — mirrors the MCP-source-deletion defensive pattern.
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js`:
  - `PANEL_IDS` extended with `connectors: 'agent-tab-panel-connectors'`.
  - Tablist HTML extended with a "Connectors" button between MCPs and Built-in Tools (`data-tab-id="connectors"`, `data-testid="tab-connectors"`).
  - Tabpanels extended with the matching `<div role="tabpanel">`.
  - Mount loop fetches the new panel and calls `renderConnectorsTab(connectorsPanel, agent, callbacks.allConnectorAccounts, { onChange: callbacks.onChange })`.
- `the_one/interfaces/web/static/js/areas/studio.js`:
  - `self._allConnectorAccounts = []` added to per-instance state (mirror of `_allMcpSources`).
  - Tab whitelist at the agent-route parser extended: `tab === 'general' || tab === 'knowledge' || tab === 'mcps' || tab === 'connectors' || tab === 'tools'` so the deep-link `#studio/agents/{name}/connectors` activates the new tab (leg 4's link target).
  - New `fetchConnectorAccountsList()` (GET `/api/connector-accounts`) and `refreshConnectorAccountsCache()` (mirror of `refreshMcpSourcesCache`).
  - Both `Promise.all([refreshToolConfigsCache(), refreshMcpSourcesCache()])` sites in `doSelect` and `doEnterCreateMode` extended with `refreshConnectorAccountsCache()` so an account created/deleted on the connector-accounts surface is reflected immediately on the next agent-edit mount.
  - `loadAll()` extended with `fetchConnectorAccountsList()` so the studio area's initial mount populates `_allConnectorAccounts` alongside the other entity lists.
  - `renderEditor` callbacks-bag now includes `allConnectorAccounts: self._allConnectorAccounts` (sibling of `allMcpSources`).
  - `collectFormData` extended with two walks: (a) `[data-connector-account-toggle][data-connector-account-id]:checked` → `data.connector_account_ids`; (b) `.connector-acl-chiplist[data-connector-acl-account][data-connector-acl-list]` → `data.connector_acls` grouped by account id and list-kind. Chip values are read from `.chip` textContent (sans trailing × glyph, mirroring `readChipListValue` from admin/tools-form-helpers.js). An account_id entry whose both inner lists are empty is OMITTED from the serialized payload (the leg-1c "absent = empty = inherit" semantic); `data.connector_acls = null` when the outer dict is empty (matches the `tool_overrides` / `mcp_overrides` null-vs-{} precedent).
- `the_one/interfaces/web/static/index.html`: registered the new `connectors-tab.js` `<script>` tag immediately after `mcps-tab.js`.

**F4-General-tab chip-area migration outcome**: NONE — the pre-leg grep `grep -rn "connector_account_ids\|connector-account-toggle\|connectorAccountId\|allConnectorAccounts" the_one/interfaces/web/static/js/` returned only a single match (a docstring reference inside `connector-account-editor.js`). F4 L5 persisted the field without shipping any General-tab chip-area surface, so leg 5 introduced the agent-side attachment UI fresh in the new Connectors tab. No migration was required; no existing tests asserted on a General-tab chip-area for connectors.

**Inherit-affordance labeling**: when an attached account has empty (or absent) per-account ACL, the details panel shows an inline `.connector-account-acl-inherit-label` element reading "no restrictions — inherits account-scope" above the (empty) peers + channels chip-lists. The label has a `data-testid="connector-account-acl-inherit-{id}"` selector for future HAT coverage and re-syncs on every chip add/remove — adding the first peer or channel hides the label so the visible state distinguishes "empty = inherit" from "populated = narrowing." The save-flow walk also OMITS an account entry whose both lists are empty from the serialized payload, so the persisted JSON matches the visual state.

**Save-flow round-trip**: `data.connector_account_ids` comes from the toggle selectors; `data.connector_acls` comes from the chip-list walk; the existing PUT handler at `api.py:537` calls `AgentConfig.model_validate(data)` which fires leg-1c's `_validate_connector_acls`. End-to-end works without backend changes. `ruff check the_one/interfaces/web/api.py` confirms no Python changes were introduced.

**Tests** (regression-net, no new test files — JS-only leg; HAT validates the new tab surface):
- `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py` — 61 passed in 12.26s (byte-identical to leg-4 baseline).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py tests/test_db_migration.py` — 168 passed in 21.64s (leg-1b + leg-1c byte-identical).
- `docker exec the-one pytest -x --timeout 30 tests/test_connector_send_tool.py tests/test_connectors_inbound.py tests/test_connectors_resolver.py` — 72 passed in 10.53s (leg-1a + leg-2 + leg-3 byte-identical).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_connectors_pool.py` — 78 passed in 4.40s (F1/F3/F4/F5 byte-identical).
- `docker exec the-one pytest -x --timeout 30` — 2065 passed, 4 skipped, 411 deselected in 142.37s. Test counts byte-identical to leg-4 baseline (2065) — leg 5 is JS-only; no Python tests added or removed.
- `node --check` clean on all three touched JS modules (`connectors-tab.js`, `agent-editor.js`, `studio.js`).
- `ruff check the_one/interfaces/web/api.py` — All checks passed (no Python changes expected, none made).

**Post-condition asserts** (all pass):
- `grep -n "data-connector-account-toggle" the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` → matches at L20 (header comment) and L120 (setAttribute call on the checkbox) — selector present.
- `grep -n "'connectors'" the_one/interfaces/web/static/js/areas/studio.js` → multiple hits including L161 (the extended four-→five-tab whitelist) — tab whitelist updated.
- `grep -n "renderConnectorsTab" the_one/interfaces/web/static/js/areas/studio/agent-editor.js` → L172 (the mount-loop call) — mount call present.

**Conservative-call decisions** (no JS unit tests; leg-7 HAT is the regression net):
- Reused the `.mcp-source-tile*` CSS classes wholesale (with additive `.connector-account-tile` class for any future divergence) to avoid introducing new CSS in a JS-only leg. Visual parity with MCPs tab is intentional — both surfaces are operator-managed entity-with-toggle lists.
- Per-account ACL editor mounts lazily on first expand. This avoids wiring chip-list listeners for accounts the operator never opens (most agents will attach few accounts) and keeps the initial render cheap for many-account installs.
- Stale connector_account_ids surface as a defensive "missing — account deleted" row rather than silently pruning. This matches the MCP-source-deletion behavior and gives the operator visibility into the misalignment. The save flow leaves the stale id in the list unless the operator explicitly un-checks.
- Inherit-affordance label syncs on every chip change (not just initial render) so the operator gets immediate visual feedback when narrowing/widening the ACL.
- No deep-link sub-route within the Connectors tab (unlike MCPs' `#studio/agents/{name}/mcps/{source-id}`). Per-account expansion state is per-session; deep-linking into a specific account's ACL editor is out of scope.
- Detach-while-ACL-populated does NOT clear the ACL entry (the leg-5 edge case noted in the leg artifact). Re-attaching re-applies the prior ACL. A "clear ACL on detach" affordance is left as F10 polish.

**Test counts**: leg adds 0 backend tests (JS-only). Total suite count unchanged: 2065 passed (byte-identical to leg-4 baseline). HAT (leg 7) validates the new Connectors tab surface end-to-end.

Leg status: `landed`. Per the deferred-batched workflow for F6, no commit is made at this point — the Flight Director batches review + commit after the last autonomous leg.

### 2026-05-18 — Leg 6 landed

**Implemented**:
- `the_one/interfaces/web/app.py:817-831`: replaced the bare `user_event = {"type": "user", ...}` dict-literal at the live-broadcast site inside `_process_and_broadcast` with the F6 L6 conditional projection. The dict is now annotated `dict[str, Any]` (defensive — accommodates the conditional `visibility` assignment without narrowing-from-literal mypy concerns) and a guarded `if session.platform is not None: user_event["visibility"] = OPERATOR_VISIBILITY` block precedes both `session.add_event(user_event)` and `_send_to_session(...)`. The inline comment block cites the F5 carry-forward source (`L997-1004` is the refresh-path Message-level tagging which remains untouched), the codec projection precedent at `db/codec.py:173-176` (only emit the key when meaningful), and the lock-serialization invariant (`session_locks[session.id]` at `app.py:258` vs `connectors/_inbound.py:155`). No other site in `app.py` is touched.
- `missions/10-bi-directional-comms-connectors/mission.md:104`: flipped the "Live-broadcast WS-typed visibility-tagging asymmetry" Known Issue from `[ ]` to `[x]` and appended the closure note `Closed by Flight 6 Leg 6 — operator-typed messages on connector-attached sessions now carry visibility=operator at live broadcast time; refresh path is unchanged.` to the bullet.
- `tests/test_ws_storage_edge_shim_visibility.py`: appended two F6 L6 tests (sections #9 and #10) reusing the existing `_ShimStubAgent` + `_patch_broadcast_and_save` fixtures from the F5 storage-edge shim file (the canonical precedent — the captured-broadcast pattern is the cleanest way to inspect what crosses the WS):
  - `test_live_broadcast_carries_operator_visibility_on_connector_attached_session` — builds a `Session(..., platform="stub")`, drives `_process_and_broadcast(...)`, asserts the first captured broadcast event has `type=="user"` and `visibility==OPERATOR_VISIBILITY`.
  - `test_live_broadcast_omits_visibility_on_web_native_session` — same shape with `platform=None`; asserts `"visibility" not in user_event` (mirrors the codec projection rule — only emit the key when meaningful, no `None` sentinel in the wire payload).
- DO-NOT-TOUCH discipline observed: the post-step Message-level tagging at `app.py:997-1004` (the refresh path) is UNCHANGED; the `_resume_paused_session` symmetric shim is unchanged; `connectors/_inbound.py` is unchanged (its broadcast already projects visibility through the codec at `db/codec.py:173-176`); no JS changes (render-side wiring through `addMsg`/`buildToolMsg`/the streaming-bubble closure has already been consuming `data.visibility` since F5).

**F5 carry-forward closure confirmed**: the F5 storage-edge shim's job (persistence + refresh-render) is byte-identical to before this leg — leg 6 attaches the visibility key at the BROADCAST dict-literal source, ahead of `agent.step()`. The refresh path's post-step Message-level tagging at L997-1004 still runs, still tags the persisted `Message.visibility`. The two sites are independent — live broadcast and persistence are now both operator-tagged at the right moment for their respective consumers. The F5 debrief's tagged Known Issue is closed atomically by this leg.

**Codec projection mirroring**: the leg adopts the codec's "only emit the key when meaningful" rule at `db/codec.py:173-176`. On `session.platform is None` (web-native session), the `visibility` key is ABSENT from the broadcast dict, not `None`. The renderer treats absent as no-tag (peer-visible) via the existing `data.visibility` truthy-check; this matches the codec's wire-format precedent and avoids the surface-area-widening that a `null` sentinel would imply.

**Tests**:
- `docker exec the-one pytest -x --timeout 30 tests/test_ws_storage_edge_shim_visibility.py` — 10 passed in 0.23s (8 existing F5 + 2 new F6 L6 cases).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py` — 31 passed in 8.09s (leg-2 + F5 byte-identical).
- `docker exec the-one ruff check the_one/interfaces/web/app.py` — All checks passed.
- `docker exec the-one pytest -x --timeout 30` — 2067 passed, 4 skipped, 411 deselected in 142.51s. +2 over leg-5 baseline of 2065, matching the 2 new F6 L6 test cases.

**Post-condition asserts** (all pass):
- `grep -n "M10 F06 L6" the_one/interfaces/web/app.py` → L818 (the inline comment block header) — injection comment present.
- `grep -n "Closed by Flight 6 Leg 6" missions/10-bi-directional-comms-connectors/mission.md` → L104 (closure note appended to the Known Issue bullet) — closure note present.
- `grep -n "^- \[x\] \*\*Live-broadcast WS-typed" missions/10-bi-directional-comms-connectors/mission.md` → L104 — checkbox flipped from `[ ]` to `[x]`.

**Test counts**: leg adds 2 tests (both in `tests/test_ws_storage_edge_shim_visibility.py`). Total suite count: 2067 passed (+2 over leg-5 baseline of 2065).

Leg status: `landed`. Per the deferred-batched workflow for F6, no commit is made at this point — the Flight Director batches review + commit after the last autonomous leg.

---

## Decisions

### Cycle-1 architect review (2026-05-18) — approve with changes
**Context**: Architect review of the v1 flight spec surfaced 3 high-severity issues, 5 medium, and a handful of low-severity items.
**High-severity issues**:
- H1: Protocol-satisfaction stance contradictory across §1 / Key non-modifications / Leg 1 (three different framings)
- H2: `session_metadata` writer was misclassified as already-satisfied substrate — `ChatSessionRepository.update()` explicitly excludes the column per `db/repositories.py:758-772`
- H3: Outbound resolver injection has three viable shapes (Protocol widening, snapshot-at-construction, per-call fetch) and the choice shapes Leg 1's hook signature; cannot be deferred to per-leg design
**Medium-severity issues**:
- M1: Leg 1 conflates Protocol + state schema + persistence + tests (too big)
- M2: Pydantic validators on `dict[str, Any]` don't fire on JSON read path without explicit `model_validate` — leg 1 must walk both read paths
- M3: Leg 6 framing was misframed as Message-level tagging — the live broadcast emits a raw dict-literal, not a Message
- M4: Open Question #4 (ToolProvider widening) was NOT correctly deferred — structurally tied to resolver shape
- M5: Per-agent ACL persistence location ambiguous (mixed framings — `AgentConfig` field vs nested in `config["allowlist"]`)
**Low-severity issues**: adaptation-criteria wording, Studio tab routing site walk, attached-agents reverse-lookup API recon
**Resolutions** (user-confirmed, recommended-option path on all four):
- H1 + Question on resolver stance → **optional hook via getattr** (mirrors F3's `display_channel`); stub does NOT implement; `_default_permit` fallback
- H2 → **new narrow primitive** `ChatSessionRepository.append_to_session_metadata` ships in leg 2 (mirrors `update_last_inbound` shape)
- H3 → **per-call repository fetch + ACL kwarg** in `SendToPlatformChannelTool.execute`; no `ToolProvider` widening
- M5 → **`AgentConfig.connector_acls`** field; v18 migration; mirrors `connector_account_ids` F4 L5 path exactly
- M1 → leg 1 SPLIT into 1a (Protocol + outcomes), 1b (account config schema + validators), 1c (AgentConfig + v18 migration)
- M3 → leg 6 reframed as dict-literal injection at `app.py:817-819` (not Message-level)
- M2 → leg 1b design walks `model_validate` (PUT path at `api.py:2218`) and `_row_to_model` (read path) explicitly; decides whether to add `model_validate` on read or accept one-sided validation
- M4 → ToolProvider widening explicitly deferred to F8 in Key non-modifications
**Impact**: Flight spec rewritten (cycle 1 → cycle 2). Legs: 7 → 9 (6 autonomous L1a/L1b/L1c/L2/L3/L4/L5/L6 + 1 required HAT = 8 autonomous + 1 HAT). v18 schema migration ADDED to flight scope (was previously "no schema migration").

### Cycle-2 architect review (2026-05-18) — approve
**Context**: Re-review of the revised flight spec after cycle-1 resolutions.
**Cycle-1 closure verification**: H1 closed, H2 closed, H3 closed, M1 closed, M2 partially closed (binary read-path validator decision correctly punted to leg-1b design), M3 closed, M4 closed, M5 closed.
**New findings** (all leg-design-time, none flight-spec-blocking):
- [medium] Leg-2 test fixture strategy named but not committed — "register_for_test variant stub OR monkeypatch the dispatcher consult site" is two mechanisms with different blast radii. Leg-2 design picks one of: (a) `StubPluginWithResolver` variant fixture, (b) monkeypatch the `getattr` consult site, (c) parametrized stub with constructor flag.
- [medium] Leg 1c's "mirrors F4 L5 exactly" needs the v18 ripple-site enumeration. F4 L5 sub-leg A touched 6+ ancillary sites: `_connector_types.py` v17 docstrings, `schema.py` inline comments referencing future flight, `agents.md` connector-type checklist, `test_db_migration.py` `CURRENT_VERSION` assertion + `TestSchemaV18` class + downstream-renumber docstrings. Leg 1c design must run `grep -n 'v18\|v17' the_one/ tests/` and enumerate ripple sites.
- [low] Adaptation Criteria #2 backfill default ("NULL → inherit") is correct but the spec could state more clearly that "attaching an account is the per-agent grant; per-agent ACL exists to NARROW, not to gate attachment." One-line note recommended in the Empty-ACL Design Decision.
- [low] "Mirrors F4 L5 exactly" framing is slightly misleading (F4 L5 was the FIX for a leg-1 gap, not the canonical pattern). Recommended rewording: "Adopts the F4 L5 sub-leg A pattern atomically — Pydantic field + ALTER TABLE + repository round-trip ship in one leg, as F4 debrief rec #1 prescribes."
- [low] `connector_acls` type annotation `dict[str, dict[str, list[str]]] | None` is structurally heavier than `mcp_overrides` and may benefit from a named `PerAgentACL(BaseModel)` submodel for cleaner Pydantic validation on read. Leg 1c design call.
**Suggestions** (non-blocking):
- Adaptation Criteria: add note that legs 1a/1b/1c may also land out-of-order (1a/1b/1c are independent of each other; only legs 2/3 consume all three).
- Verification §1 should specify the `session_metadata` audit key name explicitly (e.g. `session_metadata["audit"] = [{outcome, peer_id, ts}, ...]`). Leg-2 design call but worth flight-level pre-commitment.
**Questions for the designer** (carry to leg design):
- Does pairing-prefix validation live in `_inbound.dispatch_inbound` itself or in a separately importable helper? Affects leg-2 test fixture mechanism.
- F6's "first-attached or only-attached" temporary single-agent assumption — does it live in leg-2's dispatcher logic, or in a separate helper F7 replaces? Spec should name the F7 hand-off point unambiguously.
- Leg 4's reverse-lookup endpoint vs. client-side filter — leg-4 design picks; recon-leg-4 must check `/api/agents` payload shape.
**Impact**: No flight-spec rewrite required. All findings carried as leg-design inputs. Flight may transition to `ready`.

### Persistence shape: `config["pairing"]` + `config["allowlist"]`
**Context**: F6 needs a persistence slot for pairing code + account-scope allowlist + per-agent ACL. Two options on the table: ride on existing `config: dict[str, Any]` or add a v18 schema migration with structured columns.
**Decision**: Ride on `config`. No v18 migration.
**Impact**: Leg 1 ships Pydantic validators on the `config` dict structure rather than SQL columns. Operator UI is the authoritative inspector for state inspection. Future SQL-side queryability (e.g. "every allowlist that includes peer X") is harder than a relational shape; no F6 use case requires it.

### Pairing mechanism: peer-side `PAIR <code>` prefix
**Context**: Three options proposed (peer-prefix, operator-approval-queue, hybrid). Peer-prefix is openclaw's pattern.
**Decision**: Peer-side prefix.
**Impact**: Operator doesn't sit at console for each pairing; code is regenerable; leg 2 owns the strip-validate-persist flow.

### Resolver outcome: three outcomes (Permit / NeedsPairing / Deny)
**Context**: Boolean vs two-outcome vs three-outcome shape.
**Decision**: Three outcomes. Protocol signals shape; dispatcher validates pairing code.
**Impact**: `AllowlistResolver.resolve()` returns one of three; dispatcher's branch in leg 2 has three arms; future plugins (Slack, Discord) override `resolve()` without leaking validation into the Protocol.

### Edit surface: intra-Studio split
**Context**: Where does the operator edit each scope of state? "Admin" terminology was incorrect — both MCP Servers and Connectors live under Studio's sidebar post-F2 (per `studio.js:236,441`).
**Decision**: Account-scope state (pairing code + account-scope allowlist) on the Studio Connectors detail page; per-agent ACL on a new Studio Agent Editor Connectors tab. Plus a read-only summary of attached agents with ACL counts and deep-links on the Connectors detail page.
**Impact**: Legs 4 and 5 are sibling Studio surfaces with no inter-leg dependency; either could land first.

### Fold F5 live-broadcast gap into F6
**Context**: F5 debrief Action Item flagged this as "F6 or F10"; pre-step USER tagging is the recommended approach.
**Decision**: Fold into F6 as leg 6. Pre-step USER tagging at `_process_and_broadcast`.
**Impact**: F6 grows to 6 autonomous + 1 HAT = 7 legs (F5's exact shape). Mission Known Issue update lands as part of leg 6.

### HAT: required, not optional
**Context**: F5 debrief rec #4 — operator-visible flights end in required HAT.
**Decision**: Leg 7 is required HAT.
**Impact**: F6 is gated on operator availability for HAT close.

---

## Deviations

(None yet.)

---

## Anomalies

(None yet.)

---

## Session Notes

### 2026-05-18 — Flight planning
- Mission context loaded; F5 just merged (`c345883` on main).
- Recon walk confirmed all F1-cited F6 surfaces are absent (`AllowlistResolver`, pairing, per-agent ACLs); all consumed substrate is present (Studio MCPs tab, `connector_account_ids`, `config` slot, `session_metadata`).
- User confirmed scope, persistence, pairing flow, resolver outcomes, edit surface, fold-in, and HAT-required.
- Flight artifact drafted; design review (Phase 5b) is next.

### Flight Director Notes

- Per the agentic-workflow phase file, this flight will run under the per-leg design-review cadence with deferred batched code review and a single commit cycle after all autonomous legs land. F5's exact protocol; F5 caught 5+ bugs at design-review time via that cadence.
- HAT is REQUIRED for this flight. F5 debrief rec #4 codifies this for operator-visible flights; F6 inherits.
- Phase 5b architect review will spawn before transitioning to `ready`.

### 2026-05-18 — Flight launch + Leg 1a design

- Flight branch `flight/06-pairing-allowlists-and-per-agent-acls` created off `main` (clean tree apart from the F5-debrief-driven Known Issue edit to mission.md and the untracked flight directory; both are picked up by the eventual batched commit). Flight status set to `in-flight`.
- Leg 1a artifact drafted at `legs/01a-allowlist-resolver-hook-and-outcomes.md`. Scope: 3 outcome dataclasses + `ResolveOutcome` alias + `_default_permit` callable in `connectors/base.py`; revise 2 docstrings; reframe 4 prose sites in `agents.md` (including a one-sentence convention-block append at L96-100); append a `resolve` entry to `connectors/README.md` §4 "Optional hooks"; ship a new test file `tests/test_connectors_resolver.py`. `ConnectorPlugin` Protocol unchanged. `_stub.py` unchanged. README:363 and the `# F6:` source-code marker at `tools/connector_send.py:131` DEFERRED to leg 3.
- Cycle-1 design review (Developer agent): approve with changes. 2 medium issues (README:363 citation gap; `_default_permit` placement / forward-reference fragility) + 4 low (test file name, fixture imports, Permit zero-field, verification grep). All addressed in revisions.
- Cycle-2 design review (Developer agent): approve with changes. 2 medium issues (CommandHandler-grep invariant wrong — L339 carries TWO `CommandHandler` mentions and the reframe drops one of them; base.py off-by-one — `12` not `13`) + 4 low. All addressed: §3 docstring revision now explicitly preserves the F7 `CommandHandler` reference; §7 L339 reframe is surgical — drops only the `AllowlistResolver` mention and the bundled `Plugin + AllowlistResolver + CommandHandler` list, preserves the surrounding `CommandHandler` prose; Edge Cases now distinguishes grep-line-SET (invariant) from grep-hit-COUNT (drops by 1 on L339 by design); Files Affected reflects 6-test count and the convention-block append; two surviving test-file-name hedges scrubbed; verification grep wording clarified for the two leg-3-deferred sites.
- Two design-review cycles maxed out — implementation proceeds. Cycle-2 reviewer's "approve with changes" is closeable with the targeted spec edits above; no further design-review pass needed.
- Leg 1a status: `ready`.

### 2026-05-18 — Leg 1b design

- Leg 1b artifact drafted at `legs/01b-account-config-pairing-and-allowlist-schema.md`. Scope: `@field_validator("config", mode="after")` on `ConnectorAccount` validating the two reserved keys (`pairing`: `{code: str, issued_at: ISO-with-T}`; `allowlist`: `{peers: list[str], channels: list[str]}`). No schema migration, no change to repository or API. New `TestConnectorAccountConfigValidator` class appended to `tests/test_db_repositories.py` covering direct construction, repo round-trip, empty-allowlist verbatim preservation (both model + storage level), 7 malformed-pairing variants, 6 malformed-allowlist variants, and the cycle-1 H2 closure test (UPDATE config via raw SQL on a valid row → read raises).
- Cycle-1 H2 concern (read path validation) verified empirically by the reviewer to be closed: Pydantic v2 `@field_validator` fires on direct `BaseModel(**kwargs)` construction; existing `_validate_idle_timeout_seconds` exercises this path through `_row_to_model`. No change to `db/repositories.py` needed.
- Cycle-1 design review (Developer agent): approve with changes. 1 high (test file name `test_connector_accounts_api.py` → `test_db_api.py`); 3 medium (ISO date-only acceptance permissive — tightened to require `T` separator + new test; raw-SQL INSERT secrets-blob would mask validator path — rewritten to UPDATE config on a pre-existing valid row; non-dict config edge case clarification); 1 low (`_default_permit` aspirational AC dropped — that's a leg-2/leg-3 concern). All addressed in the spec.
- Suggestions applied: storage-level empty-allowlist assertion test (raw JSON read shows `[]` not null/absent); explicit non-dict-config Edge Case; API PUT shallow-merge semantics documented for leg-4 awareness.
- Leg 1b status: `ready`. One design-review cycle was sufficient — no cycle-2 needed (the cycle-1 fixes are mechanical and don't introduce new design surface).

### 2026-05-18 — Leg 1c design

- Leg 1c artifact drafted at `legs/01c-agent-config-connector-acls-and-v18.md`. Scope: `AgentConfig.connector_acls: dict[str, dict[str, list[str]]] | None = None` field + `@field_validator("connector_acls", mode="after")` enforcing the exact-keys `{"peers", "channels"}` inner shape; v18 migration `agents.connector_acls TEXT`; `SQLiteAgentStore.save` + `_row_to_config` round-trip — all atomically in one leg per F4 debrief rec #1. Ripple-site work renumbers F8 CHECK from v18 → v19 across the codebase (the F4 L5 sub-leg-A precedent: predictive docstrings that the next-renumbering-leg owns).
- Cycle-1 design review (Developer agent): **needs rework**. 5 high (field_validator import claim wrong — must be REQUIRED edit; schema.py:490 citation wrong — actual text is stale-pre-leg "flight 8 will land v14"; missed ripple sites at connectors/README.md:297,303, test_db_migration.py:1131, and the 4-line renumber chains at TestSchemaV14/V15) + 3 medium (validator contained dead code masked by Pydantic v2 native annotation enforcement — trimmed to the exact-keys check only; non-string-outer-key edge case wrong — Pydantic rejects, doesn't coerce; missing H2-closure analog test + empty-outer-dict round-trip test) + 2 low (line citations off ±3; markdown emphasis preservation). All addressed.
- Cycle-2 design review (Developer agent): **approve with changes**. 1 medium (stale "Verify field_validator is already imported" sentence at line 243 — leftover from cycle-1; deleted) + 2 low (verification grep `v1[5-9]` would miss `v14`-named stale sites → broadened to `v1[3-9]`; L1637 vs L1638 TestSchemaV16 reconciled).
- All cycle-2 findings closed via targeted spec edits. Two design-review cycles maxed out — implementation proceeds.
- Cycle-2 confirmed: validator trim is empirically correct (Pydantic v2 rejects non-string outer keys, non-dict outer values, non-list inner values, non-string inner entries via the annotation alone — `dict[str, dict[str, list[str]]] | None` does the heavy lifting). The trimmed validator handles only the exact-keys invariant Pydantic can't express.
- F8 CHECK renumber: v14 (stale-pre-leg in schema.py + README.md + test_db_migration.py:1131) → v15 (stale-pre-leg in README.md:303) → v18 (current 3 schema.py blocks + 4 test_db_migration.py docstrings + agents.md:302 + _connector_types.py:7-18) → all canonically v19. The leg principle: after this leg, every site that names F8 CHECK says v19; no site says v18 = F8 CHECK.
- Leg 1c status: `ready`.

### 2026-05-18 — Leg 2 design

- Leg 2 artifact drafted at `legs/02-inbound-gating-pairing-and-audit.md`. Scope: dispatcher resolver-consult + three-arm branch (Permit/NeedsPairing/Deny); pairing-prefix validator helper in new `connectors/_pairing.py`; allowlist mutation + persistence on pairing success; audit-log writes via new `ChatSessionRepository.append_to_session_metadata` narrow primitive; new `StubPluginWithResolver` test variant. Final placement: consult AFTER `resolve_session` and BEFORE per-session lock (audit always has a session_id target; `last_inbound_at` not bumped on Deny by design). Audit shape `{outcome, peer_id, ts, reason}` uniform across all outcomes.
- Open-question resolutions: pairing-prefix lives in new `connectors/_pairing.py` (pure, testable in isolation); test fixture is `StubPluginWithResolver` variant (option (a) per cycle-2 finding #1); audit key is `"audit"` (sibling to F7's future `"routing"` key); race-on-concurrent-pairing documented as F10 known limitation.
- Cycle-1 design review (Developer agent): approve with changes. 1 high (§3 contradictory narrative — rewrote linearly), 3 medium (AC consult-placement contradicted decision; audit shape uniformity for reason key; pairing-code-with-whitespace surface), 3 low (test count discrepancy; missing reason in Permit entry; pseudocode dead code). All addressed.
- Resolver-always-called and Deny-skips-last_inbound_at decisions documented explicitly in the dispatcher pseudocode and Implementation Guidance.
- Leg 2 status: `ready`. Cycle-2 not needed — cycle-1 fixes are mechanical and don't introduce new design surface.
