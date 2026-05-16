"""Unit tests for ``the_one.mcp.transports.streamable_http``.

Coverage: ``build_request_headers`` — pin the OAuth-managed-secret-key
filter so future expansions of ``OAUTH_MANAGED_SECRET_KEYS`` (storage.py)
are mechanically caught here.

F6.5 L4 expanded the filter from 4 keys to 6 (added ``token_type`` and
``scope``); without coverage the regression that motivated the fix
(stale ``token_type`` / ``scope`` leaking into the editor's Custom
Headers kv-table) could re-emerge silently. The test below iterates the
``OAUTH_MANAGED_SECRET_KEYS`` frozenset directly so any future addition
is asserted against without test edits.
"""

from __future__ import annotations

import pytest

from the_one.db.models import MCPSource
from the_one.mcp.oauth.storage import OAUTH_MANAGED_SECRET_KEYS
from the_one.mcp.transports.streamable_http import build_request_headers

# Per-key sample values typed correctly per F6.5 L4's typing fix:
# token strings stay strings, ``token_expires_at`` is a float,
# ``dcr_credentials`` is a dict. The filter is keyed on names, not types,
# so any value would prove the assertion — but the values are realistic
# so the test doubles as documentation of the secret shapes.
_SECRET_VALUE_BY_KEY: dict[str, object] = {
    "access_token": "ya29.test-access",
    "refresh_token": "1//0g.test-refresh",
    "token_expires_at": 1234567890.0,
    "token_type": "Bearer",
    "scope": "openid profile",
    "dcr_credentials": {"client_id": "test", "issuer": "https://example.com"},
}


@pytest.mark.parametrize("key", sorted(OAUTH_MANAGED_SECRET_KEYS))
def test_build_request_headers_filters_oauth_managed_keys(key: str) -> None:
    """Each key in ``OAUTH_MANAGED_SECRET_KEYS`` MUST be filtered out of
    ``build_request_headers``'s output.

    Mechanically iterates ``OAUTH_MANAGED_SECRET_KEYS`` (does NOT hardcode
    the list) so future expansions of the frozenset are caught here.
    """
    # Sanity — ensure the parametrize sample dict has not drifted from
    # the storage module's frozenset. If a new key lands without a value
    # here, the test fails loudly rather than silently skipping.
    assert key in _SECRET_VALUE_BY_KEY, (
        f"OAUTH_MANAGED_SECRET_KEYS contains {key!r} but the test's "
        f"_SECRET_VALUE_BY_KEY mapping has no entry — add one."
    )

    source = MCPSource(
        id="src-1",
        name="t",
        type="streamable-http",
        config={"url": "https://example.com/mcp"},
        secrets={key: _SECRET_VALUE_BY_KEY[key]},
    )
    headers = build_request_headers(source)
    assert key not in headers


def test_build_request_headers_preserves_operator_supplied_headers() -> None:
    """Negative control — non-OAuth-managed secrets DO pass through.

    Ensures the filter is tightly scoped to the OAuth-managed names; an
    operator-supplied custom header (e.g. ``X-Custom-Token``) still flows
    through the merge.
    """
    source = MCPSource(
        id="src-2",
        name="t",
        type="streamable-http",
        config={"url": "https://example.com/mcp", "headers": {"X-Plain": "p"}},
        secrets={"X-Custom-Token": "operator-supplied"},
    )
    headers = build_request_headers(source)
    assert headers.get("X-Plain") == "p"
    assert headers.get("X-Custom-Token") == "operator-supplied"
