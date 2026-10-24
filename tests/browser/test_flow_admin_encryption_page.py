"""Settings > Encryption and Prompts on the library (M31 F4 L08b).

Encryption: the rotate flow's result is one status that never loses a staged warning
to an earlier success timer (DD8-10), a non-JSON error body reads as ``fetchJson``'s
"Server error N ..." (DD8-11), focus stays on the button through success, staged and
error (DD8-12), the facts (last rotated, items with stored secrets) come from
``GET /api/encryption/status`` (B12) and the labels are sentence case (A4, A5).
Prompts: the layer titles are ``h2`` and the platform block titles ``h3`` (B11), the
texts are trimmed code blocks (A1) with space between layers (A2), the variants are
sub-headings, not eyebrows (A3), and an HTTP error shows an error status.

Every ``/api/encryption/*`` response is mocked through ``page.route``, so no real key
rotation happens.
"""

from __future__ import annotations

import json
import re

import pytest
from browser import _nav
from playwright.sync_api import Page, expect

_STATUS_NEVER = {"last_rotated_at": None, "credential_count": 3, "key_file_pending": False}
_ISO = "2026-10-20T12:00:00+00:00"


def _json(route, body, status=200):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


def _mock_status(page: Page, *bodies, status=200):
    """Serve the given status bodies in order (the last repeats)."""
    seen = {"n": 0}

    def handler(route):
        i = min(seen["n"], len(bodies) - 1)
        seen["n"] += 1
        _json(route, bodies[i], status)

    page.route("**/api/encryption/status", handler)
    return seen


def _mock_rotate(page: Page, *responses):
    """Serve (status, body-or-text) tuples in order (the last repeats)."""
    seen = {"n": 0}

    def handler(route):
        i = min(seen["n"], len(responses) - 1)
        seen["n"] += 1
        status, body = responses[i]
        if isinstance(body, dict):
            _json(route, body, status)
        else:
            route.fulfill(status=status, content_type="text/html", body=body)

    page.route("**/api/encryption/rotate", handler)
    return seen


def _btn(page: Page):
    return page.locator('[data-testid="rotate-key-btn"]')


def _result(page: Page):
    return page.locator('[data-testid="rotate-result"]')


def _rotate(page: Page) -> None:
    btn = _btn(page)
    expect(btn).to_be_visible(timeout=8000)
    btn.click()
    expect(btn).to_have_text("Rotate key?")
    btn.click()


def _open(page: Page, base: str) -> None:
    _nav.goto(page, base, "settings/encryption")
    expect(_btn(page)).to_be_visible(timeout=8000)


PROMOTED = (200, {"status": "ok", "key_file": "promoted"})
STAGED = (200, {"status": "ok", "key_file": "staged"})


@pytest.mark.browser
def test_staged_warning_survives_an_earlier_success_timer(app_clean: str, page: Page) -> None:
    """DD8-10: a second rotation within 3 s ends staged; the first one's 'Key rotated.'
    timer must not wipe the warning (one timer handle, cleared at the start of every
    attempt)."""
    _mock_status(page, _STATUS_NEVER)
    _mock_rotate(page, PROMOTED, STAGED)
    _open(page, app_clean)
    _rotate(page)
    expect(page.get_by_text("Key rotated.")).to_be_visible(timeout=5000)
    _rotate(page)
    warning = page.get_by_text("key file could not be updated")
    expect(warning).to_be_visible(timeout=5000)
    expect(_result(page)).to_have_attribute("data-state", "warning")
    # Longer than the 3 s success timer would have fired after the first rotation.
    page.wait_for_timeout(3500)  # absence check: the timer must NOT have wiped the warning
    expect(warning).to_be_visible()
    expect(_result(page)).to_have_attribute("data-state", "warning")


@pytest.mark.browser
def test_success_clears_after_three_seconds_and_staged_does_not(app_clean: str, page: Page) -> None:
    _mock_status(page, _STATUS_NEVER)
    _mock_rotate(page, PROMOTED)
    _open(page, app_clean)
    _rotate(page)
    expect(_result(page)).to_have_attribute("data-state", "success", timeout=5000)
    expect(_result(page)).to_contain_text("Key rotated.")
    expect(_result(page)).to_have_text("", timeout=6000)
    assert _result(page).get_attribute("data-state") is None


@pytest.mark.browser
def test_an_error_stays_until_the_next_attempt(app_clean: str, page: Page) -> None:
    _mock_status(page, _STATUS_NEVER)
    _mock_rotate(page, (500, {"detail": "disk is read-only"}), PROMOTED)
    _open(page, app_clean)
    _rotate(page)
    expect(_result(page)).to_have_attribute("data-state", "danger", timeout=5000)
    expect(_result(page)).to_contain_text("disk is read-only")
    page.wait_for_timeout(4500)  # absence check: the old 4 s timer must not clear it
    expect(_result(page)).to_contain_text("disk is read-only")
    _rotate(page)
    expect(_result(page)).to_have_attribute("data-state", "success", timeout=5000)
    expect(_result(page)).not_to_contain_text("disk is read-only")


