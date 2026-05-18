# Leg: platform-send-tool

**Status**: completed
**Flight**: [Platform-Send Built-in Tool and Outbound Routing](../flight.md)

## Objective

Land `SendToPlatformChannelTool` as a new built-in tool that takes a target (account_id + channel_id + optional thread_id) and content, validates the target against the agent's attached connector accounts (`AgentConfig.connector_account_ids` — landed in leg 1), acquires a `ConnectorClient` from the F1 pool, calls `client.send(...)` (the Protocol method widened in leg 1), and returns either a success-prefixed result string or a standard `[error] ...` envelope. Register the tool in `_TOOL_CLASSES` so it appears in the existing built-in-tools admin grid (operator enable/disable via `/api/tools/configs/send_to_platform_channel` — no new UI). Widen `BuiltinToolProvider.get_tools` with a case-discrimination branch so the factory can pass per-agent attached account ids into the tool at construction. Leg 3 wires the factory to actually pass the kwarg + the F10 baseline carve-out; leg 2 establishes the tool + its plumbing.

## Context

- **Parent flight design decisions** (see `flight.md` "Design Decisions"):
  - **Tool target validation scope**: F4 validates `target.account_id ∈ self._connector_account_ids` (account-scope). Channel/thread/peer ACLs are F6's `AllowlistResolver` Protocol. Leg 2 leaves a single-line `# F6: AllowlistResolver consultation lands here` marker that F6's diff replaces.
  - **Auto-load mechanism for the F10 baseline carve-out is a LEG 3 concern**. Leg 2 ships the tool class and registers it in `_TOOL_CLASSES`; leg 3's `AgentFactory.create()` decides whether to pre-populate `loaded_schemas` based on `(connector_attached AND tool_enabled)`. The two-step split keeps each leg atomic.
  - **Tool name**: `send_to_platform_channel` (verbatim from mission text).
  - **`SendToPlatformChannelTool.__init__` zero-arg compatibility** (architect-flagged in flight design review): all four kwargs default to `None`. Required because `BuiltinToolProvider.get_tools` at `the_one/tools/builtins.py:104-105` calls `[cls() for cls in _TOOL_CLASSES.values()]` on the introspection path. If `__init__` required `connector_account_ids`, `/api/tools` would 500 the moment the tool is registered.
  - **`BuiltinToolProvider.get_tools` widening shape**: keep the public signature backward-compatible by adding `connector_account_ids: list[str] | None = None` as a keyword-only argument. Inside the factory-path loop, use a `case-discrimination` branch (`if cls is SendToPlatformChannelTool: extra = {...} else: extra = {}`) and unpack the extra kwargs. Mirrors how `SearchTools` is constructed with extra args (`on_match`, `registry`, `source_index`, `agent_name`) at `the_one/agent/factory.py:290-297`, kept inside the provider here for symmetry with the rest of `_TOOL_CLASSES`.
  - **Success sentinel string**: returns `f"{PLATFORM_SEND_OK_PREFIX} sent to {account_id}:{channel_id}{thread_clause}: {content!r} (msg_id={result.platform_message_id})"`. `thread_clause` is `f' (thread {thread_id})'` or empty. `content!r` Python repr-escapes embedded brackets so a peer-supplied `[platform-send-ok]`-like content cannot cause cross-pollination of the dispatcher's visibility-tag matcher (architect-flagged attack-surface argument; leg 5 adds the failure-envelope-prefix sanity test).
  - **Failure envelope shape**: `f"[error] [constraint] {msg}"` for target-validation failures (mirrors `ConstraintError`-formatting pattern in existing tools like `the_one/tools/web.py:HttpRequestTool.execute`). `f"[error] {type(exc).__name__}: {exc}"` for `ConnectorClientError` subtypes raised by the pool or `client.send`. Verbatim format strings — operator-readable AND grep-stable.

- **F1 pool's `acquire` signature** (`the_one/connectors/_pool.py:407 — "async def acquire(agent_name: str, account_id: str) -> ConnectorClient:"`): takes `(agent_name, account_id)`, returns a `ConnectorClient`. May raise:
  - `RuntimeError("Connector pool is shutting down")` if `_shutting_down`
  - `KeyError` (from `_load_account`) if the account doesn't exist in the repository
  - `ConnectorRegistrationError` (from `_resolve_plugin`) if the account's `type` isn't in the registry
  - Any `ConnectorClientError` subtype propagated from `plugin.connect(...)` (e.g. `ConnectorConfigError`, `ConnectorConnectionError`, `ConnectorAuthRequired`)
  - F3's dispatcher at `the_one/connectors/_inbound.py:36 — "from the_one.connectors._pool import acquire as pool_acquire"` is the precedent — same import shape, same exception-catching idioms.

- **Operator enable/disable surface**: the existing built-in-tools admin grid at `the_one/interfaces/web/static/js/areas/admin/tools-grid.js` renders an enable toggle for every name in `_TOOL_CLASSES` via `/api/tools/configs`. Once `send_to_platform_channel` is registered in `_TOOL_CLASSES`, the toggle appears automatically. **No new UI in this leg**.

