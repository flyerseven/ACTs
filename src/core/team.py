from dataclasses import dataclass


@dataclass
class AgentTeam:
    id: str
    name: str
    captain_id: str
    members: list[str]
