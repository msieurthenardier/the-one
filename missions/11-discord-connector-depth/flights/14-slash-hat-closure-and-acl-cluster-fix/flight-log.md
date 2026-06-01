# Flight Log: Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt

**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](flight.md)

## Summary

Flight in planning. F14 closes M11 criterion #10 (slash commands validated against real Discord) by repairing the 4-bug ACL/slash-sync cluster F13 L6 surfaced (Bug C retired as false positive at recon time; Bugs B + D + E are real; Bug A is ops/docs) + shipping ephemeral-where-appropriate polish for the self-only commands + backfilling the L4-enhancement unit tests + resolving the 2 pre-existing browser failures (4-flight deferral closed) + refactoring `admits_inbound` to take an `AdmissionContext` dataclass (Option B) + authoring a re-runnable `discord-slash-end-to-end` behavior-test spec driven by a 2nd Discord bot via `discord.py`. 10 legs. Per agentic-workflow protocol, code review + commit deferred to Phase 2d.

---

## Flight Director Notes

(empty — populated during execution)

---

## Reconnaissance Report

Per `/flight` Phase 1b. Source artifacts:
- F13 debrief at `flights/13-audit-log-inspector-and-connector-inference-config/flight-debrief.md` (action items + 4-bug cluster + L4-enhancement test debt + 2 pre-existing browser failures)
- F13 L6 leg `flights/13-.../legs/06-slash-command-hat-against-real-discord.md` (cluster Known Issue with diagnostic evidence per bug)
- M11 mission outline F14 entry (`mission.md:131-134` pre-debrief shape; reshaped post-F13 to subsume slash-HAT closure)
- M11 Known Issues "F13 L6 HAT findings — ACL / slash-sync surface cluster" entry

