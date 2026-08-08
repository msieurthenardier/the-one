"""Env-based configuration for the live-traffic Discord HAT.

The driver reads bot tokens and test-guild ids from the environment ONLY —
no token value is ever read from a committed file. A local ``.env.hat``
(gitignored) is the operator's convenience for exporting these; the
contract here is the env vars themselves. ``.env.hat.example`` (committed,
placeholders only) documents the variable names.

When the required env is absent, :func:`skip_if_unconfigured` cleanly
``pytest.skip``s so ``make test-discord-hat`` with no env SKIPs rather than
errors, and the normal backend suite (which never selects ``discord_hat``)
is unaffected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pytest

from the_one.api_credential import get_credential

# Default the-one HTTP base URL — mirrors tests/test_aiat.py's convention.
_DEFAULT_BASE_URL = "http://localhost:8484"


def auth_headers() -> dict[str, str]:
    """``Authorization`` header dict carrying the long-lived local-API
    credential (Mission 20 Flight 1 Leg 5 — the gate is live).

    Uses ``get_credential()`` (ambient ``settings.data_dir`` /
    ``THE_ONE_DATA_DIR``, create-on-first-use), mirroring
    ``tests/_credential_helpers.py::auth_headers`` for the unit suite. The
    HAT runs on the same machine as the instance it targets (a local-API
    credential has no meaning across machines), so whatever data directory
    this process's ``settings.data_dir`` currently resolves to — pointed at
    the target instance's data directory via ``THE_ONE_DATA_DIR`` when the
    HAT targets anything other than the default local data dir — is the
    correct credential source.
    """
    return {"Authorization": f"Bearer {get_credential().encode()}"}


@dataclass(frozen=True)
class HatConfig:
    """Resolved, validated HAT configuration.

    ``tokens`` drives N sender bots; ``bot_user_id`` is the-one's OWN
    Discord bot user id (gateway-assigned, not persisted to the API), used
    to build ``@mention`` strings and to address DMs to the-one.

    ``bot_user_ids`` is OPTIONAL (defaults to ``[]`` when
    ``THE_ONE_HAT_BOT_USER_IDS`` is absent). Only the tests that key on
    specific burner-bot user ids (ACL peers axis) read this field and
    locally ``pytest.skip`` when it is empty — so the three scenarios that
    don't use bot ids (``test_smoke``, ``test_multi_channel``,
    ``test_multi_agent``) are NOT made to skip by this var's absence.
    """

    tokens: list[str]
    guild_id: str
    channel_ids: list[str]
    connector_id: str
    bot_user_id: str
    base_url: str
    bot_user_ids: list[str] = field(default_factory=list)


def _read_tokens() -> list[str]:
    """Read sender-bot tokens from env.

    Prefers the comma-separated ``THE_ONE_HAT_BOT_TOKENS``; falls back to
    the numbered ``THE_ONE_HAT_BOT_TOKEN_{1,2,3}`` vars (in order, skipping
    any that are unset). Returns an empty list when none are present.
    """
    combined = os.environ.get("THE_ONE_HAT_BOT_TOKENS", "").strip()
    if combined:
        return [t.strip() for t in combined.split(",") if t.strip()]
    numbered: list[str] = []
    for i in (1, 2, 3):
        val = os.environ.get(f"THE_ONE_HAT_BOT_TOKEN_{i}", "").strip()
        if val:
            numbered.append(val)
    return numbered


def _read_bot_user_ids() -> list[str]:
    """Read burner-bot user ids from ``THE_ONE_HAT_BOT_USER_IDS``.

    Comma-separated, mirroring ``_read_tokens`` / ``_read_channel_ids``.
    Returns an empty list when the var is absent — this is an OPTIONAL field;
    absence must not affect tests that don't use the ids.
    """
    raw = os.environ.get("THE_ONE_HAT_BOT_USER_IDS", "").strip()
    if not raw:
        return []
    return [uid.strip() for uid in raw.split(",") if uid.strip()]


def _read_channel_ids() -> list[str]:
    raw = os.environ.get("THE_ONE_HAT_CHANNEL_IDS", "").strip()
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


def load() -> HatConfig | None:
    """Build a :class:`HatConfig` from env, or ``None`` if any required
    value is absent. Never raises on missing env — absence is the default
    (un-provisioned) state and must produce a skip, not an error.
    """
    tokens = _read_tokens()
    guild_id = os.environ.get("THE_ONE_HAT_GUILD_ID", "").strip()
    channel_ids = _read_channel_ids()
    connector_id = os.environ.get("THE_ONE_HAT_CONNECTOR_ID", "").strip()
    bot_user_id = os.environ.get("THE_ONE_HAT_BOT_USER_ID", "").strip()
    base_url = os.environ.get("THE_ONE_TEST_URL", _DEFAULT_BASE_URL).strip()

    if not (tokens and guild_id and channel_ids and connector_id and bot_user_id):
        return None

    return HatConfig(
        tokens=tokens,
        guild_id=guild_id,
        channel_ids=channel_ids,
        connector_id=connector_id,
        bot_user_id=bot_user_id,
        base_url=base_url or _DEFAULT_BASE_URL,
        bot_user_ids=_read_bot_user_ids(),
    )


def skip_if_unconfigured() -> HatConfig:
    """Return the loaded :class:`HatConfig`, or ``pytest.skip`` if the env
    is not provisioned. Call this at the top of every ``discord_hat`` test.
    """
    cfg = load()
    if cfg is None:
        pytest.skip(
            "discord_hat env not configured "
            "(set THE_ONE_HAT_BOT_TOKENS / _GUILD_ID / _CHANNEL_IDS / "
            "_CONNECTOR_ID / _BOT_USER_ID)"
        )
    return cfg
