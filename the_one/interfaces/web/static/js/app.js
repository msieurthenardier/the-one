var App = (function () {
  var areas = {};
  var order = [];
  var currentId = null;
  var initialized = {};

  function registerArea(descriptor) {
    areas[descriptor.id] = descriptor;
    order.push(descriptor);
    order.sort(function (a, b) { return a.order - b.order; });
  }

  function renderNav() {
    var nav = document.getElementById('app-nav');
    nav.innerHTML = '';
    for (var i = 0; i < order.length; i++) {
      var a = order[i];
      var el = document.createElement('div');
      el.className = 'nav-item';
      el.dataset.area = a.id;
      el.textContent = a.icon;
      el.title = a.label;
      el.addEventListener('click', (function (id) {
        return function () { location.hash = id; };
      })(a.id));
      nav.appendChild(el);
    }
  }

  function switchTo(areaId) {
    if (!areas[areaId]) areaId = 'chat';
    if (areaId === currentId) return;

    // Deactivate current
    if (currentId && areas[currentId]) {
      areas[currentId].deactivate();
    }

    // Hide all panels
    var sidebarPanels = document.querySelectorAll('#app-sidebar .sidebar-panel');
    var contentPanels = document.querySelectorAll('#app-content .content-panel');
    for (var i = 0; i < sidebarPanels.length; i++) sidebarPanels[i].classList.remove('active');
    for (var i = 0; i < contentPanels.length; i++) contentPanels[i].classList.remove('active');

    // Init on first activation
    if (!initialized[areaId]) {
      var sidebarPanel = document.createElement('div');
      sidebarPanel.className = 'sidebar-panel area-' + areaId;
      document.getElementById('app-sidebar').appendChild(sidebarPanel);

      var contentPanel = document.createElement('div');
      contentPanel.className = 'content-panel area-' + areaId;
      document.getElementById('app-content').appendChild(contentPanel);

      areas[areaId].init(sidebarPanel, contentPanel);
      initialized[areaId] = true;
    }

    // Show target panels
    var targetSidebar = document.querySelector('#app-sidebar .area-' + areaId);
    var targetContent = document.querySelector('#app-content .area-' + areaId);
    if (targetSidebar) targetSidebar.classList.add('active');
    if (targetContent) targetContent.classList.add('active');

    // Update nav highlight
    var navItems = document.querySelectorAll('.nav-item');
    for (var i = 0; i < navItems.length; i++) {
      navItems[i].classList.toggle('active', navItems[i].dataset.area === areaId);
    }

    currentId = areaId;
    areas[areaId].activate();
  }

  function getHashArea() {
    var hash = location.hash.replace('#', '');
    return hash && areas[hash] ? hash : 'chat';
  }

  window.addEventListener('hashchange', function () {
    switchTo(getHashArea());
  });

  document.addEventListener('DOMContentLoaded', function () {
    renderNav();
    switchTo(getHashArea());
  });

  function escapeHtml(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  return { registerArea: registerArea, escapeHtml: escapeHtml };
})();
