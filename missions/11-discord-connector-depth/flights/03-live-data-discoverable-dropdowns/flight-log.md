# Flight Log: Live-Data Discoverable Dropdowns

**Flight**: [Live-Data Discoverable Dropdowns](flight.md)

## Summary

Execution phase. Branch `flight/03-live-data-discoverable-dropdowns` cut from `flight/02-pool-keying-and-directive-surface` (F2 PR #70 still open; F3 stacks per the flight artifact's completion-checklist clause). Status promoted `ready → in-flight` at orchestrator start (2026-05-22).

---

## Reconnaissance Report

Walk of every M11 mission item + F2-debrief item touching F3 scope, classified against current code state (2026-05-22, post-F2 ship at commit `cdabcec`).

| # | Item | Classification | Evidence | Recommendation |
|---|---|---|---|---|
| R1 | Allowlist editor — searchable dropdowns replacing chip-lists | confirmed-live | `connector-account-editor.js:renderAllowlistSection` at line 1774; 4 axes (peers/channels/guilds/roles) all use `_buildAllowlistChipList` at line 1856 | F3 L6 core |
| R2 | Routing-rules editor — match-value dropdowns | confirmed-live | `connector-account-editor.js:renderRoutingRulesSection` at line 2041; match-value at line 2017 uses `chip-list-editor connector-routing-match-chiplist`; scope `<select>` separate (per F1 L6 vocab discipline) | F3 L6 core |
| R3 | Per-agent overlay editor — dropdowns inherit | confirmed-live | F6 L1c shipped `AgentConfig.connector_acls`; the per-agent ACL UI mirrors `renderAllowlistSection` shape | F3 L6 (single integration point with same dropdown component) |
| R4 | Substrate-level `enumerate_discoverable_entities` plugin hook | confirmed-live | `ConnectorPlugin` Protocol at `the_one/connectors/base.py:278+`; existing optional hooks via `getattr` sentinel: `display_channel`, `resolve`, `is_dm` | F3 L3 core; widen via `optional-plugin-hook-via-getattr-sentinel` (F1 L1 codified) |
| R5 | Discord SDK fetch capabilities | confirmed-live | `discord.Client.fetch_channel` at `_discord.py:498`; `client.users`/`client.guilds`/`client.get_all_channels()` from SDK | F3 L3 — Discord plugin reads from live `client` |
| R6 | Cache + refresh strategy | confirmed-live | No discoverable-entities cache today; pool's `_RegistryEntry` carries idle TTL only | F3 L4 — extend `_RegistryEntry` + sibling refresh sweep |
| R7 | Stale-entry indicator | confirmed-live | No stale-tracking today | F3 L4 (1-cycle retention) + L5 (CSS strikethrough) |
| R8 | `connector-form-registry` extension point at n=5 | confirmed-live | `connector-form-registry.js:_validateEntry:optionalFns` at line 98 has 4 entries; F2 debrief flagged n=5 as evaluation point | F3 L5 — add 5th hook; flat-array shape preserved per operator decision |
| R9 | M10 debrief "channel-ID-vs-name UX cue" action item | partially-satisfied | F1 L6 added vocabulary substitution at routing-scope dropdown ("user" not "peer" for Discord); match-value text input is still free-form | F3 L6 closes the remaining gap |
| R10 | F2 debrief: `primitive-rename-test-classification` convention | confirmed-live | Convention not in `agents.md` (grep returns zero hits) | F3 L1 codification |
| R11 | F2 debrief: `flight-spec-dom-order-audit` convention | confirmed-live | Convention not in `agents.md` (grep returns zero hits) | F3 L1 codification |
| R12 | F2 debrief: recurring `test_connector_test_connection_button` cluster (3 flights deep) | confirmed-live + HYPOTHESIS-REVISED | F2 debrief hypothesized "missing `details_wrap.hidden = false` on success branch"; actual code at `connector-account-editor.js:1625-1631` explicitly hides on `status === 'ok'`. The test at line 67 asserts visible. Test-vs-code disagreement, not a missing toggle. | F3 L2 — operator chose "update test to match code" direction |
| R13 | F2 debrief: connector-form-registry top-comment optional-hook table | confirmed-live | `connector-form-registry.js` top comment (lines 1-40) describes the 4-required + 4-optional entry shape but doesn't carry a consolidated reference table | F3 L6 bundle |
| R14 | F2 debrief: Python↔JS directive constant lift | out-of-scope | F2 debrief recommended F5 or post-M11 | Defer per F2 debrief recommendation |
| R15 | F2 debrief: PUT handler config-merge audit | out-of-scope | F2 debrief recommended before F5 | Defer |
| R16 | F2 debrief: M11 F8 HAT-script flight priority promotion | out-of-scope | Cross-flight scope; not F3 work | Defer |
| R17 | F2 debrief: mission-control skill codification (Architect-checklist) | EXCLUDED | Operator decision at F3 planning: "no mission-control changes." Apply methodology in spirit at every F3 leg-design review cycle. | Apply at all F3 reviews; defer mission-control SKILL.md update |

**Operator-confirmed live items folded into F3**: R1 (L6), R2 (L6), R3 (L6), R4 (L3), R5 (L3), R6 (L4), R7 (L4+L5), R8 (L5), R9 (L6), R10 (L1), R11 (L1), R12 (L2), R13 (L6 bundle). R14-R17 deferred per F2 debrief / operator decision.

**Phase 4 crew interview outcomes** (2026-05-22):
- Test-connection-button bug fix direction: "update test to match code" (clean green-LED success UX is the intended shape; matches M07 inspector convention cited in code comment).
- `optionalFns` array shape: stay flat (per F2 debrief operator choice; defer object-map restructure to n=6+).
- Discoverable-entities API: GET per-account (cached) + POST refresh; no WebSocket push.
- HAT shape: same Chrome-MCP-driven walk (committed repeatable HAT script remains M11 F8 scope).
- Cache strategy: periodic 5-min background refresh + manual button + stale-indicator + 1-cycle retention.
- Dropdown UI: combobox + grouped sections + typeahead + virtualization >100 + paged >1000.
- Routing-rules: dropdowns for match values only; scope literals stay generic.
- Bundle scope: test-connection-button triage as L2; F2-debrief conventions as L1 codification; registry top-comment consolidation in L6.

---

## Leg Progress

### L1 — codify-f2-debrief-conventions

**Status**: landed (developer implementation complete; awaiting flight-end batched code review)
**Designed**: 2026-05-22
**Implemented**: 2026-05-22

Design review:
- Cycle 1: approve with changes. Issues caught: stale line-count ("~520 lines" actual ~706); inaccurate convention count ("15 existing" actual 21); two redundant byte-identity ACs; citation label format under-specified (existing precedents use `Citations (n=N from ...)` and `Citation (n=1 from ..., codified by methodology-promotion ...)`  — leg now mandates the same shape); `Source:` line shape under-specified — leg now mandates the one-line section-pointer form per existing precedent.
- Cycle 2: approve with changes. One HIGH catch: the prescribed `Source:` lines called the F2 artifact "M11 F2 mission-debrief" (wrong artifact class — it is F2's flight-debrief). Fixed. Two MED catches: Inputs section still said "15 existing conventions" (genericized away from the count); Post-Completion Checklist still referenced the dropped collect-only smoke check (replaced with `git diff --stat` framing). All addressed.
- Cycle-2 catches reinforce that the F1+F2-debrief Architect-checklist methodology continues to produce HIGH-severity catches when applied at the leg-design layer — same posture this flight expects through L2-L7.

Implementation:
- Inserted two new convention entries in `the_one/agents.md` `### Project-wide` subsection, between `### \`registry-dispatch-create-mode-AC\`` and `### Mission-specific (M10)`, in the prescribed order (rename-classification first, dom-order-audit second).
- `### \`primitive-rename-test-classification\`` now lives at agents.md line 199; `### \`flight-spec-dom-order-audit\`` at line 212.
- Both entries follow the 4-block structure (definition / applicability / `Citation(s):` / `Source:`) matching the precedents at `optional-registry-entry-hook` and `registry-dispatch-create-mode-AC`. Citation labels match the exact inline-parenthetical shapes prescribed by the leg artifact.
- `git diff the_one/agents.md` confirmed pure insertion (1 hunk, +23 lines, no other modifications). `git diff --stat` confirmed no source files touched — only `agents.md` + F3 sibling artifacts (`flight.md`, `flight-log.md`, leg artifact).
- Grep verification: `grep -n "### \`primitive-rename-test-classification\`"` returns exactly one hit; same for `flight-spec-dom-order-audit`.
- L1 checkpoint checked off in flight.md (Checkpoints + Legs sections). Leg artifact status progressed `ready → in-flight → landed`. All 16 acceptance criteria in the leg artifact verified and checked off.
- Tests: not run (doc-only leg; explicitly out-of-scope per leg Verification Steps).

### L2 — triage-test-connection-button-cluster

**Status**: landed (developer implementation complete; awaiting flight-end batched code review)
**Designed**: 2026-05-22
**Implemented**: 2026-05-22

Implementation:
- Updated exactly THREE tests in `tests/browser/test_connector_test_connection_button.py` per the leg's Implementation Guidance; the 4 sibling tests are byte-identical to their pre-leg state (confirmed by `git diff` — no hunks land inside the sibling function bodies).
- `test_default_stub_probe_renders_success_with_no_details`: flipped `expect(details_wrap).to_be_visible()` → `expect(details_wrap).to_be_hidden()`; dropped the now-moot `expect(details).to_contain_text("no additional details")` assertion + its orphan `details = page.locator(...)` line; rewrote the docstring to describe the M07-inspector-convention shape (status + one-sentence message at-a-glance; details panel opens only on debug-needed states).
- `test_non_string_detail_renders_as_font_mono_json`: dropped the two `expect(details.locator("code.font-mono", has_text=…)).to_be_visible()` assertions + the orphan `details = page.locator(...)` line; added `details_wrap` locator + `expect(details_wrap).to_be_hidden()` AFTER the existing LED `data-state="ok"` synchronization assertion (lines 181-183 pre-edit); rewrote the docstring to describe the non-string-details-on-ok-status no-surface contract.
- `test_secret_shaped_detail_value_passes_through_unmasked`: dropped the `expect(details).to_contain_text(masked_value, timeout=8000)` assertion + its orphan `details = page.locator(...)` line; added `led = page.locator('[data-testid="connector-test-led"]')` + `expect(led).to_have_attribute("data-state", "ok", timeout=8000)` IMMEDIATELY after the click as the load-bearing click-handler synchronization point (without it the subsequent `to_be_hidden()` would trivially pass against the initial hidden state of `details_wrap` at `connector-account-editor.js:429`); added `details_wrap` locator + `expect(details_wrap).to_be_hidden(timeout=8000)` AFTER the LED assertion; rewrote the docstring to describe the structural no-leak property (the wrap never renders on the ok path, so the token never reaches the DOM).
- `python3 -m py_compile tests/browser/test_connector_test_connection_button.py` passed (syntactic validity confirmed).
- `docker exec the-one pytest tests/browser/test_connector_test_connection_button.py -x --timeout 60 -q -m browser` → **7/7 passed** in 10.42s. Note: pytest config `addopts = "-m 'not live and not browser and not pixel and not requires_bwrap'"` defaults to deselecting browser tests; the explicit `-m browser` selector was required to enable them (the leg's recipe `docker exec the-one pytest <file> -x --timeout 60 -q` deselected all 7 tests at first run; this is a leg-execution.md crew-prompt detail rather than a leg-spec defect — the test file IS a browser-marked file).
- `git diff tests/browser/test_connector_test_connection_button.py` confirmed diff hunks confined to the three named tests; sibling tests untouched. `git diff --stat` confirmed only the test file + `the_one/agents.md` (L1's landed work, still uncommitted per the F3 batched protocol) appear in the worktree alongside the F3 sibling artifacts.
- L2 checkpoint checked off in flight.md (Checkpoints + Legs sections). Leg artifact status progressed `ready → in-flight → landed`. All 11 acceptance criteria in the leg artifact verified and checked off.

Notes:
- No production code modified. The leg's "do not paper over with xfail/skip" constraint did not trigger — all 7 tests passed on first run after the test-side edits.
- The trivially-true `to_be_hidden()` risk flagged in the leg's Edge Cases is mitigated in every updated test by a preceding LED `data-state="ok"` synchronization assertion (tests 1 and 2 already had one; test 3 gained one as a load-bearing addition).

### L3 — discoverable-entities-plugin-hook

**Status**: landed (developer implementation complete; awaiting flight-end batched code review)
**Designed**: 2026-05-22
**Implemented**: 2026-05-22

Implementation:
- `the_one/connectors/base.py` grew two new frozen-slotted dataclasses (`DiscoverableEntity` + `DiscoverableEntities`) inserted between `CommandResponse` and the `@runtime_checkable` `CommandHandler` Protocol — preserving the "dataclass exports clustered before each Protocol" rhythm. Both carry module-docstring-grade field docstrings describing platform-neutral semantics (id-as-round-trip-key; `@username` / `#channel-name` Discord-native labels; cross-axis `group` clustering; JSON-friendly `metadata`).
- `the_one/connectors/base.py` module docstring extended with a new paragraph documenting `enumerate_discoverable_entities(client: ConnectorClient) -> DiscoverableEntities` as an OPTIONAL plugin hook discovered via `getattr(plugin, "enumerate_discoverable_entities", None)` per the L1-codified `optional-plugin-hook-via-getattr-sentinel` convention. Paragraph inserted BETWEEN the existing `resolve` paragraph (paragraph 2) and the `canonical-import` paragraph (paragraph 3) — NOT appended — preserving the docstring's existing structure.
- `the_one/connectors/_discord.py` import block extended with `DiscoverableEntities` + `DiscoverableEntity` from `the_one.connectors.base` (slotted into the existing alphabetized block) and `from datetime import UTC, datetime` (new line above `from typing`). `cast` was already imported.
- `_DiscordPlugin.enumerate_discoverable_entities` added between `handle_command` and `normalize_session_key` (the exact insertion point per the leg artifact). Uses `cast(DiscordClient, client)._client` for type-narrowing per the `disconnect` precedent at `_discord.py:1068` — no `assert isinstance` runtime gate. Inline comment cross-references both the disconnect cast and the `_user` capture at L350. Four axes populated: peers from `Client.users` (defensive dict-keyed-by-id dedup); channels from `Client.get_all_channels()` (all `GuildChannel` subclasses; threads out of scope per design decision); groups from `Client.guilds` (`member_count or 0` collapse); roles from each guild's `.roles` with `guild:{id}` group key. `fetched_at` produced by `datetime.now(UTC).isoformat()`.
- `the_one/connectors/_stub.py` NOT modified — the stub-doesn't path is the fallback contract pinned by the L3 test.
- `ConnectorPlugin` Protocol class body NOT widened — confirmed by grep: `grep -n "async def\|def " the_one/connectors/base.py` shows the Protocol still carries only its original 4 methods (`connect`, `disconnect`, `doctor`, `normalize_session_key`).
- `tests/test_connectors_discord.py` grew six new tests using Path B (extend `_StubDiscordClient` through `plugin.connect`):
  - `test_discord_plugin_implements_enumerate_discoverable_entities` — pins `hasattr` + non-None + callable for the hook.
  - `test_discord_plugin_enumerate_returns_populated_axes` — happy-path with 3 users (one bot, one missing `global_name`), 2 guilds with 3 channels + 3 roles total. Asserts axis populations, `@`/`#` label prefixes, `guild:{id}` grouping for channels and roles, and `+00:00`-offset ISO 8601 `fetched_at` regex match.
  - `test_stub_plugin_does_not_implement_enumerate_discoverable_entities` — imports `StubPlugin` from `the_one.connectors._stub`; asserts `getattr(plugin, "enumerate_discoverable_entities", None) is None`. Pins the fallback contract.
  - `test_discord_plugin_enumerate_tolerates_unknown_member_count` — `Guild.member_count is None` collapses to `metadata["member_count"] == 0`.
  - `test_discord_plugin_enumerate_user_label_falls_back_to_name_when_global_name_missing` — exercises both `global_name`-present and `global_name`-None branches.
  - `test_discord_plugin_enumerate_dedupes_users_defensively` — passes two `_StubDiscoverableUser` entries with the same id; asserts first-occurrence wins and the list length matches.
- Test scaffolding additions: four new helper stub classes (`_StubDiscoverableUser`, `_StubDiscoverableGuild`, `_StubDiscoverableRole`, `_StubDiscoverableChannel`) mirroring only the surface the hook reads (id/name/global_name/bot for users; id/name/position/mentionable for roles; id/name/type/guild back-link for channels; id/name/member_count/channels/roles for guilds). `_StubDiscordClient.__init__` now also initializes empty `users` and `guilds` lists (no observable effect for paths that don't touch them — all 66 pre-existing tests pass byte-identically). `_StubDiscordClient.get_all_channels()` generator added (mirrors the real SDK's `for g in self.guilds: yield from g.channels`).
- Imports added at top of test file: `DiscoverableEntities` + `DiscoverableEntity` from `the_one.connectors.base`; `StubPlugin` from `the_one.connectors._stub`.
- Tests run:
  - `docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30 -q` → **72 passed** in 0.63s (66 pre-existing + 6 new).
  - `docker exec the-one pytest tests/test_connectors_discord.py tests/test_connectors_pool.py tests/test_connectors_inbound.py tests/test_connectors_e2e_platform_send.py tests/test_connectors_acl.py -x --timeout 30 -q` → **213 passed** in 12.84s. Broader connector subsystem (including ACL hook-discovery paths) clean.
- `git diff --stat` confined to the three source files (`base.py`, `_discord.py`, `tests/test_connectors_discord.py`) plus the F3 sibling artifacts. `agents.md` + `tests/browser/test_connector_test_connection_button.py` also appear in the worktree but are L1 / L2 work (also uncommitted per the F3 batched protocol) — not L3 territory.
- L3 checkpoint checked off in flight.md (Checkpoints + Legs sections). Leg artifact status progressed `ready → in-flight → landed`. All acceptance criteria checked off.

Notes:
- No `xfail` / `skip` used; all six new tests pass on first run after implementation.
- The 5-vs-6 test count drift in early artifact wording (acceptance criteria list has 6 named tests; some Outputs prose mentions "five new tests") resolved to **six tests** per the explicit AC enumeration at lines 71-77 of the leg artifact.
- The `DiscoverableEntities.fetched_at` field carries a default of `""` so the dataclass is constructable in tests without a timestamp; production callsites (the Discord plugin here, and the L4 cache sweep when it lands) always populate it.

### L4 — discoverable-entities-cache-and-api

**Status**: landed (developer implementation complete; awaiting flight-end batched code review)
**Designed**: 2026-05-22
**Implemented**: 2026-05-22

Implementation:
- `the_one/connectors/_pool.py` extended with the full L4 substrate:
  - New module-level constant `_DISCOVERABLE_REFRESH_INTERVAL_SECONDS: float = 300.0` plus its read-at-call-time resolver `_resolve_discoverable_refresh_interval_seconds()` mirroring `_resolve_ttl_seconds`'s env-var + non-float-warn pattern (env var: `THE_ONE_CONNECTOR_DISCOVERABLE_REFRESH_INTERVAL_SECONDS`).
  - `_RegistryEntry` dataclass gained four new fields with backwards-compatible defaults — `account_type: str = ""` plus `discoverable_entities_cache`, `discoverable_entities_stale_carry`, `discoverable_entities_fetched_at_monotonic` all `None`-defaulted. The empty-string `account_type` default + sweep filter (skip entries where `account_type == ""`) keeps the pre-existing `tests/test_oauth_start_endpoint.py:105` and `tests/test_connectors_pool.py:479` direct-`_RegistryEntry` constructions invisible to the sweep.
  - New module-private frozen-slotted dataclass `_DiscoverableCacheSnapshot(cache, stale_carry, fetched_at_monotonic, account_type)` returned by the API-facing helper.
  - New module-level state `_discoverable_refresh_task: asyncio.Task[None] | None = None` alongside `_reaper_task`.
  - New async helpers (in source-order): `_ensure_discoverable_refresh_running_locked`, `_refresh_discoverable_entities_for_account`, `_compute_stale_carry` (pure helper for per-axis set-difference by `entity.id`), `_discoverable_refresh_once`, `_discoverable_refresh_loop`, `_get_account_cache_snapshot`. The refresh helper accepts `account_id: str` (not `(key, entry)`) per the cycle-1 spec, synthesizing the key internally so the API handler does not need the `_ACCOUNT_POOL_AGENT_SLOT` literal.
  - Race-safety contract codified per leg artifact: `prior_cache` is read INSIDE the re-acquired lock (not snapshotted at function entry), `_shutting_down` bail after re-acquire, identity-check `_pool[key].client is not client` for use-after-evict guard, NO touch on `entry.last_activity`.
  - `agent_acquire` cold-entry branch wires `account_type=account.type` into the `_RegistryEntry(...)` kwargs and calls `_ensure_discoverable_refresh_running_locked()` immediately after the existing `_ensure_reaper_running_locked()` call. Same lock block; warm-reuse path is unchanged.
  - `shutdown_drain` extended to cancel `_discoverable_refresh_task` alongside `_reaper_task` (cancel → suppress `CancelledError` → await → reset to `None`).
  - `_clear_for_test` extended to cancel the refresh task and reset to `None` after the reaper cancellation block but before the worker-cancel loop.
- `the_one/interfaces/web/api.py` extended:
  - Top-of-file pydantic import extended to `from pydantic import BaseModel, ConfigDict, Field, ValidationError`.
  - Two new inline Pydantic response models near the connector-account section: `_DiscoverableEntityOut` (id/label/group/metadata/stale; `extra="forbid"`; `metadata` defaults to `dict` via `Field(default_factory=dict)`) and `_DiscoverableEntitiesResponse` (entities dict-of-lists, fetched_at, stale_seconds; `extra="forbid"`).
  - Three small helpers — `_empty_discoverable_response`, `_project_discoverable_entity`, `_build_discoverable_response` — keep the endpoint bodies focused on contract dispatch.
  - `GET /api/connector-accounts/{account_id}/discoverable-entities`: 404 cold-account / 404 unknown account / 503 missing-hook / 200 populated / 200 fail-open-empty (first-call inline refresh edge case).
  - `POST /api/connector-accounts/{account_id}/discoverable-entities/refresh`: same 404 / 503 contracts; always invokes the refresh helper synchronously; 200 fail-open-empty on `False` return.
  - Both endpoints use function-local imports of `_get_account_cache_snapshot`, `_refresh_discoverable_entities_for_account`, `ConnectorRegistrationError`, and `_resolve_plugin` per the section's existing convention (mirror of `test_connector_connection`'s import block).
- `tests/test_connectors_pool.py` grew the 7 new tests per the leg artifact's Outputs section:
  - `test_refresh_loop_populates_cache_for_warm_account_entry` — monkeypatches the interval to 10ms; awaits up to 1s for the sweep tick to land.
  - `test_refresh_loop_does_not_touch_last_activity` — pins the critical "do NOT touch last_activity" invariant (the cycle-1 race-fix that the design caught).
  - `test_refresh_handles_evicted_entry_gracefully` — simulates concurrent eviction by mutating `entry.client` identity from inside the hook so the post-hook identity check fails.
  - `test_refresh_computes_stale_carry_from_diff` — cycle 0/1/2 stale-carry progression with {A,B,C} → {A,B} → {A,B}.
  - `test_refresh_skips_entries_without_hook` — `_HooklessPlugin` (omits `enumerate_discoverable_entities`); `_discoverable_refresh_once` returns 0; cache stays None.
  - `test_refresh_task_started_on_first_account_acquire` — pre-call `is None`; post-`account_acquire` non-None and not-done.
  - `test_shutdown_drain_cancels_refresh_task` — both `_reaper_task` and `_discoverable_refresh_task` end as `None` post-shutdown.
  - Added a `_DiscoverablePlugin` test fixture subclass and a `patch_discoverable_plugin` pytest fixture mirroring the existing `patch_plugin` pattern.
- `tests/test_api_connector_accounts.py` (NEW file) grew the 7 new tests:
  - `test_get_discoverable_entities_returns_404_for_unknown_account`
  - `test_get_discoverable_entities_returns_404_for_cold_account`
  - `test_get_discoverable_entities_returns_200_for_warm_account` (first-call inline-refresh path exercises end-to-end)
  - `test_get_discoverable_entities_returns_503_for_account_type_without_hook`
  - `test_post_refresh_discoverable_entities_returns_200_for_warm_account` (two-POST sequence with mutated snapshot + `asyncio.sleep(0.001)` to guarantee distinct ISO `fetched_at`)
  - `test_post_refresh_discoverable_entities_returns_404_for_cold_account`
  - `test_discoverable_entities_response_projects_stale_flag` (A,B fresh; C carried as `stale: true`)
  - Fixture pattern: `AsyncClient(ASGITransport(app=FastAPI))` + in-memory aiosqlite DB + test encryptor + triple-patch (`the_one.interfaces.web.api.get_connection`, `the_one.interfaces.web.api.get_encryptor`, `the_one.db.connection.get_connection`) so the pool's function-local `_load_account` resolves against the same DB the API handler sees. The third patch was necessary because `_load_account` imports `get_connection` function-locally from `the_one.db.connection` (function-local-import-to-break-load-cycle convention), so the API-side patch alone is insufficient.
  - Pool-warming uses `await account_acquire(account_id)` directly inside the test after registering a stub plugin via `register_for_test("stub", _DiscoverableStubPlugin)` — option (a) from the leg artifact's Pool-warming pattern note.
- Tests run:
  - `docker exec the-one pytest tests/test_connectors_pool.py -x --timeout 30 -q` → **36 passed** in 0.22s (29 pre-existing + 7 new).
  - `docker exec the-one pytest tests/test_api_connector_accounts.py -x --timeout 30 -q` → **7 passed** in 1.66s.
  - Broader suite: `docker exec the-one pytest tests/test_connectors_pool.py tests/test_connectors_inbound.py tests/test_connectors_discord.py tests/test_connectors_e2e_platform_send.py tests/test_lifespan.py -x --timeout 30 -q` → **168 passed** in 12.82s. All existing connector / lifespan tests unaffected.
  - Sibling regression: `docker exec the-one pytest tests/test_api_connector_account_config_validation.py tests/test_oauth_start_endpoint.py -x --timeout 30 -q` → **25 passed** in 5.31s.
- `git diff --stat` confined to `the_one/connectors/_pool.py`, `the_one/interfaces/web/api.py`, `tests/test_connectors_pool.py`, plus the new `tests/test_api_connector_accounts.py` — and the F3 mission artifact directory (flight.md / flight-log.md / leg artifact). Other modified files (`agents.md`, `_discord.py`, `base.py`, `tests/test_connectors_discord.py`, `tests/browser/...`) are L1 / L2 / L3 work in the same flight branch, awaiting the batched F3-end review + commit.
- L4 checkpoint checked off in flight.md (Checkpoints + Legs sections). Leg artifact status progressed `ready → in-flight → landed`. All acceptance criteria checked off.

Notes:
- The L4 leg artifact's mention that "the implementation does NOT change the public signatures of `account_acquire` or `agent_acquire`" is held — only internal lifecycle wiring (sibling task spawn) + new helper exports changed.
- No `xfail` / `skip` used; all 14 new tests passed on first integrated run after implementation. Two minor fixture-shaping iterations during development (the third `get_connection` patch and the use of `_DiscoverableStubPlugin.next_snapshot` as a class attribute to mutate between POSTs) were caught locally before the first full run.
- The cycle-1 HIGH "read prior_cache INSIDE the re-acquired lock" requirement is implemented as a direct `current.discoverable_entities_cache` read after the re-acquire, in the same `async with _lock:` block as the write. Test `test_refresh_computes_stale_carry_from_diff` verifies the semantics; the race-safety property itself is doc-only (codified in the helper docstring) — no test forces an interleaving of two refresh paths because the leg artifact accepts "both writes structurally-consistent" as the design tradeoff.

### L5 — discoverable-dropdown-component

**Status**: landed (developer implementation complete; awaiting flight-end batched code review)
**Designed**: 2026-05-22
**Implemented**: 2026-05-22

Implementation:
- NEW `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` (648 LOC; under the 700 ceiling per flight Adaptation Criteria). IIFE wrapper attaching `window.App.studio.discoverableDropdown(opts) → HTMLElement`. State + DOM shape per the leg artifact:
  - 5-param public opts `{axis, accountId, currentValues, onChange, vocab}`; axis-singular vocab map (`peers → peer`, `channels → channel`, `groups → group`, `roles → role`) drives placeholder text `Add ${vocab[axisSingular]}…`.
  - DOM: input-row (combobox `<input>` + Refresh `<button>`) + `<div role="listbox">` menu with grouped sections + `<div class="chip-list-editor discoverable-dropdown-chips" role="group">` chips strip + `<div aria-live="polite">` status line. All elements carry `data-testid` attributes (`discoverable-dropdown-{input,menu,refresh,chips,status,item,chip,chip-remove}-{axis}`).
  - WCAG combobox APG: `role="combobox"`, `aria-autocomplete="list"`, `aria-expanded`, `aria-haspopup="listbox"`, `aria-controls="dd-menu-{axis}-{accountId}"`, `aria-activedescendant` updated on ArrowUp/Down. Items have `role="option"`, stable `id="dd-item-{axis}-{itemId}"`, `aria-selected`.
  - Naive render up to 1000 entries (no scroll-based virtualization in L5 — leg's cycle-1 resolution); `hidden`-attribute toggle for typeahead filter; > 1000-entries gate flips the menu to a "Filter to narrow results" hint until the operator types ≥ 2 chars (then the matching subset is rendered).
  - Cross-axis group-label lookup: a group key in one axis (e.g., a guild id for channels) is resolved against `groups`/`peers`/`roles` for its label; falls back to the bare key string.
  - AbortController-based fetch race protection: `_doFetch` aborts any in-flight controller before firing the next GET / POST so a Refresh click during the initial GET cleanly supersedes it.
  - Unknown-id chip fallback: ids in `currentValues` that don't appear in `state.entities` for the axis render with the bare id as label + `data-unknown="true"` + `title="label unknown — try Refresh"`.
  - Stale-entry rendering: `data-stale="true"` on the item AND any matching chip; CSS applies the strikethrough + opacity-0.6.
  - Pre-probe 404 path: status line shows the response detail (or fallback "Run Test Connection first."); menu stays hidden; chips re-render.
  - 503 path: status line "This connector type does not expose discoverable entities."
  - GET / POST 5xx / network error: status line "Couldn't load entities; try Refresh."; Refresh button remains active.
- Modified `connector-form-registry.js:_validateEntry`: `optionalFns` extended to the 5-element `['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection', 'renderDiscoverableDropdown']`; new paragraph in the top-comment block documents the 5th hook's signature + L6-consumer flow (F2 debrief operator decision: keep the flat-array shape at n=5; no object-map restructure).
- Modified `connector-form-discord.js`: registered entry gains `renderDiscoverableDropdown(account, axis, currentValues, vocab, onChange)` — a mechanical positional-to-opts bridge to `App.studio.discoverableDropdown({axis, accountId: account.id, currentValues, onChange, vocab})`.
- Modified `the_one/interfaces/web/static/index.html`: `<script src="/static/js/areas/studio/discoverable-dropdown.js"></script>` inserted between `connector-vocabulary.js` and `connector-account-editor.js` (load order: dropdown defined before the editor mounts so L6 consumers can reference it).
- Modified `the_one/interfaces/web/static/css/studio.css`: new `/* Discoverable Dropdown (M11 F3 L5) */` block inside the `@layer areas` wrapper (~110 LOC of CSS). Classes reuse the canonical `--glass-border`, `--bezel-shadow-inset`, `--panel-radius-sm`, `--accent-translucent`, `--accent-glow` tokens from `admin.css:388-433`'s `.chip-list-editor` precedent; typography tokens are `--fg` / `--fg-secondary` / `--fg-muted` (project does not use `--text-primary`). Stale selector is correctly scoped: `.discoverable-dropdown-item[data-stale="true"], .discoverable-dropdown .chip[data-stale="true"]` — NOT the broad `[data-stale="true"]`. Chips strip carries both `chip-list-editor` and `discoverable-dropdown-chips` classes so the existing `.chip-list-editor` styling inherits automatically.
- Modified `the_one/agents.md`: `optional-registry-entry-hook` Citation block updated to `n=5 from M11 F1+F2+F3`; array literal in the registry-file citation updated; per-hook bullets gained F2 L4 (`renderDirectiveSection`) — which the prior n=3 wording had missed — and F3 L5 (`renderDiscoverableDropdown`).
- NEW `tests/browser/test_flow_studio_connector_discoverable_dropdown.py`: 7 tests per the leg artifact. Each test follows the leg's prescribed sequence (`page.route(...)` BEFORE `page.goto(...)`; mount via `page.evaluate()` injecting `App.studio.discoverableDropdown({...})` into a `<div id="dd-test-harness">`; assertions via Playwright `expect(...)` against `data-testid` locators):
  - `test_dropdown_populates_from_api_response` — 3 items rendered; 1 group section.
  - `test_dropdown_typeahead_filters_by_label_substring` — fill `"gen"` → only `#general` is visible (other two carry `hidden`).
  - `test_dropdown_select_item_fires_onChange_with_new_value` — focus input (to open the menu) then click `#general` → `window._lastOnChange === ['111']`.
  - `test_dropdown_chip_remove_fires_onChange_with_value_dropped` — mount with `currentValues=['111']`; click chip × → `window._lastOnChange === []` and the chip is gone.
  - `test_dropdown_stale_entry_renders_with_data_stale_attribute` — `#deprecated` item has `data-stale="true"`; the scoped selector matches exactly 1 element.
  - `test_dropdown_refresh_button_posts_refresh_endpoint` — uses `page.expect_request(...)` to wait for the POST to `.../discoverable-entities/refresh`.
  - `test_dropdown_renders_pre_probe_hint_when_api_404` — route fulfills 404 with `{"detail": hint}`; status line contains the hint; menu is hidden.
- Modified `tests/browser/test_connector_form_registry.py`: added `test_registry_optionalFns_includes_renderDiscoverableDropdown` — pins both the validator's accept-path (`function` body) and reject-path (string body → `TypeError` naming the offending hook), plus the Discord entry exposes `renderDiscoverableDropdown` as a function.
- Tests run:
  - `docker exec the-one pytest tests/browser/test_flow_studio_connector_discoverable_dropdown.py -x --timeout 60 -q -m browser` → **7 passed** in 8.40s.
  - `docker exec the-one pytest tests/browser/test_connector_form_registry.py -x --timeout 60 -q -m browser` → **6 passed** in 6.80s (5 pre-existing + 1 new).
  - Sibling regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py --timeout 60 -q -m browser` → **24 passed, 1 failed**. The single failure is `test_edit_session_continuation_round_trip` asserting `"Distinct from the pool idle timeout"` against the substring; the source hint (`connector-account-editor.js:368`) now reads `"Inbound continues the same chat session within this window."` — `git diff HEAD` is empty for both files, so this is a pre-existing source/test drift on the F3 branch base that is unrelated to L5. Flagged here so the F3-end review can decide whether to also fix it (or land a sibling-correction in L6a since it touches the same editor).
- `git diff --stat` confined to the L5 scope plus L1-L4 prior-flight files awaiting batched review.
- LOC check: `wc -l discoverable-dropdown.js` → 648 LOC (under the 700 ceiling).
- L5 checkpoint checked off in flight.md (Checkpoints + Legs sections). Leg artifact status progressed `ready → in-flight → landed`. All acceptance criteria checked off.

Notes:
- The leg artifact's acceptance criteria mention "AbortController-based race protection" — implemented by `_doFetch` which `_abortInflight()`s the prior controller before issuing the next request, and ignores `AbortError` in the `.catch` handler so the aborted in-flight fetch doesn't surface as an operator-visible error.
- Component refactor tightened from a 750-LOC first cut (over-budget) to 648 LOC in a single pass by consolidating the GET + POST fetch handlers into one `_doFetch(suffix, opts, label)` helper; this is the documented "tighten the implementation" path from flight Adaptation Criteria, not the "extract a helper module" path (which remains available if a future cycle wants scroll virtualization).
- The flight artifact specified `n=3 from M11 F1` in the agents.md citation block; the actual hook count at L5 land time is n=5 because F2 L4 silently added a 4th hook (`renderDirectiveSection`) without updating the citation. The L5 update folds in both the F2 L4 omission and the L5 new hook, restoring citation currency.

### L6a — discord-dropdown-allowlist

**Status**: landed (developer implementation complete; awaiting flight-end batched code review)
**Designed**: 2026-05-22
**Implemented**: 2026-05-22

Implementation:
- NEW helper `_mountAllowlistAxisEditor(slotEl, account, storageAxis, currentValues, vocab, checkDirty)` in `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`. Centralizes the per-axis mount dispatch: consults `App.studio.connectorFormRegistry.get(account.type)`; if the entry exposes `renderDiscoverableDropdown`, mounts the live-data dropdown (after mapping storage axis `'guilds'` → API axis `'groups'`); otherwise builds the chip-list via `_buildAllowlistChipList` and wires it through `helpers.wireChipListEditor` (preserves the stub-type regression contract).
- Dropdown path installs `slotEl._allowlistValues = function () { return state.values.slice(); }` — the canonical bridge for the collect-path (the dropdown's `.chip` shape is structurally distinct from the chip-list editor's, so the text-node walk would mis-read dropdown chips). The `onChange(newValues)` callback updates `state.values` then calls `checkDirty()` so the dirty-tracker observes dropdown selections. Chip-list fallback does NOT install the getter; the collect path falls back to the existing text-node walk.
- Refactored `wireAllowlistEvents` (~L2609-2642 → ~L2666-2698) to replace its inline `_mountChipList` closure with 4 calls to `_mountAllowlistAxisEditor` — one per storage axis (peers, channels, guilds, roles), passing the existing `_vocabForAccount(account)` result.
- Refactored `collectAllowlistFromContainer` (~L2657-2674 → ~L2700-2742) so `_readChiplist(slot)` first checks `typeof slot._allowlistValues === 'function'` and, if present, returns `slot._allowlistValues()` filtered to truthy stringified ids; otherwise falls through to the existing `.chip` text-node walk. Output shape `{peers, channels, guilds, roles}` unchanged.
- `getFormSnapshot`'s allowlist branch (L858) inherits the fix without modification because it delegates to `collectAllowlistFromContainer`. Symmetric collect-path + snapshot-path coverage with zero call-site duplication.
- Modified `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` top-comment: appended a new `## Optional Hooks (each function-if-present per _validateEntry)` section listing all 5 hooks with their signatures and one-line descriptions (the F2-debrief deferred bundle — the registry surface lacked a single reference table). No change to `_validateEntry`'s code path; `optionalFns` array stays at the 5-element shape L5 shipped.
- NEW `tests/browser/test_flow_studio_connector_allowlist_dropdown.py` (6 tests; sibling file rather than extending the existing editor test file since these tests share a Discord-only seed + stub-route harness):
  - `test_allowlist_axis_renders_dropdown_for_discord_account` — open a Discord account; all 4 axes carry the `discoverable-dropdown-{peers,channels,groups,roles}` testid (the `groups` API-axis-name pinned for the storage-`guilds` row). No chip-list testids present.
  - `test_allowlist_axis_renders_chiplist_for_stub_account` — open a stub account; all 4 axes carry the existing `connector-allowlist-{peers,channels,guilds,roles}-chiplist` testid. No `discoverable-dropdown-*` elements present. The regression contract.
  - `test_allowlist_dropdown_onChange_updates_account_config_allowlist` — focus the channels input, click `#general` item, save; reload via `GET /api/connector-accounts/{id}`; `config.allowlist.channels` includes `"111"`. Exercises the full `_allowlistValues` getter collect-path.
  - `test_allowlist_dropdown_chip_remove_updates_account_config_allowlist` — seed a Discord account with `channels: ["111"]`; click the chip ×; save; reload; `"111"` is gone from `config.allowlist.channels`.
  - `test_allowlist_storage_axis_guilds_maps_to_api_groups` — pin the storage↔API axis translation. The `[data-allowlist-chiplist-slot="guilds"]` slot hosts an element with `data-axis="groups"` AND `data-testid="discoverable-dropdown-groups"`. The other three slots host elements whose `data-axis` matches their storage axis (no translation).
  - `test_create_mode_discord_does_not_render_allowlist` — defensive coverage of the `registry-dispatch-create-mode-AC` "structurally guaranteed" exclusion. Goto `#studio/connectors/new`; pick Discord; assert no allowlist UI of either flavor renders AND no GET to `/api/connector-accounts/*/discoverable-entities` fired. Route handler captures all matching requests into a list; assertion is that the list stays empty.
  - The `_route_discoverable_ok` helper registers a single Playwright `page.route(...)` that fulfills both GET and POST against `**/api/connector-accounts/{id}/discoverable-entities*` so the dropdown's mount-time fetch (and operator-clicked Refresh) both hit the stubbed payload — no warm Discord-connector pool required.
- Tests run:
  - `docker exec the-one pytest tests/browser/test_flow_studio_connector_allowlist_dropdown.py -x --timeout 60 -q -m browser` → **6 passed** in 8.51s.
  - L5 regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_discoverable_dropdown.py tests/browser/test_connector_form_registry.py -x --timeout 60 -q -m browser` → **13 passed** in 15.68s.
  - Sibling regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py --timeout 60 -q -m browser` → **17 passed, 1 failed**. The single failure is the same pre-existing `test_edit_session_continuation_round_trip` carried forward from L5 — flagged for F3-end disposition; NOT touched by L6a.
  - Discord-form regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py tests/browser/test_flow_studio_connector_directive_section.py tests/browser/test_flow_studio_connector_invite_section.py --timeout 60 -q -m browser` → **35 passed**.
- `git diff --stat` for L6a-specific files: `connector-account-editor.js` +85/-20 LOC (helper + 2 refactors), `connector-form-registry.js` +24/-1 LOC (top-comment table). Plus the new test file `test_flow_studio_connector_allowlist_dropdown.py` (~320 LOC, 6 tests). F3-prior changes from L1-L5 carry forward in `git status` untouched.
- L6a checkpoint checked off in `flight.md` (Checkpoints + Legs sections). Leg artifact status progressed `ready → in-flight → landed`. All acceptance criteria checked off.

Notes:
- The leg artifact's L6a cycle-1 catches all landed cleanly: (1) storage-`guilds` → API-`groups` translation centralized inside `_mountAllowlistAxisEditor` (bidirectional via the registry-hook input + the storage-keyed slot lookup); (2) the `_allowlistValues` getter pattern bridges the collect-path without introducing a separate editor-internal state store (it wraps the dropdown's own state); (3) create-mode AC verified NOT applicable — `renderAllowlistSection` is structurally edit-mode-only at `connector-account-editor.js:405`, and the defensive create-mode test confirms NO allowlist UI + NO discoverable-entities fetch fires in create mode.
- `getFormSnapshot`'s allowlist branch did not need direct modification; routing the snapshot through `collectAllowlistFromContainer` (already in place from M10 F8 L8) means the `_allowlistValues` consult is now applied symmetrically for the dirty-tracker too.
- The chip-list testid format was confirmed at `connector-account-editor.js:1860` before writing the tests: `data-testid="connector-allowlist-{kind}-chiplist"` (NOT `connector-allowlist-chiplist-{kind}`). The L5 debrief carried that pin forward; the L6a tests use it directly.

### L6b — discord-dropdown-routing-and-overlay

**Status**: landed (developer implementation complete; awaiting flight-end batched code review)
**Designed**: 2026-05-22
**Implemented**: 2026-05-22

Implementation:
- NEW helper `_mountRoutingMatchEditor(slotEl, account, scope, currentValues, vocab, checkDirty)` in `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`. Mirrors L6a's `_mountAllowlistAxisEditor` shape for the routing-rules table's per-row match cell. Scope→API axis mapping is centralized in the helper (`channel`/`thread` → `channels`; `dm`/`peer` → `peers`; empty/unknown → `channels` default for fresh-add rows before the operator picks a scope). For Discord-type accounts the registry-entry `renderDiscoverableDropdown` hook mounts the live-data dropdown; stub-type / no-entry accounts fall back to the chip-list editor (rebuilt in-place from `state.values`).
- Dropdown path installs `slotEl._routingMatchValues = function () { return state.values.slice(); }` on the chip-list slot — the canonical bridge for the collect-path in `collectRoutingFromContainer`. Chip-list fallback explicitly deletes the getter (handles the scope-change re-mount from dropdown→chip-list, even though that path can't be reached today with only stub+Discord registered).
- Refactored `_wireRoutingMatchChiplist(rowEl)` (~L2178-2183 → ~L2218-2244) to delegate to the new helper. Reads the row's current scope from `rowEl.querySelector('[data-routing-scope]').value` and harvests initial committed match values from the pre-rendered chip-list text-nodes before mounting.
- Refactored the routing-rules scope-change listener (~L2324-2331 → ~L2354-2376) to re-mount the row's match cell with the new scope; previous match values are cleared (the simpler semantics per leg edge-case — ids belonged to the previous axis).
- Refactored `collectRoutingFromContainer` (~L2361-2376 → ~L2396-2422) to consult `matchEl._routingMatchValues` first; falls back to the text-node walk when absent. Output shape unchanged.
- Modified `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js`: applied the same dispatch in `_renderAccountTile`'s chip-mode-axis branch (~L310-325 → expanded). Investigation found a chip-list mount site at `body.appendChild(chiplist)` reached when `accountScope.{axis}` is empty (the per-agent overlay's free chip-list mode). For Discord-type accounts the registry hook mounts the dropdown in-place (wholesale replacement of the chip-list shell's children — the wrapper still carries the `data-connector-acl-{account,list,mode}` attributes the collect path looks up). Installs `wrapper._overlayChipValues = () => values.slice()` for the collect-path bridge. Stub-type accounts continue rendering the chip-list editor.
- Modified `the_one/interfaces/web/static/js/areas/studio.js` (`collectFormData`): the chips-mode branch (~L2102-2120) now consults `wrapper._overlayChipValues` first before falling back to the text-node walk. Symmetric to L6a's allowlist collect-path refactor.
- NEW `tests/browser/test_flow_studio_connector_routing_dropdown.py` (6 tests) per the leg artifact:
  - `test_routing_match_renders_dropdown_for_discord_channel_scope` — Discord account, seeded `scope='channel'` row, match cell hosts `data-axis="channels"` dropdown (and no chip-list input).
  - `test_routing_match_renders_dropdown_for_discord_peer_scope` — `scope='peer'`, dropdown `data-axis="peers"`.
  - `test_routing_match_thread_scope_uses_channels_axis` — `scope='thread'` maps to `channels` (the thread→channels mapping pin).
  - `test_routing_match_renders_chiplist_for_stub_account` — stub-type, chip-list editor remains; no dropdown rendered.
  - `test_routing_scope_change_re_mounts_dropdown_with_new_axis` — operator changes scope from `channel`→`peer`, dropdown re-mounts with `data-axis="peers"` AND previous chips cleared.
  - `test_routing_match_onChange_persists_via_save_round_trip` — Add row, pick scope=channel, click `#general` from the dropdown, pick agent, save; reload via `GET /api/connector-accounts/{id}` shows `config.routing.rules[0].match == ["111"]`. Pins the `_routingMatchValues` collect-path bridge end-to-end.
- NEW `tests/browser/test_flow_studio_per_agent_overlay_dropdown.py` (2 tests):
  - `test_per_agent_overlay_chip_mode_renders_dropdown_for_discord` — Discord account whose `account.config.allowlist` is empty on every axis (chip-mode contract) → both axis expandos host the `discoverable-dropdown-{peers,channels}` testid; no chip-list input remains.
  - `test_per_agent_overlay_checkbox_mode_unchanged` — Discord account with non-empty peers account-scope → the per-agent overlay's peers axis renders the checkbox-list editor (regression contract; L6b touches the chip-mode path only).
- Test ambiguity fix: the dropdown's testid `discoverable-dropdown-input-channels` resolves to 2 elements when both the allowlist and the routing-rules dropdowns render on the same tab (same axis). The `test_routing_match_onChange_persists_via_save_round_trip` test scopes locators through the row's match slot (`row.locator('[data-routing-match]')`) to disambiguate.
- Tests run:
  - L6b target: `docker exec the-one pytest tests/browser/test_flow_studio_connector_routing_dropdown.py -x --timeout 60 -q -m browser` → **6 passed** in 8.31s.
  - Per-agent overlay: `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_dropdown.py -x --timeout 60 -q -m browser` → **2 passed** in 3.04s.
  - L6a regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_allowlist_dropdown.py -x --timeout 60 -q -m browser` → **6 passed** in 8.00s.
  - L5 regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_discoverable_dropdown.py tests/browser/test_connector_form_registry.py -x --timeout 60 -q -m browser` → **13 passed** in 14.62s.
  - Editor regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py --timeout 60 -q -m browser` → **17 passed, 1 failed**. The single failure is the pre-existing `test_edit_session_continuation_round_trip` carried forward from L5/L6a; not touched by L6b. All routing-rules tests (`test_routing_rules_add_rule_with_chip_list`, `test_routing_rules_drag_reorder`, `test_routing_rules_default_agent_persists`, `test_routing_rules_baseline_not_dirty`) pass byte-identically for stub-type accounts — the regression contract.
- Per-agent overlay investigation outcome: the chip-mode mount site DOES exist at `connectors-tab.js:310-325` (the chip-mode branch of `_buildAxisRow`'s account-scope-empty path). L6b applied the dispatch refactor there + installed the `_overlayChipValues` collect-path bridge. The per-agent overlay tests file is included (not skipped).
- `git diff --stat` for L6b-specific files: `connector-account-editor.js` +94 LOC (helper + 3 refactors), `connectors-tab.js` +44 LOC (dropdown dispatch in chip-mode branch), `studio.js` +25 LOC (collect-path bridge). Plus two new test files. F3-prior changes from L1-L6a carry forward untouched.
- L6b checkpoint checked off in `flight.md` (Checkpoints + Legs sections). Leg artifact status progressed `ready → in-flight → landed`. All acceptance criteria checked off.

Notes:
- The leg artifact's mid-leg verification trigger ("if the per-agent overlay turns out checkbox-only, L6b ships routing-rules only") did NOT fire — the walk confirmed a chip-list mount site exists in chip-mode and the refactor + test file landed cleanly.
- Scope-change clears values per the simpler-semantics design decision; preservation logic remains an HAT-deferred consideration.
- Both new test files use the same `_route_discoverable_ok` Playwright route-stub pattern L6a established so warm Discord-connector pools / live Discord credentials are not required for the dropdown's mount-time fetch.

---

## Decisions

Runtime decisions not in original plan.

*(empty — to be populated during execution)*

---

## Deviations

Departures from planned approach.

*(empty)*

---

## Anomalies

Unexpected issues encountered.

*(empty)*

---

## Session Notes

### 2026-05-22 — Planning Session

- F2 just landed (commits `f6969b4` + `9b6908a` + `cdabcec`; PR #70 ready for review; flight artifact status `completed`).
- F3 scope sourced from M11 mission criteria #3 (allowlist dropdowns) + #4 (routing-rules dropdowns) + the M10 debrief "channel-ID-vs-name UX cue" follow-up + four F2-debrief items operator-confirmed for inclusion.
- Phase 3 + Phase 4 crew interviews resolved eight design decisions documented in `flight.md`.
- F2-debrief hypothesis on the recurring browser test failure was INVERTED at recon time: the code intentionally hides `details_wrap` on success-with-no-details (M07 inspector convention); the test was written expecting always-visible. F3 L2 updates the test (operator-confirmed direction).
### 2026-05-22 — Architect Design Review

- **Cycle 1**: approve with changes. Three HIGH issues caught at design time (methodology working as F1+F2 debriefs predicted):
  1. L2 test-cluster scope undercounted — the file has 7 tests, of which 3 (not 1) assert `details_wrap` visible on `status:'ok'` paths. F2 debrief's hypothesis was right about the cluster's existence but undercounted membership.
  2. Protocol-widening framing contradicted L1-codified `optional-plugin-hook-via-getattr-sentinel` convention — fix: document in module docstring + plugin impl, NOT on `ConnectorPlugin` Protocol class body.
  3. Refresh-sweep ↔ idle-reaper race: if refresh routes through `account_acquire`, `last_activity` resets on every 5-min sweep, making warm entries immortal (5min interval < 30min TTL). Fix: direct `_pool._entries` access under `_lock`, capture client, release, call hook outside.
  Plus 2 MED: L5 LOC estimate too low (revised 300-400 → 500-800 by comparison to `connector-form-discord.js` actual 722 LOC); L6 atomic-leg-pattern compliance borderline (4 surface refactors bundled).
- Applied fixes inline + operator-decided 4 questions: update all 3 ok-status tests; direct pool access; 404+hint on cold GET; `ConnectorClient` wrapper signature.
- **Cycle 2**: approve clean. Two LOW informational items fixed inline (stale "3 sibling" wording → "4 sibling" with specific test enumeration; L4 sweep-shape hedging → committed to sibling-task with write-back-under-lock for use-after-evict safety). No outstanding issues.
- F3 status: `ready`. Awaiting operator approval / `/agentic-workflow` execution.

### Flight Director Notes

#### 2026-05-22 — Orchestrator start

- Skill: `/agentic-workflow flight 03 for the-one mission 11`. Phase file `leg-execution.md` validated (Crew/Interaction Protocol/Prompts sections present; 5 prompts in fenced blocks; Accessibility Reviewer optional and not engaged unless a leg surfaces material UI changes — L5/L6a/L6b qualify).
- Branch `flight/03-live-data-discoverable-dropdowns` cut from `flight/02-pool-keying-and-directive-surface` (F2 PR #70 still open). F3 will land stacked on F2 per the completion-checklist clause; the F3 PR base must be the F2 branch (or rebased onto `main` once F2 merges).
- Total legs: 8 (L1, L2, L3, L4, L5, L6a, L6b, L7 HAT). L7 is interactive — driven step-by-step with the operator; not autonomous.
- Plan: drive 7 autonomous design+implement cycles (L1→L2→L3→L4→L5→L6a→L6b) with per-leg design review but NO per-leg code review or commit; then run L7 HAT interactively; then spawn a single Reviewer for all uncommitted changes, fix-loop if needed, commit once with all artifacts, open draft PR. Per the agentic-workflow protocol amended in this skill iteration.
- Accessibility reviewer: will be spawned in parallel with the main Reviewer at the final review gate for the L5/L6a/L6b UI surfaces.

#### 2026-05-22 — Batched code review (L1–L6b)

- Reviewer and Accessibility Reviewer were spawned in parallel against the full L1–L6b uncommitted worktree. Both signaled `[HANDOFF:confirmed]` on the batched review — no blocking findings, no fix-loop required.
- Non-blocking observations surfaced by the reviewer agents were captured in their respective handoff outputs and accepted without code changes; they are tracked as follow-up candidates for F3 debrief / future flights rather than F3 commit-blockers.
- All seven autonomous-leg artifacts progressed `landed → completed`. F3 flight-end batched commit issued covering L1–L6b across the connectors substrate (`base.py`, `_discord.py`, `_pool.py`), the REST API (`api.py`), the Studio UI (`discoverable-dropdown.js`, `connector-account-editor.js`, `connector-form-registry.js`, `connector-form-discord.js`, `connectors-tab.js`, `studio.js`, `index.html`, `studio.css`), methodology codification (`agents.md`), and the test surfaces (pool + API + 4 new browser flow files + discord/test-connection-button updates).
- L7 HAT remains. It will be driven interactively with the operator against the live gleepglorp environment per the leg artifact. No remote push until after L7 lands.
