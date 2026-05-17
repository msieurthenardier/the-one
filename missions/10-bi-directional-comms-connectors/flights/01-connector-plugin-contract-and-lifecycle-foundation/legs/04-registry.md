# Leg: registry

**Status**: landed
**Flight**: [Connector Plugin Contract and Lifecycle Foundation](../flight.md)

## Objective

Create `the_one/connectors/registry.py` with the `ConnectorRegistry` class and its module-level singleton, exposing `register`, `resolve`, `types` as the runtime dispatch API for connector plugins. Ship the `register_builtin_connectors()` production-discovery hook (empty in Flight 1) and the `register_for_test`/`clear_for_test` test seam. Update `__init__.py` to re-export `ConnectorRegistry`.

## Context

This is leg 4 of Flight 1 of Mission 10. Legs 1+2 landed the persistence floor; leg 3 landed the protocol contract. This leg lands the **runtime dispatch table** — the mechanism that says "given the string `'discord'`, hand me back a `ConnectorPlugin` instance I can call `connect(account, encryptor)` on."

### Pattern alignment with the existing LLM registry

The LLM provider registry at `the_one/llm/registry.py` is the closest precedent. It's module-level functions (no class), backed by a private `_providers: dict[str, type[LLMProvider]]`, with lazy-loading via `_try_load_builtin(name)`. For connectors, we follow the same shape with two adjustments:

