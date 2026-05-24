# Leg: discord-outbound-adapter

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Fill in `DiscordClient.send(target, content)` — currently a placeholder raising `NotImplementedError("M10 F8 L5 lands the outbound adapter")` — to deliver a message via the discord.py SDK: resolve `target.channel_id` to a `discord.TextChannel` or `discord.Thread` via the SDK's `client.get_channel(id)` (or `fetch_channel(id)` if not cached), call `channel.send(content)`, and return a `SendResult(platform_message_id=str(message.id), details={...})`. Threads route via `target.thread_id` when set. Error envelopes match the F4 platform-send tool's existing error vocabulary so outbound failures surface cleanly through the agent loop.

## Context

L5 of F8. Per flight Design Decisions:

- **F4's `send_to_platform_channel` tool already drives outbound** — it calls `client.send(target, content)` against whatever `ConnectorClient` the pool returned. L5 just provides the Discord-specific concrete implementation. No new tool registration.
- **`discord.TextChannel.send(content)` / `Thread.send(content)`** are the SDK's send primitives. They return a `discord.Message` whose `.id` (snowflake int) becomes the `SendResult.platform_message_id`.
- **Channel resolution**: `client.get_channel(id)` reads from the SDK's local cache (instant); `client.fetch_channel(id)` makes an HTTP request (REST GET `/channels/{id}`). L5 prefers `get_channel` and falls back to `fetch_channel` on cache miss. If both return `None` / raise, the channel is genuinely unreachable → raise an exception that the F4 tool can translate to an error envelope.
- **Stateless plugin / per-connection state on client**: L5's `send` reads from `self._client` (the wrapped SDK Client) — no plugin-side state.
- **Thread vs channel target**: when `target.thread_id` is set, the L4-revised convention means `channel_id` is the parent's id and `thread_id` is the thread's id. L5 prefers fetching the thread directly (`client.get_channel(int(target.thread_id))` returns a `discord.Thread` when in a thread). If the resolved object is a `discord.Thread`, send there; otherwise fall back to the channel.

Key learnings from L1-L4:
- L3 wired the gateway connection and the on_ready/on_message event handlers; L5 reads from the same SDK client instance for outbound.
- L4 settled the channel_id/thread_id convention: parent channel id in `channel_id`, thread id in `thread_id`. L5's resolution logic mirrors this.

## Inputs

- `the_one/connectors/_discord.py` (post-L4) — `DiscordClient.send` is a placeholder raising `NotImplementedError`.
- `the_one/connectors/base.py:85-93` — `OutboundTarget` dataclass with `channel_id: str` and `thread_id: str | None`.
- `the_one/connectors/base.py:148-171` — `SendResult` dataclass with `platform_message_id: str | None` and `details: dict[str, Any]`.
- `the_one/connectors/_stub.py:52-69` — `StubClient.send` precedent (returns fixed `SendResult(platform_message_id="stub-msg-id", details={})`).
- `the_one/tools/connector_send.py:185` — F4's tool calls `client.send(target, content)`. The tool catches exceptions and translates to error envelopes.
- discord.py 2.4+ `client.get_channel(id)` / `client.fetch_channel(id)` / `discord.TextChannel.send` / `discord.Thread.send`.
- L1-L4 test suite green (2310 passed).

## Outputs

- `DiscordClient.send(target, content) -> SendResult` implementation in `the_one/connectors/_discord.py`:
  - Resolves the destination object:
    - If `target.thread_id` is not None: try `self._client.get_channel(int(target.thread_id))`. If it's a `discord.Thread`, use it. Else fall back to fetching the channel.
    - Else: try `self._client.get_channel(int(target.channel_id))`. If None (cache miss), `await self._client.fetch_channel(int(target.channel_id))`. If still None or raises, raise `ConnectorConnectionError(f"Discord channel {target.channel_id} not found")`.
  - Calls `await destination.send(content)`.
  - Returns `SendResult(platform_message_id=str(message.id), details={"channel_id": str(destination.id), "channel_type": destination.type.name})`.

- **Error mapping**:
  - `discord.errors.Forbidden` (bot lacks SEND_MESSAGES permission) → raise `ConnectorConfigError(f"Discord bot lacks send permission in channel {target.channel_id}")`.
  - `discord.errors.NotFound` (channel deleted) → raise `ConnectorConnectionError(f"Discord channel {target.channel_id} not found")`.
  - `discord.errors.HTTPException` with `status == 429` → raise `ConnectorRateLimitError(f"Discord send rate-limited; retry after {response.retry_after}s")`.
  - Other `discord.errors.HTTPException` → raise `ConnectorConnectionError(f"Discord send failed: {exc}")`.
  - Generic Exception → propagate (let the F4 tool catch and log).

- `tests/test_connectors_discord.py` extended with outbound tests:
  - Send to a text channel: mocked channel returns a Message with `id=12345` → SendResult with `platform_message_id="12345"`.
  - Send to a thread: `target.thread_id` set → channel resolution prefers the thread.
  - Cache miss → fetch_channel called.
  - Channel not found (get_channel returns None AND fetch_channel raises NotFound) → `ConnectorConnectionError`.
  - Forbidden → `ConnectorConfigError`.
  - Rate limit (HTTPException with status 429) → `ConnectorRateLimitError`.
  - Generic HTTP error → `ConnectorConnectionError`.

