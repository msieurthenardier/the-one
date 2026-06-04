"""Shared ACL fixture-shape translator helpers (F13 L1 extraction).

Consolidates the per-test-file translators that mechanical-translate
flat-shape allowlist fixture data to the v24 structured-tuple shape.
Imported by ``tests/test_connectors_acl.py``,
``tests/test_connectors_routing.py``,
``tests/test_connectors_commands.py``, and ``tests/browser/seeders.py``
so the four files share a single source of truth.

See ``the_one/agents.md`` M11 ``test-translator-helpers-for-shape-evolution``
for the convention this module codifies.

Post-F13 L2: ``_to_v24_agent_acl`` (per-agent translator) no longer
emits ``dm_allowed`` on bare-string OR tuple-shape peer entries —
per-agent peers entries are bare ``{id: str}`` dicts (paired with
the v26 Pydantic validator that REJECTS ``dm_allowed`` at per-agent
scope and the v26 migration that strips it from stored data; F12
footgun retirement).

Post-F17 L8 (Leg D / v28): the account-scope ``_to_v24_shape``
translator also emits bare ``{id: str}`` peers — the per-peer
``dm_allowed`` field has been retired at account scope too. The
v28 migration strips it from stored data; the Pydantic validator
(``models.py``) now REJECTS ``dm_allowed`` at account scope as well.
"""

from __future__ import annotations

# M11 F12 L5 — every channel/role entry must have a non-null
# guild_id (the v24 ``str | None`` permissive semantic was removed at
# F12 L5). Flat-string channel/role fixture entries default to this
# constant; tests that exercise guild_id matching pass the same value
# in their envelope kwargs / payloads so the entry's guild_id matches.
DEFAULT_TEST_GUILD_ID = "g-test"


def _to_v24_shape(allowlist: dict) -> dict:
    """Translate a flat-shape allowlist to the post-v28 structured shape.
    Account-scope variant — peers are bare ``{id: str}`` dicts
    (``dm_allowed`` retired by M11 F17 L8 Leg D / v28 migration).

    Tuple form for backward-compat with existing fixtures:
      - ``"P1"`` → ``{"id": "P1"}``
      - ``("P1", True)`` → ``{"id": "P1"}``  (dm_allowed silently dropped)
      - ``("P1", False)`` → ``{"id": "P1"}`` (dm_allowed silently dropped)
      - Already-dict ``{"id": ..., "dm_allowed": ...}``: dm_allowed stripped.
      - Already-bare ``{"id": ...}`` dict: passed through.
    """
    result = dict(allowlist)
    if "peers" in result and isinstance(result["peers"], list):
        peers_new = []
        for entry in result["peers"]:
            if isinstance(entry, dict):
                # Strip dm_allowed if present (legacy / pre-v28 shape).
                peers_new.append({"id": entry["id"]} if "id" in entry else entry)
            elif isinstance(entry, tuple):
                peers_new.append({"id": entry[0]})
            else:
                peers_new.append({"id": entry})
        result["peers"] = peers_new
    if "channels" in result and isinstance(result["channels"], list):
        channels_new = []
        for entry in result["channels"]:
            if isinstance(entry, dict):
                channels_new.append(entry)
            elif isinstance(entry, tuple):
                channels_new.append({"guild_id": entry[0], "channel_id": entry[1]})
            else:
                channels_new.append(
                    {
                        "guild_id": DEFAULT_TEST_GUILD_ID,
                        "channel_id": entry,
                    }
                )
        result["channels"] = channels_new
    if "roles" in result and isinstance(result["roles"], list):
        roles_new = []
        for entry in result["roles"]:
            if isinstance(entry, dict):
                roles_new.append(entry)
            elif isinstance(entry, tuple):
                roles_new.append({"guild_id": entry[0], "role_id": entry[1]})
            else:
                roles_new.append({"guild_id": DEFAULT_TEST_GUILD_ID, "role_id": entry})
        result["roles"] = roles_new
    if result.get("dm_admission") == "allowlisted-peers-only":
        result["dm_admission"] = "admin-approved"
    return result


def _to_v24_agent_acl(agent_acl: dict | None) -> dict | None:
    """Per-agent ACL translator. Same channel/role guild-default
    semantics as :func:`_to_v24_shape`.

    Post-F13 L2: per-agent peers entries are bare ``{id: str}``
    dicts; the ``dm_allowed`` field is REJECTED at per-agent scope
    (F12 footgun retirement via the v26 migration + Pydantic
    validator). This helper is a fixture-shape translator, not a
    validator:

      - Bare-string peer entries (``"P1"``) → ``{"id": "P1"}``
        (post-L2; no ``dm_allowed`` emitted).
      - Tuple peer entries (``("P1", True)`` / ``("P1", False)``)
        → ``{"id": "P1"}`` — the tuple's second element is silently
        dropped (per-agent peers no longer carry ``dm_allowed``;
        fixtures still passing tuples here lose the second element
        rather than raise).
      - Dict-shape entries pass through unchanged. Fixtures using
        dict shape are expected to already be in the post-L2 shape
        (``{"id": ...}`` only); ``{"id": ..., "dm_allowed": ...}``
        dict-shape entries are NOT stripped by the translator and
        will fail the downstream Pydantic validator.

    ``None`` short-circuits.
    """
    if agent_acl is None:
        return None
    result = dict(agent_acl)
    if isinstance(result.get("peers"), list):
        peers_new = []
        for entry in result["peers"]:
            if isinstance(entry, dict):
                peers_new.append(entry)
            elif isinstance(entry, tuple):
                peers_new.append({"id": entry[0]})
            else:
                peers_new.append({"id": entry})
        result["peers"] = peers_new
    if isinstance(result.get("channels"), list):
        channels_new = []
        for entry in result["channels"]:
            if isinstance(entry, dict):
                channels_new.append(entry)
            elif isinstance(entry, tuple):
                channels_new.append({"guild_id": entry[0], "channel_id": entry[1]})
            else:
                channels_new.append(
                    {
                        "guild_id": DEFAULT_TEST_GUILD_ID,
                        "channel_id": entry,
                    }
                )
        result["channels"] = channels_new
    if isinstance(result.get("roles"), list):
        roles_new = []
        for entry in result["roles"]:
            if isinstance(entry, dict):
                roles_new.append(entry)
            elif isinstance(entry, tuple):
                roles_new.append({"guild_id": entry[0], "role_id": entry[1]})
            else:
                roles_new.append({"guild_id": DEFAULT_TEST_GUILD_ID, "role_id": entry})
        result["roles"] = roles_new
    return result


# Alias preserved for browser-seeder import compatibility.
# Post-v28: both names produce bare ``{id}`` peer entries.
_to_v24_allowlist = _to_v24_shape
