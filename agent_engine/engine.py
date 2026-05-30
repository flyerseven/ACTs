"""Main decision engine for the Agent.

AgentEngine is the single entry point. It composes all components
and drives the OBSERVE→THINK→ACT→REFLECT loop until the goal
is achieved or a stop condition is met.
"""
from __future__ import annotations

import json
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


def _compact_body(messages: list[dict], tool_schemas: list[dict] | None, max_content: int = 300) -> str:
    """Build a compact JSON representation of the LLM request body.

    Message contents are truncated to *max_content* characters to keep
    debug output readable while still showing the structure.
    """
    compact_msgs: list[dict] = []
    for m in messages:
        c = dict(m)
        content = c.get("content", "")
        if isinstance(content, str) and len(content) > max_content:
            c["content"] = content[:max_content] + f"… ({len(content)} total)"
        compact_msgs.append(c)
    body: dict = {"messages": compact_msgs}
    if tool_schemas:
        body["tools"] = tool_schemas
    return json.dumps(body, indent=2, ensure_ascii=False)


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
        "files": {"read_file", "write_file", "list_files", "replace_in_file"},
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
        self.observer = Observer(log_format=self.config.log_format, log_level=self.config.log_level)
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

    async def run(self, goal: str, on_thought_chunk: Callable[[str], None] | None = None,
                  on_thought: Callable[[str], None] | None = None,
                  system_prompt: str = "", enabled_skills: list[str] | None = None) -> AgentState:
        """Execute the full decision loop for the given goal.

        Args:
            goal: The goal to achieve.
            on_thought_chunk: Optional callback receiving each streaming
                thought chunk during the THINK phase.
            on_thought: Optional callback receiving each reasoning/thinking
                text chunk (e.g. DeepSeek ``reasoning_content``) as it
                arrives during the THINK phase.
            system_prompt: Optional agent personality/role prompt,
                placed after the decision-loop rules as context.
            enabled_skills: Optional list of skill names enabled for this run.
        """
        self.state.start(goal)
        self._truncated_retries = 0

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

        # None = not specified → all tools allowed.  Empty list = explicitly
        # disabled → no tools at all.
        self._enabled_skills = set(enabled_skills) if enabled_skills is not None else None
        skills = enabled_skills or []
        registered_tools = self.tools.list_tools()
        registered_names = [t.name for t in registered_tools]
        logger.debug(
            "Goal: {} | Skills: {} | Tools: {} | System prompt: {} chars",
            goal[:120], skills or "(none)", registered_names or "(none)", len(full_prompt),
        )

        consecutive_llm_errors = 0
        MAX_CONSECUTIVE_LLM_ERRORS = 3

        while self.state.state.status == "running":
            if self.safety.should_stop(self.state.state):
                state = self.state.state
                if state.current_step_index >= self.config.max_steps:
                    reason = "max_steps"
                elif self.safety.stop_requested:
                    reason = "user_interrupt"
                elif len(state.errors) == 1 and state.current_step_index >= 5:
                    reason = "error_loop"
                else:
                    reason = "unknown"
                self.state.stop("stopped" if reason in ("user_interrupt", "error_loop") else "failed")
                self.observer.emit(Event("stopped", {"reason": reason}))
                logger.warning("STOPPED: {}", reason)
                break

            step_index = self.state.state.current_step_index
            self.observer.emit(Event("step_start", {"index": step_index}))

            self._step_t0 = time.monotonic()
            logger.debug("── Step {} ──", step_index + 1)

            context = self.memory.get_context_messages(
                max_tokens=self.config.context_max_tokens,
            )
            step = Step(index=step_index, phase="observe")

            # OBSERVE
            msg_count = len(context)
            est_tokens = self.memory.estimate_tokens()
            logger.debug("OBSERVE: {} msgs, ~{} tokens", msg_count, est_tokens)

            # Hard guard: force-compress if we're close to the model's context
            # limit so the LLM never receives a request that exceeds its window.
            hard_limit = self.config.context_max_tokens
            if est_tokens > hard_limit:
                logger.debug("MEMORY force-compress: ~{} tokens exceeds {}", est_tokens, HARD_LIMIT)
                self.memory.compress(force=True)
                context = self.memory.get_context_messages()
                est_tokens = self.memory.estimate_tokens()
                logger.debug("OBSERVE after compress: ~{} tokens", est_tokens)

            # Stuck detection: if we've taken many steps with tool calls but
            # never said DONE, the model is likely looping.  Inject a one-shot
            # stop prompt (not persisted to memory, so it doesn't accumulate).
            if step_index == 10:
                context = list(context) + [{"role": "user", "content": (
                    "[SYSTEM] You have taken 10 steps. If the goal is achieved, "
                    "say DONE now. If you are stuck, say FAILED. "
                    "Do NOT request more tools unless absolutely essential."
                )}]
                logger.debug("OBSERVE: injected stop prompt")

            # Absolute safety: prevent runaway loops
            if step_index >= 20:
                self.state.stop("failed")
                self.observer.emit(Event("stopped", {"reason": "runaway_loop"}))
                logger.warning("STOPPED: runaway loop ({} steps)", step_index)
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
                    logger.debug("THINK: {} tools (filtered by skills)", active_count)
                else:
                    logger.debug("THINK: {} tools", active_count)

                # Dump compact request body when debug is enabled
                if self.config.debug:
                    logger.debug("LLM request:\n{}",
                        _compact_body(context, tool_schemas))

                response = await self.llm.chat(
                    context,
                    model=self.config.llm_model,
                    temperature=self.config.llm_temperature,
                    max_tokens=self.config.llm_max_tokens,
                    tools=tool_schemas,
                    on_chunk=on_thought_chunk,
                    on_thought=on_thought,
                )
                t_think = time.monotonic() - t_think

                # ── Surface interruption reason when the stream was cut short ──
                fr = getattr(self.llm, "last_finish_reason", "")
                _interruption_notices = {
                    "length": (
                        "\n\n---\n"
                        "> ⚠️ 响应被中断：达到 token 上限（当前 max_tokens={}），"
                        "响应被截断。请增大该 Agent 的 max_tokens 设置。"
                    ).format(self.config.llm_max_tokens),
                    "content_filter": (
                        "\n\n---\n"
                        "> ⚠️ 响应被中断：内容被安全系统过滤。"
                    ),
                    "insufficient_system_resource": (
                        "\n\n---\n"
                        "> ⚠️ 响应被中断：服务器资源不足。"
                    ),
                    "thinking_exhausted": (
                        "\n\n---\n"
                        "> ⚠️ 思考被中断：思考过程消耗了所有 {} token 预算，"
                        "未能生成有效响应。请增大该 Agent 的 max_tokens 设置。"
                    ).format(self.config.llm_max_tokens),
                }
                notice = _interruption_notices.get(fr, "")
                if notice and (not response.content or fr != "stop"):
                    response.content = response.content + notice

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
                    logger.debug("MEMORY compressed")

                thought_preview = response.content[:200].replace("\n", " ")
                if len(response.content) > 200:
                    thought_preview += "…"
                logger.info("THINK [{:.1f}s]: {}", t_think, thought_preview)

                # ── Dump full LLM response to terminal + log ──
                if response.content:
                    logger.info("── LLM Content ({:,} chars) ──\n{}", len(response.content), response.content)
                if response.tool_calls:
                    for i, tc in enumerate(response.tool_calls):
                        args_json = json.dumps(tc["arguments"], ensure_ascii=False)
                        logger.info("── Tool Call [{}] {} args={}", i, tc["name"], args_json[:2000])

                consecutive_llm_errors = 0
            except Exception as e:
                ctx_info = (
                    f"step={step_index} msgs={msg_count} "
                    f"est_tokens={est_tokens} tools={active_count} "
                    f"consecutive_errors={consecutive_llm_errors + 1}"
                )
                error_msg = f"LLM error at step {step_index}: {e}"
                logger.error("{} | context: {}", error_msg, ctx_info)
                self.state.record_error(error_msg)
                step.observation = error_msg
                self.state.add_step(step)

                consecutive_llm_errors += 1
                if consecutive_llm_errors >= MAX_CONSECUTIVE_LLM_ERRORS:
                    self.state.stop("failed")
                    self.observer.emit(Event("stopped", {"reason": "consecutive_llm_errors"}))
                    logger.warning("STOPPED: {} consecutive LLM errors", consecutive_llm_errors)
                    break
                continue

            # Check for DONE — allow single-step answers
            if "DONE" in response.content.upper():
                step.is_completed = True
                self.state.add_step(step)
                self.state.stop("done")
                self.observer.emit(Event("done", {"steps": len(self.state.state.steps)}))
                t_total = time.monotonic() - self._step_t0
                logger.info("DONE in {} steps [{:.1f}s]", len(self.state.state.steps), t_total)
                break

            # ACT
            if response.tool_calls:
                step.phase = "act"
                for tc_req in response.tool_calls:
                    if not self.safety.check_tool(tc_req["name"]):
                        logger.warning("Tool '{}' blocked by safety", tc_req["name"])
                        continue

                    if not self.safety._run_hooks("before_action", tc_req["name"], tc_req["arguments"]):
                        logger.warning("ACT: {} blocked by hook", tc_req["name"])
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
                        logger.error("ACT [{:.1f}s]: {} ERROR → {}", t_tool, tc_req["name"], tool_call.error[:100])
                    else:
                        raw = str(tool_call.result)
                        limit = self.config.max_tool_result_chars
                        if len(raw) > limit:
                            truncated = raw[:limit]
                            trunc_note = (
                                f"\n\n[TRUNCATED: {len(raw)} chars → {limit} chars. "
                                f"Use read_file with offset/limit to read the rest.]"
                            )
                            step.observation = truncated + trunc_note
                            logger.debug(
                                "ACT [{:.1f}s]: {}(…) → {} chars (truncated from {})",
                                t_tool, tc_req["name"], len(step.observation), len(raw),
                            )
                        else:
                            step.observation = raw
                        result_preview = step.observation[:100].replace("\n", " ")
                        if len(step.observation) > 100:
                            result_preview += "…"
                        logger.debug("ACT [{:.1f}s]: {}({}) → {}", t_tool, tc_req["name"], args_preview, result_preview)

                    # Always record the tool result in memory — even errors.
                    # The OpenAI/DeepSeek protocol requires a tool-role message
                    # for every assistant message that has tool_calls.  Skipping
                    # this for errors creates a dangling tool_call that causes
                    # the next API request to fail with 400 Bad Request.
                    self.memory.add("tool", step.observation, name=tc_req["name"], tool_call_id=tc_req["id"])

                    self.observer.emit(Event("tool_result", {
                        "index": step_index,
                        "result": step.observation,
                        "error": tool_call.error or "",
                        "duration_ms": tool_call.duration_ms,
                    }))

                    self.safety._run_hooks("after_action", tc_req["name"], tool_call.result, tool_call.error)
                    self.state.update_metrics(tool_calls=1)
            else:
                # No tool calls and no DONE.
                # Two distinct scenarios:
                #  a) Response is completely empty — the model produced
                #     nothing (often thinking consumed all tokens).
                #  b) Response is non-empty but looks truncated mid-sentence.
                # Both warrant a retry with a nudge, but the nudge differs.
                if self._is_truncated_response(response.content):
                    self._truncated_retries += 1
                    if self._truncated_retries <= self._MAX_TRUNCATED_RETRIES:
                        content_len = len(response.content.strip())
                        logger.warning(
                            "LLM response appears {} ({} chars, ends with {!r}), "
                            "retrying ({}/{})",
                            "empty" if content_len == 0 else "truncated",
                            content_len,
                            response.content.strip()[-20:] if content_len else "",
                            self._truncated_retries,
                            self._MAX_TRUNCATED_RETRIES,
                        )
                        if content_len == 0:
                            # Completely empty — model likely wasted tokens on
                            # internal reasoning.  Push it to produce output.
                            nudge = (
                                "[SYSTEM] Your last response was completely empty — "
                                "you produced no visible output and no tool calls. "
                                "This often means your internal reasoning consumed "
                                "all available tokens.\n\n"
                                "Please respond NOW with either:\n"
                                "  - A tool call to make progress on the goal, OR\n"
                                "  - 'DONE' if the goal is truly achieved.\n\n"
                                "Do NOT output empty. You MUST produce visible output."
                            )
                        else:
                            nudge = (
                                "[SYSTEM] Your last response was cut off / truncated. "
                                "You stopped mid-sentence. Please continue from where "
                                "you left off. If the goal is already achieved, say "
                                "DONE. Otherwise, request the appropriate tool call."
                            )
                        self.memory.add("user", nudge)
                        self.state.add_step(step)
                        self.observer.emit(Event(
                            "step_end",
                            {"index": step_index, "phase": "retry_truncated"},
                        ))
                        continue
                    else:
                        logger.warning(
                            "LLM response still truncated after {} retries — "
                            "accepting as done",
                            self._MAX_TRUNCATED_RETRIES,
                        )

                # Response looks complete (or retries exhausted).
                step.is_completed = True
                self.state.add_step(step)
                self.state.stop("done")
                self.observer.emit(Event("done", {"steps": len(self.state.state.steps), "reason": "no_tool_calls"}))
                logger.info("DONE (no further actions) in {} steps", len(self.state.state.steps))
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
                    logger.warning("Agent appears stuck: {}", reflection.summary)
                    self.state.record_warning(f"Stuck: {reflection.summary}")
                    # Inject a one-shot corrective nudge so the agent knows
                    # it is looping and should change approach.  This is NOT
                    # persisted to long-term memory — it only affects the
                    # next LLM call.
                    nudge = (
                        f"[SYSTEM] You appear to be stuck or looping. "
                        f"Recent actions suggest you are repeating the same "
                        f"pattern without making progress toward the goal. "
                        f"Reflection: {reflection.summary}\n\n"
                        f"Stop re-reading the same file. If you already have "
                        f"the necessary context, take the next step: modify "
                        f"the file, run code, or declare DONE/FAILED. "
                        f"Do NOT repeat the same tool call again."
                    )
                    self.memory.add("user", nudge)
                    logger.debug("REFLECT: injected stuck-nudge prompt")
                if reflection.detected_loop:
                    flags.append("LOOP")
                status = ",".join(flags) if flags else "ok"
                summary = reflection.summary[:120].replace("\n", " ")
                logger.info("REFLECT [{:.1f}s]: [{}] off_track={:.2f} → {}",
                            t_reflect, status, reflection.off_track_score, summary)
                if not reflection.should_continue:
                    self.state.stop("failed")
                    self.observer.emit(Event("stopped", {"reason": "stuck"}))
                    self.state.add_step(step)
                    logger.warning("STOPPED: stuck detected")
                    break

            self.state.add_step(step)
            self.observer.emit(Event("step_end", {"index": step_index, "phase": step.phase}))

        report = self.observer.get_report(self.state.state)
        logger.info("\n{}", report)
        return self.state.state

    # -- Truncated-response detection --

    _MAX_TRUNCATED_RETRIES: int = 2

    @staticmethod
    def _is_truncated_response(content: str) -> bool:
        """Check whether an LLM response appears to have been cut off.

        Returns True when the content is suspiciously short and does
        not end with a sentence-terminating character — suggesting
        the stream was interrupted mid-generation.
        """
        stripped = (content or "").strip()
        if not stripped:
            return True

        # If it's long enough, assume it's a complete thought.
        if len(stripped) >= 80:
            return False

        # Explicit completion markers — definitely not truncated.
        if any(marker in stripped.upper() for marker in ("DONE", "FAILED")):
            return False

        # Sentence-ending punctuation (Chinese + English).
        _SENTENCE_END = (
            "。", "！", "？", "…", "～", "」", "』", "”", '"',
            ".", "!", "?", ")", "】", "》", "〉",
        )
        if stripped.endswith(_SENTENCE_END):
            return False

        return True

    def request_stop(self) -> None:
        """Request an emergency stop."""
        self.safety.request_stop()
