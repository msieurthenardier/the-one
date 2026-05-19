(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // Holograph (Mission-09 / L4.1) empty-state renderer.
  //
  // Three states drive the first-run flow:
  //   (1) No provider, no agent      → eyebrow IDLE, step01 .next, step02 unmarked
  //   (2) Provider, no agent         → eyebrow IDLE, step01 .done, step02 .next
  //   (3) Agent ready, no session    → eyebrow READY, no step cards (just headline)
  //
  // When state (3) is active on the *first* list_sessions response for a tab
  // (i.e. first visit to Chat after a provider+agent exist but before any
  // ChatSession was created), chat.js auto-defaults a session via WS
  // `new_session` (picking availableAgents[0]) and joins it with a subtle
  // App.toast. This eliminates the "Ready when you are" dead-end for seeded
  // fresh DBs (the verification pain point). The one-time `initialListProcessed`
  // flag keeps behavior for deliberate zero-session users (delete last →
  // welcome state; reload after delete does create a fresh default, which is
  // friendlier than an empty list forever).
  //
  // Renders into `container` (typically .convo-stream). Replaces content on
  // each call. Built via DOM APIs only (no innerHTML) — content is static
  // strings, but we follow the same hardened pattern as the prior welcome.js
  // for consistency and to satisfy the project's XSS hook.
  //
  // Signature: renderWelcomeList(container, agents, setupState, callbacks)
  //   container   — DOM element to write into (.convo-stream)
  //   agents      — array of agent objects (unused in L4.1; back-compat)
  //   setupState  — { hasProviders: bool, hasAgents: bool }
  //   callbacks   — { onStart(agentName) } (unused in empty states)
  function renderWelcomeList(container, agents, setupState, callbacks) {
    while (container.firstChild) container.removeChild(container.firstChild);

    var hasProvider = !!setupState.hasProviders;
    var hasAgent = !!setupState.hasAgents;

    // Step states.
    var step1State = hasProvider ? 'done' : 'next';
    var step2State = hasAgent ? 'done' : (hasProvider ? 'next' : '');
    var step1Prefix = hasProvider ? '✓ STEP 01' : 'STEP 01';
    var step2Prefix = hasAgent ? '✓ STEP 02' : 'STEP 02';

    // Headline + subtitle + eyebrow state.
    var headline, subtitle, eyebrowState;
    if (!hasProvider) {
      headline = 'Two steps to your first message.';
      subtitle = 'Configure a provider, build an agent, then come back here. The shortest path to a working setup takes about a minute.';
      eyebrowState = 'IDLE';
    } else if (!hasAgent) {
      headline = 'One step left.';
      subtitle = "You have a provider. Build an agent and we're live.";
      eyebrowState = 'IDLE';
    } else {
      headline = 'Ready when you are.';
      subtitle = 'Press ⌘N or use the composer to start a conversation.';
      eyebrowState = 'READY';
    }

    var root = document.createElement('div');
    root.className = 'chat-empty';
    root.setAttribute('data-testid', 'chat-welcome');

    var eyebrow = document.createElement('div');
    eyebrow.className = 'eyebrow';
    eyebrow.textContent = 'HOLOGRAPH · CHAT · ' + eyebrowState;
    root.appendChild(eyebrow);

    var brack = document.createElement('div');
    brack.className = 'brack';
    var brackTitle = document.createElement('h2');
    brackTitle.className = 'brack-title';
    brackTitle.textContent = headline;
    brack.appendChild(brackTitle);
    var brackSub = document.createElement('p');
    brackSub.className = 'brack-sub';
    brackSub.textContent = subtitle;
    brack.appendChild(brackSub);
    root.appendChild(brack);

    if (!hasProvider || !hasAgent) {
      var steps = document.createElement('div');
      steps.className = 'steps';
      steps.appendChild(
        buildStep(step1State, step1Prefix, 'Add a provider',
                  'Wire up an LLM — Anthropic, OpenAI, or local Ollama.',
                  '#admin/providers', 'Go to providers →', false)
      );
      steps.appendChild(
        buildStep(step2State, step2Prefix, 'Create an agent',
                  'Pick a model, set a persona, choose tools.',
                  '#studio/agents', 'Go to Studio →', step2State === '')
      );
      root.appendChild(steps);
    }

    container.appendChild(root);
  }

  function buildStep(stateClass, prefix, label, desc, href, ctaText, disabled) {
    var step = document.createElement('div');
    step.className = stateClass ? 'step ' + stateClass : 'step';

    var num = document.createElement('div');
    num.className = 'stepnum';
    num.textContent = prefix;
    step.appendChild(num);

    var lbl = document.createElement('div');
    lbl.className = 'steplabel';
    lbl.textContent = label;
    step.appendChild(lbl);

    var dsc = document.createElement('div');
    dsc.className = 'stepdesc';
    dsc.textContent = desc;
    step.appendChild(dsc);

    var btn = document.createElement('button');
    btn.className = 'step-cta';
    btn.type = 'button';
    btn.dataset.href = href;
    btn.textContent = ctaText;
    if (disabled) btn.disabled = true;
    step.appendChild(btn);

    return step;
  }

  // Global click delegation for `.step-cta` buttons — survives re-renders
  // because it lives on document. Idempotent install (re-loading welcome.js
  // during dev hot-reload must not stack multiple listeners).
  if (!window.App.chat._ctaHandlerInstalled) {
    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest && ev.target.closest('.step-cta');
      if (btn && !btn.disabled && btn.dataset && btn.dataset.href) {
        window.location.hash = btn.dataset.href;
      }
    });
    window.App.chat._ctaHandlerInstalled = true;
  }

  window.App.chat.renderWelcomeList = renderWelcomeList;
})();
