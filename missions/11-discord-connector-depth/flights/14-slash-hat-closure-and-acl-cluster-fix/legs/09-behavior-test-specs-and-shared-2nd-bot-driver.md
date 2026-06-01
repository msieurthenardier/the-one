# Leg: behavior-test-specs-and-shared-2nd-bot-driver

**Status**: completed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

> **Scope pivot (operator-directed, F14 execution).** The flight DD specified TWO behavior-test specs + a shared `discord.py` 2nd-bot driver that invokes the operator's bot's slash commands and reads the wire-level `flags & 64` ephemeral bit. **That is impossible** — Discord bots cannot invoke another bot's slash commands (interactions are user-initiated), and an ephemeral followup is delivered only to the invoking user (a 2nd bot can neither trigger nor observe it). FD verified against discord.py 2.4.0 (`discord.Client` has no command-invoke methods) + the repo's existing `discord-engagement.md` (which drives Discord via Chrome MCP and explicitly defers slash to "a future spec"). Operator redirected to the mission's PREFERRED surface: **Chrome MCP driving the single dedicated logged-in Discord user's web client.** This leg now authors ONE Chrome-MCP behavior-test spec; the second spec (`slash-command-ephemeral-routing.md`, wire-level 4-cell matrix + token-expiry) and the 2nd-bot driver are DROPPED — L7's backend unit tests (`DiscordClient.send` level) already cover the 4-cell `(ephemeral × token)` routing + the `NotFound`→fallback, and `flags & 64` / real token-expiry aren't observable from the DOM. Original flight DD framing preserved in flight.md as commentary; pivot recorded in the flight-log Anomalies + FD Notes. (The leg slug retains its planning name; the deliverable is the single Chrome-MCP spec.)

## Objective

Author a single re-runnable Chrome-MCP behavior-test spec, `tests/behavior/discord-slash-end-to-end.md`, that drives the one dedicated logged-in Discord user's web client to invoke all 6 platform slash commands (`/whoami`, `/agents`, `/help`, `/talk_to`, `/new`, `/reset`) against the operator's real bot and verifies each reply — including ephemeral-where-appropriate, observed via the web client's "Only you can see this" treatment on the 3 self-only commands. Status `draft` until L10's first PASS.

## Context

- **One dedicated Discord user, logged in via the chrome-devtools MCP browser session** (operator-confirmed). All Discord-side actions (invoking slash commands, reading replies) and all observation happen through that single user's web client. No 2nd bot, no second session.
- **Ephemeral verification via rendered state** (per AUTHORING "Rendered State, Not Internal State"): when the dedicated user invokes a self-only command, Discord's web client renders the interaction reply with the **"Only you can see this"** ephemeral treatment — a user-perceivable label (screenshot / a11y evidence). The 3 channel-affecting commands post a normal channel-visible reply (no ephemeral label; persists in channel history). Single-user is sufficient: the ephemeral label IS the observable; we don't need a second session to prove invisibility.
- **This spec implicitly exercises L1–L7 end-to-end against real Discord**: the commands appearing in the `/` autocomplete confirms L2's slash-sync (unified `allowlist.guilds`) fired; `/agents` returning agent names (not "No agents available") confirms L1's Bug D fix under the post-F12 structured-tuple allowlist; the ephemeral treatment confirms L7. This is criterion #10's closure surface.
- **Format**: mirror `tests/behavior/discord-engagement.md` (the proven Chrome-MCP Discord spec) and the ARTIFACTS.md "Behavior Test — Spec" format. Apparatus: browser (chrome-devtools MCP). `Cache:` cold (default).
- **L10 impact**: L10 now runs **3** behavior tests (the 2 F13 regression specs + this new one) + the manual walkthrough — not the originally-planned 4.
- **L9 produces a spec only** — no production code, no driver, no backend/browser unit tests. The spec is the artifact; it RUNS at L10.

## Inputs

- `tests/behavior/discord-engagement.md` — format + Chrome-MCP Discord precedent (preconditions shape, observables, `[mixed-frame]` discipline, step-table style).
- `.flightops/ARTIFACTS.md` "Behavior Test — Spec" — canonical format.
- The 6 slash command behaviors (from `_commands.py` handlers + L7 ephemeral dispositions): `/whoami` (self, ephemeral — names the routed agent), `/agents` (self, ephemeral — lists ACL-permitted agents), `/help` (self, ephemeral — command list), `/talk_to <agent>` (channel — sets routing override), `/new` (channel — new session), `/reset` (channel — reset session).
- The operator's live Discord connector (bot online, channel allowlisted, the dedicated user allowlisted) — the run-time environment, confirmed at L10.

## Outputs

- `tests/behavior/discord-slash-end-to-end.md` — committed (status `draft`), ~6-8 step rows, browser apparatus, ready to run at L10.

## Acceptance Criteria

