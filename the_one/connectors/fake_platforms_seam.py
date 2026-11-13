"""Dev-only seam: point the Discord and Telegram clients at local fakes.

Pure and never raises. ``fake_platform_urls`` validates the value of
``THE_ONE_FAKE_PLATFORMS_URL`` so a bot token can never be sent anywhere
but a loopback IP literal (no host names: DNS is not trusted). The lifespan
decides what to do with the result; this module reads no environment.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class FakeUrls:
    discord_rest: str
    discord_gateway: str
    telegram_base: str


@dataclass(frozen=True)
class Refused:
    reason: str
    scheme: str = ""
    host: str = ""


def _refuse(reason: str, scheme: str = "", host: str = "") -> Refused:
    return Refused(reason, scheme, host)


def fake_platform_urls(raw: object, *, dev_mode: bool) -> FakeUrls | None | Refused:
    """Return the fake URLs, ``None`` (seam off) or ``Refused(reason)``."""
    if not dev_mode:
        return None
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    if not isinstance(raw, str):
        return _refuse("the value is not a string")
    if len(raw) > 2048:
        return _refuse("the value is too long")
    value = raw.strip()
    try:
        parts = urlsplit(value)
        scheme = parts.scheme
        host = parts.hostname or ""
        if scheme != "http":
            return _refuse("the scheme must be http", scheme, host)
        if "@" in parts.netloc:
            return _refuse("credentials in the address are not allowed", scheme, host)
        if parts.query or parts.fragment or "?" in value or "#" in value:
            return _refuse("a query or fragment is not allowed", scheme, host)
        if parts.path not in ("", "/"):
            return _refuse("a path is not allowed", scheme, host)
        try:
            port = parts.port
        except ValueError:
            return _refuse("the port is invalid", scheme, host)
        if port is None:
            return _refuse("a port is required", scheme, host)
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return _refuse("the host must be a loopback IP address, not a name", scheme, host)
        if not addr.is_loopback:
            return _refuse("the host must be a loopback IP address", scheme, host)
        netloc = f"[{addr}]:{port}" if addr.version == 6 else f"{addr}:{port}"
    except Exception:
        return _refuse("the value could not be parsed")
    return FakeUrls(
        discord_rest=f"http://{netloc}/discord/api/v10",
        discord_gateway=f"ws://{netloc}/discord/gateway",
        telegram_base=f"http://{netloc}/telegram",
    )
