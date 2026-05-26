import asyncio
from pathlib import Path

from core.session import Session
from storage.file_store import FileStore


def test_session_save_and_load(tmp_path: Path) -> None:
    store = FileStore(root_dir=tmp_path / "Acts")
    store.ensure_structure()

    session = asyncio.run(Session.create("Test Session", "agent", "a1b2", store))
    asyncio.run(session.add_message("user", "hello"))
    asyncio.run(session.add_message("assistant", "hi"))
    asyncio.run(session.save())

    loaded = asyncio.run(Session.load(session.meta.id, store))
    assert loaded.meta.name == "Test Session"
    assert len(loaded.messages) >= 2
