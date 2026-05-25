"""Shared post-step ``Message``-metadata mutators for the connector dispatcher.

F7 L1: lifted home for the post-step Message-mutation idiom codified
by ``agents.md``'s ``post-step-dispatcher-message-metadata-binding``
convention. The connector dispatcher (and the F5 WS-storage-edge
shim, for the visibility mutator) attaches metadata to messages
that ``agent.step`` has appended — visibility tags, peer_name, and
(forthcoming at L3) channel context. Each mutator is a pure-by-
construction function that walks ``messages[pre_step_len:]`` (or
addresses ``messages[pre_step_len]`` directly) and mutates in place.

**Composition contract** (per ``agents.md``'s
``post-step-dispatcher-message-metadata-binding``):

- Each mutator's docstring names the ``Role``\\ s it touches and the
  ``Role``\\ s it skips. The non-overlap claim across mutators is
  verifiable by inspecting the two docstrings in tandem — readers
  do not have to reason about iteration bodies.
- Mutators iterate ``messages[pre_step_len:]`` exclusively; pre-
  existing history at indices ``< pre_step_len`` is never touched.
- Mutation happens inside the dispatcher's existing per-session
  lock (``session_locks[session_row.id]`` at ``_inbound.py``) and
  inside the existing ``try`` block wrapping ``agent.step``; the
  mutators inherit concurrency + exception-path semantics from the
  surrounding scaffolding.
- A runtime ``assert`` documents any single-message invariant a
  mutator relies on; the convention pairs each ``assert`` with a
  unit test that pins the same invariant so it survives ``python
  -O`` (which strips ``assert``\\ s).

History:

- ``tag_post_step_visibility`` — M10 F4 L4 (origin) + M10 F5 L3
  (extracted to ``connectors/visibility.py`` so the WS-storage-edge
  shim could share it). Relocated here at F7 L1.
- ``bind_peer_name`` — M11 F6 L3 (origin: inline mutation at
  ``_inbound.py:660-663``). Extracted into a named function here
  at F7 L1 as the n=3 trigger of
  ``post-step-dispatcher-message-metadata-binding`` was met by
  F7's channel-context binding (lands at F7 L3).
- ``bind_channel_context`` — M11 F7 L3. Channel context (id +
  optional name) on the appended USER message; ``channel_id`` comes
  from the envelope, ``channel_name`` is resolved from the F3 L4
  discoverable-entities cache (via :func:`resolve_channel_name`).
  Same Role-touch / Role-skip shape as :func:`bind_peer_name` —
  addresses ``messages[pre_step_len]`` exclusively. Lands alongside
  the channel-context fields on ``Message`` introduced at F7 L2.
"""

from __future__ import annotations

from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX
from the_one.connectors.base import DiscoverableEntities
from the_one.llm.base import Message, Role


def tag_post_step_visibility(
    messages: list[Message],
    pre_step_len: int,
) -> None:
    """Apply post-step visibility rules to messages appended by ``agent.step``.

    **Touches**: every ``Role`` EXCEPT ``Role.USER`` — i.e.
    ``Role.ASSISTANT`` and ``Role.TOOL`` messages at or after
    ``pre_step_len`` have their ``visibility`` overwritten.

    **Skips**: ``Role.USER`` messages at or after ``pre_step_len``.
    The peer-inbound dispatcher constructs USER with
    ``visibility=None`` (peer-visible); the operator-input WS shim
    constructs USER with ``visibility=OPERATOR_VISIBILITY``. Either
    way, the post-step pass does not touch the USER message — its
    visibility is the caller's contract.

    This is the **composition complement** of :func:`bind_peer_name`,
    which touches ``Role.USER`` exclusively and skips every other
    role; the two mutators address disjoint slices of
    ``messages[pre_step_len:]`` and cannot conflict by construction.

    Mutates ``messages`` in place. Returns ``None``. Caller is
    responsible for tagging the entry-point USER message at
    construction time (BEFORE ``agent.step``); this helper does not
    touch it.

    ``pre_step_len`` is the length of ``messages`` BEFORE the
    ``agent.step`` call. The helper iterates
    ``messages[pre_step_len:]`` and applies the rules below.

    Tagging rules (preserved verbatim from M10 F4 L4):

    - ``Role.USER`` messages at or after ``pre_step_len`` are
      SKIPPED (see above).
    - ``Role.TOOL`` whose parent ``tool_call.name ==
      "send_to_platform_channel"`` AND content starts with
      ``PLATFORM_SEND_OK_PREFIX`` → ``visibility=None`` (peer-visible;
      the platform-send tool already pushed the content to peers).
    - Everything else → ``OPERATOR_VISIBILITY`` (assistant text +
      intermediate tool calls/results stay operator-only).
    - Messages at indices ``< pre_step_len`` (the pre-existing
      history) are NEVER touched.

    Relocated from :mod:`the_one.connectors.visibility` at F7 L1 as
    part of the n=3 lift codified by
    ``post-step-dispatcher-message-metadata-binding``. The original
    module survives as a deprecation re-export shim.
    """
    new_msgs = messages[pre_step_len:]
    tool_call_names: dict[str, str] = {}
    for msg in new_msgs:
        if msg.role == Role.ASSISTANT:
            for tc in msg.tool_calls:
                tool_call_names[tc.id] = tc.name
    for msg in new_msgs:
        if msg.role == Role.USER:
            continue
        is_successful_platform_send = (
            msg.role == Role.TOOL
            and msg.tool_result is not None
            and tool_call_names.get(msg.tool_result.tool_call_id)
            == "send_to_platform_channel"
            and msg.content.startswith(PLATFORM_SEND_OK_PREFIX)
        )
        msg.visibility = (
            None if is_successful_platform_send else OPERATOR_VISIBILITY
        )


