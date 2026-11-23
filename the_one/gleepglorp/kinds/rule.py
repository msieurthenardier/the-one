"""The ``rule`` kind: add or change one of an agent's rules (M36 F4 L1a, DD2)."""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Any

import aiosqlite

from the_one.agent import rules_service
from the_one.db._rules import RuleLimitError, validate_rule_text
from the_one.gleepglorp.kinds.agent import existing_agent
from the_one.gleepglorp.kinds.base import Kind, changed_labels
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import reraise
from the_one.gleepglorp.proposals.shape import FieldSpec, Normalized, ShapeError, _bad, _check_int
from the_one.gleepglorp.proposals.store import Proposal

RULE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("text", "text", "Rule", "text", create_required=True),
    FieldSpec("enabled", "boolean", "On", "enabled"),
    FieldSpec(
        "position",
        "integer",
        "Position",
        "position",
        hint="1-based; omit for last",
        min=1,
        create_only=True,
    ),
)


def _rule_repo(conn: aiosqlite.Connection) -> Any:
    from the_one.db.repositories import AgentRuleRepository

    return AgentRuleRepository(conn)


async def normalize(
    action: str,
    target: dict[str, Any],
    changes: dict[str, Any],
    *,
    conn: Any,
    now: datetime,
    zone: tzinfo,
    enc: Any = None,
    mode: str = "propose",
) -> Normalized:
    agent = await existing_agent(conn, target.get("agent"))
    stored: dict[str, Any] = {}
    for f in RULE_FIELDS:
        if f.name not in changes:
            continue
        value = changes[f.name]
        if f.type == "text":
            if not isinstance(value, str):
                raise _bad(f, "text")
            try:
                stored["text"] = validate_rule_text(value)
            except RuleLimitError as e:
                raise ShapeError(e.detail) from None
        elif f.type == "boolean":
            if not isinstance(value, bool):
                raise _bad(f, "true or false")
            stored[f.stored] = value
        else:
            stored[f.stored] = _check_int(f, value)
    repo = _rule_repo(conn)
    rules = await repo.list_for_agent(agent)
    if action == "create":
        return Normalized("rule", "create", agent, None, f"rule:{agent}:new", stored, None)
    pos = target.get("rule")
    if isinstance(pos, bool) or not isinstance(pos, int):
        raise ShapeError("Say which rule: give rule, its number in the agent's list (from 1).")
    if not 1 <= pos <= len(rules):
        raise ShapeError(f"{agent} has {len(rules)} rules; there is no rule {pos}.")
    rule = rules[pos - 1]
    base = {f: getattr(rule, f) for f in stored}
    return Normalized("rule", "change", agent, rule.id, f"rule:{agent}:{rule.id}", stored, base)


async def exists(conn: aiosqlite.Connection, deps: KindDeps, p: Proposal) -> bool:
    if not p.agent_name or not await deps.agent.store.exists(p.agent_name):
        return False
    if p.action == "create":
        return True
    rules = await _rule_repo(conn).list_for_agent(p.agent_name)
    return any(r.id == p.target_id for r in rules)


async def apply(
    conn: aiosqlite.Connection,
    deps: KindDeps,
    p: Proposal,
    *,
    changes: dict[str, Any],
    base: dict[str, Any],
    override: bool,
    now: datetime,
    zone: Any,
    mark: Any,
    runner: Any,
    result: dict[str, Any],
) -> str | None:
    try:
        assert p.agent_name is not None
        if p.action == "create":
            pos = changes.get("position")
            await rules_service.create_rule(
                _rule_repo(conn),
                p.agent_name,
                changes["text"],
                changes.get("enabled", True),
                position=None if pos is None else pos - 1,
                on_commit=mark,
            )
        else:
            assert p.target_id is not None
            await rules_service.change_rule(
                _rule_repo(conn),
                p.agent_name,
                p.target_id,
                changes,
                base=base,
                override=override,
                on_commit=mark,
            )
    except Exception as exc:  # noqa: BLE001 - translated, or re-raised unchanged
        await reraise(exc, p, conn=conn, zone=zone)
    return None


async def summary_text(p: Proposal, zone: Any) -> dict[str, Any]:
    labels = changed_labels(RULE_FIELDS, p)
    agent = p.agent_name or ""
    text = (
        f"Added a rule to {agent}"
        if p.action == "create"
        else f"Changed a rule of {agent}: {', '.join(labels)}"
    )
    return {"summary": text, "agent": agent, "fields": labels}


KIND = Kind(
    name="rule",
    label="rule",
    summary="Add or change one of an agent's rules",
    fields=RULE_FIELDS,
    normalize=normalize,
    exists=exists,
    apply=apply,
    summary_text=summary_text,
)
