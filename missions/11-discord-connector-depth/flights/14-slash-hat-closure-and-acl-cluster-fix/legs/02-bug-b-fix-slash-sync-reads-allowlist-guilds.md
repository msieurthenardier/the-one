# Leg: bug-b-fix-slash-sync-reads-allowlist-guilds

**Status**: completed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

> **Scope pivot (operator-directed, F14 execution).** The flight's original Bug B Design Decision ("switch `_sync_slash_commands` from top-level `config.guilds` to `allowlist.guilds`; ~1-line change; 2798 unchanged") rested on a **false premise** surfaced at L2 design review and FD-verified: top-level `config.guilds` is NOT an orphan — it is the live "Scope to servers" Runtime Config field (`connector-form-discord.js:417`, validated at `api.py:1089`), *deliberately disambiguated* from the allowlist "Servers" axis (`allowlist.guilds`, the inbound-admission ACL). Slash-sync reading `config.guilds` was correct; the F13 L6 symptom was the operator leaving "Scope to servers" blank (its tooltip says "leave blank = all servers" but `_sync_slash_commands` skips on blank). Escalated to operator; operator chose **"Unify onto `allowlist.guilds`"**: retire the separate "Scope to servers" concept and make the allowlist Servers axis the single source of truth for both admission AND slash-command registration. This leg is re-scoped accordingly — it is no longer a mechanical 4-edit leg. Original flight DD framing preserved in flight.md as commentary; the pivot is recorded in the flight-log Flight Director Notes.

## Objective

Unify guild scoping onto `config.allowlist.guilds` as the single source of truth: a v27 data migration folds existing top-level `config.guilds` into `allowlist.guilds`; `_sync_slash_commands` reads `allowlist.guilds`; the standalone "Scope to servers" form field and its `api.py` validator are retired; existing tests migrate to the unified shape. After this leg, the allowlist editor's "Servers" axis governs both which guilds may send inbound (ACL admission) and which guilds get slash commands registered.

## Context

- **Two distinct "guilds" concepts in `connector-form-discord.js` — only ONE is retired:**
  - `intents.guilds` — the **"Server info" gateway intent** checkbox (`:99` `{key:'guilds', label:'Server info'}`, read at `:401`/`:462`). This is a Discord gateway intent, NOT a scoping list. **DO NOT TOUCH IT.**
  - `config.guilds` — the **"Scope to servers" text field** (`:151` read, `:200-220` render, `:412-417` write-back, `:710` `reservedConfigKeys`). **This is what gets retired.**
- **Unification target already has a UI surface**: the connector allowlist editor renders a "Servers" section (`connector-editor.js:2294-2314`, F12 L5 hierarchical Server-as-parent) bound to `account.config.allowlist.guilds`. So retiring "Scope to servers" does not strand the operator — they set guilds via the allowlist Servers axis.
- **`allowlist.guilds` validator already exists** at `db/models.py:443+` (M10 F8 L8, optional list[str]). No new validator needed; the retired `api.py:1088-1116` block is the redundant one.
- **Storage**: connector `config` is a JSON blob in `connectors.config` (`ConnectorRepository`, `repositories.py:563/586/612`). The migration row-rewrites that JSON. Latest schema is **v26**; this leg adds **v27**.
- **Blank-handling decision (explicit, reversible)**: this leg preserves the existing skip-on-blank behavior — an empty `allowlist.guilds` → `_sync_slash_commands` logs INFO and registers nowhere (global registration stays F10-deferred). The operator's "Honor blank = all guilds" option was offered separately and NOT chosen; unification was. The operator's connector always scopes to specific guilds, so blank-skip is not a live footgun for them. If a future flight wants "blank = register to all connected guilds," it's a localized change at `_sync_slash_commands` (enumerate `client.guilds` post-READY). Documented here so the asymmetry (ACL empty-axis = admit-all; slash-sync empty = sync-none) is intentional, not accidental.
- **Non-empty coupling consequence (operator FYI — design-review cycle 2)**: under unification, a **non-empty** `allowlist.guilds` now drives THREE behaviors at once: (a) restricts inbound guild-message admission, (b) participates in the DM-with-guild-restriction posture (`_acl.py:633`), and (c) scopes slash-command registration. Pre-pivot, top-level `config.guilds` could scope slash-sync to specific guilds while `allowlist.guilds` stayed empty (admit all guilds + DMs). Post-pivot those are fused — you cannot target slash commands at a specific guild without also restricting admission to it. This is the inherent meaning of "single source of truth," and the operator's connector is already guild-scoped (channels-restricted account on the test guild, F10/F12), so it costs them nothing in their live config. The fused semantic is documented in the agents.md ACL section by this leg, surfaced to the operator at session level, and noted for the flight debrief. If DM-admission independence is needed, the F12 `dm_admission`/`dm_allowed` axis already decouples DM admission from guild restriction — that path is unchanged.

