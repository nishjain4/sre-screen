"""Registry for built-in Gitea repository skills."""
from __future__ import annotations

from app.core.tools import ToolRegistry
from app.schemas import SkillInfo
from app.skills.base import Skill
from app.skills.builtin.gitea_investigation import GITEA_SKILL_CLASSES

# Keep only the working Gitea skills enabled for now.
BUILTIN_SKILLS: list[type[Skill]] = [*GITEA_SKILL_CLASSES]


class SkillRegistry:
    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools
        self._skills: dict[str, Skill] = {}
        for cls in BUILTIN_SKILLS:
            self.register(cls())

    def register(self, skill: Skill) -> None:
        if skill.id in self._skills and self._skills[skill.id].source == "builtin" and skill.source != "builtin":
            raise ValueError(f"custom skill id '{skill.id}' collides with a built-in skill")
        self._skills[skill.id] = skill

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def available(self) -> list[Skill]:
        """Skills whose tools exist in the current tool registry."""
        return [s for s in self._skills.values() if s.available(self.tools)]

    def infos(self) -> list[SkillInfo]:
        infos = []
        for skill in self.available():
            info = skill.info()
            servers = {
                tool.source.removeprefix("mcp:")
                for name in skill.tools
                if (tool := self.tools.get(name)) is not None and tool.source.startswith("mcp:")
            }
            infos.append(info.model_copy(update={"mcp_servers": sorted(servers)}))
        return infos
