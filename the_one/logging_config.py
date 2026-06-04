from __future__ import annotations

import logging
import sys

from the_one.config import settings

_HANDLER_SENTINEL = "_the_one_stdout_handler"


def configure_logging() -> None:
    """Attach a single stdout handler to the ``the_one`` namespace logger.

    Idempotent and namespace-scoped: only ``logging.getLogger("the_one")``
    is touched, so uvicorn's own loggers and the root logger are left as
    uvicorn configured them. Propagation is left at the default (True):
    uvicorn installs handlers only on the ``uvicorn*`` loggers, not root,
    so no standing root handler double-emits the_one records (lastResort
    is suppressed once our handler handles), while propagation keeps
    the_one.* records visible to pytest caplog. Call once at startup.
    """
    logger = logging.getLogger("the_one")
    level_name = str(settings.log_level).upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))
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
