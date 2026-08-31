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
| `agent-knowledge-tab-stub` | studio | |
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
| `delete-agent-btn` | studio | |
| `delete-blocked-message` | admin | |
| `delete-mcp-source-btn` | studio | |
| `delete-provider-btn` | admin | |
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
| `studio-knowledge-stub` | studio | |
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

No entries currently — the connector editor (Mission 23 Flight 1) was the
sole occupant of this table. Re-add a row here if a future feature carries
a testid through a variable/parameter the extractor can't see statically.
