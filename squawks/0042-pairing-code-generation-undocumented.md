# Squawk 0042: Setup docs don't name the "Generate pairing code" button or say pairing is required

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-03
**Completed**: 2026-09-03

## Report

`docs/connector-setup.md` Discord step 6 says "Studio's connector detail page shows a
pairing code" and Telegram step 4 says "follow the same pairing-code flow" — both read
as if the page DISPLAYS a code. It doesn't: the operator must click **Generate pairing
code**, a button that currently sits under a "Diagnostics" heading, which implies
optional troubleshooting rather than a required enrollment step. Operator hit this
during the first real setup on v0.8.0 and had to discover the button by exploring.
Fix (docs only): in both platform walkthroughs, name the button explicitly, state that
generating a code is a REQUIRED step to admit the first peer, note the 10-minute TTL,
and that the code is sent as an ordinary DM message from the peer's account.

## Evidence

- `docs/connector-setup.md:30` (Discord step 6), `:42` (Telegram step 4)
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js:344-346` — the button, under the Diagnostics section created at `:335`
- Operator report, 2026-09-03 first production setup

## Corrective Action

Docs-only edit to `docs/connector-setup.md`:

- Rewrote the shared "Pairing (both platforms)" paragraph: names the
  **Generate pairing code** button explicitly, states it is a required
  enrollment step (not a diagnostics action), notes the 10-minute TTL, states
  the code is sent back as an ordinary DM message from the peer's own
  account, and adds that a fresh connector row (e.g. after the v38 migration
  retired legacy `connectors` rows) starts with an empty allowlist, so a peer
  admitted on a previous row must be paired again.
- Rewrote Discord step 6 to name the button, mark the step required, note the
  TTL, and state the code comes back as an ordinary DM.
- Rewrote Telegram step 4 (previously just "follow the same pairing-code flow
  as Discord above") the same way, still cross-referencing Discord for the
  shared mechanics.
- Updated the "Verified against" date to 2026-09-03.

Wording refers to the button only by its label ("**Generate pairing code**"),
not by its current location under "Diagnostics", per the note that squawks
0044/0045/0046 will relocate it into its own section.

No source files were touched.

## Verification

- Read the full diff (`git diff -- docs/connector-setup.md`): changes are
  confined to the three targeted sections plus the date line; no other
  content moved.
- Ran the exact CI lint gate:
  `.venv/bin/ruff check the_one/ tests/ && .venv/bin/ruff format --check the_one/ tests/`
  → `All checks passed!` / `401 files already formatted` (expected no-op,
  confirms no Python files were touched).

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-03b — two passes (blocking dead-link issue routed back into 0046, re-reviewed after fix)
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-03b batch commit (PR follows)
