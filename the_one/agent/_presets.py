"""Agent preset registry — surfaced via the Studio "start from preset" picker.

Each preset is a recipe: a model family hint, a system prompt, and a starter
tool set. The user can edit any field after creation; presets are just a
warm-start convenience.
"""

from __future__ import annotations

from typing import Any

PRESETS: list[dict[str, Any]] = [
    {
        "name": "research",
        "description": "Read-only research assistant. Greps, reads, cites — never writes.",
        "default_model_family": "opus",
        "system_prompt": (
            "You are a research assistant. Use grep, find, read_file, and "
            "web_search to investigate the worktree and the open web. Cite "
            "specific paths and line numbers when surfacing findings. Do not "
            "modify any files."
        ),
        "tools_enabled": [
            "shell",
            "grep",
            "read_file",
            "glob",
            "list_dir",
            "web_search",
            "fetch_url",
            "http_request",
            "search_tools",
            "continue",
        ],
    },
    {
        "name": "shell-buddy",
        "description": "Fast shell + filesystem helper. Tight scope.",
        "default_model_family": "haiku",
        "system_prompt": (
            "You are a focused shell assistant. Help with one-liners, "
            "filesystem operations, and quick scripting. Ask for the working "
            "directory if unclear."
        ),
        "tools_enabled": [
            "shell",
            "read_file",
            "write_file",
            "edit_file",
            "glob",
            "list_dir",
            "search_tools",
            "continue",
        ],
    },
    {
        "name": "web-crawler",
        "description": "Web research only — no filesystem or shell.",
        "default_model_family": "sonnet",
        "system_prompt": (
            "You are a web research assistant. Use web_search, fetch_url, and "
            "http_request to gather information. Cite source URLs. You have no "
            "filesystem access."
        ),
        "tools_enabled": [
            "web_search",
            "fetch_url",
            "http_request",
            "download_file",
            "search_tools",
            "continue",
        ],
    },
]
