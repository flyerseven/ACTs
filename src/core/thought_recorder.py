"""ThoughtRecorder — intermediate layer between AgentEngine and UI.

Captures each phase of the OBSERVE→THINK→ACT→REFLECT loop,
emits pyqtSignals for the HTML frontend via QWebChannel,
and logs formatted text via loguru for CLI compatibility.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class StepSnapshot:
    index: int
    phase: str = "observe"
    thought: str = ""
    thought_streaming: bool = False
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: str = ""
    tool_error: str = ""
    tool_duration_ms: float = 0.0
    reflection: str = ""
    is_stuck: bool = False
    is_completed: bool = False


class ThoughtRecorder(QObject):
    """Emits signals for each phase of the decision loop.

    Always logs to loguru (CLI). Signals are picked up by
    QWebChannel when a ThoughtView is attached.
    """

    run_started = pyqtSignal(str)
    step_started = pyqtSignal(int)
    thought_chunk = pyqtSignal(int, str)
    thought_done = pyqtSignal(int, str)
    tool_call_started = pyqtSignal(int, str, str)
    tool_result = pyqtSignal(int, str, str, float)
    reflection_done = pyqtSignal(int, str, bool)
    step_ended = pyqtSignal(int, bool)
    run_finished = pyqtSignal(str, int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._steps: list[StepSnapshot] = []
        self._current_step: StepSnapshot | None = None
        self._goal: str = ""

    # -- Engine callback interface (called from worker thread via queued connections) --

    def start_run(self, goal: str) -> None:
        self._goal = goal
        self._steps.clear()
        self._current_step = None
        logger.info(f"Agent run started. Goal: {goal}")
        self.run_started.emit(goal)

    def on_thought_chunk(self, index: int, chunk: str) -> None:
        if self._current_step is None or self._current_step.index != index:
            self._current_step = StepSnapshot(index=index, phase="think")
            self._steps.append(self._current_step)
            logger.info(f"  Step {index} — THINK")
            self.step_started.emit(index)
        self._current_step.thought += chunk
        self._current_step.thought_streaming = True
        self.thought_chunk.emit(index, chunk)

    def on_thought_done(self, index: int, full_text: str) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.thought = full_text
            self._current_step.thought_streaming = False
        logger.info(f"  Step {index} — THINK complete ({len(full_text)} chars)")
        self.thought_done.emit(index, full_text)

    def on_tool_call(self, index: int, tool_name: str, args: dict) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.tool_name = tool_name
            self._current_step.tool_args = args
            self._current_step.phase = "act"
        logger.info(f"  Step {index} — ACT: {tool_name}({json.dumps(args, ensure_ascii=False)})")
        self.tool_call_started.emit(index, tool_name, json.dumps(args, ensure_ascii=False))

    def on_tool_result(self, index: int, result: str, error: str, duration_ms: float) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.tool_result = result
            self._current_step.tool_error = error
            self._current_step.tool_duration_ms = duration_ms
        if error:
            logger.error(f"  Step {index} — Tool error: {error}")
        else:
            logger.info(f"  Step {index} — Tool result ({len(result)} chars, {duration_ms:.0f}ms)")
        self.tool_result.emit(index, result, error, duration_ms)

    def on_reflection(self, index: int, summary: str, is_stuck: bool) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.phase = "reflect"
            self._current_step.reflection = summary
            self._current_step.is_stuck = is_stuck
        if is_stuck:
            logger.warning(f"  Step {index} — REFLECT: stuck — {summary}")
        else:
            logger.info(f"  Step {index} — REFLECT: {summary}")
        self.reflection_done.emit(index, summary, is_stuck)

    def on_step_end(self, index: int, is_completed: bool) -> None:
        if self._current_step and self._current_step.index == index:
            self._current_step.is_completed = is_completed
        logger.info(f"  Step {index} — {'COMPLETED' if is_completed else 'NEXT'}")
        self.step_ended.emit(index, is_completed)

    def finish_run(self, status: str, errors: list[str]) -> None:
        total_steps = len(self._steps)
        logger.info(f"Run finished. Status: {status}, Steps: {total_steps}, Errors: {len(errors)}")
        self.run_finished.emit(status, total_steps, json.dumps(errors, ensure_ascii=False))

    # -- Export --

    def to_markdown(self) -> str:
        lines = [f"# Agent Run: {self._goal}", "", f"**Steps:** {len(self._steps)}", ""]
        for step in self._steps:
            lines.append(f"## Round {step.index + 1}")
            lines.append("")
            if step.thought:
                lines.append(f"### THINK\n\n{step.thought}\n")
            if step.tool_name:
                lines.append(f"### ACT — `{step.tool_name}`\n")
                lines.append(f"```json\n{json.dumps(step.tool_args, indent=2, ensure_ascii=False)}\n```\n")
                if step.tool_error:
                    lines.append(f"**Error:** {step.tool_error}\n")
                else:
                    lines.append(f"```\n{step.tool_result}\n```\n")
            if step.reflection:
                lines.append(f"### REFLECT\n\n{step.reflection}\n")
            lines.append("---\n")
        return "\n".join(lines)

    def to_json(self) -> str:
        steps_data = []
        for step in self._steps:
            steps_data.append({
                "index": step.index,
                "phase": step.phase,
                "thought": step.thought,
                "tool_name": step.tool_name,
                "tool_args": step.tool_args,
                "tool_result": step.tool_result,
                "tool_error": step.tool_error,
                "tool_duration_ms": step.tool_duration_ms,
                "reflection": step.reflection,
                "is_stuck": step.is_stuck,
                "is_completed": step.is_completed,
            })
        return json.dumps({
            "goal": self._goal,
            "steps": steps_data,
        }, indent=2, ensure_ascii=False)

    def reset(self) -> None:
        self._steps.clear()
        self._current_step = None
        self._goal = ""
