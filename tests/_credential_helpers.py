"""Shared authenticated-client helper for the unit-test suite.

Mission 20 / Flight 1 / Leg 3 (``harness-credential-plumbing``) — DD10.

Plain helper FUNCTION (not a fixture), so it lives here rather than in
``tests/conftest.py`` — mirroring the project's existing split between
fixtures (must live in a ``conftest.py`` for pytest auto-discovery) and
the standalone helper modules that consume them.
Every one of the 34 unit-test
client fixtures (28 ``httpx.AsyncClient(transport=ASGITransport(...))``,
6 ``TestClient(...)``) imports ``auth_headers`` from here and passes it
as the ``headers=`` argument on client construction — a one-line-per-file
mechanical change, per the leg's binding acceptance criterion. The 28
local ``client`` fixtures themselves are NOT consolidated into one shared
fixture — that refactor is explicitly out of scope for this leg.
"""

from __future__ import annotations

from the_one.api_credential import get_credential


def auth_headers() -> dict[str, str]:
    """``Authorization`` header dict carrying the long-lived local-API
    credential (DD10).

    Deliberately uses ``get_credential()`` — the AMBIENT-``settings.
    data_dir``-reading, create-on-first-use entry point — rather than the
    path-taking writer the browser harness uses (see
    ``tests/browser/conftest.py::_write_credential``). That distinction
    matters only when the caller's app runs OUTSIDE this process (a
    subprocess with its own ``THE_ONE_DATA_DIR``, as every browser fixture
    spawns): there, this pytest process's ambient ``settings.data_dir`` is
    a DIFFERENT directory from the one the app subprocess reads, so
    ``get_credential()`` would write to the wrong place.

    None of that applies here. Every consumer of this helper builds its
    ASGI app (``httpx.ASGITransport``) or drives ``TestClient`` IN THIS
    SAME PROCESS — so whatever ``settings.data_dir`` currently is (the
    session-wide default from ``tests/conftest.py``, or a fixture's own
    ``monkeypatch.setattr(settings, "data_dir", tmp_path)`` applied
    earlier in the same fixture body) is exactly the directory
    ``FileCredentialSource.resolve()`` will also read, because it's the
    same ``settings`` singleton object in the same process. There is no
    cross-process isolation gap to bridge, so the "natural-looking call is
    wrong here" trap the browser harness has to route around does not
    apply to this helper.

    The gate (``CredentialGateMiddleware``) is not registered on any app in
    this leg — most of these 34 fixtures build a throwaway ``FastAPI()``
    wrapping only ``the_one.interfaces.web.api.router`` (no middleware at
    all, gate included, ever attached to it), so this header is inert for
    them even after `enforce-gate` registers the gate on the real app.
    Sending it anyway is still correct: it costs one cached credential
    read, and it means any of these fixtures that are later pointed at the
    real gated app already carry a valid credential with no further edit.
    """
    return {"Authorization": f"Bearer {get_credential().encode()}"}
