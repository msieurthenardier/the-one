"""``WebSearchConfig`` — the per-tool Config for ``WebSearchTool`` (M16 F08 L02).

Splits ``web_search`` off the shared ``WebConfig`` onto a dedicated config that
carries the search-engine selector + per-engine connection fields. ``web_search``
never read ``WebConfig``'s SSRF/transport fields (it consumed only the injected
``SearchBackend``), so the migration is safe — the other web tools
(``http_request`` / ``fetch_url`` / ``download_file``) keep ``WebConfig``.

References:

* **M16 F08 DD3 (refinement)** — the pluggable backend is widened to a
  configurable engine registry inside the ``web_search`` tool config. This is
  the backend half: the selector + per-engine fields live here; the schema-driven
  tools-admin form renders them for free (``ui_hint:"dropdown"`` selector,
  ``ui_hint:"password"`` secret fields). The admin UI polish + secret-at-rest
  encryption are leg ``search-config-admin``.

**Secret hygiene + leg-3 dependency.** The keyed-engine secrets
(``google_pse_api_key``, ``brave_api_key``, ``tavily_api_key``) are MARKED here
(``json_schema_extra={"ui_hint":"password","secret":true}``) but are STILL
PLAINTEXT in the persisted ``config`` blob. Leg ``search-config-admin`` MUST
land the encrypted-at-rest ``secrets`` split before the flight batch-commits.
The flight commits at the end (no intermediate release), so plaintext secrets
never ship.

**Resolver markers.** The secret fields carry NO resolver marker. ``Narrow`` on
a ``str`` raises ``NotImplementedError`` in ``_check_narrow``; a markerless field
is operator-only (an agent override on it raises ``ValueError`` at resolver
time — exactly the desired "agents cannot set search secrets" posture, mirroring
``WebConfig.redirect_cap``). The same applies to ``search_backend``,
``searxng_base_url``, and ``google_pse_cse_id``: operator-only.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The five selectable engines. Order pins the dropdown order; ``duckduckgo`` is
# the keyless default.
_SEARCH_BACKEND_UI_CHOICES: list[dict[str, object]] = [
    {"value": "duckduckgo", "label": "DuckDuckGo (default, no key needed)"},
    {"value": "searxng", "label": "SearXNG (your own server)"},
    {"value": "google_pse", "label": "Google Programmable Search (needs a key and an engine ID)"},
    {"value": "brave", "label": "Brave Search (needs a key)"},
    {"value": "tavily", "label": "Tavily (needs a key)"},
]


class WebSearchConfig(BaseModel):
    """Per-tool Config for ``WebSearchTool``: search-engine selector + per-engine
    connection fields.

    Six fields:

    * ``search_backend`` (Literal enum dropdown) — which engine is active.
      Default ``"duckduckgo"`` (keyless). Operator-only (no resolver marker).
    * ``searxng_base_url`` (str) — SearXNG instance base URL. Operator-only.
    * ``google_pse_api_key`` (str, SECRET) — Google PSE API key.
    * ``google_pse_cse_id`` (str) — Google PSE custom-search-engine id.
    * ``brave_api_key`` (str, SECRET) — Brave Search API key.
    * ``tavily_api_key`` (str, SECRET) — Tavily API key.

    Secret fields carry ``json_schema_extra={"ui_hint":"password","secret":true}``
    so the tools-admin form (leg 3) renders them masked and the persistence
    layer (leg 3) can split them into the encrypted ``secrets`` store. They are
    plaintext until leg 3 lands — acceptable because the flight batch-commits
    (no intermediate release).

    Frozen so a ``cross_configs`` entry shared by reference cannot be mutated by
    one tool to corrupt a peer's view (mirrors ``WebConfig`` / ``FilesystemConfig``
    posture).
    """

    model_config = ConfigDict(frozen=True)

    search_backend: Literal["duckduckgo", "searxng", "google_pse", "brave", "tavily"] = Field(
        default="duckduckgo",
        title="Search engine",
        description=(
            "Which search engine the tool uses. DuckDuckGo needs no account or "
            "key; the others need the details that appear below when you pick one."
        ),
        json_schema_extra={
            "ui_hint": "dropdown",
            "ui_choices": _SEARCH_BACKEND_UI_CHOICES,
        },
    )

    searxng_base_url: str = Field(
        default="",
        title="SearXNG URL",
        description=(
            "The address of your SearXNG server, for example "
            "https://searx.example.org. Needed when SearXNG is the search "
            "engine. The server must have the JSON result format turned on."
        ),
        json_schema_extra={"show_if": {"search_backend": "searxng"}},
    )

    google_pse_api_key: str = Field(
        default="",
        title="Google PSE API key",
        description=(
            "Your Google Programmable Search Engine API key. Needed when "
            "Google Programmable Search is the search engine. It is stored encrypted."
        ),
        json_schema_extra={
            "ui_hint": "password",
            "secret": True,
            "show_if": {"search_backend": "google_pse"},
        },
    )

    google_pse_cse_id: str = Field(
        default="",
        title="Google PSE engine ID",
        description=(
            "The ID of your Google Programmable Search Engine (the 'cx' value "
            "in its settings). Needed when Google Programmable Search is the search engine."
        ),
        json_schema_extra={"show_if": {"search_backend": "google_pse"}},
    )

    brave_api_key: str = Field(
        default="",
        title="Brave API key",
        description=(
            "Your Brave Search API token. Needed when Brave Search is the "
            "search engine. It is stored encrypted."
        ),
        json_schema_extra={
            "ui_hint": "password",
            "secret": True,
            "show_if": {"search_backend": "brave"},
        },
    )

    tavily_api_key: str = Field(
        default="",
        title="Tavily API key",
        description=(
            "Your Tavily API key. Needed when Tavily is the search engine. It is stored encrypted."
        ),
        json_schema_extra={
            "ui_hint": "password",
            "secret": True,
            "show_if": {"search_backend": "tavily"},
        },
    )


# The secret field names — single source of truth for the leg-3 encrypted-split
# wiring and the field-count/secret-marker guard test.
WEB_SEARCH_SECRET_FIELDS: tuple[str, ...] = (
    "google_pse_api_key",
    "brave_api_key",
    "tavily_api_key",
)
