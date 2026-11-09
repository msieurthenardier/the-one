// App.chat.chartStream -- where a streaming reply may be committed as markdown, and whether the
// tail is inside an open chart block (M35 F1 L2, flight DD8 and DD10). Pure logic: no DOM, no
// transcript state; transcript.js owns the bubble, the placeholder and the pacing.
//
// scanTail(text) proposes candidate commit offsets of three kinds, in one pass over the COMPLETE
// (newline-terminated) lines:
//   1. blank   the end of a blank line outside a fence;
//   2. close   the end of a newline-terminated top-level (column 0) closing-fence line;
//   3. chart   the start of a complete top-level (column 0) ```chart opener line.
// and reports `open`, the offset of a top-level chart opener the tail is still inside.
// The scanner's nested opener is permissive (indent then ```); its closer is exactly
// ^\s{0,n}```\s*$ for an opener indented n, so ```python inside an open fence is content, as
// for the parser. The scanner and the parser can disagree about nested fences (a fence in a
// list item ended by a column-0 line); parse confirmation is the authority.
//
// create() returns the confirming planner: plan(tail) tries the furthest candidate, then at
// most two earlier ones, and accepts the first whose prefix parses with no unclosed code block
// at any depth. A per-generation cache keeps the cost linear (verdict per offset, a poisoned
// prefix, an empty-fragment mark). The caller resets it after a non-empty commit, a stream
// reset and a finalize.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var KIND_BLANK = 'blank';
  var KIND_CLOSE = 'close';
  var KIND_CHART = 'chart';
  var MAX_TRIES = 3;

  function scanTail(text) {
    var lines = String(text).split('\n');
    var candidates = [];
    var fence = null; // {indent, top, chart, start}
    var pos = 0;
    // The last piece has no newline yet (or is the empty remainder): it is not a line.
    for (var i = 0; i < lines.length - 1; i++) {
      var line = lines[i];
      var start = pos;
      pos += line.length + 1;
      if (fence) {
        var closer = new RegExp('^\\s{0,' + fence.indent + '}```\\s*$');
        if (closer.test(line)) {
          if (fence.top) candidates.push({ offset: pos, kind: KIND_CLOSE });
          fence = null;
        }
        continue;
      }
      var om = /^(\s*)```(.*)$/.exec(line);
      if (om) {
        var top = om[1].length === 0;
        var lang = om[2].trim().split(/\s+/)[0];
        var chart = top && lang === 'chart';
        if (chart) {
          // A blank line right before the opener ends at this same offset: one candidate.
          var lastC = candidates[candidates.length - 1];
          if (lastC && lastC.offset === start) lastC.kind = KIND_CHART;
          else candidates.push({ offset: start, kind: KIND_CHART });
        }
        fence = { indent: om[1].length, top: top, chart: chart, start: start };
        continue;
      }
      if (line === '') candidates.push({ offset: pos, kind: KIND_BLANK });
    }
    var open = fence && fence.top && fence.chart ? { offset: fence.start } : null;
    return { candidates: candidates, open: open };
  }

  // True when the parse tree holds a code block whose fence never closed, at any depth.
  function hasUnclosed(node) {
    if (!node) return false;
    if (node.type === window.App.markdown.NodeType.CODE_BLOCK && node.meta && node.meta.closed === false) {
      return true;
    }
    var kids = node.children;
    if (kids) {
      for (var i = 0; i < kids.length; i++) if (hasUnclosed(kids[i])) return true;
    }
    return false;
  }

  function create() {
    var verdict = Object.create(null); // offset -> true | false | 'empty'
    var poisonAt = Infinity; // a prefix ending here held an unclosed block: every later one does
    var parses = 0;

    function check(offset, kind, tail) {
      var known = verdict[offset];
      if (known !== undefined) return known;
      var ok;
      if (offset === 0 && kind === KIND_CHART) {
        ok = true; // an empty prefix needs no parse
      } else if (offset >= poisonAt) {
        ok = false;
      } else {
        parses++;
        ok = !hasUnclosed(window.App.markdown.parse(tail.slice(0, offset)));
        if (!ok && offset < poisonAt) poisonAt = offset;
      }
      verdict[offset] = ok;
      return ok;
    }

    return {
      // plan(tail) -> {boundary, open}. boundary: the offset to commit (0: nothing). open: the
      // offset of an open top-level chart opener whose prefix was accepted, else null; both in
      // the coordinates of the tail passed in.
      plan: function (tail) {
        var scan = scanTail(tail);
        var cands = scan.candidates;
        var boundary = 0;
        var accepted = null;
        var tries = 0;
        for (var i = cands.length - 1; i >= 0 && tries < MAX_TRIES; i--, tries++) {
          var c = cands[i];
          if (check(c.offset, c.kind, tail)) {
            accepted = c;
            if (verdict[c.offset] !== 'empty') boundary = c.offset;
            break;
          }
        }
        var open = null;
        if (scan.open && verdict[scan.open.offset] !== undefined && verdict[scan.open.offset] !== false) {
          open = scan.open.offset;
        }
        return { boundary: boundary, open: open, accepted: accepted !== null };
      },
      // The commit at `offset` rendered an empty fragment (whitespace): accepted, nothing to cut.
      markEmpty: function (offset) { verdict[offset] = 'empty'; },
      reset: function () { verdict = Object.create(null); poisonAt = Infinity; },
      parseCount: function () { return parses; }
    };
  }

  // The chart type named at the start of an open block's body (after the opener line), once the
  // first key and its value are fully streamed; null before that.
  function typeOf(blockText) {
    var nl = blockText.indexOf('\n');
    if (nl < 0) return null;
    var m = /^\s*\{\s*"type"\s*:\s*"(bar|line|area|scatter|pie|sparkline)"/.exec(blockText.slice(nl + 1));
    return m ? m[1] : null;
  }

  window.App.chat.chartStream = {
    scanTail: scanTail,
    create: create,
    typeOf: typeOf
  };
})();
