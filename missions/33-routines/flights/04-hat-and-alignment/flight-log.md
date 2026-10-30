# Flight Log: HAT and Alignment

**Flight**: [HAT and Alignment](flight.md)

## Summary

*(written when the flight lands)*

## Flight Director Notes

- **2026-10-29, planning.** Operator answers: Claude Haiku over the
  Anthropic API (the operator enters the key); the operator's own Discord
  account; squawks 0286 and 0287 turned first (#339, merged as `7dd144d5`).
- **HAT bots.** Both tokens in `tests/behavior/.env.hat` return 401 from
  Discord's `GET /users/@me` (tokens never printed): the bots are deleted.
  The walk uses the installed instance's bot, one gateway at a time (DD3).
  The `discord-live-round-trip` behavior spec depends on those bots; that is
  outside this flight and goes to the mission debrief.
- **Operator quit the installed instance** for the walk; port 8484 refused
  from WSL at planning.
- **Architect cycle 1 (Opus): approve with changes.** All 21 issues applied:
  - high: Discord DMs need pairing first (`is_admitted` drops unallowlisted
    peers); Purge now never deletes routines and clears all finished run
    history (C12, L10 corrected); the Thursday recipe could not show
    Sunday-first weeks (now a Sunday start); D4 spoiled the approval
    default check (C8 moved to D4's first enable);
  - medium: concrete recipes for C1, C2 and "still running"; the gone-chat
    sentence exists only for existing-chat targets (C14 added); E2's new
    chat and prompt approval; E3's triggers replaced with refusals the
    agent can hit; DD4 gained C12-C14 and folded calls into C3, C9, L8,
    L12; Part H added for restart, missed, caught-up and interrupted; a real
    quit check; a second agent for D5; Discord cleanup moved after the
    rename; DD5 gained the taint, field, library, spec and doc contracts and
    both eval baselines;
  - low: tab order; gate flags and HAT instance stopped first; secrets
    teardown; smaller recipe gaps.
  Open questions added: the bot token, and the evidence for the upgrade
  clauses.
- **Operator answers:** the upgrade clauses rest on the v45-v48 migration
  tests (no upgrade walk). The bot token may be in a scratch file; the
  operator pastes it into the dev instance, never into this conversation.
- **Architect cycle 2 (Opus): approve with changes.** All applied:
  - high: run history shows only an outcome label for `ok`, stopped and
    interrupted runs, so the gone-chat sentence is never displayed (C14
    reframed as one display decision; C1, C4, C5 expect what the screen
    shows); E3's past one-off is refused with "must be at least a minute
    away", not "no runs left";
  - medium: Run now is disabled during a run (the 409 needs a stale view),
    and C1 has a long-prompt recipe; six reminders add five to the queue;
    H1/H2 restart windows bounded (1-5 min caught up, >5 min missed); G1
    first creates a pending proposal (E5 withdrew them);
  - low: the Done one-off's preview error on save; the allowlist check at
    D2/D5; C4 turned off at ~3.5 min; C3's rebase clause rests on tests;
    A2 sends a first message; C5 uses a future Thursday; DD3 cleanup at F2;
    one-offs deleted too; the delete stale path rests on tests.
  - Logged **squawk 0288** (routine defect): saving a connector editor opened
    before pairing replaces the allowlist and drops the paired peer. Out of
    this flight's scope; the walk guards against it at D2/D5.
  Two design cycles are the limit; open points go to the operator.

## Judgement-Call Verdicts

*(one line per DD4 row: the call, confirmed or reversed, the operator's
words, and any resulting fix or leg)*

## Mission Criteria Verdicts

*(one line per mission criterion, with the walk step that showed it)*

## Leg Progress

*(entries as the walk proceeds)*
