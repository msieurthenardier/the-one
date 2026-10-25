# Squawk 0245: The connector pairing expiry shows a raw ISO timestamp

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: 2026-10-23

## Report
After "Generate pairing code", the connector editor reads `Expires 2026-10-23T12:34:56.789+00:00`: a raw UTC ISO string. That breaks the project's clock-text rule (CLAUDE.md "Flight 6 alignment notes" DD14, as worded since the M31 F3 HAT: humanised date and time in the operator zone, precise value in `title`). Show "Expires {date}, {time}" through `App.time`, using the knowledge editor's stamp formatter or an equivalent, and keep the ISO value in `title`. The UI captures masked this text, so it was never seen. Found in the M31 F3 debrief.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` (~:457): `className: 'connector-pairing-expiry', text: 'Expires ' + result.expires_at`.
- The formatter already exists: `knowledge-shared.js::_formatStamp` (`App.time.formatDate` + `formatClock`).

## Corrective Action
`App.time.formatDateTime(iso)` (new, `time.js`: `formatDate + ', ' + formatClock`, the raw value for an unparseable one) now backs `knowledgeShared.formatStamp` and the connector editor, which renders `Expires {date}, {time}` in the operator zone with the ISO value in `title` on `span.connector-pairing-expiry`. One-shot render. Mission 31 Flight 4 Leg 02b.

## Verification
`tests/browser/test_ui_time_contract.py::test_format_date_time_reads_a_server_iso_string_in_both_engines` (Chromium and WebKit, the server's 6-digit-fraction `+00:00` string); `test_studio_connector_editor.py` asserts the text format (a regex, not the time) and the ISO `title`; the behavior spec `stub-connector-round-trip.md` step 2 amended.

## Sign-Off
