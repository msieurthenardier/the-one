# Squawk 0417: A failed page-line item lookup is swallowed without a log line

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

GleepGlorp's page line resolves the open item's name. When that lookup raises, the code falls back to no name, which is correct because it must not fail the turn, but nothing is logged. A drawer that keeps saying "Looking at Agents" with no item name can't be diagnosed. The sibling handlers in `settings.py`, `status_rows.py` and `view_core.py` all log. Found by the 2026-11-24 routine maintenance (Python Inspector).

## Evidence
- `the_one/gleepglorp/page.py` (about line 312): `except Exception:  # noqa: BLE001 - a lookup failure must not fail the turn` then `name, item_id = None, None`, with no log call.
- Compare `view_core.py` (about line 628): `logger.debug("read_app_config: %s %r unreadable", ..., exc_info=True)`.

## Corrective Action
*(written at completion)*

## Verification
The handler logs at debug level with `exc_info`, and the behaviour is unchanged. A unit test that forces the lookup to raise still gets a line with no name, and sees a log record with caplog.
