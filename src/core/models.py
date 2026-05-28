from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class LLMConfig:
    provider: str
    name: str
    temperature: float = 0.7
    max_tokens: int = 4096
    base_url: str = "https://api.openai.com/v1"
    api_key_ref: str = ""
    timeout_seconds: int = 120


@dataclass
class AgentConfig:
    id: str
    name: str
    description: str = ""
    system_prompt: str = ""
    model: LLMConfig = field(default_factory=lambda: LLMConfig(provider="mock", name="mock"))
    skills: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class SessionMeta:
    id: str
    name: str
    target_type: str
    target_id: str
    description: str = ""
    system_prompt: str = ""
    status: str = "active"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    group: str = ""
    tags: list[str] = field(default_factory=list)
    compression_interval: int = 10
    context_keep_last: int = 100
    allow_agent_switch: bool = True
    summary: str = ""
    last_compressed_turn: int = 0


@dataclass
class Message:
    role: str
    content: str
    timestamp: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


def llm_config_from_dict(data: dict[str, Any]) -> LLMConfig:
    return LLMConfig(
        provider=data.get("provider", "mock"),
        name=data.get("name", "mock"),
        temperature=float(data.get("temperature", 0.7)),
        max_tokens=int(data.get("max_tokens", 4096)),
        base_url=data.get("base_url", "https://api.openai.com/v1"),
        api_key_ref=data.get("api_key_ref", ""),
        timeout_seconds=int(data.get("timeout_seconds", 120)),
    )


def llm_config_to_dict(config: LLMConfig) -> dict[str, Any]:
    return {
        "provider": config.provider,
        "name": config.name,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "base_url": config.base_url,
        "api_key_ref": config.api_key_ref,
        "timeout_seconds": config.timeout_seconds,
    }


def agent_config_from_dict(data: dict[str, Any]) -> AgentConfig:
    model = llm_config_from_dict(data.get("model", {}))
    return AgentConfig(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        description=str(data.get("description", "")),
        system_prompt=str(data.get("system_prompt", "")),
        model=model,
        skills=list(data.get("skills", [])),
        created_at=str(data.get("created_at", utc_now_iso())),
        updated_at=str(data.get("updated_at", utc_now_iso())),
    )


def agent_config_to_dict(config: AgentConfig) -> dict[str, Any]:
    return {
        "id": config.id,
        "name": config.name,
        "description": config.description,
        "system_prompt": config.system_prompt,
        "model": llm_config_to_dict(config.model),
        "skills": list(config.skills),
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def session_meta_from_dict(data: dict[str, Any]) -> SessionMeta:
    return SessionMeta(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        target_type=str(data.get("target_type", "agent")),
        target_id=str(data.get("target_id", "")),
        description=str(data.get("description", "")),
        system_prompt=str(data.get("system_prompt", "")),
        status=str(data.get("status", "active")),
        created_at=str(data.get("created_at", utc_now_iso())),
        updated_at=str(data.get("updated_at", utc_now_iso())),
        group=str(data.get("group", "")),
        tags=list(data.get("tags", [])),
        compression_interval=int(data.get("compression_interval", 0)),
        context_keep_last=int(data.get("context_keep_last", 12)),
        allow_agent_switch=bool(data.get("allow_agent_switch", True)),
        summary=str(data.get("summary", "")),
        last_compressed_turn=int(data.get("last_compressed_turn", 0)),
    )


def session_meta_to_dict(meta: SessionMeta) -> dict[str, Any]:
    return {
        "id": meta.id,
        "name": meta.name,
        "target_type": meta.target_type,
        "target_id": meta.target_id,
        "description": meta.description,
        "system_prompt": meta.system_prompt,
        "status": meta.status,
        "created_at": meta.created_at,
        "updated_at": meta.updated_at,
        "group": meta.group,
        "tags": list(meta.tags),
        "compression_interval": meta.compression_interval,
        "context_keep_last": meta.context_keep_last,
        "allow_agent_switch": meta.allow_agent_switch,
        "summary": meta.summary,
        "last_compressed_turn": meta.last_compressed_turn,
    }
