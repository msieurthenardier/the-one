# UI Testid Registry

> **Guarded document — the test suite enforces sync.**
> `tests/test_ui_guards.py` extracts every `data-testid` definition from
> `the_one/interfaces/web/static/js/**/*.js` and diffs it against the tables
> below in both directions. Adding, renaming, or removing a testid in JS
> without updating this registry (or vice versa) fails the unit tier with an
> exact add/remove list. To update: edit the JS, then add/remove the matching
> row here. Keep each table sorted by id.
>
> Naming convention for NEW ids: `{area}-{element}` (existing ids are
> grandfathered as-is — see Flight 1 design decisions, mission 17).

Two id classes are registered:

- **Literal ids** — the full id appears as-is in the source (HTML-string
  attribute, `setAttribute('data-testid', '...')`, or an `App.ui` factory's
  `testid: '...'` option — including a `<lower>Testid` option such as
  `App.ui.searchList`'s `inputTestid` / `rowTestid`, M25 F4 L1).
- **Parametric prefix families** — the id is built by concatenation from a
  static prefix (e.g. `mcp-source-row-` + id). Registered by prefix; the guard
  matches families by prefix.

A third table lists **manual exceptions**: ids carried through variables or
parameters, invisible to regex extraction. The guard asserts each still
appears as a plain string literal somewhere in the JS sources, so deletion is
caught — but it cannot see where the attribute is emitted.

## Literal testids

| Testid | Surface | Notes |
|--------|---------|-------|
| `admin-pf-pull-btn` | admin | The Ollama Pull button; label "Pull · {size}" with a known size, "Pull" for an unknown one, "Checking size…" during the re-check; disabled with nothing selected, during the re-check and during a pull (Ollama pull sizes, sortie 01) |
| `admin-pf-pull-cancel` | admin | The pull progress bar's Cancel button; focus lands here when a confirmed pull starts (Ollama pull sizes, sortie 01) |
| `admin-pf-pull-confirm` | admin | The pull confirmation `<dialog>` (`App.ui.modal`), opened on every Pull after the size re-check (Ollama pull sizes, sortie 01) |
| `admin-pf-pull-confirm-cancel` | admin | The confirmation's Cancel (autofocused; agrees with Esc and the backdrop) (Ollama pull sizes, sortie 01) |
| `admin-pf-pull-confirm-go` | admin | The confirmation's confirm action: "Pull {size}", or "Pull anyway" when the size is unknown (Ollama pull sizes, sortie 01) |
| `admin-pf-pull-error` | admin | The pull panel's error line (a failed size re-check or a failed pull) (Ollama pull sizes, sortie 01) |
| `admin-pf-pull-progress` | admin | The pull progress bar container (hidden until a pull starts) (Ollama pull sizes, sortie 01) |
| `admin-pf-pull-select` | admin | The Pull Model `<select>` of `name:tag (size)` entries; disabled with the loading copy while the catalog fills (Ollama pull sizes, sortie 01) |
| `admin-pf-pull-size` | admin | The `aria-live` status line under the Pull row: "Download: {size}, from the Ollama registry." or the size-unknown warning (Ollama pull sizes, sortie 01) |
| `agent-chat-btn` | studio | The agent editor header's **Chat** (`App.ui.button` secondary, the `chat` icon), DOM-inserted into `.form-actions` before Cancel on a SAVED agent only (absent in create mode); `App.chat.chatWith(name)`: the guarded go() to `#chats/~new/{name}` with the chat area's pick intent, so a dirty editor asks once (M25 F4 L6, DD8) |
| `agent-empty` | studio | Agents start page node with NO agents (the description plus the line "No agents yet."; M25 F3 L3, copy and structure changed in M25 F6 L4c) |
| `agent-empty-new` | studio | Agents start page action "New agent" (both variants) -> `#agents/~new` (M25 F3 L3) |
| `cancel-connector-btn` | studio | Connector-editor header Cancel, from `App.ui.editorShell` (`actions.cancel`); enabled from the first render on the create form, else once the form is dirty (M31 F3 L07a) |
| `cancel-knowledge-btn` | studio | Knowledge detail view header Cancel, disabled until dirty (`App.ui.editorShell` `cancel`; L6-D1, M24 F06 L06; M31 F3 L05a) |
| `connector-doctor-btn` | studio | Connector-editor Diagnostics "Run doctor" (`App.ui.button`) (M23 F02 L02; M31 F3 L07a) |
| `kb-create-cancel-btn` | studio | Knowledge-base create form Cancel: discards and replaces to `#library/knowledge`; enabled on a clean form, disabled while Create is in flight (`editorShell` `cancel`; M25 F3 L4a, DD8; M31 F3 L05a) |
| `kb-create-submit-btn` | studio | Knowledge-base create form Create (enabled on a clean form; busy from submit until the request fails; `editorShell` `save`; M24 F06 L01; M25 F3 L4a; M31 F3 L05a) |
| `root-heading` | studio | The page `h1` ("Agents" / "Library") at an Agents or Library root with no editor open, visible as the start page's title since M25 F6 L4c (DD15; it was visually hidden in L1a, DD11); absent with an item open |
| `provider-models-help` | admin | The provider editor's one line of help under "Available models" (M25 F6 L1a, DD10) |
| `provider-api-key-help` | admin | The provider editor's help line under the API-key / Token field (hidden when the selected type has none; sortie 03 DD6) |
| `provider-test-result` | admin | The provider editor's Test result line (`App.ui.status`, `data-state` success / warning / danger / pending; hidden until a test runs). On a `reauth_required` result its text span also carries `plan-test-reauth` (M31 F1 L7) |
| `provider-token-expiry` | admin | The Claude Plan (Token) editor's "Token added … · expires around …" line (edit mode, `data-state` ok/soon/past; absent otherwise; sortie 03 DD6) |
| `provider-models-agents-link` | admin | Its "Agents" link -> `#agents` (M25 F6 L1a) |
| `agent-item` | studio | Agents list row: an `App.ui.listPane` `<a href="#agents/{name}">` (M25 F3 L3; kept from the retired tile grid) |
| `agent-knowledge-empty-state` | studio | Agent editor Knowledge tab — no knowledge bases exist, marker still set (M24 F06 L03) |
| `agent-knowledge-list` | studio | Agent editor Knowledge tab — attach-row list container (M24 F06 L03) |
| `agent-knowledge-load-error` | studio | Agent editor Knowledge tab — the knowledge-base fetch failed; no `data-kb-list-loaded` marker (DD-4, L3-D1, M24 F06 L03) |
| `agent-knowledge-tab` | studio | Agent editor Knowledge tab root; carries `data-kb-list-loaded="true"` on a successful fetch (DD-4, M24 F06 L03) |
| `agent-load-error` | studio | Agent editor — on the header's error slot (`span.editor-error`), present only while the fresh `GET /api/agents/{name}` has failed; the editor renders the last-known copy, the slot reads why Save is off and Save is disabled (squawk 0090) |
| `agent-picker` | chat | The agent picker `<dialog>`: an `App.ui.modal` chooser ("Start a chat with…", 640 wide at top 72, dismissible), built fresh on every `App.chat.openPicker` (M25 F4 L4a) |
| `agent-picker-close` | chat | The agent picker's "Esc" close button (accessible name "Close (Esc)"; the modal's `closeButton`, M25 F4 L4a) |
| `agent-picker-row` | chat | One agent option in the picker (`role=option`, `data-agent`; the `searchList` `rowTestid`; an agent in both "Recently used" and "All agents" has two, M25 F4 L4a) |
| `agent-picker-search` | chat | The agent picker's search input ("Find an agent"; the `searchList` `inputTestid`, focused on open, M25 F4 L4a) |
| `agent-stored-value-changed` | studio | Agent editor General tab — a `App.ui.status` note (hidden unless set) shown when a self-configuration approval or restore changed the stored description or system prompt while the operator had typed over that field: "The stored description changed. Save will replace it with your text." (or "system prompt"). Cleared by Save, Cancel and a new editor identity, and hidden once the field is clean again (M31 F2 L10a) |
| `agent-select-empty` | studio | Agents start page node WITH agents (the description plus "Pick an agent from the list to edit it."; M25 F3 L3, copy changed in M25 F6 L4c) |
| `agents-filter` | studio | Agents list filter input ("Filter agents"; matches name, model id and provider type slug) (M25 F3 L3) |
| `agents-list` | studio | Agents list column root, the `App.ui.listPane` `<section>` in the aside (M25 F3 L3) |
| `approval-mode-error` | studio | Self-configuration tab approval-mode toggle (M21 F02 L02) |
| `approval-mode-status` | studio | Self-configuration tab approval-mode status line (M21 F02 L02) |
| `approval-mode-toggle-btn` | studio | Self-configuration tab approval-mode on/off (M21 F02 L02); rendered as an `App.ui.toggle` checkbox `<input>` (it was the legacy `.tool-enable-switch`, deleted in M31 F5 L07) as of the HAT UX pass (M21 F02 L04) — same testid, moved from the retired `<button>` |
| `platform-sections` | admin | The Prompts page's mount for the platform prompt blocks (Flight 2 leg 1c, DD8; it replaced `base-prompt-content`) |
| `rules-prompt-content` | admin | The Prompts page's read-only rules-layer example (M27 F3 L3) |
| `notes-prompt-content` | admin | The Prompts page's read-only notes-layer example (M27 F3 L3) |
| `notes-prompt-content-tool-free` | admin | The Prompts page's read-only notes-layer example for a model without tools (no saving instructions; Flight 2 leg 1c) |
| `date-prompt-content` | admin | The Prompts page's read-only date-layer wording for an agent with the `current_time` tool (M28 F1 L3) |
| `date-prompt-content-without-tool` | admin | The Prompts page's read-only date-layer wording for an agent without the tool (M28 F1 L3) |
| `date-time-chosen` | admin | The chosen-zone line under "Choose a time zone" on the Date and time page (M28 F2 L3) |
| `date-time-error` | admin | A failed save's server message on the Date and time page (M28 F2 L3) |
| `date-time-mismatch` | admin | The browser-zone mismatch hint on the Date and time page (M28 F2 L3) |
| `date-time-mode` | admin | The system / chosen-zone radio group on the Date and time page (M28 F2 L3) |
| `date-time-mode-system` | admin | The "Use the system time zone" radio (M28 F2 L3) |
| `date-time-mode-zone` | admin | The "Choose a time zone" radio (M28 F2 L3) |
| `date-time-preview-clock` | admin | What agents see: the app clock line (M28 F2 L3) |
| `date-time-preview-prompt` | admin | What agents see: the new-chat date line (M28 F2 L3) |
| `date-time-preview-tool` | admin | What agents see: the time tool's first line (M28 F2 L3) |
| `date-time-search` | admin | The zone chooser's search input (M28 F2 L3) |
| `date-time-status` | admin | The "Saved." status on the Date and time page: a persistent `role=status` region that holds one status only while there is something to say, so it takes no height when empty (M28 F2 L3; M31 F4 L09) |
| `date-time-prompt-muted` | admin | The "time tool is turned off" line under "A new chat starts with" on the Date and time page (M31 F4 L09; was the `.date-time-muted` class) |
| `date-time-use-browser` | admin | The "Use {browser zone}" button in the mismatch hint (M28 F2 L3) |
| `date-time-zone-row` | admin | A zone row or alias item in the chooser; `data-zone` is the name it saves (M28 F2 L3) |
| `save-connector-btn` | studio | Connector-editor header Save / Create, from `App.ui.editorShell` (`actions.save`); busy (disabled) while its request is in flight (M31 F3 L07a) |
| `save-knowledge-btn` | studio | Knowledge detail view header Save, disabled until dirty (`App.ui.editorShell` `save`; L6-D1, M24 F06 L06; replaces `kb-edit-save-btn`; M31 F3 L05a) |
| `time-tool-note` | studio | The agent Tools tab's note on the `current_time` tool row: always available, even with a limited tool list (M28 F1 L3) |
| `cancel-agent-btn` | studio | |
| `cancel-mcp-source-btn` | studio | |
| `cancel-provider-btn` | admin | |
| `cancel-tool-btn` | admin | |
| `chat-agent-line` | chat | The chat header's "with {agent}" line (12px, `--fg-muted`; "Default agent" for a null agent; blank while a cold `#chats/~new/{agent}` validates the agent) (M25 F4 L4b) |
| `chat-attach-btn` | chat | The composer's Attach images (`btn-ghost btn-sm btn-icon`, the paperclip icon, `aria-label="Attach images"`); opens the hidden `chat-image-input` (M25 F4 L5; a plus-icon `btn-outlined-primary` "Attach image" before) |
| `chat-attachment` | chat | one per staged-image chicklet (chat-attachments row) |
| `chat-attachment-remove` | chat | one per chicklet — removes just that image |
| `chat-consent-link-url` | chat | The sign-in link block's read-only URL field in a chat's login-required group, shown once the consent URL is known (`App.consentLink.build(url, {surface: 'chat'})`, `consent-link.js`; sortie 04 DD1) |
| `chat-consent-link-open` | chat | The block's "Open sign-in page" `<a target="_blank" rel="noopener noreferrer">` styled as a button (sortie 04 DD1) |
| `chat-consent-link-copy` | chat | The block's Copy button (clipboard, `execCommand` fallback; sortie 04 DD1) |
| `chat-attachments` | chat | chicklet row above the composer box, inside the composer wrapper (`.composer`; above the old `.input-area` row before M25 F4 L5) |
| `chat-attachments-status` | chat | visually-hidden aria-live="polite" status; announces a stage/remove delta, separate from the chicklet row (M18 F03 L01) |
| `chat-drawer` | chat | The agent drawer: the static shell slot `<aside id="chat-drawer" aria-label="This chat's agent">` after `<main>` in `index.html` (also set by `App.ui.drawer`'s test id option in `areas/chat/agent-drawer.js`), filled by the chat area and toggled with `hidden`: shown only on Chats with a chat open and its mode's state open; push (a 320px flex sibling, open by default) at 1280px and wider, overlay (closed by default) below; `data-mode` mirrors the mode (M25 F4 L6, DD7) |
| `chat-drawer-facts` | chat | The drawer's facts `<dl>`: Model (mono), Provider (the provider's display name), Chats (the `sessions` count, connector sessions included); Chats only for the default or a deleted agent (M25 F4 L6) |
| `chat-drawer-note` | chat | The drawer's state line for a non-agent view: "The default agent", "This agent no longer exists" or "Loading…" (M25 F4 L6) |
| `chat-drawer-notes` | chat | the drawer Notes group's `<ul>` of notes (M27 F2 L3) |
| `chat-drawer-notes-flag` | chat | the warning-triangle (`alert-triangle`, `role=img`) on an untrusted note in the drawer; its `title` and accessible name are "Check this note: it was written after content that didn't come from you ({sources}). It may have been planted." (M27 F3 L2; replaces `chat-drawer-notes-check`) |
| `chat-drawer-notes-pending` | chat | the drawer Notes group's `<ul>` of pending notes (the open chat's prompt does not carry them yet), muted, under the Pending subheading (M27 F3 L2) |
| `chat-drawer-notes-pending-head` | chat | the "Pending · used from the next chat" subheading above the pending list (M27 F3 L2) |
| `chat-drawer-notes-empty` | chat | the Notes group's "No notes yet" (M27 F2 L3) |
| `chat-drawer-notes-item` | chat | one note in the drawer (`<li>`, `data-id`, `data-number`, full text in `title`) (M27 F2 L3) |
| `chat-drawer-notes-kept` | chat | the Notes group's "{n} kept" line, shown only while notes are off and some are stored (M27 F2 L3) |
| `chat-drawer-notes-off` | chat | the Notes group's "Off" (M27 F2 L3) |
| `chat-drawer-rule` | chat | one enabled rule in the drawer's Rules group (`<li>`, full text in `title`, text clamped to two lines) (M27 F1 L2) |
| `chat-drawer-rules` | chat | the drawer Rules group's bulleted `<ul>` of enabled rules (M27 F1 L2) |
| `chat-drawer-rules-off` | chat | the Rules group's "{n} off" line, present only when some rules are disabled (M27 F1 L2) |
| `chat-drawer-settings-link` | chat | The drawer footer's **Open agent settings** (`App.ui.button` secondary, the `settings` gear): `go(#agents/{name})`, then `App.studio.clearAgentFilter()` on a commit; its footer is hidden for the default, a deleted or a loading agent (M25 F4 L6) |
| `chat-drawer-toggle` | chat | The chat header's drawer toggle at its end (`btn-ghost btn-icon`, the `panel-right` icon, `aria-label="Show this chat's agent"`, `aria-pressed` = open, `aria-controls="chat-drawer"`); hidden while idle (M25 F4 L6) |
| `chat-drawer-uses` | chat | The drawer's "What it can use" (A13): an `h3`, then `.chat-drawer-group[data-group=rules|knowledge|mcp|tools|self-configuration]` (Rules first, M27 F1 L2), each an `h4` over a list, "None", "Loading…" or "Couldn't load" (M25 F4 L6) |
| `chat-empty-new-btn` | chat | The empty state's New chat (`App.ui.button` primary, square-pen icon), inside `chat-welcome` when setup is complete and no chat is open; opens the agent picker. Absent in the setup-guidance state (M25 F4 L4b) |
| `chat-header` | chat | The chat header (`<header>`, 48px, hairline; reference spec 5.2): an `h1` with the chat's title (read from the `sessions` store by id, so it follows the auto-title) or "New chat", and `chat-agent-line`. Hidden while idle (M25 F4 L4b) |
| `chat-image-input` | chat | The composer's hidden `<input type=file accept=image/* multiple>`, named "Attach images" by `aria-label` since M25 F4 L5 (squawk 0110) |
| `chat-input` | chat | The composer's `<textarea rows=2>` (an `<input>` before M25 F4 L5), labelled by a visually hidden `<label for>` "Message" (no `aria-label`); placeholder "Message {agent}…"; Enter sends, Shift+Enter is a newline, an IME-composing Enter does nothing |
| `chat-model` | chat | The composer toolbar's model id: the open or pending chat's agent's `llm_model` from the `agents` store, 11px `--font-family-mono` in `--fg-muted`; empty when unknown (M25 F4 L5) |
| `chat-new-state` | chat | The new-chat state (reference spec 5.4), shown only while a chat is pending: a `badge badge--{providerType}` whose text is the model (A20), the agent name (`h2`), the description, and `chat-pick-different-btn` (M25 F4 L4b) |
| `chat-pick-different-btn` | chat | The new-chat state's "Pick a different agent" (`btn-ghost btn-sm`); opens the agent picker, and a pick replaces the pending chat (M25 F4 L4b) |
| `chat-row` | chat | A Chats list row: an `App.ui.listPane` `<a href="#chats/{id}">` with `data-id` (rowStyle `chats`: title, time, agent, a connector's platform badge), or the pending chat's row (`data-pending="true"`, no `data-id`, href `#chats/~new/{agent}`) (M25 F4 L4a) |
| `chat-row-delete` | chat | A Chats list row's delete action ("Delete chat: {title}"; arm, then confirm through `App.confirmDelete`); never on the pending row (M25 F4 L4a) |
| `chat-send-btn` | chat | The composer's Send (`btn-filled-primary`, the send icon and label, `aria-keyshortcuts="Enter"`), at the toolbar's end |
| `chat-stop-btn` | chat | The composer's Stop (`btn-muted-destructive`), hidden unless the open chat has a turn in flight; just before Send when shown |
| `chat-welcome` | chat | The pane's empty and setup-guidance state (idle with no chat to auto-join): the mascot, the "Hello." `h1`, the idle notice, then the prompt and `chat-empty-new-btn` (setup complete) or the guidance links (setup incomplete). Since M25 F4 L4b it no longer holds an agent list |
| `chat-welcome-mascot` | chat | |
| `chats-list` | chat | Chats list column root, the `App.ui.listPane` `<section>` in the aside (title "Chats", 300px; M25 F4 L4a) |
| `chats-new-btn` | chat | The Chats list's full-width New chat button (the pane's header block); opens the agent picker; natively disabled while setup is incomplete (M25 F4 L4a) |
| `confirm-dialog-overlay` | shell | |
| `connector-card` | studio | Library list connector row (an `<a href="#library/connectors/{id}">`, M25 F3 L4a; was the Connectors grid tile, M23 F02 L02) |
| `connector-channel-map-add-btn` | studio | Connector-editor channel→agent map "+ Add row" (`App.ui.keyValueTable` `addTestid`) (M23 F02 L02; M31 F3 L07b) |
| `connector-channel-map-agent` | studio | Connector-editor channel→agent map, a row's agent input (`inputTestid`) (M31 F3 L07b) |
| `connector-channel-map-channel` | studio | Connector-editor channel→agent map, a row's channel-id input (`inputTestid`) (M31 F3 L07b) |
| `connector-channel-map-remove-btn` | studio | Connector-editor channel→agent map per-row remove, an icon button named "Remove row {n}" (`removeTestid`) (M23 F02 L02; M31 F3 L07b) |
| `connector-channel-map-row` | studio | Connector-editor channel→agent map, one row (M23 F02 L02) |
| `connector-delete-error` | studio | Connector-editor Danger Zone failed-DELETE notice (`App.ui.dangerZone` `notice`, role=alert) (M31 F3 L07b) |
| `connector-doctor-result` | studio | Connector-editor doctor probe result, an `App.ui.status` line (hidden until a run; danger with the response's error text on a non-OK response) (M23 F02 L02; M31 F3 L07a) |
| `connector-pairing-btn` | studio | Connector-editor "Generate pairing code" (`App.ui.button`) (M23 F02 L02; M31 F3 L07b) |
| `connector-pairing-code` | studio | Connector-editor pairing-code result — the code itself, a read-only input named "Pairing code" (`App.ui.copyField`) (Squawk 0043; M31 F3 L07b) |
| `connector-pairing-copy-btn` | studio | Connector-editor pairing-code copy button, named "Copy pairing code" (`copyField` `copyTestid`) (Squawk 0043; M31 F3 L07b) |
| `connector-pairing-result` | studio | Connector-editor pairing result region: a status line (Generating…/failure), then the copy field and the expiry line (M23 F02 L02; M31 F3 L07b) |
| `connector-setup-steps` | studio | Connector-editor inline setup-steps section container, both create and edit (Squawk 0046) |
| `connector-setup-steps-doc-ref` | studio | Connector-editor inline setup-steps plain-text reference naming `docs/connector-setup.md` — not a link; only `/static` is mounted, so an anchor would 404 (renamed from `connector-setup-steps-link` in the squawk 0046 review fix) (Squawk 0046) |
| `connector-status-label` | studio | Connector-editor header connection-status line: the root `p.ui-status` of an `App.ui.status` (its `data-state` carries the outcome; "Connection check failed" when the automatic probe gets a non-OK response), edit mode only (Squawk 0045; M31 F3 L07a) |
| `connector-status-led` | studio | The `status`-owned LED span inside the header status line (decorative, `aria-hidden`; its class carries the state), edit mode only (Squawk 0045; M31 F3 L07a) |
| `delete-agent-btn` | studio | |
| `delete-blocked-message` | admin | |
| `delete-connector-btn` | studio | Connector-editor Danger Zone (M23 F02 L02) |
| `delete-knowledge-base-btn` | studio | Knowledge detail view Danger Zone (M24 F06 L01) |
| `kb-delete-error` | studio | Knowledge detail view Danger Zone notice, role=alert, shows why a Delete failed (M31 F3 L05b) |
| `delete-mcp-source-btn` | studio | The MCP editor's Danger zone Delete (`App.ui.dangerZone`, label "Delete MCP server", armed "Confirm delete?", `data-name`); a failed Delete shows in the header's editor error (`role=alert`), reverts the button and returns focus to it (M31 F5 L10, row 29) |
| `delete-provider-btn` | admin | |
| `editor-breadcrumb-link` | studio, admin | Item header breadcrumb's link to its root: "Agents" -> `#agents` (agent editor); on a Library editor (knowledge-base detail and `~new` form, MCP server, connector) the header reads `Library / {Group}` and "Library" is the link, to `#library` (the group is plain text; model providers: `Library / Model providers`, sortie 02, DD3); studio routes a plain activation through the router (guarded) and focuses the closed item's row (M25 F3 DD2 refinement, L4b). Settings: "Settings / Built-in tools" -> `#settings/tools` (tool editor; admin routes it the same way, focus: the closed tool's name link). Settings has no provider editor since sortie 02 leg 2 |
| `editor-unsaved` | studio, admin | Item header "Unsaved changes" caption, a stable `role=status` span at the start of `.form-actions` whose text the editor's dirty report sets or clears: the agent editor (`checkDirty`, M25 F3 DD2, L3), the knowledge-base detail and `~new` form, the MCP and connector editors (L4b), the provider and tool editors (L5b; the tool editor's Cancel re-mount keeps the same span node) |
| `jump-to` | shell | The jump-to palette `<dialog>` (`js/jump-to.js`, `App.jumpTo`): an `App.ui.modal` chooser named by `ariaLabel` "Jump to" (no title, no header row), 600 wide at top 96, dismissible, built fresh on every open from Ctrl K (Meta K on macOS) or the rail's `rail-jump-to` (M25 F4 L7, DD9, DD10) |
| `jump-to-close` | shell | The palette's "Esc" button at the end of its input bar (accessible name "Close (Esc)"; built by the palette in its body, it calls the modal's `close()`; focus returns to the opener) (M25 F4 L7) |
| `jump-to-input` | shell | The palette's search input (visually hidden label "Jump to", placeholder "Jump to an agent, chat, library item or setting"; the `searchList` `inputTestid`, focused on open) (M25 F4 L7) |
| `jump-to-result` | shell | One palette result (`role=option`, `data-kind` = `agent`, `chat`, `action`, `provider`, `knowledge-base`, `mcp-server`, `connector` or `settings`, `data-id` = the agent name, session id, `new-chat`, item id or Settings route section; the `searchList` `rowTestid`); at most 8 (M25 F4 L7) |
| `kb-chunk-count` | studio | Knowledge detail view status summary — chunk count (M24 F06 L01) |
| `kb-chunk-list` | studio | Knowledge detail view chunks panel — the one box around the chunk rows (surface, border, `--radius-sm`, `--space-3` padding, max-height 400px with scroll), the same box as `kb-source-text`; the loading, error and empty lines sit outside it (M31 F3 HAT) |
| `kb-chunk-row` | studio | Knowledge detail view chunks panel — one row per chunk, `seq` order (DD-8, M24 F06 L01) |
| `kb-chunks-panel` | studio | Knowledge detail view — an item's chunks, opened on demand (DD-8, M24 F06 L01) |
| `kb-create-description-input` | studio | Knowledge-base create form description field (AC-4, M24 F06 L05; the form moved to `#library/knowledge/~new` in M25 F3 L4a) |
| `kb-create-error` | studio | Knowledge-base create form submission error line: the server's or the network's message only (M24 F06 L01; M25 F3 L4a; the empty-name error moved to `kb-create-name-error` in M31 F3) |
| `kb-create-name-error` | studio | Knowledge-base create form Name field error ("Name is required.", an `App.ui.field` error: the input gets `aria-invalid` and is focused; cleared on edit and on the next submit) (M31 F3 HAT) |
| `kb-create-name-hint` | studio | Knowledge-base create form advisory name-length hint, shown over 43 code points (DD-16, M24 F06 L01; M25 F3 L4a) |
| `kb-create-name-input` | studio | Knowledge-base create form name field (M24 F06 L01; M25 F3 L4a) |
| `kb-description-input` | studio | Knowledge detail view always-live description field, header region (L6-D1, M24 F06 L06) |
| `kb-folder-add-error` | studio | Knowledge detail view Folders section "Add folder" submission error, renders the route's `detail` message (DD-10, M24 F06 L01; renamed from `kb-folder-register-error` in M24 F06 L06) |
| `kb-folder-delete-btn` | studio | Knowledge detail view folder panel — library ghost icon button in the disclosure's `actions` (outside the summary's accessible name), trash-icon delete behind the canonical two-step `App.ui.confirm` (armed on the `<summary>`, the disclosure text as `[data-confirm-title]`; M31 F3 L06a). Takes only its VISUAL form from the Custom Headers row; that row's bare click does not carry, because this one is an irreversible server-side cascading DELETE (amended L6-D3, M24 F06 L06; replaces the labelled two-step `kb-folder-remove-btn`) |
| `kb-folder-panel` | studio | Knowledge detail view Folders section — one native `<details>` panel per registered folder, carrying path/status/watch in its summary and that folder's files in its body (L6-D2, M24 F06 L06; renamed from `kb-folder-row`) |
| `kb-folder-path-input` | studio | Knowledge detail view Folders section "Add folder" path field (M24 F06 L01) |
| `kb-folder-status` | studio | Knowledge detail view folder panel summary — the "status: X" chip (M31 F3 L06a) |
| `kb-folder-summary` | studio | Knowledge detail view folder panel — the `<summary>` element (the disclosure's `summaryTestid`); the armed two-step confirm's `.confirm-delete`/`.confirm-lapsed` state lives here (M31 F3 L06a) |
| `kb-folder-watch` | studio | Knowledge detail view folder panel summary — the "watch: X" chip (M31 F3 L06a) |
| `kb-folders-cascade-hint` | studio | Knowledge detail view Folders section — persistent helper text naming the removal's cascade, section-level rather than per-row (L6-D3, M24 F06 L06; replaces the per-row `kb-folder-remove-caption`) |
| `kb-folders-list` | studio | Knowledge detail view Folders section — folder-panel + "Individual files" panel container (M24 F06 L01; moved out of Status in M24 F06 L06; "Other items" renamed at the M31 F3 HAT) |
| `kb-individual-files-hint` | studio | Knowledge detail view "Individual files" panel — the description, the body's first child: "Added one at a time through the API. These files aren’t watched for changes; use Re-index all files to pick up edits." (M31 F3 HAT) |
| `kb-individual-files-panel` | studio | Knowledge detail view Folders section — trailing bordered `App.ui.disclosure` for file items with no `parent_id`, summary "Individual files ({n})", no summary chips; an item whose `parent_id` names a folder the client does not know is held out of every panel (M31 F3 HAT; replaces `kb-other-items-panel`) |
| `kb-indexer-state` | studio | Knowledge detail view status summary — indexer state word (M24 F06 L01) |
| `kb-item-error` | studio | Knowledge detail view item row — a `failed` item's error text (M24 F06 L01) |
| `kb-item-full-path` | studio | Knowledge detail view "Individual files" row — the item's full path on one small ellipsised line under the basename, the path as `title` (M31 F3 HAT) |
| `kb-item-indexed-at` | studio | Knowledge detail view item row — the item's content-freshness signal, rendered from `indexed_at` (only when the item has ever indexed — never a fabricated timestamp) as "Indexed {date}, {time}" for an indexed item, "Last indexed {date}, {time}" for a pending, indexing or failed one (M31 F3 HAT); the precise value is `data-indexed-at` and leads the hover title, with `content_hash`, when present, after it (DD-6, Flight 7 Leg 2; date and time since the M31 F3 HAT) |
| `kb-folder-indexed-at` | studio | Knowledge detail view folder panel body — "Last checked {date}, {time}" from the folder's own `indexed_at` (every completed walk), the precise value in `title` and `data-indexed-at` (M31 F3 HAT) |
| `kb-item-menu` | studio | Knowledge detail view item row — the overflow menu (`role="menu"`, an `App.ui.menu` popup since M31 F3 L06b), carries "View chunks"/"View source" (L5-D4, M24 F06 L05) |
| `kb-item-menu-btn` | studio | Knowledge detail view item row — the overflow menu's trigger (`aria-haspopup="menu"`) (L5-D4, M24 F06 L05) |
| `kb-item-remove-btn` | studio | Knowledge detail view "Individual files" row — ghost icon-only trash button ("Remove file {path} (press twice to confirm)", title "Remove file"), `App.ui.confirm` armed on the button itself ("Confirm remove?"), one DELETE of the item; only on parentless rows, never on walked files (M31 F3 HAT) |
| `kb-item-row` | studio | Knowledge detail view — one row per file item, nested inside a folder panel or the "Individual files" panel (M24 F06 L01) |
| `kb-item-standalone-badge` | studio | Knowledge detail view item row — warning chip "Also in folder {folder basename}", the full folder path as `title`, for an individual file whose path lies inside a registered folder; only rendered inside the "Individual files" panel (DD-9, M24 F06 L01; text since the M31 F3 HAT) |
| `kb-item-status` | studio | Knowledge detail view item row — the item's `status` word; absent when the item is indexed and has an `indexed_at` (the stamp says "Indexed …") (M24 F06 L01; rule since the M31 F3 HAT) |
| `kb-name-hint` | studio | Knowledge detail view always-live name field's advisory hint, shown over 43 code points, reuses the create form's DD-16 hint text (L6-D1, M24 F06 L06; renamed from `kb-edit-name-hint`) |
| `kb-name-input` | studio | Knowledge detail view always-live name field, header region — no edit-button toggle (L6-D1, M24 F06 L06; renamed from `kb-edit-name-input`) |
| `kb-panel-close-btn` | studio | Knowledge detail view chunks/source panel — ghost icon-only x ("Close chunks"/"Close source", title "Close"): hides the panel, drops a late response, and returns focus to the opener (else the summary of the panel holding the item, else the Add-folder input); Escape does not close (M31 F3 HAT) |
| `kb-panel-file-name` | studio | Knowledge detail view chunks/source panel — the open file's basename under the heading; part of the heading's accessible name ("Chunks runbook-01.md") (M31 F3 HAT) |
| `kb-panel-file-path` | studio | Knowledge detail view chunks/source panel — the open file's full path on one ellipsised line, the path as `title` (M31 F3 HAT) |
| `kb-panel-title` | studio | Knowledge detail view chunks/source panel — the panel's one stable `h3` heading (`tabindex=-1`, built once; focus lands on it when a panel opens), the static text "Chunks"/"Source", named by itself plus `kb-panel-file-name` (kb-studio-round-trip remediation FIX 4, M24 F06; an `h3` since M31 F3 L06b; static since the M31 F3 HAT, the file is named by `kb-panel-file-name`/`kb-panel-file-path`) |
| `kb-reindex-all-btn` | studio | Knowledge detail view Status section re-index control (`scope=all`) (M24 F06 L01; label "Re-index all files"; an `App.ui.button` since M31 F3 L05b) |
| `kb-reindex-changed-btn` | studio | Knowledge detail view Status section re-index control (`scope=changed`) (M24 F06 L01; an `App.ui.button` since M31 F3 L05b) |
| `kb-reindex-scope-hint` | studio | Knowledge detail view Status section — helper text stating that re-indexing covers every registered folder (there is no per-folder re-index) and what each scope does (M24 F06 L06 HAT polish pass) |
| `kb-search-btn` | studio | Knowledge detail view search submit (M24 F06 L01; an `App.ui.button` since M31 F3 L05b) |
| `kb-search-clear-btn` | studio | Knowledge detail view search field's x button, empties the query, results and degraded line (squawk 0100, M31 F3 L05b) |
| `kb-search-degraded` | studio | Knowledge detail view search degrade line, shown alongside the response's own `indexer` word (AC-12, M24 F06 L01) |
| `kb-search-announcer` | studio | Knowledge detail view search: visually hidden polite status announcing the result count ("N results", "1 result", "No results."); empty on clear (WCAG 4.1.3, M31 F3 review fix) |
| `kb-search-hit` | studio | Knowledge detail view — one search result row (an `li` since the M31 F3 HAT): the file name, a meta line with the full path and "score 0.016", and the snippet (M24 F06 L01) |
| `kb-search-input` | studio | Knowledge detail view search query field (DD-6, M24 F06 L01) |
| `kb-search-results` | studio | Knowledge detail view search results container (M24 F06 L01) |
| `kb-source-panel` | studio | Knowledge detail view — an item's source text, opened on demand (DD-8, M24 F06 L01) |
| `kb-source-text` | studio | Knowledge detail view — the fetched source text itself (M24 F06 L01) |
| `kb-status-count` | studio | Knowledge detail view status summary — one per-status file count chip (M24 F06 L01) |
| `kb-status-summary` | studio | Knowledge detail view status summary container (M24 F06 L01) |
| `knowledge-base-card` | studio | Library list knowledge-base row (an `<a href="#library/knowledge/{id}">`, M25 F3 L4a; was the Knowledge grid tile, M24 F06 L01) |
| `knowledge-chunking-note` | admin | Knowledge settings panel — states chunking applies to future indexing only (L4-D2, M24 F06 L04) |
| `knowledge-embedding-backend` | admin | Knowledge settings panel — read-only embedding backend value (DD-7, M24 F06 L04) |
| `knowledge-embedding-dim` | admin | Knowledge settings panel — read-only embedding dimensions value (DD-7, M24 F06 L04) |
| `knowledge-embedding-model` | admin | Knowledge settings panel — read-only embedding model id value (DD-7, M24 F06 L04) |
| `knowledge-embedding-readonly-reason` | admin | Knowledge settings panel — states why embedding is read-only, not a disabled input (L4-D1, M24 F06 L04) |
| `knowledge-monitoring-note` | admin | Knowledge settings panel — states monitoring changes apply live (L4-D2, M24 F06 L04) |
| `knowledge-overlap-chars-error` | admin | Knowledge settings panel — `overlap_chars` inline validation message, cross-field re-evaluated on `size_chars` change (L4-D3, M24 F06 L04) |
| `knowledge-overlap-chars-input` | admin | Knowledge settings panel — `chunking.overlap_chars` field (M24 F06 L04) |
| `knowledge-overlap-hint` | admin | Knowledge settings panel — static hint under the overlap field (M24 F06 L04) |
| `knowledge-reconcile-interval-error` | admin | Knowledge settings panel — `reconcile_interval_seconds` inline validation message (L4-D3, M24 F06 L04) |
| `knowledge-reconcile-interval-input` | admin | Knowledge settings panel — `monitoring.reconcile_interval_seconds` field (M24 F06 L04) |
| `knowledge-settings-cancel-btn` | admin | Knowledge settings panel — Cancel in the page header; patches the fields back to the baseline (M31 F4 L10) |
| `knowledge-settings-intro` | admin | Knowledge settings panel — the intro line under the page title (B15, M31 F4 L10) |
| `knowledge-settings-error` | admin | Knowledge settings panel — the shell's error span after a save failure with no field of its own (M31 F4 L10) |
| `knowledge-reconcile-interval-echo` | admin | Knowledge settings panel — the interval echoed in words beside the field, empty when invalid (A22, M31 F4 L10) |
| `knowledge-settings-chunking-section` | admin | Knowledge settings panel — Chunking section container (M24 F06 L04) |
| `knowledge-settings-embedding-section` | admin | Knowledge settings panel — Embedding (read-only) section container (M24 F06 L04) |
| `knowledge-settings-flash` | admin | Knowledge settings panel — region holding the "Saved." `App.ui.status` (inserted on success, cleared by the next attempt or after 3 s; M31 F4 L10) |
| `knowledge-settings-load-error` | admin | Knowledge settings panel — `GET /api/knowledge-settings` failure text, set on the shell's error span (`errorRole: 'alert'`); the fields are disabled and Save never enables (M24 F06 L04, M31 F4 L10) |
| `knowledge-settings-monitoring-section` | admin | Knowledge settings panel — Monitoring section container (M24 F06 L04) |
| `knowledge-settings-panel` | admin | Knowledge settings panel — the `.admin-form` body under the page header, holding the sections (M24 F06 L04) |
| `knowledge-settings-save-btn` | admin | Knowledge settings panel — the one explicit Save for chunking + monitoring together (L4-D4, M24 F06 L04) |
| `knowledge-settings-vector-store-section` | admin | Knowledge settings panel — Vector Store (read-only) section container (M24 F06 L04) |
| `knowledge-size-chars-error` | admin | Knowledge settings panel — `size_chars` inline validation message (L4-D3, M24 F06 L04) |
| `knowledge-size-chars-input` | admin | Knowledge settings panel — `chunking.size_chars` field (M24 F06 L04) |
| `knowledge-vector-store-backend` | admin | Knowledge settings panel — read-only vector-store backend value (DD-7, M24 F06 L04) |
| `knowledge-vector-store-dtype` | admin | Knowledge settings panel — read-only vector-store dtype value (DD-7, M24 F06 L04) |
| `knowledge-vector-store-readonly-reason` | admin | Knowledge settings panel — states why vector store is read-only, not a disabled input (L4-D1, M24 F06 L04) |
| `knowledge-watch-enabled-toggle` | admin | Knowledge settings panel — `monitoring.watch_enabled` toggle (M24 F06 L04) |
| `kv-add-row-btn` | studio | The MCP environment variables / headers table's Add row button (`addTestid`, M31 F5 L07) |
| `library-add-btn` | studio | Library list title-row "Add" (`App.ui.menu` trigger, small outlined, plus icon; the menu opens with `align: 'end'`) (M25 F3 L4a, DD5) |
| `library-add-connector` | studio | Library Add menu item "Connector" -> `#library/connectors/~new` (M25 F3 L4a) |
| `library-add-provider` | studio | Library Add menu item "Model provider" (the first item) -> `#library/providers/~new` (sortie 02, DD6) |
| `library-add-knowledge` | studio | Library Add menu item "Knowledge base" -> `#library/knowledge/~new` (M25 F3 L4a) |
| `library-add-mcp` | studio | Library Add menu item "MCP server" -> `#library/mcp/~new` (M25 F3 L4a) |
| `library-start` | studio | The Library start page (`#library`, the one Library root: a card per group, each with a `library-start-{group}-add` button) (model-providers sortie, DD6; it replaced `library-empty-{group}`) |
| `library-list` | studio | Library list column root, the grouped `App.ui.listPane` `<section>` in the aside (M25 F3 L4a, DD5) |
| `mcp-consent-link-url` | studio | The sign-in link block's read-only URL field in the MCP editor's status panel (`App.consentLink.build(url, {surface: 'mcp'})`; sortie 04 DD1) |
| `mcp-consent-link-open` | studio | The block's "Open sign-in page" anchor (`target="_blank"`; sortie 04 DD1) |
| `mcp-consent-link-copy` | studio | The block's Copy button (sortie 04 DD1) |
| `mcp-command-custom` | studio | |
| `mcp-command-hint` | studio | |
| `mcp-command-runtime` | studio | |
| `mcp-connection-error` | studio | The Test error block (plain headline, raw text under Technical details) in the result area; its headline follows the transport (M31 F5 L08b, A18) |
| `mcp-connection-led` | studio | The status line's LED, decorative (`aria-hidden`); the line's words carry the state (M31 F5 L08b) |
| `mcp-connection-status` | studio | The Connection section's status line (`App.ui.status`; `data-state` is the LED state, `data-mcp-state` is `App.usage.mcpState`'s state), with the words from `App.usage.mcpStateLabel`: "Connected · checked 3:42 PM", "Not connected", "Couldn't connect" (plus " · last connected …"), "Sign-in needed" (M31 F5 L08b, A6, A9) |
| `mcp-consent-btn` | studio | The "Sign in" button in the Test result area (the auto-run after create, and the retry after a failed sign-in) |
| `forget-mcp-connection-btn` | studio | "Forget tools list" (armed "Forget tools list?"), beside the status line, for a cached streamable-HTTP server without a sign-in; disabled during a consent session (M31 F5 L08b, A7, DD6) |
| `mcp-error-raw` | studio | |
| `mcp-empty-state` | studio | |
| `mcp-env-headers-section` | studio | The "Environment variables" / "Headers" `App.ui.section`; hidden while a create form has no type (M31 F5 L06, L07) |
| `mcp-kv-table` | studio | The environment variables / headers `App.ui.keyValueTable` (`<table>`, named like its section); its thead hides while it has no rows (M31 F5 L07) |
| `mcp-sandbox-section` | studio | |
| `mcp-server-facts` | studio | The Server section's `App.ui.facts` (Version, Protocol, Offers, Website; only rows with a value) (M31 F5 L09, A16) |
| `mcp-server-header` | studio | The Server section's identity row (icon, title, name); hidden when there is neither a title nor an icon (M31 F5 L09) |
| `mcp-server-icon` | studio | The server's icon `<img>` (decorative, `alt=""`); absent when the URL fails `App.safeUrl` (squawk 0010) (M31 F5 L09) |
| `mcp-server-info-section` | studio | The "Server" `App.ui.section`; always mounted in edit mode, hidden while the cache has nothing to show (M31 F5 L09) |
| `mcp-server-instructions` | studio | The Instructions plain `App.ui.disclosure` (hidden without instructions) (M31 F5 L09, A15) |
| `mcp-server-instructions-text` | studio | The instructions body, text only, line breaks kept (M31 F5 L09) |
| `mcp-server-meta` | studio | The Metadata plain disclosure (hidden without `_meta`) (M31 F5 L09) |
| `mcp-server-meta-content` | studio | The Metadata JSON `App.ui.codeBlock` (M31 F5 L09) |
| `mcp-server-offers` | studio | The "Offers" facts row: the announced capabilities capitalised, or "Nothing announced" (M31 F5 L09, A16) |
| `mcp-server-protocol` | studio | The "Protocol" facts row (monospace), kept per B10 (M31 F5 L09) |
| `mcp-server-subtitle` | studio | The server's name under its title, only when it differs (M31 F5 L09) |
| `mcp-server-title` | studio | The server's title (or name) (M31 F5 L09) |
| `mcp-server-version` | studio | The "Version" facts row (M31 F5 L09) |
| `mcp-server-website` | studio | The "Website" facts row: a link (`target=_blank`, `rel="noopener noreferrer"`) through `App.safeUrl`, inert text when rejected (squawk 0010) (M31 F5 L09) |
| `mcp-source-card` | studio | Library list MCP-server row (an `<a href="#library/mcp/{id}">`, M25 F3 L4a; was the MCP Servers grid tile) |
| `mcp-sources-list` | studio | |
| `mcp-editor-subtitle` | studio | The MCP editor header's subtitle (`editorShell` `subtitleTestid`): "{type label} · {command or URL}", the type label alone without a detail, the raw type for a legacy row; absent on the create form; follows an edit Save (M31 F5 L10, A4, defect 12) |
| `mcp-test-connection` | studio | The header's Test button (`editorShell` `actions.test`, M31 F5 L10), built only for an edit-mode stdio or streamable-HTTP mount; its state has one writer, `syncTestHold`; reads "Waiting for sign-in…" and is disabled while a consent session runs (M31 F5 L08b, B2) |
| `mcp-test-status` | studio | The Test result area directly after the status line, in the Connection section; empty and hidden at rest and after a success (M31 F5 L08b, A8) |
| `mcp-test-live` | studio | The editor's one persistent polite live region (visually hidden, created at mount, after the result area); its text is set to announce "Testing connection…" and the sign-in prompt (M31 F5 B4, WCAG 4.1.3) |
| `mcp-tool-description` | studio | A tool's full description in its body; shown only when it is longer than the summary's cut (or has line breaks, or is empty: "No description provided.") (M31 F5 L09, A15) |
| `mcp-tool-item` | studio | One tool's bordered `App.ui.disclosure` in the Tools list (on the `<details>`) (M31 F5 L09, A15) |
| `mcp-tool-schema` | studio | A tool's input schema `App.ui.codeBlock`; absent for an empty schema (the body says "No input schema.") (M31 F5 L09) |
| `mcp-tools-empty` | studio | "Press Test to load this server's tools." while no tools are loaded (M31 F5 L09) |
| `mcp-tools-list` | studio | The tool disclosures, reconciled by name in place; hidden until tools are loaded (M31 F5 L09) |
| `mcp-tools-section` | studio | The "Tools" `App.ui.section` (M31 F5 L09) |
| `message` | chat | |
| `modal-cancel-btn` | shell | |
| `modal-confirm-btn` | shell | |
| `model-capabilities` | studio | |
| `model-ctx-chip` | studio | |
| `new-agent-btn` | studio | Unified create CTA (M17 F3 L3); since M25 F3 L3 the Agents list's title-row "New" (`App.ui.button`, small outlined, plus icon) -> `#agents/~new` |
| `notes-applies-note` | studio | the Notes section's "Changes apply…" line (M27 F2 L3) |
| `notes-clear-all` | studio | Notes **Clear all** (opens the confirm dialog; hidden when there are no notes) (M27 F2 L3) |
| `notes-create-mode` | studio | create-mode notice "Save the agent first to let it keep notes." (M27 F2 L3) |
| `notes-empty` | studio | the Notes list's "No notes yet." (M27 F2 L3) |
| `notes-enabled-toggle` | studio | the "Let this agent keep notes" `App.ui.toggle` input (`role=switch`); saves immediately (M27 F2 L3) |
| `notes-error` | studio | the Notes section's inline error area (`role=alert`, hidden when empty) (M27 F2 L3) |
| `notes-list` | studio | the notes list (`<ul>`) (M27 F2 L3) |
| `notes-off-message` | studio | "Notes are off. This agent can't see or write notes. Saved notes are kept." (hidden while on) (M27 F2 L3) |
| `notes-row` | studio | one note row (`<li>`, `data-id`, `data-number`) (M27 F2 L3) |
| `notes-row-cancel` | studio | note inline edit Cancel (M27 F2 L3) |
| `notes-row-delete` | studio | note Delete, two-step through `App.confirmDelete` (M27 F2 L3) |
| `notes-row-edit` | studio | note Edit; `data-note-id` (M27 F2 L3) |
| `notes-row-edit-count` | studio | the inline edit's live "{n} / 400" count (M27 F2 L3) |
| `notes-row-edit-input` | studio | the note inline edit textarea (M27 F2 L3) |
| `notes-row-edited` | studio | "Edited by you" on an operator-edited note (M27 F2 L3) |
| `notes-row-flag` | studio | the warning-triangle (`App.ui.noteFlag`, `role=img`) on an untrusted note in the Rules and notes tab; `title` and accessible name are "Check this note: it was written after content that didn't come from you ({sources}). It may have been planted." (M27 F3 L2; replaces `notes-row-check`) |
| `notes-row-meta` | studio | a note's meta line (time, origin, badges) (M27 F2 L3) |
| `notes-row-origin` | studio | the note's origin: chat link, "(chat deleted)", platform and peer, or "Outside a chat" (M27 F2 L3) |
| `notes-row-origin-link` | studio | the origin `<a>` to `#chats/{id}` when the chat still exists (M27 F2 L3) |
| `notes-row-platform` | studio | a connector origin's platform badge (M27 F2 L3) |
| `notes-row-save` | studio | note inline edit Save (M27 F2 L3) |
| `notes-row-text` | studio | the note's text paragraph (M27 F2 L3) |
| `notes-row-time` | studio | the note's time ("Updated …" when edited) (M27 F2 L3) |
| `notes-section` | studio | the Notes section of the Rules and notes tab (M27 F2 L3) |
| `notes-status` | studio | the Notes section's visually hidden polite status line (the limit; the delete arm moved to `ui-confirm-live`) (M27 F2 L3, M31 F2 L5) |
| `notes-usage` | studio | the "{used} of {total} characters" line (M27 F2 L3) |
| `pending-count` | studio | Self-configuration tab per-agent pending-revision count (M21 F02 L02) |
| `pending-queue` | studio | Self-configuration tab pending-revision queue container (M21 F02 L02) |
| `pending-queue-empty` | studio | Self-configuration tab empty-queue notice (M21 F02 L02) |
| `pending-queued` | chat | |
| `pending-queued-cancel` | chat | |
| `pending-queued-region` | chat | |
| `plan-code-input` | admin | anthropic-plan sign-in: consent-code paste field (no `data-field` — deliberately outside the dirty snapshot) |
| `plan-code-submit-btn` | admin | anthropic-plan sign-in: submit pasted code → POST /oauth/code |
| `plan-connected-indicator` | admin | anthropic-plan sign-in: connected-state status line (`App.ui.status`) |
| `plan-reauth-btn` | admin | anthropic-plan sign-in: standing re-auth affordance (connected state) |
| `plan-reset-btn` | admin | anthropic-plan sign-in: reset connection (two-step confirm) → DELETE /oauth |
| `plan-signin-btn` | admin | anthropic-plan sign-in: sign-in affordance (create mode auto-saves the provider first, then starts the OAuth flow) |
| `plan-signin-consent` | admin | anthropic-plan sign-in: consent block wrapper (URL + code paste) |
| `plan-signin-copy-btn` | admin | anthropic-plan sign-in: copy authorize URL |
| `plan-signin-error` | admin | anthropic-plan sign-in: inline error area |
| `plan-signin-open-btn` | admin | anthropic-plan sign-in: the "Open sign-in page" link (`<a target="_blank">`, from `App.ui.consentLink`) |
| `plan-signin-url` | admin | anthropic-plan sign-in: copyable authorize URL (readonly input) |
| `plan-test-reauth` | admin | provider /test result: distinct reauth_required message span |
| `provider-card` | studio | A Library list row in the first group, "Model providers" (`<a href="#library/providers/{id}">` with the name, a type badge and "{n} agents" meta; the list pane marks the open one selected). Sortie 02: the Settings tile's name link (an `admin` row) retired with the Providers page |
| `purge-history-btn` | studio | |
| `rail-jump-to` | shell | The rail footer's **Jump to** control (`App.ui.button` ghost icon-only, the `search` icon, 44px, `aria-label="Jump to (Ctrl K)"` with `aria-keyshortcuts="Control+K"`, or "Jump to (⌘ K)" / `Meta+K` on macOS), set by `js/app.js` through `App.ui.rail`'s `footer`; a click opens the palette (`jump-to`) with it as the opener (M25 F4 L7, DD9). A literal beside the `rail-` destination family |
| `reset-mcp-connection-btn` | studio | "Reset connection" (armed "Reset connection?"), beside the status line, only for a signed-in server (`oauth_active`); patches in place, disabled during a consent session (M31 F5 L08b, A7) |
| `revision-approve-btn` | studio | Self-configuration pending-revision card approve (M21 F02 L02) |
| `revision-base` | studio | Self-configuration pending-revision card current/base value (M21 F02 L02) |
| `revision-card` | studio | Self-configuration pending-revision card (M21 F02 L02) |
| `revision-current` | studio | Self-configuration staleness panel current value (M21 F02 L02) |
| `revision-dismiss-btn` | studio | Self-configuration pending-revision card dismiss (M21 F02 L02) |
| `revision-error` | studio | Self-configuration pending-revision card action error (M21 F02 L02) |
| `revision-field` | studio | Self-configuration pending-revision card field label (M21 F02 L02) |
| `revision-history` | studio | Self-configuration revision-history timeline container (M21 F02 L03); lives inside the collapsible `revision-history-details` as of the HAT UX pass (M21 F02 L04) |
| `revision-history-details` | studio | Self-configuration chronological-log `App.ui.disclosure` (plain) `<details>` wrapper (M21 F02 L04 HAT — collapses the full log; the restore-node list stays outside it, always visible) |
| `revision-history-empty` | studio | Self-configuration revision-history empty notice (M21 F02 L03) |
| `revision-history-entry` | studio | Self-configuration revision-history entry (M21 F02 L03) |
| `revision-history-summary` | studio | Self-configuration chronological-log `<summary>`, text "History (N)" (M21 F02 L04 HAT) |
| `revision-override-btn` | studio | Self-configuration staleness override/confirm (M21 F02 L02) |
| `revision-proposed` | studio | Self-configuration pending-revision card proposed value (M21 F02 L02) |
| `revision-restore-btn` | studio | Self-configuration revision-history restore control (M21 F02 L03) |
| `revision-restore-controls` | studio | Self-configuration revision-history restore-controls group (M21 F02 L03) |
| `revision-restore-empty` | studio | Self-configuration revision-history no-earlier-values notice (M21 F02 L03) |
| `revision-restore-error` | studio | Self-configuration revision-history restore action error (M21 F02 L03) |
| `revision-restore-node` | studio | Self-configuration revision-history distinct value-node row (M21 F02 L03) |
| `revision-stale` | studio | Self-configuration staleness (409) panel (M21 F02 L02) |
| `revision-stale-proposed` | studio | Self-configuration staleness panel proposed value (M21 F02 L02) |
| `theme-picker` | admin | The Appearance page's theme radio group (the fieldset; M31 F4 L08a) |
| `theme-option-light` | admin | The Appearance page's Light radio (M31 F4 L08a) |
| `theme-option-dark` | admin | The Appearance page's Dark radio (M31 F4 L08a) |
| `theme-option-auto` | admin | The Appearance page's Auto radio (M31 F4 L08a) |
| `rotate-result` | admin | The Encryption page's rotation result: a polite live region holding one status, with `data-state` `success` (clears after 3 s), `warning` (a staged rotation; stays until the next attempt) or `danger` (stays until the next attempt) (M31 F4 L08b) |
| `encryption-facts` | admin | The Encryption page's key facts list (M31 F4 L08b) |
| `encryption-last-rotated` | admin | The facts value for when the key was last rotated: "Never", or the date and time with the ISO value in `title` and `data-rotated-at` (M31 F4 L08b) |
| `encryption-credential-count` | admin | The facts value for how many stored items hold a secret (M31 F4 L08b) |
| `encryption-facts-error` | admin | The status shown instead of the facts when `GET /api/encryption/status` fails (M31 F4 L08b) |
| `prompts-load-error` | admin | The Prompts page's load-error host (an error status when `GET /api/info` fails) (M31 F4 L08b) |
| `rotate-key-btn` | admin | The Encryption page's rotate control (`#settings/encryption`; on the single General page until M25 F3 L5a) |
| `route-announcer` | shell | Visually-hidden polite live region (`role=status`) written by `js/router.js` on a commit that changes destination/section/item (flight 02 review, WCAG 4.1.3) |
| `save-agent-btn` | studio | |
| `save-mcp-source-btn` | studio | |
| `save-provider-btn` | admin | |
| `save-tool-btn` | admin | |
| `self-configuration-action-status` | studio | Self-configuration tab post-action `aria-live` summary + focus target (flight-end a11y fix) |
| `self-configuration-error` | studio | Self-configuration tab (M21 F01 L02) |
| `self-configuration-external-credential-row` | studio | Self-configuration External access — one active-grant row (M21 F03 L03) |
| `self-configuration-external-empty` | studio | Self-configuration External access — empty active-grants notice (M21 F03 L03) |
| `self-configuration-external-error` | studio | Self-configuration External access — section-level error (M21 F03 L03) |
| `self-configuration-external-grant-btn` | studio | Self-configuration External access — Grant access button (M21 F03 L03) |
| `self-configuration-external-grant-hint` | studio | Self-configuration External access — disabled-surface hint (M21 F03 L03) |
| `self-configuration-external-grant-label` | studio | Self-configuration External access — grant label input (M21 F03 L03) |
| `self-configuration-external-list` | studio | Self-configuration External access — active-grants list container (M21 F03 L03) |
| `self-configuration-external-revoke-btn` | studio | Self-configuration External access — revoke control, two-step confirm (M21 F03 L03) |
| `self-configuration-external-rotate-btn` | studio | Self-configuration External access — rotate control (M21 F03 L03) |
| `self-configuration-external-status` | studio | Self-configuration External access — `aria-live` status/announcement line (M21 F03 L03) |
| `self-configuration-external-token-copy-btn` | studio | Self-configuration External access — copy-once token copy button (M21 F03 L03) |
| `self-configuration-external-token-dismiss-btn` | studio | Self-configuration External access — copy-once reveal dismiss (M21 F03 L03) |
| `self-configuration-external-token-reveal` | studio | Self-configuration External access — copy-once secret reveal region (M21 F03 L03) |
| `self-configuration-external-token-url` | studio | Self-configuration External access — surface URL in the reveal (M21 F03 L03) |
| `self-configuration-external-token-value` | studio | Self-configuration External access — copy-once token readonly field (M21 F03 L03) |
| `rules-add-btn` | studio | Rules and notes tab, Add rule button; disabled while the text is empty after trimming (M27 F1 L2) |
| `rules-add-count` | studio | the Add textarea's live "{n} / 500" count (M27 F1 L2) |
| `rules-add-input` | studio | the Add rule textarea, with a visible label "Add a rule" (M27 F1 L2) |
| `rules-applies-note` | studio | "Changes apply to new and reopened chats, and to the next message in connector channels." (M27 F1 L2) |
| `rules-create-mode` | studio | create-mode notice "Save the agent first to add rules." (M27 F1 L2) |
| `rules-empty` | studio | the Rules list's "No rules yet." empty state (M27 F1 L2) |
| `rules-error` | studio | the Rules section's inline error area (`role=alert`, hidden when empty); shows a 422's `detail` (M27 F1 L2) |
| `rules-status` | studio | the Rules section's visually hidden polite status line: announces crossing the per-rule limit; the delete arm moved to `ui-confirm-live` (M27 F1 review, M31 F2 L5) |
| `rules-list` | studio | the ordered rule list (`<ol>`) (M27 F1 L2) |
| `rules-row` | studio | one rule row (`<li>`, `data-id`, `data-enabled`); `.rules-row--off` when disabled (M27 F1 L2) |
| `rules-row-cancel` | studio | inline edit Cancel; restores the text (M27 F1 L2) |
| `rules-row-delete` | studio | rule Delete, two-step through `App.confirmDelete` (M27 F1 L2) |
| `rules-row-down` | studio | rule Move down; disabled on the last row (M27 F1 L2) |
| `rules-row-edit` | studio | rule Edit (opens the inline textarea); `data-rule-id` (M27 F1 L2) |
| `rules-row-edit-input` | studio | the inline edit textarea (M27 F1 L2) |
| `rules-row-save` | studio | inline edit Save (M27 F1 L2) |
| `rules-row-text` | studio | the rule's text paragraph (M27 F1 L2) |
| `rules-row-toggle` | studio | the rule's on/off `App.ui.toggle` input (`role=switch`, name "Rule N enabled") (M27 F1 L2) |
| `rules-row-up` | studio | rule Move up; disabled on the first row (M27 F1 L2) |
| `rules-section` | studio | the Rules section of the Rules and notes tab (M27 F1 L2) |
| `self-configuration-save-first` | studio | Self-configuration tab, create-mode notice (M21 F01 L02) |
| `self-configuration-status` | studio | Self-configuration tab (M21 F01 L02) |
| `self-configuration-toggle-btn` | studio | Self-configuration tab enable/disable (M21 F01 L02); rendered as an `App.ui.toggle` checkbox `<input>` (it was the legacy `.tool-enable-switch`, deleted in M31 F5 L07) as of the HAT UX pass (M21 F02 L04) — same testid, moved from the retired `<button>` |
| `settings-nav` | admin | The Settings nav (`<nav aria-label="Settings">`, an `App.ui.navGroups` in the Settings column, reference spec section 8.1); its items are `settings-nav-{section}` links (M25 F3 L5a, DD6) |
| `studio-knowledge-inventory` | studio | Knowledge-base detail view root (L1-D5, M24 F06 L01; retires the F5 placeholder testid). Since M25 F3 L4a it marks the detail view only: the grid is retired, and the create form at `#library/knowledge/~new` does not carry it |
| `test-connection-btn` | admin | |
| `test-provider-btn` | studio | |
| `test-provider-result` | studio | |
| `test-result` | admin | M31 F4 L07d — the Built-in tools editor's Test result: a polite live region (`aria-live=polite`, `data-state` pending / success / warning / danger) holding one `App.ui.status` with the fixed headline ("Returned a result ({N} ms)", "Blocked by this tool's settings ({N} ms)", "Request failed"); empty until a Test runs |
| `test-saved-hint` | admin | M31 F4 L07d — "Tests the saved settings.", visible only while the editor is dirty |
| `test-tool-btn` | admin | |
| `thinking-disclosure` | chat | |
| `thinking-indicator` | chat | |
| `tool-card` | admin | The Built-in tools tile (kept since M25 F3 L5b: no longer a click target; its tool name is the item link `a.tool-tile-link` -> `#settings/tools/{name}`, `aria-current="page"` on the open tool's, the tile carries the selected wash) |
| `tool-editor-header` | admin | The open Built-in tool editor's header (`editorShell` `testid`); the page reveals and focuses it on an intent open (M31 F4 L11, replaces class queries) |
| `tool-test-details` | admin | M31 F4 L07d — the collapsed "Technical details" `App.ui.disclosure` under the Test result (absent when the output is empty) |
| `tool-test-output` | admin | M31 F4 L07d — the code block inside `tool-test-details`: the first 2 KB of the tool's output, with an ellipsis at the cut |
| `tool-toggle` | admin | The tile's enable switch (`role=switch`, named "Enable {name} for all agents", M31 F4 L06); it never navigates (M25 F3 L5b) |
| `tools-load-error` | admin | M31 F4 L06 — the Built-in tools list's load failure (`App.ui.status`, `role=alert`: "Couldn't load the built-in tools." and the server's reason); cleared by the next render |
| `tools-load-retry` | admin | M31 F4 L06 — the Retry button beside `tools-load-error` |
| `tools-loading` | admin | M31 F4 L06 — the "Loading tools…" status shown until the first list response |
| `trace-shell` | chat | |
| `ui-confirm-live` | shared | M31 F2 L5 (squawk 0220) — the one shared polite live region `App.ui.confirm` appends to `document.body` on the first arm; announces arm, lapse and commit |

## Parametric prefix families

| Prefix | Surface | Notes |
|--------|---------|-------|
| `platform-section-` | admin | The Prompts page's platform prompt blocks: `platform-section-{variant}-{id}` (`variant` `tools` or `tool_free`; one list, in assembly order, the tool-free Identity beside the tools Identity; the tool-free Formatting block is absent while its text equals the tools Formatting text, so only the tools block shows; a retired id cannot sit under a live family prefix, so it is not in the retired table, and `platform-variant-` is the retired entry) is a block, with `-applies-when` (its "Applies when" line) and `-text` (its `<pre>`) suffixes (Flight 2 leg 1c, DD8) |
| `agent-knowledge-row-` | studio | Agent editor Knowledge tab — one row per knowledge base, suffixed with the knowledge base id (M24 F06 L03) |
| `agent-knowledge-toggle-` | studio | Agent editor Knowledge tab — a row's attach checkbox, suffixed with the knowledge base id (DD-3, M24 F06 L03) |
| `agent-knowledge-tool-name-` | studio | Agent editor Knowledge tab — a row's server-derived tool name slot, suffixed with the knowledge base id (L3-D2, M24 F06 L03) |
| `connector-setup-steps-list-` | studio | Connector-editor inline setup-steps `<ul>`, suffixed with the selected connector type (e.g. `-discord`) (Squawk 0046) |
| `library-start-` | studio | The Library start page's per-group Add button, suffixed with the group and `-add` (`library-start-providers-add` (first), `library-start-knowledge-add`, `library-start-mcp-add`, `library-start-connectors-add`); each opens the group's `~new` form (model-providers sortie, DD6; it replaced the `library-empty-{group}` family) |
| `mcp-auth-required-link-` | studio | |
| `mcp-auth-required-notice-` | studio | |
| `mcp-no-tools-msg-` | studio | |
| `mcp-refresh-tools-btn-` | studio | |
| `mcp-source-details-body-` | studio | |
| `mcp-source-expand-` | studio | |
| `mcp-source-row-` | studio | |
| `mcp-source-self-configuration-hint-` | studio | locked attach-toggle hint on the owning agent's own surface row (M21 F01 L02) |
| `mcp-source-subtitle-` | studio | |
| `mcp-source-toggle-` | studio | |
| `mcp-tool-toggle-` | studio | |
| `mcp-tools-checkbox-group-` | studio | |
| `mcp-tools-error-` | studio | |
| `rail-` | shell | Workbench rail destination links, suffixed with the destination id (`rail-chats`, `rail-agents`, `rail-library`, `rail-settings`) — set by `js/app.js` through `App.ui.rail`'s per-item test id option (M25 F2 L6) |
| `settings-nav-` | admin | Settings nav links, suffixed with the page's route section (`settings-nav-appearance`, `-prompts`, `-encryption`, `-tools`, `-knowledge-indexing`); plain `<a href="#settings/{section}">`, the selected one `aria-current="page"` (M25 F3 L5a, DD6) |
| `tab-` | admin, studio | `tab-{id}` from `App.ui.tabs` items (ids `tools-tab-{id}` / `tools-panel-{id}` on the Built-in tools page, `idPrefix: 'tools'`, M31 F4 L06): the Built-in tools page's tabs and (M31 F2 L06a, now built from the item id) the agent editor's six: `tab-general`, `tab-rules-and-notes` (label "Rules and notes", route `#agents/{name}/rules-and-notes`, M27 F1 L2), `tab-knowledge`, `tab-mcps`, `tab-tools`, `tab-self-configuration` |

## Manual exceptions (variable-carried literals)

| Testid | Surface | Notes |
|--------|---------|-------|
| `kb-add-folder-btn` | studio | Knowledge detail view Folders section "Add folder" submit, same `_btn` indirection (M24 F06 L01; renamed from `kb-register-folder-btn`, and the button's own text from "Register folder", in M24 F06 L06) |
| `kb-folder-path` | studio | Knowledge detail view folder panel summary — the folder path text (the disclosure's `summaryTextTestid`; `[data-confirm-title]`, so it reads "Confirm delete?" while armed; M31 F3 L06a) |
| `kb-folder-skip-counts` | studio | Knowledge detail view folder panel body — the last completed walk's persisted `skipped_dirs`/`skipped_entries`, as " · Skipped 2 folders, 1 file" after the Last checked text, naming only non-zero counts; absent until a walk has completed and when both counts are zero (DD-7, Flight 7 Leg 2; wording since the M31 F3 HAT) |
| `kb-folder-status-error` | studio | Knowledge detail view folder panel body — the folder's own walk `error`, when set (M24 F06 L01) |
| `kb-folder-watch-error` | studio | Knowledge detail view folder panel body — `watch_error`, when set (M24 F06 L01) |
| `kb-item-chunks-btn` | studio | Knowledge detail view item row overflow menu — "View chunks" menuitem, same `_btn` indirection (M24 F06 L01; moved behind the overflow menu in L5-D4) |
| `kb-item-source-btn` | studio | Knowledge detail view item row overflow menu — "View source" menuitem, same `_btn` indirection (M24 F06 L01; moved behind the overflow menu in L5-D4) |

## Retired testids (not extracted; kept for the record)

The registry guard ignores this table. Ids here no longer exist in the UI. The
retired-selector guard (`tests/test_nav_helper.py` `RETIRED_SELECTORS`) fails if
any browser test or helper module names one, with no per-file exemption (M25 F3
L6), and `test_retired_selectors_cover_the_registry_retired_table` fails if an
id here is missing from `RETIRED_SELECTORS` or is registered in a live table
again. A retired id cannot come back.

| Retired id | Surface | Retired by |
|------------|---------|------------|
| `admin-theme-toggle-mount` | admin | M31 F4 L08a (DD6, DD8-19) — the Appearance page's segmented theme toggle (`App.theme.renderToggle`, an element id rather than a testid) is replaced by the `theme-picker` radio group (`theme-option-light`, `-dark` and `-auto`) |
| `platform-variant-` | admin | HAT step 9 (M31 F4, ledger 52) — the Platform prompt's "With tools" / "Without tools" sub-headings are removed; each block's "Applies when" line says it |
| `mcp-kv-tbody` | studio | M31 F5 L07 — the MCP key-value table is `App.ui.keyValueTable`; reach rows through `[data-testid="mcp-kv-table"] tbody tr` |
| `mcp-kv-thead` | studio | M31 F5 L07 — use `[data-testid="mcp-kv-table"] thead` (hidden while the table has no rows) |
| `mcp-kv-sensitive-info` | studio | M31 F5 L07 — the Sensitive column's info button is `App.ui.infoButton` (named "More information about Sensitive") |
| `base-prompt-content` | admin | Flight 2 leg 1c (DD8) — the Prompts page's single base-prompt block is replaced by one block per platform prompt section (`platform-section-{variant}-{id}`) |
| `kb-other-items-panel` | studio | M31 F3 HAT — the "Other items" panel is renamed "Individual files" (`kb-individual-files-panel`), with a description and a per-row remove |
| `agent-select` | chat | M25 F4 L4a (DD3, DD5) — the chat sidebar's "Select Agent" dropdown is retired; the Chats list's New chat (`chats-new-btn`) opens the agent picker (`agent-picker`). Fenced EXACTLY (`RETIRED_EXACT`): the live `agent-select-empty` (studio) is unaffected |
| `agent-tile-mcp-tool-count` | studio | M25 F3 L3 — the agents tile grid (its per-tile MCP tool count) is replaced by the Agents list |
| `agent-tile-tool-count` | studio | M25 F3 L3 — the agents tile grid (its per-tile built-in tool count) is replaced by the Agents list |
| `back-agent-btn` | studio | M25 F3 L3 (DD2) — the agent editor is hosted beside the Agents list; the "Agents" breadcrumb replaces Back |
| `back-connector-btn` | studio | M25 F3 L4b (DD2) — the connector editor is hosted beside the Library list; the breadcrumb's "Connectors" link (`editor-breadcrumb-link`) replaces Back |
| `back-knowledge-btn` | studio | M25 F3 L4b (DD2) — the knowledge-base detail is hosted beside the Library list; the breadcrumb's "Knowledge bases" link (`editor-breadcrumb-link`) replaces Back |
| `back-mcp-source-btn` | studio | M25 F3 L4b (DD2) — the MCP server editor is hosted beside the Library list; the breadcrumb's "MCP servers" link (`editor-breadcrumb-link`) replaces Back |
| `back-provider-btn` | admin | M25 F3 L5b (DD2, DD7) — the provider editor opens below the Providers tiles; the breadcrumb's "Providers" link (`editor-breadcrumb-link`) replaces Back |
| `back-tool-btn` | admin | M25 F3 L5b (DD2, DD7) — the tool editor opens below the tool list; the breadcrumb's "Built-in tools" link (`editor-breadcrumb-link`) replaces Back |
| `chat-drawer-notes-check` | chat | M27 F3 L2 (HAT decision, overrides #230) — renamed `chat-drawer-notes-flag`; the "Check this" chip is a warning triangle |
| `chat-drawer-notes-clear` | chat | M27 F3 L2 (HAT decision, overrides #230) — the drawer's Notes group is read-only; notes are managed in the Rules and notes tab |
| `chat-drawer-notes-delete` | chat | M27 F3 L2 (HAT decision, overrides #230) — the drawer's Notes group is read-only; notes are managed in the Rules and notes tab |
| `chat-drawer-notes-edit-link` | chat | M27 F3 L2 (HAT decision, overrides #230) — Open agent settings (`chat-drawer-settings-link`) is the way to the editor |
| `chat-drawer-notes-failed` | chat | M27 F3 L2 (HAT decision, overrides #230) — no delete in the drawer, so no delete failure |
| `chat-drawer-notes-status` | chat | M27 F3 L2 (HAT decision, overrides #230) — no delete arm to announce |
| `chat-drawer-rules-edit-link` | chat | M27 F3 L2 (HAT decision, overrides #230) — Open agent settings (`chat-drawer-settings-link`) is the way to the editor |
| `notes-row-check` | studio | M27 F3 L2 — the "Check this" badge is the warning-triangle flag `notes-row-flag` |
| `mcp-tools-last-updated` | studio | M31 F5 L08b (A6, DD9-13) — the "Last updated: 2 minutes ago" line is replaced by the status line's clock time (`mcp-connection-status`: "Connected · checked 3:42 PM") |
| `entity-tile` | studio, admin | M25 F3 (the tile grids are replaced by the list panes). The testid is retired, but the `entity-tile*` CSS classes are deliberately kept: they are live on the Built-in tools tiles (`areas/admin/tools-grid.js`), so the classes' presence is not a sign the testid still exists |
| `library-empty-` | studio | Model-providers sortie (DD6, DD8) — the Library start page's testids were renamed with `#library` becoming the one root: the page is `library-start` and each card's Add button `library-start-{group}-add`. A prefix, fenced as such: every `library-empty-*` id is gone |
| `new-chat-btn` | chat | M25 F4 L4b (DD3, DD6) — the chat header's hover-expanding "New Chat" (a new chat with the current agent) is retired with `h2.session-agent-badge`; the Chats list's New chat (`chats-new-btn`) and the new-chat state's "Pick a different agent" (`chat-pick-different-btn`) open the agent picker |
| `new-connector-btn` | studio | M25 F3 L4a (DD5) — the Connectors grid is retired; the Library list's Add menu (`library-add-connector`) replaces it |
| `new-knowledge-base-btn` | studio | M25 F3 L4a (DD5) — the Knowledge grid and its inline create form are retired; the Library list's Add menu (`library-add-knowledge`) opens the `~new` form |
| `new-mcp-source-btn` | studio | M25 F3 L4a (DD5) — the MCP Servers grid is retired; the Library list's Add menu (`library-add-mcp`) replaces it |
| `new-provider-btn` | admin | Model-providers sortie (DD8) — the Settings Providers page is gone; providers are created from the Library Add menu (`library-add-provider`) and the start-page card (`library-start-providers-add`) |
| `providers-empty` | admin | Model-providers sortie (DD8) — the Settings Providers page and its empty state are gone. A prefix, so it also covers `providers-empty-add`; the Library start page's Model providers card replaces it |
| `ui-demo-chooser` | admin | M31 F1 L1 (DD7) — the Design language reference page is retired; the library's contract tests run from the disk harness |
| `ui-demo-chooser-close` | admin | M31 F1 L1 (DD7) — the Design language reference page is retired; the library's contract tests run from the disk harness |
| `ui-demo-chooser-row` | admin | M31 F1 L1 (DD7) — the Design language reference page is retired; the library's contract tests run from the disk harness |
| `ui-demo-chooser-search` | admin | M31 F1 L1 (DD7) — the Design language reference page is retired; the library's contract tests run from the disk harness |
| `ui-demo-drawer-` | admin | M31 F1 L1 (DD7) — the Design language reference page is retired; the library's contract tests run from the disk harness |
| `ui-demo-drawer-toggle-` | admin | M31 F1 L1 (DD7) — the Design language reference page is retired; the library's contract tests run from the disk harness |
| `ui-demo-modal` | admin | M31 F1 L1 (DD7) — the Design language reference page is retired; the library's contract tests run from the disk harness |
