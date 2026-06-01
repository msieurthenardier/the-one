# Leg: bug-f-slash-sync-copy-global-to-guild

**Status**: landed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

> **Discovered at L10 HAT (not in the original 4-bug cluster).** The L10 slash HAT surfaced — and a diagnostic confirmed — the TRUE root cause that slash commands have NEVER registered in this deployment (Discord: "This application has no commands"; autocomplete empty across F8→F13→F14, masked because all prior HATs used the text-prefix path). This is the actual blocker for M11 criterion #10. Added as a new leg per the agentic-workflow inline-HAT-fix path (diagnose → fix → re-verify).

## Objective

Fix `_sync_slash_commands` so the bot's 6 slash commands actually register per-guild: call `tree.copy_global_to(guild=guild_obj)` before `tree.sync(guild=guild_obj)`. The commands are *defined* in discord.py's GLOBAL registry (`tree.command(...)` with no `guild=`) but *synced* against the per-guild registry (empty) — so `tree.sync(guild=...)` PUTs zero commands. Copying global→guild before the per-guild sync registers all six.

## Context

- **Diagnostic evidence (L10)**: a standalone in-container script using the app's repo + encryptor loaded the Discord connector (`58f1fe5a833f`, "Discord Constellation"), confirmed `config.allowlist.guilds == ['1447766672441348150']` (L2 read correct), decrypted the token, logged in, and called `tree.sync(guild=Object(id=1447766672441348150))` on a global-only tree → **returned 0 commands, no exception** (the empty per-guild bucket). Adding `tree.copy_global_to(guild=...)` first → **all 6 commands registered** (verified live via `GET /applications/{app}/guilds/{guild}/commands`). The `applications.commands` scope works; the guild-read works; the ONLY defect is the global-vs-guild registry mismatch.
- **discord.py model**: `CommandTree` has two registries — global and per-guild. `tree.command(...)` without `guild=` registers globally. `tree.sync(guild=g)` PUTs only the per-guild bucket for `g`. `tree.copy_global_to(guild=g)` copies the current global commands into `g`'s bucket so the subsequent per-guild sync includes them. This preserves the existing per-guild-sync design (fast propagation, F8 L9 rationale) — commands stay globally defined, copied per configured guild, synced per guild.
- **Pre-existing since F8 L9** — not introduced by F14. F14's L2 (guilds-read unification) is correct and necessary but insufficient on its own; this leg is the missing piece that makes slash registration actually work, unblocking criterion #10.
- **Site**: `_sync_slash_commands` in `the_one/connectors/_discord.py` (~`:251-270`), the per-guild sync loop.

## Inputs

- `the_one/connectors/_discord.py` — `_sync_slash_commands` (~`:236-270`); the command-registration loop at `:1064-1067` (`tree.command(...)`, global) + the post-READY call at `:1147`.
- `tests/test_connectors_discord.py` — existing `_sync_slash_commands` tests (`test_connect_syncs_once_per_configured_guild` etc., post-L2 using `allowlist.guilds`). These mock `tree.sync` and assert it's called per guild — they did NOT catch this bug because they don't exercise the global-vs-guild registry distinction.

## Outputs

- `_sync_slash_commands` calls `tree.copy_global_to(guild=guild_obj)` before `await tree.sync(guild=guild_obj)` for each configured guild.
- A regression test that WOULD have caught this — asserting the global-defined commands reach the guild sync (e.g. `copy_global_to` is invoked per guild, or the guild bucket is non-empty at sync time).

## Acceptance Criteria

- [ ] `_sync_slash_commands` copies global commands into each configured guild's bucket (`tree.copy_global_to(guild=guild_obj)`) immediately before `await tree.sync(guild=guild_obj)`. The doc-comment notes WHY (global-defined commands must be copied to the per-guild bucket the sync targets).
- [ ] A regression test in `tests/test_connectors_discord.py` pins the fix: with the global-only command definitions, the sync path must result in the guild receiving the commands (assert `copy_global_to(guild=...)` is called per configured guild, OR — stronger — using a real `CommandTree` with the 6 commands added globally, assert the per-guild bucket is non-empty after the copy). The test must FAIL against the pre-fix code (global-only → empty guild sync).
- [ ] Existing `_sync_slash_commands` tests still pass (the per-guild `tree.sync` call + the empty-guilds-skip behavior are unchanged).
- [ ] Full backend suite green / 0 errors (record the count; expect prior 2811 + the new test).
- [ ] (Verified at re-HAT, not in this leg) after a container restart with the fix, Discord autocomplete shows the 6 commands + Server Settings → Integrations lists them.

## Verification Steps

- `docker exec the-one bash /app/scripts/run-tests.sh tests/test_connectors_discord.py -x --timeout 30 -q` — new + existing sync tests pass.
- `docker exec the-one bash /app/scripts/run-tests.sh -m 'not browser and not live and not pixel' -q` — full backend green (leg-end).
- `git grep -n "copy_global_to" the_one/connectors/_discord.py` — the fix is present in the sync loop.
- (Post-restart, at re-HAT) the 6 commands appear in the channel's `/` autocomplete and persist across restart.

## Implementation Guidance

1. **Add the copy in the sync loop** (`_sync_slash_commands`, ~`:256-270`): inside `for guild_id in guild_ids_raw:`, build `guild_obj = discord.Object(id=int(guild_id))` once, then `tree.copy_global_to(guild=guild_obj)` BEFORE `await tree.sync(guild=guild_obj)`. Keep the existing per-guild error handling (Forbidden/HTTP → WARNING + continue) wrapping both calls. Update the docstring/comment to explain the global→guild copy.
2. **Regression test**: the cleanest is a real-`CommandTree` test — construct a `discord.app_commands.CommandTree` on a stub/mock client, add a couple commands globally (mirroring `:1064-1067`'s `tree.command(...)` with no guild=), then drive `_sync_slash_commands` (or its copy+sync sequence) with a mock `tree.sync` that records the guild bucket size, and assert the guild received the commands. If `tree.sync` must be mocked, assert `copy_global_to` was called with the right guild before sync (a `MagicMock` tree recording call order). Ensure the test would FAIL without the `copy_global_to` line. Reuse the existing test scaffolding (`_StubCommandTree` if present, or the connect-test fakes).
3. **Run via the bounded wrapper**; record counts.

## Edge Cases

- **Multiple guilds**: `copy_global_to` must be called per guild inside the loop (each guild bucket needs the copy). Confirm the loop does it per-iteration.
- **Empty guilds list**: unchanged — the existing `if not guild_ids_raw: ... skipping; return` short-circuits before the loop (no copy needed).
- **`copy_global_to` idempotency**: it overwrites the guild bucket with the current global set each call — fine for the PUT-style per-guild sync (idempotent on reconnect).
- **Global commands left registered globally too**: `copy_global_to` does NOT clear the global registry. Since the connect path never calls a global `tree.sync()` (only per-guild), no global commands are pushed to Discord — so there's no global/guild duplication in the client. (If a future flight wants global registration, that's separate.)

## Files Affected

- `the_one/connectors/_discord.py` — `copy_global_to` in `_sync_slash_commands`.
- `tests/test_connectors_discord.py` — regression test for the global→guild copy.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — commit handled by the FD at the L10 re-HAT close:**

- [ ] `copy_global_to` fix in place; regression test added that fails pre-fix; existing sync tests pass
- [ ] Full backend green (count recorded)
- [ ] Update flight-log.md with an L11/Bug F leg-progress entry (root cause + fix + test)
- [ ] Set this leg's status to `landed`
- [ ] Do NOT commit yet (FD commits at the L10 re-HAT close, after restart + re-verify)
