"""Tests for agent_engine.tools."""
import asyncio
import pytest
from agent_engine.tools import ToolRegistry, ToolDef


class TestToolRegistry:
    def test_register_tool_def(self):
        reg = ToolRegistry()
        td = ToolDef(name="test", description="A test", parameters={"type": "object", "properties": {}})
        reg.register(td)
        names = [t.name for t in reg.list_tools()]
        assert "test" in names

    def test_register_duplicate_raises(self):
        reg = ToolRegistry()
        td = ToolDef(name="test", description="d", parameters={})
        reg.register(td)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(td)

    def test_unregister(self):
        reg = ToolRegistry()
        td = ToolDef(name="test", description="d", parameters={})
        reg.register(td)
        reg.unregister("test")
        assert len(reg.list_tools()) == 0

    def test_unregister_nonexistent(self):
        reg = ToolRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nonexistent")

    def test_register_from_func_sync(self):
        reg = ToolRegistry()

        def add(a: int, b: int) -> int:
            """Add two numbers.

            :param a: First number
            :param b: Second number
            """
            return a + b

        reg.register_from_func(add)
        tools = reg.list_tools()
        assert len(tools) == 1
        t = tools[0]
        assert t.name == "add"
        assert t.description == "Add two numbers."
        assert "a" in t.parameters.get("properties", {})
        assert "b" in t.parameters.get("properties", {})
        assert t.is_async is False

    def test_register_from_func_async(self):
        reg = ToolRegistry()

        async def fetch(url: str) -> str:
            """Fetch a URL."""
            return "ok"

        reg.register_from_func(fetch)
        t = reg.list_tools()[0]
        assert t.name == "fetch"
        assert t.is_async is True

    def test_register_from_openai(self):
        reg = ToolRegistry()
        schema = {
            "name": "search",
            "description": "Search the web",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }

        def search_fn(query: str) -> str:
            return f"results for {query}"

        reg.register_from_openai(schema, search_fn)
        t = reg.list_tools()[0]
        assert t.name == "search"

    @pytest.mark.asyncio
    async def test_call_sync_tool(self):
        reg = ToolRegistry()

        def double(x: int) -> int:
            return x * 2

        reg.register_from_func(double)
        result = await reg.call("double", {"x": 5})
        assert result.result == 10
        assert result.error is None

    @pytest.mark.asyncio
    async def test_call_async_tool(self):
        reg = ToolRegistry()

        async def double(x: int) -> int:
            await asyncio.sleep(0.01)
            return x * 2

        reg.register_from_func(double)
        result = await reg.call("double", {"x": 5})
        assert result.result == 10

    @pytest.mark.asyncio
    async def test_call_timeout(self):
        reg = ToolRegistry()

        async def slow() -> str:
            await asyncio.sleep(10)
            return "done"

        reg.register(ToolDef(
            name="slow", description="d", parameters={},
            func=slow, is_async=True, timeout_sec=0.05, max_retries=0,
        ))
        result = await reg.call("slow", {})
        assert result.error is not None
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_call_retry(self):
        reg = ToolRegistry()
        call_count = 0

        async def flaky(x: int) -> int:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("fail")
            return x

        reg.register(ToolDef(
            name="flaky", description="d", parameters={},
            func=flaky, is_async=True, timeout_sec=5.0, max_retries=3,
        ))
        result = await reg.call("flaky", {"x": 42})
        assert result.result == 42
        assert result.retry_count == 2

    @pytest.mark.asyncio
    async def test_call_nonexistent_tool(self):
        reg = ToolRegistry()
        with pytest.raises(KeyError, match="not found"):
            await reg.call("nonexistent", {})

    def test_list_openai_schemas(self):
        reg = ToolRegistry()

        def search(query: str) -> str:
            """Search the web."""
            return "results"

        reg.register_from_func(search)
        schemas = reg.list_openai_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "search"
        assert "parameters" in schemas[0]
