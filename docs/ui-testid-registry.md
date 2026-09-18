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
  attribute or `setAttribute('data-testid', '...')`).
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
| `agent-empty` | studio | |
| `agent-item` | studio | |
| `agent-knowledge-empty-state` | studio | Agent editor Knowledge tab — no knowledge bases exist, marker still set (M24 F06 L03) |
| `agent-knowledge-list` | studio | Agent editor Knowledge tab — attach-row list container (M24 F06 L03) |
| `agent-knowledge-load-error` | studio | Agent editor Knowledge tab — the knowledge-base fetch failed; no `data-kb-list-loaded` marker (DD-4, L3-D1, M24 F06 L03) |
| `agent-knowledge-tab` | studio | Agent editor Knowledge tab root; carries `data-kb-list-loaded="true"` on a successful fetch (DD-4, M24 F06 L03) |
| `agent-select` | chat | |
| `agent-tile-mcp-tool-count` | studio | |
| `agent-tile-tool-count` | studio | |
| `approval-mode-error` | studio | Self-configuration tab approval-mode toggle (M21 F02 L02) |
| `approval-mode-status` | studio | Self-configuration tab approval-mode status line (M21 F02 L02) |
| `approval-mode-toggle-btn` | studio | Self-configuration tab approval-mode on/off (M21 F02 L02); rendered as a `.tool-enable-switch` checkbox `<input>` as of the HAT UX pass (M21 F02 L04) — same testid, moved from the retired `<button>` |
| `back-agent-btn` | studio | |
| `back-mcp-source-btn` | studio | |
| `back-provider-btn` | admin | |
| `back-tool-btn` | admin | |
| `base-prompt-content` | admin | |
| `cancel-agent-btn` | studio | |
| `cancel-mcp-source-btn` | studio | |
| `cancel-provider-btn` | admin | |
| `cancel-tool-btn` | admin | |
| `chat-attach-btn` | chat | |
| `chat-attachment` | chat | one per staged-image chicklet (chat-attachments row) |
| `chat-attachment-remove` | chat | one per chicklet — removes just that image |
| `chat-attachments` | chat | chicklet row above the composer, above .input-area |
| `chat-attachments-status` | chat | visually-hidden aria-live="polite" status; announces a stage/remove delta, separate from the chicklet row (M18 F03 L01) |
| `chat-image-input` | chat | |
| `chat-input` | chat | |
| `chat-send-btn` | chat | |
| `chat-stop-btn` | chat | |
| `chat-welcome` | chat | |
| `chat-welcome-mascot` | chat | |
| `confirm-dialog-overlay` | shell | |
| `connector-card` | studio | Connectors grid tile (M23 F02 L02); `data-id` carries the connector id |
| `connector-channel-map-row` | studio | Connector-editor channel→agent map, one row (M23 F02 L02) |
| `connector-doctor-result` | studio | Connector-editor doctor probe result region (M23 F02 L02) |
| `connector-pairing-code` | studio | Connector-editor pairing-code result — the code itself, in its own selectable `<code>` element (Squawk 0043) |
| `connector-pairing-result` | studio | Connector-editor pairing-code + expiry result region (M23 F02 L02) |
| `connector-setup-steps` | studio | Connector-editor inline setup-steps section container, both create and edit (Squawk 0046) |
| `connector-setup-steps-doc-ref` | studio | Connector-editor inline setup-steps plain-text reference naming `docs/connector-setup.md` — not a link; only `/static` is mounted, so an anchor would 404 (renamed from `connector-setup-steps-link` in the squawk 0046 review fix) (Squawk 0046) |
| `connector-status-label` | studio | Connector-editor header connection-status text, edit mode only (Squawk 0045) |
| `connector-status-led` | studio | Connector-editor header connection-status LED, edit mode only (Squawk 0045) |
| `delete-agent-btn` | studio | |
| `delete-blocked-message` | admin | |
| `delete-connector-btn` | studio | Connector-editor Danger Zone (M23 F02 L02) |
| `delete-knowledge-base-btn` | studio | Knowledge detail view Danger Zone (M24 F06 L01) |
| `delete-mcp-source-btn` | studio | |
| `delete-provider-btn` | admin | |
| `kb-chunk-count` | studio | Knowledge detail view status summary — chunk count (M24 F06 L01) |
| `kb-chunk-row` | studio | Knowledge detail view chunks panel — one row per chunk, `seq` order (DD-8, M24 F06 L01) |
| `kb-chunks-panel` | studio | Knowledge detail view — an item's chunks, opened on demand (DD-8, M24 F06 L01) |
| `kb-create-error` | studio | Knowledge grid create-form submission error (M24 F06 L01) |
| `kb-create-name-hint` | studio | Knowledge grid create-form advisory name-length hint, shown over 43 code points (DD-16, M24 F06 L01) |
| `kb-create-name-input` | studio | Knowledge grid create-form name field (M24 F06 L01) |
| `kb-folder-path-input` | studio | Knowledge detail view register-a-folder form path field (M24 F06 L01) |
| `kb-folder-register-error` | studio | Knowledge detail view register-a-folder form submission error, renders the route's `detail` message (DD-10, M24 F06 L01) |
| `kb-folder-row` | studio | Knowledge detail view status section — one row per registered folder (M24 F06 L01) |
| `kb-folder-status-error` | studio | Knowledge detail view folder row — the folder's own walk `error`, when set (M24 F06 L01) |
| `kb-folder-watch-error` | studio | Knowledge detail view folder row — `watch_error`, when set (M24 F06 L01) |
| `kb-folders-list` | studio | Knowledge detail view status section — folders container (M24 F06 L01) |
| `kb-indexer-state` | studio | Knowledge detail view status summary — indexer state word (M24 F06 L01) |
| `kb-item-error` | studio | Knowledge detail view item row — a `failed` item's error text (M24 F06 L01) |
| `kb-item-row` | studio | Knowledge detail view — one row per file item (M24 F06 L01) |
| `kb-item-standalone-badge` | studio | Knowledge detail view item row — standalone-inside-folder badge (DD-9, M24 F06 L01) |
| `kb-item-status` | studio | Knowledge detail view item row — the item's `status` (M24 F06 L01) |
| `kb-items-list` | studio | Knowledge detail view items container (M24 F06 L01) |
| `kb-panel-title` | studio | Knowledge detail view chunks/source panel — titled with the open item's path so the panel is attributable when it isn't beside its row (kb-studio-round-trip remediation FIX 4, M24 F06) |
| `kb-rename-error` | studio | Knowledge detail view rename-form submission error (M24 F06 L03) |
| `kb-rename-name-hint` | studio | Knowledge detail view rename-form advisory name-length hint, shown over 43 code points, reuses the create form's DD-16 hint text (M24 F06 L03) |
| `kb-rename-name-input` | studio | Knowledge detail view rename-form name field (M24 F06 L03) |
| `kb-search-degraded` | studio | Knowledge detail view search degrade line, shown alongside the response's own `indexer` word (AC-12, M24 F06 L01) |
| `kb-search-hit` | studio | Knowledge detail view — one search result row, carries `score` (M24 F06 L01) |
| `kb-search-input` | studio | Knowledge detail view search query field (DD-6, M24 F06 L01) |
| `kb-search-results` | studio | Knowledge detail view search results container (M24 F06 L01) |
| `kb-source-panel` | studio | Knowledge detail view — an item's source text, opened on demand (DD-8, M24 F06 L01) |
| `kb-source-text` | studio | Knowledge detail view — the fetched source text itself (M24 F06 L01) |
| `kb-status-count` | studio | Knowledge detail view status summary — one per-status file count chip (M24 F06 L01) |
| `kb-status-summary` | studio | Knowledge detail view status summary container (M24 F06 L01) |
| `knowledge-base-card` | studio | Knowledge grid tile; `data-id` carries the knowledge base id (M24 F06 L01) |
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
| `knowledge-settings-chunking-section` | admin | Knowledge settings panel — Chunking section container (M24 F06 L04) |
| `knowledge-settings-embedding-section` | admin | Knowledge settings panel — Embedding (read-only) section container (M24 F06 L04) |
| `knowledge-settings-flash` | admin | Knowledge settings panel — save success/error flash, mirrors `.admin-system-flash` (M24 F06 L04) |
| `knowledge-settings-load-error` | admin | Knowledge settings panel — `GET /api/knowledge-settings` failure banner; no defaults are rendered over it (M24 F06 L04) |
| `knowledge-settings-monitoring-section` | admin | Knowledge settings panel — Monitoring section container (M24 F06 L04) |
| `knowledge-settings-panel` | admin | Knowledge settings panel — root `.admin-form` container (M24 F06 L04) |
| `knowledge-settings-save-btn` | admin | Knowledge settings panel — the one explicit Save for chunking + monitoring together (L4-D4, M24 F06 L04) |
| `knowledge-settings-vector-store-section` | admin | Knowledge settings panel — Vector Store (read-only) section container (M24 F06 L04) |
| `knowledge-size-chars-error` | admin | Knowledge settings panel — `size_chars` inline validation message (L4-D3, M24 F06 L04) |
| `knowledge-size-chars-input` | admin | Knowledge settings panel — `chunking.size_chars` field (M24 F06 L04) |
| `knowledge-vector-store-backend` | admin | Knowledge settings panel — read-only vector-store backend value (DD-7, M24 F06 L04) |
| `knowledge-vector-store-dtype` | admin | Knowledge settings panel — read-only vector-store dtype value (DD-7, M24 F06 L04) |
| `knowledge-vector-store-readonly-reason` | admin | Knowledge settings panel — states why vector store is read-only, not a disabled input (L4-D1, M24 F06 L04) |
| `knowledge-watch-enabled-toggle` | admin | Knowledge settings panel — `monitoring.watch_enabled` toggle (M24 F06 L04) |
| `kv-add-row-btn` | studio | |
| `mcp-command-custom` | studio | |
| `mcp-command-hint` | studio | |
| `mcp-command-runtime` | studio | |
| `mcp-connection-led` | studio | |
| `mcp-consent-btn` | studio | |
| `mcp-empty-state` | studio | |
| `mcp-kv-sensitive-info` | studio | |
| `mcp-kv-table` | studio | |
| `mcp-kv-tbody` | studio | |
| `mcp-kv-thead` | studio | |
| `mcp-sandbox-section` | studio | |
| `mcp-server-info-section` | studio | |
| `mcp-server-instructions` | studio | |
| `mcp-server-meta` | studio | |
| `mcp-source-card` | studio | |
| `mcp-sources-list` | studio | |
| `mcp-test-connection` | studio | |
| `mcp-test-status` | studio | |
| `mcp-tools-last-updated` | studio | |
| `mcp-tools-list` | studio | |
| `message` | chat | |
| `modal-cancel-btn` | shell | |
| `modal-confirm-btn` | shell | |
| `model-capabilities` | studio | |
| `model-ctx-chip` | studio | |
| `nav-chat-btn` | shell | |
| `new-agent-btn` | studio | Unified create CTA (M17 F3 L3) — always-visible header button |
| `new-chat-btn` | chat | |
| `new-mcp-source-btn` | studio | Unified create CTA (M17 F3 L3) — always-visible header button |
| `new-provider-btn` | admin | Unified create CTA (M17 F3 L3) — always-visible header button |
| `pending-count` | studio | Self-configuration tab per-agent pending-revision count (M21 F02 L02) |
| `pending-queue` | studio | Self-configuration tab pending-revision queue container (M21 F02 L02) |
| `pending-queue-empty` | studio | Self-configuration tab empty-queue notice (M21 F02 L02) |
| `pending-queued` | chat | |
| `pending-queued-cancel` | chat | |
| `pending-queued-region` | chat | |
| `plan-code-input` | admin | anthropic-plan sign-in: consent-code paste field (no `data-field` — deliberately outside the dirty snapshot) |
| `plan-code-submit-btn` | admin | anthropic-plan sign-in: submit pasted code → POST /oauth/code |
| `plan-connected-indicator` | admin | anthropic-plan sign-in: connected-state label |
| `plan-reauth-btn` | admin | anthropic-plan sign-in: standing re-auth affordance (connected state) |
| `plan-reset-btn` | admin | anthropic-plan sign-in: reset connection (two-step confirm) → DELETE /oauth |
| `plan-signin-btn` | admin | anthropic-plan sign-in: sign-in affordance (create mode auto-saves the provider first, then starts the OAuth flow) |
| `plan-signin-consent` | admin | anthropic-plan sign-in: consent block wrapper (URL + code paste) |
| `plan-signin-copy-btn` | admin | anthropic-plan sign-in: copy authorize URL |
| `plan-signin-error` | admin | anthropic-plan sign-in: inline error area |
| `plan-signin-open-btn` | admin | anthropic-plan sign-in: gesture-context popup opener |
| `plan-signin-url` | admin | anthropic-plan sign-in: copyable authorize URL (readonly input) |
| `plan-test-reauth` | admin | provider /test result: distinct reauth_required message span |
| `provider-card` | admin | |
| `purge-history-btn` | studio | |
| `reset-mcp-connection-btn` | studio | |
| `revision-approve-btn` | studio | Self-configuration pending-revision card approve (M21 F02 L02) |
| `revision-base` | studio | Self-configuration pending-revision card current/base value (M21 F02 L02) |
| `revision-card` | studio | Self-configuration pending-revision card (M21 F02 L02) |
| `revision-current` | studio | Self-configuration staleness panel current value (M21 F02 L02) |
| `revision-dismiss-btn` | studio | Self-configuration pending-revision card dismiss (M21 F02 L02) |
| `revision-error` | studio | Self-configuration pending-revision card action error (M21 F02 L02) |
| `revision-field` | studio | Self-configuration pending-revision card field label (M21 F02 L02) |
| `revision-history` | studio | Self-configuration revision-history timeline container (M21 F02 L03); lives inside the collapsible `revision-history-details` as of the HAT UX pass (M21 F02 L04) |
| `revision-history-details` | studio | Self-configuration chronological-log `<details class="advanced-collapsible">` wrapper (M21 F02 L04 HAT — collapses the full log; the restore-node list stays outside it, always visible) |
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
| `rotate-key-btn` | admin | |
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
| `self-configuration-save-first` | studio | Self-configuration tab, create-mode notice (M21 F01 L02) |
| `self-configuration-status` | studio | Self-configuration tab (M21 F01 L02) |
| `self-configuration-toggle-btn` | studio | Self-configuration tab enable/disable (M21 F01 L02); rendered as a `.tool-enable-switch` checkbox `<input>` as of the HAT UX pass (M21 F02 L04) — same testid, moved from the retired `<button>` |
| `studio-knowledge-inventory` | studio | Knowledge section root — rendered by both the grid and detail branches (L1-D5, M24 F06 L01; retires the F5 placeholder testid) |
| `tab-general` | studio | |
| `tab-knowledge` | studio | |
| `tab-mcps` | studio | |
| `tab-self-configuration` | studio | fifth agent-editor tab (M21 F01 L02) |
| `tab-tools` | studio | |
| `test-connection-btn` | admin | |
| `test-provider-btn` | studio | |
| `test-provider-result` | studio | |
| `test-tool-btn` | admin | |
| `thinking-disclosure` | chat | |
| `thinking-indicator` | chat | |
| `tool-card` | admin | |
| `tool-toggle` | admin | |
| `trace-shell` | chat | |

