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
    // Convention: activate() must refresh the area's data so changes made in
    // other areas (e.g. adding a provider in Admin) are reflected immediately.
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

  function escapeAttr(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB', 'TB'];
    var i = 0;
    var val = bytes;
    while (val >= 1024 && i < units.length - 1) { val /= 1024; i++; }
    return (i >= 2 ? val.toFixed(1) : Math.round(val)) + ' ' + units[i];
  }

  function showFlash(container, msg, isError) {
    var el = document.createElement('div');
    el.className = 'app-flash' + (isError ? ' error' : '');
    if (isError) {
      el.setAttribute('role', 'alert');
    } else {
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
    }
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(function () { el.classList.add('visible'); }, 10);
    setTimeout(function () {
      el.classList.remove('visible');
      setTimeout(function () { el.remove(); }, 300);
    }, 2000);
  }

  return { registerArea: registerArea, escapeHtml: escapeHtml, escapeAttr: escapeAttr, formatBytes: formatBytes, showFlash: showFlash };
})();
