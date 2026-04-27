(function () {
  var areas = {};
  var order = [];
  var currentId = null;
  var currentSub = null;
  var initialized = {};

  function registerArea(descriptor) {
    areas[descriptor.id] = descriptor;
    order.push(descriptor);
    order.sort(function (a, b) { return a.order - b.order; });
  }

  function renderTopBar() {
    var topbar = document.getElementById('app-topbar');
    topbar.innerHTML =
      '<h1 class="app-topbar-title">the-one</h1>' +
      '<div class="app-topbar-actions">' +
        '<button class="app-picker-button" aria-label="Switch app" aria-haspopup="true" aria-expanded="false">' +
          App.icons.menu +
        '</button>' +
      '</div>' +
      '<nav class="app-picker-popover" aria-label="App areas" data-open="false"></nav>';

    var pickerBtn = topbar.querySelector('.app-picker-button');
    var popover = topbar.querySelector('.app-picker-popover');

    // Picker open/close — defined here so option-click handlers can call closePicker via closure.
    function openPicker() {
      popover.dataset.open = 'true';
      pickerBtn.setAttribute('aria-expanded', 'true');
      var firstOpt = popover.querySelector('.app-picker-option');
      // data-open switches CSS to display: block synchronously (attribute sets are
      // synchronous; the CSS rule applies to the next style recalc which happens
      // before focus() returns). Safe to focus immediately.
      if (firstOpt) firstOpt.focus();
    }
    function closePicker() {
      popover.dataset.open = 'false';
      pickerBtn.setAttribute('aria-expanded', 'false');
    }

    // Build picker options — closePicker is in scope here.
    for (var i = 0; i < order.length; i++) {
      var a = order[i];
      var opt = document.createElement('button');
      opt.className = 'app-picker-option';
      opt.dataset.area = a.id;
      opt.setAttribute('type', 'button');
      opt.innerHTML = a.icon + '<span>' + a.label + '</span>';
      opt.addEventListener('click', (function (id) {
        return function (e) {
          // stopPropagation guards against click-outside listener firing after
          // option click — defensive; option handler calls closePicker() itself.
          e.stopPropagation();
          location.hash = id;
          closePicker();
        };
      })(a.id));
      popover.appendChild(opt);
    }

    pickerBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (popover.dataset.open === 'true') closePicker();
      else openPicker();
    });

    // Click-outside closes
    document.addEventListener('click', function (e) {
      if (popover.dataset.open !== 'true') return;
      if (popover.contains(e.target) || pickerBtn.contains(e.target)) return;
      closePicker();
    });

    // Keyboard within popover (Escape, arrow-cycle)
    popover.addEventListener('keydown', function (e) {
      var opts = Array.prototype.slice.call(popover.querySelectorAll('.app-picker-option'));
      var idx = opts.indexOf(document.activeElement);
      if (e.key === 'Escape') {
        e.preventDefault();
        closePicker();
        pickerBtn.focus();
        return;
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
        e.preventDefault();
        if (idx === -1) opts[0].focus();
        else opts[(idx + 1) % opts.length].focus();
        return;
      }
      if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
        e.preventDefault();
        if (idx === -1) opts[opts.length - 1].focus();
        else opts[(idx - 1 + opts.length) % opts.length].focus();
        return;
      }
    });
  }

  function parseHash(hashString) {
    var raw = (hashString || '').replace(/^#/, '');
    if (!raw) return { area: null, sub: null };
    var slash = raw.indexOf('/');
    if (slash === -1) return { area: raw, sub: null };
    return { area: raw.slice(0, slash), sub: raw.slice(slash + 1) };
  }

  function switchTo(areaId, sub) {
    if (!areas[areaId]) areaId = 'chat';
    sub = (sub === undefined ? null : sub);

    // Same-area sub-change: only hydrate
    if (areaId === currentId && sub === currentSub) return;
    if (areaId === currentId && sub !== currentSub) {
      currentSub = sub;
      if (typeof areas[areaId].hydrateState === 'function') areas[areaId].hydrateState(sub);
      return;
    }

    // Cross-area navigation: deactivate current, activate target
    if (currentId && areas[currentId]) {
      areas[currentId].deactivate();
    }

    // Hide all panels
    var sidebarPanels = document.querySelectorAll('#app-sidebar .sidebar-panel');
    var contentPanels = document.querySelectorAll('#main-content .content-panel');
    for (var i = 0; i < sidebarPanels.length; i++) sidebarPanels[i].classList.remove('active');
    for (var i = 0; i < contentPanels.length; i++) contentPanels[i].classList.remove('active');

    // Init on first activation
    if (!initialized[areaId]) {
      var sidebarPanel = document.createElement('div');
      sidebarPanel.className = 'sidebar-panel area-' + areaId;
      document.getElementById('app-sidebar').appendChild(sidebarPanel);

      var contentPanel = document.createElement('div');
      contentPanel.className = 'content-panel area-' + areaId;
      document.getElementById('main-content').appendChild(contentPanel);

      areas[areaId].init(sidebarPanel, contentPanel);
      initialized[areaId] = true;
    }

    // Show target panels
    var targetSidebar = document.querySelector('#app-sidebar .area-' + areaId);
    var targetContent = document.querySelector('#main-content .area-' + areaId);
    if (targetSidebar) targetSidebar.classList.add('active');
    if (targetContent) targetContent.classList.add('active');

    // Set aside aria-label for the active area
    var asideEl = document.getElementById('app-sidebar');
    var areaLabel = areas[areaId].sidebarLabel || (areas[areaId].label + ' sidebar');
    asideEl.setAttribute('aria-label', areaLabel);

    // Update picker highlight
    var pickerOpts = document.querySelectorAll('.app-picker-option');
    for (var i = 0; i < pickerOpts.length; i++) {
      pickerOpts[i].classList.toggle('active', pickerOpts[i].dataset.area === areaId);
    }

    currentId = areaId;
    currentSub = sub;
    // Convention: activate() must refresh the area's data so changes made in
    // other areas (e.g. adding a provider in Admin) are reflected immediately.
    areas[areaId].activate();

    if (typeof areas[areaId].hydrateState === 'function') areas[areaId].hydrateState(sub);
  }

  window.addEventListener('hashchange', function () {
    var parsed = parseHash(location.hash);
    if (!parsed.area || !areas[parsed.area]) return; // skip-link / unknown area
    switchTo(parsed.area, parsed.sub);
  });

  document.addEventListener('DOMContentLoaded', function () {
    renderTopBar();
    var parsed = parseHash(location.hash);
    var area = (parsed.area && areas[parsed.area]) ? parsed.area : 'chat';
    switchTo(area, parsed.sub);
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

  window.App = window.App || {};
  Object.assign(window.App, {
    registerArea: registerArea,
    router: {
      parseHash: parseHash,
      /**
       * Update the URL sub-state without pushing history. Used by area code when
       * the user navigates within an area (selects a different session/agent/category).
       * The area is implicit (currentId) — only the sub portion is updated.
       * Calling this does NOT fire hashchange (replaceState is silent), so it does
       * not loop back through switchTo.
       */
      replaceSub: function (sub) {
        if (!currentId) return;
        var newHash = sub ? '#' + currentId + '/' + sub : '#' + currentId;
        if (location.hash === newHash) return; // no-op
        history.replaceState(null, '', newHash);
      },
    },
    escapeHtml: escapeHtml,
    escapeAttr: escapeAttr,
    formatBytes: formatBytes,
    showFlash: showFlash,
  });
})();
