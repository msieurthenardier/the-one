# Leg: hat-alignment

**Status**: completed
**Flight**: [Telegram and the Name Directory](../flight.md)

## Objective

Guided HAT: prove Telegram live from real accounts (DM silence → pairing → round-trip → group always-listen → `/new`), exercise the cross-connector name-directory sends the stub gate could not (Discord + Telegram by name from the console), and close with daily-driver alignment — inline fixes per the fix-vs-feature gate, sized to the ~261-line mission slack.

## Context

- Interactive leg. Operator supplies the MAIN bot token (@BotFather); the FD drives the app side and can drive the "robot" Telegram USER account via the operator's goldfinch web.telegram.org session (environment note in the flight log) — the operator verifies and acts from their own account where a second human surface matters.
- `/setprivacy` OFF required for group always-listen (docs/connector-setup.md states it; verify during setup).
- Cross-state rule: at least one step verifies a surface the actor isn't looking at.

## Verification Steps (one at a time)

1. **Setup**: BotFather bot exists (privacy OFF); dev instance booted (8485, scratch, dev_mode); telegram connector created in Studio (token, `default_agent: test-agent`); doctor green.
2. **Unadmitted-DM silence**: robot account DMs the bot → total silence, nothing persisted.
3. **Pairing**: FD mints code; robot account DMs it → allowlist gains its user id, silently.
4. **DM round-trip**: robot account DMs a question → reply arrives in Telegram (DD-10 via Telegram's PeerTarget); `DM: <name>` session app-side with peer attribution + username captured in the directory.
5. **Group always-listen**: bot + robot account in a group; group chat id in `always_listen`; unprompted message → reply in-group; directory gains the group's title (chat.title capture live).
6. **`/new`**: robot account sends `/new` in the DM → session resets per the command contract.
7. **Cross-connector name sends** (the RQ11 multi-connector proof, live): from an unbound console chat — "send X to <robot account's name> on telegram" AND "send Y to Chuck R on discord" (Discord connector re-created on the dev instance with the GleepGlorp token if its row is absent post-scratch-reuse) → both arrive on their platforms via lookup→send.
8. **Daily-driver alignment (open)**: operator's own items; fix-vs-feature gate applies; budget-aware.

## Acceptance
- [x] Steps 1–7 verified live
- [x] Step 8 concluded, operator satisfied
- [x] Inline fixes reviewed and committed per HAT protocol
- [x] Flight log records each step

---

## Post-Completion
FD: leg → `completed`, flight → `landed`, mission check-off, PR #190 ready, `[COMPLETE:flight]`.
