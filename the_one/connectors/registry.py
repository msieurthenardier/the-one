"""Connector type registry — runtime dispatch from type name to plugin instance.

Mirrors :mod:`the_one.llm.registry`'s shape (module-level dispatch table with
collision-check on register, raise-on-unknown at lookup time), but wraps the
table in a :class:`ConnectorRegistry` class so the connector-subsystem boundary
is explicit and tests can isolate state via a fresh instance if needed.

The module-level singleton ``_registry`` is what the production code touches;
the convenience functions (:func:`register`, :func:`resolve`, :func:`types`)
delegate to it.

Future connector types are added via :func:`register_builtin_connectors` —
flight 8 (Discord) and flight 9 (second connector) extend its body. The
function is called once at module import time so the singleton is in its
baseline state from the first dispatch.

Per the test convention in this codebase, the test seam is explicit:
:func:`register_for_test` and :func:`clear_for_test`. No env-var runtime
branching; no test-mode shortcuts in production code paths.
"""

from __future__ import annotations

from the_one.connectors.base import ConnectorPlugin
from the_one.connectors.errors import ConnectorRegistrationError


class ConnectorRegistry:
    """Maps connector type names to plugin classes.

    Plugins are stateless per the leg-3 design; ``resolve`` instantiates a
    fresh plugin on every call (cheap). No instance cache — premature
    optimization until profiling demonstrates the cost.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, type[ConnectorPlugin]] = {}

    def register(
        self,
        type_name: str,
        plugin_class: type[ConnectorPlugin],
    ) -> None:
        """Register a connector plugin class under ``type_name``.

        Raises :class:`ConnectorRegistrationError` if ``type_name`` is
        already registered. Test code that needs to swap plugins between
        tests should use :func:`register_for_test` (module-level) instead.
        """
        if type_name in self._plugins:
            existing_name = self._plugins[type_name].__name__
            raise ConnectorRegistrationError(
                type_name=type_name,
                reason=f"already registered as {existing_name!r}",
            )
        self._plugins[type_name] = plugin_class

    def resolve(self, type_name: str) -> ConnectorPlugin:
        """Resolve a plugin instance for ``type_name``.

        Raises :class:`ConnectorRegistrationError` if ``type_name`` is
        unknown or if the registered class produces an instance that does
        NOT structurally satisfy :class:`ConnectorPlugin`. The instance
        check guards against a silent class of bug where the protocol is
        widened later (flights 4/6/7) and a registered class no longer
        conforms — without this check the non-conforming plugin would
        ride through ``resolve`` and surface deep in the lifecycle pool.
        Returns a fresh plugin instance (no cache).
        """
        cls = self._plugins.get(type_name)
        if cls is None:
            raise ConnectorRegistrationError(
                type_name=type_name,
                reason="not registered",
            )
        plugin = cls()
        if not isinstance(plugin, ConnectorPlugin):
            raise ConnectorRegistrationError(
                type_name=type_name,
                reason="instance does not satisfy ConnectorPlugin protocol",
            )
        return plugin

    def types(self) -> list[str]:
        """Return a sorted list of registered type names."""
        return sorted(self._plugins.keys())


# Module-level singleton. Production code touches this via the convenience
# functions below.
_registry = ConnectorRegistry()


def register(type_name: str, plugin_class: type[ConnectorPlugin]) -> None:
    """Register ``plugin_class`` under ``type_name`` in the production singleton."""
    _registry.register(type_name, plugin_class)


def resolve(type_name: str) -> ConnectorPlugin:
    """Resolve a plugin instance from the production singleton."""
    return _registry.resolve(type_name)


def types() -> list[str]:
    """Return the sorted list of types registered in the production singleton."""
    return _registry.types()


def register_for_test(
    type_name: str,
    plugin_class: type[ConnectorPlugin],
) -> None:
    """Test seam: register or overwrite ``type_name`` without the collision check.

    Use from tests that need to swap stub plugins between cases. Pair with
    :func:`clear_for_test` to reset to baseline at test teardown.
    """
    _registry._plugins[type_name] = plugin_class


def clear_for_test() -> None:
    """Test seam: empty the singleton's `_plugins` dict.

    Hard-clear. Does NOT re-run :func:`register_builtin_connectors`. Tests
    that want the production-shaped baseline (empty in flight 1; ``{"discord": ...}``
    in flight 8+) should use :func:`restore_to_baseline_for_test` instead.

    Splitting "empty" from "production baseline" lets a test mean exactly
    one of the two without leaking implementation knowledge of which
    builtins exist at this flight's checkpoint.
    """
    _registry._plugins.clear()


def restore_to_baseline_for_test() -> None:
    """Test seam: reset the singleton to the post-:func:`register_builtin_connectors` baseline.

    Empties the registry then re-runs the builtin discovery hook so the
    state matches what production code sees at module import time. For
    flight 1 the baseline is empty (no builtins yet); flight 8+ this
    restores ``"discord"`` (and Flight 9's second connector).
    """
    _registry._plugins.clear()
    register_builtin_connectors()


def register_builtin_connectors() -> None:
    """Production discovery hook — called once at module import time.

    Registers ``"discord"`` → :class:`DiscordPlugin` (M10 F8 L2). The
    ``"stub"`` test-only type is NOT registered here — tests register it
    explicitly via :func:`register_for_test` per the production-purity
    convention codified in ``_stub.py:18-19`` (and mirrored by
    ``_connector_types.py``'s docstring).

    Future flights extend the body — Flight 9 (second connector) registers
    the second platform's plugin.

    Per the connector-type 6-layer checklist (``agents.md`` §"Connector
    type extension checklist"), this is layer 3 of the coordination — the
    runtime-dispatch registration that pairs with the persistence-layer
    type literal (layer 1), the ``CONNECTOR_TYPES`` tuple (layer 2), and
    the SQL CHECK constraint (layer 4).
    """
    # Function-local import per the
    # ``function-local-import-to-break-load-cycle`` convention codified in
    # ``agents.md``. ``_discord`` may eventually need to reach back into
    # ``registry`` (e.g. for the F7 CommandHandler / F8 L9 surface);
    # deferring the import until ``register_builtin_connectors`` is
    # actually invoked keeps the module-import graph acyclic.
    from the_one.connectors._discord import DiscordPlugin

    # Idempotency: the second-call contract pinned by
    # ``test_register_builtin_connectors_is_idempotent`` predates F8 L2.
    # Re-running the hook must not raise (``restore_to_baseline_for_test``
    # calls ``_registry._plugins.clear()`` then ``register_builtin_connectors``
    # back-to-back; that path works as long as this function is happy to
    # be called from a clean OR a discord-present registry). The skip-if-
    # already-registered guard preserves the F1 contract while honoring
    # the F1 collision-check on the first call.
    if "discord" not in _registry._plugins:
        register("discord", DiscordPlugin)


register_builtin_connectors()
