# Squawk 0046: No per-platform setup guidance in the connector UI

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-03
**Completed**: 2026-09-03

## Report

Setting up a connector requires knowledge that lives only in
`docs/connector-setup.md` (Discord: Message Content intent, OAuth invite; Telegram:
BotFather, `/setprivacy` Disable before adding to groups). Nothing in Studio points
there or summarizes it, so a first-time setup is guesswork unless the operator already
knows the doc exists. Fix: render a short, type-specific step list in the connector
editor when a type is selected, ending with a link to the full walkthrough.

**Pinned technical decision** (FD, recorded): the steps are a small STATIC per-type
list in the editor JS (4-6 condensed bullets each, Discord and Telegram; stub gets
none), with a link to `docs/connector-setup.md` for the full text. No fetching or
rendering of the markdown doc, no sync machinery — the doc stays the source of truth
for detail and carries its own "verified against" date; the inline list is a
signpost, and its bullets name the two things that silently break setups (Discord's
Message Content intent; Telegram's privacy mode). If keeping the two in sync ever
becomes a real problem, that is a separate conversation, not this squawk.

## Evidence

- `docs/connector-setup.md` — the walkthrough that exists but is unreferenced in the UI
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` — no guidance surface today
- Operator request, 2026-09-03: "would be real nice to have clear provider specific step by step instruction right in the UI"

## Corrective Action

Added a static, per-type "Setup steps" section to the connector editor
(`the_one/interfaces/web/static/js/areas/studio/connector-editor.js`),
rendered on **both** the create and edit forms, right after Identity (so
the Type select drives it). Per the pinned technical decision: no
fetching/rendering of `docs/connector-setup.md`, no sync machinery — a
hand-maintained `SETUP_STEPS_BY_TYPE` map with condensed bullets derived
from that doc, kept live against the Type `<select>`'s `change` event.

- **discord** (5 bullets): create the application + Bot user at the
  Discord developer portal's Bot tab (token source, copy-once); enable
  **Message Content Intent** under Privileged Gateway Intents — named as
  the thing that silently breaks setup ("every inbound message arrives
  with empty content... connector looks connected but silent"); OAuth2
  URL Generator invite; set a default agent then use the Pairing section
  (referenced by name, its help line not duplicated); add channel id(s)
  to Admission/Always-listen.
- **telegram** (4 bullets): `@BotFather` → `/newbot` (token source);
  `/setprivacy` → **Disable**, called out as required **BEFORE** adding
  the bot to any always-listen group, with the non-retroactive-delivery
  consequence named; set a default agent then use the Pairing section
  (by name); add the bot to a group and its chat id to Admission.
- **stub** (and any unrecognized type): no bullets — the section hides
  itself (`hidden`) rather than rendering empty.
- Ends with a real `<a>` anchor (`docs/connector-setup.md`,
  `target="_blank" rel="noopener noreferrer"`) for the full walkthrough —
  `data-testid="connector-setup-steps-link"`.
- Container carries `data-testid="connector-setup-steps"`; each type's
  `<ul>` carries `data-testid="connector-setup-steps-list-{type}"`.
- CSS additions in `studio.css`: `.connector-setup-steps-list`,
  `.connector-setup-steps-link`, and a defensive
  `.connector-setup-steps[hidden]{display:none}` rule matching this
  file's existing pattern for JS-toggled `hidden` sections.
- Registered the 2 new literal testids + 1 new parametric prefix
  (`connector-setup-steps-list-`) in `docs/ui-testid-registry.md` (only
  the ids this squawk introduces — the registry gaps from squawks
  0043/0045's `connector-pairing-code` / `connector-status-led` /
  `connector-status-label` predate this squawk and were left alone, per
  scope).

File deltas: `connector-editor.js` 633 → 710 lines (+77, all additive:
the static step-copy map + the section render/update wiring — no
existing code paths changed). `studio.css` +21 lines. No backend/Python
changes — no route serves `docs/connector-setup.md`. *(Superseded by the
Review-fix paragraph below: this first pass rendered the reference as a
real `<a href="docs/connector-setup.md">`, which 404s; it is now plain
text. Left in place rather than rewritten so the record shows what was
built and what the review caught.)*

**Review fix (dead link)**: the batch Reviewer flagged that the walkthrough
anchor's `href="docs/connector-setup.md"` 404s — only `/static` is mounted
(`the_one/interfaces/web/app.py`), so `docs/` is not served over HTTP, and
the new browser test only asserted the href substring rather than that the
target resolved, so it passed CI while the link was dead. Grepped the rest
of the app (static/js, templates) for an existing "point at repo docs"
pattern first; none exists. Fixed by replacing the `<a>` with a plain-text
reference — `<span class="field-hint connector-setup-steps-doc-ref">Full
walkthrough: docs/connector-setup.md (in the repo)</span>` — reusing the
shared `.field-hint` muted-caption primitive (components.css) rather than
inventing new styling. **FD decision, recorded**: no route or static mount
for the `docs/` tree (that is new HTTP surface with a security-posture
question, out of scope for a squawk), and no external GitHub link (this is
a local-first app that may run offline; an outbound link is an operator's
functional choice, not an implementer's). Testid renamed
`connector-setup-steps-link` → `connector-setup-steps-doc-ref` (no longer
an anchor) and updated in `docs/ui-testid-registry.md`. Browser test
updated to assert the doc path appears in the element's text and that the
element is not an `<a>`, instead of inspecting `href`.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio -q`
  (foreground): **151 passed, 3 skipped** in ~4.5 min, including the new
  `test_studio_connector_setup_steps_shown_per_type` (create form: steps
  container visible; selecting `discord` shows the intent warning;
  selecting `telegram` shows the `/setprivacy` warning; the doc-link
  anchor is present with `docs/connector-setup.md` in its `href`).
  *(Stale as of the review fix above — the assertion this bullet
  describes is exactly the one that let a dead link pass CI. The test
  now locates `connector-setup-steps-doc-ref`, asserts the doc path is
  in its text, and asserts the element is NOT an `<a>`.)*
- `.venv/bin/ruff check the_one/ tests/` — all checks passed.
- `.venv/bin/ruff format --check the_one/ tests/` — 401 files already
  formatted, no diff.
- Noted but out of scope at the time: `tests/test_ui_guards.py::
  test_testids_in_source_are_registered` failed on 3 unregistered
  testids from squawks 0043/0045 (`connector-pairing-code`,
  `connector-status-led`, `connector-status-label`) — correctly flagged
  by this squawk's implementer rather than silently absorbed.
  **Resolved within the batch**: a follow-up registry pass registered
  those three plus `connector-pairing-copy-btn` (unregistered too, but
  invisible to the guard's literal-extraction regex because it goes
  through the `_btn` helper — registered anyway rather than only
  satisfying the checker). `tests/test_ui_guards.py` → 14 passed.
  Batch lesson recorded in the commit: a squawk that adds a testid must
  run the ui-guards test, not just its browser lane.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-03b — two passes (blocking dead-link issue routed back into 0046, re-reviewed after fix)
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-03b batch commit (PR follows)
