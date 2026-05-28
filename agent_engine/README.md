# Agent Engine

A general-purpose autonomous Agent decision system. Provide goals, and the Agent autonomously plans tasks, calls tools, executes actions, reflects on results, and adjusts strategy until completion.

**Key features:**
- OBSERVE->THINK->ACT->REFLECT decision loop
- Dynamic tool registration (Python functions or OpenAI schema)
- Short-term memory with automatic summarization
- Periodic self-reflection with loop detection
- Safety controls: step limits, tool whitelists, hooks
- Structured logging, event callbacks, Mermaid flowcharts
- Built-in tools: calculator, file I/O, web search, code execution

## Installation

```bash
pip install -e .
```

Or install manually:

```bash
pip install pydantic loguru python-dotenv httpx pydantic-settings
```

Optional dependencies:

```bash
pip install requests  # for builtin web_search tool
```

## Quick Start

```python
import asyncio
from agent_engine import AgentEngine, EngineConfig
from agent_engine.llm import OpenAIAdapter

async def main():
    engine = AgentEngine(
        llm=OpenAIAdapter(api_key="sk-...", model="gpt-4o"),
        config=EngineConfig(max_steps=10),
    )

    # Register custom tools
    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        return f"Weather in {city}: Sunny, 22 C"

    engine.tools.register_from_func(get_weather)

    state = await engine.run("What's the weather in Tokyo and should I bring an umbrella?")

    print(f"Status: {state.status}")
    print(f"Steps taken: {len(state.steps)}")
    for step in state.steps:
        print(f"  Step {step.index}: [{step.phase}] {step.thought[:60]}...")

asyncio.run(main())
```

## CLI Usage

```bash
# Run with a goal
agent-engine run "Find the top 3 Python web frameworks and compare them" --api-key sk-xxx

# Save state and Mermaid diagram
agent-engine run "Analyze data.csv" --api-key sk-xxx --output state.json --mermaid flow.mmd

# List available tools
agent-engine tools

# Visualize a saved state
agent-engine visualize state.json --output flow.mmd
```

## Architecture

```
AgentEngine.run(goal)
  |
  +-- StateManager     -- tracks goal, steps, errors, metrics
  +-- MemoryManager    -- manages conversation messages + summarization
  +-- ToolRegistry     -- registers and executes tools
  +-- Reflector        -- periodic self-reflection, loop detection
  +-- SafetyChecker    -- step limits, tool whitelist, hooks
  +-- Observer         -- logging, callbacks, Mermaid, reports
  +-- LLMAdapter       -- OpenAI-compatible or custom callback
```

## Configuration

All settings can be configured via `EngineConfig` or environment variables (prefixed with `AGENT_ENGINE_`):

| Parameter | Env Var | Default |
|-----------|---------|---------|
| max_steps | `AGENT_ENGINE_MAX_STEPS` | 50 |
| reflect_interval | `AGENT_ENGINE_REFLECT_INTERVAL` | 3 |
| openai_api_key | `AGENT_ENGINE_OPENAI_API_KEY` | "" |
| openai_model | `AGENT_ENGINE_OPENAI_MODEL` | gpt-4o |
| log_format | `AGENT_ENGINE_LOG_FORMAT` | text |

## Extending

### Custom Tools

```python
# From Python function (auto-infer schema)
engine.tools.register_from_func(my_function)

# From OpenAI schema
engine.tools.register_from_openai(schema_dict, handler_function)

# Explicit ToolDef
engine.tools.register(ToolDef(name="...", description="...", parameters={...}, func=...))
```

### Custom LLM Backend

```python
from agent_engine.llm import LLMAdapter, LLMResponse

class MyAdapter(LLMAdapter):
    async def chat(self, messages, tools=None):
        # Call your LLM here
        return LLMResponse(content="response")
```

### Safety Hooks

```python
engine.safety.before_action(lambda name, args: args.get("path") != "/etc/passwd")
engine.safety.after_action(lambda name, result, error: True)
```

## License

MIT
