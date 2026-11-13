# Connectors

Bridges external chat platforms to the agent loop. Mission 23 Flight 1 removed
the pre-reset framework (a ~430-line message-routing layer, per-agent ACLs,
manual peer-approval flows, a slash-command surface, the Discord plugin)
wholesale; Flight 2 rebuilt a small, platform-agnostic core from scratch.
This file is the contract — not a tutorial on the pre-reset design, which is
gone.

Flight 3 ships the first real plugin, Discord (`discord/`) — registered
unconditionally at lifespan startup, unlike `stub.py`'s in-process
`StubPlugin`, which stays a test/dev fixture registered only by tests or by
the dual-gated startup hook described under "Test seams" below, never in a
real deployment. See "Discord (Flight 3)" below for the plugin's own
contract.

## Protocol (`base.py`)

Two structural `Protocol`s (`the_one/agents.md`'s
`structural-Protocol-satisfaction` convention — no inheritance required):

- **`ConnectorPlugin`** — the type-level adapter for a platform. `connect(account, encryptor, on_inbound) -> ConnectorClient` returns once the plugin's gateway listener is live; it does not block for the connection's lifetime. `disconnect(client)` is idempotent teardown. `doctor(account, encryptor) -> DoctorReport` is a cheap health probe.
- **`ConnectorClient`** — one instance per running listener. `is_alive()` is polled by the manager's supervisor loop. `send(target, content) -> SendResult` delivers outbound content. `history(target, limit) -> list[HistoryMessage]` is OPTIONAL (DD-8) — discovered via `getattr(client, "history", None)`, not declared on the Protocol, so a plugin that doesn't support history carries no stub method. `sever_for_test()` is another OPTIONAL hook, same discovery pattern (DD-7, Mission 23 Flight 3 Leg 3) — the Discord client's controlled-disconnect test seam; see "Test seams" below.

`InboundCallback = Callable[[InboundEnvelope], Awaitable[None]]` — the
callback a plugin invokes (from inside its own gateway-listener task) for
every inbound message. `ConnectorManager` threads this callback into every
`plugin.connect()` call; plugins never import `the_one.connectors.inbound`
directly (that would invert the dependency direction — plugins are leaves,
the manager wires them up).

## Envelope flags (`InboundEnvelope`, `base.py`)

A normalized inbound message: `platform`, `connector_id`, `channel_id`,
`thread_id`, `peer_id`, `peer_name`, `text`, `is_dm`, `mentions_bot`. `is_dm`
and `mentions_bot` are set by the *platform client's own translation layer* —
the inbound pipeline never infers them from `channel_id` shape.

`SendTarget = ChannelTarget | PeerTarget` — a channel-keyed or peer-keyed
(DM) send destination. `channel_map` (below) never applies to a `PeerTarget`
(DD-4).

## Manager lifecycle (`manager.py`)

One `ConnectorManager` instance is installed at lifespan startup
(`set_manager`/`get_manager`, mirroring `agent.factory.set_factory`/
`get_factory`). It owns one supervised listener task per connector:

- `start(account, encryptor, repo=None)` spawns a supervisor task
  (`_run`) that connects, holds while `client.is_alive()`, and
  reconnects with exponential backoff (`backoff_base` → `backoff_max`,
  ±25% jitter) on disconnect or a failed connect.
- The **first** connect attempt uses the `account` snapshot passed to
  `start()`. Every attempt **after** that — every reconnect — re-fetches a
  fresh row from `repo` (when supplied) before reconnecting, so a listener
  that outlives a `PUT`-driven config change or an encryption-key rotation
  never reconnects on stale credentials.
- `stop(connector_id)` cancels the task and awaits it; idempotent on an
  unknown id. `drain()` stops everything (lifespan shutdown).
- Pairing codes (below) live in the same instance, keyed by connector id.

## Inbound pipeline (`inbound.py`)

`dispatch_inbound(connector_id, envelope, manager=...)` runs one inbound
envelope through, in order:

1. **Admission** — `is_admitted`: flat allowlist check (peer OR channel).
   Unadmitted → silent drop, with one exception: a DM whose body is the
   live pairing code consumes it and appends the sender to
   `allowlist.peers`. Nothing else persists for an unadmitted sender.
2. **`/new` interception** — an admitted DM/channel message that is exactly
   `/new` writes an `ended_at` sentinel on the matching session (if any) and
   returns; no agent turn runs. Any other `/foo` command is not
   intercepted — it reaches the agent as ordinary text.
3. **Reply policy** — `should_reply`: DM, `@mention`, or an
   `always_listen` channel. Otherwise the message is admitted (and could
   pair/append to history) but gets no agent turn.
