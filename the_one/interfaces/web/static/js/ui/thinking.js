(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var FRAMES = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'];
  var TONE_CLASS = {
    assistant: 'ui-message--assistant',
    system: 'ui-message--system'
  };

  // App.ui.thinking(opts) -> {el, settle(text), destroy()}  (M31 F6 L04, DD4)
  //
  // The ephemeral "the model is working" line. Its root composes the message look:
  // div.ui-message.ui-message--assistant.ui-thinking (italic, muted), or the system
  // look for tone 'system' (the centred "Loading model" line).
  //
  // opts:
  //   label    the text before the dots (default 'thinking'; the caller words it)
  //   tone     'assistant' (default) or 'system'
  //   testid   placed on the root (supplied by the caller)
  //
  // The dots spin at 120ms unless the user prefers reduced motion (read once, at
  // creation: then one static ellipsis). The interval stops on destroy(), on settle(),
  // and once the node has been connected and then disconnected. A node that was built
  // but not yet appended keeps ticking until it is attached.
  // settle(text) stops the timer, drops the thinking modifier and replaces the contents
  // with plain text, keeping the same node (the "Model loaded." line). destroy() stops
  // the timer; it never removes the node. Both are safe to repeat.
  App.ui.thinking = function (opts) {
    opts = opts || {};
    var tone = opts.tone || 'assistant';
    if (!TONE_CLASS[tone]) throw new Error('App.ui.thinking: unknown tone "' + tone + '"');
    var util = App.ui.util;
    var textEl = util.el('span', {
      className: 'ui-thinking-text',
      text: opts.label === undefined || opts.label === null ? 'thinking' : String(opts.label)
    });
    var dotEl = util.el('span', { className: 'ui-thinking-dots', 'aria-hidden': 'true' });
    var root = util.el('div', { className: 'ui-message ' + TONE_CLASS[tone] + ' ui-thinking' }, [textEl, dotEl]);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    var timer = null;
    var wasConnected = false;
    var frame = 0;
    function stop() {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    }
    var reduceMotion = !!(window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    if (reduceMotion) {
      dotEl.textContent = ' …';
    } else {
      timer = setInterval(function () {
        if (root.isConnected) {
          wasConnected = true;
        } else if (wasConnected) {
          stop();
          return;
        }
        frame = (frame + 1) % FRAMES.length;
        dotEl.textContent = ' ' + FRAMES[frame];
      }, 120);
    }

    return {
      el: root,
      settle: function (text) {
        stop();
        root.classList.remove('ui-thinking');
        root.textContent = text === undefined || text === null ? '' : String(text);
      },
      destroy: function () { stop(); }
    };
  };
})();
