App.registerArea({
  id: 'studio',
  label: 'Studio',
  icon: '\uD83E\uDD16',
  order: 20,

  init: function (sidebar, content) {
    sidebar.innerHTML =
      '<div class="stub-sidebar">' +
        '<div class="title">Studio</div>' +
        '<div class="subtitle">Agent workspace</div>' +
      '</div>';
    content.innerHTML = '<div class="stub-content">Coming in Flight 03</div>';
  },

  activate: function () {},
  deactivate: function () {}
});
