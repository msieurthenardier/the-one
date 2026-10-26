# Leg: flight-hat

**Status**: completed
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
The operator walks the MCP server editor in every seeded state, plus the agent MCPs tab, the Library list, and the danger buttons of the provider, connector and knowledge editors (A1, B7), in both themes, on a dedicated dev instance. The walk confirms:
- the approved visible changes (the ledger, rows 1-36) look right;
- the planning defects stay fixed (DD9);
- nothing else moved.

The operator approves the before and after capture set (the mission's capture criterion).

## Context
- **Flight decisions:** DD7 (the ledger), DD9 (the defects), DD8 (captures).
- **The flight spec's HAT rules:**
  - steps come from the ledger and are dry-run by the FD first;
  - destructive steps use their own disposable, clearly named servers;
  - at least one step covers state the operator isn't looking at (a sign-in completed while the editor is closed);
  - if the HAT changes code, leg 12's close checks re-run before landing, and a HAT feature gets the Accessibility Reviewer too.
- **Captures:** before `$HOME/.cache/the-one-ui-capture/m31-f5-before`, after `m31-f5-after` (leg 12's compare table, flight log). On request the FD publishes a private comparison page.
- **Fix-or-feature gate:**
  - a look-and-feel fix rides inline;
  - new behaviour goes through a scoped design review first;
  - a change spanning more than one surface gets a quick Developer design pass first.

  A HAT-fix brief states "a library option, never consumer CSS on library internals" up front.

## Inputs
- **Commits:** legs 01-12 are completed and committed (`e4c553a`). The draft PR opens after the HAT, per the workflow.
- **A seeded dev instance** (FD, scratch helper `hat_seed.py` over `scripts/ui_capture.py`'s `start_instance` / `seed` / `seed_mcp`, detached):
  - URL `http://127.0.0.1:54432/`, PID 2351453;
  - data dir `$HOME/.cache/the-one-ui-capture/hat-20261026-102706/data`;
  - the fixture MCP servers `ok`, `legacy` and `401` (PIDs 2351479, 2351481, 2351483).
- **Seeded servers:**

  | Server | State |
  |---|---|
  | Hello tools (local) | stdio, connected; env vars incl. a stored secret `HELLO_API_TOKEN`; a long argument; two writable paths |
  | Always fails (local) | stdio, "Couldn't connect" |
  | Docs search | HTTP, connected; a plain header and a stored `Authorization`; server facts, instructions, 4 tools |
  | Legacy wiki | HTTP, older protocol, connected |
  | Billing API | HTTP, rejected credentials, "Couldn't connect" |
  | Team calendar | HTTP, dead port, "Not connected" |

  The capture agent `capture-mcp` has them all attached.
- **Disposables:** "HAT disposable - delete me" (stdio) and "HAT disposable - forget tools" (cached HTTP, no sign-in).
- **Seed note:** the seed's own Tests send a `{}` body, which by design never records `last_check`. The FD re-ran a body-less Test on the five servers, so the list and editors open in their recorded states.

## HAT steps (state transitions)
Each step is presented one at a time, after the FD has dry-run it. Steps 1-11 are in the light theme; step 12 repeats the key surfaces in dark.

1. **[open → Library]** Open the handoff URL, then Library.
   - The MCP servers group shows each server with a state word ("Couldn't connect", "{n} tools", "Not connected") and a Local or Remote badge (row 27).
   - The provider rows keep their type badges.
2. **[stdio editor] Open "Hello tools (local)".**
   - Title, subtitle "Local program (stdio) · {command}" (rows 3, 4).
   - Sections in order: Connection, Environment variables, Sandbox, Server, Tools, Danger zone (row 22).
   - The status line reads "Connected · checked h:mm AM/PM" (row 6), and Test is in the header (row 23).
   - The plain type and command choices (row 24), with the muted command hint under Command (row 5).
   - Arguments and Writable paths are chips with a muted × (rows 14, 34). The long argument is one line with a middle ellipsis, and the full value shows on hover (row 25).
   - "Allow network access" is a switch with its label inline and a hint (row 10).
3. **[env vars and secrets] Still on "Hello tools (local)".**
   - The Environment variables table has fixed columns, with a Sensitive switch per row and an info button beside the Sensitive heading that opens the written text (rows 11, 13).
   - `HELLO_API_TOKEN` shows dots, no eye, and "Stored. Type a new value to replace it." (row 26). Click into it: the whole value is selected, so typing replaces it.
   - Change its **key** (add `_2`): the value empties and reads "Type the value again for the new name." (row 35). Click Cancel: everything is back.
4. **[server and tools] Still on "Hello tools (local)", then "Docs search".**
   - Server shows Version, Protocol, Offers, Website (row 16); Instructions and Tools are disclosures, each description shown once (row 15).
   - On "Docs search": Headers sits above Server and Tools, and the stored `Authorization` header is in stored mode. The Test result sits at the end of Connection, with no "Server exposes N tools." line (row 8).
   - It offers "Forget tools list" (no sign-in), not "Reset connection" (row 7).
5. **[failures] "Always fails (local)", then "Billing API". Press Test on each.**
   - "Always fails": "Couldn't connect", with the stdio headline "The server's command didn't start or stopped. Open Technical details for its output." and the raw text under "Technical details" (rows 9, 18). *(FD correction during the HAT: the first step text said the stdio headline ends "then try again". That phrase belongs to the HTTP headlines; see "Team calendar".)*
   - "Team calendar" (a dead port): Test gives "Couldn't connect to this server. Check that it's running and that its address and headers are right, then try again." (row 18).
   - "Billing API": "Couldn't connect" and "The server rejected the configured credentials. Check the headers on this MCP server.", with no Reset button (rows 7, 18).
   - Close and reopen "Always fails": it still reads "Couldn't connect" (row 9).
6. **[forget patches in place] Open "HAT disposable - forget tools".**
   - Type a change in Name (the form goes dirty).
   - Press "Forget tools list", which arms as "Forget tools list?", then press it again.
   - "Tools list forgotten" shows. The status reads "Not connected", Tools reads "Press Test to load this server's tools.", and your unsaved Name edit and "Unsaved changes" are still there (row 30).
   - Cancel to drop the edit.
7. **[create and errors] Library › Add › MCP server.**
   - The title is "New MCP server", and only Name and Type show until a type is chosen (row 17).
   - Choose "Local program (stdio)", leave Name empty, and Create: "Enter a name." appears on the field, and focus goes to Name (row 2).
   - Leave with Library: the leave guard asks; choose Continue.
8. **[delete] Open "HAT disposable - delete me".**
   - The danger button reads "Delete MCP server". Press it: it arms as "Confirm delete?" (row 28). Confirm.
   - "MCP server deleted" shows, the row is gone, and focus lands sensibly (row 3).
9. **[agent MCPs tab] Agents › capture-mcp › MCPs.**
   - The tab bar reads "Built-in tools" (row 21).
   - Each server's Tools button is announced "Tools for {server}" (a screen reader or hover, row 20).
   - "Always fails" shows its error headline at one size with "then try again" (row 18).
   - The General tab's danger button reads "Delete agent" (row 28). Don't confirm.
10. **[other editors] Library › a model provider, the knowledge base "Capture knowledge", and a connector if seeded.**
    - Their danger buttons read "Delete provider", "Delete knowledge base", … and arm as "Confirm delete?" (row 28). Don't confirm.
11. **[sign-in, state you aren't looking at] Add a real OAuth MCP server you use** (your choice, on this scratch instance only; for example a remote MCP that signs in with your account).
    - Before Create the status reads "Not connected"; Test reads "Sign-in needed" with the wording "Complete the sign-in in your browser. This page updates when you're done." and an "Open sign-in page" / Copy link block (row 19).
    - Close the popup without finishing: "Waiting for sign-in…" (row 19).
    - Start the sign-in again, then go to a different Library item and finish the sign-in in the browser. The callback page is styled (row 31).
    - Reopen the server: it reads "Connected", lists its tools, and now offers "Reset connection", which arms as "Reset connection?" (row 7).
    - The Library row's state follows (row 27).
12. **[dark theme and 1024] Settings › Appearance › Dark, then revisit Library, "Docs search" and "Hello tools (local)".**
    - Nothing reads wrong in dark: the status dots, the badges, the danger zone, the disabled Save.
    - Narrow the window to about 1024 px wide: no sideways scroll in the tables (row 12), and the long chip still truncates.
13. **[captures] Review the before and after set** (or the comparison page). Approve it, or name each difference to change.

## Acceptance Criteria
- [x] Every step passes, or each failure is fixed and re-verified, with the fixes recorded in the flight log. (Steps 1-10, 12, 13 pass; five inline fixes re-verified by the operator; step 11 deferred by the operator, rows 7/19/31 resting on browser tests.)
- [x] The before and after capture set is approved (operator, 2026-10-26).
- [x] If any code changed during the HAT, leg 12's close checks re-ran (guards, catalogue and docs greps, a full gate) before landing. (Code and accessibility reviews confirmed; `make gate`: unit 7665 passed / 15 skipped, browser `PARALLEL_RESULT rc=0 total=1581s`, no lane over budget.)

## Edge Cases
- **Step 11** needs a real OAuth server and the operator's account. If none is at hand, the operator may defer it. The disposition is recorded, and rows 7 (Reset), 19 and 31 then rest on their browser tests.
- **Seed-dependent steps:** if the seed does not produce a state, the FD fixes the seed before presenting the step, never by improvising in the step text.
- **Rows not walked by hand, pinned by tests:**
  - row 32 (`autocomplete="new-password"`, not visible);
  - row 29 (Delete and Reset errors as the editor error, which needs a failing server response);
  - row 33 (disabled while in flight, too quick to see);
  - rows 1 and 36 (a long editor error, shown in the captures `mcp-edit-save-error` and `ref-provider-long-error`).

## Dry run (FD, 2026-10-26)
Checked by Playwright on the seeded instance:
- **Library list:** the state words and badges as in step 1.
- **Editors:**
  - "Hello tools" and "Docs search": section order, status lines "Connected · checked 3:29 PM", the header Test;
  - "Docs search" and "Legacy wiki" offer "Forget tools list"; "Billing API" and "Team calendar" offer no Reset or Forget;
  - Test on "Always fails" and "Billing API": "Couldn't connect" and the rejected-credentials headline under "Technical details".
- **Create:** an empty Name gives "Enter a name." with focus on Name. Leaving dirty asks "Unsaved changes … Stay / Continue".
- **Key rename:** renaming `HELLO_API_TOKEN` shows "Type the value again for the new name."; Cancel restores it.
- **Forget (on a dry-run-only copy, since deleted):** "Tools list forgotten", "Not connected", and the unsaved Name edit and "Unsaved changes" kept. Focus moves to Test because the Forget button goes away.
- **Agent editor:** the tab bar reads "General, Rules and notes, Knowledge, MCPs, Built-in tools, Self-configuration".
- **Not dry-run:**
  - step 11, which needs the operator's real OAuth server;
  - step 12's 1024 width, which the captures cover at 1024.

Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
