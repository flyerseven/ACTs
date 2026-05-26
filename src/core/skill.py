from dataclasses import dataclass


@dataclass
class Skill:
    name: str
    description: str
    type: str
    prompt_extension: str = ""
