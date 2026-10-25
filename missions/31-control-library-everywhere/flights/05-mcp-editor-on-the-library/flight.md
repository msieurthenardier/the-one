# Flight: The MCP server editor on the library

**Status**: in-flight
**Mission**: [Every control comes from one library](../../mission.md)

## Contributing to Criteria
- [ ] **Every kind of control is defined once in the library** (partial). This flight adds:
  - a secret value column and a per-row switch column to `App.ui.keyValueTable` (the masked column the mission assigned to Flight 5);
  - the editor shell's error line (A1).

  It retires the last legacy toggle (`.tool-enable-switch`, the catalogue's "Legacy toggle 1" row) and the string-built chip list (`tools-form-helpers.js`).
- [ ] **A change to one control reaches every place it appears** (partial). `mcp-server-editor.js` (31 rows, 105 uses) and `tools-form-helpers.js` (3 rows, 11 uses) reach zero ownership-allowance rows, and `css/studio.css` drops its 7 chip, info-icon and LED rows (15 uses). Whole-app: 66 rows / 167 uses → about 25 rows / 36 uses: chat's (Flight 6), `icons.js` and `markdown.js` (2 rows each), and 4 `studio.css` rows (DD11).
- [ ] **No UI markup is built from HTML strings** (partial). `mcp-server-editor.js` reaches zero sinks (18 today). `HTML_SINK_ALLOWANCE` then holds only `areas/chat.js: 5`, and `DYNAMIC_SINK_BASELINE` is empty.
- [ ] **Each control's styles are owned by that control** (partial). The MCP-only rules in `studio.css` (the `.mcp-tool-*`, `.mcp-server-*`, `.mcp-kv-*` and connection-row families, the legacy switch and the string chip-list rules) are deleted or folded into their owners. The unused-selector report is reviewed.
- [ ] **Every migrated surface looks as it did before, apart from approved differences.** Before and after captures of the MCP editor in every state, both themes, on one seed (DD8). The approved visible changes are the planning survey's items (DD7), not ones found at the HAT.
- [ ] **Every library control works by keyboard and by role in both engines.** The new columns, the connection status, the tool disclosures and the Sensitive switch get contract tests in Chromium and WebKit.
- [ ] **The area code is organised by surface** (partial). `mcp-server-editor.js` (2,153 lines) splits into modules of 800 lines or fewer, and its line-guard allowance entry is removed.
- [ ] **Existing behaviour holds.** The defects found in planning are fixed, each with a test that fails first (DD9). The server's masked-secret contract is unchanged (DD5).

---

## Pre-Flight

### Objective
Move the MCP server editor, the largest and riskiest editor left, onto the control library with no surface left half-migrated.
- **The editor:** split `mcp-server-editor.js` by surface; then build every part from library controls, with patch-in-place Save and Cancel, async writes keyed on identity, and a real teardown.
- **The library:** grow `keyValueTable` with a secret column and a switch column for the environment variables and headers.
- **Retired:** the string chip list (`tools-form-helpers.js`) and the legacy iOS switch.
- **Visible changes:** the operator's approved survey items (DD7). The flight also fixes the editor's planning defects test-first (DD9): cross-item writes from in-flight requests, the OAuth poll that never stops, secrets lost or unmasked after a Save, and double Create.

Four changes reach beyond the MCP editor, and are named here so no lane is surprised:
- **The editor shell's error line (A1)** reaches every Library and Settings editor.
- **Sentence-case danger buttons (B7)** change the provider, connector and knowledge editors.
- **The MCP error headline (A18)** is shared with the agent MCPs tab.
- **The Library list's MCP rows (B6)** need one additive server field.

### Open Questions
- [x] Which presentation items are approved? → DD7 (operator, 2026-10-25): all of A1-A21. From B: B1 (a), B2 (b), B3 (a), B4 (a), B5 (a), B6 (a and b) and B7 (a). B8, B9 and B10 are left as they are.
- [x] Where does Refresh connection live? → DD7 B2: in the header as "Test", as in the provider editor. Its result line sits in the Connection section (A8).
- [x] Patch in place or remount? → DD4 (patch: Flight 4 DD5, plus a real `destroy`)
- [x] Where do errors go? → DD4 (Flight 4 DD3: validation errors on the field, request errors at editor level, one reader)
- [x] Does the server's secrets contract change? → DD5 (no; the client is brought into line with it)
- [x] The MCP Library rows need a "Couldn't connect" state, and the server records only successes → DD6 (an additive `_cache.last_check`, merged through one helper; reworked at Architect cycle 1)
- [x] Does `setBusy` lock Save during a consent poll? → DD4 (no: only Test stays disabled; leaving the editor cancels the poll)
- [x] Is there no Reset for servers without a sign-in? → DD6 ("Forget tools list" for a cached streamable-HTTP server with no sign-in, the escape from a stale `no_auth` hint; stdio gets neither)
- [x] Does a Test with unsaved form values record `last_check`? → DD6 (no)
- [x] Does the agent MCPs tab's tools load record it? → DD6 (yes; "the last connection check from Studio")
- [x] Where does A1's error line go in page-variant editors? → DD7 (under the page header, the same row)
- [x] **A stdio server that can't start says only "Connection closed"** (survey 0.1) → squawk **0260**, outside this flight (operator, 2026-10-25). The flight fixes only the stdio headline wording (A18).
- [x] **Companion squawks** → operator, 2026-10-25, as recommended:
  - **0214** (the OAuth callback page) in leg 08b;
  - **0216** (the Test-connection race) in leg 08b;
  - **0203** (documentation) in leg 12;
  - **0259** (`chats` re-timed) in leg 01;
  - **0257** stays its own squawk.
- [x] **The clock wording for A6 and A9** ("Connected · checked 3:42 PM" rather than "2 minutes ago"; DD9-13) → approved with the spec (operator, 2026-10-25).
- [x] **B5 elsewhere** → MCP editor only for now (operator, 2026-10-25). The stored-value behaviour is built as a column option that the masked column uses. The provider and tool editors keep today's eye.

### Design Decisions

**DD1: One flight, the MCP editor only** (mission plan; the Flight 4 debrief, Recommendation 3).
- **In scope:** the editor (`mcp-server-editor.js`), its glue (`mcp-glue.js`: lifecycle only), the shared MCP error text (`js/mcp-error.js`, A18), the agent MCPs tab's two small items (A20, A21), the Library list rows (B6), and the four reaches named in the objective.
- **Out of scope:**
  - `chat.js`'s consent link and `App.confirmDelete` (Flight 6);
  - squawk 0249 (chat's OAuth test, not this editor: the survey corrects the Flight 4 debrief here);
  - the server-side `_cache` asymmetry: `create_mcp_source` keeps a client-sent `_cache`, which the browser seeders rely on (`tests/browser/seeders.py:195-201`). It is a squawk candidate, raised in the flight log.
- **Size:** 13 autonomous legs plus the HAT (leg 08 split into 08a and 08b at Architect cycle 1). The Flight 4 debrief asked for a nudge past about 15 legs. If design review pushes past 15, the FD raises a split with the operator before continuing (Adaptation Criteria).

**DD2: Groundwork first (leg 01).** No product behaviour change.
- **`scripts/ui_capture.py` gains MCP surfaces.** Today it has only the skipped `mcp-consent-link`. The survey's seed becomes the capture seed:
  - a stdio fixture server with long args, plain and sensitive env vars, and writable paths;
  - a stdio source that always fails to start: a command that exits at once, such as the venv python with `-c "import sys; sys.exit(1)"`. Not a uvx package, whose outcome depends on `uvx` being on PATH and on its cache. The capture log records which sandbox backend ran;
  - a streamable-HTTP fixture with server info, instructions and 4 tools, and a sensitive header;
  - a legacy-protocol server (`tests/fixtures/mcp/asgi_legacy.py`);
  - a 401 server (`asgi_401.py`);
  - a sign-in state with `/test/connect` stubbed to `auth_required`.

  The fixture servers run on ports 8493 and above, inside the same namespace under `THE_ONE_TEST_NETNS=1`. They are stopped by PID.
- **Surfaces:** create (empty, stdio, HTTP); edit (stdio, HTTP, legacy, rejected, error); the tool and instructions disclosures open; dirty; a Save error; Reset armed; danger armed; sign-in; the agent MCPs tab; the Library list. Plus the provider, connector and knowledge editors, because A1 and B7 change them.
- **The before set** is taken here, before any MCP file changes, in both themes at 1280. The key/value table and the create form are also captured at 1024 (A12).
- **The allowance MOVES table** (Flight 4 debrief, Recommendation 6). `tests/_ui_ownership_allowance.py` gains a committed `MOVES` table (class, from file, to file, uses, retire-by flight), and the ownership test changes its rule to "total uses only shrink; a row may change file only through `MOVES`".
  - The same rule covers `HTML_SINK_ALLOWANCE` and `DYNAMIC_SINK_BASELINE`, whose snippets move to the new modules' keys (`test_ui_guards.py:353` fails without them). Leg 02's moves are the first entries, and every entry is retired by leg 10.
- **Squawk 0259:** `--lane chats` runs alone twice on a quiet host. Then re-budget or split by the measured-plus-25% rule, and record the quiet-host clause in CLAUDE.md's lane-budget paragraph and `scripts/run-tests.sh`'s budget comment.

**DD3: A behaviour-free split before any migration (leg 02).**
- The modules, each 800 lines or fewer, under `areas/studio/`, reached through `App.studio.mcpEditor.*` (the code survey's proposal; names and boundaries may move at the leg's design review):
  - `mcp-editor-shared.js`: constants, the runtime helpers, `hasOAuthState`;
  - `mcp-connection-fields.js` (Name, Type, runtime, command, cwd, Arguments, URL) and `mcp-sandbox-fields.js`;
  - `mcp-env-headers.js`;
  - `mcp-server-info.js`;
  - `mcp-connection-status.js`;
  - `mcp-oauth-consent.js`;
  - the controller, which stays `mcp-server-editor.js` and keeps `App.studio.renderMcpSourceEditor`.
- **Strings move unchanged** in this leg, as Flight 4 split `admin.js`. Each moved sink is a `HTML_SINK_ALLOWANCE` row change, and each moved ownership use is a `MOVES` entry (DD2). No test changes behaviour: only path pins and the code-text anchors listed below.
- **The line-guard entry goes in the leg the controller drops to 800 lines or fewer.** The guard fails on a listed module at or under 800, so if the split controller already lands there, the entry goes in leg 02.
- **Code-text anchors that are not path pins** are re-anchored where the code moves, and listed in each leg. They are never relaxed:
  - in `test_store_static.py`: the `INVALIDATION_ROWS` anchors, and the per-file minimum of 2 `invalidate('agents')` calls (Reset moves out of the controller, leaving 1);
  - in `test_consent_link_static.py`: the script order, and the `launchConsentPopup` window.

**DD4: The mount, save and dirty model** (Flight 4 DD5, plus the Flight 4 debrief, Recommendation 3).
- **One controller with a teardown.** `renderMcpSourceEditor` returns `{destroy, setBusy, setError, runTest}`, as `connector-editor.js` does. `mcp-glue.js` keeps the current controller and calls `destroy()` in two places:
  - from `reset()`, which the discard path already reaches (`studio.js:389`);
  - before every remount (create → edit), as `connector-glue.js:70-79` does.

  The auto-run after create calls `current.runTest({autoRun: true})`, not a synthetic click on the button. `destroy` cancels:
  - the OAuth poll and its `message` listener (`mcp-oauth-consent.js` `start()` returns `{cancel}`);
  - in-flight writes;
  - nothing global: `App.focusAfter.cancel()` is global and would wipe the create → edit restore, so the mount's restore targets are alive-gated instead (leg 03 design review). Cancelling the consent session stops the poll and the listener but does not close the popup, so a sign-in the operator is finishing still lands on the server.
- **Every async write is keyed on identity and latest-ness** (`App.ui.util.latest()` plus the glue's `editorGen`). A response for source A never writes into source B: not the title, the dirty mirror, the server info, the Reset control or the store. At most one consent poll runs per editor.
- **Mount once, patch in place.**
  - Edit-mode Save and Cancel patch from control handles. Reset patches too: it no longer remounts.
  - Create → edit still remounts, because the danger zone and the header change. That remount goes through `destroy` first.
  - Dirty compares a snapshot read from the handles, never from `querySelector`.
- **A Save re-baselines from the server's response, after the re-mask** (the Flight 4 practice). A field changed during the request keeps its new value and stays dirty. The controller's `source` is replaced with the response, so a later Cancel reverts to the saved values (defect 3).
- **`setBusy`** covers Save, Cancel, Create and Test while a Save, Create or Test request is in flight. The fields stay live (the connector precedent), so a change typed during the request is kept and stays dirty.
  - During a consent poll (up to 120 s), only Test stays disabled, labelled "Waiting for sign-in…". Save and Cancel stay available, a Save does not cancel the poll, and leaving the editor does (`destroy`).
  - **The shell needs a new option for this** (Architect cycle 2). `editorShell`'s `apply()` re-enables Test on every `setDirty` (`editor.js:192-198`), and it has no way to set the Test label. Leg 05 therefore adds `setTestState({disabled, label})`, with a contract test.
  - Until leg 10, the 08b Test is an `App.ui.button` placed in the hand-built header and driven directly. Leg 10 moves it to `actions.test` with `setTestState`.
- **Each surface leg moves its own fields onto handles** (Architect M6). Until leg 10, the controller still reads the form by class (`.kv-key-input`, `data-original-masked`, `.chip-list-editor`). Each surface leg (06, 07, 08b, 09) therefore mounts its module into a placeholder and moves the snapshot, collect, revert and partition for its own fields onto that module's handles, in the same leg. No leg leaves a field that the controller can no longer read, and leg 10 is left with the shell, the sections and the save model.
  - **Where the handles live.** Leg 03 creates a per-mount `handles` object and passes it to `collectFormData`, `getFormSnapshot` and `revertEditorToSource`, which today take only `container`.
  - **The dirty wiring moves with each field.** `attachStaticListeners` binds by `.field-input` and `.field-select`, so a library toggle (`.ui-toggle-input`) would stop marking the form dirty. The table's switch cell also needs a `change` path.
  - **The DOM contract is kept.** Each field keeps its `id` and `data-field` options.
- **Errors** follow Flight 4 DD3:
  - client validation and a server 422 go to the field, through `App.api.fieldErrors`;
  - request errors go to `editorShell.setError`, which carries `role=alert`;
  - Delete and Reset errors move from toasts to the editor error (a ledger row).
- **Focus** after Save, Cancel, Test and Reset goes through `App.focusAfter`.
- **Remount side-effect inventory** (Flight 4 DD5). Every patch-in-place leg lists each effect a remount used to have, and gives each a decision and a test. The code survey's table (flight log) is the starting list: the auto-run Test after create (streamable-HTTP only, with no auto-popup), the four store invalidations, `onListStale`, the server-info repaint (squawk 0102), the Reset visibility, the transport visibility, and the runtime-picker collapse and expand.
- **The stable DOM contract** (the Flight 4 DD13 idea):
  - every `mf-*` id, every `data-field`, and every testid listed in the flight log is kept;
  - `mcp-test-connection` moves to the header Test button (B2);
  - a retired testid goes into the registry's retired table.

**DD5: Secrets.** The server contract does not change.
- **The contract, kept exactly** (`the_one/interfaces/web/api.py::update_mcp_source`):
  - a masked value (`__MASKED__` or the GET mask shape, `_looks_masked`) keeps the stored secret;
  - a key omitted from `secrets` is deleted;
  - the OAuth-managed keys are pinned and never writable;
  - `config` is replaced, apart from the server-pinned `_cache`.

- **`POST .../test/connect` is stricter** (corrected at Architect cycle 1). Its override path recognises only the literal `__MASKED__` (`api.py:3804`), not the mask shape. A mask shape sent in a Test body would reach the remote server as the secret.
- **What the client must do, in both the Save and the Test body:**
  - send every surviving sensitive key, with the `__MASKED__` sentinel for an unchanged stored secret (never the mask shape) or the new value;
  - never put a masked tail into plaintext `config`;
  - never send a managed key;
  - keep the `npx -y` / `pipx run` split.
- **Renaming a stored secret's key** (Architect M9). Today the row's `__MASKED__` goes out under the new key, which the server drops (`api.py:3184`). The old key is omitted, so the server deletes it, and the secret silently disappears. In the secret column, editing the key of a row that holds a stored mask clears the value and asks for it again ("Type the value again for the new name."). Payload test first (defect 15).
- **The masked column** (leg 04):
  - the value is set through `.value` only, never an attribute (the `secretInput` contract), and a test proves no attribute holds the masked text;
  - `autocomplete="new-password"`;
  - the eye has `aria-pressed` and a per-row name.
- **B5:** a stored secret shows no eye and the hint "Stored. Type a new value to replace it." The eye appears once the operator types. Focusing a stored value selects it all, so typing replaces the mask rather than appending to it. That closes survey edge 14, where appending to a mask stores a corrupted literal.
- **Unticking Sensitive** on a row that still holds its stored mask clears the value (today's rule, `SENSITIVE_HINT`), now as a column option.
- **Re-mask after Save:** only on a row whose field still holds the submitted value. The re-mask patches rows in place (`setRow`) without moving focus (defect 4).
- **Payload tests** cover each rule against the real server: a browser round trip plus API-level asserts on the stored row.
- **Leg 07 adds the Security Reviewer** (the masked column and the env and headers module): the crew file's reviewer prompt, scoped to the secrets path.

**DD6: One connection state for the editor and the Library list (A6, A9, B6), from one additive server field.** (Reworked at Architect cycle 1: the first draft's three premises were false.)
- **One derivation, two readers.** A shared helper, `App.usage.mcpState(source)` (in `store.js` beside `mcpToolCount`), returns `{state, tools, checkedAt}`. The editor's status line (leg 08b) and the Library row (leg 11) both read it, and a test asserts they name the same state for each seeded server. The state takes the first that applies:
  1. **"Sign-in needed":** `!has_access_token && (oauth_active || last_check.status === 'auth_required')`.
  2. **"Couldn't connect":** `last_check.status === 'error'`.
  3. **"Connected":** the tools list is cached, and the last check is absent, `ok`, or an `auth_required` superseded by a token (leg 08a's design review). The row shows "{n} tools".
  4. **"Not connected":** otherwise.

  `checkedAt` is `last_check.at`, falling back to `_cache.last_updated`.

  The row's badge is "Local" or "Remote" (B3's wording), using the provider rows' `badge--*` pattern.
- **The server change** (leg 08a, before the status line, so the editor reads the recorded state from the start; the Library list follows in leg 11). Today `_cache` is written on the ok branches (`api.py` :3544, :3650, :3965), and on the error paths only `auth_posture` is written (`_persist_oauth_posture`, `_clear_auth_posture`). `tests/test_mcp_stdio_test_connect.py:275` pins "no `_cache` on a failure", so this **inverts a pinned contract on purpose**: that test is renamed and inverted, never deleted.
  - **One write point:** a thin wrapper around the route body calls one helper with the outcome, so none of the route's roughly 15 return points writes it separately.
  - **The helper records** `_cache.last_check = {status: "ok" | "error" | "auth_required", at}`.
  - **It merges, never replaces.** It goes through a new narrow repository method, `MCPSourceRepository.merge_cache(source_id, fields)`: one transaction that re-reads `config._cache`, merges the field and writes only `config`. It never rewrites the other columns and never bumps `updated_at`. Every other `_cache` key survives (`auth_posture`, `tools`, `server_info`, …), and a test proves each does.
  - **The lost-update risk is accepted in writing.** A concurrent full-row update with an older `config` can drop `last_check`, which is a hint. That includes the OAuth storage's `get`-then-update (`mcp/oauth/storage.py:119-132`). The two posture helpers (`_persist_oauth_posture`, `_clear_auth_posture`, `api.py:3432-3466`) move onto `merge_cache` too, which narrows it.
  - **Feasible as stated** (Architect cycle 2). `MCPSourceRepository.update` writes every column and stamps `updated_at` (`repositories.py:1210-1226`). A config-only re-read and write inside `write_transaction` works under the single write lock, and nothing reads `updated_at` for MCP sources.
  - **Only a Test of the saved server is recorded** (Architect cycle 2). Today the editor always sends its form body, and `override_applied` (`api.py:3822-3827`) compares the whole config, so clean forms count as overrides while unsaved secrets do not.
    - The client sends a body only when the form is dirty (the agent tab already sends none).
    - The route records only for a body-less Test.
    - The inner route function returns `(result, recordable)`. A 404, a bad JSON body, an unsupported type or an exception records nothing.
    - Unit tests include a partial-config source created through the API.
  - **Both callers record it.** The agent MCPs tab's tools load posts the same route (`agent-data.js:372`), so `last_check` means "the last connection check from Studio". `agents.md` says so.
  - **Existing guards still cover it.** The PUT's `_cache` pin and Reset's `_cache` drop.
- **The store.** On every Test outcome, not only `ok`, the client invalidates `mcp-sources`. The editor (MSE :2059) also calls `onListStale`; `agent-data.js:381` invalidates only, because it has no `onListStale`. `test_store_static.py`'s `INVALIDATION_ROWS` pin is updated in that leg.
- **The editor sees the new state** (Architect cycle 2). After every Test outcome, and after the poll, Reset and Forget, the editor refetches the source behind an identity guard. It then copies `_cache`, `oauth_active` and `has_access_token` into the controller's `source`. Today it refetches only on `ok` and never copies `_cache`.
- **Reset and its stale-hint escape** (A7; Architect M7).
  - **"Reset connection"** shows only when `oauth_active` (the `_cache` fallback at MSE :95 goes). Otherwise DD6's failure write would show it on every failed server.
  - **A cached `auth_posture: no_auth` makes a later 401 skip the re-probe** (`api.py:3864`, :3591-3599), and today only Reset clears it. So a streamable-HTTP server with no sign-in but a cached `auth_posture` or tools list (`streamable-http && !oauth_active && (_cache.auth_posture || _cache.tools)`) gets a quieter **"Forget tools list"**, A7's approved wording.
  - It calls the same `DELETE .../connection`, and its armed label reads "Forget tools list?" (leg 08b's design review).
  - stdio gets neither button. The route evicts the pool, which would stop a running stdio child, and the existing tests pin "no Reset for stdio".

**DD7: Visible changes, and the ledger.**
- **The presentation survey** ran at planning (the Flight 3 debrief practice, Flight 4 DD7). It covered seven seeded servers, the agent MCPs tab and the Library list, at 1280 and 1024 in both themes: 21 obvious items (A1-A21) and 10 taste items (B1-B10). Evidence: the review page (https://claude.ai/artifact/3QhTwTHBu5phSdgDCqwKSB) and `f5-presentation-debt.md` (FD scratchpad). The summary is copied to the flight log.
- **Approved by the operator** (2026-10-25):
  - **all of A1-A21**;
  - **B1 (a):** the section order is Connection, then Environment variables or Headers, then Sandbox, then the read-only Server and Tools, then the Danger zone;
  - **B2 (b):** Refresh connection becomes the header's **Test** button (`editorShell` `actions.test`, edit mode only, as in the provider editor). Its result line (A6/A8/A9) sits at the end of the Connection section, as `provider-test-result` does. Reset stays beside that status line, shown only when the server has a sign-in, with "Forget tools list" for a cached streamable-HTTP server without one (A7, DD6);
  - **B3 (a):** "Local program (stdio)" and "Remote server (HTTP)", "Choose how it connects", "Python package (uvx)", "Node package (npx)", "Python package (pipx)", "Other command…" (the rest at the leg's design review, plainly worded);
  - **B4 (a):** a middle ellipsis plus the full value on hover, for Arguments and Writable paths (the library `chipList` behaviour);
  - **B5 (a):** DD5;
  - **B6 (a and b):** DD6;
  - **B7 (a):** sentence-case danger buttons ("Delete MCP server", "Delete provider", "Delete connector", "Delete knowledge base") in all four editors, and armed labels in the library form ("Confirm delete?");
  - **left as they are:** B8 (the save flash), B9 (the MCPs tab layout) and B10 (the protocol version stays, shown as one of A16's facts).
- **Shared reaches:**
  - **A1** is an `editorShell` change, built in leg 05 (Architect M5):
    - **The new place.** The error moves out of the button cluster to its own full-width row under the header, still inside `shell.el` (so the knowledge `_HEADER .editor-error` locators keep resolving).
    - **The page variant** puts it under the page header in the same way.
    - **The pins it moves**, each retargeted, never relaxed:
      - `test_ui_editor_contract.py:74-80` and `:271-274`;
      - `test_ui_page_header_contract.py:150` and `:221`;
      - `test_flow_provider_editor.py:134` and `:145`;
      - `test_design_tokens_a11y.py:471-477`.
    - **The old selector stays until leg 10.** The `.form-actions .editor-error` colour rule (`components.css:1292`) is kept, because the hand-built MCP header still uses it in legs 05-09. Leg 10 deletes it.
    - **Tests:** a computed-layout test and a long-error degenerate test, both in both engines; every editor lane is run.
  - **B7** reaches the provider, connector and knowledge editors.
  - **A18** reaches the agent MCPs tab.
- **Every leg appends its visible differences to the ledger** (flight log, rows 1-34 at planning). The HAT walks the ledger.
- **Ledger criteria carry a derived-relationship test** where they describe a look (Flight 4 debrief, Key Learning 2). For example: the Test result line names the same state as the status dot; the badge text matches the Type select's label; a row's accessible names name its key.

**DD8: Captures.** Before set in leg 01; after set in leg 12. Each is compared with PIL `ImageChops`, and each difference is mapped to a ledger row. Then, separately, each mapped difference is judged against what its row promised (Flight 4 debrief, Key Learning 3: explained is not correct). Captures are local evidence and are never committed.

**DD9: The defects found in planning are fixed, test first.** Each gets a test that fails on today's code, then the fix (code survey §5; numbers are the survey's):
1. In-flight Save, Test and OAuth-poll responses write into the next editor (leg 03).
2. The OAuth timer and `message` listener are never torn down (leg 03).
3. Cancel after an edit-Save reverts to the pre-Save values, and the next Save drops the secrets the first one added (leg 10).
4. Secrets are not re-masked after Save, and unticking Sensitive then stores the secret in plaintext config (leg 07).
5. Create and Save have no busy state, so a double-click on Create makes two sources (leg 10).
6. Reset discards edits, leaves a phantom dirty flag and loses focus (leg 03 for the dirty flag and focus; leg 08b makes Reset patch in place).
7. A chip edit after Cancel is not tracked as dirty (leg 06).
8. Two consent pollers can run at once (leg 03).
9. Test writes Save's validation text into the editor error (leg 08b).
10. Errors are not on the field, not announced, and Delete and Reset errors are toasts (legs 08b and 10).
11. Unnamed key/value inputs; an eye with no `aria-pressed`; identical row names; an LED not exposed to assistive tech (legs 04, 07, 08b).
12. The subtitle goes stale after Save (leg 10, with A4).
13. The relative time is computed outside `App.time` (leg 08b). `App.time` has no relative-time helper (`time.js:220`), and a ticking one would need a timer that `destroy` cancels. So the status line uses the DD14 clock wording through `App.time.formatClock` (with `formatDate` when not today): "Connected · checked 3:42 PM", "Last connected 3:42 PM". This adjusts A6's and A9's approved "2 minutes ago" to the app's clock rule, and is recorded as a ledger row.
14. Appending to a masked tail stores a corrupted secret (leg 04, DD5).
15. Renaming a stored secret's key silently deletes the secret (leg 04, DD5).
- **Survey 0.2** (a failed Test still says "Connected") is A9, in leg 08b.

**DD10: Standing leg rules** (Flight 4 DD11, plus the Flight 4 debrief). Every leg spec carries these:
- **No consumer CSS on library internals and no `[data-testid]` style hooks.** A needed look becomes a library option in a control leg.
- **Mind the cascade layers.** A rule moved into a control deletes or narrows the area rule in the same change. A computed-style check under an `area-studio` ancestor proves the owner's rule applies. Watch the `.editor-section--flush` `!important` trap (Flight 4 debrief).
- **What the old control gave for free** (Flight 4 debrief, Recommendation 1). Every control-replacement leg lists it and keeps each item or records a ledger row. Examples:
  - a password input's masking and autocomplete behaviour;
  - a native checkbox's Space toggle and form value;
  - `<details>` opening on find-in-page;
  - the chip input's Enter, comma, paste-split and Backspace behaviour;
  - a `<select>`'s typeahead.
- **Derived-relationship or degenerate-input criteria** on every relabel or restyle (DD7). Examples: an empty server name; a value 200 characters long; a stdio source with no args; a server with no tools; a tool with no description.
- **Append to the ledger,** with an in-progress log line at each internal checkpoint.
- **Retarget pins, never relax them.**
- **The remount side-effect inventory** in every patch-in-place leg (DD4).
- **Re-run the line guard and `git grep` the moved paths and deleted classes** across `tests/`, `scripts/`, `Makefile`, `docs/` and `tests/behavior/`, and run the owning lane for each deleted class (the Flight 4 stale-test lesson). Paste the hits into the leg.
- **A new browser test file gets its lane** in `scripts/run-tests.sh`: `mcp_pat` and `library_pat` are explicit lists. Otherwise it lands in `shared`.
- **A HAT-fix Developer brief** states "a library option, never consumer CSS on library internals" up front.

**DD11: When a control owns its classes** (Flight 4 DD12). The allowance only shrinks.
- **The masked column** adds classes under `ui-kv-*` (new marker classes). The legacy `.mcp-kv-*` rules are deleted in leg 07, the leg that moves their last user.
- **The legacy switch** (`.tool-enable-switch*`, `studio.css:1268-1340`). Leg 06 moves "Allow network access" off it. Its last user is the per-row Sensitive switch (`mcp-server-editor.js:943-946`), which moves in leg 07. So leg 07 deletes the rules, removes the catalogue row ("Legacy toggle 1"), and retargets its token and contrast pins to `App.ui.toggle`:
  - `test_design_tokens_a11y.py:579-581, 633-643`;
  - `test_deep_violet_computed_styles.py:48-49`;
  - `test_ui_tile_contract.py:681`;
  - `test_flow_studio_mcp_editor.py:729-748`.
- **The chip list.** In leg 06, `tools-form-helpers.js` is deleted with its `index.html:103` tag.
  - **First, the four guarded reads.** Every read is guarded (`if (helpers && helpers.readChipListValue)`), so deleting the file early would throw nothing: Save would quietly send empty args and writable paths. The four sites must be replaced by `chipList` handles before the file goes: `getFormSnapshot` `:1018`, `collectFormData` `:1729-1741`, `revertEditorToSource` `:1634-1666`, and the mount `:958-991`. A payload test that asserts the saved args and writable paths is written first.
  - **Then the cleanup.** `test_tools_form_helpers_assets.py` is inverted into a "the file is gone" test. The two legacy-parity tests in `test_ui_chip_list_contract.py` (`:292`, `:385-397`) are retired, or frozen as a fixture, with a reason (the `_legacy_tool_css.py` precedent). The `studio.css` `:not(.ui-chip-list)` rules (`:1343-1404`) and their 5 allowance keys are deleted.
- **The `.mcp-tool-*` and `.mcp-server-*` CSS families** are deleted in leg 09. `test_ui_disclosure_contract.py:243-259` uses `mcp-tool-item`; it is retired or frozen as a fixture in that leg, with a reason. The stale comment at `studio.css:136-157` is fixed.
- **The emitted-class guard** (`test_ui_emitted_classes.py`) keeps every new class owned.

**DD12: Tests, lanes and specs.**
- **Lanes:**
  - `mcp` (364/450 s) carries most of the new editor tests;
  - `library` (173/210 s, 82%) holds `test_mcp_test_connection_button.py`, so new tests go to `mcp`;
  - `contracts-controls` (318/420) carries the masked column, with both engines under `THE_ONE_REQUIRE_WEBKIT=1`;
  - `providers`, `knowledge`, `library`, `settings` and `settings-tools` are run for A1 and B7;
  - the unit tier carries leg 08a (the route, `merge_cache`, the inverted pin);
  - `agents` for the MCPs tab (A20, A21);
  - `shared` for the chip-list label test.

  Re-budget at leg 12 by the 15% and 1.3x rules, using quiet-host readings only (DD2).
- **Batch mode with the HAT at the end** (the operator's preference; Flight 4 debrief methodology notes). Legs run in batches with scoped checks: each leg's own lanes, plus the unit guards. At each batch end:
  - grep the tests for every deleted selector and class, and run its lane;
  - run the changed lanes with at most one other lane running when a budget reading counts.

  The full gate runs at leg 12 and after any HAT code change.
- **Fixed waits.** No new test uses a fixed `wait_for_timeout` to prove "nothing changed after a late response". It holds the request with `page.route`, releases it, waits for it to finish, then asserts. This is also squawk 0216's fix.
- **Behavior specs:**
  - `list-and-detail.md` step 13 (Add → MCP server, Streamable HTTP, Create) is re-read in leg 10 and amended for B2 and B3's wording;
  - `jump-to-palette.md` step 6 is checked in leg 12.
- **A new behavior spec, `mcp-sensitive-headers-round-trip`,** is drafted in leg 07 and run in leg 12. It covers a sensitive header created, saved, re-masked, edited, unticked and cleared, against a dedicated dev instance. It also checks that the stored row (through the API) never holds a mask or a plaintext secret in `config`. It is the real-environment check of DD5, which no existing spec covers.

### Citation Audit

Verified against the working tree at `b1e47ae` (FD read and grep, 2026-10-25, plus the code survey's citations, spot-checked):

| Citation | Status |
|---|---|
| `js/ui/key-value-table.js` — `var CELL_TYPES = { text: true };` (:6); an unknown `type` throws (:39); `root.addEventListener('input', onInput)` only (:123); `setValues` rebuilds rows and focuses (:242-258) | verified |
| `js/areas/studio/mcp-server-editor.js::renderMcpSourceEditor` — one `container.innerHTML = html` mount (:714); returns nothing (:736-737); Refresh row only `!isCreate` (:546); `hasOAuthState` gates Reset (:553) | verified |
| `js/areas/studio/mcp-glue.js` — `editorGen` checks at :65 and :84 only; `discardOpen_` from ctx (:27); `reset()` (:235) | verified |
| `js/areas/studio.js` — `discardOpen_` blanks the content and bumps `editorGen`; it already reaches `mcpGlue.reset()` (:389), so `destroy` from `reset()` covers discard (corrected at Architect cycle 1) | verified |
| `the_one/interfaces/web/api.py::update_mcp_source` (:3143) — "Keys absent from the incoming secrets dict are dropped" (:3165-3173); `_cache` pinned (:3218-3221) | verified |
| `api.py` test/connect — `persisted_config["_cache"] = {…}` written on the ok branches (:3544, :3650, :3965); the error paths write only `auth_posture` (`_persist_oauth_posture`, `_clear_auth_posture`); the override path recognises only the literal `__MASKED__` (:3800); `override_applied` (:3825) (corrected at Architect cycle 1) | verified |
| `tests/test_mcp_stdio_test_connect.py:275` — pins no `_cache` on a failure (DD6 inverts it) | verified (Architect) |
| `js/areas/studio/agent-data.js` — the MCPs tab's tools load POSTs `/test/connect` (:372) and invalidates only on ok (:381) | verified (Architect) |
| `js/ui/editor.js` — `section` returns `setTitle` (:239) | verified (Architect) |
| `api.py::_mcp_source_response` (:2890) — `oauth_active`, `has_access_token`; no last-outcome field | verified |
| `js/ui/editor.js::editorShell` — `actions.test` builds a secondary Test button in the cluster (:153-163); `setBusy` disables it (:198) | verified |
| `js/areas/studio/provider-editor.js` — `h.testStatus = App.ui.status({ testid: 'provider-test-result' })`, placed last in the Connection section (:203-208) | verified |
| `App.adminFormHelpers` — only `mcp-server-editor.js` calls it outside its own file (5 calls, 2 comments) | verified |
| `tests/test_ui_guards.py` — `HTML_SINK_ALLOWANCE` `chat.js: 5`, `mcp-server-editor.js: 18` (:134-137) | verified |
| `tests/test_area_module_size.py` — `"studio/mcp-server-editor.js": 2153` (:26) | verified |
| `tests/_ui_ownership_allowance.py` — 66 rows / 167 uses; MSE 31/105, `tools-form-helpers.js` 3/11, `studio.css` 11/21 | verified |
| `js/areas/studio/library-pane.js::libraryItem` — MCP meta `'Tools not loaded'` or the tool count (:226-227) | verified |
| `scripts/run-tests.sh` — `[library]=210`, `[mcp]=450`; `mcp_pat` and `library_pat` explicit lists (:181, :189) | verified |

### Prerequisites
- [x] The operator's answers on the three open questions (0.1 → squawk 0260; the companions as recommended; B5 MCP-only), 2026-10-25.
- [ ] The branch `flight/05-mcp-editor-on-the-library` is created from `main` (`b1e47ae` or later) at flight start.
- [ ] WebKit userland and `THE_ONE_TEST_NETNS=1` work. Re-verify at the start of every leg that runs browser tests.
- [ ] The MCP fixture servers (`tests/fixtures/mcp/hello_server.py`, `asgi_legacy.py`, `asgi_401.py`) start under the namespace (proven by the survey, 2026-10-25). Re-verify in leg 01.
- [ ] The before captures are taken in leg 01, before any MCP file changes.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified (the branch, WebKit and the fixture checks are re-verified at flight start and per leg)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Groundwork and the split first**, with no behaviour change.
2. **The lifecycle next** (teardown, identity, one poller), so every later leg builds on a controller that cannot write into the wrong editor.
3. **The library pieces** (the masked column; the shell's error line, B7, any small options), each contract-tested in both engines before its consumer moves.
4. **Then each surface module moves onto the library**, in dependency order: the fields, the env and headers, the connection-check record (server), the connection status and sign-in, the server info and tools. Each moves its own fields' snapshot, collect and revert onto handles in the same leg (DD4).
5. **The controller last:** it composes the shell, sections and danger zone, takes the patch-in-place Save and Cancel, and takes the editor under 800 lines with zero sinks and allowance rows.
6. **The list rows and the MCPs tab**, then the close and the HAT.

### Checkpoints
- [x] The MCP surfaces are in the capture tool, the before set is taken, the MOVES rule is in, and `chats` is re-measured.
- [ ] The editor is split into modules with no behaviour change; full gate green.
- [x] The editor has a teardown, async writes are keyed on identity, and one consent poll at most; defects 1, 2, 6 and 8 fixed.
- [x] The masked column and the shell's error line are in the library, contract-tested in both engines; the channel map is unchanged.
- [ ] The server records the last connection check without losing any other `_cache` key, and the editor and the Library list read one derived state.
- [ ] The fields, the env and headers, the connection status and sign-in, and the server info are on the library; `tools-form-helpers.js` and the legacy switch are gone.
- [ ] The controller is on `editorShell` with patch-in-place Save and Cancel; zero sinks and zero allowance rows in the MCP files; under 800 lines.
- [ ] The list rows and the MCPs tab items are in; docs, budgets and the after set are done; full gate green; the new behavior spec passes.
- [ ] HAT passed, and the close checks re-run after any HAT code change.

### Adaptation Criteria

**Divert if**:
- The split cannot stay behaviour-free (a test changes behaviour, not just a path pin): stop and re-plan the boundary.
- The masked column cannot serve the editor without changing the channel map's behaviour: keep the channel map on the text column and raise it.
- Any server change beyond DD6 (`last_check`, `merge_cache`) and squawk 0214's callback page turns out to be needed, above all anything in `update_mcp_source`'s secrets handling, or a re-probe on a 401 with a cached `no_auth` hint: raise it as its own question.
- Design review pushes the flight past 15 autonomous legs: raise a split with the operator (DD1).

**Acceptable variations**:
- Module boundaries and names inside DD3.
- Option names on the new columns.
- Splitting a leg further at its design review (never merging legs).
- An `mcp` lane split.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `groundwork-and-before-set` (01): the MCP surfaces and fixture seed in `scripts/ui_capture.py`; the before set; the `MOVES` rule for the ownership and sink allowances; squawk 0259's quiet-host re-measure, the re-budget and the CLAUDE.md clause.
- [x] `editor-split` (02): `mcp-server-editor.js` split into the DD3 modules, behaviour-free, with strings moved unchanged.
  - The guards follow the move: the sink and allowance rows (including the `DYNAMIC_SINK_BASELINE` keys) move through `MOVES`.
  - Path pins and code-text anchors are retargeted, as listed in DD3.
  - The line-guard entry goes here if the controller lands at 800 lines or fewer.
  - Lanes: `mcp`, `library`, `shared`, `routing` (the store pins).
- [x] `editor-lifecycle` (03), **tier high (lifecycle, async)**: `renderMcpSourceEditor` returns `{destroy, setBusy, setError, runTest}`; the glue calls `destroy` from `reset()` and before every remount, and runs the auto-run after create through `runTest({autoRun: true})`; `latest()` and identity guards on Save, Test and the poll; the per-mount `handles` object passed to collect, snapshot and revert (DD4); `oauthConsent.start()` returns `{cancel}` with one poll at most; Reset's dirty flag and focus. Defects 1, 2, 6 (part) and 8, test first.
- [x] `kv-secret-column` (04), **tier high (a shared library control, secrets)**:
  - `keyValueTable` gains a `secret` cell (masked by a boolean row key, the `secretInput` shell, `.value` only, `autocomplete="new-password"`, the eye with `aria-pressed` and a per-row name, B5's stored-value hint and select-on-focus) and a `toggle` cell (`App.ui.toggle`, with a `change` listener);
  - a `clearOnUnmask` option, a focus-keeping `setRow`, and per-row remove names;
  - new `ui-kv-*` marker classes; the catalogue row; contract tests in both engines;
  - the connector channel map unchanged (its 32 tests pass untouched).
  - Key edits on a row with a stored mask clear the value and ask for it again (DD5).
  - Defects 11 (part), 14 and 15.
- [x] `shared-editor-changes` (05), **tier high (every editor)**:
  - the `editorShell` error line (A1), per DD7, with the pins listed there retargeted, the page variant included, and the `.form-actions .editor-error` rule kept for the MCP header until leg 10;
  - `editorShell` `setTestState({disabled, label})`, so a dirty change does not re-enable a Test held for a consent poll (DD4), with a contract test in both engines;
  - B7's sentence-case danger buttons in the provider, connector and knowledge editors.
  - (`section.setTitle` already exists, `editor.js:239`, so the env and headers title swap needs no new option.)
  - Lanes: `providers`, `library`, `knowledge`, `settings`, `settings-tools`, both contracts lanes.
- [x] `connection-and-sandbox-fields` (06):
  - Name, Type, the runtime select, command, cwd, Arguments and URL on `field`, `select`, `textInput` and `chipList`; Writable paths on `chipList` with the middle ellipsis (B4); Allow network on `App.ui.toggle`;
  - the presentation items: B3's labels, A5's hint, A10, A14 and A17;
  - the fields' snapshot, collect and revert moved onto their handles (DD4); field `setError` handles for leg 10; defect 7;
  - the chip-list handover (DD11): the four guarded helper reads replaced first, with a payload test written first; then `tools-form-helpers.js` deleted with its script tag, its asset test inverted, the chip-list parity tests retired, and the `studio.css` chip rules and their 5 allowance keys gone. The legacy switch stays until leg 07.
- [x] `env-and-headers` (07), **tier high (secrets; the Security Reviewer)**:
  - the env and headers module on the masked column (A11-A13, the table named "Environment variables" or "Headers"), with its snapshot, collect, revert and partition on handles (DD4);
  - the re-mask after Save (defect 4); the Save and Test bodies send `__MASKED__`, never a mask shape (DD5);
  - the payload round-trip tests (DD5); the `mcp-sensitive-headers-round-trip` behavior spec drafted;
  - the `.mcp-kv-*` rules deleted; the legacy switch deleted (its last user moves here) with its catalogue row and its pins retargeted (DD11).
- [x] `connection-check-record` (08a), **tier high (server, an inverted pin)**:
  - DD6's server part: the route wrapper and the one helper, with the inner function returning `(result, recordable)`; `MCPSourceRepository.merge_cache`, with the two posture helpers moved onto it; `last_check` only for a body-less Test of the saved server; unit tests for each outcome, a partial-config source, the survival of every other `_cache` key, no `updated_at` bump, the PUT pin and Reset's drop;
  - the client sends a Test body only when the form is dirty;
  - `tests/test_mcp_stdio_test_connect.py:275` inverted and renamed;
  - `App.usage.mcpState` with unit-level browser tests;
  - the client invalidates `mcp-sources` on every outcome (the editor, plus `onListStale`; `agent-data.js`), with the `INVALIDATION_ROWS` pin updated.
  - Lanes: the unit tier, `mcp`, `agents`, `routing` (`test_store_library.py`).
- [ ] `connection-status-and-sign-in` (08b), **tier high (OAuth, focus, popup gesture rules)**:
  - Test in the header (B2), edit mode only;
  - the status line at the end of Connection, on `App.ui.status`, reading `App.usage.mcpState` (A6, A8, A9, survey 0.2), with the DD14 clock wording (defect 13);
  - the identity-guarded refetch after every Test outcome, the poll, Reset and Forget, copying `_cache`, `oauth_active` and `has_access_token` into the controller's source (DD6);
  - "Reset connection" only when `oauth_active`, and "Forget tools list" by DD6's predicate, both patching in place on `App.ui.confirm` (A7, defect 6);
  - the consent block on `App.ui.consentLink` (no alias), with A19's wording; A18's stdio headline and one size in both hosts (`js/mcp-error.js`, `.mcp-tools-error`);
  - defects 9 and 10 (part); squawks 0216 and 0214 (the callback page styled with no `/static/` dependency, a unit test).
  - It keeps the popup rules: open synchronously on the click, never auto-popup on the auto-run path, a `null` from `window.open` is not a failure, the same-origin `message` check, the 120 s ceiling, and `isSafeUrl`.
- [ ] `server-info-and-tools` (09): the Server section and tools list DOM-built on `section`, `disclosure`, `codeBlock` and `facts` (A15, A16, with the protocol kept as a fact per B10), reconciled in place (squawk 0102's repaint kept); `App.safeUrl` fail-closed kept (squawk 0010); the `.mcp-tool-*` and `.mcp-server-*` CSS deleted (DD11).
- [ ] `editor-controller` (10), **tier high (the save model)**:
  - `editorShell`, `section` and `dangerZone`, with B1's section order;
  - patch-in-place Save and Cancel from the handles; the `source` replaced from the response (defect 3); `setBusy` on Create and Save (defect 5);
  - `fetchJson` with `fieldErrors` (A2, defect 10); A3's copy; A4's subtitle, updated after Save (defect 12);
  - `App.ui.flash` and `App.ui.confirm` (no `App.showFlash`, `App.confirmDelete` or `App.icon`); the side-effect inventory;
  - zero sinks and zero allowance rows in every MCP file; the `MOVES` entries retired; the line-guard entry removed;
  - `list-and-detail.md` step 13 amended.
- [ ] `list-rows-and-mcps-tab` (11): the Library list's MCP state and badge from `App.usage.mcpState` (B6), with a test that each seeded server's row and editor status name the same state; A20 and A21 in the agent editor. Lanes: `mcp`, `agents`.
- [ ] `mcp-close` (12):
  - the alias recount into the mission's Known Issues; the unused-selector report;
  - the catalogue rows (the secret input, "Legacy toggle 1" removed, the editor header, the chip list, `keyValueTable`); `agents.md` (the invalidation map's new paths, the MCP editor contract, the `last_check` note, the masked column);
  - CLAUDE.md: the control-library paragraph's flight-by-flight detail moves to `agents.md` (Flight 4 debrief, Recommendation 8), and the "eleven lanes" wording fixed;
  - squawk 0203's documentation; `jump-to-palette.md` checked; the stale `tool-enable-switch`, `tools-form-helpers` and `adminFormHelpers` mentions fixed (the list under Verification);
  - the lane re-budget (quiet host); the after set and its compare (DD8); the full gate; the behavior spec run.
- [ ] `flight-hat` *(the operator wants one per flight, at the end)*:
  - the operator walks the MCP editor in every seeded state, the agent MCPs tab, the Library list, and the provider, connector and knowledge editors (A1, B7), in both themes;
  - the steps come from the ledger, and the FD dry-runs each one on the seeded instance; destructive steps (Delete, Reset) use their own disposable, clearly named servers;
  - at least one step covers state the operator isn't looking at: a sign-in completed in the popup while the editor is closed, then reopened;
  - if the HAT changes code, leg 12's close checks re-run before landing, and a HAT feature gets the Accessibility Reviewer too.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
- **Guards:**
  - `tests/test_ui_guards.py`: `HTML_SINK_ALLOWANCE` is `{"areas/chat.js": 5}` and `DYNAMIC_SINK_BASELINE` is empty;
  - `tests/_ui_ownership_allowance.py` has no row for any MCP file or `tools-form-helpers.js`, and `MOVES` is empty;
  - `tests/test_area_module_size.py` has no `mcp-server-editor.js` entry;
  - `git grep -n "adminFormHelpers\|tools-form-helpers\|tool-enable-switch" the_one/interfaces/web/static/` finds nothing. The doc mentions are fixed in leg 12: `docs/ui-control-inventory.md` (45, 58, 110), `the_one/agents.md` (1257, 1914, 2083, 2111, 2115, 2169, 2171, 2308, 2311, 2630), the testid registry (72, 416), and the comments at `studio.css:401, 433`, `components.css:329` and `js/ui/chip-list.js:9`.
- **Gate:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate` passes, with no lane over budget on a quiet host.
- **Behavior spec:** `/mission-control:behavior-test mcp-sensitive-headers-round-trip` passes on a dedicated dev instance (never 8484 or the default data dir).
- **Captures:** the after set is approved by the operator against the ledger at the HAT.
