"""The ``provider`` kind: create a model provider or change its name, type, address or options
(Mission 36 F4 L5a, DD10).

GleepGlorp may set a provider's ``name`` and ``type``, its ``base_url`` (where the type shows
one) and the three options the editor shows per type: ``num_ctx`` (Ollama), ``thinking_enabled``
(the Claude types) and ``reasoning_effort``.

It never sets ``api_key`` or ``secrets``, and a key never follows a provider across a type
change: a change from one key-taking type to a different one is refused as a proposal (the
operator changes the type in the editor and enters the new key), a change into a type with no
key clears the stored key, and a change out of ``anthropic-plan`` signs the provider out. A
``mock`` provider is never created or changed. Keys and sign-in always happen on the page; the
card's warnings say so. The write is the provider write service's
(``the_one/llm/provider_service.py``), so the operator's own validation applies and the
proposal's status mark rides in the write's transaction.

A provider is targeted by id (or an unambiguous name) through ``target``; the proposal's
``agent_name`` is ``None`` and the card's name and ``target_gone`` come from a lookup by id.
``mode`` is ``"propose"`` or ``"fill"``: a fill may move between key-taking types and name the
token type, because the operator then enters the key on the form themselves (Leg 5b).
"""

from __future__ import annotations

import uuid
from datetime import datetime, tzinfo
from typing import Any
from urllib.parse import urlparse

import aiosqlite

from the_one.db._provider_types import (
    PROVIDER_TYPE_DEFAULTS,
    PROVIDER_TYPE_LABELS,
    PROVIDER_TYPES,
)
from the_one.gleepglorp.kinds.base import Kind, changed_labels, id_fill_extras
from the_one.gleepglorp.kinds.deps import KindDeps
from the_one.gleepglorp.kinds.errors import reraise
from the_one.gleepglorp.proposals.shape import (
    FieldSpec,
    Normalized,
    ShapeError,
    _bad,
    _check_int,
    _check_text,
    _q,
    _ref_entries,
)
from the_one.gleepglorp.proposals.store import Proposal
from the_one.llm import provider_service
from the_one.naming import NameRuleError, check_name

#: The types a proposal may name: every type but ``mock``.
TYPES = tuple(t for t in PROVIDER_TYPES if t != "mock")
_URL_MAX = 2000
_ANTHROPIC_PLAN = "anthropic-plan"
_PLAN_TOKEN = provider_service.PLAN_TOKEN_TYPE

#: Plain-language words per type, so a user's wording maps to the type name. The editor label
#: comes from ``PROVIDER_TYPE_LABELS`` (no drift); this adds who it is for.
_TYPE_WORDS = {
    "anthropic": "Claude with an API key",
    "anthropic-plan": "Claude Pro/Max subscription: sign in on the page",
    "anthropic-plan-token": "Claude Pro/Max subscription with a setup token",
}
_TYPE_GLOSS = ", ".join(
    f"{t} ({PROVIDER_TYPE_LABELS[t]}" + (f"; {_TYPE_WORDS[t]}" if t in _TYPE_WORDS else "") + ")"
    for t in TYPES
)

PROVIDER_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", "text", "Name", "name", create_required=True),
    FieldSpec(
        "type",
        "text",
        "Type",
        "type",
        hint=(
            f"{_TYPE_GLOSS}; the operator enters a key or signs in on the page. Changing "
            "between types that take a key is refused: the operator does that in the editor"
        ),
        create_required=True,
    ),
    FieldSpec(
        "base_url",
        "text",
        "Address",
        "base_url",
        hint=(
            "the API address; leave it out for openai, anthropic and anthropic-plan (fixed). "
            "ollama and openrouter default; openai-compatible needs one"
        ),
        address_or_command=True,
    ),
    FieldSpec(
        "num_ctx",
        "integer",
        "Context window",
        "num_ctx",
        hint="ollama only: the context window in tokens",
        min=1,
        path=("config", "num_ctx"),
    ),
    FieldSpec(
        "thinking_enabled",
        "boolean",
        "Extended thinking",
        "thinking_enabled",
        hint="Claude types only (anthropic, anthropic-plan)",
        path=("config", "thinking_enabled"),
    ),
    FieldSpec(
        "reasoning_effort",
        "text",
        "Reasoning effort",
        "reasoning_effort",
        hint="low, medium, high, or empty for the provider default",
        path=("config", "reasoning_effort"),
    ),
)
_BY_NAME = {f.name: f for f in PROVIDER_FIELDS}
_OPTIONS = ("num_ctx", "thinking_enabled", "reasoning_effort")

