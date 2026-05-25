"""Deprecated home for :func:`tag_post_step_visibility`.

The function lives at :mod:`the_one.connectors.post_step_metadata` as
of F7 L1 — the n=3 trigger of ``agents.md``'s
``post-step-dispatcher-message-metadata-binding`` convention was met
by F7's channel-context binding (forthcoming at L3), prompting the
mutators to be lifted into a shared module. This re-export preserves
the import path for any external importer (none known in-repo at
F7 L1, but ``agents.md`` historically cited the convention by this
module's file path); internal callers migrate inline.
"""

from __future__ import annotations

from the_one.connectors.post_step_metadata import tag_post_step_visibility

__all__ = ["tag_post_step_visibility"]
