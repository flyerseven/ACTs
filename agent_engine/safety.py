"""Safety checker for the Agent decision engine.

Enforces step limits, tool whitelists, sensitive operation detection,
and provides before/after action hooks for extensible safety policies.
"""
from __future__ import annotations

from typing import Any, Callable

from loguru import logger

from agent_engine.types import AgentState


class SafetyChecker:
    """Enforces safety constraints on the agent's behavior.

    Built-in checks:
    - max_steps: hard limit on total loop iterations
    - tool_whitelist: optional allowlist for tool names
    - confirm_sensitive: tools that should require external confirmation
    - stop_requested: emergency stop flag
    - error_loop: same error repeated 5+ times

    Extensible via before_action / after_action hooks.
    """

    def __init__(
        self,
        max_steps: int = 50,
        tool_whitelist: set[str] | None = None,
        confirm_sensitive: set[str] | None = None,
    ):
        self.max_steps = max_steps
        self.tool_whitelist = tool_whitelist
        self.confirm_sensitive = confirm_sensitive or {"exec", "shell", "file_delete", "code_exec"}
        self.stop_requested = False
        self._before_hooks: list[Callable] = []
        self._after_hooks: list[Callable] = []

    # -- Core checks --

    def should_stop(self, state: AgentState) -> bool:
        """Check if the agent should stop."""
        if self.stop_requested:
            logger.info("Stop requested by user")
            return True

        if state.current_step_index >= self.max_steps:
            logger.warning(f"Max steps ({self.max_steps}) reached")
            return True

        # Error loop: same error 5+ times and only one unique error
        if len(state.errors) == 1 and state.current_step_index >= 5:
            logger.warning("Error loop detected: same error repeated")
            return True

        return False

    def check_tool(self, tool_name: str, arguments: dict | None = None) -> bool:
        """Check if a tool call should be allowed."""
        if self.tool_whitelist is not None and tool_name not in self.tool_whitelist:
            logger.warning(f"Tool '{tool_name}' blocked by whitelist")
            return False
        return True

    def is_sensitive(self, tool_name: str) -> bool:
        """Check if a tool requires external confirmation."""
        return tool_name in self.confirm_sensitive

    def request_stop(self) -> None:
        """Request an emergency stop at the next iteration."""
        self.stop_requested = True
        logger.info("Emergency stop requested")

    # -- Hook system --

    def before_action(self, callback: Callable[[str, dict], bool]) -> None:
        """Register a callback invoked before each tool execution.
        Callback receives (tool_name, arguments) and should return
        True to allow or False to block.
        """
        self._before_hooks.append(callback)

    def after_action(self, callback: Callable[[str, Any, str | None], bool]) -> None:
        """Register a callback invoked after each tool execution.
        Callback receives (tool_name, result, error) and should return
        True to continue or False to abort the loop.
        """
        self._after_hooks.append(callback)

    def _run_hooks(self, hook_name: str, *args: Any) -> bool:
        """Run all registered hooks of a given type. Returns False if
        any hook returns False (blocking), True otherwise."""
        hooks = self._before_hooks if hook_name == "before_action" else self._after_hooks
        for hook in hooks:
            try:
                if not hook(*args):
                    logger.info(f"Action blocked by {hook_name} hook")
                    return False
            except Exception as e:
                logger.error(f"Hook error in {hook_name}: {e}")
        return True
