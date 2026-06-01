# Leg: bug-d-fix-permitted-agents-threads-envelope-context

**Status**: completed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

## Objective

Fix Bug D: `_commands.py:_permitted_agents` calls `admits_inbound` with only `(account, agent_acl, peer_id, channel_id)` — omitting the `is_dm`/`guild_id`/`member_roles` kwargs that the post-F12 structured-tuple allowlist requires — so all six slash commands' eligibility filter wrongly denies under a real Discord guild; thread the full envelope context into the call so the command-handler's secondary admission matches the dispatcher's primary path.

## Context

- **Design decision (flight)**: L1 lands BEFORE L8 (AdmissionContext refactor) so the refactor migrates an already-correct call site rather than threading two changes through `_commands.py:108` in opposite directions.
- **Bug D lineage** (M11 Known Issues + F14 recon): broken since F7 (commit `dfff8ac`, 2026-05-19); latent until F12's structured-tuple `allowlist.channels` made `guild_id` load-bearing for the channel-match path. The dispatcher's primary admission at `_routing.py:_agent_admits` (`:165-189`) DOES pass all five pieces; the command-handler's secondary re-check at `_commands.py:_permitted_agents` (`:108`) does not. All six platform-side slash commands (`/agents`, `/talk_to`, `/whoami`, `/new`, `/reset`, `/help`) route their eligibility filter through `_permitted_agents`, so the omission breaks the ACL gate for every one of them.
- **Reference call site**: `_routing.py:165-189` is the canonical derivation. It resolves `is_dm` via the `optional-plugin-hook-via-getattr-sentinel` pattern (`getattr(plugin, "is_dm", _default_not_dm)(envelope)`), and reads `guild_id` / `member_roles` directly from `envelope.raw` (the latter defaulting to `[]`).
- **Recon correction to the flight spec's ~8-line estimate**: the flight's L1 sketch offered "import `_default_not_dm` directly into `_commands.py`" as option (a). Recon found `DiscordPlugin.is_dm` is a real override at `_discord.py:1598` (returns `bool(envelope.raw.get("is_dm", False))` for Discord). Hardcoding `_default_not_dm` (which always returns `False`) would deny slash commands invoked in Discord **DMs** under a channels-restricted account — re-introducing the exact ACL DM-admission failure mode this mission already fixed at F10/F12. The leg therefore takes option (b): a shared `is_dm` derivation helper that honors the plugin hook, plus threading `plugin` into the command context. This keeps the command path byte-for-byte aligned with the routing path.

## Inputs

- `the_one/connectors/_commands.py` — `_permitted_agents` at `:87-113`; the dispatch context it consumes (`account`, `envelope`, `eligible_attached_agents`) does NOT currently carry `plugin`.
- `the_one/connectors/_inbound.py` — `dispatch_inbound` builds the command `context` dict at `:650-657` (no `plugin` key); `plugin: ConnectorPlugin` is in scope as a function param (`:174`).
- `the_one/connectors/_routing.py:165-189` — `_agent_admits`, the reference derivation.
- `the_one/connectors/_acl.py` — `admits_inbound` at `:297`; `_default_not_dm` at `:85`; `__all__` at `:76`.
- `the_one/connectors/_discord.py:1598` — `DiscordPlugin.is_dm` override (confirms the hook is live for Discord).

## Outputs

- `_permitted_agents` calls `admits_inbound` with all five pieces of context (`peer_id`, `channel_id`, `is_dm`, `guild_id`, `member_roles`), derived identically to `_routing.py:_agent_admits`.
- A shared `is_dm` derivation helper in `_acl.py` consumed by BOTH `_routing.py` and `_commands.py` (no duplicated `getattr(plugin, "is_dm", ...)` logic).
- `plugin` threaded into the command `context` dict at `_inbound.py`.
- 2 new regression tests under `TestPermittedAgentsAgainstStructuredAllowlist`.

## Acceptance Criteria

- [ ] `_permitted_agents` passes `is_dm`, `guild_id`, and `member_roles` to `admits_inbound` — `is_dm` via the plugin hook (NOT a hardcoded `_default_not_dm`), `guild_id` via `envelope.raw.get("guild_id")`, `member_roles` via `envelope.raw.get("member_roles", [])`.
- [ ] The `is_dm` derivation is factored into a single shared helper (in `_acl.py`, beside `_default_not_dm`) used by both `_routing.py:_agent_admits` and `_commands.py:_permitted_agents`; the duplicated `getattr` expression no longer appears at two sites.
- [ ] The command `context` dict built in `dispatch_inbound` carries `plugin` so `_permitted_agents` can resolve the hook.
- [ ] `tests/test_connectors_commands.py` gains a `TestPermittedAgentsAgainstStructuredAllowlist` class with 2 tests: (a) `_handle_agents` returns the agent when the connector's structured-tuple `allowlist.channels` matches the envelope's `guild_id` + `channel_id`; (b) `_handle_agents` returns "No agents available for this conversation." when `guild_id` is absent or doesn't match the structured-tuple entry.
- [ ] Backend suite: **2798** passed / 4 skipped / 0 errors (baseline 2796 + 2).
- [ ] `git grep -nE 'admits_inbound\(' the_one/connectors/_commands.py` shows the call site passing all five required pieces of context.

## Verification Steps

- `docker exec the-one pytest tests/test_connectors_commands.py -x --timeout 30 -q` — new class passes.
- `docker exec the-one pytest -x --timeout 30 -q` — full suite at 2798 / 0 errors (run once at leg-end).
- `git grep -nE 'admits_inbound\(' the_one/connectors/_commands.py` — call site shows the threaded context.
- Manual read: confirm the `is_dm` helper is defined once and imported at both `_routing.py` and `_commands.py`.

