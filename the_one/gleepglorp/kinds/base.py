"""The :class:`Kind` record: one proposable kind of change (Mission 36 F4 L1a, DD2).

A kind is declared once, in its own module (``agent``, ``rule``, ``routine``), as a frozen
``Kind`` holding its field table and the functions that act on it: normalize a model's
proposal, say whether the target still exists, apply the stored change, word the result's
summary and title the card. The registry (``the_one.gleepglorp.kinds.REGISTRY``) is an
explicit tuple of them; nothing registers itself on import.

The callables take the same arguments for every kind, so the apply path and the tools
dispatch by name and never branch on a kind.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from the_one.gleepglorp.proposals.shape import FieldSpec, Normalized

if TYPE_CHECKING:
    from the_one.gleepglorp.proposals.store import Proposal

# The proposal fields that are internal stored keys, not something the operator reads.
HIDDEN_FIELDS = ("anchor_at",)

#: ``normalize(action, target, changes, *, conn, now, zone, enc, mode="propose") -> Normalized``;
#: ``mode`` is ``"propose"`` or ``"fill"`` (only a kind with a fill-only allowance reads it).
NormalizeFn = Callable[..., Awaitable[Normalized]]
#: ``exists(conn, deps, p) -> bool``: the target of the stored proposal is still there.
ExistsFn = Callable[..., Awaitable[bool]]
#: ``apply(conn, deps, p, *, changes, base, override, now, zone, mark, runner, result)``;
#: raises ``ApplyError`` for a failure the apply records, and anything else propagates.
ApplyFn = Callable[..., Awaitable[str | None]]
#: ``summary_text(p, zone) -> {"summary", "agent", "fields", ...}``
SummaryFn = Callable[..., Awaitable[dict[str, Any]]]
#: ``resolve_target(conn, ref) -> (target_id, name)``: the existing target a model named by
#: id or name; raises ``ShapeError`` with a plain sentence for an unknown or ambiguous ref.
ResolveTargetFn = Callable[..., Awaitable[tuple[str, str]]]
#: ``warnings(conn, enc, p, mode="propose") -> list[str]``; ``mode`` is ``"propose"`` (a proposal
#: card: the operator approves) or ``"fill"`` (a fill: the operator saves the form themselves).
WarningsFn = Callable[..., Awaitable[list[str]]]
#: ``card_extras(conn, p) -> {"title": ..., "target_gone": ..., ...}``
CardExtrasFn = Callable[..., Awaitable[dict[str, Any]]]
#: ``fill_extras(conn, fill, labels) -> {"title", "target_gone", "stale", "clears_key"}``: the four
#: values ``fill_view`` cannot read off the stored fill (``labels`` maps stored field -> label).
FillExtrasFn = Callable[..., Awaitable[dict[str, Any]]]

#: How a tool call names the target of a kind: ``agent`` (an agent, with ``target`` as an alias
#: of ``agent``), ``agent-owned`` (an agent plus a rule position or routine name), ``id`` (one
#: row named by ``target``, an id or a name) or ``page`` (a page's settings, no target at all).
ADDRESSINGS = ("agent", "agent-owned", "id", "page")


def changed_labels(fields: tuple[FieldSpec, ...], p: Proposal) -> list[str]:
    """The card labels of the stored fields a proposal changes, in stored order."""
    by_stored = {f.stored: f.label for f in fields}
    return [by_stored.get(k, k) for k in p.changes if k not in HIDDEN_FIELDS]


def default_title(p: Proposal) -> str:
    """The card title's wording, e.g. ``change agent Issue digest``."""
    return f"{p.action} {p.kind} {p.agent_name or ''}".strip()


def default_card_title(kind: str, action: str, agent_name: str | None) -> str:
    quoted = f"“{agent_name}”"
    return f"{'Create' if action == 'create' else 'Change'} {kind} {quoted}"


def id_fill_extras(
    card_extras: CardExtrasFn,
    stale_fn: Callable[..., Awaitable[list[dict[str, Any]]]] | None = None,
    clears_key_fn: Callable[..., Awaitable[bool]] | None = None,
) -> FillExtrasFn:
    """The ``fill_extras`` of an id-targeted kind: title and ``target_gone`` come from the
    kind's ``card_extras`` (a lookup by id); ``stale`` from ``stale_fn(conn, fill, labels)``,
    only for a change with a base whose target is still there; ``clears_key`` from
    ``clears_key_fn(conn, fill)`` (``False`` without one)."""

    async def fill_extras(conn: Any, fill: Any, labels: dict[str, str]) -> dict[str, Any]:
        extras = await card_extras(conn, fill)
        gone = bool(extras.get("target_gone", False))
        stale: list[dict[str, Any]] = []
        if stale_fn is not None and fill.action == "change" and not gone and fill.base:
            stale = await stale_fn(conn, fill, labels)
        clears_key = await clears_key_fn(conn, fill) if clears_key_fn is not None else False
        return {
            "title": extras["title"],
            "target_gone": gone,
            "stale": stale,
            "clears_key": clears_key,
        }

    return fill_extras


