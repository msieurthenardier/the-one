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
| 8 | 08b | MCP editor | The Test result line sits at the end of the Connection section; Tools lists only tools; the "Server exposes N tools." line goes (the status line says Connected, and Tools lists them) | A8 |
| 9 | 08b | MCP editor | A failed Test sets "Couldn't connect" and "Last connected 3:42 PM", also after reopening the editor (DD6) | A9, survey 0.2 |
| 10 | 06 | MCP editor | "Allow network access" is the library switch, label inline, with a hint | A10 |
| 11 | 07 | MCP editor | Env vars and headers on the library key-value table: named table, named rows and controls, fixed columns, the Sensitive switch | A11 |
| 12 | 07 | MCP editor | No 4 px sideways scroll at 1024 | A12 |
| 13 | 07 | MCP editor | The Sensitive info is the library info toggletip, with the written text | A13 |
| 14 | 06 | MCP editor | Arguments and Writable paths on the library chip list (a muted ×) | A14 |
| 15 | 09 | MCP editor | Tools and Instructions are library disclosures; the description shown once; sub-labels in the field-label style | A15 |
| 16 | 09 | MCP editor | Server facts: Version, Protocol, Offers, Website (the protocol kept, B10) | A16, B10 |
| 17 | 06 | MCP editor (create) | Env vars and Sandbox hidden until a type is chosen | A17 |
| 18 | 08b | MCP editor, agent MCPs tab | A stdio error headline; "then try again" (correct in both hosts: the editor's Test and the tab's refresh); "address and headers" for HTTP; one size in both hosts | A18 |
| 19 | 08b | MCP editor | Sign-in wording: "Complete the sign-in in your browser. This page updates when you're done."; "Waiting for sign-in…" after the popup closes. The consent-link text is shared, so chat's sign-in block shows the same fixed wording | A19 |
| 20 | 11 | Agent MCPs tab | Each server's Tools button is named "Tools for {server}" | A20 |
| 21 | 11 | Agent editor | The tab reads "Built-in tools" | A21 |
| 22 | 10 | MCP editor | Section order: Connection, Env vars or Headers, Sandbox, Server, Tools, Danger zone | B1 |
| 23 | 08b | MCP editor | Refresh connection becomes the header's Test button (edit mode only) | B2 |
| 24 | 06 | MCP editor | Plain type and command choices: "Local program (stdio)", "Remote server (HTTP)", "Choose how it connects", "Python package (uvx)", … | B3 |
| 25 | 06 | MCP editor | Long chip values: middle ellipsis, full value on hover and in the accessible name | B4 |
| 26 | 04/07 | MCP editor | A stored secret shows no eye and "Stored. Type a new value to replace it."; focus selects it, so typing replaces it | B5, defect 14 |
| 27 | 11 | Library list | MCP rows show a state ("Sign-in needed", "Couldn't connect", "{n} tools", "Not connected") and a Local or Remote badge | B6 |
| 28 | 05 | Provider, connector, knowledge and MCP editors | Sentence-case danger buttons ("Delete provider", …) and "Confirm delete?"; the agent editor's "Delete agent" too (operator yes, 2026-10-25; done in leg 11) | B7 |
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

