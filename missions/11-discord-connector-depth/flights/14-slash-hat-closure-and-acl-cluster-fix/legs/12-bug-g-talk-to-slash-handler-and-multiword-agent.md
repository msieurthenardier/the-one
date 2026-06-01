# Leg: bug-g-talk-to-slash-handler-and-multiword-agent

**Status**: landed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

> **Discovered at L10 re-run #2 — the last criterion-#10 blocker.** After Bug F (L11) fixed slash registration, the HAT re-run scored 6/7: `/whoami`/`/agents`/`/help` ephemeral ✅, `/new`/`/reset` channel-visible ✅, but `/talk_to` failed — its deferred "thinking…" ack never resolved to a routing confirmation. Two `/talk_to`-specific defects (both pre-flagged: the talk_to/talk-to split at the L7 design review; the multi-word truncation at L10 run #1) cause it. Added per the agentic-workflow inline-HAT-fix path.

## Objective

Make `/talk_to <agent>` work end-to-end as a real Discord slash command: (1) the slash name `talk_to` (underscore) must reach the `talk-to` (hyphen) handler instead of falling through to the agent; (2) a multi-word agent name (e.g. "Sonos Agent") must be passed whole, not truncated to the first token.

## Context

- **Bug G.1 — handler-key mismatch (the "stuck thinking" cause)**: Discord application-command names cannot contain hyphens, so the slash command is registered as `talk_to` (underscore) (`_SLASH_COMMAND_VOCAB`). The slash body synthesizes envelope text `/talk_to <args>` and re-parses it; `_parse_command` yields `command_name="talk_to"` (underscore). But `_HANDLERS` (`_commands.py:242-249`) keys on `"talk-to"` (hyphen). `_dispatch_builtin_command` does `handler = _HANDLERS.get("talk_to")` → `None` → falls through to `agent.step` (the agent then "responds" to the literal text "Sonos Agent", hence the never-resolving "thinking…"). The other 5 commands' slash names match their handler keys, so only `talk_to` is affected. (The L7 design review flagged this exact talk_to/talk-to coupling.)
- **Bug G.2 — multi-word agent name truncation**: `_handle_talk_to` (`_commands.py:151+`) sets `target = args[0]` — only the first whitespace token. The agent is named "Sonos Agent" (with a space). Whether via slash (Discord passes `args="Sonos Agent"` as one string, but the synthesized-text re-parse splits it) or text-prefix, `target` becomes "Sonos" → "No such agent or you don't have permission: Sonos". The v1 grammar is `/talk-to <agent-slug>` where the slug is the rest of the line, so the full argument string is the agent name.
- **Both confirmed live at L10**: run #1 showed the truncation ("Sonos"); run #2 showed the handler-miss (fall-through to agent). Fixing both makes `/talk_to Sonos Agent` reply "Now routing your messages to Sonos Agent." (channel-visible) and actually set the routing override.

## Inputs

- `the_one/connectors/_commands.py` — `_dispatch_builtin_command` (`:252-292`, the `_HANDLERS.get(command_name)` lookup at `:288`); `_HANDLERS` (`:242-249`, key `"talk-to"`); `_handle_talk_to` (`:151-182`, `target = args[0]`).
- `tests/test_connectors_commands.py` — existing command tests + `_build_context` helper (carries `plugin` per L1).

## Outputs

- Command-name normalization so `talk_to` (underscore) resolves to the `talk-to` handler.
- `_handle_talk_to` uses the full joined argument as the agent name.
- Regression tests for both.

## Acceptance Criteria

