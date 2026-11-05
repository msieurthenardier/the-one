# Leg: hat

**Status**: in-flight
**Flight**: [Secrets](../flight.md)

## Objective
Guided human acceptance of sortie 10 with the operator on a scratch instance built from the branch:
- the Library › Secrets editor;
- the Tools-tab grants, the drawer and the Prompts page;
- a real model using a secret through Goldfinch;
- a live chat in another tab picking up a changed value.

Issues are fixed as they come up, through the fix-vs-feature gate.

## Context
- Branch `sortie/10-secrets` at `2bcc2a04`: legs 1-3 completed; behavior run 1 passed 10/10 (after leg 2).
- **External prerequisites, re-verified now (flight Prerequisites):** Goldfinch running and reachable as an MCP source from the scratch instance; the operator's own model provider; a Goldfinch vault the operator is willing to unlock in a test.
- **Polish carried in from the leg 3 reviews**, to look at in step H4:
  - the Tools-tab section's 422 status is un-hidden and filled in one step;
  - that error isn't linked to the switches;
  - a stale section error survives a toggle;
  - a secret deleted in another tab leaves its row until refresh.
- **Apparatus (sortie 09 lessons):**
  - Scratch instance on a port of 8490 or higher (not 8484, 8485 or 8492), with scratch data and cwd under `$HOME`, `THE_ONE_DEV_MODE=true`, started from the scratch cwd with the branch venv.
  - The PID is taken from `ss -ltnp` and verified through `/proc/<pid>/environ`.
  - **After every restart, verify the new PID owns the port**; `/api/live` alone proves nothing.
  - A fresh handoff link for each new browser context.
  - Re-read the affected behavior-spec steps after any HAT fix that changes their surface.
- The operator's loaded-host note stands: timing is ignored.

## Steps (state transitions)

1. **H1 [empty] → [Library open]: Library › Secrets, empty.**
   - The Library list shows a "Secrets" group with "No secrets yet." and the Add menu has "Secret".
   - The start page shows the Secrets card.
   - No error messages.
2. **H2 [Library open] → [secret created]: create "Goldfinch vault key".**
   - Typing the name fills the first key `goldfinch_vault_key`; editing the key stops that.
   - Value is masked with Show; Create with no allowed tools is refused on the field.
   - Search-ahead finds `mcp__goldfinch__vaultUnlock` (keyboard and mouse).
   - Create opens the saved secret: the value shows as stored and masked, the row meta reads "1 value · 0 agents", and Used by is empty.
   - No error messages.
3. **H3 [secret created] → [multi-value secret]: create "Home address"** with `home_address`, `home_city`, `home_postcode`, allowed tools `mcp__goldfinch__typeText` and one more.
   - "+ Add pair", remove a pair, rename a key (its value clears), a duplicate key (refused on its row), a duplicate name (refused on Name).
   - Leave with unsaved edits: Stay keeps them, Continue discards them.
4. **H4 [secrets exist] → [granted]: Agents › an agent › Tools.**
   - The Secrets section is first, with name and "description · N tools" only.
   - Grant "Goldfinch vault key" and Save; open and close without changes stays clean.
   - The chat drawer lists it; Settings › Prompts shows the Secrets example.
   - Look at the carried polish items.
5. **H5 [granted] → [used by a real model]:** chat with the agent on the operator's own provider, asking it to unlock the Goldfinch vault.
   - The model writes `{{secret:goldfinch_vault_key}}`, and the vault unlocks.
   - The trace shows the placeholder, and any echoed value shows `[secret:goldfinch_vault_key]`.
   - The prompt wording is acceptable to the operator (DD8, option b).
   - A request for a tool not on the list is refused by name only.
6. **H6 [chat open] → [value changed elsewhere]: the state you aren't looking at** (criterion 4, the long-lived Agent).
   - With that chat open in tab A, change the secret's value in the Library in tab B and Save.
   - Back in tab A's open chat, the next tool call uses the new value, with no reload.
7. **H7 [granted] → [deleted]: delete a granted secret.**
   - The arm text reads "Delete and remove from 1 agent?".
   - After deleting, the agent's Tools tab no longer lists it, and the drawer no longer lists it.
8. **H8: keyboard and theme pass.** The editor, search-ahead, Tools tab and drawer work by keyboard only, in light and dark.
9. **H9: operator satisfied.**

## Binding addendum (HAT findings)
- **H6 substitute:** the Goldfinch vault does not relock, so H6 was run on Home address with `mcp__Goldfinch__typeText` in one open chat; the operator observed the changed value.
- **Doc-only fix F1:** SECURITY-MODEL.md (the Secrets runtime residual risks) and `the_one/agents.md` (Secrets section) record two accepted limits:
  - a short value can mask unrelated text, because there is no minimum length (seen: a postcode inside a base64 alphabet);
  - image results are not masked. Today an MCP image reaches the model and the stored chat only as an `[image: N bytes, mime=...]` line, so no pixels carry a value; a future change that forwards images to a model must address secrets.

## Acceptance Criteria
- [ ] H1-H8 pass as observed by the operator, or each failure is fixed and re-verified. A FEATURE request goes through the fix-vs-feature gate.
- [ ] Every HAT fix is committed with its test, and the owning lanes are re-run.
- [ ] Behavior test `secrets-round-trip` is re-run on the final build if any HAT fix changed server behaviour.
- [ ] H9: the operator is satisfied.

## Verification Steps
The operator's observations, step by step, recorded in the flight log.
