"""Pydantic models for database entities (KnowledgeBase, KBItem, MCPSource, ChatSession)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field, field_validator

from the_one.db._connector_types import CONNECTOR_TYPES
from the_one.db._provider_types import PROVIDER_TYPES


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LLMProviderConfig(BaseModel):
    """An LLM provider connection configuration."""

    id: str
    name: str
    # NOTE: keep this ``Literal[...]`` spelled out explicitly — Pydantic /
    # static type checkers cannot consume ``Literal[*PROVIDER_TYPES]``
    # unpacking. The module-load assertion below pins the two in sync.
    type: Literal[
        "ollama",
        "openai-compatible",
        "openai",
        "anthropic",
        "mock",
        "openrouter",
        "anthropic-plan",
    ]
    base_url: str
    api_key: str | None = None
    config: dict = Field(default_factory=dict)
    # M19 F01 L01 — OAuth-managed credential blob for ``anthropic-plan``
    # providers (access_token / refresh_token / token_expires_at / scope /
    # token_type). Encrypted at rest as a whole-dict Fernet blob by
    # ``LLMProviderRepository`` (DD-2); stripped from every API response
    # (``_provider_response`` exposes an ``oauth_active`` boolean instead).
    secrets: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @field_validator("api_key", mode="after")
    @classmethod
    def _normalize_api_key(cls, value: str | None) -> str | None:
        """Strip whitespace and collapse empty results to ``None``.

        This is the canonical-form contract for ``api_key``. Callers
        (``/test``, ``/models``, chat-create, the SDK constructors) MUST
        NOT re-strip — the stored value is already canonical, so any
        downstream ``.strip()`` is a sign that an old code path is
        defending against a bug that's already fixed at this layer.

        The ``__MASKED__`` sentinel path in
        ``the_one/interfaces/web/api.py::update_provider`` runs BEFORE
        this validator (it overwrites ``data["api_key"]`` with the
        existing-stored value, which is itself already canonical), so the
        sentinel literal is never asked to round-trip through this
        validator. Verified by ``test_masked_sentinel_path_unchanged``.
        """
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


# Pin the explicit ``Literal`` arg-set to ``PROVIDER_TYPES`` at import time so
# any future drift between ``_provider_types.py`` and the model annotation
# trips immediately rather than at first DB write.
assert set(get_args(LLMProviderConfig.model_fields["type"].annotation)) == set(PROVIDER_TYPES), (
    "LLMProviderConfig.type Literal drifted from PROVIDER_TYPES — update both in lockstep."
)


class KnowledgeBase(BaseModel):
    """A knowledge base — stub for future RAG pipeline."""

    id: str
    name: str
    description: str = ""
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class KBItem(BaseModel):
    """An item within a knowledge base (file or URL)."""

    id: str
    kb_id: str
    parent_id: str | None = None
    type: Literal["file", "url"]
    path_or_url: str
    status: str = "pending"
    created_at: str = Field(default_factory=now_iso)


class MCPSource(BaseModel):
    """An MCP source definition — operator-registered server entry."""

    id: str
    name: str
    type: Literal["stdio", "streamable-http"]
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def merged_config(self) -> dict[str, Any]:
        """Return a flat dict combining `config` and `secrets`.

        Used by F2's bearer-token-from-config / env-var resolution path at
        MCP-process spawn time. F4's resolver path keeps the split — do not
        call this method from the resolver.

        Secrets win on key collision so an operator-marked-sensitive field
        overrides any plaintext default of the same name.
        """
        return {**self.config, **self.secrets}


# Hoisted module-level so the F7 L7 Studio editor (and any future routing UI)
# can import the enum without going through the validator.
VALID_ROUTING_SCOPES = frozenset({"channel", "thread", "dm", "peer"})


class Connector(BaseModel):
    """A connector — operator-registered third-party-platform identity.

    Mirrors :class:`MCPSource` shape. Stored in ``connectors``
    (v13 table originally named ``connector_accounts``; v14 added the
    ``name`` column to match MCPSource; v19 added the
    ``CHECK (type IN ('discord', 'stub'))`` constraint via the F8 L2
    table-rename ceremony; v23 renamed the table to ``connectors`` and
    the ``Connector`` Pydantic class to ``Connector`` via M11
    F11 L1).

    ``type`` is narrowed to ``Literal["discord", "stub"]`` (F8 L2). The
    module-load assertion below pins the Literal arg-set to
    ``CONNECTOR_TYPES`` so the two cannot drift, paralleling
    :class:`LLMProviderConfig`'s assert at the top of this module.
    """

    id: str
    name: str
    # NOTE: keep this ``Literal[...]`` spelled out explicitly — Pydantic /
    # static type checkers cannot consume ``Literal[*CONNECTOR_TYPES]``
    # unpacking. The module-load assertion below pins the two in sync.
    type: Literal["discord", "stub"]
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    idle_timeout_seconds: int | None = None
    session_continuation_seconds: int | None = None  # M10 F03 L01
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @field_validator("idle_timeout_seconds")
    @classmethod
    def _validate_idle_timeout_seconds(cls, value: int | None) -> int | None:
        """Bound the per-account pool idle TTL to ``[1, 604800]`` seconds.

        ``None`` means "no per-account override — fall through to the env
        var / default in ``_resolve_ttl_seconds``." The 7-day upper bound
        catches the milliseconds-vs-seconds typo (a value like
        ``31_536_000_000`` is suspiciously high for "keep the connection
        warm"); the lower bound rejects zero / negative which would make
        the warm entry immediately reapable.
        """
        if value is None:
            return value
        if not (1 <= value <= 604800):
            raise ValueError("idle_timeout_seconds must be between 1 and 604800 seconds (7 days)")
        return value

    @field_validator("session_continuation_seconds")
    @classmethod
    def _validate_session_continuation_seconds(cls, value: int | None) -> int | None:
        """Bound the per-account chat-session continuation window to
        ``[1, 604800]`` seconds.

        ``None`` means "no per-account override — fall through to the
        env var / default in
        ``the_one.connectors._session._resolve_continuation_seconds``"
        (the resolver lands in F3 L3; the field exists from this leg
        so the repository round-trip is complete before the resolver
        consumes it).

        Same `1 ≤ value ≤ 604800` bounds as ``idle_timeout_seconds``
        (the 7-day upper bound catches the ms-vs-s typo; the lower
        bound rejects zero / negative). These two are independent
        timeouts — pool warm-entry TTL vs. chat-session continuation
        window — that happen to share an envelope.
        """
        if value is None:
            return value
        if not (1 <= value <= 604800):
            raise ValueError(
                "session_continuation_seconds must be between 1 and 604800 seconds (7 days)"
            )
        return value

    @field_validator("config", mode="after")
    @classmethod
    def _validate_config_reserved_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Enforce shape on the four reserved top-level keys in ``config``.

        The reserved keys are ``"pairing"`` (DM-pairing state),
        ``"allowlist"`` (account-scope peer/channel admission),
        ``"routing"`` (M10 F7: account-scope per-channel agent selection),
        and ``"always_listen"`` (M11 F7 L5: account-level capability
        switch — master gate for the inference path; default False).
        Each is OPTIONAL — when absent, the consumer applies its own
        default (permit for ``pairing`` / ``allowlist`` / ``routing`` via
        ``_default_permit`` at ``the_one/connectors/base.py``; FALSE for
        ``always_listen`` at the policy-gate consume site). All other
        top-level keys in ``config`` pass through unchanged — the F1
        promise that ``config`` is schema-loose remains intact.

        Shape contracts (raise ``ValueError`` on violation):

        - ``config["pairing"] = {"code": str (non-empty), "issued_at": str (ISO)}``.
          No extra keys. Both fields required when ``pairing`` is present.
          The code is stored verbatim — no whitespace trimming (a leg-4
          Studio-form concern, not a model-validation concern). The
          pairing CODE lives in plaintext ``config``, NOT in encrypted
          ``secrets``, because it is a one-time low-entropy shared
          secret meant to gate first-contact; it does not carry the
          lifetime threat model of an API token.
        - ``config["allowlist"] = {"peers": list[str], "channels": list[str]}``.
          Both inner lists required (no partial shape). Empty inner lists
          are PERMITTED and PRESERVED VERBATIM. The validator does NOT
          de-duplicate list entries.

          M10 F6 L7 HAT — semantic redesign (see flight-log
          "Deviations"). Per-axis interpretation:
            - axis missing (``allowlist`` itself absent) → unrestricted
              on every axis (default-permit)
            - axis is ``[]`` (empty list) → unrestricted on THIS axis
              (was "locked / no peer admitted" pre-redesign; flipped to
              match the "empty = unrestricted" intent operators expressed
              at HAT)
            - axis is ``[items]`` → only those peers / channels are
              permitted
          The validator's job is shape, not semantic; the resolver and
          outbound checks interpret the lists. Shape unchanged from
          pre-redesign — existing rows round-trip verbatim; only the
          downstream interpretation flipped.
        - ``config["routing"] = {"rules": list[RoutingRule], "default": str | None}``
          where ``RoutingRule = {"scope": Literal["channel","thread","dm","peer"],
          "match": list[str], "agent": str}``.
          ``match`` is a non-empty list of non-empty strings — set-membership /
          OR semantics: the rule fires if ANY listed value matches the envelope's
          corresponding field.
          The rule list is operator-declared order; the routing engine in F7 L4
          walks it top-to-bottom and the first match wins (Specificity-then-order
          precedence per F7 design decisions). Empty rule list is permitted.
          ``default`` is the per-account fallback agent slug; ``None`` means
          "use first-eligible-attached-agent at routing-engine time."

        ``config["pairing"] = None`` (JSON ``null``) is treated as absent
        — the operator effectively un-pairs the account. Same for
        ``config["allowlist"] = None`` and ``config["routing"] = None``.

        M11 F13 L2 — two new optional reserved flat keys:
        ``inference_provider_config_id`` and ``inference_model``. Each
        is ``str | None``; non-string non-None values are rejected.
        The v26 migration backfills both as ``None`` on existing
        connector rows; operators set them per-connector via the
        Studio connector editor (F13 L4). ``None`` at the dispatcher
        policy gate (F13 L3) falls through to the routed agent's LLM.

        Pydantic v2 ``@field_validator`` runs on both
        ``Connector(**kwargs)`` direct construction AND
        ``Connector.model_validate(dict)``, so this fires on the
        repository read path AT
        ``the_one/db/repositories.py:_row_to_model`` and on the API write
        path at ``the_one/interfaces/web/api.py:{create,update}_connector``.
        """
        pairing = value.get("pairing")
        if pairing is not None:
            if not isinstance(pairing, dict):
                raise ValueError("config['pairing'] must be a dict with keys {'code', 'issued_at'}")
            extra = set(pairing.keys()) - {"code", "issued_at"}
            if extra:
                raise ValueError(f"config['pairing'] has unexpected keys: {sorted(extra)}")
            missing = {"code", "issued_at"} - set(pairing.keys())
            if missing:
                raise ValueError(f"config['pairing'] is missing required keys: {sorted(missing)}")
            code = pairing.get("code")
            if not isinstance(code, str) or not code:
                raise ValueError("config['pairing']['code'] must be a non-empty string")
            issued_at = pairing.get("issued_at")
            if not isinstance(issued_at, str):
                raise ValueError("config['pairing']['issued_at'] must be an ISO-format string")
            # Require a time component (T separator) — date-only strings
            # like "2026-05-18" parse cleanly through fromisoformat but
            # carry no audit value. The leg-4 Studio writer emits full
            # ISO timestamps with time + offset; this guard rejects
            # accidental date-only entries.
            if "T" not in issued_at:
                raise ValueError(
                    "config['pairing']['issued_at'] must include a time "
                    "component (e.g. '2026-05-18T12:34:56Z'); got "
                    f"date-only value {issued_at!r}"
                )
            try:
                # Accept Z-suffix and naive forms; Python 3.11+
                # ``fromisoformat`` parses both with the .replace shim.
                datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
            except ValueError as e:
                raise ValueError(f"config['pairing']['issued_at'] is not ISO-format: {e}")

        allowlist = value.get("allowlist")
        if allowlist is not None:
            if not isinstance(allowlist, dict):
                raise ValueError(
                    "config['allowlist'] must be a dict with keys "
                    "{'peers', 'channels'} (optionally 'guilds', 'roles')"
                )
            # M10 F8 L8 — 4-axis allowlist extension. ``guilds`` and
            # ``roles`` are OPTIONAL Discord-flavored axes; existing 2-key
            # rows still validate (back-compat). The per-axis tri-state
            # semantic (see ``per-axis-tri-state-override`` in agents.md)
            # applies uniformly to all 4 axes downstream — absent axis =
            # unrestricted on this axis.
            # M11 F10 L1 — ``dm_admission`` axis (Literal-string) joins
            # the inner-dict surface as an OPTIONAL key. Default
            # ``"admin-approved"`` is inserted in-place during validation
            # when ``allowlist`` is present but the key is absent
            # (fresh-account default — see M11 F10 L1 + M11 F12 L3 leg
            # artifacts for the full rationale).
            # M11 F12 L3 — structured-tuple shape for ``peers`` (per-peer
            # ``dm_allowed`` bool) + ``channels`` and ``roles`` (per-
            # entry guild_id scoping). The pre-v24 flat ``list[str]``
            # shape is REJECTED post-v24; the v24 migration handles row
            # rewrites. ``dm_admission`` Literal value rename
            # ``"allowlisted-peers-only"`` → ``"admin-approved"``.
            extra = set(allowlist.keys()) - {
                "peers",
                "channels",
                "guilds",
                "roles",
                "dm_admission",
            }
            if extra:
                raise ValueError(f"config['allowlist'] has unexpected keys: {sorted(extra)}")
            missing = {"peers", "channels"} - set(allowlist.keys())
            if missing:
                raise ValueError(f"config['allowlist'] is missing required keys: {sorted(missing)}")

            # M11 F17 L8 (Leg D) — peers axis: list[{id: str}] bare dicts.
            # Post-v28 the per-peer ``dm_allowed`` flag is dropped;
            # in-list == can-DM under ``dm_admission="admin-approved"``.
            # The required key set is now just ``{"id"}``; extra keys
            # are still rejected so callers get clear errors on
            # stale-shape data. (``dm_allowed`` entries still in storage
            # pre-v28 are stripped by the v28 migration; the read path
            # here is strict post-migration.)
            peers_entries = allowlist["peers"]
            if not isinstance(peers_entries, list):
                raise ValueError("config['allowlist']['peers'] must be a list of {id} dicts")
            for i, item in enumerate(peers_entries):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"config['allowlist']['peers'][{i}] must be a "
                        f"dict with key 'id'; got "
                        f"{type(item).__name__}"
                    )
                item_keys = set(item.keys())
                extra_keys = item_keys - {"id"}
                if extra_keys:
                    raise ValueError(
                        f"config['allowlist']['peers'][{i}] has "
                        f"unexpected keys: {sorted(extra_keys)}"
                    )
                missing_keys = {"id"} - item_keys
                if missing_keys:
                    raise ValueError(
                        f"config['allowlist']['peers'][{i}] is missing "
                        f"required keys: {sorted(missing_keys)}"
                    )
                if not isinstance(item["id"], str):
                    raise ValueError(
                        f"config['allowlist']['peers'][{i}]['id'] must "
                        f"be a string; got {type(item['id']).__name__}"
                    )

            # M11 F12 L5 — channels axis:
            # list[{guild_id: str, channel_id: str}]. Post-v25 the
            # guild_id field is REQUIRED and non-null (was str | None in
            # L3); channel_id accepts the wildcard sentinel ``"*"``
            # meaning "any channel of this guild" — emitted by the
            # hierarchical Server-as-parent UI when a server row has no
            # explicit channel narrowing.
            channel_entries = allowlist["channels"]
            if not isinstance(channel_entries, list):
                raise ValueError(
                    "config['allowlist']['channels'] must be a list of {guild_id, channel_id} dicts"
                )
            for i, item in enumerate(channel_entries):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"config['allowlist']['channels'][{i}] must be "
                        f"a dict with keys {{'guild_id', 'channel_id'}}"
                        f"; got {type(item).__name__}"
                    )
                item_keys = set(item.keys())
                extra_keys = item_keys - {"guild_id", "channel_id"}
                if extra_keys:
                    raise ValueError(
                        f"config['allowlist']['channels'][{i}] has "
                        f"unexpected keys: {sorted(extra_keys)}"
                    )
                missing_keys = {"channel_id", "guild_id"} - item_keys
                if missing_keys:
                    raise ValueError(
                        f"config['allowlist']['channels'][{i}] is "
                        f"missing required keys: {sorted(missing_keys)}"
                    )
                if not isinstance(item["channel_id"], str):
                    raise ValueError(
                        f"config['allowlist']['channels'][{i}]"
                        f"['channel_id'] must be a string; got "
                        f"{type(item['channel_id']).__name__}"
                    )
                guild_id = item["guild_id"]
                if not isinstance(guild_id, str):
                    raise ValueError(
                        f"config['allowlist']['channels'][{i}]"
                        f"['guild_id'] must be a non-null string "
                        f"(post-v25 the hierarchical Server-as-parent UI "
                        f"requires every channel entry to be guild-"
                        f"scoped); got {type(guild_id).__name__}"
                    )

            # M10 F8 L8 — guilds axis (OPTIONAL): list[str].
            if "guilds" in allowlist:
                guild_entries = allowlist["guilds"]
                if not isinstance(guild_entries, list):
                    raise ValueError("config['allowlist']['guilds'] must be a list of strings")
                for i, item in enumerate(guild_entries):
                    if not isinstance(item, str):
                        raise ValueError(f"config['allowlist']['guilds'][{i}] must be a string")

            # M11 F12 L5 — roles axis (OPTIONAL):
            # list[{guild_id: str, role_id: str}]. Post-v25 the
            # guild_id field is REQUIRED and non-null (was str | None in
            # L3); role_id accepts the wildcard sentinel ``"*"`` meaning
            # "any role of this guild" — emitted by the hierarchical
            # Server-as-parent UI when a server row has no explicit role
            # narrowing.
            if "roles" in allowlist:
                role_entries = allowlist["roles"]
                if not isinstance(role_entries, list):
                    raise ValueError(
                        "config['allowlist']['roles'] must be a list of {guild_id, role_id} dicts"
                    )
                for i, item in enumerate(role_entries):
                    if not isinstance(item, dict):
                        raise ValueError(
                            f"config['allowlist']['roles'][{i}] must be "
                            f"a dict with keys {{'guild_id', 'role_id'}}"
                            f"; got {type(item).__name__}"
                        )
                    item_keys = set(item.keys())
                    extra_keys = item_keys - {"guild_id", "role_id"}
                    if extra_keys:
                        raise ValueError(
                            f"config['allowlist']['roles'][{i}] has "
                            f"unexpected keys: {sorted(extra_keys)}"
                        )
                    missing_keys = {"role_id", "guild_id"} - item_keys
                    if missing_keys:
                        raise ValueError(
                            f"config['allowlist']['roles'][{i}] is "
                            f"missing required keys: "
                            f"{sorted(missing_keys)}"
                        )
                    if not isinstance(item["role_id"], str):
                        raise ValueError(
                            f"config['allowlist']['roles'][{i}]"
                            f"['role_id'] must be a string; got "
                            f"{type(item['role_id']).__name__}"
                        )
                    guild_id = item["guild_id"]
                    if not isinstance(guild_id, str):
                        raise ValueError(
                            f"config['allowlist']['roles'][{i}]"
                            f"['guild_id'] must be a non-null string "
                            f"(post-v25 the hierarchical Server-as-"
                            f"parent UI requires every role entry to be "
                            f"guild-scoped); got "
                            f"{type(guild_id).__name__}"
                        )

            # M11 F10 L1 + M11 F12 L3: dm_admission axis validation +
            # default insertion. Literal["none", "admin-approved", "all"].
            # Default for absent-key on a present allowlist:
            # "admin-approved" (fresh-account default — F9 flow's intended
            # state, renamed from "allowlisted-peers-only" per F12 L3
            # operator-vocabulary alignment). The v24 migration walks
            # legacy rows and rewrites "allowlisted-peers-only" →
            # "admin-approved", so post-v24 rows reaching this validator
            # ALREADY carry the new Literal value and skip the default.
            dm_admission = allowlist.get("dm_admission")
            if dm_admission is None:
                allowlist["dm_admission"] = "admin-approved"
            elif dm_admission not in ("none", "admin-approved", "all"):
                raise ValueError(
                    f"config['allowlist']['dm_admission'] must be one of "
                    f"{{'none', 'admin-approved', 'all'}}; "
                    f"got {dm_admission!r}"
                )

        routing = value.get("routing")
        if routing is not None:
            if not isinstance(routing, dict):
                raise ValueError("config['routing'] must be a dict with keys {'rules', 'default'}")
            extra = set(routing.keys()) - {"rules", "default"}
            if extra:
                raise ValueError(f"config['routing'] has unexpected keys: {sorted(extra)}")
            missing = {"rules", "default"} - set(routing.keys())
            if missing:
                raise ValueError(f"config['routing'] is missing required keys: {sorted(missing)}")
            rules = routing["rules"]
            if not isinstance(rules, list):
                raise ValueError("config['routing']['rules'] must be a list")
            for i, rule in enumerate(rules):
                if not isinstance(rule, dict):
                    raise ValueError(
                        f"config['routing']['rules'][{i}] must be a dict with keys "
                        "{'scope', 'match', 'agent'}"
                    )
                extra = set(rule.keys()) - {"scope", "match", "agent"}
                if extra:
                    raise ValueError(
                        f"config['routing']['rules'][{i}] has unexpected keys: {sorted(extra)}"
                    )
                missing = {"scope", "match", "agent"} - set(rule.keys())
                if missing:
                    raise ValueError(
                        f"config['routing']['rules'][{i}] is missing required keys: "
                        f"{sorted(missing)}"
                    )
                scope = rule["scope"]
                if not isinstance(scope, str) or scope not in VALID_ROUTING_SCOPES:
                    raise ValueError(
                        f"config['routing']['rules'][{i}]['scope'] must be one of "
                        f"{sorted(VALID_ROUTING_SCOPES)}; got {scope!r}"
                    )
                match = rule["match"]
                if isinstance(match, str):
                    # Legacy single-value form (pre-HAT2). Coerce in-place
                    # to the multi-value list form. Subsequent writes
                    # round-trip the coerced shape, so each row converges
                    # to the new form on next save. No SQL migration needed.
                    match = [match]
                    rule["match"] = match
                if not isinstance(match, list) or not match:
                    raise ValueError(
                        f"config['routing']['rules'][{i}]['match'] must be a "
                        "non-empty list of non-empty strings"
                    )
                for j, match_value in enumerate(match):
                    if not isinstance(match_value, str) or not match_value:
                        raise ValueError(
                            f"config['routing']['rules'][{i}]['match'][{j}] "
                            "must be a non-empty string"
                        )
                agent = rule["agent"]
                if not isinstance(agent, str) or not agent:
                    raise ValueError(
                        f"config['routing']['rules'][{i}]['agent'] must be a non-empty string"
                    )
            default = routing["default"]
            if default is not None and (not isinstance(default, str) or not default):
                raise ValueError(
                    "config['routing']['default'] must be either None or a non-empty string"
                )

        # M11 F7 L5 — ``always_listen``: optional bool. Absent →
        # consume-time default-False (the policy gate at
        # ``_inbound.py`` reads ``account.config.get("always_listen", False)``).
        # Present → must be a bool; non-bool values rejected so the
        # operator can't accidentally smuggle truthy/falsy non-bools
        # through the kv-table editor path.
        if "always_listen" in value:
            always_listen = value["always_listen"]
            if not isinstance(always_listen, bool):
                raise ValueError(
                    "config['always_listen'] must be a bool "
                    "(True or False) when present; absent is treated as "
                    "default-False at consume time"
                )

        # M11 F13 L2 — connector-scope inference LLM configuration.
        # Two optional flat keys on ``config`` (sibling to
        # ``always_listen``): the LLM provider + model the policy-gate
        # inference call uses for this connector. Both default to
        # None at the v26 backfill (operator edits per-connector via
        # the Studio connector editor at F13 L4); ``None`` falls
        # through to the routed agent's LLM at the dispatcher
        # (F13 L3).
        if "inference_provider_config_id" in value:
            ipci = value["inference_provider_config_id"]
            if ipci is not None and not isinstance(ipci, str):
                raise ValueError(
                    "config['inference_provider_config_id'] must be "
                    "a string or None; got "
                    f"{type(ipci).__name__}"
                )
        if "inference_model" in value:
            im = value["inference_model"]
            if im is not None and not isinstance(im, str):
                raise ValueError(
                    f"config['inference_model'] must be a string or None; got {type(im).__name__}"
                )

        # M11 F7 L5 — strip the legacy ``auto_relay_platform_replies``
        # key on every validate cycle. Existing rows with the key
        # continue to load (the reserved-keys validator above does
        # not touch it on read), but the first save after L5 lands
        # cleans the dict so persisted rows converge to the new
        # shape. Auto-relay became invariant in F7; the key carries
        # no useful information and is removed from the public
        # contract.
        value.pop("auto_relay_platform_replies", None)

        return value


