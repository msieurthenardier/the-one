# Leg: macos-hat

**Status**: completed
**Flight**: [macOS app](../flight.md)

## Objective
The operator reviews what the hosted Mac runner saw (there is no Mac to walk), and decides each open finding. Any look-and-feel fix rides the inline protocol and is verified by the spare dispatch (5 of 5).

## Context
- Evidence: lifecycle run `40214604211` (13 PASS checks, 13 PASS lifecycle). The review page with the screenshots, the run summary and the decisions: https://claude.ai/artifact/NDe59MPrKZpU5Cwe5LxDYh (private).
- The Flight Director's diagnosis of P1 was corrected after the decision. The +1 s frame is the main window shown before its page painted (`visible=true` already), covering the frameless splash; it is not the splash drawn with a title bar. The operator's "fix now" stands, since the visible symptom and the intent are the same.

## Steps
1. The operator reviews the page: the screenshots, the rows, and the guide links.
2. The decisions (2026-10-25):
   - **P1** (the unpainted main window for about 1 s): "Fix now". On darwin the main window shows once its page has loaded, with a bounded fallback; `lifecycle.sh` L1 asserts it. A look-and-feel FIX, single surface (`shell.py`'s darwin boot path); Linux and Windows unchanged, proven by the GTK smoke test.
   - **P2** (the `model_catalog` warning at every launch): "Squawk it" → **squawk 0260**. The seed lists a retired model, so the catalog cache never refreshes.
   - **The `xattr` tip:** "Keep with a warning".
   - **The second Dock icon** on a second launch: "Accept".
3. Verify the P1 fix on dispatch 5 (`mode=lifecycle`): L1's new row PASS, the +1 s screenshot showing the splash or a painted page, and every other row still PASS.

## Acceptance Criteria
- [x] Every finding has a recorded disposition.
- [x] The P1 fix is reviewed, committed, and verified by a green lifecycle run.
- [x] The docs reflect the decisions (the `xattr` warning).

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