## Implementation Guidance

1. **Extract a shared `is_dm` derivation helper in `_acl.py`.**
   - Add a module-level helper (e.g. `def envelope_is_dm(envelope: InboundEnvelope, plugin) -> bool:`) that returns `getattr(plugin, "is_dm", _default_not_dm)(envelope)` when `plugin is not None`, else `_default_not_dm(envelope)` (preserving `_routing.py:168-171`'s `plugin is None` defensive fallback).
   - Add it to `__all__` if other modules import from `_acl`'s public surface (match the existing convention there).
   - Keep `_default_not_dm` as-is (it remains the getattr sentinel).

2. **Migrate `_routing.py:_agent_admits` to the shared helper.**
   - Replace the inline `if plugin is None: ... else: getattr(...)` block (`:168-171`) with a call to the new helper. Behavior must be identical — verify the existing routing tests still pass unchanged.

3. **Thread `plugin` into the command context.**
   - In `dispatch_inbound` (`_inbound.py:650-657`), add `"plugin": plugin` to the `context` dict (the dispatcher always resolves `plugin` at `:347`, so production always supplies it).

4. **Fix `_permitted_agents` to thread the full context.**
   - Read `plugin = context["plugin"]`, derive `is_dm` via the shared helper, read `guild_id = envelope.raw.get("guild_id")` and `member_roles = envelope.raw.get("member_roles", [])`, and pass all three as kwargs to `admits_inbound` alongside the existing `peer_id`/`channel_id`.
   - Update `_permitted_agents`'s docstring to note it now consumes `context["plugin"]`.

5. **Update the shared test-context builder so existing tests don't `KeyError`** *(design-review high-severity catch)*.
   - `tests/test_connectors_commands.py`'s `_build_context` helper (around `:293-313`) builds the context dict with NO `plugin` key; it's used at 25+ call sites across `TestPermittedAgents` / `TestHandleAgents`. Adding a bare `context["plugin"]` read in production would break ALL of them.
   - Add `"plugin": None` to `_build_context`'s dict. `plugin=None` flows through the shared helper to `_default_not_dm` → `is_dm=False`, which is correct for the existing non-DM channel-scoped tests. (Keep the production read as `context["plugin"]`, not `.get(...)` — the dispatcher contract always supplies it; the test builder now matches that contract.)

6. **Add regression tests.**
   - New class `TestPermittedAgentsAgainstStructuredAllowlist` in `tests/test_connectors_commands.py`. Build a `Connector` whose `allowlist.channels` holds a v24 structured-tuple entry `{guild_id, channel_id}` (reuse `DEFAULT_TEST_GUILD_ID` + the tuple form from `tests/_acl_shape_helpers.py`, F13 L1). The envelope's `raw` must carry the matching `guild_id` — the existing `_envelope`/`_build_context` helpers default `raw={}`, so the test overrides `raw` to include `guild_id`. Pass a local stub plugin whose `is_dm` returns `False` (the file's existing stub patterns test hook *absence*; this needs a stub that *implements* `is_dm`). Test (a): matching `guild_id` + `channel_id` → `_handle_agents` lists the agent. Test (b): absent/mismatched `guild_id` → "No agents available for this conversation."

## Edge Cases

- **DM-invoked slash command**: `is_dm=True` must flow through so a DM peer on a channels-restricted account isn't wrongly denied. The plugin-hook derivation (not `_default_not_dm`) is what makes this correct — this is the whole reason for option (b).
- **`plugin is None`** (test stub / pre-F8 plugin): the shared helper falls back to `_default_not_dm` → `is_dm=False`, preserving fail-closed behavior. Ensure the new context always carries `plugin` (the dispatcher always resolves it at `_inbound.py:347`).
- **`member_roles` absent in `raw`** (pre-F8-L4 envelope): default `[]` — same pattern as `_routing.py:179`.
- **Test-construction path**: the shared `_build_context` test helper must carry `plugin` (set to `None`) so the production `context["plugin"]` read doesn't `KeyError` across the existing command tests (see step 5).

## Note for L8

The `envelope_is_dm` helper this leg introduces is the natural home for L8's `AdmissionContext.from_envelope` `is_dm` derivation — L8 reuses it rather than re-deriving. L1 leaving `plugin` in the command context dict gives L8's `from_envelope` a clean source. (Also: flight.md:96 mis-describes `_default_not_dm` as returning `not envelope.raw.get("is_dm", False)`; the real function at `_acl.py:85` returns a plain `False`. Recorded in the flight-log so L8's author isn't misled.)

## Files Affected

- `the_one/connectors/_acl.py` — new shared `is_dm` derivation helper (+ `__all__`).
- `the_one/connectors/_routing.py` — `_agent_admits` uses the shared helper.
- `the_one/connectors/_inbound.py` — `plugin` added to command `context` dict.
- `the_one/connectors/_commands.py` — `_permitted_agents` threads full context; docstring update.
- `tests/test_connectors_commands.py` — `TestPermittedAgentsAgainstStructuredAllowlist` (+2 tests).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — except commit, which is deferred to Phase 2d per agentic-workflow batch protocol:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (2798)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (NOT `completed` — commit is batched at Phase 2d)
- [ ] Do NOT check off this leg in flight.md yet (done at Phase 2d commit)
- [ ] Do NOT commit (batched at Phase 2d)
