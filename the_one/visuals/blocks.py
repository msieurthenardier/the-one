"""Top-level fenced blocks of a reply, with their character spans (M35 F3 L3).

Standard library only. The fence rule is the chat's own (``static/js/markdown.js``
``parseBlocks``) and is held equal to the frozen ``evals.checks._top_level_blocks`` by the
parity corpus ``tests/fixtures/visual-blocks/replies.json``:

* a block opens at a line that starts at column 0 with three backticks; any other fence
  (``json``, a bare one) is code and swallows what is inside it, a chart fence included;
* the tag is the info string's first whitespace token;
* the only closer is a column-0 line of three backticks and whitespace (``~~~`` is never a
  fence, an indented or quoted fence never opens a block);
* an unterminated block runs to the end of the text.

Known residual: a fence nested in another block's body is not found, as in the chat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_OPENER = re.compile(r"```(.*)$")
_CLOSER = re.compile(r"```\s*$")


@dataclass(frozen=True, slots=True)
class Block:
    """One top-level fenced block.

    ``text[start:end]`` is the block's source: the opener line through the closer line,
    including the closer's newline when there is one (``len(text)`` for an unterminated block).
    """

    tag: str
    body: str
    closed: bool
    start: int
    end: int


def find_blocks(text: str) -> list[Block]:
    """Every top-level fenced block of ``text``, of any tag, in order."""
    lines = text.split("\n")
    blocks: list[Block] = []
    offset = 0  # index of lines[i]'s first character
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _OPENER.match(line)
        if m is None:
            offset += len(line) + 1
            i += 1
            continue
        tokens = m.group(1).split()
        start = offset
        offset += len(line) + 1
        i += 1
        body: list[str] = []
        while i < len(lines) and not _CLOSER.match(lines[i]):
            body.append(lines[i])
            offset += len(lines[i]) + 1
            i += 1
        closed = i < len(lines)
        if closed:
            offset += len(lines[i]) + 1  # past the closer line (may pass len(text))
            end = min(offset, len(text))
        else:
            end = len(text)
        i += 1  # the closer (or past the end)
        if tokens:  # a bare fence swallows its content but is not a tagged block
            blocks.append(
                Block(
                    tag=tokens[0],
                    body="\n".join(body) + ("\n" if body else ""),
                    closed=closed,
                    start=start,
                    end=end,
                )
            )
    return blocks