- [x] `_dispatch_builtin_command` resolves the slash underscore form to the hyphen handler — e.g. `handler = _HANDLERS.get(command_name) or _HANDLERS.get(command_name.replace("_", "-"))` (try exact first, then underscore→hyphen). A comment explains WHY (Discord slash names use underscores; the v1 vocab uses hyphens). Unknown commands still return `None` (fall through). The other 5 commands are unaffected (their names have no underscore/hyphen).
- [x] `_handle_talk_to` sets the target to the FULL argument (e.g. `target = " ".join(args)`), not `args[0]`, so a multi-word agent name ("Sonos Agent") is matched whole. Empty args still → the "Usage: /talk-to <agent-slug>" message. Update the handler's arg handling + any docstring.
- [x] Regression tests in `tests/test_connectors_commands.py`: (a) a `talk_to` (underscore) command_name dispatches to `_handle_talk_to` (would fall through / return None pre-fix); (b) `_handle_talk_to` with a multi-word agent name (args=["Sonos","Agent"], a permitted agent "Sonos Agent") sets the routing override + returns the "Now routing your messages to Sonos Agent." confirmation (pre-fix → "No such agent … Sonos"). Both must FAIL pre-fix.
- [x] Existing `/talk-to` (hyphen) tests still pass (the hyphen form still resolves; single-word agent names still work).
- [x] Full backend suite green / 0 errors (2818 passed, 4 skipped; prior 2812 + 6 new = 2818).
- [ ] (Verified at re-HAT, not this leg) `/talk_to Sonos Agent` via real Discord slash → channel-visible "Now routing your messages to Sonos Agent." confirmation.

## Verification Steps

- `docker exec the-one bash /app/scripts/run-tests.sh tests/test_connectors_commands.py -x --timeout 30 -q` — new + existing command tests pass.
- `docker exec the-one bash /app/scripts/run-tests.sh -m 'not browser and not live and not pixel' -q` — full backend green (leg-end).
- `git grep -nE 'replace\("_", "-"\)|" ".join\(args\)' the_one/connectors/_commands.py` — both fixes present.

## Implementation Guidance

1. **Normalize the lookup** in `_dispatch_builtin_command` (`:288`): `handler = _HANDLERS.get(command_name) or _HANDLERS.get(command_name.replace("_", "-"))`. Comment: slash command names use underscores (Discord rejects hyphens); the F7 v1 vocabulary uses hyphens — normalize so both reach the same handler. (Alternative: add a `"talk_to"` alias key — but the normalize form is general and prevents the same class of bug for any future hyphenated command.)
2. **Full agent name** in `_handle_talk_to`: replace `target = args[0]` with `target = " ".join(args)` (the agent slug is the rest of the line). Keep the empty-args Usage guard (`if not args:`). The `target` is then matched against `_permitted_agents(context)` as before.
3. **Tests**: add to `tests/test_connectors_commands.py`. For (a): call `_dispatch_builtin_command("talk_to", ["x"], context)` (or drive via the path that synthesizes it) and assert it routes to `_handle_talk_to` (not None). For (b): build a context whose `_permitted_agents` yields `["Sonos Agent"]` (a permitted multi-word agent), call `_handle_talk_to` with `args=["Sonos","Agent"]`, assert the response is "Now routing your messages to Sonos Agent." and the routing_override was set. Reuse `_build_context` (carries `plugin` per L1). Ensure both fail pre-fix.
4. **Run via the bounded wrapper**; record counts.

## Edge Cases

- **Other commands with no underscore**: `command_name.replace("_","-")` is a no-op for them (no underscore) — the exact-match `.get(command_name)` hits first anyway. Safe.
- **A genuinely-unknown command with an underscore** (e.g. `/foo_bar`): exact miss → hyphen-normalized miss (`foo-bar` not a handler) → `None` → falls through, as intended.
- **`/talk_to` with no agent arg**: `args == []` → `" ".join([]) == ""`; keep the `if not args:` Usage guard BEFORE the join so empty args returns Usage, not an empty-string lookup.
- **Agent names without spaces**: `" ".join(["Sonos"]) == "Sonos"` — single-word names still work.

## Files Affected

- `the_one/connectors/_commands.py` — command-name normalization in `_dispatch_builtin_command`; full-arg agent name in `_handle_talk_to`.
- `tests/test_connectors_commands.py` — regression tests for both fixes.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — commit handled by the FD at the L10 re-HAT close:**

- [x] Both fixes in place; regression tests added that fail pre-fix; existing `/talk-to` tests pass
- [x] Full backend green (2818 passed, 4 skipped; 2812 prior + 6 new)
- [x] Update flight-log.md with an L12/Bug G leg-progress entry
- [x] Set this leg's status to `landed`
- [ ] Do NOT commit yet (FD commits at the L10 re-HAT close, after restart + re-verify)
