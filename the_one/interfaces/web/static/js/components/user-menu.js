// L9 — User menu (avatar dropdown).
//
// Items: Theme (Light/Dark/Auto via App.theme.renderToggle) ·
//        System → General · version footer.
//
// No sign-out / profile / multi-user features — this app is single-user
// no-auth per SECURITY-MODEL.md.
(function () {
  'use strict';

  var root = null;
  var anchor = null;

  function build() {
    root = document.createElement('div');
    root.className = 'user-menu';
    root.setAttribute('role', 'menu');
    root.setAttribute('data-testid', 'user-menu');
    root.style.display = 'none';

    // Theme row — renderToggle handles the radiogroup + ARIA.
    var themeHead = document.createElement('div');
    themeHead.className = 'user-menu-heading';
    themeHead.id = 'um-theme-heading';
    themeHead.textContent = 'Theme';

    var themeBox = document.createElement('div');
    themeBox.className = 'user-menu-theme';

    var sysItem = document.createElement('a');
    sysItem.className = 'user-menu-item';
    sysItem.setAttribute('role', 'menuitem');
    sysItem.href = '#admin/general';
    sysItem.textContent = 'System → General';
    sysItem.addEventListener('click', close);

    var divider = document.createElement('div');
    divider.className = 'user-menu-divider';

    var version = document.createElement('div');
    version.className = 'user-menu-version';
    var v = (window.App && window.App.config && window.App.config.version) || 'unknown';
    version.textContent = 'Holograph v' + v;

    root.appendChild(themeHead);
    root.appendChild(themeBox);
    root.appendChild(sysItem);
    root.appendChild(divider);
    root.appendChild(version);

    // Now that themeBox is in the DOM, populate it.
    if (window.App && window.App.theme && typeof window.App.theme.renderToggle === 'function') {
      window.App.theme.renderToggle(themeBox, { labelledBy: 'um-theme-heading' });
    }

    document.body.appendChild(root);
    return root;
  }

  function position() {
    if (!anchor) return;
    var rect = anchor.getBoundingClientRect();
    root.style.position = 'fixed';
    // 220px wide; right-align to anchor's right edge.
    root.style.top  = (rect.bottom + 6) + 'px';
    root.style.left = (rect.right - 220) + 'px';
  }

  function onOutsideClick(e) {
    if (!root || root.style.display === 'none') return;
    if (root.contains(e.target)) return;
    if (anchor && anchor.contains(e.target)) return;
    close();
  }

  function onKeydown(e) {
    if (!root || root.style.display === 'none') return;
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
  }

  function onHashChange() { if (root && root.style.display !== 'none') close(); }
  function onTopnavRerender() {
    if (root && root.style.display !== 'none' && anchor && !anchor.isConnected) {
      close();
    }
  }

  function toggle(anchorEl) {
    if (root && root.style.display !== 'none') {
      close();
      return;
    }
    if (!root) build();
    anchor = anchorEl || null;
    root.style.display = 'block';
    position();
  }

  function close() {
    if (!root) return;
    root.style.display = 'none';
    if (anchor && anchor.isConnected && typeof anchor.focus === 'function') {
      try { anchor.focus(); } catch (e) { /* ignore */ }
    }
    anchor = null;
  }

  document.addEventListener('click', onOutsideClick);
  document.addEventListener('keydown', onKeydown);
  window.addEventListener('hashchange', onHashChange);
  document.addEventListener('topnav:rerender', onTopnavRerender);

  window.App = window.App || {};
  window.App.userMenu = { toggle: toggle, close: close };
})();
