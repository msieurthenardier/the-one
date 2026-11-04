# Leg: hat

**Status**: ready
**Flight**: [Per-agent MCP credentials](../flight.md)

## Objective
A guided human acceptance session with the operator over the per-agent credentials surfaces. It covers the Tools tab tile, the Library "Set per agent" placeholder, two agents on one server, an open chat in another tab after a key change, the OAuth Authorization row (charter criterion 4) and the stdio "Environment for this agent" path. Issues are fixed inline until the operator is satisfied.

## Context
- Legs 1-3 are committed (`4b274ae4`, `4b6071f1`, `0bfdfd38`, `794a4d30`). The behavior test `per-agent-mcp-credentials` passed 14/14 (`9bcc2fe4`).
- Items the behavior test raised for the operator to judge:
  - the row reads "Set per agent · missing" between typing a key and Save, with no pending state;
  - the cached wording after a reload is "Last checked with this agent's values · N tools";
  - a test error is announced through the tile's alert, not the status line;
  - `test_an_mcp_refusal_gets_focus_over_a_tool_override_one` can't prove the MCP-over-tool focus order in its setup, so check it by hand.
- **Fix-vs-feature gate:** a look-and-feel fix rides inline. Anything that adds behaviour is promoted to a scoped design review first, and a change spanning more than one surface gets a lightweight design review before the implementing spawn.
- **Apparatus:** a dev instance on port 8486 with a scratch data directory under `$HOME`, plus the sortie's key server, a stdio `hello_server` (with its `dump_env` tool) and a source given OAuth state. The Flight Director sets these up. Ports 8484 and 8485 and the operator's default data directory are never used. The operator opens the instance in their own browser through a handoff link.

## Acceptance Criteria (verification steps; run one at a time with the operator)
- [ ] H1. **[Library]** The `keyed` server's blank `X-Api-Key` shows "Set per agent", and the hint reads clearly.
- [ ] H2. **[no key] -> [set, unsaved] -> [saved]** On alpha's Tools tab:
  - switching `keyed` on shows "Set per agent · missing" and "Needs a value for X-Api-Key", with no tools and no error;
  - setting a key and pressing Test lists alpha's tools;
  - Save, then a reload, keeps "Set for this agent" and the list, with the form clean.
  - The operator judges the wording and the pre-save row state.
- [ ] H3. **[two agents]** beta, given its own key, lists a different tool set; plain, with no key, is told it needs one.
- [ ] H4. **[open chat in another tab]** An alpha chat open in one tab keeps working after alpha's key is replaced and saved in another tab. The next tool call uses the new key (the key server log shows it).
- [ ] H5. **[editing]** Replace, Use server value with Undo, Add header with Cancel, and a refused value (for example a header name with a space) landing on its row with focus. Use server value then Save removes the agent's value.
- [ ] H6. **[OAuth server]** On a server with sign-in tokens, Authorization reads "Supplied by the server's sign-in" with no action, while another header can still be set for the agent. An API attempt to set Authorization is refused with the plain sentence.
- [ ] H7. **[stdio]** A stdio server's tile reads "Environment for this agent". A variable set for the agent reaches the spawned server (its `dump_env` tool shows it), and a blank Library value is not passed.
- [ ] H8. **[keyboard and screen-reader spot check]** Tab order through a row; the focus order on a mixed 422 (an MCP refusal and a tool-override refusal together).
- [ ] H9. The operator is satisfied, and every inline fix is committed with its tests green.

## Implementation Guidance
1. Set up the apparatus and seed data. Give the operator the handoff link.
2. Present one step at a time, wait for the operator's report, and fix issues inline per the gate above.
3. After each fix: `THE_ONE_TEST_NETNS=1 make test-unit` plus the owning browser lane, then re-verify the step.
4. At the end: tear down by PID and commit the leg's fixes and artifacts.

## Citation Audit
Verification-only leg. The surfaces and testids are those of legs 1-3; see their Citation Audits and `tests/behavior/per-agent-mcp-credentials.md`.
