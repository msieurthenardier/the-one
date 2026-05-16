// L8 — command palette scorer.
//
// Pure scoring function. Higher score = better match. 0 = no match.
// Scoring (case-insensitive throughout):
//   +100  query is a prefix of label, OR a prefix of any whitespace-
//         separated token in label.
//   +50   query is a substring of label.
//   +20   query is a substring of (section + keywords).
//   0     no match.
//
// Inputs:
//   q     — string user query (trimmed, possibly empty)
//   item  — { label, section?, keywords? }
(function () {
  'use strict';

  window.App = window.App || {};
  window.App.commandFuzzy = {
    score: function (q, item) {
      if (!q || !item || typeof item.label !== 'string') return 0;
      var query = String(q).toLowerCase().trim();
      if (!query) return 0;

      var label = item.label.toLowerCase();
      var section = (item.section || '').toLowerCase();
      var keywords = (item.keywords || '').toLowerCase();

      // Prefix match — label start OR any whitespace-separated token.
      if (label.indexOf(query) === 0) return 100;
      var tokens = label.split(/\s+/);
      for (var i = 0; i < tokens.length; i++) {
        if (tokens[i].indexOf(query) === 0) return 100;
      }

      if (label.indexOf(query) !== -1) return 50;
      if ((section + ' ' + keywords).indexOf(query) !== -1) return 20;
      return 0;
    }
  };
})();
