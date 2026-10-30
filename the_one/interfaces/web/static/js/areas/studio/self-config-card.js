// App.studio.selfConfigCard -- one item card of the Self-configuration tab (M33 F4 L06, mockup
// SC2). `create(opts)` builds an App.ui.groupTile (expand: false) holding the item's enable
// switch, bold title, the "Require approval" switch on the title row and a one-line description,
// then a compact status area and two bordered App.ui.disclosure expanders: "Waiting for approval"
// (with a count chip) and "History". The section modules fill the two bodies and report the
// waiting count through `setWaitingCount(n)`; nothing here knows what a revision or a routine is.
//
//   opts: key ('prompt' | 'routines'), title, description, enableLabel,
//         approvalLabel (the accessible name; the visible label is "Require approval").
//   No test ids are set here: the registry guard reads only literal ids, so each caller sets
//   its own on the elements this returns (`el`, `enable.control`, `approval.control`,
//   `queue.chip`, `queue.zero`, `queue.details.el` / `.summary`, `history.details.el` /
//   `.summary`).
//   returns: {el, tile, enable, approval, statusHost,
//             queue: {details, body, chip, zero, open(), setCount(n), setUnavailable(text)},
//             history: {details, body}, setWaitingCount(n)}
//
// At zero waiting the expander is replaced by plain muted text "Waiting for approval (0)" (a
// disclosure has no disabled state); a count above zero shows the expander, collapsed until the
// operator opens it (or an action inside it fails or goes stale: `queue.open()`).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var WAITING = 'Waiting for approval';

  function create(opts) {
    var util = App.ui.util;
    var approval = App.ui.toggle({ label: 'Require approval', disabled: true });
    // The visible label is "Require approval"; the full name says what it applies to and starts
    // with the visible words (SC 2.5.3).
    approval.control.setAttribute('aria-label', opts.approvalLabel);
    approval.el.classList.add('self-config-approval');

    var tile = App.ui.groupTile({
      name: opts.title,
      expand: false,
      dataset: { item: opts.key },
      master: {
        label: opts.enableLabel, tristate: false, state: 'off', disabled: true
      },
      actions: [approval.el],
      subtitle: opts.description
    });
    tile.el.classList.add('self-config-card');
    // Own classes for the card's layout rules (the library's classes are not selected outside
    // js/ui): the title row wraps, and the name has a readable basis before the approval wraps.
    tile.el.firstElementChild.classList.add('self-config-card-row');
    tile.nameEl.classList.add('self-config-card-name');
    // The title is the card's heading (the tab's h2 eyebrow precedes it).
    tile.nameEl.setAttribute('role', 'heading');
    tile.nameEl.setAttribute('aria-level', '3');

    var statusHost = util.el('div', { className: 'self-config-card-status' });
    tile.el.appendChild(statusHost);

    // ── Waiting for approval ────────────────────────────────────────────
    var chip = util.el('span', { className: 'self-config-count-chip', text: '0' });
    var waiting = App.ui.disclosure({
      variant: 'bordered',
      summary: WAITING,
      meta: [chip],
      className: 'self-config-expander'
    });
    waiting.el.hidden = true;
    var zero = util.el('div', {
      className: 'self-config-waiting-zero', text: WAITING + ' (0)'
    });
    zero.tabIndex = -1;

    function setCount(n) {
      var count = n > 0 ? n : 0;
      chip.textContent = String(count);
      waiting.el.hidden = count === 0;
      zero.hidden = count > 0;
      zero.textContent = WAITING + ' (0)';
    }
    // A queue that cannot be confirmed shows no actionable item: the plain line says so.
    function setUnavailable(text) {
      chip.textContent = '0';
      waiting.el.hidden = true;
      zero.hidden = false;
      zero.textContent = WAITING + ': ' + text;
    }
    setCount(0);

    // ── History ─────────────────────────────────────────────────────────
    var history = App.ui.disclosure({
      variant: 'bordered',
      summary: 'History',
      className: 'self-config-expander'
    });

    tile.el.appendChild(waiting.el);
    tile.el.appendChild(zero);
    tile.el.appendChild(history.el);

    return {
      el: tile.el,
      tile: tile,
      enable: tile.toggle,
      approval: approval,
      statusHost: statusHost,
      queue: {
        details: waiting,
        body: waiting.body,
        chip: chip,
        zero: zero,
        open: function () { waiting.setOpen(true); },
        setCount: setCount,
        setUnavailable: setUnavailable
      },
      history: {
        details: history,
        body: history.body
      },
      setWaitingCount: setCount
    };
  }

  window.App.studio.selfConfigCard = { create: create };
})();
