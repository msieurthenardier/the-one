(function () {
  'use strict';
  window.App = window.App || {};
  window.App.layout = window.App.layout || {};

  // Generic sidebar section navigation primitive.
  //
  // Renders a header + N vertical buttons (one per item). The active button has
  // aria-current="page" and tabindex="0"; the others have tabindex="-1"
  // (roving tabindex). Up/Down arrows move focus, Home/End jump to first/last,
  // Enter/Space (or click) activates via onSelect.
  //
  // The helper does NOT mutate URL state — that's the caller's job
  // (single _writeUrl call site discipline).
  // Helper contract:
  //   - container: element to render into; helper sets its className + role
  //   - items: required array of {id, label} objects
  //   - active: id of the active item (or null on first render)
  //   - options.onSelect: callback (id) => void
  //   - options.header: required string — the section-nav header text
  //   - options.ariaLabel: required string — the container's accessible name
  // Caller contract: single-mount-per-container. The helper attaches a
  // keydown listener to `container`; calling renderSectionNav twice on the
  // same container would accumulate listeners. Use updateActiveSection for
  // active-state changes; only call renderSectionNav once at init.
  function renderSectionNav(container, items, active, options) {
    options = options || {};
    var onSelect = options.onSelect || function () {};
    var headerText = options.header || '';
    var ariaLabel = options.ariaLabel || '';

    container.innerHTML = '';
    container.className = 'section-nav';
    container.setAttribute('role', 'group');
    if (ariaLabel) container.setAttribute('aria-label', ariaLabel);
    // Defensive: warn if no aria-label provided. The container's role="group"
    // requires an accessible name (WAI-ARIA spec); silent-omit would regress
    // a11y vs. the F5 helper which hardcoded a label.
    if (!ariaLabel && console && console.warn) {
      console.warn('App.layout.renderSectionNav: ariaLabel not provided; container has no accessible name.');
    }

    if (headerText) {
      var header = document.createElement('div');
      header.className = 'section-nav-header';
      header.textContent = headerText;
      container.appendChild(header);
    }

    var buttons = [];
    for (var i = 0; i < items.length; i++) {
      (function (item) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'section-nav-item';
        btn.dataset.section = item.id;
        btn.textContent = item.label;
        var isActive = item.id === active;
        if (isActive) {
          btn.setAttribute('aria-current', 'page');
          btn.setAttribute('tabindex', '0');
        } else {
          btn.setAttribute('tabindex', '-1');
        }
        btn.addEventListener('click', function () { onSelect(item.id); });
        buttons.push(btn);
        container.appendChild(btn);
      })(items[i]);
    }

    container.addEventListener('keydown', function (e) {
      var current = document.activeElement;
      var idx = buttons.indexOf(current);
      if (idx === -1) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        buttons[(idx + 1) % buttons.length].focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        buttons[(idx - 1 + buttons.length) % buttons.length].focus();
      } else if (e.key === 'Home') {
        e.preventDefault();
        buttons[0].focus();
      } else if (e.key === 'End') {
        e.preventDefault();
        buttons[buttons.length - 1].focus();
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        var section = current.dataset.section;
        if (section) onSelect(section);
      }
    });
  }

  function updateActiveSection(container, active) {
    var buttons = container.querySelectorAll('.section-nav-item');
    for (var i = 0; i < buttons.length; i++) {
      var btn = buttons[i];
      var isActive = btn.dataset.section === active;
      if (isActive) {
        btn.setAttribute('aria-current', 'page');
        btn.setAttribute('tabindex', '0');
      } else {
        btn.removeAttribute('aria-current');
        btn.setAttribute('tabindex', '-1');
      }
    }
  }

  window.App.layout.renderSectionNav = renderSectionNav;
  window.App.layout.updateActiveSection = updateActiveSection;
})();