# Fields the operator alone controls; never in any kind's spec (a test asserts it).
OPERATOR_ONLY = ("api_key", "secrets")

#: The keys whose values skip the guard's key-shape heuristics (a UUID path is not a key).
RELAXED_GUARD_KEYS = frozenset({"base_url"})

KEY_HANDOFF = (
    "A provider's API key can't follow it to another type. Tell the operator to change the "
    "type in the provider editor and enter the new key."
)
TOKEN_HANDOFF = (
    "A Claude Plan (Token) provider needs a token from claude setup-token. Tell the operator "
    "to create it in the provider editor."
)
MOCK_MESSAGE = "A mock provider can't be created or changed from here."

# --- resolution --------------------------------------------------------------------------


async def resolve_target(conn: Any, ref: Any) -> tuple[str, str]:
    """``(id, name)`` of an existing model provider named by id or name (id first)."""
    from the_one.gleepglorp import kinds

    return kinds.resolve_by_id_or_name(await _ref_entries(conn, "provider"), ref, "model provider")


async def _load(conn: Any, enc: Any, provider_id: str) -> Any:
    """The stored provider (decrypted), or ``None``."""
    from the_one.config import settings
    from the_one.db.repositories import LLMProviderRepository
    from the_one.encryption import get_encryptor

    repo = LLMProviderRepository(conn, enc if enc is not None else get_encryptor(settings.data_dir))
    try:
        return await repo.get(provider_id)
    except KeyError:
        return None


# --- value checks ------------------------------------------------------------------------


def _check_url(spec: FieldSpec, value: Any) -> str:
    text = _check_text(spec, value).strip()
    if len(text) > _URL_MAX:
        raise ShapeError(f"base_url is limited to {_URL_MAX:,} characters.")
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ShapeError("base_url must be an http or https address.")
    return text


def _check_name_unique(name: str, entries: list[tuple[str, str]], self_id: str | None) -> None:
    folded = name.casefold()
    if any(n.casefold() == folded for i, n in entries if i != self_id):
        raise ShapeError(f"A model provider named {_q(name)} already exists.")


def _check_option(spec: FieldSpec, value: Any, new_type: str) -> Any:
    if not PROVIDER_TYPE_DEFAULTS[new_type][_shows_key(spec.name)]:
        where = {
            "num_ctx": "an Ollama provider",
            "thinking_enabled": "a Claude provider (anthropic or anthropic-plan)",
            "reasoning_effort": "this provider type",
        }[spec.name]
        raise ShapeError(f"{spec.name} only applies to {where}, not to {new_type}.")
    if spec.name == "num_ctx":
        return _check_int(spec, value)
    if spec.name == "thinking_enabled":
        if not isinstance(value, bool):
            raise _bad(spec, "true or false")
        return value
    text = _check_text(spec, value).strip().lower()
    if text not in provider_service.REASONING_EFFORTS:
        raise ShapeError("reasoning_effort must be low, medium, high or empty (the default).")
    return text


def _shows_key(option: str) -> str:
    return {
        "num_ctx": "shows_num_ctx",
        "thinking_enabled": "shows_thinking",
        "reasoning_effort": "shows_reasoning_effort",
    }[option]


