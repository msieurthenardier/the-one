# Leg: uat-and-alignment

**Status**: landed
**Flight**: [Discord Connector-Type Registration + Discord-Shaped Creation Form](../flight.md)

## Objective

Operator-driven HAT walk of the Discord-shaped creation + detail flow against a real Discord application: open Studio → select Discord → fill the typed form → Create & Test → observe probe report → see computed invite URL → invite bot to test guild → attach to an agent. Surface any UX friction the autonomous Playwright tests didn't catch.

## Context

- Interactive leg — Flight Director guides the operator through verification steps ONE AT A TIME.
- Existing bot: `gleepglorp` from M10 F8 HAT (or fresh).
- Browser-driven (dev server at `localhost:8484`); operator logs into Discord separately for the out-of-band invite step.
- HAT-discovered fixes land in the flight-log under L7 Anomalies. Per the L1-codified `prompt-discipline-needs-mechanical-fallback` convention, any HAT-time fix that reverses a substrate contract pauses the flight and triggers fresh design review.

## Verification Steps (operator-paced)

1. **Dev server up**: confirm `localhost:8484` is reachable; Studio loads.
2. **Create form → select Discord**: open Studio → New Connector → pick `discord` from the type dropdown → confirm typed form renders (Intents 3 checkboxes all checked, Guilds empty input, Presence empty inputs, Advanced disclosure closed). Confirm: NO generic kv-table at the top level (it lives inside the Advanced `<details>`).
3. **Bot token entry**: paste the BOT_TOKEN into the typed secrets field. Confirm: field is masked (`type="password"`); show/hide eye toggles visibility.
4. **Create & Test**: click Save (or Create-and-Test if available); verify the probe runs and the result banner shows status + application_id surfaced.
5. **Invite section appears post-probe**: confirm the Invite section is visible below Test Connection; URL contains `client_id=<your-app-id>` and `permissions=2147552256`; Copy button works.
6. **Intent recompute (stability test)**: toggle one intent checkbox; verify the URL stays byte-identical (permissions are intent-orthogonal) and the recompute happens without errors.
7. **Out-of-band invite**: copy the URL → paste into a new browser tab → authorize the bot for the test guild. Confirm the bot lands in the guild.
8. **Attach to an agent**: open an agent in Studio → Connectors tab → attach this Discord account → save.
9. **Vocabulary check**: open the Discord account's edit page → Access and Routing tab → confirm Allowlist labels read "Users / Channels / Servers / Roles" (NOT "Peers / Channels / Guilds / Roles"). Confirm hint text on Servers/Roles does NOT contain "Discord-flavored; ignored by other platforms".
10. **Routing-scope dropdown vocabulary**: add a routing rule on the Discord account → confirm scope dropdown lists "user / channel / thread / dm" (with `user` substituted for `peer`'s display text); the `<option value>` for "user" is still `peer` (verify via DevTools).

## Acceptance Criteria

- [ ] All 10 verification steps pass with no blocking UX friction.
- [ ] Any failures diagnosed + fixed inline; re-verified after fix.
- [ ] Anomalies recorded in flight-log L7 Notes section.

---

## Post-Completion Checklist

- [ ] All verification steps confirmed passing by the operator
- [ ] Anomalies (if any) documented in flight-log
- [ ] Set this leg's status to `landed`
- [ ] Check off `uat-and-alignment` in flight.md
- [ ] Commit (this is the only post-flight-commit commit — L7 lands separately because it's gated to operator pacing)
