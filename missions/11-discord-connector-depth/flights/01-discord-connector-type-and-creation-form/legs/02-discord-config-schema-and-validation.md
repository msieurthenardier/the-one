# Leg: discord-config-schema-and-validation

**Status**: landed
**Flight**: [Discord Connector-Type Registration + Discord-Shaped Creation Form](../flight.md)

## Objective

Add API-layer per-type config validation for Discord connector accounts and lift the existing plugin-side inline checks for `intents`, `guilds`, and `presence` to the API boundary; replace the Discord plugin's hardcoded intents at `_discord.py:619-622` with `account.config["intents"]` reads that fall back to existing-behavior defaults so M10 F8 accounts round-trip with byte-identical behavior.

## Context

- **Why now**: F1 flight Design Decision "Per-type config validation layer — API-layer per-type dispatch" (`flight.md` Design Decisions §1) commits to a `_validate_connector_account_config(account)` validator mirroring the existing `_validate_mcp_source_config` precedent. The L2 spec in `flight.md` Legs §2 names this leg, lists the three config keys, and binds it to L1's freshly codified `atomic-leg-pattern` (validator + plugin + consistency-test all in one leg). The current `create_connector_account` at `api.py:2148-2166` carries a comment at `api.py:2160-2163` explicitly deferring per-type validation to this flight: "No per-type config-shape validation in this leg — the F1 stub accepts arbitrary config, and per-type validation lands per-connector in Flights 8 / 9 (mirror of `_validate_mcp_source_config` which is type-aware)." L2 closes that comment.
- **Prerequisite from L1**: `atomic-leg-pattern` is now codified in `the_one/agents.md` under Project Conventions; this leg invokes it by name — the validator (`interfaces/web/api.py`), the plugin behavior change (`connectors/_discord.py`), and the new consistency tests land together.
- **Backward-compatibility shape**: M10 F8 shipped accounts whose `config` lacks an `intents` key. The plugin currently sets all three intents (`message_content`, `members`, `guilds`) to True unconditionally at `_discord.py:619-622`. L2 must produce byte-identical behavior for accounts without `config["intents"]` — fallback `{message_content: True, members: True, guilds: True}`. The existing `tests/test_connectors_discord.py::test_intent_construction` (line 416) is the regression gate: it does NOT set `config["intents"]` and asserts all three booleans are True. L2 must NOT break this test.
- **What's NOT in scope**: typed UI for intents/guilds/presence — that's L4. The kv-table UI keeps accepting these keys via the generic editor until L4 lands the typed form. The Discord plugin's read sites for `presence` (`_discord.py:624`) and `guilds` (`_discord.py:240`) are unchanged by L2 — they already read from `account.config`; the existing inline shape checks at `_build_activity` (lines 297-302 — the `elif presence_config is not None` block) and `_sync_per_guild_commands` (line 236+) stay as defensive runtime guards because the operator may manually edit the DB outside the API write path, and the F1 single-user local-tool trust posture treats that as acceptable.
- **State-machine reachability**: this leg introduces no new states. The validator is a pure shape-gate at the API write boundary; it does not change the DB schema, the plugin lifecycle, or any pool keying. No FK constraints, caches, or migrations touched.

### Design Decisions (L2-internal, promoted from edge cases for visibility)