# --- normalize ---------------------------------------------------------------------------


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
    for key in changes:
        if key in OPERATOR_ONLY:
            raise ShapeError(f"{key} can only be set by the operator, in the provider editor.")
        if key not in _BY_NAME:
            raise ShapeError(
                f"provider changes can't include {_q(key)!r}. "
                f"Allowed fields: {', '.join(_BY_NAME)}."
            )
    fill = mode == "fill"
    entries = await _ref_entries(conn, "provider")
    current: Any = None
    target_id: str | None = None
    if action == "change":
        target_id, _name = await resolve_target(conn, target.get("target"))
        current = await _load(conn, enc, target_id)
        if current is None:
            raise ShapeError("No model provider with that id.")
        if current.type == "mock":
            raise ShapeError(MOCK_MESSAGE)
        new_type = changes.get("type", current.type)
    else:
        new_type = changes.get("type")
    if not isinstance(new_type, str) or new_type not in PROVIDER_TYPES:
        raise ShapeError(f"type must be one of: {', '.join(TYPES)}.")
    if new_type == "mock":
        raise ShapeError(MOCK_MESSAGE)
    type_changed = current is not None and new_type != current.type

    # The type rules (DD10): a key never follows a provider, and the token type needs a token.
    if not fill:
        if new_type == _PLAN_TOKEN and (action == "create" or type_changed):
            raise ShapeError(TOKEN_HANDOFF)
        if type_changed and provider_service.takes_key(current.type):
            if provider_service.takes_key(new_type):
                raise ShapeError(KEY_HANDOFF)

    named_url = changes.get("base_url")
    stored: dict[str, Any] = {}
    for f in PROVIDER_FIELDS:
        if f.name not in changes:
            continue
        value = changes[f.name]
        if f.name == "name":
            try:
                text = check_name(value)
            except NameRuleError as e:
                raise ShapeError(e.message) from None
            _check_name_unique(text, entries, target_id)
            stored["name"] = text
        elif f.name == "type":
            stored["type"] = new_type
        elif f.name == "base_url":
            stored["base_url"] = _check_url(f, value)
        else:
            stored[f.name] = _check_option(f, value, new_type)

    if action == "create" or type_changed:
        url, why = provider_service.base_url_for(
            new_type, stored.get("base_url") if named_url is not None else None
        )
        if why is not None:
            raise ShapeError(why)
        if action == "create":
            # The stored change carries the address it will create with.
            ordered: dict[str, Any] = {}
            for key in ("name", "type"):
                ordered[key] = stored[key]
            ordered["base_url"] = url
            ordered.update({k: v for k, v in stored.items() if k not in ordered})
            stored = ordered
    elif "base_url" in stored and not PROVIDER_TYPE_DEFAULTS[new_type]["base_url_shown"]:
        raise ShapeError(provider_service.base_url_for(new_type, stored["base_url"])[1] or "")

    key = _target_key(action, target_id, stored.get("name"))
    if action == "create":
        return Normalized("provider", "create", None, None, key, stored, None)
    if not stored:
        raise ShapeError("Nothing to change. Give at least one field in changes.")
    assert target_id is not None and current is not None
    return Normalized("provider", "change", None, target_id, key, stored, _base(current, stored))


def _target_key(action: str, target_id: str | None, name: str | None) -> str:
    from the_one.gleepglorp import kinds

    return kinds.target_key("provider", action, target_id, name)


def _base(provider: Any, stored: dict[str, Any]) -> dict[str, Any]:
    """The stored value of each field named (an option absent now is left out, so "absent
    then, present at apply" reads as stale). Never a key."""
    base: dict[str, Any] = {}
    for key in stored:
        if key in ("name", "type", "base_url"):
            base[key] = getattr(provider, key)
        elif key in (provider.config or {}):
            base[key] = provider.config[key]
    return base


# --- exists, apply, wording ---------------------------------------------------------------


async def _row_name(conn: Any, provider_id: str | None) -> str | None:
    """The current name of a provider, else ``None``."""
    if not provider_id:
        return None
    for i, n in await _ref_entries(conn, "provider"):
        if i == provider_id:
            return n
    return None


async def exists(conn: aiosqlite.Connection, deps: KindDeps, p: Proposal) -> bool:
    if p.action == "create":
        return True
    return await _row_name(conn, p.target_id) is not None


def _write_deps(deps: KindDeps) -> provider_service.ProviderWriteDeps:
    return provider_service.ProviderWriteDeps(repo=deps.agent.provider_repo)