## Inputs

- `the_one/connectors/_discord.py` — `_sync_slash_commands` (`:236-254`); connect-path doc-comment (`:995-1006`).
- `the_one/db/schema.py` — migration ladder; latest INSERT is v26 at `:1718`. v24 (`:1417`) is the row-rewrite precedent to mirror.
- `the_one/db/repositories.py` — `ConnectorRepository` config JSON round-trip (`:563/586/612`).
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — "Scope to servers" field (`:151/:200-220/:412-417/:710`); `intents.guilds` checkbox (`:99/:401/:462`, KEEP).
- `the_one/interfaces/web/api.py:1088-1116` — top-level `config.guilds` validator (retire).
- `the_one/connectors/_acl.py` — consumes `allowlist.guilds` for admission (unchanged; confirms the unified key's existing meaning).
- `the_one/agents.md:797` — L9 slash-registration narrative.
- `tests/test_connectors_discord.py:2838/2909/2951` — tests constructing top-level `config={"guilds": [...]}` (migrate).

## Outputs

- Schema **v27** migration: every connector row's `config.guilds` unioned into `config.allowlist.guilds`, then top-level `config.guilds` removed. Idempotent + partial-apply safe.
- `_sync_slash_commands` reads `account.config.get("allowlist", {}).get("guilds") or []`.
- "Scope to servers" form field removed from `connector-form-discord.js` (intents.guilds checkbox untouched).
- `api.py` top-level `config.guilds` validator removed.
- Existing slash-sync tests migrated to the `allowlist.guilds` shape; a v27 migration test added.
- agents.md + `_discord.py` doc references describe the unified read path.

## Acceptance Criteria

- [ ] **`CURRENT_VERSION` bumped 26 → 27** at `the_one/db/schema.py:15` (cycle-2 HIGH catch — without this the `version < 27` block never runs).
- [ ] A v27 migration in `the_one/db/schema.py` rewrites each connector row: `allowlist.guilds := dedup(allowlist.guilds ∪ config.guilds)`, then deletes top-level `config.guilds`. Migration is idempotent (re-run is a no-op once top-level `guilds` is gone) and follows the established INSERT-OR-IGNORE-schema_version-LAST partial-apply pattern. Use a `.pop("guilds", None)` idiom (NOT `if "guilds" in cfg:`) so the grep gate reaches a clean 0.
- [ ] `tests/test_db_migration.py:261-264`'s hardcoded `assert CURRENT_VERSION == 26` updated to `27` (with refreshed "M11 F14 L02" message). A v27 migration test added mirroring the v24/v25/v26 style (bare `await conn.close()` teardown — do NOT widen the latent aiosqlite teardown pattern, M11 Known Issue) + a fresh-db final-shape assertion (`max(versions) == CURRENT_VERSION`) and a `Connector.model_validate` round-trip proving no top-level `guilds` survives the fold.
- [ ] `_sync_slash_commands` reads `account.config.get("allowlist", {}).get("guilds") or []`; doc-comment (`:1000`) and docstring (`:237`) describe the unified path.
- [ ] The "Scope to servers" text field (`data-field="guilds-list"` / `data-testid="discord-guilds-list"`) is removed from `connector-form-discord.js` at ALL sites: render block (`:200-220`), the `:151` read, the `:412-417` write-back, the **`snapshot()` read at `:464`** (`guildsList: _readInputValue(...)`), the **dirty-tracking listener at `:580`** (`_wireListener(... '[data-field="guilds-list"]' ...)`), and the `'guilds'` entry in `reservedConfigKeys` (`:710`). Delete `_splitGuildsList` (`:381`) — its only caller is the retired write-back (confirmed single caller). **The `intents.guilds` "Server info" checkbox (`:99`/`:401`/`:462`, `data-field="intent-guilds"`) is untouched.**
- [ ] The top-level `config.guilds` validator block at `api.py:1088-1116` is removed (the `allowlist.guilds` validator at `db/models.py:443` remains the guild-list guard).
- [ ] `tests/test_connectors_discord.py:2838/2909/2951` migrated to construct `config={"allowlist": {"guilds": [...]}}`; assert `tree.sync` fires for those ids. **`:2951` (`config={"guilds": [987654321]}`, raw int) must use STRING ids `["987654321"]` and be renamed** — the `allowlist.guilds` model validator (`db/models.py:443`) enforces `list[str]` at `Connector(...)` construction, so int ids would raise `ValueError`. Int-id support is intentionally dropped under unification (matches the `list[str]` convention at `agent/config.py:364` + the doctor path). Use string ids matching the doctor tests' `["G1","G2"]` shape.
- [ ] **Browser tests in `tests/browser/test_flow_studio_connector_discord_form.py`** updated in lockstep (cycle-2 HIGH catch — these definitely break, not hypothetical):
  - `test_guilds_add_saves` (`:225-241`) fills `discord-guilds-list` + asserts `after["config"]["guilds"]` — remove it, or rewrite against the allowlist "Servers" axis.
  - `test_additional_config_hides_reserved_keys` (`:266-309`) seeds top-level `config.guilds=["111","222"]` at `:283` and asserts `"guilds" not in keys` at `:308` — drop the `:283` fixture line and the `:308` assertion (after `'guilds'` leaves `reservedConfigKeys`, a seeded top-level `guilds` would legitimately surface in the kv-table; the test's premise no longer holds).
- [ ] The agents.md slash-sync narrative — the sentence containing `for each g in account.config.get("guilds", [])` in the "Slash commands via `CommandHandler` (M10 F8 L9)" section — reflects the unified `allowlist.guilds` read path. Locate by that sentence, not by line number (it is NOT the L8 4-axis ACL section). Additionally add a one-line note in the ACL/guilds-axis section that `allowlist.guilds` now also scopes slash-command registration (the non-empty coupling).
- [ ] **Grep gate (Phase 5c)**: `git grep -nE 'config\.get\("guilds"\)|config\["guilds"\]|"guilds"\s*in\s*cfg|config\.guilds\b' the_one/` returns 0 hits in source referencing the *top-level* `config.guilds` (allowlist.guilds reads are fine; with the `.pop()` migration idiom there is no residue to flag).
- [ ] Backend suite green / 0 errors. Net count will shift (3 tests migrated in-place + new v27 migration test(s); the CURRENT_VERSION-assert test edited in place); record the actual final count in the flight-log L2 entry rather than asserting a fixed number (the flight's "2798 unchanged" no longer applies post-pivot).
- [ ] Browser suite green (the 2 named tests above resolved; no other test still expects the "Scope to servers" field).

## Verification Steps

- `docker exec the-one pytest tests/test_connectors_discord.py tests/test_db_migration.py -x --timeout 30 -q` — slash-sync + migration tests pass.
- `docker exec the-one pytest -x --timeout 30 -q` — full backend suite green / 0 errors (record count).
- Browser: run the connector-form / connector-editor flow tests; confirm none still expect the "Scope to servers" field.
- Grep gate (above) → 0 top-level `config.guilds` source references (migration body excepted).
- Manual: open the connector editor → confirm guilds are set via the allowlist "Servers" axis and there's no orphaned "Scope to servers" input.

## Implementation Guidance

1. **Bump `CURRENT_VERSION`** at `the_one/db/schema.py:15` from `26` to `27` FIRST (the migration loop only applies blocks up to `CURRENT_VERSION`). Then update `tests/test_db_migration.py:261-264`'s `assert CURRENT_VERSION == 26` → `27` + refresh its message to reference "M11 F14 L02".

2. **Add the v27 data migration** (`the_one/db/schema.py`, mirror the v24 row-rewrite at `:1417`).
   - Iterate connector rows; for each, `cfg = json.loads(config)`, `popped = cfg.pop("guilds", None)` (use `.pop`, not `if "guilds" in cfg:`, so the grep gate is clean). If `popped` is non-empty, `allowlist = cfg.setdefault("allowlist", {})`; `allowlist["guilds"] = ` order-preserving dedup-union of `allowlist.get("guilds", [])` + `popped`. An empty/`None` top-level `guilds` is simply dropped without touching `allowlist`. Write `json.dumps(cfg)` back (skip the UPDATE when nothing changed).
   - `INSERT OR IGNORE INTO schema_version (version) VALUES (27)` LAST. Idempotent: once top-level `guilds` is gone, the pop yields `None` → row unchanged.
   - Add the v27 test in `tests/test_db_migration.py` in the existing v24/v25/v26 style (bare `await conn.close()` teardown — do NOT widen the latent aiosqlite pattern). Cover: union when both keys present; idempotent re-run; empty-top-level-guilds drop; fresh-db `max(versions) == CURRENT_VERSION`; a `Connector.model_validate` round-trip showing no top-level `guilds` survives.

3. **Point `_sync_slash_commands` at the unified key** (`_discord.py:247`): `account.config.get("allowlist", {}).get("guilds") or []`. Update the `:237` docstring and `:1000` doc-comment to say `account.config["allowlist"]["guilds"]`. Keep the skip-on-blank INFO log behavior (see blank-handling decision in Context).

4. **Retire the "Scope to servers" form field** (`connector-form-discord.js`) at ALL sites:
   - Render block (`:200-220`), `guildsCfg` read (`:151`), `guildsValue`/`guildsList` write-back (`:206`, `:412-417`), **`snapshot()` read (`:464`, `guildsList: _readInputValue(...)`)**, **dirty-tracking listener (`:580`, `'[data-field="guilds-list"]'`)**, and the `'guilds'` element of `reservedConfigKeys` (`:710`).
   - Delete `_splitGuildsList` (`:381`) — confirmed single caller is the retired write-back.
   - **Leave the `intents.guilds` "Server info" checkbox fully intact** (`:99`, `:401`, `:462`, wiring) — gateway intent, `data-field="intent-guilds"`, unrelated to scoping. After the edit, verify `data-testid="discord-guilds-list"` is gone AND `data-field="intent-guilds"` remains.

4. **Remove the redundant `api.py` validator** (`:1088-1116`, the `if "guilds" in cfg:` block). The unified guild list is validated by `db/models.py:443`'s `allowlist.guilds` guard. Verify no other api.py path depends on rejecting a top-level `config.guilds` (after the migration + form retirement, nothing writes it).

5. **Migrate the existing tests** (`tests/test_connectors_discord.py:2838/2909/2951`): change `config={"guilds": [...]}` → `config={"allowlist": {"guilds": [...]}}`; keep the `tree.sync`-fires assertions. Rename test method names only if they explicitly say "config guilds" (optional; semantic clarity).

6. **Update agents.md narrative** (`:797`) to the unified `allowlist.guilds` read path — by intent, not wholesale rewrite (project-owned doc; Skill–Project Boundary discipline).

7. **Run the grep gate** and record results + the final backend/browser test counts in the flight-log L2 entry. Note the operator-cleanup is now automatic — the v27 migration moves their diagnostically-added top-level `config.guilds` into the allowlist.

## Edge Cases

- **`intents.guilds` vs `config.guilds` confusion** — the single most likely implementation error. Retire ONLY the "Scope to servers" text field; the "Server info" intent checkbox stays. Verify both `data-testid="discord-guilds-list"` (retire) and `data-field="intent-guilds"` (keep) after the edit.
- **Migration union when both keys present** (operator's row: top-level `config.guilds` from the F13 L6 PUT + possibly populated allowlist.guilds): union + dedup, preserving order, no duplicates.
- **`allowlist` key absent on old rows**: `setdefault("allowlist", {})` creates it; only do so when there's a top-level `guilds` to fold (don't gratuitously add empty allowlists to rows that never had guilds).
- **Empty `allowlist.guilds` post-migration**: slash-sync skips with INFO (documented blank-handling). ACL treats empty guilds-axis as admit-all per its existing tri-state — the asymmetry is intentional.
- **Partial migration apply** (crash mid-loop): re-run folds remaining rows; already-folded rows are no-ops. schema_version INSERT is last.

## Files Affected

- `the_one/db/schema.py` — `CURRENT_VERSION` 26→27 (`:15`); v27 migration.
- `the_one/connectors/_discord.py` — `_sync_slash_commands` read; docstring (`:237`); doc-comment (`:1000`).
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — retire "Scope to servers" field at all 6 sites (`:151/:200-220/:412-417/:464/:580/:710`) + delete `_splitGuildsList` (`:381`); KEEP `intents.guilds` checkbox.
- `the_one/interfaces/web/api.py` — remove top-level `config.guilds` validator (`:1088-1116`).
- `the_one/agents.md` — slash-sync narrative (in the M10 F8 L9 CommandHandler section, located by the `for each g in ...` sentence) + a coupling note in the guilds-axis ACL section.
- `tests/test_connectors_discord.py` — migrate 3 slash-sync tests (`:2838/:2909/:2951`; `:2951` int→str + rename).
- `tests/test_db_migration.py` — update `CURRENT_VERSION` assert (`:261-264`) to 27; add v27 migration test.
- `tests/browser/test_flow_studio_connector_discord_form.py` — `test_guilds_add_saves` (`:225-241`) remove/rewrite; `test_additional_config_hides_reserved_keys` (`:266-309`) drop the `:283` fixture + `:308` assert.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — except commit, which is deferred to Phase 2d per agentic-workflow batch protocol:**

- [ ] All acceptance criteria verified (v27 migration + grep gate are the load-bearing ones)
- [ ] Backend + browser suites green / 0 errors (final counts recorded in flight-log)
- [ ] Update flight-log.md with L2 leg progress entry (scope pivot already logged in FD Notes; record migration version, test-count delta, grep-gate result)
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off this leg in flight.md yet (done at Phase 2d commit)
- [ ] Do NOT commit (batched at Phase 2d)