# Pin the explicit ``Literal`` arg-set to ``CONNECTOR_TYPES`` at import time so
# any future drift between ``_connector_types.py`` and the model annotation
# trips immediately rather than at first DB write. M10 F8 L2 — paralleling
# ``LLMProviderConfig``'s assert above (mirrors the M07 ``'mock'``-in-
# ``PROVIDER_TYPES`` precedent; ``'stub'`` is the test-only carve-out
# documented in ``_connector_types.py``).
assert set(get_args(Connector.model_fields["type"].annotation)) == set(CONNECTOR_TYPES), (
    "Connector.type Literal drifted from CONNECTOR_TYPES — update both in lockstep."
)


class PendingApproval(BaseModel):
    """A pending Discord-native peer-approval row.

    M11 F9 L2 — Discord-native approval flow primary path. Created by
    the inbound dispatcher when an unknown DM arrives without a
    ``PAIR `` prefix; consumed (via ``mark_approved``) by the API
    endpoint at F9 L3 ``POST /api/connectors/{account_id}/
    peer-approvals/{approval_id}/approve``; rendered by the Chat UI
    at F9 L4.

    Dedup: at most ONE row per ``(connector_id, peer_id)``
    with ``status='pending'`` at any time; the dispatcher's emit path
    upserts. ``approved`` and ``dismissed`` rows are terminal and
    persist as history; a new ``pending`` may coexist with them after
    the operator removes a peer from the allowlist.
    """

    id: str
    connector_id: str
    peer_id: str
    peer_name: str
    preview: str
    received_at: str = Field(default_factory=now_iso)
    status: Literal["pending", "approved", "dismissed"] = "pending"
    resolved_at: str | None = None
    # v29 replay-context fields (M11 F17 L10 — Leg F).
    # All nullable for back-compat with pre-v29 rows (legacy path).
    original_message: str | None = None
    """The full inbound text (NOT the truncated ``preview``). Used to
    reconstruct the ``InboundEnvelope`` at approval-replay time."""
    channel_id: str | None = None
    """The DM channel id from the original inbound envelope."""
    thread_id: str | None = None
    """The thread id from the original inbound envelope (None for top-level
    DM messages)."""
    is_dm: bool | None = None
    """True when the original message was a direct message."""


