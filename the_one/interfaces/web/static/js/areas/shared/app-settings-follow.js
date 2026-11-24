// App.appSettingsFollow -- the one `app_settings` follow registration of the page (M36 F5 L4b,
// flight DD8 and DD9). App.gleepglorpFollow.listen registers once per kind per page (a second call
// for the same kind is a silent no-op), so every consumer of an approved Settings change shares
// this dispatcher, which listens once and hands the event to the page that owns its `target_id`
// (the Settings route section: `date-and-time` or `knowledge-indexing`).
//
//   register(pageKey, fn) -> unregister()
//       fn(detail, settings) runs for each approved change to that page. For `date-and-time` the
//       stored settings were read once (GET /api/time-settings) and `settings` is that row; for
//       `knowledge-indexing` it is undefined (the Knowledge indexing page reads its own).
//
// The app's own clock follows in EVERY window whatever page it shows: before the Date and time
// page's handler (when it is mounted) runs, App.time.applySettings moves the zone, so every
// rendered time that subscribes through App.time.onChange re-renders in the new zone. A failed
// read is dropped (the next boot reads the stored zone).
//
// This file loads right after gleepglorp-follow-core.js and is always loaded, which is why the
// clock follow lives here and not in the Date and time page.
(function () {
  'use strict';
  window.App = window.App || {};

  var handlers = Object.create(null); // pageKey -> [fn]

  function register(pageKey, fn) {
    (handlers[pageKey] = handlers[pageKey] || []).push(fn);
    return function unregister() {
      var list = handlers[pageKey] || [];
      var at = list.indexOf(fn);
      if (at !== -1) list.splice(at, 1);
    };
  }

  function run(pageKey, detail, settings) {
    (handlers[pageKey] || []).slice().forEach(function (fn) {
      try { fn(detail, settings); } catch (err) { /* one page's follow never stops another's */ }
    });
  }

  function onEvent(detail) {
    if (detail.target_id === 'date-and-time') {
      App.api.fetchJson('/api/time-settings').then(function (r) {
        App.time.applySettings(r);
        run('date-and-time', detail, r);
      }, function () { /* the next boot reads the stored zone */ });
      return;
    }
    run(detail.target_id, detail);
  }

  App.gleepglorpFollow.listen('app_settings', onEvent);

  window.App.appSettingsFollow = { register: register, onEvent: onEvent };
})();
