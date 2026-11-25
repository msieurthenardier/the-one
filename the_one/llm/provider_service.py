"""The model-provider write service (Mission 36 Flight 4 Leg 5a, DD10).

The writes the provider routes make, moved out of ``the_one/interfaces/web/api.py`` so
GleepGlorp's approve path runs the same validation the operator's own save does. The routes
stay thin: they call :func:`create_provider` or :func:`replace_provider` and map
:class:`ProviderWriteError` to ``HTTPException``. A proposal calls :func:`create_provider` or
:func:`change_provider`.

This module imports nothing from ``fastapi``, ``the_one.interfaces`` or ``the_one.gleepglorp``,
and keeps the repository behind ``TYPE_CHECKING`` (an ``ast`` test pins both): it is
injected through :class:`ProviderWriteDeps`. Every refusal raises :class:`ProviderWriteError`
carrying the status and the exact ``detail`` the route returned before the move.

Two write shapes, both **re-reading the row inside the write transaction**
(``LLMProviderRepository.update_in_txn``) so an OAuth token a refresh wrote a moment ago is
never overwritten by the secrets blob read earlier (the race this leg fixes for operator
saves too):

- :func:`replace_provider` is the route's PUT exactly (``config`` replaced whole, a masked key
  preserved, the per-type secret rules);
- :func:`change_provider` merges **named fields** (``name``, ``type``, ``base_url`` and the
  per-key options) and never takes a key: it can clear one (a type change to a type with no
  key) and never carry one across key-taking types.

``dev_mode`` is a parameter; the service never reads settings.
"""

from __future__ import annotations

import copy
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import aiosqlite
from pydantic import ValidationError

from the_one.db._provider_types import CLAUDE_PROVIDER_TYPES, PROVIDER_TYPE_DEFAULTS
from the_one.db.models import LLMProviderConfig, now_iso
from the_one.llm import anthropic_oauth, plan_credentials
from the_one.naming import NameRuleError, check_name, name_rule_detail
from the_one.secret_mask import looks_masked

if TYPE_CHECKING:
    from the_one.db.repositories import LLMProviderRepository

OnCommit = Callable[[aiosqlite.Connection], Awaitable[None]]

#: Provider types that skip URL safety validation. ``mock`` has no real URL; ``ollama`` is
#: local-by-design and operators frequently point it at a LAN host that is trusted.
URL_VALIDATION_SKIPPED_TYPES = frozenset({"mock", "ollama"})

#: OAuth-managed keys in ``llm_providers.secrets`` for ``anthropic-plan``; written only by the
#: OAuth exchange and refresh paths.
PLAN_OAUTH_MANAGED_KEYS = anthropic_oauth.OAUTH_MANAGED_SECRET_KEYS

PLAN_TOKEN_TYPE = "anthropic-plan-token"
PLAN_TOKEN_MISSING_DETAIL = "Paste a token from claude setup-token."
PLAN_TOKEN_API_KEY_DETAIL = (
    "That is an Anthropic API key. Use the Anthropic provider type for API keys; "
    "Claude Plan (Token) takes a token from `claude setup-token`."
)
MOCK_DETAIL = "Mock provider type requires THE_ONE_DEV_MODE=true"

#: The editor's Ollama context window default (``DEFAULT_NUM_CTX`` in ``provider-editor.js``).
DEFAULT_NUM_CTX = 32768
REASONING_EFFORTS = ("", "low", "medium", "high")

#: The fields :func:`change_provider` may set (a flat shape; the three options live under
#: ``config``).
OPTION_FIELDS = ("num_ctx", "thinking_enabled", "reasoning_effort")
CHANGE_FIELDS = ("name", "type", "base_url", *OPTION_FIELDS)
_OPTION_SHOWN = {
    "num_ctx": "shows_num_ctx",
    "thinking_enabled": "shows_thinking",
    "reasoning_effort": "shows_reasoning_effort",
}
_ABSENT = object()

KEY_TYPE_CHANGE_DETAIL = (
    "A provider's API key can't follow it to another type. Change the type in the provider "
    "editor and enter the new key."
)