def _create_body(changes: dict[str, Any], provider_id: str) -> dict[str, Any]:
    config = {k: changes[k] for k in _OPTIONS if k in changes}
    return {
        "id": provider_id,
        "name": changes["name"],
        "type": changes["type"],
        "base_url": changes["base_url"],
        "config": provider_service.seeded_config(changes["type"], config),
    }


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
        write_deps = _write_deps(deps)
        if p.action == "create":
            # The id is made here so the status mark, the summary and the config_changed frame
            # can carry it (the row does not exist until the write commits).
            provider_id = uuid.uuid4().hex[:12]
            result["target_id"] = provider_id
            await provider_service.create_provider(
                write_deps, _create_body(changes, provider_id), dev_mode=False, on_commit=mark
            )
        else:
            assert p.target_id is not None
            current = await _row_name(conn, p.target_id)
            if current is not None:
                labels = changed_labels(PROVIDER_FIELDS, p)
                result["summary"] = f"Changed {', '.join(labels)} on provider {current}"
                result["provider"] = current
            await provider_service.change_provider(
                write_deps, p.target_id, changes, base=base, override=override, on_commit=mark
            )
    except Exception as exc:  # noqa: BLE001 - translated, or re-raised unchanged
        await reraise(exc, p, conn=conn, zone=zone)
    return None


async def summary_text(p: Proposal, zone: Any) -> dict[str, Any]:
    labels = changed_labels(PROVIDER_FIELDS, p)
    name = p.changes.get("name") or ""
    if p.action == "create":
        text = f"Created provider {name}"
    else:
        # ``apply`` adds the provider's current name once it has looked it up.
        text = f"Changed {', '.join(labels)} on a provider"
    return {"summary": text, "agent": None, "fields": labels}


def title(p: Proposal) -> str:
    name = p.changes.get("name") or ""
    return f"{p.action} provider {name}".strip()


def card_title(action: str, name: str | None) -> str:
    quoted = f" “{name}”" if name else ""
    return f"{'Create' if action == 'create' else 'Change'} model provider{quoted}"


async def card_extras(conn: aiosqlite.Connection, p: Proposal) -> dict[str, Any]:
    """The card's title and ``target_gone``, from a lookup by id at view time."""
    if p.action == "create":
        return {"title": card_title("create", p.changes.get("name")), "target_gone": False}
    current = await _row_name(conn, p.target_id)
    name = current or p.changes.get("name")
    return {"title": card_title("change", name), "target_gone": current is None}


async def fill_stale(conn: Any, fill: Any, labels: dict[str, str]) -> list[dict[str, Any]]:
    """The ``stale`` rows of a provider change fill: the named fields whose stored value moved
    since the fill was made, labelled and in display form (an absent option reads ``None``)."""
    from the_one.llm.provider_service import stale_fields

    source = await _load(conn, None, fill.target_id) if fill.target_id else None
    if source is None:
        return []
    return [
        {
            "field": row["field"],
            "label": labels.get(row["field"], row["field"]),
            "current": row["current"],
            "proposed": row["proposed"],
        }
        for row in stale_fields(source, fill.changes, fill.base or {})
    ]


async def clears_key(conn: Any, fill: Any) -> bool:
    """Whether the fill clears the editor's key field: a provider change whose type differs from
    the stored type and which leaves a key-taking type, whichever type it enters. Into a type
    with no key row (ollama, anthropic-plan) the key is cleared as the apply would; between
    key-taking types it is cleared so the old key is never sent to the new service."""
    if fill.action != "change" or not fill.target_id:
        return False
    new_type = (fill.changes or {}).get("type")
    base_type = (fill.base or {}).get("type")
    if not new_type or new_type == base_type:
        return False
    from the_one.llm import provider_service

    return base_type is not None and provider_service.takes_key(base_type)


fill_extras = id_fill_extras(card_extras, stale_fn=fill_stale, clears_key_fn=clears_key)


# --- warnings -----------------------------------------------------------------------------


