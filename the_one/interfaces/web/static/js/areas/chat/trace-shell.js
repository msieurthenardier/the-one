(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // Build a per-assistant-turn trace shell.
  //
  // Structure:
  //   <div class="trace-shell" data-parent-msg-id="..." data-testid="trace-shell">
  //     <details>
  //       <summary class="trace-toggle">
  //         <span class="trace-summary">Tool activity</span>
  //         <span class="trace-count" aria-hidden="true">0</span>
  //       </summary>
  //       <div class="trace-body"></div>
  //     </details>
  //   </div>
  //
  // Keyboard-operable for free via native <details>/<summary>.
  // `data-parent-msg-id` lets chat.js find an existing shell to append into.
  function renderTrace(parentMessageId) {
    var shell = document.createElement('div');
    shell.className = 'trace-shell';
    shell.dataset.parentMsgId = parentMessageId;
    shell.setAttribute('data-testid', 'trace-shell');
    var details = document.createElement('details');
    var summary = document.createElement('summary');
    summary.className = 'trace-toggle';
    var label = document.createElement('span');
    label.className = 'trace-summary';
    label.textContent = 'Tool activity';
    var count = document.createElement('span');
    count.className = 'trace-count';
    count.setAttribute('aria-hidden', 'true');
    count.textContent = '0';
    summary.appendChild(label);
    summary.appendChild(count);
    // F2 Leg 2 (A.11): wire the count into the summary's accessible
    // name so SR users hear "Tool activity, 0 items" instead of just
    // "Tool activity" (the visible count span is aria-hidden so we
    // need an aria-label to carry the count semantically). Updated
    // by appendToTrace below.
    summary.setAttribute('aria-label', 'Tool activity, 0 items');
    var body = document.createElement('div');
    body.className = 'trace-body';
    details.appendChild(summary);
    details.appendChild(body);
    shell.appendChild(details);
    return shell;
  }

  // Append a tool message into a trace shell's body. Updates the count
  // shown in the summary. The msgEl is expected to be a .msg.tool element
  // (or .msg.tool.error) with data-testid="message" and a data-tool-call-id
  // attribute set by the caller.
  function appendToTrace(traceEl, msgEl) {
    if (!traceEl || !msgEl) return;
    var body = traceEl.querySelector('.trace-body');
    if (!body) return;
    body.appendChild(msgEl);
    var count = traceEl.querySelector('.trace-count');
    var n = body.children.length;
    if (count) {
      count.textContent = String(n);
    }
    // F2 Leg 2 (A.11): keep the summary's aria-label in lockstep with
    // the visible count so SR announcement reflects the current state
    // (visible count is aria-hidden — accessible name is the only SR
    // exposure of "how many tools fired").
    var summary = traceEl.querySelector('summary');
    if (summary) {
      summary.setAttribute('aria-label', 'Tool activity, ' + n + ' ' + (n === 1 ? 'item' : 'items'));
    }
  }

  // M16 F10 L05: build a per-assistant-turn thinking disclosure.
  //
  // Structure:
  //   <details class="thinking-disclosure" data-testid="thinking-disclosure">
  //     <summary class="thinking-toggle">Thinking</summary>
  //     <div class="thinking-body">…reasoning text…</div>
  //   </details>
  //
  // Collapsed by default (no `open` attribute); native <details>/<summary>
  // gives keyboard focus + Enter/Space toggle for free. This is a DISTINCT
  // identifier from the ephemeral loading spinner (.msg.assistant.thinking /
  // createThinking/removeThinking) — do NOT conflate the two.
  //
  // Position-independent by design (mirrors getOrCreateTrace, which appends to
  // messagesEl without a preceding bubble): the caller appends the returned
  // node in stream order. Criterion #1's turn (thinking + tool call, empty
  // content) emits a thinking event with NO preceding assistant bubble, so this
  // must not depend on "the last assistant bubble." It is its own disclosure —
  // NOT routed through getOrCreateTrace (that would nest it in the tool trace).
  //
  // Tolerates both event shapes: the live event is {type,content} (no
  // parent_message_id/vis); the replayed event adds parent_message_id + vis.
  // Missing keys must not throw.
  function renderThinking(evt) {
    evt = evt || {};
    var details = document.createElement('details');
    details.className = 'thinking-disclosure';
    details.setAttribute('data-testid', 'thinking-disclosure');
    if (evt.parent_message_id != null) {
      details.dataset.parentMsgId = evt.parent_message_id;
    }
    var summary = document.createElement('summary');
    summary.className = 'thinking-toggle';
    summary.textContent = 'Thinking';
    var body = document.createElement('div');
    body.className = 'thinking-body';
    body.textContent = evt.content != null ? evt.content : '';
    details.appendChild(summary);
    details.appendChild(body);
    return details;
  }

  window.App.chat.renderTrace = renderTrace;
  window.App.chat.appendToTrace = appendToTrace;
  window.App.chat.renderThinking = renderThinking;
})();
