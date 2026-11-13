"""A small multipart/form-data parser for tests (standard library only)."""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import HTTP

import httpx

Part = tuple[str | None, str | None, bytes]


def parse(request: httpx.Request) -> dict[str, Part]:
    """Return ``{field name: (filename | None, content type | None, bytes)}``."""
    header = request.headers["content-type"].encode()
    msg = BytesParser(policy=HTTP).parsebytes(
        b"Content-Type: " + header + b"\r\n\r\n" + request.read()
    )
    parts: dict[str, Part] = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        content_type = part.get("Content-Type")
        parts[str(name)] = (
            part.get_filename(),
            str(content_type) if content_type is not None else None,
            part.get_payload(decode=True) or b"",
        )
    return parts
