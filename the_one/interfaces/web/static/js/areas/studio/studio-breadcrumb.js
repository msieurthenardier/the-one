// App.studio.breadcrumb -- the item header's breadcrumb link (M25 F3 L4b; DD2 refinement),
// split out of studio.js (squawk 0386). Reaches the shell only through ctx:
//   self, content, libraryPane,
//   agentsList()   call-time getter (the agents list handle)
//
// Every Agents and Library item header (the agent editor, the knowledge-base detail and
// `~new` form, the MCP and connector editors) shows "Agents" or "Library / {Group}" with
// its last segment a link to the destination or section root (`editor-breadcrumb-link`,
// built by each editor). With Back retired it is the visible way to close an item. A
// plain activation (a click, or Enter on the link) is routed here, ahead of App.nav's
// document-level interceptor: an intent go() to the root, so the router's guard asks once
// about a dirty editor and the root's hydrate closes the item (closeOpenItem). Once it has
// navigated, focus goes to the closed item's row (DD8); a create form has no row, so focus
// goes where Cancel on a create form sends it (the section's first row, else the list's
// primary action). The focus waits one task: after a Continue, nav.js focuses <main> from
// a setTimeout, and the row must land last. Modified clicks (new tab, etc.) keep the
// browser's behaviour.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var content = ctx.content;
    var libraryPane = ctx.libraryPane;

    function closingItem_() {
      var section = self._activeSection;
      var list = ctx.agentsList();
      return { section: section, rowId: section === 'agents' ? list.selection() : libraryPane.selection() };
    }

    function focusClosedItem_(closing) {
      var list = ctx.agentsList();
      // The user moved on: an Agents close must still be on Agents, a Library
      // close at the Library root (DD1) with nothing open.
      if (self._activeSection !== (closing.section === 'agents' ? 'agents' : 'library')) return;
      if (closing.section === 'agents') {
        if (!list.isOpen() || self._selectedAgent || self._createMode) return;
        list.focusNear(closing.rowId != null ? list.indexOf(closing.rowId) : 0);
        return;
      }
      if (!libraryPane.isOpen() || !libraryPane.atRoot()) return;
      if (closing.rowId != null) libraryPane.focusNear(libraryPane.rowIndex(closing.rowId));
      else libraryPane.focusGroupStart(closing.section);
    }

    function onBreadcrumbClick(e) {
      if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      var link = e.target && typeof e.target.closest === 'function'
        ? e.target.closest('a[data-testid="editor-breadcrumb-link"]') : null;
      if (!link || !content.contains(link)) return;
      e.preventDefault();
      var closing = closingItem_();
      App.router.go(link.getAttribute('href'), { opener: link }).then(function (navigated) {
        if (navigated) setTimeout(function () { focusClosedItem_(closing); }, 0);
      });
    }
    content.addEventListener('click', onBreadcrumbClick);
  }

  window.App.studio.breadcrumb = { create: create };
})();
