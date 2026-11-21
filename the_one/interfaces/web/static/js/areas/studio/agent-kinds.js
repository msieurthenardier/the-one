// The agent kinds of the GleepGlorp registry (M36 F4 L2, flight DD11): `agent`, `rule` and
// `routine`. They register here, where the Studio code they wrap lives, at the end of the Studio
// script block (after agents-list.js). Every call into App.studio.* is late-bound, so the spec
// works whatever the Studio init order is.
//
// All three record an approval under the agent's name, invalidate the `agents` store and link to
// the agent's page (a rule opens the Rules and notes tab, a routine the Routines tab). Only
// `agent` is fillable.
(function () {
  'use strict';
  window.App = window.App || {};

  var TABS = { rule: 'rules-and-notes', routine: 'routines' };

  function agentExists(name) {
    return App.store.get('agents', { force: true }).then(function (list) {
      return (list || []).some(function (a) { return a.name === name; });
    }, function () { return true; }); // unknown: do not call it gone
  }

  function openLink(kind) {
    return function (view) {
      if (!view.agent_name) return null;
      var spec = { destination: 'agents', id: view.agent_name };
      if (TABS[kind]) spec.tab = TABS[kind];
      return { spec: spec, text: 'Open agent', testid: 'proposal-open-agent' };
    };
  }

  function recordKey(kind) {
    return function (detail) {
      if (!detail || !detail.agent) return null;
      return { scope: 'agent', id: detail.agent, fields: TABS[kind] ? [kind === 'rule' ? 'rules' : 'routines'] : null };
    };
  }

  function labels(noun, withdrawnGone) {
    return {
      itemNoun: noun,
      editorUnavailable: 'The agent editor could not open.',
      targetGone: 'That agent no longer exists.',
      withdrawnGone: withdrawnGone
    };
  }

  var AGENT_GONE = function () { return 'the agent no longer exists.'; };

  var agentFill = {
    routeFor: function (view) {
      return view.action === 'create'
        ? { destination: 'agents', create: true }
        : { destination: 'agents', id: view.agent_name };
    },
    openKey: function (view) {
      return view.action === 'create' ? 'create' : 'edit:' + view.agent_name;
    },
    exists: function (view) { return agentExists(view.agent_name); },
    isOpen: function (key) { return App.studio.agentEditorFill.isOpen(key); },
    whenSettled: function (key) { return App.studio.agentEditorFill.whenSettled(key); },
    select: function () { App.studio.agentEditorFill.selectGeneral(); },
    beforeNavigate: function (view) {
      if (view.action === 'create') App.studio.agentsList.suppressNextCreateFocus();
    },
    afterNavigate: function () { App.studio.agentsList.clearCreateFocusSuppression(); },
    apply: function (view) { return App.studio.agentEditorFill.apply(view); }
  };

  App.gleepglorpKinds.register('agent', {
    labels: labels('agent', AGENT_GONE),
    openLink: openLink('agent'),
    store: 'agents',
    recordKey: recordKey('agent'),
    fill: agentFill
  });

  App.gleepglorpKinds.register('rule', {
    labels: labels('rule', function (view) {
      return view.action === 'change' ? 'the rule no longer exists.' : 'the agent no longer exists.';
    }),
    openLink: openLink('rule'),
    store: 'agents',
    recordKey: recordKey('rule')
  });

  App.gleepglorpKinds.register('routine', {
    labels: labels('routine', function (view) {
      return view.action === 'change' ? 'the routine no longer exists.' : 'the agent no longer exists.';
    }),
    openLink: openLink('routine'),
    store: 'agents',
    recordKey: recordKey('routine')
  });
})();
