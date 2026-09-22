"""Single source of truth for the KB item type/status enums and lifecycle.

Two layers must agree on the valid values, mirroring ``_provider_types.py``:

- The Pydantic ``Literal`` annotations on ``KBItem.type`` / ``KBItem.status``
  (compile-time type checking, JSON-schema generation, request validation at
  the API edge).
- ``KBItemRepository.update_status``'s transition table, which renders its
  ``status IN (…)`` clause from :data:`KB_ITEM_TRANSITIONS`.

Unlike ``_provider_types.py``, these tuples do NOT feed the SQL CHECK
constraints. **The SQL CHECKs in the v40 ``kb_items`` block
(``schema.py``) are frozen inline literals**, not derived from these
tuples — ``schema.py:22-28`` records why derivation was retired for
CHECK constraints: schema history is append-only, so a CHECK, once
written into a migration block, must never change out from under a
database that already ran it. These tuples pin the Pydantic ``Literal``s
(via the import-time assert in ``models.py``, the ``_provider_types.py``
pattern) and the transition table only; the consistency tests in
``tests/test_kb_types_consistency.py`` pin the ``Literal``s to these
tuples and separately assert the fresh-DB CHECK rejects a bogus value —
never by deriving the CHECK's SQL from this module.
"""

from __future__ import annotations

from dataclasses import dataclass

KB_ITEM_TYPES: tuple[str, ...] = ("file", "url", "folder")

KB_ITEM_STATUSES: tuple[str, ...] = ("pending", "indexing", "indexed", "failed")

# Keyed by TARGET status, so `update_status` can render `status IN (…)`
# straight from `KB_ITEM_TRANSITIONS[target]`. Each value is the frozenset
# of statuses a transition into the key is allowed to originate from.
KB_ITEM_TRANSITIONS: dict[str, frozenset[str]] = {
    "indexing": frozenset({"pending"}),
    "indexed": frozenset({"indexing"}),
    "failed": frozenset({"indexing"}),
    "pending": frozenset({"indexing", "failed", "indexed"}),
}


class KBItemTransitionError(ValueError):
    """Raised when a requested KB item status transition is not allowed
    by :data:`KB_ITEM_TRANSITIONS`."""


@dataclass(frozen=True)
class ChunkRecord:
    """One chunk awaiting insertion via ``KBChunkRepository.replace_item_chunks``.

    Flight 2 Leg 2. The shape the chunker (Leg 3) produces and the chunk
    repository consumes — a plain value crossing between the two, so it is
    a dataclass rather than a Pydantic model. Validates nothing here;
    ``kb_chunks``'s ``UNIQUE(item_id, seq)`` and ``NOT NULL`` columns do the
    enforcing at insert time.
    """

    seq: int
    text: str
    char_start: int
    char_end: int
