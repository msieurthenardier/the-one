// App.studio.renderSecretsSection -- the agent editor's Tools-tab "Secrets" section
// (sortie 10, leg 3 part B, DD2). The Knowledge tab's twin: a toggle per secret, labelled
// with its name, then "{description} · N tool(s)". No keys and no tool names are shown.
//
//   var h = App.studio.renderSecretsSection(host, agent, allSecrets, callbacks)
//     host        -- a div the section fills (it is wiped on a rebuild)
//     agent       -- AgentConfig (null in create mode)
//     allSecrets  -- array of secret rows (GET /api/secrets, masked)
//     callbacks   -- { onChange, secretsLoaded }
//                    `secretsLoaded` is the explicit load-success flag (never inferred from
//                    the array: a populated array can be a stale cache after a failed refresh).
//   h = { setAgent(agent, opts), showError(text), destroy() }. Mounted once per agent
//   identity; setAgent patches each toggle from `agent.secret_ids` and rebuilds only when
//   the loaded flag or the set of secret ids changes. `opts` is
//   {allSecrets, secretsLoaded}.
//
// Save-flow selector (agent-form-data.js): [data-secret-toggle][data-secret-id]:checked ->
// secret_ids, gated on the root's data-secret-list-loaded="true" marker (set only when the
// load flag is true). Without it secret_ids is omitted from the PUT and the server keeps the
// stored grants (the kb_ids pattern).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function renderSecretsSection(host, agent, allSecrets, callbacks) {
    callbacks = callbacks || {};
    var ui = window.App.ui;
    var onChange = callbacks.onChange || function () {};
    var rows = {};   // secret id -> toggle handle
    var metaIds = {};   // secret id -> its meta text's element id
    var builtIds = null;
    var builtLoaded = null;
    var errorEl = null;

    function idsOf(list) {
      var out = [];
      for (var i = 0; i < (list || []).length; i++) out.push(list[i].id);
      return out.join('\n');
    }

    // The error is a permanent live region (never hidden): it only changes text, so a
    // screen reader announces it. While it shows, each switch also references it.
    function clearError() {
      if (!errorEl) return;
      errorEl.set('idle', '');
      Object.keys(rows).forEach(function (id) { describe(id, false); });
    }

    function describe(id, withError) {
      var ids = [metaIds[id]];
      if (withError && errorEl) ids.push(errorEl.el.id);
      rows[id].control.setAttribute('aria-describedby', ids.join(' '));
    }

    function patchRows(a) {
      var granted = {};
      var ids = (a && a.secret_ids) || [];
      for (var i = 0; i < ids.length; i++) granted[ids[i]] = true;
      Object.keys(rows).forEach(function (id) { rows[id].setChecked(granted[id] === true); });
    }

    function build(a, secrets, loaded) {
      host.textContent = '';
      rows = {};
      metaIds = {};
      errorEl = null;
      builtIds = idsOf(secrets);
      builtLoaded = loaded;

      var root = document.createElement('div');
      root.className = 'agent-secrets-section';
      root.setAttribute('data-testid', 'agent-secrets-root');
      host.appendChild(root);

      var intro = document.createElement('p');
      intro.className = 'admin-pf-models-help';
      intro.setAttribute('data-testid', 'agent-secrets-intro');
      intro.textContent = 'Secrets this agent can pass to its tools. It never sees their values. ' +
        'Manage them in Library › Secrets.';
      root.appendChild(intro);

      if (!loaded) {
        var err = ui.status({ testid: 'agent-secrets-load-error' });
        err.set('danger',
          'Couldn’t load secrets. Saving will leave this agent’s secrets unchanged.');
        root.appendChild(err.el);
        return;
      }
      root.setAttribute('data-secret-list-loaded', 'true');

      errorEl = ui.status({ testid: 'agent-secrets-error', led: false, textTone: true });
      errorEl.el.id = ui.util.uid('secerr');
      root.appendChild(errorEl.el);

      if (!secrets || secrets.length === 0) {
        var link = document.createElement('a');
        link.href = App.router.href({ destination: 'library' });
        link.textContent = 'Create one in the Library.';
        root.appendChild(ui.emptyState({
          title: 'No secrets yet.',
          titleTag: 'p',
          action: link,
          testid: 'agent-secrets-empty-state'
        }));
        return;
      }

      var listEl = document.createElement('div');
      listEl.className = 'agent-knowledge-list';
      listEl.setAttribute('data-testid', 'agent-secrets-list');
      listEl.setAttribute('role', 'group');
      if (callbacks.headingId) listEl.setAttribute('aria-labelledby', callbacks.headingId);
      else listEl.setAttribute('aria-label', 'Secrets');
      root.appendChild(listEl);

      secrets.forEach(function (s) {
        var row = document.createElement('div');
        row.className = 'agent-knowledge-row';
        row.setAttribute('data-testid', 'agent-secret-row-' + s.id);
        row.setAttribute('data-secret-id', s.id);

        var toggle = ui.toggle({
          label: s.name,
          dataset: { secretToggle: '', secretId: s.id },
          testid: 'agent-secret-toggle-' + s.id,
          onChange: function () { clearError(); onChange(); }
        });
        row.appendChild(toggle.el);

        var n = (s.allowed_tools || []).length;
        var text = document.createElement('span');
        text.className = 'agent-knowledge-row-tool-name agent-secret-row-meta';
        text.id = ui.util.uid('secmeta');
        text.setAttribute('data-testid', 'agent-secret-meta-' + s.id);
        text.textContent = (s.description ? s.description + ' · ' : '') +
          n + (n === 1 ? ' tool' : ' tools');
        metaIds[s.id] = text.id;
        row.appendChild(text);

        rows[s.id] = toggle;
        describe(s.id, false);
        listEl.appendChild(row);
      });
      patchRows(a);
    }

    build(agent, allSecrets, callbacks.secretsLoaded === true);

    return {
      setAgent: function (a, opts) {
        var secrets = allSecrets;
        var loaded = callbacks.secretsLoaded === true;
        if (opts) {
          if (opts.allSecrets !== undefined) secrets = opts.allSecrets;
          if (opts.secretsLoaded !== undefined) loaded = opts.secretsLoaded === true;
        }
        allSecrets = secrets;
        callbacks.secretsLoaded = loaded;
        if (loaded !== builtLoaded || idsOf(secrets) !== builtIds) {
          build(a, secrets, loaded);
          return;
        }
        clearError();
        patchRows(a);
      },
      // A 422 on ["secret_ids", i]: shown on the section.
      showError: function (text) {
        if (!errorEl) return;
        errorEl.set('danger', text);
        Object.keys(rows).forEach(function (id) { describe(id, true); });
      },
      destroy: function () { host.textContent = ''; rows = {}; errorEl = null; }
    };
  }

  window.App.studio.renderSecretsSection = renderSecretsSection;
})();
