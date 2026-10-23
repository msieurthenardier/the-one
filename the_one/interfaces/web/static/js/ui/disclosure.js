(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.disclosure(opts) -> {el, summary, summaryText, body, actions,
  // setOpen(bool), isOpen(), setSummary(textOrNode), destroy()} (M31 F3 L03a,
  // flight DD4). A native <details>/<summary> with two looks.
  //   variant: 'bordered' | 'plain' (required, no default; anything else throws).
  //     bordered is the folder-panel / MCP tool-tile look; plain is the quiet
  //     top-border look (the self-configuration history).
  //   summary (string or node), meta [non-interactive nodes after the text; part
  //   of the summary's accessible name], actions [interactive nodes after meta,
  //   before the chevron; NOT part of the summary's name], open, onToggle(open),
  //   onFirstOpen(body) (once, the first time it opens; with open:true it runs
  //   synchronously at creation and onToggle does not fire for that initial
  //   state), chevron (default true for bordered, false for plain), testid,
  //   summaryTestid, summaryTextTestid, dataset, className.
  //   The plain variant takes no meta, actions or chevron:true (it throws) and
  //   keeps the native marker; it carries no margin (the caller owns spacing).
  //   The summary text always carries data-confirm-title, so App.ui.confirm armed
  //   on ctl.summary swaps and restores it. setSummary replaces only the text and
  //   is a no-op returning false while the summary is armed (.confirm-delete).
  //   Nothing here rebuilds el or summary: a caller rebuilds only inside body.
  App.ui.disclosure = function (opts) {
    opts = opts || {};
    var variant = opts.variant;
    if (variant !== 'bordered' && variant !== 'plain') {
      throw new Error('App.ui.disclosure: unknown variant "' + variant + '"');
    }
    var meta = opts.meta || [];
    var actionNodes = opts.actions || [];
    if (variant === 'plain' && (meta.length || actionNodes.length || opts.chevron === true)) {
      throw new Error('App.ui.disclosure: the plain variant takes no meta, actions or chevron');
    }
    var util = App.ui.util;
    var showChevron = opts.chevron === undefined ? variant === 'bordered' : !!opts.chevron;

    var el = util.el('details', {
      className: 'ui-disclosure ui-disclosure--' + variant + (opts.className ? ' ' + opts.className : ''),
      'data-testid': opts.testid
    });
    util.applyDataset(el, opts.dataset);

    var summary = util.el('summary', {
      className: 'ui-disclosure-summary',
      'data-testid': opts.summaryTestid
    });
    var summaryText = util.el('span', {
      className: 'ui-disclosure-text',
      id: util.uid('disclosure-text'),
      'data-confirm-title': '',
      'data-testid': opts.summaryTextTestid
    });
    summary.appendChild(summaryText);

    var labelIds = [summaryText.id];
    var i;
    for (i = 0; i < meta.length; i++) {
      if (!meta[i].id) meta[i].id = util.uid('disclosure-meta');
      labelIds.push(meta[i].id);
      summary.appendChild(meta[i]);
    }
    summary.setAttribute('aria-labelledby', labelIds.join(' '));

    var actionsEl = null;
    if (actionNodes.length) {
      actionsEl = util.el('span', { className: 'ui-disclosure-actions' });
      for (i = 0; i < actionNodes.length; i++) actionsEl.appendChild(actionNodes[i]);
      summary.appendChild(actionsEl);
    }
    if (showChevron) {
      summary.appendChild(util.el('span', {
        className: 'ui-disclosure-chevron',
        'aria-hidden': 'true',
        text: '▸'
      }));
    }
    el.appendChild(summary);

    var body = util.el('div', { className: 'ui-disclosure-body' });
    el.appendChild(body);

    var onToggle = opts.onToggle;
    var onFirstOpen = opts.onFirstOpen;
    var opened = false;
    var destroyed = false;
    var lastReported = !!opts.open;

    function renderSummary(value) {
      summaryText.textContent = '';
      if (value === null || value === undefined) return;
      if (typeof value === 'string' || typeof value === 'number') {
        summaryText.textContent = String(value);
      } else {
        summaryText.appendChild(value);
      }
    }
    renderSummary(opts.summary);

    function markOpened() {
      if (opened || destroyed) return;
      opened = true;
      var cb = onFirstOpen;
      onFirstOpen = null;
      if (cb) cb(body);
    }

    function handleToggle() {
      if (destroyed) return;
      var now = el.open;
      if (now) markOpened();
      if (now === lastReported) return;
      lastReported = now;
      if (onToggle) onToggle(now);
    }
    el.addEventListener('toggle', handleToggle);

    if (opts.open) {
      el.open = true;
      markOpened();
    }

    return {
      el: el,
      summary: summary,
      summaryText: summaryText,
      body: body,
      actions: actionsEl,
      setOpen: function (open) {
        if (destroyed) return;
        el.open = !!open;
        if (el.open) markOpened();
      },
      isOpen: function () { return el.open; },
      setSummary: function (value) {
        if (destroyed) return false;
        if (summary.classList.contains('confirm-delete')) return false;
        renderSummary(value);
        return true;
      },
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        el.removeEventListener('toggle', handleToggle);
        onToggle = null;
        onFirstOpen = null;
      }
    };
  };
})();
