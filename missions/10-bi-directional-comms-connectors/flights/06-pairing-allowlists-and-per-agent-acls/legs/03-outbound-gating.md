# Leg: outbound-gating

**Status**: completed
**Flight**: [Pairing, Allowlists, and Per-Agent ACLs](../flight.md)

> **Post-redesign note (M10 F6 L7 HAT, 2026-05-19)**: outbound gating
> semantics were flipped during HAT. Account-scope
> `allowlist.channels = []` now PERMITS all channels (was: deny
> everyone). Per-agent `channels` is tri-state — `None` inherits,
> `[]` is the F8-deferred "DMs only" sentinel (fail closed until F8
> ships DM classification), `[items]` narrows. See the **Deviations**
> entry in `../flight-log.md` for the new model and surface impact.
> The body of this artifact reflects the pre-redesign two-state
> contract for archaeology.

## Objective

Land the outbound consult that `SendToPlatformChannelTool.execute` ships with a `# F6:` placeholder. The tool's `__init__` gains a `connector_acls: dict[str, dict[str, list[str]]] | None = None` kwarg (passed by `AgentFactory.create` from `config.connector_acls`); `execute` does a function-local-import per-call fetch of the account from `ConnectorAccountRepository.get(account_id)` and intersects two scopes against `target.channel_id`: (i) account-scope `account.config["allowlist"]["channels"]` (absent → permit); (ii) per-agent `self._connector_acls[account_id]["channels"]` (account_id absent OR empty list → no agent-level narrowing). Denial returns the standard `[error] [constraint] ...` envelope; permit proceeds to the existing pool_acquire + client.send. No `ToolProvider` Protocol widening (deferred to F8 per cycle-2 finding). The `# F6:` marker comment is replaced by the actual consultation; `connectors/README.md:380` quoted marker text is updated alongside.

## Context