class ProviderWriteError(Exception):
    """A refused provider write: an HTTP-shaped ``status`` and ``detail``.

    ``detail`` is exactly the payload the route returns (a sentence, or a 422 list on
    ``loc``). It carries no HTTP type: ``api.py`` turns it into ``HTTPException``.
    """

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"{status}: {detail!r}")
        self.status = status
        self.detail = detail

    @property
    def items(self) -> list[dict[str, Any]]:
        """``[{loc, msg}]`` for the approve path."""
        if isinstance(self.detail, list):
            out: list[dict[str, Any]] = []
            for d in self.detail:
                if isinstance(d, dict):
                    loc = [x if isinstance(x, (str, int)) else str(x) for x in d.get("loc", [])]
                    out.append({"loc": loc, "msg": str(d.get("msg", ""))})
                else:
                    out.append({"loc": [], "msg": str(d)})
            return out
        return [{"loc": [], "msg": str(self.detail)}]


class ProviderNotFound(Exception):  # noqa: N818 - the route answers 404
    """No provider has this id."""

    def __init__(self, provider_id: str) -> None:
        super().__init__(f"Provider not found: {provider_id}")
        self.provider_id = provider_id


class ProviderStaleError(Exception):
    """A touched field's stored value differs from the ``base`` the change was written
    against. ``fields`` is ``[{"field", "current", "proposed"}]``."""

    def __init__(self, fields: list[dict[str, Any]]) -> None:
        super().__init__("stale: " + ", ".join(str(f["field"]) for f in fields))
        self.fields = fields


@dataclass(frozen=True)
class ProviderWriteDeps:
    """What a provider write needs: the repository (injected, so this module stays DB-free
    at import)."""

    repo: LLMProviderRepository


# ── Validators (moved from api.py with their exact details) ──────────────


def validation_detail(e: ValidationError) -> list[dict]:
    """The 422 body for a pydantic ``ValidationError`` (no ``ctx``, no echoed input)."""
    return e.errors(include_context=False, include_input=False)


def checked_name(value: object) -> str:
    """The trimmed name, or a list-shaped 422 on ``loc ["name"]``."""
    try:
        return check_name(value)
    except NameRuleError as e:
        raise ProviderWriteError(422, name_rule_detail(e.message)) from None


def check_plan_token(api_key: str | None) -> None:
    """DD2 / DD4: require a token and refuse an Anthropic API key (422).

    Never echoes the submitted value.
    """
    if not api_key:
        raise ProviderWriteError(422, PLAN_TOKEN_MISSING_DETAIL)
    if api_key.startswith("sk-ant-api"):
        raise ProviderWriteError(422, PLAN_TOKEN_API_KEY_DETAIL)


def is_safe_provider_url(url: str) -> tuple[bool, str | None]:
    """Validate an LLM provider ``base_url``.

    Returns ``(True, None)`` for ``https://...`` always; for ``http://...`` only when the
    host is one of ``localhost``/``127.0.0.1``/``::1`` or ends with ``.localdomain``. Any
    other scheme/host combination is rejected with a human-readable explanation.

    Rationale: API keys are sent via the ``Authorization: Bearer ...`` header. Routing them
    over plaintext ``http://`` to a non-localhost host would leak the key on the wire.
    Refusing at save time is cheaper than detecting after exposure.
    """
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return True, None
    if parsed.scheme == "http":
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localdomain"):
            return True, None
        return (
            False,
            "Provider base_url uses http:// for a non-localhost host. "
            "API keys would be sent in cleartext. Use https:// or restrict to localhost.",
        )
    return (
        False,
        f"Provider base_url scheme '{parsed.scheme}' not supported. "
        "Use http:// (localhost only) or https://.",
    )


def _check_url(provider: LLMProviderConfig) -> None:
    if provider.type not in URL_VALIDATION_SKIPPED_TYPES:
        ok, msg = is_safe_provider_url(provider.base_url)
        if not ok:
            raise ProviderWriteError(422, msg)


def _refuse(loc: list[Any], msg: str) -> ProviderWriteError:
    return ProviderWriteError(422, [{"type": "value_error", "loc": loc, "msg": msg}])


# ── Type facts, shared with the kind ─────────────────────────────────────


def defaults_for(provider_type: str) -> dict[str, object]:
    """The editor's defaults for a type (``KeyError`` for an unknown type)."""
    return PROVIDER_TYPE_DEFAULTS[provider_type]


def takes_key(provider_type: str) -> bool:
    """Whether the type stores an API key or token (the editor's ``showApiKey``)."""
    return bool(PROVIDER_TYPE_DEFAULTS[provider_type]["shows_api_key"])


