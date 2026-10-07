// App.time - local clock formatting (M25 F6 L4b, DD14; own module since squawk 0128).
// Local 12-hour clock time, "3:45 PM": hand-formatted (never toLocaleString) so every
// engine and locale draws the same label. Shared by the Chats list's Today rows and
// the message attributions.
(function () {
  'use strict';

  function formatClock(d) {
    var h = d.getHours();
    var m = d.getMinutes();
    var suffix = h < 12 ? 'AM' : 'PM';
    h = h % 12;
    if (h === 0) h = 12;
    return h + ':' + (m < 10 ? '0' + m : String(m)) + ' ' + suffix;
  }

  window.App = window.App || {};
  window.App.time = { formatClock: formatClock };
})();
