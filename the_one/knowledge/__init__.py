"""Knowledge-base app-wide configuration and text chunking (M24 F02 L03).

Two operator-facing settings records (DD-6), stored as JSON strings in the
``app_metadata`` key/value table via ``AppMetadataRepository``: the embedding
backend/model choice (fixed to the bundled local model per DD-2) and the
chunking policy (size/overlap) new content is split into before embedding.
Defaults are applied on read — an empty ``app_metadata`` table (a fresh DB)
behaves identically to one holding the default values explicitly.

``chunking.py`` holds the deterministic, paragraph-aware chunker (DD-7) that
turns raw item text into the ``the_one.db._kb_types.ChunkRecord`` rows
``KBChunkRepository.replace_item_chunks`` (Flight 2 Leg 2) consumes.
"""

from __future__ import annotations
