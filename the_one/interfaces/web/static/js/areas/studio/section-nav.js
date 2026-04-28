(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Studio sidebar section navigation primitive.
  //
  // Renders a header ("Studio") + three vertical buttons (Agents / Knowledge / Tools).
  // The active section button has aria-current="page" and tabindex="0"; the others
  // have tabindex="-1" (roving tabindex). Up/Down arrows move focus between buttons,
  // Home/End jump to first/last, Enter/Space (or click) activates via onSelect.
  //
  // The helper does NOT mutate URL state — that's studio.js's job (single _writeUrl
  // call site discipline).
  var SECTIONS = [
    { id: 'agents', label: 'Agents' },
    { id: 'knowledge', label: 'Knowledge' },
    { id: 'tools', label: 'Tools' }
  ];

  function renderSectionNav(container, active, options) {
    options = options || {};
    var onSelect = options.onSelect || function () {};

    container.innerHTML = '';
    container.className = 'section-nav';
    container.setAttribute('role', 'group');
    container.setAttribute('aria-label', 'Studio sections');

    var header = document.createElement('div');
    header.className = 'section-nav-header';
    header.textContent = 'Studio';
    container.appendChild(header);

    var buttons = [];
    for (var i = 0; i < SECTIONS.length; i++) {
      (function (section) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'section-nav-item';
        btn.dataset.section = section.id;
        btn.textContent = section.label;
        var isActive = section.id === active;
        if (isActive) {
          btn.setAttribute('aria-current', 'page');
          btn.setAttribute('tabindex', '0');
        } else {
          btn.setAttribute('tabindex', '-1');
        }
        btn.addEventListener('click', function () {
          onSelect(section.id);
        });
        buttons.push(btn);
        container.appendChild(btn);
      })(SECTIONS[i]);
    }

    // Keyboard handling: Up/Down/Home/End/Enter/Space on any of the buttons.
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

  // Updates active state on existing nav buttons in-place (idempotent re-render
  // avoidance — no need to rebuild DOM on every section change).
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

  window.App.studio.renderSectionNav = renderSectionNav;
  window.App.studio.updateActiveSection = updateActiveSection;
})();
