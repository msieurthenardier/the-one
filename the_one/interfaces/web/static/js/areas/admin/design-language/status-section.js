(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // STATUS section samples non-destructive indicator primitives. Two flash
  // variants are overridden inline to render `position: relative` so they
  // sit in the gallery flow rather than the fixed top-of-viewport docking
  // the live primitive uses. The .empty-canvas sample is wrapped in a
  // fixed-height flex parent — per components.css:404-411 the primitive's
  // `flex: 1` needs `display: flex; flex-direction: column` on its parent
  // to claim vertical space.
  function render(host) {
    host.innerHTML =
      // --- badges (provider / tool category / connector) ---
      //     Per-badge ink (M17 F3 L4): each badge×ink pair clears body AA in
      //     both themes. Provider + tool badges use their real .area-admin
      //     classes (the gallery renders inside .area-admin). The connector
      //     badge is .area-studio-scoped, so discord is shown via the shared
      //     provider-badge base with inline fill/ink tokens for reference.
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">provider badges</span>' +
        '<div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">' +
          '<span class="admin-provider-badge admin-provider-badge--ollama">ollama</span>' +
          '<span class="admin-provider-badge admin-provider-badge--openai-compatible">openai-compatible</span>' +
          '<span class="admin-provider-badge admin-provider-badge--openai">openai</span>' +
          '<span class="admin-provider-badge admin-provider-badge--anthropic">anthropic</span>' +
          '<span class="admin-provider-badge admin-provider-badge--anthropic-plan">anthropic-plan</span>' +
          '<span class="admin-provider-badge admin-provider-badge--openrouter">openrouter</span>' +
          '<span class="admin-provider-badge admin-provider-badge--mock">mock</span>' +
          '<span class="admin-provider-badge admin-provider-badge--unknown">unknown</span>' +
        '</div>' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">tool category badges</span>' +
        '<div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">' +
          '<span class="admin-tool-badge admin-tool-badge--filesystem">filesystem</span>' +
          '<span class="admin-tool-badge admin-tool-badge--execution">execution</span>' +
          '<span class="admin-tool-badge admin-tool-badge--web">web</span>' +
          '<span class="admin-tool-badge admin-tool-badge--unknown">unknown</span>' +
        '</div>' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">connector badge (studio-scoped; shown for reference)</span>' +
        '<div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">' +
          '<span class="admin-provider-badge" style="background: var(--badge-discord); color: var(--badge-ink-discord);">discord</span>' +
        '</div>' +
      '</div>' +

      // --- LED indicator primitive ---
      '<div style="display: flex; flex-direction: column; gap: 4px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">indicator-led (canonical primitive)</span>' +
        '<div style="display: flex; gap: 14px; align-items: center;">' +
          '<span class="indicator-led indicator-led--success" aria-hidden="true"></span><span style="font-size: var(--font-size-body-sm);">Success</span>' +
          '<span class="indicator-led indicator-led--warning" aria-hidden="true"></span><span style="font-size: var(--font-size-body-sm);">Warning</span>' +
          '<span class="indicator-led indicator-led--danger" aria-hidden="true"></span><span style="font-size: var(--font-size-body-sm);">Danger</span>' +
          '<span class="indicator-led indicator-led--idle" aria-hidden="true"></span><span style="font-size: var(--font-size-body-sm);">Idle</span>' +
        '</div>' +
      '</div>' +

      // --- telemetry-strip (gallery sample — gallery-only until a downstream
      //     polish flight finds a real consumer, per flight design decision) ---
      '<div style="display: flex; flex-direction: column; gap: 4px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">telemetry-strip (gallery sample)</span>' +
        '<div class="telemetry-strip">' +
          '<div class="section-title">System</div>' +
          '<div class="telemetry-value"><span class="indicator-led indicator-led--success" aria-hidden="true"></span><span>Online</span></div>' +
        '</div>' +
        '<div class="telemetry-strip">' +
          '<div class="section-title">Agents</div>' +
          '<div class="telemetry-value">3 active</div>' +
        '</div>' +
        '<div class="telemetry-strip">' +
          '<div class="section-title">MCP</div>' +
          '<div class="telemetry-value"><span class="indicator-led indicator-led--warning" aria-hidden="true"></span><span>2/3</span></div>' +
        '</div>' +
      '</div>' +

      // --- test-result variants ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">test-result</span>' +
        '<div style="display: flex; gap: 16px; align-items: center;">' +
          '<span>Result:<span class="test-result test-result-ok"> ok</span></span>' +
          '<span>Result:<span class="test-result test-result-fail"> fail</span></span>' +
          '<span>Result:<span class="test-result test-result-warning"> warning</span></span>' +
          '<span>Result:<span class="test-result test-result-pending"> pending</span></span>' +
        '</div>' +
      '</div>' +

      // --- app-flash (success + error) — positioned relative for gallery flow ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">app-flash (success / error)</span>' +
        '<div style="display: flex; gap: 12px; flex-wrap: wrap;">' +
          '<div class="app-flash visible" style="position: relative; transform: none; left: auto; top: auto;">Saved successfully</div>' +
          '<div class="app-flash visible error" style="position: relative; transform: none; left: auto; top: auto;">Save failed</div>' +
        '</div>' +
      '</div>' +

      // --- banner (error / warning / info) ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">banner (error / warning / info)</span>' +
        '<div class="banner banner-error">Banner error variant — destructive action blocked, hard failure surfaced inline.</div>' +
        '<div class="banner banner-warning">Banner warning variant — irreversible operation, attention required before proceeding.</div>' +
        '<div class="banner banner-info">Banner info variant — informational note, neutral advisory.</div>' +
      '</div>' +

      // --- chip + chip-remove ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">chip + chip-remove</span>' +
        '<div style="display: flex; gap: 8px; flex-wrap: wrap;">' +
          '<span class="chip">sample-chip-a<button type="button" class="chip-remove" aria-label="remove">×</button></span>' +
          '<span class="chip">sample-chip-b<button type="button" class="chip-remove" aria-label="remove">×</button></span>' +
          '<span class="chip">no-remove-chip</span>' +
        '</div>' +
      '</div>' +

      // --- empty-state ---
      //     (--panel-radius-sm alias retired in L1; boxed with --radius-sm.)
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">empty-state</span>' +
        '<div style="border: 1px dashed var(--border); border-radius: var(--radius-sm);">' +
          '<div class="empty-state">Nothing here yet.</div>' +
        '</div>' +
      '</div>' +

      // --- empty-canvas — one-line statement + one primary action (the
      //     vocabulary empty-state, M17 F3 L4). Fixed-height flex parent
      //     required so the primitive's flex:1 claims vertical space. ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">empty-canvas (statement + primary action)</span>' +
        '<div style="height: 220px; display: flex; flex-direction: column; border: 1px dashed var(--border); border-radius: var(--radius-sm);">' +
          '<div class="empty-canvas">' +
            '<div class="empty-canvas-inner">' +
              '<div>No items yet — create your first one to get started.</div>' +
              '<button type="button" class="btn-outlined-primary empty-canvas-cta">Create item</button>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</div>';
  }

  window.App.admin.designLanguage.statusSection = { render: render };
})();
