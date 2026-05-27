from __future__ import annotations

from dataclasses import dataclass, field
import json
import shutil
from typing import Iterable

from core.models import Message, SessionMeta, session_meta_from_dict, session_meta_to_dict, utc_now_iso
from storage.file_store import FileStore
from storage.yaml_io import read_yaml, write_yaml


@dataclass
class Session:
    meta: SessionMeta
    store: FileStore
    messages: list[Message] = field(default_factory=list)

    @classmethod
    async def create(
        cls,
        name: str,
        target_type: str,
        target_id: str,
        store: FileStore,
        context_keep_last: int = 100,
        compression_interval: int = 10,
        description: str = "",
        system_prompt: str = "",
    ) -> "Session":
        session_id = store.new_session_id()
        meta = SessionMeta(
            id=session_id,
            name=name,
            target_type=target_type,
            target_id=target_id,
            description=description,
            system_prompt=system_prompt,
            context_keep_last=context_keep_last,
            compression_interval=compression_interval,
        )
        session = cls(meta=meta, store=store)
        await session.save()
        return session

    @staticmethod
    def delete(session_id: str, store: FileStore) -> None:
        session_dir = store.session_dir(session_id)
        if session_dir.exists():
            shutil.rmtree(session_dir)

    @classmethod
    async def load(cls, session_id: str, store: FileStore) -> "Session":
        meta_path = store.session_yaml_path(session_id)
        data = read_yaml(meta_path)
        meta = session_meta_from_dict(data)
        session = cls(meta=meta, store=store)
        content_path = store.session_content_path(session_id)
        legacy_path = store.session_legacy_content_path(session_id)
        if content_path.exists():
            session.messages = list(parse_content_lines(content_path.read_text(encoding="utf-8")))
        elif legacy_path.exists():
            session.messages = list(parse_content_lines(legacy_path.read_text(encoding="utf-8")))
        return session

    async def add_message(self, role: str, content: str) -> Message:
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        self.meta.updated_at = utc_now_iso()
        return msg

    def build_context_messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.meta.system_prompt:
            messages.append({"role": "system", "content": self.meta.system_prompt})
        if self.meta.summary:
            summary = f"Summary of previous context:\n{self.meta.summary}"
            messages.append({"role": "system", "content": summary})

        start_index = self.meta.last_compressed_turn
        recent = self.messages[start_index:]
        if self.meta.context_keep_last > 0:
            recent = recent[-self.meta.context_keep_last :]

        for msg in recent:
            messages.append({"role": msg.role, "content": msg.content})
        return messages

    def maybe_compress_context(self) -> None:
        interval = self.meta.compression_interval
        if interval <= 0:
            return

        turns = self._count_turns()
        if turns <= 0 or turns % interval != 0:
            return

        keep_last = max(self.meta.context_keep_last, 1)
        if len(self.messages) <= keep_last:
            return

        cutoff = len(self.messages) - keep_last
        if cutoff <= self.meta.last_compressed_turn:
            return

        chunk = self.messages[self.meta.last_compressed_turn:cutoff]
        self.meta.summary = summarize_messages(self.meta.summary, chunk)
        self.meta.last_compressed_turn = cutoff

    def _count_turns(self) -> int:
        return sum(1 for msg in self.messages if msg.role == "assistant")

    async def save(self) -> None:
        session_dir = self.store.session_dir(self.meta.id)
        session_dir.mkdir(parents=True, exist_ok=True)
        self.store.session_content_dir(self.meta.id).mkdir(parents=True, exist_ok=True)
        write_yaml(self.store.session_yaml_path(self.meta.id), session_meta_to_dict(self.meta))
        content = render_content_lines(self.meta, self.messages)
        self.store.session_content_path(self.meta.id).write_text(content, encoding="utf-8")


def render_content_lines(meta: SessionMeta, messages: Iterable[Message]) -> str:
    lines = [f"# Session: {meta.name}", f"# Created: {meta.created_at}", ""]
    for msg in messages:
        encoded = json.dumps(msg.content, ensure_ascii=True)
        lines.append(f"[{msg.timestamp}] [{msg.role}] {encoded}")
        lines.append("")
    return "\n".join(lines)


def parse_content_lines(text: str) -> Iterable[Message]:
    for line in text.splitlines():
        if not line.startswith("["):
            continue
        try:
            prefix, content = line.split("] ", 1)
            timestamp = prefix[1:]
            role, body = content.split("] ", 1)
            role = role.lstrip("[")
            decoded = body
            try:
                loaded = json.loads(body)
                if isinstance(loaded, str):
                    decoded = loaded
            except ValueError:
                decoded = body
            yield Message(role=role, content=decoded, timestamp=timestamp)
        except ValueError:
            continue


def summarize_messages(existing_summary: str, messages: Iterable[Message]) -> str:
    lines: list[str] = []
    if existing_summary:
        lines.append("Previous summary:")
        lines.append(existing_summary)
        lines.append("")

    for msg in messages:
        lines.append(f"{msg.role}: {msg.content}")

    summary = "\n".join(lines)
    if len(summary) > 2000:
        summary = summary[-2000:]
        summary = "..." + summary
    return summary