class ToolConfig(BaseModel):
    """A tool-level config row — operator-set defaults for a built-in tool.

    Mirrors `MCPSource` shape but keyed by `name` (the tool's stable
    identifier). The resolver composes this with a per-agent override
    dict from `AgentConfig.tool_overrides` at `AgentFactory.create()`
    time (session-bound; mid-session edits do not affect running agents).

    `enabled` (added in schema v9) is operator-set tool-level on/off.
    Disabled tools are filtered out of the registry at L1's enforcement
    point — independent of per-agent enabled_tools / disabled_tools.
    """

    name: str
    config: dict = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def merged_config(self) -> dict[str, Any]:
        """Return a flat dict combining `config` and `secrets`.

        Used by the agent factory's resolver feed (`factory.py`) so the
        tool-policy resolver / `build_search_backend` receive the REAL
        decrypted secret values (api keys), not the masked admin-GET view.

        Secrets win on key collision so an operator-marked-secret field
        overrides any plaintext default of the same name. Mirrors
        `MCPSource.merged_config()`.
        """
        return {**self.config, **self.secrets}


class ChatSession(BaseModel):
    """A chat session with message history.

    Mission 10 Flight 3 Leg 1: connector-keyed sessions add the
    (platform, connector_id, channel_id, thread_id, peer_id)
    quintuple plus a JSON metadata column and a last_inbound_at
    timestamp. All seven default to None for non-connector sessions
    (back-compat) and are populated by the inbound dispatcher
    (leg 4) for connector-driven sessions.

    The (platform, connector_id, channel_id, COALESCE(thread_id, ''))
    4-tuple is the lookup key consumed by leg 3's resolver against the
    partial expression index ``idx_chat_sessions_external_key``.
    ``peer_id`` is stored for audit and future per-peer-scoped sessions
    (Flight 6 territory) but is NOT part of the lookup key.
    """

    id: str
    agent_name: str | None = None
    title: str = "New chat"
    messages: str = "[]"  # JSON-encoded via codec
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    # M10 F03 L01: connector-session external key + metadata.
    # ``session_metadata`` is a dict at the model layer; the repository
    # encodes via ``json.dumps`` on write and decodes via ``json.loads``
    # on read (parallel to how ``messages`` is a JSON-encoded string in
    # the column but a Python list at the codec layer).
    platform: str | None = None
    connector_id: str | None = None
    channel_id: str | None = None
    thread_id: str | None = None
    peer_id: str | None = None
    session_metadata: dict[str, Any] | None = None
    last_inbound_at: str | None = None
