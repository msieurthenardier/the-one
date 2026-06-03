"""Connector disposition observability helper.

M11 F17 L1 — single shared module for connector disposition vocabulary
and stdout projection. Every inbound decision and every outbound send
passes through :func:`log_disposition` which emits ONE structured stdout
line and best-effort increments the matching per-account counter via
:func:`record_disposition` (imported from :mod:`_pool`).

Inbound disposition vocabulary (aligns to DB audit/routing values so an
operator can grep-correlate the stdout line against the DB record):
    stepped | command-intercepted | no-eligible | policy-silent
    | denied | dropped

Outbound disposition vocabulary:
    ok | rate_limited | error

The ``dropped`` disposition is debug-level only (bot-author / self /
factory-unavailable silent filters); all other dispositions are INFO.

**Content/token invariant**: this module MUST NOT log message content
or tokens. Callers pass ids, dispositions, reasons, and numeric
latency/retry values ONLY. The :func:`log_disposition` signature
enforces this structurally — there is no ``content`` or ``token``
parameter.
"""

from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)

# ─── Vocabulary constants ──────────────────────────────────────────────────────

InboundDisposition = Literal[
    "stepped",
    "command-intercepted",
    "no-eligible",
    "policy-silent",
    "denied",
    "dropped",
]

OutboundDisposition = Literal[
    "ok",
    "rate_limited",
    "error",
]

Kind = Literal["inbound", "outbound"]

# The ``dropped`` disposition is debug-only (silent noise filters);
# all other inbound/outbound dispositions log at INFO.
_DEBUG_DISPOSITIONS: frozenset[str] = frozenset({"dropped"})


def log_disposition(
    *,
    account_id: str,
    channel_id: str,
    peer_id: str | None,
    kind: Kind,
    disposition: str,
    reason: str | None = None,
    retry_after: float | None = None,
    latency_ms: float | None = None,
    error_type: str | None = None,
) -> None:
    """Emit one structured stdout line for a connector inbound or outbound
    disposition and best-effort increment the matching per-account counter.

    Emits at DEBUG for ``dropped``; INFO for all other dispositions.

    Callers MUST NOT pass message content, tokens, or secrets — only ids,
    dispositions, reasons, and numeric values.

    The per-account counter increment is best-effort via
    :func:`record_disposition`: when no warm pool entry exists the
    increment is a no-op (no exception raised).
    """
    parts = [
        f"connector.{kind}",
        f"account={account_id}",
        f"channel={channel_id}",
        f"peer={peer_id}",
        f"disposition={disposition}",
    ]
    if reason is not None:
        parts.append(f"reason={reason}")
    if retry_after is not None:
        parts.append(f"retry_after={retry_after:.3f}")
    if latency_ms is not None:
        parts.append(f"latency_ms={latency_ms:.1f}")
    if error_type is not None:
        parts.append(f"error_type={error_type}")

    line = " ".join(parts)
    if disposition in _DEBUG_DISPOSITIONS:
        logger.debug(line)
    else:
        logger.info(line)

    # Best-effort counter increment — import deferred to avoid circular
    # import at module-load time (_pool imports connectors.base; this module
    # must be importable before _pool is fully loaded in some test setups).
    try:
        from the_one.connectors._pool import record_disposition as _record

        _record(account_id, kind, disposition)
    except Exception:
        # Best-effort — counter increment must never surface as a user-visible
        # error. Log at DEBUG so tests can assert silence.
        logger.debug(
            "connector observability: record_disposition best-effort failed "
            "(account=%s, kind=%s, disposition=%s)",
            account_id,
            kind,
            disposition,
            exc_info=True,
        )
