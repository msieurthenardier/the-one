# Leg: uat-and-alignment

**Status**: landed
**Flight**: [Pool-Keying Refactor + Per-Account System-Prompt Directive Surface](../flight.md)

## Objective

Operator-driven Chrome-MCP-driven HAT against gleepglorp: verify directive section UI works end-to-end, the multi-agent pool-keying refactor produces ONE pool entry under real traffic, the probe-gateway-intents lift matches what `connect()` uses, and `MASKED_SENTINEL` + `data-account-id` polish work transparently.

## Context

Required (not optional) per F1 debrief recommendation: any flight touching registry-mediated UI dispatch gets a required HAT. F2 L4 adds `renderDirectiveSection` registry hook → HAT required.

Existing gleepglorp bot from F1 L7 reused. Flight Director drives Chrome MCP; operator confirms.

## Verification Steps (operator-paced)

1. **Dev server reachable + Discord Constellation loads** — Studio → Connectors → Discord Constellation. Confirm: editor renders typed Discord form (intents, guilds, presence, Advanced disclosure) + Invite section (from F1) + the NEW SYSTEM PROMPT DIRECTIVE section between Pairing and Attached Agents.
2. **Directive section structure** — confirm: textarea visible with `placeholder="(leave empty for no override)"`; help text "Your text is appended to whichever default fires for this account's current state. Empty = no override."; three `<details>` disclosures below (all closed). Annotation "(this account's current)" appears on the "When auto-relay is ON" disclosure (account's default state).
3. **Disclosure verbatim text** — expand each of the three disclosures; visually confirm each contains the agent's full system-prompt directive text starting with "This conversation is attached to a connector account…". The browser test `test_three_default_disclosures_render_verbatim_python_text` already pins JS↔Python equality automatically; this step is a visual sanity check.
4. **Annotation reactivity to auto-relay toggle** — switch to Access and Routing tab; uncheck "Auto-relay peer replies to platform"; switch back to General tab; confirm annotation moved to "When auto-relay is OFF and platform-send tool is enabled" disclosure. Re-check the box; confirm annotation moves back to auto-relay-ON. No save needed for the annotation repaint.
5. **Directive save round-trip** — type "Sign every reply with a coffee emoji ☕." in the textarea; click Save; confirm Save success banner; reload the editor; confirm textarea pre-populated with the same text. Verify via GET `/api/connector-accounts/{id}` (Flight Director can do this via fetch) that `config.system_prompt_directive` is the saved string.
6. **Empty directive omits the key** — clear the textarea; Save; reload; confirm textarea empty AND `config.system_prompt_directive` is NOT in the config dict (no empty-string noise).
7. **Pool-keying verification** — attach a SECOND agent to Discord Constellation (Cave Man Bot + Pirate Bot are already attached per F1 L7; if a third doesn't exist, attach an existing agent like a Mock-LLM agent). Send a peer message in the test Discord guild; confirm via the operator console that the message routes correctly. Then in the JS console execute `window.fetch('/api/connector-accounts/' + window.location.hash.split('/').pop()).then(r=>r.json()).then(a=>console.log(a))` or have the Flight Director run an evaluate_script that calls Python's `_pool._keys_for_test()` via a debug endpoint. ALTERNATIVELY: simpler proxy — verify the `gleepglorp` bot is only making ONE Discord IDENTIFY connection at a time by checking the bot status in Discord (single online indicator).
8. **`data-account-id` attribute** — DevTools → inspect the `.connector-account-editor` element; confirm it carries `data-account-id="<gleepglorp's actual account id>"` in edit mode.
9. **`MASKED_SENTINEL` global constant** — DevTools console: `App.studio.MASKED_SENTINEL` returns `'__MASKED__'`.
10. **Probe + intents alignment** — click Test Connection; observe probe report (should show "Discord probe ok" assuming gleepglorp is reachable). If the operator's account has `config.intents.message_content = false` set (toggle it in the Advanced kv-table or via a known test path), the probe respects it now (previously the probe used hardcoded all-True). Optional verification: toggle one intent off → save → re-run Test Connection → probe still passes (probe doesn't crash on different intents) → connect() now picks up the same shape.

## Acceptance Criteria

- [ ] All 10 verification steps pass with no blocking UX friction.
- [ ] Any failures diagnosed + fixed inline; re-verified after fix.
- [ ] Anomalies recorded in flight-log L6 Notes section.

---

## Post-Completion Checklist

- [ ] All verification steps confirmed passing by the operator
- [ ] Anomalies (if any) documented in flight-log
- [ ] Set this leg's status to `landed`
- [ ] Check off `uat-and-alignment` in flight.md
- [ ] Update flight status to `landed`
- [ ] Commit the L6 work (separate commit per agentic-workflow v2)
- [ ] Mark PR #70 ready for review
