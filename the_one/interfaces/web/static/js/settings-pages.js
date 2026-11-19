// App.settingsPages -- the one Settings page table (M25 F4 L7, flight DD10, leg AC9).
//
// A plain data table with no dependencies, loaded BEFORE router.js. Three
// readers, none of which keeps its own copy of these labels:
//   - the Settings nav (areas/admin.js builds its App.ui.navGroups from it);
//   - the router (router.js builds the Settings labels its announcer and the
//     document title speak, lazily, inside describeRoute);
//   - the jump-to palette (jump-to.js lists every visible page).
//
// Each row is {section, label, group}, in nav order:
//   section  the ROUTE segment as the router knows it (`#settings/{section}`),
//            never the admin area's internal category id (the Knowledge
//            indexing page is `knowledge-indexing` here, `knowledge` inside
//            admin.js). Build the link with
//            App.router.href({destination: 'settings', section: section}).
//   label    the page's name (the nav item, the router's spoken label, the
//            palette row).
//   group    the nav group it sits under (the palette's "Settings · {group}").
(function () {
  'use strict';
  window.App = window.App || {};

  var PAGES = [
    { section: 'gleepglorp', label: 'GleepGlorp', group: 'Assistant' },
    { section: 'appearance', label: 'Appearance', group: 'General' },
    { section: 'date-and-time', label: 'Date and time', group: 'General' },
    { section: 'prompts', label: 'Prompts', group: 'General' },
    { section: 'encryption', label: 'Encryption', group: 'General' },
    { section: 'tools', label: 'Built-in tools', group: 'Defaults for agents' },
    { section: 'knowledge-indexing', label: 'Knowledge indexing', group: 'Defaults for agents' }
  ];
  for (var i = 0; i < PAGES.length; i++) Object.freeze(PAGES[i]);

  window.App.settingsPages = Object.freeze(PAGES);
})();
