from pathlib import Path

from storage.file_store import FileStore
from storage.yaml_io import read_yaml, write_yaml


def test_filestore_structure(tmp_path: Path) -> None:
    store = FileStore(root_dir=tmp_path / "Acts")
    store.ensure_structure()
    assert store.agents_dir.exists()
    assert store.sessions_dir.exists()
    assert store.teams_dir.exists()


def test_yaml_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sample.yaml"
    data = {"name": "agent", "model": {"provider": "mock"}}
    write_yaml(path, data)
    loaded = read_yaml(path)
    assert loaded["name"] == "agent"
