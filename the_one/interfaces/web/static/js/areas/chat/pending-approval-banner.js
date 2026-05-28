// M11 F9 L4 — pending-approval banner renderer.
//
// IIFE module: its own scope. Cross-module communication is via the
// callbacks parameter. The fetch + error-reporting path lives in
// chat.js (which has access to addMsg); this module is render-only.
//
// Two public bindings on window.App.chat:
//   renderPendingApproval(event, callbacks) -> HTMLElement (root)
//   applyApprovalStatus(bannerEl, status)
//
// Event shape (canonical, F9 §5):
//   { type, approval_id, peer_name, peer_id, preview, received_at,
//     connector_account_id, status }
//
// Callbacks shape:
//   { onApprove(approval_id, connector_account_id, bannerEl),
//     onDismiss(approval_id, connector_account_id, bannerEl) }
//
// Terminal-status events (approved/dismissed) render with a status
// badge and NO action buttons. ``applyApprovalStatus`` is used post-
// click to swap the footer from buttons to a badge in place.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function renderPendingApproval(event, callbacks) {
    var el = document.createElement('div');
    el.className = 'msg msg-pending-approval';
    el.setAttribute('data-testid', 'pending-approval-banner');
    el.setAttribute('data-approval-id', event.approval_id);
    el.setAttribute('data-connector-account-id', event.connector_account_id);

    // Header: peer name + received_at timestamp.
    var header = document.createElement('div');
    header.className = 'msg-pending-approval-header';
    var name = document.createElement('span');
    name.className = 'msg-pending-approval-peer-name';
    // textContent escapes via DOM API — XSS-safe.
    name.textContent = event.peer_name || '';
    header.appendChild(name);
    var ts = document.createElement('span');
    ts.className = 'msg-pending-approval-ts';
    ts.textContent = event.received_at || '';
    header.appendChild(ts);
    el.appendChild(header);

    // Body: preview text (italicized via CSS).
    var preview = document.createElement('div');
    preview.className = 'msg-pending-approval-preview';
    preview.textContent = event.preview || '';
    el.appendChild(preview);

    // Footer: buttons (pending) OR status badge (terminal).
    var footer = document.createElement('div');
    footer.className = 'msg-pending-approval-footer';
    if (event.status === 'pending') {
      var approveBtn = document.createElement('button');
      approveBtn.type = 'button';
      approveBtn.className = 'msg-pending-approval-approve';
      approveBtn.setAttribute('data-testid', 'pending-approval-approve');
      approveBtn.textContent = 'Approve';
      approveBtn.addEventListener('click', function () {
        if (callbacks && typeof callbacks.onApprove === 'function') {
          callbacks.onApprove(event.approval_id, event.connector_account_id, el);
        }
      });
      footer.appendChild(approveBtn);

      var dismissBtn = document.createElement('button');
      dismissBtn.type = 'button';
      dismissBtn.className = 'msg-pending-approval-dismiss';
      dismissBtn.setAttribute('data-testid', 'pending-approval-dismiss');
      dismissBtn.textContent = 'Dismiss';
      dismissBtn.addEventListener('click', function () {
        if (callbacks && typeof callbacks.onDismiss === 'function') {
          callbacks.onDismiss(event.approval_id, event.connector_account_id, el);
        }
      });
      footer.appendChild(dismissBtn);
    } else {
      var badge = document.createElement('span');
      badge.className =
        'msg-pending-approval-badge msg-pending-approval-badge--' + event.status;
      badge.setAttribute('data-testid', 'pending-approval-badge');
      badge.textContent = event.status;
      footer.appendChild(badge);
    }
    el.appendChild(footer);

    return el;
  }

  // Replace the banner's footer with a status badge after a successful
  // approve/dismiss POST. Removes the buttons (or any prior badge) and
  // clears the "acting" optimistic-state class.
  function applyApprovalStatus(bannerEl, status) {
    if (!bannerEl) return;
    var footer = bannerEl.querySelector('.msg-pending-approval-footer');
    if (!footer) return;
    while (footer.firstChild) footer.removeChild(footer.firstChild);
    var badge = document.createElement('span');
    badge.className =
      'msg-pending-approval-badge msg-pending-approval-badge--' + status;
    badge.setAttribute('data-testid', 'pending-approval-badge');
    badge.textContent = status;
    footer.appendChild(badge);
    bannerEl.classList.remove('msg-pending-approval-acting');
  }

  window.App.chat.renderPendingApproval = renderPendingApproval;
  window.App.chat.applyApprovalStatus = applyApprovalStatus;
})();
