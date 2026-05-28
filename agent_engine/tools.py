"""Tool registry for the Agent decision engine.

Manages tool registration, discovery, parameter validation, and
execution with timeout/retry support. Tools can be registered as
ToolDef objects, Python functions (auto-inferred schema), or
OpenAI Function Calling format.
"""
from __future__ import annotations

import asyncio
import inspect
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger

from agent_engine.types import ToolCall, ToolDef


class ToolRegistry:
    """Registry of tools the agent can call.

    Supports three registration paths:
    1. register(ToolDef) -- full definition
    2. register_from_func(func) -- auto-infer from type hints + docstring
    3. register_from_openai(schema, func) -- OpenAI Function Calling format
    """

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    # -- Registration --

    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def register_from_func(self, func: Callable, name: str = "", description: str = "", **overrides) -> None:
        tool_name = name or func.__name__
        schema = self._infer_schema_from_func(func)
        if description:
            schema["description"] = description
        is_async = inspect.iscoroutinefunction(func)

        self.register(ToolDef(
            name=tool_name,
            description=schema.get("description", ""),
            parameters={"type": "object", "properties": schema.get("properties", {}),
                        "required": schema.get("required", [])},
            func=func,
            is_async=is_async,
            **overrides,
        ))

    def register_from_openai(self, schema: dict, func: Callable) -> None:
        func_def = schema if "name" in schema else schema.get("function", schema)
        name = func_def["name"]
        is_async = inspect.iscoroutinefunction(func)
        self.register(ToolDef(
            name=name,
            description=func_def.get("description", ""),
            parameters=func_def.get("parameters", {"type": "object", "properties": {}}),
            func=func,
            is_async=is_async,
        ))

    def unregister(self, name: str) -> None:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        del self._tools[name]
        logger.debug(f"Unregistered tool: {name}")

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def get_tool(self, name: str) -> ToolDef:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        return self._tools[name]

    def list_openai_schemas(self) -> list[dict]:
        schemas = []
        for t in self._tools.values():
            schemas.append({
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            })
        return schemas

    async def call(self, name: str, arguments: dict) -> ToolCall:
        tool = self.get_tool(name)
        tc = ToolCall(
            id=f"call_{int(time.time() * 1000)}",
            tool_name=name,
            arguments=arguments,
            started_at=datetime.now(timezone.utc),
        )

        last_error: str | None = None
        for attempt in range(tool.max_retries + 1):
            try:
                if tool.is_async:
                    result = await asyncio.wait_for(
                        tool.func(**arguments),
                        timeout=tool.timeout_sec,
                    )
                else:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(tool.func, **arguments),
                        timeout=tool.timeout_sec,
                    )

                tc.result = result
                tc.finished_at = datetime.now(timezone.utc)
                tc.duration_ms = (tc.finished_at - tc.started_at).total_seconds() * 1000
                tc.retry_count = attempt
                logger.info(f"Tool '{name}' succeeded (attempt {attempt + 1}, {tc.duration_ms:.0f}ms)")
                return tc

            except asyncio.TimeoutError:
                last_error = f"Tool '{name}' timeout after {tool.timeout_sec}s"
                logger.warning(f"{last_error} (attempt {attempt + 1})")
            except Exception as e:
                last_error = f"Tool '{name}' error: {e}"
                logger.warning(f"{last_error} (attempt {attempt + 1})")

        tc.error = last_error
        tc.finished_at = datetime.now(timezone.utc)
        tc.duration_ms = (tc.finished_at - tc.started_at).total_seconds() * 1000
        tc.retry_count = tool.max_retries
        return tc

    @staticmethod
    def _infer_schema_from_func(func: Callable) -> dict:
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""

        param_descriptions: dict[str, str] = {}
        for match in re.finditer(r":param\s+(\w+)\s*:\s*(.+?)(?:\n|$)", doc):
            param_descriptions[match.group(1)] = match.group(2).strip()

        description = doc.split("\n")[0].strip() if doc else ""

        type_map = {
            str: "string", int: "integer", float: "number",
            bool: "boolean", list: "array", dict: "object",
        }

        properties: dict[str, dict] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            param_type = "string"
            if param.annotation is not inspect.Parameter.empty:
                param_type = type_map.get(param.annotation, "string")
            properties[param_name] = {
                "type": param_type,
                "description": param_descriptions.get(param_name, ""),
            }
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "description": description,
            "properties": properties,
            "required": required,
        }
