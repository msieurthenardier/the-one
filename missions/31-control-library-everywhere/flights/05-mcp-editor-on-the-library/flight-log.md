# Flight Log: The MCP server editor on the library

**Flight**: [The MCP server editor on the library](flight.md)

## Summary
Planned 2026-10-25 from `main` at `b1e47ae` (Flight 4 merged as #309). The branch is `flight/05-mcp-editor-on-the-library`, cut from `main` at flight start.

---

## Planning Notes

- **Operator decisions, 2026-10-25:**
  - the flight is planned the way Flight 4 was: a presentation survey approved up front, batched legs, and the HAT at the end (the Flight 4 debrief's recommendation and the operator's stated preference);
  - the presentation items are decided on the review page (https://claude.ai/artifact/3QhTwTHBu5phSdgDCqwKSB): all of A1-A21; B1 (a), B2 (b), B3 (a), B4 (a), B5 (a), B6 (a and b) and B7 (a); B8 left as it is; B9 and B10 skipped (DD7).
- **Operator answers, 2026-10-25:**
  - survey 0.1 → squawk **0260**, logged open, outside the flight;
  - the companion squawks as recommended: 0214 and 0216 in leg 08b, 0203 in leg 12, 0259 in leg 01; 0257 stays separate;
  - B5 is MCP-only for now.
- **Planning surveys at `b1e47ae`** (two read-only crew; reports in the FD scratchpad):
  - **Code:** `f5-code-survey.md`. It covers the structure map and split, every sink and allowance use with its replacement, the library gaps, the side-effect inventory, 15 defects found by reading, the tests and lanes, the squawk recheck and the alias recount.
  - **Presentation debt:** `f5-presentation-debt.md`, with 350 screenshots in `f5-debt/shots/`. It ran on a scratch instance at port 8492 (data dir `$HOME/the-one-f5-debt/data`, cwd `$HOME/the-one-f5-debt/cwd`) plus fixture MCP servers on 8493-8495, all inside `unshare -rn`, each stopped by its recorded PID. Ports 8484, 8485 and 8491 and the default data dir were never touched.
- **Flight Director calls, made out loud:**
  - one flight for the MCP editor, 12 autonomous legs plus the HAT, with a split raised if design review takes it past 15 (DD1);
  - the server's secrets contract is not changed (DD5);
  - B6's "Couldn't connect" needs a recorded outcome, so `_cache.last_check` is an additive server field, written by the editor's Test only (DD6);
  - B2 puts Test in the header and its result line at the end of Connection, mirroring `provider-test-result` (DD7);
  - the `MOVES` table for the allowances (the Flight 4 debrief, Recommendation 6) lands in groundwork, because the split is the first move (DD2);
  - squawk 0249 is not this flight's: its code is chat's OAuth (correcting the Flight 4 debrief, Recommendation 3).

## Reconnaissance Report

Sources: the Flight 4 debrief (Recommendations 1-8, Technical "Leftovers for Flight 5", the carried items), the mission's Known Issues, and the open squawks touching MCP. Classified at `b1e47ae`.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Debrief R1: "what the old control gave for free" and derived-relationship criteria | confirmed-live (a process rule) | n/a | DD10 standing rule; DD7 ledger criteria |
| Debrief R2 / squawk 0257: agent `tool_overrides` unvalidated | confirmed-live; outside this flight | `api.py:1087-1091` preserve-on-omit only; `tools/resolver.py:195` raises at build | A separate squawk (no shared files, different lanes) |
| Debrief R3: retire the `tools-form-helpers.js` chip path | confirmed-live | sole caller `mcp-server-editor.js` (5 calls) | Leg 06 handover (DD11) |
| Debrief R3: "the five `.area-studio` chip and switch allowance keys" | partially-satisfied (drifted wording) | all five are chip keys (`chip`, `chip-list-editor`, `chip-list-input`, `ui-chip-list`, `ui-chip-list-input`; 13 uses); the switch has no allowance key; two more rows can go (`field-info-icon` `studio.css:427`, `indicator-led` `:125`) | 7 rows / 15 uses retired across legs 06-08 |
| Debrief R3: "the two `App.icon` calls on the chip path" | already-satisfied | `tools-form-helpers.js` has 0 `App.icon` calls; the 8 left are all in `mcp-server-editor.js` | Retire the 8 in legs 06-10 |
| Debrief R3: "Flight 5 also carries squawk 0249" | drifted | 0249 is `tests/browser/test_oauth_modal_flow.py:188-224` (chat's `startLoginFlow`) | Not this flight (Flight 6, chat) |
| Debrief R3: latest-request counters "to convert" (Flight 4 DD3) | drifted | the MCP editor has no counters; `mcp-glue.js` guards only `onSaveSuccess` (`:84`) | New work, leg 03 |
| Debrief R4 / squawk 0259: `chats` lane at budget | confirmed-live | `scripts/run-tests.sh:63` `[chats]=450` | Leg 01 (quiet-host re-measure) |
| Debrief R5: revisit Flight 6's scope | confirmed-live | alias recount (below) | At this flight's debrief |
| Debrief R6: the allowance `MOVES` table | confirmed-live | `tests/test_ui_ownership.py` has no move rule | Leg 01 (DD2) |
| Debrief R7: `searchList` reconciliation; `.editor-section--flush` | confirmed-live; not this surface | n/a | Not this flight; DD10 notes the cascade trap |
| Debrief R8: CLAUDE.md control-library deltas to `agents.md` | confirmed-live | CLAUDE.md control-library paragraph | Leg 12 |
| Squawk 0214: the OAuth callback page unstyled | confirmed-live | `api.py:4661-4663` links `/static/…`; `middleware.py:212` exempts only the callback path, so assets 401 | Leg 08b |
| Squawk 0216: Test-connection transient-text race | confirmed-live | `tests/browser/test_mcp_test_connection_button.py:191, :196` | Leg 08b |
| Squawk 0215: chat's stale sign-in link | confirmed-live; chat | `areas/chat.js:1306-1309` | Flight 6 |
| Squawk 0203: era docstring and negotiation docs | confirmed-live (docs only) | `the_one/mcp/_era.py:7-8`; `the_one/agents.md:1088` | Leg 12 |
| Survey 0.1: stdio "Connection closed" with no cause | confirmed-live | repro in `f5-presentation-debt.md` §0.1 | Squawk 0260 (operator); A18 fixes the wording only |
| Survey 0.2: a failed Test still says "Connected" | confirmed-live | `mcp-server-editor.js:2128-2150` | A9, leg 08b |
| `create_mcp_source` keeps a client-sent `_cache` | confirmed-live; outside | `api.py:3097-3115`; `tests/browser/seeders.py:195-201` | A squawk candidate (a test-seam plan needed) |

**Alias calls outside `js/ui/`** (re-counted at `b1e47ae`):
- `App.confirmDelete(` 3 (MSE 2, `chat.js` 1);
- `App.showFlash(` 8 (MSE 5, `markdown.js` 3);
- `App.icon(` 9 (MSE 8, `markdown.js` 1);
- `App.consentLink.` 7 (MSE 3, `chat.js` 4);
- `App.adminFormHelpers` (MSE 5).

After this flight: `chat.js` (confirmDelete 1, consentLink 4) and `markdown.js` (showFlash 3, icon 1).

## Presentation-Debt Survey (summary)

The full report, with every screenshot path and `file:line`, is in the FD scratchpad (`f5-presentation-debt.md`).

- **A (obvious), 21 items:**
  - header: A1-A4;
  - connection: A5-A9;
  - sandbox and the key/value table: A10-A14;
  - server and tools: A15-A16;
  - create form: A17;
  - shared MCP wording: A18-A19;
  - agent editor: A20-A21.
- **B (taste), 10 items:** B1-B10.
- **Fine, no change:**
  - the Library list's MCP group, selection and widths;
  - the breadcrumb, the Cancel and Save states and the unsaved caption;
  - section titles, field labels and inputs (already at library sizes);
  - the danger zone's arm, confirm and lapse;
  - the rejected-credentials headline and Technical details;
  - the consent-link block;
  - dark-theme contrast;
  - no overflow at 1024 apart from A12.

## Code Survey: side-effect inventory (DD4 starting list)

| Effect | Today | Where |
|---|---|---|
| Create, then Save | the glue remounts the editor (create → edit), then auto-clicks Refresh for streamable-HTTP only (`dataset.autoRun`, no popup: the "Sign in" button) | `mcp-glue.js:83-138` |
| Edit, then Save | patch: invalidate `mcp-sources`, flash, the snapshot re-read from the DOM, the buttons, the caption, the title (squawk 0126), focus-after. The subtitle, `source` and secret masks are not updated | `mcp-server-editor.js:1279-1301` |
| Cancel (edit) | patch to the mount-time `source`; the kv rebuild; chips remounted with a no-op `onChange` | `:1214-1229`, `:1579-1670` |
| Cancel (create) | discard, `router.go('#library', {replace, bypassGuard})`, focus the group | `mcp-glue.js:72-82` |
| Delete | two-step confirm; DELETE; invalidate `mcp-sources` + `agents`; flash; `onDeleteSuccess`; on error, an error flash | `:1370-1391` |
| Test (today Refresh) | Refresh disabled until settled; the in-flight form values sent; on ok: invalidate `mcp-sources`, status, LED, tools list, "Last updated", `onListStale`, refetch, Reset visibility, server-info repaint (squawk 0102) | `:1312-1367`, `:1792-2150` |
| `auth_required` (click) | consent block; `window.open` only when `isSafeUrl` (a `null` is fine); same-origin `message` listener; a 500 ms poll for `has_access_token` up to 120 s; re-POST with `noAutoPopup` | `:1841-2023` |
| `auth_required` (auto-run) | a "Sign in" button; `settle()` re-enables Refresh | `:2103-2127` |
| Reset | confirm; DELETE `.../connection`; invalidate `mcp-sources` + `agents`; `onListStale`; refetch; full remount; flash | `:1410-1446` |
| Transport switch | `.is-hidden` toggles; the kv title swap; kv rows kept (env becomes headers) | `:1100-1112`, `:1560-1575` |
| Runtime picker | the custom row and hint; `npx -y` / `pipx run` split on collect and collapsed on hydrate | `:185-219`, `:1704-1732` |
| Sensitive toggle | password and text; the eye added or removed; the masked tail cleared on unmask | `:1504-1541` |
| Dirty mirror | `onDirtyChange` → `state.dirty`; `isDirty = state.dirty && editorOpen()` | `studio.js:688-691` |

**The stable DOM contract** (DD4): every `mf-*` id and `data-field`, and the testids:
- `save-mcp-source-btn`, `cancel-mcp-source-btn`, `delete-mcp-source-btn`, `editor-unsaved`;
- `mcp-test-connection` (moves to the header Test), `mcp-test-status`, `mcp-connection-led`, `mcp-tools-last-updated`, `mcp-tools-list`, `reset-mcp-connection-btn`;
- `mcp-command-runtime`, `mcp-command-custom`, `mcp-command-hint`, `mcp-sandbox-section`;
- `mcp-kv-table`, `mcp-kv-tbody`, `mcp-kv-thead`, `mcp-kv-sensitive-info`, `kv-add-row-btn`;
- `mcp-server-info-section`, `mcp-server-instructions`, `mcp-server-meta`.

A testid that cannot survive the library control (for example `mcp-kv-tbody` inside `keyValueTable`) is retired in the registry in the leg that drops it, with its tests retargeted.

## Visible-Differences Ledger

| # | Leg | Surface | Change | Source |
|---|---|---|---|---|
| 1 | 05 | Every editor on `editorShell` | The editor error is its own full-width line under the header, never inside the button cluster | A1 |
| 2 | 10 | MCP editor | Required-field and 422 errors on the field, with focus to it; plain wording ("Enter a name.", "Choose or enter a command.", "Enter the server's URL.") | A2 |
| 3 | 10 | MCP editor | Sentence case: "New MCP server", "Working directory", "MCP server saved/created/deleted", "Input schema", "Environment variables", "Headers" | A3 |
| 4 | 10 | MCP editor | The subtitle uses the type's label (or the command or URL alone) and updates after Save | A4 |
| 5 | 06 | MCP editor | The command hint is a muted field hint under Command, in plain words | A5 |
| 6 | 08b | MCP editor | Connection status is a status line (dot and text): "Connected · checked 3:42 PM", "Not connected", "Couldn't connect", "Sign-in needed" (clock wording per DD14, not "2 minutes ago": DD9-13) | A6 |
| 7 | 08b | MCP editor | "Reset connection" only when signed in (armed "Reset connection?"); a cached streamable-HTTP server without a sign-in gets "Forget tools list" instead (DD6) | A7, A3 |
| 8 | 08b | MCP editor | The Test result line sits at the end of the Connection section; Tools lists only tools | A8 |
| 9 | 08b | MCP editor | A failed Test sets "Couldn't connect" and "Last connected 3:42 PM", also after reopening the editor (DD6) | A9, survey 0.2 |
| 10 | 06 | MCP editor | "Allow network access" is the library switch, label inline, with a hint | A10 |
| 11 | 07 | MCP editor | Env vars and headers on the library key-value table: named table, named rows and controls, fixed columns, the Sensitive switch | A11 |
| 12 | 07 | MCP editor | No 4 px sideways scroll at 1024 | A12 |
| 13 | 07 | MCP editor | The Sensitive info is the library info toggletip, with the written text | A13 |
| 14 | 06 | MCP editor | Arguments and Writable paths on the library chip list (a muted ×) | A14 |
| 15 | 09 | MCP editor | Tools and Instructions are library disclosures; the description shown once; sub-labels in the field-label style | A15 |
| 16 | 09 | MCP editor | Server facts: Version, Protocol, Offers, Website (the protocol kept, B10) | A16, B10 |
| 17 | 06 | MCP editor (create) | Env vars and Sandbox hidden until a type is chosen | A17 |
| 18 | 08b | MCP editor, agent MCPs tab | A stdio error headline; "then try Test"; one size in both hosts | A18 |
| 19 | 08b | MCP editor | Sign-in wording: "Complete the sign-in in your browser. This page updates when you're done."; "Waiting for sign-in…" after the popup closes | A19 |
| 20 | 11 | Agent MCPs tab | Each server's Tools button is named "Tools for {server}" | A20 |
| 21 | 11 | Agent editor | The tab reads "Built-in tools" | A21 |
| 22 | 10 | MCP editor | Section order: Connection, Env vars or Headers, Sandbox, Server, Tools, Danger zone | B1 |
| 23 | 08b | MCP editor | Refresh connection becomes the header's Test button (edit mode only) | B2 |
| 24 | 06 | MCP editor | Plain type and command choices: "Local program (stdio)", "Remote server (HTTP)", "Choose how it connects", "Python package (uvx)", … | B3 |
| 25 | 06 | MCP editor | Long chip values: middle ellipsis, full value on hover and in the accessible name | B4 |
| 26 | 04/07 | MCP editor | A stored secret shows no eye and "Stored. Type a new value to replace it."; focus selects it, so typing replaces it | B5, defect 14 |
| 27 | 11 | Library list | MCP rows show a state ("Sign-in needed", "Couldn't connect", "{n} tools", "Not connected") and a Local or Remote badge | B6 |
| 28 | 05 | Provider, connector, knowledge and MCP editors | Sentence-case danger buttons ("Delete provider", …) and "Confirm delete?" | B7 |
| 29 | 10 | MCP editor | Delete and Reset errors show as the editor error, not a toast | DD4 |
| 30 | 08b | MCP editor | Reset patches in place: unsaved edits and focus are kept (no remount) | defect 6 |
| 31 | 08b | OAuth callback page | Styled in the system browser (no `/static/` dependency) | squawk 0214 |
| 32 | 04 | Every `keyValueTable` with a secret column | The value field has `autocomplete="new-password"` (no saved-password offers) | DD5 |
| 33 | 10 | MCP editor | Save, Cancel, Create and Test disabled while a request is in flight | defect 5 |
| 34 | 06 | MCP editor | The chip remove × in the muted colour (the library look), not accent purple Arial | A14 |
| 35 | 04/07 | MCP editor | Renaming the key of a stored secret clears its value and asks for it again ("Type the value again for the new name.") | DD5, defect 15 |
| 36 | 05 | Every editor on `editorShell` (page variant too) | A long error wraps on its own row; the title and breadcrumb keep their width | A1 (degenerate case) |

## Leg Progress

### Leg 01: groundwork-and-before-set (landed, 2026-10-25)
- **Move rules** (no `the_one/` change; `git diff main -- the_one/` empty): `tests/_ui_ownership_allowance.py` gains `OwnershipMove`, `START_ROWS`, `MOVES` (empty) and `TOTAL_USES` (45 keys, exact); `tests/test_ui_ownership.py` gains `test_total_uses_are_exact`, `test_new_allowance_rows_are_covered_by_moves`, `test_moves_name_live_rows` and fixture tests; `tests/test_ui_guards.py` gains `SinkMove`/`SnippetMove`, `SINK_TOTAL` (23), `SINK_MOVES`, `SNIPPET_MOVES` (both empty) with `test_sink_total_is_exact`, `test_new_sink_files_are_covered_by_moves`, `test_sink_moves_name_live_rows`, `test_snippet_moves_cover_baseline_changes` and fixture tests. Existing exact tests untouched.
- **Capture tool:** `tests/fixtures/mcp/rich_http_server.py` (modes ok/legacy/401, port 0), `FixtureServers`, `check_fixture_port` (8484, 8485, 8491, instance port), `Surface.widths`, `Surface.needs_mcp`, `seed_mcp()`, sandbox probe, mask rules (port, run id, relative time), manifest fields. 20 new surfaces (17 MCP, 3 `ref-*`); unit tests in `tests/test_ui_capture_safety.py`.
- **Before set:** `$HOME/.cache/the-one-ui-capture/m31-f5-before`, 50 PNGs + manifest.json, 0 failed. Command: `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out $HOME/.cache/the-one-ui-capture/m31-f5-before --surfaces <the 20 names>`. Sandbox backend: BubblewrapSandbox; `git_status_the_one` empty. Seed Tests: Always fails -> `MCPConnectionError: MCP connect failed: MCPError: Connection closed`; Billing API -> `MCPCredentialsRejected ... (401)`. Deviation: failed/rejected states are client-side today, so those two surfaces click Test in `prepare` (real, deterministic); connected ones come from the seed Test. Fixture processes and ports verified gone after the run.
- **Squawk 0259 (quiet-host `--parallel 3`, start load 1.03; 8491 instance stopped before the run):** `PARALLEL_RESULT rc=0 total=1490s lanes=13 failed=-`. routing 513/600, agents 441/540, chats 391/450, mcp 335/450, providers 328/420, contracts-controls 331/420, shared 318/420, knowledge 297/420, agent-tabs 301/360, settings 296/360, settings-tools 268/330, contracts-overlay 243/270, library 165/210. Decision: `chats` budget stays 450 (not over, moved 4%). Quiet-host clause added to CLAUDE.md and `run-tests.sh`.
- **Unit tier:** `make test-unit` 7219 passed, 12 skipped; ruff check and format clean.

### Leg 02: editor-split (landed, 2026-10-25)
- **What:** `mcp-server-editor.js` split, behaviour-free, into eight modules under `js/areas/studio/`:
  - the controller, `mcp-server-editor.js`, 775 lines;
  - `mcp-editor-shared.js` 221; `mcp-server-info.js` 268; `mcp-connection-fields.js` 213; `mcp-sandbox-fields.js` 68; `mcp-env-headers.js` 297; `mcp-connection-status.js` 335; `mcp-oauth-consent.js` 233.

  The line-guard entry is removed.
- **The one seam:** `launchConsentPopup({consentUrl, statusEl, sourceId, settle, rerun})`, where `rerun` is a closure built in `handleTestConnection`. The consent module never names `connectionStatus`. The call-time wrappers reach `oauthConsent` and `App.studio.renderMcpSourceEditor`.
- **Guards:**
  - `MOVES` holds 25 entries, `SINK_MOVES` 4 and `SNIPPET_MOVES` 9, each `retire_by` `M31 F5 L10`;
  - totals unchanged (ownership per key exact; `SINK_TOTAL` 23);
  - pins retargeted: `test_store_static.py` (two files; `invalidate('agents')` 1 + 1) and `test_consent_link_static.py` (the consent module).
- **Verification:** all 50 capture PNGs are pixel-identical to the before set; lanes `mcp` (110) and `library` (51) pass, plus 44 by file; `make test-unit` 7219 passed, 12 skipped. The details are in the Flight Director Notes entry for 2026-10-25.

### Batch B1 review (legs 01-02)
- **Reviewer** (Sonnet tier: the diff moves the secret-handling code; no Accessibility Reviewer, since nothing visible changed): `[HANDOFF:confirmed]`.
  - It diffed main's editor against the union of the eight modules and found only the consent seam changed, with one section-banner comment dropped.
  - It confirmed no alias is captured as `undefined` and no module cycle; the move rules enforce what leg 01 specifies; the capture-tool safety refusals are intact.
  - It re-ran the unit guards (423 passed) and the `mcp` lane (110 passed, 313 s).
- **The one non-blocking gap** (this Leg 02 progress entry) was added by the FD.
- **Checkpoint commit** for B1. Legs 01 and 02 are `completed`.

## Decisions

*(none yet)*

## Flight Director Notes

- **2026-10-25, Architect cycle 1:** approve with changes (`f5-architect-1.md`, FD scratchpad). Every issue was applied:
  - **H1:** the switch deletion moves to leg 07.
  - **H2:** the four guarded chip-list reads are replaced before `tools-form-helpers.js` goes, with a payload test written first.
  - **H3 and H4:** DD6 reworked. One wrapper, `merge_cache`, an inverted pin, no record for an unsaved-form Test, both Studio callers record, invalidation on every outcome. Leg 08 is split into 08a and 08b, and the shared `App.usage.mcpState` is added.
  - **M5:** A1's pins are listed, with the old selector kept until leg 10.
  - **M6:** each surface leg moves its own fields onto handles.
  - **M7:** "Forget tools list" is the stale-hint escape, and A7's predicate is `oauth_active` alone.
  - **M8:** the server part lands before the status line.
  - **M9:** a key rename on a stored secret clears it (defect 15).
  - **M10:** the Test body uses only `__MASKED__`.
  - **M11:** MOVES covers `DYNAMIC_SINK_BASELINE`; the line-guard entry is removed when the file drops; code-text anchors are listed.
  - **L12-L16:** citations corrected; the verification grep scoped and the doc mentions fixed in leg 12; the clock wording replaces relative time (a ledger change to A6/A9, flagged to the operator); deterministic capture failures and 1024 captures; the baseline taken from the response.
  - **The suggestions** were all taken: `runTest`, `destroy` on every remount, and the disclosure contract test named.
  - **The FD's call:** this is substantive, so a second Architect cycle runs.
- **2026-10-25, Architect cycle 2:** approve with changes (`f5-architect-2.md`). The cycle-1 fixes were confirmed in the text, and `merge_cache` was confirmed feasible. Every issue was applied:
  - **H1:** "Sign-in needed" now requires no access token, so a sign-in that finishes while the editor is closed clears it.
  - **H2:** only a body-less Test of the saved server is recorded; the client sends a body only when dirty; the inner route returns `(result, recordable)`.
  - **M3:** "Forget tools list" is streamable-HTTP only, by an explicit predicate; stdio gets neither button.
  - **M4:** leg 05 adds `editorShell` `setTestState`; until leg 10, the 08b Test is a library button in the hand-built header.
  - **M5:** the editor refetches the source after every outcome, behind an identity guard.
  - **M6:** a per-mount `handles` object from leg 03; the dirty wiring moves with each field.
  - **L7:** the lost-update reasoning corrected, and the posture helpers move onto `merge_cache`.
  - **L8:** the editor-and-row match test moves to leg 11.
  - **L9:** the verification grep is scoped, and every doc mention listed.
  - **L10:** 25 rows / 36 uses.
  - **L11:** text fixes.
  - **L12:** the clock wording is raised to the operator.

  This was the second and last design cycle. Nothing unresolved remains apart from the operator's call on the clock wording.
- **2026-10-25, planning.** Loaded the flight skill (plugin 1.2.0) and `.flightops/agent-crews/flight-design.md`. Spawned two read-only survey crew in parallel (code and presentation). Built and published the review page; the operator returned decisions the same day. Recorded the flight spec and this log on `main`'s working tree, uncommitted; they move to the flight branch at flight start.
- **2026-10-25, spec approved by the operator** (including DD9-13's clock wording). Status → `ready`. The planning artifacts and squawk 0260 are uncommitted on `main`'s working tree, and go to the flight branch at flight start.
- **2026-10-25, flight start.** Branch `flight/05-mcp-editor-on-the-library` cut from `main` at `b1e47ae`; status set to `in-flight`. Loaded `.flightops/agent-crews/leg-execution.md` (Developer Sonnet; Reviewer Sonnet for security-sensitive diffs, Haiku otherwise; an optional Accessibility Reviewer).
  - **Execution mode** (the operator's preference, DD12): legs run in batches with scoped checks. Each batch ends with a review and a checkpoint commit, as in Flight 4. The full gate runs at leg 12. The HAT is at the end.
- **Leg 01 tier: high.** It changes the ratchet semantics of the ownership and sink guards that every later leg depends on (the `MOVES` rule). The capture tool work and the lane re-measure are low risk on their own. A Developer design review runs before implementation.
- **Leg 01 design review** (Developer, cycle 1): approve with changes. All applied in place (the leg's Design Review section); status `ready`. The implementing Developer was spawned.
- **Leg 02 tier: high.** It is behaviour-free, but it breaks the consent and Test cycle, rewires about 20 pins and anchors, and is the base for every later leg. Developer design review, cycle 1: approve with changes. All applied in place; status `ready`. It implements after leg 01 lands, because it needs the move rules.
- **The instance on 8491** (pid 2322812, `THE_ONE_DATA_DIR=~/the-one-gf-diag/data`, cwd deleted, running 10 days) is a leftover Goldfinch-diagnosis dev instance. It is not this flight's, so it is left alone, and the operator is asked whether to stop it.
- **The 8491 instance was stopped** on the operator's instruction (2026-10-25): `kill 2322812` after re-checking its environ (`THE_ONE_PORT=8491`, `THE_ONE_DATA_DIR=~/the-one-gf-diag/data`). Port 8491 is free. Its data dir was left in place.
- **2026-10-25, leg 01 landed.** The quiet-host run began at load 1.03 (the host's idle baseline here is about 1.0-1.3 from other sessions; CPU was 98% idle).
- **Leg 01 landed; FD check of the one unverified criterion.**
  - **"Always fails" is deterministic.** The FD re-ran `mcp-edit-stdio-failed` and `mcp-edit-rejected` into `~/.cache/the-one-ui-capture/m31-f5-recheck`. `mcp_seed_tests` matches the before set's manifest, the sandbox backend is `BubblewrapSandbox` both times, and all four PNGs are pixel-identical to the before set (`ImageChops` bbox `None`).
  - **Spot-checked by eye:** `mcp-edit-rejected` and `mcp-edit-http` (light, 1280). They show today's editor as the survey described: the Reset on a non-OAuth server (A7), the bare dot (A6), "streamable-http" in the subtitle (A4).
- **Batch B1 = legs 01 and 02.** The review and the checkpoint commit come after leg 02 lands. Leg 02's Developer was spawned.
- **2026-10-25, leg 02 landed** (editor split; not committed, the batch review and checkpoint commit follow).
  - **Modules** (`js/areas/studio/`): `mcp-server-editor.js` 775 (controller), `mcp-editor-shared.js` 221, `mcp-server-info.js` 268, `mcp-connection-fields.js` 213, `mcp-sandbox-fields.js` 68, `mcp-env-headers.js` 297, `mcp-connection-status.js` 335, `mcp-oauth-consent.js` 233. All under 800. The controller came in at 775, so the `test_area_module_size.py` ALLOWANCE entry was removed (not lowered).
  - **Built by script from line ranges of the original** (moved verbatim); only references, explicit parameters and a few wrappers changed. Cross-module calls use local aliases with the original identifiers, so every pinned anchor and `DYNAMIC_SINK_BASELINE` snippet keeps its text.
  - **Deviations from the table:** (1) `renderConnectionActions(source)` in `connectionStatus` returns the Refresh/Reset/LED/Last-updated row including its stdio/streamable-http condition (the controller just does `html += renderConnectionActions(source)`); (2) `renderSandboxSection(source, type)` in `sandboxFields`; (3) `connectionStatus` loads before `oauthConsent` (table order), so it calls the consent module and `App.studio.renderMcpSourceEditor` through call-time wrappers (`launchConsentPopup`, `renderMcpSourceEditor`), never cached at load; (4) `launchConsentPopup({consentUrl, statusEl, sourceId, settle, rerun})`, with `rerun` a closure built in `handleTestConnection`; the consent module never names `connectionStatus`; (5) `envHeaders.wire(container, onChange)` owns `nextRowIdx`; the controller passes `checkDirty`.
  - **Guards.** Allowance: 25 `MOVES` entries (all `retire_by` `M31 F5 L10`), measured from the guards' output: ownership totals unchanged (e.g. `api:App.confirmDelete(` 1+1, `api:App.icon(` 1 controller + 1 status + 6 env/headers, `api:App.showFlash(` 3+2). `SINK_MOVES` 4 entries (fields 2, status 7, env-headers 4, server-info 1; the controller keeps 4; whole-app sinks stay 23). `SNIPPET_MOVES` 9 entries. Pins retargeted: `test_store_static.py` (connect window stays in the controller, Reset window and the test-connect row point at `mcp-connection-status.js`, the `invalidate('agents')` minimum is two rows, 1 + 1), `test_consent_link_static.py` (consumer list and the `isSafeUrl(consentUrl)` window read `mcp-oauth-consent.js`), `_ui_guard_helpers.py` comment, CSS and `tools-form-helpers.js` comments, `docs/ui-control-inventory.md` and `the_one/agents.md` paths (paths only; the content changes in leg 12).
  - **Verification.** Static guards (ui_guards, ui_ownership, area_module_size, store_static, consent_link_static, index_asset_cache_busting, token_definitions, design_tokens_a11y): 396 passed. Browser (netns): lane `mcp` 110 passed, lane `library` 51 passed, `test_flow_chiplist_label_resolver.py` + `test_oauth_modal_flow.py` + `test_studio_mcps_tab.py` 44 passed. Capture compare: the 20 MCP/reference surfaces (50 PNGs) retaken into `m31-f5-split`, PIL `ImageChops` bbox `None` on all 50. `make test-unit`: 7219 passed, 12 skipped. ruff check and format clean.
  - **`git grep -n "mcp-server-editor" tests/ scripts/ Makefile docs/ tests/behavior/ the_one/ CLAUDE.md`, by file (hits left on purpose):** `tests/_ui_ownership_allowance.py` (80: controller rows, START_ROWS, MOVES `from_file`), `tests/test_ui_guards.py` (18: controller rows and move `from_file`), `tests/test_store_static.py` (4: controller anchors), `the_one/agents.md` (4: the registry-shaped-surfaces note, the `checkDirty` list, the invalidation rows for save and delete), `docs/ui-control-inventory.md` (1: the editor shell still hand-built in the controller), `index.html` (1: the script tag), browser test comments (6, line-number citations, comments only). The spec's 8 agents.md / 7 inventory hits were retargeted where the code moved. Not touched: `CLAUDE.md`, `scripts/`, `Makefile`, `tests/behavior/` have none.
  - **Not done / for later legs:** no `destroy`, no guards, no behaviour change; the string-equality script was skipped because the 50-PNG pixel compare (create, edit, OAuth sign-in, rejected, stdio-failed surfaces) is the backstop.
