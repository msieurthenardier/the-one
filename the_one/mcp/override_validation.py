"""Save-time validation of per-agent MCP credentials (sortie 09 DD2).

``validate_mcp_overrides`` checks the RAW ``mcp_overrides`` of an agent write
(before the credential merge), so what is checked is what the operator sent. A
value shaped like a mask (``_looks_masked``) is the client keeping a stored
value and is not checked. Every refusal is a detail in the sortie 07 shape::

    {"type": "mcp_override",
     "loc": ["mcp_overrides", <source name>, "headers"|"env"|"bearer_token", <name>?],
     "msg": <one plain sentence>}

A message never contains a value (and never a header or variable name: ``loc``
carries it). The value grammar is the RFC 9110 field-value grammar without
obs-text: any other control character would make the HTTP layer raise an error
that embeds the value, and that text reaches the agent through the tool-error
envelope.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from the_one.mcp._overrides import MCP_OVERRIDE_CREDENTIAL_KEYS, has_oauth_state

OAUTH_AUTHORIZATION_REFUSAL = (
    "This server signs in with OAuth, so its Authorization header can't be set per agent."
)

# RFC 9110 `tchar`.
_TOKEN_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Visible ASCII, space and tab.
_FIELD_VALUE_RE = re.compile(r"^[\x20-\x7e\t]+$")

_TRANSPORT_MANAGED = frozenset(
    {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "content-type",
        "accept",
        "mcp-session-id",
        "mcp-protocol-version",
    }
)


def carries_credentials(incoming: Any) -> bool:
    """True iff any source entry of ``incoming`` has a credential key or ``plain_names``
    (even a null clear): the entries ``validate_mcp_overrides`` has something to check in."""
    if not isinstance(incoming, dict):
        return False
    return any(
        isinstance(entry, dict)
        and (any(k in entry for k in MCP_OVERRIDE_CREDENTIAL_KEYS) or "plain_names" in entry)
        for entry in incoming.values()
    )


def _detail(source: str, field: str, name: str | None, msg: str) -> dict[str, Any]:
    loc: list[str] = ["mcp_overrides", source, field]
    if name is not None:
        loc.append(name)
    return {"type": "mcp_override", "loc": loc, "msg": msg}


def _header_value_problem(value: str) -> str | None:
    trimmed = value.strip()
    if not trimmed:
        return "A header value can't be empty."
    if not _FIELD_VALUE_RE.fullmatch(trimmed):
        return "A header value can only contain visible ASCII characters, spaces and tabs."
    return None


def validate_mcp_overrides(
    incoming: Any,
    sources_by_name: dict[str, Any],
    looks_masked: Callable[[Any], bool],
) -> list[dict[str, Any]]:
    """The refusals for a raw ``mcp_overrides`` body (``[]`` when it is valid).

    ``sources_by_name`` maps a source name to its stored ``MCPSource``; a name
    with no source is an orphan entry, which only the source-independent rules
    apply to. ``looks_masked`` is the API's mask recognizer, passed in so this
    module does not import the API.
    """
    details: list[dict[str, Any]] = []
    if not isinstance(incoming, dict):
        return details
    for source_name, entry in incoming.items():
        if not isinstance(entry, dict):
            continue
        source = sources_by_name.get(source_name)
        oauth = source is not None and has_oauth_state(source)
        stdio = source is not None and source.type == "stdio"
        http = source is not None and source.type != "stdio"

        # plain_names (sortie 09 L05): names whose value is returned in clear
        if "plain_names" in entry and entry["plain_names"] is not None:
            plain = entry["plain_names"]
            if not isinstance(plain, list) or not all(isinstance(n, str) for n in plain):
                details.append(
                    _detail(
                        source_name,
                        "plain_names",
                        None,
                        "Plain names must be a list of names.",
                    )
                )
            else:
                for name in plain:
                    if not stdio and name.strip().lower() == "authorization":
                        details.append(
                            _detail(
                                source_name,
                                "plain_names",
                                name,
                                "An Authorization value is always sensitive.",
                            )
                        )

        # headers
        if "headers" in entry and entry["headers"] is not None:
            headers = entry["headers"]
            if not isinstance(headers, dict):
                details.append(
                    _detail(
                        source_name,
                        "headers",
                        None,
                        "Headers must be a set of names and values.",
                    )
                )
            else:
                if stdio and headers:
                    details.append(
                        _detail(
                            source_name,
                            "headers",
                            None,
                            "This server runs as a local command, so it takes environment "
                            "variables, not headers.",
                        )
                    )
                seen: dict[str, str] = {}
                for name, value in headers.items():
                    masked = looks_masked(value)
                    lowered = name.strip().lower() if isinstance(name, str) else name
                    prior = seen.get(lowered)
                    if prior is not None:
                        if not masked or not looks_masked(headers.get(prior)):
                            details.append(
                                _detail(
                                    source_name,
                                    "headers",
                                    name,
                                    "Two header names differ only by case; keep one.",
                                )
                            )
                        continue
                    seen[lowered] = name
                    if masked:
                        continue
                    if not isinstance(name, str) or not _TOKEN_RE.fullmatch(name):
                        details.append(
                            _detail(
                                source_name,
                                "headers",
                                str(name),
                                "A header name can only use letters, digits and !#$%&'*+-.^_`|~.",
                            )
                        )
                        continue
                    if lowered in _TRANSPORT_MANAGED:
                        details.append(
                            _detail(
                                source_name,
                                "headers",
                                name,
                                "This header is set by the connection itself and can't be "
                                "overridden.",
                            )
                        )
                        continue
                    if not isinstance(value, str):
                        details.append(
                            _detail(source_name, "headers", name, "A header value must be text.")
                        )
                        continue
                    problem = _header_value_problem(value)
                    if problem:
                        details.append(_detail(source_name, "headers", name, problem))
                        continue
                    if oauth and lowered == "authorization":
                        details.append(
                            _detail(source_name, "headers", name, OAUTH_AUTHORIZATION_REFUSAL)
                        )

        # env
        if "env" in entry and entry["env"] is not None:
            env = entry["env"]
            if not isinstance(env, dict):
                details.append(
                    _detail(
                        source_name,
                        "env",
                        None,
                        "Environment must be a set of names and values.",
                    )
                )
            else:
                if http and env:
                    details.append(
                        _detail(
                            source_name,
                            "env",
                            None,
                            "This server is reached over HTTP, so it takes headers, not "
                            "environment variables.",
                        )
                    )
                for name, value in env.items():
                    if looks_masked(value):
                        continue
                    if not isinstance(name, str) or not _ENV_NAME_RE.fullmatch(name):
                        details.append(
                            _detail(
                                source_name,
                                "env",
                                str(name),
                                "An environment variable name can only use letters, digits and "
                                "underscores, and can't start with a digit.",
                            )
                        )
                        continue
                    if not isinstance(value, str):
                        details.append(
                            _detail(
                                source_name,
                                "env",
                                name,
                                "An environment variable value must be text.",
                            )
                        )
                        continue
                    if not value.strip():
                        details.append(
                            _detail(
                                source_name,
                                "env",
                                name,
                                "An environment variable value can't be empty.",
                            )
                        )
                    elif "\x00" in value:
                        details.append(
                            _detail(
                                source_name,
                                "env",
                                name,
                                "An environment variable value can't contain a NUL character.",
                            )
                        )

        # bearer_token
        if "bearer_token" in entry and entry["bearer_token"] is not None:
            token = entry["bearer_token"]
            if not looks_masked(token):
                if not isinstance(token, str):
                    details.append(
                        _detail(source_name, "bearer_token", None, "A bearer token must be text.")
                    )
                else:
                    problem = _header_value_problem(token)
                    if problem:
                        details.append(
                            _detail(
                                source_name,
                                "bearer_token",
                                None,
                                problem.replace("A header value", "A bearer token"),
                            )
                        )
                    elif oauth:
                        details.append(
                            _detail(source_name, "bearer_token", None, OAUTH_AUTHORIZATION_REFUSAL)
                        )
    return details
