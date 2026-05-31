# Flight Log: Audit-log inspector + per-connector inference config + slash-command HAT

**Flight**: [Audit-log inspector + per-connector inference config + slash-command HAT](flight.md)

## Summary

Flight in planning. F13 covers three M11 operator surfaces (audit-log inspector for `session_metadata["routing"]`, per-connector inference LLM configuration UI, slash-command verification against real Discord) plus three F12 debrief carry-forward items (shared test-fixture translator module, two agents.md M11 conventions, per-agent `peers[*].dm_allowed` retirement). Six legs (L2 split into L2 + L3 per architect cycle-1 finding): L1 methodology-foldins-and-shared-test-helpers, L2 schema-v26-and-validator-tightening, L3 settings-removal-and-dispatcher-inference-source-refactor, L4 connector-editor-inference-provider-and-model-row, L5 audit-log-inspector-backend-and-chat-ui-panel, L6 slash-command-hat-against-real-discord. Per agentic-workflow protocol, code review + commit deferred to Phase 2d.

---

## Flight Director Notes

(empty — populated during execution)

---

## Reconnaissance Report

Per `/flight` Phase 1b. Source artifacts:
- F12 debrief at `flights/12-hierarchical-allowlist-and-snake-case-rename/flight-debrief.md` (carry-forward Action Items)
- M11 mission outline F13 entry (`mission.md:131`)
- M11 Known Issues — none filed against F13 directly; F12 closed both hierarchical-allowlist + snake_case-rename items

