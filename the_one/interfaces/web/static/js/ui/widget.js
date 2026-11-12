(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.widget(opts) (M35 F2 L4, flight DD3, DD5, DD7, DD10-DD12): the card around a hardened
  // widget frame. Options:
  //   source     the widget body (string)
  //   closed     false when the fence never closed (default true): a muted notice, never run
  //   agentName  the agent's name; null shows "the agent"
  //   testid     the testid prefix {t} (default 'widget'); chat uses 'chat-widget'
  //   key        an opaque string for the lifecycle manager (leg 5); stored on the handle
  //   paused     start with the operator's pause on (default false)
  //   managed    default true: the lifecycle manager (widget-lifecycle.js, leg 5) decides when the
  //              frame loads, runs and pauses; the card starts waiting. false mounts the frame at
  //              construction and every control acts directly (leg 4's behaviour, no registration)
  // Returns null for an empty or whitespace-only source; the notice's own {el, destroy()} for a
  // too-large (over 64 KiB of UTF-8) or cut-off source (no card, no frame); otherwise the card
  //   {el, key, destroy(), state(), start(), pause(), resume(), autoPause(), autoResume(),
  //    restart(), unload(), stop(kind)}
  // state() is running | paused-user | paused-auto | waiting | stopped-hung | stopped-escape.
  // The operator's pause (pause/resume) shows the header chip; the automatic pause (autoPause/
  // autoResume, driven by leg 5) does not. unload() drops the frame and keeps the slot height.
  // stop('hung' | 'hung-last') is the hang guard's stop. For a managed card, start(), restart() and
  // Start anyway are requests the manager grants under the cap; prefers-reduced-motion is read once
  // at construction and starts the card with the operator's pause on. No document listener (the
  // manager owns the one); a theme change reaches the frame through the frame core's own observer.
  //
  // App.ui.widget.sweep() destroys every card that was connected once and no longer is.
  // App.ui.widget._instances() is a test-only seam (the live card count).

  var MAX_BYTES = 65536;
  var TITLE_CAP = 60;
  var TITLE_SCAN = 8192;
  var TITLE_RE = /<title[^>]*>([\s\S]*?)<\/title\s*>/i;
  var instances = [];

  // Remembered slot heights (in memory only): widget key -> {h, w}, the last height a frame
  // reported and the slot width it was reported at. A card created again for the same key at the
  // same width (a re-rendered chat in this page) starts at that height, so loading it changes
  // nothing. Bounded: the least recently used entry goes first.
  var HEIGHT_MEMORY_MAX = 500;
  var heightMemory = new Map();
  function rememberHeight(key, h, w) {
    if (!key) return;
    heightMemory.delete(key);
    heightMemory.set(key, { h: h, w: w });
    if (heightMemory.size > HEIGHT_MEMORY_MAX) heightMemory.delete(heightMemory.keys().next().value);
  }
  function recallHeight(key, w) {
    var r = key ? heightMemory.get(key) : null;
    if (!r || Math.abs(r.w - w) > 1) return null;
    heightMemory.delete(key);
    heightMemory.set(key, r);
    return r.h;
  }
  var uidCount = 0;
  var CAP_TEXT = 'Paused: three widgets are already running.';

  function utf8Bytes(s) {
    var n = 0;
    var i;
    for (i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if (c < 0x80) n += 1;
      else if (c < 0x800) n += 2;
      else if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length &&
               s.charCodeAt(i + 1) >= 0xdc00 && s.charCodeAt(i + 1) <= 0xdfff) {
        n += 4;
        i += 1;
      } else n += 3;
    }
    return n;
  }

  function extractTitle(source) {
    var m = TITLE_RE.exec(source.slice(0, TITLE_SCAN));
    if (!m) return '';
    var t = m[1].replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
    var cps = Array.from(t);
    if (cps.length > TITLE_CAP) t = cps.slice(0, TITLE_CAP).join('').trim();
    return t;
  }

  function noticeHandle(notice) {
    return {
      el: notice.el,
      destroy: function () {
        if (notice.el.parentNode) notice.el.parentNode.removeChild(notice.el);
      }
    };
  }

  App.ui.widget = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var source = typeof opts.source === 'string' ? opts.source : '';
    var t = opts.testid || null;
    if (source.trim() === '') return null;
    if (opts.closed === false) {
      return noticeHandle(App.ui.visualNotice({
        tone: 'muted',
        headline: 'This widget was cut off before it finished.',
        source: source,
        sourceLabel: 'Widget source',
        testid: opts.testid ? opts.testid + '-notice' : null
      }));
    }
    var bytes = utf8Bytes(source);
    if (bytes > MAX_BYTES) {
      return noticeHandle(App.ui.visualNotice({
        tone: 'danger',
        headline: "Couldn't run this widget.",
        reason: 'This widget is too large to run (' + Math.ceil(bytes / 1024) +
          ' KB; the limit is 64 KB).',
        source: source,
        sourceLabel: 'Widget source',
        testid: opts.testid ? opts.testid + '-notice' : null
      }));
    }

    var who = 'Widget by ' + (opts.agentName ? String(opts.agentName) : 'the agent');
    var title = extractTitle(source);
    var destroyed = false;
    var seen = false;
    var userPaused = false;
    var autoPaused = false;
    var mode = 'waiting'; // waiting | live | hung | hung-last | escape
    var frame = null;
    var lastHeight = App.ui.widgetFrame.limits.initialHeight;
    var heightKnown = false; // true once a frame has reported a height
    var stoppedEl = null;
    var cappedEl = null;
    var capped = false;
    var link = null;
    var managed = opts.managed !== false && !!App.ui.widget._manager;
    var handle;

    function notify(type) {
      if (link) link.notify(type);
    }

    // ---- DOM, built once ----
    var pauseBtn = App.ui.button({
      variant: 'ghost', size: 'sm', icon: 'pause', ariaLabel: 'Pause widget',
      className: 'ui-widget-btn', testid: opts.testid ? opts.testid + '-pause' : null
    });
    var pauseLabel = util.el('span', { className: 'ui-widget-btn-label', text: 'Pause' });
    pauseBtn.appendChild(pauseLabel);
    var restartBtn = App.ui.button({
      variant: 'ghost', size: 'sm', icon: 'refresh-cw', ariaLabel: 'Restart widget',
      className: 'ui-widget-btn', testid: opts.testid ? opts.testid + '-restart' : null
    });
    restartBtn.appendChild(util.el('span', { className: 'ui-widget-btn-label', text: 'Restart' }));
    var titleEl = util.el('span', { className: 'ui-widget-title', text: title ? '· ' + title : '' });
    if (!title) titleEl.hidden = true;
    uidCount += 1;
    var byEl = util.el('span', { className: 'ui-widget-by', text: who, id: 'ui-widget-by-' + uidCount });
    var chipSlot = util.el('span', { className: 'ui-widget-chip-slot' });
    var head = util.el('div', { className: 'ui-widget-head' }, [
      App.ui.icon('widget', { className: 'ui-widget-icon' }),
      byEl,
      titleEl,
      chipSlot,
      util.el('span', { className: 'ui-widget-spacer' }),
      pauseBtn,
      restartBtn
    ]);
    var body = util.el('div', { className: 'ui-widget-body' });
    var details = App.ui.disclosure({
      variant: 'plain', summary: 'View source', testid: opts.testid ? opts.testid + '-source-details' : null,
      className: 'ui-widget-source'
    });
    details.body.appendChild(App.ui.codeBlock({
      text: source, maxHeight: 'short', label: 'Widget source', testid: opts.testid ? opts.testid + '-source' : null
    }).el);
    // A polite status present from construction: its text is set when the card stops or is held
    // back by the cap (announced on change), never for an automatic or operator pause.
    var statusEl = util.el('div', {
      className: 'ui-widget-status', role: 'status', 'data-testid': t ? t + '-status' : null
    });
    var el = util.el('figure', { className: 'ui-widget', 'data-testid': t, 'aria-labelledby': byEl.id },
      [head, statusEl, body, details.el]);
    // The lifecycle key (leg 6): readable by the flow tests, which compare live and reloaded keys.
    if (typeof opts.key === 'string') el.setAttribute('data-widget-key', opts.key);

    // The first time the card is seen connected, a remembered height for its key at this slot
    // width becomes its slot height (a layout read once per card, never while a frame is loading).
    var adopted = false;
    function adopt() {
      if (adopted) return;
      adopted = true;
      if (heightKnown || mode === 'live' || typeof opts.key !== 'string') return;
      var h = recallHeight(opts.key, body.getBoundingClientRect().width);
      if (h === null) return;
      lastHeight = h;
      heightKnown = true;
      body.style.height = h + 'px';
    }

    function markSeen() {
      if (!el.isConnected) return;
      seen = true;
      adopt();
    }

    function gated() {
      return userPaused || autoPaused;
    }

    function dropFrame() {
      if (frame) {
        frame.destroy();
        frame = null;
      }
    }

    function clearStopped() {
      if (stoppedEl && stoppedEl.parentNode) stoppedEl.parentNode.removeChild(stoppedEl);
      stoppedEl = null;
      if (cappedEl && cappedEl.parentNode) cappedEl.parentNode.removeChild(cappedEl);
      cappedEl = null;
    }

    function mountFrame(paused) {
      dropFrame();
      clearStopped();
      // A card that has reported a height keeps its slot at that height through the remount (the
      // slot never collapses, so the reader's scroll position is not moved); the new frame also
      // starts at it and the first size message replaces it.
      // A card never-seen keeps whatever its waiting slot holds (the initial height) instead of
      // clearing it: clearing and re-inserting the frame moves WebKit's scroll position.
      body.style.minHeight = '';
      if (heightKnown) body.style.height = lastHeight + 'px';
      mode = 'live';
      notify('mount');
      var mine = null;
      mine = App.ui.widgetFrame({
        slot: body,
        source: source,
        title: who,
        paused: paused,
        initialHeight: heightKnown ? lastHeight : undefined,
        // The pre-layout report (raw height 0, which the frame core would clamp to its 48 px
        // minimum) is ignored: the slot keeps its waiting or known height until a real size
        // arrives, so a first load changes the slot once (240 -> real), not twice.
        onReport: function (raw) {
          return raw > 0;
        },
        onSize: function (h) {
          lastHeight = h;
          heightKnown = true;
          if (frame === mine && mode === 'live') {
            body.style.height = h + 'px';
            if (el.isConnected) rememberHeight(opts.key, h, body.getBoundingClientRect().width);
          }
        },
        onHeartbeat: function () {
          if (frame === mine) notify('beat');
        },
        onEscape: function () {
          if (destroyed) return;
          frame = null;
          mode = 'escape';
          render();
          notify('escape');
        }
      });
      frame = mine;
      if (t) frame.iframe.setAttribute('data-testid', t + '-frame');
      frame.iframe.addEventListener('load', function () {
        markSeen();
        if (frame === mine && mine.loads() === 1) notify('loaded');
      });
      render();
    }

    // Start anyway (a stopped card) and the cap card's Start. Managed: a request the manager
    // grants under the cap and the in-view rules. Unmanaged: mount at once, unpaused.
    function startAnyway() {
      // The Start button is removed by the action; if it held focus, hand focus on (2.4.3).
      var ae = document.activeElement;
      var hadFocus = !!ae && ae !== document.body && el.contains(ae) &&
        ((stoppedEl && stoppedEl.contains(ae)) || (cappedEl && cappedEl.contains(ae)));
      userPaused = false;
      autoPaused = false;
      if (!managed) {
        mountFrame(false);
      } else {
        if (mode !== 'waiting') {
          mode = 'waiting';
          clearStopped();
        }
        render();
        notify('start');
      }
      if (hadFocus && !destroyed) {
        var cur = document.activeElement;
        if (!cur || cur === document.body || !cur.isConnected) {
          if (!pauseBtn.disabled) {
            pauseBtn.focus();
          } else {
            el.setAttribute('tabindex', '-1');
            el.focus();
          }
        }
      }
    }

    function stoppedMessage() {
      if (mode === 'escape') return 'This widget tried to leave its frame and was stopped.';
      if (mode === 'hung-last') return 'This widget stopped responding last time.';
      return 'This widget stopped responding.';
    }

    // Only a change of text is announced; the same text set again stays silent.
    function setStatus(text) {
      if (statusEl.textContent !== text) statusEl.textContent = text;
    }

    function render() {
      if (destroyed) return;
      markSeen();
      var live = mode === 'live';
      var up = userPaused;
      pauseBtn.setAttribute('aria-label', up ? 'Resume widget' : 'Pause widget');
      pauseLabel.textContent = up ? 'Resume' : 'Pause';
      App.ui.button.setIcon(pauseBtn, up ? 'play' : 'pause');
      pauseBtn.disabled = !live;
      while (chipSlot.firstChild) chipSlot.removeChild(chipSlot.firstChild);
      if (up && live) {
        chipSlot.appendChild(App.ui.chip({ label: 'Paused', size: 'sm', testid: opts.testid ? opts.testid + '-paused' : null }));
      }
      if (live) {
        clearStopped();
        setStatus('');
        return;
      }
      clearStopped();
      if (mode === 'waiting') {
        setStatus(capped && !userPaused ? CAP_TEXT : '');
        if (capped && !userPaused) {
          // The cap card (DD7): in view, held back because three widgets already run.
          // The cap card keeps the slot height (known, or the waiting height).
          // The known height is a minimum, not a fixed height: the notice must be able to grow
          // (400% zoom, 320 px wide) without spilling over the View source row.
          body.style.height = '';
          body.style.minHeight = lastHeight + 'px';
          cappedEl =util.el('div', { className: 'ui-widget-capped' }, [
            util.el('span', { className: 'ui-widget-capped-text', text: CAP_TEXT }),
            App.ui.button({
              variant: 'secondary', size: 'sm', label: 'Start', testid: opts.testid ? opts.testid + '-start' : null,
              onClick: startAnyway
            })
          ]);
          body.appendChild(cappedEl);
          return;
        }
        body.style.minHeight = '';
        body.style.height = lastHeight + 'px';
        return;
      }
      // A stopped or escaped card keeps its slot height as a minimum (known, or the waiting
      // height); the notice may grow past it.
      body.style.height = '';
      body.style.minHeight = lastHeight + 'px';
      setStatus(stoppedMessage());
      stoppedEl = util.el('div', { className: 'ui-widget-stopped', 'data-testid': t ? t + '-stopped' : null }, [
        util.el('span', { className: 'ui-widget-stopped-text', text: stoppedMessage() }),
        App.ui.button({
          variant: 'secondary', size: 'sm', label: 'Start anyway', testid: opts.testid ? opts.testid + '-start' : null,
          onClick: startAnyway
        })
      ]);
      body.appendChild(stoppedEl);
    }

    function pause() {
      if (destroyed || userPaused) return;
      userPaused = true;
      if (frame) frame.postPause();
      render();
      notify('pause');
    }

    function resume() {
      if (destroyed || !userPaused) return;
      userPaused = false;
      if (frame && !autoPaused) frame.postResume();
      render();
      notify('resume');
    }

    function restart() {
      if (destroyed) return;
      userPaused = false;
      autoPaused = false;
      if (!managed) {
        mountFrame(false);
        return;
      }
      // Managed: drop the frame and ask; the manager mounts a fresh one under the cap.
      dropFrame();
      clearStopped();
      mode = 'waiting';
      render();
      notify('restart');
    }

    function unload() {
      if (destroyed) return;
      dropFrame();
      mode = 'waiting';
      autoPaused = false;
      render();
    }

    // The mount itself (the manager's, or start() on an unmanaged card).
    function mountNow() {
      if (destroyed || mode !== 'waiting') return;
      capped = false;
      mountFrame(gated());
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      dropFrame();
      var i = instances.indexOf(handle);
      if (i >= 0) instances.splice(i, 1);
      if (el.parentNode) el.parentNode.removeChild(el);
      notify('destroy');
      link = null;
    }

    pauseBtn.addEventListener('click', function () {
      if (userPaused) resume();
      else pause();
    });
    restartBtn.addEventListener('click', restart);

    handle = {
      el: el,
      key: typeof opts.key === 'string' ? opts.key : null,
      destroy: destroy,
      state: function () {
        if (mode === 'live') return userPaused ? 'paused-user' : autoPaused ? 'paused-auto' : 'running';
        if (mode === 'waiting') return 'waiting';
        return mode === 'escape' ? 'stopped-escape' : 'stopped-hung';
      },
      // Managed: a start request the manager grants; unmanaged: mount now.
      start: function () {
        if (destroyed || mode !== 'waiting') return;
        if (managed) notify('start');
        else mountNow();
      },
      pause: pause,
      resume: resume,
      autoPause: function () {
        if (destroyed || autoPaused) return;
        autoPaused = true;
        if (frame) frame.postPause();
      },
      autoResume: function () {
        if (destroyed || !autoPaused) return;
        autoPaused = false;
        if (frame && !userPaused) frame.postResume();
      },
      restart: restart,
      unload: unload,
      stop: function (kind) {
        if (destroyed) return;
        dropFrame();
        autoPaused = false;
        mode = kind === 'hung-last' ? 'hung-last' : 'hung';
        render();
        notify('stop');
      },
      // Manager seams (underscored: not for callers).
      _facts: function () {
        return {
          loaded: mode === 'live',
          userPaused: userPaused,
          stopped: mode === 'hung' || mode === 'hung-last' || mode === 'escape'
        };
      },
      _mount: mountNow,
      _seen: markSeen,
      _setCapped: function (b) {
        b = b === true;
        if (destroyed || capped === b) return;
        capped = b;
        if (mode === 'waiting') render();
      },
      // sweep(): was this card ever connected (a frame load, or a render while connected).
      _seenOnce: function () {
        markSeen();
        return seen;
      },
      // Test-only: the live frame core handle, or null.
      _frame: function () {
        return frame;
      }
    };
    instances.push(handle);
    userPaused = opts.paused === true;
    if (!managed) {
      mountFrame(userPaused);
      return handle;
    }
    // Reduced motion is read once, here: the card then starts with the operator's pause on.
    try {
      if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) userPaused = true;
    } catch (e) { /* no matchMedia: motion allowed */ }
    render();
    App.ui.widget._manager.register(handle, function (l) {
      link = l;
    });
    return handle;
  };

  App.ui.widget.sweep = function () {
    var gone = instances.filter(function (h) {
      return h._seenOnce() && !h.el.isConnected;
    });
    gone.forEach(function (h) {
      h.destroy();
    });
    return gone.length;
  };

  App.ui.widget._instances = function () {
    return instances.length;
  };
})();
