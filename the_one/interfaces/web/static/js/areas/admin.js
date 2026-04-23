App.registerArea({
  id: 'admin',
  label: 'Admin',
  icon: '\u2699\uFE0F',
  order: 30,

  init: function (sidebar, content) {
    sidebar.innerHTML =
      '<div class="stub-sidebar">' +
        '<div class="title">Admin</div>' +
        '<div class="subtitle">System settings</div>' +
      '</div>';
    content.innerHTML = '<div class="stub-content">Coming in Flight 05</div>';
  },

  activate: function () {},
  deactivate: function () {}
});
