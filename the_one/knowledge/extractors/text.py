"""``TextExtractor`` — the built-in plain-text/markdown/code extractor
(Flight 3 Leg 2, DD-4).

HTML is deliberately absent from :data:`TEXT_EXTENSIONS`: raw tags are
poor chunk text, and ``readability-lxml`` + ``markdownify`` are already in
the closure for a later ``HtmlExtractor`` — one module and one
``register`` call away, per the extractor seam's mission criterion. PDF
and Office formats follow the same path in a later mission.
"""

from __future__ import annotations

from pathlib import Path

from the_one.knowledge.extractors import ExtractionError

TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt",
        ".text",
        ".md",
        ".markdown",
        ".rst",
        ".adoc",
        ".py",
        ".pyi",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".jsx",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".csv",
        ".tsv",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".bat",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".cs",
        ".rb",
        ".php",
        ".swift",
        ".sql",
        ".xml",
    }
)


class TextExtractor:
    """Decodes a file as ``utf-8-sig`` with ``errors="replace"`` — the
    ``ReadFileTool`` precedent (``the_one/tools/filesystem.py:383``): a
    UTF-8 BOM is stripped, and a stray non-UTF-8 byte degrades to U+FFFD
    rather than failing the file. Satisfies the ``Extractor`` Protocol
    structurally (no inheritance)."""

    name = "text"
    extensions = TEXT_EXTENSIONS

    def extract(self, path: Path) -> str:
        try:
            return path.read_bytes().decode("utf-8-sig", errors="replace")
        except OSError as exc:
            raise ExtractionError(f"cannot read {path}: {exc}") from exc
