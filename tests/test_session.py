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


def test_add_message_with_thinking(tmp_path: Path) -> None:
    """Thinking messages are persisted before assistant messages."""
    store = FileStore(root_dir=tmp_path / "Acts")
    store.ensure_structure()

    session = asyncio.run(
        Session.create("test", "agent", "agt1", store)
    )
    asyncio.run(session.add_message("user", "Hello"))
    asyncio.run(session.add_message("assistant", "Response",
                                     thinking="Let me think..."))
    asyncio.run(session.save())

    # Reload
    loaded = asyncio.run(Session.load(session.meta.id, store))
    roles = [m.role for m in loaded.messages]
    assert roles == ["user", "thinking", "assistant"]
    assert loaded.messages[1].content == "Let me think..."
    assert loaded.messages[1].thinking is None  # thinking messages don't nest


def test_build_context_excludes_thinking(tmp_path: Path) -> None:
    """build_context_messages() must NOT include [thinking] role messages."""
    store = FileStore(root_dir=tmp_path / "Acts")
    store.ensure_structure()

    session = asyncio.run(
        Session.create("test", "agent", "agt1", store)
    )
    asyncio.run(session.add_message("user", "Hello"))
    asyncio.run(session.add_message("assistant", "Response",
                                     thinking="Let me think..."))

    context = session.build_context_messages()
    roles = [m["role"] for m in context]
    assert "thinking" not in roles
    # Verify assistant message is still included
    assert "assistant" in roles
    assert "user" in roles