Three surfaces enumerated via `/Explore` agent recon at planning time:

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| Audit-log inspector for `session_metadata["routing"]` (M11 criterion #15) | **confirmed-live** | Dispatcher writes rich routing entries at `_inbound.py:549-806` (6 write sites); session-detail endpoint at `api.py:3188` returns full session but `_session_summary()` at `:3246` STRIPS `session_metadata` from response — no current UI exposure | F13 L4 core scope; extend `_session_summary()` + add Chat UI panel |
| Slash-command verification (M11 criterion #10) | **partial — verify-only per operator** | 6 commands registered + handlers wired (`_discord.py:121-128`, `_commands.py:116-204`); all currently channel-visible per `_discord.py:858-859` ("ephemeral-response customizations deferred to F10 hardening"); no autocomplete; F7 CommandHandler Protocol at `base.py` | F13 L5 verify-only HAT; ephemeral + autocomplete explicitly deferred to future flight per operator decision |
| Inference LLM UI (M11 criterion #12) | **confirmed-live (reshaped at planning)** | F7 added `Settings.inference_provider_config_id` at `config.py:31` but NO UI; Settings is env-var-only (no runtime persistence). **Operator reshaped at planning**: relocate from Settings to `connector.config` ("simply a property of the connector"). Settings fields removed; v26 backfills `None` | F13 L2 (substrate) + L3 (UI) |
| F12: extract `tests/_acl_shape_helpers.py` | **confirmed-live** | F12 debrief Recommendation #3 — translator helpers duplicated across `tests/test_connectors_acl.py`, `test_connectors_routing.py`, `test_connectors_commands.py`, `tests/browser/seeders.py` | F13 L1 fold-in |
| F12: codify 2 conventions in agents.md M11 | **confirmed-live** | F12 debrief Recommendation #5 — `column-aware-index-create-for-rewind-paths` + `test-translator-helpers-for-shape-evolution` | F13 L1 fold-in |
| F12: retire per-agent `peers[*].dm_allowed` footgun | **confirmed-live** | F12 debrief Action Item — Developer + Architect crews flagged independently. The field is stored on per-agent peers for "structural uniformity" but NOT consulted by ACL per L3 DM Composition Truth Table | F13 L2 fold-in (bundled with v26 row-rewrite) |
| F12: `_acl.py` axis-level extraction | **deferred — out of F13 scope** | F12 debrief Recommendation #2 — "Don't do this proactively unless a concrete bug surfaces"; file at 740 LOC with helper-level duplication. F13's only `_acl.py` touch is the small mechanical update for stripped per-agent peers shape | Stays as routine-maintenance candidate; re-evaluate at F14 planning |
| F12: aiosqlite event-loop-closed teardown warning | **deferred — out of F13 scope** | F12 debrief Action Item — F11 debrief's "apply L3 fixture pattern" recommendation was re-classified by F12 recon as not-applicable (test_db_migration.py fixture is already async; warnings come from aiosqlite library-internal worker-thread teardown). Real fix needs investigation | Stays as routine-maintenance candidate |
| F12: 2 pre-existing browser test failures | **deferred — out of F13 scope** | F12 debrief Action Item — `test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` + `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection` unaddressed since pre-F10 | Stays as routine-maintenance candidate or fold into next browser-touching flight |

**Classification summary**: 6 confirmed-live items drive F13 scope (5 legs); 3 items deferred to routine-maintenance.

**Recon adjustments to source-artifact framing**:
- M11 criterion #12 (mentions-aware response policy) was conceptually closed by F7 at the substrate layer but the *operator-configuration surface* was missing — F7 shipped `Settings.inference_provider_config_id` as env-var-only with no UI. F13 closes the operator surface and relocates the persistence to the connector per operator's planning-time clarification ("the LLM has to be set up first, and each connection may choose a different LLM, to me this is simply a property of the connector"). The criterion's mark transitions from `[ ]` to `[x]` only after both the connector storage AND the connector-editor UI land.
- M11 criterion #10 (slash commands) marked `[~]` at F13 land per operator's verify-only choice. Ephemeral + autocomplete deferred to a future flight; the criterion's "ephemeral where appropriate" sub-bullet stays open.
- F11 debrief's "rename `idx_pending_approvals_account_peer_status` index name" recommendation closed at F12 L3 (bundled into v24 migration); not F13 scope.

---

## Pulled-Forward F12 Debrief Methodology Lessons

Per F11 + F12 methodology lessons applied across F13:

1. **Grep-gate-scope-is-a-design-decision** (F11 lesson #1, F12 L1 application): F13 L2's verification gate `git grep -nE "settings\.inference_provider_config_id|settings\.inference_model" the_one/ tests/` enumerates allowed residue explicitly (deprecation-warning code reading via `os.environ.get`).
2. **Phase 5c architect cycle for grep-gate flights** (F11 lesson #2, F12 L1 + L4 application): F13 L1 + L2 specify a Phase 5c architect cycle that runs the literal grep against the codebase pre-implementation.
3. **Separate test-surface from production-surface recon** (F11 lesson #3, F12 L3 application): F13 L1 spec calls out a separate test-surface grep at design time to enumerate the translator-helper consumer sites.
4. **Two-symmetric-paths-in-acl convention** (F11 lesson #5, F12 L2 codification): F13 L2's ACL helper update for stripped per-agent peers shape verifies both `_admits_inbound_dm` and `_admits_inbound_guild` at recon (the convention applies to any `_acl.py`-touching leg).
5. **Operator-local-state preservation discipline** (`docker-compose.yml` stays unstaged): preserved as F13 implementation guidance across all 5 legs. Note: F13 L2's Settings removal makes the operator's `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` + `THE_ONE_INFERENCE_MODEL` env vars no-ops; the env vars stay in operator's docker-compose.yml unchanged (out of F13 commits) and become dead weight that the startup-warning surfaces.
6. **Mechanical-prereq-leg-before-semantic-changes** (F11 L1, F12 L1 + L2 pattern): F13 L1 (test-helpers extraction + agents.md conventions; structural no-op) lands before L2 (substrate semantic changes).
7. **Translator-helper-at-test-module-top → shared-module promotion** (F12 L3 pattern, F12 debrief Rec #3): F13 L1 promotes the F12-introduced pattern from per-file helpers to a shared module.

---

## Leg Progress

(empty — populated during execution)

---

## Decisions

(empty — populated during execution; planning-time decisions live in flight.md Design Decisions)

---

## Deviations

(empty — populated during execution)

---

## Anomalies

(empty — populated during execution)

---

## Session Notes

(empty — populated during execution)
