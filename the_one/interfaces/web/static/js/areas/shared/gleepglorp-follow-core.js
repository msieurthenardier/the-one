// App.gleepglorpFollow -- what the editors' GleepGlorp follow modules share (M36 F5 L2, flight
// DD4). An editor follows a change the operator approved in a GleepGlorp chat: App.approvals'
// CONFIG_CHANGED event names the kind and the target, the editor fetches the stored row and
// rebases (or says it cannot), and a note under the header says who changed it.
//
//   buildNote(detail, {testid, text?, field?, item?}) -> <p>
//       The approval note: "Changed by a change you approved in a GleepGlorp chat · time · Open
//       chat". `text` replaces the whole sentence (no time, no link); `field` and `item` add
//       data-field and data-item (an item note also takes the --item class). A null detail is
//       fine (the text then has no time and no link).
//   matches(kind, detail) -> bool
//       The detail is a change of `kind` with a target_id.
//   listen(kind, handler)
//       Registers handler(detail) on App.approvals.CONFIG_CHANGED for a change of `kind` with a
//       target_id. The document is the transport and has no `off`, so a kind registers once per
//       page; a second call for the same kind is a no-op.
//   fieldNotes(place, {testid}) -> {show(detail, fields), clear()}
//       The per-field follow notes (the Library editors that place a note under each field).
//   refetchThen(ctl, url, isCurrent, fn)
//       Waits for the controller to be idle, fetches `url`, and calls fn(row) when the controller
//       is still the live one (isCurrent() and ctl.alive()). A Save that began while the row was
//       in flight defers it: the row is fetched again once the Save ends. A failed fetch is
//       dropped (the next open reads the stored row).
(function () {
  'use strict';
  window.App = window.App || {};

  var NOTE_TEXT = 'Changed by a change you approved in a GleepGlorp chat';
  var listening = Object.create(null);

  function buildNote(detail, opts) {
    var o = opts || {};
    var p = document.createElement('p');
    p.className = 'agent-approved-change-note';
    p.setAttribute('data-testid', o.testid);
    if (o.field !== undefined) p.setAttribute('data-field', o.field);
    if (o.item !== undefined) {
      p.setAttribute('data-item', o.item);
      p.className += ' agent-approved-change-note--item';
    }
    if (o.text) {
      p.appendChild(document.createTextNode(o.text));
      return p;
    }
    var when = '';
    var t = detail && detail.at ? new Date(detail.at) : null;
    if (t && !isNaN(t.getTime())) when = ' · ' + App.time.formatClock(t);
    p.appendChild(document.createTextNode(NOTE_TEXT + when));
    if (detail && detail.session_id) {
      p.appendChild(document.createTextNode(' · '));
      var a = document.createElement('a');
      a.setAttribute('href', App.router.href({ destination: 'chats', id: detail.session_id }));
      a.textContent = 'Open chat';
      // A note repeated per card names its subject, so the links are told apart (WCAG 2.4.4).
      if (o.linkLabel) a.setAttribute('aria-label', 'Open chat (' + o.linkLabel + ')');
      p.appendChild(a);
    }
    return p;
  }

  function matches(kind, detail) {
    return !!detail && detail.kind === kind && !!detail.target_id;
  }

  function listen(kind, handler) {
    if (listening[kind]) return;
    listening[kind] = true;
    document.addEventListener(App.approvals.CONFIG_CHANGED, function (e) {
      if (matches(kind, e.detail)) handler(e.detail);
    });
  }

  function refetchThen(ctl, url, isCurrent, fn) {
    ctl.onIdle(function () {
      if (!isCurrent() || !ctl.alive()) return;
      App.api.fetchJson(url).then(function (row) {
        if (!isCurrent() || !ctl.alive()) return;
        // A Save began while the row was in flight: wait for it, then read the row again.
        if (ctl.saving()) { refetchThen(ctl, url, isCurrent, fn); return; }
        fn(row);
      }, function () { /* the next open reads the stored row */ });
    });
  }

  // fieldNotes(place, {testid}) -> {show(detail, fields), clear()}
  //   The per-field follow notes of an editor (DD14: one note under each changed field it shows).
  //   place(field, el) appends el where the field's control lives and returns the controls it
  //   describes, or null for a field the editor does not show (that field gets no note). show
  //   replaces the notes drawn before; each note is linked on its controls' aria-describedby
  //   (through App.gleepglorpFill.link) and clear removes the notes and unlinks them.
  function fieldNotes(place, opts) {
    var drawn = [];
    function clear() {
      drawn.forEach(function (d) {
        App.gleepglorpFill.unlink(d.entry);
        if (d.el.parentNode) d.el.parentNode.removeChild(d.el);
      });
      drawn = [];
    }
    function show(detail, fields) {
      clear();
      (fields || []).forEach(function (field) {
        var el = buildNote(detail, Object.assign({}, opts, { field: field }));
        var controls = place(field, el);
        if (!controls) return;
        drawn.push({ el: el, entry: App.gleepglorpFill.link(el, controls) });
      });
    }
    return { show: show, clear: clear };
  }

  window.App.gleepglorpFollow = {
    buildNote: buildNote, matches: matches, listen: listen, refetchThen: refetchThen,
    fieldNotes: fieldNotes
  };
})();
