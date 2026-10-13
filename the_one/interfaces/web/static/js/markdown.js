/* App.markdown — hand-rolled CommonMark-subset markdown library.
 *
 * Public API (all on window.App.markdown):
 *
 *   App.markdown.parse(text)  -> { type: 'document', children: Node[] }
 *   App.markdown.render(text) -> DocumentFragment
 *   App.markdown.NodeType     -> frozen object with all 19 node-type string constants
 *
 * AST node shape:
 *   { type: NodeType_value, children?: Node[], value?: string, meta?: object }
 *
 * Supported subset (v1):
 *   paragraphs, ATX headers (`#`..`######`), fenced code blocks (triple
 *   backtick + optional language tag), blockquotes (single level),
 *   unordered + ordered lists (one nesting level), horizontal rules
 *   (`---` / `***`), emphasis (`*` / `_`), strong (`**` / `__`),
 *   inline code (backtick), links (`[text](url)`; URLs may contain
 *   balanced parens, e.g. Wikipedia citations), soft breaks (single
 *   `\n`), hard breaks (trailing TWO spaces + `\n`),
 *   GFM-style pipe tables (header row + `| --- |` separator + data rows;
 *   optional leading/trailing pipe; per-cell inline markup).
 *
 * Out of subset (v1 non-goals):
 *   column alignment (`:---`, `---:`, `:---:`), footnotes, definition
 *   lists, autolinks (bare URLs), reference-style links, HTML passthrough,
 *   recursive nested emphasis.
 *
 * XSS guarantee:
 *   The renderer constructs DOM via `document.createElement` +
 *   `document.createTextNode` + `setAttribute` + `appendChild` /
 *   `textContent` exclusively. The library never uses inner-HTML
 *   assignments — a grep for the inner-HTML token across markdown.js
 *   returns zero hits.
 *   The trusted icons.js SVG string for the code-block copy button is
 *   parsed via `DOMParser().parseFromString(svg, 'image/svg+xml').documentElement`
 *   to keep the no-inner-HTML invariant intact. Link href values pass
 *   through a scheme allow-list (`http`, `https`, `mailto`, `tel`,
 *   root-relative `/`, fragment `#`); other schemes (notably `javascript:`,
 *   `data:`, `vbscript:`, `file:`) and protocol-relative `//host` URLs are
 *   stripped to `#`. The allow-list is anchored and fail-closed, so
 *   obfuscated schemes (leading whitespace / control chars, mixed case)
 *   also fall through to `#`.
 *
 * Robustness:
 *   parse(undefined) / parse(null) / parse('') -> { type: 'document', children: [] }
 *   render(undefined) / render(null) / render('') -> empty DocumentFragment
 *   These behaviours are deliberate so streaming callers can pass partial
 *   buffers without try/catch ceremony.
 *
 * Nested-emphasis v1 contract (non-recursive):
 *   `***word***` parses to {emphasis > strong > text:'word'} (outer-em-first).
 *   Inside an emphasis or strong run, further emphasis/strong delimiters
 *   are emitted as literal text (the `inEmphasisRun` suppression flag).
 *   So `**bold *with em***` is `<strong>bold *with em*</strong>` — the
 *   inner `*with em*` is literal text. Recursive emphasis (full
 *   CommonMark left/right flanking delimiter run algorithm) is v2 scope.
 */

