# Leg: channel-context-tools

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Ship the four channel-context built-in tools (`fetch_channel_history`, `fetch_thread_history`, `fetch_dm_history`, `list_visible_channels`) + the two new optional plugin hooks (`fetch_history`, `fetch_dm_history`) per Flight DD §10. Each tool resolves the current session's connector account via the existing `current_chat_session_id` ContextVar plumbing, respects per-agent `connector_acls`, and returns the standard list-of-dicts (or axis-keyed dict for `list_visible_channels`) shape. Discord plugin implementations wrap `discord.py`'s history primitives. The four tools' presence makes L9's "if available" forward-references real.

## Context

- **Flight DD §10 verbatim** — four built-in tools + two new plugin hooks (via `optional-plugin-hook-via-getattr-sentinel`); `list_visible_channels` reuses the existing F3 `enumerate_discoverable_entities` hook (no new hook needed for it).
- **Tool framework precedent (recon-confirmed)** — `tools/builtins.py:_TOOL_CLASSES` is the registration dict; `BuiltinToolProvider.get_tools(...)` accepts `connector_account_ids` + `connector_acls` kwargs (L10 mirrors the SendToPlatformChannelTool wiring at lines 159-166); tools extend the `Tool` base with `name`, `description`, `parameters` (JSON Schema), async `execute(...)`.
- **ACL discipline (DD §10)** — fetch tools gate read access via per-axis ACL checks:
  - `fetch_channel_history` + `fetch_thread_history`: call `admits_outbound(account, agent_acl, channel_id)` (channel axis).
  - `fetch_dm_history`: **`admits_outbound` does NOT cover the peers axis** (cycle-1 review verified — peers logic lives only in `admits_inbound`). L10 must inline a peer-axis check matching the `admits_inbound` peers-block at `_acl.py:250-259` (account scope) + `_acl.py:287-304` (per-agent scope). The check structure: (a) if `account.config["allowlist"]["peers"]` is set + non-empty + `peer_id` not in it → deny; (b) if `agent_acl["peers"]` is `None` → inherit account-scope; (c) if `agent_acl["peers"]` is `[]` (explicitly empty) → DENY for fetch_dm_history (NOT a DMs-only sentinel here — the DMs-only sentinel is `channels=[]`, not `peers=[]`); (d) if `agent_acl["peers"]` is a non-empty list and `peer_id` not in it → deny. Alternative: add a sibling helper `admits_dm_peer(account, agent_acl, peer_id) -> tuple[bool, str]` in `_acl.py` for symmetry with `admits_outbound`. The Developer agent picks one approach; both satisfy the convention.
  - On deny (any axis), return `[{"error": "agent not permitted to read <axis> X: <reason>"}]`. The error format is a single-element list-of-dict with `error` key.
