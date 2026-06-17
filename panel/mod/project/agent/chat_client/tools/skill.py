
import os
import json
from . import register_tool
from .base import _xml_response
from ..skills import skill_manager

# 动态生成文档字符串以包含可用 skills
def _get_skill_doc():
    skills = skill_manager.all_enabled()

    if not skills:
        return "Load a specialized skill that provides domain-specific instructions and workflows. No skills are currently available."

    skill_list = "\n".join([
        f"  <skill>\n    <name>{s.name}</name>\n    <description>{s.description}</description>\n  </skill>"
        for s in skills
    ])

    examples = ", ".join([f"'{s.name}'" for s in skills[:3]])
    hint = f" (e.g., {examples}, ...)" if examples else ""

    return f"""Load a specialized skill that provides domain-specific instructions, workflows, and bundled resources.

When you recognize a task matching one of the skills below, use this tool to load its full instructions.
The skill output will include a <skill_content> block with detailed instructions and related files.

Available skills:
{skill_list}

Args:
    name: The exact skill name from the list above{hint}
"""


class Skills:
    """
    Skills, dynamically load Skills list, update available skills via dynamic __doc__ generation.
    """
    
    __name__ = "Skills"
    
    @property
    def __doc__(self):
        # 每次访问 __doc__ 时都重新生成，确保获取最新的 skills 状态
        return _get_skill_doc()
    
    def __call__(self, name: str):
        """
        Load a specialized skill that provides domain-specific instructions and workflows.

        Args:
            name: The name of the skill from available_skills
        """
        skill_obj = skill_manager.get_enabled(name)
        
        if not skill_obj:
            target_skill = skill_manager.get(name)
            if target_skill and not skill_manager.is_enabled(name):
                return _xml_response("Skills", "error", f"Skill '{name}' is disabled.")
            available = ", ".join([s.name for s in skill_manager.all_enabled()])
            return _xml_response("Skills", "error", f"Skill '{name}' not found. Available skills: {available or 'none'}")

        # 获取文件列表
        skill_dir = os.path.dirname(skill_obj.location)
        files = skill_manager.list_files(skill_dir)
        file_list_str = "\n".join([f"<file>{f}</file>" for f in files])

        output = [
            f"<skill_content name=\"{skill_obj.name}\">",
            f"# Skill: {skill_obj.name}",
            "",
            skill_obj.content.strip(),
            "",
            f"Base directory for this skill: {skill_dir}",
            "Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.",
            "Note: file list is sampled. limited to 50 files.",
            "",
            "<skill_files>",
            file_list_str,
            "</skill_files>",
            "</skill_content>"
        ]

        return _xml_response("Skills", "done", "\n".join(output))


# 注册工具
Skills = register_tool(category="Agent", name_cn="Skills", risk_level="low")(Skills())
