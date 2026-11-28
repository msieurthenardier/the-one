"""Quiet the SDK's error log for an expected sign-in refusal (sortie 22 DD1).

``mcp.client.auth.oauth2`` logs ``logger.exception("OAuth flow error")`` for any
exception raised inside its authorization flow, including our own
``SignInNotAvailable`` refusal (an ordinary, expected outcome: the connection
cannot be signed in through, so the turn pauses). The filter below drops exactly
that record, and only when the logged exception is the refusal class; every
other OAuth error still logs. It sits on the SDK's logger itself (a handler would
not see records another logger's handlers drop) and is installed once at import
of ``the_one.mcp.oauth``.
"""

from __future__ import annotations

import logging

from the_one.mcp.oauth.errors import SignInNotAvailable

SDK_OAUTH_LOGGER_NAME = "mcp.client.auth.oauth2"


class SignInRefusalFilter(logging.Filter):
    """Drop the SDK's "OAuth flow error" record when it carries ``SignInNotAvailable``."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc_info = record.exc_info
        if exc_info and isinstance(exc_info[1], SignInNotAvailable):
            return False
        return True


def install_sign_in_refusal_filter() -> None:
    """Add the filter to the SDK's OAuth logger once (idempotent)."""
    sdk_logger = logging.getLogger(SDK_OAUTH_LOGGER_NAME)
    if not any(isinstance(f, SignInRefusalFilter) for f in sdk_logger.filters):
        sdk_logger.addFilter(SignInRefusalFilter())
