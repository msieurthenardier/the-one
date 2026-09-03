"""Deterministic markdown -> Telegram HTML renderer (Mission 23 Flight 4,
HAT step 8 daily-driver fix -- promoted through a scoped review). No
third-party markdown dependency: Telegram's HTML ``parse_mode`` subset is
small (``<b> <i> <a href> <code> <pre>``) and the inputs here are agent
chat replies, not arbitrary user-authored documents, so a small
hand-rolled pass beats pulling in a general parser.

Pass order (deliberate -- each earlier pass protects its content from
being re-interpreted by a later one):

1. Fenced code blocks, then inline code spans -- pulled out into opaque
   tokens so nothing downstream can "format" code content. Escaped
   (``< > &``) at extraction time.
2. Markdown tables -- degraded whole-block to ``<pre>`` (also tokenized
   and escaped at extraction time) -- Telegram HTML has no table tag.
3. Headings (``#`` .. ``######``) -- the marker is stripped and the
   remaining line text is wrapped in a *sentinel* (not a token, unlike
   code/tables/links) so it still passes through the link/bold/italic
   passes below before becoming ``<b>...</b>``.
4. Links ``[text](url)`` -- tokenized. The href is escaped separately
   from the link text (at minimum ``"`` and ``&``); the link text is not
   itself recursively re-parsed for nested formatting.
5. ``**bold**`` -- sentinel-wrapped (not tokenized) so nested italic
   inside a bold span still converts in the next pass.
6. ``*italic*`` / ``_italic_`` -- sentinel-wrapped. Requires
   non-whitespace immediately adjacent to both delimiters, which as a
   consequence also excludes a line-start bullet marker (``* `` followed
   by a space) from ever being read as an opening delimiter -- the
   reviewer's collision rule. Delimiter type must match on both ends
   (``*...*`` / ``_..._``, never mixed).
7. Whatever prose is left (not inside a token or sentinel) gets its
   ``< > &`` escaped in a single final pass. Tokens/sentinels are marked
   with control characters outside that set, so this pass cannot corrupt
   them, and content already escaped at steps 1/2/4 is not touched again
   (double-escaping only happens where the SOURCE text itself already
   contained escaped entities -- see module docstring note below).
8. Sentinels resolve to real tags; tokens resolve to the HTML registered
   for them in steps 1/2/4.

Determinism note: this converter does not attempt to detect or preserve
pre-existing HTML entities in the input (e.g. a literal ``&amp;`` in the
source text is escaped again, same as a literal ``&``). That is
intentional -- the input is plain-text/lightly-markdown agent output, not
HTML, so "every ``&`` in the source is a literal ampersand" is the
correct and only interpretation.

Never raises by contract. ``TelegramClient.send()`` wraps the call in a
``try/except Exception`` regardless (belt-and-suspenders, review HIGH),
but this module is also written defensively on its own: regex-only (no
recursive descent that could blow the stack), no group-index accesses
that assume a match succeeded, and control characters that might appear
in adversarial input are stripped up front so they cannot be confused
with the module's own internal sentinels/tokens.
"""

from __future__ import annotations

import re

# Sentinels mark a span that still needs further inline processing before
# becoming a tag (headings/bold/italic). Tokens (see _TOKEN) mark a span
# that is ALREADY finished HTML and must never be touched again.
_B_OPEN, _B_CLOSE = "\x01", "\x02"
_I_OPEN, _I_CLOSE = "\x03", "\x04"
_TOKEN = "\x00"
_CONTROL_CHARS_RE = re.compile("[\x00-\x04]")
_TOKEN_RE = re.compile(f"{_TOKEN}(\\d+){_TOKEN}")

