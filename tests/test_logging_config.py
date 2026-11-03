"""Unit tests for ``the_one.logging_config.configure_logging``.

M11 F15 L1 — pins the ``the_one`` namespace-logger contract (originally
motivated by connector observability; the contract itself is general):

- A single stdout ``StreamHandler`` is attached to the ``the_one``
  namespace logger at ``settings.log_level``.
- The call is idempotent (no duplicate handlers under ``--reload`` /
  repeated lifespan entry).
- Only the ``the_one`` logger is touched — the root logger and
  ``uvicorn*`` loggers are left alone.
- ``propagate`` is LEFT at the default (``True``). This is load-bearing:
  ``tests/test_lifespan.py``'s deprecation-warning tests capture
  ``the_one.*`` WARNINGs via pytest ``caplog``, which captures through
  the root logger and therefore depends on propagation. Test 4 pins this.
- A bogus ``THE_ONE_LOG_LEVEL`` value falls back to ``INFO`` without
  raising.
"""

from __future__ import annotations

import logging

import pytest

from the_one.logging_config import _HANDLER_SENTINEL, configure_logging


@pytest.fixture(autouse=True)
def _hermetic_the_one_logger():
    """Remove any sentinel handler our calls add and restore the level,
    so configured state never leaks into other tests in the process."""
    logger = logging.getLogger("the_one")
    original_level = logger.level
    original_propagate = logger.propagate
    yield
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_SENTINEL, False):
            logger.removeHandler(handler)
    logger.setLevel(original_level)
    logger.propagate = original_propagate


def _sentinel_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [h for h in logger.handlers if getattr(h, _HANDLER_SENTINEL, False)]


def test_handler_attached_at_configured_level() -> None:
    configure_logging()

    logger = logging.getLogger("the_one")
    handlers = _sentinel_handlers(logger)
    assert len(handlers) == 1
    # Default level (no THE_ONE_LOG_LEVEL override) is INFO.
    assert logger.level == logging.INFO
    # Propagation is left at the default — load-bearing for caplog.
    assert logger.propagate is True


def test_idempotent_no_duplicate_handler() -> None:
    configure_logging()
    logger = logging.getLogger("the_one")
    count_after_first = len(logger.handlers)

    configure_logging()
    assert len(logger.handlers) == count_after_first
    assert len(_sentinel_handlers(logger)) == 1


def test_root_and_uvicorn_loggers_untouched() -> None:
    root = logging.getLogger()
    uvicorn = logging.getLogger("uvicorn")
    root_handlers_before = list(root.handlers)
    uvicorn_propagate_before = uvicorn.propagate

    configure_logging()

    # Root handlers list is unchanged — no sentinel handler leaked onto it.
    assert list(root.handlers) == root_handlers_before
    assert not _sentinel_handlers(root)
    # uvicorn's own propagation flag is not mutated.
    assert uvicorn.propagate == uvicorn_propagate_before
    assert not _sentinel_handlers(uvicorn)


def test_the_one_warning_still_visible_to_caplog(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression — pins the ``test_lifespan.py`` contract. After
    ``configure_logging()`` runs, a ``the_one.*`` WARNING must still be
    captured by pytest ``caplog`` (which captures through the root
    logger and depends on ``propagate=True``)."""
    configure_logging()

    child = logging.getLogger("the_one.probe_module.test_caplog_probe")
    with caplog.at_level(logging.WARNING, logger="the_one.probe_module.test_caplog_probe"):
        child.warning("probe-visible-to-caplog")

    matching = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "probe-visible-to-caplog" in r.getMessage()
    ]
    assert len(matching) == 1, (
        "the_one.* WARNING must remain visible to caplog after "
        f"configure_logging(); saw {[r.getMessage() for r in caplog.records]}"
    )


def test_bogus_log_level_falls_back_to_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid ``THE_ONE_LOG_LEVEL`` value resolves to INFO without
    raising (``getattr(logging, name, logging.INFO)`` fallback)."""
    from the_one.config import settings

    monkeypatch.setattr(settings, "log_level", "NOPE")
    configure_logging()  # must not raise

    assert logging.getLogger("the_one").level == logging.INFO


def test_a_the_one_record_is_written_once_with_a_root_rich_handler() -> None:
    """Squawk 0308: the ``mcp`` SDK's ``basicConfig`` leaves a standing root
    ``RichHandler``; a the_one record must reach the app handler and that
    console handler exactly once between them, while other libraries'
    records still reach the console handler."""
    import io

    from rich.console import Console
    from rich.logging import RichHandler

    console_buf = io.StringIO()
    rich_handler = RichHandler(console=Console(file=console_buf, width=200))
    root = logging.getLogger()
    root.addHandler(rich_handler)
    try:
        configure_logging()
        app_handler = _sentinel_handlers(logging.getLogger("the_one"))[0]
        assert isinstance(app_handler, logging.StreamHandler)
        app_buf = io.StringIO()
        app_handler.setStream(app_buf)

        with_level = logging.getLogger("the_one").level
        assert with_level <= logging.INFO
        logging.getLogger("the_one.x").info("sq0308-marker")
        other = logging.getLogger("some_other_lib")
        other.setLevel(logging.INFO)
        other.info("other-lib-marker")
        configure_logging()  # idempotent: no second filter either
    finally:
        root.removeHandler(rich_handler)

    assert app_buf.getvalue().count("sq0308-marker") == 1
    assert console_buf.getvalue().count("sq0308-marker") == 0
    assert console_buf.getvalue().count("other-lib-marker") == 1
    assert len(rich_handler.filters) == 1
