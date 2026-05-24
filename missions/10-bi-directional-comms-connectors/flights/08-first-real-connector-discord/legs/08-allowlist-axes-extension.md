# Leg: allowlist-axes-extension

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Extend the F6 per-axis tri-state allowlist with two new axes: `guilds` and `roles`. The four axes (peers, channels, guilds, roles) compose per-axis AND, NOT single-list AND, per the `per-axis-tri-state-override` convention codified in L1. Touch:
1. **Pydantic validator** (`_validate_config_reserved_keys` in `db/models.py`) — accept `guilds` and `roles` as OPTIONAL keys in `config["allowlist"]` (back-compat: existing 2-key rows still validate; absent axis = unrestricted on that axis).
2. **`AgentConfig.connector_acls` inner-dict validator** — same shape extension; back-compat.
3. **`_acl.admits_inbound` and `admits_outbound`** — consult the two new axes from `account.config["allowlist"]` and per-agent ACL. The inbound caller computes `guild_id` from `envelope.raw.get("guild_id")` and `member_roles` from `envelope.raw.get("member_roles", [])` (L4 populates both). Outbound has no envelope context — guilds/roles axes are NOT consulted on outbound (consistent with the F6 channel-axis fallback).
4. **Studio Allowlist editor** (`connector-account-editor.js`) — add two new chip-list rows for guilds + roles (mirror the existing peers/channels rows). F6 carry-forward: remove the two stale Enable-toggle refs at lines `:658` and `:1361`.
5. **Tests** — extend validator tests, acl tests, routing tests; ~10+ new tests total.

## Context

L8 of F8. Per flight Design Decisions:

- **Per-axis tri-state generalizes**: axis missing → unrestricted; axis `[]` → unrestricted on this axis; non-empty list → subset. Applies to all 4 axes uniformly.
- **Outbound doesn't consult guilds/roles**: the F4 platform-send tool has only `(channel_id, thread_id)` — no envelope. The L8 outbound code path leaves guilds/roles unchecked (silently permit if peers/channels axes permit). F10 hardening can revisit if HAT surfaces concrete needs.
- **F6 carry-forward — stale `editor.js` Enable-toggle refs**: lines `:658` and `:1361` reference an Enable toggle that F6 dropped. L8 removes those comments while extending the editor.
- **Validator back-compat**: existing accounts have `{peers: [...], channels: [...]}` only. After L8, the validator accepts `{peers, channels}` (existing), `{peers, channels, guilds}` (partial L8), `{peers, channels, guilds, roles}` (full L8). The 2-key shape is the no-op-on-new-axes default; the `_acl` admission code reads missing axes as unrestricted.

Key learnings from L4-L7:
- L4 populates `envelope.raw["guild_id"]` (str or None) and `envelope.raw["member_roles"]` (list of str role IDs). L8's admits_inbound reads these.
- L6 added the `is_dm: bool` kwarg pattern; L8 follows the same shape (additive optional kwargs on `_acl` admission helpers).
- L7's allowlist-resolution probe reads `account.config["allowlist"]["guilds"]` defensively — that pattern works after L8 because the new axis is optional/empty by default.

## Inputs

- `the_one/db/models.py:192-329` — `_validate_config_reserved_keys` with the existing 2-axis allowlist validation (lines 301-328).
- `the_one/db/models.py:_validate_connector_acls` (or similar — find it in the file; F6 L1c shipped the inner-dict validator on `AgentConfig.connector_acls`).
- `the_one/connectors/_acl.py` (post-L6) — `admits_inbound` and `admits_outbound` with the `is_dm` kwarg added. The 4-axis extension follows the same additive shape: new `guild_id: str | None = None` and `member_roles: list[str] | None = None` kwargs.
- `the_one/connectors/_routing.py:_agent_admits` (post-L6) — passes the plugin through; L8 also passes `envelope.raw.get("guild_id")` and `envelope.raw.get("member_roles", [])` into `admits_inbound`.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — chip-list rows for peers + channels exist (F6 L4); lines `:658` and `:1361` have stale Enable-toggle refs.
- L1-L7 test suite green (2341 passed).

## Outputs

- **`db/models.py:_validate_config_reserved_keys`** — extend the `allowlist` validation:
  - Replace `extra = set(allowlist.keys()) - {"peers", "channels"}` with `... - {"peers", "channels", "guilds", "roles"}`.
  - Replace `missing = {"peers", "channels"} - set(allowlist.keys())` with `missing = {"peers", "channels"} - set(allowlist.keys())` (UNCHANGED — peers + channels remain required; guilds + roles are optional).
  - Extend the loop `for key in ("peers", "channels"):` to `for key in ("peers", "channels", "guilds", "roles"):` — same shape contract for all 4 (list of strings, per-item is str, no de-dup).

