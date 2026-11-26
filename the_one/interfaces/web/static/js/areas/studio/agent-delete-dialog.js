// App.studio.agentDeleteDialog -- the agent Delete confirmation (sortie 20, DD5/DD6, layout
// Option A). Deleting an agent deletes its chats, so the General tab's Delete opens this
// dialog instead of arming a second click: the title names the agent, the message says how many
// chats go with it, and Delete stays disabled until the operator ticks the acknowledgement.
//
//   App.studio.agentDeleteDialog.open({name, opener, onDeleted(body)})
//     Opens once the chat count has been read; a call while a dialog is open or being
//     prepared does nothing (a second click opens nothing more).
//     onDeleted(body) runs after a successful DELETE, with the dialog already closed; body is
//     the response ({status, chats_deleted}). It runs even when Escape closed the dialog while
//     the request was in flight. Cancel and Escape send nothing.
//
// A composition, not a control-library factory: the modal's own actions always close it, so the
// dialog builds its Cancel and Delete buttons and passes them as footerEnd (precedent:
// routines-custom-recurrence.js). The count is a fresh read of the sessions store filtered by
// agent_name; when the read fails the message drops the number.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var busy = false; // true from the first click until the dialog has closed

  function plural(n) { return n + (n === 1 ? ' chat' : ' chats'); }

  function messageText(count) {
    if (count === null) {
      return 'This deletes the agent and all of its chats, with every message in them. ' +
        "This can't be undone.";
    }
    if (count === 0) return "This deletes the agent. It has no chats. This can't be undone.";
    return 'This deletes the agent and its ' + plural(count) + ', with every message in them. ' +
      "This can't be undone.";
  }

  function flashText(name, deleted) {
    return deleted > 0
      ? 'Deleted ' + name + ' and ' + plural(deleted) + '.'
      : 'Deleted ' + name + '.';
  }

  function countChats(name) {
    return App.store.get('sessions', { force: true }).then(function (list) {
      var n = 0;
      (list || []).forEach(function (s) { if (s && s.agent_name === name) n += 1; });
      return n;
    }).catch(function () { return null; });
  }

  function build(req, count) {
    var util = App.ui.util;
    var name = req.name;
    var modal = null;
    var running = false;

    var message = util.el('p', { className: 'agent-delete-message', text: messageText(count) });
    message.id = util.uid('agent-delete-message');

    var deleteBtn = null;
    var ack = App.ui.checkbox({
      label: "I understand this will delete all of this agent's chat history",
      testid: 'delete-agent-ack-checkbox',
      onChange: function (checked) { if (!running) deleteBtn.disabled = !checked; }
    });
    // Polite status: "Deleting..." while the request runs, empty otherwise (WCAG 4.1.3).
    var status = util.el('span', { className: 'visually-hidden', role: 'status' });
    var body = util.el('div', { className: 'agent-delete-body' }, [message, ack.el, status]);
    var closed = false;

    var cancelBtn = App.ui.button({
      variant: 'ghost', label: 'Cancel', testid: 'delete-agent-cancel-btn',
      onClick: function () { modal.close(null); }
    });
    deleteBtn = App.ui.button({
      variant: 'danger', label: 'Delete', testid: 'delete-agent-confirm-btn',
      disabled: true, onClick: function () { commit(); }
    });
    deleteBtn.setAttribute('aria-describedby', message.id);
    var actions = util.el('div', { className: 'agent-delete-actions' }, [cancelBtn, deleteBtn]);

    function setRunning(on) {
      running = on;
      ack.setDisabled(on);
      deleteBtn.disabled = on || !ack.control.checked;
      status.textContent = on ? 'Deleting…' : '';
      var dlg = body.closest('[role="dialog"]');
      if (dlg) { if (on) dlg.setAttribute('aria-busy', 'true'); else dlg.removeAttribute('aria-busy'); }
    }

    function commit() {
      if (running || !ack.control.checked) return;
      setRunning(true);
      cancelBtn.focus(); // Delete and the checkbox just disabled; keep focus inside the dialog
      busy = true;
      fetch('/api/agents/' + encodeURIComponent(name), { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) {
            return r.json().then(function (e) { throw new Error((e && e.detail) || 'Delete failed'); },
              function () { throw new Error('Delete failed'); });
          }
          return r.json();
        })
        .then(function (resp) {
          // A no-op when Escape already closed the dialog.
          running = false;
          modal.close('deleted');
          busy = false;
          if (typeof req.onDeleted === 'function') req.onDeleted(resp || {});
        })
        .catch(function (err) {
          setRunning(false);
          if (closed) busy = false; // Escape closed it mid-request: the opener is free again
          else deleteBtn.focus(); // still ticked: the user can retry
          App.ui.flash((err && err.message) || 'Delete failed', { error: true });
        });
    }

    modal = App.ui.modal({
      title: 'Delete "' + name + '"?', width: 460, body: body, footerEnd: actions,
      initialFocus: cancelBtn, testid: 'delete-agent-dialog',
      // Keep the opener guarded while a request is still in flight after Escape.
      onClose: function () { closed = true; if (!running) busy = false; }
    });
    modal.open(req.opener || null);
    return modal;
  }

  function open(req) {
    if (busy) return;
    busy = true;
    countChats(req.name).then(function (count) {
      try {
        build(req, count);
      } catch (err) {
        busy = false;
        throw err;
      }
    });
  }

  window.App.studio.agentDeleteDialog = { open: open, flashText: flashText };
})();
