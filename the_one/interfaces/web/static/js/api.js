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
//
//   The thrown Error also carries (M31 F4 L03a, additive; .message is unchanged):
//     .status  number   the HTTP status
//     .detail  any      the raw parsed `detail` (string, array or undefined)
//     .body    string   the raw response text
//
//   App.api.fieldErrors(err, names) -> {fields: {name: msg}, rest: [msg], text}
//     Maps a 422 `detail` array onto field names (see its comment below).
//   App.api.humanizeMessage(msg)   -> plain sentence for a Pydantic v2 `msg`.

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
          var rawDetail = detail;
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
          var err = new Error(detail || 'Request failed');
          err.status = r.status;
          err.detail = rawDetail;
          err.body = body;
          throw err;
        });
      }
      return r.json();
    });
  }

  var HUMANISERS = [
    [/^Input should be greater than or equal to (-?[\d.]+)/, 'Must be $1 or more'],
    [/^Input should be greater than (-?[\d.]+)/, 'Must be more than $1'],
    [/^Input should be less than or equal to (-?[\d.]+)/, 'Must be at most $1'],
    [/^Input should be less than (-?[\d.]+)/, 'Must be less than $1'],
    [/^Input should be a valid integer.*$/, 'Must be a whole number'],
    [/^Input should be a valid number.*$/, 'Must be a number']
  ];

  function humanizeMessage(msg) {
    var s = String(msg == null ? '' : msg);
    if (s.indexOf('Value error, ') === 0) return s.slice('Value error, '.length);
    for (var i = 0; i < HUMANISERS.length; i++) {
      if (HUMANISERS[i][0].test(s)) return s.replace(HUMANISERS[i][0], HUMANISERS[i][1]);
    }
    return s;
  }

  function sentence(t) {
    t = String(t).trim();
    return /[.!?]$/.test(t) ? t : t + '.';
  }

  // fieldErrors(err, names) maps a fetchJson error onto field names.  Each
  // detail item's `loc` loses a leading "body" segment, then the FIRST segment
  // whose String() equals a name in `names` (exact, never a substring) picks
  // the field; the message is humanised.  Everything else goes to `rest`
  // (humanised, no loc prefix).  `text` is the editor-level text: `rest`
  // sentences joined by a space (each ends with a period), or, with no rest
  // and no matched field, err.message.  Never throws.
  function fieldErrors(err, names) {
    var out = { fields: {}, rest: [], text: '' };
    if (!err || typeof err.status !== 'number') {
      out.text = (err && err.message) || String(err || '');
      return out;
    }
    names = names || [];
    var items = Array.isArray(err.detail) ? err.detail :
      (typeof err.detail === 'string' && err.detail ? [{ msg: err.detail, loc: [], plain: true }] : []);
    items.forEach(function (d) {
      if (!d || typeof d !== 'object' || d.msg === undefined) return;
      var msg = d.plain ? d.msg : humanizeMessage(d.msg);
      var loc = Array.isArray(d.loc) ? d.loc.slice() : [];
      if (loc.length && String(loc[0]) === 'body') loc.shift();
      var hit = null;
      for (var i = 0; i < loc.length && hit === null; i++) {
        if (names.indexOf(String(loc[i])) !== -1) hit = String(loc[i]);
      }
      if (hit !== null) {
        if (!(hit in out.fields)) out.fields[hit] = msg;
      } else {
        out.rest.push(msg);
      }
    });
    if (out.rest.length) {
      out.text = out.rest.map(sentence).join(' ');
    } else if (!Object.keys(out.fields).length) {
      out.text = err.message || '';
    }
    return out;
  }

  window.App = window.App || {};
  window.App.api = window.App.api || {};
  window.App.api.fetchJson = fetchJson;
  window.App.api.fieldErrors = fieldErrors;
  window.App.api.humanizeMessage = humanizeMessage;
})();