Walked each item against current code (post-F13 commit `ed78d0e` on main):

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| Bug A — uvicorn `--reload` keeps stale Pydantic class objects | `confirmed-live` | Verified during F13 L6 diagnostic walk; uvicorn re-imports modules on file change but in-memory class objects (with frozen Pydantic validator schemas) from prior imports persist in the running worker | L6 leg: `CLAUDE.md` note + "restart container after Pydantic edits" discipline. NOT a code fix. |
| Bug B — `_sync_slash_commands` reads top-level `config.guilds`; UI writes `allowlist.guilds` | `confirmed-live` | `the_one/connectors/_discord.py:247` reads `account.config.get("guilds")`; validator at `db/models.py:443` validates `allowlist["guilds"]`; UI at `connector-editor.js:4332` reads `allowlist.guilds`; `_routing.py` consumes from `allowlist`. Top-level `config.guilds` is the lone hold-out. | L2 leg: single-site fix at `_discord.py:247`. Phase 5c grep gate enforces 0 orphan top-level readers post-L2. agents.md L4 narrative (line ~797) updated in lockstep. |
| Bug C — Discord plugin not passing `member_roles` to `admits_inbound` | `already-satisfied` (FALSE POSITIVE at F13 diagnosis) | `the_one/connectors/_discord.py:207-228` extracts `member_roles` from `interaction.user.roles` and embeds in `envelope.raw["member_roles"]`; `the_one/connectors/_routing.py:178-188` reads `envelope.raw.get("member_roles", [])` and forwards to `admits_inbound`. The F13 L6 diagnostic Python test bypassed the dispatcher's plumbing layer and called `admits_inbound` directly without `member_roles` — spurious denial in the test, not in production. | RETIRE from cluster. Document the false-positive lineage in this flight's recon report for traceability. |
| Bug D — `_commands.py:_permitted_agents` missing kwargs to `admits_inbound` | `confirmed-live` | `the_one/connectors/_commands.py:108` passes `(account, agent_acl, envelope.peer_id, envelope.channel_id)` — only 4 positional args; the `is_dm`/`guild_id`/`member_roles` kwargs use their defaults (False/None/None). The dispatcher's `_routing.py:180` call site DOES pass all 5; commands' secondary admission re-check doesn't. Latent since F7 (commit `dfff8ac`, 2026-05-19); unmasked by F12's structured-tuple allowlist requiring `guild_id` to match channel entries. Verified live via F13 L6 HAT. | L1 leg: ~5-line code change at `_commands.py:108` + 2-3 regression tests under `TestPermittedAgentsAgainstStructuredAllowlist` exercising `_handle_agents` against a structured-tuple allowlist. |
| Bug E — Channel allowlist accepts category ids | `confirmed-live` | F13 L6 diagnostic evidence: `enumerate_discoverable_entities` returns channels with `metadata.type` of `category`, `text`, `voice`, `text` (subchannel), etc. UI picker doesn't filter; operator picks a category id (e.g. `1447766673108107396` = `#Text Channels` category); ACL channel-match silently denies because messages come from child text-channels with their own ids. | L3 leg: filter `type=category` at the Discord plugin's `enumerate_discoverable_entities` site (substrate-side; cleanest separation per operator's selected Option). +1 unit test + 1 browser picker-filter test. |
| L4-enhancement unit-test backfill | `confirmed-live` | `grep -n "populateInferenceModelDropdown\|wireInferenceModelRepopulate" tests/browser/test_flow_studio_connector_inference_provider_row.py` returns 0 hits. The F13 L4-enhancement (model dropdown + race-guard + `(custom)` fallback) shipped with zero unit-test coverage; the behavior test caught the recapture-regression that unit tests missed | L4 leg: 3-5 browser tests covering Ollama + provider-switch + custom-fallback + no-provider placeholder + GUI-clear-saves-null. |
| 2 pre-existing browser failures | `confirmed-live` | `tests/browser/test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` (test name says "three" but asserts 4 tabs — likely name-vs-assert drift) and `tests/browser/test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection` (state preservation) exist at the cited locations. Both have persisted across F10 → F13 unaddressed (4-flight deferral). | L5 leg: investigate-at-implementation with flexible fix-or-update-assertions disposition. Divert clause if either surfaces >3-day work. |

**Classification summary**: 6 confirmed-live items drive F14 scope (10 legs total); 1 item (Bug C) retired as false positive.

**Recon adjustments to F13 debrief framing**:
- F13 debrief Recommendation #1 enumerated "4 substrate-touching bugs"; F14 recon retired Bug C as a false positive (Discord plugin + dispatcher do plumb `member_roles` correctly — the F13 L6 isolated Python test omitted it). Cluster narrows from 4 to 3 real bugs.
- The slash-command HAT closure scope EXPANDS at F14 vs F13's verify-only stance: F14 L7 adds ephemeral-where-appropriate polish for the 3 self-only commands (`/whoami`, `/agents`, `/help`) per operator's planning decision, closing M11 criterion #10's "ephemeral where appropriate" sub-bullet that F13 L6 deferred. Autocomplete polish stays deferred to a later flight.
- The L8 `admits_inbound` refactor uses Option B (`AdmissionContext` dataclass) per operator's selection after Phase 4 context. Option C (no-defaults) would prevent Bug D's exact failure mode but doesn't structurally prevent the broader signature-widening hazard; Option A (full envelope) couples ACL to envelope shape.
- The L9 behavior-test uses `discord.py`-as-second-bot driver (NOT Chrome MCP) per the M11 mission outline's explicit allowance ("Chrome MCP or `discord.py`-as-second-bot driver, resolved at flight planning"). Slash invocations against Discord's REST API are programmatic without browser automation, sidestepping web-client bot-detection.

---

## Pulled-Forward F13 Debrief Methodology Lessons

Per F13 debrief recommendations + F11/F12 carry-forwards still relevant:

1. **Grep-gate-scope-is-a-design-decision** (F11 lesson #1, F12 + F13 application): F14 L2 + L8 verification gates enumerate allowed residue explicitly.
2. **Phase 5c architect cycle for grep-gate flights** (F11 lesson #2): F14 L2 + L8 specify a Phase 5c architect cycle that runs the literal grep against the codebase pre-implementation.
3. **Mechanical-prereq-leg-before-semantic-changes** (F11 L1, F12 L1, F13 L1 pattern): F14 doesn't have a pure mechanical-prereq leg, but L1 (Bug D fix) lands BEFORE L8 (AdmissionContext refactor) so the refactor lands against a corrected call-site rather than threading two changes through `_commands.py:108` in opposite directions.
4. **Operator-local-state preservation discipline** (`docker-compose.yml` stays unstaged): preserved as F14 implementation guidance across all 10 legs.
5. **Consumer-callsite-audit-on-public-api-signature-widening** (F13 debrief codification): L8's AdmissionContext refactor is the structural implementation of the convention's process recommendation — instead of relying on architect-cycle grep discipline, the type system enforces it.
6. **Diagnostic-surface-co-ships-with-decision-path** (F13 debrief codification): F14 doesn't introduce new dispatcher paths but L7's ephemeral-polish surfaces extend an existing observable (the slash command response shape); no new audit-log surface needed.
7. **Detail-endpoint-attaches-rich-payload** (F13 debrief codification): F14 doesn't add new REST surfaces.
8. **In-memory-snapshot-from-db-restore** (F13 debrief codification): F14 doesn't add new in-memory snapshot fields.
9. **Provider-aware-model-dropdown-with-custom-fallback** (F13 debrief codification): L4 backfills test coverage for the F13 L4-enhancement that established this pattern.
10. **Two-symmetric-paths-in-acl** (F11 lesson #5, F12 L2 codification): F14 L8's AdmissionContext refactor touches `admits_inbound`; recon verified `admits_outbound` doesn't have the kwargs-omitted hazard (no F12-shape requirement), so the symmetric path is satisfied trivially. L8 still verifies both at recon.

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
