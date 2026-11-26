"""Rule writes shared by the rule routes and (Mission 36 F2) the proposal approval path.

Both take validated primitives (the request body models stay in the interface layer) and
the rule repository as an argument. A refusal is an :class:`AgentWriteError` carrying the
status and ``detail`` the route returned before this module existed. Nothing here imports
``the_one.interfaces``.
"""

from __future__ import annotations

import logging
from typing import Any

from the_one.agent.service import AgentStaleError, AgentWriteError, OnCommit
from the_one.db._rules import RuleLimitError
from the_one.db.models import AgentRule
from the_one.db.repositories import AgentRuleRepository

logger = logging.getLogger(__name__)

# The fields change_rule may set (a move is the reorder route's job).
CHANGEABLE_RULE_FIELDS = ("text", "enabled")


def _not_found(rule_id: str) -> AgentWriteError:
    return AgentWriteError(404, f"Rule not found: {rule_id}")


async def create_rule(
    repo: AgentRuleRepository,
    agent: str,
    text: str,
    enabled: bool = True,
    position: int | None = None,
    on_commit: OnCommit | None = None,
) -> AgentRule:
    """Add a rule for ``agent`` (``position`` None appends; an int inserts there, the rest
    move down). The total-characters limit is a 422 on the same detail as the route's."""
    try:
        rule = await repo.create(agent, text, enabled, position=position, on_commit=on_commit)
    except RuleLimitError as e:
        raise AgentWriteError(422, e.detail) from None
    logger.info("agent %s rule %s: created", agent, rule.id)
    return rule


async def change_rule(
    repo: AgentRuleRepository,
    agent: str,
    rule_id: str,
    changes: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    override: bool = False,
    on_commit: OnCommit | None = None,
) -> AgentRule:
    """Change a rule's ``text`` and/or ``enabled`` (the keys of ``changes``).

    With ``base`` (the values the change was written against) and no ``override``, a changed
    field whose stored value differs from ``base[field]`` raises :class:`AgentStaleError`
    (naming it) and nothing is written; a field with no ``base`` entry is not compared. The
    compare runs under the write lock against the row read inside the transaction, so no
    retry is needed. A missing rule is a 404.
    """
    unknown = sorted(set(changes) - set(CHANGEABLE_RULE_FIELDS))
    if unknown:
        raise AgentWriteError(
            422,
            [
                {"type": "value_error", "loc": [key], "msg": "This field can't be changed here."}
                for key in unknown
            ],
        )

    def precheck(current: AgentRule | None) -> None:
        if current is None or base is None or override:
            return
        stale = [
            {"field": f, "current": getattr(current, f), "proposed": changes[f]}
            for f in CHANGEABLE_RULE_FIELDS
            if f in changes and f in base and getattr(current, f) != base[f]
        ]
        if stale:
            raise AgentStaleError(stale)

    try:
        rule = await repo.update(
            agent,
            rule_id,
            text=changes.get("text"),
            enabled=changes.get("enabled"),
            precheck=precheck,
            on_commit=on_commit,
        )
    except KeyError:
        raise _not_found(rule_id) from None
    except RuleLimitError as e:
        raise AgentWriteError(422, e.detail) from None
    logger.info("agent %s rule %s: changed", agent, rule_id)
    return rule
