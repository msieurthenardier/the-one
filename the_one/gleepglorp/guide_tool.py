"""``get_app_guide``: GleepGlorp's help-topic tool (M36 F1 L07, DD6).

The guide is plain help text shipped in the package (``the_one/gleepglorp/guide/*.md``),
written for a person and quoted by GleepGlorp. The tool reads one topic file by exact,
case-insensitive id, or lists the topics. It never touches the network, never writes,
and its result is shipped text, so it is in ``TRUSTED_TOOL_NAMES`` (a note saved after a
lookup is not flagged).

Topic files load from ``Path(__file__).parent / "guide"``, the pattern the other bundled
data uses (the fonts, the seed catalogue); the freeze specs and ``pyproject.toml`` carry
the files (``tests/test_gleepglorp_guide.py`` pins both).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from the_one.tools.base import Tool

logger = logging.getLogger(__name__)

GET_APP_GUIDE_TOOL_NAME = "get_app_guide"

GUIDE_DIR = Path(__file__).parent / "guide"

# The topic ids, in the order the list shows them, each with a one-line purpose (the tool
# description carries both). The test ties this table to the files in both directions.
TOPICS: dict[str, str] = {
    "overview": "the four main pages and what lives where",
    "agents": "creating and editing an agent",
    "agent-tools": "an agent's built-in tools, overrides, MCP servers, knowledge and secrets",
    "rules-and-notes": "an agent's rules and the notes it keeps",
    "routines": "scheduled prompts an agent runs on its own",
    "self-configuration": "letting an agent edit its own prompt and routines, with approval",
    "mcp-servers": "adding a tool server, signing in, testing, per-agent credentials",
    "model-providers": "connecting a model: Claude, OpenAI, Ollama and the rest",
    "knowledge-bases": "folders of documents agents can search",
    "connectors": "linking an agent to Discord or Telegram",
    "secrets": "values an agent can use in a tool without seeing them",
    "settings": "each Settings page",
    "gleepglorp": "what GleepGlorp can and cannot do, and its settings",
}


def topic_path(topic_id: str) -> Path:
    return GUIDE_DIR / f"{topic_id}.md"


def read_topic(topic_id: str) -> str | None:
    """The topic's text, or ``None`` for an unknown id or a missing file."""
    if topic_id not in TOPICS:
        return None
    try:
        return topic_path(topic_id).read_text(encoding="utf-8")
    except OSError:
        logger.warning("Guide topic %r could not be read", topic_id, exc_info=True)
        return None


def title_and_summary(text: str) -> tuple[str, str]:
    """The ``# Title`` line's text and the first paragraph after it."""
    lines = text.splitlines()
    title = lines[0][2:].strip() if lines and lines[0].startswith("# ") else ""
    summary: list[str] = []
    for line in lines[1:]:
        if line.strip():
            summary.append(line.strip())
        elif summary:
            break
    return title, " ".join(summary)


def topic_list() -> str:
    """Every topic with its title and summary, one per entry."""
    out = ["App guide topics. Call get_app_guide with one id to read it."]
    for topic_id in TOPICS:
        text = read_topic(topic_id)
        if text is None:
            continue
        title, summary = title_and_summary(text)
        out.append(f"- {topic_id}: {title}. {summary}")
    return "\n".join(out)


def _description() -> str:
    topics = "; ".join(f"{i} ({purpose})" for i, purpose in TOPICS.items())
    return (
        "Read a help topic about how this app works and how to set it up. Give topic as one "
        "of the ids below; an unknown or empty topic lists them all. Topics: " + topics + "."
    )


class GetAppGuideTool(Tool):
    """Return one app-guide topic, or the topic list."""

    name = GET_APP_GUIDE_TOOL_NAME
    summary = "Reads the app's help topics."
    description = _description()
    parameters = {
        "type": "object",
        "properties": {
            "topic": {
                "type": ["string", "null"],
                "description": "A topic id from the list; omit to list the topics.",
            }
        },
    }

    async def execute(self, topic: Any = None, **_extra: Any) -> str:  # type: ignore[override]
        wanted = topic.strip().lower() if isinstance(topic, str) else ""
        text = read_topic(wanted) if wanted else None
        return text if text is not None else topic_list()
