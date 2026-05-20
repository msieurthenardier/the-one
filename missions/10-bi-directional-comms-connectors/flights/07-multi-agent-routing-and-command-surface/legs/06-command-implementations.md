# Leg: command-implementations

**Status**: landed
**Flight**: [Multi-Agent Routing and the Platform-Side Command Surface](../flight.md)

## Objective

Replace L5's `_dispatch_builtin_command` placeholder with the six v1 command handlers: `/agents`, `/talk-to <slug>`, `/whoami`, `/new`, `/reset` (alias for `/new`), `/help`. Each handler returns a `CommandResponse(text=...)` consumed by L5's dispatcher (which emits the text via system-outbound). Touch `connectors/_session.resolve_session` to honor a `session_metadata["ended_at"]` sentinel for `/new` semantics (new session on next inbound). Rewrite the L5-pinned placeholder test `test_dispatch_inbound_command_text_falls_through_to_agent_step_in_L5` to reflect `/agents` now being intercepted. No agent-loop changes; no Studio surface (L7); no routing-engine changes (L4 reads `routing_override` already).

## Context

This is the sixth F7 leg. Per Design Decisions in `flight.md`:

- **"Six commands, two as aliases"** — v1 vocabulary:
  - `/agents` — list agents the peer is permitted to invoke on this account (filtered by per-agent ACL via the eligible-attached-agents list from L5's context).
  - `/talk-to <slug>` — set `session_metadata["routing_override"] = <slug>` via L5's `set_session_metadata_key` primitive. Succeeds → confirmation text; fails (slug not in eligible list, unknown agent, or empty/missing arg) → peer-facing error.
  - `/whoami` — respond with the routed agent name for this turn (from L5's `context["routed_agent_name"]`).
  - `/new` — write `session_metadata["ended_at"] = <iso>` on the current session via L5's `set_session_metadata_key`. The next inbound creates a fresh session via the F3 lifecycle (teach `resolve_session` to treat sessions with `ended_at` set as not-current).
  - `/reset` — alias for `/new`. Same handler.
  - `/help` — list available commands with one-line descriptions, filtered by the peer's permissions (since `/agents` requires ≥1 eligible attached agent, and `/talk-to` requires ≥1 eligible, the same eligible-list filter applies to which commands are advertised).
- **F3 resolve_session touch** — the leg's one F3 ripple. Mechanism: in the existing-row reuse path (`_session.py:153-170`), check whether `existing.session_metadata` contains an `"ended_at"` key. If so, skip the reuse path and create a new row (drop through to the new-row creation block). Tests pin this against an existing-row whose `session_metadata["ended_at"]` is set.
- **Concurrency posture** — `/talk-to` writes `routing_override` via the last-writer-wins `set_session_metadata_key` primitive (L5). Two concurrent `/talk-to` inbounds on the same session land in non-deterministic order; the last writer's intent wins silently. Documented at L5's primitive docstring; L6 honors the contract.
- **L7 / L8 are downstream**: L7 ships the Studio Routing Rules editor; L8 ships the F6 carry-forward bundle. L6 finalizes the connector-side command surface — no Studio work, no Discord-side slash-command registration (that's F8 via the optional `CommandHandler` Protocol from L1).
- **Audit-log interaction** — the routing decision's audit entry (L5 step 8) already carries `disposition: "command-intercepted"` when a command handler returns a `CommandResponse`. The handler itself does NOT write a separate audit entry; the L5 dispatcher's existing write covers the audit need. For `/talk-to`, the override write is via `set_session_metadata_key("routing_override", ...)` — a separate sibling primitive call, NOT an audit-log entry. The combination produces TWO writes to `session_metadata` per `/talk-to`: (i) the `routing_override` set, (ii) the routing-decision append with `disposition: "command-intercepted"`. Both pin in tests.
- **Permission filtering** — `/agents` and `/help` filter their listed agents/commands by what THE PEER is permitted to invoke on this account. The "permitted" definition for L6: an agent is permitted to this peer if it's in `eligible_attached_agents` AND `admits_inbound(account, agent_acl_for_this_account, envelope.peer_id, envelope.channel_id)` returns `(True, ...)`. The L5 dispatcher's `eligible_attached_agents` is the full attached list; L6's handlers apply the ACL filter on top.

Key learnings from prior legs:

- L1: `_parse_command` returns `(command_name, args)` or `None`. Lowercase-only command names with `[a-z0-9-]` shape.
- L2: `admits_inbound(account, agent_acl, peer_id, channel_id) -> tuple[bool, str]`. L6 handlers call this directly (not via L4's engine, since L6 needs per-agent permission filtering for the `/agents` list).
- L3: `SQLiteAgentStore.list_by_connector_account(account_id) -> list[AgentConfig]`. L5 passes the alphabetical list via `context["eligible_attached_agents"]` — handlers consume the context.
- L4: `resolve_routing` consults `session_metadata["routing_override"]` first. L6's `/talk-to` writes this key; the next inbound's routing picks the override.
- L5: `_dispatch_builtin_command(command_name, args, context) -> CommandResponse | None`. Placeholder returns `None` for all. L6 rewrites the body.
- L5: `ChatSessionRepository.set_session_metadata_key(session_id, key, value)` — overwrite-semantic primitive. L6 uses it for `routing_override` AND `ended_at` writes.

## Inputs

What exists before this leg runs:

- `the_one/connectors/_commands.py:_dispatch_builtin_command` (L5 placeholder returning `None` for all). L6 rewrites the body.
- `the_one/connectors/_commands.py:_parse_command` (L1 pure function). Unchanged.
- `the_one/connectors/base.py:CommandResponse` (L1 dataclass). Consumed by handlers.
- `the_one/connectors/_acl.py:admits_inbound` (L2 pure function). Called by `/agents` and `/talk-to` handlers for permission filtering.
- `the_one/connectors/_session.py:resolve_session` (F3, lines 106-191). L6 adds the `ended_at` sentinel check in the reuse-path branch.
- `the_one/db/repositories.py:ChatSessionRepository.set_session_metadata_key` (L5 primitive). L6 consumes for `routing_override` AND `ended_at` writes.
- L5-shape dispatcher tests in `tests/test_connectors_inbound.py:TestF7RoutingIntegration` — `test_dispatch_inbound_command_text_falls_through_to_agent_step_in_L5` is the test L6 must REWRITE.
- F1–F7 (post-L5) test suite green: 452 connector+tool+repo tests pass.

## Outputs

What exists after this leg completes:

- `the_one/connectors/_commands.py` with `_dispatch_builtin_command` body filled in: dispatch by `command_name` to one of six handler functions. The placeholder's `None`-return is removed for the six recognized commands; unknown command names continue to return `None` (fall-through to agent.step preserves the L5-default behavior for unrecognized commands).
- Six private command-handler functions in `_commands.py`, each pure-with-context (consume the context dict; produce `CommandResponse`).
- `the_one/connectors/_session.py:resolve_session` updated: existing-row reuse path checks `session_metadata.get("ended_at")` and falls to new-row creation if set.
- `tests/test_connectors_commands.py` extended with command-handler tests (happy + denied paths per Acceptance Criteria).
- `tests/test_connectors_inbound.py:test_dispatch_inbound_command_text_falls_through_to_agent_step_in_L5` REWRITTEN to assert `/agents` is intercepted (audit `disposition="command-intercepted"`; system-outbound emit captured by `StubPlugin.outbound_records`).
- `tests/test_connectors_session.py` extended with one test for the `ended_at` reuse-path skip.
- F1–F7 (post-L5) regression suite passes byte-identically except the rewritten L5 placeholder test, which now asserts the L6 semantic.

## Acceptance Criteria

- [ ] `the_one/connectors/_commands.py` ships six command handlers:
  - `_handle_agents(context) -> CommandResponse` — returns text listing the ACL-permitted attached agents (alphabetical). Format: one agent per line, or comma-separated for short lists. Header text: "Agents available to you on this account:" followed by the list. If no ACL-permitted agents, returns "No agents available for this conversation." (unifies byte-for-byte with L5's no-eligible peer-facing string at `_inbound.py:394` for consistency across surfaces).
  - `_handle_talk_to(context) -> CommandResponse` — reads `args` from context (the L1 parser hands `(command_name, args)` to L5; L5 packs them into context). If `args` is empty → returns "Usage: /talk-to <agent-slug>". If the requested slug is not in the ACL-permitted attached agents → returns "No such agent or you don't have permission: <slug>". Otherwise: `await chat_repo.set_session_metadata_key(session_id, "routing_override", slug)`; returns "Now routing your messages to <slug>."
  - `_handle_whoami(context) -> CommandResponse` — returns "Currently responding: <routed_agent_name>." consumed from `context["routed_agent_name"]`. (No DB read; L5 already routed to this agent.)
  - `_handle_new(context) -> CommandResponse` — writes `session_metadata["ended_at"] = now_iso()` via `set_session_metadata_key`; returns "Started a new conversation. Your next message will begin a fresh session." (Note: the CURRENT inbound — the `/new` command itself — already routed and is being intercepted; the "next message" is the user's next inbound after this one.)
  - `_handle_reset(context) -> CommandResponse` — alias: `return await _handle_new(context)`.
  - `_handle_help(context) -> CommandResponse` — returns text listing the available commands with one-line descriptions, filtered for the peer's permissions per the flight Design Decision. `/whoami`, `/new`, `/reset`, `/help` are ALWAYS listed (no eligible-agent dependency). `/agents` and `/talk-to` are listed ONLY when `_permitted_agents(context)` is non-empty. Header: "Available commands:". Format: one command per line.
- [ ] L6 needs an `args` field in the L5 context dict — L5 currently passes the parsed args to `_dispatch_builtin_command(command_name, args, context)` as positional arg. Verify L5's call site already does this. If not (the L5 spec passed args separately): the L6 handler signatures accept context only, so L5 must pack args into context too. ACTION: L6 updates L5's dispatcher call site to pack `args` into context: `context["args"] = args`. Alternatively: handlers take `(args, context)` signature. Pick one. Recommendation: keep handlers as `_handle_X(context)` for uniformity (the `/help` handler doesn't use args); pack args into context as `context["args"] = args` in L5's existing site. L6's leg explicitly modifies L5's dispatcher site to add this one line.
- [ ] `_dispatch_builtin_command` body (replaces L5 placeholder):
  ```python
  _HANDLERS: dict[str, Callable[[dict[str, Any]], Awaitable[CommandResponse]]] = {
      "agents": _handle_agents,
      "talk-to": _handle_talk_to,
      "whoami": _handle_whoami,
      "new": _handle_new,
      "reset": _handle_reset,
      "help": _handle_help,
  }
  async def _dispatch_builtin_command(
      command_name: str,
      args: list[str],
      context: dict[str, Any],
  ) -> CommandResponse | None:
      handler = _HANDLERS.get(command_name)
      if handler is None:
          return None  # Unknown command → fall through to agent.step.
      context["args"] = args  # Pack args into context for the handlers.
      return await handler(context)
  ```
- [ ] `the_one/connectors/_session.resolve_session` updated:
  - In the existing-row reuse path (currently `_session.py:153-170`), the existing single combined condition `if existing is not None and existing.last_inbound_at is not None:` is RESTRUCTURED into a nested form so the `ended_at` sentinel check can short-circuit reuse independently of the continuation-window check. Final shape:
    ```python
    if existing is not None:
        metadata = existing.session_metadata or {}
        if "ended_at" in metadata:
            # The /new command marked this session as ended.
            # Fall through to new-row creation below.
            pass
        elif existing.last_inbound_at is not None:
            # ... existing continuation-window check unchanged ...
    ```
  - The change is BEHAVIORALLY ADDITIVE — no existing test sets `session_metadata["ended_at"]`, so all existing reuse-path tests pass byte-identically. The STRUCTURAL change (combined `if` → nested `if`) is intentional and required to accommodate the new sentinel.
- [ ] `tests/test_connectors_commands.py` extended with command-handler tests:
  - `TestHandleAgents` — `/agents` lists permitted; empty list returns "No agents available to you on this account."; ACL-denied agents are filtered out.
  - `TestHandleTalkTo` — empty args returns "Usage:..."; whitespace-only-args (the parser-collapsed equivalent of `/talk-to    `) returns "Usage:..." (pins the trailing-whitespace → empty-args contract from L1); unknown slug returns peer-facing error; valid slug writes `routing_override` via `set_session_metadata_key` (verify by reading back the session row) and returns confirmation text; ACL-denied slug treated as unknown (same error path); second `/talk-to` overwrites first (pins the last-writer-wins primitive contract — `set_session_metadata_key("routing_override", "alice")` followed by `set_session_metadata_key("routing_override", "bob")` yields `"bob"` on read-back).
  - `TestHandleWhoami` — returns the routed agent name from context.
  - `TestHandleNew` — writes `session_metadata["ended_at"]`; returns confirmation; subsequent `_session.resolve_session` call on the same external-key creates a NEW chat_sessions row (integration test).
  - `TestHandleReset` — alias proves: calling `_handle_reset(context)` produces the SAME `CommandResponse` and the SAME `session_metadata["ended_at"]` side-effect as `_handle_new(context)`.
  - `TestHandleHelp` — two cases: (a) peer with ≥1 permitted agent — response lists all six command names; (b) peer with zero permitted agents (ACL denies all attached agents) — response lists only `/whoami`, `/new`, `/reset`, `/help` (NOT `/agents` or `/talk-to`).
  - `TestDispatchBuiltinCommand` — `_dispatch_builtin_command("agents", [], context)` returns the `/agents` response; unknown commands (e.g. `_dispatch_builtin_command("nonsense", [], context)`) return `None` (fall-through preserved).
- [ ] `tests/test_connectors_inbound.py:test_dispatch_inbound_command_text_falls_through_to_agent_step_in_L5` REWRITTEN to:
  - Rename to `test_dispatch_inbound_command_text_intercepted_after_L6` (or similar — the new test should reflect the post-L6 reality).
  - Envelope text `"/agents"`; assert system-outbound emission via `StubPlugin.outbound_records` containing the `/agents` response text; audit-log entry `disposition="command-intercepted"`; `agent.step` did NOT run (assert via recording factory or by checking that the chat_sessions row's `messages` field stayed empty after the inbound).
  - The new test is the integration anchor for L6's command-intercept path.
- [ ] `tests/test_connectors_session.py` extended with one test:
  - `test_resolve_session_skips_reuse_when_ended_at_is_set` — seed an existing chat_sessions row matching the envelope's external key with `session_metadata = {"ended_at": "<iso>"}` and a recent `last_inbound_at`; call `resolve_session(envelope, account, chat_repo, agent_name=..., plugin=...)`; assert the returned row is a NEW row (different `id`) — the `ended_at` sentinel skipped the reuse path even though continuation window would otherwise apply.
- [ ] Documentation:
  - `the_one/connectors/README.md` — add a new section (after the L5 12-step trace) on the v1 command vocabulary: list the six commands with one-line descriptions; note `/new`/`/reset` aliasing; cite `_commands.py` as canonical home.
  - `the_one/agents.md` — extend the F7 routing-convention paragraph (or add a sibling paragraph) covering the v1 command surface: text-prefix parsing, system-outbound emission, the `routing_override` and `ended_at` `session_metadata` keys.
- [ ] F1–F7 (post-L5) regression suite passes byte-identically PLUS the new command-handler tests AND the rewritten L5 placeholder test:
  ```
  docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'
  ```
  Expected: ~468+ tests pass (~452 prior + ~14 new command-handler tests + 1 rewritten = ~466 minimum; allow headroom for the integration test variants).

## Verification Steps

How to confirm each criterion is met:

**Command-handler tests** (in `tests/test_connectors_commands.py`):

For each handler:
- Happy path: handler returns `CommandResponse(text=...)` matching the expected text.
- Permission-filter path (for `/agents`, `/talk-to`, `/help`): ACL-denied agents are filtered.
- Side-effect path (for `/talk-to`, `/new`, `/reset`): `set_session_metadata_key` was called with the expected (key, value); verify by reading the session row back.
- Error path: empty / invalid args return the right peer-facing text.

**Dispatcher integration** (in `tests/test_connectors_inbound.py` — rewritten test):

- Envelope `"/agents"` → `StubPlugin.outbound_records` contains the response text; audit `disposition="command-intercepted"`; agent.step did NOT execute (no agent messages persisted).

**`resolve_session` ended_at semantic** (in `tests/test_connectors_session.py`):

- Existing row with `session_metadata["ended_at"]` is skipped; a new row is created.
- Existing row WITHOUT `ended_at` (and with recent `last_inbound_at`) continues to be reused — pins the change is additive.

**Regression**:

- Full suite green: ~468+ tests.

## Implementation Guidance

### 1. Command handlers in `_commands.py`

Add the six handlers as private async functions. Each takes a `context: dict[str, Any]`.

```python
from __future__ import annotations

from typing import Any, Awaitable, Callable

from the_one.connectors._acl import admits_inbound
from the_one.connectors.base import CommandResponse, InboundEnvelope
from the_one.db.models import ConnectorAccount, now_iso


def _permitted_agents(
    context: dict[str, Any],
) -> list[str]:
    """Return alphabetically-sorted agent names that the envelope's peer
    is permitted to invoke on the account (filtered by per-agent ACL).
    """
    account: ConnectorAccount = context["account"]
    envelope: InboundEnvelope = context["envelope"]
    eligible = context["eligible_attached_agents"]
    permitted: list[str] = []
    for agent_config in eligible:
        agent_acl = None
        if agent_config.connector_acls is not None:
            agent_acl = agent_config.connector_acls.get(account.id)
        admits, _reason = admits_inbound(
            account, agent_acl, envelope.peer_id, envelope.channel_id
        )
        if admits:
            permitted.append(agent_config.name)
    return permitted


async def _handle_agents(context: dict[str, Any]) -> CommandResponse:
    names = _permitted_agents(context)
    if not names:
        return CommandResponse(text="No agents available for this conversation.")
    lines = ["Agents available to you on this account:"]
    lines.extend(f"- {n}" for n in names)
    return CommandResponse(text="\n".join(lines))


async def _handle_talk_to(context: dict[str, Any]) -> CommandResponse:
    args: list[str] = context["args"]
    if not args:
        return CommandResponse(text="Usage: /talk-to <agent-slug>")
    target = args[0]
    permitted = _permitted_agents(context)
    if target not in permitted:
        return CommandResponse(
            text=f"No such agent or you don't have permission: {target}"
        )
    chat_repo = context["chat_repo"]
    session_id: str = context["session_id"]
    await chat_repo.set_session_metadata_key(session_id, "routing_override", target)
    return CommandResponse(text=f"Now routing your messages to {target}.")


async def _handle_whoami(context: dict[str, Any]) -> CommandResponse:
    routed = context["routed_agent_name"]
    return CommandResponse(text=f"Currently responding: {routed}.")


async def _handle_new(context: dict[str, Any]) -> CommandResponse:
    chat_repo = context["chat_repo"]
    session_id: str = context["session_id"]
    await chat_repo.set_session_metadata_key(session_id, "ended_at", now_iso())
    return CommandResponse(
        text=(
            "Started a new conversation. Your next message will begin a "
            "fresh session."
        )
    )


async def _handle_reset(context: dict[str, Any]) -> CommandResponse:
    return await _handle_new(context)


async def _handle_help(context: dict[str, Any]) -> CommandResponse:
    # Per flight Design Decision: `/help` is permission-filtered.
    # `/agents` and `/talk-to` are listed only if the peer has at least
    # one permitted agent on this account; the four agent-independent
    # commands are always listed.
    lines = ["Available commands:"]
    if _permitted_agents(context):
        lines.append("- /agents — list agents you can talk to here")
        lines.append("- /talk-to <agent> — switch to a different agent")
    lines.append("- /whoami — show which agent is currently responding")
    lines.append("- /new — start a fresh conversation")
    lines.append("- /reset — alias for /new")
    lines.append("- /help — show this list")
    return CommandResponse(text="\n".join(lines))


_HANDLERS: dict[str, Callable[[dict[str, Any]], Awaitable[CommandResponse]]] = {
    "agents": _handle_agents,
    "talk-to": _handle_talk_to,
    "whoami": _handle_whoami,
    "new": _handle_new,
    "reset": _handle_reset,
    "help": _handle_help,
}


async def _dispatch_builtin_command(
    command_name: str,
    args: list[str],
    context: dict[str, Any],
) -> CommandResponse | None:
    """Dispatch a parsed v1 command to its handler.

    M10 F7 L6: replaces the L5 placeholder that returned ``None`` for
    every command. Unknown command names (those not in v1 vocabulary)
    continue to return ``None`` — the dispatcher falls through to
    agent.step, treating them as regular user messages.

    The context dict is L5 dispatcher's per-invocation state:
    ``account``, ``envelope``, ``eligible_attached_agents``,
    ``routed_agent_name``, ``session_id``, ``chat_repo``. L6 adds
    ``args`` (the parsed argument list) into the context for handler
    consumption.
    """
    handler = _HANDLERS.get(command_name)
    if handler is None:
        return None
    context["args"] = args
    return await handler(context)
```

### 2. `_session.py` reuse-path update

Insert the `ended_at` check at the top of the existing-row branch:

```python
    if existing is not None:
        metadata = existing.session_metadata or {}
        if "ended_at" in metadata:
            # /new sentinel — skip reuse, fall through to new-row creation.
            pass
        elif existing.last_inbound_at is not None:
            try:
                last = datetime.fromisoformat(existing.last_inbound_at)
            except ValueError:
                logger.warning(
                    "chat_sessions.last_inbound_at=%r is not ISO; treating as stale",
                    existing.last_inbound_at,
                )
                last = None
            if last is not None:
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if (now - last).total_seconds() < continuation:
                    return existing

    # Create a new row on the (no-match OR outside-window OR ended) paths.
    # ... existing creation logic ...
```

### 3. L5 dispatcher site

L5's `_dispatch_builtin_command(command_name, args, context)` call site needs no change — the function already receives args as a positional parameter. The L6 implementation simply packs them into context.

### 4. Order of file edits

1. `the_one/connectors/_commands.py` — replace placeholder; add handlers + `_HANDLERS` dispatch map.
2. `the_one/connectors/_session.py` — add `ended_at` reuse-path skip.
3. `tests/test_connectors_commands.py` — extend with handler tests.
4. `tests/test_connectors_session.py` — add `ended_at`-skip test.
5. `tests/test_connectors_inbound.py` — rewrite the placeholder test.
6. `the_one/connectors/README.md` — add v1 command vocabulary section.
7. `the_one/agents.md` — extend routing-convention paragraph.
8. Run full regression: `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'`.

### 5. Things NOT in scope

- Per-platform slash-command registration (`CommandHandler` Protocol implementations) — F8 / F9 territory.
- Studio Routing Rules editor — L7.
- F6 carry-forward bundle — L8.
- `/reset` distinct-from-`/new` semantics — confirmed by HAT or future mission; L6 ships alias-only.

## Edge Cases

- **`/talk-to` with whitespace-only slug** (`/talk-to    `): L1 parser produces `args=[]` (str.split collapses trailing whitespace). Handler returns "Usage:..." message. Pinned.
- **`/talk-to` with multiple args** (`/talk-to alice extra`): handler reads `args[0]` only; `extra` is ignored. Pinned by test.
- **`/agents` when only ACL-denied agents are attached**: returns "No agents available to you on this account." — matches L5's no-eligible peer-facing string for consistency.
- **`/whoami` after `/talk-to` writes routing_override but the override hasn't taken effect yet**: the CURRENT inbound (the `/whoami` command) was already routed by L5 BEFORE `/talk-to` could write the override. So `/whoami` returns whatever agent routed the CURRENT inbound, NOT the override target. The override takes effect on the NEXT inbound. This is the correct semantic; pinned by test.
- **`/new` on a session that's already marked ended**: writing `ended_at` again is idempotent (overwrite-semantic). The next inbound creates a new session either way. No issue.
- **`/new` followed by an immediate next inbound from the SAME peer**: the resolve_session lookup finds the now-ended row, skips the reuse path, creates a new row with empty `session_metadata`. Pinned by the integration test.
- **`/help` for a peer with zero permitted agents**: per the flight Design Decision, `/help` is permission-filtered. The four agent-independent commands (`/whoami`, `/new`, `/reset`, `/help`) are always listed; `/agents` and `/talk-to` are listed only when the peer has at least one ACL-permitted attached agent. Pinned by test (zero-permitted-agents fixture asserts response text contains `/whoami` / `/new` / `/reset` / `/help` and does NOT contain `/agents` / `/talk-to`).
- **Unknown command (e.g. `/foo`)**: parser succeeds; dispatch returns `None`; L5 falls through to agent.step. The agent sees `"/foo"` as the user message. Pinned by `TestDispatchBuiltinCommand`.

## Files Affected

- `the_one/connectors/_commands.py` — replace placeholder `_dispatch_builtin_command`; add six private handlers + `_HANDLERS` dispatch map.
- `the_one/connectors/_session.py` — add `ended_at` sentinel check in `resolve_session` reuse path.
- `tests/test_connectors_commands.py` — extend with command-handler tests + `_dispatch_builtin_command` integration tests.
- `tests/test_connectors_session.py` — add `ended_at`-skip test.
- `tests/test_connectors_inbound.py` — rewrite the L5 placeholder test for the L6 intercept semantic.
- `the_one/connectors/README.md` — v1 command vocabulary section.
- `the_one/agents.md` — F7 routing-convention paragraph extended.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)

## Citation Audit

Citations verified against current code at leg design time:

| Citation | Status | Notes |
|----------|--------|-------|
| `the_one/connectors/_commands.py:_dispatch_builtin_command` | OK | L5-shipped placeholder; L6 replaces body |
| `the_one/connectors/_commands.py:_parse_command` | OK | L1 pure function; unchanged |
| `the_one/connectors/base.py:CommandResponse` | OK | L1 dataclass; consumed by handlers |
| `the_one/connectors/_acl.py:admits_inbound` | OK | L2 pure function |
| `the_one/connectors/_session.py:106-191` (resolve_session) | OK | Reuse path at 153-170; new-row creation at 172-191 |
| `the_one/db/repositories.py:ChatSessionRepository.set_session_metadata_key` | OK | L5-landed primitive |
| `tests/test_connectors_inbound.py:test_dispatch_inbound_command_text_falls_through_to_agent_step_in_L5` | OK | L5-pinned placeholder test; L6 rewrites |
| `tests/test_connectors_commands.py` (L1 + L2 test mirror) | OK | Style precedent for L6 extensions |

8 in-leg-artifact code-location citations verified.
