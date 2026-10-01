"""Playwright helper over the single shared resolver ``_a11y_resolve.js``.

M25 F1 L1 (DD3). The resolver JS lives in exactly one place and is read from
disk here and by ``scripts/webkitgtk_probe.py``
(``single-source-of-truth-for-paired-helpers``). A ``root_selector`` matching no
element is a failure, never a vacuous pass.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

RESOLVER_JS_PATH = Path(__file__).with_name("_a11y_resolve.js")


def resolver_js() -> str:
    return RESOLVER_JS_PATH.read_text()


def collect_label_failures(page: Page, root_selector: str) -> list[str]:
    """Return the resolver's failure strings for ``root_selector``; never raises
    on resolver findings (an evaluate-level error is returned as a failure)."""
    try:
        result = page.evaluate(resolver_js(), root_selector)
    except Exception as exc:  # noqa: BLE001 - surfaced as a failure string
        return [f"resolver evaluation error: {exc}"]
    return list(result["failures"])


def assert_controls_labelled_and_described(page: Page, root_selector: str) -> None:
    """Assert every control under ``root_selector`` is named and its id
    references resolve. The message lists the failures verbatim."""
    failures = collect_label_failures(page, root_selector)
    if failures:
        raise AssertionError(
            f"{len(failures)} label/description failure(s) under {root_selector!r}:\n"
            + "\n".join(f"  {f}" for f in failures)
        )
