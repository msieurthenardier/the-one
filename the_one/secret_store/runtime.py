"""Secrets at run time (sortie 10, DD7).

:class:`SecretResolver` is injected into every factory-built ``Agent``. For each tool
call, :meth:`SecretResolver.prepare` fills ``{{secret:key}}`` placeholders into a *copy*
of the arguments, refuses a call that names a secret the agent isn't granted or a tool
the secret isn't allowed in, and returns a masker that replaces every stored value in
the tool's output with ``[secret:key]``. The model, the stored session and the provider
request therefore only ever hold the placeholder.

Reads are never cached: every ``prepare`` reads the current values and grants, so an
edit, a rotation or a grant change applies on the next call to an already-open Agent.
Any failure to read fails closed (the call is refused, never run unmasked).

Import rule: ``the_one.agent.core`` imports this module, so the agent package's
``_context`` is imported lazily, inside a function.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from the_one.secret_store.refused import is_refused_tool

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"\{\{secret:([A-Za-z0-9_-]{1,64})\}\}")

UNAVAILABLE_MESSAGE = "Secrets are unavailable right now, so this tool call was not run."
WITHHELD_MESSAGE = "The tool's output could not be checked for secrets, so it was withheld."


class SecretMaskError(Exception):
    """Masking a tool result failed; the output must be withheld."""


def _needles(value: str) -> set[str]:
    out = {
        value,
        repr(value)[1:-1],
        json.dumps(value, ensure_ascii=True)[1:-1],
        json.dumps(value, ensure_ascii=False)[1:-1],
        urllib.parse.quote(value, safe=""),
        urllib.parse.quote_plus(value),
    }
    out.discard("")
    return out


def build_masker(values: list[tuple[str, str]]) -> Callable[[Any], Any]:
    """A pure masker for ``[(stored_key, plaintext)]``; identity when there are none."""
    needle_key: dict[str, str] = {}
    for key, value in values:
        for needle in _needles(value):
            needle_key.setdefault(needle, key)
    if not needle_key:
        return lambda obj: obj
    # One pass, longest needle first: a replacement is never re-scanned.
    pattern = re.compile(
        "|".join(re.escape(n) for n in sorted(needle_key, key=lambda n: (-len(n), n)))
    )

    def _sub(m: re.Match[str]) -> str:
        return f"[secret:{needle_key[m.group(0)]}]"

    def mask(obj: Any) -> Any:
        if isinstance(obj, str):
            return pattern.sub(_sub, obj)
        if isinstance(obj, dict):
            return {(mask(k) if isinstance(k, str) else k): mask(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [mask(v) for v in obj]
        return obj

    return mask


@dataclass
class Prepared:
    """The outcome of :meth:`SecretResolver.prepare`."""

    args: dict[str, Any]
    mask: Callable[[Any], Any]
    refusal: str | None = None

    def safe_mask(self, obj: Any) -> Any:
        """:attr:`mask`, with any failure raised as :class:`SecretMaskError`."""
        try:
            return self.mask(obj)
        except Exception as e:  # noqa: BLE001 - never let a masker fault leak output
            raise SecretMaskError from e


def _identity(obj: Any) -> Any:
    return obj


def _refuse(message: str) -> Prepared:
    return Prepared(args={}, mask=_identity, refusal=message)


def _collect(obj: Any, found: list[str]) -> None:
    if isinstance(obj, str):
        found.extend(m.group(1) for m in TOKEN_RE.finditer(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect(v, found)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect(v, found)


def _fill(obj: Any, lookup: Callable[[str], str]) -> Any:
    if isinstance(obj, str):
        return TOKEN_RE.sub(lambda m: lookup(m.group(1)), obj)
    if isinstance(obj, dict):
        return {k: _fill(v, lookup) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill(v, lookup) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_fill(v, lookup) for v in obj)
    return obj


class SecretResolver:
    """Per-agent resolver; reads the database afresh on every call."""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    async def _grant_agent(self, conn: Any) -> str:
        # Lazy: importing ``the_one.agent`` at load would cycle through ``core``.
        from the_one.agent._context import current_chat_session_id, current_turn

        turn = current_turn.get()
        session_id = (
            turn.session_id if turn is not None else None
        ) or current_chat_session_id.get()
        if session_id:
            async with conn.execute(
                "SELECT agent_name FROM chat_sessions WHERE id = ?", (session_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is not None and row[0]:
                return row[0]
        return self.agent_name

    async def prepare(self, tool_name: str, args: dict[str, Any]) -> Prepared:
        written: list[str] = []
        _collect(args, written)
        try:
            from the_one.db.connection import get_connection
            from the_one.db.repositories import SecretRepository

            conn = await get_connection()
            repo = SecretRepository(conn)
            agent = await self._grant_agent(conn)
            values = await repo.all_values()
            # Any token goes through the lookup (an unknown key is refused, even with an
            # empty Library); only no tokens and no stored values take the fast path.
            if not values and not written:
                return Prepared(args=args, mask=_identity)
            secrets = await repo.list()
            async with conn.execute(
                "SELECT secret_ids FROM agents WHERE name = ?", (agent,)
            ) as cur:
                row = await cur.fetchone()
            try:
                granted_raw = json.loads(row[0] or "[]") if row is not None else []
            except ValueError:
                granted_raw = []
            granted = {g for g in granted_raw if isinstance(g, str)}
            mask = build_masker([(k, v) for _sid, k, v in values])
        except Exception:  # noqa: BLE001 - fail closed; no value or detail is logged
            logger.warning("Secrets could not be loaded for a tool call", exc_info=False)
            return _refuse(UNAVAILABLE_MESSAGE)

        by_key = {ref.key.lower(): s for s in secrets for ref in s.values if ref.key}
        plain = {(k.lower()): v for _sid, k, v in values}
        for key in written:
            secret = by_key.get(key.lower())
            if secret is None or secret.id not in granted:
                return _refuse(f"Secret `{key}` is not granted to this agent.")
            if is_refused_tool(tool_name) or tool_name not in secret.allowed_tools:
                return _refuse(f"Secret `{key}` can't be used with the tool `{tool_name}`.")
        if not written:
            return Prepared(args=args, mask=mask)
        return Prepared(args=_fill(args, lambda k: plain[k.lower()]), mask=mask)
