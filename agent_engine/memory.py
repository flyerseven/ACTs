"""Memory manager for the Agent decision engine.

Manages the conversation message list with smart truncation and
automatic summarization when approaching context limits.
"""
from __future__ import annotations

from agent_engine.types import Message


class MemoryManager:
    """Manages short-term conversation memory.

    Features:
    - Message list with role/content tracking
    - Smart truncation: system prompt always preserved, recent messages prioritized
    - Token estimation (char_count / 4)
    - Auto-compression via summarization when token threshold exceeded
    """

    def __init__(self, compress_trigger_tokens: int = 6000, compress_target_tokens: int = 3000):
        self._messages: list[Message] = []
        self.compress_trigger_tokens = compress_trigger_tokens
        self.compress_target_tokens = compress_target_tokens
        self._summary: str = ""

    # -- Message management --

    def add(self, role: str, content: str, **meta: object) -> None:
        self._messages.append(Message(
            role=role,  # type: ignore[arg-type]
            content=content,
            tool_call_id=meta.get("tool_call_id"),  # type: ignore[arg-type]
            name=meta.get("name"),  # type: ignore[arg-type]
            tool_calls=meta.get("tool_calls"),  # type: ignore[arg-type]
        ))

    def set_system_prompt(self, prompt: str) -> None:
        self._messages = [m for m in self._messages if m.role != "system"]
        self._messages.insert(0, Message(role="system", content=prompt))

    def get_messages(self) -> list[Message]:
        return list(self._messages)

    def get_context_messages(self, max_tokens: int = 24000) -> list[dict]:
        """Return messages formatted for LLM API, truncated to fit max_tokens.
        System prompt and the first user message (the goal) are always
        included. Recent messages are prioritized after that."""
        max_chars = max_tokens * 4
        result: list[dict] = []
        chars_used = 0

        # Always include system message if present
        for m in self._messages:
            if m.role == "system":
                result.append({"role": m.role, "content": m.content})
                chars_used += len(m.content)
                break

        # Find the first user message (the goal) — always include it,
        # even if we exceed max_chars.  Without the goal the LLM has
        # no idea what it's supposed to do.
        first_user_content: str | None = None
        for m in self._messages:
            if m.role == "user":
                first_user_content = m.content
                break

        # Add most recent messages first (reverse), then reverse back
        non_system = [m for m in self._messages if m.role != "system"]
        recent: list[dict] = []
        for m in reversed(non_system):
            msg_dict: dict = {"role": m.role}
            if m.tool_calls:
                # DeepSeek rejects "content": null — omit the key entirely
                # when tool_calls is present.
                if m.content:
                    msg_dict["content"] = m.content
            else:
                msg_dict["content"] = m.content
            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if m.name and m.role != "tool":
                # DeepSeek rejects "name" on tool-role messages.
                msg_dict["name"] = m.name
            if m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            msg_len = len(m.content or "")
            if chars_used + msg_len <= max_chars:
                recent.append(msg_dict)
                chars_used += msg_len
            else:
                # If this is the goal message, force it in anyway
                if m.role == "user" and m.content == first_user_content:
                    recent.append(msg_dict)
                    chars_used += msg_len
                    logger.debug("get_context_messages: forced goal message in (over budget)")
                else:
                    break

        recent.reverse()
        return result + recent

    # -- Token estimation --

    def estimate_tokens(self) -> int:
        total_chars = sum(len(m.content) for m in self._messages)
        return max(1, (total_chars + 3) // 4)  # ceiling division

    # -- Compression --

    def compress(self, force: bool = False) -> None:
        """Summarize old messages to reduce context size."""
        if not force and self.estimate_tokens() <= self.compress_trigger_tokens:
            return

        if len(self._messages) <= 3:
            return

        # Summarize oldest 50% of non-system messages
        non_system = [m for m in self._messages if m.role != "system"]
        split_point = len(non_system) // 2
        old_messages = non_system[:split_point]
        recent_messages = non_system[split_point:]

        if not old_messages:
            return

        summary_lines = []
        for m in old_messages:
            if m.role == "user":
                summary_lines.append(f"User asked: {m.content[:200]}")
            elif m.role == "assistant":
                summary_lines.append(f"Assistant: {m.content[:200]}")
            elif m.role == "tool":
                summary_lines.append(f"Tool '{m.name}': {str(m.content)[:200]}")

        summary_text = "Previous conversation summary:\n" + "\n".join(summary_lines[-20:])
        self._summary = summary_text

        system_msgs = [m for m in self._messages if m.role == "system"]
        self._messages = system_msgs + [
            Message(role="system", content=summary_text),
        ] + recent_messages

    # -- Utilities --

    def clear(self) -> None:
        self._messages.clear()
        self._summary = ""

    def to_dict(self) -> dict:
        return {
            "messages": [m.model_dump(mode="json") for m in self._messages],
            "summary": self._summary,
            "compress_trigger_tokens": self.compress_trigger_tokens,
            "compress_target_tokens": self.compress_target_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryManager":
        mm = cls(
            compress_trigger_tokens=data.get("compress_trigger_tokens", 6000),
            compress_target_tokens=data.get("compress_target_tokens", 3000),
        )
        mm._messages = [Message(**m) for m in data.get("messages", [])]
        mm._summary = data.get("summary", "")
        return mm