## Parametric prefix families

| Prefix | Surface | Notes |
|--------|---------|-------|
| `agent-knowledge-row-` | studio | Agent editor Knowledge tab — one row per knowledge base, suffixed with the knowledge base id (M24 F06 L03) |
| `agent-knowledge-toggle-` | studio | Agent editor Knowledge tab — a row's attach checkbox, suffixed with the knowledge base id (DD-3, M24 F06 L03) |
| `agent-knowledge-tool-name-` | studio | Agent editor Knowledge tab — a row's server-derived tool name slot, suffixed with the knowledge base id (L3-D2, M24 F06 L03) |
| `connector-setup-steps-list-` | studio | Connector-editor inline setup-steps `<ul>`, suffixed with the selected connector type (e.g. `-discord`) (Squawk 0046) |
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
| `mcp-tools-body-` | studio | |
| `mcp-tools-checkbox-group-` | studio | |
| `mcp-tools-error-` | studio | |
| `tab-` | admin | |

## Manual exceptions (variable-carried literals)

| Testid | Surface | Notes |
|--------|---------|-------|
| `back-connector-btn` | studio | Connector-editor header — passed through the local `_btn(className, testid, text)` helper's `testid` parameter (M23 F02 L02) |
| `back-knowledge-btn` | studio | Knowledge detail view header — passed through the local `_btn(className, testid, text)` helper's `testid` parameter (M24 F06 L01) |
| `cancel-connector-btn` | studio | Connector-editor header, same `_btn` indirection (M23 F02 L02) |
| `connector-channel-map-add-btn` | studio | Connector-editor channel→agent map add-row, same `_btn` indirection (M23 F02 L02) |
| `connector-channel-map-remove-btn` | studio | Connector-editor channel→agent map per-row remove, same `_btn` indirection (M23 F02 L02) |
| `connector-doctor-btn` | studio | Connector-editor doctor probe, same `_btn` indirection (M23 F02 L02) |
| `connector-pairing-btn` | studio | Connector-editor pairing-code generation, same `_btn` indirection (M23 F02 L02) |
| `connector-pairing-copy-btn` | studio | Connector-editor pairing-code copy-to-clipboard button, same `_btn` indirection (Squawk 0043) |
| `kb-create-submit-btn` | studio | Knowledge grid create-form submit, same `_btn` indirection (M24 F06 L01) |
| `kb-item-chunks-btn` | studio | Knowledge detail view item row, same `_btn` indirection (M24 F06 L01) |
| `kb-item-source-btn` | studio | Knowledge detail view item row, same `_btn` indirection (M24 F06 L01) |
| `kb-register-folder-btn` | studio | Knowledge detail view register-a-folder form submit, same `_btn` indirection (M24 F06 L01) |
| `kb-reindex-all-btn` | studio | Knowledge detail view re-index control, same `_btn` indirection (M24 F06 L01) |
| `kb-reindex-changed-btn` | studio | Knowledge detail view re-index control, same `_btn` indirection (M24 F06 L01) |
| `kb-rename-submit-btn` | studio | Knowledge detail view rename-form submit, same `_btn` indirection (M24 F06 L03) |
| `kb-search-btn` | studio | Knowledge detail view search control submit, same `_btn` indirection (M24 F06 L01) |
| `new-connector-btn` | studio | Unified create CTA (M17 F3 L3 pattern), same `_btn` indirection (M23 F02 L02) |
| `new-knowledge-base-btn` | studio | Unified create CTA (M17 F3 L3 pattern), same `_btn` indirection (M24 F06 L01) |
| `rename-knowledge-base-btn` | studio | Knowledge detail view header rename toggle, same `_btn` indirection (M24 F06 L03) |
| `save-connector-btn` | studio | Connector-editor header, same `_btn` indirection (M23 F02 L02) |
