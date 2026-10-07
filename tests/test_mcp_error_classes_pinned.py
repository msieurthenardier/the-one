"""Pin the MCP error classifier's class names against the backend (squawk 0129).

``App.mcpErrorMessage`` (``static/js/mcp-error.js``, DD19) picks a headline from the
leading exception class name in the ``"{Class}: {message}"`` text the ``test/connect``
envelope returns (``type(e).__name__`` in ``api.py``). A new or renamed backend class
would silently fall back to the generic headline. This test makes that loud: every
``MCPClientError`` subclass must be either recognised by the classifier or listed in
``DELIBERATELY_GENERIC`` with a reason, and the classifier may not name a class that
no longer exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import the_one.mcp.oauth.errors  # noqa: F401  (registers the MCPOAuth* subclasses)
import the_one.platform.sandbox.errors  # noqa: F401  (registers SandboxError)
from the_one.mcp.errors import MCPClientError

JS = (
    Path(__file__).resolve().parent.parent
    / "the_one"
    / "interfaces"
    / "web"
    / "static"
    / "js"
    / "mcp-error.js"
)

# Classes that reach the envelope (or could, via its catch-all) but keep the generic
# "Couldn't load this server's tools." headline on purpose.
DELIBERATELY_GENERIC = {
    "MCPClientError": "base class; never raised directly",
    "MCPAuthRequired": "sign-in control flow; the OAuth sign-in UI handles it, not a headline",
    "MCPToolNotFoundError": "tool-call path only; not raised by test/connect",
    "MCPArgumentError": "tool-call path only; not raised by test/connect",
    "MCPCallError": "tool-call path only; not raised by test/connect",
    "MCPRegistrationError": "source registration path; not raised by test/connect",
    "MCPOAuthError": "OAuth base class; only reaches the envelope via the catch-all",
    "MCPOAuthDiscoveryError": "reaches the envelope only via the catch-all; generic is correct",
    "MCPOAuthRegistrationError": "reaches the envelope only via the catch-all; generic is correct",
    "MCPOAuthRefreshFailed": "reaches the envelope only via the catch-all; generic is correct",
}


def _backend_classes() -> set[str]:
    found: set[str] = {MCPClientError.__name__}
    stack = [MCPClientError]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub.__name__ not in found:
                found.add(sub.__name__)
                stack.append(sub)
    return found


def _recognised_classes() -> set[str]:
    src = JS.read_text(encoding="utf-8")
    names = set(re.findall(r"\bcls === '([A-Za-z_][A-Za-z0-9_]*)'", src))
    assert len(names) >= 4, f"classifier regex matched too little ({names}); fix the pin"
    return names


def test_every_backend_error_class_is_classified_or_deliberately_generic():
    backend = _backend_classes()
    recognised = _recognised_classes()
    unaccounted = backend - recognised - set(DELIBERATELY_GENERIC)
    assert not unaccounted, (
        f"backend error class(es) {sorted(unaccounted)} are neither classified in "
        "mcp-error.js nor listed in DELIBERATELY_GENERIC; classify them or mark generic"
    )


def test_classifier_names_only_existing_backend_classes():
    stale = _recognised_classes() - _backend_classes()
    assert not stale, f"mcp-error.js recognises class(es) no longer in the backend: {sorted(stale)}"


def test_generic_set_has_no_stale_or_overlapping_entries():
    backend = _backend_classes()
    generic = set(DELIBERATELY_GENERIC)
    assert not generic - backend, f"stale generic entries: {sorted(generic - backend)}"
    assert not generic & _recognised_classes(), "class is both recognised and marked generic"
