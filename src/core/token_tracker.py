from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Approximate pricing per 1M tokens (USD)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-7": {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "deepseek-v4-pro": {"input": 0.28, "output": 1.10},
    "deepseek-chat": {"input": 0.14, "output": 0.56},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
}


def _model_price_key(model: str) -> str | None:
    """Find the pricing key that best matches the given model name."""
    model_lower = model.lower()
    for key in MODEL_PRICING:
        if key in model_lower or model_lower in key:
            return key
    if "gpt-4o" in model_lower:
        return "gpt-4o"
    if "gpt-4" in model_lower:
        return "gpt-4"
    if "gpt-3.5" in model_lower:
        return "gpt-3.5-turbo"
    if "claude" in model_lower:
        if "sonnet" in model_lower:
            return "claude-sonnet-4-6"
        if "opus" in model_lower:
            return "claude-opus-4-7"
        if "haiku" in model_lower:
            return "claude-haiku-4-5"
        return "claude-sonnet-4-6"
    if "deepseek" in model_lower:
        return "deepseek-chat"
    return None


def _calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    key = _model_price_key(model)
    if key is None:
        return None
    pricing = MODEL_PRICING[key]
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)


@dataclass
class TokenUsage:
    timestamp: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    agent_id: str = ""
    session_id: str = ""
    cost: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "provider": self.provider,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenUsage":
        return cls(
            timestamp=data.get("timestamp", ""),
            model=data.get("model", ""),
            provider=data.get("provider", ""),
            prompt_tokens=int(data.get("prompt_tokens", 0)),
            completion_tokens=int(data.get("completion_tokens", 0)),
            total_tokens=int(data.get("total_tokens", 0)),
            agent_id=data.get("agent_id", ""),
            session_id=data.get("session_id", ""),
            cost=data.get("cost"),
        )


@dataclass
class UsageStats:
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)


class TokenTracker:
    def __init__(self, log_path: Path | None = None) -> None:
        if log_path is None:
            from pathlib import Path as _Path

            project_root = _Path(__file__).resolve().parents[2]
            log_path = project_root / ".claude" / "token_usage.jsonl"
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        agent_id: str = "",
        session_id: str = "",
    ) -> TokenUsage:
        usage = TokenUsage(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            agent_id=agent_id,
            session_id=session_id,
            cost=_calculate_cost(model, prompt_tokens, completion_tokens),
        )
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(usage.to_dict(), ensure_ascii=True) + "\n")
        return usage

    def _iter_records(self) -> list[TokenUsage]:
        if not self.log_path.exists():
            return []
        records: list[TokenUsage] = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(TokenUsage.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError):
                    continue
        return records

    def get_session_stats(self, session_id: str) -> UsageStats:
        stats = UsageStats()
        for r in self._iter_records():
            if r.session_id != session_id:
                continue
            stats.total_requests += 1
            stats.total_prompt_tokens += r.prompt_tokens
            stats.total_completion_tokens += r.completion_tokens
            stats.total_tokens += r.total_tokens
            if r.cost is not None:
                stats.total_cost += r.cost
            model_key = r.model or "unknown"
            if model_key not in stats.by_model:
                stats.by_model[model_key] = {"requests": 0, "tokens": 0, "cost": 0.0}
            stats.by_model[model_key]["requests"] += 1
            stats.by_model[model_key]["tokens"] += r.total_tokens
            if r.cost is not None:
                stats.by_model[model_key]["cost"] += r.cost
        stats.total_cost = round(stats.total_cost, 6)
        return stats

    def get_total_stats(self) -> UsageStats:
        stats = UsageStats()
        for r in self._iter_records():
            stats.total_requests += 1
            stats.total_prompt_tokens += r.prompt_tokens
            stats.total_completion_tokens += r.completion_tokens
            stats.total_tokens += r.total_tokens
            if r.cost is not None:
                stats.total_cost += r.cost
            model_key = r.model or "unknown"
            if model_key not in stats.by_model:
                stats.by_model[model_key] = {"requests": 0, "tokens": 0, "cost": 0.0}
            stats.by_model[model_key]["requests"] += 1
            stats.by_model[model_key]["tokens"] += r.total_tokens
            if r.cost is not None:
                stats.by_model[model_key]["cost"] += r.cost
        stats.total_cost = round(stats.total_cost, 6)
        return stats

    def get_recent(self, limit: int = 20) -> list[TokenUsage]:
        records = self._iter_records()
        return records[-limit:]

    def clear(self) -> None:
        if self.log_path.exists():
            self.log_path.unlink()
