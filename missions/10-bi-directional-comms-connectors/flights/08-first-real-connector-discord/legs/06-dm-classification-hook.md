# Leg: dm-classification-hook

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Implement `DiscordPlugin.is_dm(envelope) -> bool` returning `envelope.raw["is_dm"]` (the value L4's translate helper already populates based on `discord.ChannelType.private`). Add the `getattr`-sentinel consult at `_acl.py:95, 171` (the DMs-only fail-closed branches) so the deny becomes "permit if is_dm; else deny." Thread the `is_dm` bool through `admits_inbound` and `admits_outbound` via a new optional `is_dm: bool = False` keyword (additive; back-compat preserved). Inbound callers compute the bool at the consult site (`_routing._agent_admits`) via `getattr(plugin, "is_dm", _default_not_dm)(envelope)`; outbound callers default to `False` until F10 hardening adds a plugin-level outbound DM determination.

## Context

L6 of F8. Per flight Design Decisions:

- **`is_dm` hook via `getattr` sentinel** — mirrors F6's `resolve` hook discovery pattern. Plugins opt in by exposing the method; the default (no plugin or no method) is `False` matching today's F7 behavior (all stub envelopes are treated as non-DM).
- **`_default_not_dm(envelope) -> bool` returns False** — back-compat: stub envelopes (and any other plugins that don't implement `is_dm`) continue to fail the DMs-only check.
- **F4 outbound path doesn't have envelope context** — the F4 platform-send tool is called by the agent with `target=(channel_id, thread_id)`. There's no inbound envelope at outbound time. For L6, outbound passes `is_dm=False` (preserves the existing deny); F10 hardening can add a plugin-level "is_dm(target)" determination if HAT surfaces the need.
- **Threading the bool through `_acl`** rather than passing plugin+envelope keeps `_acl` pure-functional (no I/O, no SDK reach); the consult site (one caller for inbound: `_routing._agent_admits`) does the `getattr` lookup and passes the resolved bool. This matches the `verbatim-message-equality`-style boundary discipline.

Key learnings from L1-L5:
- L4 already populates `envelope.raw["is_dm"]` for Discord — `_translate_discord_message_to_envelope` sets it based on `message.channel.type == discord.ChannelType.private`.
- The stub plugin does NOT implement `is_dm` — back-compat means stub envelopes still fail the DMs-only check (existing tests pass byte-identically).
- The DMs-only fail-closed branches at `_acl.py:95` (outbound) and `_acl.py:171` (inbound) carry the F8 marker comments.

## Inputs

- `the_one/connectors/_discord.py` (post-L5) — `DiscordPlugin` has 4 implemented methods (`connect`, `disconnect`, `normalize_session_key`) and `doctor` still raising `NotImplementedError`. No `is_dm` yet.
- `the_one/connectors/_acl.py:64-108` — `admits_outbound(account, agent_acl, channel_id) -> (bool, str)` with the F8 marker comment at line 95 (outbound DMs-only fail-closed).
- `the_one/connectors/_acl.py:111-184` — `admits_inbound(account, agent_acl, peer_id, channel_id) -> (bool, str)` with the F8 marker comment at line 171 (inbound DMs-only fail-closed).
- `the_one/connectors/_routing.py:141-158` — `_agent_admits(account, agent_config, envelope) -> bool` is the inbound consult caller; has access to `envelope` AND can resolve the plugin via `resolve_plugin(account.type)`.
- `the_one/tools/connector_send.py:179` — outbound caller; has `account, agent_acl, channel_id`. Does NOT have envelope context.
- L1-L5 test suite green (2322 passed).

## Outputs

- `DiscordPlugin.is_dm(envelope) -> bool` in `the_one/connectors/_discord.py`:
  ```python
  def is_dm(self, envelope: InboundEnvelope) -> bool:
      """Return True if the envelope represents a Discord DM."""
      return bool(envelope.raw.get("is_dm", False))
  ```
  - Sync function (mirrors `normalize_session_key`'s signature).
  - Defensive: `.get("is_dm", False)` handles malformed raw dicts.

- `the_one/connectors/_acl.py`:
  - Adds module-level `def _default_not_dm(envelope: InboundEnvelope) -> bool: return False` (the sentinel default callable matching `getattr(plugin, "is_dm", _default_not_dm)` resolution).
  - `admits_outbound(account, agent_acl, channel_id, *, is_dm: bool = False) -> (bool, str)`:
    - At line 95's DMs-only branch (`agent_channels == []`): if `is_dm`, return `(True, "")` (permit); else return the existing deny (with updated reason text dropping the "DM classification lands in F8" forward-reference).
  - `admits_inbound(account, agent_acl, peer_id, channel_id, *, is_dm: bool = False) -> (bool, str)`:
    - At line 171's DMs-only branch: same pattern — if `is_dm`, permit; else deny.

- `the_one/connectors/_routing.py:_agent_admits`:
  - Resolves `is_dm` via `getattr(plugin, "is_dm", _default_not_dm)(envelope)` where `plugin` is the resolved `ConnectorPlugin` instance (already in scope via `_resolve_plugin(account.type)`).
  - Passes `is_dm=is_dm_value` into `admits_inbound`.
  - The `_default_not_dm` import comes from `_acl` (re-exported via `__all__` or imported directly).

- `the_one/tools/connector_send.py:179` — `admits_outbound` call site passes the default (`is_dm=False`) explicitly OR omits the kwarg (default preserved). Behavior identical to today.

- `tests/test_connectors_discord.py` — add `is_dm` tests:
  - `DiscordPlugin().is_dm(envelope_with_raw_is_dm_true)` returns True.
  - `DiscordPlugin().is_dm(envelope_with_raw_is_dm_false)` returns False.
  - `DiscordPlugin().is_dm(envelope_with_raw_missing_is_dm_key)` returns False (defensive).

- `tests/test_connectors_acl.py` (or equivalent) — extended with DMs-only-with-is_dm tests:
  - `admits_outbound(account_with_dms_only_agent_channels, is_dm=True)` → permits.
  - `admits_outbound(account_with_dms_only_agent_channels, is_dm=False)` → denies (existing behavior).
  - `admits_inbound(account_with_dms_only_agent_channels, is_dm=True)` → permits.
  - `admits_inbound(account_with_dms_only_agent_channels, is_dm=False)` → denies.

- `tests/test_connectors_routing.py` (or equivalent) — `_agent_admits` test:
  - With a plugin that implements `is_dm` returning True on a DM envelope: `_agent_admits` permits even with `agent_channels = []`.
  - With the stub plugin (no `is_dm` method): `_agent_admits` denies on `agent_channels = []` (existing F7 behavior preserved).

- `the_one/agents.md` Connector subsystem section: update the `optional-plugin-hook-via-getattr-sentinel` convention citation to add `is_dm` as a third occurrence (alongside `display_channel` and F6's `resolve`).

- L1-L5 regression: 2322 → ~2330 (~8 new tests).

## Acceptance Criteria

- [x] **`DiscordPlugin.is_dm(envelope) -> bool`** implemented in `_discord.py`. Sync. Returns `bool(envelope.raw.get("is_dm", False))`. Three tests pin: raw["is_dm"]=True→True, raw["is_dm"]=False→False, raw missing key→False.

- [x] **`_default_not_dm` sentinel added to `_acl.py`** as a module-level callable: `def _default_not_dm(envelope: InboundEnvelope) -> bool: return False`. Exported via `__all__` (alongside `admits_outbound` and `admits_inbound`).

- [x] **`admits_outbound` signature extended** with `is_dm: bool = False` keyword-only argument. At line 95's DMs-only branch: if `is_dm`, return `(True, "")`; else preserve current deny (update reason text to drop the "DM classification lands in F8" forward-reference — say "(DMs-only override; sender's message is not a DM)" or similar).

- [x] **`admits_inbound` signature extended** with `is_dm: bool = False` keyword-only argument. At line 171's DMs-only branch: same is_dm-or-deny pattern.

- [x] **`_routing._agent_admits` updated** to resolve `is_dm` via the plugin and pass it through:
  ```python
  is_dm_value = getattr(plugin, "is_dm", _default_not_dm)(envelope)
  admits, _reason = admits_inbound(account, agent_acl, envelope.peer_id, envelope.channel_id, is_dm=is_dm_value)
  ```
  Where `plugin` is resolved via `_resolve_plugin(account.type)` (the existing F7 pattern). If `_agent_admits` doesn't already have access to the plugin, extend its signature to receive it from the caller (`resolve_routing`).

- [x] **`tests/test_connectors_discord.py` extended** with 3 `is_dm` tests.

- [x] **`tests/test_connectors_acl.py` (or wherever `admits_outbound`/`admits_inbound` tests live) extended** with 4 DMs-only-with-is_dm permit/deny tests (2 outbound + 2 inbound).

- [x] **`tests/test_connectors_routing.py` (or equivalent) extended** with at least 2 `_agent_admits` tests: plugin-with-is_dm-implemented (permits DM); stub-without-is_dm (denies — back-compat).

- [x] **F1-F7 + L1-L5 regression**: 2322 → ~2330. Specifically: all existing F7 dispatcher tests that use the stub plugin's `admits_*` paths pass byte-identically (the stub doesn't implement `is_dm`, so `_default_not_dm` returns False, so the existing fail-closed behavior is preserved verbatim). Actual: 2331.

- [x] **`agents.md` Connector subsystem section** — extend the `optional-plugin-hook-via-getattr-sentinel` convention citation to add `is_dm` as a third occurrence.

## Verification Steps

- `grep -c "def is_dm" the_one/connectors/_discord.py` — exactly 1.
- `grep -c "_default_not_dm" the_one/connectors/_acl.py` — at least 1 (declaration) plus an export entry.
- `grep -c "is_dm=" the_one/connectors/_acl.py` — at least 2 (the two consult sites in admits_inbound and admits_outbound).
- `grep -c "F8: DM classification lands here" the_one/connectors/_acl.py` — 0 (markers replaced).
- `docker exec the-one pytest tests/ -x --timeout 30` — full suite passes.

## Implementation Guidance

1. Add `DiscordPlugin.is_dm` to `_discord.py` (simple).
2. Add `_default_not_dm` to `_acl.py` + extend `__all__`.
3. Extend `admits_outbound` and `admits_inbound` signatures with `is_dm` kwarg + flip the DMs-only branches.
4. Update `_routing._agent_admits` to resolve the plugin and pass `is_dm` through. If `_agent_admits` doesn't already have the plugin, extend its signature; the caller (`resolve_routing`) has the plugin available via the F7 dispatcher's `_resolve_plugin(account.type)` call.
5. Tests: extend test_connectors_discord.py, test_connectors_acl.py, test_connectors_routing.py with the new cases.
6. Update agents.md.
7. Full suite green.

### Code patterns to follow

- **`getattr` sentinel** — F6's `getattr(plugin, "resolve", _default_permit)` at `_routing.py:_resolve_for_dispatch` is the precedent. Same shape applies for `is_dm`.
- **Back-compat preservation** — the stub plugin doesn't implement `is_dm`, so `_default_not_dm` fires, returning False; the existing fail-closed behavior is preserved verbatim.

## Edge Cases

- **`envelope.raw["is_dm"]` is not a bool** (e.g. a string from a misbehaving plugin): `bool(...)` coerces. "False"/"True" strings become True (truthy), but in practice only DiscordPlugin sets this and we control the value.
- **Plugin's `is_dm` raises**: the `getattr` consult doesn't wrap in try/except. An exception propagates. Defer try/except wrapping to F10 hardening if HAT surfaces flaky `is_dm` implementations.
- **`_agent_admits` gets a None plugin** (shouldn't happen — `_resolve_plugin` raises if unknown): defensive — if plugin is None, fall back to `_default_not_dm`.

## Files Affected

- `the_one/connectors/_discord.py` — `DiscordPlugin.is_dm` method body
- `the_one/connectors/_acl.py` — `_default_not_dm` sentinel + signature extensions + DMs-only branch flip
- `the_one/connectors/_routing.py` — `_agent_admits` updated to resolve plugin and pass `is_dm` through
- `the_one/agents.md` — `optional-plugin-hook-via-getattr-sentinel` convention update
- `tests/test_connectors_discord.py` — `is_dm` tests (3+)
- `tests/test_connectors_acl.py` — DMs-only-with-is_dm tests (4+)
- `tests/test_connectors_routing.py` — `_agent_admits` tests (2+)

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set leg status to `landed`
- [x] Check off L6 in flight.md
- [x] Do NOT commit — wait for flight-level review

## Citation Audit

- `the_one/connectors/_acl.py:64-108` — admits_outbound — **OK**
- `the_one/connectors/_acl.py:95` — F8 marker (outbound DMs-only) — **OK**
- `the_one/connectors/_acl.py:111-184` — admits_inbound — **OK**
- `the_one/connectors/_acl.py:171` — F8 marker (inbound DMs-only) — **OK**
- `the_one/connectors/_routing.py:141-158` — `_agent_admits` — **OK**
- `the_one/tools/connector_send.py:179` — outbound caller — **OK**

6 citations verified.