- F1-F7 + L1-L4 regression: 2310 → ~2317 (~7 new tests).

## Acceptance Criteria

- [x] **`DiscordClient.send(target, content) -> SendResult`** fully implemented in `the_one/connectors/_discord.py`:
  - When `target.thread_id` is not None and resolves to a `discord.Thread`: send via the thread.
  - When `target.thread_id` is None or doesn't resolve to a Thread: send via `self._client.get_channel(int(target.channel_id))` (cache hit) OR `await self._client.fetch_channel(int(target.channel_id))` (cache miss).
  - Returns `SendResult(platform_message_id=str(sent_message.id), details={"channel_id": str(destination.id), "channel_type": destination.type.name})`.

- [x] **Error mapping** matches the table above. Each error class is `from the_one.connectors.errors` (`ConnectorConfigError`, `ConnectorConnectionError`, `ConnectorRateLimitError`) — verify these exist by reading `the_one/connectors/errors.py`. *(Constructor shapes differ from the spec's single-string assumption — see flight-log L5 Deviations #1; spirit-of-the-mapping preserved by threading `account_id` through `DiscordClient`.)*

- [x] **Channel resolution**: `get_channel` first (cache); `fetch_channel` fallback (HTTP). The two-step lookup is critical — `get_channel` returns None for uncached channels, NOT raises. Only `fetch_channel` does the HTTP request that surfaces 403/404.

- [x] **Thread routing**: when `target.thread_id` is set, resolution prefers the thread. If `get_channel(int(thread_id))` returns a `discord.Thread`, use it. If it returns something else or None, fall through to the channel-only path with `target.channel_id`.

- [x] **`tests/test_connectors_discord.py` extended** with at least 6 new outbound tests covering: channel send happy path, thread send happy path, cache-miss fetch, channel-not-found, Forbidden, rate-limit, generic HTTPException. *(13 new tests shipped; spec floor was 6.)*

- [x] **F1-F7 + L1-L4 regression**: 2310 → ~2317. *(Actual: 2322. The extra count comes from splitting 7 spec-predicted tests into 13 finer branches; see flight-log L5 Deviations #4.)*

## Implementation Guidance

1. Read `the_one/connectors/errors.py` to confirm the three error classes' constructor signatures.
2. Read `tests/test_connectors_discord.py`'s existing mock pattern (the stub `_StubDiscordClient` from L3). Extend it with `get_channel` / `fetch_channel` returning a mock channel/thread, and the mock channel's `send` returning a mock Message with `id` attribute.
3. Implement `DiscordClient.send`:
   - Resolution: walk the thread-first / channel-second ladder.
   - Send: `await destination.send(content)`.
   - Result: construct `SendResult` with the snowflake-string id.
   - Errors: catch the discord.errors hierarchy by specific type → translate to typed connector errors.
4. Run tests; fix.
5. Update flight log; mark leg landed.

## Edge Cases

- **`target.thread_id` set but `get_channel` returns a non-Thread object** (operator misconfigured): fall back to the channel-only path with `target.channel_id`. Don't raise — be tolerant.
- **`content` is empty string**: discord.py rejects `channel.send("")` with `HTTPException`. L5 lets the SDK error propagate via the generic HTTPException → `ConnectorConnectionError` path. Could also pre-validate; defer.
- **`content` exceeds 2000 chars** (Discord message length limit): SDK raises `HTTPException(400)` with body content. F10 hardening can add splitting; for L5, propagate as ConnectorConnectionError.
- **Rate limit Retry-After**: discord.py 2.4+ surfaces this on `HTTPException.retry_after`. L5 includes it in the error message so the operator/agent can see the wait duration.
- **Channel send returns `None`** (shouldn't happen per SDK contract, but defensive): raise `ConnectorConnectionError("Discord send returned None")`.

## Files Affected

- `the_one/connectors/_discord.py` — `DiscordClient.send` body (replaces L3 placeholder)
- `tests/test_connectors_discord.py` — extended with outbound tests

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30` → 36 passed; full suite → 2322 passed, 4 skipped, 411 deselected)
- [x] Update flight-log.md with leg progress entry
- [x] Set leg status to `landed`
- [x] Check off L5 in flight.md
- [x] Do NOT commit — wait for flight-level review

## Citation Audit

- `the_one/connectors/base.py:85-93` — OutboundTarget — **OK**
- `the_one/connectors/base.py:148-171` — SendResult — **OK**
- `the_one/connectors/_stub.py:52-69` — StubClient.send precedent — **OK**
- `the_one/connectors/errors.py` — ConnectorConfigError/ConnectorConnectionError/ConnectorRateLimitError — verified at implementation time (errors.py is the F1 shipped module)
- `the_one/tools/connector_send.py:185` — F4 tool caller — **OK**

5 citations verified at leg-design time.