- **Flight Design Decision — "Per-call repository fetch + ACL kwarg"** (flight.md): `SendToPlatformChannelTool.__init__` gains `connector_acls: dict[str, dict[str, list[str]]] | None` kwarg; `execute()` fetches `account.config["allowlist"]` via `ConnectorAccountRepository.get(account_id)` at call time (function-local import — mirrors `_inbound.py:130-142`). Default-permit semantics: account with no `config["allowlist"]` and agent with no `connector_acls[account_id]` entry → permit. Stale-snapshot risk avoided by reading account state at send time.
- **No `ToolProvider` Protocol widening** (cycle-2 finding #4 deferred to F8): the existing F4 pattern at `factory.py:314-331` already isinstance-branches on `BuiltinToolProvider` to pass the widened kwargs. Leg 3 adds ONE kwarg (`connector_acls`) to the same widened path. F8 may eventually justify Protocol widening once a third factory-time-kwarg case emerges; not yet.
- **Empty-ACL inheritance semantics** (flight Design Decision + leg 1c): if `connector_acls[account_id]` is ABSENT from the agent's ACL dict (or the per-account inner shape is `{"peers": [], "channels": []}` with empty channels), the agent does NOT narrow — it inherits whatever the account-scope allowlist says. A non-empty `channels` list IS narrowing — the agent reaches ONLY those channels (intersected with account-scope). Documented at `agent/config.py:connector_acls` per leg 1c.
- **`account.config["allowlist"]["channels"]` source** is from leg 1b. The validator runs on `_row_to_model` direct construction, so the dispatcher receives a validated dict. Default-permit-on-absence semantics — same as inbound leg 2.
- **Symbolic marker replacement**: the comment `# F6: AllowlistResolver consultation lands here.` at `tools/connector_send.py:131` is the F4-shipped placeholder. Leg 3 replaces it with the actual consultation. The quoted marker text in `connectors/README.md:380` (deferred by leg 1a) is updated alongside — the README's "Outbound flow trace" section names the literal marker; leg 3 rewrites that prose to reflect the actual F6 consultation that now lives there.
- **Tool-target validation order**: existing flow at `connector_send.py:106-129` does shape checks then account-scope (`account_id ∈ self._connector_account_ids`). Leg 3 INSERTS the F6 channel+per-agent ACL consultation AFTER account-scope and BEFORE pool_acquire. Rationale: account-scope is the existing F4 fast-path constraint (no DB hit); F6's per-call account fetch is the more expensive consult. Keep the cheap denial first.
- **The per-call account fetch error path**: `ConnectorAccountRepository.get(account_id)` raises `KeyError` if the account doesn't exist. Since account-scope validation already rejected unknown `account_id` values (leg 1a F4 pattern, line 125), reaching the F6 consult with a known-good `account_id` should be invariant. Defensive: catch the KeyError and return `[error] [constraint] account_id <id> not found` (this is unreachable in the F4 path's invariant but worth defending against test races where the account is deleted mid-tool-call).
- **No agent-loop change**: leg 3 only modifies `tools/connector_send.py` (and downstream test sites). The agent loop at `agent/core.py` is untouched.
- **Function-local import convention** (per `agents.md:function-local-import-to-break-load-cycle`): `from the_one.db.connection import get_connection`, `from the_one.db.repositories import ConnectorAccountRepository`, `from the_one.encryption import get_encryptor`, `from the_one.config import settings` go INSIDE `execute()`. Mirrors the same pattern as `connectors/_inbound.py:130-142`. Inline comment captures the load-cycle motivation.
- **F4 success-path PLATFORM_SEND_OK_PREFIX** stays untouched. Leg 3 only adds an EARLY-RETURN denial path; the existing success envelope is unchanged.
- **Leg 1c's `AgentConfig.connector_acls`** is the source. `AgentFactory.create` passes `config.connector_acls` through to `BuiltinToolProvider.get_tools(..., connector_acls=...)`, which passes it through to `SendToPlatformChannelTool.__init__(..., connector_acls=...)`. Three pass-through sites:
  - `the_one/agent/factory.py:320` (kwargs to `provider.get_tools`)
  - `the_one/tools/builtins.py:99-105` (signature) + `:158-162` (extra_kwargs assembly)
  - `the_one/tools/connector_send.py:89-100` (__init__) + `:100` (self attribute) + execute consultation

## Inputs

- `the_one/tools/connector_send.py` — the F4 tool implementation; leg 3 modifies `__init__` (kwarg) and `execute` (consult site)
- `the_one/tools/builtins.py:99-167` — `BuiltinToolProvider.get_tools` widened-signature path
- `the_one/agent/factory.py:253-334` — `AgentFactory.create` provider invocation site
- `the_one/agent/config.py:AgentConfig.connector_acls` — leg 1c's field
- `the_one/db/models.py:ConnectorAccount.config` — leg 1b's allowlist shape
- `the_one/connectors/_inbound.py:130-142` — function-local-import precedent (same load-cycle motivation)
- `the_one/connectors/README.md:380` (verify exact line; may have drifted post-leg-1a) — quoted marker text site
- `tests/test_connector_send.py` (or wherever F4 tool tests live; verify) — F4 regression net; leg 3 extends with the channel-ACL tests

## Outputs

