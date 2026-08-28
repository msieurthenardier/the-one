"""Cross-site verification that `GET /api/oauth/callback` reaches the
handler without a credential — Mission 22 / Flight 01 / Leg 03
(`oauth-callback-reachability`).

No external IdP is configured in the operator's environment (recorded in
the flight log). This test is the live verification of flight Design
Decision Q3 in its stead: `localhost` and `127.0.0.1` are different
sites, so a top-level navigation from one to the other is a genuine
cross-site navigation — exactly the shape of an IdP's redirect back to
the app — on which the `SameSite=Strict` session cookie is withheld by
spec. `app_clean` spawns the app on `http://127.0.0.1:<port>` only, so
this test signs in on `127.0.0.1` and initiates the cross-site hop from a
`localhost` document (the mirror image of the flight artifact's
"sign in on localhost, navigate to 127.0.0.1" phrasing — recorded as a
Deviation in the flight log; the proof is identical either direction).

Deliberately does NOT use the shared `page` fixture or
`credentialed_context()` (`conftest.py`): both call
`context.set_extra_http_headers({"Authorization": ...})`, which is
context-wide in Playwright — every page opened in that context, including
a "raw" one meant to be unauthenticated, would carry the header and
authenticate through it, making the cross-site assertion below pass for
the wrong reason. Instead this test builds its own `browser.new_context()`
with no extra headers, authenticates only `ctx.request` calls (session
handoff, seam seed) via a per-call header, and drives a `raw` page that
carries no credential of its own — only whatever cookie the browser
itself decides to attach per its same-site/cross-site rules.
"""

from __future__ import annotations

import pytest
from browser._credential_registry import credential_for
from browser.conftest import _establish_session_cookie
from playwright.sync_api import Browser


@pytest.mark.browser
def test_oauth_callback_reachable_cross_site_with_no_cookie(
    app_clean: str, browser: Browser
) -> None:
    """AC6: seed a pending flow, then reach `/api/oauth/callback` from a
    genuinely cross-site top-level navigation with no `Authorization`
    header and (per the `SameSite=Strict` cookie) no session cookie
    either — and confirm the callback still completes. Two controls
    bracket the proof: a same-site positive control (the cookie exists
    and *is* sent same-site) and a cross-site negative control (a
    DIFFERENT gated route, same cross-site shape, still refused) — so a
    pass here is attributable to the callback's specific exemption, not
    to the gate being generally inert in this harness.
    """
    credential = credential_for(app_clean)
    assert credential is not None, (
        f"no credential registered for {app_clean!r} — app_clean should have registered "
        "one via _spawn_app"
    )

    # A dedicated context, no extra headers — see module docstring.
    ctx = browser.new_context()
    try:
        # Establishes the session cookie via the real handoff exchange
        # (mint + follow-redirect), landing it in ctx's cookie jar —
        # shared between ctx.request and every page ctx opens.
        _establish_session_cookie(ctx, app_clean, credential)

        # Seed a pending flow through the dev-mode-gated test seam. Only
        # in-process `_state.register` can create one; this subprocess app
        # is a separate process, so it goes through the HTTP seam instead
        # — a per-call Authorization header, never context-wide.
        state = "S-cross-site-1"
        seed_resp = ctx.request.post(
            f"{app_clean}/api/_test/oauth/pending",
            headers={"Authorization": f"Bearer {credential.encode()}"},
            data={
                "state": state,
                "source_id": "src-cross-site-1",
                "chat_session_id": "cs-cross-site-1",
            },
        )
        assert seed_resp.ok, f"seam seed failed: {seed_resp.status} {seed_resp.text()}"

        raw = ctx.new_page()

        # ── Same-site positive control ──────────────────────────────
        # The session cookie exists in ctx's jar and IS attached on a
        # same-site (127.0.0.1 -> 127.0.0.1) navigation.
        resp = raw.goto(f"{app_clean}/api/info")
        assert resp is not None
        assert resp.status == 200

        # `localhost` may resolve to `::1` first on some hosts (Happy
        # Eyeballs falls back to IPv4 on loopback) — irrelevant here, the
        # test only relies on `localhost` being a *different site* from
        # `127.0.0.1`, which holds either way.
        localhost_url = app_clean.replace("127.0.0.1", "localhost")

        # ── Cross-site callback ─────────────────────────────────────
        # Load a localhost document first so the next navigation's
        # initiator is a different site, then top-level-navigate to the
        # 127.0.0.1 callback URL — withholding the Strict cookie exactly
        # as after an IdP redirect.
        raw.goto(f"{localhost_url}/api/live")
        callback_url = f"{app_clean}/api/oauth/callback?code=c&state={state}"
        # The callback page auto-closes ~1.2s after paint on success —
        # assert on the navigation response body directly rather than the
        # page's content() after the fact, in case the tab has already
        # started to close.
        with raw.expect_navigation() as nav_info:
            raw.evaluate("(url) => { window.location.assign(url); }", callback_url)
        nav_response = nav_info.value
        assert nav_response is not None
        assert "Login successful" in nav_response.text()

        # ── Cross-site negative control ─────────────────────────────
        # Re-navigate to a fresh localhost document (the callback tab may
        # already be mid-auto-close) so the following hop is again a
        # genuine cross-site navigation, then confirm a DIFFERENT gated
        # route is refused cross-site — proving (4) really crossed the
        # gate unauthenticated, not that the gate is inert in this
        # harness.
        raw.goto(f"{localhost_url}/api/live")
        with raw.expect_navigation() as neg_nav_info:
            raw.evaluate("(url) => { window.location.assign(url); }", f"{app_clean}/api/info")
        neg_response = neg_nav_info.value
        assert neg_response is not None
        assert neg_response.status == 401
    finally:
        ctx.close()
