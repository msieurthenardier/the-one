// TEST-ONLY DD8 harness (M25 F1 L2): a minimal wrapper implementing the modal
// stacking rule so the checks in _dialog_rule_checks.py can run before the real
// wrapper exists (Flight 2 points the same checks at it). Not production code.
//
// The rule: native <dialog> + showModal(); explicit opener and explicit focus
// on open; Escape handled on keydown on the dialog with BOTH preventDefault and
// stopPropagation, closing the topmost layer only; cancel prevented and routed
// through the same path; a close listener keeps the stack in sync (ignoring a stale close
// event that fires after a reopen); a backdrop
// click closes transient dialogs only; focus returns to the recorded opener.
(function () {
  var stack = [];

  function indexOf(dlg) {
    for (var i = 0; i < stack.length; i++) {
      if (stack[i].dlg === dlg) return i;
    }
    return -1;
  }

  function firstFocusable(dlg) {
    return (
      dlg.querySelector('[autofocus]') ||
      dlg.querySelector('button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])')
    );
  }

  function restore(entry) {
    if (entry.opener && entry.opener.isConnected) entry.opener.focus();
  }

  function closeEntry(entry) {
    var i = indexOf(entry.dlg);
    if (i !== -1) stack.splice(i, 1);
    if (entry.dlg.open) entry.dlg.close();
    restore(entry);
  }

  function closeTopmost() {
    var top = stack[stack.length - 1];
    if (!top) return false;
    closeEntry(top);
    return true;
  }

  function bind(dlg) {
    if (dlg.__ruleBound) return;
    dlg.__ruleBound = true;
    dlg.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      e.stopPropagation();
      closeTopmost();
    });
    dlg.addEventListener('cancel', function (e) {
      e.preventDefault();
      closeTopmost();
    });
    dlg.addEventListener('close', function () {
      // close is queued as a task: a stale close from an earlier close can fire
      // after the dialog was reopened. Only sync the stack for a really closed one.
      if (dlg.open) return;
      var i = indexOf(dlg);
      if (i === -1) return;
      var entry = stack.splice(i, 1)[0];
      restore(entry);
    });
    dlg.addEventListener('click', function (e) {
      var i = indexOf(dlg);
      if (i === -1 || !stack[i].transient) return;
      var r = dlg.getBoundingClientRect();
      var outside = e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
      if (outside) closeEntry(stack[i]);
    });
  }

  window.DialogRule = {
    open: function (dlg, opts) {
      opts = opts || {};
      bind(dlg);
      stack.push({ dlg: dlg, opener: opts.opener || null, transient: !!opts.transient });
      dlg.showModal();
      var target = firstFocusable(dlg);
      if (target) target.focus();
    },
    closeTopmost: closeTopmost,
    depth: function () { return stack.length; }
  };
})();