- **Empty `intents` dict is a 422, not a "use defaults" signal**: `config["intents"] = {}` violates the validator's "exactly these three keys" rule. The absence of the `intents` key is the canonical "use defaults" signal; the explicit empty-dict form is rejected. Rationale: the absent-key path round-trips M10 F8 accounts byte-for-byte; the explicit-empty-dict form is operator intent that the validator should treat as a deliberate malformed shape rather than as a synonym for absence. This decision IS load-bearing on the API contract — promoted from Edge Cases so a future contributor doesn't quietly relax it.
- **Presence `type` value set is pinned at the validator layer, not derived from the plugin**: the plugin's `_resolve_activity_type` at `_discord.py:124-137` uses `getattr(discord.ActivityType, type_name)` with a try/except fallback to `watching` — so any string would technically not crash the plugin. The validator nonetheless pins the operator-meaningful subset of `discord.ActivityType` values at the API boundary: `{"playing", "streaming", "listening", "watching", "competing"}`. Excluded: `"unknown"` (a default sentinel, never an operator choice) and `"custom"` (Discord-API-only via custom status, not supported by the bot-presence surface). L4's typed dropdown UI inherits this exact set. **Note for the implementer**: the validator pins this set as a local frozenset literal — do NOT read from `discord.ActivityType` at validator-import time, because the validator must stay testable in environments where `discord` is patched/absent.
- **WARNING-log on `message_content=False` is novel behavior**: the M10 F8 baseline had no log for disabled intents (because they couldn't be disabled — hardcoded True). L2 introduces the WARNING-log; record this as a deviation in the flight-log at leg-completion so reviewers can audit the new log site.
- **Validator 422 detail strings are operator-facing**: per `verbatim-message-equality` (codified in agents.md), the rejection-test assertions pin the detail strings byte-for-byte. The exact strings are defined in §§ 4-6 below; the implementing agent must write them as specified (and the tests must `assert detail == "..."` not regex-match).

## Inputs

Files that must exist:
- `the_one/interfaces/web/api.py` (target for the new `_validate_connector_account_config` helper and the two call sites in `create_connector_account` / `update_connector_account`)
- `the_one/connectors/_discord.py` (target for the intents-from-config refactor at lines 619-622)
- `tests/test_connectors_discord.py` (existing `test_intent_construction` at line 416 — regression gate; new `test_intents_from_config` test goes here)
- `tests/test_db_api.py` or a new `tests/test_api_connector_account_config_validation.py` (test landing site for the API-rejection tests)
- `tests/test_connector_types_consistency.py` (existing consistency-pin test — verify it still passes; not extended here)
- `the_one/db/models.py` (`ConnectorAccount` model — read for context; NO edit; per F1 Design Decision "Pydantic model stays type-neutral; per-type knowledge lives at the API boundary")

State that must be true:
- L1 is `landed` (codification of the six conventions in `the_one/agents.md`, including `atomic-leg-pattern`)
- Flight branch `flight/01-discord-connector-type-and-creation-form` is checked out
- No uncommitted source changes besides L1's `agents.md` edit + the M11 mission/flight/leg artifacts

## Outputs

State changes after this leg:
- `the_one/interfaces/web/api.py` gains `_validate_connector_account_config(account: ConnectorAccount) -> None` mirroring `_validate_mcp_source_config:730+`; dispatches on `account.type`. Discord branch validates the three config keys; `'stub'` branch passes through (no per-type config knowledge for stubs).
- `create_connector_account` at `api.py:2148` calls `_validate_connector_account_config(account)` between `model_validate` and `repo.create` (replacing the deferred-validation comment at lines 2160-2163).
- `update_connector_account` at `api.py:2169` calls `_validate_connector_account_config(updated)` between `model_validate(merged)` and `repo.update` (same insertion shape).
- `the_one/connectors/_discord.py:619-622` replaced: `intents = discord.Intents.default()` followed by `intents_cfg = account.config.get("intents", {})` and three `intents.<axis> = intents_cfg.get("<axis>", True)` reads. The hardcoded `= True` literals are gone; defaults flow through the `.get("<axis>", True)` second-arg.
- Plugin emits a single WARNING-level log line at `connect()` if `intents_cfg.get("message_content", True) is False` (with a short message: "Discord intents.message_content disabled in config; bot will silently receive no channel messages"). No log if all three default-True remain.
- `tests/test_connectors_discord.py` gains `test_intents_from_config_honored` (config-driven shape, all three explicitly False except `message_content=True`) and `test_intents_fallback_defaults_when_config_missing` (renames or supplements the existing `test_intent_construction`; the existing test continues to assert default-True behavior).
- New test file `tests/test_api_connector_account_config_validation.py` (or extension to `tests/test_db_api.py` if that's the established home for connector-account API tests) covers the validator's rejection cases per Acceptance Criteria below.

## Acceptance Criteria

- [ ] `interfaces/web/api.py` defines `_validate_connector_account_config(account: ConnectorAccount) -> None` placed near `_validate_mcp_source_config` (alphabetical or grouped-by-purpose, reviewer's discretion). The helper dispatches on `account.type` with branches for `'discord'` and `'stub'`; `'stub'` branch passes (no shape validation). A trailing `else` branch raises `HTTPException(500, detail="Unknown connector type")` for forward-compat — this is unreachable for properly-validated input (Pydantic `Literal["discord", "stub"]` gates this upstream) but matches the `_validate_mcp_source_config` defensive-exhaustiveness pattern at `api.py:840-849`.
- [ ] Discord-branch validation for `account.config["intents"]`: when present, must be a `dict[str, bool]` with EXACTLY the three keys `{"message_content", "members", "guilds"}`, each value `bool` (`isinstance(value, bool)`, NOT `int` — bool-is-int trap from MCP precedent at `api.py:816`). Extra keys → 422. Missing required keys → 422. Non-bool value → 422. When `intents` key is absent entirely → pass through (plugin uses defaults).
- [ ] Discord-branch validation for `account.config["guilds"]`: when present, must be a `list[str]` where every entry is a string of decimal digits (Discord snowflake IDs are digit-only; the existing plugin read site at `_discord.py:236-249` already iterates and calls `int(g)` so non-digit entries crash at sync time — the validator catches them at the API boundary instead). Empty list `[]` passes. When absent → pass.
- [ ] Discord-branch validation for `account.config["presence"]`: when present, must be a `dict` with optional keys `name: str` (non-empty when present) and `type: str` (must be in the pinned set `_DISCORD_PRESENCE_TYPES = frozenset({"playing", "streaming", "listening", "watching", "competing"})` defined as a module-local constant in `api.py` next to the validator helper). When absent → pass; the existing defensive checks in `_build_activity` (lines 297-302) and the malformed-shape fallback behavior stay as runtime guards for DB-edited rows. Per Design Decisions §2: do NOT derive the set from `discord.ActivityType` at import time — the validator must remain testable without the Discord SDK patched in.
- [ ] `create_connector_account` calls `_validate_connector_account_config(account)` AFTER `ConnectorAccount.model_validate(data)` (so the validator sees an already-typed model) and BEFORE `repo.create(account)`. Same pattern as the MCP precedent at `api.py:create_mcp_source` (verify the MCP precedent's call site shape at design time and match it).
- [ ] `update_connector_account` calls `_validate_connector_account_config(updated)` AFTER the `ConnectorAccount.model_validate(merged)` at `api.py:2218` and BEFORE `repo.update(updated)` at `api.py:2221`.
- [ ] `connectors/_discord.py` lines 619-622 replaced as documented in Outputs above. The plugin reads `account.config.get("intents", {})` once, then three `.get("<axis>", True)` calls. WARNING log fires iff `message_content is False`.
- [ ] `tests/test_connectors_discord.py::test_intent_construction` (or its successor name) passes UNMODIFIED if it isn't renamed: an account without `config["intents"]` produces all three intents True. If the existing test is renamed (e.g. to `test_intents_fallback_defaults_when_config_missing`), the rename uses the established convention of preserving git blame on the body — the body byte-identical.
- [ ] New test `test_intents_from_config_honored` (in `tests/test_connectors_discord.py`): an account with `config["intents"] = {"message_content": False, "members": True, "guilds": True}` produces a client whose `_intents.message_content is False`, `_intents.members is True`, `_intents.guilds is True`. The test patches the `discord` SDK consistent with the existing test module's `_patch_discord` helper.
- [ ] New API-validation tests cover the rejection matrix:
  - intents missing a required key → 422
  - intents with extra keys → 422
  - intents with a non-bool value → 422
  - guilds with a non-digit entry → 422
  - guilds with a non-string entry → 422
  - presence as a non-dict → 422
  - presence with `name=""` (empty string) → 422
  - presence with an unknown `type` → 422
  - happy path: all three keys present and well-formed → 201/200
  - happy path: all three keys absent → 201/200 (M10 F8 backward compat)
  - `'stub'` account-type with arbitrary `config` → passes (no Discord-shape validation)
- [ ] `pytest tests/test_connector_types_consistency.py` continues to pass UNMODIFIED — the consistency layer is layer-1/3/4; L2 doesn't touch any of those.
- [ ] Full suite `docker exec the-one pytest -x --timeout 30 -q` stays at or beats the L1 post-leg baseline (2404 passed). New tests add to the count; no regressions.

## Verification Steps

- `grep -n "_validate_connector_account_config" the_one/interfaces/web/api.py` returns: one definition (mirrors location of `_validate_mcp_source_config:730`), one call in `create_connector_account`, one call in `update_connector_account`. Three hits total.
- `grep -n "intents.message_content = True" the_one/connectors/_discord.py` returns ZERO hits (the hardcoded literals are gone).
- `grep -n 'account.config.get("intents"' the_one/connectors/_discord.py` returns exactly one hit (the new fallback read).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_discord.py::test_intent_construction` (or its rename) PASSES with the existing assertion body (all three intents True for an account without `config["intents"]`).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_discord.py::test_intents_from_config_honored` PASSES against a config with explicit `message_content: False`.
- `docker exec the-one pytest -x --timeout 30 tests/test_connector_types_consistency.py` PASSES UNMODIFIED.
- `docker exec the-one pytest -x --timeout 30 tests/test_api_connector_account_config_validation.py` (new file) — every rejection case returns 422; every happy-path case returns 201/200. Use the existing test-app fixture pattern from `tests/test_db_api.py` (read it first to match the fixture-setup shape).
- `docker exec the-one pytest -x --timeout 30 -q` — full suite stays at L1 post-leg baseline + new test count. No regressions.

## Implementation Guidance

1. **Read the MCP precedent end-to-end**:
   - `the_one/interfaces/web/api.py:_validate_mcp_source_config` at line 730 (the helper definition; ~120 lines)
   - The call sites: `create_mcp_source` and `update_mcp_source` in the same file — locate them via `grep -n "create_mcp_source\|update_mcp_source" the_one/interfaces/web/api.py`. Confirm the call-site shape: validator runs AFTER `model_validate` and BEFORE `repo.create` / `repo.update`. Match the connector-account call sites to the same shape.
   - Note especially the `isinstance(value, bool)` (NOT `int`) pattern at `api.py:816` — replicate.
   - Note the trailing `else` defensive-exhaustiveness raise at `api.py:840-849` — replicate at the connector-account level.

2. **Read the existing plugin-side checks** that the validator lifts:
   - `the_one/connectors/_discord.py:_build_activity` at line 267 — current shape check for `presence`. The validator should accept the same set of `type` values; enumerate them by reading the function body (look for the canonical set; the design decision named `"watching"`, `"playing"`, `"listening"`, `"streaming"`, `"competing"` as the likely set but confirm against the source).
   - `the_one/connectors/_discord.py:_sync_per_guild_commands` at line 236 — current iteration over `account.config.get("guilds")`. The validator's "digit-only string" rule is what makes this iteration's `int(g)` call safe at the API boundary.
   - The runtime defensive checks stay in place: an operator editing the DB directly can still inject malformed config; the runtime guards catch it; the validator catches it at write-time.

3. **Design the validator's helper structure**. Inside the Discord branch:
   ```python
   def _validate_connector_account_config(account: ConnectorAccount) -> None:
       """..."""
       cfg = account.config
       if account.type == "discord":
           _validate_discord_intents(cfg)
           _validate_discord_guilds(cfg)
           _validate_discord_presence(cfg)
       elif account.type == "stub":
           pass  # stubs accept any config — F1 trust posture
       else:
           raise HTTPException(status_code=500, detail=f"Unknown connector type: {account.type!r}")
   ```
   The three private helpers (`_validate_discord_intents`, `_validate_discord_guilds`, `_validate_discord_presence`) are file-local; alternatively inline the three blocks into the main `_validate_connector_account_config` body if you prefer the `_validate_mcp_source_config` flat-block shape — both are acceptable. Reviewer preference: inline for parity with MCP unless any block exceeds ~25 lines, in which case extract.

4. **Implement `_validate_discord_intents(cfg)`**:
   - If `"intents"` not in cfg → return (validator passes; plugin uses defaults).
   - If `cfg["intents"]` is not a dict → `HTTPException(422, detail="Discord connector config.intents must be a dict.")`.
   - Define `REQUIRED = {"message_content", "members", "guilds"}`. If `set(cfg["intents"].keys()) != REQUIRED` → `HTTPException(422, detail=f"Discord connector config.intents must have exactly these keys: {sorted(REQUIRED)}; got: {sorted(cfg['intents'].keys())}.")`.
   - For each `key, value in cfg["intents"].items()`: if `not isinstance(value, bool)` → `HTTPException(422, detail=f"Discord connector config.intents.{key} must be a boolean; got {type(value).__name__}.")`.

5. **Implement `_validate_discord_guilds(cfg)`**:
   - If `"guilds"` not in cfg → return.
   - If not isinstance list → 422 ("config.guilds must be a list of digit-only strings if present.").
   - For each entry: if not isinstance str → 422 ("config.guilds entries must be strings; got {type(entry).__name__}."). If not entry.isdigit() OR len(entry) == 0 → 422 ("config.guilds entries must be non-empty decimal-digit strings; got {entry!r}.").

6. **Implement `_validate_discord_presence(cfg)`**:
   - Module-level constant near the helper: `_DISCORD_PRESENCE_TYPES = frozenset({"playing", "streaming", "listening", "watching", "competing"})`. Do NOT use `discord.ActivityType` at import time (the validator must be testable without the SDK patched in).
   - If `"presence"` not in cfg → return.
   - If `not isinstance(cfg["presence"], dict)` → 422 with detail string `"Discord connector config.presence must be a dict if present."`.
   - If `"name"` in presence: must be `str`; must be non-empty after `.strip()`. Detail string on rejection: `"Discord connector config.presence.name must be a non-empty string."`.
   - If `"type"` in presence: must be `str`; must be in `_DISCORD_PRESENCE_TYPES`. Detail string on rejection: `f"Discord connector config.presence.type must be one of: {sorted(_DISCORD_PRESENCE_TYPES)}; got: {value!r}."`.
   - Extra keys in the presence dict: silently allowed (the runtime ignores unknown keys per the `trust-the-runtime` convention codified in agents.md). Don't enforce.

7. **Wire into `create_connector_account`** at `api.py:2148`. Replace the deferred-validation comment block at `api.py:2160-2163` with the BARE call (no try/except wrapper — verified at design review: `create_mcp_source` at `api.py:900` invokes its validator as `_validate_mcp_source_config(source)` directly; the helper raises `HTTPException` and the FastAPI exception-handler chain takes care of the response. Match exactly):
   ```python
   _validate_connector_account_config(account)
   ```

8. **Wire into `update_connector_account`** at `api.py:2169`. Place the call AFTER `updated = ConnectorAccount.model_validate(merged)` at line 2218 and BEFORE `await repo.update(updated)` at line 2221.

9. **Refactor the Discord plugin intents block** at `_discord.py:619-622`:
   ```python
   # Before:
   intents = discord.Intents.default()
   intents.message_content = True
   intents.members = True
   intents.guilds = True
   # After:
   intents = discord.Intents.default()
   intents_cfg = account.config.get("intents", {})
   intents.message_content = intents_cfg.get("message_content", True)
   intents.members = intents_cfg.get("members", True)
   intents.guilds = intents_cfg.get("guilds", True)
   if intents.message_content is False:
       logger.warning(
           "Discord intents.message_content disabled in config for account %s; "
           "bot will silently receive no channel messages",
           account.id,
       )
   ```
   Place the new code in the same indentation context as the original (inside `DiscordPlugin.connect`, near line 619).

10. **Update the existing intent test**:
    - The existing `tests/test_connectors_discord.py::test_intent_construction` (line 416) currently asserts all three intents True with no `config["intents"]` set. **Default**: leave the test name unchanged — the assertion still holds because the new code path falls back to the same True defaults; preserving the name is the lower-risk path (no rename → blame preserved trivially).
    - **`_make_account` extension**: the helper at `tests/test_connectors_discord.py:356-377` currently accepts discrete kwargs (`bot_token_plaintext`, `presence`, `ready_timeout_seconds`) and builds `config` from them. Add a new discrete kwarg `intents: dict[str, bool] | None = None`, mirroring the existing `presence` pattern: `if intents is not None: config["intents"] = intents`. Do NOT add a generic `config=` kwarg — discrete kwargs are the established pattern in this fixture helper.
    - Add a new test `test_intents_from_config_honored` immediately after the existing `test_intent_construction`. Use the same `_patch_discord` + `_make_encryptor` + `_make_account` helpers; pass `intents={"message_content": False, "members": True, "guilds": True}` into `_make_account` (per the discrete-kwarg extension above). Assert that `client._intents.message_content is False`, `client._intents.members is True`, `client._intents.guilds is True`.

11. **Create the new API-validation test file** at `tests/test_api_connector_account_config_validation.py`. Use the test-app fixtures established in `tests/test_db_api.py` (verified at design review to carry the connector-account API tests at line 544+). Mirror its fixture-setup shape — read the file's top-of-file imports + fixtures (FastAPI test client, in-memory DB, encryptor stub) and replicate. One test class `TestConnectorAccountConfigValidation` with the rejection-matrix cases listed under Acceptance Criteria as separate `async def test_*` methods. Assertions on detail strings must be byte-for-byte (`assert detail == "..."`) per `verbatim-message-equality`.

12. **Verify the `'stub'` carve-out**: pass through with arbitrary config. Add a test case in the validation test file that creates a stub-type connector account with `config={"foo": "bar", "intents": "this would fail discord validation"}` and confirms 201/200 — the validator MUST NOT apply Discord shape checks to stub-type accounts.

13. **Run tests in the prescribed order**:
    - `docker exec the-one pytest -x --timeout 30 tests/test_connectors_discord.py` first — confirms intent-construction tests pass.
    - `docker exec the-one pytest -x --timeout 30 tests/test_api_connector_account_config_validation.py` — new file's tests pass.
    - `docker exec the-one pytest -x --timeout 30 tests/test_connector_types_consistency.py` — unchanged pass.
    - `docker exec the-one pytest -x --timeout 30 -q` — full suite final check.

## Edge Cases

- **Bool-is-int trap**: `isinstance(1, bool)` is False in Python but `isinstance(True, int)` is True. The MCP precedent at `api.py:816` uses `isinstance(value, bool)` not `int` — the JSON `1` (which JSON decoders parse as int) MUST fail the intent-validator. Replicate exactly.
- **Empty `intents` dict**: `config["intents"] = {}` violates the "exactly these three keys" rule. The validator must reject with 422. The alternative ("empty dict means use defaults") is rejected because the absence of the key is the canonical "use defaults" signal.
- **Empty `guilds` list**: `config["guilds"] = []` is valid — passes the validator and the plugin's `_sync_per_guild_commands` at line 240 already handles the empty-or-absent case with an INFO log and early return.
- **`config["presence"] = {}`**: empty dict is valid — the plugin's `_build_activity` falls back to the default `Watching agent traffic`.
- **Stub-type with Discord-shaped config**: a stub account that happens to carry a `config["intents"]` key MUST NOT be validated as Discord. The dispatch on `account.type` ensures this; verify the test covers it.
- **Migration-residue rows**: F2 ships connector_accounts with `config = '{}'` plaintext as the column default. Reading them via the M10 F8 read path produces `config = {}` (empty dict). The validator (called only on API write paths) does NOT see these reads; they round-trip unchanged because the plugin's three `.get("<axis>", True)` calls fall back. No backfill required.
- **L4 typed UI not present yet**: operators editing via the generic kv-table can post a malformed `intents` shape ({"message_content": "yes"} with a string). The validator catches it pre-L4 — the UX is "submit fails with 422 detail string" until L4 ships the typed form. Acceptable per the flight's L2/L4 ordering.

## Files Affected

- `the_one/interfaces/web/api.py` — add `_validate_connector_account_config` helper; insert two call-site invocations in `create_connector_account` and `update_connector_account`; remove the deferred-validation comment at lines 2160-2163.
- `the_one/connectors/_discord.py` — replace hardcoded intents block at lines 619-622 with config-driven reads + WARNING-log; ~10 lines net change.
- `tests/test_connectors_discord.py` — optionally rename `test_intent_construction` (line 416); add `test_intents_from_config_honored` immediately below.
- `tests/test_api_connector_account_config_validation.py` — NEW FILE; rejection-matrix tests + happy-path + stub-type carve-out.
- `missions/11-discord-connector-depth/flights/01-discord-connector-type-and-creation-form/flight-log.md` — Leg Progress entry appended at leg-completion.
- `missions/11-discord-connector-depth/flights/01-discord-connector-type-and-creation-form/legs/02-discord-config-schema-and-validation.md` — status header transitions (planning → ready → in-flight → landed).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `docker exec the-one pytest -x --timeout 30 -q` final pass at or beating L1's 2404-passed baseline (new tests add to the count; no regressions)
- [ ] No source file modified beyond `api.py`, `_discord.py`, and the two test files; `git status` shows only those plus the leg/flight-log artifacts
- [ ] Each new validator branch grepped — verify exact call sites and helper definition appear at the expected locations
- [ ] Update flight-log.md with leg progress entry (Started / Completed timestamps, Changes Made summary, Notes on any decisions)
- [ ] Set this leg's status to `landed` (NOT `completed`) in this file's header
- [ ] Do NOT check off the leg in flight.md (that happens at flight-commit time)
- [ ] Do NOT commit (per agentic-workflow v2 — single flight-end commit at flight close)

## Citation Audit

Citations verified at leg design time (2026-05-21, post-L1; second pass after design review):

- `the_one/interfaces/web/api.py:_validate_mcp_source_config` — verified at line 730; ~120-line helper with three transport branches and a defensive-exhaustiveness `else` raise at lines 840-849. The `isinstance(value, bool)` check (not `int`) is at line 816.
- `the_one/interfaces/web/api.py:create_mcp_source` — verified: invokes `_validate_mcp_source_config(source)` as a BARE call at line 900 (no try/except wrapper). This is the precedent the connector-account call sites match.
- `the_one/interfaces/web/api.py:create_connector_account` — verified at line 2148. The deferred-validation comment is at lines 2160-2163.
- `the_one/interfaces/web/api.py:update_connector_account` — verified at line 2169. `ConnectorAccount.model_validate(merged)` at line 2218; `await repo.update(updated)` at line 2221. Insertion point is between them.
- `the_one/connectors/_discord.py:619-622` — verified: `intents = discord.Intents.default()` at 619, three hardcoded `= True` assignments at 620-622.
- `the_one/connectors/_discord.py:_resolve_activity_type` — verified at lines 124-137; uses `getattr(discord.ActivityType, type_name)` with try/except fallback to `watching`. There is NO module-level canonical-set; the validator pins its own frozenset (Design Decisions §2).
- `the_one/connectors/_discord.py:_build_activity` — verified at line 267; ~35-line helper. The presence-shape `isinstance(presence_config, dict)` and `elif presence_config is not None` guards are at lines 276 + 297-302. Falls back to `_DEFAULT_PRESENCE` (`{"name": "Watching agent traffic", "type": "watching"}` at lines 94-97) on malformed shape; logs WARNING.
- `the_one/connectors/_discord.py:_sync_per_guild_commands` — verified at line 236+; iterates `account.config.get("guilds") or []`; per-guild `int(guild_id)` call would crash on non-digit strings (validator catches at API boundary).
- `tests/test_connectors_discord.py::_make_account` — verified at lines 356-377: accepts discrete kwargs (`bot_token_plaintext`, `presence`, `ready_timeout_seconds`); NO `config` kwarg today. Extend with `intents: dict[str, bool] | None = None` mirroring the `presence` shape.
- `tests/test_connectors_discord.py::test_intent_construction` — verified at line 416; asserts all three intents True for an account without `config["intents"]`. Recommend: do NOT rename; the existing body still asserts correct fallback behavior post-refactor.
- `tests/test_db_api.py` — verified to exist; connector-account API tests land here starting at line 544. Use its established fixtures (FastAPI test client + in-memory DB + encryptor stub) as the template for the new validation-test file.

Eleven citation clusters verified live. No drift.
