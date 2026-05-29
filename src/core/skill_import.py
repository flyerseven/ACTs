"""Skill import adapters for converting external formats into ACTs' internal
SKILL.md format.

Supported source formats:
- OpenAI Function / Tool  (JSON)
- LangChain BaseTool      (Python class)
- Custom YAML Skill       (already close to internal format)
"""

from __future__ import annotations

import ast
import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from core.skill import Skill, write_skill_md

# ── Base adapter ───────────────────────────────────────────────────────────


class SkillImportAdapter(ABC):
    """ABC for format-specific import adapters."""

    name: str = "base"  # Display name of this adapter

    @abstractmethod
    def detect(self, source: str) -> bool:
        """Return True if `source` is in this adapter's format."""
        ...

    @abstractmethod
    def parse(self, source: str) -> Skill:
        """Parse `source` into a Skill. Assumes detect() already passed."""
        ...

    def import_and_save(self, source: str, skills_dir: Path) -> Path:
        """Parse and persist to `skills_dir/<name>/SKILL.md`. Returns the path."""
        skill = self.parse(source)
        target_dir = skills_dir / _safe_dirname(skill.name)
        return write_skill_md(skill, target_dir)


# ── Adapters registry ─────────────────────────────────────────────────────

def _get_all_adapters() -> list[SkillImportAdapter]:
    return [
        OpenAIFunctionAdapter(),
        LangChainToolAdapter(),
        YamlSkillAdapter(),
    ]


def detect_and_import(source: str, skills_dir: Path) -> Skill | None:
    """Auto-detect format, parse, and save. Returns the Skill on success, None if
    no adapter can handle the source."""
    for adapter in _get_all_adapters():
        if adapter.detect(source):
            adapter.import_and_save(source, skills_dir)
            return adapter.parse(source)
    return None


def detect_format(source: str) -> str:
    """Return the format name of `source`, or 'unknown'."""
    for adapter in _get_all_adapters():
        if adapter.detect(source):
            return adapter.name
    return "unknown"