4. **Session resolution** — `resolve_session`: keyed on
   `(platform, connector_id, channel_id, thread_id)` — **not** `peer_id`,
   which is stored on the row but not part of the lookup. Reuses the most
   recent matching row within the continuation window
   (`session_continuation_seconds` override, else
   `THE_ONE_SESSION_CONTINUATION_SECONDS` env var, else 24h) unless it
   carries a `/new`-written `ended_at` sentinel, else creates a fresh row
   titled `f"DM: {peer_name}"` (DM) or the channel id.
   The continuation rule itself is `inbound.is_continuable(row, seconds, now)`
   (no `ended_at`, a parseable `last_inbound_at` — naive reads as UTC — younger
   than the window).
5. **Dispatch** — under a per-session lock (`the_one.sessions.session_locks`),
   rebuilds the agent from the session's stored history, runs
   `agent.step(envelope.text)`, tags post-step message visibility (see
   "Reply visibility" below), and persists the updated history. Errors at
   any stage are logged and swallowed — a connector-layer failure never
   takes the agent runtime down.

Explicitly **out of scope** (superseded by design, not a placeholder): no
per-agent ACL, no message-routing layer, no routing/audit log, no
command-handler protocol beyond `/new`, no LLM-inferred engagement filter.

## Pairing (DD-3)

`POST /api/connectors/{id}/pairing-code` (operator-only) mints a
`secrets.token_hex(4)` code with a 10-minute TTL
(`ConnectorManager.PAIRING_TTL_SECONDS`), replacing any prior code for that
connector. Consumption (`consume_pairing_code`) has no `await` between check
and delete, so concurrent submissions of the same code resolve atomically
under asyncio's cooperative scheduling — first caller wins. A second
submission (wrong, expired, or already-consumed) is a silent no-op, exactly
like any other unadmitted message.

## Reply visibility

Every message an `agent.step()` call appends is tagged by
`tag_post_step_visibility` (`the_one/llm/base.py`): a successful
`send_to_platform_channel` tool result (content starting with
`[platform-send-ok]`) gets `visibility=None` (peer-visible — the tool
already pushed it to the platform); everything else the turn produces
(plain assistant text, intermediate tool calls/results) is tagged
`visibility="operator"` — console-only, not yet forwarded.

**DD-10 auto-reply mechanical fallback**: for an inbound turn dispatched
through `dispatch_inbound` (i.e. a peer's own message, not the operator's
console), that "everything else" tagging is not the end of the story. Right
after `tag_post_step_visibility` runs, `dispatch_inbound`'s
`_auto_deliver_reply` pass mechanically delivers the turn's FINAL assistant
message text to the ORIGINATING target — `PeerTarget(connector_id, peer_id)`
for a DM, `ChannelTarget(connector_id, channel_id, thread_id)` for a channel
— via `manager.client_for(connector_id).send()`, then flips that message's
`visibility` back to `None` (peer-visible), since it genuinely reached the
peer. **Skip rule (no double-send)**: if the turn already contains a
successful `send_to_platform_channel` result, the agent spoke to the
platform deliberately — auto-delivery is skipped entirely for that turn
(even when the tool-send targeted a *different* channel; the agent's own
plain text then stays operator-only, by design). Delivery failure (no live
client, `ConnectorClientError`, or any other exception from `send()`) is
logged and the message's visibility is left as `tag_post_step_visibility`
tagged it (operator-only) — no retry, no crash; the turn is still persisted.

**Step-limit line (M31 F6 leg 06, DD8 F2)**: when the turn ended because the
agent ran out of steps (`Agent.stopped_at_step_limit`), `dispatch_inbound`
sends one more neutral plain line, "(Stopped: reached its step limit for this
message.)", to the same target through the same client — AFTER the turn is
persisted, through `_send_step_limit_line`, which never raises. It is sent
always, including after a `send_to_platform_channel` turn. With no live client,
or on a send failure, it is logged and dropped. It is not stored, so the
persisted messages hold no such line.

