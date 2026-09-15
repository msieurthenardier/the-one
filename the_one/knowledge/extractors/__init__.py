"""Extractor seam: a ``runtime_checkable`` Protocol plus an in-tree
registry keyed by lower-cased dotted suffix (Flight 3 Leg 2, DD-4).

Mirrors ``the_one/connectors/registry.py``'s shape (a plain module-level
dict, populated at process start for production types, plus a
``clear_for_test``/re-register cycle for tests) — never entry points (no
plugin-discovery machinery exists anywhere in this tree). Unlike that
registry's flat 1:1 ``dict[str, ConnectorPlugin]``, one extractor here
claims MANY suffixes (``TextExtractor.extensions`` is dozens of
extensions), so this registry is keyed by suffix rather than by name:
``register`` inserts one dict entry per suffix in ``extractor.extensions``,
checking every one of them for a conflict with a *different* extractor's
``name`` before inserting any (all-or-nothing) — re-registering the SAME
name (even for a different/overlapping suffix set) is a no-op, never a
conflict. ``unregister(name)`` scans the dict and removes every entry
whose owner's ``.name`` matches.

Adding a new format is "one module and one ``register`` call" (DD-4's
mission criterion, pinned by ``tests/test_kb_extractors.py``'s M7 test): a
future ``HtmlExtractor`` needs no change to this module, ``indexer.py``, or
the pipeline — HTML is deliberately absent from ``TextExtractor`` today
(raw tags are poor chunk text).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = [
    "Extractor",
    "ExtractionError",
    "register",
    "unregister",
    "extractor_for",
    "supported_extensions",
    "clear_for_test",
]


@runtime_checkable
class Extractor(Protocol):
    """Structural contract every extractor satisfies (no inheritance, per
    ``structural-Protocol-satisfaction``).

    - ``name``: a stable identifier, used by ``unregister`` and by the
      registry's same-name-is-a-no-op / different-name-is-a-conflict rule.
    - ``extensions``: lower-cased, dot-prefixed suffixes this extractor
      claims (e.g. ``{".txt", ".md"}``).
    - ``extract(path)``: synchronous — the indexer runs it under
      ``asyncio.to_thread``. Raises :class:`ExtractionError` for anything
      the extractor considers a failed extraction.
    """

    name: str
    extensions: frozenset[str]

    def extract(self, path: Path) -> str: ...


class ExtractionError(RuntimeError):
    """Raised by an ``Extractor.extract`` implementation on failure."""


_BY_SUFFIX: dict[str, Extractor] = {}


def register(extractor: Extractor) -> None:
    """Register ``extractor`` under every suffix in ``extractor.extensions``.

    All-or-nothing: every suffix is checked for a conflicting *different*
    extractor name before any dict entry is inserted, so a partial
    conflict never leaves the registry half-updated. Re-registering the
    same ``name`` (even over a different or overlapping suffix set) is a
    no-op for each suffix already owned by that same name; a suffix
    already claimed by a DIFFERENT name raises ``ValueError``.
    """
    for suffix in extractor.extensions:
        existing = _BY_SUFFIX.get(suffix)
        if existing is not None and existing.name != extractor.name:
            raise ValueError(
                f"suffix {suffix!r} is already registered to extractor "
                f"{existing.name!r} (cannot register to {extractor.name!r})"
            )
    for suffix in extractor.extensions:
        _BY_SUFFIX[suffix] = extractor


def unregister(name: str) -> None:
    """Drop every suffix registered to ``name``. Idempotent — a no-op for
    an unknown name."""
    for suffix in [suffix for suffix, extractor in _BY_SUFFIX.items() if extractor.name == name]:
        del _BY_SUFFIX[suffix]


def extractor_for(path: Path) -> Extractor | None:
    """The registered extractor for ``path``'s lower-cased suffix, or
    ``None`` if none is registered."""
    return _BY_SUFFIX.get(path.suffix.lower())


def supported_extensions() -> frozenset[str]:
    """Every suffix currently registered, across all extractors."""
    return frozenset(_BY_SUFFIX.keys())


def clear_for_test() -> None:
    """Drop every registration. Test fixtures only — pair with a
    re-import/re-call of :func:`_register_builtins` in teardown so later
    tests still see the built-in extractors."""
    _BY_SUFFIX.clear()


def _register_builtins() -> None:
    """Register the built-in extractors. Called at import time, and again
    by any test that has called :func:`clear_for_test` and needs the
    built-ins restored.

    The import of ``text.py`` lives inside this function (not at module
    top-level) so the package import order is never circular.
    """
    from the_one.knowledge.extractors.text import TextExtractor

    register(TextExtractor())


_register_builtins()
