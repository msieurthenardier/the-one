"""Shared streaming-accumulator helper for LLM providers.

F7 L04 / M12 F6 L1: consolidates the near-identical tool-call-delta
accumulator (hand-rolled in OpenAI and Ollama providers) and the
byte→interim-usage emitter (triplicated across OpenAI, Ollama, and
Anthropic) into a single, parameterised class.

Import discipline: this module imports ONLY from ``the_one.llm.base``.
That keeps the ``llm/`` import graph acyclic — ``base`` is the leaf;
``_streaming`` depends only on ``base``; providers depend on both.
"""

from __future__ import annotations

import json

from the_one.llm.base import StreamChunk, TokenUsage

# Shared threshold (bytes between interim usage emissions). Matches
# the per-provider constants that previously lived in each provider.
# ~200 bytes ≈ 50 tokens at 4 bytes/token; at ~20 tokens/sec, one
# update every ~2.5 s — smooth without flooding the frontend.
INTERIM_USAGE_BYTE_THRESHOLD = 200


class _StreamAccumulator:
    """Accumulates streaming tool-call deltas and emits mid-stream usage.

    Encapsulates the two cross-provider streaming concerns:

    1. **Tool-call delta accumulation** — keyed by index (OpenAI /
       Ollama streaming convention).  Feed normalised str increments via
       ``feed_tool_call_delta``; call ``finalize_tool_calls()`` at
       stream-end to get the completed ``list[dict]`` entries.

    2. **Byte→interim-usage emission** — call ``maybe_emit_interim``
       after yielding each content delta.  Returns a
       ``StreamChunk(usage=…)`` when the cumulative byte count since the
       last emission crosses ``threshold`` bytes; returns ``None``
       otherwise.

    Provider-edge normalisation stays in each provider.  The accumulator
    never receives a dict for ``arguments`` — the Ollama provider edge
    must ``json.dumps(args)`` before passing to ``feed_tool_call_delta``.

    Parameters
    ----------
    bytes_per_token:
        Provider-specific bytes-per-token heuristic.
        OpenAI / OpenRouter: 4.0; Ollama: 3.5; Anthropic: 3.7.
        Pass ``self._bytes_per_token_for_interim()`` at stream-open so
        OpenRouter's override still applies.
    threshold:
        Cumulative-byte delta between interim emissions (default: the
        shared 200-byte constant above).
    """

    def __init__(
        self,
        bytes_per_token: float,
        threshold: int = INTERIM_USAGE_BYTE_THRESHOLD,
    ) -> None:
        self._bytes_per_token = bytes_per_token
        self._threshold = threshold

        # Tool-call accumulation: index → {id, name, arguments} (str)
        self.tool_calls_acc: dict[int, dict[str, str]] = {}

        # Byte accumulators for the interim-usage heuristic.
        self._accumulated_bytes: int = 0
        self._last_emitted_bytes: int = 0

    # ------------------------------------------------------------------
    # Tool-call accumulation
    # ------------------------------------------------------------------

    def feed_tool_call_delta(
        self,
        index: int,
        id_str: str,
        name_str: str,
        arguments_str: str,
    ) -> None:
        """Accumulate one tool-call delta.

        All parameters must be ``str`` (the caller normalises SDK
        objects or dict arguments before calling here).  Strings are
        appended / overwritten per the index-keyed entry.

        ``id_str`` and ``name_str`` are set (not appended) so they
        overwrite an empty default; ``arguments_str`` is appended so
        fragmented argument chunks concatenate correctly.
        """
        entry = self.tool_calls_acc.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if id_str:
            entry["id"] = id_str
        if name_str:
            entry["name"] = name_str
        if arguments_str:
            entry["arguments"] += arguments_str

    def finalize_tool_calls(self) -> list[dict[str, str]]:
        """Return accumulated tool-call entries in index order.

        Each entry is ``{"id": str, "name": str, "arguments": str}``
        where ``arguments`` is the raw JSON string (json.loads is the
        caller's responsibility, so the provider can decide between
        ``json.loads``-or-``{}`` vs. a bare ``{}``) — this returns the
        raw dict so the provider can construct ``ToolCall`` objects
        directly.

        Concretely: returns entries sorted by key (``sorted(keys)``) to
        match the original per-provider finalisation behaviour.
        """
        result = []
        for idx in sorted(self.tool_calls_acc.keys()):
            e = self.tool_calls_acc[idx]
            raw = e["arguments"]
            try:
                args_obj = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                args_obj = {}
            result.append({"id": e["id"] or e["name"], "name": e["name"], "arguments": args_obj})
        return result

    # ------------------------------------------------------------------
    # Mid-stream byte→usage emitter
    # ------------------------------------------------------------------

    def maybe_emit_interim(self, text: str) -> StreamChunk | None:
        """Accumulate ``text`` bytes and emit an interim usage chunk if
        the threshold is crossed.

        Call this AFTER yielding the content ``StreamChunk``, passing the
        same delta text — exactly the existing per-provider pattern:

            yield StreamChunk(content=text, is_final=False)
            interim = acc.maybe_emit_interim(text)
            if interim:
                yield interim

        Returns a ``StreamChunk(content="", is_final=False, usage=…)``
        when the cumulative delta since the last emission exceeds the
        configured threshold, or ``None`` otherwise.

        The synthesised ``TokenUsage`` carries the cumulative
        ``output_tokens`` estimate (input_tokens=0 — the frontend's
        last-write-wins semantics handle the final input_tokens from the
        end-of-stream usage event).
        """
        if not text:
            return None
        self._accumulated_bytes += len(text.encode("utf-8"))
        if self._accumulated_bytes - self._last_emitted_bytes >= self._threshold:
            self._last_emitted_bytes = self._accumulated_bytes
            return StreamChunk(
                content="",
                is_final=False,
                usage=TokenUsage(
                    input_tokens=0,
                    output_tokens=int(self._accumulated_bytes / self._bytes_per_token),
                ),
            )
        return None
