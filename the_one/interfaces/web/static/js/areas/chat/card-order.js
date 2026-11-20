// App.chat.cardOrder -- where a transcript card sits (M36 F3 L6, the shared order of the GleepGlorp
// proposal cards and the form-fill receipts).
//
// A card is a direct child of the message log, drawn after the work group of the turn that made it
// (the group holding its `tool_call_id`) and after the last node of that turn. Within the turn, cards
// are ordered by:
//   1. the DOM position of the tool call that made each ([data-tool-call-id] in the log),
//   2. then `created_at`,
//   3. then kind and id.
// A card with no tool call id, or whose tool call is not in the log, is appended after everything
// (the anchored ones come first). One module, so the two kinds of card never disagree.
//
// A card carries `data-card-kind`, `data-card-id`, `data-card-created` and `data-card-call` (never
// `data-tool-call-id`, which marks the tool call itself).
//
// Exposes: mark(el, info), place(messagesEl, el, info), compare(messagesEl, a, b).
//   info: { kind, id, createdAt, toolCallId }
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function mark(el, info) {
    el.setAttribute('data-card-kind', String(info.kind));
    el.setAttribute('data-card-id', String(info.id));
    el.setAttribute('data-card-created', info.createdAt || '');
    el.setAttribute('data-card-call', info.toolCallId || '');
  }

  function infoOf(node) {
    return {
      kind: node.getAttribute('data-card-kind'),
      id: Number(node.getAttribute('data-card-id')),
      createdAt: node.getAttribute('data-card-created') || '',
      toolCallId: node.getAttribute('data-card-call') || ''
    };
  }

  // The index of the tool call among the log's tool-call nodes, or Infinity when it is not there.
  function position(messagesEl, toolCallId) {
    if (!toolCallId) return Infinity;
    var found = messagesEl.querySelectorAll('[data-tool-call-id]');
    for (var i = 0; i < found.length; i++) {
      if (found[i].getAttribute('data-tool-call-id') === toolCallId) return i;
    }
    return Infinity;
  }

  function compare(messagesEl, a, b) {
    var pa = position(messagesEl, a.toolCallId);
    var pb = position(messagesEl, b.toolCallId);
    if (pa !== pb) return pa < pb ? -1 : 1;
    var ca = a.createdAt || '';
    var cb = b.createdAt || '';
    if (ca !== cb) return ca < cb ? -1 : 1;
    if (a.kind !== b.kind) return a.kind < b.kind ? -1 : 1;
    return a.id - b.id;
  }

  // The work group of the turn that made the tool call, or null (trimmed history, no id).
  function anchorGroup(messagesEl, toolCallId) {
    if (!toolCallId) return null;
    var found = messagesEl.querySelectorAll('[data-tool-call-id]');
    for (var i = 0; i < found.length; i++) {
      if (found[i].getAttribute('data-tool-call-id') !== toolCallId) continue;
      var group = found[i].closest('[data-testid="turn-work"]');
      if (group && group.parentNode === messagesEl) return group;
    }
    return null;
  }

  function isBoundary(messagesEl, node, info) {
    if (node.nodeType !== 1) return false;
    if (node.getAttribute('data-role') === 'user') return true;
    var tid = node.getAttribute('data-testid');
    if (tid === 'turn-work' || tid === 'chat-approval-line') return true;
    if (node.hasAttribute('data-card-kind')) return compare(messagesEl, infoOf(node), info) > 0;
    return false;
  }

  function place(messagesEl, el, info) {
    var group = anchorGroup(messagesEl, info.toolCallId);
    var ref = null;
    if (group) {
      ref = group.nextSibling;
      while (ref && !isBoundary(messagesEl, ref, info)) ref = ref.nextSibling;
    }
    messagesEl.insertBefore(el, ref);
  }

  window.App.chat.cardOrder = { mark: mark, place: place, compare: compare };
})();