**Delivery primitives (M33 F1 L2).** `connectors/delivery.py` holds the
envelope-free pieces: `deliver_final_reply(messages, pre_step_len, target,
connector_id, manager)` (the skip rule and the send above; it returns nothing
and never raises), `send_step_limit_line(target, ...)` and `authorized_agent_for(connector,
channel_id=...)` (the send tool's authorization rule). It has no dependency on
`inbound.py`; `_auto_deliver_reply` and `_send_step_limit_line` are thin
wrappers that build the target from the envelope.

The operator's own typed message in the same session is unaffected: it is
tagged `visibility="operator"` at construction time by the WS handler and
never runs through `dispatch_inbound` at all, so it is never auto-delivered
— **an operator's console note never reaches the platform**. What DD-10
changes is narrower and specific: a peer's inbound message that gets a
plain-text reply now has that reply mechanically delivered back to the same
peer/channel, independent of whether the model chose to call
`send_to_platform_channel`. The send tool remains the agent-INITIATED path
(speak-first, cross-channel, or a deliberate re-send) — this fallback only
ever fires for the turn's own reply-in-kind.

## Send-tool target defaulting (DD-11)

`send_to_platform_channel`'s `target` argument is OPTIONAL (Mission 23
Flight 3, mid-flight amendment — live-gate checkpoint 5 proved the DD-5
carve-out works (the model calls the tool by name, unprompted) but "send
to this channel" dead-ends: the session's connector/channel keying is
invisible to the model, so it asks the operator for platform ids). When
`target` is omitted, the tool resolves one from `current_chat_session_id`
(`agent/_context.py`) → that session's `chat_sessions` row → the row's
own keying columns, mirroring `resolve_session`'s keying (`channel_id`,
not `peer_id`, is the session's primary key, per "Session resolution"
above): a `channel_id`-bearing session resolves to
`ChannelTarget(connector_id, channel_id, thread_id)`; a session with no
`channel_id` but a `peer_id` resolves to `PeerTarget(connector_id,
peer_id)`. No active session context, or a session not bound to a
connector at all (both columns unset), is a clear `[error] [constraint]`
— never a guess. The resolved default is folded into the exact dict
shape an explicit `target` takes, so it is authorized by the SAME rule
below — a defaulted target that fails authorization errors identically
to an explicit one. Explicit `target` arguments are unaffected.

## Lookup tool (`find_platform_destination`, DD-5, Mission 23 Flight 4 Leg 3)

Read-only. `tools/connector_lookup.py`'s `FindPlatformDestinationTool` looks
up an observed peer/channel by name — case-insensitive substring match over
`display_name` OR `username`, ≤10 results, newest `last_seen` first — and
returns a compact JSON array of candidates. Each candidate carries
`connector_id`, `connector_name`, `kind`, `display_name`, `username`,
`last_seen`, and is keyed LITERALLY as `send_to_platform_channel`'s `target`
expects: a peer candidate carries `peer_id` (never a channel key); a channel
candidate carries `channel_id` (+ `thread_id` when set, never a peer key) —
no generic `platform_id` ever reaches the model. Zero matches returns a
clear message naming the query, not an empty array. An empty/whitespace
query is a clear `[error] [constraint] ...`, never a full-table dump.

**Authorization is CONNECTOR-LEVEL** (`ConnectorDirectoryRepository.search`,
`db/repositories.py`) — quoting the repository's own scoping ruling
verbatim:

> Search scoping is CONNECTOR-LEVEL by design (designer ruling,
> 2026-09-02): a connector is in scope when `agent_name` appears ANYWHERE
> in its binding (`config.default_agent` OR any `config.channel_map`
> value) — a deliberate simplification, NOT per-target precision.
> Rationale: send-time authorization remains the real per-target gate
> (unchanged, enforced in `tools/connector_send.py`); this lookup exposes
> only names within one connector, which is one operator trust domain; a
> per-target search filter would duplicate the send matrix for marginal
> privacy inside a domain the operator already configured.

Read-only: NO authorization error paths beyond scoping — an out-of-scope
connector's rows are simply absent from results (enumeration reveals
nothing). An unbound agent (no connector names it) gets an empty result,
not an error.

Seeded via the DD-6 baseline-visibility carve-out, same as
`send_to_platform_channel` — see `agent/factory.py`'s seed loop and
`the_one/agents.md`'s "DD-5 baseline-visibility carve-out" for the
mechanism. The two-call chain (lookup → send with explicit ids) is the
operator-chosen shape for name-addressed sends; see
`tests/behavior/directory-lookup-send.md` for the end-to-end gate.

## Authorization rule (send tool + history tool)

`send_to_platform_channel` (`tools/connector_send.py`) and
`fetch_channel_history` (`tools/connector_history.py`, DD-8) share one
binding-derived authorization rule, re-checked against the live `Connector`
row at call time — a union across the two target shapes:

- **Channel target** — sendable/readable by `channel_map[channel_id]`'s
  agent if that channel has a mapping, else by `default_agent`: the same
  agent that would *receive* an inbound message on that channel.
- **DM (peer) target** — sendable/readable **only** by `default_agent` —
  `channel_map` never applies to DMs — and only to a peer already on
  `allowlist.peers`.

Any other calling agent, or a DM target outside the allowlist, gets an
`[error] [constraint] ...` string back — never an exception, never a
platform call.

