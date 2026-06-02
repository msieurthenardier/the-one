"""Multi-bot ``discord.py`` driver + HTTP-API assertion helpers for the
live-traffic Discord HAT.

:class:`BotDriver` brings up N concurrent :class:`discord.Client`s (one per
configured token) on the running test event loop with default (non-privileged)
intents — the sender bots only post, never read message content. It exposes a small posting API
(:meth:`post`, :meth:`mention`, :meth:`dm`) and tears every client down
cleanly on exit so no pending tasks / unclosed sessions leak.

The driver bots are POSTING-ONLY: they register no ``on_message`` handler
and never auto-reply. This is the planning M2 feedback-loop guard — the
test connector targets the isolated test guild only, and adding any
auto-reply behavior here would risk a bot↔the-one loop.

Assertion helpers (:func:`wait_for_session`, :func:`latest_routing_entry`,
:func:`inbound_peer_names`) poll the-one's dev-mode lookup seam to locate
the connector-attached session, then read its detail (messages +
session_metadata.routing) over HTTP. The lookup seam is the SUPPORTED way
to match a connector+channel to a session — the ``_session_summary`` list
shape carries no connector-keying fields.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import TracebackType
from urllib.parse import quote

import discord
import httpx

from .config import HatConfig

# Per-client login/ready bound. discord.py's gateway handshake is normally
# a few seconds; 30s tolerates a slow CI network without hanging forever.
_READY_TIMEOUT_SECONDS = 30.0


class BotDriver:
    """Async context manager owning N concurrent sender bots.

    Usage::

        async with BotDriver(cfg) as bots:
            await bots.post(0, channel_id, bots.mention("hi"))

    Each token becomes a ``discord.Client`` started as a background task on
    the current loop; ``__aenter__`` waits for every client's ``on_ready``
    (bounded by :data:`_READY_TIMEOUT_SECONDS`) before returning.
    """

    def __init__(self, cfg: HatConfig) -> None:
        self.cfg = cfg
        self._clients: list[discord.Client] = []
        self._tasks: list[asyncio.Task] = []
        self._ready_events: list[asyncio.Event] = []

    def _build_client(self, ready_event: asyncio.Event) -> discord.Client:
        # The sender bots only POST messages (and DM the-one's bot) — they
        # never READ message content — so default intents suffice. We do NOT
        # request the privileged ``message_content`` intent: it is a *receive*
        # capability (the-one's own GleepGlorp bot carries it to read these
        # bots' posts), and requesting a privileged intent the bot apps don't
        # have enabled would make discord.py raise PrivilegedIntentsRequired on
        # connect. Default intents (guilds/messages) cover get_channel + send +
        # create_dm. (F15 L3 provisioning correction — see flight log 2026-06-02.)
        intents = discord.Intents.default()
        client = discord.Client(intents=intents)

        @client.event
        async def on_ready() -> None:  # noqa: ANN202 — discord.py event hook
            ready_event.set()

        return client

    async def __aenter__(self) -> BotDriver:
        for token in self.cfg.tokens:
            ready = asyncio.Event()
            client = self._build_client(ready)
            self._clients.append(client)
            self._ready_events.append(ready)
            # client.start() runs the gateway connect+listen loop; running
            # it as a task keeps all N clients live on one event loop (the
            # Architect-confirmed standard pattern — the-one itself runs its
            # client as a background task).
            self._tasks.append(asyncio.create_task(client.start(token)))

        # Wait for every client to reach on_ready (bounded). If any client
        # fails to log in, its start() task raised — surface that rather
        # than hanging the whole timeout.
        try:
            await asyncio.wait_for(
                asyncio.gather(*(ev.wait() for ev in self._ready_events)),
                timeout=_READY_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception):
            await self._shutdown()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._shutdown()

    async def _shutdown(self) -> None:
        """Close every client and cancel its start() task. Idempotent and
        tolerant of partially-started clients (a login failure mid-setup)."""
        for client in self._clients:
            if not client.is_closed():
                await client.close()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        # Await cancellation so no "Task was destroyed but it is pending"
        # warning leaks. Swallow the CancelledError/login error from each.
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._clients.clear()
        self._tasks.clear()
        self._ready_events.clear()

    # ── posting API ──────────────────────────────────────────────────────

    def mention(self, content: str) -> str:
        """Prefix ``content`` with an ``@mention`` of the-one's bot user so
        the resulting post engages the-one via the deterministic mention
        policy outcome (no inference). ``is_mention`` on the-one's side
        matches the bot user id in ``message.mentions``."""
        return f"<@{self.cfg.bot_user_id}> {content}"

    def _resolve_channel(self, bot_idx: int, channel_id: str):
        client = self._clients[bot_idx]
        return client.get_channel(int(channel_id))

    async def post(self, bot_idx: int, channel_id: str, content: str) -> discord.Message:
        """Send ``content`` to ``channel_id`` as bot ``bot_idx``. Resolves
        the channel from cache, fetching from the API if not yet cached."""
        client = self._clients[bot_idx]
        channel = client.get_channel(int(channel_id))
        if channel is None:
            channel = await client.fetch_channel(int(channel_id))
        return await channel.send(content)

    async def dm(self, bot_idx: int, content: str) -> discord.Message:
        """Open (or reuse) a DM to the-one's bot user and send ``content``
        as bot ``bot_idx``. Returns the sent message — its ``channel.id`` is
        the DM channel id, which the-one keys the DM session on."""
        client = self._clients[bot_idx]
        user = client.get_user(int(self.cfg.bot_user_id))
        if user is None:
            user = await client.fetch_user(int(self.cfg.bot_user_id))
        dm_channel = user.dm_channel or await user.create_dm()
        return await dm_channel.send(content)


# ── HTTP-API assertion helpers ───────────────────────────────────────────


async def wait_for_session(
    base_url: str,
    connector_id: str,
    channel_id: str,
    *,
    thread_id: str | None = None,
    until: Callable[[dict], bool] | None = None,
    timeout: float = 60.0,
    poll_interval: float = 1.0,
) -> dict:
    """Poll the dev-mode lookup seam until it resolves the connector-attached
    session for ``(connector_id, channel_id[, thread_id])``, then keep fetching
    that session's detail dict (``messages`` + ``session_metadata``) until
    ``until(detail)`` holds (or ``timeout``). Returns the detail dict.

    ``until`` is REQUIRED in practice for any assertion on message history:
    the session row is created early in the dispatch (at ``resolve_session``),
    but the inbound message + ``peer_name`` and the engaged-path routing entry
    are persisted only after ``agent.step()`` completes — seconds later, once
    the LLM call returns. Without an ``until`` predicate the caller races the
    dispatch and reads an empty ``messages`` array. Pass e.g.
    ``until=lambda d: inbound_peer_names(d)`` to wait for attribution, or
    ``until=lambda d: latest_routing_entry(d)`` to wait for a routing entry.
    When ``until`` is None, returns as soon as the session resolves (topology /
    existence checks only).

    Raises :class:`AssertionError` if no session (or no ``until`` state) appears
    within ``timeout``.
    """
    params: dict[str, str] = {"connector_id": connector_id, "channel_id": channel_id}
    if thread_id is not None:
        params["thread_id"] = thread_id

    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
        session_id: str | None = None
        last_detail: dict | None = None
        while asyncio.get_event_loop().time() < deadline:
            if session_id is None:
                resp = await http.get(
                    "/api/_test/chat/sessions/lookup", params=params
                )
                resp.raise_for_status()
                session_id = resp.json().get("session_id")
            if session_id is not None:
                detail = await http.get(f"/api/chat/sessions/{session_id}")
                detail.raise_for_status()
                last_detail = detail.json()
                if until is None or until(last_detail):
                    return last_detail
            await asyncio.sleep(poll_interval)

        if not session_id:
            raise AssertionError(
                "no connector-attached session resolved for "
                f"connector_id={connector_id!r} channel_id={channel_id!r} "
                f"thread_id={thread_id!r} within {timeout}s. First suspects: "
                "ingest_bots not set on the test connector, the sender bot not "
                "on the allowlist, or a wrong connector id (check `docker logs`)."
            )
        _d = last_detail or {}
        n_msgs = len(_d.get("messages") or [])
        n_routing = len((_d.get("session_metadata") or {}).get("routing") or [])
        raise AssertionError(
            f"session {session_id} resolved but the `until` condition was not "
            f"met within {timeout}s (last messages={n_msgs}, routing={n_routing}). "
            "If the agent's LLM step is slow, raise the timeout; check "
            "`docker logs` for a step error."
        )


def latest_routing_entry(detail: dict) -> dict | None:
    """Return the most-recent ``session_metadata.routing`` entry, or None."""
    meta = detail.get("session_metadata") or {}
    routing = meta.get("routing") or []
    return routing[-1] if routing else None


def inbound_peer_names(detail: dict) -> list[str]:
    """Extract ``peer_name`` from inbound (``role == "user"``) messages.

    Only ``user``-role messages carry the F6 peer attribution; assistant /
    system messages are excluded (the non-blocking review note: filter on
    role before reading peer_name).
    """
    names: list[str] = []
    for msg in detail.get("messages") or []:
        if msg.get("role") != "user":
            continue
        name = msg.get("peer_name")
        if name:
            names.append(name)
    return names


# ── per-agent ACL overlay helpers ────────────────────────────────────────
#
# ``PUT /api/agents/{name}`` is a FULL-config replace (the route runs
# ``AgentConfig.model_validate(data)`` and saves the whole config — a partial
# PUT wipes other fields). So every overlay mutation GETs the full agent body,
# mutates only ``connector_acls``, and PUTs the whole body back. Agent names
# carry spaces ("Connector Agent 1"), so URL-encode the path segment.


async def set_agent_connector_acl(
    base_url: str,
    agent_name: str,
    account_id: str,
    acl: dict,
) -> dict | None:
    """Set the per-agent ACL overlay for ``account_id`` on ``agent_name``.

    GETs the full agent body, merges ``{account_id: acl}`` into its
    ``connector_acls`` (preserving any other accounts' overlays), and PUTs the
    full body back. ``acl`` is the inner overlay dict, e.g.
    ``{"peers": [{"id": bot0}], "channels": None}`` — note ``channels: None``
    (inherit) NOT ``[]`` (the DMs-only sentinel that denies guild messages).

    Returns the PRIOR ``connector_acls`` value (the whole dict, or ``None`` if
    the agent had none) so the caller can restore it exactly via
    :func:`restore_agent_connector_acls`.
    """
    path = f"/api/agents/{quote(agent_name)}"
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
        resp = await http.get(path)
        resp.raise_for_status()
        body = resp.json()
        prior = body.get("connector_acls")
        # Shallow-copy the prior overlays so the merge doesn't depend on the
        # PUT side-effecting the GET'd dict; an explicit None prior → {}.
        body["connector_acls"] = {**(prior or {}), account_id: acl}
        put = await http.put(path, json=body)
        put.raise_for_status()
    return prior


async def restore_agent_connector_acls(
    base_url: str,
    agent_name: str,
    prior: dict | None,
) -> None:
    """Restore ``agent_name``'s ``connector_acls`` to ``prior`` exactly.

    GETs the full agent body, replaces ``connector_acls`` wholesale with
    ``prior`` (the value captured by :func:`set_agent_connector_acl`), and PUTs
    the full body. Restores to the captured pre-test value — ``None`` is a
    legitimate prior, not "no-op".
    """
    path = f"/api/agents/{quote(agent_name)}"
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
        resp = await http.get(path)
        resp.raise_for_status()
        body = resp.json()
        body["connector_acls"] = prior
        put = await http.put(path, json=body)
        put.raise_for_status()


# ── connector routing-rules helpers ──────────────────────────────────────
#
# ``PUT /api/connectors/{account_id}`` shallow-merges the supplied ``config``
# and PRESERVES the existing ``secrets`` (e.g. the bot token) when the body
# omits a ``secrets`` key (``update_connector`` at ``api.py:2489`` keeps
# ``existing.secrets``). So every routing mutation GETs the full connector,
# rewrites only ``config["routing"]``, and PUTs ``{"config": config}`` with NO
# ``secrets`` key — the token is never round-tripped. The routing dict shape is
# ``{"rules": list[RoutingRule], "default": str | None}`` (BOTH keys required
# when ``routing`` is non-None); ``RoutingRule`` is
# ``{"scope": ..., "match": list[str], "agent": str}`` (``match`` is a LIST).


async def set_connector_routing(
    base_url: str,
    connector_id: str,
    routing: dict,
) -> dict | None:
    """Set the connector's ``config["routing"]`` to ``routing``.

    GETs the full connector body, takes its ``config``, records the PRIOR
    ``config.get("routing")`` (``None`` when no routing was configured), sets
    ``config["routing"] = routing``, and PUTs ``{"config": config}`` WITHOUT a
    ``secrets`` key (so the bot token is preserved). ``routing`` must carry both
    ``"rules"`` and ``"default"`` keys.

    Returns the PRIOR routing value (the dict, or ``None``) so the caller can
    restore it exactly via :func:`restore_connector_routing`.
    """
    path = f"/api/connectors/{connector_id}"
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
        resp = await http.get(path)
        resp.raise_for_status()
        body = resp.json()
        config = body["config"]
        prior = config.get("routing")
        config["routing"] = routing
        # PUT only `config` (no `secrets`) → the token is preserved.
        put = await http.put(path, json={"config": config})
        put.raise_for_status()
    return prior


async def restore_connector_routing(
    base_url: str,
    connector_id: str,
    prior: dict | None,
) -> None:
    """Restore the connector's ``config["routing"]`` to ``prior`` exactly.

    GETs the full connector body, sets ``config["routing"] = prior`` (``None``
    is a legitimate prior — "no routing configured", NOT a no-op), and PUTs
    ``{"config": config}`` WITHOUT a ``secrets`` key (token preserved).
    """
    path = f"/api/connectors/{connector_id}"
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
        resp = await http.get(path)
        resp.raise_for_status()
        body = resp.json()
        config = body["config"]
        config["routing"] = prior
        put = await http.put(path, json={"config": config})
        put.raise_for_status()


# ── connector allowlist helpers ──────────────────────────────────────────
#
# Same ``PUT /api/connectors/{account_id}`` shallow-merge-config + preserve-
# secrets pattern as the routing helpers above: GET the full connector, rewrite
# only ``config["allowlist"]``, PUT ``{"config": config}`` with NO ``secrets``
# key (the bot token is preserved by ``update_connector``). The allowlist dict
# shape is validated by ``the_one/db/models.py`` (~:354-390): ``peers`` and
# ``channels`` are REQUIRED keys; account-scope ``peers`` entries are structured
# ``{id: str, dm_allowed: bool}`` dicts (bare strings AND extra keys rejected),
# ``channels`` are ``{guild_id, channel_id}`` tuples; ``guilds`` / ``roles`` /
# ``dm_admission`` are optional.


async def set_connector_allowlist(
    base_url: str,
    connector_id: str,
    allowlist: dict,
) -> dict | None:
    """Set the connector's ``config["allowlist"]`` to ``allowlist``.

    GETs the full connector body, takes its ``config``, records the PRIOR
    ``config.get("allowlist")`` (``None`` when none configured), sets
    ``config["allowlist"] = allowlist``, and PUTs ``{"config": config}`` WITHOUT
    a ``secrets`` key (so the bot token is preserved). ``allowlist`` must carry
    both the REQUIRED ``"peers"`` and ``"channels"`` keys, and account-scope
    ``peers`` entries must be ``{id, dm_allowed}`` structured dicts (the v24
    shape the Pydantic validator at ``models.py:~354-390`` enforces — bare
    strings AND extra keys are rejected).

    Returns the PRIOR allowlist value (the dict, or ``None``) so the caller can
    restore it exactly via :func:`restore_connector_allowlist`.
    """
    path = f"/api/connectors/{connector_id}"
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
        resp = await http.get(path)
        resp.raise_for_status()
        body = resp.json()
        config = body["config"]
        prior = config.get("allowlist")
        config["allowlist"] = allowlist
        # PUT only `config` (no `secrets`) → the token is preserved.
        put = await http.put(path, json={"config": config})
        put.raise_for_status()
    return prior


async def restore_connector_allowlist(
    base_url: str,
    connector_id: str,
    prior: dict | None,
) -> None:
    """Restore the connector's ``config["allowlist"]`` to ``prior`` exactly.

    GETs the full connector body, sets ``config["allowlist"] = prior`` (``None``
    is a legitimate prior — "no allowlist configured", NOT a no-op), and PUTs
    ``{"config": config}`` WITHOUT a ``secrets`` key (token preserved).
    """
    path = f"/api/connectors/{connector_id}"
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
        resp = await http.get(path)
        resp.raise_for_status()
        body = resp.json()
        config = body["config"]
        config["allowlist"] = prior
        put = await http.put(path, json={"config": config})
        put.raise_for_status()


async def post_and_wait_new_routing(
    base_url: str,
    connector_id: str,
    channel_id: str,
    bots: BotDriver,
    sender_idx: int,
    content: str,
    *,
    until_entry: Callable[[dict], bool] | None = None,
    timeout: float = 90.0,
    poll_interval: float = 1.0,
) -> dict:
    """Post ``content`` from ``bots[sender_idx]`` and return the NEW routing
    entry it produces.

    Records the session's routing length BEFORE posting, posts the message,
    then polls the session detail until a new entry has landed AND the latest
    entry satisfies the terminal predicate — returning that latest entry. Used
    for the ACL phases: routing entries carry no ``peer_id``, so the only
    reliable way to correlate "this peer → this agent" is to post one bot at a
    time and read the single new entry.

    ``until_entry`` selects which latest entry counts as terminal. When ``None``
    (the default — used by the L4/L5 ACL/rule callers, which is byte-for-byte
    unchanged from those legs), the helper waits for the latest entry's
    ``disposition`` to be ``stepped`` or ``no-eligible`` (an engaged-or-denied
    routing decision). When PROVIDED, the helper waits until the latest entry
    satisfies ``until_entry(latest)`` — e.g. pass
    ``until_entry=lambda e: e.get("disposition") == "command-intercepted"`` to
    wait for a text-prefix command (``/talk-to``, ``/new``) which is intercepted
    at dispatch step 11 with NO LLM step (fast) and never reaches the engagement
    gate, so its disposition is ``command-intercepted`` (NOT ``stepped``).

    The before-length is read from the current session detail (the session
    already exists from Phase A). Raises :class:`AssertionError` (via
    :func:`wait_for_session`) if no new matching entry lands within ``timeout``.
    """
    if until_entry is None:
        # Default (L4/L5): a terminal engaged/denied routing decision.
        def until_entry(entry: dict) -> bool:
            return entry.get("disposition") in {"stepped", "no-eligible"}

    def _routing_len(detail: dict) -> int:
        meta = detail.get("session_metadata") or {}
        return len(meta.get("routing") or [])

    # Snapshot the routing length before posting so we can detect a NEW entry
    # (not a re-read of a historical one from an earlier phase).
    before_detail = await wait_for_session(base_url, connector_id, channel_id)
    before = _routing_len(before_detail)

    await bots.post(sender_idx, channel_id, content)

    detail = await wait_for_session(
        base_url,
        connector_id,
        channel_id,
        until=lambda d: _routing_len(d) > before
        and until_entry(latest_routing_entry(d) or {}),
        timeout=timeout,
        poll_interval=poll_interval,
    )
    entry = latest_routing_entry(detail)
    assert entry is not None  # guaranteed by the until predicate
    return entry