@pytest.mark.browser
def test_a_non_json_error_body_reads_as_a_server_error(app_clean: str, page: Page) -> None:
    """DD8-11: an HTML 500 body used to show 'Error: Unexpected token ...'."""
    _mock_status(page, _STATUS_NEVER)
    _mock_rotate(page, (500, "<html><body>Internal Server Error</body></html>"))
    _open(page, app_clean)
    _rotate(page)
    expect(_result(page)).to_contain_text("Server error 500", timeout=5000)
    expect(page.locator("body")).not_to_contain_text("Unexpected token")


@pytest.mark.browser
@pytest.mark.parametrize(
    "response",
    [PROMOTED, STAGED, (500, {"detail": "nope"})],
    ids=["success", "staged", "error"],
)
def test_focus_stays_on_the_rotate_button(app_clean: str, page: Page, response) -> None:
    """DD8-12: the in-flight state must not drop focus to the body."""
    _mock_status(page, _STATUS_NEVER)
    _mock_rotate(page, response)
    _open(page, app_clean)
    _rotate(page)
    expect(_result(page)).not_to_have_text("", timeout=5000)
    expect(_btn(page)).to_be_focused()
    assert _btn(page).get_attribute("disabled") is None
    assert _btn(page).get_attribute("aria-disabled") is None


@pytest.mark.browser
def test_the_button_ignores_clicks_while_a_rotation_is_in_flight(
    app_clean: str, page: Page
) -> None:
    _mock_status(page, _STATUS_NEVER)
    calls = {"n": 0}
    release = {"fn": None}

    def hold(route):
        calls["n"] += 1
        release["fn"] = lambda: _json(route, {"status": "ok", "key_file": "promoted"})

    page.route("**/api/encryption/rotate", hold)
    _open(page, app_clean)
    _rotate(page)
    expect(_btn(page)).to_have_attribute("aria-disabled", "true", timeout=5000)
    expect(_btn(page)).to_have_text("Rotating…")
    # aria-disabled buttons are "not enabled" to Playwright's click; dispatch the event.
    _btn(page).dispatch_event("click")
    _btn(page).dispatch_event("click")
    page.wait_for_timeout(300)  # absence check: no second request may start
    assert calls["n"] == 1
    release["fn"]()
    expect(_result(page)).to_contain_text("Key rotated.", timeout=5000)
    expect(_btn(page)).to_have_text("Rotate encryption key")


@pytest.mark.browser
def test_labels_banner_and_intro(app_clean: str, page: Page) -> None:
    """A4, A5: sentence-case labels; the banner states only the consequence."""
    _mock_status(page, _STATUS_NEVER)
    _open(page, app_clean)
    expect(_btn(page)).to_have_text("Rotate encryption key")
    banner = page.locator(".content-panel.active .banner-warning")
    expect(banner).to_have_text("The old key is discarded. This can’t be undone.")
    expect(banner).to_have_attribute("role", "note")
    expect(page.locator(".content-panel.active")).to_contain_text("Rotating generates a new key")
    assert page.locator(".admin-system-flash").count() == 0


@pytest.mark.browser
def test_facts_never_and_a_count(app_clean: str, page: Page) -> None:
    _mock_status(page, _STATUS_NEVER)
    _open(page, app_clean)
    expect(page.locator('[data-testid="encryption-last-rotated"]')).to_have_text("Never")
    expect(page.locator('[data-testid="encryption-credential-count"]')).to_have_text("3")
    expect(page.locator('[data-testid="encryption-facts"]')).to_contain_text(
        "Items with stored secrets"
    )


@pytest.mark.browser
def test_facts_show_the_rotation_time_in_the_operator_zone(app_clean: str, page: Page) -> None:
    _mock_status(page, {"last_rotated_at": _ISO, "credential_count": 0, "key_file_pending": False})
    _open(page, app_clean)
    when = page.locator('[data-testid="encryption-last-rotated"]')
    expect(when).to_have_text(re.compile(r"^Oct 20, 2026, \d{1,2}:\d{2} (AM|PM)$"), timeout=5000)
    expect(when).to_have_attribute("title", _ISO)
    expect(when).to_have_attribute("data-rotated-at", _ISO)


@pytest.mark.browser
def test_facts_refresh_after_a_rotation(app_clean: str, page: Page) -> None:
    seen = _mock_status(
        page,
        _STATUS_NEVER,
        {"last_rotated_at": _ISO, "credential_count": 5, "key_file_pending": False},
    )
    _mock_rotate(page, PROMOTED)
    _open(page, app_clean)
    expect(page.locator('[data-testid="encryption-last-rotated"]')).to_have_text("Never")
    _rotate(page)
    expect(page.locator('[data-testid="encryption-last-rotated"]')).to_contain_text(
        "Oct 20, 2026", timeout=5000
    )
    expect(page.locator('[data-testid="encryption-credential-count"]')).to_have_text("5")
    assert seen["n"] == 2


