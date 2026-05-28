"""Tests for agent_engine.safety."""
import pytest
from agent_engine.safety import SafetyChecker
from agent_engine.state import StateManager
from agent_engine.types import Step


class TestSafetyChecker:
    def test_defaults(self):
        sc = SafetyChecker()
        assert sc.max_steps == 50
        assert sc.tool_whitelist is None
        assert "exec" in sc.confirm_sensitive

    def test_should_stop_max_steps(self):
        sc = SafetyChecker(max_steps=3)
        sm = StateManager()
        sm.start("goal")
        for i in range(3):
            sm.add_step(Step(index=i, phase="think"))
        assert sc.should_stop(sm.state) is True

    def test_should_not_stop_under_limit(self):
        sc = SafetyChecker(max_steps=10)
        sm = StateManager()
        sm.start("goal")
        sm.add_step(Step(index=0, phase="think"))
        assert sc.should_stop(sm.state) is False

    def test_stop_requested(self):
        sc = SafetyChecker()
        sm = StateManager()
        sm.start("goal")
        sc.request_stop()
        assert sc.should_stop(sm.state) is True

    def test_error_loop_detection(self):
        sc = SafetyChecker()
        sm = StateManager()
        sm.start("goal")
        for i in range(5):
            sm.add_step(Step(index=i, phase="think"))
            sm.record_error("same error")
        assert sc.should_stop(sm.state) is True

    def test_tool_whitelist_allows(self):
        sc = SafetyChecker(tool_whitelist={"search", "calc"})
        assert sc.check_tool("search", {}) is True
        assert sc.check_tool("calc", {}) is True

    def test_tool_whitelist_blocks(self):
        sc = SafetyChecker(tool_whitelist={"search"})
        assert sc.check_tool("exec", {}) is False

    def test_whitelist_none_allows_all(self):
        sc = SafetyChecker(tool_whitelist=None)
        assert sc.check_tool("anything", {}) is True

    def test_sensitive_tool_detection(self):
        sc = SafetyChecker()
        assert sc.is_sensitive("exec") is True
        assert sc.is_sensitive("search") is False

    def test_before_action_hook(self):
        sc = SafetyChecker()
        calls = []

        def hook(name, args):
            calls.append((name, args))
            return True

        sc.before_action(hook)
        assert sc._run_hooks("before_action", "search", {"q": "test"}) is True
        assert len(calls) == 1

    def test_before_action_hook_blocks(self):
        sc = SafetyChecker()

        def blocker(name, args):
            return False

        sc.before_action(blocker)
        assert sc._run_hooks("before_action", "exec", {}) is False

    def test_after_action_hook(self):
        sc = SafetyChecker()
        calls = []

        def hook(name, result, error):
            calls.append((name, error))
            return True

        sc.after_action(hook)
        assert sc._run_hooks("after_action", "search", "result", None) is True
        assert len(calls) == 1