**DM channel ids and the bound-agent rule.** Discord DMs are channels
under the hood (see "Discord (Flight 3)" below). The two rules above are
keyed on which field the caller sets, not on what the id "really" points
to: if a raw DM channel id is passed as `target.channel_id` (a Channel
target), it authorizes under the **bound-agent rule** —
`channel_map[channel_id]`'s agent, else `default_agent` — same as any
other channel target, **not** the peer allowlist; the allowlist only
applies to the `peer_id`-shaped target. This is a stated property of the
design (HAT-verified 2026-09-02), not a gap: the peer-allowlist guarantee
holds in practice regardless, because a DM channel id is only ever
learnable through an already allowlist-gated path — a `Create DM` call
against an allowlisted peer (the `PeerTarget` send path's own REST call,
see "Discord (Flight 3)" below) or an admitted inbound DM. An unadmitted
DM is dropped at Admission before anything persists, so its channel id
never reaches the agent or the stored history — there is no route by
which a model could learn a DM channel id for a peer it isn't already
allowed to reach.

## Config schema (DD-2)

`Connector.config` is a closed reserved-key dict — unknown top-level keys
are rejected at validation time:

| Key | Shape | Meaning |
|-----|-------|---------|
| `default_agent` | `str` | The DM recipient/sender; the channel fallback when no `channel_map` entry matches. A dangling reference (renamed/deleted agent) is a doctor-reported warning, not a validator error. |
| `channel_map` | `dict[str, str]` | `channel_id -> agent_name`, channel targets only. |
| `allowlist` | `{"peers"?: [str], "channels"?: [str]}` | Admission list (see above). |
| `always_listen` | `list[str]` | Channel ids that get a reply with no `@mention`. |

`Connector.secrets` is a free-form dict (the platform credential, e.g.
`{"token": "..."}"`), Fernet-encrypted at rest and masked on every API
response — see [SECURITY-MODEL.md](../../SECURITY-MODEL.md) "Connector
Channel Contract" for the masking/rotation contract.

`enabled` (`bool`, default `true`, DD-6) pauses a connector without
deleting it: `false` stops the listener (and keeps it stopped across
restarts — `start_all` skips disabled rows) while the row, config, and
secrets stay intact. Absent key reads as enabled — no migration was
needed. A `PUT` branches on the NEW effective value only: `true` → stop
+ start, `false` → stop only, regardless of the prior value (so a
disabled→disabled save never accidentally restarts the listener). Doctor
reports `disabled` as a distinct top-level field, independent of the
plugin's own health status — a connector can be both disabled AND carry a
stale permanent-failure marker.

## Discord (Flight 3)

`discord/` (`_gateway.py`, `_rest.py`, `plugin.py`) — a hand-rolled Gateway
v10 client on `websockets` and a bot-only REST client on `httpx`; no
`discord.py`/`aiohttp` dependency (mission constraint). Registered
unconditionally at lifespan startup (`the_one/interfaces/web/app.py`) — a
real platform, not gated like the stub.

- **Gateway protocol scope**: hello → heartbeat loop (jittered first beat,
  ACK-watchdog — a missed ACK closes and lets the manager reconnect) →
  identify (`GUILDS | GUILD_MESSAGES | DIRECT_MESSAGES | MESSAGE_CONTENT`
  intents) → dispatch, handling `READY` (captures `session_id` +
  `resume_gateway_url`) and `MESSAGE_CREATE`. **No sharding, no zlib
  compression** — out of scope for a personal-bot deployment; a guild
  count that would require sharding is not this project's target shape.
- **Resume behavior**: a dropped connection resumes against the
  `resume_gateway_url` READY advertised, replaying `session_id` +
  `last_seq`; a stale/unreachable resume URL falls back to a fresh
  `Get Gateway Bot` lookup + identify within the same `connect()` call. Op
  7 (`RECONNECT`) triggers a prompt self-initiated close so the next
  attempt resumes normally.
- **Close-code policy**: Discord's non-reconnectable codes (`4004` auth
  failure; `4010`–`4014` shard/intent misconfiguration) raise a
  `PermanentConnectorFailure` (`connectors/base.py` — contract-level, so
  Telegram inherits it). The manager stops retrying and logs; the plugin
  records a per-account failure marker so `doctor()` short-circuits to
  `"permanently failed: <reason>"` without a REST round-trip. The marker
  clears unconditionally at the top of every fresh `connect()` — the only
  reset point, so a PUT-driven stop/start recovers a fixed token with no
  extra wiring. **Accepted trade-off**: the close-code check runs only
  pre-`READY`; a permanent code observed mid-session is not raised
  immediately — it surfaces at the *next* handshake instead (one backoff
  cycle of latency), deliberately, since the token is equally bad either
  way and an immediate-signal path would add machinery for no recovery
  benefit.
- **REST rate limiting**: per-bucket serialization keyed by
  `X-RateLimit-Bucket` (learned from the first response on a route) plus a
  global gate that a `429` with `global: true` engages across every
  bucket; `retry_after` is honored with bounded retries. No request
  queuing beyond per-bucket serialization — a personal bot's volume
  doesn't need it. ~10 endpoints: Get Gateway Bot, Get Current User,
  Create Message, Create DM, Get Channel, Get Channel Messages (powers
  `history`), Trigger Typing, Get Guild Channels. No webhooks, no
  interactions/slash surface.
