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
  static prefix (e.g. `connector-row-` + id). Registered by prefix; the guard
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
| `agent-knowledge-tab-stub` | studio | |
| `agent-select` | chat | |
| `agent-tile-mcp-tool-count` | studio | |
| `agent-tile-tool-count` | studio | |
| `back-agent-btn` | studio | |
| `back-connector-btn` | studio | |
| `back-mcp-source-btn` | studio | |
| `back-provider-btn` | admin | |
| `back-tool-btn` | admin | |
| `base-prompt-content` | admin | |
| `cancel-agent-btn` | studio | |
| `cancel-connector-btn` | studio | |
| `cancel-mcp-source-btn` | studio | |
| `cancel-provider-btn` | admin | |
| `cancel-tool-btn` | admin | |
| `chat-input` | chat | |
| `chat-send-btn` | chat | |
| `chat-stop-btn` | chat | |
| `chat-welcome` | chat | |
| `chat-welcome-mascot` | chat | |
| `confirm-dialog-overlay` | shell | |
| `connector-advanced-section` | studio | |
| `connector-allowlist-banner` | studio | |
| `connector-allowlist-banner-led` | studio | |
| `connector-allowlist-banner-refresh` | studio | |
| `connector-allowlist-banner-status` | studio | |
| `connector-allowlist-dm-admission-hint` | studio | |
| `connector-allowlist-dm-admission-row` | studio | |
| `connector-allowlist-dm-admission-select` | studio | |
| `connector-allowlist-guilds-hint` | studio | |
| `connector-allowlist-lists` | studio | |
| `connector-allowlist-peers-hint` | studio | |
| `connector-allowlist-peers-row` | studio | |
| `connector-allowlist-server-rows` | studio | |
| `connector-allowlist-servers-section` | studio | |
| `connector-allowlist-servers-slot` | studio | |
| `connector-always-listen-hint` | studio | |
| `connector-always-listen-toggle` | studio | |
| `connector-attached-agents-list` | studio | |
| `connector-attached-agents-table` | studio | |
| `connector-bot-token-hint` | studio | |
| `connector-card` | studio | |
| `connector-config` | studio | |
| `connector-config-add-row-btn` | studio | |
| `connector-config-inference-model-hint` | studio | |
| `connector-config-inference-model-select` | studio | |
| `connector-config-inference-provider-hint` | studio | |
| `connector-config-inference-provider-select` | studio | |
| `connector-config-table` | studio | |
| `connector-config-tbody` | studio | |
| `connector-connection-section` | studio | |
| `connector-continuation-hint` | studio | |
| `connector-editor-error` | studio | |
| `connector-empty-types-banner` | studio | |
| `connector-idle-hint` | studio | |
| `connector-inference-rows-container` | studio | |
| `connector-invite-copy-btn` | studio | |
| `connector-invite-hint` | studio | |
| `connector-invite-info` | studio | |
| `connector-invite-recompute-btn` | studio | |
| `connector-invite-section` | studio | |
| `connector-invite-url` | studio | |
| `connector-invite-url-wrap` | studio | |
| `connector-live-status` | studio | |
| `connector-live-status-error` | studio | |
| `connector-live-status-error-link` | studio | |
| `connector-live-status-error-wrap` | studio | |
| `connector-name-input` | studio | |
| `connector-pairing-code-input` | studio | |
| `connector-pairing-copy-btn` | studio | |
| `connector-pairing-generate-btn` | studio | |
| `connector-pairing-reveal-row` | studio | |
| `connector-pairing-status` | studio | |
| `connector-routing-add-row-btn` | studio | |
| `connector-routing-default` | studio | |
| `connector-routing-default-hint` | studio | |
| `connector-routing-table` | studio | |
| `connector-routing-tbody` | studio | |
| `connector-runtime-config-section` | studio | |
| `connector-secrets-add-row-btn` | studio | |
| `connector-secrets-table` | studio | |
| `connector-secrets-tbody` | studio | |
| `connector-test-connection-btn` | studio | |
| `connector-test-details` | studio | |
| `connector-test-details-wrap` | studio | |
| `connector-test-led` | studio | |
| `connector-test-message` | studio | |
| `connector-type-readonly` | studio | |
| `connector-type-select` | studio | |
| `connectors-empty-state` | studio | |
| `connectors-list` | studio | |
| `delete-agent-btn` | studio | |
| `delete-blocked-message` | admin | |
| `delete-connector-btn` | studio | |
| `delete-mcp-source-btn` | studio | |
| `delete-provider-btn` | admin | |
| `discord-additional-config-row` | studio | |
| `discord-bot-token` | studio | |
| `discord-bot-token-eye-btn` | studio | |
| `discord-presence-hint` | studio | |
| `discord-presence-name` | studio | |
| `discord-presence-type` | studio | |
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
| `nav-pending-badge` | shell | |
| `new-agent-btn` | studio | Unified create CTA (M17 F3 L3) — always-visible header button |
| `new-chat-btn` | chat | |
| `new-connector-btn` | studio | Unified create CTA (M17 F3 L3) — always-visible header button |
| `new-mcp-source-btn` | studio | Unified create CTA (M17 F3 L3) — always-visible header button |
| `new-provider-btn` | admin | Unified create CTA (M17 F3 L3) — always-visible header button |
| `pending-approval-approve` | chat | |
| `pending-approval-badge` | chat | |
| `pending-approval-banner` | chat | |
| `pending-approval-dismiss` | chat | |
| `pending-approval-item` | chat | |
| `pending-approvals-section` | chat | |
| `pending-queued` | chat | |
| `pending-queued-cancel` | chat | |
| `pending-queued-region` | chat | |
| `provider-card` | admin | |
| `purge-history-btn` | studio | |
| `reset-mcp-connection-btn` | studio | |
| `rotate-key-btn` | admin | |
| `routing-audit-badge` | chat | |
| `routing-audit-body` | chat | |
| `routing-audit-close` | chat | |
| `routing-audit-empty` | chat | |
| `routing-audit-expansion` | chat | |
| `routing-audit-overlay` | chat | |
| `routing-audit-policy` | chat | |
| `routing-audit-refresh` | chat | |
| `routing-audit-row` | chat | |
| `routing-audit-row-summary` | chat | |
| `routing-audit-trigger` | chat | |
| `save-agent-btn` | studio | |
| `save-mcp-source-btn` | studio | |
| `save-provider-btn` | admin | |
| `save-tool-btn` | admin | |
| `studio-knowledge-stub` | studio | |
| `tab-access-and-routing` | studio | |
| `tab-connectors` | studio | |
| `tab-general` | studio | |
| `tab-knowledge` | studio | |
| `tab-mcps` | studio | |
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
| `agent-connector-admit-dms-` | studio | |
| `agent-connector-admit-dms-hint-` | studio | |
| `agent-connector-admit-dms-row-` | studio | |
| `agent-connector-always-listen-` | studio | |
| `agent-connector-peers-dm-note-` | studio | |
| `connector-acl-` | studio | |
| `connector-acl-axis-` | studio | |
| `connector-acl-axis-count-` | studio | |
| `connector-acl-axis-toggle-` | studio | |
| `connector-acl-checkbox-warn-` | studio | |
| `connector-allowlist-` | studio | |
| `connector-allowlist-channels-wildcard-` | studio | |
| `connector-allowlist-roles-wildcard-` | studio | |
| `connector-allowlist-server-row-` | studio | |
| `connector-allowlist-server-row-remove-` | studio | |
| `connector-attached-agent-` | studio | |
| `connector-attached-agent-channels-` | studio | |
| `connector-attached-agent-detach-` | studio | |
| `connector-attached-agent-link-` | studio | |
| `connector-attached-agent-peers-` | studio | |
| `connector-details-body-` | studio | |
| `connector-missing-` | studio | |
| `connector-row-` | studio | |
| `connector-toggle-` | studio | |
| `discoverable-dropdown-` | studio | |
| `discoverable-dropdown-chip-` | studio | |
| `discoverable-dropdown-chip-remove-` | studio | |
| `discoverable-dropdown-chips-` | studio | |
| `discoverable-dropdown-input-` | studio | |
| `discoverable-dropdown-item-` | studio | |
| `discoverable-dropdown-menu-` | studio | |
| `discoverable-dropdown-status-` | studio | |
| `mcp-auth-required-link-` | studio | |
| `mcp-auth-required-notice-` | studio | |
| `mcp-no-tools-msg-` | studio | |
| `mcp-refresh-tools-btn-` | studio | |
| `mcp-source-details-body-` | studio | |
| `mcp-source-expand-` | studio | |
| `mcp-source-row-` | studio | |
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
| `connector-continuation-input` | studio | passed to `renderLifecycleSelect(...)`, `connector-editor.js` |
| `connector-idle-timeout-input` | studio | passed to `renderLifecycleSelect(...)`, `connector-editor.js` |
| `create-and-test-connector-btn` | studio | `saveTestId` ternary, `connector-editor.js` (create mode) |
| `save-connector-btn` | studio | `saveTestId` ternary, `connector-editor.js` (edit mode) |
