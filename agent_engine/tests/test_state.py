"""Tests for agent_engine.state."""
import pytest
from agent_engine.state import StateManager
from agent_engine.types import Step


class TestStateManager:
    def test_initial_state(self):
        sm = StateManager()
        assert sm.state.status == "idle"
        assert sm.state.goal == ""

    def test_start(self):
        sm = StateManager()
        sm.start("test goal")
        assert sm.state.status == "running"
        assert sm.state.goal == "test goal"
        assert sm.state.started_at is not None

    def test_cannot_start_twice(self):
        sm = StateManager()
        sm.start("goal")
        with pytest.raises(RuntimeError, match="already running"):
            sm.start("other")

    def test_pause_resume(self):
        sm = StateManager()
        sm.start("goal")
        sm.pause()
        assert sm.state.status == "paused"
        sm.resume()
        assert sm.state.status == "running"

    def test_cannot_pause_when_idle(self):
        sm = StateManager()
        with pytest.raises(RuntimeError, match="not running"):
            sm.pause()

    def test_stop(self):
        sm = StateManager()
        sm.start("goal")
        sm.stop("done")
        assert sm.state.status == "done"
        assert sm.state.finished_at is not None

    def test_add_step(self):
        sm = StateManager()
        sm.start("goal")
        step = Step(index=0, phase="think", thought="let me think")
        sm.add_step(step)
        assert len(sm.state.steps) == 1
        assert sm.state.current_step_index == 1

    def test_get_last_n_steps(self):
        sm = StateManager()
        sm.start("goal")
        for i in range(5):
            sm.add_step(Step(index=i, phase="think"))
        last3 = sm.get_last_n_steps(3)
        assert len(last3) == 3
        assert last3[0].index == 2
        assert last3[-1].index == 4

    def test_record_error(self):
        sm = StateManager()
        sm.start("goal")
        sm.record_error("something went wrong")
        assert len(sm.state.errors) == 1

    def test_error_deduplication(self):
        sm = StateManager()
        sm.start("goal")
        sm.record_error("timeout")
        sm.record_error("timeout")
        sm.record_error("timeout")
        assert len(sm.state.errors) == 1  # deduplicated

    def test_sub_goals(self):
        sm = StateManager()
        sm.start("main goal")
        sm.set_sub_goals(["step 1", "step 2", "step 3"])
        assert sm.state.sub_goals == ["step 1", "step 2", "step 3"]
        sm.complete_sub_goal(0)
        assert len(sm.state.sub_goals) == 3

    def test_to_dict_from_dict(self):
        sm = StateManager()
        sm.start("goal")
        sm.add_step(Step(index=0, phase="think", thought="test"))
        data = sm.to_dict()
        restored = StateManager.from_dict(data)
        assert restored.state.goal == "goal"
        assert len(restored.state.steps) == 1

    def test_metrics_update(self):
        sm = StateManager()
        sm.start("goal")
        sm.update_metrics(tool_calls=5, tokens_used=1000)
        assert sm.state.metrics["tool_calls"] == 5
        assert sm.state.metrics["tokens_used"] == 1000
        sm.update_metrics(tool_calls=3)  # accumulates
        assert sm.state.metrics["tool_calls"] == 8