(function () {
  'use strict';

  var NodeType = Object.freeze({
    DOCUMENT: 'document',
    PARAGRAPH: 'paragraph',
    HEADING: 'heading',
    CODE_BLOCK: 'codeBlock',
    BLOCKQUOTE: 'blockquote',
    LIST: 'list',
    LIST_ITEM: 'listItem',
    HORIZONTAL_RULE: 'horizontalRule',
    TABLE: 'table',
    TABLE_HEAD: 'tableHead',
    TABLE_ROW: 'tableRow',
    TABLE_CELL: 'tableCell',
    TEXT: 'text',
    EMPHASIS: 'emphasis',
    STRONG: 'strong',
    INLINE_CODE: 'inlineCode',
    LINK: 'link',
    SOFT_BREAK: 'softBreak',
    HARD_BREAK: 'hardBreak'
  });

  // ── Helpers ─────────────────────────────────────────────────────────────

  function isBlankLine(line) {
    return /^\s*$/.test(line);
  }

  // Split a GFM table row on pipe characters, stripping leading/trailing
  // pipes and trimming each cell. Returns an array of raw cell strings.
  function splitTableRow(line) {
    var s = line.trim();
    if (s.charAt(0) === '|') s = s.slice(1);
    if (s.charAt(s.length - 1) === '|') s = s.slice(0, s.length - 1);
    return s.split('|').map(function (c) { return c.trim(); });
  }

  // Returns true iff `line` is a GFM separator row (only |, -, :, space).
  function isTableSeparator(line) {
    return /^\|?[\s]*:?-{1,}:?[\s]*(\|[\s]*:?-{1,}:?[\s]*)*\|?$/.test(line.trim());
  }

  function safeHref(href) {
    // Protocol-relative URLs (`//host/...`) inherit the page's scheme and
    // resolve OFF-SITE. A markdown author writing `//host` is not clearly
    // asking for that, so force `#` (M17 F4 L1 hardening decision). Checked
    // first — a leading `/` would otherwise satisfy the relative-path branch
    // of the allow-list below. Leading-whitespace variants (` //host`) are
    // caught too, though they already fail the allow-list independently.
    if (/^\s*\/\//.test(href)) return '#';
    // Allow http:, https:, mailto:, tel:, root-relative (/), fragment (#).
    // FAIL-CLOSED: javascript:, data:, vbscript:, file: — and obfuscated
    // variants (leading whitespace / tab / newline / control chars, mixed
    // case) — do not match the anchored allow-list and fall through to '#'.
    // The `i` flag makes the scheme match case-insensitive; the anchor `^`
    // (with no leading `\s`) means any leading junk defeats the match. This
    // is the single source of truth for URL safety in the renderer; the
    // renderer trusts AST href values.
    if (/^(https?:|mailto:|tel:|\/|#)/i.test(href)) return href;
    return '#';
  }

  // ── Block-level parser ──────────────────────────────────────────────────

  function parseBlocks(lines, startIdx, endIdx) {
    // Walk lines[startIdx..endIdx) and emit block-level nodes.
    var nodes = [];
    var i = startIdx;
    while (i < endIdx) {
      var line = lines[i];

      // Blank line — skip.
      if (isBlankLine(line)) { i++; continue; }

      // ATX heading: 1-6 leading hashes followed by a space.
      var hMatch = /^(#{1,6})\s+(.*)$/.exec(line);
      if (hMatch) {
        var level = hMatch[1].length;
        var content = hMatch[2].replace(/\s+#+\s*$/, ''); // strip optional trailing hashes
        nodes.push({
          type: NodeType.HEADING,
          meta: { level: level },
          children: parseInline(content)
        });
        i++;
        continue;
      }

      // Fenced code block: ```lang
      var fMatch = /^```(.*)$/.exec(line);
      if (fMatch) {
        var langRaw = fMatch[1].trim();
        var lang = langRaw.length > 0 ? langRaw : null;
        var codeLines = [];
        i++;
        while (i < endIdx && !/^```\s*$/.test(lines[i])) {
          codeLines.push(lines[i]);
          i++;
        }
        // Skip the closing fence (if any — be lenient if missing).
        if (i < endIdx) i++;
        nodes.push({
          type: NodeType.CODE_BLOCK,
          meta: { lang: lang },
          value: codeLines.join('\n') + (codeLines.length ? '\n' : '')
        });
        continue;
      }

      // Horizontal rule: --- or *** (3+ chars).
      if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
        nodes.push({ type: NodeType.HORIZONTAL_RULE });
        i++;
        continue;
      }

      // Blockquote: lines starting with > (after optional leading whitespace).
      if (/^\s*>/.test(line)) {
        var quoteLines = [];
        while (i < endIdx && /^\s*>/.test(lines[i])) {
          // Strip the leading > and one optional space.
          quoteLines.push(lines[i].replace(/^\s*>\s?/, ''));
          i++;
        }
        nodes.push({
          type: NodeType.BLOCKQUOTE,
          children: parseBlocks(quoteLines, 0, quoteLines.length)
        });
        continue;
      }

      // List: - / * / + or N.
      var listMatch = /^(\s*)([-*+]|\d+\.)\s+(.*)$/.exec(line);
      if (listMatch) {
        var listInfo = parseList(lines, i, endIdx);
        nodes.push(listInfo.node);
        i = listInfo.next;
        continue;
      }

      // GFM table: header row | separator row | data rows.
      // Requires at least one pipe in the header line and a valid separator
      // on the NEXT line. We peek ahead one line before committing.
      if (line.indexOf('|') !== -1 && i + 1 < endIdx && isTableSeparator(lines[i + 1])) {
        var headerCells = splitTableRow(line);
        i += 2; // skip header + separator
        var headChildren = [];
        for (var hc = 0; hc < headerCells.length; hc++) {
          headChildren.push({ type: NodeType.TABLE_CELL, children: parseInline(headerCells[hc]) });
        }
        var tableRows = [{ type: NodeType.TABLE_HEAD, children: headChildren }];
        while (i < endIdx && !isBlankLine(lines[i]) && lines[i].indexOf('|') !== -1) {
          var dataCells = splitTableRow(lines[i]);
          var rowChildren = [];
          for (var dc = 0; dc < dataCells.length; dc++) {
            rowChildren.push({ type: NodeType.TABLE_CELL, children: parseInline(dataCells[dc]) });
          }
          tableRows.push({ type: NodeType.TABLE_ROW, children: rowChildren });
          i++;
        }
        nodes.push({ type: NodeType.TABLE, children: tableRows });
        continue;
      }

      // Default: paragraph — consume consecutive non-blank, non-block-start lines.
      var paraLines = [line];
      i++;
      while (i < endIdx) {
        var nl = lines[i];
        if (isBlankLine(nl)) break;
        // A new block-start line terminates the paragraph.
        if (/^#{1,6}\s+/.test(nl)) break;
        if (/^```/.test(nl)) break;
        if (/^\s*(-{3,}|\*{3,})\s*$/.test(nl)) break;
        if (/^\s*>/.test(nl)) break;
        if (/^(\s*)([-*+]|\d+\.)\s+/.test(nl)) break;
        // Table header line followed by separator terminates paragraph.
        if (nl.indexOf('|') !== -1 && i + 1 < endIdx && isTableSeparator(lines[i + 1])) break;
        paraLines.push(nl);
        i++;
      }
      nodes.push({
        type: NodeType.PARAGRAPH,
        children: parseInline(paraLines.join('\n'))
      });
    }
    return nodes;
  }

  function parseList(lines, startIdx, endIdx) {
    // Determine the parent list's indent + ordered/unordered + start.
    var first = /^(\s*)([-*+]|\d+\.)\s+(.*)$/.exec(lines[startIdx]);
    var parentIndent = first[1].length;
    var firstMarker = first[2];
    var ordered = /\d+\./.test(firstMarker);
    var startNum = null;
    if (ordered) {
      var sm = /^(\d+)\./.exec(firstMarker);
      startNum = sm ? parseInt(sm[1], 10) : 1;
      if (startNum === 1) startNum = null; // omit start attr when default
    }

    var items = [];
    var i = startIdx;

    while (i < endIdx) {
      var line = lines[i];
      if (isBlankLine(line)) {
        // Blank line — peek ahead. If the next non-blank line is another item
        // at the same parent indent, continue the list; else terminate.
        var j = i + 1;
        while (j < endIdx && isBlankLine(lines[j])) j++;
        if (j >= endIdx) { i = j; break; }
        var peek = /^(\s*)([-*+]|\d+\.)\s+/.exec(lines[j]);
        if (!peek || peek[1].length !== parentIndent) break;
        var peekOrdered = /\d+\./.test(peek[2]);
        if (peekOrdered !== ordered) break;
        i = j;
        continue;
      }

      var m = /^(\s*)([-*+]|\d+\.)\s+(.*)$/.exec(line);
      if (!m || m[1].length !== parentIndent) break;
      var thisOrdered = /\d+\./.test(m[2]);
      if (thisOrdered !== ordered) break;

      // Collect this item: the marker line plus any continuation lines and
      // any nested-list lines (indent > parentIndent + 1).
      var itemLines = [m[3]];
      i++;
      while (i < endIdx) {
        var cl = lines[i];
        if (isBlankLine(cl)) {
          // Lookahead: if next non-blank is a same-level marker or a less-
          // indented line, terminate this item; else accept.
          var k = i + 1;
          while (k < endIdx && isBlankLine(lines[k])) k++;
          if (k >= endIdx) break;
          var nextMarker = /^(\s*)([-*+]|\d+\.)\s+/.exec(lines[k]);
          if (nextMarker && nextMarker[1].length <= parentIndent) break;
          itemLines.push('');
          i = k;
          continue;
        }
        var nm = /^(\s*)([-*+]|\d+\.)\s+/.exec(cl);
        if (nm) {
          if (nm[1].length <= parentIndent) break;
          // Nested list line — keep with its relative indent stripped.
          itemLines.push(cl.substring(parentIndent + 2));
          i++;
          continue;
        }
        // Non-marker, non-blank line. Continuation if indented at least 2 past
        // parent; otherwise it terminates the item.
        var indentMatch = /^(\s*)/.exec(cl);
        if (indentMatch[1].length >= parentIndent + 2) {
          itemLines.push(cl.substring(parentIndent + 2));
          i++;
        } else {
          break;
        }
      }

      items.push({
        type: NodeType.LIST_ITEM,
        children: parseBlocks(itemLines, 0, itemLines.length)
      });
    }

    var node = {
      type: NodeType.LIST,
      meta: { ordered: ordered, start: startNum },
      children: items
    };
    return { node: node, next: i };
  }

  // ── Inline parser ───────────────────────────────────────────────────────

  function parseInline(text) {
    return scanInline(text, false);
  }

  function scanInline(text, inEmphasisRun) {
    // Walk character-by-character; emit text/emphasis/strong/inlineCode/
    // link/softBreak/hardBreak nodes. When inEmphasisRun is true, emphasis
    // and strong delimiters are NOT recognised — they fall through to text.
    var nodes = [];
    var buf = '';
    var i = 0;
    var n = text.length;

    function flushText() {
      if (buf.length > 0) {
        nodes.push({ type: NodeType.TEXT, value: buf });
        buf = '';
      }
    }

    while (i < n) {
      var ch = text.charAt(i);

      // Hard break: two-or-more trailing spaces + \n.
      if (ch === ' ') {
        var sp = i;
        while (sp < n && text.charAt(sp) === ' ') sp++;
        if (sp - i >= 2 && sp < n && text.charAt(sp) === '\n') {
          flushText();
          nodes.push({ type: NodeType.HARD_BREAK });
          i = sp + 1;
          continue;
        }
        // Otherwise — it's just a space (single trailing space + \n is
        // handled by the \n branch below as a soft break).
        buf += ' ';
        i++;
        continue;
      }

      // Soft break: a literal newline (no preceding two-space marker).
      if (ch === '\n') {
        flushText();
        nodes.push({ type: NodeType.SOFT_BREAK });
        i++;
        continue;
      }

      // Inline code: backtick run.
      if (ch === '`') {
        var end = text.indexOf('`', i + 1);
        if (end !== -1) {
          flushText();
          nodes.push({ type: NodeType.INLINE_CODE, value: text.substring(i + 1, end) });
          i = end + 1;
          continue;
        }
        // No closing backtick — treat as literal.
        buf += ch;
        i++;
        continue;
      }

      // Link: [text](url).
      if (ch === '[') {
        var linkEnd = parseLink(text, i);
        if (linkEnd !== null) {
          flushText();
          nodes.push(linkEnd.node);
          i = linkEnd.next;
          continue;
        }
        // Malformed — treat the [ as literal.
        buf += ch;
        i++;
        continue;
      }

      // Emphasis / strong delimiters — only when NOT inside an emphasis run.
      if (!inEmphasisRun && (ch === '*' || ch === '_')) {
        var runStart = i;
        var runChar = ch;
        while (i < n && text.charAt(i) === runChar) i++;
        var runLen = i - runStart;

        // For underscore, treat mid-word as literal (CommonMark "intraword
        // emphasis" rule for `_`). Asterisk allows mid-word.
        if (runChar === '_') {
          var prevCh = runStart > 0 ? text.charAt(runStart - 1) : '';
          var nextCh = i < n ? text.charAt(i) : '';
          if (/\w/.test(prevCh) && /\w/.test(nextCh)) {
            buf += text.substring(runStart, i);
            continue;
          }
        }

        // Triple delimiter: open both emphasis and strong (length-3 case).
        if (runLen >= 3) {
          var tripleEnd = findClosingDelim(text, i, runChar, 3);
          if (tripleEnd !== null) {
            flushText();
            var inner3 = text.substring(i, tripleEnd);
            var innerNodes3 = scanInline(inner3, true);
            if (runLen > 3) {
              nodes.push({
                type: NodeType.TEXT,
                value: runChar.repeat(runLen - 3)
              });
            }
            nodes.push({
              type: NodeType.EMPHASIS,
              children: [{ type: NodeType.STRONG, children: innerNodes3 }]
            });
            i = tripleEnd + 3;
            continue;
          }
          // No closing triple — fall through and try double, then single.
        }

        if (runLen >= 2) {
          var doubleEnd = findClosingDelim(text, i, runChar, 2);
          if (doubleEnd !== null) {
            flushText();
            var inner2 = text.substring(i, doubleEnd);
            var innerNodes2 = scanInline(inner2, true);
            if (runLen > 2) {
              nodes.push({
                type: NodeType.TEXT,
                value: runChar.repeat(runLen - 2)
              });
            }
            nodes.push({
              type: NodeType.STRONG,
              children: innerNodes2
            });
            i = doubleEnd + 2;
            continue;
          }
        }

        if (runLen >= 1) {
          var singleEnd = findClosingDelim(text, i, runChar, 1);
          if (singleEnd !== null) {
            flushText();
            var inner1 = text.substring(i, singleEnd);
            var innerNodes1 = scanInline(inner1, true);
            if (runLen > 1) {
              nodes.push({
                type: NodeType.TEXT,
                value: runChar.repeat(runLen - 1)
              });
            }
            nodes.push({
              type: NodeType.EMPHASIS,
              children: innerNodes1
            });
            i = singleEnd + 1;
            continue;
          }
        }

        // No matching closer — emit the entire run as literal text.
        buf += text.substring(runStart, i);
        continue;
      }

      // Default — accumulate as plain text.
      buf += ch;
      i++;
    }

    flushText();
    return nodes;
  }

  function findClosingDelim(text, startIdx, delimChar, delimLen) {
    // Find the next run of `delimChar` of length >= delimLen. Skips over
    // inline code spans so delimiters inside them don't match. Returns
    // the index such that consuming `delimLen` chars from that index lands
    // at the END of the closing run — for an exact-length match this is
    // `runStart`; for an overlong run (e.g. `***` closing a `**` opener)
    // this is `runStart + (runLen - delimLen)` so the extra leading
    // delimiters fall INTO the inner span as literal content (matches the
    // "**bold *with em***" v1 contract). Returns null if none found.
    var i = startIdx;
    var n = text.length;
    while (i < n) {
      if (text.charAt(i) === delimChar) {
        var runLen = 0;
        var runStart = i;
        while (i < n && text.charAt(i) === delimChar) { runLen++; i++; }
        if (runLen >= delimLen) {
          return runStart + (runLen - delimLen);
        }
        continue;
      }
      if (text.charAt(i) === '`') {
        var cend = text.indexOf('`', i + 1);
        if (cend === -1) { i++; continue; }
        i = cend + 1;
        continue;
      }
      i++;
    }
    return null;
  }

  function parseLink(text, startIdx) {
    // Parse `[text](url)` starting at the `[` position. Returns
    // { node, next } on success or null on malformed input.
    var n = text.length;
    var i = startIdx + 1; // past the [
    var depth = 1;
    var labelEnd = -1;
    while (i < n) {
      var c = text.charAt(i);
      if (c === '\\' && i + 1 < n) { i += 2; continue; }
      if (c === '[') { depth++; i++; continue; }
      if (c === ']') {
        depth--;
        if (depth === 0) { labelEnd = i; break; }
        i++;
        continue;
      }
      i++;
    }
    if (labelEnd === -1) return null;
    if (labelEnd + 1 >= n || text.charAt(labelEnd + 1) !== '(') return null;

    var labelText = text.substring(startIdx + 1, labelEnd);

    // Parse URL with paren-balance counter — `)` only terminates when
    // balanced.
    var u = labelEnd + 2;
    var pdepth = 0;
    var urlEnd = -1;
    while (u < n) {
      var uc = text.charAt(u);
      if (uc === '\\' && u + 1 < n) { u += 2; continue; }
      if (uc === '(') { pdepth++; u++; continue; }
      if (uc === ')') {
        if (pdepth === 0) { urlEnd = u; break; }
        pdepth--;
        u++;
        continue;
      }
      u++;
    }
    if (urlEnd === -1) return null;

    var rawUrl = text.substring(labelEnd + 2, urlEnd);
    var href = safeHref(rawUrl);

    return {
      node: {
        type: NodeType.LINK,
        meta: { href: href },
        children: scanInline(labelText, false)
      },
      next: urlEnd + 1
    };
  }

  // ── Top-level parse() ───────────────────────────────────────────────────

  function parse(text) {
    if (text === null || text === undefined) text = '';
    var src = String(text);
    if (src.length === 0) {
      return { type: NodeType.DOCUMENT, children: [] };
    }
    src = src.replace(/\r\n?/g, '\n');
    var lines = src.split('\n');
    if (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();
    var children = parseBlocks(lines, 0, lines.length);
    return { type: NodeType.DOCUMENT, children: children };
  }

  // ── Renderer ────────────────────────────────────────────────────────────

  function injectIcon(parent, name) {
    // Trusted icons.js SVG strings are parsed via DOMParser to avoid
    // inner-HTML assignments. The resulting documentElement is appended
    // in place of the parent's existing children — keeping the
    // markdown-library no-inner-HTML invariant intact.
    var svgString = (window.App && window.App.icon) ? window.App.icon(name) : '';
    if (!svgString) return;
    var doc = new DOMParser().parseFromString(svgString, 'image/svg+xml');
    if (doc && doc.documentElement && doc.documentElement.nodeName.toLowerCase() === 'svg') {
      parent.appendChild(doc.documentElement);
    }
  }

  function renderNodes(nodes, parent) {
    for (var idx = 0; idx < nodes.length; idx++) {
      var node = nodes[idx];
      var el;
      switch (node.type) {
        case NodeType.PARAGRAPH:
          el = document.createElement('p');
          renderNodes(node.children || [], el);
          parent.appendChild(el);
          break;

        case NodeType.HEADING:
          var lvl = (node.meta && node.meta.level) || 1;
          el = document.createElement('h' + lvl);
          renderNodes(node.children || [], el);
          parent.appendChild(el);
          break;

        case NodeType.CODE_BLOCK:
          parent.appendChild(renderCodeBlock(node));
          break;

        case NodeType.BLOCKQUOTE:
          el = document.createElement('blockquote');
          renderNodes(node.children || [], el);
          parent.appendChild(el);
          break;

        case NodeType.LIST:
          var ordered = node.meta && node.meta.ordered;
          el = document.createElement(ordered ? 'ol' : 'ul');
          if (ordered && node.meta && node.meta.start != null) {
            el.setAttribute('start', String(node.meta.start));
          }
          renderNodes(node.children || [], el);
          parent.appendChild(el);
          break;

        case NodeType.LIST_ITEM:
          el = document.createElement('li');
          // If the list-item contains a single paragraph, inline its
          // children directly into the <li> (tight-list rendering).
          // Otherwise render block children as-is.
          var kids = node.children || [];
          if (kids.length === 1 && kids[0].type === NodeType.PARAGRAPH) {
            renderNodes(kids[0].children || [], el);
          } else {
            renderNodes(kids, el);
          }
          parent.appendChild(el);
          break;

        case NodeType.HORIZONTAL_RULE:
          parent.appendChild(document.createElement('hr'));
          break;

        case NodeType.TABLE:
          el = document.createElement('table');
          // First child is always TABLE_HEAD; rest are TABLE_ROW.
          var kids = node.children || [];
          if (kids.length > 0 && kids[0].type === NodeType.TABLE_HEAD) {
            var thead = document.createElement('thead');
            var headerRow = document.createElement('tr');
            var headCells = kids[0].children || [];
            for (var hIdx = 0; hIdx < headCells.length; hIdx++) {
              var th = document.createElement('th');
              renderNodes(headCells[hIdx].children || [], th);
              headerRow.appendChild(th);
            }
            thead.appendChild(headerRow);
            el.appendChild(thead);
          }
          var tbody = document.createElement('tbody');
          for (var rIdx = 1; rIdx < kids.length; rIdx++) {
            if (kids[rIdx].type !== NodeType.TABLE_ROW) continue;
            var tr = document.createElement('tr');
            var rowCells = kids[rIdx].children || [];
            for (var cIdx = 0; cIdx < rowCells.length; cIdx++) {
              var td = document.createElement('td');
              renderNodes(rowCells[cIdx].children || [], td);
              tr.appendChild(td);
            }
            tbody.appendChild(tr);
          }
          el.appendChild(tbody);
          parent.appendChild(el);
          break;

        case NodeType.TEXT:
          parent.appendChild(document.createTextNode(node.value));
          break;

        case NodeType.EMPHASIS:
          el = document.createElement('em');
          renderNodes(node.children || [], el);
          parent.appendChild(el);
          break;

        case NodeType.STRONG:
          el = document.createElement('strong');
          renderNodes(node.children || [], el);
          parent.appendChild(el);
          break;

        case NodeType.INLINE_CODE:
          el = document.createElement('code');
          el.textContent = node.value;
          parent.appendChild(el);
          break;

        case NodeType.LINK:
          el = document.createElement('a');
          var linkHref = (node.meta && node.meta.href) || '#';
          el.setAttribute('href', linkHref);
          el.setAttribute('rel', 'noopener noreferrer');
          // Absolute http(s) links open outside the app: a new tab in a
          // browser, the system browser in the pywebview desktop shell.
          if (/^https?:/i.test(linkHref)) el.setAttribute('target', '_blank');
          renderNodes(node.children || [], el);
          parent.appendChild(el);
          break;

        case NodeType.SOFT_BREAK:
          parent.appendChild(document.createTextNode(' '));
          break;

        case NodeType.HARD_BREAK:
          parent.appendChild(document.createElement('br'));
          break;

        default:
          // Unknown node type — silently skip.
          break;
      }
    }
  }

  function renderCodeBlock(node) {
    var wrap = document.createElement('div');
    wrap.className = 'markdown-code-wrap';
    var pre = document.createElement('pre');
    var code = document.createElement('code');
    if (node.meta && node.meta.lang) {
      code.setAttribute('class', 'language-' + node.meta.lang);
    }
    code.textContent = node.value || '';
    pre.appendChild(code);
    wrap.appendChild(pre);

    var btn = document.createElement('button');
    btn.setAttribute('class', 'markdown-copy-btn');
    btn.setAttribute('aria-label', 'Copy code');
    btn.setAttribute('type', 'button');
    injectIcon(btn, 'copy');
    wrap.appendChild(btn);

    btn.addEventListener('click', function () {
      var clip = (typeof navigator !== 'undefined') && navigator.clipboard;
      if (!clip || typeof clip.writeText !== 'function') {
        if (window.App && window.App.showFlash) {
          window.App.showFlash(wrap, 'Copy failed', true);
        }
        return;
      }
      clip.writeText(code.textContent).then(function () {
        if (window.App && window.App.showFlash) {
          window.App.showFlash(wrap, 'Copied!');
        }
      }).catch(function () {
        if (window.App && window.App.showFlash) {
          window.App.showFlash(wrap, 'Copy failed', true);
        }
      });
    });

    return wrap;
  }

  function render(text) {
    var frag = document.createDocumentFragment();
    if (text === null || text === undefined || String(text).length === 0) {
      return frag;
    }
    var ast = parse(text);
    renderNodes(ast.children || [], frag);
    return frag;
  }

  // ── Public API ──────────────────────────────────────────────────────────

  window.App = window.App || {};
  window.App.markdown = {
    NodeType: NodeType,
    parse: parse,
    render: render
  };
})();
