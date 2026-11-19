// App.studio.providerDelete -- the provider editor's Delete flow (M36 F1 HAT).
//
//   var del = App.studio.providerDelete.create({ provider, danger, callbacks });
//   // danger: the App.ui.dangerZone handle; callbacks: { onDeleteSuccess }
//   // dangerZone action: { beforeArm: del.beforeArm, onConfirm: del.doDelete }
//   // del.refresh() re-reads the users.
//
// When the open provider is in use (agents or GleepGlorp), the Danger zone shows ONE
// neutral box from the moment the editor opens: who uses it (links), what deleting
// does, the "Delete anyway and clear their model" checkbox, then the Delete button
// itself (moved into the box), disabled until the box is ticked. Once ticked, the
// app's two-step confirm still applies and the commit sends ?force=true. A provider
// used by nobody keeps the plain Delete button with its two-step confirm.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function userLink(n) {
    return App.ui.util.el('a', {
      href: n === 'GleepGlorp'
        ? App.router.href({ destination: 'settings', section: 'gleepglorp' })
        : App.router.href({ destination: 'agents', id: n }),
      'data-testid': 'delete-user-link', text: n
    });
  }

  // "This provider is used by {a}." / "... by GleepGlorp and 2 agents: a, b."
  function explanation(names) {
    var util = App.ui.util;
    var kids = [document.createTextNode('This provider is used by ')];
    var agents = names.filter(function (n) { return n !== 'GleepGlorp'; });
    var hasGg = agents.length !== names.length;
    if (hasGg) kids.push(userLink('GleepGlorp'));
    if (hasGg && agents.length) kids.push(document.createTextNode(' and '));
    if (agents.length === 1 && !hasGg) {
      kids.push(userLink(agents[0]));
    } else if (agents.length) {
      kids.push(document.createTextNode(agents.length + (agents.length === 1 ? ' agent: ' : ' agents: ')));
      agents.forEach(function (n, i) {
        if (i > 0) kids.push(document.createTextNode(', '));
        kids.push(userLink(n));
      });
    }
    kids.push(document.createTextNode('. '));
    var one = names.length === 1;
    return util.el('p', { className: 'provider-delete-text', 'data-testid': 'delete-blocked-message' }, kids.concat([
      document.createTextNode('If you delete it, ' + (one ? 'it' : 'they') +
        ' will need a new model before ' + (one ? 'it' : 'they') + ' can answer.')
    ]));
  }

  function create(opts) {
    var provider = opts.provider;
    var danger = opts.danger;
    var callbacks = opts.callbacks || {};
    var forceDelete = false;
    var box = null;
    var forceBox = null;
    var gen = 0;

    function clearBox() {
      if (!box) return;
      // Put the button back as the zone's own child before dropping the box.
      danger.el.appendChild(danger.button);
      danger.button.removeAttribute('aria-describedby');
      box.remove();
      box = null;
      forceBox = null;
      forceDelete = false;
      danger.setDisabled(false);
    }

    function show(users) {
      clearBox();
      if (!users.length) return;
      var text = explanation(users);
      text.id = App.ui.util.uid('provider-delete-text');
      forceBox = App.ui.checkbox({
        label: 'Delete anyway and clear their model', testid: 'delete-force-checkbox',
        describedBy: text.id,
        onChange: function (checked) {
          // Unticking while Delete is armed takes the arm back (it needs the tick).
          if (!checked) App.ui.confirm.disarm(danger.button);
          danger.setDisabled(!checked);
        }
      });
      box = App.ui.util.el('div', { className: 'provider-delete-box' }, [
        text, forceBox.el, danger.button
      ]);
      // The disabled Delete says why: the explanation names it (and the tick it needs).
      danger.button.setAttribute('aria-describedby', text.id);
      danger.el.appendChild(box);
      danger.setDisabled(true);
    }

    function refresh() {
      var mine = ++gen;
      return fetch('/api/providers/' + encodeURIComponent(provider.id) + '/agents')
        .then(function (r) { return r.json(); })
        .then(function (data) { if (mine === gen) show((data && data.agents) || []); })
        .catch(function () { /* fail open: the plain flow; the server still refuses with a 409 */ });
    }

    function beforeArm(proceed) {
      // The button is enabled only when there are no users or the box is ticked.
      if (forceBox) forceDelete = true;
      proceed();
    }

    function doDelete(revertFn) {
      var url = '/api/providers/' + encodeURIComponent(provider.id) +
        (forceDelete ? '?force=true' : '');
      fetch(url, { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) {
            return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
          }
          return r.json();
        })
        .then(function (body) {
          App.store.invalidate('providers');
          App.store.invalidate('agents');
          App.store.invalidate('sessions');
          var cleared = (body && body.cleared) || [];
          App.ui.flash(cleared.length
            ? 'Provider deleted. Cleared the model for ' + cleared.join(', ') + '.'
            : 'Provider deleted');
          if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
        })
        .catch(function (err) {
          var hadFocus = !!(box && box.contains(document.activeElement));
          revertFn();
          if (forceBox) { forceDelete = false; forceBox.setChecked(false); danger.setDisabled(true); }
          App.ui.flash(err.message, { error: true });
          // refresh() rebuilds the box; focus that was inside it goes to the new checkbox.
          refresh().then(function () {
            if (hadFocus && forceBox && forceBox.control) forceBox.control.focus();
          });
        });
    }

    refresh();
    return { beforeArm: beforeArm, doDelete: doDelete, refresh: refresh };
  }

  window.App.studio.providerDelete = { create: create };
})();
