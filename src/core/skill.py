from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from storage.yaml_io import read_yaml


@dataclass
class Skill:
    name: str
    description: str
    type: str = ""
    prompt_extension: str = ""
    source_format: str = ""  # "openai_function", "langchain_tool", "yaml", "builtin"
    tool_definitions: list[dict] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)  # builtin tool function names this skill needs

    def to_frontmatter_dict(self) -> dict:
        """Serialize to the YAML frontmatter format used in SKILL.md."""
        d: dict = {
            "name": self.name,
            "description": self.description,
        }
        if self.type:
            d["type"] = self.type
        if self.source_format:
            d["source_format"] = self.source_format
        return d


# ── SKILL.md frontmatter parsing ──────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def parse_skill_md(path: Path) -> Skill | None:
    """Parse a SKILL.md file with YAML frontmatter + markdown body."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None

    import yaml

    try:
        frontmatter = yaml.safe_load(m.group(1)) or {}
    except Exception:
        return None

    body = m.group(2).strip()
    return Skill(
        name=frontmatter.get("name", path.parent.name),
        description=frontmatter.get("description", ""),
        type=frontmatter.get("type", ""),
        prompt_extension=body,
        source_format=frontmatter.get("source_format", ""),
        requires=frontmatter.get("requires", []),
    )


def write_skill_md(skill: Skill, target_dir: Path) -> Path:
    """Write a Skill to skills/<name>/SKILL.md. Returns the written path."""
    import yaml

    target_dir.mkdir(parents=True, exist_ok=True)
    skill_path = target_dir / "SKILL.md"

    frontmatter = yaml.safe_dump(
        skill.to_frontmatter_dict(),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()

    parts = ["---", frontmatter, "---"]
    if skill.prompt_extension:
        parts.append("")
        parts.append(skill.prompt_extension)

    content = "\n".join(parts) + "\n"
    skill_path.write_text(content, encoding="utf-8")
    return skill_path


# ── Skill discovery ───────────────────────────────────────────────────────

def _load_skill_from_yaml(path: Path) -> Skill | None:
    try:
        data = read_yaml(path)
        return Skill(
            name=data.get("name", path.stem),
            description=data.get("description", ""),
            type=data.get("type", ""),
            prompt_extension=data.get("prompt_extension", ""),
            requires=data.get("requires", []),
        )
    except Exception:
        return None


def discover_skills(skills_dir: Path) -> list[tuple[Path, Skill]]:
    """Discover all skills under `skills_dir/`.

    Supports two layouts:
    1. skills/<name>/SKILL.md  (new format)
    2. skills/*.yaml           (legacy flat format)
    """
    skills: list[tuple[Path, Skill]] = []
    if not skills_dir.exists():
        return skills

    # New format: skills/<name>/SKILL.md
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill = parse_skill_md(skill_md)
        if skill:
            skills.append((skill_md, skill))

    # Legacy format: skills/*.yaml (skip if a SKILL.md already covers it)
    seen_names = {s.name for _, s in skills}
    for yaml_file in sorted(skills_dir.glob("*.yaml")):
        skill = _load_skill_from_yaml(yaml_file)
        if skill and skill.name not in seen_names:
            skills.append((yaml_file, skill))
            seen_names.add(skill.name)

    return skills
