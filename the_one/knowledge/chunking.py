"""Deterministic, paragraph-aware text chunker (M24 F02 L03, DD-7).

``chunk_text`` splits raw item text into fixed-size, overlapping windows
whose boundaries prefer clean break points — a paragraph gap, a line break,
or a sentence end — over an arbitrary character cut. Offsets are into the
ORIGINAL text (never a normalized copy), so a chunk's ``(char_start,
char_end)`` always satisfies ``text[char_start:char_end] == chunk.text``,
which is what lets Flight 3's "show me the source material behind this
chunk" feature work without re-deriving anything.

**Boundary model**: rather than a three-tier "paragraph, then line, then
sentence" cascade, every candidate break position — after a blank-line run,
after any single line break, after a sentence terminator followed by
whitespace — is collected into one sorted position set up front. Choosing a
window's end as the *latest* candidate at or before the size cap and a
window's overlap start as the *earliest* candidate at or after the overlap
floor is behaviorally equivalent for the chunker's stated contract (a chunk
boundary always lands on one of the three boundary kinds when one exists in
range) and is simpler to reason about and verify than three separate
splitting passes.

**Overlap direction note** (deviation from the leg spec's literal phrasing,
recorded in the flight log): the leg's Implementation Guidance describes
searching for "the latest boundary at or before ``end - overlap_chars``" for
the NEXT window's start. Worked through with concrete numbers, that
direction produces overlap >= ``overlap_chars`` (searching backward from the
floor can only move the start earlier, never later), not the "<=
overlap_chars" the same paragraph requires. This implementation instead
searches for the EARLIEST boundary at or after ``end - overlap_chars`` — the
one closest to (but never before) the floor — which is what actually bounds
overlap above by ``overlap_chars`` while keeping it clean. See AC-7 and the
"Overlap window" note below for the exact guarantee this produces. The
character-level fallback (no boundary found in range) is unchanged from the
spec: the next window starts exactly at ``end - overlap_chars``.
"""

from __future__ import annotations

import bisect
import re

from the_one.db._kb_types import ChunkRecord

# Boundary kinds, each contributing candidate END-of-match positions to one
# combined, de-duplicated, sorted position set. `\r?\n` (never a literal
# `\n` alone) so CRLF text is treated as a single line-break unit without
# ever normalizing `\r\n` -> `\n` in the text itself (offsets stay exact).
_PARAGRAPH_BOUNDARY_RE = re.compile(r"(?:\r?\n)[ \t]*(?:\r?\n)[ \t\r\n]*")
_LINE_BOUNDARY_RE = re.compile(r"\r?\n")
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?]+[ \t\r\n]+")


def _boundary_positions(text: str) -> list[int]:
    """All candidate break positions in ``text``, sorted ascending."""
    positions: set[int] = set()
    for pattern in (_PARAGRAPH_BOUNDARY_RE, _LINE_BOUNDARY_RE, _SENTENCE_BOUNDARY_RE):
        for match in pattern.finditer(text):
            positions.add(match.end())
    return sorted(positions)


def _latest_boundary_at_or_before(boundaries: list[int], limit: int, after: int) -> int | None:
    """The largest boundary in ``(after, limit]``, or ``None``."""
    idx = bisect.bisect_right(boundaries, limit) - 1
    if idx >= 0 and boundaries[idx] > after:
        return boundaries[idx]
    return None


def _earliest_boundary_in_range(boundaries: list[int], lo: int, hi: int) -> int | None:
    """The smallest boundary in ``[lo, hi)``, or ``None``."""
    idx = bisect.bisect_left(boundaries, lo)
    if idx < len(boundaries) and boundaries[idx] < hi:
        return boundaries[idx]
    return None


def chunk_text(
    text: str,
    *,
    size_chars: int = 1000,
    overlap_chars: int = 150,
) -> list[ChunkRecord]:
    """Split ``text`` into overlapping chunks, offsets into the original text.

    Deterministic — the same ``text``/``size_chars``/``overlap_chars`` always
    produce the same result. An empty or whitespace-only ``text`` yields
    ``[]``. Every chunk's ``text[char_start:char_end] == chunk.text`` holds,
    and ``len(chunk.text) <= size_chars`` always (a single unbreakable run
    longer than ``size_chars`` is hard-split at exactly that length).

    **Overlap window**: consecutive chunks overlap by at most
    ``overlap_chars`` characters, and by at least one character whenever the
    earlier chunk was "full" (``len(chunk.text) == size_chars`` — a hard cap
    hit). A chunk that closed early on a paragraph/line/sentence boundary is
    not "full" and carries no overlap guarantee — and if the window that
    just closed was itself no longer than ``overlap_chars``, the next window
    starts with zero overlap rather than backing up past the previous
    window's own start.
    """
    if not text or not text.strip():
        return []

    boundaries = _boundary_positions(text)
    n = len(text)
    chunks: list[ChunkRecord] = []
    start = 0
    seq = 0

    while start < n:
        target_end = start + size_chars
        if target_end >= n:
            end = n
        else:
            boundary = _latest_boundary_at_or_before(boundaries, target_end, start)
            end = boundary if boundary is not None else target_end

        raw = text[start:end]
        stripped = raw.strip()
        if stripped:
            lstrip_count = len(raw) - len(raw.lstrip())
            rstrip_count = len(raw) - len(raw.rstrip())
            chunk_start = start + lstrip_count
            chunk_end = end - rstrip_count
            chunks.append(
                ChunkRecord(seq=seq, text=stripped, char_start=chunk_start, char_end=chunk_end)
            )
            seq += 1

        if end >= n:
            break

        window_len = end - start
        if window_len <= overlap_chars:
            # Can't sustain the configured overlap from a window this
            # short — take none rather than back up past this window's
            # own start (which would either loop or double-count text).
            next_start = end
        else:
            floor = end - overlap_chars
            boundary = _earliest_boundary_in_range(boundaries, floor, end)
            next_start = boundary if boundary is not None else floor
        start = next_start

    return chunks
