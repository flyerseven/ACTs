"""Tests for agent_engine.memory."""
import pytest
from agent_engine.memory import MemoryManager
from agent_engine.types import Message


class TestMemoryManager:
    def test_add_message(self):
        mm = MemoryManager()
        mm.add("user", "hello")
        msgs = mm.get_messages()
        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].content == "hello"

    def test_set_system_prompt(self):
        mm = MemoryManager()
        mm.set_system_prompt("You are helpful.")
        msgs = mm.get_messages()
        assert len(msgs) == 1
        assert msgs[0].role == "system"

    def test_get_context_messages_preserves_system(self):
        mm = MemoryManager()
        mm.set_system_prompt("system prompt")
        for i in range(20):
            mm.add("user", f"message {i}")
            mm.add("assistant", f"response {i}")
        ctx = mm.get_context_messages(max_tokens=500)
        assert ctx[0]["role"] == "system"
        total_chars = sum(len(m["content"]) for m in ctx)
        assert total_chars <= 500 * 4 + 1000  # generous margin

    def test_estimate_tokens(self):
        mm = MemoryManager()
        mm.add("user", "hello world")  # 11 chars
        tokens = mm.estimate_tokens()
        assert tokens == 3  # 11 / 4 = 2.75 -> 3

    def test_compress_basic(self):
        mm = MemoryManager()
        mm.set_system_prompt("system")
        mm.add("user", "hello")
        mm.add("assistant", "hi there")
        mm.add("user", "how are you")
        mm.add("assistant", "I am fine")
        mm.compress(force=True)
        msgs = mm.get_messages()
        # Should have system prompt + summary + recent messages
        assert msgs[0].role == "system"

    def test_to_dict_from_dict(self):
        mm = MemoryManager()
        mm.set_system_prompt("sys")
        mm.add("user", "hello")
        data = mm.to_dict()
        restored = MemoryManager.from_dict(data)
        assert len(restored.get_messages()) == 2

    def test_clear(self):
        mm = MemoryManager()
        mm.add("user", "hello")
        mm.clear()
        assert len(mm.get_messages()) == 0
