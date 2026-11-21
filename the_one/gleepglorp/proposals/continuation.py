"""What happens in the chat after the operator resolves a proposal (M36 F2 L5, DD8).

An approval starts GleepGlorp's next turn with a marked message, so a request with several
steps continues one step at a time. A dismissal, or an approval while GleepGlorp is not
ready, is recorded in the chat as a marked message with no turn.

The turn host is the neutral seam in ``the_one.sessions.turn_host`` (nothing here imports
``interfaces``). With no host registered (the eval harness has no server) every function
here returns quietly: the harness passes ``continue_chat=False`` to the apply functions and
drives the continuation itself with :func:`approval_text`.
"""

from __future__ import annotations

import logging
from typing import Any

import aiosqlite

from the_one.gleepglorp import kinds
from the_one.gleepglorp import settings as gg_settings
from the_one.gleepglorp.kinds.base import default_title
from the_one.gleepglorp.proposals.store import Proposal
from the_one.sessions.turn_host import get_turn_host

logger = logging.getLogger(__name__)

APPROVAL_TEXT = "Approved proposal {id}: {summary}. Continue with the next step, if there is one."
DISMISSAL_TEXT = "Dismissed proposal {id} ({title}). Do not apply it."


def approval_text(proposal_id: int, summary: str) -> str:
    return APPROVAL_TEXT.format(id=proposal_id, summary=summary)


def dismissal_text(proposal_id: int, title: str) -> str:
    return DISMISSAL_TEXT.format(id=proposal_id, title=title)


def proposal_title(p: Proposal) -> str:
    """The card title's wording, e.g. ``change agent Issue digest``."""
    try:
        return kinds.get(p.kind).title(p)
    except KeyError:  # a kind this build does not know: the generic wording
        return default_title(p)


async def is_ready(conn: aiosqlite.Connection) -> bool:
    """The one readiness check (the race branch in the web app uses the same function)."""
    return await gg_settings.state(conn, await gg_settings.load_settings(conn)) == "ready"


async def on_approved(conn: aiosqlite.Connection, p: Proposal, summary: str) -> None:
    """Start the continuation turn, or record the approval with no turn. Never raises."""
    host = get_turn_host()
    if host is None:
        logger.debug("proposal %s approved: no turn host, no continuation", p.id)
        return
    text = approval_text(p.id, summary)
    try:
        session, _status = await host.get_or_restore(p.session_id)
        if session is None:
            return
        if await is_ready(conn):
            try:
                host.spawn_turn(session, text, {"proposal": {"id": p.id, "event": "approved"}})
                return
            except Exception:
                logger.warning("could not start the approval turn for %s", p.id, exc_info=True)
        await _append(host, p, text, "approved_no_turn")
    except Exception:
        logger.warning("approval continuation for proposal %s failed", p.id, exc_info=True)


async def on_dismissed(p: Proposal) -> None:
    """Record the dismissal in the chat with no turn. Never raises."""
    host = get_turn_host()
    if host is None:
        logger.debug("proposal %s dismissed: no turn host", p.id)
        return
    try:
        await _append(host, p, dismissal_text(p.id, proposal_title(p)), "dismissed")
    except Exception:
        logger.warning("dismissal message for proposal %s failed", p.id, exc_info=True)


async def _append(host: Any, p: Proposal, text: str, event: str) -> None:
    await host.append_marked_message(
        p.session_id, text, {"proposal_id": p.id, "proposal_event": event}
    )
