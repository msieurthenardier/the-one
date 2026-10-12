"""Shared helpers for the provider browser tests (sortie 02).

``block_claude_ai`` (shared by ``test_flow_provider_library.py`` and
``test_flow_provider_plan_signin.py``): the anthropic-plan sign-in opens a
claude.ai consent popup, and no browser test may let a request leave for it.
"""

from __future__ import annotations

from playwright.sync_api import Page


def block_claude_ai(page: Page) -> None:
    """Abort any request to claude.ai (the consent popup navigation).

    Context-level so popup windows are covered too.
    """
    page.context.route("https://claude.ai/**", lambda route: route.abort())


def studio_dirty(page: Page) -> bool:
    """The studio area's shared dirty mirror (``_dirty``)."""
    return bool(
        page.evaluate(
            "() => { const a = (App.areas || []).find(x => x.id === 'studio');"
            " return !!(a && a._dirty); }"
        )
    )
