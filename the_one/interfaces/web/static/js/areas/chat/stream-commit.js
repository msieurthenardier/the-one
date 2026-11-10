// App.chat.streamCommit -- the streaming bubble's pacing and safe markdown commit (M35 F2 L2,
// flight DD12 and DD14; moved out of transcript.js with no behaviour change). It owns the pending
// character queue, the pacing timer, commitSafeBoundary, the visual placeholder hold and the
// finalize drain, plus the boundary planner (App.chat.visualStream). transcript.js keeps creating
// the streaming bubble (App.ui.message), the iteration anchor, history, notices, copy and
// clearLog, and hands the bubble over with begin(msg).
//
// create(ctx) -> {begin, enqueue, active, reset, finalize}. ctx (the area's seam):
//   tags                  the fence languages that are visual blocks (['chart', 'widget'])
//   isPinned()            is the log scrolled to (near) the bottom
//   setPinned(bool)       set the remembered pinned flag
//   pinToBottom()         scroll the log to the bottom and mark it pinned
//   scrollToBottomIfPinned()
//   mdOpts()              the markdown render options (code block renderers, copy live node)
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function create(ctx) {
    // The bubble (the App.ui.message handle, streaming: true) the chunks land in; null when no
    // assistant iteration is streaming.
    var streamMsg = null;

    // Render-pacing queue: API chunks enqueue here; a setInterval loop
    // drains characters into the bubble's pending tail at ~60 chars/sec.
    // Adaptive: long queue drains faster so we don't lag behind a fast API.
    // On finalize, the queue drains synchronously before the markdown swap.
    var pendingChars = '';
    var pacingTimer = null;

    // Safe incremental rendering (M35 F1 L2, DD8/DD10). The candidate boundaries (a blank line,
    // a top-level closing fence's line end, a top-level opener of a visual tag) come from
    // App.chat.visualStream; a candidate is committed only when the parser agrees its prefix
    // holds no unclosed code block, so a fence is never split.
    var boundaries = App.chat.visualStream.create({ tags: ctx.tags });

    // The streaming chart placeholder, if one is up: {placeholder, offset} where offset is where
    // its ```chart opener lies in the bubble's tail. A placeholder is raised only after the
    // opener's prefix was parser-confirmed (so it never sits on text the parser treats as code).
    var visualHold = null;

    // The placeholder for a visual tag (M35 F2 L6): a chart's takes its type from the stream; a
    // widget's is the generic card and never has a type.
    var PLACEHOLDERS = {
      chart: function () {
        return App.ui.chart.placeholder({ type: null, testid: 'chat-chart-placeholder' });
      },
      widget: function () {
        return App.ui.chart.placeholder({
          type: null,
          label: 'Rendering widget',
          sourceLabel: 'Widget source',
          shape: 'generic',
          testid: 'chat-widget-placeholder'
        });
      }
    };

    function dropVisualHold() {
      var hold = visualHold;
      visualHold = null;
      if (!hold) return;
      try { if (streamMsg) streamMsg.setTailHold(0, null); } catch (e) { /* defensive */ }
      try { hold.placeholder.destroy(); } catch (e2) { /* defensive */ }
      if (hold.placeholder.el.parentNode) hold.placeholder.el.parentNode.removeChild(hold.placeholder.el);
    }

    // After paced text is appended to the pending tail, plan the commit. If a boundary was
    // confirmed, render the prefix as markdown and shrink the tail; then keep the placeholder
    // for an open top-level chart block in step with the tail.
    function commitSafeBoundary() {
      if (!streamMsg) return;
      var tail = streamMsg.tail();
      var plan = boundaries.plan(tail);
      var consumed = 0;
      if (plan.boundary > 0) {
        var frag = App.markdown.render(tail.slice(0, plan.boundary), ctx.mdOpts());
        if (frag.firstChild) {
          streamMsg.commit(frag, plan.boundary);
          consumed = plan.boundary;
          boundaries.reset();
        } else {
          boundaries.markEmpty(plan.boundary);
        }
      }
      // A commit that cut text removed the bubble's hold with it (or the block it held is now
      // drawn): the placeholder is spent, and a new open block gets a new one below.
      if (consumed > 0) dropVisualHold();
      var lang = plan.open === null ? null : plan.open.lang;
      var openAt = lang === null || ctx.tags.indexOf(lang) < 0 ? null : plan.open.offset - consumed;
      if (openAt === null || openAt < 0) {
        dropVisualHold();
        return;
      }
      if (visualHold && visualHold.lang !== lang) dropVisualHold();
      if (!visualHold) {
        visualHold = {
          lang: lang,
          placeholder: PLACEHOLDERS[lang](),
          offset: openAt,
          source: null
        };
        streamMsg.setTailHold(openAt, visualHold.placeholder.el);
      }
      var blockText = streamMsg.tail().slice(openAt);
      var nl = blockText.indexOf('\n');
      var body = nl < 0 ? '' : blockText.slice(nl + 1);
      if (body !== visualHold.source) {
        visualHold.source = body;
        visualHold.placeholder.setSource(body);
      }
      // Only a chart has a type to read from the stream.
      if (lang === 'chart') {
        var type = App.chat.visualStream.typeOf(blockText);
        if (type) visualHold.placeholder.setType(type);
      }
    }

    function pacingTick() {
      if (!pendingChars.length || !streamMsg) return;
      // Sampled before the text and any commit (a chart swap can grow the log by more than the
      // pin threshold at once).
      var wasPinned = ctx.isPinned();
      var n = Math.max(1, Math.ceil(pendingChars.length / 30));
      var slice = pendingChars.slice(0, n);
      pendingChars = pendingChars.slice(n);
      streamMsg.appendText(slice);
      commitSafeBoundary();
      if (wasPinned) ctx.pinToBottom();
      else ctx.scrollToBottomIfPinned();
    }

    function startPacing() {
      if (pacingTimer) return;
      pacingTimer = setInterval(pacingTick, 16);
    }

    function stopPacing() {
      if (pacingTimer) { clearInterval(pacingTimer); pacingTimer = null; }
    }

    function drainPacing() {
      if (pendingChars.length && streamMsg) streamMsg.appendText(pendingChars);
      pendingChars = '';
      stopPacing();
    }

    return {
      // A new streaming bubble: a stale placeholder from an earlier bubble never carries over.
      begin: function (msg) {
        dropVisualHold();
        boundaries.reset();
        streamMsg = msg;
        startPacing();
      },
      enqueue: function (text) { pendingChars += text; },
      active: function () { return streamMsg !== null; },
      // Drop a streaming bubble that belongs to the conversation being left.
      reset: function () {
        stopPacing();
        dropVisualHold();
        boundaries.reset();
        pendingChars = '';
        streamMsg = null;
      },
      // Swap the streaming bubble's pending tail for its markdown-rendered fragment.
      // Already-committed blocks (from commitSafeBoundary) stay in place. Idempotent: returns
      // false when no bubble is active. `afterRender` runs once the bubble is finalized, before
      // the pin scroll (the caller adds the reply's Copy button there).
      finalize: function (afterRender) {
        drainPacing();
        var bubble = streamMsg;
        if (!bubble) return false;
        var wasPinned = ctx.isPinned();
        // The placeholder is destroyed before the tail renders: the tail may hold the block it
        // stood for, which now draws as a chart or as the error / cut-off notice.
        dropVisualHold();
        boundaries.reset();
        streamMsg = null;
        var tail = bubble.tail();
        bubble.finalize(tail ? App.markdown.render(tail, ctx.mdOpts()) : null);
        if (afterRender) afterRender();
        if (wasPinned) ctx.pinToBottom();
        return true;
      }
    };
  }

  window.App.chat.streamCommit = { create: create };
})();
