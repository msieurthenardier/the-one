# Squawk 0378: The widget card's escape contract test can miss the frame's first load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: —

## Report
`tests/browser/test_ui_widget_card_contract.py::test_escape_stops_the_card_and_keeps_the_marking[webkit]` failed once in the sortie 18 debrief's browser gate (`--parallel 3`, lane `contracts-widget`, host load 1.0 rising to 5.3): `Page.wait_for_function: Timeout 30000ms exceeded`. A re-run of the test passed in both engines. The sortie touched nothing in the widget area.

The timeout was not in the test's own wait for the stopped state. It was in the helper `_make_wait`, which waits until the card's frame has loaded once. This test's widget reloads itself 50 ms after it loads; the card then stops and removes the frame, after which `__cards[0]._frame()` is empty for good. If the page's polling does not run inside that 50 ms window, the helper's condition can never become true and it waits the full 30 s. That reading fits the stack and explains why only a loaded host shows it; it has not been confirmed by reproducing.

Expected: the test does not depend on observing a state that lasts 50 ms. For example, it creates the card without the "loaded once" wait and waits only for `stopped-escape`.

## Evidence
- `tests/browser/test_ui_widget_card_contract.py::_make_wait` — `page.wait_for_function("() => __cards[0]._frame() && __cards[0]._frame().loads() >= 1")`.
- `tests/browser/test_ui_widget_card_contract.py::test_escape_stops_the_card_and_keeps_the_marking` — the widget source is `setTimeout(function () { location.reload(); }, 50)`; the next line waits for `state() === 'stopped-escape'`.
- The failing run's stack: `test_ui_widget_card_contract.py:295` → `:50 in _make_wait` → `TimeoutError: Page.wait_for_function: Timeout 30000ms exceeded`, engine `webkit 27.2`.
- `sorties/18-mcp-arguments-as-rows/flight-debrief.md`, "Test metrics" — `PARALLEL_RESULT rc=1 total=2643s lanes=20 failed=contracts-widget`.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