@pytest.mark.browser
def test_a_failed_status_read_shows_the_facts_unavailable_and_never_blocks_rotation(
    app_clean: str, page: Page
) -> None:
    _mock_status(page, {"detail": "boom"}, status=500)
    _mock_rotate(page, PROMOTED)
    _open(page, app_clean)
    expect(page.locator('[data-testid="encryption-facts-error"]')).to_be_visible(timeout=5000)
    expect(page.locator('[data-testid="encryption-facts"]')).to_be_hidden()
    _rotate(page)
    expect(_result(page)).to_contain_text("Key rotated.", timeout=5000)


@pytest.mark.browser
def test_a_pending_key_file_keeps_its_warning_across_a_reload(app_clean: str, page: Page) -> None:
    _mock_status(page, {"last_rotated_at": _ISO, "credential_count": 1, "key_file_pending": True})
    _open(page, app_clean)
    expect(_result(page)).to_have_attribute("data-state", "warning", timeout=5000)
    expect(_result(page)).to_contain_text("staged")
    page.wait_for_timeout(3500)  # absence check: no timer clears a pending-key warning
    expect(_result(page)).to_have_attribute("data-state", "warning")


# ── Prompts ──────────────────────────────────────────────────────────────


def _open_prompts(page: Page, base: str) -> None:
    _nav.goto(page, base, "settings/prompts")
    expect(page.locator('[data-testid="platform-section-tools-identity"]')).to_be_visible(
        timeout=8000
    )


@pytest.mark.browser
def test_prompt_headings_layers_are_h2_and_platform_blocks_h3(app_clean: str, page: Page) -> None:
    """B11: the layer title is the stronger heading."""
    _open_prompts(page, app_clean)
    panel = page.locator(".content-panel.active")
    layers = panel.locator("h2.section-title")
    assert [t.lower() for t in layers.all_inner_texts()] == [
        "platform prompt",
        "rules",
        "notes",
        "date",
    ]
    blocks = panel.locator('[data-testid^="platform-section-"][data-testid$="-identity"] h3')
    expect(blocks.first).to_be_visible()
    assert panel.locator('[data-testid^="platform-section-tools-"] > h3').count() >= 5
    assert panel.locator("h1").count() == 1


@pytest.mark.browser
def test_prompt_variants_are_subheadings_not_eyebrows(app_clean: str, page: Page) -> None:
    """A3 (HAT step 9): Platform prompt has no variant sub-headings; the Notes and
    Date variants stay plain sub-headings, never eyebrows."""
    _open_prompts(page, app_clean)
    assert page.locator(".platform-sections .prompt-variant").count() == 0
    assert page.locator(".content-panel.active .prompt-variant").count() == 4
    # The eyebrow family is only the four layer titles.
    assert page.locator(".content-panel.active .section-title").count() == 4


@pytest.mark.browser
def test_prompt_texts_are_trimmed_code_blocks(app_clean: str, page: Page) -> None:
    """A1: no leading or trailing blank lines in any text."""
    _open_prompts(page, app_clean)
    texts = page.locator(
        '[data-testid$="-text"][data-testid^="platform-section-"], '
        '[data-testid$="prompt-content"], [data-testid*="prompt-content-"]'
    )
    assert texts.count() >= 8
    for i in range(texts.count()):
        raw = texts.nth(i).evaluate("el => el.textContent")
        assert raw == raw.strip("\n \t"), (i, raw[:40], raw[-40:])
        assert "ui-code-block" in (texts.nth(i).get_attribute("class") or "")


@pytest.mark.browser
def test_prompt_layers_have_space_above_their_titles(app_clean: str, page: Page) -> None:
    """A2: a layer title sits at least 12 px below the previous layer's last block."""
    _open_prompts(page, app_clean)
    gaps = page.evaluate(
        """() => {
          const titles = [...document.querySelectorAll('.content-panel.active h2.section-title')];
          return titles.slice(1).map(t => {
            const section = t.parentElement;
            const prev = section.previousElementSibling;
            const blocks = prev.querySelectorAll('pre');
            const last = blocks[blocks.length - 1].getBoundingClientRect();
            return t.getBoundingClientRect().top - last.bottom;
          });
        }"""
    )
    assert gaps and all(g >= 12 for g in gaps), gaps


@pytest.mark.browser
def test_an_info_http_error_shows_an_error_status(app_clean: str, page: Page) -> None:
    page.route(
        "**/api/info",
        lambda route: route.fulfill(
            status=500, content_type="application/json", body='{"detail": "info exploded"}'
        ),
    )
    _nav.goto(page, app_clean, "settings/prompts")
    err = page.locator('[data-testid="prompts-load-error"]')
    expect(err).to_contain_text("info exploded", timeout=8000)
    expect(err.locator('[role="alert"]')).to_have_count(1)
    expect(page.locator(".content-panel.active")).not_to_contain_text("platform prompt unavailable")
