from __future__ import annotations

import logging
import sys

from the_one.config import settings

_HANDLER_SENTINEL = "_the_one_stdout_handler"

# Squawk 0037: the Telegram Bot API puts the bot token in the request URL
# path (``/bot<token>/<method>`` -- see ``connectors/telegram/_api.py``),
# and httpx/httpcore log the full request URL at INFO on every request
# (their "HTTP Request: ..." line), so an unquieted httpx/httpcore logger
# leaks the token into the host log on every poll cycle. Quieted to
# WARNING below, every call, unconditionally (NOT gated behind the
# idempotent handler-sentinel check) -- some third-party SDKs
# (``anthropic``/``openai``) set the ``httpx`` logger's level themselves
# at import time when e.g. ``ANTHROPIC_LOG=info`` is set, and those
# imports happen before this function ever runs, so re-asserting WARNING
# here on every call is what wins. Discord's REST client sends its token
# in a header, never the URL, so it was never exposed by this and is
# unaffected by quieting these loggers.
_QUIETED_THIRD_PARTY_LOGGERS = ("httpx", "httpcore")


def configure_logging() -> None:
    """Attach a single stdout handler to the ``the_one`` namespace logger,
    and quiet noisy third-party HTTP client loggers (see
    ``_QUIETED_THIRD_PARTY_LOGGERS`` above).

    Idempotent and namespace-scoped: only ``logging.getLogger("the_one")``
    is touched for handler attachment, so uvicorn's own loggers and the
    root logger are left as uvicorn configured them. Propagation is left
    at the default (True): uvicorn installs handlers only on the
    ``uvicorn*`` loggers, not root, so no standing root handler
    double-emits the_one records (lastResort is suppressed once our
    handler handles), while propagation keeps the_one.* records visible
    to pytest caplog. Call once at startup (safe to call again --
    idempotent).

    This is the established per-library logger-quieting spot -- add
    further noisy third-party loggers to ``_QUIETED_THIRD_PARTY_LOGGERS``
    rather than creating a second spot.
    """
    logger = logging.getLogger("the_one")
    level_name = str(settings.log_level).upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))

    for _third_party_name in _QUIETED_THIRD_PARTY_LOGGERS:
        logging.getLogger(_third_party_name).setLevel(logging.WARNING)

    # propagate is LEFT at its default (True) — see Edge Cases. Our
    # handler on ``the_one`` emits each record once (Python's lastResort
    # is suppressed once any handler handles), and propagation keeps
    # the_one.* records visible to pytest caplog (root-attached).
    if any(getattr(h, _HANDLER_SENTINEL, False) for h in logger.handlers):
        return  # already configured (re-import under --reload, repeated lifespan)
    handler = logging.StreamHandler(sys.stdout)
    setattr(handler, _HANDLER_SENTINEL, True)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
