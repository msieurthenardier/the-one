// App.mcpErrorMessage / App.buildMcpError - plain-words MCP connection errors
// (M25 F6 DD19). Shared by the agent MCPs tab and the Library MCP editor, so they
// live in their own module (squawk 0128) loaded before both.
(function () {
  'use strict';

  // DD19: plain-words MCP connection errors. The API returns
  // "{ExceptionClass}: {message}"; the UI shows a plain headline and keeps the
  // raw text, unchanged, under a collapsed "Technical details".
  function mcpErrorMessage(raw) {
    var text = (raw === null || raw === undefined) ? '' : String(raw);
    var cls = (/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:/.exec(text) || [])[1] || '';
    var headline;
    if (/^(fetchMcpSourceTools: HTTP|Server error)\b/.test(text.trim())) {
      headline = "The app couldn't check this server (the request failed).";
    } else if (cls === 'MCPCredentialsRejected') {
      headline = 'The server rejected the configured credentials. ' +
        'Check the headers on this MCP server.';
    } else if (cls === 'MCPConnectionError' && /did not respond within/.test(text)) {
      headline = "The server didn't respond in time. Check that it's running, then try Refresh.";
    } else if (cls === 'MCPConnectionError') {
      headline = "Couldn't connect to this server. Check that it's running and that its " +
        'address and key are right, then try Refresh.';
    } else if (cls === 'MCPVersionMismatch') {
      headline = "This server uses a protocol version the app doesn't support.";
    } else if (cls === 'MCPCapabilityMissing') {
      headline = "This server doesn't offer the tools capability.";
    } else if (cls === 'SandboxError') {
      headline = "The server couldn't start in its sandbox.";
    } else {
      headline = "Couldn't load this server's tools.";
    }
    return { headline: headline, detail: text };
  }

  // Builds the headline-plus-details block; callers set the root's testid.
  function buildMcpError(raw) {
    var msg = mcpErrorMessage(raw);
    var root = document.createElement('div');
    root.className = 'mcp-tools-error';
    // WCAG 4.1.3: announced when inserted; each build is a fresh node, so
    // unrelated re-renders that don't rebuild it stay silent.
    root.setAttribute('role', 'alert');
    var head = document.createElement('div');
    head.className = 'mcp-error-headline';
    head.textContent = msg.headline;
    root.appendChild(head);
    if (msg.detail.trim()) {
      var details = document.createElement('details');
      details.className = 'mcp-error-details';
      var summary = document.createElement('summary');
      summary.textContent = 'Technical details';
      var pre = document.createElement('pre');
      pre.className = 'mcp-error-raw';
      pre.setAttribute('data-testid', 'mcp-error-raw');
      pre.textContent = msg.detail;
      details.appendChild(summary);
      details.appendChild(pre);
      root.appendChild(details);
    }
    return root;
  }

  window.App = window.App || {};
  window.App.mcpErrorMessage = mcpErrorMessage;
  window.App.buildMcpError = buildMcpError;
})();
