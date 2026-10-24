# Leg: flight-hat

**Status**: planning
**Flight**: [Settings on the library](../flight.md)

## Objective
The operator walks every Settings page on a dedicated dev instance, in both themes, plus the Agents and Library surfaces this flight changed. The walk confirms:
- the approved visible changes (the ledger, rows 1-48) look right;
- the DD8 defects are fixed;
- nothing else moved.

The operator approves the before and after capture set (the mission's capture criterion).

## Context
- **Flight decisions:** DD7 (the ledger), DD8 (the defects), the Flight 3 debrief lessons:
  - steps are dry-run by the FD on the seeded instance before they are presented;
  - destructive steps use their own disposable, clearly named items;
  - if the HAT changes code, leg 11's close checks re-run before landing;
  - a HAT feature gets the Accessibility Reviewer too.
- **Captures:**
  - before: `$HOME/.cache/the-one-ui-capture/m31-f4-before` (v2, deterministic; masked times may differ from later sets by AM/PM only);
  - after: `$HOME/.cache/the-one-ui-capture/m31-f4-after` (leg 11).

  On request, the FD publishes a private comparison page.
- **Fix-or-feature gate:** a look-and-feel fix rides inline. New behaviour goes through a scoped design review first. A change spanning more than one surface gets a quick Developer design pass before the fix.

## Inputs
- The flight is reviewed and committed (the flight review, then the commit; the draft PR is open).
- A dev instance through `scripts/ui_capture.py --keep-running`:
  - port 8492 or higher (never 8484, 8485 or 8491);
  - a scratch data dir under `$HOME`;
  - seeded with the leg 01 realistic seed: the 97-character allowlist path, a custom size, tools disabled globally, non-default Knowledge indexing, the time zone in zone mode.
- **Disposable items for destructive steps:** a provider named "HAT disposable provider" (for the double-Create check). The encryption rotation runs only on this scratch instance.

## HAT steps (state transitions)
Each step is presented one at a time, after the FD has dry-run it.
1. **[open] The instance through its handoff URL → Settings › Built-in tools.**
   - The tiles show short summaries (B1), no category badge (A6), and an in-flow switch (row 40).
   - Tab to a switch: it announces "Enable {name} for all agents, switch, on" (DD8-1).
   - Toggle one off and on: the list doesn't jump, and focus stays on the switch.
2. **[tool editor] Open `read_file`.**
   - The breadcrumb reads "Settings / Built-in tools", with "Built-in tools" linked, and the title is the Library size (B2). The category subtitle reads "Filesystem" (A13).
   - The prompt is in its own section and doesn't rewrap when the form is dirty (A14).
   - "Enabled for all agents" sits on one line beside the switch (A9). Labels are written ("Maximum read size", A7).
   - The custom size reads "4MB (custom)" or similar (A8). The long allowlist chip is one line with a middle ellipsis and the full value on hover (B4).
   - The info buttons open on press (row 41).
   - The default denylist shows (squawk 0248).
3. **[errors] On `fetch_url`, set a negative redirect limit and Save.**
   - The field shows "Must be 0 or more" (A11), announced once (DD8-9), with no banner.
   - Cancel restores the saved values in place.
4. **[save model] Type a change, Save, and type again while it saves.**
   - The second change stays dirty (DD8-6).
   - Open another tool while dirty: the leave guard asks. Choose Stay.
5. **[test] On `fetch_url`, Test a URL outside the allowlist.**
   - The result reads "Blocked by this tool's settings", with one status mark, and the raw output is under "Technical details" (A15).
   - The input is a standard field with the button on its line (A16).
   - While dirty, the "Tests the saved settings." hint shows (row 47).
6. **[hidden fields] Open `delete_file` and `shell`.**
   - The read size cap and binary flag are absent on `delete_file` (B6), and the Filesystem fields have info buttons (B7).
   - The number fields are short text inputs (row 46).
7. **[agent tools] Open an agent's Tools tab and expand a Filesystem tool's Overrides.**
   - The labels and descriptions are written, booleans are inline (row 10), and the long chips use the ellipsis.
   - Enter "1.5" in a number override and Save: the field error shows, the panel opens and focus goes to the field. Nothing is saved.
8. **[appearance] Settings › Appearance.**
   - The theme picker is three cards (row 39). Arrows change the theme.
   - Switch to the other theme and back.
9. **[prompts] Settings › Prompts.**
   - No blank first lines (A1), captions have their space (A2), no stacked eyebrows (A3), and the layer titles lead (B11).
10. **[encryption] Settings › Encryption** (scratch instance only).
    - Sentence-case labels (A4), the shorter warning (A5), and "Last rotated: Never" with the stored-secrets count (B12).
    - Rotate (arm, then confirm): "Key rotated.", focus stays on the button (DD8-12), and "Last rotated" updates.
11. **[date and time] Settings › Date and time**, opened with the browser zone different from the effective zone.
    - The mismatch hint leads with city names (B9). Choose "Use {zone}": focus moves to the chosen-zone line (DD8-13).
    - The selected zone is centred in the list (B8), and picking a row low in the list doesn't scroll it.
    - No gap below the zone card (B10).
12. **[knowledge indexing] Settings › Knowledge indexing.**
    - Cancel and Save are top right (A19), with one rule per section (A18).
    - The switch label is on one line (A20). The interval echo reads "15 minutes" (A22).
    - The read-only values are humanised and aligned (A23, row 48), the notes are in plain wording (A24), and there is an intro line (B15).
    - Enter a chunk size of 50: the error replaces the hint (A21).
    - Fix it and Save while typing again: the edit stays dirty (DD8-15).
13. **[disabled buttons] In the dark theme, look at a disabled Save** (any clean editor). It is readable (row 37, B14).
14. **[library] Library › a provider (plan sign-in error), and an agent's Self-configuration tab** (the banner and code blocks, 04f). Nothing reads wrong.
    - Add a provider named "HAT disposable provider" and double-click Create: exactly one appears (squawk 0236).
    - Then delete it.
15. **[captures] Review the before and after set** (or the comparison page). Approve it, or name each difference to change.

## Acceptance Criteria
- [ ] Every step passes, or each failure is fixed and re-verified, with the fixes recorded in the flight log.
- [ ] The before and after capture set is approved.
- [ ] If any code changed during the HAT, leg 11's close checks re-ran (line guard, unused selectors, catalogue and docs greps, a full gate) before landing.

## Edge Cases
- **The encryption rotation** runs only on the scratch instance (never 8484 or the operator's data dir).
- **Steps that depend on seeded data:** if the seed doesn't produce a state, the FD fixes the seed before presenting the step, never by improvising in the step text.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
