from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from the_one.tools.base import Tool

MC_DIR = Path("/mission-control")
SKILLS_DIR = MC_DIR / ".claude" / "skills"
DOCS_DIR = MC_DIR / "docs"


class MissionControlTool(Tool):
    """Read and execute mission-control skills — structured workflow prompts."""

    name = "mission_control"
    description = (
        "Access the Mission Control methodology. Actions:\n"
        "- list_skills: Show available workflow skills\n"
        "- read_skill: Read a skill's prompt template (e.g. 'leg', 'mission', 'flight')\n"
        "- read_doc: Read a methodology doc (e.g. 'overview', 'missions', 'flights', 'legs', 'workflow')\n"
        "- list_docs: Show available methodology docs\n"
        "Use this to understand the Mission Control workflow and execute structured tasks."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "One of: list_skills, read_skill, read_doc, list_docs",
            },
            "name": {
                "type": "string",
                "description": "Skill or doc name (e.g. 'leg', 'overview'). Required for read_skill and read_doc.",
            },
        },
        "required": ["action"],
    }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        name = kwargs.get("name", "")

        if not MC_DIR.exists():
            return "[error] Mission Control not found at /mission-control. It may not have been cloned yet."

        if action == "list_skills":
            return self._list_skills()
        elif action == "read_skill":
            return self._read_skill(name)
        elif action == "list_docs":
            return self._list_docs()
        elif action == "read_doc":
            return self._read_doc(name)
        else:
            return f"[error] Unknown action '{action}'. Use: list_skills, read_skill, list_docs, read_doc"

    def _list_skills(self) -> str:
        if not SKILLS_DIR.exists():
            return "[error] Skills directory not found."
        skills = []
        for d in sorted(SKILLS_DIR.iterdir()):
            if d.is_dir() and (d / "SKILL.md").exists():
                # Read first line of description from frontmatter
                text = (d / "SKILL.md").read_text()
                desc = ""
                for line in text.split("\n"):
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()
                        break
                skills.append(f"- {d.name}: {desc}")
        return "Available skills:\n" + "\n".join(skills) if skills else "No skills found."

    def _read_skill(self, name: str) -> str:
        if not name:
            return "[error] Provide a skill name. Use list_skills to see available skills."
        skill_file = SKILLS_DIR / name / "SKILL.md"
        if not skill_file.exists():
            return f"[error] Skill '{name}' not found at {skill_file}"
        content = skill_file.read_text()
        # Truncate if very long to fit in context
        if len(content) > 8000:
            content = content[:8000] + "\n\n[... truncated]"
        return content

    def _list_docs(self) -> str:
        if not DOCS_DIR.exists():
            return "[error] Docs directory not found."
        docs = []
        for f in sorted(DOCS_DIR.iterdir()):
            if f.suffix == ".md":
                docs.append(f"- {f.stem}")
        return "Available docs:\n" + "\n".join(docs) if docs else "No docs found."

    def _read_doc(self, name: str) -> str:
        if not name:
            return "[error] Provide a doc name. Use list_docs to see available docs."
        doc_file = DOCS_DIR / f"{name}.md"
        if not doc_file.exists():
            return f"[error] Doc '{name}' not found at {doc_file}"
        content = doc_file.read_text()
        if len(content) > 8000:
            content = content[:8000] + "\n\n[... truncated]"
        return content