- `the_one/tools/connector_send.py` — `__init__` accepts `connector_acls: dict[str, dict[str, list[str]]] | None = None` kwarg (default-none = no per-agent narrowing); stored as `self._connector_acls`. `execute` replaces the `# F6:` marker with: function-local import + per-call `account = await acc_repo.get(account_id)` (guarded with try/except KeyError → constraint envelope); account-scope channel check (`channel_id ∈ account.config["allowlist"]["channels"]` if allowlist present); per-agent ACL channel check (`channel_id ∈ self._connector_acls[account_id]["channels"]` if account_id key present AND list non-empty); denial returns `[error] [constraint] channel_id <id> is not reachable for this agent on account <account_id>`. Module docstring updated to remove the "Channel/thread/peer ACLs are F6 territory" placeholder note.
- `the_one/tools/builtins.py:99-105` — widen signature with `connector_acls: dict[str, dict[str, list[str]]] | None = None` kwarg; thread through `extra_kwargs` at L158-162 (the existing `SendToPlatformChannelTool` special-case branch).
- `the_one/agent/factory.py:320` — extend the `BuiltinToolProvider` call site to pass `connector_acls=config.connector_acls`.
- `the_one/connectors/README.md` — update the §11-area "Outbound flow trace" quoted marker text from `# F6: AllowlistResolver consultation lands here` (or whatever leg 1a left) to a description of the actual F6 consultation now living at that site.
- `tests/test_connector_send.py` (or appropriate F4 test file) — new tests covering: permit when no allowlist + no ACL; permit when channel in account.allowlist; denial when channel not in account.allowlist; denial when channel in account.allowlist but NOT in per-agent ACL channels; permit when per-agent ACL has empty channels list (inherit); permit when account_id absent from per-agent ACL (inherit); existing F4 account-scope denial still works; KeyError on mid-call account deletion returns constraint envelope.
- Flight log gains a leg-3 entry.

## Acceptance Criteria

