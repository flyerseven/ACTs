import asyncio
from pathlib import Path

from core.agent import Agent
from core.models import AgentConfig, LLMConfig, agent_config_to_dict
from security.vault import Vault
from storage.file_store import FileStore
from storage.yaml_io import write_yaml


def test_agent_mock_chat(tmp_path: Path) -> None:
    store = FileStore(root_dir=tmp_path / "Acts")
    store.ensure_structure()

    config = AgentConfig(
        id="a1b2",
        name="Mock Agent",
        model=LLMConfig(provider="mock", name="mock"),
    )
    write_yaml(store.agent_yaml_path("a1b2"), agent_config_to_dict(config))

    vault = Vault(store.vault_path, use_keyring=False)
    vault.load()

    agent = asyncio.run(Agent.load("a1b2", store, vault))
    response = asyncio.run(agent.chat([{"role": "user", "content": "ping"}]))
    assert "ping" in response
