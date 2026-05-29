"""Main decision engine for the Agent.

AgentEngine is the single entry point. It composes all components
and drives the OBSERVE→THINK→ACT→REFLECT loop until the goal
is achieved or a stop condition is met.
"""
from __future__ import annotations

import json
import sys
import time
from typing import Callable

from loguru import logger

from agent_engine.types import AgentState, Step
from agent_engine.state import StateManager
from agent_engine.tools import ToolRegistry
from agent_engine.memory import MemoryManager
from agent_engine.reflect import Reflector
from agent_engine.observe import Observer, Event
from agent_engine.safety import SafetyChecker
from llm.base import LLMAdapter
from agent_engine.config import EngineConfig


class AgentEngine:
    """The main Agent decision engine.

    Composes all subsystems and executes the autonomous decision loop:

        OBSERVE → THINK → ACT → REFLECT → (repeat or stop)

    Usage:
        engine = AgentEngine(llm=adapter, config=EngineConfig())
        engine.tools.register_from_func(my_tool)
        state = await engine.run("Your goal here")
    """

    # Mapping from skill names (user-configured) to the tool names they
    # enable.  Used to filter the tool schemas sent to the LLM when
    # ``enabled_skills`` is passed to ``run()``.
    SKILL_TO_TOOL_NAMES: dict[str, set[str]] = {
        "calculator": {"calculate"},
        "files": {"read_file", "write_file", "list_files"},
        "search": {"web_search"},
        "code_exec": {"execute_python"},
    }

    def __init__(
        self,
        llm: LLMAdapter,
        config: EngineConfig | None = None,
        state: StateManager | None = None,
        tools: ToolRegistry | None = None,
        memory: MemoryManager | None = None,
        skill_tool_map: dict[str, set[str]] | None = None,
    ):
        self.config = config or EngineConfig()
        self.llm = llm
        self.state = state or StateManager()
        self.tools = tools or ToolRegistry()
        self.memory = memory or MemoryManager(
            compress_trigger_tokens=self.config.compress_trigger_tokens,
            compress_target_tokens=self.config.compress_target_tokens,
        )
        self.reflector = Reflector(reflect_interval=self.config.reflect_interval)
        self.observer = Observer(log_format=self.config.log_format)
        self.safety = SafetyChecker(
            max_steps=self.config.max_steps,
            tool_whitelist=self.config.tool_whitelist_set,
        )
        self._step_t0: float = 0
        self._enabled_skills: set[str] | None = None
        # Merge instance-level skill→tool mapping with class-level defaults.
        self._skill_tool_names = dict(self.SKILL_TO_TOOL_NAMES)
        if skill_tool_map:
            self._skill_tool_names.update(skill_tool_map)

    def _debug(self, *args, end: str = "\n") -> None:
        """Print debug output to stderr when debug mode is enabled."""
        if self.config.debug:
            print(*args, file=sys.stderr, end=end)

    def _debug_step_header(self, step_index: int) -> None:
        """Print a visual step separator."""
        self._step_t0 = time.monotonic()
        self._debug(f"\n{'═'*50}")
        self._debug(f"  STEP {step_index + 1}")
        self._debug(f"{'─'*50}")

    def _debug_phase(self, phase: str, detail: str = "", elapsed: float = 0, is_sub: bool = False) -> None:
        """Print a phase line with optional timing and detail."""
        marker = "  └─" if is_sub else "  ▶"
        timing = f" [{elapsed:.1f}s]" if elapsed else ""
        if detail:
            self._debug(f"{marker} {phase}{timing}  → {detail}")
        else:
            self._debug(f"{marker} {phase}{timing}")

    def _debug_request(self, messages: list[dict], tool_schemas: list[dict] | None) -> None:
        """Dump the full LLM request body to stderr for inspection."""
        import json as _json
        body: dict = {"messages": messages}
        if tool_schemas:
            body["tools"] = tool_schemas
        self._debug(f"\n  ╔{'═'*58}")
        self._debug(f"  ║  LLM REQUEST BODY (full)")
        self._debug(f"  ╠{'═'*58}")
        for line in _json.dumps(body, indent=2, ensure_ascii=False).splitlines():
            self._debug(f"  ║ {line}")
        self._debug(f"  ╚{'═'*58}")

    async def run(self, goal: str, on_thought_chunk: Callable[[str], None] | None = None,
                  system_prompt: str = "", enabled_skills: list[str] | None = None) -> AgentState:
        """Execute the full decision loop for the given goal.

        Args:
            goal: The goal to achieve.
            on_thought_chunk: Optional callback receiving each streaming
                thought chunk during the THINK phase.
            system_prompt: Optional agent personality/role prompt,
                placed after the decision-loop rules as context.
            enabled_skills: Optional list of skill names enabled for this run.
        """
        self.state.start(goal)

        # Decision-loop rules come FIRST so they aren't buried by
        # a long agent system prompt.  The agent's personality/role
        # follows as contextual guidance.
        rules = (
            "You operate in a strict OBSERVE→THINK→ACT→REFLECT loop. "
            "Each response MUST end with exactly one of these two signals:\n\n"
            "  - If the goal is achieved: output 'DONE' followed by the final answer.\n"
            "  - If you need to take action: request a tool call.\n\n"
            "Do NOT output both. Do NOT output neither."
        )
        if system_prompt.strip():
            full_prompt = f"{rules}\n\n---\n\nYour role and context:\n{system_prompt.strip()}"
        else:
            full_prompt = f"{rules}\n\n---\n\nYou are an autonomous AI agent."

        self.memory.set_system_prompt(full_prompt)
        self.memory.add("user", goal)
        self.observer.emit(Event("start", {"goal": goal}))

        self._enabled_skills = set(enabled_skills) if enabled_skills else None
        skills = enabled_skills or []
        registered_tools = self.tools.list_tools()
        registered_names = [t.name for t in registered_tools]
        self._debug(f"\n{'='*50}")
        self._debug(f"  GOAL: {goal}")
        self._debug(f"  SKILLS: {skills if skills else '(none)'}")
        self._debug(f"  TOOLS:  {registered_names if registered_names else '(none)'}")
        self._debug(f"  SYSTEM PROMPT ({len(full_prompt)} chars):")
        for line in full_prompt.splitlines():
            self._debug(f"    {line}")
        self._debug(f"{'='*50}")

        consecutive_llm_errors = 0
        MAX_CONSECUTIVE_LLM_ERRORS = 3

        while self.state.state.status == "running":
            if self.safety.should_stop(self.state.state):
                reason = "max_steps" if self.state.state.current_step_index >= self.config.max_steps else "user_interrupt"
                self.state.stop("stopped" if reason == "user_interrupt" else "failed")
                self.observer.emit(Event("stopped", {"reason": reason}))
                self._debug(f"\n  ⛔ STOPPED: {reason}")
                break

            step_index = self.state.state.current_step_index
            self.observer.emit(Event("step_start", {"index": step_index}))

            self._debug_step_header(step_index)

            context = self.memory.get_context_messages()
            step = Step(index=step_index, phase="observe")

            # OBSERVE
            msg_count = len(context)
            est_tokens = self.memory.estimate_tokens()
            self._debug_phase("OBSERVE", f"{msg_count} msgs, ~{est_tokens} tokens")

            # Hard guard: force-compress if we're dangerously close to typical
            # context limits (DeepSeek ≈ 64K, GPT-4 ≈ 128K).  Aggressive
            # compression at 24K gives plenty of headroom.
            HARD_LIMIT = 24_000
            if est_tokens > HARD_LIMIT:
                self._debug_phase("MEMORY", f"force-compress: ~{est_tokens} tokens exceeds {HARD_LIMIT}", is_sub=True)
                self.memory.compress(force=True)
                context = self.memory.get_context_messages()
                est_tokens = self.memory.estimate_tokens()
                self._debug_phase("OBSERVE", f"after compress: ~{est_tokens} tokens", is_sub=True)

            # Stuck detection: if we've taken many steps with tool calls but
            # never said DONE, the model is likely looping.  Inject a one-shot
            # stop prompt (not persisted to memory, so it doesn't accumulate).
            if step_index == 10:
                context = list(context) + [{"role": "user", "content": (
                    "[SYSTEM] You have taken 10 steps. If the goal is achieved, "
                    "say DONE now. If you are stuck, say FAILED. "
                    "Do NOT request more tools unless absolutely essential."
                )}]
                self._debug_phase("OBSERVE", "injected stop prompt", is_sub=True)

            # Absolute safety: prevent runaway loops
            if step_index >= 20:
                self.state.stop("failed")
                self.observer.emit(Event("stopped", {"reason": "runaway_loop"}))
                self._debug(f"\n  ⛔ STOPPED: runaway loop ({step_index} steps)")
                break

            # THINK
            step.phase = "think"
            try:
                all_tool_count = len(self.tools.list_tools())
                t_think = time.monotonic()
                tool_schemas = self.tools.list_openai_schemas() if all_tool_count else None
                if tool_schemas and self._enabled_skills is not None:
                    allowed_names: set[str] = set()
                    for skill in self._enabled_skills:
                        allowed_names.update(self._skill_tool_names.get(skill, set()))
                    tool_schemas = [t for t in tool_schemas if t["name"] in allowed_names]
                    if not tool_schemas:
                        tool_schemas = None
                active_count = len(tool_schemas) if tool_schemas else 0
                if self._enabled_skills is not None:
                    self._debug_phase("THINK", f"tools={active_count}/{all_tool_count} (filtered by skills)", is_sub=False)
                else:
                    self._debug_phase("THINK", f"tools={active_count}", is_sub=False)

                # ── Dump full request body to debug output ──
                if self.config.debug:
                    self._debug_request(context, tool_schemas)

                response = await self.llm.chat(
                    context,
                    model=self.config.llm_model,
                    temperature=self.config.llm_temperature,
                    max_tokens=self.config.llm_max_tokens,
                    tools=tool_schemas,
                    on_chunk=on_thought_chunk,
                )
                t_think = time.monotonic() - t_think
                step.thought = response.content
                tool_calls_dicts = None
                if response.tool_calls:
                    tool_calls_dicts = [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                        for tc in response.tool_calls
                    ]
                self.memory.add("assistant", response.content, tool_calls=tool_calls_dicts)

                if self.memory.estimate_tokens() > self.config.compress_trigger_tokens:
                    self.memory.compress()
                    self._debug_phase("MEMORY", "compressed", is_sub=True)

                thought_preview = response.content[:200].replace("\n", " ")
                if len(response.content) > 200:
                    thought_preview += "…"
                self._debug_phase("THINK", thought_preview, elapsed=t_think)
                consecutive_llm_errors = 0
            except Exception as e:
                error_msg = f"LLM error at step {step_index}: {e}"
                logger.error(error_msg)
                self.state.record_error(error_msg)
                step.observation = error_msg
                self.state.add_step(step)
                self._debug_phase("THINK", f"ERROR: {e}", is_sub=True)

                consecutive_llm_errors += 1
                if consecutive_llm_errors >= MAX_CONSECUTIVE_LLM_ERRORS:
                    self.state.stop("failed")
                    self.observer.emit(Event("stopped", {"reason": "consecutive_llm_errors"}))
                    self._debug(f"\n  ⛔ STOPPED: {consecutive_llm_errors} consecutive LLM errors")
                    break
                continue

            # Check for DONE — allow single-step answers
            if "DONE" in response.content.upper():
                step.is_completed = True
                self.state.add_step(step)
                self.state.stop("done")
                self.observer.emit(Event("done", {"steps": len(self.state.state.steps)}))
                t_total = time.monotonic() - self._step_t0
                self._debug_phase("DONE", f"completed in {len(self.state.state.steps)} steps")
                self._debug(f"{'═'*50}")
                break

            # ACT
            if response.tool_calls:
                step.phase = "act"
                for tc_req in response.tool_calls:
                    if not self.safety.check_tool(tc_req["name"]):
                        logger.warning(f"Tool '{tc_req['name']}' blocked by safety")
                        self._debug_phase("ACT", f"{tc_req['name']}: BLOCKED", is_sub=True)
                        continue

                    if not self.safety._run_hooks("before_action", tc_req["name"], tc_req["arguments"]):
                        self._debug_phase("ACT", f"{tc_req['name']}: hook blocked", is_sub=True)
                        continue

                    args_preview = str(tc_req["arguments"])[:80]
                    t_tool = time.monotonic()
                    tool_call = await self.tools.call(tc_req["name"], tc_req["arguments"])
                    t_tool = time.monotonic() - t_tool
                    step.tool_call = tool_call

                    self.observer.emit(Event("tool_call", {
                        "index": step_index,
                        "name": tc_req["name"],
                        "arguments": tc_req["arguments"],
                    }))

                    if tool_call.error:
                        step.observation = f"Tool error: {tool_call.error}"
                        self.state.record_error(tool_call.error)
                        self._debug_phase("ACT", f"{tc_req['name']}: ERROR → {tool_call.error[:100]}", elapsed=t_tool, is_sub=True)
                    else:
                        step.observation = str(tool_call.result)[:1000]
                        self.memory.add("tool", step.observation, name=tc_req["name"], tool_call_id=tc_req["id"])
                        result_preview = step.observation[:100].replace("\n", " ")
                        if len(step.observation) > 100:
                            result_preview += "…"
                        self._debug_phase("ACT", f"{tc_req['name']}({args_preview}) → {result_preview}", elapsed=t_tool, is_sub=True)

                    self.observer.emit(Event("tool_result", {
                        "index": step_index,
                        "result": step.observation,
                        "error": tool_call.error or "",
                        "duration_ms": tool_call.duration_ms,
                    }))

                    self.safety._run_hooks("after_action", tc_req["name"], tool_call.result, tool_call.error)
                    self.state.update_metrics(tool_calls=1)
            else:
                # No tool calls and no DONE → LLM considers the task complete
                step.is_completed = True
                self.state.add_step(step)
                self.state.stop("done")
                self.observer.emit(Event("done", {"steps": len(self.state.state.steps), "reason": "no_tool_calls"}))
                self._debug_phase("DONE", f"completed (no further actions) in {len(self.state.state.steps)} steps")
                self._debug(f"{'═'*50}")
                break

            # REFLECT
            if step_index > 0 and step_index % self.reflector.reflect_interval == 0:
                step.phase = "reflect"
                t_reflect = time.monotonic()
                reflection = await self.reflector.reflect(self.state.state, self.memory, self.llm)
                t_reflect = time.monotonic() - t_reflect
                step.reflection = reflection.summary
                self.observer.emit(Event("reflection", {
                    "index": step_index,
                    "summary": reflection.summary,
                    "is_stuck": reflection.is_stuck,
                }))
                flags = []
                if reflection.is_stuck:
                    flags.append("STUCK")
                    logger.warning(f"Agent appears stuck: {reflection.summary}")
                    self.state.record_error(f"Stuck: {reflection.summary}")
                if reflection.detected_loop:
                    flags.append("LOOP")
                status = ",".join(flags) if flags else "ok"
                summary = reflection.summary[:120].replace("\n", " ")
                self._debug_phase("REFLECT", f"[{status}] off_track={reflection.off_track_score:.2f} → {summary}", elapsed=t_reflect)
                if not reflection.should_continue:
                    self.state.stop("failed")
                    self.observer.emit(Event("stopped", {"reason": "stuck"}))
                    self.state.add_step(step)
                    self._debug(f"\n  ⛔ STOPPED: stuck detected")
                    break

            self.state.add_step(step)
            self.observer.emit(Event("step_end", {"index": step_index, "phase": step.phase}))

        report = self.observer.get_report(self.state.state)
        logger.info(f"\n{report}")
        self._debug(f"\n{report}")
        return self.state.state

    def request_stop(self) -> None:
        """Request an emergency stop."""
        self.safety.request_stop()
