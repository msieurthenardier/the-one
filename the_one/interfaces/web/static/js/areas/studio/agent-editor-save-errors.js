// App.studio.agentEditorSaveErrors -- the agent editor's failed-Save handling (split out of
// agent-editor-controller.js in M36 F2 L7, no behaviour change): the server's name refusal
// goes on the Name field, tool-override and secret refusals on their own fields, every other
// message in the header. A factory the controller calls once:
//
//   var errors = App.studio.agentEditorSaveErrors.create(ctx);
//
// ctx (controller -> module): editorEl, slot (the mount slot), currentData() (the current
// mount's data or null), setActiveTab(tab), setNameError(text), setEditorError(text) and
// toolsTab() (the Built-in tools tab handle or null).
// handle: onSaveError(err).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var editorEl = ctx.editorEl;
    var slot = ctx.slot;
    var currentData_ = ctx.currentData;
    var setActiveTab = ctx.setActiveTab;
    var setNameError_ = ctx.setNameError;
    var setEditorError_ = ctx.setEditorError;
    var toolsTab_ = ctx.toolsTab;

    // A failed save: the server's name refusal goes on the Name field (focused, so
    // the operator lands on it), every other message in the header.
    function onSaveError_(err) {
      // Sortie 07, DD9: a refusal of a tool override carries a three-segment loc
      // ["tool_overrides", tool, field] (App.api.fieldErrors matches single segments
      // only), so those entries are split off and placed on their field below.
      var items = (err && Array.isArray(err.detail)) ? err.detail : [];
      var toolItems = items.filter(function (d) {
        return d && d.type === 'tool_override' && Array.isArray(d.loc) &&
          d.loc[0] === 'tool_overrides' && d.loc.length >= 2;
      });
      // Sortie 10: ["secret_ids", i] refusals show on the Tools tab's Secrets section.
      var secretItems = items.filter(function (d) {
        return d && Array.isArray(d.loc) && d.loc[0] === 'secret_ids';
      });
      var plain = err;
      if (toolItems.length || secretItems.length) {
        plain = { status: err.status, message: err.message, body: err.body,
          detail: items.filter(function (d) {
            return toolItems.indexOf(d) < 0 && secretItems.indexOf(d) < 0;
          }) };
      }
      if (secretItems.length) {
        setActiveTab('tools');
        var sd = currentData_();
        if (sd && sd.handle && sd.handle.secrets) {
          sd.handle.secrets.showError(secretItems.map(function (d) { return d.msg; }).join(' '));
        }
      }
      var fe = App.api.fieldErrors(plain, ['name']);
      setNameError_(fe.fields.name || null);
      var headerText = fe.text || '';
      if (plain !== err && !plain.detail.length) headerText = '';
      setEditorError_(headerText);
      if (fe.fields.name) {
        var input = editorEl.querySelector('#studio-name');
        if (input) input.focus();
      }
      if (toolItems.length) {
        showToolOverrideErrors_(toolItems, headerText, !!fe.fields.name);
      }
    }

    // Select the Built-in tools tab, open each refused tool's panel and put the
    // server's sentence on its field (focus on the first). A refusal with no field
    // (an unknown tool) or no panel to open goes in the header with the rest.
    function showToolOverrideErrors_(items, headerText, nameFocused) {
      // Still the same mount (a tab switch below may re-sync the URL, which must not
      // count as a rebuild).
      var tok = currentData_() ? currentData_().token : null;
      function guard() {
        var c = slot.current();
        return !!c && c.token === tok;
      }
      var sentences = [];
      var placed = [];
      function sentence(msg) {
        var t = String(msg == null ? '' : msg).trim();
        return /[.!?]$/.test(t) ? t : t + '.';
      }
      var wantsTab = items.some(function (d) { return d.loc.length >= 3; });
      if (wantsTab) setActiveTab('tools');
      var tab = toolsTab_();
      var jobs = items.map(function (d) {
        var tool = d.loc[1];
        var field = d.loc[2];
        if (field === undefined || !tab) {
          sentences.push(sentence(d.msg));
          return Promise.resolve();
        }
        return tab.openTool(tool).then(function () {
          var byField = tab.fieldHandles()[tool] || {};
          var handle = byField[field];
          if (!handle) {
            sentences.push(sentence(d.msg));
            return;
          }
          handle.setError(d.msg);
          placed.push(handle);
        }, function () {
          sentences.push(sentence(d.msg));
        });
      });
      Promise.all(jobs).then(function () {
        if (!guard()) return;
        if (sentences.length) {
          setEditorError_((headerText ? headerText + ' ' : '') + sentences.join(' '));
        }
        if (placed.length && !nameFocused) placed[0].focus();
      });
    }

    return { onSaveError: onSaveError_ };
  }

  window.App.studio.agentEditorSaveErrors = { create: create };
})();
