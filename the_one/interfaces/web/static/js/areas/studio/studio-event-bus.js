// App.studio.eventBus — Studio cross-module CustomEvent bus.
//
// Shared seam for inter-module event dispatch within the Studio area.
// F7 Recommendation #3(c) triggered the extraction.
//
// Public API:
//   App.studio.eventBus.emit(name, detail)
//   App.studio.eventBus.on(name, handler)
//
// No `off` primitive — Studio listeners are registered ONCE at module
// init and never torn down.
// The bus uses ``document`` as the underlying transport, so any module
// that lacks the bus reference can still listen via the native
// ``document.addEventListener(name, handler)`` interface; both
// interfaces produce/consume the same events.
//
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, {detail: detail}));
  }

  function on(name, handler) {
    document.addEventListener(name, handler);
  }

  window.App.studio.eventBus = {emit: emit, on: on};
})();
