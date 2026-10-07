# Leg: alignment-walk

**Status**: completed
**Flight**: [Alignment](../flight.md)

## Objective

A light, interactive walk (HAT) with the operator over this flight's own fixes (flight
DD18), plus the Flight Director's live check of DD17 (text selection) on a Windows test
copy, and the inline fixes the walk and the flight-end review leave.

## Context

- **DD18.** The operator used the installed v0.10.0 and found it "pretty good with the
  feedback I've already provided". So:
  - SC8's surface walk is that use;
  - the decision sheet and SC9 were answered in one batch before the walk (flight log,
    Decisions);
  - this walk covers only what this flight changed.
- **The walk instance.**
  - It runs on port 8486 with the scratch data dir `/tmp/the-one-f6-walk`, in dev mode.
  - It is seeded through the API with: a mock provider with three models, three agents,
    an unreachable MCP source attached to `code-helper`, a knowledge base, a disabled
    Discord connector, and five chats with messages (today, yesterday, 4 days and 20
    days).
  - The operator opens it in their Windows browser through a one-time handoff.
- **The inline batch** (DD7). The flight-end review's non-blocking items:
  - the MCP error is announced (`role="alert"`);
  - each info icon is read once;
  - the one-`cancelled`-per-`cancel` note.

  They get a batched Reviewer and Accessibility Reviewer pass before this leg's commit.

## Acceptance Criteria

- [ ] **The operator walks the seven items** and reports on each:
  1. the section labels (Settings nav, the provider editor, the red danger zone);
  2. "Available models" and its help line;
  3. the tiles' name and badge;
  4. the Agents and Library start pages;
  5. 12-hour times in the Chats list and the messages, and the composer meeting the
     context readout;
  6. the plain MCP error on `code-helper`'s MCPs tab;
  7. focus after Save.
- [ ] **DD17 is checked live** on a Windows test copy built from the branch (source, not
  frozen). It runs on app port 8490 and CDP port 9390, with a scratch data dir under the
  helper's root, and every session is bracketed by `snapshot --out` and `--compare`.
  - **The probe:** `getComputedStyle(document.body).userSelect` is not `none` in the
    desktop window.
  - **The selection:** a CDP mouse drag over a reply selects its text
    (`window.getSelection().toString()` is non-empty and comes from the reply).
- [ ] **The inline batch** is implemented, reviewed and committed with this leg.

## Verification Steps

- The operator's verdicts are recorded in the flight log.
- The DD17 probe's output (JSON) and the snapshot compare are recorded in the flight log.
  Evidence goes under /tmp and is never committed.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
