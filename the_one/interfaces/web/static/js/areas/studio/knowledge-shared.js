// App.studio.knowledgeShared — the Knowledge section's shared helpers
// (Mission 31 Flight 3 Leg 02, split out of the former knowledge-section.js).
//
// Pure DOM-builder micro-helpers (no HTML-string sinks anywhere: the
// Mission 17 Flight 1 dynamic-sink freeze in tests/test_ui_guards.py forbids
// new call sites), the folder-path helpers and the response-error reader. Nothing here holds per-mount state.
// Loaded before every other knowledge-* module; they read it as
// `App.studio.knowledgeShared`.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var STATUS_LABELS = ['pending', 'indexing', 'indexed', 'failed'];

  // ── DOM-builder micro-helpers (no innerHTML anywhere below) ──────────

  function _el(tag, opts) {
    var e = document.createElement(tag);
    opts = opts || {};
    if (opts.className) e.className = opts.className;
    if (opts.text !== undefined) e.textContent = opts.text;
    return e;
  }

  function _errorMessageFromResponse(body) {
    var detail;
    try {
      var parsed = JSON.parse(body);
      detail = parsed && parsed.detail;
    } catch (_e) {
      // Non-JSON body — fall through.
    }
    if (Array.isArray(detail)) {
      detail = detail.map(function (d) {
        var loc = (d.loc || []).join('.');
        return loc ? (loc + ': ' + d.msg) : d.msg;
      }).join(' | ');
    }
    return detail;
  }

  // AC-9 (Leg 6)/DD-9: separator-aware containment — a bare
  // `itemPath.startsWith(folderPath)` is wrong at directory boundaries
  // (folder `/data/foo` would falsely claim item `/data/foobar/x.txt`).
  // `sep` is read off the folder path's own separator (the server stores
  // `str(canonical)` in OS-native form with no guaranteed trailing
  // separator). Only ever consulted for items rendered in the trailing
  // "Individual files" panel — a truly-parented item (its own `parent_id`
  // matches a folder id) never needs the guess.
  function _containingFolder(item, folders) {
    for (var i = 0; i < folders.length; i++) {
      var folderPath = folders[i].path;
      var sep = (folderPath.indexOf('\\') !== -1 && folderPath.indexOf('/') === -1) ? '\\' : '/';
      if (item.path_or_url === folderPath || item.path_or_url.indexOf(folderPath + sep) === 0) {
        return folders[i];
      }
    }
    return null;
  }

  // Leg 6 (HAT): a file row INSIDE a folder panel shows its path relative
  // to that folder's own root (`notes/incident.md`), not the absolute path
  // repeated from the summary line above it. L6-D2 deliberately refuses to
  // nest a subdirectory as its own panel (a subdirectory is not a
  // registered item, so a panel would render false parentage), which
  // flattens a tree into one list — the relative path is what puts the
  // subdirectory back on screen without inventing structure.
  //
  // Separator handling mirrors `_containingFolder` above: read `sep` off
  // the folder path itself (the server stores `str(canonical)` in
  // OS-native form), never assume POSIX. Trailing separators are stripped
  // first, so a folder recorded as `/data/` or `C:\` still yields the
  // right prefix (stripping `/` down to `''` leaves prefix `/`, which is
  // correct for a root-registered folder).
  //
  // Returns null — NOT a mangled string — whenever the item is not
  // actually under the folder root. That should not happen (these rows are
  // reached through `parent_id`, not a path guess), but if it ever does the
  // caller falls back to the full path, which is always truthful.
  function _relativeItemPath(itemPath, folderPath) {
    if (!itemPath || !folderPath) return null;
    var sep = (folderPath.indexOf('\\') !== -1 && folderPath.indexOf('/') === -1) ? '\\' : '/';
    var root = folderPath;
    while (root.length > 0 && root.charAt(root.length - 1) === sep) {
      root = root.slice(0, -1);
    }
    var prefix = root + sep;
    if (itemPath.indexOf(prefix) !== 0) return null;
    var rel = itemPath.slice(prefix.length);
    return rel.length > 0 ? rel : null;
  }

  // The last segment of a path ("runbook-01.md"), for a display name. The
  // separator is read the same way as `_containingFolder` does (backslash only
  // when the path has no forward slash); trailing separators are ignored, and
  // a path with no separator, or a bare root, is returned as it came.
  function _baseName(path) {
    if (!path) return '';
    var sep = (path.indexOf('\\') !== -1 && path.indexOf('/') === -1) ? '\\' : '/';
    var p = path;
    while (p.length > 1 && p.charAt(p.length - 1) === sep) p = p.slice(0, -1);
    var i = p.lastIndexOf(sep);
    return (i === -1 || i === p.length - 1) ? p : p.slice(i + 1);
  }

  // "Oct 23, 2026, 8:57 AM": a server ISO timestamp as a person reads it, in
  // the operator zone through App.time (the only module that may call the
  // Date getters). The precise value stays with the caller, in a `title` and
  // `data-indexed-at`. An unparseable value is shown as it came.
  function _formatStamp(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    return App.time.formatDate(d) + ', ' + App.time.formatClock(d);
  }

  window.App.studio.knowledgeShared = {
    formatStamp: _formatStamp,
    STATUS_LABELS: STATUS_LABELS,
    el: _el,
    errorMessageFromResponse: _errorMessageFromResponse,
    containingFolder: _containingFolder,
    relativeItemPath: _relativeItemPath,
    baseName: _baseName
  };
})();
