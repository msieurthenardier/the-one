"""Discord Gateway v10 + REST connector (Mission 23 Flight 3, DD-1..DD-4).

Hand-rolled on ``websockets`` + ``httpx`` (already base deps — no new
dependencies; ``discord.py``/``aiohttp`` stay absent). ``register()`` wires
the production plugin into ``the_one.connectors.registry`` for app
lifespan startup.
"""

from __future__ import annotations

from the_one.connectors import registry
from the_one.connectors.discord._rest import DEFAULT_BASE_URL
from the_one.connectors.discord.plugin import DiscordClient, DiscordPlugin

__all__ = ["DiscordClient", "DiscordPlugin", "register"]


def register(*, rest_base_url: str = DEFAULT_BASE_URL, gateway_url: str | None = None) -> None:
    """Register the production ``DiscordPlugin`` under type ``"discord"``.

    Called unconditionally from app lifespan startup (DD-1) — Discord is
    a real platform, unlike the dual-gated stub. Idempotent in the sense
    ``registry.register`` always is (a flat dict overwrite). The two URL
    keywords exist for the dev-only fake-platforms seam; this package
    never reads the environment.
    """
    registry.register(
        "discord", DiscordPlugin(rest_base_url=rest_base_url, gateway_url=gateway_url)
    )
