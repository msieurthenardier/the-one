# Squawk 0094: the knowledge-base attach toggle is not reachable by accessibility role

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-21
**Completed**: —

## Report

The per-knowledge-base attach toggle on an agent's Knowledge tab is a real,
functional `<input type="checkbox">` — but it is **not found by a role-based
accessibility query**. During Mission 24 Flight 7's `kb-studio-round-trip` run
(2026-09-21, step 9), `page.get_by_role("checkbox")` returned **0 elements** on
a page where the toggle was present, rendered and operable.

The markup is a standard custom-switch pattern: the native input is visually
hidden (`bounding_box: None`, `is_visible(): False`), a `<span class="tool-switch">`
inside the wrapping `<label class="agent-knowledge-row-toggle">` provides the
visual affordance, and the native label-input association forwards the click.
The Executor worked around it by clicking the **label** and reading
`element.checked` directly rather than through the role-based API.

**Why this is worth confirming rather than assuming either way.** Playwright's
role query is a heuristic over the accessibility tree, not a screen reader. The
visible label does carry the knowledge base's name, so a screen-reader user
plausibly still gets an accessible name. But a control that a role-based query
cannot find is at minimum a smell, and this specific pattern — visually-hidden
native input behind a styled span — is exactly the shape that produces
unreachable controls when it goes slightly wrong.

**The coverage gap is the durable part.** This codebase audits **colour
contrast** (`tests/test_design_tokens_a11y.py`, WCAG 2.1 AA) and nothing audits
**custom form-control semantics**. A defect of this class has no test that would
catch it, which is why it surfaced incidentally in a behaviour test looking at
something else entirely.

## Evidence

- `tests/behavior/kb-studio-round-trip/runs/2026-09-21-02-10-21.md` — "Incidental
  findings", item 2; Executor closing summary item 3
- Step 9 observation: `page.get_by_role("checkbox")` → 0 matches; the input's
  `data-testid="agent-knowledge-toggle-<kb_id>"` is present in the DOM and its
  `.checked` property transitions `false` → `true` on a label click
- `tests/test_design_tokens_a11y.py` — the existing a11y surface, contrast only

## Disposition

Qualified against the squawk gate: **one coherent item** ✅ (one control's
accessible exposure); **no design decisions** ✅ (the remedies for this pattern
are standard — an `aria-label`/`aria-labelledby` on the input, or the
visually-hidden-but-focusable idiom rather than fully hidden; the codebase's own
`.visually-hidden` conventions apply); **bounded blast radius** ✅ (one toggle in
`knowledge-tab` rendering, though see below); **verifiable** ✅.

**First step is confirmation, not a fix.** The Playwright heuristic is suggestive,
not decisive — confirm against `axe` or an actual screen reader before changing
markup. If it turns out the control *is* properly exposed and Playwright's query
simply doesn't match this pattern, close this as not-a-defect and record that,
which is itself useful.

**If the same markup pattern is shared with other toggles** (the MCPs tab uses a
visually similar row toggle), the blast radius grows and that is the escalation
trigger — a shared-control change across tabs is a flight, not a squawk.

## Corrective Action

*(pending)* Confirm first with a real accessibility tool. If genuinely
unreachable, apply the standard remedy for the custom-switch pattern and keep the
native input as the accessible control rather than replacing the pattern.

## Verification

*(pending)* An accessibility assertion that the attach toggle is reachable and
operable by role, and — since this class of defect currently has no home —
consider whether it belongs in a new custom-form-control audit alongside the
existing contrast tests rather than as a one-off.

## Sign-Off

*(written at completion)*