def validate_kind(k: Any) -> None:
    """Raise ``ValueError`` when a kind breaks a registry rule: ``card_extras`` set, a
    ``fill_extras`` for every fillable kind, ``addressing`` one of :data:`ADDRESSINGS` and a
    ``target_noun`` for an ``"id"`` kind. Run by ``Kind.__post_init__`` and the registry test."""
    name = getattr(k, "name", "?")
    if getattr(k, "card_extras", None) is None:
        raise ValueError(f"kind {name!r} needs card_extras")
    if getattr(k, "fillable", ()) and getattr(k, "fill_extras", None) is None:
        raise ValueError(f"kind {name!r} is fillable and needs fill_extras")
    if getattr(k, "addressing", None) not in ADDRESSINGS:
        raise ValueError(f"kind {name!r} needs addressing, one of {', '.join(ADDRESSINGS)}")
    if k.addressing == "id" and not getattr(k, "target_noun", ""):
        raise ValueError(f"kind {name!r} is addressed by id and needs target_noun")


@dataclass(frozen=True)
class Kind:
    """One kind of change GleepGlorp may propose.

    ``operator_only`` names the stored fields the operator alone controls: they appear in no
    kind's ``fields`` (a test pins it). ``fillable`` lists the actions the ``fill_form`` tool
    may carry; empty means the kind is not fillable. ``title`` words the chat's marker for a
    proposal, ``card_title`` the fill card's title. ``resolve_target`` is optional (``None``):
    a kind that is targeted by id (not by an agent plus a position or name) sets it to resolve
    the model's ref to ``(id, name)`` (Leg 4's MCP server and provider kinds).
    """

    name: str
    label: str
    summary: str
    fields: tuple[FieldSpec, ...]
    normalize: NormalizeFn
    exists: ExistsFn
    apply: ApplyFn
    summary_text: SummaryFn
    #: One of :data:`ADDRESSINGS`; ``target_args`` reads it (required).
    addressing: str
    #: ``card_extras(conn, p) -> {title, target_gone, ...}``: the proposal card's title,
    #: ``target_gone`` and any kind-specific keys (required, ``validate_kind``).
    card_extras: CardExtrasFn
    operator_only: tuple[str, ...] = ()
    fillable: tuple[str, ...] = ()
    actions: tuple[str, ...] = ("create", "change")
    title: Callable[[Any], str] = default_title
    card_title: Callable[[str, str | None], str] | None = None
    resolve_target: ResolveTargetFn | None = None
    #: ``warnings(conn, enc, p, mode="propose") -> [sentence]``: what the operator should know
    #: before approving (``mode="fill"``: before saving), read from the stored row (computed for
    #: pending and failed proposals only). A kind whose sentences do not mention approval ignores
    #: ``mode``.
    warnings: WarningsFn | None = None
    #: ``target_noun``: the sentence subject of an ``"id"`` kind's refusal of ``agent`` (``"An
    #: MCP server"``). Required for ``"id"`` kinds; "a" or "an" cannot be derived from a label.
    target_noun: str = ""
    #: ``fill_extras(conn, fill, labels) -> {title, target_gone, stale, clears_key}``. Required
    #: for a fillable kind (``validate_kind``); ``None`` for a kind that is not fillable.
    fill_extras: FillExtrasFn | None = None
    #: ``operator_only_message(names) -> sentence``: the refusal for a change naming an
    #: ``operator_only`` field, in place of the generic unknown-field one.
    operator_only_message: Callable[[list[str]], str] | None = None
    #: Other names a model uses for an ``operator_only`` field: refused with the same message,
    #: but kept out of ``operator_only`` (which feeds the cross-kind ``OPERATOR_ONLY_FIELDS``).
    operator_only_aliases: tuple[str, ...] = ()
    #: ``action_refused(action, mode) -> sentence``: the refusal for an action the kind does not
    #: allow (``actions`` for a proposal, ``fillable`` for a fill), in place of the generic one.
    action_refused: Callable[[str, str], str] | None = None
    #: Whether a bare ``KeyError`` from the apply means the target is gone (the proposal is
    #: withdrawn). A kind that leaves it ``False`` gets a ``KeyError`` re-raised, not hidden.
    keyerror_is_gone: bool = False
    #: The stored keys whose values skip the guard's key-shape heuristics (the stored-secret
    #: containment and the token-prefix rule still apply to every value).
    relaxed_guard_keys: frozenset[str] = frozenset()
    #: ``create_only_message(names) -> sentence``: the refusal for a change that names a
    #: ``create_only`` field, in place of the generic one.
    create_only_message: Callable[[list[str]], str] | None = None

    def __post_init__(self) -> None:
        validate_kind(self)

    def card(self, action: str, agent_name: str | None) -> str:
        if self.card_title is not None:
            return self.card_title(action, agent_name)
        return default_card_title(self.name, action, agent_name)
