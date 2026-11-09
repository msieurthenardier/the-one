(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.chart.placeholder({type, testid, sourceTestid}) ->
  //   {el, setType(type), setSource(text), destroy()}   (M35 F1 L1, flight DD8)
  //
  // The card that holds a chart's place while its block streams: "Rendering chart" (or
  // "Rendering {type} chart" once the type is known) with the thinking dots, a glimmering
  // title bar and a glimmering plot area shaped by the type (a generic block; bars; a line
  // for line, area and scatter; a disc for pie; a short row for sparkline), and a "Show
  // source" disclosure whose code well setSource() updates in place. Under reduced motion
  // there is no glimmer (a static fill) and the dots show their static text.
  //
  //   type         the chart type, if already known (anything else is the generic shape)
  //   testid       placed on the root; the source disclosure is <testid>-source unless
  //                sourceTestid says otherwise
  // setType(t) swaps the label and the shape in place, once per real change; an unknown
  // type or null is the generic shape. destroy() stops the dots and removes nothing the
  // caller owns (the caller removes el).
  var SHAPE_OF = {
    bar: 'bars',
    line: 'line',
    area: 'line',
    scatter: 'line',
    pie: 'disc',
    sparkline: 'row'
  };
  var BAR_COUNT = 6;
  var SEGMENT_COUNT = 5;

  function shapeFor(type) {
    if (typeof type === 'string' && Object.prototype.hasOwnProperty.call(SHAPE_OF, type)) {
      return SHAPE_OF[type];
    }
    return 'generic';
  }

  function buildShape(shape) {
    var util = App.ui.util;
    var kids = [];
    var i;
    var cls;
    if (shape === 'bars') {
      for (i = 0; i < BAR_COUNT; i++) kids.push(util.el('span', { className: 'ui-chart-ph-bar ui-chart-ph-glimmer' }));
      cls = 'ui-chart-ph-shape ui-chart-ph-shape--bars';
    } else if (shape === 'line') {
      for (i = 0; i < SEGMENT_COUNT; i++) kids.push(util.el('span', { className: 'ui-chart-ph-seg ui-chart-ph-glimmer' }));
      cls = 'ui-chart-ph-shape ui-chart-ph-shape--line';
    } else if (shape === 'disc') {
      kids.push(util.el('span', { className: 'ui-chart-ph-disc ui-chart-ph-glimmer' }));
      cls = 'ui-chart-ph-shape ui-chart-ph-shape--disc';
    } else if (shape === 'row') {
      kids.push(util.el('span', { className: 'ui-chart-ph-row ui-chart-ph-glimmer' }));
      cls = 'ui-chart-ph-shape ui-chart-ph-shape--row';
    } else {
      kids.push(util.el('span', { className: 'ui-chart-ph-block ui-chart-ph-glimmer' }));
      cls = 'ui-chart-ph-shape ui-chart-ph-shape--generic';
    }
    return util.el('div', { className: cls, 'data-shape': shape, 'aria-hidden': 'true' }, kids);
  }

  App.ui.chart.placeholder = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var type = null;
    var shape = null;
    var destroyed = false;

    var dots = App.ui.thinking.dots();
    var label = util.el('span', { className: 'ui-chart-ph-label', text: 'Rendering chart' });
    var head = util.el('div', { className: 'ui-chart-ph-head' }, [label, dots.el]);
    var title = util.el('div', { className: 'ui-chart-ph-title ui-chart-ph-glimmer', 'aria-hidden': 'true' });
    var plotSlot = util.el('div', { className: 'ui-chart-ph-plot' });

    var disclosure = App.ui.disclosure({
      variant: 'plain',
      summary: 'Show source',
      testid: opts.sourceTestid || (opts.testid ? opts.testid + '-source' : null)
    });
    var code = App.ui.codeBlock({ text: '', maxHeight: 'short', label: 'Chart source' });
    disclosure.body.appendChild(code.el);

    var root = util.el('div', { className: 'ui-chart-placeholder' }, [head, title, plotSlot, disclosure.el]);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    function setType(next) {
      if (destroyed) return;
      var known = typeof next === 'string' && Object.prototype.hasOwnProperty.call(SHAPE_OF, next);
      var nextType = known ? next : null;
      var nextShape = shapeFor(nextType);
      if (nextShape !== shape) {
        shape = nextShape;
        plotSlot.textContent = '';
        plotSlot.appendChild(buildShape(shape));
      }
      if (nextType !== type || label.textContent === '') {
        type = nextType;
        label.textContent = type ? 'Rendering ' + type + ' chart' : 'Rendering chart';
        root.setAttribute('data-type', type || '');
      }
    }
    setType(opts.type);

    return {
      el: root,
      setType: setType,
      setSource: function (text) {
        if (!destroyed) code.set(text === undefined || text === null ? '' : String(text));
      },
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        dots.destroy();
        disclosure.destroy();
      }
    };
  };
})();
