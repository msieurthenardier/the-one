"""One process-wide API app for the unit suite (Mission 34 F1 L01, squawks 0222/0234).

Building ``FastAPI()`` + ``include_router(router)`` costs about 55 ms (the router
has 120+ routes) and about fifty test files did it once per test. The app object
holds no per-test state: each test's database connection and encryptor are
injected with ``patch("the_one.interfaces.web.api.get_connection" /
"get_encryptor")``, which route handlers resolve at call time as module globals,
and the ``ASGITransport`` / ``AsyncClient`` are still built per test.

The rule: an API-client fixture calls ``shared_app()`` instead of building its
own app. A test file that sets ``app.state.*``, adds middleware, uses
``dependency_overrides``, runs a lifespan or patches the router keeps its own app
and is listed in ``tests/test_api_app_guard.py``'s allowlist with the reason.

Isolation is checked, not assumed: ``check_isolation()`` (run after every test by
the autouse ``_shared_app_isolation`` fixture in ``tests/conftest.py``, and a
no-op until the app has been built) compares the app with a snapshot taken when
it was built and fails the test that left it changed.
"""

from __future__ import annotations

import functools
from typing import Any

from fastapi import FastAPI


@functools.cache
def shared_app() -> FastAPI:
    """The shared app: built on first use (never at import), then reused."""
    from the_one.interfaces.web.api import router

    app = FastAPI()
    app.include_router(router)
    _SNAPSHOT[0] = _snapshot(app)
    return app


_SNAPSHOT: list[dict[str, Any] | None] = [None]


def _snapshot(app: FastAPI) -> dict[str, Any]:
    """The app state a test must never change.

    ``app.middleware_stack`` is built lazily by Starlette on the first request, so
    it is expected to change and is not part of the snapshot.
    """
    return {
        "state": dict(app.state._state),
        "dependency_overrides": dict(app.dependency_overrides),
        "user_middleware": list(app.user_middleware),
        "exception_handlers": set(app.exception_handlers),
        "routes": len(app.router.routes),
        "on_startup": len(app.router.on_startup),
        "on_shutdown": len(app.router.on_shutdown),
        "lifespan_context": app.router.lifespan_context,
    }


def check_isolation() -> None:
    """Raise ``AssertionError`` when the shared app no longer matches its build snapshot."""
    before = _SNAPSHOT[0]
    if before is None:
        return  # never built in this process
    after = _snapshot(shared_app())
    changed = sorted(k for k in before if before[k] != after[k])
    assert not changed, (
        f"the shared API app was changed by a test: {changed}. A test that sets app.state, "
        "adds middleware, uses dependency_overrides or patches the router must build its "
        "own app (and be listed in tests/test_api_app_guard.py's allowlist)."
    )
