// App.toolOverrideState -- the agent-mode state of one tool-settings field (sortie 07,
// leg 4, DD9). tool-config-fields.js builds the field; this module adds what makes it an
// override: whether the agent owns the value or inherits it, Reset, the clipped-field
// line (the stored value was narrowed by the app-wide setting) and the paths note.
//
//   App.toolOverrideState.decorate(h, o) -> h
//     h  a handle from App.toolConfigFields (renderBase, agent mode)
//     o  { name, prop, marker, operatorValue, own, storedValue, notice, onChange }
//        own: the key is in the stored override; storedValue: that stored value;
//        notice: the agent's clip notice for this field, or null; onChange: the host's
//        dirty callback.
//   Handle additions: isOwn(), ownValue() (the value to store, or undefined: nothing),
//   reset(), touch() (an operator edit makes the field own), rebase({own, storedValue,
//   notice}) (the agent was saved or refreshed), setNote(text|null), focus(). setError
//   is wrapped so a refusal from the server clears on the next edit.
//
// The state is in text and a data attribute, never colour alone:
//   control   data-tool-override-state="own" | "inherited"; data-tool-override-stored
//             (an own number's stored value, which the range check exempts)
//   text      the field's hint "Inherited from Settings" / "This agent's own"
//             (testid tool-override-state; a status line under a checkbox)
//   Reset     tool-override-reset, named "Reset {title} to inherited", shown while own
//   clipped   tool-override-clipped, with tool-override-use-narrowed and
//             tool-override-clipped-reset; drawn from the handle's state, so it shows only
//             while the field still holds its loaded stored value
//   note      tool-override-note (the paths note set by the Tools tab)
(function () {
  'use strict';
  window.App = window.App || {};

  // The reserved host a clip writes for "no hosts" (resolver.NO_HOSTS). It is never
  // shown as an editable chip.
  var NO_HOSTS = 'none.invalid';

  function sameValue(a, b) {
    if (Array.isArray(a) && Array.isArray(b)) {
      if (a.length !== b.length) return false;
      var x = a.map(String).sort();
      var y = b.map(String).sort();
      for (var i = 0; i < x.length; i++) if (x[i] !== y[i]) return false;
      return true;
    }
    return JSON.stringify(a) === JSON.stringify(b);
  }

  function emptyValue(v) {
    return v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0);
  }

  function clippedText(notice) {
    var dropped = notice.dropped || [];
    if (dropped.length) {
      return 'Narrowed by the app-wide setting: ' + dropped.join(', ') + ' no longer applies.';
    }
    return notice.message || 'Narrowed by the app-wide setting.';
  }

  // One persistent polite live node for the whole page (a visually hidden App.ui.status),
  // reused for every announcement; created on first use and re-attached if its host was
  // torn down.
  var liveStatus = null;
  var liveTimer = null;
  function ensureLive() {
    if (!liveStatus) {
      liveStatus = window.App.ui.status({ led: false, testid: 'tool-override-live' });
      liveStatus.el.classList.add('visually-hidden');
    }
    if (!liveStatus.el.isConnected) document.body.appendChild(liveStatus.el);
  }
  function announce(text) {
    ensureLive();
    // Clear first so the same words announce again on a later action.
    liveStatus.set('idle', '');
    if (liveTimer) clearTimeout(liveTimer);
    liveTimer = setTimeout(function () { liveStatus.set('idle', text); }, 50);
  }

  function decorate(h, o) {
    var ui = window.App.ui;
    ensureLive();
    var title = o.prop.title || o.name;
    var locked = (o.marker === 'NarrowSuperset' && Array.isArray(o.operatorValue))
      ? o.operatorValue.map(String)
      : [];
    var st = { own: !!o.own, stored: o.storedValue, notice: o.notice || null };
    var keepNoHosts = false;
    var noteStatus = null;
    var clipEl = null;
    var clipLineEl = null;
    var stateStatus = null;

    // Ids this module adds to the control's aria-describedby (the field library rewrites
    // the attribute on a hint or error change, so syncDescribed() re-applies them).
    var managedIds = [];
    function focusTarget() { return h.chips ? h.chips.input : h.control; }
    function elId(el) {
      if (!el.id) el.id = ui.util.uid('tos');
      if (managedIds.indexOf(el.id) < 0) managedIds.push(el.id);
      return el.id;
    }
    function syncDescribed() {
      // The focusable element (a chip list's input), the one the field library wires.
      var target = focusTarget();
      var current = (target.getAttribute('aria-describedby') || '').split(/\s+/)
        .filter(function (t) { return t && managedIds.indexOf(t) < 0; });
      if (stateStatus && stateStatus.el.parentNode) current.push(elId(stateStatus.el));
      if (clipEl && clipLineEl) current.push(elId(clipLineEl));
      if (noteStatus && noteStatus.el.parentNode) current.push(elId(noteStatus.el));
      if (current.length) target.setAttribute('aria-describedby', current.join(' '));
      else target.removeAttribute('aria-describedby');
    }

    function notify() { if (typeof o.onChange === 'function') o.onChange(); }

    function inheritedValue() {
      return window.App.toolConfigFields.seedValue(o.prop, {}, o.name, o.operatorValue);
    }

    function ownValue() {
      if (!st.own) return undefined;
      var v = h.value();
      if (Array.isArray(v)) {
        if (locked.length) v = v.filter(function (x) { return locked.indexOf(String(x)) < 0; });
        if (v.length === 0) return keepNoHosts ? [NO_HOSTS] : undefined;
        return v;
      }
      if (emptyValue(v)) return undefined;
      return v;
    }

    // The stored value as ownValue() would give it (a legacy full union loses the
    // locked operator chips).
    function norm(stored) {
      if (Array.isArray(stored) && locked.length) {
        return stored.filter(function (x) { return locked.indexOf(String(x)) < 0; });
      }
      return stored;
    }

    function clippedVisible() {
      if (!st.notice || !st.own || st.stored === undefined) return false;
      return sameValue(ownValue(), norm(st.stored));
    }

    function stateText() {
      if (!st.own) return 'Inherited from Settings';
      return keepNoHosts ? 'This agent\'s own: no hosts' : 'This agent\'s own';
    }

    function effectiveUsable(effective) {
      if (Array.isArray(effective)) {
        return effective.length > 0 && !(effective.length === 1 && effective[0] === NO_HOSTS);
      }
      return effective !== null && effective !== undefined && effective !== '';
    }

    function buildClipped() {
      var notice = st.notice;
      var usable = effectiveUsable(notice.effective);
      var line = ui.status({ live: 'off', textTone: true, testid: 'tool-override-clipped' });
      var text = clippedText(notice);
      if (!usable) text += ' Reset it to inherited, or turn this tool off for this agent.';
      line.set('warning', text);
      clipLineEl = line.el;
      var row = document.createElement('div');
      row.setAttribute('data-tool-override-clipped-row', '');
      row.appendChild(line.el);
      if (usable) {
        row.appendChild(ui.button({
          variant: 'ghost', size: 'sm', label: 'Use narrowed value',
          ariaLabel: 'Use the narrowed value for ' + title,
          testid: 'tool-override-use-narrowed',
          onClick: function () {
            h.setValue(notice.effective);
            st.own = true;
            keepNoHosts = false;
            refresh();
            notify();
            focusTarget().focus();
            announce('Using the narrowed value');
          }
        }));
      }
      row.appendChild(ui.button({
        variant: 'ghost', size: 'sm', label: 'Reset to inherited',
        ariaLabel: 'Reset ' + title + ' to inherited',
        testid: 'tool-override-clipped-reset',
        onClick: function () { doReset(); }
      }));
      return row;
    }

    function refresh() {
      h.control.setAttribute('data-tool-override-state', st.own ? 'own' : 'inherited');
      if (st.own && typeof st.stored === 'number') {
        h.control.setAttribute('data-tool-override-stored', String(st.stored));
      } else {
        h.control.removeAttribute('data-tool-override-stored');
      }
      var text = stateText();
      if (h.field) h.field.setHint(text);
      else if (stateStatus) stateStatus.set('idle', text);
      resetBtn.hidden = !st.own;
      var show = clippedVisible();
      if (show && !clipEl) {
        clipEl = buildClipped();
        h.el.appendChild(clipEl);
      } else if (!show && clipEl) {
        clipEl.parentNode.removeChild(clipEl);
        clipEl = null;
        clipLineEl = null;
      }
      syncDescribed();
    }

    function doReset() {
      st.own = false;
      keepNoHosts = false;
      h.setValue(inheritedValue());
      h.setError(null);
      refresh();
      notify();
      focusTarget().focus();
      announce('Reset to inherited');
    }

    var resetBtn = ui.button({
      variant: 'ghost', size: 'sm', label: 'Reset',
      ariaLabel: 'Reset ' + title + ' to inherited',
      testid: 'tool-override-reset',
      onClick: doReset
    });
    if (!h.field) {
      stateStatus = ui.status({ live: 'off', led: false, testid: 'tool-override-state' });
      h.el.appendChild(stateStatus.el);
    }
    var actions = document.createElement('div');
    actions.appendChild(resetBtn);
    h.el.appendChild(actions);

    // A stored "no hosts" is never an editable chip; it stays stored until the operator
    // edits the field or resets it.
    if (o.marker === 'NarrowAnyWhenEmpty' && st.own && Array.isArray(st.stored) &&
        st.stored.indexOf(NO_HOSTS) >= 0) {
      keepNoHosts = true;
      h.setValue(st.stored.filter(function (x) { return x !== NO_HOSTS; }));
    }

    // A server refusal shown on the field is cleared by the operator's next edit.
    var baseSetError = h.setError;
    var serverError = false;
    h.setError = function (msg) {
      serverError = !!msg;
      baseSetError(msg);
      syncDescribed();
    };
    h.focus = function () { focusTarget().focus(); };
    // The number field's own input handler rewrites the error (and so the describedby
    // ids) itself; re-sync after it whatever the listener order.
    if (typeof h.validate === 'function') {
      var baseValidate = h.validate;
      h.validate = function () {
        var msg = baseValidate();
        syncDescribed();
        return msg;
      };
    }
    h.isOwn = function () { return st.own; };
    h.ownValue = ownValue;
    h.reset = doReset;
    // An edit by the operator (not a programmatic write) makes the field its own.
    h.touch = function (e) {
      var type = e && e.type;
      keepNoHosts = false;
      st.own = true;
      // Clearing the field leaves nothing of its own: the field is inherited again (the
      // dirty state still follows the stored map, so a stored own value is removed on
      // Save). A text or number field is mid-typing on an input event, so its text is
      // left alone (typing on makes it own again); the inherited value is written back
      // on change (blur) while it is still empty. A chip list is not mid-typing: it
      // takes the inherited chips at once.
      if (ownValue() === undefined) {
        st.own = false;
        if (o.marker !== 'NarrowSuperset' && type !== 'input') {
          var inh = inheritedValue();
          h.setValue(inh);
          h.setError(null);
          var shown = Array.isArray(inh) ? (inh.length ? 'list' : '') : inh;
          announce(shown === '' || shown === undefined || shown === null
            ? 'Using the inherited value'
            : (shown === 'list' ? 'Using the inherited list' : 'Using the inherited value, ' + shown));
          if (h.chips) focusTarget().focus();
        }
      }
      if (serverError) {
        serverError = false;
        // A number's own whole-number message stays; a refusal from the server goes.
        var msg = h.validate ? h.validate() : null;
        if (!msg) baseSetError(null);
      }
      refresh();
    };
    // The agent was saved or refreshed: the stored state, and its notice, are new.
    // A pending edit (the field differs from what was stored before AND from what is
    // stored now) is kept; otherwise the field takes the new stored state.
    h.rebase = function (r) {
      var rOwn = !!r.own;
      var differsNew = rOwn !== st.own || (rOwn && !sameValue(ownValue(), norm(r.storedValue)));
      var differsOld = (st.stored !== undefined) !== st.own ||
        (st.own && !sameValue(ownValue(), norm(st.stored)));
      st.stored = r.storedValue;
      st.notice = r.notice || null;
      if (!(differsNew && differsOld)) {
        st.own = rOwn;
        if (differsNew) {
          keepNoHosts = false;
          if (!rOwn) {
            h.setValue(inheritedValue());
            h.setError(null);
          } else {
            h.setValue(Array.isArray(r.storedValue)
              ? r.storedValue.filter(function (x) { return x !== NO_HOSTS; })
              : r.storedValue);
            keepNoHosts = Array.isArray(r.storedValue) && r.storedValue.indexOf(NO_HOSTS) >= 0;
          }
        }
      }
      refresh();
    };
    h.setNote = function (text) {
      if (!text) {
        if (noteStatus) {
          noteStatus.el.parentNode.removeChild(noteStatus.el);
          noteStatus = null;
        }
        syncDescribed();
        return;
      }
      if (!noteStatus) {
        noteStatus = ui.status({ live: 'off', led: false, testid: 'tool-override-note' });
        h.el.appendChild(noteStatus.el);
      }
      noteStatus.set('idle', text);
      syncDescribed();
    };
    refresh();
    return h;
  }

  window.App.toolOverrideState = { decorate: decorate };
})();
