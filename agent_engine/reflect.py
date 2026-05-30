"""Reflection module for the Agent decision engine.

Implements periodic self-reflection: every N steps, the agent reviews
its progress against the original goal, detects loops and repetition,
and suggests strategy adjustments.
"""
from __future__ import annotations

from pydantic import BaseModel

from agent_engine.types import AgentState, Step


class Reflection(BaseModel):
    """Result of a reflection step."""
    should_continue: bool = True
    strategy_adjustment: str = ""
    is_stuck: bool = False
    detected_loop: bool = False
    off_track_score: float = 0.0
    summary: str = ""


class Reflector:
    """Periodic self-reflection for the agent.

    Combines rule-based checks (no LLM needed) with LLM-based
    strategy review. Triggered every `reflect_interval` steps.
    """

    def __init__(self, reflect_interval: int = 3):
        self.reflect_interval = reflect_interval

    async def reflect(self, state: AgentState, memory, llm_adapter) -> Reflection:
        """Run a full reflection: rule checks + optional LLM review."""
        steps = state.steps
        reflection = Reflection()

        # Rule-based checks
        reflection.detected_loop = self.detect_repetition(steps)
        reflection.off_track_score = self.detect_off_track(state.goal, steps)

        if reflection.detected_loop:
            reflection.is_stuck = True
            reflection.should_continue = False
            reflection.summary = "Detected loop: same tool called with same arguments repeatedly."
            return reflection

        if reflection.off_track_score > 0.7:
            reflection.is_stuck = True
            reflection.summary = f"Agent appears off-track (score: {reflection.off_track_score:.2f})."

        # LLM-based strategy review
        if llm_adapter:
            try:
                review_prompt = self._build_review_prompt(state)
                msgs = memory.get_context_messages(max_tokens=4000)
                msgs.append({"role": "user", "content": review_prompt})
                resp = await llm_adapter.chat(msgs)
                reflection.strategy_adjustment = resp.content
            except Exception:
                reflection.strategy_adjustment = ""

        return reflection

    # -- Rule-based checks --

    def detect_repetition(self, steps: list[Step]) -> bool:
        """Check if the last 3 tool calls are identical."""
        tool_steps = [s for s in steps if s.tool_call is not None]
        if len(tool_steps) < 3:
            return False
        recent = tool_steps[-3:]
        first = recent[0].tool_call
        if first is None:
            return False
        for s in recent[1:]:
            tc = s.tool_call
            if tc is None:
                return False
            if tc.tool_name != first.tool_name:
                return False
            if tc.arguments != first.arguments:
                return False
        return True

    def detect_off_track(self, goal: str, steps: list[Step]) -> float:
        """Estimate how off-track the agent is (0.0 = fully on track,
        1.0 = completely off). Uses keyword overlap across thoughts,
        observations, and tool call details.

        Short-circuits to 0.0 when recent tool calls form a known
        productive pattern (e.g. write→read verification, progressive
        reads with different offsets) — those are false positives for
        the keyword heuristic.
        """
        if not steps or not goal:
            return 0.0

        goal_words = set(goal.lower().split())
        if not goal_words:
            return 0.0

        recent = steps[-5:]
        tool_names = [s.tool_call.tool_name if s.tool_call else "" for s in recent]

        # Pattern 1: write/replace followed by read = verification
        if self._has_verify_pattern(tool_names):
            return 0.0

        # Pattern 2: progressive reads with different offsets / staggered
        # exploration — the agent is systematically gathering information.
        if self._has_progressive_reads(recent):
            return 0.0

        # Keyword-overlap heuristic.
        relevant_count = 0
        for s in recent:
            text_parts = [s.thought, s.observation]
            if s.tool_call:
                text_parts.append(s.tool_call.tool_name)
                text_parts.append(" ".join(
                    f"{k} {v}" for k, v in s.tool_call.arguments.items()
                ))
            text = " ".join(text_parts).lower()
            overlap = goal_words & set(text.split())
            if overlap:
                relevant_count += 1

        return 1.0 - (relevant_count / len(recent))

    # -- Pattern helpers --

    @staticmethod
    def _has_verify_pattern(tool_names: list[str]) -> bool:
        """True when recent tool calls contain a write→read pair, which
        is a normal verification step, not stuck behavior."""
        for i in range(len(tool_names) - 1):
            if tool_names[i] in ("write_file", "replace_in_file") and tool_names[i + 1] == "read_file":
                return True
        return False

    @staticmethod
    def _has_progressive_reads(recent_steps: list[Step]) -> bool:
        """True when the agent is reading a file at different offsets —
        systematic exploration, not a loop."""
        read_args: list[dict] = []
        for s in recent_steps:
            if s.tool_call and s.tool_call.tool_name == "read_file":
                read_args.append(s.tool_call.arguments)
        if len(read_args) < 2:
            return False
        offsets: set[int] = set()
        for args in read_args:
            if "offset" in args:
                offsets.add(args["offset"])
        # At least two different offsets → progressive exploration.
        return len(offsets) >= 2

    def summarize_errors(self, errors: list[str]) -> str:
        """Deduplicate and categorize errors into a summary."""
        seen: set[str] = set()
        unique: list[str] = []
        for e in errors:
            if e not in seen:
                seen.add(e)
                unique.append(e)
        if not unique:
            return "No errors."
        return "Errors encountered: " + "; ".join(unique[-5:])

    def _build_review_prompt(self, state: AgentState) -> str:
        steps_summary = "\n".join(
            f"Step {s.index} [{s.phase}]: {s.thought[:100]}"
            for s in state.steps[-5:]
        )
        return (
            f"Goal: {state.goal}\n\n"
            f"Recent steps:\n{steps_summary}\n\n"
            f"Errors: {state.errors[-3:] if state.errors else 'None'}\n\n"
            "Review: Are we on track? Should we adjust the strategy? "
            "If the goal is achieved, say 'DONE'. If stuck, suggest a different approach."
        )
