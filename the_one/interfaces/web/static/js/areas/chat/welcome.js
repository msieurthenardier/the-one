(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // `href` is a router href (App.router.href), e.g. '#settings/providers'.
  function welcomeLink(text, href) {
    var a = document.createElement('a');
    a.className = 'chat-welcome-link';
    a.href = href;
    a.textContent = text;
    return a;
  }

  // Renders the welcome canvas based on current setup + agents state.
  // Four states: no providers (& maybe no agents), no agents only,
  // ready-with-agents (full picker), and "no agents in fetch but live"
  // (rare race: setupState says agents exist but availableAgents is empty).
  function renderWelcomeList(welcomeEl, welcomeListEl, agents, setupState, callbacks) {
    var promptEl = welcomeEl.querySelector('.chat-welcome-prompt');
    welcomeListEl.innerHTML = '';

    // Setup-incomplete states — show a guidance line, no agent picker.
    if (!setupState.hasProviders || !setupState.hasAgents) {
      promptEl.hidden = true;
      // Drop the listbox role when there are no options to pick.
      welcomeListEl.removeAttribute('role');
      welcomeListEl.removeAttribute('aria-label');
      var guidance = document.createElement('p');
      guidance.className = 'chat-welcome-guidance';
      if (!setupState.hasProviders && !setupState.hasAgents) {
        guidance.appendChild(document.createTextNode('Add a provider in '));
        guidance.appendChild(welcomeLink('Settings', App.router.href({ destination: 'settings', section: 'providers' })));
        guidance.appendChild(document.createTextNode(', then create an agent in '));
        guidance.appendChild(welcomeLink('Agents', App.router.href({ destination: 'agents' })));
        guidance.appendChild(document.createTextNode(' to start chatting.'));
      } else if (!setupState.hasProviders) {
        guidance.appendChild(document.createTextNode('Add a provider in '));
        guidance.appendChild(welcomeLink('Settings', App.router.href({ destination: 'settings', section: 'providers' })));
        guidance.appendChild(document.createTextNode(' to start chatting.'));
      } else {
        guidance.appendChild(document.createTextNode('Create an agent in '));
        guidance.appendChild(welcomeLink('Agents', App.router.href({ destination: 'agents' })));
        guidance.appendChild(document.createTextNode(' to start chatting.'));
      }
      welcomeListEl.appendChild(guidance);
      return;
    }

    // Ready state — show the agent picker.
    promptEl.hidden = false;
    welcomeListEl.setAttribute('role', 'listbox');
    welcomeListEl.setAttribute('aria-label', 'Available agents');
    for (var i = 0; i < agents.length; i++) {
      (function (agent, idx) {
        var opt = document.createElement('div');
        opt.className = 'chat-welcome-item';
        opt.setAttribute('role', 'option');
        opt.setAttribute('tabindex', idx === 0 ? '0' : '-1');
        opt.setAttribute('aria-selected', 'false');
        opt.dataset.agentName = agent.name;

        var nameEl = document.createElement('span');
        nameEl.className = 'chat-welcome-item-name';
        nameEl.textContent = agent.name;
        opt.appendChild(nameEl);

        var metaBits = [];
        if (agent.model) metaBits.push(agent.model);
        if (agent.provider) metaBits.push(agent.provider);
        if (metaBits.length) {
          var metaEl = document.createElement('span');
          metaEl.className = 'chat-welcome-item-meta';
          metaEl.textContent = metaBits.join(' · ');
          opt.appendChild(metaEl);
        }

        opt.addEventListener('click', function () { callbacks.onStart(agent.name); });
        opt.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            callbacks.onStart(agent.name);
          }
        });
        welcomeListEl.appendChild(opt);
      })(agents[i], i);
    }
  }

  window.App.chat.welcomeLink = welcomeLink;
  window.App.chat.renderWelcomeList = renderWelcomeList;
})();
