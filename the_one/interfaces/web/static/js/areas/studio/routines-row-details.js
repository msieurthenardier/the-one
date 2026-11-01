// App.studio.routinesRowDetails -- the details of one Routines tab card (M33 F4 L03): the
// routine's prompt and its recent runs. Each run is one line: when, how it started
// (Scheduled, Run now, Caught up), the outcome with its stored reason, and a link to the chat
// the run started. Every string from the server (prompt, reasons) is written with textContent
// only.
//
//   App.studio.routinesRowDetails.create({fetchRuns})
//     fetchRuns({limit, before}) -> Promise<{runs}>
//   -> {el, setOpen(bool), isOpen(), update(row), reload(), destroy()}
//
// `el` goes in the card's body (the card's expand button shows and hides the body; setOpen only
// tells this module when to load). The first page (5 runs) loads the first time it opens; "Show
// more runs" appends the next 20 through the cursor. update(row) repaints the prompt and the
// "Open chat" link names and, while open and loaded, reloads the runs when the row's last run
// changed (so an open card follows a running routine through the tab's refetch). The two labels
// are h4 headings (the tab's section title is the h3).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var shared = window.App.studio.rulesNotesShared;
  var el = shared.el;
  var describe = window.App.studio.routinesDescribe;

  var FIRST_PAGE = 5;
  var NEXT_PAGE = 20;
  var MAX_RELOAD = 100;

  function runSig(run) {
    return run ? [run.outcome, run.finished_at, run.session_id].join('|') : '';
  }

  function label(text) {
    return el('h4', 'routine-details-label', text);
  }

  // A visually hidden separator, so "when / how / outcome" do not read as one run-on string.
  function separator(text) {
    return el('span', 'visually-hidden', text);
  }

  function create(opts) {
    var fetchRuns = opts.fetchRuns;
    var region = el('div', 'routine-details');

    region.appendChild(label('Prompt'));
    // The stored prompt is shown as the app shows other stored text (Settings > Prompts, the
    // approval queue): a read-only code block, textContent only.
    var promptBlock = App.ui.codeBlock({
      text: '', maxHeight: 'short', label: 'Prompt', testid: 'routine-details-prompt'
    });
    region.appendChild(promptBlock.el);

    region.appendChild(label('Recent runs'));
    var errorLine = shared.buildErrorLine();
    region.appendChild(errorLine.el);
    var emptyEl = el('p', 'routine-details-empty', 'No runs yet.');
    emptyEl.hidden = true;
    region.appendChild(emptyEl);
    var listEl = el('ul', 'routine-recent-runs');
    listEl.setAttribute('role', 'list');
    listEl.setAttribute('aria-label', 'Recent runs');
    listEl.setAttribute('data-testid', 'routine-recent-runs');
    region.appendChild(listEl);
    var moreBtn = App.ui.button({
      variant: 'ghost', size: 'sm', label: 'Show more runs', className: 'routine-more-btn',
      testid: 'routine-recent-runs-more',
      onClick: function () { load(true); }
    });
    moreBtn.hidden = true;
    region.appendChild(moreBtn);

    var open = false;
    var loaded = false;
    var destroyed = false;
    var gen = 0;
    var cursor = null;
    var loadedSig = '';
    var row = null;

    // The link is named for the routine and the run, since "Open chat" repeats down the list.
    function linkName(when) {
      return 'Open chat, ' + ((row && row.name) || 'routine') + (when ? ', run at ' + when : '');
    }

    function runLine(run) {
      var li = el('li', 'routine-recent-run');
      li.setAttribute('data-testid', 'routine-recent-run');
      var at = run.started_at || run.due_at;
      var when = at ? describe.describeWhen(at) : '';
      var whenEl = el('span', 'routine-recent-when', when);
      whenEl.appendChild(separator(', '));
      li.appendChild(whenEl);
      var how = el('span', 'routine-recent-how', describe.describeTrigger(run.trigger_kind));
      how.appendChild(separator(', '));
      li.appendChild(how);
      var st = describe.outcomeStatus(run, false);
      var status = App.ui.status({ state: st.state, text: st.text, live: 'off', textTone: true });
      status.el.classList.add('routine-recent-outcome');
      li.appendChild(status.el);
      var tail = el('span', 'routine-recent-chat');
      if (run.session_id && run.chat_exists) {
        var link = el('a', 'routine-recent-run-link', 'Open chat');
        link.setAttribute('href', App.router.href({ destination: 'chats', id: run.session_id }));
        link.setAttribute('data-testid', 'routine-recent-run-chat');
        link.setAttribute('data-when', when);
        link.setAttribute('aria-label', linkName(when));
        tail.appendChild(link);
      } else if (run.session_id) {
        tail.appendChild(el('span', 'routine-recent-gone', 'Chat deleted'));
      }
      li.appendChild(tail);
      return li;
    }

    // The first page replaces the list (as many runs as are showing, at least 5); "Show more
    // runs" appends the next page after the cursor.
    function load(more) {
      var mine = more ? gen : ++gen;
      var limit = more ? NEXT_PAGE : Math.min(Math.max(FIRST_PAGE, listEl.children.length), MAX_RELOAD);
      var before = more ? cursor : null;
      errorLine.show('');
      moreBtn.disabled = true;
      return Promise.resolve().then(function () {
        return fetchRuns({ limit: limit, before: before });
      }).then(function (body) {
        if (destroyed || mine !== gen) return;
        var runs = (body && body.runs) || [];
        if (!more) listEl.textContent = '';
        runs.forEach(function (run) { listEl.appendChild(runLine(run)); });
        loaded = true;
        if (!more) loadedSig = runSig(row && row.last_run);
        var last = runs.length ? runs[runs.length - 1] : null;
        cursor = last ? last.started_at : cursor;
        moreBtn.hidden = !(runs.length >= limit && last && last.started_at);
        emptyEl.hidden = listEl.children.length > 0;
      }, function (err) {
        if (!destroyed) errorLine.show('Couldn’t load the runs: ' + shared.messageOf(err));
      }).then(function () { moreBtn.disabled = false; });
    }

    return {
      el: region,
      setOpen: function (flag) {
        open = !!flag;
        if (open && !loaded) load(false);
      },
      isOpen: function () { return open; },
      update: function (next) {
        row = next;
        promptBlock.set(next.prompt || '');
        // A rename renames the links already listed.
        var links = listEl.querySelectorAll('.routine-recent-run-link');
        for (var i = 0; i < links.length; i++) {
          links[i].setAttribute('aria-label', linkName(links[i].getAttribute('data-when')));
        }
        if (open && loaded && runSig(next.last_run) !== loadedSig) load(false);
      },
      // The clock moved (zone change): repaint the times.
      reload: function () { if (open && loaded) load(false); },
      destroy: function () { destroyed = true; gen++; }
    };
  }

  window.App.studio.routinesRowDetails = { create: create };
})();
