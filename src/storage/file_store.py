from __future__ import annotations

from pathlib import Path

from utils.id_gen import new_id


class FileStore:
    def __init__(self, root_dir: Path | None = None) -> None:
        if root_dir is None:
            project_root = Path(__file__).resolve().parents[2]
            root_dir = project_root / "Acts"
        self.root_dir = root_dir
        self.agents_dir = self.root_dir / "Agents"
        self.teams_dir = self.root_dir / "Team"
        self.sessions_dir = self.root_dir / "Sessions"
        self.vault_path = self.root_dir / ".vault.enc"
        self.db_path = self.root_dir / "index.db"

    def ensure_structure(self) -> None:
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.teams_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def agent_dir(self, agent_id: str) -> Path:
        return self.agents_dir / agent_id

    def agent_yaml_path(self, agent_id: str) -> Path:
        return self.agent_dir(agent_id) / "AGENT.yaml"

    def team_yaml_path(self, team_id: str) -> Path:
        return self.teams_dir / f"{team_id}.yaml"

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id

    def session_yaml_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "SESSION.yaml"

    def session_content_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "content"

    def session_content_path(self, session_id: str) -> Path:
        return self.session_content_dir(session_id) / "content.txt"

    def session_legacy_content_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "content.txt"

    def list_agents(self) -> list[str]:
        if not self.agents_dir.exists():
            return []
        return [p.name for p in self.agents_dir.iterdir() if p.is_dir()]

    def list_sessions(self) -> list[str]:
        if not self.sessions_dir.exists():
            return []
        return [p.name for p in self.sessions_dir.iterdir() if p.is_dir()]

    def new_agent_id(self) -> str:
        return new_id()

    def new_session_id(self) -> str:
        return new_id()