- [ ] `SendToPlatformChannelTool.__init__` accepts `connector_acls: dict[str, dict[str, list[str]]] | None = None` kwarg (matches `AgentConfig.connector_acls` annotation shape); stored as `self._connector_acls` (default `None` → no per-agent narrowing)
- [ ] `execute()` consultation lands at the former `# F6:` marker (line ~131); the marker comment is REMOVED and replaced with the actual consultation; the docstring "Channel/thread/peer ACLs are F6 territory" note in the module docstring (lines 11-13) is REMOVED
- [ ] Function-local imports for `ConnectorAccountRepository`, `get_connection`, `get_encryptor`, `settings` mirror the `_inbound.py:130-142` pattern with an inline load-cycle comment
- [ ] `KeyError` on `acc_repo.get(account_id)` returns `[error] [constraint] account_id <id> not found` (defensive; unreachable in the happy path because account-scope validation already rejected unknown ids)
- [ ] Account-scope channel check: if `account.config.get("allowlist") is None` → permit (default-permit on absence); if present and `channel_id` not in `allowlist["channels"]` → return `[error] [constraint] channel_id <id> is not reachable on account <account_id>`
- [ ] Per-agent ACL channel check (only runs if account-scope check passed): if `self._connector_acls is None` OR account_id key absent → permit (inherit); if account_id key present with non-empty `channels` list AND `channel_id` not in that list → return `[error] [constraint] channel_id <id> is not reachable for this agent on account <account_id>`; if `channels` list is EMPTY → inherit (no agent-level narrowing per leg-1c documented semantics)
- [ ] `BuiltinToolProvider.get_tools` accepts `connector_acls: dict[str, dict[str, list[str]]] | None = None` kwarg; threads it through `extra_kwargs` for `SendToPlatformChannelTool` only
- [ ] `AgentFactory.create` passes `connector_acls=config.connector_acls` to `BuiltinToolProvider.get_tools`
- [ ] `ToolProvider` Protocol is UNCHANGED (no widening; the existing isinstance-branch at `factory.py:314-331` continues to handle the difference)
- [ ] Existing F4 account-scope tests pass byte-identically (denial path unchanged; success path's first denial gate still works)
- [ ] F1/F2/F3/F4/F5 + leg-1a/1b/1c/2 regression suites pass byte-identically
- [ ] New tests: ≥8 cases covering the consultation matrix (permit, account-scope denial, per-agent ACL denial, inheritance edges, mid-call deletion KeyError)
- [ ] `connectors/README.md` quoted marker text reflects the actual consultation (no more "F6 territory" placeholder language)
- [ ] `ruff check` clean on modified files; full test suite passes

## Verification Steps

- `grep -n "# F6:" the_one/tools/connector_send.py` — should return NOTHING (marker replaced)
- `grep -n "AllowlistResolver" the_one/` — should return ZERO hits (leg 1a's deferred sites all closed in leg 3)
- `python -c "from the_one.tools.connector_send import SendToPlatformChannelTool; t = SendToPlatformChannelTool(connector_acls={'a': {'peers': [], 'channels': ['c1']}}); print(t._connector_acls)"` — confirms kwarg path
- `docker exec the-one pytest -x --timeout 30 tests/test_connector_send.py` (or the F4 test file) — new + existing tests pass
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_inbound.py tests/test_connectors_resolver.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_connectors_pool.py tests/test_connectors.py tests/test_db_repositories.py tests/test_db_migration.py tests/test_db_api.py` — F1-F5 + leg 1a/1b/1c/2 byte-identical
- `docker exec the-one pytest -x --timeout 30` — full suite passes

## Implementation Guidance

1. **Find the F4 test file** (`grep -rn "SendToPlatformChannelTool" tests/`) — typically `tests/test_connector_send.py` or `tests/test_tools_connector_send.py`. Use whatever file holds the F4 round-trip tests; append the new `TestF6OutboundGating` class there.

2. **Modify `the_one/tools/connector_send.py`**:
   - Module docstring (lines 11-13): replace "Channel/thread/peer ACLs are F6 territory — see the inline `# F6:` marker" with "Channel/per-agent ACLs are consulted at execute time via a per-call account fetch (M10 F6 L3); default-permit on absence."
   - `__init__` (lines 89-100): add `connector_acls: dict[str, dict[str, list[str]]] | None = None` kwarg between `connector_account_ids` and the function body; store as `self._connector_acls: dict[str, dict[str, list[str]]] | None = connector_acls`.
   - `execute()` (lines 102-153): REPLACE lines 131-134 (the `# F6:` marker comment block) with the consultation:

     ```python
     # ── Channel + per-agent ACL consultation (M10 F6 L3) ───────
     # Function-local imports — adopted defensively by symmetry with
     # connectors/_inbound.py:130-142 (the existing precedent for the
     # connectors→db boundary). A cycle is NOT observed in tools/
     # connector_send.py's current import graph; the convention is
     # adopted prophylactically because per-call account fetches will
     # multiply this module's coupling to db.repositories over time.
     from the_one.config import settings
     from the_one.db.connection import get_connection
     from the_one.db.repositories import ConnectorAccountRepository
     from the_one.encryption import get_encryptor

     conn = await get_connection()
     encryptor = get_encryptor(settings.data_dir)
     acc_repo = ConnectorAccountRepository(conn, encryptor)
     try:
         account = await acc_repo.get(account_id)
     except KeyError:
         return (
             f"[error] [constraint] account_id {account_id!r} "
             "not found"
         )

     # Account-scope channel check.
     allowlist = account.config.get("allowlist")
     if allowlist is not None:
         allowed_channels = allowlist.get("channels", [])
         if channel_id not in allowed_channels:
             return (
                 f"[error] [constraint] channel_id {channel_id!r} "
                 f"is not reachable on account {account_id!r}"
             )

     # Per-agent ACL channel check (intersected with account-scope).
     if self._connector_acls is not None:
         agent_acl = self._connector_acls.get(account_id)
         if agent_acl is not None:
             agent_channels = agent_acl.get("channels", [])
             # Empty list = inherit account-scope (no agent-level
             # narrowing). Non-empty = narrow further.
             if agent_channels and channel_id not in agent_channels:
                 return (
                     f"[error] [constraint] channel_id {channel_id!r} "
                     f"is not reachable for this agent on account "
                     f"{account_id!r}"
                 )
     ```

3. **Modify `the_one/tools/builtins.py:99-167`**:
   - Add `connector_acls: dict[str, dict[str, list[str]]] | None = None` kwarg to `get_tools` signature (sibling to `connector_account_ids` at line 105).
   - At the `SendToPlatformChannelTool` special-case branch (line 158-162), extend `extra_kwargs`:

     ```python
     extra_kwargs: dict[str, Any] = (
         {
             "connector_account_ids": connector_account_ids or [],
             "connector_acls": connector_acls,
         }
         if cls is SendToPlatformChannelTool
         else {}
     )
     ```

4. **Modify `the_one/agent/factory.py:316-321`** — extend the `BuiltinToolProvider` call site:

   ```python
   tools = provider.get_tools(
       tool_configs_by_name,
       agent_overrides,
       agent_name=name,
       connector_account_ids=config.connector_account_ids,
       connector_acls=config.connector_acls,
   )
   ```

5. **Modify `the_one/connectors/README.md`** — locate the quoted marker text (was at L363 pre-leg-1a; verify current line via grep). Replace the quoted F6 placeholder text with prose like: "F6 leg 3 replaced the marker with the actual consultation: per-call `ConnectorAccountRepository.get(account_id)` fetches the account; the tool intersects `target.channel_id` against (i) account-scope `config["allowlist"]["channels"]` (absent → permit) and (ii) per-agent `AgentConfig.connector_acls[account_id]["channels"]` (absent or empty → inherit). Denials return the standard `[error] [constraint]` envelope."

6. **Write tests** in the F4 test file. New class `TestF6OutboundGating` (or extend existing). At minimum 8 cases:
   - `test_permit_when_no_allowlist_no_acl` — both absent → success
   - `test_permit_when_channel_in_account_allowlist_no_acl` — account allowlist has channel; per-agent absent → success
   - `test_deny_when_channel_not_in_account_allowlist` — `[error] [constraint] channel_id 'X' is not reachable on account 'A'`
   - `test_deny_when_channel_in_account_but_not_in_per_agent_acl` — agent narrows further → `[error] [constraint] channel_id 'X' is not reachable for this agent on account 'A'`
   - `test_permit_when_per_agent_acl_has_empty_channels_list` — inherit (no narrowing)
   - `test_permit_when_per_agent_acl_account_id_absent` — inherit
   - `test_permit_when_channel_in_both_account_allowlist_and_per_agent_acl` — intersection-positive (both axes permit) → success. Mirror of the deny-by-intersection test but on the success path.
   - `test_keyerror_on_mid_call_account_deletion_returns_constraint` — delete account between construct and execute; expect `[error] [constraint] account_id 'A' not found`
   - `test_f4_account_scope_denial_still_works` — REGRESSION PIN, not new behavior: `account_id` not in `connector_account_ids`; existing F4 envelope `[error] [constraint] account_id 'X' is not attached to this agent` (unchanged). Worth pinning explicitly so a future leg-3 refactor doesn't silently regress F4's contract.

7. **Run verification budget** in order:
   1. `pytest tests/test_connector_send.py` (or whichever F4 file)
   2. `pytest tests/test_connectors_inbound.py tests/test_connectors_resolver.py` — leg-1a + leg-2 regression
   3. `pytest tests/test_connectors.py tests/test_connectors_e2e_session.py tests/test_connectors_session.py tests/test_connectors_pool.py` — F1/F3/F4/F5 regression
   4. `pytest tests/test_db_repositories.py tests/test_db_migration.py tests/test_db_api.py` — leg-1b + leg-1c regression
   5. `pytest` — full suite
   6. `ruff check the_one/tools/connector_send.py the_one/tools/builtins.py the_one/agent/factory.py tests/test_connector_send.py` — clean

8. **Update the flight log** with the leg-3 entry: consultation site, ToolProvider non-widening defense (cycle-2 finding #4 closure), per-call account fetch performance acceptance, README marker closure, test counts. Note the `# F6:` marker is now removed from the source code — the F6 contract lives in the module docstring + `connectors/README.md`.

9. **Set leg status to `landed`**. Do NOT commit.

## Edge Cases

- **Account deletion mid-call**: defended by the KeyError catch returning a constraint envelope. The previous-leg's pool-acquire path catches the same case differently; here we surface a constraint denial because the operator's intent ("send to this account") cannot be satisfied.
- **Account.config["allowlist"] = {"peers": [], "channels": []}** (empty-list lockdown from leg 1b): channel_id NEVER in `[]` → denial via the account-scope branch. The agent gets a constraint envelope; the operator's lockdown is enforced. Empty-channels lockdown ≠ absent — distinct semantics per leg 1b.
- **Per-agent ACL `{"peers": [], "channels": []}` (both empty)**: peers-empty is irrelevant for outbound (channel routing only); channels-empty MEANS inherit per leg 1c's documented "empty list = no narrowing" semantic. Document inline at the consultation comment.
- **`thread_id` is NOT checked by leg 3**: the flight scope is channel-level + per-agent ACL only. Thread-level ACLs are an F7 enhancement, NOT this leg. The tool's `thread_id` field is passed through to the pool unchanged.
- **`connector_acls={"acct-a": {}}`** (per-agent entry with missing inner keys): the validator at leg 1c rejects this at construction time (`_validate_connector_acls` requires exact-keys `{"peers", "channels"}`). The dispatcher reads validated dicts; this case is unreachable. Defensive: `agent_acl.get("channels", [])` returns `[]` if somehow the validation didn't run; an empty channels list collapses to the documented "inherit account-scope" semantic — the conservative default, not a fail-open exception.
- **Stale account state**: per-call fetch ensures the dispatcher reads CURRENT account state. If the operator removes a channel from the allowlist mid-session, the next send is gated by the new state. Documented in the flight Design Decision; this is the EXPECTED behavior (cf. flight Design Decision rationale "Stale-snapshot risk avoided by reading account state at send time").
- **Concurrent agent.step calls invoking the tool**: each call independently fetches the account. SQLite read concurrency is fine. The per-account write path (leg 2's pairing flow) and the per-account read path (leg 3 outbound) don't interfere; the read sees whatever's committed.
- **F4 success-path string format**: unchanged. PLATFORM_SEND_OK_PREFIX + the existing `(msg_id=...)` envelope is preserved. Leg 3 only adds an EARLY-RETURN denial path before pool_acquire.

## Files Affected

- `the_one/tools/connector_send.py` — module docstring + `__init__` kwarg + `execute()` consultation replacement (~50 added lines, ~5 removed lines)
- `the_one/tools/builtins.py` — `get_tools` signature widened + `extra_kwargs` thread-through (~5 lines)
- `the_one/agent/factory.py` — 1 kwarg added to `provider.get_tools` call (1 line)
- `the_one/connectors/README.md` — update quoted marker prose (~5 lines)
- `tests/test_connector_send.py` (or F4 file) — new `TestF6OutboundGating` class with ≥8 tests (~200 lines)
- `the_one/connectors/base.py` — UNCHANGED
- `the_one/connectors/_stub.py` — UNCHANGED
- `the_one/connectors/_inbound.py` — UNCHANGED
- `the_one/db/models.py` — UNCHANGED
- `the_one/db/repositories.py` — UNCHANGED (consumes existing `ConnectorAccountRepository.get`)
- `the_one/agent/config.py` — UNCHANGED (consumes existing `connector_acls` field)
- The flight log gains a leg-3 entry

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT modify flight.md
- [ ] Do NOT commit (deferred-batched workflow)

## Citation Audit

Citations verified at design time:
- `the_one/tools/connector_send.py:11-13` — confirmed (module docstring placeholder note)
- `the_one/tools/connector_send.py:89-100` — confirmed (`__init__`)
- `the_one/tools/connector_send.py:106-129` — confirmed (target shape + account-scope validation)
- `the_one/tools/connector_send.py:131-134` — confirmed (`# F6:` marker comment block)
- `the_one/tools/builtins.py:99-167` — confirmed (`BuiltinToolProvider.get_tools` widened path)
- `the_one/agent/factory.py:316-321` — confirmed (`BuiltinToolProvider` call site)
- `the_one/agent/config.py:connector_acls` — confirmed (leg 1c's field)
- `the_one/connectors/_inbound.py:130-142` — confirmed (function-local-import precedent)
- `the_one/db/models.py:ConnectorAccount.config["allowlist"]` — confirmed (leg 1b's shape)

All citations verified clean.
