# Squawk 0389: Mission 36 Flight 1 documents and the full-gate target

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: —

## Report
After Mission 36 Flight 1, three documents lag the code:
1. **The "Full-gate target" paragraph in CLAUDE.md** is from Mission 34 Flight 1: 43 minutes, from a 229 s unit tier plus a 2027 s browser run.
   - Flight 1's final gate was 308.75 s plus 2270 s, about 43.0 minutes, but on a loaded host.
   - Run the full gate on a quiet host (load below about 1.0).
   - Restate the target from that reading, with the 350 s unit target.
   - Re-budget any lane that moved more than 15%, per the quiet-host rule.
2. **`the_one/agents.md` should state the final HAT designs as the reference:**
   - the GleepGlorp setup state (a quiet next step, option A);
   - the shared notes list (option A, no edit);
   - the provider delete box shown on open.
   The flight log holds superseded versions of all three.
3. **CLAUDE.md's "Control library" paragraph** should name `App.ui.button`'s `tone: 'danger'` and `App.ui.confirm.disarm`. Both are in the catalogue.

## Evidence
- `CLAUDE.md` "Full-gate target (M34 F1 L02)".
- The flight log's "Flight-end review fixes and gate" (the loaded reading, start load 1.91) and its "Superseded HAT entries" paragraph.
- `docs/ui-control-inventory.md`, the `button` and `confirm` rows.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