WARN_KEY_NEEDED = "Enter its API key on the page after approving."
WARN_SIGN_IN = "Sign in on the page after approving."
WARN_KEY_CLEARED_SIGN_IN = "The stored key is cleared; sign in after approving."
# The fill wordings: a fill is applied by the operator saving the form, not by approving.
WARN_FILL_KEY_NEEDED = "Enter its API key on this page."
WARN_FILL_SIGN_IN = "Sign in on this page after saving."
WARN_FILL_KEY_CLEARED_SIGN_IN = "The stored key is cleared; sign in on this page after saving."
_FILL_WORDING = {
    WARN_KEY_NEEDED: WARN_FILL_KEY_NEEDED,
    WARN_SIGN_IN: WARN_FILL_SIGN_IN,
    WARN_KEY_CLEARED_SIGN_IN: WARN_FILL_KEY_CLEARED_SIGN_IN,
}
WARN_KEY_CLEARED = "The stored key is cleared."
WARN_SIGNS_OUT = "This signs the provider out."
WARN_URL_MOVES_KEY = "This provider's saved key will be sent to the new address."
WARN_GLEEPGLORP = "GleepGlorp uses this provider."


def _agents_sentence(names: list[str]) -> str:
    n = len(names)
    if n == 1:
        return "1 agent uses this provider; its model name stays as it is."
    return f"{n} agents use this provider; their model names stay as they are."


async def warnings(
    conn: aiosqlite.Connection, enc: Any, p: Proposal, mode: str = "propose"
) -> list[str]:
    """What the operator should know before approving, read from the stored row. ``mode="fill"``
    words the approval-dependent sentences for a fill (saved on the page, never approved)."""
    out = await _warnings(conn, enc, p)
    if mode == "fill":
        out = [_FILL_WORDING.get(w, w) for w in out]
    return out


async def _warnings(conn: aiosqlite.Connection, enc: Any, p: Proposal) -> list[str]:
    out: list[str] = []
    changes = p.changes
    if p.action == "create":
        new_type = changes.get("type")
        if new_type in PROVIDER_TYPE_DEFAULTS:
            if PROVIDER_TYPE_DEFAULTS[new_type]["shows_api_key"]:
                out.append(WARN_KEY_NEEDED)
            elif PROVIDER_TYPE_DEFAULTS[new_type]["plan_sign_in"]:
                out.append(WARN_SIGN_IN)
        return out
    current = await _load(conn, enc, p.target_id) if p.target_id else None
    if current is None:
        return out
    new_type = changes.get("type", current.type)
    if new_type != current.type and new_type in PROVIDER_TYPE_DEFAULTS:
        if new_type == _ANTHROPIC_PLAN:
            out.append(WARN_KEY_CLEARED_SIGN_IN if current.api_key else WARN_SIGN_IN)
        elif not provider_service.takes_key(new_type) and current.api_key:
            out.append(WARN_KEY_CLEARED)
        if current.type == _ANTHROPIC_PLAN:
            out.append(WARN_SIGNS_OUT)
        if not provider_service.takes_key(current.type) and provider_service.takes_key(new_type):
            out.append(WARN_KEY_NEEDED)
        async with conn.execute(
            "SELECT name FROM agents WHERE provider_config_id = ? ORDER BY name", (current.id,)
        ) as cur:
            agents = [r[0] for r in await cur.fetchall()]
        if agents:
            out.append(_agents_sentence(agents))
        from the_one.gleepglorp.settings import load_settings

        if (await load_settings(conn)).provider_config_id == current.id:
            out.append(WARN_GLEEPGLORP)
    if (
        "base_url" in changes
        and changes["base_url"] != current.base_url
        and new_type == current.type
        and current.api_key
    ):
        out.append(WARN_URL_MOVES_KEY)
    return out


KIND = Kind(
    name="provider",
    label="model provider",
    summary="Create a model provider or change its name, type, address or options",
    fields=PROVIDER_FIELDS,
    normalize=normalize,
    exists=exists,
    apply=apply,
    summary_text=summary_text,
    addressing="id",
    target_noun="A model provider",
    fill_extras=fill_extras,
    keyerror_is_gone=True,
    operator_only=OPERATOR_ONLY,
    fillable=("create", "change"),
    title=title,
    card_title=card_title,
    resolve_target=resolve_target,
    warnings=warnings,
    card_extras=card_extras,
    relaxed_guard_keys=RELAXED_GUARD_KEYS,
)
