(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // Shared helper for the control-library sections (M25 F1 L6, DD10).
  // demo(host, factoryName, buildFn) appends a [data-ui-demo="<factoryName>"]
  // root holding a dark and a light pane. buildFn(pane, theme) runs once per
  // pane, so every demo is built twice: ids come from App.ui.util.uid and no
  // demo passes a testid. Each pane sets its own colour and background (CSS
  // .design-language-ui-pane) because inherited colour resolves at <body>.
  var el = App.ui.util.el;

  function caption(text) {
    return el('span', { className: 'design-language-caption', text: text });
  }

  function row(children) {
    return el('div', { className: 'design-language-ui-row' }, children);
  }

  function demo(host, factoryName, buildFn) {
    var themes = ['dark', 'light'];
    var panes = [];
    for (var i = 0; i < themes.length; i++) {
      var pane = el('div', {
        className: 'design-language-ui-pane',
        dataset: { theme: themes[i] }
      }, [caption(themes[i])]);
      buildFn(pane, themes[i]);
      panes.push(pane);
    }
    var root = el('div', {
      className: 'design-language-ui-demo',
      dataset: { uiDemo: factoryName }
    }, panes);
    host.appendChild(root);
    return root;
  }

  window.App.admin.designLanguage.uiDemo = { demo: demo, caption: caption, row: row };
})();
