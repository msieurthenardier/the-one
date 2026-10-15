// App.consentLink - the sign-in link block for MCP sign-in (sortie 04, DD1).
//
// Shown in chat (the login-required group) and the MCP editor (the status
// panel) whenever a consent URL is known, whatever window.open returned: the
// desktop webview hands window.open to the system browser and returns null, so
// the link is the one path that always works. A read-only URL field, an
// "Open sign-in page" anchor (target=_blank, styled as a button), a Copy button
// and one helper line. DOM APIs only; classes consent-link-*; testids are
// literals per surface (one setAttribute per id) so the registry extractor sees them.
(function () {
  'use strict';

  var idSeq = 0;

  // Only http(s) addresses are ever shown as a link, opened or navigated to: the
  // consent URL comes from the MCP server's authorization endpoint.
  function isSafeUrl(url) {
    return typeof url === 'string' && /^https?:\/\//i.test(url);
  }

  // The element a keyboard user should land on when this block replaces the
  // control they were on: the open link, else the URL field, else the notice.
  function focusTarget(block) {
    if (!block) return null;
    return block.querySelector('.consent-link-open') ||
      block.querySelector('.consent-link-url') ||
      block.querySelector('.consent-link-unsafe');
  }

  function build(url, opts) {
    var surface = opts && opts.surface === 'mcp' ? 'mcp' : 'chat';
    var isMcp = surface === 'mcp';
    var sourceName = opts && opts.sourceName ? String(opts.sourceName) : '';

    var block = document.createElement('div');
    block.className = 'consent-link consent-link--' + surface;

    if (!isSafeUrl(url)) {
      var bad = document.createElement('p');
      bad.className = 'consent-link-help consent-link-unsafe';
      bad.tabIndex = -1;
      bad.textContent = "This server sent a sign-in address that isn't a web link, " +
        "so it can't be opened.";
      block.appendChild(bad);
      return block;
    }

    var row = document.createElement('div');
    row.className = 'consent-link-row';

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'field-input consent-link-url';
    input.readOnly = true;
    input.value = url;
    input.setAttribute('aria-label',
      sourceName ? 'Sign-in address for ' + sourceName : 'Sign-in page URL');
    if (isMcp) input.setAttribute('data-testid', 'mcp-consent-link-url');
    else input.setAttribute('data-testid', 'chat-consent-link-url');
    row.appendChild(input);

    var helpId = 'consent-help-' + (++idSeq);
    var open = document.createElement('a');
    open.className = 'btn-outlined-primary consent-link-open';
    open.href = url;
    open.target = '_blank';
    open.rel = 'noopener noreferrer';
    open.setAttribute('aria-describedby', helpId);
    open.appendChild(document.createTextNode('Open sign-in page'));
    var hint = document.createElement('span');
    hint.className = 'visually-hidden';
    hint.textContent = ' (opens in your browser)';
    open.appendChild(hint);
    if (isMcp) open.setAttribute('data-testid', 'mcp-consent-link-open');
    else open.setAttribute('data-testid', 'chat-consent-link-open');
    row.appendChild(open);

    var copy = document.createElement('button');
    copy.type = 'button';
    copy.className = 'btn-outlined-primary consent-link-copy';
    copy.textContent = 'Copy';
    if (isMcp) copy.setAttribute('data-testid', 'mcp-consent-link-copy');
    else copy.setAttribute('data-testid', 'chat-consent-link-copy');

    var live = document.createElement('span');
    live.className = 'visually-hidden consent-link-live';
    live.setAttribute('role', 'status');

    function announce(ok) {
      live.textContent = ok ? 'Link copied'
        : 'Copy failed — select the link and copy it';
      if (ok) {
        // Visual feedback only: the accessible name stays "Copy" so the
        // live region's "Link copied" is the one announcement.
        copy.setAttribute('aria-label', 'Copy');
        copy.textContent = 'Copied';
        setTimeout(function () {
          copy.textContent = 'Copy';
          copy.removeAttribute('aria-label');
        }, 2000);
      }
    }
    copy.addEventListener('click', function () {
      function fallbackCopy() {
        var ok = false;
        input.select();
        try { ok = !!document.execCommand('copy'); } catch (e) { ok = false; }
        announce(ok);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function () { announce(true); }, fallbackCopy);
      } else {
        fallbackCopy();
      }
    });
    row.appendChild(copy);
    block.appendChild(row);
    block.appendChild(live);

    var help = document.createElement('p');
    help.className = 'consent-link-help';
    help.id = helpId;
    help.textContent = "Finish signing in in the browser window. This page updates when you're done.";
    block.appendChild(help);

    return block;
  }

  window.App = window.App || {};
  window.App.consentLink = { build: build, isSafeUrl: isSafeUrl, focusTarget: focusTarget };
})();
