(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function welcomeLink(text, areaId) {
    var a = document.createElement('a');
    a.className = 'chat-welcome-link';
    a.href = '#' + areaId;
    a.textContent = text;
    return a;
  }

  // Renders the empty-state agent picker (or setup-guidance) directly into
  // the container element (typically .convo-stream). Replaces container
  // content on each call.
  //
  // Four states:
  //   (a) !hasProviders && !hasAgents → guidance: admin/providers + studio
  //   (b) !hasProviders (agents may exist) → guidance: admin/providers
  //   (c) hasProviders && !hasAgents → guidance: studio
  //   (d) ready → agent picker cards
  //
  // Signature: renderWelcomeList(container, agents, setupState, callbacks)
  //   container   — DOM element to write into (.convo-stream)
  //   agents      — array of agent objects {name, model, provider}
  //   setupState  — { hasProviders: bool, hasAgents: bool }
  //   callbacks   — { onStart(agentName) }
  function renderWelcomeList(container, agents, setupState, callbacks) {
    container.innerHTML = '';

    var wrapper = document.createElement('div');
    wrapper.className = 'chat-empty-state';
    wrapper.setAttribute('data-testid', 'chat-welcome');

    var heading = document.createElement('h2');
    heading.className = 'chat-empty-title';
    heading.textContent = 'Hello.';
    wrapper.appendChild(heading);

    // Setup-incomplete states — guidance paragraph, no agent picker.
    if (!setupState.hasProviders || !setupState.hasAgents) {
      var guidance = document.createElement('p');
      guidance.className = 'chat-empty-guidance';

      if (!setupState.hasProviders && !setupState.hasAgents) {
        guidance.appendChild(document.createTextNode('Add a provider in '));
        guidance.appendChild(welcomeLink('LLM Settings', 'admin/providers'));
        guidance.appendChild(document.createTextNode(', then create an agent in '));
        guidance.appendChild(welcomeLink('Agent Studio', 'studio'));
        guidance.appendChild(document.createTextNode(' to start chatting.'));
      } else if (!setupState.hasProviders) {
        guidance.appendChild(document.createTextNode('Add a provider in '));
        guidance.appendChild(welcomeLink('LLM Settings', 'admin/providers'));
        guidance.appendChild(document.createTextNode(' to start chatting.'));
      } else {
        guidance.appendChild(document.createTextNode('Create an agent in '));
        guidance.appendChild(welcomeLink('Agent Studio', 'studio'));
        guidance.appendChild(document.createTextNode(' to start chatting.'));
      }

      wrapper.appendChild(guidance);
      container.appendChild(wrapper);
      return;
    }

    // Ready state — agent picker.
    var sub = document.createElement('p');
    sub.className = 'chat-empty-sub';
    sub.textContent = 'Which agent would you like to chat with?';
    wrapper.appendChild(sub);

    var listEl = document.createElement('div');
    listEl.className = 'chat-empty-list';
    listEl.setAttribute('role', 'listbox');
    listEl.setAttribute('aria-label', 'Available agents');

    for (var i = 0; i < agents.length; i++) {
      (function (agent, idx) {
        var card = document.createElement('div');
        card.className = 'chat-agent-card';
        card.setAttribute('role', 'option');
        card.setAttribute('tabindex', idx === 0 ? '0' : '-1');
        card.setAttribute('aria-selected', 'false');
        card.dataset.agentName = agent.name;

        var nameEl = document.createElement('span');
        nameEl.className = 'chat-agent-card-name';
        nameEl.textContent = agent.name;
        card.appendChild(nameEl);

        var metaBits = [];
        if (agent.model) metaBits.push(agent.model);
        if (agent.provider) metaBits.push(agent.provider);
        if (metaBits.length) {
          var metaEl = document.createElement('span');
          metaEl.className = 'chat-agent-card-meta';
          metaEl.textContent = metaBits.join(' · ');
          card.appendChild(metaEl);
        }

        card.addEventListener('click', function () { callbacks.onStart(agent.name); });
        card.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            callbacks.onStart(agent.name);
          }
          // Roving tabindex arrow navigation within .chat-empty-list.
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End') {
            e.preventDefault();
            var opts = listEl.querySelectorAll('.chat-agent-card');
            if (!opts.length) return;
            var cur = -1;
            for (var j = 0; j < opts.length; j++) { if (opts[j] === card) { cur = j; break; } }
            var next;
            if (e.key === 'Home') next = 0;
            else if (e.key === 'End') next = opts.length - 1;
            else if (e.key === 'ArrowDown') next = (cur + 1) % opts.length;
            else next = (cur - 1 + opts.length) % opts.length;
            for (var k = 0; k < opts.length; k++) opts[k].setAttribute('tabindex', k === next ? '0' : '-1');
            opts[next].focus();
          }
        });

        listEl.appendChild(card);
      })(agents[i], i);
    }

    wrapper.appendChild(listEl);
    container.appendChild(wrapper);
  }

  window.App.chat.welcomeLink = welcomeLink;
  window.App.chat.renderWelcomeList = renderWelcomeList;
})();