- [ ] `tests/behavior/discord-slash-end-to-end.md` exists, follows the ARTIFACTS.md spec format (Intent / Preconditions / Observables Required / Steps / Out of Scope), status `draft`, `Created` dated, `Last Run: never`.
- [ ] **Intent** states it verifies the 6 platform slash commands end-to-end against the real bot from the dedicated Discord user's frame, including ephemeral-where-appropriate; and why a behavior test (real web client + real bot + live slash registration/ACL path; not unit-testable as a UX flow).
- [ ] **Preconditions** are operator-checkable and include active-verification for decaying state: container up; the operator's Discord bot online + connector configured with the test guild in `allowlist.guilds` (so slash commands register post-L2); the dedicated Discord user logged into the web client in the chrome-devtools MCP session with the test channel open; the dedicated user is on the connector's allowlist (so commands are ACL-permitted post-L1); **a precondition-check step probing that the 6 commands appear in the channel's `/` autocomplete** (live-state verification that slash-sync fired — without it, every step fails confusingly).
- [ ] **Observables Required**: browser (Discord web client rendered state — screenshot + a11y primary, DOM supplementary), measured via chrome-devtools MCP.
- [ ] **Steps**: one row per command (6) + a precondition/autocomplete-probe row. Each command row's Expected Results are user-perceivable:
  - `/whoami` / `/agents` / `/help` → the reply renders with the **"Only you can see this"** ephemeral treatment (the self-only ephemeral assertion); `/agents` lists ≥1 agent (NOT "No agents available" — pins the L1 Bug D fix); `/whoami` names the routed agent; `/help` lists the commands incl. `/talk_to`.
  - `/talk_to <agent>` / `/new` / `/reset` → the reply is **channel-visible** (no ephemeral label; persists in channel history); `/talk_to` confirms the routing override; `/new`/`/reset` confirm session reset.
- [ ] Expected Results are written in rendered-state terms ("the reply shows 'Only you can see this'", "the message appears in the channel"), NOT DOM internals. Any cross-frame check is marked `[mixed-frame]` with justification (likely none needed — pure browser frame).
- [ ] **Out of Scope** notes: wire-level `flags & 64` (not DOM-observable — covered by L7 backend unit tests); multi-user/multi-channel routing; the dropped `slash-command-ephemeral-routing.md` (its substrate matrix is L7-unit-tested).
- [ ] No production code, no driver script, no unit tests added (spec-only).

## Verification Steps

- The spec file exists, parses as the ARTIFACTS.md format, status `draft`.
- A read-through confirms every Expected Result references the browser observable and is user-perceivable; the autocomplete-probe precondition step is present.
- (The spec RUNS at L10 via `/behavior-test discord-slash-end-to-end` — not in this leg.)

## Implementation Guidance

1. **Model on `discord-engagement.md`** — same preconditions shape (bot online, connector + allowlist, dedicated user logged into the Chrome MCP session, channel open), same browser-observable discipline, same step-table voice.
2. **Lead with an autocomplete-probe step** (active precondition verification): in the channel message box, type `/` and confirm the 6 commands (`whoami`/`agents`/`help`/`talk_to`/`new`/`reset`) appear in Discord's autocomplete — this proves L2's slash-sync registered them for the guild before the command rows run.
3. **One row per command.** Action: type the command (with an arg for `/talk_to`, e.g. an attached agent's name), select from autocomplete, send. Expected Result: the reply + its ephemeral disposition (rendered "Only you can see this" for self-only; channel-visible for the others) + the command-specific content assertion.
4. **Ephemeral observable**: assert the web client's user-perceivable ephemeral treatment ("Only you can see this" text near the reply; the reply does not appear as a normal channel message in history). Screenshot is the primary evidence. Do NOT assert `flags & 64` (not DOM-reachable; L7 unit tests own it).
5. **Pin the bug fixes**: `/agents` Expected Result must assert a real agent list (not "No agents available for this conversation.") — this is the observable proof of L1's Bug D fix under the real structured-tuple allowlist.
6. **Sequencing note for `/talk_to`/`/new`/`/reset`**: order them so they don't leave the session in a state that breaks a later row (e.g. run `/new` or `/reset` last, or note the expected session effect). Keep each row's expectation self-contained.
7. Status `draft`; `Last Run: never`. L10 flips it to `active` on first PASS.

## Edge Cases

- **Autocomplete doesn't show the commands** (slash-sync didn't fire): the probe step catches it up front as a precondition failure, not a confusing mid-test cascade — and would indicate an L2 regression.
- **`/talk_to` needs a valid attached agent name**: the spec should reference selecting an actually-attached, ACL-permitted agent (parameterize or instruct the operator to use a known agent at run time).
- **Ephemeral label wording**: Discord renders "Only you can see this" (current web client). If the exact phrasing differs at run time, the Validator judges the ephemeral-treatment intent (a clearly-private reply visible only to the invoker), not a byte-exact string.

## Files Affected

- `tests/behavior/discord-slash-end-to-end.md` — new spec (status `draft`).
- (No `slash-command-ephemeral-routing.md`, no `discord_slash_driver.py`, no `SLASH-HAT-SETUP.md` — dropped per the scope pivot.)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — except commit, which is deferred to Phase 2d per agentic-workflow batch protocol:**

- [ ] `discord-slash-end-to-end.md` authored per the ARTIFACTS.md format, status `draft`
- [ ] Every Expected Result references the browser observable + is user-perceivable; autocomplete-probe precondition present; `/agents` pins the L1 fix; self-only commands assert the ephemeral treatment
- [ ] No production code / driver / unit tests added
- [ ] Update flight-log.md with L9 leg progress entry (single Chrome-MCP spec; the 2nd spec + driver dropped per the operator pivot)
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off this leg in flight.md yet (Phase 2d)
- [ ] Do NOT commit (batched at Phase 2d)
