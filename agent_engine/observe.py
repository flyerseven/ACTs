"""Observability layer for the Agent decision engine.

Provides structured logging, event callbacks, Mermaid flowchart
generation, and runtime metrics reporting.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger as _loguru_logger

from agent_engine.types import AgentState


class Event:
    """An observable event emitted during the decision loop."""

    __slots__ = ("type", "timestamp", "data")

    def __init__(self, type: str, data: dict | None = None):
        self.type = type
        self.timestamp = datetime.now(timezone.utc)
        self.data = data or {}


# Event → loguru level mapping.  Lifecycle events are informational;
# per-step detail events are DEBUG so they only appear in the file sink
# (or on console when debug mode is active).
_EVENT_LEVELS: dict[str, str] = {
    "start":       "INFO",
    "done":        "INFO",
    "stopped":     "WARNING",
    "step_start":  "DEBUG",
    "step_end":    "DEBUG",
    "tool_call":   "DEBUG",
    "tool_result": "DEBUG",
    "reflection":  "INFO",
}


class Observer:
    """Unified observability layer.

    - Structured logging via loguru (text or JSON format)
    - Event callbacks for external integration (e.g., GUI updates)
    - Mermaid flowchart generation from AgentState steps
    - Runtime metrics report
    """

    def __init__(self, log_format: str = "text", log_level: str = "INFO"):
        self._callbacks: list[Callable[[Event], None]] = []
        self._events: list[Event] = []
        self._setup_logging(log_format, log_level)

    def _setup_logging(self, log_format: str, log_level: str = "INFO") -> None:
        """Configure loguru for standalone use (CLI mode).

        When the application entry point (main.py) has already called
        ``setup_logging()`` from ``utils.logger``, loguru will already
        have handlers — we skip reconfiguration to preserve those
        dual-sink settings.

        In standalone CLI mode (no prior setup), we add a minimal
        console sink so output is visible.
        """
        if _loguru_logger._core.handlers:
            # Already configured by the application (e.g. main.py via
            # utils.logger.setup_logging).  Don't overwrite.
            return

        _loguru_logger.remove()
        if log_format == "json":
            _loguru_logger.add(
                sys.stderr,
                format='{"time":"{time}","level":"{level}","message":"{message}"}',
                level=log_level,
            )
        else:
            _loguru_logger.add(
                sys.stderr,
                format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
                level=log_level,
                colorize=True,
            )

    # -- Events --

    def on_event(self, callback: Callable[[Event], None]) -> None:
        """Register a callback for all events."""
        self._callbacks.append(callback)

    def emit(self, event: Event) -> None:
        """Emit an event to registered callbacks and the log.

        The log level is chosen based on the event type:
        lifecycle events (start/done/stopped) use INFO/WARNING;
        per-step detail events use DEBUG.
        """
        self._events.append(event)
        level = _EVENT_LEVELS.get(event.type, "DEBUG")
        _loguru_logger.log(level, "[{}] {}", event.type, event.data)
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    # -- Mermaid --

    def generate_mermaid(self, state: AgentState) -> str:
        """Generate a Mermaid flowchart from the agent's step history."""
        lines = ["flowchart TD"]

        for step in state.steps:
            node_id = f"S{step.index}"
            if step.phase == "think":
                label = f"THINK: {step.thought[:40]}"
            elif step.phase == "act" and step.tool_call:
                label = f"ACT: {step.tool_call.tool_name}"
                if step.tool_call.error:
                    label += " (ERROR)"
            elif step.phase == "reflect":
                label = f"REFLECT: {step.reflection[:40]}"
            else:
                label = step.phase.upper()

            label = label.replace('"', "'")
            lines.append(f'    {node_id}["{label}"]')

        # Connect steps
        if state.steps:
            lines.append("    Start([Goal]) --> S0")
            for i in range(len(state.steps) - 1):
                lines.append(f"    S{i} --> S{i + 1}")
            last = f"S{len(state.steps) - 1}"
            lines.append(f"    {last} --> End([{state.status.upper()}])")
        else:
            lines.append("    Start([Goal]) --> End([No steps])")

        return "\n".join(lines)

    # -- Metrics --

    def get_report(self, state: AgentState) -> str:
        """Generate a human-readable metrics report."""
        elapsed = ""
        if state.started_at:
            end = state.finished_at or datetime.now(timezone.utc)
            secs = (end - state.started_at).total_seconds()
            elapsed = f"{secs:.1f}s"

        tool_calls = sum(1 for s in state.steps if s.tool_call is not None)
        tool_errors = sum(1 for s in state.steps if s.tool_call and s.tool_call.error)

        lines = [
            "=" * 50,
            "  Agent Run Report",
            "=" * 50,
            f"  Status:       {state.status}",
            f"  Goal:         {state.goal[:80]}",
            f"  Total steps:  {len(state.steps)}",
            f"  Tool calls:   {tool_calls}",
            f"  Tool errors:  {tool_errors}",
            f"  Errors:       {len(state.errors)}",
            f"  Warnings:     {len(state.warnings)}",
            f"  Elapsed:      {elapsed}",
            "=" * 50,
        ]
        return "\n".join(lines)