def bind_peer_name(
    messages: list[Message],
    pre_step_len: int,
    peer_name: str | None,
) -> None:
    """Bind ``peer_name`` onto the USER message ``agent.step`` appended.

    **Touches**: ``Role.USER`` only — the single message at
    ``messages[pre_step_len]``, which is the USER message
    ``Agent.step`` appended at the start of its loop.

    **Skips**: every other ``Role``. This mutator addresses
    ``messages[pre_step_len]`` directly and never iterates other
    indices.

    This is the **composition complement** of
    :func:`tag_post_step_visibility`, which touches every role
    EXCEPT ``Role.USER`` and skips USER; the two mutators address
    disjoint slices of ``messages[pre_step_len:]`` and cannot
    conflict by construction.

    Mutates ``messages[pre_step_len]`` in place. Returns ``None``.
    ``peer_name=None`` is allowed — the assignment then leaves the
    field at its default for any plugin without a peer-name concept
    (non-Discord connectors emitting ``working_envelope.peer_name=
    None``).

    Asserts ``messages[pre_step_len].role == Role.USER`` at runtime
    so a future ``agent.step`` regression that fails to append a
    USER message surfaces here, not at the next consumer. Per
    ``agents.md``'s ``post-step-dispatcher-message-metadata-binding``
    convention, the runtime ``assert`` is paired with a unit test
    that pins the same invariant so it survives ``python -O``.

    History: extracted from ``_inbound.py:660-663`` at F7 L1; the
    original M11 F6 L3 introduced the binding as an inline mutation.
    The inline comment block at the call site (documenting WHY the
    binding happens here — mission constraint forbids modifying
    ``agent/core.py`` to populate ``peer_name`` at append-time) is
    preserved at the call site; this docstring documents WHAT.
    """
    assert messages[pre_step_len].role == Role.USER, (
        "agent.step must append a Role.USER message at pre_step_len"
    )
    messages[pre_step_len].peer_name = peer_name


def resolve_channel_name(
    cache: DiscoverableEntities | None,
    channel_id: str,
) -> str | None:
    """Resolve a friendly channel label from the F3 L4 discoverable-entities cache.

    Returns the matching channel entity's ``label`` if one exists with
    ``id == channel_id``; returns ``None`` when the cache is ``None``
    (cold pool, plugin doesn't implement
    ``enumerate_discoverable_entities``, or the first refresh hasn't
    landed) or when no matching entry is found (stale cache, channel
    deleted, bot kicked).

    Pure synchronous walk over ``cache.channels``. The caller (the
    dispatcher's post-step block in :mod:`the_one.connectors._inbound`)
    fetches the cache snapshot async upstream so this helper stays
    sync-and-testable.

    M11 F7 L3 — companion to :func:`bind_channel_context`. Kept on the
    module's public surface (no leading underscore) so it can be imported
    by ``_inbound.py``.
    """
    if cache is None:
        return None
    for entity in cache.channels:
        if entity.id == channel_id:
            return entity.label
    return None


def bind_channel_context(
    messages: list[Message],
    pre_step_len: int,
    channel_id: str,
    channel_name: str | None,
) -> None:
    """Bind channel context onto the USER message ``agent.step`` appended.

    **Touches**: ``Role.USER`` only — the single message at
    ``messages[pre_step_len]``, which is the USER message
    ``Agent.step`` appended at the start of its loop.

    **Skips**: every other ``Role``. This mutator addresses
    ``messages[pre_step_len]`` directly and never iterates other
    indices. Same Role-scope as :func:`bind_peer_name` and
    composition complement of :func:`tag_post_step_visibility`
    (which skips USER and touches every other role); the three
    mutators address disjoint slices of ``messages[pre_step_len:]``
    and cannot conflict by construction (n=3 set per ``agents.md``'s
    ``post-step-dispatcher-message-metadata-binding`` convention).

    ``channel_id`` is bound unconditionally — the envelope always
    carries one (see :class:`the_one.connectors.base.InboundEnvelope`
    invariant: Discord's translator at ``_discord_translate.py:122``
    sets ``channel_id=channel_id_str`` for every inbound; non-Discord
    plugins follow the same shape).

    ``channel_name`` may be ``None`` when the F3 L4 discoverable-
    entities cache hasn't resolved a label (cold pool, stub plugin,
    cache miss after a fresh platform-side channel creation); the
    field stays ``None`` and L4's provider projection handles
    partial-absence gracefully.

    Mutates ``messages[pre_step_len]`` in place. Returns ``None``.

    Asserts ``messages[pre_step_len].role == Role.USER`` at runtime
    so a future ``agent.step`` regression that fails to append a
    USER message surfaces here, not at the next consumer. Per
    ``agents.md``'s ``post-step-dispatcher-message-metadata-binding``
    convention, the runtime ``assert`` is paired with a unit test
    that pins the same invariant so it survives ``python -O``.

    M11 F7 L3 (added to the lifted module's n=3 set; see
    ``agents.md`` § ``post-step-dispatcher-message-metadata-binding``).
    """
    assert messages[pre_step_len].role == Role.USER, (
        "agent.step must append a Role.USER message at pre_step_len"
    )
    messages[pre_step_len].channel_id = channel_id
    messages[pre_step_len].channel_name = channel_name
