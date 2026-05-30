"""State manager for the Agent decision engine.

Tracks the agent's runtime state: goal, sub-goals, steps, errors,
metrics, and the state machine lifecycle (idle→running→done/failed/stopped).
"""
from __future__ import annotations

from datetime import datetime, timezone

from agent_engine.types import AgentState, Step


class StateManager:
    """Manages the Agent's full runtime state.

    All mutations go through this class; the internal AgentState
    pydantic model acts as the single source of truth.
    """

    VALID_TRANSITIONS: dict[str, set[str]] = {
        "idle": {"running"},
        "running": {"paused", "done", "failed", "stopped"},
        "paused": {"running", "stopped"},
        "done": set(),
        "failed": set(),
        "stopped": set(),
    }

    def __init__(self):
        self.state = AgentState(goal="")

    # -- Lifecycle --

    def start(self, goal: str) -> None:
        if self.state.status != "idle":
            raise RuntimeError(f"Cannot start: agent is already {self.state.status}")
        self.state.goal = goal
        self.state.status = "running"
        self.state.started_at = datetime.now(timezone.utc)

    def pause(self) -> None:
        if self.state.status not in ("running",):
            raise RuntimeError("Cannot pause: agent is not running")
        self._transition("paused")

    def resume(self) -> None:
        self._transition("running")

    def stop(self, reason: str) -> None:
        valid_final = {"done", "failed", "stopped"}
        if reason not in valid_final:
            raise ValueError(f"Stop reason must be one of {valid_final}, got '{reason}'")
        self._transition(reason)
        self.state.finished_at = datetime.now(timezone.utc)

    def _transition(self, target: str) -> None:
        allowed = self.VALID_TRANSITIONS.get(self.state.status, set())
        if target not in allowed:
            raise RuntimeError(f"Cannot transition from '{self.state.status}' to '{target}'")
        self.state.status = target

    # -- Steps --

    def add_step(self, step: Step) -> None:
        self.state.steps.append(step)
        self.state.current_step_index = len(self.state.steps)

    def get_last_n_steps(self, n: int) -> list[Step]:
        return self.state.steps[-n:]

    # -- Sub-goals --

    def set_sub_goals(self, goals: list[str]) -> None:
        self.state.sub_goals = list(goals)

    def complete_sub_goal(self, index: int) -> None:
        if 0 <= index < len(self.state.sub_goals):
            current = self.state.sub_goals[index]
            if not current.startswith("[✓] "):
                self.state.sub_goals[index] = f"[✓] {current}"

    # -- Errors & Warnings --

    def record_error(self, error: str) -> None:
        if error not in self.state.errors:
            self.state.errors.append(error)

    def record_warning(self, warning: str) -> None:
        if warning not in self.state.warnings:
            self.state.warnings.append(warning)

    def get_error_summary(self) -> str:
        if not self.state.errors:
            return "No errors recorded."
        return f"{len(self.state.errors)} unique errors: " + "; ".join(self.state.errors[-5:])

    # -- Metrics --

    def update_metrics(self, **kwargs: int | float) -> None:
        for key, value in kwargs.items():
            current = self.state.metrics.get(key, 0)
            self.state.metrics[key] = current + value

    def get_metrics(self) -> dict:
        elapsed = 0.0
        if self.state.started_at:
            end = self.state.finished_at or datetime.now(timezone.utc)
            elapsed = (end - self.state.started_at).total_seconds()
        return {
            **self.state.metrics,
            "elapsed_sec": elapsed,
            "total_steps": len(self.state.steps),
            "error_count": len(self.state.errors),
        }

    # -- Serialization --

    def to_dict(self) -> dict:
        return self.state.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> "StateManager":
        sm = cls()
        sm.state = AgentState(**data)
        return sm