- **`FetchedMessage` dataclass** — new substrate type at `the_one/connectors/base.py` alongside `InboundEnvelope`. Fields per recon: `peer_id`, `peer_name`, `content`, `ts`, `thread_id`. Tools convert to dicts via `dataclasses.asdict(msg)`.
- **Plugin hook discipline** — two new optional hooks via `optional-plugin-hook-via-getattr-sentinel`. Tools use `getattr(plugin, "fetch_history", None)` / `getattr(plugin, "fetch_dm_history", None)`. If None (plugin doesn't implement, e.g., stub), the tool returns `[{"error": "this plugin does not support history fetch"}]`.
- **`list_visible_channels` reuses `enumerate_discoverable_entities`** — same hook from F3 L4. Tool acquires client, calls the hook, converts the `DiscoverableEntities` dataclass to the dict the LLM sees: `{"peers": [...], "channels": [...], "groups": [...], "roles": [...]}` where each entry is a dict `{"id": "...", "label": "..."}`. If the hook is missing (stub plugin), return `{"error": "this plugin does not support entity enumeration", "peers": [], "channels": [], "groups": [], "roles": []}`.
- **Session resolution via ContextVar** — tools read `current_chat_session_id.get()` → look up the session row via `ChatSessionRepository.get(session_id)` → read `session.connector_account_id` → resolve plugin + client via `account_acquire(account_id)`. If `current_chat_session_id` is None (tool called outside connector context), return `[{"error": "this tool is only available in a connector-attached session"}]`.
- **L9 directive forward-references** — L9 already shipped the directive with `fetch_*_history` and `list_visible_channels` mentions under "if available" hedging. L10 makes them real. The hedge stays in the directive (per L10 recon's analysis: keeps the prompt truthful for plugin variations).
- **Substrate-generic hooks** — `fetch_history(client, channel_id, thread_id, limit)` and `fetch_dm_history(client, peer_id, limit)` are connector-agnostic. Discord implements them by wrapping `discord.TextChannel.history()` / `discord.Thread.history()` / `discord.User.create_dm().history()`. Future Slack/Matrix plugins implement their own; the substrate stays neutral.

## Inputs

- L1-L9 landed uncommitted; F7 policy gate active; L9's directive forward-references in place.
- `the_one/tools/builtins.py` with `_TOOL_CLASSES` dict + `BuiltinToolProvider.get_tools(...)` factory accepting `connector_account_ids` + `connector_acls` kwargs.
- `the_one/tools/connector_send.py:SendToPlatformChannelTool` (precedent for tool shape + ACL handling + pool acquire).
- `the_one/agent/_context.py:current_chat_session_id` ContextVar.
- `the_one/connectors/_acl.py:admits_outbound` for per-channel/peer ACL gating.
- `the_one/connectors/_pool.py:account_acquire(account_id) -> ConnectorClient` for client acquisition.
- `the_one/connectors/_pool.py:_get_account_cache_snapshot(account_id)` for accessing cached `DiscoverableEntities` (preferred over forcing a fresh refresh).
- `the_one/connectors/base.py:InboundEnvelope`, `DiscoverableEntities`, `DiscoverableEntity` — type precedents for adding `FetchedMessage`.
- `the_one/connectors/_discord.py:DiscordClient`, `DiscordPlugin` — sites for the new Discord hook implementations.
- `the_one/connectors/_stub.py` — stub plugin used by tests; does NOT need to implement the new hooks (tests use the missing-hook fallback to exercise the error path).
- `tests/test_connector_send_tool.py` — test scaffolding precedent.

## Outputs

- `the_one/connectors/base.py`:
  - **ADD** new `FetchedMessage` dataclass alongside `InboundEnvelope`:
    ```python
    @dataclass(frozen=True, slots=True)
    class FetchedMessage:
        """A message fetched from channel/thread/DM history via plugin hook.

        Returned by the substrate-generic ``fetch_history`` and
        ``fetch_dm_history`` plugin hooks (optional via
        ``optional-plugin-hook-via-getattr-sentinel``). The L10 fetch tools
        convert each instance to a dict via ``dataclasses.asdict`` before
        emitting to the LLM.
        """
        peer_id: str
        peer_name: str
        content: str
        ts: str
        thread_id: str | None
    ```
- `the_one/tools/connector_history.py` (NEW file — group the four tools + their shared helpers):
  - Module docstring citing M11 F7 L10 + Flight DD §10.
  - Shared helper `_resolve_connector_account_context() -> tuple[str, ConnectorAccount, ConnectorPlugin, ConnectorClient] | None`:
    - Reads `current_chat_session_id.get()`; if None → return None.
    - Looks up session via `ChatSessionRepository.get(session_id)`; if no `connector_account_id` → return None.
    - Loads `ConnectorAccount` via `ConnectorAccountRepository.get(account_id)`.
    - Resolves plugin via `registry.resolve(account.type)`.
    - Acquires client via `account_acquire(account_id)`.
    - Returns the four-tuple, OR None if any step fails.
  - Shared helper `_format_outside_connector_error() -> list[dict]`: returns `[{"error": "this tool is only available in a connector-attached session"}]`.
  - Tool class `FetchChannelHistoryTool(Tool)`:
    - `name = "fetch_channel_history"`
    - `description = "Fetch recent messages from a channel the bot can see. Returns a list of message dicts (peer_id, peer_name, content, ts, thread_id) ordered most-recent-last. Respects per-agent channel ACL — denied channels return [{'error': '...'}]."`
    - `parameters` JSON schema: `channel_id` (string, required), `limit` (integer, default 20).
    - `__init__` signature **must mirror `SendToPlatformChannelTool.__init__` exactly** to satisfy `BuiltinToolProvider.get_tools`'s `cls(cfg, cross_configs=cross_configs, agent_name=agent_name, **extra_kwargs)` call (`builtins.py:168`):
      ```python
      def __init__(
          self,
          config,
          *,
          cross_configs=(),
          agent_name=None,
          connector_account_ids=(),
          connector_acls=None,
      ):
          super().__init__(config, cross_configs=cross_configs, agent_name=agent_name)
          self._connector_account_ids = tuple(connector_account_ids or ())
          self._connector_acls = connector_acls
      ```
      The Developer agent reads `connector_send.py:100-115` for the exact precedent shape.
    - `async def execute(self, channel_id: str, limit: int = 20) -> list[dict]`:
      - Resolve context via helper; on None → return outside-connector error.
      - Lookup `agent_acl = connector_acls.get(account.id) if connector_acls else None`.
      - Call `admits_outbound(account, agent_acl, channel_id)`; if denied → return `[{"error": f"agent not permitted to read channel {channel_id}: {reason}"}]`.
      - `hook = getattr(plugin, "fetch_history", None)`; if None → return `[{"error": "this plugin does not support history fetch"}]`.
      - Try `messages = await hook(client, channel_id, None, limit)`; on exception → return `[{"error": f"fetch_history failed: {type(exc).__name__}: {exc}"}]`.
      - Return `[asdict(m) for m in messages]`.
  - Tool class `FetchThreadHistoryTool(Tool)`:
    - Same `__init__` signature as `FetchChannelHistoryTool`. Parameters: `channel_id` AND `thread_id` (both required, strings) + `limit` (default 20). Calls `hook(client, channel_id, thread_id, limit)`. ACL admission on `channel_id` via `admits_outbound`.
  - Tool class `FetchDmHistoryTool(Tool)`:
    - Same `__init__` signature. Parameter: `peer_id` (string, required) + `limit` (default 20).
    - ACL admission on `peer_id` via **peer-axis check** (NOT `admits_outbound`, which is channel-axis only — cycle-1 review verified). Inline the peer-axis logic per Context bullet "ACL discipline (DD §10)" above, OR add a new `admits_dm_peer(account, agent_acl, peer_id) -> tuple[bool, str]` helper in `_acl.py` mirroring `admits_outbound`'s shape. The Developer agent picks the approach at impl time.
    - Calls `hook = getattr(plugin, "fetch_dm_history", None)`.
    - Returns same dict shape.
  - Tool class `ListVisibleChannelsTool(Tool)`:
    - `name = "list_visible_channels"`
    - No parameters.
    - `parameters = {"type": "object", "properties": {}}`.
    - `async def execute(self) -> dict[str, Any]`:
      - Resolve context; on None → return `{"error": "this tool is only available in a connector-attached session", "peers": [], "channels": [], "groups": [], "roles": []}`.
      - Get cached snapshot via `_get_account_cache_snapshot(account.id)`; if snapshot has cache → convert to dict and return; if snapshot.cache is None OR snapshot is None → call hook live via `enumerate_discoverable_entities(client)` (the F3 plugin hook); if hook is None → return `{"error": "this plugin does not support entity enumeration", "peers": [], "channels": [], "groups": [], "roles": []}`.
      - Convert `DiscoverableEntities` to dict: `{"peers": [asdict(p) for p in cache.peers], "channels": [...], "groups": [...], "roles": [...]}`. Drop the `fetched_at` field from the result (LLM doesn't need it).
- `the_one/tools/builtins.py`:
  - **ADD** imports for the four new tool classes at the top.
  - **ADD** four entries to `_TOOL_CLASSES`:
    ```python
    "fetch_channel_history": FetchChannelHistoryTool,
    "fetch_thread_history": FetchThreadHistoryTool,
    "fetch_dm_history": FetchDmHistoryTool,
    "list_visible_channels": ListVisibleChannelsTool,
    ```
  - **EXTEND** `BuiltinToolProvider.get_tools(...)` (lines 159-166 per recon) to inject `connector_account_ids` + `connector_acls` kwargs into the four new tools (mirroring how it injects them into `SendToPlatformChannelTool`).
- `the_one/connectors/_discord.py`:
  - **ADD** `DiscordPlugin.fetch_history(self, client: ConnectorClient, channel_id: str, thread_id: str | None, limit: int) -> list[FetchedMessage]`:
    - Wraps `discord.TextChannel.history()` / `discord.Thread.history()`.
    - Resolves the channel/thread object via `client._client.get_channel(int(channel_id))` (and `.get_thread(int(thread_id))` if thread_id is set).
    - Iterates the history (`async for message in obj.history(limit=limit):`).
    - Constructs `FetchedMessage(peer_id=str(msg.author.id), peer_name=msg.author.display_name, content=msg.content, ts=msg.created_at.isoformat(), thread_id=str(msg.thread.id) if hasattr(msg, 'thread') and msg.thread else None)`.
    - Returns list. Defensive: handle case where `get_channel` returns None → return empty list. Handle SDK exceptions → propagate (the tool's try/except catches them).
  - **ADD** `DiscordPlugin.fetch_dm_history(self, client: ConnectorClient, peer_id: str, limit: int) -> list[FetchedMessage]`:
    - Resolves the user via `await client._client.fetch_user(int(peer_id))`; calls `await user.create_dm()` to get the DMChannel; iterates `.history(limit=limit)`.
    - Constructs FetchedMessage entries; thread_id is always None for DMs.
- New tests in `tests/test_connector_history_tools.py`:
  - Reuse the test fixtures from `tests/test_connector_send_tool.py` (`isolated_db`, `_clear_pool_and_registry`, `_reset_stub_state`).
  - **Tests for `fetch_channel_history`**:
    - `test_fetch_channel_history_outside_connector_returns_error` — `current_chat_session_id` is None → error dict.
    - `test_fetch_channel_history_denied_by_agent_acl_returns_error` — ACL denies `channel_id` → `[{"error": "agent not permitted to read channel X..."}]`.
    - `test_fetch_channel_history_missing_plugin_hook_returns_error` — stub plugin (no `fetch_history`) → `[{"error": "this plugin does not support history fetch"}]`.
    - `test_fetch_channel_history_returns_messages` — stub plugin with a custom `fetch_history` returning known `FetchedMessage` objects → tool returns the dict list.
    - `test_fetch_channel_history_plugin_exception_returns_error_dict` — hook raises → tool returns error dict.
  - **Tests for `fetch_thread_history`**: same five patterns but with thread_id parameter.
  - **Tests for `fetch_dm_history`**: same five patterns but with peer_id parameter; ACL admission on peer axis.
  - **Tests for `list_visible_channels`**:
    - `test_list_visible_channels_outside_connector_returns_error_dict` — `current_chat_session_id` is None → error-with-empty-axes dict.
    - `test_list_visible_channels_uses_cache_snapshot_when_present` — pool has cached `DiscoverableEntities` → tool returns it as dict.
    - `test_list_visible_channels_falls_back_to_live_hook_when_cache_empty` — pool snapshot is None or cache is None; plugin has `enumerate_discoverable_entities`; tool calls live and returns.
    - `test_list_visible_channels_missing_hook_returns_error_dict` — stub plugin without enumerate → error dict with empty axes.
  - **Tool-registration tests**:
    - `test_builtin_provider_includes_four_history_tools` — `BuiltinToolProvider().get_tools(...)` returns tool objects for all four names.
  - **Additional coverage** (cycle-1 review):
    - `test_fetch_channel_history_session_lookup_failure_returns_error` — `current_chat_session_id` set but `ChatSessionRepository.get(session_id)` raises KeyError (deleted session) → outside-connector error path returns gracefully.
    - `test_list_visible_channels_drops_fetched_at_field` — verify the `fetched_at` timestamp from `DiscoverableEntities` is omitted from the tool's response dict (per Outputs spec).

## Acceptance Criteria

- [ ] `the_one/connectors/base.py` has a `FetchedMessage` dataclass with the five fields listed.
- [ ] `the_one/tools/connector_history.py` exists with the four tool classes + shared helpers.
- [ ] `the_one/tools/builtins.py:_TOOL_CLASSES` registers the four new tool names.
- [ ] `BuiltinToolProvider.get_tools(...)` injects `connector_account_ids` + `connector_acls` kwargs into the four new tools.
- [ ] `the_one/connectors/_discord.py:DiscordPlugin` has `fetch_history` and `fetch_dm_history` methods that wrap `discord.py` history primitives.
- [ ] The four tools properly resolve the connector account from `current_chat_session_id`, gate via per-agent `connector_acls`, and return the standard list-of-dict / axis-keyed-dict shapes.
- [ ] Tools handle the four failure modes per Outputs: outside-connector, ACL-denied, missing-hook, hook-exception. All return descriptive error dicts.
- [ ] All new tests pass: `docker exec the-one pytest tests/test_connector_history_tools.py -x --timeout 30`.
- [ ] Existing dispatcher + send-tool tests continue to pass (L10 doesn't touch their surfaces).
- [ ] Full suite at leg-end: `docker exec the-one pytest -x --timeout 60` — no L10-introduced regressions.
- [ ] Flight log L10 entry under `## Leg Progress` documents the leg; leg checked off in `flight.md`; status set to `landed`.

## Verification Steps

- `python -c "from the_one.connectors.base import FetchedMessage; m = FetchedMessage(peer_id='1', peer_name='a', content='hi', ts='2026', thread_id=None); print(m)"` prints a representation.
- `python -c "from the_one.tools.builtins import _TOOL_CLASSES; print(sorted(_TOOL_CLASSES.keys()))"` includes the four new names.
- `grep -n "fetch_history\|fetch_dm_history" the_one/connectors/_discord.py` returns the new method definitions.
- Targeted: `docker exec the-one pytest tests/test_connector_history_tools.py tests/test_connector_send_tool.py -x --timeout 30` — all green.
- Full suite: `docker exec the-one pytest -x --timeout 60` — all green.

## Implementation Guidance

1. **Add `FetchedMessage` dataclass** to `the_one/connectors/base.py` per Outputs.

2. **Create `the_one/tools/connector_history.py`** with the four tool classes + shared helpers. Read `the_one/tools/connector_send.py` to mirror the `SendToPlatformChannelTool` shape (`__init__`, `name`/`description`/`parameters` class vars, `async def execute`, error response patterns).

3. **Locate ACL admission for DMs (peer axis)** — the recon flagged uncertainty about whether `admits_outbound` covers peers or if a peer-specific helper exists. Read `the_one/connectors/_acl.py` and determine. If `admits_outbound` is channel-axis only, look for `admits_peer` or fall back to manually checking `agent_acl.get("peers")` against `peer_id` per the F6 ACL convention.

4. **Update `the_one/tools/builtins.py`** to register the four new tools + extend `get_tools` to inject `connector_account_ids` + `connector_acls` into them (mirror lines 159-166 per recon).

5. **Add the Discord plugin hooks** (`DiscordPlugin.fetch_history` + `DiscordPlugin.fetch_dm_history`) using `discord.py` SDK methods. Read existing `DiscordClient.send` (line 372) to see how the SDK is used in this codebase.

6. **Decision: live vs cached `list_visible_channels`** — DD §10 names `enumerate_discoverable_entities` as the source; the F3 cache via `_get_account_cache_snapshot` is the natural read path. Prefer cache (faster, doesn't hit rate limits); fall back to live hook only if the snapshot's cache is None. Document the choice in the tool's docstring.

7. **Add tests** in `tests/test_connector_history_tools.py`. Mirror the `test_connector_send_tool.py` fixture pattern. Extend the stub plugin (or define a local stub subclass) with `fetch_history` / `fetch_dm_history` / `enumerate_discoverable_entities` implementations that return canned data. The "missing hook" tests use the base StubPlugin (no implementations).

8. **Run targeted tests**, then full suite. Update flight log under `## Leg Progress` with `### L10 — channel-context-tools`. Check off in flight.md. Set L10 status to `landed`. Do NOT commit.

## Edge Cases

- **Tool invoked outside a connector-attached session** — `current_chat_session_id` is None → tool returns the outside-connector error dict. The LLM may have hallucinated calling the tool in a non-connector context.
- **Session has no `connector_account_id`** — same shape: tool returns outside-connector error (defensive against malformed session rows).
- **Plugin's `fetch_history` raises** — tool catches and returns `[{"error": "..."}]`. The agent sees the error but the dispatcher's flow is unaffected.
- **`list_visible_channels` with a populated cache that's stale** — the tool returns the stale data; the operator can run "Refresh" in the connector account editor to force a refresh. L10 doesn't trigger refreshes; that's a separate UI concern (L11 or later).
- **`limit > 100` for Discord history** — `discord.py` accepts large limits but the API may rate-limit. The tool passes the limit through verbatim; the plugin's exception handler catches rate-limit errors and returns them as error dicts.
- **`thread_id` for a non-thread message** — `fetch_thread_history` with a `thread_id` that doesn't exist returns whatever Discord returns (likely empty or 404 error caught and returned as error dict).
- **`peer_id` for an unknown user** — `fetch_dm_history` may raise from `fetch_user(...)`. Caught and returned as error dict.
- **Per-agent ACL with `peers=[]`** — cycle-1 review correction: `peers=[]` is NOT a DMs-only sentinel for peers (only `channels=[]` is the DMs-only sentinel per `_acl.py:32-37` module docstring). `peers=[]` means "explicitly no peers admitted." Therefore:
  - `fetch_dm_history` with `peers=[]` → DENY (no peers allowed at all).
  - `fetch_channel_history` with `channels=[]` → DMs-only sentinel applies; deny for channel reads (the agent has no channel access).
  - `fetch_thread_history` with `channels=[]` → same as channel; deny.
- **Per-agent ACL with `peers=None`** — inherits account-scope; check `account.config["allowlist"]["peers"]` before admitting.
- **L9's directive "if available" hedge** — KEPT after L10. The tools ARE available now for Discord, but plugin-agnosticism keeps the hedge truthful for future plugins. Do NOT update the directive in L10.
- **Test isolation** — the existing fixture pattern (`_clear_pool_and_registry`, `_reset_stub_state`) resets pool + registry between tests. L10's tests rely on this hygiene; do not skip the fixtures.

## Files Affected

- `the_one/connectors/base.py` — ADD `FetchedMessage` dataclass.
- `the_one/tools/connector_history.py` — NEW file with four tool classes + helpers.
- `the_one/tools/builtins.py` — REGISTER four new tools + extend `get_tools` to inject kwargs.
- `the_one/connectors/_discord.py` — ADD `DiscordPlugin.fetch_history` + `DiscordPlugin.fetch_dm_history`.
- `tests/test_connector_history_tools.py` — NEW file with 22 tests (5+5+5+4+1+2 = 22 per the Outputs enumeration after cycle-1 additions).
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND L10 entry.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (targeted + full suite)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md
- [ ] Commit all changes — DEFERRED per F7 flight-level commit ordering.

## Citation Audit

Citations verified against current code at design time via the F7 L10 reconnaissance pass:

- `the_one/tools/builtins.py:_TOOL_CLASSES:40-61` — built-in tool registration dict (verified).
- `the_one/tools/builtins.py:BuiltinToolProvider.get_tools:159-166` — kwarg injection for connector tools (verified).
- `the_one/tools/connector_send.py:SendToPlatformChannelTool:47-208` — precedent for tool shape (verified).
- `the_one/agent/_context.py:current_chat_session_id:45-46` — ContextVar definition (verified).
- `the_one/connectors/_acl.py:admits_outbound:105-186` — channel-axis ACL admission (verified).
- `the_one/connectors/_pool.py:account_acquire:830-848` — client acquisition (verified).
- `the_one/connectors/_pool.py:_get_account_cache_snapshot` — discoverable cache read (verified, L3 precedent).
- `the_one/connectors/base.py:DiscoverableEntities:437-486` — return type for `enumerate_discoverable_entities` (verified).
- `the_one/connectors/_discord.py:DiscordClient:309-470` — Discord SDK wrapping site (verified).
- L9's `_CONNECTOR_AUTO_RELAY_DIRECTIVE` forward-references at `agent/config.py:78-105` (verified).

Recon flagged the ACL-peer-axis question for the Developer agent to resolve at impl time (whether `admits_outbound` covers peers or a peer-specific helper is needed).
