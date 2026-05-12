(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // Type ladder, descending in size. Each entry maps a size token to its
  // human-readable label. Operators see "display 24px" rendered AT that
  // size so the ladder is self-documenting.
  var SIZE_TOKENS = [
    { token: '--font-size-display',  label: 'display' },
    { token: '--font-size-h1',       label: 'h1' },
    { token: '--font-size-h2',       label: 'h2' },
    { token: '--font-size-h3',       label: 'h3' },
    { token: '--font-size-body-lg',  label: 'body-lg' },
    { token: '--font-size-body',     label: 'body' },
    { token: '--font-size-body-sm',  label: 'body-sm' },
    { token: '--font-size-caption',  label: 'caption' },
    { token: '--font-size-tiny',     label: 'tiny' }
  ];

  var SAMPLE_TEXT = 'The quick brown fox';

  function render(host) {
    var rootStyle = window.getComputedStyle(document.documentElement);

    for (var i = 0; i < SIZE_TOKENS.length; i++) {
      var entry = SIZE_TOKENS[i];
      var value = rootStyle.getPropertyValue(entry.token).trim();

      var row = document.createElement('div');
      row.style.display = 'flex';
      row.style.alignItems = 'baseline';
      row.style.gap = '16px';

      var sample = document.createElement('span');
      sample.style.fontSize = 'var(' + entry.token + ')';
      sample.textContent = SAMPLE_TEXT;

      var labelEl = document.createElement('span');
      labelEl.style.fontFamily = 'var(--font-family-mono)';
      labelEl.style.fontSize = 'var(--font-size-tiny)';
      labelEl.style.color = 'var(--fg-muted)';
      labelEl.textContent = entry.label + ' ' + value;

      row.appendChild(sample);
      row.appendChild(labelEl);
      host.appendChild(row);
    }

    // Mono variants — body + body-sm in mono font
    var monoBody = document.createElement('div');
    monoBody.style.display = 'flex';
    monoBody.style.alignItems = 'baseline';
    monoBody.style.gap = '16px';
    monoBody.style.marginTop = '12px';

    var monoBodySample = document.createElement('span');
    monoBodySample.style.fontFamily = 'var(--font-family-mono)';
    monoBodySample.style.fontSize = 'var(--font-size-body)';
    monoBodySample.textContent = SAMPLE_TEXT;

    var monoBodyLabel = document.createElement('span');
    monoBodyLabel.style.fontFamily = 'var(--font-family-mono)';
    monoBodyLabel.style.fontSize = 'var(--font-size-tiny)';
    monoBodyLabel.style.color = 'var(--fg-muted)';
    monoBodyLabel.textContent = 'mono body';
    monoBody.appendChild(monoBodySample);
    monoBody.appendChild(monoBodyLabel);
    host.appendChild(monoBody);

    var monoSm = document.createElement('div');
    monoSm.style.display = 'flex';
    monoSm.style.alignItems = 'baseline';
    monoSm.style.gap = '16px';

    var monoSmSample = document.createElement('span');
    monoSmSample.style.fontFamily = 'var(--font-family-mono)';
    monoSmSample.style.fontSize = 'var(--font-size-body-sm)';
    monoSmSample.textContent = SAMPLE_TEXT;

    var monoSmLabel = document.createElement('span');
    monoSmLabel.style.fontFamily = 'var(--font-family-mono)';
    monoSmLabel.style.fontSize = 'var(--font-size-tiny)';
    monoSmLabel.style.color = 'var(--fg-muted)';
    monoSmLabel.textContent = 'mono body-sm';
    monoSm.appendChild(monoSmSample);
    monoSm.appendChild(monoSmLabel);
    host.appendChild(monoSm);
  }

  window.App.admin.designLanguage.typographySection = { render: render };
})();
