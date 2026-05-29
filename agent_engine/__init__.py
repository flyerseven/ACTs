"""agent_engine — A general-purpose autonomous Agent decision system.

Usage:
    from agent_engine import AgentEngine, EngineConfig, ToolRegistry
    from llm.factory import LLMAdapterFactory
    from llm.deepseek import DeepSeekAdapter

    adapter = DeepSeekAdapter(api_key="sk-...")
    engine = AgentEngine(
        llm=adapter,
        config=EngineConfig(),
    )
    engine.tools.register_from_func(my_tool)
    state = await engine.run("Your goal")
"""
__version__ = "0.1.0"

from agent_engine.engine import AgentEngine
from agent_engine.config import EngineConfig
from agent_engine.tools import ToolRegistry, ToolDef
from agent_engine.state import StateManager
from agent_engine.memory import MemoryManager
from agent_engine.reflect import Reflector, Reflection
from agent_engine.observe import Observer, Event
from agent_engine.safety import SafetyChecker
from agent_engine.types import (
    ToolCall,
    Step,
    AgentState,
    Message,
)

__all__ = [
    "AgentEngine",
    "EngineConfig",
    "ToolRegistry",
    "ToolDef",
    "StateManager",
    "MemoryManager",
    "Reflector",
    "Reflection",
    "Observer",
    "Event",
    "SafetyChecker",
    "ToolCall",
    "Step",
    "AgentState",
    "Message",
]