- **Credential**: the bot token lives in `Connector.secrets["token"]`
  (`Authorization: Bot <token>` on every REST call and in the gateway
  identify payload) — the same masked-at-rest, Fernet-encrypted contract
  every connector's secrets follow.
- **Per-account state**: `registry` plugins are type-keyed singletons, so
  `DiscordPlugin` holds `session_id`/`resume_gateway_url`/live-connection
  state in an account-id-keyed dict (the shape `StubPlugin._live` already
  established) — one Discord connector's reconnect never touches another's
  state.
- **Envelope translation**: `MESSAGE_CREATE` → `InboundEnvelope` with
  `is_dm` from the channel type (resolved via the READY private-channels
  cache or a channel fetch, cached thereafter), `mentions_bot` from the
  mentions array containing the bot's own user id, `peer_name` from the
  author's global/display name, `thread_id` set for thread channel types.
  Messages authored by the bot itself, any other bot, or a webhook are
  dropped before the pipeline (loop prevention) — webhook-authored content
  is treated as bot-authored, a deliberate scope trade-off.
- **Controlled-disconnect test seam**: see "Test seams" below — this is a
  test-only hook, never reachable in production traffic.

## Visuals on platforms (Mission 35 Flight 3)

A reply's top-level chart and widget blocks are converted on the way out by one shared helper,
`delivery.send_reply(client, target, content, *, connector_id)`, used by both send paths
(`deliver_final_reply` and `send_to_platform_channel`). It returns `(result, images_sent)`; the tool
appends ` (1 image)` / ` (N images)` to its success line when `images_sent > 0`.

- **What converts.** `the_one/visuals/blocks.py::find_blocks` finds top-level fenced blocks (the chat's
  fence rule, held equal to the evals finder by `tests/fixtures/visual-blocks/replies.json`);
  `visuals/outbound.py::plan_outbound` plans the reply. A closed chart `parse_chart` accepts becomes
  a candidate (the first 10; later ones stay as code); every widget block, closed or not, becomes
  the one-line note "Interactive widget: open this chat in the app to see it."; a drawn chart
  becomes a marker line `Chart: {title} (below)` (or `Chart {n} (below)`). With nothing to convert
  the call is exactly `client.send(target, content)`. The Rich visuals switch is never consulted.
- **Drawing** runs in one `asyncio.to_thread` call (`chart_image.render_png`); a chart that fails to
  draw stays as its source block and logs one "falling back to text" warning (index and connector id, never its data).