- **`db/models.py:_validate_connector_acls`** (or wherever F6 L1c lives) — same extension. Optional `guilds` and `roles` keys on the inner per-account dict.

- **`_acl.py:admits_inbound`** signature extension:
  ```python
  def admits_inbound(
      account, agent_acl, peer_id, channel_id,
      *, is_dm: bool = False,
      guild_id: str | None = None,
      member_roles: list[str] | None = None,
  ) -> tuple[bool, str]:
  ```
  - After the existing peers + channels checks: add account-scope guild check (if `allowlist["guilds"]` is non-empty AND `guild_id not in allowlist["guilds"]` → deny). Then account-scope roles check (if `allowlist["roles"]` is non-empty AND no overlap with `member_roles` → deny).
  - Per-agent overlay follows the per-axis tri-state semantic: axis missing → inherit account-scope; axis `[]` → unrestricted on this axis at per-agent scope; axis non-empty → subset narrows further.

- **`_acl.py:admits_outbound`** — receives the new kwargs but does NOT consult guilds/roles. The kwargs are accepted for signature uniformity; the implementation is no-op for outbound. Comment: "outbound has no envelope context; guilds/roles consulted only on inbound."

- **`_routing.py:_agent_admits`** updated to pass `guild_id=envelope.raw.get("guild_id")` and `member_roles=envelope.raw.get("member_roles", [])` into `admits_inbound`.

- **`connector-account-editor.js`** — extend the Allowlist editor with two new chip-list rows:
  - "Guilds" — chip list for `account.config.allowlist.guilds`.
  - "Roles" — chip list for `account.config.allowlist.roles`.
  - Both rows match the existing peers/channels row shape (input + chip rendering + add/remove buttons).
  - Section heading: "Discord allowlist axes (guilds, roles)" or similar — these are platform-specific axes (Slack equivalent in F9 would be workspaces + groups; Matrix would be rooms + power-levels). The editor doesn't gate visibility by platform — all 4 axes show on every connector account; absent/empty axes mean "unrestricted." This is the pragmatic generic-UI / platform-agnostic choice; F10 hardening can revisit if operator UX surfaces confusion.

- **`connector-account-editor.js`** F6 carry-forward — remove the stale Enable-toggle refs at lines `:658` and `:1361`. These reference a feature F6 dropped.