_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)\n?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_TABLE_SEP_CELL_RE = re.compile(r"^:?-{2,}:?$")
_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^()\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.DOTALL)
# Single-delimiter italic. Body excludes the delimiter chars themselves
# (bold's ** is already gone by the time this runs -- see pass order
# above) and excludes newlines (italic never spans lines here). The
# (?!\s) / (?<!\s) adjacency requirement is what excludes a line-start
# "* " bullet marker from ever matching as an opening delimiter: right
# after that "*" is a space, so it fails (?!\s) and is left untouched.
_ITALIC_RE = re.compile(r"(?P<delim>[*_])(?!\s)(?P<body>[^*_\n]+?)(?<!\s)(?P=delim)")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(text: str) -> str:
    return _escape(text).replace('"', "&quot;")


def _is_table_separator(line: str) -> bool:
    """``|---|---|``, ``---|---`` (no outer pipes), and alignment
    colons (``:--|--:``) all count -- Telegram HTML has no table tag, so
    the exact separator dialect doesn't matter, only "is this a table"."""
    stripped = line.strip().strip("|").strip()
    if not stripped:
        return False
    cells = [c.strip() for c in stripped.split("|")]
    return all(_TABLE_SEP_CELL_RE.match(c) for c in cells)


def _protect_tables(text: str, tokens: list[str]) -> str:
    """Degrade contiguous markdown-table blocks (>=2 pipe-bearing lines,
    at least one a ``---|---``-shaped separator row) to a single ``<pre>``
    token holding the raw block, escaped verbatim."""
    lines = text.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        if "|" in lines[i] and lines[i].strip():
            j = i
            block: list[str] = []
            has_sep = False
            while j < n and "|" in lines[j] and lines[j].strip():
                block.append(lines[j])
                if _is_table_separator(lines[j]):
                    has_sep = True
                j += 1
            if len(block) >= 2 and has_sep:
                idx = len(tokens)
                tokens.append(f"<pre>{_escape(chr(10).join(block))}</pre>")
                out.append(f"{_TOKEN}{idx}{_TOKEN}")
                i = j
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def render_telegram_html(text: str) -> str:
    """Convert a markdown-ish agent reply into Telegram's HTML
    ``parse_mode`` subset. Deterministic, pure, never raises."""
    tokens: list[str] = []
    working = _CONTROL_CHARS_RE.sub("", text)

    def _tokenize_code(pattern: re.Pattern[str], wrap: str, source: str) -> str:
        def _sub(m: re.Match[str]) -> str:
            idx = len(tokens)
            tokens.append(wrap.format(_escape(m.group(1))))
            return f"{_TOKEN}{idx}{_TOKEN}"

        return pattern.sub(_sub, source)

    working = _tokenize_code(_FENCE_RE, "<pre>{}</pre>", working)
    working = _tokenize_code(_INLINE_CODE_RE, "<code>{}</code>", working)
    working = _protect_tables(working, tokens)

    working = _HEADING_RE.sub(lambda m: f"{_B_OPEN}{m.group(1)}{_B_CLOSE}", working)

    def _link_sub(m: re.Match[str]) -> str:
        idx = len(tokens)
        label, href = m.group(1), m.group(2)
        tokens.append(f'<a href="{_escape_attr(href)}">{_escape(label)}</a>')
        return f"{_TOKEN}{idx}{_TOKEN}"

    working = _LINK_RE.sub(_link_sub, working)
    working = _BOLD_RE.sub(lambda m: f"{_B_OPEN}{m.group(1)}{_B_CLOSE}", working)
    working = _ITALIC_RE.sub(lambda m: f"{_I_OPEN}{m.group('body')}{_I_CLOSE}", working)

    # Everything still literal in `working` at this point is prose (list
    # markers included -- they were never touched, so they "stay literal
    # text" for free) plus our own sentinel/token control characters,
    # which `_escape` cannot touch (it only replaces & < >).
    working = _escape(working)

    working = (
        working.replace(_B_OPEN, "<b>")
        .replace(_B_CLOSE, "</b>")
        .replace(_I_OPEN, "<i>")
        .replace(_I_CLOSE, "</i>")
    )
    working = _TOKEN_RE.sub(lambda m: tokens[int(m.group(1))], working)
    return working