### Leg 06: connection-and-sandbox-fields (landed, 2026-10-25)
- **Tests first, on the unchanged tree.** The payload tests (`-k payload`, five: create `npx -y` with a user arg and a writable path; create `pipx run` with two paths; edit a seeded `npx -y` source with args `['-y','pkg','--flag']`, change only the name, `config.args` unchanged; edit and add a chip to each list; an "Other command..." source with args) plus the stored `network_allowed: false` Cancel test: **6 passed on the unchanged tree** (leg 05 code, string-built chip lists). Defect 7 (`test_chip_edit_after_cancel_is_tracked_as_dirty`, args and writable paths): **2 failed on the unchanged tree**, both at the second chip removal after Cancel (`Save` stayed disabled and the caption stayed empty: the Cancel revert re-mounted the chip lists with a no-op `onChange`). Both pass after the fix. The server-label test (`test_types_endpoint_returns_two_transports`, exact labels) was changed in the same step.
- **Modules (all under `js/areas/studio/`; line counts):** `mcp-connection-fields.js` 187: `create({source, mcpTypes, onChange, onTypeChange}) -> {el, values(), setValues(source), setError(field, msg|null), focus(field), setType(type), destroy()}`; `mcp-sandbox-fields.js` 68: `create({source, onChange}) -> {el, values(), setValues(source), setType(type), destroy()}`; `mcp-env-headers.js` 314 gains `setType(container, type)` (the title swap and the A17 hide, section testid `mcp-env-headers-section`); `mcp-editor-lifecycle.js` 60 gains `mount.onDestroy(fn)` (a disposer list run once by `destroy`); `mcp-editor-shared.js` 220 (A5/B3 texts). **Controller `mcp-server-editor.js` 676 lines** (798 before, target 760): `getFormSnapshot`, `collectFormData` and `revertEditorToSource` read and write the fields through `handles.connectionFields` / `handles.sandboxFields`; the dirty wiring is the modules' `onChange` through a late-bound trampoline; `attachStaticListeners` (and its `.field-input` / `.field-select` selectors) is gone, so no field has a second listener; the type fan-out is the connection module's own select handler (it calls its own `setType`, then `onTypeChange` -> `sandboxFields.setType` and `envHeaders.setType`, so the controller never calls `connectionFields.setType` itself).
- **Handover (DD11), in order, payload tests re-run after the reads were replaced (6 passed) and again at the end:** (1) payload tests; (2) the four guarded `App.adminFormHelpers` reads replaced by handle reads (snapshot, collect, revert, mount); (3) `js/areas/admin/tools-form-helpers.js` deleted with its `index.html` tag and its three ownership rows (`chip`, `chip-list-editor`, `chip-list-input`); `git grep "adminFormHelpers\|tools-form-helpers\|renderChipListEditor" the_one/interfaces/web/static` finds only a historical comment in `js/ui/chip-list.js` (reworded) and none that name the symbols; (4) `tests/test_tools_form_helpers_assets.py` inverted (the file is gone, `index.html` does not reference it, no script names the helper namespace); (5) the two legacy-parity tests in `test_ui_chip_list_contract.py` retired with the reason written in the file (`test_computed_styles_equal_legacy_area_studio`, `test_string_built_chip_list_keeps_the_area_look`) and their now-unused `LEGACY_LOCKED_CHIP_CSS` fixture deleted; (6) the `studio.css` `:not(.ui-chip-list)` chip-list rules deleted (64 lines) and the 5 allowance keys with them (`chip`, `chip-list-editor`, `chip-list-input`, `ui-chip-list`, `ui-chip-list-input`); (7) `FIELD_FOR_ID_HELPER_INDIRECTED` is now empty (the library emits `inputId`; the runtime guard `test_flow_chiplist_label_resolver.py` still proves `label[for]` resolves); (8) the legacy switch CSS stays for leg 07. Docs: the catalogue chip-list row, `the_one/agents.md` (4 mentions), `CLAUDE.md`, `js/ui/chip-list.js` comment, the testid registry (`mcp-env-headers-section`).
- **Retargeted pins (none deleted or relaxed):** about 20 `is-hidden` class assertions (`.mcp-stdio-only`, `.mcp-streamable-http-only`, `.mcp-command-custom-row`, the sandbox section) became `to_be_hidden()` / `to_be_visible()`; `.chip-remove` -> `.ui-chip-remove`; the computed-colour pin re-derived for the muted x (`--fg-secondary`, ledger rows 14 and 34; the fill stays `--accent-translucent`); the hint assertions follow A5's texts; the network switch tests (`check()` / `uncheck()` on the input) now click the switch's label (the library toggle's track covers its visually hidden input, as in the connector editor tests). The kv thead `is-hidden` pins stay (leg 07).
- **New tests** (`test_flow_studio_mcp_editor.py`, lane `mcp`): the payload set, defect 7, `test_stored_network_off_cancel_returns_it_to_off`, type and runtime labels plus the placeholder hidden from the open list (B3), each runtime hint matches its option / linked by `aria-describedby` / under Command / no backtick, "operator", "container" or "Fetched +" (A5, 7 parametrized), field labels and order (A3), create with no type shows only Name and Type through `get_by_role` counts and hides the env and sandbox sections (A17), the network switch (`role=switch`, name, inline, hint, Space, dirty), long chips with a 90-character argument and an 87-character path (B4), Enter / comma / Backspace / paste-split and the select's typeahead (DD10), switching the type keeps the args and Cancel restores the stored type's rows.
- **Runs:** `mcp` lane 143 passed; `library` 51; `routing` 184 (the leg touches `data-field` users there); `test_flow_chiplist_label_resolver.py` + `test_ui_chip_list_contract.py` (both engines, `THE_ONE_REQUIRE_WEBKIT=1`) + `test_studio_mcps_tab.py` 68; `test_router_announce.py` 14. `make test-unit` (no netns) **7221 passed, 12 skipped** (7219 at leg 01; +2 from the inverted asset test). Ruff check and format clean.
- **Guard totals before -> after:** ownership allowance 84 rows / 167 uses -> 63 rows / 103 uses (`TOTAL_USES` 167 -> 103); `MOVES` 25 -> 16 entries; HTML sinks 23 -> 19 (`SINK_TOTAL`; `mcp-connection-fields.js` 2 -> 0, the controller 4 -> 2); `SINK_MOVES` 4 -> 3, `SNIPPET_MOVES` 9 -> 7. `mcp-connection-fields.js` and `mcp-sandbox-fields.js` have zero sinks and zero allowance rows. Every `mcp-*.js` file is 800 lines or fewer.
- **Captures** (`m31-f5-l06`, 50 PNGs, 0 failed; compared with `m31-f5-l03` by `ImageChops`): 8 identical (`agent-mcps-full` x2, `mcp-library-list` x2, `ref-connector-danger-armed` x2, `ref-provider-danger-armed` x2); `ref-provider-long-error` x2 differ from `l03` and are identical to `l05` (leg 05's rows 1 and 36, not this leg). The rest, by surface: `mcp-edit-http`, `-http-open`, `-legacy`, `-rejected`, `-reset-armed`, `-signin`, `-signin-after-create` (14 PNGs) and `-save-error` (2): only the Type select's text, "Streamable HTTP" -> "Remote server (HTTP)" (row 24); `mcp-create-http` (4): the Name placeholder "My MCP server" (row 3) and the Type text (row 24); `mcp-create-empty` (4): the placeholder (3), "Choose how it connects" (24), and the env and sandbox sections gone (row 17); `mcp-create-stdio` (4): rows 3, 5 (hint under Command, plain), 10 (the switch inline with its hint), 24 (Type and Command labels), and the shorter page they cause; `mcp-edit-stdio` (4, 78 and 101 px shorter), `-stdio-failed` (2), `-dirty` (2), `-danger-armed` (2): rows 3, 5, 10, 14 and 34 (library chips, muted x), 24, 25 (the 90-character argument and the 87-character paths in the middle ellipsis) and the layout those cause. Nothing differs that is not on one of the rows 3, 5, 10, 14, 17, 24, 25 or 34. Knock-ons judged as part of their rows: the Refresh row now follows Arguments directly (the hint row left it); the Sandbox section uses the library `section` stack spacing (row 10). The old `title` tooltip on the network switch ("Network access enabled/disabled") is gone, as intended (A10's inline label replaces it).
- **Ledger status (leg 06):** row 3 (field labels share only: "Working directory", the Name placeholder; the title, subtitle and flash wording stay leg 10): visible, matches. Row 5: visible, matches (a muted hint under Command; each option has its own plain text). Row 10: visible, matches. Row 14: visible, matches. Row 17: visible, matches (create with no type shows Name and Type only; the Connection title, the header and Cancel remain). Row 24: visible, matches (server labels in `api.py`, runtime labels in `mcp-editor-shared.js`; "Choose how it connects"). Row 25: visible, matches. Row 34: visible, matches. **No visible change outside the ledger rows.**
- **Judgment calls:** (1) the env and headers section titles keep today's wording ("Environment Variables", "Custom Headers"); the sentence-case change is row 3's other share, which belongs to leg 10. (2) `onTypeChange` is called by the connection module after it has run its own `setType`; the controller fans it out to the two other modules only. (3) A hidden stdio field's value still counts in the snapshot (as before), so changing the Custom command text while another runtime is selected marks the form dirty.

### Leg 07: env-and-headers (landed, 2026-10-25)
- **Tests first, on the leg 06 tree** (security-sensitive leg). Payload tests 1-12 plus the attribute scan were written into `tests/browser/test_flow_studio_mcp_editor.py` and run before any product change (`-k "payload or no_attribute"`, 22 cases with test 11's five parameters): **5 failed, 17 passed**.
  - **Failed first, and why:**
    - **test 6** (rename a stored secret, defect 15): the value kept its mask under the new key, so the UI did not clear it (the `to_have_value("")` check failed). The payload it would send is `__MASKED__` under the new key, which the server drops (the key does not exist), and the old key is omitted, so the secret is lost silently;
    - **test 7** (defect 4, edit mode): after Save the row kept the typed secret and an empty `_originalMasked`, so it was not re-masked (`to_have_value("***...wxyz")` failed); unticking Sensitive then could not clear it, so the secret would move into plaintext `config.headers`;
    - **test 9** (Cancel after a Save, H1): Cancel rebuilt the table from the stale `source`, so the deleted `X-Gone` came back and the saved `X-New` row vanished (`['X-Gone', 'X-Keep']`);
    - **test 10** (edit during an in-flight Save, H2): the post-Save snapshot absorbed the edit, so Save read disabled and the form clean;
    - **the attribute scan**: four attributes held mask text (`value=` and `data-original-masked=` on the value inputs).
  - **Passed first, as the spec expected:** tests 1-5, 8 (the Test body already sends `__MASKED__`, never `***`), 12 (a cleared stored value saves as `''`; unchanged behaviour, recorded here) and **all five test 11 cases** (the old Save recaptured the snapshot from the live form, so it already read clean; the new module baseline keeps that and adds H2). Test 2 asserts the stored mask and the sensitive state through selectors that read the same on both markups; the stored-mode UI (no eye, the hint) is asserted in the new UI tests.
  - **On the new tree: 22 of 22 pass.** No payload assertion was weakened.
- **Module** `mcp-env-headers.js` (298 lines, was 314): `envHeaders.create({source, type, onChange}) -> {el, values(), isDirty(), revert(), setType(type), partition(plain, secrets), remaskAfterSave(submitted, response), destroy()}`. `el` is an `App.ui.section` (`mcp-env-headers-section`, "Environment variables" or "Headers") holding one `App.ui.keyValueTable` (`mcp-kv-table`, `kv-add-row-btn`, the Sensitive column with an `App.ui.infoButton`, the `th` named exactly "Sensitive" with `aria-label`). Every row has a module `_rid`; the baseline is the module's own; `partition` returns the per-row record that the controller stashes at the Save click (`handles.lastPartition`). Judgment calls: (1) a sensitive row the server dropped (`__MASKED__` sent, key not in the response) also clears its value, not only `_originalMasked` (a mask-shaped text in a plain field would mislead); (2) the Sensitive column is 120px: the library's 88px toggle column wrapped the header (the label plus the info button), so the library gained an optional column `width` (a CSS length; the catalogue row, a contract test, both engines), the only library change.
- **Controller** `mcp-server-editor.js` 640 lines (was 676): the env and headers markup, `nextRowIdx`, `wire`, the kv parts of `getFormSnapshot`, `collectFormData` and `revertEditorToSource`, and the `tbody.innerHTML` sink are gone. `checkDirty`, `recaptureSnapshot` and the Save success path read `fields snapshot OR envHeaders.isDirty()`; the Save success path runs `remaskAfterSave`, then `recaptureSnapshot`. Cancel runs `revertEditorToSource` (`setType`, then `envHeaders.revert()`), then `recaptureSnapshot`, then the focus restore.
- **Ledger status (leg 07):** row 11 visible, matches (named table "Headers" / "Environment variables", named rows, fixed columns, the Sensitive `role=switch`); row 12 visible, matches (`scrollWidth <= clientWidth` at 1024 is a test); row 13 visible, matches (toggletip, press-only, the written text); row 26 visible, matches (no eye on a stored secret, the hint); row 35 visible, matches (rename clears the value, hint "Type the value again for the new name."). **Row 3 share done here:** the section titles are sentence case ("Environment variables", "Headers"; they were "Environment Variables" / "Custom Headers"); the rest of row 3 stays with leg 10. Defects 4 and 15 fixed with tests.
- **Deletions.**
  - `studio.css`: the `.mcp-kv-*` and `.kv-remove-row-btn` rules (including `.mcp-kv-th-sensitive .field-info-icon` and its allowance row) and the whole legacy iOS switch block (`.tool-enable-switch*`, DD10). Before deleting: `git grep tool-enable-switch` found no JS user (the last, `mcp-env-headers.js`, was rewritten); the owning lanes ran after the deletion (`mcp` 164, `agents` 161, `contracts-overlay` 510 + 1 skipped, `contracts-controls` 954 + 4 skipped, plus `test_studio_mcps_tab`, `test_deep_violet_computed_styles` and `test_ui_tile_contract` 98).
  - **Pins retargeted, none dropped:** `test_design_tokens_a11y.py`'s three `.tool-enable-switch` pins (on-track `--accent-fill` not `--accent`; off-track `--control-border` not `--border-strong`; thumb `--control-thumb` not `--fg-on-accent`) are the library toggle's own pins (`.ui-toggle-input:checked + .ui-toggle-track`, `.ui-toggle-track`, `.ui-toggle-track::after`), which already existed in the same list, so every pair stays gated; `test_deep_violet_computed_styles.py` drops the two legacy `tr-studio-*` rows (the `tsw-*` rows assert the identical colour pairs on `.ui-toggle-track`); `_legacy_tool_css.py` is kept (the tile-contract fixture at `test_ui_tile_contract.py:681` still carries the legacy switch markup and reads its frozen copy), with the reason in both files; `test_ui_key_value_table_contract.py` froze the deleted `.mcp-kv-*` rules as `LEGACY_KV_CSS` for its two parity tests (the legacy class `mcp-kv-thead` renamed `legacy-kv-head` in the fixture because the retired-selector guard fences the old id).
  - Docs: the "Legacy toggle 1" catalogue row removed; catalogue rows 45, 58 and the key-value table row updated (the "hand-built copy" notes and "intentional duplicates until Flight 5"); `components.css` comments (`:329`, `:2450`); `agents.md` (`:1914`, `:2083`, `:2309`, and a new "MCP environment variables and headers" paragraph); the testid registry rows for the two toggle testids; the comments in `test_flow_admin_tools_editor.py` and the two `test_studio_self_configuration_*` files.
  - **Retired testids** (registry "Retired testids" table and `RETIRED_SELECTORS`, which `test_retired_selectors_cover_the_registry_retired_table` pins together): `mcp-kv-tbody`, `mcp-kv-thead`, `mcp-kv-sensitive-info`. Added: `mcp-env-headers-section` kept, `mcp-kv-table` and `kv-add-row-btn` kept with registry text.
  - `git grep` for `mcp-kv-`, `kv-remove-row-btn`, `kv-key-input`, `kv-value-input`, `kv-sensitive` and `tool-enable-switch` under `the_one/interfaces/web/static/` finds only the kept testid `mcp-kv-table` (the `testid:` option and the module header comment in `mcp-env-headers.js`); the leg's "finds nothing" criterion reads past that kept testid.
- **Guard totals before -> after:** ownership allowance 63 rows / 103 uses -> **56 rows / 86 uses** (`TOTAL_USES` 103 -> 86); `MOVES` 16 -> 10 entries; HTML sinks 19 -> **14** (`SINK_TOTAL`; `mcp-env-headers.js` 4 -> 0, the controller 2 -> 1); `SINK_MOVES` 3 -> 2, `SNIPPET_MOVES` 7 -> 3. `mcp-env-headers.js` has zero sinks and zero allowance rows. Every `mcp-*.js` file is 800 lines or fewer (largest `mcp-server-editor.js` 640).
- **New tests** in `test_flow_studio_mcp_editor.py` (lane `mcp`): the 12 payload tests (22 cases), the attribute scan, and the UI set (Sensitive header name and toggletip, row names and the eye's `aria-pressed`, stored hint and rename hint, no sideways scroll at 1024, trash icon, the library switch, section order, the type switch moving rows); the thead assertions became `table.locator("thead")`. `test_ui_key_value_table_contract.py` gained the column `width` test.
- **Runs:** `mcp` 164 passed; `library` 51; `agents` 161; `contracts-controls` 954 passed + 4 skipped and `contracts-overlay` 510 + 1 skipped (`THE_ONE_REQUIRE_WEBKIT=1`, both engines); `test_studio_mcps_tab.py` + `test_deep_violet_computed_styles.py` + `test_ui_tile_contract.py` 98 passed; the static guards (`test_ui_guards.py`, `test_ui_ownership.py`, `test_nav_helper.py`, `test_ui_control_inventory.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`) pass; ruff check and format clean. `make test-unit` (host-native, no netns): **7218 passed, 12 skipped** (7221 at leg 06; the legacy-switch pins and the env table tests are browser tier).
- **Captures** (`m31-f5-l07`, 50 PNGs, 0 failed; compared with `m31-f5-l06` by `ImageChops`): 20 identical (`agent-mcps-full`, `mcp-create-empty`, `mcp-create-stdio` at both widths and themes, `mcp-edit-stdio-failed`, `mcp-library-list`, `ref-*`). The 30 that differ all differ only inside the env and headers table or its title: `mcp-create-http` x4 and `mcp-edit-legacy`, `-signin`, `-signin-after-create` x2 each (only the title wording "Custom Headers" -> "Headers", a 113 x 9 px region: row 3's share); `mcp-edit-http` (4), `-rejected`, `-reset-armed`, `-save-error` (2 each) (the table: rows 11, 12, 13, 26, with the lower sections shifted by the table's new height); `mcp-edit-stdio` (4), `-dirty`, `-danger-armed`, `-http-open` (2 each), whose page grew by 19 px (the stored-secret hint line, row 26, and the Sensitive header row). Judged against the rows: the Sensitive header is one line with the info button beside it; a stored secret shows no eye and the hint; columns are fixed. A first capture showed the "SENSITIVE" header wrapping the info button onto a second line at 88px, which is why the column `width` option was added.
- **Behavior spec** `tests/behavior/mcp-sensitive-headers-round-trip.md` drafted (status draft; 8 steps; dedicated dev instance on 8486 or higher, a scratch data dir under `$HOME`; browser plus API observables); leg 12 runs it. It was not run.
- **Squawk candidate (for the debrief, from the leg's Edge Cases):** a typed secret that looks like a mask (`***` or `***...abcd`) matches the server's `_looks_masked`, so a PUT silently keeps or drops it, while the Test override recognises only the literal `__MASKED__`. The server's contract; not fixed here.

### Leg 08a: connection-check-record (landed, 2026-10-25)
- **Tests first** (security-sensitive leg). `tests/test_mcp_last_check.py` (14 tests) and the renamed, inverted pin were written and run on the leg 07 tree before any product change: **10 of 14 new tests failed** (`merge_cache` missing: the three `merge_cache` tests, the sequence/PUT/Reset test, the posture-helper test whose `updated_at` was bumped by `repo.update`, `test_recording_failure_is_swallowed`; no `last_check` recorded: the ok, error, auth_required (stubbed inner missing) and 404/invalid-body tests) and the inverted pin `test_stdio_test_connect_error_records_last_check_only` failed (`_cache` was `None`). Passing first, as expected: the body-ful, secrets-only, unknown-status and no-secret-in-response tests (nothing recorded yet). The `updated_at` bump in the posture-helper test is the old `repo.update` stamping, which `merge_cache` removes.
- **Pin:** `test_stdio_test_connect_surfaces_connection_error` renamed `test_stdio_test_connect_error_records_last_check_only` and inverted: `_cache == {"last_check": {...}}` with status `error` and a float `at`, no tools. Never deleted.
- **Server:** `MCPSourceRepository.merge_cache(source_id, fields, delete=())` (one `write_transaction`, config only, `updated_at` untouched, `None` stored, `KeyError` when missing). `test_mcp_connection` is now a wrapper over `_test_mcp_connection_inner -> (result, recordable)`; `recordable = not body_bytes`, forced false at the unsupported-type return (the invalid-JSON and non-object returns already have a body). The three ok-branch writes and both posture helpers go through `merge_cache`; the DD2 comment now says the editor sends a body only when dirty. The inner split was done by rewriting its 16 return points mechanically (AST positions), then `ruff format`.
- **Intended behaviour change:** the Phase A/B ok write no longer drops an existing `auth_posture` (tested: `test_http_phase_a_ok_records_and_keeps_oauth_posture`).
- **Deviation:** the spec asked for a test of the unsupported-type return not recording. That branch is unreachable through the API (the `MCPSource` model admits only `stdio` and `streamable-http`, and a body with another type 500s in `MCPSource(...)` construction before the branch), so it is covered by the `False` flag in code only. The auth_required outcome is tested with the inner function stubbed (the wrapper's recording is what is under test; the real Phase B path is covered by the existing OAuth tests, which still pass).
- **Client:** `App.usage.mcpState` / `mcpStateLabel` in `store.js` (DD6 precedence verbatim, `checkedAt` in seconds). `runTest` checks dirtiness first (snapshot differs or `envHeaders.isDirty()`): clean posts no body and does not call `collectFormData`; dirty collects and sends. `rerun` already re-sends the captured `formData`, so a sign-in from a dirty form never records. `handleTestConnection` invalidates `mcp-sources` on every outcome (before the torn-down return) and calls `opts.onListStale` once for a non-ok outcome (an ok reaches `callbacks.onListStale` through `onSuccess`, once). `agent-data.js` invalidates on every outcome.
- **Store pins:** `tests/test_store_static.py` rows retargeted. Editor row end anchor `"renderToolsListHtml(data.tools)"` -> `"if (!live && data.status !== 'ok') return;"`; agent row end anchor `"return data;"` -> `"if (data.status === 'ok') {"`. New assertions in `test_mcp_list_stale_callback_follows_the_non_save_invalidations` for invalidate-then-`opts.onListStale()`-then-torn-down-return and `onListStale: callbacks.onListStale`.
- **Browser tests:** `tests/browser/test_store_mcp_state.py` (17-row table plus null-tolerance and labels; picked up by the `routing` lane's `test_store*` glob), and in `test_flow_studio_mcp_editor.py` the body rule (clean: no body and empty `.editor-error`; dirty: body with the typed URL) and the every-outcome list refetch (error and auth_required, parametrized).
- **Docs:** `agents.md` "MCP error translation" gains "The last connection check from Studio". `CLAUDE.md` unchanged (no new route).
- **Runs:** unit 15 in the new file; related MCP/OAuth unit files 73 passed; `make test-unit` 7233 passed, 12 skipped (includes `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_store_static`); lanes `mcp` 167 (was 164, +3), `agents` 161, `library` 51, `routing` 186 (was 184, +2); `contracts-controls` not run (nothing under `js/ui/` touched). ruff check and format clean. Guard totals unchanged (no new HTML sinks or ownership rows).

### Leg 08b: connection-status-and-sign-in (landed, 2026-10-25)
- **Tests first** (high-risk leg: sign-in, focus, a callback page). 19 new browser tests in `test_flow_studio_mcp_editor.py` (the status line against `App.usage.mcpState` for each seeded state, A9 with a reopen, Test in the header, A8 placement, the Tools list kept when a Test starts, a dirty Test's note, defect 9, A18 per transport, the Reset and Forget predicates, both patching in place, the session hold for Reset and Forget, label restore after a failed sign-in, the optimistic line) and `tests/test_oauth_callback_page_static.py` (4 tests) were run on the leg 08a tree (HEAD 66193d0) before any product change: **all 19 browser tests failed** (no `mcp-connection-status` element, Test still the old Refresh button in the Connection section, the result area inside Tools and visible at rest, `hasOAuthState` still true on a cache, no Forget button, no hold label, `address and key` headline) and **the first callback test failed** (the page linked three `/static/` assets; `-x` stopped the file there, and all four pass on the new tree). After the change: 19 of 19 and 4 of 4 pass, with no assertion weakened.
- **Client:**
  - `mcp-connection-status.js` is rewritten as `create({container, mount, callbacks, getSource, testBtn, setError, titleEl})` (362 to 438 lines): the `App.ui.status` line (`mcp-connection-status`, LED `mcp-connection-led` decorative, `data-state` the LED state, `data-mcp-state` `mcpState`'s state; words from `App.usage.mcpStateLabel`; clock through `App.time.formatClock`, with the date when not today), the result area (`mcp-test-status`, inside the Connection section directly after the status row, hidden at rest and after a success, no role of its own: the transient text is an inner `role=status` span and the error block keeps its `role=alert`), Reset and Forget (built once on first need through `App.ui.button` plus a `span[data-confirm-title]`, confirmed through `App.ui.confirm` with the server name as `announceName`, then only `hidden` toggled), the identity-guarded refetch after every outcome through `getSource()` and `App.ui.util.latest()`, and the Test flow. The Tools list is not cleared when a Test starts; Reset and Forget empty it and show "Press Test to load this server's tools.".
  - `hasOAuthState` is exactly `streamable-http && oauth_active === true` (no `_cache` fallback); `formatTimeAgo` and the managed-key list are deleted from `mcp-editor-shared.js`.
  - `mcp-editor-lifecycle.js`: `setSession` holds Test (disabled, "Waiting for sign-in…" replacing the label's text node, the icon kept); `endSession` restores the label (also on a destroyed mount) and state; `onSessionChange(fn)` lets Reset and Forget follow (disabled during a session). One text, "Waiting for sign-in…", for the Test label, the first status text and the popup-closed text.
  - `mcp-oauth-consent.js` is on `App.ui.consentLink.build/focusTarget/isSafeUrl` (no alias); its retry "Sign in" is an `App.ui.button`. Popup rules unchanged: `window.open` still runs synchronously where the manual path reaches it, no auto-popup on the auto-run path, a `null` return is not a failure, `isSafeUrl` gates it, the same-origin check and the 120 s ceiling stay.
  - `mcp-server-editor.js` (648 to 579 lines): Test is an `App.ui.button` (`play`) inserted before Cancel, edit mode only; no Refresh; `collectFormData(..., {silent: true})` returns `{error}` and writes nothing (defect 9: the message goes to the result area and no request is sent); `setBusy` also blocks Test.
  - `mcp-error.js`: `mcpErrorMessage(raw, {transport})` and `buildMcpError(raw, {transport})` (A18); `mcps-tab.js` passes the source's type; `.mcp-tools-error` gets `font-size: var(--font-size-body-sm)` (12 px in both hosts, tested). `ui/consent-link.js`: "Complete the sign-in in your browser. This page updates when you're done." (A19; chat shows it too).
  - CSS: dead `.mcp-test-row`, `.mcp-connection-actions`, `.mcp-tools-last-updated`, `.mcp-refresh-connection-btn` and `.mcp-tools-status` removed, `.mcp-connection-state`, `.mcp-connection-status-row`, `.mcp-test-result`, `.mcp-test-note` and `.mcp-tools-empty` added. `scripts/unused_selectors.py studio.css`: `unused (0)`, `dynamic (0)`.
- **Server:** only squawk 0214: `_render_oauth_callback_page` links nothing under `/static/`; inline styles with an explicit token subset (light, plus a `prefers-color-scheme: dark` override; the system font stack; `--radius-lg` where the old `--panel-radius` named a token that never existed), pinned to `tokens.css` and `fonts.css` by the unit test.
- **Squawks:** 0214 and 0216 are `completed` (corrective action, verification; the Disposition sections removed). 0216's two racing assertions in `test_mcp_test_connection_button.py` now hold the response with `page.route` until "Testing connection…" is asserted. Both squawks' Sign-Off verdict and commit read `pending` until the batch review and commit.
- **Retargets (none deleted):** `test_flow_studio_mcp_editor.py` ("Server exposes" to the Tools list or the status line, "Last updated" to the status line's clock, "Refresh connection" to the header Test, "Confirm Reset?" to "Reset connection?", "Awaiting" and "Finalizing sign-in" to "Waiting for sign-in", the late-Test probe to the status line, the Reset test now asserts the same controller and the kept edit instead of a re-mount), `test_mcp_test_connection_button.py`, `test_flow_studio_library_list.py` (the save-create tools state), `test_ui_copy_contract.py` (A19), `test_studio_mcps_tab.py` (two new tests: A18 per transport, one size in both hosts), `test_store_static.py` (the connect and Reset windows now in the status module; the Reset row ends at the identity check), `test_nav_helper.py` (`mcp-tools-last-updated` retired), `docs/ui-testid-registry.md` (added `mcp-connection-status`, `forget-mcp-connection-btn`; rows rewritten; one retired row).
- **Guards:** ownership 56 rows / 86 uses (`MOVES` 10) to **47 rows / 70 uses (`MOVES` 2)**; sinks 14 to **8** (`mcp-connection-status.js` 7 to 1, only the Tools-list line left, leg 09's; the "Server exposes" snippet and its move deleted); `mcp-server-editor.js` 579 lines; no new use. No stale move entry.
- **Lanes:** `mcp` 186 passed (was 167), `library` 51, `agents` 163 (was 161), `contracts-controls` with `THE_ONE_REQUIRE_WEBKIT=1` 954 passed, 4 skipped (as before); by file `test_oauth_modal_flow.py`, `test_flow_oauth_callback_cross_site.py`, `test_flow_studio_library_focus.py`, `test_mcp_test_connection_button.py`, `test_studio_mcps_tab.py` all pass; static guards, 471 passed (guards, ownership, size, consent-link, store, nav helper, emitted classes, tokens, a11y, inventory); `make test-unit` 7242 passed, 12 skipped (was 7238); ruff check and format clean. One first run of `mcp` showed 16 failures, all in tests this leg retargets (the lane had loaded the old file); they pass retargeted.
- **Captures** (`~/.cache/the-one-ui-capture/m31-f5-l08b`, 23 surfaces both themes, compared with `m31-f5-l07` through PIL `ImageChops`): unchanged (pixel-identical) 14: the three `mcp-create-*` forms in every size and theme (12) and `mcp-library-list` (2). `agent-mcps` (4 images) is new in the tool and has no leg 07 counterpart. Changed, all on the ledger: `mcp-edit-http` (1024, 1280), `-http-open`, `-legacy`, `-rejected`, `-signin`, `-signin-after-create`, `-stdio` (1024, 1280), `-stdio-failed`, `-dirty`, `-save-error`, `-danger-armed`, `-reset-armed` (now Forget armed): rows 6 (the status line), 7 (Reset only when signed in; Forget for the cached Docs search), 8 (the result area and the missing "Server exposes" line), 9 (stdio-failed reads "Couldn't connect"), 19 ("Waiting for sign-in…" and the new link help text in `-signin`), 23 (the header Test with its play icon); `agent-mcps-full` (both themes): row 18 (stdio headline, "headers", 12 px; 31 px shorter). I looked at `mcp-edit-http` light, `mcp-edit-stdio-failed` light, `mcp-edit-signin` dark, `mcp-edit-reset-armed` light and `agent-mcps-full` light: each matches its row, with no change outside the ledger. The `mcp-edit-signin` line reads "Not connected" because that capture stubs the connect, so the refetch (the real server) overrides the optimistic "Sign-in needed"; a real auth_required records `last_check`. `scripts/ui_capture.py`: `mcp-edit-reset-armed` now arms whichever of Reset or Forget is shown (its description says Forget).
- **Ledger status (leg 08b):** rows 6, 7, 8, 9, 18, 19, 23, 30 and 31 visible, match. Row 8 note: the "Server exposes N tools." line is gone. Row 30: Reset and Forget patch in place (tested: marker on the title survives, the dirty field and caption are kept, focus lands on Test). Row 31: the callback page is styled with no session (unit-tested, not looked at in a system browser). **No visible change outside the ledger rows.**
- **Deviations from the spec, with reasons:** (1) the dirty-form Test that succeeds shows "Connected. Tested with your unsaved changes." in the result area (the spec says the area is hidden after a success, but a dirty Test leaves the line on the saved record, so a silent success would give no answer); the word comes from `mcpStateLabel`. (2) `announceName` for the two armed buttons is the server's name ("Press {name} again to reset connection."), because the button's own label would repeat the action. (3) `App.ui.status` marks the LED decorative, so the derived-relationship test asserts the line's text and `data-mcp-state`, not an LED name (the spec's own "LED is decorative" paragraph prevails over its test bullet). (4) The Tools hint has no testid (a class, `mcp-tools-empty`), so no registry row. (5) The `Reset`/`Forget` buttons are not disabled while a Test is merely in flight, only during a consent session, as specified.
- **Squawk candidate for the debrief:** the capture `mcp-edit-signin` stub artifact above (a stubbed connect never records `last_check`); and the ownership file's `START_ROWS` still lists rows that no longer exist (harmless, shrink-only).

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
- **Checkpoint B1 committed** as `ebf3ef6` (local; not pushed).
- **Leg 03 tier: high** (lifecycle, async, focus). Design review cycle 1 said "needs rework", and the leg was rewritten. Cycle 2 approved with changes, applied in place; status `ready`.
  - **FD decision:** cancelling a consent session stops the poll and the listener but does not close the popup, so a sign-in the operator is finishing still lands on the server.
  - **`flight.md` DD4** was amended to match: no global `focusAfter.cancel()` in `destroy`.
- **Batch B2 = legs 03, 04, 05,** implemented one after another (one working tree; the lane limit), then reviewed and committed together. Leg 03's Developer was spawned.
- **Leg 04 tier: high** (a shared library control, secrets). Cycle 1 approved with changes, and the rework was substantive (`beforeinput` replacement, hint ownership, `aria-describedby` tokens, the `--fixed` modifier, `setRow` merge, the key-rename state), so cycle 2 is running.
- **Leg 05 tier: high** (every shell editor). Cycle 1 approved with changes, applied in place (the empty-row collapse, the 8 px compensation, the scoped page wrap, the full pin list); status `ready`. "Delete Agent" is asked of the operator and unchanged without a yes.
- **Leg 04 cycle 2:** approved with changes, applied in place (`core.js` helpers, the `beforeinput` guarantee with an `input` fallback for IME, the rename baseline and a polite hint, `setRow` merge order, `<colgroup>` widths, the real test counts); status `ready`. Legs 04 and 05 wait for leg 03 to land (one working tree).
- **2026-10-25, leg 03 landed** (editor lifecycle; not committed, batch B2 continues with legs 04 and 05).
  - **Tests first.** Added to `tests/browser/test_flow_studio_mcp_editor.py` and run on the leg 02 tree before any product change:
    - FAILED, as intended: `test_late_save_never_writes_into_the_next_editor` (B's title became A's saved name), `test_late_delete_never_closes_the_next_editor` (B was closed by A's late DELETE), `test_late_test_connection_never_paints_the_next_editor` (B's LED went to success, "Last updated" shown, a Reset injected), `test_leaving_the_editor_stops_the_sign_in_poll[other-item|settings|breadcrumb]` (the poll kept running: 240 GETs of A after the leave, not 3), `test_one_sign_in_poll_at_a_time` (Test stayed enabled during a session), `test_destroy_is_idempotent` (no controller returned), `test_reset_leaves_the_editor_clean_and_focused` (failed at the missing `_currentMcpEditor` seam, so its dirty-flag and focus assertions were not exercised on the old tree; they follow from the old Reset never calling `onDirtyChange(false)`).
    - Passed on the old tree, as regression guards: `test_auto_run_after_create_fires_once_for_http_and_never_for_stdio[streamable-http-1|stdio-0]`.
    - Test fixes made while writing them, not product changes: the per-id route regex had to exclude `/types`; `wait_for_function` cannot be used under `page.clock` (its rAF is faked), so counts are read directly after `run_for`.
  - **Built.** New `js/areas/studio/mcp-editor-lifecycle.js` (54 lines, `createMount`: `alive`, `ifAlive`, idempotent `destroy` that never calls `App.focusAfter.cancel()`, one session slot, `handles`). Controller: returns `{destroy, setBusy, setError, runTest}`, reports `onMounted` on every mount, reports the initial clean `onDirtyChange(false)`, `applyButtons()` shared by dirty and busy, `runTest({autoRun})` the one Test entry (a no-op while Test is disabled or a session is live), `handles` passed to `getFormSnapshot`/`collectFormData`/`revertEditorToSource`. Connection status: `opts.mount` threaded through `rerun`, Reset in the specified order (alive, `begin(resetBtn)`, destroy, mount, restore focus to Test or the `h1`, flash). Consent: `launchConsentPopup` registers a session `{cancel, isDone}` with the mount; `cancel` stops the poll, listener and the delayed first status write, and does not close the popup. Glue: `current` set from `onMounted` (a stale-generation controller is destroyed), destroyed at the top of `renderMcpSourcesSection`, before the mount inside `ready.then`, in `_closeMcpForm`, `reset()` and `_resetMcp`; `studio.js` `deactivate()` calls `_resetMcp`; no `dataset.autoRun` anywhere.
  - **Defect 8 as built (refuse).** Starting a consent session (`mount.setSession`) disables Test; the session ending (finalize or cancel) re-enables it (`mount.endSession`). A second launch cancels the first through `setSession`. The auto-run `auth_required` branch still calls `settle()` before any session exists, so Test is enabled until "Sign in" is pressed. "Sign in" is not disabled. `runTest()` is a no-op while a session is active.
  - **Dead-mount rule (M4).** Save, Delete, Test continuations and every `.catch` and `settle` are skipped; `invalidate` then `onListStale()` still run (late Save and late Test call `onListStale`; late Delete calls `onListStale` instead of `onDeleteSuccess`). `destroy` aborts no request.
  - **Deviations.** (1) The test seam is on the studio area descriptor (`App.areas.find(a => a.id === 'studio')._currentMcpEditor()`, like the area's other `_` seams), not `App.studio._currentMcpEditor`: `self` is the descriptor, not `App.studio`. (2) The glue's auto-run guard is the controller identity plus `mcpGen` plus `state.editingMcpSource === updated` (the create editor it replaces is excluded), because the edit mount is rendered by a later `ready.then` than the `onSaveSuccess` call that schedules it. (3) Reset's fallback focus target is `h1` rather than `.editor-title`, to avoid a new ownership use. (4) `setError` is the one `.editor-error` writer inside the wiring (Save uses it), keeping the ownership count at 3.
  - **Remount side-effect inventory rows touched (DD4).** Reset re-mount: now reports the clean dirty flag, restores focus, hands the glue the new controller. Save, Delete, Test continuations: keyed on the mount. Consent poll: owned by the mount and cancelled on destroy.
  - **Verification.** Static guards (ui_guards, ui_ownership, area_module_size, store_static, consent_link_static, index_asset_cache_busting, token_definitions, design_tokens_a11y): 396 passed, no table changes. Browser (netns): new tests 11 passed; lane `mcp` 121 passed (110 + 11); lane `library` 51 passed; `test_studio_mcps_tab.py` + `test_oauth_modal_flow.py` + `test_flow_chiplist_label_resolver.py` 44 passed. Capture compare against `m31-f5-split`: 20 surfaces, 50 PNGs, PIL bbox `None` on all 50 (`m31-f5-l03`). `make test-unit`: 7219 passed, 12 skipped. ruff check and format clean.
  - **Line counts (`mcp-*.js`):** controller 798, connection-status 357, oauth-consent 257, glue 261, lifecycle 54, shared 221, server-info 268, connection-fields 213, sandbox-fields 68, env-headers 297.
- **Leg 03 landed** (FD reading of the report):
  - **Tests:** 8 defect tests failed first and now pass; the 2 auto-run guards passed before and after. Lanes `mcp` 121, `library` 51, plus 44 by file. Captures pixel-identical (50 of 50). Unit 7219 passed, 12 skipped.
  - **Accepted deviations:**
    - the test seam is on the studio area descriptor (`App.areas…_currentMcpEditor()`), like the area's other `_` seams;
    - the auto-run guard also compares `state.editingMcpSource`;
    - the poll tests read page-side counters after `run_for` (`wait_for_function` is unusable under `page.clock`).
  - **Noted for leg 10:**
    - the controller is at 798 of 800 lines;
    - Reset's fallback focus selects the `h1` by tag, to avoid a new `editor-title` use in `mcp-connection-status.js`. Leg 10 replaces it with the shell's `titleEl`.
- **Leg 04's Developer was spawned.**
- **Leg 06 tier: high** (handover deletes a shared file; payload correctness). Cycle 1 approved with changes, applied in place; status `ready`.

- **2026-10-25, leg 04 landed** (kv-secret-column; not committed, batch B2 continues with leg 05).
  - **Built.** `App.ui.util.addDescribedBy`/`removeDescribedBy` (`core.js`); `secretInput` gains `showLabel`/`hideLabel`, `setLabels`, `stored`/`setStored`, `setHint`, `sync` and a lazy `hintEl` (`div.ui-secret-hint`); `keyValueTable` gains `secret` and `toggle` column types, `keyColumn`, `setRow`, the delegated toggle `change` listener, clear on unmask, the key-rename rule, `ui-kv-secret`/`ui-kv-toggle`/`ui-kv-table--fixed` and a `<colgroup>`; CSS in the `.ui-kv*` block and beside `.api-key-*`; two catalogue rows updated.
  - **Deviation (WebKit).** A selection made inside `beforeinput` is ignored by WebKit for the current edit (the edit lands at the old caret: `***Xabcd`), so the stored-mode handler resolves the edit itself for delete* and insert* types (`preventDefault`, set the value, dispatch an `input` event) and only selects all for other types; the `input` fallback still covers IME. Backspace with the caret at 0 fires no event in WebKit, so the start-caret Backspace test uses Delete.
  - **Process note.** The contract tests were written in the same pass as the implementation, so the tests-first failure run was not captured; the WebKit stored-mode failures and a click-target bug in the first test draft (the switch input is visually hidden, click its label) were found and fixed on the first run.
  - **Verification.** Contract files: table 14 functions / 28 runs before, 37 functions after (parametrized stored-mode matrix included); secret input 7 / 14 runs before, 11 functions after; together 134 runs; both files 134 passed with `THE_ONE_REQUIRE_WEBKIT=1` (Chromium + WebKit). Lanes: `library` 51 passed, `providers` 134 passed, unedited. Guards (`ui_control_inventory`, `ui_ownership`, `ui_emitted_classes`, `ui_guards`, `token_definitions`, `design_tokens_a11y`): 374 passed, no allowance changes. Captures against a fresh `main` worktree set: `connector-edit` and the 8 `provider-edit-*` (36 PNGs): 28 pixel-identical, 8 differ only in the random port digits printed in the Ollama and OpenAI-compatible subtitles. `make test-unit`: 7219 passed, 12 skipped. ruff clean.
- **Leg 04 landed** (FD reading of the report):
  - **Tests:** contract runs 134 passed (table 14 → 37 functions, secret input 7 → 11); lanes `library` 51 and `providers` 134 pass unedited; the provider and connector captures match (8 differ only in random port digits, read on crops); the guards pass; unit 7219 passed, 12 skipped.
  - **Accepted deviation (WebKit):** a selection made inside `beforeinput` is ignored, so for insert and delete types the stored-mode handler cancels the event and sets the value itself, then dispatches `input`. The catalogue says "replaces the whole value".
  - **Process miss, recorded:** the contract tests were written in the same pass as the implementation, so there is no captured fails-first run.
  - **Left to the batch review:** the full `contracts-controls` lane was not run, so the batch B2 Reviewer, or the leg 05 run, covers it.
- **Leg 05's Developer was spawned.** "Delete Agent" stays unchanged, because the operator has not answered.
- **Leg 07 tier: high** (secrets). Design review cycles 1 and 2 both approved with changes, applied in place. FD decisions: Cancel restores the last saved rows; the baseline is taken from the live rows by `_rid` after a Save; an empty sensitive value still sends `''` (the cycle 1 'send nothing' idea was withdrawn at cycle 2). Status `ready`. A mask-shaped typed secret is recorded as a squawk candidate for the debrief.

- **2026-10-25, leg 05 landed** (shared-editor-changes; not committed, batch B2 ready for review).
  - **Tests first (run on the unchanged code):** 28 failures across both engines (14 per engine): the long-error full-width row (4 per engine: default and page, 1024 and 1280; the error was inside the cluster), the empty-row `data-empty` marker (4 empty-row geometry cases and 2 marker cases), `setTestState` (3: the hold test and the no-op test, plus none existed), and the danger default title / accessible name ("Danger Zone" vs "Danger zone"). The no-error geometry comparison against a fixture copy of the old structure passed on the old code once its Test button carried the play icon (a first fixture draft lacked the icon: a 22 px width gap, a test bug fixed before the product change).
  - **API/CSS:** `editorShell` errorEl is the header's last child (`span.editor-error.ui-editor-error-row`, `data-empty` while empty, set by `setError`); the header gains `ui-editor-shell-header`; new `setTestState({disabled, label})` (hold survives `setDirty`/`setBusy`; label replaces the text node; `null` restores; no-op without `actions.test`); `dangerZone` default title "Danger zone"; components.css: shared colour/size declaration (`.form-actions .editor-error, .ui-editor-error-row`), `.ui-editor-shell-header` (wrap, row-gap 0, cluster `margin-right: 8px`), `.ui-editor-error-row` (flex 0 0 100%, block, overflow-wrap anywhere, `:not([data-empty])` top margin 8px). Catalogue rows updated (editor shell, danger zone). B7: "Delete provider", "Delete connector", "Delete knowledge base"; provider title "Danger zone"; "Delete Agent" untouched (no operator yes recorded).
  - **Pins retargeted (none deleted or loosened):** `test_ui_editor_contract.py` DOM shape (`actKids` loses the error span, a new last-child assertion; root class gains `ui-editor-shell-header`; danger default title and label); `test_ui_page_header_contract.py` (`kids`, `acts`, root class, default-variant DOM, error element class); `test_flow_provider_editor.py` the two `.form-actions .editor-error` locators now `.editor-header .editor-error`, three label asserts, the title; `test_studio_connector_editor.py` label; `test_flow_studio_knowledge_inventory.py` two labels and the title; `test_design_tokens_a11y.py` contrast pin now reads both selectors; `tests/behavior/system-provider-config.md` (three label mentions). Also `test_ui_library_contract.py::test_core_namespace_and_helpers` (leg 04's missed pin: `addDescribedBy`/`removeDescribedBy` in the util key list; this was the one failure in the full `contracts-controls` lane that leg 04 had not run). `the_one/agents.md` gained a "Shared editor changes" block.
  - **New contract tests (both engines):** long error row at 1024 and 1280 for the default and page variants (title, cluster and breadcrumb unchanged, row below both and full width); empty row adds no height and nothing moves (header, title, cluster place and height, Save and Test buttons, versus a fixture copy of the old structure, with and without `errorRole`); empty marker follows `setError`; `setTestState` (hold across dirty and busy, label, no-op); danger button accessible name equals its visible label.
  - **Lanes:** `PARALLEL_RESULT rc=1 total=1560s lanes=13 failed=contracts-controls` on the first run: the only failures were the 2 `test_core_namespace_and_helpers` runs (leg 04's util pin, fixed; re-run 2 passed). Every other lane rc=0. Times: routing 527, agents 455, chats 399, mcp 382, knowledge 306, providers 338, contracts-controls 397 (950 passed, 2 failed, 4 skipped), shared 331, agent-tabs 312, settings 291, settings-tools 262, contracts-overlay 231, library 157. Static guards (inventory, ownership, emitted classes, ui_guards, token definitions, a11y, nav helper): 451 passed. `make test-unit`: 7219 passed, 12 skipped. ruff clean.
  - **Captures:** fresh `main` worktree set (`m31-f5-l05-main`, removed after) against `m31-f5-l05` for the no-error surfaces (provider-edit-*, provider-create, connector-new/edit, kb-*, settings-*, agent-general): every difference is the random port digits or the delete button's lowercase label; `provider-create`, `connector-new`, `kb-new`, `settings-*` and `agent-general` are pixel-identical. Error and danger surfaces against `m31-f5-before`: `ref-provider-long-error` shows the title, breadcrumb and subtitle intact with the error as a full-width row under them (before: title squeezed to "Libra"); the armed surfaces differ only in the library list pane (the MCP servers seeded in the before set only).
- **Leg 05 landed** (FD reading of the report):
  - **Tests:** 28 fails-first contract runs (14 per engine), then all passing.
  - **Full `--parallel 3` run:** rc=1, total 1560 s. The only failure was leg 04's missed util-key pin in `test_ui_library_contract.py`, which was fixed and re-run (2 passed). `contracts-controls` otherwise 950 passed, 4 skipped. Lane times (s): routing 527, agents 455, chats 399, mcp 382, contracts-controls 397, providers 338, shared 331, agent-tabs 312, knowledge 306, settings 291, settings-tools 262, contracts-overlay 231, library 157. All are within budget.
  - **Captures:** the no-error editors are identical to `main`, apart from the B7 label and the random ports. `ref-provider-long-error` now keeps the title, where before it was squeezed to "Libra".
  - **Unit:** 7219 passed, 12 skipped.
  - **"Delete Agent"** is unchanged (no operator answer).
- **Batch B2 (legs 03-05) end:** no class was deleted in this batch, so there is no deleted-selector grep. A Reviewer (Sonnet: secret-handling library code) and an Accessibility Reviewer (the UI changes) were spawned in parallel.
- **Leg 08a tier: high** (server, an inverted pin). Cycle 1 approved with changes, applied in place; `flight.md` DD6's precedence was corrected to match. Status `ready`.
- **Batch B2 review:**
  - **Reviewer** (Sonnet, security focus): `[HANDOFF:confirmed]`. It ran 481 guards, 260 contract runs in both engines and the `mcp` lane (121), and found no secret leak. Its non-blocking items: the IME composition rewrite (CJK), no cut, drop or undo test, and the unguarded `opts.mount`.
  - **Accessibility Reviewer:** `[HANDOFF:confirmed]`, with no WCAG 2.1 AA failure. Its non-blocking items: the lazily created hint's announcement, redundant hint writes, the eye losing focus, a repeated error not re-announcing, and a silent masking switch.
  - **The FD chose to fix before the checkpoint:** the IME composition, the `opts.mount` guard and four accessibility items (a fix-review-issues Developer was spawned).
  - **Accepted as is:** the silent masking switch (the switch's state is announced); the untested cut, drop and undo paths (they share the tested `beforeinput` path); and the alternative hint wording, because the operator's approved text is kept.

## Batch B2 review fixes

- secretInput stored-mode IME fallback no longer rewrites `.value` while `isComposing`; the strip-the-mask rule runs on `compositionend`. Test: `test_secret_input_ime_composition_is_not_rewritten_mid_composition`.
- `handleTestConnection` (mcp-connection-status.js) tolerates missing `opts`/`opts.mount` (always-alive mount, as before leg 03). No dedicated test (covered by the mcp lane).
- The stored hint element is created on first stored use, then stays in the DOM (empty, `aria-live=polite`, collapsed via `:empty` CSS, never `hidden`); describedby only while it has text; default DOM unchanged. Tests: existing stored-mode/KV tests updated to assert on text, `test_secret_input_hint_stays_in_dom_and_writes_only_on_change`.
- Hint text is written only when it changes (same test, MutationObserver count).
- Focus moves from the eye to the input before the eye is hidden on re-entering stored mode. Test: `test_secret_input_moves_focus_off_the_eye_when_stored_mode_is_reentered`.
- `editorShell.setError` with an identical message clears then restores on the next animation frame so it re-announces. Test: `test_set_error_same_message_twice_reannounces`.
- **Batch B2 fix re-review** (Sonnet, scoped): `[HANDOFF:confirmed]`. One accepted nit: a one-frame margin twitch when an identical error repeats. Legs 03-05 are `completed`; checkpoint B2 committed.
- **Checkpoint B2 committed** as `6f430c4` (local).
- **Batch B3 = legs 06, 07, 08a**, run one after another (all three touch the controller). Leg 06's Developer was spawned.
- **Leg 08b tier: high** (OAuth, focus, popup rules; a server page for 0214). Cycle 1 approved with changes, applied in place; `flight.md` DD6's Forget label was aligned. Status `ready`. The ledger notes for rows 8, 18 and 19 were updated (the tool-count line dropped; "try again"; A19 reaches chat).
- **Leg 09 tier: low** (FD call): a single surface (the Server and Tools sections), built from existing library controls (`section`, `facts`, `disclosure`, `codeBlock`, `syncChildren`), with no shared interface, server or security change. No per-leg design review; the batch Reviewer covers it. Status `ready`.
- **Leg 11 tier: medium,** treated as high only if `App.ui.toolTile` needs a new option for A20's names (then a library change with a contract test). It is designed now; its design review runs before implementation.
- **Leg 11 design review:** approved with changes, applied in place. The tier was raised to high (the `toolTile` `expandLabel` option is required). `mcpStateLabel` moved into leg 08a, and leg 08b reads it. Status `ready`.
- **Operator, 2026-10-25: "yes on Delete agent".** It joins leg 11 (which already edits the agent editor for A21). Ledger row 28 is updated.
- **Leg 06 landed** (FD reading of the report):
  - **Tests:** the payload tests passed before and after; defect 7 failed first (2 of 2) and passes now. Lanes `mcp` 143, `library` 51, `routing` 184, plus 68 and 14 by file. Unit 7221 passed, 12 skipped.
  - **Guards:**
    - ownership 167 → 103 uses (`MOVES` 25 → 16);
    - sinks 23 → 19;
    - the controller 798 → 676 lines;
    - `tools-form-helpers.js` deleted.
  - **The FD looked at two captures** (`mcp-edit-stdio` light 1280, `mcp-create-empty` dark 1024): the B3 labels, the A5 hint under Command, the inline A10 switch with its hint, the library chips with the middle ellipsis (B4), and A17 (only Name and Type on create). Each matches its row.
  - **Accepted deviation:** the network switch tests click its label, because the library toggle's track covers the input, as in the connector tests.
  - **Leftover processes:** none, checked by the FD after the agent reported background work.
- **Leg 07's Developer was spawned.**
- **Leg 07 landed** (FD reading of the report):
  - **Fails-first:** 22 payload and scan cases ran on the leg 06 tree before any product change; 5 failed as the spec predicted (6, 7, 9, 10 and the attribute scan), and 1-5, 8, 11 and 12 passed. All 22 pass after. No payload assertion was weakened and there was no `[BLOCKED]`, so the server contract matched the spec.
  - **Guards:** ownership 63 / 103 → 56 rows / 86 uses (`MOVES` 16 → 10); sinks 19 → 14 (`SINK_MOVES` 3 → 2, `SNIPPET_MOVES` 7 → 3); the controller 676 → 640 lines; `mcp-env-headers.js` at zero sinks and zero rows. The last legacy switch (`.tool-enable-switch*`) is deleted, and its contrast pins sit on `.ui-toggle-*` with every pair kept.
  - **Lanes:** `mcp` 164, `library` 51, `agents` 161, `contracts-controls` 954 (4 skipped, WebKit required), `contracts-overlay` 510, plus 98 by file; static guards pass; unit 7218 passed, 12 skipped.
  - **Accepted deviations:** (1) a `__MASKED__` key the server drops also clears its value, not only `_originalMasked`; (2) a library change: `App.ui.keyValueTable` gained an optional column `width` (Sensitive at 120px, so its header and info button stay on one line), with a catalogue row update and a both-engine contract test. The batch Reviewer covers the library change.
  - **The FD looked at two captures** (`mcp-edit-http` light 1280, `mcp-edit-stdio` dark 1024): sentence-case titles "Headers" and "Environment variables", the Sensitive column on one line, the stored-secret hint "Stored. Type a new value to replace it." under the masked value, and sentence-case "+ Add row". Each matches rows 3, 11, 12, 13 and 26. "Delete MCP Server" is still title case; it is leg 10's (B7, row 28).
  - **Behavior spec** `tests/behavior/mcp-sensitive-headers-round-trip.md` drafted, not run (leg 12 runs it).
  - **Debrief squawk candidate** (already noted): a typed secret shaped like a mask.
  - **Host:** another session's gate (the `m32-installers` worktree) is running 3 browser lanes. Leg 08a's Developer is told to keep the host-wide total at 3 lanes.
- **Leg 08a's Developer was spawned.**
- **Leg 08a landed** (FD reading of the report):
  - **Fails-first:** 10 of 14 new server tests failed on the leg 07 tree for the predicted reasons (no `merge_cache`, no `last_check`, `updated_at` bumped by the old posture write), and so did the inverted pin. The inverted pin was renamed `test_stdio_test_connect_error_records_last_check_only`, not deleted.
  - **Lanes:** `mcp` 167, `agents` 161, `library` 51, `routing` 186; unit 7233 passed, 12 skipped; guard totals unchanged.
  - **Accepted deviations:** (1) the unsupported-type "not recorded" case can't be reached through the API (the model allows only `stdio` and `streamable-http`), so the `False` flag is covered by reading the code only; (2) auth_required is tested with the inner function stubbed, while the real Phase B path stays covered by the existing OAuth tests.
  - **Behaviour change, intended:** an ok HTTP write now keeps an existing `auth_posture` (it used to drop it), because `_cache` is merged rather than replaced. This is tested and documented. The batch Reviewer is asked to confirm it.
- **Batch B3 (legs 06, 07, 08a) end.** A Reviewer (Sonnet, because the batch touches secrets and the check-record route) and an Accessibility Reviewer were spawned in parallel over the diff since `6f430c4`.
- **Batch B3 Accessibility Reviewer:** `[HANDOFF:confirmed]`, with no blocking or non-blocking issue to fix. It reviewed the code only: it ran no browser tests and did not look at the captures. It checked the per-row names, the column name "Sensitive", the stored hint's `aria-describedby`, focus after add and remove, and the create-mode reveal. Its advisory: a live announcement when create-mode fields appear. Accepted without change: the change follows the user's own Type choice, and focus stays on the select.
- **Batch B3 Reviewer** (Sonnet, security focus): `[HANDOFF:confirmed]`, with no blocking issue. Its security checks were clean: the secrets contract unchanged, `partition` and `remaskAfterSave` never put a secret where a mask belongs, no mask in a DOM attribute, and `last_check` holding only `{status, at}`. It ran 677 guard and unit tests and 234 browser tests in both engines. Its non-blocking items:
  1. **A stale `last_check` and `auth_posture` after a PUT that changes the server.** The PUT pins all of `_cache`. Since leg 08a merges rather than replaces, the old server's posture and check now survive a URL or type change, past the next ok write. **The FD fixes this before the checkpoint**, because leg 08a introduced the persistence. A PUT that changes `type` or `config.url` drops `_cache.last_check` and `_cache.auth_posture`, beside the existing `forget_era`. Every other edit keeps them (DD6 unchanged for those). The tools cache stays pinned, which is the pre-flight behaviour.
  2. **A sensitive row named like an OAuth-managed key** (`access_token` and the others) is dropped silently by the server, and the row reads clean. This predates the flight, so it is a **debrief squawk candidate**.
  3. **The untracked `env.sh`** at the repo root is never committed (standing rule).
- **Batch B3 fix (review item 1, stale `last_check`/`auth_posture` after a PUT that changes the server):** five tests added to `tests/test_mcp_last_check.py` first; on the unfixed tree 4 failed (URL change, type change, forged `_cache` after a URL change, emptied-cache) and 1 passed (name-only and headers-only keep both). After the fix in `update_mcp_source` the file is 20 passed; the 7 files that exercise the route are 282 passed; `make test-unit` is 7238 passed, 12 skipped.
- **Batch B3 fix re-review** (Sonnet, scoped): `[HANDOFF:confirmed]`, with no issues. It ran 222 tests over the four route files. Legs 06, 07 and 08a are `completed`. The checkpoint "the editor and the Library list read one derived state" stays open until leg 11.
- **Checkpoint B3 committed** as `66193d0` (local).
- **Batch B4 = legs 08b and 09**, run one after the other (both touch the controller and the connection-status module). Leg 08b's Developer was spawned.
- **Leg 08b landed** (FD reading of the report):
  - **Fails-first:** 19 new browser tests and the first of 4 callback-page unit tests failed on `66193d0`; all pass after, with no assertion weakened. Squawk 0216's two racing assertions are held with `page.route`.
  - **Lanes:** `mcp` 186, `library` 51, `agents` 163, `contracts-controls` 954 (4 skipped), plus 5 files by name; static guards 471; unit 7242 passed, 12 skipped.
  - **Guards:** ownership 56 / 86 → 47 rows / 70 uses (`MOVES` 10 → 2); sinks 14 → 8; the controller 648 → 579 lines.
  - **Squawks 0214 and 0216** are `completed`; their sign-off and commit are filled in at checkpoint B4.
  - **The FD looked at two captures** (`mcp-edit-http` light, `mcp-edit-stdio-failed` dark):
    - the header Test (row 23);
    - "Connected · checked …" with "Forget tools list" beside it (rows 6 and 7);
    - no "Server exposes" line (row 8);
    - "Couldn't connect" with the A18 stdio headline and Technical details (rows 9 and 18);
    - "Press Test to load this server's tools." after a failure.

    The capture's line shows a date because the capture fixes the browser clock at 2026-03-01 while the seed-time Test records the real time, so "not today" is correct. That text differs run to run; the compare treats it as expected.
  - **Accepted deviations:**
    1. **A dirty Test that succeeds** shows "Connected. Tested with your unsaved changes." in the result area. Otherwise the line, which reads the saved record, would give no answer. This is a new visible string outside the survey, flagged for the HAT walk.
    2. **The armed Reset and Forget** announce the server's name.
    3. **The LED is decorative.** The spec's own paragraph prevails, and the tests assert the text and `data-mcp-state`.
    4. **The Tools hint** has a class and no testid.
    5. **Reset and Forget** are disabled only during a consent session, as specced.
    6. **The 0214 callback card** uses `--radius-lg`, because `--panel-radius` never existed.
  - **Not checked:** the callback page was never viewed in a real browser. It is added to the HAT walk.
- **Leg 09's Developer was spawned** (tier low, batch B4).
- **Leg 09 landed** (server-info-and-tools, Developer):
  - **Citation drift:** the spec's `mcp-connection-status.js` description was stale: 08b had already rewritten it as `create(...)` with the Tools-list sink in `showTools`/`emptyTools`; the Server and Tools strings were in `mcp-server-editor.js`, not the status module. `studio.css` ranges had moved (`:119-338` was the whole family).
  - **Fails-first:** 12 new or retargeted browser tests failed on the 08b tree (14 failed, 3 passed in the selected set, all for missing testids or the old shape); all pass after. `test_capability_flags_render...` was retargeted to the Offers row. No test deleted or weakened.
  - **Built:** `mcp-server-info.js` is now `serverInfo.create({cache})` returning `{serverEl, toolsEl, update, setTools, destroy}`: `App.ui.section` x2, `facts` (Version, Protocol, Offers, Website), plain `disclosure` for Instructions and Metadata (`codeBlock`), a bordered `disclosure` per tool reconciled by name through `syncChildren` (open panels persist). Server section is always mounted in edit mode and `hidden` when the cache has nothing to show. The status module calls `setTools`/`update`; the editor mounts the two sections over hosts and registers `destroy`.
  - **Deviations:** (1) a tool's body shows "Description" when the text is longer than the cut, has a line break, or is empty ("No description provided."); otherwise the summary meta carries it once. (2) New owned CSS classes `mcp-info-*` (identity row, text blocks, tool summary arrangement, field-label-style sub-labels); the `.mcp-tool-*`, `.mcp-server-*` and `.mcp-capability-flags*` rules are deleted. (3) `summaryTextTestid` is not scanned by the registry guard, so the tool name has no testid (tests use the summary text span). (4) The Instructions/Metadata plain disclosures keep the native marker (the plain variant has no chevron option). (5) The old `mcp-tool-*` look is frozen as `LEGACY_MCP_TOOL_CSS` in `tests/browser/_legacy_tool_css.py` for `test_ui_disclosure_contract.py`.
  - **Guards:** sinks 8 -> 6 (`mcp-server-info.js` and `mcp-connection-status.js` rows gone; `SINK_MOVES`/`SNIPPET_MOVES` emptied); ownership rows/uses: `mcp-server-info.js` rows gone, editor `editor-section` and `section-title` 3 -> 2 each, `TOTAL_USES` editor-section 5 -> 3, section-title 4 -> 2, `MOVES` emptied.
  - **Lanes:** `mcp` 194 (after two test fixes), `library` 51 (one retarget re-run), `agents` 163, disclosure contract + new tests in both engines 33, static guards 465, `make test-unit` 7242 passed, 12 skipped. Every `mcp-*.js` at most 573 lines.
  - **Captures** (`m31-f5-l09` vs `m31-f5-l08b`): changed surfaces `mcp-edit-http`, `mcp-edit-http-open`, `mcp-edit-legacy`, `mcp-edit-stdio` (page height +9px: the server section only) differ in the Server and Tools regions (rows 15 and 16); `mcp-edit-signin` and `mcp-library-list` are identical. Looked at `mcp-edit-http-open` light before and after: facts rows, Instructions disclosure, tools as name + short description with Description/Input schema sub-labels; no other region changed.

- **Leg 09 landed** (FD reading of the report):
  - **Fails-first:** 14 of 17 selected tests failed on the 08b tree (the new testids and DOM shape); no test was deleted or weakened. No library or server change was needed, so the low tier held.
  - **Guards:** sinks 8 → 6; `MOVES`, `SINK_MOVES` and `SNIPPET_MOVES` are all empty; every `mcp-*.js` is 573 lines or fewer.
  - **Gap:** `mcp` (192 passed, 2 failed) and `library` (50, 1 failed) had test-side failures, fixed and passed in isolation, but neither lane was re-run end to end. **The batch B4 Reviewer is asked to run both lanes in full before confirming.**
  - **The FD looked at `mcp-edit-http-open` light 1280:**
    - the Server facts read Version, Protocol, Offers, Website (row 16);
    - Instructions is an open disclosure;
    - the tools are bordered disclosures with "Description" only for the long one, then "Input schema" in a code block (row 15).

    Each matches its row.
  - **Accepted deviations:**
    1. "Description" appears only when the text is long, multi-line or empty (the summary carries a short one once, per A15).
    2. The new owned classes are `mcp-info-*`.
    3. The tool name has no testid.
    4. The plain disclosures keep the native marker.
    5. The Server section is hidden, not absent, when empty.
- **Batch B4 (legs 08b, 09) end.** A Reviewer (Sonnet: OAuth sign-in, the callback page, untrusted server text) and an Accessibility Reviewer were spawned in parallel over the diff since `66193d0`.
- **Batch B4 Accessibility Reviewer:** `[HANDOFF:confirmed]`, with no blocking issue. It reviewed the code only. FD calls on its non-blocking notes:
  1. **A failed Test may be announced twice** (the status line, plus the `role=alert` error). **Fix in batch B4:** the result area's error does not re-announce what the status line says.
  2. **"Testing connection…" and the authorization prompt** are inserted into a live region that is already populated, so they may not be read. **Fix in batch B4:** one persistent live region in the result area.
  3. **The section titles are `div`s, not headings.** Accepted for this flight: it is the app-wide `section` default (every editor), so changing two MCP sections alone would be inconsistent. Carried to the mission debrief as an app-wide candidate (`titleTag` everywhere).
  4. **A tool's long summary name** (the name plus the description). Accepted: it is the A15 layout the operator approved.
  5. **`<main role="status">` on the callback page** overrides the landmark. **Fix in batch B4:** the live region goes on an inner element.
- **Leg 10 designed** (`legs/10-editor-controller.md`). **Tier high** (the save model, a shared-control consumer, the guard tables). Its FD decisions:
  - **A4's subtitle** is "{type label} · {command or URL}", falling back to the raw type for a legacy row.
  - **Type's error wording** is "Choose how it connects.", to match the create placeholder.
  - **A new testid,** `mcp-editor-subtitle`.

  Its design review was spawned while the batch B4 code Reviewer runs. The review is read-only, and B4's fixes touch only `mcp-connection-status.js` and `api.py`.
- **Leg 10 design review, cycle 1:** approve with changes, applied in place.
  - **The highs:**
    - Test had three writers of its disabled state, and the shell's `apply()` would re-enable Test mid-Test. Now there is one `syncTestHold()`.
    - There was no per-field baseline. FD decision, option b: a pure `baselineFrom(source)` on the two field modules.
    - `test_store_static.py`'s anchors.
  - **The rest:** the tests that read the old copy, the exact guard entries (read the start-record semantics first), the shell gaps, and `collectFormData` returning `{error, fields}`.
  - Cycle 2 was spawned, because the changes are substantive.
- **Leg 10 design review, cycle 2:** approve with changes (2 medium, 3 low; no high). Applied in place:
  - `baselineFrom` goes through the controls' normalisation;
  - the store anchors are two rows, create and edit;
  - one `onSessionChange` registration and the creation order;
  - the destroyed-mount label test is retargeted by name.

  Status `ready`; no third cycle.
- **Batch B4 Reviewer** (Sonnet, security focus): `[HANDOFF:confirmed]`, with no blocking issue.
  - **It ran:** the full `mcp` lane (194 passed) and `library` lane (51 passed), which closes leg 09's gap, plus unit 7242 passed, 12 skipped.
  - **Security checks, all clean:**
    - the popup gesture and `isSafeUrl`;
    - one poll, with an idempotent cancel;
    - the callback page escapes its query text and links no static asset;
    - leg 09's untrusted text goes through `textContent` and `App.safeUrl`, failing closed.
  - **Its non-blocking items, both fixed in this batch:**
    1. **A malformed tool** (a non-string description, or a null tool) can throw in `mcp-server-info.js` `setTools`/`fillBody`. Fix: coerce with `String()` and skip null entries.
    2. **`runDelete`** reads `getSource().id` without a null guard. Fix: add one.
  - **Batch B4 fix pass:** these two plus the accessibility items 1, 2 and 5. A Developer was spawned.

## Batch B4 review fixes

Fixes after the flight review of legs 08b and 09. Tests were written first and run
against the pre-fix source (fixes temporarily reverted), then the fixes restored.

| # | Fix | Test | Fails first? |
|---|---|---|---|
| 1 | `mcp-server-info.js` `setTools`/`fillBody` skip null/non-object tools and coerce `name`/`description` with `String()` (null/undefined description = empty) | `test_malformed_cached_tools_render_without_error` (numeric description, null entry, object description) | yes |
| 2 | `mcp-connection-status.js` `runDelete` returns with no request when there is no source id; the post-response check is null-safe | covered by the existing Reset/Forget tests (no fails-first: the guard is defensive, no reachable path on the unfixed tree) | n/a |
| 3 | `buildMcpError(raw, {live})`: `'alert'` (default, unchanged for the agent MCPs tab and chat), `'status'`, `'none'`; the editor's result area passes `'none'` so the status line is the one announcement | `test_build_mcp_error_live_option` (all values and the default); `test_test_result_uses_one_persistent_live_region` (no `role=alert` in the result area); `test_library_editor_connection_error_plain_headline` assertion changed from `role=alert` to no role | yes |
| 4 | One persistent polite live region (`div.visually-hidden[role=status][data-testid=mcp-test-live]`) created at mount after the hidden-at-rest `mcp-test-status` area (so `display:none` never removes it); `showText` and the sign-in prompt set its text; `clearArea` empties it; the visible text nodes lost their per-message `role=status` | `test_test_result_uses_one_persistent_live_region` (same element before/after a Test, holds "Testing connection…") | yes |
| 5 | OAuth callback page: `<main>` is plain; the message sits in an inner `<div role="status">` | `test_main_landmark_is_plain_and_message_is_an_inner_status` in `tests/test_oauth_callback_page_static.py` | yes |

Counts: the new tests fail 3/3 browser and 1/1 static on the pre-fix source, pass after.
`--lane mcp`: 197 tests, 196 passed and 1 failed (the plain-headline assertion above, updated and re-run green).
`--lane library`: 51 passed. `--lane agents` (touched `mcp-error.js`): 163 passed. `test_oauth_modal_flow.py` + `test_flow_oauth_callback_cross_site.py`: 19 passed.
Static guards (ui_guards, token_definitions, design_tokens_a11y, ui_ownership, ui_emitted_classes, oauth_callback_page_static, nav_helper): 448 passed after registering `mcp-test-live` in `docs/ui-testid-registry.md`.
`make test-unit`: first run 7241 passed, 12 skipped, 2 failed (`tests/test_store_static.py`, which pins the exact text of the Reset guard line); the pin and the line were updated to `!getSource() ||` and the file re-run green (51 with ui_guards). The Reset/Forget browser tests were re-run after that edit.
- **Batch B4 fix re-review** (Sonnet, scoped): `[HANDOFF:confirmed]`. It ran unit (7243 passed, 12 skipped) and the `mcp` lane (197 passed). The store pin was re-anchored on the null-safe guard line and still asserts the same order. Its accepted nits:
  - the unreachable no-id early return leaves the armed button un-reverted;
  - the hidden live region may keep "Testing connection…" until the next clear.

  Legs 08b and 09 are `completed`; squawks 0214 and 0216 are signed off. The checkpoint "the fields, env and headers, status and sign-in, and server info are on the library" is met.