- **`Tool.Config = _EmptyConfig`**: the operator enable/disable is a tool-row-level concern handled by `ToolConfigRepository.enabled` (consumed by the factory's `disabled_names` filter at `the_one/agent/factory.py:241,301`), NOT a `Config`-field concern. The tool has zero operator-tunable policy fields, so `Config = _EmptyConfig`. Leg 3 reads `ToolConfigRepository.get("send_to_platform_channel").enabled` to gate the F10 carve-out.

- **F6 ACL hook point** (documented inline in `SendToPlatformChannelTool.execute()`): after target-account validation passes, before pool acquire. F6's `AllowlistResolver` Protocol consultation will check whether the agent is permitted to post into `(account_id, channel_id, thread_id)`. F4 ships the comment marker only; F6's diff replaces it with the resolver call.

- **Architect-flagged sanity test** (the literal-prefix sentinel attack-surface argument): a peer-supplied `content` of `"[platform-send-ok] fake"` is interpolated via Python `repr()` (`{content!r}` → `'[platform-send-ok] fake'` with quotes/escapes), so the dispatcher's `startswith(PLATFORM_SEND_OK_PREFIX)` check only matches the literal first 18 chars at position 0 — the embedded one is at position ~20. The fragility risk is operator-facing (a future flight changing the failure envelope to also start with `[platform-send-ok]` would silently corrupt the visibility-tagger), NOT peer-facing. Mitigation lives in leg 2 as a sanity test: `tool.execute(...failure path...) does NOT start with PLATFORM_SEND_OK_PREFIX`.

- **Import topology**: `the_one/tools/connector_send.py` (new) will import `from the_one.connectors._pool import acquire as pool_acquire` at module top. Verified import-safe: `the_one/connectors/_pool.py` top-level imports `connectors.base`, `connectors.errors`, `connectors.registry` (no `tools/` or `agent/` reachout); the `db.connection` / `db.repositories` imports inside `_pool` are function-local (per `function-local-import-to-break-load-cycle` convention). `the_one/tools/builtins.py` will newly import `from the_one.tools.connector_send import SendToPlatformChannelTool` at module top — no new cycle, since `connector_send` doesn't reach back into `tools/` or `agent/`.

- **No prior consumers of `SendToPlatformChannelTool` exist** (this leg introduces the class). Grep-confirmed: no test or source file currently imports the class.

- **F6 ACL test fixture** — `tests/test_connector_send_tool.py` (new this leg) tests target validation, pool dispatch, and error envelopes. F5's Chat-UI work and F6's allowlist work consume `connector_account_ids` and ACLs respectively — neither breaks leg 2.

## Inputs

State that must exist before this leg runs:

- F4 branch `flight/04-platform-send-tool-and-outbound` checked out; leg 1 work uncommitted on the branch (per agentic-workflow batched-review).
- `the_one/agent/config.py:AgentConfig` has `connector_account_ids: list[str] = Field(default_factory=list)` (leg 1 output).
- `the_one/connectors/base.py:ConnectorClient.send(target, content) -> SendResult` is on the Protocol (leg 1 output).
- `the_one/connectors/base.py:SendResult` frozen dataclass exists (leg 1 output).
- `the_one/connectors/__init__.py:PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"` is exported (leg 1 output).
- `the_one/connectors/_stub.py:StubClient.send` is implemented and records via `StubPlugin.record_outbound` (leg 1 output). `StubPlugin.send_should_raise` ClassVar exists for failure injection (leg 1 output).
- `the_one/connectors/_pool.py:407 — "async def acquire(agent_name: str, account_id: str) -> ConnectorClient:"` — extant pool entry-point.
- `the_one/connectors/errors.py` defines the 6 typed exceptions (`ConnectorClientError`, `ConnectorConfigError`, `ConnectorConnectionError`, `ConnectorAuthRequired`, `ConnectorRegistrationError`, `ConnectorRateLimitError`) — extant since F1.
- `the_one/tools/base.py:Tool` base class with `__init__(self, config=None, cross_configs=None, agent_name=None)` signature — extant since F2.
- `the_one/tools/base.py:ConstraintError` exception — extant since F2.
- `the_one/tools/resolver.py:_EmptyConfig` — extant since F2.
- `the_one/tools/builtins.py:_TOOL_CLASSES` — extant 19-entry dict (lines 37-57); leg 2 adds the 20th entry.
- `the_one/tools/builtins.py:BuiltinToolProvider.get_tools` — extant signature `(self, tool_configs, agent_overrides, agent_name)` (lines 95-148); leg 2 widens with `connector_account_ids` kwarg.
- `the_one/tools/builtins.py:104-105 — "if tool_configs is None and agent_overrides is None: return [cls() for cls in _TOOL_CLASSES.values()]"` — introspection-path zero-arg construction; the new tool's `__init__` MUST accept `cls()` with no args.
- `the_one/connectors/__init__.py:OPERATOR_VISIBILITY` and `PLATFORM_SEND_OK_PREFIX` available for import.

## Outputs

State that must exist after this leg completes:

- New module `the_one/tools/connector_send.py` defines `SendToPlatformChannelTool(Tool)` with:
  - `name = "send_to_platform_channel"`
  - `description` — operator-facing text explaining the tool's purpose AND that plain-text replies do NOT auto-route to the platform (only invocations of this tool deliver to peers).
  - `parameters` — JSON Schema: `target` object with `account_id` (string, required), `channel_id` (string, required), `thread_id` (string|null, optional); `content` (string, required).
  - `Config = _EmptyConfig`.
  - `__init__(self, config=None, cross_configs=None, agent_name=None, connector_account_ids: list[str] | None = None)` — all-None defaults; stores `self._connector_account_ids = connector_account_ids or []`. Calls `super().__init__(config, cross_configs, agent_name)`.
  - `async def execute(self, target: dict, content: str) -> str` implementing the validation → F6 hook → pool acquire → `client.send` → return-success-or-error pipeline.
- `the_one/tools/builtins.py:_TOOL_CLASSES` gains a new entry `"send_to_platform_channel": SendToPlatformChannelTool`. Place at end of dict (after `"web_search": WebSearchTool` at L57).
- `the_one/tools/builtins.py:BuiltinToolProvider.get_tools` signature widened with a keyword-only `connector_account_ids: list[str] | None = None` parameter. Body's factory-path loop uses case-discrimination:
  ```python
  extra_kwargs: dict[str, Any] = (
      {"connector_account_ids": connector_account_ids or []}
      if cls is SendToPlatformChannelTool
      else {}
  )
  result.append(cls(cfg, cross_configs=cross_configs, agent_name=agent_name, **extra_kwargs))
  ```
  The introspection-path branch (`if tool_configs is None and agent_overrides is None: return [cls() for cls in _TOOL_CLASSES.values()]`) is unchanged — zero-arg construction works because the tool's `__init__` defaults all kwargs.
- New test file `tests/test_connector_send_tool.py` covers:
  - **Registry presence**: `"send_to_platform_channel"` is in `_TOOL_CLASSES`; mapped to `SendToPlatformChannelTool`.
  - **Zero-arg construction (introspection path)**: `SendToPlatformChannelTool()` does not raise; `tool.name == "send_to_platform_channel"`; `tool._connector_account_ids == []`.
  - **`BuiltinToolProvider.get_tools` introspection path** (`provider.get_tools()` zero-arg) returns a list including a `SendToPlatformChannelTool` instance — `/api/tools` shape preserved.
  - **`BuiltinToolProvider.get_tools` factory path** (`provider.get_tools({}, {}, agent_name="a", connector_account_ids=["acc-1"])`) constructs the tool with `_connector_account_ids == ["acc-1"]` and `_agent_name == "a"`.
  - **Target validation — malformed target**: `target` not a dict, missing `account_id`, missing `channel_id`, non-string `account_id`/`channel_id` → return `[error] ...` envelope; does NOT call pool.
  - **Target validation — unattached account_id**: tool constructed with `connector_account_ids=["acc-A"]`; `execute(target={"account_id": "acc-B", "channel_id": "c1"}, content="x")` → returns `[error] [constraint] account_id 'acc-B' is not attached to this agent`; does NOT call pool.
  - **Pool dispatch happy path**: stub plugin registered for the test; stub account in the DB; tool constructed with `connector_account_ids=[stub_account_id]` and `agent_name="test-agent"`; `execute(target={"account_id": stub_account_id, "channel_id": "c1"}, content="hello peers")` → returns a string starting with `PLATFORM_SEND_OK_PREFIX`; `StubPlugin.outbound_records` contains `(OutboundTarget(channel_id="c1", thread_id=None), "hello peers")`.
  - **Pool dispatch with `thread_id`**: `target={"account_id": ..., "channel_id": "c1", "thread_id": "t1"}` → `OutboundTarget(channel_id="c1", thread_id="t1")` recorded; success string includes `(thread t1)`.
  - **Pool acquire failure — unknown account**: `target.account_id` IS in the tool's allowed list but the account does NOT exist in the repository (registered in `connector_account_ids` but not persisted) → pool raises `KeyError` → tool returns `[error] KeyError: ...`; no outbound recorded.
  - **Pool acquire failure — unknown plugin type**: stub account in the DB AND `registry.clear_for_test()` called at the START of the test body to ensure the registry is empty for this scenario → pool raises `ConnectorRegistrationError` → tool returns `[error] ConnectorRegistrationError: ...`; no outbound recorded. The autouse `restore_to_baseline_for_test` runs at teardown of the previous test, not at setup of this one — so unconditional `clear_for_test()` at test-body start is the correct shape.
  - **`client.send` failure — rate limit**: `StubPlugin.send_should_raise = ConnectorRateLimitError("retry after 60s", retry_after=60)` → tool returns `[error] ConnectorRateLimitError: ...`; no outbound recorded.
  - **`client.send` failure — connection error**: `StubPlugin.send_should_raise = ConnectorConnectionError("gateway closed")` → tool returns `[error] ConnectorConnectionError: ...`.
  - **Failure-envelope sanity (architect-flagged)**: every failure-path return string is asserted to NOT start with `PLATFORM_SEND_OK_PREFIX`. Locks the dispatcher's visibility-tagging contract against accidental corruption by a future failure-envelope change.
  - **Content interpolation does NOT echo the prefix**: tool constructed with `connector_account_ids=[stub_account_id]`; `execute(content="[platform-send-ok] fake")` → success path produces a string containing `PLATFORM_SEND_OK_PREFIX` at position 0, AND the peer-supplied substring is properly `repr()`-escaped (e.g. `'[platform-send-ok] fake'` with surrounding quotes/escapes from `f"{content!r}"`).
- Flight log gains a "Leg Progress: platform-send-tool" entry.
- Leg status flipped to `landed` in this file's header. Do NOT commit.

## Acceptance Criteria

- [ ] `the_one/tools/connector_send.py` exists, exporting `SendToPlatformChannelTool(Tool)`.
- [ ] `SendToPlatformChannelTool.name == "send_to_platform_channel"`.
- [ ] `SendToPlatformChannelTool.parameters` is a JSON Schema with `target` object (required `account_id`, `channel_id`; optional `thread_id`) and `content` (string, required).
- [ ] `SendToPlatformChannelTool.Config is _EmptyConfig`.
- [ ] `SendToPlatformChannelTool.__init__` accepts zero args (`cls()` does not raise) AND accepts `connector_account_ids: list[str] | None = None` as a keyword argument. Stores it as `self._connector_account_ids = connector_account_ids or []` (None becomes empty list).
- [ ] `SendToPlatformChannelTool` is in `_TOOL_CLASSES` with key `"send_to_platform_channel"`.
- [ ] `BuiltinToolProvider.get_tools` signature includes a keyword-only `connector_account_ids: list[str] | None = None` parameter.
- [ ] `BuiltinToolProvider.get_tools()` (zero-arg introspection path) returns a list containing a `SendToPlatformChannelTool` instance.
- [ ] `BuiltinToolProvider.get_tools({}, {}, agent_name="a", connector_account_ids=["acc-1"])` constructs the platform-send tool with `_connector_account_ids == ["acc-1"]`.
- [ ] `execute(target={...malformed...}, content="x")` returns a string starting with `[error]` and does NOT call the pool. Test all four malformed cases (non-dict, missing `account_id`, missing `channel_id`, non-string `account_id`/`channel_id`).
- [ ] `execute(target={"account_id": <unattached>, "channel_id": "c1"}, content="x")` returns `[error] [constraint] account_id '<unattached>' is not attached to this agent`. Does NOT call the pool.
- [ ] Happy path: `execute(target={"account_id": <attached_stub>, "channel_id": "c1"}, content="hello")` returns a string starting with `PLATFORM_SEND_OK_PREFIX`; `StubPlugin.outbound_records` captures `(OutboundTarget(channel_id="c1", thread_id=None), "hello")`.
- [ ] With `thread_id`: `execute(target={..., "thread_id": "t1"}, content="x")` records `OutboundTarget(channel_id=..., thread_id="t1")` and the success string contains `(thread t1)`.
- [ ] Pool's `KeyError` (unknown account_id): tool returns `[error] KeyError: ...`. No outbound.
- [ ] Pool's `ConnectorRegistrationError` (unregistered plugin type): tool returns `[error] ConnectorRegistrationError: ...`. No outbound.
- [ ] `client.send` raises `ConnectorRateLimitError`: tool returns `[error] ConnectorRateLimitError: ...`. No outbound recorded.
- [ ] `client.send` raises `ConnectorConnectionError`: tool returns `[error] ConnectorConnectionError: ...`.
- [ ] Sanity: every failure-path return string does NOT start with `PLATFORM_SEND_OK_PREFIX`. Locks the literal-prefix sentinel contract for the dispatcher's visibility-tagger.
- [ ] Content interpolation: `execute(content="[platform-send-ok] fake")` on the happy path produces a string starting with `PLATFORM_SEND_OK_PREFIX` AT POSITION 0; the peer's bracketed substring appears later, repr-escaped.
- [ ] F6 ACL hook-point comment is present in `execute()` body between target-account validation and pool acquire.
- [ ] `docker exec the-one pytest tests/test_connector_send_tool.py -x --timeout 30` passes.
- [ ] `docker exec the-one pytest tests/test_builtins.py -x --timeout 30` passes — the existing built-in-tools tests are NOT regressed by the new tool entry.
- [ ] `docker exec the-one pytest tests/test_api_tool_configs.py -x --timeout 30` passes — the `/api/tools/configs` admin grid surface now lists `send_to_platform_channel` automatically (verify the new entry shows `enabled=True` and `config={}` by default).
- [ ] `docker exec the-one pytest -x --timeout 30` (full suite) passes. No regression in F1 pool, F2 admin, F3 dispatcher, or leg-1 tests.
- [ ] `docker exec the-one ruff check the_one tests` clean.
- [ ] Flight log gains a "Leg Progress: platform-send-tool" entry; this file's `**Status**` → `landed`.

## Verification Steps

- `docker exec the-one pytest tests/test_connector_send_tool.py -v -x --timeout 30` — every new test passes; ~15 tests expected.
- `docker exec the-one pytest tests/test_builtins.py tests/test_api_tool_configs.py -x --timeout 30` — no regression on existing built-in-tools and admin-grid tests; the new tool surfaces correctly in `/api/tools/configs`.
- `docker exec the-one pytest -x --timeout 30` — full suite green. F1/F2/F3 tests + leg-1 tests + new leg-2 tests all pass.
- `docker exec the-one ruff check the_one tests` — clean.
- `grep -n "send_to_platform_channel" the_one/tools/builtins.py` — exactly one match (the new `_TOOL_CLASSES` entry).
- `grep -rn "SendToPlatformChannelTool" the_one/ tests/` — at least: import in builtins.py, class def in connector_send.py, test imports in test_connector_send_tool.py.
- `python3 -c "from the_one.tools.connector_send import SendToPlatformChannelTool; t = SendToPlatformChannelTool(); print(t.name, t._connector_account_ids)"` (or its docker-exec equivalent) — prints `send_to_platform_channel []` without raising.

## Implementation Guidance

1. **Create the new module `the_one/tools/connector_send.py`**:

   ```python
   """Built-in platform-send tool — the agent-side outbound entry point.

   Mission 10 Flight 4 Leg 2. Registered in :data:`the_one.tools.builtins._TOOL_CLASSES`
   so it surfaces in the existing built-in-tools admin grid; operator
   enable/disable lives at :class:`ToolConfigRepository.enabled`.

   The tool delivers content to the external platform via the F1 pool's
   ``acquire`` → ``client.send`` path. Validation in :meth:`execute`
   covers shape (the JSON Schema layer is permissive at the LLM boundary
   but defensive validation here protects the pool from malformed inputs)
   and account-scope (`target.account_id` must be in the agent's attached
   set). Channel/thread/peer ACLs are F6 territory — see the inline
   ``# F6:`` marker.

   Success returns a :data:`PLATFORM_SEND_OK_PREFIX`-prefixed string that
   the F4-leg-4 dispatcher visibility-tagger consumes to decide
   ``visibility=None`` on the tool_result message. Failure returns a
   standard ``[error] ...`` envelope.
   """

   from __future__ import annotations

   from typing import Any

   from the_one.connectors import PLATFORM_SEND_OK_PREFIX
   from the_one.connectors._pool import acquire as pool_acquire
   from the_one.connectors.base import OutboundTarget
   from the_one.connectors.errors import ConnectorClientError, ConnectorRegistrationError
   from the_one.tools.base import Tool


   class SendToPlatformChannelTool(Tool):
       """Send a message to the external platform conversation this agent
       is attached to via a connector account."""

       name = "send_to_platform_channel"
       description = (
           "Send a message to the external platform conversation this "
           "agent is attached to (Discord, Slack, etc. via the configured "
           "connector account). Use this to reply to peer messages on the "
           "platform. Your plain-text replies in this session do NOT "
           "auto-reach the platform — only invocations of this tool "
           "deliver content to peers. The target identifies the "
           "destination (account_id from the attached set, channel_id "
           "from the inbound you're responding to, and an optional "
           "thread_id for thread-scoped replies)."
       )
       parameters = {
           "type": "object",
           "properties": {
               "target": {
                   "type": "object",
                   "properties": {
                       "account_id": {
                           "type": "string",
                           "description": (
                               "The connector account id to send through. "
                               "Must be one of the accounts attached to "
                               "this agent."
                           ),
                       },
                       "channel_id": {
                           "type": "string",
                           "description": (
                               "Platform-native channel id (Discord "
                               "channel snowflake, Slack channel id). "
                               "Typically copied from the inbound "
                               "envelope this reply responds to."
                           ),
                       },
                       "thread_id": {
                           "type": ["string", "null"],
                           "description": (
                               "Optional thread id for thread-scoped "
                               "replies. Null/absent posts in the channel."
                           ),
                       },
                   },
                   "required": ["account_id", "channel_id"],
               },
               "content": {
                   "type": "string",
                   "description": "The message body to deliver.",
               },
           },
           "required": ["target", "content"],
       }

       def __init__(
           self,
           config: Any = None,
           cross_configs: dict[type, object] | None = None,
           agent_name: str | None = None,
           connector_account_ids: list[str] | None = None,
       ) -> None:
           # All four kwargs default to None so `cls()` works on the
           # `/api/tools` introspection path (BuiltinToolProvider.get_tools
           # at builtins.py:104-105 constructs every tool zero-arg there).
           super().__init__(config, cross_configs, agent_name)
           self._connector_account_ids: list[str] = connector_account_ids or []

       async def execute(self, target: Any = None, content: Any = None, **_extra: Any) -> str:  # type: ignore[override]
           # `**_extra` defensively accepts unexpected kwargs from the LLM
           # tool-call dispatch — silently ignored. Matches the web/filesystem
           # tool convention; harder against schema-vs-call-time drift.
           # ── Target-shape validation ────────────────────────────────
           if not isinstance(target, dict):
               return "[error] target must be an object with account_id and channel_id"
           account_id = target.get("account_id")
           channel_id = target.get("channel_id")
           if not isinstance(account_id, str) or not account_id:
               return "[error] target.account_id must be a non-empty string"
           if not isinstance(channel_id, str) or not channel_id:
               return "[error] target.channel_id must be a non-empty string"
           thread_id = target.get("thread_id")
           if thread_id is not None and not isinstance(thread_id, str):
               return "[error] target.thread_id must be a string or null"
           # Coerce empty-string thread_id to None — operator intent is
           # "no thread" and downstream platforms reject empty thread ids.
           thread_id = thread_id or None
           if not isinstance(content, str):
               return "[error] content must be a string"

           # ── Account-scope validation ───────────────────────────────
           if account_id not in self._connector_account_ids:
               return (
                   f"[error] [constraint] account_id {account_id!r} is "
                   f"not attached to this agent"
               )

           # F6: AllowlistResolver consultation lands here.
           # F4 ships account-scope validation only; per-channel/thread/peer
           # ACLs are F6 territory. The resolver call replaces this comment
           # and short-circuits to an [error] [constraint] envelope on deny.

           # ── Pool acquire + client.send ─────────────────────────────
           try:
               client = await pool_acquire(self._agent_name or "", account_id)
           except (KeyError, ConnectorRegistrationError, ConnectorClientError, RuntimeError) as exc:
               return f"[error] {type(exc).__name__}: {exc}"

           target_obj = OutboundTarget(channel_id=channel_id, thread_id=thread_id)
           try:
               result = await client.send(target_obj, content)
           except ConnectorClientError as exc:
               return f"[error] {type(exc).__name__}: {exc}"

           thread_clause = f" (thread {thread_id})" if thread_id else ""
           return (
               f"{PLATFORM_SEND_OK_PREFIX} sent to "
               f"{account_id}:{channel_id}{thread_clause}: "
               f"{content!r} (msg_id={result.platform_message_id})"
           )
   ```

2. **Register the tool in `the_one/tools/builtins.py`**:

   - Add the import at the appropriate place in the import block (after `the_one.tools.shell` and before `the_one.tools.web` for alphabetical order; or append at end — match the existing convention in builtins.py):
     ```python
     from the_one.tools.connector_send import SendToPlatformChannelTool
     ```
   - Add the dict entry at the end of `_TOOL_CLASSES` (after `"web_search": WebSearchTool` at line 57):
     ```python
     "send_to_platform_channel": SendToPlatformChannelTool,
     ```
     Decision: place at end of dict, not alphabetically-sorted, because:
     - `_TOOL_CLASSES` is iterated in declared order to produce admin-grid display order; tail-placement keeps the new tool visually separate from the existing categorized clusters (filesystem block, sessions block, web block).
     - The provider's cross_configs build walks `_TOOL_CLASSES.items()` once in declared order resolving each distinct `cls.Config`. Tail-placement means `SendToPlatformChannelTool`'s `_EmptyConfig` is encountered AFTER all the real-Config tools — no risk of breaking existing tool resolution.

   **Mandatory test-fixture updates triggered by the new entry** (architect-flagged hardcoded count assertions):
   - `tests/test_builtins.py:56` — change `assert len(zero_arg) == 19` to `== 20`.
   - `tests/test_builtins.py:63` — change `assert len(tools) == 19` to `== 20`.
   - `tests/test_builtins.py:65-85` — extend the name-set with `"send_to_platform_channel",`.
   - `tests/test_builtins.py:110` — change `assert len(tools) == 19` to `== 20`.
   - `tests/test_builtins.py:54,60,105-107` — update the comments mentioning "19 tools" to "20 tools".
   - `tests/test_api_tool_configs.py:51` — rename `test_list_configs_returns_all_19_tools` to `test_list_configs_returns_all_20_tools`.
   - `tests/test_api_tool_configs.py:59` — change `assert len(rows) == len(_TOOL_CLASSES) == 19` to `== 20`.
   - These updates are part of leg 2's acceptance criteria — without them the existing tests fail the moment the new entry is added.

3. **Widen `BuiltinToolProvider.get_tools`**:

   - Update the signature (around line 95):
     ```python
     def get_tools(
         self,
         tool_configs: dict[str, dict] | None = None,
         agent_overrides: dict[str, dict] | None = None,
         agent_name: str | None = None,
         *,
         connector_account_ids: list[str] | None = None,
     ) -> list[Tool]:
     ```
     `connector_account_ids` is **keyword-only** (after `*`) so positional callers don't break; the existing one-arg / no-arg paths remain unchanged.
   - In the factory-path loop body (currently lines 137-148), modify to:
     ```python
     result: list[Tool] = []
     for name, cls in _TOOL_CLASSES.items():
         cfg = resolve(
             cls.Config,
             tool_configs.get(name),
             agent_overrides.get(name),
         )
         # F4 leg 2: SendToPlatformChannelTool needs the agent's attached
         # connector-account ids at construction. Mirrors the
         # SearchTools special construction at factory.py:290-297, kept
         # inside the provider for _TOOL_CLASSES symmetry.
         extra_kwargs: dict[str, Any] = (
             {"connector_account_ids": connector_account_ids or []}
             if cls is SendToPlatformChannelTool
             else {}
         )
         result.append(
             cls(cfg, cross_configs=cross_configs, agent_name=agent_name, **extra_kwargs)
         )
     return result
     ```
   - Add the `SendToPlatformChannelTool` import (already in the file's import block from step 2) — needed for the `cls is SendToPlatformChannelTool` identity check.
   - **Do NOT touch the introspection branch at L104-105**: `if tool_configs is None and agent_overrides is None: return [cls() for cls in _TOOL_CLASSES.values()]` continues to work zero-arg because `SendToPlatformChannelTool.__init__` accepts all-None kwargs.

4. **Add `Any` to the imports of `builtins.py`** if not already present — the `extra_kwargs` annotation requires it. Verify by reading the existing import block.

5. **Create `tests/test_connector_send_tool.py`**:

   The test file follows the project's existing async-test patterns (see `tests/test_connectors_inbound.py` for the `acquire`-touching test fixture pattern and `tests/test_connectors_e2e.py` for the stub-plugin-driven e2e shape). Imports:

   ```python
   import dataclasses
   import pytest

   from the_one.connectors import PLATFORM_SEND_OK_PREFIX
   from the_one.connectors._stub import StubPlugin
   from the_one.connectors.base import OutboundTarget
   from the_one.connectors.errors import (
       ConnectorConnectionError,
       ConnectorRateLimitError,
   )
   from the_one.tools.builtins import BuiltinToolProvider, _TOOL_CLASSES
   from the_one.tools.connector_send import SendToPlatformChannelTool
   ```

   Test structure: pytest fixtures are module-scoped by default — fixtures defined in `tests/test_connectors_inbound.py` (`isolated_db`, `_seed_stub_account`, autouse `_reset_stub_state`, autouse `_clear_pool_locks_registry` at L40-160) are NOT importable across test files. The leg-2 author MUST either:
   - **Replicate the needed fixtures verbatim into `test_connector_send_tool.py`** — the F3 debrief flagged "extract leg-4 + leg-6 test helpers to `tests/_connector_dispatch_helpers.py`" as a leg-5 carry-forward action item. Leg 2 ships its own copy; leg 5 will extract.
   - **OR** factor them into a shared `tests/_connector_dispatch_helpers.py` proactively in leg 2. Either path is acceptable; the simpler call for atomic leg-scoping is replication-now-extract-in-leg-5.

   Key fixtures the leg-2 author will need:
   - `isolated_db` — isolated test database
   - `_seed_stub_account` — creates a `ConnectorAccount` of type `"stub"`
   - Stub plugin registration / cleanup via `register_for_test` + `restore_to_baseline_for_test`
   - `StubPlugin.reset_for_test()` between tests (autouse)
   - Pool lock + registry clearing between tests (autouse — see `tests/test_connectors_inbound.py:_clear_pool_locks_registry`)

   For tests that don't require pool dispatch (registry presence, target validation), no DB or pool setup is needed — just construct `SendToPlatformChannelTool(connector_account_ids=[...])` directly.

   **Important test correctness notes**:
   - Tests that exercise `pool_acquire` MUST use the F3-pattern fixtures (`isolated_db`, stub-account seeded in DB, `register_for_test("stub", StubPlugin)`). Otherwise `pool_acquire` will fail to load the account row OR fail to resolve the plugin.
   - `StubPlugin.send_should_raise` is set per-test on the class; the autouse fixture must clear it via `StubPlugin.reset_for_test()` to prevent leakage.
   - The "unknown account" test seeds NO account row but adds the account_id to the tool's `connector_account_ids` — the tool passes account-scope validation, then `pool_acquire` raises `KeyError` (from `_load_account` not finding the row). The tool should return `[error] KeyError: ...`.
   - The "unregistered plugin type" test seeds the account with `type="stub"` AND ensures the registry does NOT have `"stub"` registered (e.g. call `clear_for_test()` after the autouse fixture restored the baseline). The tool should return `[error] ConnectorRegistrationError: ...`.

6. **Run the targeted test file and then the full suite**:
   - `docker exec the-one pytest tests/test_connector_send_tool.py -x --timeout 30`
   - `docker exec the-one pytest tests/test_builtins.py tests/test_api_tool_configs.py -x --timeout 30` — verify no regression on existing built-in-tool tests and that the new tool surfaces in `/api/tools/configs`.
   - `docker exec the-one pytest -x --timeout 30` — full suite green.
   - `docker exec the-one ruff check the_one tests` — clean.

7. **Update the flight log** at `missions/.../04-platform-send-tool-and-outbound/flight-log.md` with a "Leg Progress: platform-send-tool" entry. Capture: files modified, test count delta from leg-1 baseline (1888), any deviations, any anomalies.

8. **Flip this leg's `**Status**` to `landed`**. Do NOT commit.

## Edge Cases

- **`self._agent_name` is None at execute time**: only possible if the tool is constructed via the introspection path (`/api/tools`) and then mis-used by code calling `execute()`. The current implementation passes `self._agent_name or ""` to `pool_acquire`, which will then fail to find any account under the empty-string agent key. The error envelope returned is `[error] KeyError: ...` — operator-readable. The factory path always passes a real `agent_name`, so production never hits this case. Acceptable; test optional.

- **`target.thread_id` provided but empty string `""`**: the validation treats empty string differently from None — `isinstance("", str)` is True, `"" is not None` is True. The `OutboundTarget(thread_id="")` would carry an empty string; downstream platforms may or may not accept it. Conservative call: treat `thread_id == ""` as "no thread" (coerce to None before constructing OutboundTarget). This matches operator intent and avoids surfacing a peer-supplied empty string to platform APIs. **Decision**: add `thread_id = thread_id or None` after the type-check to coerce empty-string to None.

- **`content` is empty string `""`**: pass through. The platform may reject empty messages (Discord does); the tool surfaces the platform's `ConnectorClientError` as the failure envelope. Not the tool's concern to pre-validate.

- **Pool's `RuntimeError("Connector pool is shutting down")`**: caught by the broad except clause; returns `[error] RuntimeError: Connector pool is shutting down`. Mid-shutdown sends fail-fast with a clear message.

- **`client.send` returns a `SendResult` with `platform_message_id=None`**: success string contains `(msg_id=None)` — operator-readable, no crash. Some platforms don't return ids.

- **Tool called via `BuiltinToolProvider.get_tools()` (zero-arg)**: zero-arg construction yields `self._connector_account_ids = []` and `self._agent_name = None`. All `execute()` calls with non-empty `target.account_id` fail account-scope validation. Introspection callers (`/api/tools`) don't call `execute()`; the schema-only access via `to_schema()` works.

- **Duplicate registration**: `_TOOL_CLASSES["send_to_platform_channel"] = SendToPlatformChannelTool` — single dict entry; no duplicate concern. If a future flight accidentally adds a second entry with the same key, the second wins (dict semantics) — would be caught at code review.

- **Concurrent `execute()` on the same tool instance**: each `execute()` is async-safe — `pool_acquire` is idempotent (single-spawn semantics on warm entries), `client.send` is per-call. Multiple concurrent sends from the same agent serialize at the F1 pool layer's worker task. Not a correctness concern for leg 2; leg 5's event-coordinated tests cover the e2e concurrency story.

## Files Affected

- `the_one/tools/connector_send.py` (new) — `SendToPlatformChannelTool` class
- `the_one/tools/builtins.py` — register in `_TOOL_CLASSES`; widen `BuiltinToolProvider.get_tools` with `connector_account_ids` kwarg + case-discrimination branch; add `Any` to imports if needed
- `tests/test_connector_send_tool.py` (new) — comprehensive tool tests
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/flight-log.md` — append leg-progress entry
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/legs/02-platform-send-tool.md` — flip status to `landed`

---

## Post-Completion Checklist

**Per agentic-workflow batched-review model: do NOT commit; defer to flight-end.**

- [ ] All acceptance criteria verified (run the Verification Steps above)
- [ ] Full test suite passes (`docker exec the-one pytest -x --timeout 30`)
- [ ] Lint clean (`docker exec the-one ruff check the_one tests`)
- [ ] Update `flight-log.md` with a "Leg Progress: platform-send-tool" entry
- [ ] Set this leg's `**Status**` to `landed` in this file's header
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director — do NOT commit, do NOT check off in flight.md, do NOT mark `completed`

---

## Citation Audit

All 13 code-location citations verified against current code at leg design time:

| Citation | Status | Evidence |
|---|---|---|
| `the_one/connectors/_pool.py:407 — "async def acquire(agent_name: str, account_id: str) -> ConnectorClient:"` | OK | Verified at L407 |
| `the_one/connectors/_inbound.py:36 — "from the_one.connectors._pool import acquire as pool_acquire"` | OK | Verified at L36 |
| `the_one/connectors/_inbound.py:93 (pool_acquire call site, error handling pattern)` | OK | Verified — pattern at L92-109 |
| `the_one/connectors/errors.py — 6 typed exceptions` | OK | Confirmed via F1 design |
| `the_one/connectors/base.py:OutboundTarget` | OK | Verified earlier (leg 1 audit) |
| `the_one/connectors/__init__.py:PLATFORM_SEND_OK_PREFIX` | OK | Leg 1 just landed it |
| `the_one/connectors/_stub.py:StubClient.send` | OK | Leg 1 just landed it |
| `the_one/connectors/_stub.py:StubPlugin.send_should_raise` | OK | Leg 1 just landed it |
| `the_one/tools/base.py:Tool` base class | OK | Verified earlier |
| `the_one/tools/base.py:ConstraintError` | OK | Verified earlier |
| `the_one/tools/resolver.py:_EmptyConfig` | OK | Verified earlier |
| `the_one/tools/builtins.py:_TOOL_CLASSES (lines 37-57, 19 entries)` | OK | Verified — 19 entries; leg 2 adds 20th |
| `the_one/tools/builtins.py:BuiltinToolProvider.get_tools (lines 95-148, signature + body)` | OK | Verified |
| `the_one/tools/builtins.py:104-105 — "if tool_configs is None and agent_overrides is None: return [cls() for cls in _TOOL_CLASSES.values()]"` | OK | Verified at L104-105 |
| `the_one/tools/builtins.py:137-148 (factory-path loop)` | OK | Verified |
| `the_one/agent/factory.py:290-297 (SearchTools special construction)` | OK | Verified earlier |
| `the_one/agent/factory.py:241,301 (ToolConfigRepository.enabled filter)` | OK | Verified earlier — `disabled_names` set built at L241; consulted at L301 |
| `the_one/tools/web.py:HttpRequestTool.execute (ConstraintError-formatting pattern)` | OK | Verified — `f"[error] [constraint] {e}"` shape consistent across web.py tools |
| `the_one/tools/_search_tools.py:148-174 (SearchTools class, the special-construction analog)` | OK | Verified at L148-174 — `__init__` takes `on_match`, `registry`, `source_index`, `agent_name` |
