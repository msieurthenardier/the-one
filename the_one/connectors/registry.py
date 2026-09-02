"""Connector type → plugin registry.

Mirrors ``the_one.mcp.oauth``'s credential-source registration shape:
a plain module-level dict, populated at process start for production
types and via :func:`register_for_test` in tests. No production plugin
ships yet (Discord lands Flight 3) — only tests register (the ``"stub"``
type).
"""

from __future__ import annotations

from the_one.connectors.base import ConnectorPlugin

_PLUGINS: dict[str, ConnectorPlugin] = {}


def register_for_test(type_name: str, plugin: ConnectorPlugin) -> None:
    """Register ``plugin`` under ``type_name``. Tests only."""
    _PLUGINS[type_name] = plugin


def register(type_name: str, plugin: ConnectorPlugin) -> None:
    """Register ``plugin`` under ``type_name`` for production use.

    The production counterpart to :func:`register_for_test` — called from
    app lifespan startup for a real platform plugin (Discord, Mission 23
    Flight 3), unconditionally (unlike the stub hook, which is dual-gated
    dev/test-only). Mechanically identical to :func:`register_for_test`
    (one flat dict); the separate name and docstring exist so call sites
    read as "this is how a real platform registers" vs. "this is a test
    seam" — a distinction of intent, not of runtime behavior.
    """
    _PLUGINS[type_name] = plugin


def get_plugin(type_name: str) -> ConnectorPlugin | None:
    """Return the registered plugin for ``type_name``, or ``None``."""
    return _PLUGINS.get(type_name)


def unregister(type_name: str) -> None:
    """Drop the registration for ``type_name``, if any. Idempotent.

    Mission 23 Flight 2 Leg 2: the counterpart to :func:`register_for_test`
    for the dual-gated stub-registration lifespan hook
    (``interfaces/web/app.py``) — that hook registers "stub" at startup
    when the gate is open and must unregister it symmetrically at
    shutdown so a later lifespan cycle in the same process (e.g. across
    ``TestClient(app)`` cycles in the unit-test suite) never inherits a
    stale registration from a cycle where the gate was open.
    """
    _PLUGINS.pop(type_name, None)


def clear_for_test() -> None:
    """Drop every registration. Test fixtures only."""
    _PLUGINS.clear()