- **Two OPTIONAL client methods**, found with `getattr` like `history`: `send_visual(target, content,
  images: Sequence[OutboundImage]) -> SendResult` (`details` may carry `images_sent` and
  `images_failed`) and `send_visual_fallback(target, content) -> SendResult` (the text resend under
  the client's clamped 429 policy; `send` is used without it). A client with no `send_visual` gets the
  fallback text: charts as code, widgets as the note.
- **Error contract.** `send_visual` raises `VisualUploadError` (a `ConnectorClientError`, in `base.py`)
  **only when nothing of the reply was posted** (a 4xx before anything went out); the helper then
  resends the fallback text once. Any later failure of an image is the client's own per-image
  fallback, and any other failure is a plain `ConnectorClientError` that propagates (never resent), so
  the text is never duplicated. `OutboundImage` (`visuals/outbound.py`) is re-exported by `base.py`.
- **Stub.** `StubClient.send_visual` records a `StubVisualRecord`, a tuple subclass of
  `(target, content)` with `.images`, so every existing reader keeps working (`==` ignores `.images`;
  assert it explicitly). `StubPlugin.send_visual_should_raise` fails only the visual path. The route
  `GET /api/_test/stub/outbound` adds `images: [{filename, title, width, height, size, sha256}]`
  (no bytes) to a record that carries images, and nothing to a text record.
- **Residual: nested blocks.** A chart or widget fence inside a quote or a list is not a top-level
  block (as in the chat), so it is sent as its source text.
- **Cap and limits.** At most 10 images per reply (Discord's attachment limit); long text is not split.

### Discord and Telegram uploads (M35 F3 Leg 4)

- **Discord** `send_visual` posts ONE `multipart/form-data` message to `/channels/{id}/messages`: a
  `payload_json` part (`Content-Type: application/json`: `content` plus `attachments[{id, filename,
  description}]`, the description being the chart title cut to 1024) and one `files[i]` part per image
  (`image/png`). A 4xx (400, a 413 over the size limit, or a 429 after its one retry) raises
  `VisualUploadError` and the helper resends the text through `send_visual_fallback`
  (`create_message(clamped=True)`); a 5xx raises `DiscordRestError` and a transport failure
  `DiscordTransportError`, both propagate and nothing is resent (the message may have gone). Over-long
  content is a 400 and so takes the fallback, which fails the same way: message splitting is out of scope.
- **Telegram** `send_visual` sends the text exactly as `send` does (HTML, then the plain retry), then one
  `sendPhoto` (multipart, caption = the title cut to 1024 characters with an ellipsis, no `parse_mode`) per
  image in order, to the same chat and thread. A text failure propagates before any photo. After that
  nothing raises: a photo refused with a 4xx (a 413, a dimension limit, a 429 after its retry, or a
  401/404/409) sends that image's source as a follow-up text straight after it; a 5xx, a transport error
  or a budget timeout may have posted it, so it is logged and skipped with no fallback; the rest are still
  attempted. Images the budget never reached go out as ONE text (their sources joined by a blank line).
  `SendResult.details` carries `images_sent` and `images_failed`.
- **429 policy.** Both visual paths (the Discord multipart POST and fallback, Telegram `sendPhoto` and
  the fallback text) retry a 429 at most once after `min(retry_after, 10)` seconds. Plain `send` /
  `create_message` / `send_message` keep their policy (Discord 3 retries unclamped, Telegram one retry
  clamped to 60 s). Telegram's retry lives in one function, `_post_with_429_retry`.
- **The 45 s photo budget.** The Telegram photos and their per-photo fallback texts share
  `_PHOTO_BUDGET_SECONDS = 45`, enforced by `asyncio.wait_for` on the time left (httpx's `timeout` limits
  each phase, not the request) plus a per-request `timeout=min(15, remaining)`. A 429 whose clamped wait
  is not under the time left is not slept on: it is a 4xx and takes the fallback. It sits under the 110 s
  liveness window (`2 * 50 + 10`) because the whole send runs inside the poll task. **Residual:** the text
  send's own worst case (an HTML attempt and a plain retry, each with up to a 60 s 429 wait) predates this
  and can already exceed 110 s, and the final pending-images text adds at most one 10 s-clamped request.
- **Upload limits.** Each platform's own limits (Discord's per-message size, Telegram's 10 MB and its
  dimension limits) surface as a 4xx and so take the fallbacks above.
- **Transport errors.** An `httpx.HTTPError` during any request is now `DiscordTransportError` /
  `TelegramTransportError`, siblings (not subclasses) of `DiscordRestError` / `TelegramApiError`, so
  `TelegramClient.send`'s plain-text retry (any `TelegramApiError`) does not run after a timeout and
  post a reply twice. The Telegram mapping raises `from None` and names only the exception type, since
  the bot token is in the URL path. Side effects: the connector `doctor` on both platforms now reports
  "failed" on a transport failure instead of raising, and `send_to_platform_channel` returns
  `[error] DiscordTransportError: ...` / `[error] TelegramTransportError: ...`. Errors built from a
  response carry `.status`, which the fallback rules read (4xx: not posted; 5xx or none: maybe posted).
- **Logging.** Each fallback event is exactly one WARNING containing "falling back to text" (the
  Discord refusal is logged by `send_reply` alone, with the chart indices, connector id, client class
  and HTTP status; the Discord plugin's own line is DEBUG), and a skip (a 5xx, transport error or budget
  timeout that may have posted) is one warning that does not say "fallback". Each carries the image
  indices, the status (or `transport` / `budget`) and the chat id; never the bytes, title, caption,
  fallback text, the exception text or the platform's response body.

## Test seams (DD-10, DD-7)

`POST /api/_test/stub/inbound` and `GET /api/_test/stub/outbound`
(`interfaces/web/api.py`) require **both** `settings.dev_mode` and
`THE_ONE_STUB_TEST_ENDPOINT=1` — the same dual gate that admits `"stub"`
into `GET /api/connectors/types` and drives the lifespan-startup hook that
registers `StubPlugin`. These seams inject free text into a live agent loop
with real LLM calls and tool execution (purge-sweep's risk profile, not the
inert-metadata OAuth-pending seam's) — never available outside a
dev/test instance. See `tests/behavior/stub-connector-round-trip.md` for the
end-to-end HAT that exercises them against a real agent loop.

**Fake-platforms seam (M35 F3 L6).** `THE_ONE_FAKE_PLATFORMS_URL=http://<loopback IP>:<port>`,
with `THE_ONE_DEV_MODE=true`, makes the lifespan register the Discord and Telegram plugins with
URLs under that base (`/discord/api/v10`, the explicit `ws://…/discord/gateway`, `/telegram`), so
the real clients talk to `scripts/fake_platforms.py`. It is read from the process environment only
(not `.env`, not a `Settings` field), is ignored silently with `dev_mode` off, and accepts only an
`http` URL with a loopback IP literal (`127.0.0.1`, `[::1]`), an explicit port, no userinfo, path,
query or fragment (`fake_platforms_seam.py`; `localhost` and other names are refused because DNS
is not trusted, and a bot token must never leave the machine through it). A refusal logs one error
with the reason, the scheme and the host only, and the real URLs are used; a valid value logs one
warning, "connectors use the fake platforms at http://127.0.0.1:P". Residual: the fakes prove what
the app sends, not what Discord or Telegram show. The stub route's outbound records also carry an
`images` list (see above). End-to-end use: `tests/behavior/charts-reach-platforms.md`.

`POST /api/_test/discord/sever` (Mission 23 Flight 3 Leg 3, DD-7) requires
**both** `settings.dev_mode` and `THE_ONE_DISCORD_TEST_ENDPOINT=1` — its own
gate name, not the stub gate above (`risk-tiered-test-seam-gating`,
`the_one/agents.md`). Abruptly severs a live connector's gateway websocket
via the OPTIONAL `sever_for_test` hook (`getattr(client, "sever_for_test",
None)`, discovered through `manager.client_for` — never a Discord-specific
import, so any future plugin that defines the hook gets this seam for
free). Body: `{"connector_id": "..."}`. Error taxonomy: unknown connector
→ 404; row exists but no live client (mid-backoff or never started) → 409;
client present but no hook (e.g. a stub-typed connector) → 501. Never a
production kill switch. See `tests/behavior/discord-live-round-trip.md`'s
step 6 for the end-to-end resume proof this seam drives.

### Fake platforms (developer tool, M35 F3 Leg 5)

`scripts/fake_platforms.py` is a standalone, loopback-only fake of the Discord REST API and gateway
and the Telegram Bot API (`the_one/` never imports it). It records every send the app makes (JSON
bodies, multipart fields, and per file the size, SHA-256 and PNG dimensions, never the bytes, and
never the Telegram token), injects inbound messages (`/_control/discord/inject`,
`/_control/telegram/inject`) and fails chosen sends (`/_control/fail-next`, kind `upload` or `any`).
It proves what the app sends, not what a platform shows, and models no size limits. Differences
from the real services: the first `getUpdates` after a `getMe` answers at once (so `connect()`
resolves), later empty polls are held; READY carries no `resume_gateway_url`, so the Discord
client always re-IDENTIFYs. Start it with `.venv/bin/python scripts/fake_platforms.py` (first
stdout line `{"port": P, "pid": N}`; `--port` 0 or at least 8490, `--save-dir` outside the repo,
`--heartbeat-ms`). Leg 6 adds the app seam that points the real clients at it.

## Telegram (Flight 4)

`telegram/` (`_api.py`, `plugin.py`) — a hand-rolled long-poll client on
`httpx` (DD-1/DD-2, Mission 23 Flight 4); no new dependency
(`python-telegram-bot`/`aiogram` stay absent). Registered unconditionally
at lifespan startup, same block pattern as Discord.

- **Poll loop**: one `getUpdates(offset, timeout=50, allowed_updates=
  ["message"])` loop per account. `offset` is the at-least-once
  redelivery cursor — advanced only after a batch is fully dispatched, so
  an unclean restart re-fetches (and redelivers) the last un-acknowledged
  batch; no dedup is attempted (personal-bot scale, documented trade-off,
  not hidden). `getMe` at `connect()` captures the bot's id + `@username`.
  `is_alive()` = the poll task lives and the last successful poll is
  within `2*timeout+grace`.
- **Error policy**: 401/404 (bad token) and 409 Conflict (another
  `getUpdates` consumer already holds the long-poll slot — a config error
  retrying cannot fix) raise `PermanentConnectorFailure` (REUSED from
  Discord's contract, `connectors/base.py` — zero new shared code);
  anything else lets the loop die and the manager's ordinary backoff
  reconnect (a fresh `connect()`) own retry, mirroring Discord's own
  pre-READY-only close-code policy trade-off.
- **Translation**: `chat.type == "private"` → `is_dm`; `mentions_bot` from
  a `mention` entity slicing to `@botusername` (case-insensitive, UTF-16
  code-unit offsets) or a `text_mention` entity matching the bot's id;
  `peer_name` from `first_name [+ last_name]`; `peer_username` from
  `from.username`; channel/group targets keyed by `str(chat.id)`; a
  `message_thread_id` becomes the envelope's `thread_id` (forum topics);
  bot-authored messages drop unless allowlisted (Flight 3's DD-4
  parity); text-less messages (joins, stickers, captionless media) drop.
- **Directory**: every group/supergroup message carries `chat.title` —
  upserted into the channel directory unconditionally (not
  admission-gated, per the flight's DD-4 cycle-2 ruling — see
  `plugin.py`'s `_upsert_channel_directory`). Peer entries come from the
  shared `dispatch_inbound` hook, same as Discord.
- **Outbound**: `sendMessage(chat_id=..., text=...)` — a `ChannelTarget`
  maps to `chat_id=channel_id` (+ `message_thread_id` when set); a
  `PeerTarget` maps to `chat_id=peer_id` directly — Telegram's DM chat id
  IS the user id, so there is no Create-DM REST step (unlike Discord).
- **Formatted rendering (HAT step 8, daily-driver fix promoted through a
  scoped review)**: `TelegramClient.send()` runs `content` through
  `_render.render_telegram_html` (a small hand-rolled, dependency-free
  markdown → Telegram-HTML converter — `<b> <i> <a href> <code> <pre>`
  only; tables/headings degrade, list markers stay literal text) and
  sends with `parse_mode="HTML"`. `_api.TelegramApiClient.send_message`
  gained an **optional** `parse_mode` param, omitted from the payload
  when `None` (mirrors the existing `message_thread_id` pattern).
  Two layers of defense, both exercised by `tests/test_telegram_render.py`
  and `tests/test_telegram_plugin.py`:
  - **No-raise guarantee**: `send()` wraps the converter call in
    `try/except Exception` — any converter failure degrades to the
    original, unconverted text with no `parse_mode` at all (the
    formatted attempt is never even made).
  - **Mechanical fallback**: if the formatted attempt itself raises
    `TelegramApiError` (any 4xx/5xx/`ok:false` — never string-matched;
    this also heals HTML-inflation past the 4096-char limit), `send()`
    retries **once** with the original text and no `parse_mode`. A
    second failure re-raises normally. `_api`'s own one-shot-429 retry
    stays self-contained inside each of those two attempts, so at most
    two independent send attempts ever happen — no double-delivery
    combination exists. Fallback logging records the chat id, the error
    description, and before/after byte-lengths — **never the message
    content** (log-hygiene; see squawk 0037 in this same subpackage,
    about the token itself leaking via httpx's own request-URL logging).
- **NO `history` hook.** The Bot API has no message-history endpoint —
  the optional-hook pattern (`ConnectorClient.history`, above) working as
  designed: `TelegramClient` simply omits the method, and
  `fetch_channel_history`'s existing `getattr(client, "history", None) is
  None` branch covers it with zero new code.
- **Credential**: the bot token lives in `Connector.secrets["token"]`,
  baked into the Bot API URL path (`/bot<token>/<method>`) rather than a
  header — same masked-at-rest, Fernet-encrypted contract as Discord.

See [`docs/connector-setup.md`](../../docs/connector-setup.md) for the
operator walkthrough (both platforms), including Telegram's `/setprivacy`
requirement for always-listen groups.

## Known limitations

- **No in-band way for an agent to discover its own `connector_id`/`peer_id`,
  for a DELIBERATE (agent-initiated) send.** `dispatch_inbound` passes only
  the raw inbound `text` to `agent.step()` — no connector id, no peer id, no
  directive is injected into the turn (the pre-reset auto-relay
  system-prompt directive was deleted in the Mission 23 reset, not
  reattached). For the ORDINARY reply case this is no longer a live gap:
  Mission 23 Flight 3's DD-10 auto-reply mechanical fallback (see "Reply
  visibility" above) delivers a plain reply back to the originating target
  without the model ever needing to discover or call
  `send_to_platform_channel` — the mechanical fallback
  `the_one/agents.md`'s `prompt-discipline-needs-mechanical-fallback`
  convention calls for. DD-11's target defaulting (see "Send-tool target
  defaulting" above) narrows what remains further: a model that decides to
  proactively call the send tool for its OWN session's platform
  conversation — a deliberate re-send, or a reply the auto-fallback's skip
  rule suppressed — no longer needs to discover a target at all; omitting
  `target` reaches that same conversation mechanically. What is still open
  is narrower still: a model choosing to send to a *different*
  channel/DM than the one it's currently bound to, with no in-band
  instruction naming that other target, still has no way to discover an id
  it wasn't told. See `tests/behavior/stub-connector-round-trip.md`'s "Why
  the reply steps embed the tool-call target" note for the empirical read
  on this residual gap.

## Size budget

Mission 23 capped the connector subsystem at **3,000 Python lines**: the
`the_one/connectors/` package plus the three connector tools
(`connector_send.py`, `connector_lookup.py`, `connector_history.py` in
`the_one/tools/`). The count is a plain `wc -l`, so blank lines, comments and
docstrings all count. Reproduce it from the repo root:

```bash
find the_one/connectors -name '*.py' | xargs cat the_one/tools/connector_*.py | wc -l
```

Figure at the time of writing: **2,970 / 3,000** (package 2,553 + tools 417),
the same as at the Mission 23 close. A new platform does not fit in the
remaining 30 lines and requires an explicit trim-or-raise decision before it is
planned.