def import_from_file(filepath: Path, skills_dir: Path) -> Skill | None:
    """Read a file and import it into the skills directory."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return None

    for adapter in _get_all_adapters():
        if adapter.detect(source):
            return adapter.parse(source)
    return None


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_dirname(name: str) -> str:
    """Convert a skill name to a safe directory name."""
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-").lower() or "unnamed-skill"


def _params_to_markdown(params: dict | None) -> str:
    """Render JSON Schema parameters as a readable Markdown block."""
    if not params or "properties" not in params:
        return ""
    required: set[str] = set(params.get("required", []))
    lines = ["**Parameters:**", ""]
    for prop_name, prop_schema in sorted(params["properties"].items()):
        ptype = prop_schema.get("type", "any")
        req = "required" if prop_name in required else "optional"
        desc = prop_schema.get("description", "")
        enum = prop_schema.get("enum")
        lines.append(f"- `{prop_name}` ({ptype}, {req}) — {desc}")
        if enum:
            lines.append(f"  Allowed values: {', '.join(repr(e) for e in enum)}")
    return "\n".join(lines)


# ── OpenAI Function adapter ────────────────────────────────────────────────


class OpenAIFunctionAdapter(SkillImportAdapter):
    name = "openai_function"

    def detect(self, source: str) -> bool:
        source = source.strip()
        if not source:
            return False
        try:
            data = json.loads(source)
        except json.JSONDecodeError:
            return False
        return self._is_function_def(data) or self._is_tool_def(data) or self._is_function_list(data)

    def parse(self, source: str) -> Skill:
        data = json.loads(source.strip())

        # Normalize to a list of function dicts
        funcs: list[dict] = []
        if isinstance(data, list):
            funcs = data
        elif self._is_tool_def(data):
            funcs = [data["function"]]
        elif self._is_function_def(data):
            funcs = [data]

        primary = funcs[0]
        name = primary.get("name", "unnamed-function")
        description = primary.get("description", "")
        params = primary.get("parameters")

        # Build prompt extension
        parts = [f"## {name}", "", description]
        params_md = _params_to_markdown(params)
        if params_md:
            parts.extend(["", params_md])

        return Skill(
            name=name,
            description=description,
            type="imported",
            prompt_extension="\n".join(parts),
            source_format="openai_function",
            tool_definitions=funcs,
        )

    @staticmethod
    def _is_function_def(data: Any) -> bool:
        return isinstance(data, dict) and "name" in data

    @staticmethod
    def _is_tool_def(data: Any) -> bool:
        return isinstance(data, dict) and "function" in data and isinstance(data["function"], dict)

    @staticmethod
    def _is_function_list(data: Any) -> bool:
        return isinstance(data, list) and all(
            isinstance(d, dict) and "name" in d for d in data
        )


# ── LangChain BaseTool adapter ─────────────────────────────────────────────


class LangChainToolAdapter(SkillImportAdapter):
    name = "langchain_tool"

    # Patterns to detect LangChain tools
    _BASE_CLASSES = {"BaseTool", "StructuredTool", "Tool", "BaseModel"}
    _LANGCCHAIN_IMPORTS = {"langchain", "langchain_core", "langchain_community"}

    def detect(self, source: str) -> bool:
        source = source.strip()
        if not source or "class " not in source:
            return False
        # Must import from a langchain package OR inherit from known base classes
        has_langchain_import = any(
            f"from {pkg}" in source or f"import {pkg}" in source
            for pkg in self._LANGCCHAIN_IMPORTS
        )
        if has_langchain_import:
            return True
        # Check for inheritance from known base classes
        for base in self._BASE_CLASSES:
            if re.search(rf"class\s+\w+\s*\([^)]*\b{base}\b", source):
                return True
        return False

    def parse(self, source: str) -> Skill:
        tree = ast.parse(source)

        name = "unnamed-tool"
        description = ""
        args_schema: dict[str, Any] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Try class name
                if name == "unnamed-tool":
                    name = _to_snake_case(node.name)

                # Scan class body for name, description, args_schema assignments
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                if target.id == "name" and isinstance(item.value, ast.Constant):
                                    name = item.value.value
                                elif target.id == "description" and isinstance(item.value, ast.Constant):
                                    description = item.value.value
                                elif target.id == "args_schema" and isinstance(item.value, ast.Name):
                                    args_schema["_ref"] = item.value.id

                # Scan _run method signature
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "_run":
                        args_schema = self._extract_run_signature(item)
                        if not description and isinstance(item.body, list):
                            docstring = ast.get_docstring(item)
                            if docstring:
                                description = docstring.strip()

        parts = [f"## {name}", "", description]
        if args_schema:
            params_md = self._args_to_markdown(args_schema)
            if params_md:
                parts.extend(["", params_md])

        return Skill(
            name=name,
            description=description,
            type="imported",
            prompt_extension="\n".join(parts),
            source_format="langchain_tool",
        )

    def _extract_run_signature(self, func: ast.FunctionDef) -> dict[str, Any]:
        """Extract parameter info from a `_run(self, ...)` method signature."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        args = func.args
        all_args = args.args + args.posonlyargs + args.kwonlyargs
        defaults_map: dict[str, Any] = {}

        # Map defaults to their parameter names (defaults align with the last N args)
        num_defaults = len(args.defaults)
        if num_defaults > 0:
            for i, default in enumerate(args.defaults):
                param_index = len(args.args) - num_defaults + i
                if param_index < len(args.args):
                    param_name = args.args[param_index].arg
                    if isinstance(default, ast.Constant):
                        defaults_map[param_name] = default.value

        for arg in all_args:
            if arg.arg == "self":
                continue
            annotation = "string"
            if arg.annotation:
                anno_str = ast.unparse(arg.annotation) if hasattr(ast, "unparse") else ast.dump(arg.annotation)
                annotation = anno_str
            properties[arg.arg] = {"type": annotation}
            if arg.arg not in defaults_map:
                required.append(arg.arg)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _args_to_markdown(self, args_schema: dict) -> str:
        if "_ref" in args_schema:
            ref = args_schema["_ref"]
            return f"**Args schema:** `{ref}` (Pydantic model)"
        return _params_to_markdown(args_schema)


# ── YAML Skill adapter ────────────────────────────────────────────────────


class YamlSkillAdapter(SkillImportAdapter):
    name = "yaml_skill"

    def detect(self, source: str) -> bool:
        source = source.strip()
        if not source or not source.startswith(("name:", "#", "---")):
            return False
        try:
            import yaml
            data = yaml.safe_load(source)
            return isinstance(data, dict) and "name" in data
        except Exception:
            return False

    def parse(self, source: str) -> Skill:
        import yaml

        data = yaml.safe_load(source) or {}
        name = data.get("name", "unnamed-skill")
        description = data.get("description", "")
        prompt_ext = data.get("prompt_extension", "")

        if prompt_ext:
            parts = [f"## {name}", "", description, "", prompt_ext]
        else:
            parts = [f"## {name}", "", description]

        return Skill(
            name=name,
            description=description,
            type=data.get("type", "imported"),
            prompt_extension="\n".join(parts),
            source_format="yaml",
        )


# ── Helpers ────────────────────────────────────────────────────────────────

def _to_snake_case(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    return re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s).lower()
