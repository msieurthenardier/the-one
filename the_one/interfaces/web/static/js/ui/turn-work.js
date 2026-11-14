(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var LABELS = {
    'working': 'Working',
    'done': 'Work',
    'stopped': 'Stopped',
    'error': 'Ended with an error',
    'step-limit': 'Paused at the step limit',
    'sign-in': 'Waiting for sign-in'
  };
  var KINDS = ['narration', 'thinking', 'tool'];
  var PREVIEW_MAX = 400;

  // App.ui.turnWork(opts) -> handle  (Sortie 16 L01, flight DD1-DD4, DD7)
  //
  // The per-turn work group: one quiet line for everything the agent did in a turn before
  // its reply (narration, thinking, tool calls), a native <details> closed in every state.
  //
  // opts:
  //   testid         placed on the root
  //   previewTestid  placed on the preview node
  //   state          'working' (default), 'done', 'stopped', 'error', 'step-limit' or 'sign-in'
  //
  // Handle: el, setState(name) (an unknown name throws), setToolCalls(n), setActivity(text|null),
  // setPreview(text|null), setOperatorOnly(bool), stopDots(), add(kind, content) -> item,
  // isEmpty(), destroy().
  //   - setActivity and setPreview show only while 'working' and are cleared on leaving it.
  //   - setPreview shows the END of the text (the last 400 characters, whitespace collapsed)
  //     in at most two lines, overflow cut at the top; text only, never markup.
  //   - stopDots() swaps the spinner for a static ellipsis without changing the state (the
  //     Stop click); fresh dots start when the group next ENTERS 'working' from another state
  //     (setState to the state it is already in changes nothing).
  //   - add('tool', node) | add('thinking', string) | add('narration', string|node) returns
  //     {el, kind, setContent(content), remove()}; both are safe to repeat.
  //   - destroy() stops the dots timer; it never removes the node and is safe to repeat.
  //
  // Accessible name of the summary (aria-label): the state's label, then ", N tool call(s)"
  // or ", thinking" when the count text shows one, then ", operator only" when the chip
  // shows. The count, the tool name and the preview are aria-hidden, and only existing
  // nodes' text or attributes change, because the chat log is role=log with
  // aria-relevant="additions": new text nodes would be announced.
  App.ui.turnWork = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var state = opts.state === undefined || opts.state === null ? 'working' : String(opts.state);
    if (!Object.prototype.hasOwnProperty.call(LABELS, state)) {
      throw new Error('App.ui.turnWork: unknown state "' + state + '"');
    }
    var toolCalls = 0;
    var operatorOnly = false;
    var gone = false;
    var dots = null;
    var thinkingItems = 0;

    var lead = util.el('span', { className: 'ui-turn-work-lead', 'aria-hidden': 'true' });
    var labelEl = util.el('span', { className: 'ui-turn-work-label' });
    var countEl = util.el('span', { className: 'ui-turn-work-count', 'aria-hidden': 'true' });
    var nowEl = util.el('span', { className: 'ui-turn-work-now', 'aria-hidden': 'true' });
    var chipEl = util.el('span', { className: 'ui-turn-work-chip' });
    chipEl.hidden = true;
    var summary = util.el('summary', { className: 'ui-turn-work-toggle' },
      [lead, labelEl, countEl, nowEl, chipEl]);
    var body = util.el('div', { className: 'ui-turn-work-body' });
    var details = util.el('details', { className: 'ui-turn-work-details' }, [summary, body]);
    var preview = util.el('div', { className: 'ui-turn-work-preview', 'aria-hidden': 'true' });
    preview.hidden = true;
    if (opts.previewTestid) preview.setAttribute('data-testid', opts.previewTestid);
    var root = util.el('div', { className: 'ui-turn-work' }, [details, preview]);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    function countText() {
      if (toolCalls >= 1) return '· ' + toolCalls + (toolCalls === 1 ? ' tool call' : ' tool calls');
      if (state === 'done' && thinkingItems > 0) return '· thinking';
      return '';
    }

    function refresh() {
      var count = countText();
      labelEl.textContent = LABELS[state];
      countEl.textContent = count;
      var name = LABELS[state];
      if (count) name += ', ' + count.slice(2);
      if (operatorOnly) name += ', operator only';
      summary.setAttribute('aria-label', name);
    }

    function stopTimer() {
      if (dots) {
        dots.destroy();
        dots = null;
      }
    }

    function showLead() {
      stopTimer();
      lead.textContent = '';
      if (state === 'working' && !gone) {
        dots = App.ui.thinking.dots();
        lead.appendChild(dots.el);
      } else {
        lead.appendChild(util.icon('chevron-right'));
      }
    }

    function clearLive() {
      nowEl.textContent = '';
      preview.textContent = '';
      preview.hidden = true;
    }

    function clean(text) {
      var t = String(text).replace(/\s+/g, ' ').trim();
      return t.length > PREVIEW_MAX ? t.slice(t.length - PREVIEW_MAX) : t;
    }

    function fill(wrap, kind, content) {
      wrap.textContent = '';
      if (kind === 'thinking') {
        wrap.appendChild(util.el('span', { className: 'ui-turn-work-thinking-label', text: 'Thinking' }));
        wrap.appendChild(util.el('div', {
          className: 'ui-turn-work-thinking-text',
          text: content === undefined || content === null ? '' : String(content)
        }));
      } else if (typeof content === 'string') {
        wrap.classList.add('ui-turn-work-narration--plain');
        wrap.textContent = content;
      } else if (content) {
        wrap.classList.remove('ui-turn-work-narration--plain');
        wrap.appendChild(content);
      }
    }

    var handle = {
      el: root,
      setState: function (name) {
        name = String(name);
        if (!Object.prototype.hasOwnProperty.call(LABELS, name)) {
          throw new Error('App.ui.turnWork: unknown state "' + name + '"');
        }
        var was = state;
        state = name;
        root.setAttribute('data-state', state);
        if (was !== state) {
          if (state !== 'working') clearLive();
          showLead();
        }
        refresh();
      },
      setToolCalls: function (n) {
        toolCalls = typeof n === 'number' && isFinite(n) && n > 0 ? Math.floor(n) : 0;
        refresh();
      },
      setActivity: function (text) {
        nowEl.textContent = state === 'working' && text ? String(text) : '';
      },
      setPreview: function (text) {
        var t = state === 'working' && text !== null && text !== undefined ? clean(text) : '';
        preview.textContent = t;
        preview.hidden = !t;
      },
      setOperatorOnly: function (on) {
        operatorOnly = !!on;
        chipEl.textContent = '';
        if (operatorOnly) chipEl.appendChild(App.ui.chip({ label: 'Operator only', size: 'sm' }));
        chipEl.hidden = !operatorOnly;
        refresh();
      },
      stopDots: function () {
        if (state !== 'working' || !dots) return;
        stopTimer();
        lead.textContent = '';
        lead.appendChild(util.el('span', { className: 'ui-thinking-dots', text: ' …' }));
      },
      add: function (kind, content) {
        if (KINDS.indexOf(kind) === -1) throw new Error('App.ui.turnWork: unknown kind "' + kind + '"');
        var wrap = util.el('div', {
          className: 'ui-turn-work-item ui-turn-work-' + kind,
          'data-kind': kind
        });
        fill(wrap, kind, content);
        body.appendChild(wrap);
        if (kind === 'thinking') thinkingItems += 1;
        refresh();
        var removed = false;
        return {
          el: wrap,
          kind: kind,
          setContent: function (next) { fill(wrap, kind, next); },
          remove: function () {
            if (removed) return;
            removed = true;
            if (wrap.parentNode === body) body.removeChild(wrap);
            if (kind === 'thinking') thinkingItems -= 1;
            refresh();
          }
        };
      },
      isEmpty: function () { return body.children.length === 0; },
      destroy: function () {
        gone = true;
        stopTimer();
      }
    };

    root.setAttribute('data-state', state);
    showLead();
    refresh();
    return handle;
  };
})();
