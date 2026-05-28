"""Main decision engine for the Agent.

AgentEngine is the single entry point. It composes all components
and drives the OBSERVE→THINK→ACT→REFLECT loop until the goal
is achieved or a stop condition is met.
"""
from __future__ import annotations

from typing import Callable

from loguru import logger

from agent_engine.types import AgentState, Step
from agent_engine.state import StateManager
from agent_engine.tools import ToolRegistry
from agent_engine.memory import MemoryManager
from agent_engine.reflect import Reflector
from agent_engine.observe import Observer, Event
from agent_engine.safety import SafetyChecker
from agent_engine.llm import LLMAdapter
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

    def __init__(
        self,
        llm: LLMAdapter,
        config: EngineConfig | None = None,
        state: StateManager | None = None,
        tools: ToolRegistry | None = None,
        memory: MemoryManager | None = None,
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

    async def run(self, goal: str, on_thought_chunk: Callable[[str], None] | None = None) -> AgentState:
        """Execute the full decision loop for the given goal.

        Args:
            goal: The goal to achieve.
            on_thought_chunk: Optional callback receiving each streaming
                thought chunk during the THINK phase.
        """
        self.state.start(goal)
        self.memory.set_system_prompt(
            f"You are an autonomous AI agent. Your goal is: {goal}\n\n"
            "Follow the OBSERVE→THINK→ACT→REFLECT loop:\n"
            "1. THINK: Analyze the situation and decide the next action.\n"
            "2. ACT: Request a tool call if needed.\n"
            "3. When the goal is achieved, say 'DONE' and explain the result.\n"
            "4. If stuck, admit it and say 'FAILED' with the reason.\n"
        )
        self.memory.add("user", goal)
        self.observer.emit(Event("start", {"goal": goal}))

        while self.state.state.status == "running":
            if self.safety.should_stop(self.state.state):
                reason = "max_steps" if self.state.state.current_step_index >= self.config.max_steps else "user_interrupt"
                self.state.stop("stopped" if reason == "user_interrupt" else "failed")
                self.observer.emit(Event("stopped", {"reason": reason}))
                break

            step_index = self.state.state.current_step_index
            self.observer.emit(Event("step_start", {"index": step_index}))

            context = self.memory.get_context_messages()
            step = Step(index=step_index, phase="observe")

            # THINK
            step.phase = "think"
            try:
                tool_schemas = self.tools.list_openai_schemas() if self.tools.list_tools() else None
                response = await self.llm.chat(context, tool_schemas, on_chunk=on_thought_chunk)
                step.thought = response.content
                self.memory.add("assistant", response.content)

                if self.memory.estimate_tokens() > self.config.compress_trigger_tokens:
                    self.memory.compress()
            except Exception as e:
                error_msg = f"LLM error at step {step_index}: {e}"
                logger.error(error_msg)
                self.state.record_error(error_msg)
                step.observation = error_msg
                self.state.add_step(step)
                continue

            # Check for DONE
            if "DONE" in response.content.upper() and len(self.state.state.steps) > 0:
                step.is_completed = True
                self.state.add_step(step)
                self.state.stop("done")
                self.observer.emit(Event("done", {"steps": len(self.state.state.steps)}))
                break

            # ACT
            if response.tool_calls:
                step.phase = "act"
                for tc_req in response.tool_calls:
                    if not self.safety.check_tool(tc_req.name):
                        logger.warning(f"Tool '{tc_req.name}' blocked by safety")
                        continue

                    if not self.safety._run_hooks("before_action", tc_req.name, tc_req.arguments):
                        continue

                    tool_call = await self.tools.call(tc_req.name, tc_req.arguments)
                    step.tool_call = tool_call

                    self.observer.emit(Event("tool_call", {
                        "index": step_index,
                        "name": tc_req.name,
                        "arguments": tc_req.arguments,
                    }))

                    if tool_call.error:
                        step.observation = f"Tool error: {tool_call.error}"
                        self.state.record_error(tool_call.error)
                    else:
                        step.observation = str(tool_call.result)[:1000]
                        self.memory.add("tool", step.observation, name=tc_req.name)

                    self.observer.emit(Event("tool_result", {
                        "index": step_index,
                        "result": step.observation,
                        "error": tool_call.error or "",
                        "duration_ms": tool_call.duration_ms,
                    }))

                    self.safety._run_hooks("after_action", tc_req.name, tool_call.result, tool_call.error)
                    self.state.update_metrics(tool_calls=1)
            else:
                step.observation = "No tool calls requested."

            # REFLECT
            if step_index > 0 and step_index % self.reflector.reflect_interval == 0:
                step.phase = "reflect"
                reflection = await self.reflector.reflect(self.state.state, self.memory, self.llm)
                step.reflection = reflection.summary
                self.observer.emit(Event("reflection", {
                    "index": step_index,
                    "summary": reflection.summary,
                    "is_stuck": reflection.is_stuck,
                }))
                if reflection.is_stuck:
                    logger.warning(f"Agent appears stuck: {reflection.summary}")
                    self.state.record_error(f"Stuck: {reflection.summary}")
                if not reflection.should_continue:
                    self.state.stop("failed")
                    self.observer.emit(Event("stopped", {"reason": "stuck"}))
                    self.state.add_step(step)
                    break

            self.state.add_step(step)
            self.observer.emit(Event("step_end", {"index": step_index, "phase": step.phase}))

        report = self.observer.get_report(self.state.state)
        logger.info(f"\n{report}")
        return self.state.state

    def request_stop(self) -> None:
        """Request an emergency stop."""
        self.safety.request_stop()
