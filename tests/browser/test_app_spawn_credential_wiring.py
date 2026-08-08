"""Acceptance test for the Playwright-context credential wiring.

Mission 20 / Flight 1 / Leg 3 (``harness-credential-plumbing``) — binding
acceptance criterion under "Browser app-spawn": "The Playwright browser
context carries the credential via ``extra_http_headers``, sourced from
the same app instance the test targets... A test must assert the
context's credential matches the app it is driving."

Every browser app-spawn fixture registers its credential in
``browser._credential_registry``, keyed by ``base_url``; the shared
``page`` fixture (``conftest.py``) resolves it lazily, at ``page.goto()``
time, from whichever ``base_url`` is actually being navigated to (see
that fixture's docstring for why this can't be decided at
context-creation time — a single ``page`` fixture is paired with
different app fixtures across the suite). Getting this wrong is silent:
attaching one app's credential to a request against a DIFFERENT app's
instance never fails loudly, since the gate is not registered yet (this
leg's whole point). This test drives TWO distinct app instances with the
SAME ``page``/context and asserts the outgoing ``Authorization`` header
observed on each app's document request matches THAT app's own
credential — never the other one's.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from browser._credential_registry import credential_for
from browser._credential_registry import unregister as _unregister_credential
from browser.conftest import _spawn_app, _teardown_proc
from playwright.sync_api import Page


@pytest.fixture
def two_apps(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, str]]:
    """Two independently spawned apps for this test's dual-instance
    assertion. NOT the ``app_clean`` + ``app_with_data_dir`` fixtures
    together — both of those derive their ``data_dir`` from the SAME
    per-test ``tmp_path``
    (``tmp_path / "the-one-data"``), so requesting both in one test
    collides on directory creation. Using ``tmp_path_factory`` to mint two
    independent roots sidesteps that rather than changing either fixture's
    long-standing ``tmp_path``-relative layout for every other consumer.
    """
    tmp_path_a = tmp_path_factory.mktemp("app-a")
    tmp_path_b = tmp_path_factory.mktemp("app-b")
    base_url_a, proc_a, _cred_a, _dir_a = _spawn_app(tmp_path_a)
    base_url_b, proc_b, _cred_b, _dir_b = _spawn_app(tmp_path_b)
    try:
        yield base_url_a, base_url_b
    finally:
        _unregister_credential(base_url_a)
        _unregister_credential(base_url_b)
        _teardown_proc(proc_a)
        _teardown_proc(proc_b)


@pytest.mark.browser
def test_page_authorization_header_matches_the_app_navigated_to(
    two_apps: tuple[str, str],
    page: Page,
) -> None:
    base_url_a, other_base_url = two_apps

    # Two independently spawned apps must never share a credential — this
    # is what makes the assertions below meaningful. If `_spawn_app`
    # somehow generated the same value twice (or the registry lost an
    # entry), a broken header-matching implementation could pass by
    # accident; this guards against that.
    credential_a = credential_for(base_url_a)
    credential_b = credential_for(other_base_url)
    assert credential_a is not None
    assert credential_b is not None
    assert credential_a.encode() != credential_b.encode()

    captured: dict[str, str] = {}

    def _capture(request) -> None:
        auth = request.headers.get("authorization")
        if auth is not None:
            captured[request.url] = auth

    page.on("request", _capture)

    # Navigate to app A (base_url_a) first and check the document request
    # carried exactly base_url_a's credential.
    page.goto(base_url_a)
    expected_a = f"Bearer {credential_a.encode()}"
    matched_a = [v for u, v in captured.items() if u.rstrip("/") == base_url_a.rstrip("/")]
    assert matched_a, f"no captured request matched {base_url_a!r}; captured={captured!r}"
    assert matched_a[-1] == expected_a, (
        f"page's Authorization header after navigating to base_url_a ({base_url_a}) "
        f"was {matched_a[-1]!r}, expected {expected_a!r} — the context is carrying "
        "the wrong app's credential"
    )

    # Now navigate to app B (the second spawned instance) with the SAME
    # page/context and check the header switched to app B's own
    # credential — not a stale copy of app A's.
    captured.clear()
    page.goto(other_base_url)
    expected_b = f"Bearer {credential_b.encode()}"
    matched_b = [v for u, v in captured.items() if u.rstrip("/") == other_base_url.rstrip("/")]
    assert matched_b, f"no captured request matched {other_base_url!r}; captured={captured!r}"
    assert matched_b[-1] == expected_b, (
        f"page's Authorization header after navigating to the second app "
        f"({other_base_url}) was {matched_b[-1]!r}, expected {expected_b!r} — "
        "attaching the first app's credential to the second app is exactly "
        "the silent bug this leg's acceptance criterion exists to catch"
    )
