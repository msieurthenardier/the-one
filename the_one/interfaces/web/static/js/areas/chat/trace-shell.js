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
    if (count) {
      count.textContent = String(body.children.length);
    }
  }

  window.App.chat.renderTrace = renderTrace;
  window.App.chat.appendToTrace = appendToTrace;
})();