def base_url_for(provider_type: str, named: str | None) -> tuple[str, str | None]:
    """``(base_url, refusal)`` for a type being set: a hidden-URL type takes its default (a
    named address is refused); a shown-URL type takes the named one or, failing that, its
    default (empty for ``openai-compatible``, which then needs one)."""
    d = PROVIDER_TYPE_DEFAULTS[provider_type]
    default = str(d["base_url"])
    if not d["base_url_shown"]:
        if named is not None and named.strip():
            return default, (
                f"A {provider_type} provider's address is fixed ({default}); don't set base_url."
            )
        return default, None
    url = named.strip() if named is not None and named.strip() else default
    if not url:
        return "", f"A {provider_type} provider needs its base_url."
    return url, None


def seeded_config(provider_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """``config`` with what the editor seeds on a type change: Ollama's context window and a
    Claude type's extended thinking, each only when absent."""
    cfg = dict(config)
    d = PROVIDER_TYPE_DEFAULTS[provider_type]
    if d["shows_num_ctx"] and cfg.get("num_ctx") is None:
        cfg["num_ctx"] = DEFAULT_NUM_CTX
    if provider_type in CLAUDE_PROVIDER_TYPES and cfg.get("thinking_enabled") is None:
        cfg["thinking_enabled"] = True
    return cfg


# ── Post-commit side effects ─────────────────────────────────────────────


def _after_write(provider_id: str) -> None:
    # DD-3 invalidation contract: a provider update evicts the cached plan credential source
    # so the next consumer re-reads the stored row. No-op for non-plan types / uncached ids.
    plan_credentials.evict_credential_source(provider_id)


# ── Create and replace (the routes) ──────────────────────────────────────


async def create_provider(
    deps: ProviderWriteDeps,
    data: dict[str, Any],
    *,
    dev_mode: bool,
    on_commit: OnCommit | None = None,
) -> LLMProviderConfig:
    """Create a provider from a request body. ``on_commit`` runs inside the insert's
    transaction (a proposal's status mark rides there)."""
    data = dict(data)
    if data.get("type") == "mock" and not dev_mode:
        raise ProviderWriteError(400, MOCK_DETAIL)
    data["name"] = checked_name(data.get("name"))
    client_id = "id" in data
    if not client_id:
        data["id"] = uuid.uuid4().hex[:12]
    # DD-2 create direction: secrets are OAuth-managed, force-empty regardless of the body.
    data["secrets"] = {}
    try:
        provider = LLMProviderConfig.model_validate(data)
    except ValidationError as e:
        # A missing field is a 422; ``include_input=False`` keeps ``api_key`` out of it.
        raise ProviderWriteError(422, validation_detail(e)) from None
    # Token plan type (sortie 03 DD2-DD4): runs on the validated (stripped) key, then stamps
    # when it was set. The stamp is server-owned.
    if provider.type == PLAN_TOKEN_TYPE:
        check_plan_token(provider.api_key)
        provider = provider.model_copy(update={"secrets": {"token_set_at": now_iso()}})
    # Sortie 17 DD4: a new Claude provider starts with extended thinking on.
    if provider.type in CLAUDE_PROVIDER_TYPES and provider.config.get("thinking_enabled") is None:
        provider = provider.model_copy(
            update={"config": {**provider.config, "thinking_enabled": True}}
        )
    _check_url(provider)
    try:
        await deps.repo.create(provider, on_commit=on_commit)
    except sqlite3.IntegrityError:
        # A client-supplied id that already exists (squawk 0402). Confirmed against the row,
        # not assumed, so a race between two creates is a 409 too; the transaction has rolled
        # back, so an ``on_commit`` mark rolled back with it.
        clash = False
        if client_id:
            try:
                await deps.repo.get(provider.id)
                clash = True
            except KeyError:
                pass
        if not clash:
            raise
        raise ProviderWriteError(
            409, f"A model provider with id {provider.id} already exists."
        ) from None
    return provider


async def replace_provider(
    deps: ProviderWriteDeps, provider_id: str, data: dict[str, Any], *, dev_mode: bool
) -> LLMProviderConfig:
    """The route's PUT, on the row re-read inside the write transaction.

    Computed from the raw body before the transaction: whether a fresh key was supplied (a
    type change INTO the token type requires one). Everything that reads the stored row runs
    in the mutator, on the fresh row; the 404 comes before the mock 400, as it always did.
    """
    data = dict(data)
    data["id"] = provider_id
    raw_key = data.get("api_key")
    fresh_key_supplied = (
        isinstance(raw_key, str) and raw_key.strip() != "" and not looks_masked(raw_key)
    )

    def mutate(existing: LLMProviderConfig) -> LLMProviderConfig:
        body = dict(data)
        # Gate mock-typed updates on dev_mode. Compare the resulting type so an update that
        # doesn't change the type isn't accidentally rejected.
        if body.get("type", existing.type) == "mock" and not dev_mode:
            raise ProviderWriteError(400, MOCK_DETAIL)
        # A masked key preserves the stored one.
        if looks_masked(body.get("api_key")):
            body["api_key"] = existing.api_key
        # DD-2 / sortie 03 DD3, DD11: server-managed secret keys are never taken from the
        # client; the real secrets are built below on the RESOLVED type.
        body["secrets"] = {}
        # ``model_copy(update=...)`` does not re-run validators: round-trip through
        # ``model_validate`` so a malformed PUT cannot corrupt the stored row (squawk 0013).
        try:
            merged = existing.model_dump()
            merged.update(body)
            if "name" in body:
                merged["name"] = checked_name(merged["name"])
            updated = LLMProviderConfig.model_validate(merged)
        except ValidationError as e:
            raise ProviderWriteError(422, validation_detail(e)) from None

        # Pin / force / check / stamp by the RESOLVED type (DD2-DD4, DD11).
        resolved_secrets: dict[str, Any] = {}
        overrides: dict[str, Any] = {}
        if updated.type == "anthropic-plan":
            for key in PLAN_OAUTH_MANAGED_KEYS:
                if key in existing.secrets:
                    resolved_secrets[key] = existing.secrets[key]
            # The OAuth type never uses ``api_key``; do not leave a token behind.
            overrides["api_key"] = None
        elif updated.type == PLAN_TOKEN_TYPE:
            entering = existing.type != PLAN_TOKEN_TYPE
            if entering and not fresh_key_supplied:
                raise ProviderWriteError(422, PLAN_TOKEN_MISSING_DETAIL)
            check_plan_token(updated.api_key)
            stamp = existing.secrets.get("token_set_at") if not entering else None
            if not stamp or updated.api_key != existing.api_key:
                stamp = now_iso()
            resolved_secrets["token_set_at"] = stamp
        overrides["secrets"] = resolved_secrets
        updated = updated.model_copy(update=overrides)
        # URL safety on the RESOLVED base_url (after the merge), so a request that does not
        # touch ``base_url`` cannot let an unsafe stored value survive an update.
        _check_url(updated)
        return updated

    try:
        _before, after = await deps.repo.update_in_txn(provider_id, mutate)
    except KeyError:
        raise ProviderNotFound(provider_id) from None
    _after_write(provider_id)
    return after


# ── Change (a proposal) ──────────────────────────────────────────────────


def _current_value(provider: LLMProviderConfig, key: str) -> Any:
    if key in ("name", "type", "base_url"):
        return getattr(provider, key)
    return (provider.config or {}).get(key, _ABSENT)


def stale_fields(
    current: LLMProviderConfig, changes: dict[str, Any], base: dict[str, Any]
) -> list[dict[str, Any]]:
    """The touched fields whose stored value is not the ``base`` value."""
    out: list[dict[str, Any]] = []
    for key, proposed in changes.items():
        cur = _current_value(current, key)
        was = base.get(key, _ABSENT)
        if cur != was:
            out.append(
                {"field": key, "current": None if cur is _ABSENT else cur, "proposed": proposed}
            )
    return out


def _check_option(key: str, value: Any) -> None:
    if key == "num_ctx":
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise _refuse([key], "num_ctx must be a whole number of at least 1.")
    elif key == "thinking_enabled":
        if not isinstance(value, bool):
            raise _refuse([key], "thinking_enabled must be true or false.")
    elif not isinstance(value, str) or value not in REASONING_EFFORTS:
        raise _refuse([key], "reasoning_effort must be low, medium, high or empty (the default).")


def _apply_change(
    current: LLMProviderConfig,
    changes: dict[str, Any],
    base: dict[str, Any] | None,
    override: bool,
) -> LLMProviderConfig:
    """The mutator: runs on the row re-read inside the write transaction."""
    for key in changes:
        if key not in CHANGE_FIELDS:
            raise _refuse([key], f"{key!r} can't be changed here.")
    if current.type == "mock":
        raise _refuse(["type"], "A mock provider can't be changed from here.")
    if base is not None and not override:
        stale = stale_fields(current, changes, base)
        if stale:
            raise ProviderStaleError(stale)

    new_type = changes.get("type", current.type)
    if not isinstance(new_type, str) or new_type not in PROVIDER_TYPE_DEFAULTS:
        raise _refuse(["type"], "type isn't a known provider type.")
    if new_type == "mock":
        raise _refuse(["type"], "A provider can't be changed to a mock provider from here.")
    type_changed = new_type != current.type
    if type_changed:
        # Fail closed: the key never follows a provider across key-taking types (the setup
        # token would otherwise become an API key), and a token type needs a fresh token.
        if takes_key(current.type) and takes_key(new_type):
            raise _refuse(["type"], KEY_TYPE_CHANGE_DETAIL)
        if new_type == PLAN_TOKEN_TYPE:
            raise _refuse(["type"], PLAN_TOKEN_MISSING_DETAIL)

    # base_url: a hidden-URL type's address is fixed; a type change takes the default unless
    # a shown-URL type is given one.
    named_url = changes.get("base_url")
    if named_url is not None and not isinstance(named_url, str):
        raise _refuse(["base_url"], "base_url must be text.")
    if type_changed:
        base_url, why = base_url_for(new_type, named_url)
        if why is not None:
            raise _refuse(["base_url"], why)
    elif "base_url" in changes:
        if not PROVIDER_TYPE_DEFAULTS[new_type]["base_url_shown"]:
            why = base_url_for(new_type, named_url)[1]
            raise _refuse(["base_url"], why or "base_url is fixed for this type.")
        base_url = named_url.strip() if isinstance(named_url, str) else ""
        if not base_url:
            raise _refuse(["base_url"], "base_url can't be empty.")
    else:
        base_url = current.base_url

    # Options merge per key onto the stored config (keys the editor does not show are kept).
    cfg = copy.deepcopy(current.config or {})
    shown = PROVIDER_TYPE_DEFAULTS[new_type]
    for key in OPTION_FIELDS:
        if key not in changes:
            continue
        if not shown[_OPTION_SHOWN[key]]:
            raise _refuse([key], f"{key} doesn't apply to a {new_type} provider.")
        _check_option(key, changes[key])
        cfg[key] = changes[key]
    if type_changed:
        cfg = seeded_config(new_type, cfg)

    name = checked_name(changes["name"]) if "name" in changes else current.name

    # The key and the secrets follow the RESOLVED type, as the PUT does.
    api_key = current.api_key
    secrets: dict[str, Any] = {}
    if type_changed and not takes_key(new_type):
        api_key = None  # into ollama / anthropic-plan: the stored key is cleared
    if new_type == "anthropic-plan":
        api_key = None
        for key in PLAN_OAUTH_MANAGED_KEYS:
            if key in current.secrets:
                secrets[key] = current.secrets[key]
    elif new_type == PLAN_TOKEN_TYPE:
        check_plan_token(api_key)
        secrets["token_set_at"] = current.secrets.get("token_set_at") or now_iso()
    try:
        candidate = LLMProviderConfig.model_validate(
            {
                **current.model_dump(),
                "name": name,
                "type": new_type,
                "base_url": base_url,
                "api_key": api_key,
                "config": cfg,
                "secrets": secrets,
            }
        )
    except ValidationError as e:
        raise ProviderWriteError(422, validation_detail(e)) from None
    _check_url(candidate)
    return candidate


async def change_provider(
    deps: ProviderWriteDeps,
    provider_id: str,
    changes: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
    override: bool = False,
    on_commit: OnCommit | None = None,
) -> LLMProviderConfig:
    """Apply a proposal's named fields to the row, inside one write transaction.

    The row is re-read under the write lock and the change merged onto it (options per key),
    so an OAuth token written a moment ago is kept. ``base`` (the values the proposal was
    written against) is compared on the fresh row unless ``override``: a mismatch raises
    :class:`ProviderStaleError` and nothing is written. Never takes a key; clears it on a
    change into a type with none; refuses a change between key-taking types. Eviction runs
    after the commit, and never if the write (or ``on_commit``) raised. Returns the row.
    """

    def mutate(current: LLMProviderConfig) -> LLMProviderConfig:
        return _apply_change(current, changes, base, override)

    try:
        _before, after = await deps.repo.update_in_txn(provider_id, mutate, on_commit=on_commit)
    except KeyError:
        raise ProviderNotFound(provider_id) from None
    _after_write(provider_id)
    return after