1. **Class + module-level singleton, not module-level functions alone.** The class is a forward-compatibility escape hatch: no production code in flights 1-10 of this mission requires fresh `ConnectorRegistry()` instances, but the class exists so tests OR future flights that need parallel-state isolation can opt in without a future refactor. The module-level convenience functions (`register`, `resolve`, `types`) delegate to a module-level singleton so production callers don't thread a registry reference. **Honest note**: the only consumer of the class qua class in this leg is `test_fresh_registry_isolated_from_singleton`. If by flight 10 no other consumer has emerged, leg 8's `agents.md` writeup may recommend dropping the class in a future maintenance flight. We accept the small over-engineering cost now to honor the original mission/flight design instruction "ConnectorRegistry class (module-level singleton)."
2. **Eager registration, not lazy loading.** LLM providers lazy-load because each provider drags a heavy SDK import (`anthropic`, `openai`, etc.). Connector plugins in this mission are eager — Flight 8 will register `'discord'` at import time, Flight 9 the second connector. The MCP precedent (which doesn't lazy-load either) is the better reference. If a future connector ever needs lazy loading, we revisit then.

### `_PROVIDER_TYPE_MAP` parallel — the connector-type six-layer checklist

`agents.md` documents the provider-type six-layer coordination checklist (L251-267) — the `_PROVIDER_TYPE_MAP` at `agent/factory.py:122-129` is layer 2 of that checklist. The connector subsystem gets a parallel checklist in leg 8; this leg is the **registry layer** of that future checklist. The eventual checklist will read approximately:

1. Add the type to `the_one/db/_connector_types.py:CONNECTOR_TYPES`
2. Narrow the Pydantic `Literal[...]` on `ConnectorAccount.type` (and add the `assert get_args(...) == set(CONNECTOR_TYPES)` pin) — currently `type: str`, narrowed in Flight 8
3. **Register the plugin class in `register_builtin_connectors()` at `the_one/connectors/registry.py`** — *this leg ships the hook; flight 8 adds the call*
4. Add the v15 CHECK migration in `the_one/db/schema.py` (Flight 8 — was originally v14, renumbered after leg 2's v14 name-column addition)
5. API gating in `interfaces/web/api.py` (Flight 2 admin REST routes)
6. Frontend (Flight 2 admin UI)

### Design constraints from the flight that bind this leg

- **Class + module-level singleton** — see Pattern alignment above.
- **`register_builtin_connectors()` is the production discovery hook.** It is called once at module import. In this leg it's a no-op (`pass`) — Flight 8 changes the body to `register("discord", DiscordPlugin)`, Flight 9 adds the second registration. No env-var test-mode seam; mirrors the `mock` LLM provider pattern.
- **Test seam is explicit functions, not env-var conditional behavior.** `register_for_test(type_name, plugin_class)` overrides any production registration for the duration of a test; `clear_for_test()` resets the singleton to the post-`register_builtin_connectors()` baseline. Honors `agents.md` `container-test-entrypoints-reach-via-make` and the project's anti-env-var-test-seam stance.
- **Unknown type at `resolve()` raises `ConnectorRegistrationError`** with `type_name` and a reason string. Duplicate-register at `register()` raises the same exception with a different reason. Both failure modes are covered by the existing exception's two-failure-mode docstring in `connectors/errors.py` (leg 3 deliverable).
- **`resolve()` returns a plugin INSTANCE, not a class.** Plugins are stateless adapters per leg 3's design; `cls()` invocation per `resolve()` call is cheap. No instance cache (premature; if it becomes hot, leg 8 maintenance can add caching). The LLM registry does the same (`return _providers[name](**kwargs)` at `the_one/llm/registry.py:21`).

## Inputs

What exists before this leg runs:

- Legs 1+2+3 landed (uncommitted on the `flight/01-connector-plugin-contract-and-lifecycle-foundation` branch)
- `the_one/connectors/base.py` exports `ConnectorPlugin` (`@runtime_checkable` Protocol with 4 methods)
- `the_one/connectors/errors.py` exports `ConnectorRegistrationError(type_name: str, reason: str)`
- `the_one/connectors/__init__.py` re-exports the public surface from `base.py` and `errors.py`
- `tests/test_connectors.py` exists with 4 test classes and helper stubs (`_MinimalPlugin`, `_MinimalClient`)
- Patterns this leg mirrors:
  - `the_one/llm/registry.py` — module-level functions, private `_providers: dict[str, type[...]]`, error-on-unknown-type, the `register(name, cls)` shape
  - `the_one/agent/factory.py:_PROVIDER_TYPE_MAP` (lines 122-132) — the type-name → registry-name map plus the literal-pinning assert against `PROVIDER_TYPES`
  - `the_one/mcp/__init__.py` — re-export at `__init__.py` time, `noqa: E402` ordering, `__all__` declaration

## Outputs

What exists after this leg completes:

- New file `the_one/connectors/registry.py` with:
  - `ConnectorRegistry` class — instance methods `register(type_name, plugin_class)`, `resolve(type_name) -> ConnectorPlugin`, `types() -> list[str]`; private `_plugins: dict[str, type[ConnectorPlugin]]`
  - Module-level singleton `_registry = ConnectorRegistry()`
  - Module-level convenience functions `register(type_name, plugin_class)`, `resolve(type_name)`, `types()` delegating to `_registry`
  - Test seam: `register_for_test(type_name, plugin_class)` and `clear_for_test()`
  - Production discovery hook: `register_builtin_connectors()` — empty body in Flight 1, called once at module import time
- Updated `the_one/connectors/__init__.py` re-exporting `ConnectorRegistry` from `registry.py`
- New test class `TestConnectorRegistry` in `tests/test_connectors.py` covering the registry contract
- New pytest fixture `clean_registry` in `tests/test_connectors.py` for test-state isolation
- All tests pass; `make test`, `make lint` clean
- Leg status `landed`
- Flight log gains a `### Leg 04: registry` entry

## Acceptance Criteria

- [ ] `the_one/connectors/registry.py` exists
- [ ] `ConnectorRegistry` class is defined with:
    - `__init__(self) -> None` that initializes `self._plugins: dict[str, type[ConnectorPlugin]] = {}`
    - `register(self, type_name: str, plugin_class: type[ConnectorPlugin]) -> None` — raises `ConnectorRegistrationError` if `type_name` is already registered
    - `resolve(self, type_name: str) -> ConnectorPlugin` — raises `ConnectorRegistrationError` if `type_name` is unknown; returns a fresh plugin instance (no instance cache)
    - `types(self) -> list[str]` — returns a sorted list of registered type names
- [ ] Module-level singleton `_registry = ConnectorRegistry()` is created at module import
- [ ] Module-level functions `register(type_name, plugin_class)`, `resolve(type_name)`, `types()` delegate to `_registry`
- [ ] Test seam `register_for_test(type_name, plugin_class)` bypasses the collision check (used to swap test stubs between tests)
- [ ] Test seam `clear_for_test()` HARD-empties the singleton's `_plugins` dict; does NOT re-run `register_builtin_connectors()`
- [ ] Test seam `restore_to_baseline_for_test()` empties then re-runs `register_builtin_connectors()` — restores the production-shaped baseline (empty in Flight 1; with `discord` in Flight 8+)
- [ ] `resolve()` defensively `isinstance`-checks the produced plugin against `ConnectorPlugin`; a class that doesn't structurally satisfy raises `ConnectorRegistrationError`
- [ ] `register_builtin_connectors()` exists as a module-level function with an empty body (just `pass` plus a comment explaining the flight 8 / flight 9 expansion path)
- [ ] `register_builtin_connectors()` is called once at the bottom of `registry.py` so the singleton is in its baseline state at module import
- [ ] `the_one/connectors/__init__.py` re-exports `ConnectorRegistry` from `registry.py`; updates `__all__` accordingly
- [ ] `TestConnectorRegistry` class exists in `tests/test_connectors.py` with at minimum these tests:
    - `test_register_and_resolve_round_trip` — register a stub plugin class; `resolve(type_name)` returns a fresh instance that satisfies `ConnectorPlugin`
    - `test_resolve_unknown_type_raises_registration_error` — `resolve("nonexistent")` raises `ConnectorRegistrationError` with the type name in the message
    - `test_duplicate_register_raises_registration_error` — registering the same type twice raises `ConnectorRegistrationError` with reason mentioning "already registered"
    - `test_types_returns_sorted` — register multiple types, assert `types()` returns sorted
    - `test_register_for_test_bypasses_collision_check` — `register_for_test` can overwrite an existing registration without raising
    - `test_clear_for_test_resets_to_baseline` — register stubs, call `clear_for_test`, assert `types() == []`
    - `test_module_level_functions_delegate_to_singleton` — call module-level `register(...)`, assert `_registry.types()` reflects it
    - `test_fresh_registry_isolated_from_singleton` — instantiate `ConnectorRegistry()` directly, register a stub, assert the singleton's state is unchanged
    - `test_register_builtin_connectors_is_idempotent` — calling it multiple times after `clear_for_test` does not raise (currently a no-op; this test locks the contract so flight 8's expansion respects it)
- [ ] A `clean_registry` pytest fixture exists in `tests/test_connectors.py` that wraps each `TestConnectorRegistry` test with `clear_for_test()` calls before and after — applied via explicit fixture parameter (not autouse)
- [ ] Existing tests in `tests/test_connectors.py` from leg 3 still pass unchanged
- [ ] `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py` clean
- [ ] `docker exec the-one pytest -x --timeout 30` full suite clean
- [ ] `make lint` clean
- [ ] Leg status `landed`
- [ ] `registry` checkbox checked in flight.md's Legs section
- [ ] Flight log gains a `### Leg 04: registry` entry under `## Leg Progress`

## Verification Steps

1. **Module structure**:
   - `docker exec the-one ls the_one/connectors/` shows `__init__.py`, `base.py`, `errors.py`, `registry.py`

2. **Class + singleton + module functions**:
   - `docker exec the-one python -c "from the_one.connectors.registry import ConnectorRegistry, register, resolve, types, register_for_test, clear_for_test, register_builtin_connectors, _registry; assert isinstance(_registry, ConnectorRegistry); print('ok')"`

3. **Public re-export**:
   - `docker exec the-one python -c "from the_one.connectors import ConnectorRegistry as A; from the_one.connectors.registry import ConnectorRegistry as B; assert A is B; print('ok')"`

4. **Empty registry at import time**:
   - `docker exec the-one python -c "from the_one.connectors.registry import types; assert types() == []; print('ok')"`

5. **Registry contract**:
   - `TestConnectorRegistry` class is the canonical verifier — all 9 tests pass

6. **No regression**:
   - `docker exec the-one pytest -x --timeout 30` full suite green

## Implementation Guidance

### Step 1: Create `the_one/connectors/registry.py`

```python
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
                reason=f"instance does not satisfy ConnectorPlugin protocol",
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

    Flight 1 registers nothing (no real connector types yet — the empty
    ``CONNECTOR_TYPES`` tuple at :mod:`the_one.db._connector_types` reflects
    this).

    Future flights extend the body:

    - Flight 8 (Discord): ``register("discord", DiscordPlugin)``
    - Flight 9 (second connector): registers the second platform's plugin

    Per the connector-type six-layer checklist (landed in agents.md by
    leg 8), this is layer 3 of the coordination — the runtime-dispatch
    registration that pairs with the persistence-layer type literal and
    the API-layer gating.
    """
    # Intentionally empty in flight 1. Future flights extend.
    return


register_builtin_connectors()
```

### Step 2: Update `the_one/connectors/__init__.py`

Add the re-export for `ConnectorRegistry` from `registry.py`. Update the import block + the `__all__` list:

```python
from the_one.connectors.base import (
    ConnectorClient,
    ConnectorPlugin,
    DoctorReport,
    InboundEnvelope,
    OutboundTarget,
    SessionKey,
)
from the_one.connectors.errors import (
    ConnectorAuthRequired,
    ConnectorClientError,
    ConnectorConfigError,
    ConnectorConnectionError,
    ConnectorRateLimitError,
    ConnectorRegistrationError,
)
from the_one.connectors.registry import ConnectorRegistry

__all__ = [
    # Protocols + supporting types
    "ConnectorClient",
    "ConnectorPlugin",
    "DoctorReport",
    "InboundEnvelope",
    "OutboundTarget",
    "SessionKey",
    # Exception hierarchy
    "ConnectorAuthRequired",
    "ConnectorClientError",
    "ConnectorConfigError",
    "ConnectorConnectionError",
    "ConnectorRateLimitError",
    "ConnectorRegistrationError",
    # Registry (class — module-level functions stay at the_one.connectors.registry)
    "ConnectorRegistry",
]
```

**Do NOT re-export** the module-level `register`, `resolve`, `types`, `register_for_test`, `clear_for_test`, or `register_builtin_connectors` from `__init__.py`. Production callers that need them import from `the_one.connectors.registry` directly (matches the canonical-import discipline; convenience re-exports stay narrow). The class re-export is enough for the common test-isolation case.

### Step 3: Add `TestConnectorRegistry` to `tests/test_connectors.py`

Add the imports and the fixture + test class. Tests use the `clean_registry` fixture for explicit isolation.

```python
# Add to imports at the top of tests/test_connectors.py:
from the_one.connectors import ConnectorRegistry
from the_one.connectors.registry import (
    _registry,
    clear_for_test,
    register,
    register_builtin_connectors,
    register_for_test,
    resolve,
    restore_to_baseline_for_test,
    types,
)


# Add to the fixtures section (or near the top after existing imports):
@pytest.fixture
def clean_registry():
    """Reset the production registry to its production-shaped baseline before and after each test.

    Uses ``restore_to_baseline_for_test`` so the test starts where production
    starts (in flight 1: empty; in flight 8+: with discord pre-registered).
    Tests that want a TRULY empty registry post-fixture can call
    ``clear_for_test()`` after the fixture sets up.
    """
    restore_to_baseline_for_test()
    yield
    restore_to_baseline_for_test()


# Add this class after TestConnectorPackageExports:
class TestConnectorRegistry:
    """The connector type registry — class, module-level singleton, and test seams."""

    def test_register_and_resolve_round_trip(self, clean_registry) -> None:
        register("stub", _MinimalPlugin)
        plugin = resolve("stub")
        assert isinstance(plugin, ConnectorPlugin)
        assert isinstance(plugin, _MinimalPlugin)

    def test_resolve_unknown_type_raises_registration_error(self, clean_registry) -> None:
        with pytest.raises(ConnectorRegistrationError) as excinfo:
            resolve("nonexistent")
        assert "nonexistent" in str(excinfo.value)
        assert excinfo.value.type_name == "nonexistent"

    def test_duplicate_register_raises_registration_error(self, clean_registry) -> None:
        register("stub", _MinimalPlugin)
        with pytest.raises(ConnectorRegistrationError) as excinfo:
            register("stub", _MinimalPlugin)
        assert "already registered" in str(excinfo.value)
        assert excinfo.value.type_name == "stub"

    def test_types_returns_sorted(self, clean_registry) -> None:
        register("zebra", _MinimalPlugin)
        register("alpha", _MinimalPlugin)
        register("mango", _MinimalPlugin)
        assert types() == ["alpha", "mango", "zebra"]

    def test_register_for_test_bypasses_collision_check(self, clean_registry) -> None:
        register("stub", _MinimalPlugin)
        # register_for_test must NOT raise on duplicate.
        register_for_test("stub", _MinimalPlugin)
        assert types() == ["stub"]

    def test_clear_for_test_empties_registry(self, clean_registry) -> None:
        register("stub_a", _MinimalPlugin)
        register("stub_b", _MinimalPlugin)
        assert len(types()) == 2
        clear_for_test()
        # clear_for_test is a HARD clear — does not re-run register_builtin_connectors.
        # In flight 1 this happens to equal the baseline (empty); in flight 8+
        # they will differ.
        assert types() == []

    def test_restore_to_baseline_re_runs_builtin_discovery(self, clean_registry) -> None:
        register("stub", _MinimalPlugin)
        assert "stub" in types()
        restore_to_baseline_for_test()
        # Flight 1's baseline is empty (register_builtin_connectors is a no-op).
        # When flight 8 adds discord registration, this test will need to
        # update to assert "discord" in types() — that's the intended
        # behavior, not an oversight.
        assert types() == []

    def test_module_level_functions_delegate_to_singleton(self, clean_registry) -> None:
        register("stub", _MinimalPlugin)
        # Singleton state reflects the module-level call.
        assert "stub" in _registry.types()
        # Each resolve returns a FRESH instance — no instance cache. Locks
        # the "no instance cache" contract in the leg's design.
        via_module = resolve("stub")
        via_singleton = _registry.resolve("stub")
        assert type(via_module) is type(via_singleton)
        assert via_module is not via_singleton

    def test_fresh_registry_isolated_from_singleton(self, clean_registry) -> None:
        fresh = ConnectorRegistry()
        fresh.register("stub", _MinimalPlugin)
        # Singleton unchanged.
        assert types() == []
        # Fresh has the registration.
        assert fresh.types() == ["stub"]

    def test_register_builtin_connectors_is_idempotent(self, clean_registry) -> None:
        # Currently empty body — calling it repeatedly must not raise. Flight 8
        # changes the body to register("discord", DiscordPlugin); this test
        # locks the contract so flight 8's expansion uses idempotent registration
        # (e.g. via register_for_test inside the function, or a check-before-register
        # guard). Without idempotency, restore_to_baseline_for_test would raise
        # on the second call.
        register_builtin_connectors()
        register_builtin_connectors()
        assert types() == []

    def test_resolve_rejects_plugin_that_does_not_satisfy_protocol(
        self, clean_registry
    ) -> None:
        """`resolve` defensively isinstance-checks the produced plugin against
        ConnectorPlugin. A class that doesn't structurally satisfy the
        Protocol raises ConnectorRegistrationError rather than handing back
        a non-conforming instance that surfaces deep in the lifecycle pool."""

        class _NotAPlugin:
            """No connect, no disconnect, no doctor, no normalize_session_key."""
            pass

        register_for_test("broken", _NotAPlugin)  # bypass register's static-check
        with pytest.raises(ConnectorRegistrationError) as excinfo:
            resolve("broken")
        assert "does not satisfy" in str(excinfo.value).lower()
        assert excinfo.value.type_name == "broken"
```

### Step 4: Run tests + lint

```bash
docker exec the-one pytest -x --timeout 30 tests/test_connectors.py
docker exec the-one pytest -x --timeout 30
docker exec the-one bash -c "cd /workspace && make lint"
```

### Step 5: Update flight artifacts + leg status

- Append `### Leg 04: registry` entry under `## Leg Progress` in the flight log
- Check off `registry` in the flight artifact's Legs section
- Set this leg's status to `landed`
- Signal `[HANDOFF:review-needed]`; do NOT commit

## Edge Cases

- **`register_builtin_connectors` is called eagerly at module import.** If a future flight registers a plugin whose constructor has side effects (e.g. opens a file at import time), those side effects fire at every `import the_one.connectors.registry`. Current scope has no such plugin; Flight 8's `DiscordPlugin()` constructor must be inert (no network, no file I/O) — this is a contract for future flights.
- **`clear_for_test` re-runs `register_builtin_connectors`.** When Flight 8 adds the `'discord'` registration, `clear_for_test` will restore it. Tests that want a TRULY empty registry post-clear must call `_registry._plugins.clear()` directly after `clear_for_test()` — this is intentional (we want test isolation to mean "production baseline," not "empty"). Document in the docstring; the existing test `test_clear_for_test_resets_to_baseline` will need updating in Flight 8 to assert `types() == ["discord"]` instead of `types() == []`.
- **Module-level `_registry` access from tests.** The test `test_module_level_functions_delegate_to_singleton` imports `_registry` from `the_one.connectors.registry`. Verified ruff config (`pyproject.toml`'s selected rules `E/F/I/N/W`) does NOT flag underscore-prefix imports — no `noqa` needed.
- **`type[ConnectorPlugin]` in type hints.** Since `ConnectorPlugin` is a `Protocol`, `type[ConnectorPlugin]` is the canonical hint for "a class that structurally satisfies ConnectorPlugin." Python's typing accepts this even though Protocols can't be `isinstance`-checked at the type-system level without `runtime_checkable`. The `TYPE_CHECKING` guard avoids a runtime import.
- **`_MinimalPlugin` test helper.** This test class already lives in `tests/test_connectors.py` (leg 3 deliverable) at the module level (it's not nested in any test class). The registry tests use it directly. No new helper needed.
- **The `ConnectorRegistrationError` shape.** Constructor is `ConnectorRegistrationError(type_name=..., reason=...)`. The assertion `excinfo.value.type_name == "nonexistent"` works because the exception stores the kwargs as instance attributes (leg 3 deliverable). Verified against leg 3's `connectors/errors.py`.

## Files Affected

- `the_one/connectors/registry.py` (NEW) — class, singleton, module-level functions, test seams, builtin discovery hook
- `the_one/connectors/__init__.py` — re-export `ConnectorRegistry`; add to `__all__`
- `tests/test_connectors.py` — imports, `clean_registry` fixture, `TestConnectorRegistry` class (9 tests)
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` — check off `registry`
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight-log.md` — `### Leg 04: registry` entry under `## Leg Progress`
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/legs/04-registry.md` (this file) — status to `landed`

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] All listed tests passing
- [ ] `make lint` clean
- [ ] Flight log + flight artifact updated
- [ ] Leg status `landed`
- [ ] Signal `[HANDOFF:review-needed]`; do NOT commit

---

## Citation Audit

8 citations verified against current code at leg design time:

| Citation | Verification |
|---|---|
| `the_one/llm/registry.py:register_provider` (lines 10-11) | OK — read in full |
| `the_one/llm/registry.py:get_provider` (line 21 — `return _providers[name](**kwargs)`) | OK — confirmed instantiation pattern |
| `the_one/llm/registry.py:_try_load_builtin` (lazy-load shape, NOT mirrored here per leg design) | OK — read; deliberately not mirrored |
| `the_one/agent/factory.py:_PROVIDER_TYPE_MAP` (lines 122-132) — type-name dict + literal-pinning assert | OK — confirmed pattern |
| `agents.md` L251-267 — provider-type six-layer coordination checklist | OK — referenced as the parallel-checklist precedent |
| `the_one/connectors/base.py:ConnectorPlugin` (leg 3 deliverable) | OK — landed in leg 3 |
| `the_one/connectors/errors.py:ConnectorRegistrationError` (leg 3 deliverable, constructor `(type_name, reason)`) | OK — landed in leg 3, shape confirmed |
| `tests/test_connectors.py:_MinimalPlugin` (leg 3 helper, module-level) | OK — landed in leg 3 |