- **Tests**:
  - `tests/test_db_repositories.py` (or wherever connector_account model tests live) — extend with 4-axis allowlist validation tests: full-4-axis shape, partial-axis shape, extra-key rejection, per-item-string validation.
  - `tests/test_connectors_acl.py` — extend with guilds/roles axes tests: guild deny, guild permit, role deny, role permit, per-axis tri-state cases.
  - `tests/test_connectors_routing.py` — `_agent_admits` test with guild + member_roles in envelope.raw.
  - Browser test (Playwright) for the new chip-list rows: NOT in L8 scope (L10 is the routing-rules-editor browser test; new editor UI doesn't get its own browser test in F8 — defer to F10 hardening if HAT surfaces issues).

- L1-L7 regression: 2341 → ~2360 (~19 new tests across validator/acl/routing).

## Acceptance Criteria

- [x] **`_validate_config_reserved_keys` accepts `guilds` + `roles`** as OPTIONAL keys in `allowlist`. Existing 2-key shape passes verbatim. Extra-key set is `{peers, channels, guilds, roles}` (rejects anything else). Per-item validation (list of strings) applies to all 4 axes.

- [x] **`_validate_connector_acls`** (the F6 L1c inner-dict validator) — extended with the same 4-axis allowlist shape. Back-compat: 2-key shape passes.

- [x] **`admits_inbound(account, agent_acl, peer_id, channel_id, *, is_dm=False, guild_id=None, member_roles=None)`** consults all 4 axes:
  - Account-scope guild check: if `allowlist["guilds"]` is non-empty AND `guild_id not in allowlist["guilds"]` → deny.
  - Account-scope roles check: if `allowlist["roles"]` is non-empty AND no overlap with `member_roles` → deny.
  - Per-agent guild check (overlay): same semantic at the per-agent scope.
  - Per-agent roles check (overlay): same semantic at the per-agent scope.
  - All four axes use the F6 per-axis tri-state semantic (missing = unrestricted; `[]` = unrestricted on this axis; non-empty = subset).

- [x] **`admits_outbound` signature** extended with the new kwargs (accept; do not consult). Body unchanged for guilds/roles. Comment notes the outbound-no-envelope rationale.

- [x] **`_routing._agent_admits` updated** to pass `guild_id=envelope.raw.get("guild_id")` and `member_roles=envelope.raw.get("member_roles", [])` into `admits_inbound`.

- [x] **Studio editor extension** — `connector-account-editor.js` adds two new chip-list rows for guilds + roles, matching the existing peers/channels row shape. Both rows render on every connector account regardless of platform.

- [x] **F6 carry-forward — stale Enable-toggle refs removed** at `connector-account-editor.js:658` and `:1361`.

- [x] **Tests**: at least 19 new tests across:
  - 4 validator tests (full 4-axis shape; partial axes; extra-key rejection; per-item-string)
  - 8 acl tests (guild deny/permit; role deny/permit; per-axis tri-state for each new axis; per-agent narrowing for guilds; per-agent narrowing for roles)
  - 2 routing tests (`_agent_admits` with guild + member_roles)
  - 5 misc / coverage of the new flow

- [x] **`agents.md` Connector subsystem section** — add a one-paragraph note on the 4-axis allowlist + the outbound-no-guilds/roles fallback.

- [x] **F1-F7 + L1-L7 regression**: 2341 → ~2360. All existing F6/F7 allowlist tests pass byte-identically (existing 2-key shape preserved; admission semantics for absent axes are unchanged).

## Verification Steps

- `grep -c '"guilds"\|"roles"' the_one/db/models.py` — at least 2 (validator extension).
- `grep -c 'guild_id\|member_roles' the_one/connectors/_acl.py` — at least 4 (account + per-agent for both axes).
- `grep -c "ENABLE_TOGGLE\|enable_toggle\|enableToggle\|enable-toggle" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — 0 (stale refs removed).
- `docker exec the-one pytest tests/test_db_repositories.py tests/test_connectors_acl.py tests/test_connectors_routing.py -x --timeout 30` — all pass.
- `docker exec the-one pytest tests/ -x --timeout 30` — full suite passes.

## Implementation Guidance

1. Extend `_validate_config_reserved_keys` (and the connector_acls validator) with the 4-axis shape. Run validator tests.
2. Extend `admits_inbound` with the new kwargs + 4-axis consult logic.
3. Extend `admits_outbound` signature (accept kwargs, don't consult).
4. Update `_routing._agent_admits` to thread the new fields from envelope.raw.
5. Extend `connector-account-editor.js` with the two new chip-list rows. Drop the stale Enable-toggle refs in the same pass.
6. Tests: validator first, then acl, then routing.
7. agents.md note.
8. Full suite green.

## Edge Cases

- **`envelope.raw["guild_id"]` is None** (DM context): the guild check sees `guild_id=None`. If `allowlist["guilds"]` is non-empty, `None not in <list of strs>` → deny. **Decision**: DMs (no guild) when `guilds` axis is restrictive should DENY — the operator narrowed to specific guilds, DMs are out-of-scope. Alternative: bypass guilds axis when `is_dm=True`. Default: deny per the per-axis semantic. Document and pin in tests.
- **`envelope.raw["member_roles"]` is empty list**: the roles overlap check `set(member_roles) & set(allowlist["roles"])` is empty → deny. Consistent: peer has no roles, role-restricted account denies.
- **Pre-L8 rows decode to `allowlist = {peers, channels}`**: the new axes are absent → unrestricted by tri-state semantic. No deny. Back-compat.
- **`per-agent` ACL has only guilds set**: `peers` + `channels` axes inherit account-scope; `guilds` axis narrows further. Tri-state per axis is independent.

## Files Affected

- `the_one/db/models.py` — `_validate_config_reserved_keys` allowlist extension + `_validate_connector_acls` inner-dict allowlist extension
- `the_one/connectors/_acl.py` — `admits_inbound` extended; `admits_outbound` signature accepting but not consulting new kwargs
- `the_one/connectors/_routing.py` — `_agent_admits` passes guild_id + member_roles through
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — new guilds + roles chip-list rows; stale Enable-toggle refs removed at `:658` and `:1361`
- `the_one/agents.md` — Connector subsystem 4-axis allowlist note
- `tests/test_db_repositories.py` (or model-specific test file) — validator tests
- `tests/test_connectors_acl.py` — acl axis tests
- `tests/test_connectors_routing.py` — routing test

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set leg status to `landed`
- [x] Check off L8 in flight.md
- [x] Do NOT commit — wait for flight-level review

## Citation Audit

- `db/models.py:192-329` — `_validate_config_reserved_keys` + allowlist validation block — **OK**
- `db/models.py:_validate_connector_acls` — F6 L1c shipped (exact line at implementation time)
- `connectors/_acl.py:admits_inbound` — post-L6 signature — **OK**
- `connectors/_routing.py:_agent_admits` — post-L6 — **OK**
- `interfaces/web/static/js/areas/studio/connector-account-editor.js:658, 1361` — stale Enable-toggle refs — **OK** (per L1 recon, file is now 2277 lines)
- L4-populated `envelope.raw["guild_id"]` and `envelope.raw["member_roles"]` — **OK**

6 citations verified.
