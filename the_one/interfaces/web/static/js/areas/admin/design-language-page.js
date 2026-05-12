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
    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">Design Language</h1>' +
      '</div>' +
      '<div class="admin-content-body design-language-sections" id="design-language-sections"></div>';

    var sectionsHost = container.querySelector('#design-language-sections');

    var SECTIONS = [
      { slug: 'tokens',     title: 'TOKENS' },
      { slug: 'typography', title: 'TYPOGRAPHY' },
      { slug: 'buttons',    title: 'BUTTONS' },
      { slug: 'fields',     title: 'FIELDS' },
      { slug: 'surfaces',   title: 'SURFACES' },
      { slug: 'status',     title: 'STATUS' },
      { slug: 'tabs',       title: 'TABS' },
      { slug: 'modal',      title: 'MODAL' },
      { slug: 'markdown',   title: 'MARKDOWN' }
    ];

    for (var i = 0; i < SECTIONS.length; i++) {
      var section = SECTIONS[i];
      var sectionEl = document.createElement('section');
      sectionEl.className = 'design-language-section';
      sectionEl.setAttribute('data-section', section.slug);
      sectionEl.innerHTML =
        '<div class="section-title">' + section.title + '</div>' +
        '<div class="design-language-section-body"></div>';
      sectionsHost.appendChild(sectionEl);

      var moduleName = section.slug + 'Section';
      var module = window.App.admin.designLanguage[moduleName];
      if (module && typeof module.render === 'function') {
        module.render(sectionEl.querySelector('.design-language-section-body'));
      }
    }
  }

  window.App.admin.renderDesignLanguagePage = renderDesignLanguagePage;
})();
