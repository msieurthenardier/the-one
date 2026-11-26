# Squawk 0428: `_nav.goto` does not wait for the app to boot, so first expectations time out under load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: —

## Report

`tests/browser/_nav.py::goto` is a plain `page.goto` to a hash URL. On a heavily loaded host (load about 26), the app's boot takes longer than Playwright's default 5 s `expect` timeout. The bwrap probe slows the first `/api/config`, the router starts late, and only then do the areas render. So a test whose first step is `expect(...).to_be_visible()` fails with "element(s) not found".

Seen at the 2026-11-25 squawk turnaround on `tests/browser/test_flow_chat_composer_library.py::test_the_empty_states_text_column_is_centred`. It failed in the `chats` lane, and again 2 of 2 in isolation, at load 26. That file was untouched by the turnaround.

This is the same class as squawk 0424. That squawk's fix covers `open_destination` (rail clicks) and the predicates that call `_sessionState()`. It does not cover `goto`.

## Evidence
- `tests/browser/_nav.py::goto` only calls `page.goto`. Compare `open_destination`, which since 0424 calls `wait_router_started(page)` first.
- `tests/browser/test_flow_chat_composer_library.py:134-136`: `_nav.goto(...)` then `expect(welcome).to_be_visible()`, with the default 5 s timeout.

## Corrective Action
*(written at completion)*

Suggested direction: `goto` calls `wait_router_started(page)` after `page.goto`. That costs nothing on a warm page. A full browser run must validate it, because every lane uses `goto`. Check first for callers that load a page without `window.App`.

## Verification
At high load (above 10), the failing test passes 3 of 3 in isolation. A full browser gate on a quiet host stays green.

## Sign-Off
*(written at completion)*
