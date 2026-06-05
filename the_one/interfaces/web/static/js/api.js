// App.api — shared fetch helpers (F6 leg 02).
//
// Public API (on window.App.api):
//
//   App.api.fetchJson(url, opts)
//     Wraps fetch(url, opts) with centralized ok-check, 422-detail
//     flattening, snippet fallback, and consistent throw.  On success
//     returns the parsed JSON body.  On HTTP error throws an Error whose
//     .message is the best human-readable description available from the
//     response body.
//
// Error-message resolution order:
//   1. parsed.detail (string) — used verbatim
//   2. parsed.detail (array of {loc, msg}) — flattened to "loc: msg | …"
//   3. "Server error {status} {statusText}: {snippet}" where snippet is
//      the first 500 characters of the raw body
//   4. "Request failed" (last-resort fallback if all of the above are empty)

(function () {
  'use strict';

  function fetchJson(url, opts) {
    return fetch(url, opts).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (body) {
          var detail;
          try {
            var parsed = JSON.parse(body);
            detail = parsed && parsed.detail;
          } catch (_) { /* non-JSON body */ }
          if (Array.isArray(detail)) {
            detail = detail.map(function (d) {
              var loc = (d.loc || []).join('.');
              return loc ? (loc + ': ' + d.msg) : d.msg;
            }).join(' | ');
          }
          if (!detail) {
            var snippet = (body || '').trim().slice(0, 500);
            detail = 'Server error ' + r.status + ' ' + r.statusText +
                     (snippet ? ': ' + snippet : '');
          }
          throw new Error(detail || 'Request failed');
        });
      }
      return r.json();
    });
  }

  window.App = window.App || {};
  window.App.api = window.App.api || {};
  window.App.api.fetchJson = fetchJson;
})();
