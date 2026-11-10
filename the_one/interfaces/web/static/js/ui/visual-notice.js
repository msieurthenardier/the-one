(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.visualNotice (M35 F2 L2, flight DD14): the notice a visual block shows when it
  // cannot draw. It is the composition the chart's error block used to build by hand, lifted so
  // the widget block (leg 4) shares it:
  //
  //   App.ui.visualNotice({tone, headline, reason, source, sourceLabel, testid, detailsTestid})
  //     -> {el}
  //
  // An App.ui.notice (tone 'danger' or 'muted') holding a headline, an optional reason and a
  // closed "Technical details" App.ui.disclosure with an App.ui.codeBlock of the source. Every
  // string is set with textContent, so a source such as "<script>" is shown as text. The
  // notice's testid is `testid`; the disclosure's is `detailsTestid`, defaulting to
  // `testid + '-details'`. Never throws on an empty source.

  App.ui.visualNotice = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var cutOff = opts.tone === 'muted';
    var details = App.ui.disclosure({
      variant: 'plain',
      summary: 'Technical details',
      testid: opts.detailsTestid || (opts.testid ? opts.testid + '-details' : null),
      className: 'ui-visual-notice-details'
    });
    details.body.appendChild(App.ui.codeBlock({
      text: opts.source === undefined || opts.source === null ? '' : String(opts.source),
      maxHeight: 'short',
      label: opts.sourceLabel || 'Source'
    }).el);
    var kids = [util.el('div', { className: 'ui-visual-notice-head', text: opts.headline || '' })];
    if (opts.reason) kids.push(util.el('div', { className: 'ui-visual-notice-reason', text: opts.reason }));
    kids.push(details.el);
    return {
      el: App.ui.notice({
        tone: cutOff ? 'muted' : 'danger',
        body: util.el('div', { className: 'ui-visual-notice' }, kids),
        testid: opts.testid || null
      }).el
    };
  };
})();
