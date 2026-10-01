(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // Mission 08 F2 L2: container module drives a SECTIONS descriptor list.
  // Each entry's render(host) is provided by a sibling module in
  // ./design-language/<slug>-section.js, registered on
  // window.App.admin.designLanguage[<slug>Section].
  function renderDesignLanguagePage(container) {
    var el = window.App.ui.util.el;
    var sectionsHost = el('div', {
      className: 'admin-content-body design-language-sections',
      id: 'design-language-sections'
    });
    container.textContent = '';
    container.appendChild(el('div', { className: 'page-header' }, [
      el('h1', { className: 'page-title', text: 'Design Language' })
    ]));
    container.appendChild(sectionsHost);

    // M25 F1 L6 (DD10): the six ui-* sections are the control library's living
    // reference, one [data-ui-demo] root per App.ui factory.
    var SECTIONS = [
      { slug: 'tokens',      title: 'Tokens' },
      { slug: 'typography',  title: 'Typography' },
      { slug: 'uiButtons',   title: 'Library: buttons' },
      { slug: 'uiFields',    title: 'Library: fields' },
      { slug: 'uiChoices',   title: 'Library: checkbox and toggle' },
      { slug: 'uiFeedback',  title: 'Library: badges and empty states' },
      { slug: 'uiLists',     title: 'Library: list pane' },
      { slug: 'uiMenus',     title: 'Library: menu' },
      { slug: 'uiModal',     title: 'Library: modal' },
      { slug: 'surfaces',    title: 'Surfaces' },
      { slug: 'status',      title: 'Status' },
      { slug: 'tabs',        title: 'Tabs' },
      { slug: 'markdown',    title: 'Markdown' }
    ];

    for (var i = 0; i < SECTIONS.length; i++) {
      var section = SECTIONS[i];
      var body = el('div', { className: 'design-language-section-body' });
      sectionsHost.appendChild(el('section', {
        className: 'design-language-section',
        dataset: { section: section.slug }
      }, [
        el('div', { className: 'section-title', text: section.title }),
        body
      ]));

      var module = window.App.admin.designLanguage[section.slug + 'Section'];
      if (module && typeof module.render === 'function') {
        module.render(body);
      }
    }
  }

  window.App.admin.renderDesignLanguagePage = renderDesignLanguagePage;
})();
