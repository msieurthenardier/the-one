// WebKitGTK probe setup script (M25 F1 L2): mounts a factory list pane (with
// filter and groups), a button and a field into #ui-probe-root, appended to
// <body> outside the app shell so the router never re-renders it. Evaluated
// verbatim by scripts/webkitgtk_probe.py (--setup-script) and by the Playwright
// contract test test_probe_mount_script_mounts_and_resolves. Statements only;
// the caller appends the trailing true.
var previous = document.getElementById('ui-probe-root');
if (previous) previous.remove();
var probeRoot = document.createElement('div');
probeRoot.id = 'ui-probe-root';
document.body.appendChild(probeRoot);
var pane = App.ui.listPane({
  title: 'Probe list',
  filter: { label: 'Filter probe list', placeholder: 'Filter' },
  selectedId: 'b',
  emptyText: 'Nothing matches',
  groups: [
    { label: 'First group', items: [
      { id: 'a', label: 'Alpha', meta: 'one', href: '#probe-a', icon: 'plus' },
      { id: 'b', label: 'Beta', meta: 'two', href: '#probe-b' }
    ] },
    { label: 'Second group', items: [
      { id: 'c', label: 'Gamma', meta: 'three', onSelect: function () {}, badges: ['3'] }
    ] }
  ]
});
probeRoot.appendChild(pane.el);
probeRoot.appendChild(App.ui.button({ label: 'Probe action', variant: 'primary', icon: 'plus' }));
var probeField = App.ui.field({
  label: 'Probe name',
  control: App.ui.textInput({}),
  hint: 'A hint',
  error: 'An error'
});
probeRoot.appendChild(probeField.el);
// M25 F1 L4 controls: textarea, select, a checkbox in all three states, a toggle
// in both states, a badge of two kinds, both empty-state sizes, and a list pane
// whose rows carry kinded badges and counts.
probeRoot.appendChild(
  App.ui.field({ label: 'Probe notes', control: App.ui.textarea({ value: 'Some text' }), hint: 'Notes hint' }).el
);
probeRoot.appendChild(
  App.ui.field({
    label: 'Probe kind',
    control: App.ui.select({
      options: [
        { value: 'a', label: 'Option A' },
        { label: 'Group', options: [{ value: 'b', label: 'Option B' }] }
      ],
      value: 'b'
    })
  }).el
);
probeRoot.appendChild(App.ui.checkbox({ label: 'Probe unchecked', hint: 'Checkbox hint' }).el);
probeRoot.appendChild(App.ui.checkbox({ label: 'Probe checked', checked: true }).el);
probeRoot.appendChild(App.ui.checkbox({ label: 'Probe mixed', indeterminate: true }).el);
probeRoot.appendChild(App.ui.toggle({ label: 'Probe toggle off', hint: 'Toggle hint' }).el);
probeRoot.appendChild(App.ui.toggle({ label: 'Probe toggle on', checked: true }).el);
probeRoot.appendChild(App.ui.badge({ text: 'ollama', kind: 'ollama' }));
probeRoot.appendChild(App.ui.badge({ text: 'approved', kind: 'ollama' }));
probeRoot.appendChild(App.ui.emptyState({ title: 'Probe inline empty', body: 'Nothing to show here' }));
probeRoot.appendChild(
  App.ui.emptyState({
    title: 'Probe pane empty',
    size: 'pane',
    icon: 'plus',
    action: App.ui.button({ label: 'Probe create', variant: 'primary' })
  })
);
var kindPane = App.ui.listPane({
  title: 'Probe kinded list',
  selectedId: 'k1',
  items: [
    { id: 'k1', label: 'Kinded one', meta: 'selected', href: '#probe-k1', badges: [{ text: 'web', kind: 'local' }, 'tag'], count: 4 },
    { id: 'k2', label: 'Kinded two', meta: 'idle', onSelect: function () {}, count: 9 }
  ]
});
probeRoot.appendChild(kindPane.el);
// M25 F1 L5 menu: one closed menu and one opened (its popup visible, so the probe
// resolves labels and contrast over the open state too).
probeRoot.appendChild(
  App.ui.menu({
    trigger: { label: 'Probe menu closed' },
    items: [{ label: 'Closed one', onSelect: function () {} }]
  }).el
);
var probeOpenMenu = App.ui.menu({
  trigger: { label: 'Probe menu open' },
  items: [
    { label: 'Open one', onSelect: function () {} },
    { label: 'Open locked', disabled: true, onSelect: function () {} },
    { label: 'Open danger', danger: true, icon: 'trash', onSelect: function () {} }
  ]
});
probeRoot.appendChild(probeOpenMenu.el);
probeOpenMenu.open('first');
