"""Per-process registry mapping a spawned app's ``base_url`` to its
long-lived local-API credential.

Mission 20 / Flight 1 / Leg 3 (``harness-credential-plumbing``) — DD10.

Split into its own module rather than folded into ``conftest.py`` to avoid
a circular import: ``conftest.py`` already imports ``seeders.py``
(``from browser.seeders import ...``), and ``seeders.py`` needs this
registry to resolve the credential for the ``base_url`` it already
receives — without touching any of the 252 seeder call sites or widening
any seeder's signature (leg acceptance criteria). ``conftest.py``'s
``page`` fixture also reads this registry, to attach the correct
credential's ``Authorization`` header for whichever app a test navigates
to (see that fixture's docstring for why this can't be decided at
context-creation time).

Scoped by the app-spawn lifecycle, not a bare persistent global (leg
Implementation Guidance #3): every spawn path in ``conftest.py`` calls
``register()`` right after writing its credential and ``unregister()`` in
the same fixture's teardown — mirroring ``the_one/api_credential.py``'s
``_cache``/``_sources`` isolation discipline (leg Inputs). A stale entry
cannot leak into a later test's assertions because each spawned app's port
(and therefore its ``base_url``) is freshly OS-allocated per fixture
invocation; ``unregister()`` at teardown keeps the dict from growing
unboundedly across a long browser-suite run.
"""

from __future__ import annotations

from the_one.api_credential import LocalApiCredential

_registry: dict[str, LocalApiCredential] = {}


def register(base_url: str, credential: LocalApiCredential) -> None:
    """Record *credential* as the credential for the app at *base_url*."""
    _registry[base_url] = credential


def unregister(base_url: str) -> None:
    """Drop *base_url*'s entry, if any. Safe to call unconditionally at
    fixture teardown (no-op if never registered, e.g. spawn failed)."""
    _registry.pop(base_url, None)


def auth_headers_for(base_url: str) -> dict[str, str]:
    """``Authorization`` header dict for whichever app is registered at
    *base_url*, or ``{}`` if none is registered.

    Mission 20 / Flight 1 / Leg 4 (``enforce-gate``) — shared convenience
    so the ~50 inline ``httpx`` call sites across ``tests/browser/*.py``
    (test bodies making direct requests to the app under test, as opposed
    to the seeders/fixtures in this package which already resolve their
    own headers) don't each duplicate the ``credential_for(...)`` lookup
    and ``None``-guard. Mirrors ``conftest.py``'s private
    ``_auth_headers_for`` / ``seeders.py``'s private ``_auth_headers``
    (both pre-existing, both module-local) — this one is public because
    it is meant to be imported directly by test modules outside this
    package's own fixture/seeder machinery.
    """
    credential = credential_for(base_url)
    if credential is None:
        return {}
    return {"Authorization": f"Bearer {credential.encode()}"}


def credential_for(base_url: str) -> LocalApiCredential | None:
    """Return the credential registered for *base_url*.

    *base_url* may carry a path/query/fragment beyond the bare origin — a
    document navigation like ``f"{base_url}#chat/sessions/{id}"`` — so a
    registered origin is matched as a prefix, not just by exact equality.
    Returns ``None`` if no registered app matches, which callers should
    treat as "attach no credential header" rather than an error (e.g. a
    navigation to ``about:blank`` or to a URL this registry never saw).
    """
    direct = _registry.get(base_url)
    if direct is not None:
        return direct
    for registered_base, credential in _registry.items():
        if base_url == registered_base or base_url.startswith(
            (f"{registered_base}/", f"{registered_base}#", f"{registered_base}?")
        ):
            return credential
    return None
