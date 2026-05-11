(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // MARKDOWN section is a passive consumer of App.markdown.render(text)
  // per markdown.js:6. The helper returns a DocumentFragment that ALREADY
  // contains the <div class="markdown-code-wrap"><pre><code>…</code></pre>
  // <button class="markdown-copy-btn">…</button></div> structure including
  // the click-to-copy handler (markdown.js:753-790). The section MUST NOT
  // re-implement any of this — mount via host.appendChild(...) matching
  // the existing consumer pattern at message-bubble.js:28.
  function render(host) {
    var sample = [
      'Sample markdown showing a paragraph and a fenced code block. Hover',
      'the code block to reveal the copy button (top-right corner).',
      '',
      '```js',
      '// Example: register a section module',
      'window.App.admin.designLanguage.exampleSection = {',
      '  render: function (host) {',
      '    host.innerHTML = \'<p>hello design language</p>\';',
      '  }',
      '};',
      '```',
      '',
      'A trailing paragraph rounds out the sample so the markdown helper',
      'shows both inline rendering and code-fence treatment.'
    ].join('\n');

    if (window.App && window.App.markdown && typeof window.App.markdown.render === 'function') {
      host.appendChild(window.App.markdown.render(sample));
    } else {
      host.textContent = '[App.markdown.render is unavailable]';
    }
  }

  window.App.admin.designLanguage.markdownSection = { render: render };
})();
